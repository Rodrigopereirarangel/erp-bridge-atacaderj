# -*- coding: utf-8 -*-
"""Saturacao: se num slot TODOS os PDVs abertos ficaram colados passando cupom,
a chegada foi represada pela capacidade -> a demanda observada e PISO, nao
estimativa. Isso e medido, nao suposto."""
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import dim_saturacao as sat  # noqa: E402

DIA = date(2026, 7, 16)
BASE = datetime(2026, 7, 16, 10, 0, 0)   # 10:00 = slot 20 (36000s / 1800)


def _cupom(pdv, offset_ini, dur):
    return {"pdv": pdv, "inicio": BASE + timedelta(seconds=offset_ini),
            "fim": BASE + timedelta(seconds=offset_ini + dur)}


def test_slot_de_usa_faixa_de_30min():
    assert sat.slot_de(datetime(2026, 7, 16, 0, 0, 0)) == 0
    assert sat.slot_de(datetime(2026, 7, 16, 0, 29, 59)) == 0
    assert sat.slot_de(datetime(2026, 7, 16, 0, 30, 0)) == 1
    assert sat.slot_de(datetime(2026, 7, 16, 10, 0, 0)) == 20


def test_pdv_colado_o_slot_inteiro_nao_tem_folga():
    # 1 PDV, 18 cupons de 100s = 1800s ocupado num slot de 1800s -> folga 0
    cupons = [_cupom(1, i * 100, 100) for i in range(18)]
    folga = sat.folga_por_slot(cupons)
    assert abs(folga[(DIA, 20)] - 0.0) < 1e-9
    assert (DIA, 20) in sat.slots_saturados(cupons, limiar=0.05)


def test_pdv_com_metade_do_tempo_livre_tem_folga():
    # 1 PDV, 9 cupons de 100s = 900s de 1800s -> folga 0.5
    cupons = [_cupom(1, i * 200, 100) for i in range(9)]
    folga = sat.folga_por_slot(cupons)
    assert abs(folga[(DIA, 20)] - 0.5) < 1e-9
    assert sat.slots_saturados(cupons, limiar=0.05) == set()


def test_folga_considera_todos_os_pdvs_abertos():
    # PDV 1 colado (1800s), PDV 2 quase vazio (100s) -> folga = 1 - 1900/3600
    cupons = [_cupom(1, i * 100, 100) for i in range(18)] + [_cupom(2, 0, 100)]
    folga = sat.folga_por_slot(cupons)
    assert abs(folga[(DIA, 20)] - (1 - 1900.0 / 3600.0)) < 1e-9
    assert sat.slots_saturados(cupons, limiar=0.05) == set()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
