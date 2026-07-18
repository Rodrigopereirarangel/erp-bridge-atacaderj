# -*- coding: utf-8 -*-
"""Ad-hoc (18/07): a cadeia COMPLETA de classificacao (folha -> raiz) de
produtos-exemplo (FOFURA, TRAKINAS, AYMORE SALPET, TORC) + histograma de
profundidade do catalogo. Motivo: o relatorio de exposicao mostra
setor/corredor/prateleira deslizados (prateleira = 'CORREDOR 140')."""
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
import db  # noqa: E402

SQL_CADEIA = """
WITH sobe AS (
    SELECT p.cdProduto, sp.nmProdutoPai AS descricao,
           c.cdClassificacaoProduto, c.cdEmpresa,
           c.nmClassificacaoProduto, c.cdClassificacaoProdutoPai,
           c.cdEmpresaPai, 0 AS nivel
    FROM dbo.tbProduto p
    JOIN dbo.tbSuperProduto sp ON sp.cdSuperProduto = p.cdSuperProduto
    LEFT JOIN dbo.tbClassificacaoProduto c
           ON c.cdClassificacaoProduto = sp.cdClassificacaoProduto
          AND c.cdEmpresa = sp.cdEmpresa
    WHERE sp.nmProdutoPai LIKE '%{alvo}%'
    UNION ALL
    SELECT s.cdProduto, s.descricao,
           c.cdClassificacaoProduto, c.cdEmpresa,
           c.nmClassificacaoProduto, c.cdClassificacaoProdutoPai,
           c.cdEmpresaPai, s.nivel + 1
    FROM sobe s
    JOIN dbo.tbClassificacaoProduto c
      ON c.cdClassificacaoProduto = s.cdClassificacaoProdutoPai
     AND c.cdEmpresa = s.cdEmpresaPai
    WHERE s.nivel < 8
)
SELECT cdProduto, descricao, nivel, nmClassificacaoProduto
FROM sobe ORDER BY cdProduto, nivel
"""

SQL_PROFUNDIDADE = """
WITH sobe AS (
    SELECT p.cdProduto, sp.cdClassificacaoProduto AS cd, sp.cdEmpresa AS emp,
           0 AS nivel
    FROM dbo.tbProduto p
    JOIN dbo.tbSuperProduto sp ON sp.cdSuperProduto = p.cdSuperProduto
    WHERE p.inAtivo = 1 AND sp.cdClassificacaoProduto IS NOT NULL
    UNION ALL
    SELECT s.cdProduto, c.cdClassificacaoProdutoPai, c.cdEmpresaPai, s.nivel + 1
    FROM sobe s
    JOIN dbo.tbClassificacaoProduto c
      ON c.cdClassificacaoProduto = s.cd AND c.cdEmpresa = s.emp
    WHERE c.cdClassificacaoProdutoPai IS NOT NULL AND s.nivel < 8
)
SELECT profundidade, COUNT(*) AS produtos FROM (
    SELECT cdProduto, MAX(nivel) + 1 AS profundidade FROM sobe
    GROUP BY cdProduto
) t GROUP BY profundidade ORDER BY profundidade
"""


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    cfg = json.load(open(os.path.join(RAIZ, "config.local.json"), encoding="utf-8"))
    conn = db.conectar(cfg["db"])
    try:
        for alvo in ("FOFURA REQUEIJAO", "TRAKINAS", "AYMORE SALPET",
                     "TORC 60G CHURRASCO"):
            linhas = db.consultar(conn, SQL_CADEIA.format(alvo=alvo))
            print(f"\n== {alvo} ==")
            atual = None
            for r in linhas:
                if r["cdProduto"] != atual:
                    atual = r["cdProduto"]
                    print(f"  {r['cdProduto']} {r['descricao']}")
                print(f"     nivel {r['nivel']}: {r['nmClassificacaoProduto']}")
        print("\n== profundidade da arvore (produtos ativos) ==")
        for r in db.consultar(conn, SQL_PROFUNDIDADE):
            print(f"  {r['profundidade']} degraus: {r['produtos']} produtos")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
