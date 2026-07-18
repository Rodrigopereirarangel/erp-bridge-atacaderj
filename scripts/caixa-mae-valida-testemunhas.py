# -*- coding: utf-8 -*-
"""VALIDACAO das testemunhas de caixa-mae — rodada 2 (18/07).

Rodada 1 mediu: EAN do PDV 51% (qtVenda=12 e valor-padrao em 12k produtos),
DESC 19% ("C 30" costuma ser display, nao caixa) -> REPROVADAS.
NOTA (entradas 12m) 98,4% e PEDIDO (compras 12m) 98,8% -> aprovadas.

Rodada 2 mede as fontes de CADASTRO nativo descobertas no schema:
  EMB   tbEmbalagemSuperProduto (cdEmpresa=10, qtEmbalagem>1 inteiro unanime)
  NFE   tbProdutoPessoaComercialNFe.FatorConversaoUnitario (>1 inteiro unanime)
e ja cruza com a populacao SEM caixa-mae (708) sob duas reguas:
  A) >=1 voto aprovado, sem discordancia entre votos
  B) >=2 votos aprovados concordando

Uso (NO PC-PONTE):  python scripts/caixa-mae-valida-testemunhas.py
"""
import csv
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
import db  # noqa: E402

SQL_GABARITO = """
SELECT pr.SEQPRODUTO AS codigo, CAST(MAX(pr.QUANTIDADE_CAIXA) AS int) AS caixa,
       MAX(sp.nmProdutoPai) AS descricao
FROM dbo.VW_NEOGRID_PRODUTO_PRECO pr
JOIN dbo.tbProduto p       ON p.cdProduto = pr.SEQPRODUTO
JOIN dbo.tbSuperProduto sp ON sp.cdSuperProduto = p.cdSuperProduto
WHERE pr.SEQLOJA = 1
GROUP BY pr.SEQPRODUTO
HAVING MAX(pr.QUANTIDADE_CAIXA) > 1
"""

# so opiniao INTEIRA e unanime vale (12.0 sim; 12.5 nao — meia caixa nao existe)
SQL_NOTA = """
SELECT i.cdProduto AS codigo, COUNT(DISTINCT i.qtEmbalagem) AS n_fatores,
       CAST(MAX(i.qtEmbalagem) AS int) AS fator, COUNT(*) AS vezes
FROM dbo.tbNotaItem i
JOIN dbo.tbNotaEntrada ne
  ON ne.cdNotaEntrada = i.cdNota AND ne.cdPessoaFilial = i.cdPessoaFilial
WHERE ne.dtChegada >= DATEADD(month, -12, CAST(GETDATE() AS date))
  AND i.qtEmbalagem > 1 AND i.qtEmbalagem = FLOOR(i.qtEmbalagem)
  AND i.cdProduto IS NOT NULL
GROUP BY i.cdProduto
"""

SQL_PEDIDO = """
SELECT i.cdProduto AS codigo, COUNT(DISTINCT i.qtEmbalagem) AS n_fatores,
       CAST(MAX(i.qtEmbalagem) AS int) AS fator, COUNT(*) AS vezes
FROM dbo.tbPedidoItem i
JOIN dbo.tbPedido p
  ON p.cdPedido = i.cdPedido AND p.cdPessoaFilial = i.cdPessoaFilial
WHERE p.inEntrada = 1
  AND p.dtPedido >= DATEADD(month, -12, CAST(GETDATE() AS date))
  AND i.qtEmbalagem > 1 AND i.qtEmbalagem = FLOOR(i.qtEmbalagem)
  AND i.cdProduto IS NOT NULL
GROUP BY i.cdProduto
"""

SQL_EMB = """
SELECT p.cdProduto AS codigo, COUNT(DISTINCT e.qtEmbalagem) AS n_fatores,
       CAST(MAX(e.qtEmbalagem) AS int) AS fator, COUNT(*) AS vezes
FROM dbo.tbEmbalagemSuperProduto e
JOIN dbo.tbProduto p ON p.cdSuperProduto = e.cdSuperProduto
WHERE e.cdEmpresa = 10
  AND e.qtEmbalagem > 1 AND e.qtEmbalagem = FLOOR(e.qtEmbalagem)
GROUP BY p.cdProduto
"""

SQL_NFE = """
SELECT cdProduto AS codigo, COUNT(DISTINCT FatorConversaoUnitario) AS n_fatores,
       CAST(MAX(FatorConversaoUnitario) AS int) AS fator, COUNT(*) AS vezes
FROM dbo.tbProdutoPessoaComercialNFe
WHERE FatorConversaoUnitario > 1
  AND FatorConversaoUnitario = FLOOR(FatorConversaoUnitario)
  AND cdProduto IS NOT NULL
  -- SO unidade de CAIXA na NF-e: fornecedor faturando em KG/UN gera fator de
  -- conversao (kg -> bandeja), nao caixa-mae — a armadilha da carne moida
  -- que o dono avisou (18/07)
  AND UPPER(LTRIM(RTRIM(uComNFe))) IN ('CX','CX1','CX2','CX3','FD','DP','FRD',
                                       'CAIXA','FARDO','DZ','PC','PCT','SC')
GROUP BY cdProduto
"""

SQL_NFE_UNIDADES = """
SELECT UPPER(LTRIM(RTRIM(uComNFe))) AS unidade, COUNT(*) AS linhas
FROM dbo.tbProdutoPessoaComercialNFe
WHERE FatorConversaoUnitario > 1 AND cdProduto IS NOT NULL
GROUP BY UPPER(LTRIM(RTRIM(uComNFe)))
ORDER BY COUNT(*) DESC
"""


def _unanime(m, cod):
    t = m.get(cod)
    return t["fator"] if (t and t["n_fatores"] == 1) else None


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    cfg = json.load(open(os.path.join(RAIZ, "config.local.json"), encoding="utf-8"))
    conn = db.conectar(cfg["db"])
    try:
        gab = db.consultar(conn, SQL_GABARITO)
        fontes = {
            "NOTA": {r["codigo"]: r for r in db.consultar(conn, SQL_NOTA)},
            "PEDIDO": {r["codigo"]: r for r in db.consultar(conn, SQL_PEDIDO)},
            "EMB": {r["codigo"]: r for r in db.consultar(conn, SQL_EMB)},
            "NFE": {r["codigo"]: r for r in db.consultar(conn, SQL_NFE)},
        }
        unidades = db.consultar(conn, SQL_NFE_UNIDADES)
    finally:
        conn.close()

    print("unidades da NF-e com fator>1: " +
          ", ".join(f"{u['unidade']}={u['linhas']}" for u in unidades[:15]))
    print(f"\ngabarito (cadastro Neogrid com caixa>1): {len(gab)} itens\n")
    for nome, m in fontes.items():
        acertos = erros = 0
        exemplos = []
        for r in gab:
            v = _unanime(m, r["codigo"])
            if v is None:
                continue
            if v == r["caixa"]:
                acertos += 1
            else:
                erros += 1
                if len(exemplos) < 4:
                    exemplos.append((r["codigo"], r["descricao"][:40],
                                     r["caixa"], v))
        n = acertos + erros
        pct = 100.0 * acertos / n if n else 0.0
        print(f"{nome:>7}: opina em {n:>5} | acerta {pct:5.1f}%")
        for e in exemplos:
            print(f"          erro: {e[0]} {e[1]:<40} cadastro={e[2]} testemunha={e[3]}")

    # populacao sem caixa-mae do relatorio
    exp_dir = cfg["saida"].get("exposicao_dir") or os.path.join(RAIZ, "saida", "exposicao")
    populacao = []
    with open(os.path.join(exp_dir, "catalogo_exposicao.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter=";"):
            if int(r["caixa_mae"]) == 1 and r.get("peso", "0") != "1":
                populacao.append({"codigo": int(r["codigo"]),
                                  "descricao": r["descricao"]})
    print(f"\npopulacao sem caixa-mae (nao-peso): {len(populacao)}")

    resultado = []
    regua_a = regua_b = discordam = 0
    for item in populacao:
        votos = {}
        for nome, m in fontes.items():
            v = _unanime(m, item["codigo"])
            if v is not None:
                votos[nome] = v
        distintos = set(votos.values())
        if len(distintos) == 1:
            if len(votos) >= 2:
                regua_b += 1
            regua_a += 1
            resultado.append((item, votos))
        elif len(distintos) > 1:
            discordam += 1

    print(f"  regua A (>=1 voto, sem discordancia): {regua_a}")
    print(f"  regua B (>=2 votos concordando):      {regua_b}")
    print(f"  votos discordantes (fica manual):     {discordam}")

    por_fonte = {}
    for _, votos in resultado:
        for nome in votos:
            por_fonte[nome] = por_fonte.get(nome, 0) + 1
    print(f"  cobertura por fonte na regua A: {por_fonte}")
    print("\nexemplos regua A:")
    for item, votos in resultado[:25]:
        print(f"   {item['codigo']:>7} {item['descricao'][:48]:<48} {votos}")


if __name__ == "__main__":
    main()
