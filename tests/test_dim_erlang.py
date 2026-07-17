# -*- coding: utf-8 -*-
"""Erlang-B/C conferidos contra valores analiticos conhecidos."""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import dim_erlang as e  # noqa: E402


def test_erlang_b_caso_conhecido():
    # B(1, a) = a/(1+a) — derivavel na mao
    assert abs(e.erlang_b(1, 0.5) - (0.5 / 1.5)) < 1e-12
    # B(2, 1) = (1^2/2!)/(1 + 1 + 1/2) = 0.5/2.5 = 0.2
    assert abs(e.erlang_b(2, 1.0) - 0.2) < 1e-12


def test_erlang_c_em_mm1_e_igual_a_rho():
    # M/M/1: P(esperar) = rho. Com c=1 e a=rho, Erlang-C tem que dar exatamente rho.
    for rho in (0.1, 0.5, 0.8):
        assert abs(e.erlang_c(1, rho) - rho) < 1e-12


def test_prob_espera_maior_em_mm1():
    # M/M/1: P(W > t) = rho * exp(-(1-rho) * t / ts)
    rho, ts, t = 0.5, 100.0, 100.0
    esperado = rho * math.exp(-(1 - rho) * t / ts)
    assert abs(e.prob_espera_maior(1, rho, t, ts) - esperado) < 1e-12


def test_saturado_espera_sempre():
    # a >= c: fila explode, P(W > t) = 1
    assert e.erlang_c(2, 2.0) == 1.0
    assert e.prob_espera_maior(2, 3.0, 180, 110) == 1.0


def test_caixas_minimos_monotono_na_carga():
    # mais carga nunca pede menos caixa
    ts, meta_pct, meta_seg = 110.0, 0.95, 180.0
    anterior = 0
    for a in (0.5, 1.0, 2.0, 3.0, 4.0, 5.0):
        c = e.caixas_minimos(a, ts, meta_pct, meta_seg, c_max=20)
        assert c >= anterior
        anterior = c


def test_caixas_minimos_atinge_a_meta():
    ts, meta_pct, meta_seg = 110.0, 0.95, 180.0
    a = 3.36
    c = e.caixas_minimos(a, ts, meta_pct, meta_seg, c_max=20)
    assert e.prob_espera_maior(c, a, meta_seg, ts) <= 1 - meta_pct
    # e c-1 nao atinge (e o MINIMO)
    assert e.prob_espera_maior(c - 1, a, meta_seg, ts) > 1 - meta_pct


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
