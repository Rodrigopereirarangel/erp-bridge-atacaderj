# -*- coding: utf-8 -*-
"""DIAGNOSTICO (dono, 18/07): os ~708 itens SEM caixa-mae no cadastro Neogrid
(QUANTIDADE_CAIXA=1, nao-peso) — da para preencher com seguranca a partir de
OUTRAS fontes do proprio banco?

NAO altera calculo nenhum. Mede tres testemunhas independentes e conta em
quantos itens elas CONCORDAM:

  EAN     tbProdutoVenda (cadastro do PDV, cdEmpresa=10): EAN com qtVenda>1
          = codigo de barras da CAIXA (DUN-14) registrado no cadastro.
  NOTA    tbNotaItem.qtEmbalagem>1 nas entradas de 12 meses (=1 e fornecedor
          faturando em unidade — ausencia de opiniao, nao discordancia).
  PEDIDO  tbPedidoItem.qtEmbalagem>1 nos pedidos de compra de 12 meses.

Regra que o dono pediu (sem presuncao ousada): so vale proposta quando DUAS
testemunhas independentes dizem O MESMO numero (unanime em cada uma). Uma
testemunha sozinha, ou discordancia, fica SEM caixa-mae p/ ajuste manual.
Itens por PESO nem entram (ex. carne moida: NF em kg, venda em bandeja).

Uso (NO PC-PONTE):  python scripts/caixa-mae-proposta.py
"""
import csv
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
import db           # noqa: E402
import projections  # noqa: E402

# Por testemunha: 1 linha por produto com o fator DOMINANTE + quantos fatores
# distintos existem (n_fatores>1 = testemunha em conflito consigo mesma).
SQL_EAN = """
SELECT cdProduto AS codigo,
       COUNT(DISTINCT qtVenda)   AS n_fatores,
       CAST(MAX(qtVenda) AS int) AS fator,
       COUNT(*)                  AS vezes
FROM dbo.tbProdutoVenda
WHERE cdEmpresa = 10 AND qtVenda > 1 AND cdProduto IS NOT NULL
GROUP BY cdProduto
"""

SQL_NOTA = """
SELECT i.cdProduto AS codigo,
       COUNT(DISTINCT i.qtEmbalagem)   AS n_fatores,
       CAST(MAX(i.qtEmbalagem) AS int) AS fator,
       COUNT(*)                        AS vezes
FROM dbo.tbNotaItem i
JOIN dbo.tbNotaEntrada ne
  ON ne.cdNotaEntrada = i.cdNota AND ne.cdPessoaFilial = i.cdPessoaFilial
WHERE ne.dtChegada >= DATEADD(month, -12, CAST(GETDATE() AS date))
  AND i.qtEmbalagem > 1 AND i.cdProduto IS NOT NULL
GROUP BY i.cdProduto
"""

SQL_PEDIDO = """
SELECT i.cdProduto AS codigo,
       COUNT(DISTINCT i.qtEmbalagem)   AS n_fatores,
       CAST(MAX(i.qtEmbalagem) AS int) AS fator,
       COUNT(*)                        AS vezes
FROM dbo.tbPedidoItem i
JOIN dbo.tbPedido p
  ON p.cdPedido = i.cdPedido AND p.cdPessoaFilial = i.cdPessoaFilial
WHERE p.inEntrada = 1
  AND p.dtPedido >= DATEADD(month, -12, CAST(GETDATE() AS date))
  AND i.qtEmbalagem > 1 AND i.cdProduto IS NOT NULL
GROUP BY i.cdProduto
"""


def _mapa(linhas):
    return {r["codigo"]: r for r in linhas}


def _unanime(t):
    """A testemunha opinou com UMA voz? -> fator; senao None."""
    if t and t["n_fatores"] == 1:
        return t["fator"]
    return None


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    cfg = json.load(open(os.path.join(RAIZ, "config.local.json"), encoding="utf-8"))

    exp_dir = cfg["saida"].get("exposicao_dir") or os.path.join(RAIZ, "saida", "exposicao")
    populacao = []          # os "sem caixa-mae" do relatorio de exposicao
    with open(os.path.join(exp_dir, "catalogo_exposicao.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter=";"):
            if int(r["caixa_mae"]) == 1 and r.get("peso", "0") != "1":
                populacao.append({"codigo": int(r["codigo"]),
                                  "descricao": r["descricao"]})

    conn = db.conectar(cfg["db"])
    try:
        ean = _mapa(db.consultar(conn, SQL_EAN))
        nota = _mapa(db.consultar(conn, SQL_NOTA))
        pedido = _mapa(db.consultar(conn, SQL_PEDIDO))
    finally:
        conn.close()

    classes = {}
    saida = []
    for item in populacao:
        cod = item["codigo"]
        te, tn, tp = ean.get(cod), nota.get(cod), pedido.get(cod)
        fe, fn, fp = _unanime(te), _unanime(tn), _unanime(tp)
        votos = [f for f in (fe, fn, fp) if f]

        if len(set(votos)) == 1 and len(votos) >= 2:
            classe, proposta = "2+ testemunhas CONCORDAM", votos[0]
        elif len(votos) >= 2:
            classe, proposta = "testemunhas DISCORDAM", None
        elif len(votos) == 1:
            quem = "EAN" if fe else ("NOTA" if fn else "PEDIDO")
            classe, proposta = f"so 1 testemunha ({quem})", None
        elif te or tn or tp:
            classe, proposta = "testemunha em conflito interno", None
        else:
            classe, proposta = "nenhuma testemunha", None

        classes.setdefault(classe, []).append((item, votos))
        saida.append([cod, item["descricao"], proposta or "",
                      fe or "", (te or {}).get("n_fatores", 0),
                      fn or "", (tn or {}).get("vezes", 0),
                      fp or "", (tp or {}).get("vezes", 0), classe])

    caminho = os.path.join(exp_dir, "caixa_mae_proposta.csv")
    projections._escrever_atomico(caminho, projections._csv_ponto_virgula(
        ["codigo", "descricao", "caixa_proposta", "ean_fator", "ean_n_fatores",
         "nota_fator", "nota_vezes", "pedido_fator", "pedido_vezes", "classe"],
        saida))

    print(f"populacao sem caixa-mae (nao-peso): {len(populacao)}")
    for classe in sorted(classes, key=lambda c: -len(classes[c])):
        itens = classes[classe]
        print(f"\n[{len(itens):>4}] {classe}")
        for item, votos in itens[:8]:
            print(f"        {item['codigo']:>7} {item['descricao'][:52]:<52} {votos}")
    print(f"\n-> {caminho}")


if __name__ == "__main__":
    main()
