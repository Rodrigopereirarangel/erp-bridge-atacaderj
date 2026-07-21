# -*- coding: utf-8 -*-
"""Quadrante 'vendendo abaixo do custo': hierarquia de preco + janela de venda."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import painel_compras as pc  # noqa: E402

CAT = [
    # promo vigente MANDA e esta abaixo do custo -> entra como "promo"
    {"codigo": "1", "descricao": "PROMO SANGRANDO", "custo_atual": 10.0,
     "preco_varejo": 12.0, "preco_promocao": 8.5, "curva": "A"},
    # sem promo; varejo abaixo do custo -> entra como "varejo"
    {"codigo": "2", "descricao": "VAREJO SANGRANDO", "custo_atual": 5.0,
     "preco_varejo": 4.0, "preco_promocao": None, "curva": "B"},
    # promo vigente ACIMA do custo (mesmo com varejo abaixo, promo manda) -> fora
    {"codigo": "3", "descricao": "PROMO SAUDAVEL", "custo_atual": 5.0,
     "preco_varejo": 4.0, "preco_promocao": 6.0, "curva": "A"},
    # abaixo do custo mas SEM venda nos 5 dias -> fora
    {"codigo": "4", "descricao": "SEM GIRO", "custo_atual": 10.0,
     "preco_varejo": 7.0, "preco_promocao": None, "curva": "C"},
]
VEN5 = [
    {"codigo": "1", "qtd_vendida": 10},
    {"codigo": "1", "qtd_vendida": 5},
    {"codigo": "2", "qtd_vendida": 2},
    {"codigo": "3", "qtd_vendida": 1},
]


def test_hierarquia_do_preco_e_janela_de_venda():
    itens = pc.montar_abaixo_custo(CAT, VEN5)
    assert [i["codigo"] for i in itens] == ["1", "2"]   # maior prejuizo primeiro
    p1 = itens[0]
    assert p1["origem"] == "promo" and p1["preco"] == 8.5
    assert p1["qtd_5d"] == 15 and p1["prejuizo_5d"] == 22.5   # (10-8.5)*15
    assert p1["margem_pct"] == -15.0
    p2 = itens[1]
    assert p2["origem"] == "varejo" and p2["prejuizo_5d"] == 2.0


def test_custo_zerado_ou_preco_igual_ficam_fora():
    cat = [{"codigo": "9", "descricao": "CUSTO ZERO", "custo_atual": 0,
            "preco_varejo": 5.0, "preco_promocao": None, "curva": "A"},
           {"codigo": "8", "descricao": "NO CUSTO", "custo_atual": 5.0,
            "preco_varejo": 5.0, "preco_promocao": None, "curva": "A"}]
    ven = [{"codigo": "9", "qtd_vendida": 1}, {"codigo": "8", "qtd_vendida": 1}]
    assert pc.montar_abaixo_custo(cat, ven) == []
