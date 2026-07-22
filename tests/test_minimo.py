# -*- coding: utf-8 -*-
"""Regra 2 do spec: mediana de janelas rolantes; ruptura por curva
(A=10, B=20, C=30 dias seguidos sem venda; sem curva = 20)."""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import minimo  # noqa: E402

FIM = date(2026, 7, 20)


def _serie(valores, fim=FIM):
    """valores[i] = venda do dia (fim - (len-1-i)) — ultimo item = dia `fim`."""
    n = len(valores)
    return {(fim - timedelta(days=n - 1 - i)).isoformat(): v
            for i, v in enumerate(valores) if v}


def test_limiares_oficiais():
    assert minimo.LIMIAR_POR_CURVA == {"A": 10, "B": 20, "C": 30}
    assert minimo.LIMIAR_PADRAO == 20


def test_venda_constante_mediana_e_a_soma_da_janela():
    vendas = _serie([2] * 10)
    # 6 janelas de 5 dias, todas somam 10
    assert minimo.calcular(vendas, FIM, "A", janela=5, historico=10) == (10.0, "")


def test_mediana_par_usa_media_dos_dois_do_meio():
    vendas = _serie([10, 8, 0, 12, 9, 11, 0, 10])
    # janelas de 5 em 8 dias: somas 39, 40, 32, 42 -> mediana (39+40)/2 = 39.5
    u, m = minimo.calcular(vendas, FIM, "A", janela=5, historico=8,
                           limiares={"A": 99})
    assert (u, m) == (39.5, "")


def test_janela_com_ruptura_e_descartada():
    # dias: 5,5,0,0,0,5,5,5 ; limiar 3 -> janelas com >=3 zeros seguidos caem
    vendas = _serie([5, 5, 0, 0, 0, 5, 5, 5])
    # janelas (5d): [5,5,0,0,0]=10 (streak 3, cai) [5,0,0,0,5]=10 (cai)
    #              [0,0,0,5,5]=10 (cai) [0,0,5,5,5]=15 (streak 2, fica)
    u, m = minimo.calcular(vendas, FIM, "A", janela=5, historico=8,
                           limiares={"A": 3})
    assert (u, m) == (15.0, "")


def test_curva_c_tolera_streak_que_derruba_curva_a():
    vendas = _serie([5, 5, 0, 0, 0, 5, 5, 5])
    ua, _ = minimo.calcular(vendas, FIM, "A", janela=5, historico=8,
                            limiares={"A": 3, "C": 4})
    uc, _ = minimo.calcular(vendas, FIM, "C", janela=5, historico=8,
                            limiares={"A": 3, "C": 4})
    assert ua == 15.0
    assert uc == 10.0      # so a janela do meio tem streak 3 <4? nao: todas
    # ficam -> somas 10,10,10,15 -> mediana (10+10)/2 = 10.0


def test_todas_com_ruptura_usa_todas_e_marca_asterisco():
    vendas = _serie([5, 0, 0, 0, 0, 0, 0, 5])
    # toda janela de 5 tem streak >=3 -> fallback: somas 5,0,0,5 -> mediana 2.5
    u, m = minimo.calcular(vendas, FIM, "A", janela=5, historico=8,
                           limiares={"A": 3})
    assert (u, m) == (2.5, "*")


def test_janelas_antes_da_primeira_venda_nao_contam():
    # primeira venda no dia 4 (indice 3): janelas comecam ali
    vendas = _serie([0, 0, 0, 4, 4, 4, 4, 4])
    u, m = minimo.calcular(vendas, FIM, "A", janela=5, historico=8,
                           limiares={"A": 99})
    assert (u, m) == (20.0, "")   # unica janela pos-1a-venda: [4,4,4,4,4]


def test_produto_novo_estimativa_proporcional():
    # primeira venda ha 3 dias (nao cabe janela de 5): media diaria x janela
    vendas = _serie([0, 0, 0, 0, 0, 6, 0, 6])
    u, m = minimo.calcular(vendas, FIM, "A", janela=5, historico=8,
                           limiares={"A": 99})
    # desde a 1a venda: dias [6,0,6] -> media 4 -> 4 x 5 = 20
    assert (u, m) == (20.0, "novo")


def test_sem_venda_nenhuma():
    assert minimo.calcular({}, FIM, "A", janela=5, historico=8) == (None, "sem_venda")


def test_realista_180_dias_gap_de_25_derruba_b_mas_nao_c():
    # venda 1/dia, com buraco de 25 dias no meio (dias 80..104 zerados)
    valores = [1] * 180
    for i in range(80, 105):
        valores[i] = 0
    vendas = _serie(valores)
    ub, mb = minimo.calcular(vendas, FIM, "B")     # limiar 20: gap derruba
    uc, mc = minimo.calcular(vendas, FIM, "C")     # limiar 30: gap fica
    assert mb == "" and mc == ""
    assert ub == 45.0        # janelas limpas vendem 1/dia -> soma 45
    assert uc < ub           # com as janelas do buraco, a mediana cai


def test_curva_desconhecida_usa_limiar_padrao():
    vendas = _serie([1] * 40)
    u1, _ = minimo.calcular(vendas, FIM, None, janela=5, historico=40)
    u2, _ = minimo.calcular(vendas, FIM, "B", janela=5, historico=40)
    assert u1 == u2
