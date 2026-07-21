# -*- coding: utf-8 -*-
"""Quadrante Verba SellOut: forma da query, demo e montagem."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import demo_data  # noqa: E402
import painel_compras as pc  # noqa: E402
import queries    # noqa: E402

HOJE = "2026-07-21"


def test_rec_sellout_e_select_puro_sem_placeholder():
    sql = queries.REC_SELLOUT
    assert sql.strip().upper().startswith("WITH")
    assert "tbPromocaoItem" in sql and "tbVendaPDV" in sql
    assert "dtPagamentoReceitaSellOut" in sql
    assert "{" not in sql   # sem placeholder — format nao pode quebrar


def test_demo_tem_forma_da_query_e_os_4_casos():
    linhas = demo_data.receita_sellout()
    assert len(linhas) >= 4
    for r in linhas:
        assert {"produto", "promocao", "tipo_promocao", "fornecedor", "inicio",
                "fim", "vencimento", "verba_un", "total"} <= set(r)


def test_montar_sellout_calcula_dias_vencida_e_ordena():
    linhas = [
        {"produto": "B", "promocao": "P1", "tipo_promocao": "Rebaixa",
         "fornecedor": "F1", "inicio": "2026-06-01", "fim": "2026-06-10",
         "vencimento": "2026-06-30", "verba_un": 1.0, "total": 100.0},
        {"produto": "A", "promocao": "P2", "tipo_promocao": "Encarte",
         "fornecedor": "F2", "inicio": "2026-06-01", "fim": "2026-06-10",
         "vencimento": "2026-07-01", "verba_un": 2.0, "total": 900.0},
        {"produto": "SEM GIRO", "promocao": "P3", "tipo_promocao": "",
         "fornecedor": "", "inicio": "2026-06-01", "fim": "2026-06-10",
         "vencimento": "2026-06-15", "verba_un": 2.0, "total": 0.0},
        {"produto": "NO PRAZO", "promocao": "P4", "tipo_promocao": "Rebaixa",
         "fornecedor": "F3", "inicio": "2026-07-01", "fim": "2026-07-20",
         "vencimento": "2026-07-30", "verba_un": 1.0, "total": 50.0},
    ]
    itens = pc.montar_sellout(linhas, HOJE)
    # vencidas com R$ primeiro, maior total no topo
    assert [i["produto"] for i in itens[:2]] == ["A", "B"]
    assert itens[0]["dias_vencida"] == 20      # venc 01/07, hoje 21/07
    assert itens[1]["dias_vencida"] == 21
    por = {i["produto"]: i for i in itens}
    assert por["NO PRAZO"]["dias_vencida"] == -9   # ainda nao venceu
    assert por["SEM GIRO"]["total"] == 0.0
