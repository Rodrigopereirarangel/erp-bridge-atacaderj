# -*- coding: utf-8 -*-
"""Regra 1 do spec: COTACAO exclusivo > quem mais entregou em 6m >
negociacao mais recente > SEM FORNECEDOR."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import fornecedor  # noqa: E402


def test_cotacao_e_exclusivo_mesmo_com_entregas_de_outro():
    neg = [{"codigo": 15450, "fornecedor": "COTACAO", "dt_alteracao": ""},
           {"codigo": 15450, "fornecedor": "WAL MART", "dt_alteracao": "2026-05-01"}]
    ent = [{"codigo": 15450, "data": "2026-07-01",
            "fornecedor": "WAL MART", "qtd": 999.0}]
    assert fornecedor.atribuir(neg, ent)[15450] == "COTACAO"


def test_cotacao_casa_sem_diferenciar_caixa_e_espacos():
    neg = [{"codigo": 1, "fornecedor": "  Cotacao ", "dt_alteracao": ""}]
    assert fornecedor.atribuir(neg, [])[1] == "COTACAO"


def test_dominante_por_soma_de_unidades_nos_6m():
    ent = [{"codigo": 2, "data": "2026-07-01", "fornecedor": "RICLAN", "qtd": 60.0},
           {"codigo": 2, "data": "2026-06-01", "fornecedor": "GARCIA", "qtd": 50.0},
           {"codigo": 2, "data": "2026-05-01", "fornecedor": "RICLAN", "qtd": 10.0}]
    # RICLAN 70 > GARCIA 50
    assert fornecedor.atribuir([], ent)[2] == "RICLAN"


def test_empate_na_soma_vence_a_entrega_mais_recente():
    ent = [{"codigo": 3, "data": "2026-07-10", "fornecedor": "A1", "qtd": 50.0},
           {"codigo": 3, "data": "2026-06-01", "fornecedor": "B2", "qtd": 50.0}]
    assert fornecedor.atribuir([], ent)[3] == "A1"


def test_entrada_sem_fornecedor_nao_conta_na_dominancia():
    ent = [{"codigo": 4, "data": "2026-07-10", "fornecedor": "", "qtd": 999.0},
           {"codigo": 4, "data": "2026-06-01", "fornecedor": "JW DOCES", "qtd": 1.0}]
    assert fornecedor.atribuir([], ent)[4] == "JW DOCES"


def test_sem_entrada_cai_na_negociacao_mais_recente():
    neg = [{"codigo": 5, "fornecedor": "GARCIA", "dt_alteracao": "2026-01-01"},
           {"codigo": 5, "fornecedor": "RICLAN", "dt_alteracao": "2026-06-01"}]
    assert fornecedor.atribuir(neg, [])[5] == "RICLAN"


def test_negociacao_com_dt_vazia_perde_para_dt_preenchida():
    neg = [{"codigo": 6, "fornecedor": "GARCIA", "dt_alteracao": ""},
           {"codigo": 6, "fornecedor": "RICLAN", "dt_alteracao": "2026-06-01"}]
    assert fornecedor.atribuir(neg, [])[6] == "RICLAN"


def test_negociacoes_todas_sem_dt_desempata_por_ordem_alfabetica():
    neg = [{"codigo": 7, "fornecedor": "ZAMBONI", "dt_alteracao": ""},
           {"codigo": 7, "fornecedor": "AMBEV", "dt_alteracao": ""}]
    assert fornecedor.atribuir(neg, [])[7] == "AMBEV"


def test_sem_nada_vira_sem_fornecedor():
    assert fornecedor.atribuir([], []) == {}
    # quem consulta usa .get(codigo, SEM_FORNECEDOR)
    assert fornecedor.SEM_FORNECEDOR == "SEM FORNECEDOR"
