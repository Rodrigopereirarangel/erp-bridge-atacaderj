# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import formato  # noqa: E402


def test_caixa_mae_arredonda_para_cima():
    assert formato.exibir(130.0, 20, 0) == "7 cx"     # 6,5 -> 7
    assert formato.exibir(40.0, 20, 0) == "2 cx"      # exato nao sobe


def test_sem_caixa_mae_sai_em_unidades():
    assert formato.exibir(39.5, None, 0) == "40 un"
    assert formato.exibir(39.5, 1, 0) == "40 un"      # embalagem 1 = sem caixa


def test_balanca_sai_em_kg_e_ignora_embalagem():
    assert formato.exibir(11.2, 20, 1) == "12 kg"


def test_sem_dado():
    assert formato.exibir(None, 20, 0) == "—"


def test_rotulo_rua_igual_ao_deposito():
    assert formato.rotulo_rua(1) == "A1 bisc1"
    assert formato.rotulo_rua(9) == "A9"              # sem nome
    assert formato.rotulo_rua(26) == "A24 vitrine"    # rotulo especial
    assert formato.rotulo_rua(None) == ""


def test_ordem_rua_sem_rua_vai_para_o_fim():
    assert formato.ordem_rua(1) < formato.ordem_rua(26)
    assert formato.ordem_rua(26) < formato.ordem_rua(None)


def test_ordem_rua_vitrine_ordena_como_a24_antes_do_terreo():
    # dono 22/07: "A24 vitrine" (rua interna 26) vem ANTES de "A25 TERREO"
    assert formato.ordem_rua(24) < formato.ordem_rua(26)
    assert formato.ordem_rua(26) < formato.ordem_rua(25)


def test_ean_unico_por_linha_com_selo_cx_ou_un():
    # dono, 24/07: so a caixa-mae; sem ela, a unidade — sempre com o selo
    assert formato.ean_exibir(17891107101628, 7891107101621) == \
        ("17891107101628", "CX")
    assert formato.ean_exibir(None, 7891107101621) == ("7891107101621", "UN")
    assert formato.ean_exibir("", "") == ("", "")
