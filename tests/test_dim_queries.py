# -*- coding: utf-8 -*-
"""A query e texto: da para travar o RECORTE sem tocar no banco.
O recorte errado (esquecer o PDV 11/12, ou perder tbCupomCancelado) e o
jeito mais facil de esta analise mentir — por isso ele e testado."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import dim_queries as q  # noqa: E402


def _branches(sql):
    """Extrai as duas branches (tbCupom e tbCupomCancelado) do UNION ALL.
    Guarda contra regressoes que mudem a contagem de branches."""
    partes = sql.split("UNION ALL")
    assert len(partes) == 2, \
        f"Query deve ter exatamente 2 branches (UNION ALL), encontrou {len(partes)}"
    return partes[0], partes[1]


def test_cupons_exclui_atacado_e_operador_nao_operacional():
    """Verifica que PDV 11/12 (atacado) e operador 7000 (fiscal) sao excluídos
    em AMBAS as branches (tbCupom e tbCupomCancelado)."""
    sql = q.CUPONS.upper()
    parte1, parte2 = _branches(sql)

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

    # Verifica UNION ALL e extrai as branches
    assert "UNION ALL" in sql, "Query deve usar UNION ALL para combinar branches"
    parte1, parte2 = _branches(sql)

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
    """Verifica que domingo (DATEPART(weekday)=1) e excluido de AMBAS as
    branches (tbCupom e tbCupomCancelado). Loja fechada; se cair de uma branch,
    domingos vao surgir no resultado."""
    sql = q.CUPONS.upper()
    parte1, parte2 = _branches(sql)

    filtro_domingo = "DATEPART(WEEKDAY, DTCUPOM) <> 1"
    assert filtro_domingo in parte1, \
        f"Filtro '{filtro_domingo}' faltando na branch 1 (tbCupom)"
    assert filtro_domingo in parte2, \
        f"Filtro '{filtro_domingo}' faltando na branch 2 (tbCupomCancelado)"


def test_cupons_exclui_horas_inválidas():
    """Verifica que as três condicoes de sanidade de tempo estao em AMBAS as
    branches: HoraInicio IS NOT NULL, HoraFim IS NOT NULL, HoraFim >= HoraInicio.
    Se caírem, horas negativas ou vazias vao entrar na demanda."""
    sql = q.CUPONS.upper()
    parte1, parte2 = _branches(sql)

    # HoraInicio NOT NULL
    assert "HORAINICIO IS NOT NULL" in parte1, \
        "Filtro 'HoraInicio IS NOT NULL' faltando na branch 1 (tbCupom)"
    assert "HORAINICIO IS NOT NULL" in parte2, \
        "Filtro 'HoraInicio IS NOT NULL' faltando na branch 2 (tbCupomCancelado)"

    # HoraFim NOT NULL
    assert "HORAFIM IS NOT NULL" in parte1, \
        "Filtro 'HoraFim IS NOT NULL' faltando na branch 1 (tbCupom)"
    assert "HORAFIM IS NOT NULL" in parte2, \
        "Filtro 'HoraFim IS NOT NULL' faltando na branch 2 (tbCupomCancelado)"

    # HoraFim >= HoraInicio
    assert "HORAFIM >= HORAINICIO" in parte1, \
        "Filtro 'HoraFim >= HoraInicio' faltando na branch 1 (tbCupom)"
    assert "HORAFIM >= HORAINICIO" in parte2, \
        "Filtro 'HoraFim >= HoraInicio' faltando na branch 2 (tbCupomCancelado)"


def test_cupons_placeholder_desde_presente():
    """Verifica que o placeholder '{desde}' (data inicial, runtime) e presente
    em AMBAS as branches. Se cair de uma, datas antigas vao entrar no resultado."""
    sql = q.CUPONS
    parte1, parte2 = _branches(sql)

    assert "{desde}" in parte1, \
        "Placeholder '{desde}' faltando na branch 1 (tbCupom)"
    assert "{desde}" in parte2, \
        "Placeholder '{desde}' faltando na branch 2 (tbCupomCancelado)"


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
