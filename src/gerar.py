# -*- coding: utf-8 -*-
"""Le os 4 CSVs do bridge + estado de ruas do deposito e escreve o HTML.

Manual por enquanto (decisao do dono 22/07: SEM tarefa agendada ate ele
validar os numeros). Falha de insumo -> exit 1 e o HTML anterior fica."""
import argparse
import csv
import glob
import json
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import formato      # noqa: E402
import fornecedor   # noqa: E402
import minimo       # noqa: E402
import relatorio    # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ler_csv(caminho):
    with open(caminho, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


def _ler_ruas(caminho):
    """Estado do deposito: {"15450": {"rua": 13, ...}} ou {"15450": 13}.
    Insumo OPCIONAL: ausente OU ilegivel -> sem corredor (aviso no log)."""
    if not caminho:
        return {}
    if not os.path.exists(caminho):
        print(f"AVISO: estado de ruas nao encontrado em {caminho} - "
              "corredor sai vazio (confira ruas_estado_json no config)",
              file=sys.stderr)
        return {}
    try:
        with open(caminho, encoding="utf-8") as f:
            bruto = json.load(f)
    except (OSError, ValueError) as e:
        print(f"AVISO: estado de ruas ilegivel ({e}) - corredor sai vazio",
              file=sys.stderr)
        return {}
    ruas = {}
    for cod, v in bruto.items():
        rua = v.get("rua") if isinstance(v, dict) else v
        if isinstance(rua, int):
            ruas[int(cod)] = rua
    return ruas


def _ler_ruptura(rounds_dir, hoje):
    """Codigos em POSSIVEL RUPTURA na ultima rodada do detector-estoque
    (dono, 22/07). MESMA regra do quadrante do painel (erp-bridge
    historico_painel.corte_ruptura / template — manter em sincronia):
    probabilidade > 0.75, parado > 1 dia, e guardrail (entrega ha <=30d
    com cobertura sobrando nao conta). Insumo OPCIONAL: ausente ou
    ilegivel -> sem alertas (aviso no log), nunca derruba."""
    if not rounds_dir:
        return set()
    if not os.path.isdir(rounds_dir):
        print(f"AVISO: rounds do detector nao encontrados em {rounds_dir}"
              " - relatorio sai sem alerta de ruptura", file=sys.stderr)
        return set()
    arquivos = sorted(glob.glob(os.path.join(rounds_dir, "*.json")))
    if not arquivos:
        print("AVISO: nenhuma rodada do detector em"
              f" {rounds_dir} - sem alerta de ruptura", file=sys.stderr)
        return set()
    try:
        with open(arquivos[-1], encoding="utf-8") as f:
            rodada = json.load(f)
    except (OSError, ValueError) as e:
        print(f"AVISO: rodada do detector ilegivel ({e}) - sem alerta de"
              " ruptura", file=sys.stderr)
        return set()
    codigos = set()
    for i in rodada.get("items", []):
        if (i.get("probabilidade") or 0) <= 0.75:
            continue
        if (i.get("diasParado") or 0) <= 1:
            continue
        data = str((i.get("receipt") or {}).get("date") or "")[:10]
        if data:
            try:
                entrega_dias = (hoje - date.fromisoformat(data)).days
            except ValueError:
                entrega_dias = None
            if (entrega_dias is not None and entrega_dias <= 30
                    and (i.get("coverageRemaining") or 0) > 0):
                continue
        try:
            codigos.add(int(i.get("codigo")))
        except (TypeError, ValueError):
            continue
    return codigos


def main():
    ap = argparse.ArgumentParser(description="Listagem por fornecedor (HTML)")
    ap.add_argument("--config", default=os.path.join(RAIZ, "config.local.json"))
    args = ap.parse_args()
    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    ent = cfg["entrada"]

    cat = _ler_csv(ent["catalogo_csv"])
    vendas_rows = _ler_csv(ent["vendas_csv"])
    entradas = [{"codigo": int(r["codigo"]), "data": r["data"],
                 "fornecedor": r["fornecedor"], "qtd": float(r["qtd"])}
                for r in _ler_csv(ent["entradas_csv"])]
    negociacoes = [{"codigo": int(r["codigo"]), "fornecedor": r["fornecedor"],
                    "dt_alteracao": r["dt_alteracao"]}
                   for r in _ler_csv(ent["negociacao_csv"])]
    ruas = _ler_ruas(ent.get("ruas_estado_json"))
    em_ruptura = _ler_ruptura(ent.get("ruptura_rounds_dir"), date.today())

    vendas_por_cod = {}
    datas = []
    for r in vendas_rows:
        cod = int(r["codigo"])
        vendas_por_cod.setdefault(cod, {})[r["data"]] = \
            vendas_por_cod.get(cod, {}).get(r["data"], 0.0) + float(r["qtd_vendida"])
        datas.append(r["data"])
    fim = date.fromisoformat(max(datas)) if datas else date.today()

    mapa_forn = fornecedor.atribuir(negociacoes, entradas)

    por_fornecedor = {}
    for p in cat:
        if str(p.get("ativo")) != "1":
            continue
        cod = int(p["codigo"])
        unidades, marca = minimo.calcular(
            vendas_por_cod.get(cod, {}), fim, p.get("curva") or None)
        # mediana zero so acontece no fallback com ruptura (janela limpa
        # exige venda) — "0 un" leria como recomendacao de estoque zero;
        # caso real 22/07: cervejas C12 com 2-4 vendas em 180d (dono)
        if unidades == 0 and marca == "*":
            unidades, marca = None, "ruptura_cronica"
        embalagem = float(p["embalagem"]) if p.get("embalagem") else None
        peso = str(p.get("peso")) == "1"
        rua = ruas.get(cod)
        linha = {"codigo": cod, "nome": p["descricao"],
                 "curva": p.get("curva") or "", "rua": rua,
                 "rua_rotulo": formato.rotulo_rua(rua),
                 # unidades por caixa-mae; sem caixa (ou balanca) = 1 (dono)
                 "cx_mae": int(embalagem) if embalagem and embalagem > 1 else 1,
                 "minimo": formato.exibir(unidades, embalagem, peso),
                 "marca": marca,
                 "ruptura": cod in em_ruptura}
        nome_forn = mapa_forn.get(cod, fornecedor.SEM_FORNECEDOR)
        por_fornecedor.setdefault(nome_forn, []).append(linha)

    dados_de = datetime.fromtimestamp(
        os.path.getmtime(ent["vendas_csv"])).strftime("%d/%m/%Y %H:%M")
    html = relatorio.montar(relatorio.preparar(por_fornecedor), dados_de)

    destino = cfg["saida_html"]
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    tmp = destino + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, destino)
    alertas = sum(1 for v in por_fornecedor.values()
                  for ln in v if ln["ruptura"])
    print(f"OK: {destino} ({sum(len(v) for v in por_fornecedor.values())} "
          f"produtos, {len(por_fornecedor)} fornecedores, "
          f"{alertas} com alerta de ruptura, dados de {dados_de})")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:                      # noqa: BLE001
        import traceback
        print(f"[ERRO] listagem NAO gerada (a anterior fica): {e}",
              file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
