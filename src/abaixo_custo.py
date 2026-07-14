# -*- coding: utf-8 -*-
"""Relatorio diario "vendidos abaixo do custo" (WhatsApp 06:00).

Ver docs/superpowers/specs/2026-07-14-abaixo-custo-6h-design.md para o design
completo (formato exato da mensagem, guardas de execucao, calculo de markup).

Semantica valor/custo (conferida em queries.py antes de escrever o SELECT
abaixo): tbVendaPDV tem 1 linha por produto/cupom, com vlVenda e vlCusto
UNITARIOS (comentario no topo de queries.py + a query VENDAS de la, que faz
CAST(SUM(qtVenda*vlVenda)...) AS valor e CAST(SUM(qtVenda*vlCusto)...) AS
custo_venda). Ou seja: `valor` e `custo` agregados por produto/dia sao
TOTAIS do dia, nao unitarios. O SELECT deste modulo replica exatamente esse
padrao (mesmas tabelas/joins, agora filtrado a UM dia so). A partir dos
totais, a media ponderada pela quantidade e:
    venda_media = valor / qtd
    custo_medio = custo / qtd
e o markup e `venda_media / custo_medio - 1` — a mesma logica de qualquer
"preco medio do dia" (o Vl. Medio do relatorio oficial do ERP, documentado em
VENDAS_MENSAL, tambem e Venda/Qtde calculado no consumidor, nunca extraido
pronto). Validar num item conhecido contra o ERP antes do 1o envio real
(risco documentado no design doc).

Uso:
  python src/abaixo_custo.py [--dia YYYY-MM-DD] [--config caminho.json] [--dry-run]
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Mesmas tabelas/joins da query VENDAS de queries.py, agregadas por produto
# num UNICO dia (em vez de por produto+dia numa janela) — so o que este
# relatorio precisa. So SELECT (a guarda de src/db.py recusa qualquer outra
# coisa).
SQL_VENDAS_DIA = """
SELECT
    v.cdProduto                                        AS codigo,
    MAX(sp.nmProdutoPai)                               AS descricao,
    CAST(SUM(v.qtVenda) AS decimal(14,3))              AS qtd,
    CAST(SUM(v.qtVenda * v.vlVenda) AS decimal(14,2))  AS valor,
    CAST(SUM(v.qtVenda * v.vlCusto) AS decimal(14,2))  AS custo
FROM dbo.tbVendaPDV v
JOIN dbo.tbProduto p       ON p.cdProduto = v.cdProduto
JOIN dbo.tbSuperProduto sp ON sp.cdSuperProduto = p.cdSuperProduto
WHERE v.cdProduto IS NOT NULL
  AND CAST(v.dtVenda AS date) = '{dia}'
GROUP BY v.cdProduto
"""

EPS = 1e-9      # tolerancia de ponto flutuante na comparacao markup <= margemMax
CORTE = 60      # maximo de itens listados na mensagem


def dia_anterior_util(hoje):
    """Dia-alvo do relatorio: ontem, pulando domingo (loja fechada).

    hoje/retorno sao `date` (nao `datetime`). Segunda-feira -> sabado.
    """
    d = hoje - timedelta(days=1)
    if d.weekday() == 6:  # domingo
        d -= timedelta(days=1)
    return d


def _fmt_num(valor, casas=2):
    """Formata em padrao BR: virgula decimal, ponto de milhar. So para numeros >= 0."""
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def filtrar_itens(linhas, margem_max):
    """Separa as linhas cruas (uma por produto, agregadas no dia-alvo) em:

      - itens com custo cadastrado e markup <= margem_max, ordenados do pior
        markup (mais negativo) para o melhor;
      - contagem de itens sem custo cadastrado (custo nulo/0 — ficam de fora
        da lista E da conta de prejuizo, so contam no rodape).

    Devolve (itens_ordenados, n_sem_custo). Cada item da lista:
      {"descricao", "venda_media", "custo_medio", "markup", "qtd"}
    """
    itens = []
    n_sem_custo = 0
    for linha in linhas:
        qtd = float(linha.get("qtd") or 0)
        valor = float(linha.get("valor") or 0)
        custo = float(linha.get("custo") or 0)
        if qtd <= 0:
            continue
        if custo <= 0:
            n_sem_custo += 1
            continue
        venda_media = valor / qtd
        custo_medio = custo / qtd
        markup = venda_media / custo_medio - 1
        if markup <= margem_max + EPS:
            itens.append({
                "descricao": linha.get("descricao") or f"produto {linha.get('codigo')}",
                "venda_media": venda_media,
                "custo_medio": custo_medio,
                "markup": markup,
                "qtd": qtd,
            })
    itens.sort(key=lambda i: i["markup"])
    return itens, n_sem_custo


def montar_mensagem(dia_str, itens, n_sem_custo):
    """Monta o texto da mensagem (pura, sem I/O). `dia_str` ja no formato dd/MM."""
    if not itens:
        return f"✅ nenhum item vendido no/abaixo do custo em {dia_str}"

    partes = [f">Produtos vendidos abaixo do custo dia {dia_str}<"]

    exibidos = itens[:CORTE]
    for item in exibidos:
        sinal = "+" if item["markup"] >= 0 else "-"
        pct = _fmt_num(abs(item["markup"]) * 100, 1)
        linha2 = (f"venda {_fmt_num(item['venda_media'])} · "
                  f"custo {_fmt_num(item['custo_medio'])} · {sinal}{pct}%")
        partes.append(f"{item['descricao']}\n{linha2}")

    resto = len(itens) - len(exibidos)
    if resto > 0:
        partes.append(f"… e mais {resto} itens")

    prejuizo = sum(max(0.0, (i["custo_medio"] - i["venda_media"]) * i["qtd"]) for i in itens)
    rodape = f"{len(itens)} itens · prejuízo potencial R$ {_fmt_num(prejuizo)}"
    if n_sem_custo > 0:
        rodape += f"\n⚠ {n_sem_custo} itens sem custo cadastrado (fora da conta)"
    partes.append(rodape)

    return "\n\n".join(partes)


# --------------------------------------------------------------------------
# I/O: config, banco, envio. Nada acima desta linha toca banco/arquivo/rede.
# --------------------------------------------------------------------------

def carregar_config(caminho):
    """Mesmo padrao de src/bridge.py:carregar_config (sem merge com o example;
    config.local.json e o arquivo completo, gitignored, com a senha)."""
    if caminho is None:
        caminho = os.path.join(RAIZ, "config.local.json")
    if not os.path.exists(caminho):
        raise SystemExit(
            f"[ERRO] Config nao encontrada: {caminho}\n"
            f"       Copie config.example.json para config.local.json e preencha."
        )
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolver_node():
    """Task Scheduler roda sem o PATH do usuario (mesmo problema documentado
    em auditoria-16h.ps1/register-tasks.ps1) — tenta os caminhos reais primeiro."""
    candidatos = [
        os.path.join(os.environ.get("ProgramFiles", ""), "nodejs", "node.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "nodejs", "node.exe"),
    ]
    for c in candidatos:
        if c and os.path.exists(c):
            return c
    return "node"


def main():
    ap = argparse.ArgumentParser(
        description="Relatorio diario 'abaixo do custo' (markup <= margemMax) via WhatsApp")
    ap.add_argument("--dia", default=None, help="YYYY-MM-DD (default: dia anterior util)")
    ap.add_argument("--config", default=None, help="caminho do config (default: config.local.json)")
    ap.add_argument("--dry-run", action="store_true", help="monta e imprime, nao envia")
    args = ap.parse_args()

    if args.dia:
        dia_dt = datetime.strptime(args.dia, "%Y-%m-%d").date()
    else:
        dia_dt = dia_anterior_util(datetime.now().date())
    dia_ymd = dia_dt.strftime("%Y-%m-%d")
    dia_ddmm = dia_dt.strftime("%d/%m")

    saida_dir = os.path.join(RAIZ, "saida", "abaixo-custo")
    carimbo = os.path.join(saida_dir, f"enviado-{dia_ymd}.txt")

    # guarda 1: idempotencia — ja enviado para este dia
    if os.path.exists(carimbo):
        print(f"[abaixo-custo] carimbo ja existe para {dia_ymd} — nada a fazer.")
        sys.exit(0)

    cfg = carregar_config(args.config)
    cfg_ac = cfg.get("abaixo_custo") or {}
    numero = cfg_ac.get("numero")
    margem_max = cfg_ac.get("margemMax", 0.03)

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import db  # noqa: E402 — so precisa de pyodbc/pymysql quando de fato consulta o banco

    conn = db.conectar(cfg["db"])
    try:
        linhas = db.consultar(conn, SQL_VENDAS_DIA.format(dia=dia_ymd))
    finally:
        conn.close()

    # guarda 2: ERP sem NENHUMA venda no dia-alvo (atraso de sync das manhas)
    # -> silencioso, o retry as 06:30/07:00/... pega quando o sync chegar.
    if not linhas:
        sys.exit(0)

    itens, n_sem_custo = filtrar_itens(linhas, float(margem_max))
    texto = montar_mensagem(dia_ddmm, itens, n_sem_custo)

    if args.dry_run:
        print(texto)
        sys.exit(0)

    if not numero:
        print("[abaixo-custo] AVISO: config.local.json sem abaixo_custo.numero — nao enviado.",
              file=sys.stderr)
        sys.exit(1)

    os.makedirs(saida_dir, exist_ok=True)
    tmp = os.path.join(saida_dir, f".tmp-envio-{dia_ymd}.txt")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(texto)
    try:
        wa_dir = os.path.join(RAIZ, "scripts", "whatsapp")
        r = subprocess.run(
            [_resolver_node(), "enviar.mjs", "--para", numero, "--texto-arquivo", tmp],
            cwd=wa_dir,
        )
        if r.returncode != 0:
            sys.exit(f"[ERRO] enviar.mjs saiu com codigo {r.returncode}")
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass

    # guarda 3 (fim): grava o carimbo com a mensagem enviada dentro (auditoria)
    with open(carimbo, "w", encoding="utf-8") as f:
        f.write(texto)
    print(f"[abaixo-custo] enviado para {numero} ({dia_ddmm}): {len(itens)} itens.")


if __name__ == "__main__":
    main()
