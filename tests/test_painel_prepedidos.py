# -*- coding: utf-8 -*-
"""Quadrante Pre-pedidos: forma da query, demo e montagem."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import demo_data  # noqa: E402
import painel_compras as pc  # noqa: E402
import queries    # noqa: E402


def test_pre_pedidos_formata_janela_e_filtra_abertos():
    sql = queries.PRE_PEDIDOS.format(prepedido_dias=21)
    assert "-21" in sql and "tbPrePedido" in sql
    assert "inEncerrado" in sql and "cdPedidoCompra IS NULL" in sql


def test_demo_tem_forma_da_query():
    linhas = demo_data.pre_pedidos()
    assert len(linhas) >= 2
    for r in linhas:
        assert {"pre_pedido", "fornecedor", "data_pre", "limite",
                "itens", "valor"} <= set(r)


def test_montar_prepedidos_calcula_dias_e_ordena_mais_novo_primeiro():
    linhas = [
        {"pre_pedido": 1, "fornecedor": "A", "data_pre": "2026-07-10",
         "limite": "2026-07-30", "itens": 3, "valor": 1500.0},
        {"pre_pedido": 2, "fornecedor": "B", "data_pre": "2026-07-20",
         "limite": None, "itens": 1, "valor": 500.0},
    ]
    itens = pc.montar_prepedidos(linhas, "2026-07-21")
    assert [i["pre_pedido"] for i in itens] == [2, 1]   # mais novo primeiro
    assert itens[0]["dias"] == 1 and itens[1]["dias"] == 11
    assert itens[0]["limite"] is None and itens[1]["limite"] == "2026-07-30"
