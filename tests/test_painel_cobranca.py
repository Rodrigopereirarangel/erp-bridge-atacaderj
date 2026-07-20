# -*- coding: utf-8 -*-
"""Regras do quadrante de cobranca de fornecedor."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import painel_compras as pc  # noqa: E402

HOJE = "2026-07-20"


def _p(**kw):
    base = {"pedido": 1, "data_pedido": "2026-07-01", "fornecedor": "F",
            "previsao_entrega": None, "ddd": "", "telefone": "", "contato": "",
            "itens_pendentes": 1, "valor_pendente": 100.0}
    base.update(kw)
    return base


def test_entra_por_limiar_de_dias():
    itens = pc.montar_cobranca([_p(pedido=1, data_pedido="2026-07-12")], HOJE, 7)
    assert len(itens) == 1 and itens[0]["dias_aberto"] == 8


def test_recente_sem_previsao_vencida_fica_fora():
    itens = pc.montar_cobranca(
        [_p(pedido=2, data_pedido="2026-07-18", previsao_entrega="2026-07-25")],
        HOJE, 7)
    assert itens == []


def test_recente_mas_previsao_vencida_entra():
    itens = pc.montar_cobranca(
        [_p(pedido=3, data_pedido="2026-07-17", previsao_entrega="2026-07-19")],
        HOJE, 7)
    assert len(itens) == 1
    assert itens[0]["dias_aberto"] == 3 and itens[0]["atraso_previsao"] == 1


def test_ordena_pior_primeiro_e_formata_telefone():
    itens = pc.montar_cobranca([
        _p(pedido=1, data_pedido="2026-07-10", ddd="21", telefone="33334444",
           contato="ANA"),
        _p(pedido=2, data_pedido="2026-07-01", ddd="00", telefone="00000000"),
    ], HOJE, 7)
    assert [i["pedido"] for i in itens] == [2, 1]
    assert itens[1]["telefone"] == "(21) 33334444" and itens[1]["contato"] == "ANA"
    assert itens[0]["telefone"] == ""   # 00/00000000 = lixo, nao mostrar


def test_telefone_so_zeros_com_separador_e_escondido():
    itens = pc.montar_cobranca([
        _p(pedido=1, data_pedido="2026-07-01", ddd="21", telefone="0000-0000"),
        _p(pedido=2, data_pedido="2026-07-01", ddd="21", telefone="0000 0000"),
    ], HOJE, 7)
    assert len(itens) == 2
    assert itens[0]["telefone"] == "" and itens[1]["telefone"] == ""


def test_fronteira_do_limiar_e_desempate_por_valor():
    itens = pc.montar_cobranca([
        _p(pedido=1, data_pedido="2026-07-13", valor_pendente=100.0),
        _p(pedido=2, data_pedido="2026-07-13", valor_pendente=900.0),
    ], HOJE, 7)
    assert len(itens) == 2
    assert itens[0]["dias_aberto"] == 7
    assert [i["pedido"] for i in itens] == [2, 1]
