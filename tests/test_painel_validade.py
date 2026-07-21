# -*- coding: utf-8 -*-
"""Cruzamento validade x relampago do Painel de Compras."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import painel_compras as pc  # noqa: E402

CATALOGO = [
    {"codigo": "2411", "descricao": "SUCRILHOS 240G", "curva": "A"},
    {"codigo": 3905, "descricao": "SAPOLIO 450ML", "curva": "C"},
]
VALIDADES = [
    {"codigo": "2411", "validade": "2026-08-08"},   # 19 dias a partir de 20/07
    {"codigo": "2411", "validade": "2026-10-01"},
]
RELAMPAGO = [
    {"codigo": "2411", "promo_inicio": "2026-07-18", "promo_fim": "2026-07-25",
     "preco_relampago": 15.9},
    {"codigo": 3905, "promo_inicio": "2026-07-20", "promo_fim": "2026-07-23",
     "preco_relampago": 2.99},
    {"codigo": "9999", "promo_inicio": "2026-07-20", "promo_fim": "2026-07-21",
     "preco_relampago": 2.0},
]


def test_cruza_validade_e_ordena_por_urgencia():
    itens = pc.cruzar_validade_relampago(RELAMPAGO, VALIDADES, CATALOGO, "2026-07-20")
    assert [i["codigo"] for i in itens] == ["2411", "3905", "9999"]
    i0 = itens[0]
    assert i0["descricao"] == "SUCRILHOS 240G" and i0["curva"] == "A"
    assert i0["validades"] == ["2026-08-08", "2026-10-01"]  # menor primeiro
    assert i0["dias_ate_vencer"] == 19


def test_sem_validade_e_fora_do_catalogo_nao_somem():
    itens = pc.cruzar_validade_relampago(RELAMPAGO, VALIDADES, CATALOGO, "2026-07-20")
    por_cod = {i["codigo"]: i for i in itens}
    assert por_cod["3905"]["dias_ate_vencer"] is None      # sem validade registrada
    assert por_cod["3905"]["validades"] == []
    assert por_cod["9999"]["descricao"] == "(fora do catalogo)"


def test_relampago_duplicado_fica_com_o_fim_mais_proximo():
    dupl = RELAMPAGO + [{"codigo": "2411", "promo_inicio": "2026-07-01",
                         "promo_fim": "2026-07-22", "preco_relampago": 14.0}]
    itens = pc.cruzar_validade_relampago(dupl, VALIDADES, CATALOGO, "2026-07-20")
    i0 = [i for i in itens if i["codigo"] == "2411"][0]
    assert i0["promo_fim"] == "2026-07-22" and i0["preco_relampago"] == 14.0


def test_validade_ja_vencida_da_dias_negativos():
    val = [{"codigo": "2411", "validade": "2026-07-15"}]
    itens = pc.cruzar_validade_relampago(RELAMPAGO[:1], val, CATALOGO, "2026-07-20")
    assert itens[0]["dias_ate_vencer"] == -5


def test_dias_pos_promo_usa_o_fim_da_promo_como_referencia():
    # 2411: promo_fim 2026-07-25; validades 08/08 e 01/10 -> menor validade
    # sobra 14 dias APOS o fim da promo. 3905 sem validade -> None.
    itens = pc.cruzar_validade_relampago(RELAMPAGO, VALIDADES, CATALOGO, "2026-07-20")
    por_cod = {i["codigo"]: i for i in itens}
    assert por_cod["2411"]["dias_pos_promo"] == 14
    assert por_cod["3905"]["dias_pos_promo"] is None
    # validade ANTES do fim da promo -> negativo (vence durante a promocao)
    val = [{"codigo": "2411", "validade": "2026-07-22"}]
    so_2411 = pc.cruzar_validade_relampago(RELAMPAGO[:1], val, CATALOGO, "2026-07-20")
    assert so_2411[0]["dias_pos_promo"] == -3


def test_normalizador_de_codigo():
    assert pc._cod(18464) == "18464"
    assert pc._cod("18464.0") == "18464"
    assert pc._cod(" 2411 ") == "2411"
