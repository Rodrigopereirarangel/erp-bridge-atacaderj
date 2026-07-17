# -*- coding: utf-8 -*-
"""A query e texto: da para travar o RECORTE sem tocar no banco.
O recorte errado (esquecer o PDV 11/12, ou perder tbCupomCancelado) e o
jeito mais facil de esta analise mentir — por isso ele e testado."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import dim_queries as q  # noqa: E402


def test_cupons_exclui_atacado_e_operador_nao_operacional():
    """Verifica que PDV 11/12 (atacado) e operador 7000 (fiscal) sao excluídos
    em AMBAS as branches (tbCupom e tbCupomCancelado)."""
    sql = q.CUPONS.upper()
    parte1, parte2 = sql.split("UNION ALL")

    # Filtro PDV 11/12 deve estar em ambas as branches
    filtro_pdv = "NOT IN (11, 12)"
    assert filtro_pdv in parte1.replace("  ", " "), \
        f"Filtro '{filtro_pdv}' faltando na branch 1 (tbCupom)"
    assert filtro_pdv in parte2.replace("  ", " "), \
        f"Filtro '{filtro_pdv}' faltando na branch 2 (tbCupomCancelado)"

    # Filtro operador 7000 deve estar em ambas as branches
    filtro_op = "CDOPERADOR <> 7000"
    assert filtro_op in parte1.replace("  ", " "), \
        f"Filtro '{filtro_op}' faltando na branch 1 (tbCupom)"
    assert filtro_op in parte2.replace("  ", " "), \
        f"Filtro '{filtro_op}' faltando na branch 2 (tbCupomCancelado)"

    # Filtro filial deve estar em ambas as branches
    filtro_filial = "CDFILIAL = 1"
    assert filtro_filial in parte1.replace("  ", " "), \
        f"Filtro '{filtro_filial}' faltando na branch 1 (tbCupom)"
    assert filtro_filial in parte2.replace("  ", " "), \
        f"Filtro '{filtro_filial}' faltando na branch 2 (tbCupomCancelado)"


def test_cupons_inclui_a_tabela_de_cancelados():
    """Verifica que AMBAS as branches existem: tbCupom (nao cancelado)
    e tbCupomCancelado (cancelado). Cupom cancelado consumiu tempo de caixa:
    fora dele, subdimensiona."""
    sql = q.CUPONS.upper()

    # Verifica UNION ALL
    assert "UNION ALL" in sql, "Query deve usar UNION ALL para combinar branches"

    # Split nas branches
    partes = sql.split("UNION ALL")
    assert len(partes) == 2, "Query deve ter exatamente 2 branches (UNION ALL)"
    parte1, parte2 = partes

    # Branch 1 deve ter tbCupom (nao cancelado) - busca a clausula FROM completa
    assert "FROM DORSAL.DBO.TBCUPOM\n" in parte1, \
        "Branch 1 deve ter FROM DORSAL.dbo.tbCupom"

    # Branch 2 deve ter tbCupomCancelado - busca a clausula FROM completa
    assert "FROM DORSAL.DBO.TBCUPOMCANCELADO\n" in parte2, \
        "Branch 2 deve ter FROM DORSAL.dbo.tbCupomCancelado"

    # Verifica que nao ha a tabela cancelada na branch 1
    assert "TBCUPOMCANCELADO" not in parte1, \
        "Branch 1 deve ter APENAS tbCupom, nao tbCupomCancelado"


def test_cupons_exclui_domingo():
    # loja fechada; DATEPART(weekday) = 1 e domingo no SQL Server
    assert "DATEPART(weekday, dtCupom) <> 1" in q.CUPONS


def test_cupons_nao_extrai_valor_monetario():
    # regra do repo: nada de preco/custo. E a analise nao precisa.
    assert "vlCupom" not in q.CUPONS


def test_queries_sao_somente_leitura():
    import db
    for sql in (q.CUPONS, q.CONFERENCIA_CONSOLIDADO):
        assert db._e_somente_leitura(sql)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
