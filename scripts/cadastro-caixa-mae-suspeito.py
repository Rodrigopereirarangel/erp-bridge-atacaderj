# -*- coding: utf-8 -*-
"""DIAGNOSTICO (spec 2026-07-17 §8.1 / D17): itens cuja caixa-mae cadastrada
e duvidosa.

NAO altera calculo nenhum. O MIN/MAX usa SEMPRE o cadastro (decisao do dono,
D7); este script so mostra onde o cadastro cheira mal, p/ o dono consertar no
ERP.

Criterio (medido em 17/07/2026):
  - A nota de entrada so vale como testemunha quando qtEmbalagem > 1. Em 1.291
    itens ela diz 1 porque o fornecedor faturou EM UNIDADE — ausencia de
    opiniao, nao discordancia. Ex.: QUALY 500G vem com nota=1, mas a caixa
    tem 12 (confirmado pelo dono).
  - Nesse recorte, a nota confirma o cadastro 933x contra 240 do EAN -> o
    cadastro e a fonte (D7).
  - Sobram ~30 itens onde a nota fala de caixa real e discorda do cadastro.
    Ex.: TAPIOCA ROSA 500G cadastro=50 nota=5 (chegou 7x assim);
         FOFURA REQUEIJAO 60G C10 cadastro=1 (!) nota=10.
  - 23 dos 30 tem a nota MENOR que o cadastro — a direcao que superexpoe a
    prateleira (mais mercadoria parada = a avaria/validade que o MAX combate).

Uso (NO PC-PONTE):
  python scripts/cadastro-caixa-mae-suspeito.py
"""
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
import db           # noqa: E402
import projections  # noqa: E402

SQL = """
WITH nota AS (
    SELECT codigo, caixa_nota, entradas FROM (
        SELECT i.cdProduto AS codigo, i.qtEmbalagem AS caixa_nota,
               COUNT(*) AS entradas,
               ROW_NUMBER() OVER (PARTITION BY i.cdProduto
                                  ORDER BY COUNT(*) DESC, i.qtEmbalagem DESC) AS rn
        FROM dbo.tbNotaItem i
        JOIN dbo.tbNotaEntrada ne
          ON ne.cdNotaEntrada = i.cdNota AND ne.cdPessoaFilial = i.cdPessoaFilial
        WHERE ne.dtChegada >= DATEADD(month, -12, CAST(GETDATE() AS date))
          AND i.qtEmbalagem > 1        -- SO nota informativa: =1 e faturamento em unidade
          AND i.cdProduto IS NOT NULL
        GROUP BY i.cdProduto, i.qtEmbalagem
    ) t WHERE rn = 1
), cadastro AS (
    SELECT SEQPRODUTO AS codigo, MAX(QUANTIDADE_CAIXA) AS caixa_cadastro
    FROM dbo.VW_NEOGRID_PRODUTO_PRECO WHERE SEQLOJA = 1 GROUP BY SEQPRODUTO
)
SELECT c.codigo, sp.nmProdutoPai AS descricao,
       CAST(c.caixa_cadastro AS int) AS caixa_cadastro,
       CAST(n.caixa_nota AS int)     AS caixa_nota,
       n.entradas                    AS vezes_que_chegou_assim
FROM cadastro c
JOIN nota n ON n.codigo = c.codigo
LEFT JOIN dbo.tbProduto p       ON p.cdProduto = c.codigo
LEFT JOIN dbo.tbSuperProduto sp ON sp.cdSuperProduto = p.cdSuperProduto
WHERE n.caixa_nota <> c.caixa_cadastro
ORDER BY n.entradas DESC, c.codigo
"""


def main():
    cfg = json.load(open(os.path.join(RAIZ, "config.local.json"), encoding="utf-8"))
    conn = db.conectar(cfg["db"])
    try:
        linhas = db.consultar(conn, SQL)
    finally:
        conn.close()

    exp_dir = cfg["saida"].get("exposicao_dir") or os.path.join(RAIZ, "saida", "exposicao")
    caminho = os.path.join(exp_dir, "cadastro_caixa_mae_suspeito.csv")
    cab = ["codigo", "descricao", "caixa_cadastro", "caixa_nota", "vezes_que_chegou_assim"]
    projections._escrever_atomico(caminho, projections._csv_ponto_virgula(
        cab, [[r["codigo"], r["descricao"], r["caixa_cadastro"],
               r["caixa_nota"], r["vezes_que_chegou_assim"]] for r in linhas]))

    menor = sum(1 for r in linhas if r["caixa_nota"] < r["caixa_cadastro"])
    print(f"{len(linhas)} itens com caixa-mae suspeita -> {caminho}")
    print(f"  {menor} tem a nota MENOR que o cadastro (direcao que SUPEREXPOE a prateleira)\n")
    print(f"{'codigo':>8} {'cadastro':>9} {'nota':>6} {'vezes':>6}  descricao")
    for r in linhas[:30]:
        print(f"{r['codigo']:>8} {r['caixa_cadastro']:>9} {r['caixa_nota']:>6} "
              f"{r['vezes_que_chegou_assim']:>6}  {r['descricao']}")


if __name__ == "__main__":
    main()
