# -*- coding: utf-8 -*-
"""Historico semanal do painel (spec §13): amostragem, series, merge e demo."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import historico_painel as hp  # noqa: E402
import painel_compras as pc    # noqa: E402


def test_segundas_desde_toda_segunda_mais_hoje():
    dias = hp.segundas_desde("2026-04-06", "2026-07-21")
    assert dias[0] == "2026-04-06" and dias[-1] == "2026-07-21"
    assert "2026-07-20" in dias                    # ultima segunda
    assert len(dias) == 17                         # 16 segundas + o hoje (ter)
    # hoje sendo segunda nao duplica
    so_segundas = hp.segundas_desde("2026-04-06", "2026-07-20")
    assert len(so_segundas) == 16 and so_segundas[-1] == "2026-07-20"


def test_values_dias_rejeita_data_invalida():
    with pytest.raises(ValueError):
        hp._values_dias(["2026-04-06'; DROP TABLE x--"])


def test_sql_series_interpola_regras_vigentes():
    sqls = hp.sql_series(["2026-04-06", "2026-04-13"], 30, 7, 21)
    assert set(sqls) == {"validade_relampago", "cobranca", "sellout",
                         "prepedidos"}
    assert "tbPromocaoRelampago" in sqls["validade_relampago"]
    assert "-30" in sqls["cobranca"] and ">= 7" in sqls["cobranca"]
    assert "-21" in sqls["prepedidos"]
    for sql in sqls.values():
        assert "('2026-04-06'), ('2026-04-13')" in sql


def test_serie_abaixo_custo_conta_itens_distintos_da_semana():
    vendas = [
        {"codigo": 1, "data": "2026-07-15", "qtd_vendida": 2,
         "valor": 10.0, "custo_venda": 12.0},     # abaixo
        {"codigo": 1, "data": "2026-07-16", "qtd_vendida": 1,
         "valor": 5.0, "custo_venda": 6.0},       # mesmo item, nao duplica
        {"codigo": 2, "data": "2026-07-20", "qtd_vendida": 3,
         "valor": 30.0, "custo_venda": 20.0},     # acima do custo
        {"codigo": 3, "data": "2026-07-01", "qtd_vendida": 1,
         "valor": 1.0, "custo_venda": 2.0},       # so na semana ate 07/07
    ]
    serie = hp.serie_abaixo_custo(vendas, ["2026-07-07", "2026-07-20"])
    assert serie == [{"s": "2026-07-07", "v": 1}, {"s": "2026-07-20", "v": 1}]


def test_corte_ruptura_espelha_a_regra_do_template():
    itens = [
        {"probabilidade": 0.9, "dias_parado": 3},                    # entra
        {"probabilidade": 0.7, "dias_parado": 3},                    # prob baixa
        {"probabilidade": 0.9, "dias_parado": 1},                    # parado <= 1
        {"probabilidade": 0.9, "dias_parado": 3, "entrega_dias": 15,
         "cobertura_restante": 4.0},                                 # guardrail
        {"probabilidade": 0.9, "dias_parado": 3, "entrega_dias": 15,
         "cobertura_restante": 0.0},                                 # sem cobertura
        {"probabilidade": 0.9, "dias_parado": 3, "entrega_dias": 47,
         "cobertura_restante": 9.0},                                 # entrega velha
    ]
    assert hp.corte_ruptura(itens) == 3


def test_mesclar_preserva_pontos_antigos_e_substitui_iguais(tmp_path):
    d = str(tmp_path)
    hp.mesclar_historico(d, {"ruptura": [{"s": "2026-04-06", "v": 5},
                                         {"s": "2026-04-13", "v": 7}]}, "t1")
    out = hp.mesclar_historico(d, {"ruptura": [{"s": "2026-04-13", "v": 9},
                                               {"s": "2026-07-21", "v": 2}]},
                               "t2")
    assert out["series"]["ruptura"] == [
        {"s": "2026-04-06", "v": 5},     # preservado (fora das novas)
        {"s": "2026-04-13", "v": 9},     # substituido
        {"s": "2026-07-21", "v": 2}]
    arq = json.loads((tmp_path / "historico.json").read_text(encoding="utf-8"))
    assert arq["gerado_em"] == "t2"


def test_rodar_demo_embute_historico_no_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "RAIZ", str(tmp_path))
    pc.rodar({"painel": {"dir_saida": str(tmp_path / "painel")}},
             usar_demo=True)
    dados = json.loads((tmp_path / "painel" / "dados_painel.json").read_text(
        encoding="utf-8"))
    hist = dados["historico"]
    assert {"validade_relampago", "cobranca", "sellout", "prepedidos",
            "abaixo_custo"} <= set(hist)
    assert len(hist["cobranca"]) >= 2
    assert (tmp_path / "painel" / "historico.json").exists()
