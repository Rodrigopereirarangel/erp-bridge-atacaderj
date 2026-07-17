# -*- coding: utf-8 -*-
"""Handover = mediana dos gaps < corte entre cupons consecutivos no mesmo PDV.
Razao do corte: com fila, o gap E a troca de cliente pura; gap grande e
ociosidade (nao havia proximo cliente), nao troca."""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import dim_servico as s  # noqa: E402

BASE = datetime(2026, 7, 16, 8, 0, 0)


def _cupom(pdv, offset_ini, dur, operador=1):
    return {"pdv": pdv, "operador": operador,
            "inicio": BASE + timedelta(seconds=offset_ini),
            "fim": BASE + timedelta(seconds=offset_ini + dur)}


def test_percentil_interpola():
    assert s.percentil([1, 2, 3, 4], 0.0) == 1
    assert s.percentil([1, 2, 3, 4], 1.0) == 4
    assert s.percentil([1, 2, 3, 4], 0.5) == 2.5   # (2+3)/2
    assert s.percentil([], 0.85) == 0


def test_duracoes_sao_fim_menos_inicio():
    assert s.duracoes([_cupom(1, 0, 100), _cupom(1, 200, 50)]) == [100.0, 50.0]


def test_handover_e_a_mediana_dos_gaps_curtos():
    # gaps: 10s, 20s, 30s (curtos = troca de cliente) e 600s (ociosidade, ignorar)
    cupons = [
        _cupom(1, 0, 100),      # fim em 100
        _cupom(1, 110, 100),    # gap 10  -> fim 210
        _cupom(1, 230, 100),    # gap 20  -> fim 330
        _cupom(1, 360, 100),    # gap 30  -> fim 460
        _cupom(1, 1060, 100),   # gap 600 -> ociosidade, fora
    ]
    assert s.estimar_handover(cupons, corte_seg=120.0) == 20.0  # mediana de [10,20,30]


def test_handover_nao_mistura_pdvs():
    # o "gap" entre o ultimo cupom do PDV 1 e o primeiro do PDV 2 nao existe
    cupons = [_cupom(1, 0, 100), _cupom(2, 110, 100)]
    assert s.estimar_handover(cupons, corte_seg=120.0) == 0.0  # nenhum gap valido


def test_servico_soma_o_handover():
    cupons = [_cupom(1, 0, 100, operador=7), _cupom(1, 200, 50, operador=7)]
    por_op = s.servicos_por_operador(cupons, handover=15.0)
    assert por_op[7] == [115.0, 65.0]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
