# -*- coding: utf-8 -*-
"""A query e texto: da para travar o RECORTE sem tocar no banco.
O recorte errado (esquecer o PDV 11/12, ou perder tbCupomCancelado) e o
jeito mais facil de esta analise mentir — por isso ele e testado."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import dim_queries as q  # noqa: E402


def test_cupons_exclui_atacado_e_operador_nao_operacional():
    sql = q.CUPONS.upper()
    assert "NOT IN (11, 12)" in sql.replace("  ", " ")
    assert "7000" in sql
    assert "CDFILIAL = 1" in sql.replace("  ", " ")


def test_cupons_inclui_a_tabela_de_cancelados():
    # cupom cancelado consumiu tempo de caixa: fora dele, subdimensiona
    sql = q.CUPONS.upper()
    assert "TBCUPOM" in sql
    assert "TBCUPOMCANCELADO" in sql
    assert "UNION ALL" in sql


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
