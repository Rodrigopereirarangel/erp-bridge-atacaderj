# -*- coding: utf-8 -*-
"""Ad-hoc (18/07, pedido do dono): p/ os itens SEM caixa-mae (caixa_origem=
'verificar' no catalogo da exposicao), listar os EANs de caixa do PDV
(tbProdutoVenda qtVenda>1) — o dono quer julgar A OLHO se da p/ aproveitar
(a fonte foi reprovada na media: 51% no gabarito, qtVenda=12 e default)."""
import csv
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
import db  # noqa: E402

SQL = """
SELECT cdProduto AS codigo, cdEAN AS ean, CAST(qtVenda AS int) AS qt
FROM dbo.tbProdutoVenda
WHERE cdEmpresa = 10 AND qtVenda > 1 AND cdProduto IS NOT NULL
ORDER BY cdProduto, qtVenda, cdEAN
"""


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    cfg = json.load(open(os.path.join(RAIZ, "config.local.json"), encoding="utf-8"))
    exp_dir = cfg["saida"].get("exposicao_dir") or os.path.join(RAIZ, "saida", "exposicao")

    alvo = {}
    with open(os.path.join(exp_dir, "catalogo_exposicao.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter=";"):
            if r.get("caixa_origem") == "verificar":
                alvo[int(r["codigo"])] = r

    conn = db.conectar(cfg["db"])
    try:
        eans = db.consultar(conn, SQL)
    finally:
        conn.close()

    por_item = {}
    for r in eans:
        if r["codigo"] in alvo:
            por_item.setdefault(r["codigo"], []).append(f"{r['ean']}:{r['qt']}")

    saida = os.path.join(exp_dir, "ean_pdv_sem_caixa.csv")
    with open(saida, "w", encoding="utf-8", newline="\n") as f:
        f.write("codigo;descricao;setor;corredor;eans\n")
        for cod in sorted(alvo):
            r = alvo[cod]
            f.write(f"{cod};{r['descricao']};{r['setor']};{r['corredor']};"
                    f"{'|'.join(por_item.get(cod, []))}\n")
    print(f"{len(alvo)} itens sem caixa-mae ({len(por_item)} com EAN de caixa "
          f"no PDV) -> {saida}")


if __name__ == "__main__":
    main()
