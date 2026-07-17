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


def test_cupom_cruza_slot_20_para_21():
    # Valida a propriedade mais importante: clipping no limite de slot.
    # 1 PDV, 1 cupom comecando em 10:29:00 (offset 1740s de BASE=10:00) com 200s de duracao.
    # Slot 20 vai 10:00-10:30 (36000-37800s em absolute)
    # Slot 21 vai 10:30-11:00 (37800-39600s em absolute)
    # Cupom vai 10:29:00-10:32:20 (37740-37940s em absolute)
    # Slot 20 contribui: min(37940, 37800) - max(37740, 36000) = 37800 - 37740 = 60s
    # Slot 21 contribui: min(37940, 39600) - max(37740, 37800) = 37940 - 37800 = 140s
    cupons = [_cupom(1, 1740, 200)]
    folga = sat.folga_por_slot(cupons)
    ocupado_20 = 60.0
    ocupado_21 = 140.0
    disponivel = 1 * 1800  # 1 PDV
    expected_folga_20 = 1.0 - ocupado_20 / disponivel
    expected_folga_21 = 1.0 - ocupado_21 / disponivel
    assert abs(folga[(DIA, 20)] - expected_folga_20) < 1e-9
    assert abs(folga[(DIA, 21)] - expected_folga_21) < 1e-9
    # Ambos os slots devem constar no dicionario
    assert (DIA, 20) in folga
    assert (DIA, 21) in folga


def test_cupom_apos_meia_noite_clipeado():
    # Valida o guard: cupom que cruzaria meia-noite e clipado, nao emite slot >= 48.
    # Criamos um cupom hipotetico comecando em 23:59:00 (86340s) com 120s de duracao.
    # Teoricamente fim_s seria 86460s (slot 48, invalido).
    # Apos clipping, fim_s vira min(86460, 86400) = 86400. Slot 48 ainda e iterado
    # (ultimo = 48), mas sempre contribui dentro <= 0 (pois ini_s < 86400 e fim_s <= 86400),
    # entao o filtro if dentro > 0 o suprime. Nao ha bound em ultimo; a protecao e o filtro.
    # Nota: usando uma data diferente para evitar conflito com testes anteriores.
    outro_dia = date(2026, 7, 15)
    tarde = datetime(2026, 7, 15, 23, 59, 0)
    cupom_noite = {
        "pdv": 1,
        "inicio": tarde,
        "fim": tarde + timedelta(seconds=120)
    }
    folga = sat.folga_por_slot([cupom_noite])
    # Nenhuma chave deve ter slot >= 48
    for (dia, slot), _ in folga.items():
        assert slot < 48, f"Slot invalido {slot} para dia {dia}"
    # Deve haver exatamente uma entrada: (outro_dia, 47)
    assert len(folga) == 1
    assert (outro_dia, 47) in folga
    # Verifica que exatamente 60s (nao 120s) foi contado: cupom comeca em 86340s,
    # slot 47 termina em 86400s, entao contribui min(86400, 86400) - 86340 = 60s.
    assert abs(folga[(outro_dia, 47)] - (1 - 60.0/1800.0)) < 1e-9


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
