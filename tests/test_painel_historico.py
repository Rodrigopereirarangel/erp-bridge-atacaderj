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
                         "prepedidos", "avaria"}
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


def test_corte_ruptura_espelha_a_regra_e_conta_por_curva():
    itens = [
        {"probabilidade": 0.9, "dias_parado": 3, "curva": "A"},      # entra (A)
        {"probabilidade": 0.7, "dias_parado": 3, "curva": "A"},      # prob baixa
        {"probabilidade": 0.9, "dias_parado": 1, "curva": "B"},      # parado <= 1
        {"probabilidade": 0.9, "dias_parado": 3, "entrega_dias": 15,
         "cobertura_restante": 4.0, "curva": "A"},                   # guardrail
        {"probabilidade": 0.9, "dias_parado": 3, "entrega_dias": 15,
         "cobertura_restante": 0.0, "curva": "B"},                   # entra (B)
        {"probabilidade": 0.9, "dias_parado": 3, "entrega_dias": 47,
         "cobertura_restante": 9.0, "curva": "B"},                   # entra (B)
        {"probabilidade": 0.9, "dias_parado": 3, "curva": "C"},      # C+ fora
    ]
    assert hp.corte_ruptura(itens) == {"a": 1, "b": 2}


def test_mesclar_poda_dias_soltos_mantendo_segundas_e_ultimo(tmp_path):
    d = str(tmp_path)
    hp.mesclar_historico(d, {"x": [{"s": "2026-07-13", "v": 1},     # segunda
                                   {"s": "2026-07-15", "v": 2}]}, "t1")  # qua
    out = hp.mesclar_historico(d, {"x": [{"s": "2026-07-16", "v": 3}]}, "t2")
    # a quarta antiga (15) cai; fica a segunda (13) + o mais recente (16)
    assert [p["s"] for p in out["series"]["x"]] == ["2026-07-13", "2026-07-16"]


def test_contar_concorrente_por_zona_e_frescor(tmp_path):
    html = ('<script>const ITENS = ['
            '{"g": "kvi", "v": [{"dt": "15/07/2026"}]}, '
            '{"g": "kvi", "v": [{"dt": "01/07/2026"}]}, '     # velho (>10d)
            '{"g": "alinha", "v": [{"dt": "20/07/2026"}]}, '
            '{"g": "alinha", "v": []}, '                      # sem coleta
            '{"g": "degrau", "v": [{"dt": "20/07/2026"}]}'    # outra zona
            '];</script>')
    arq = tmp_path / "rev.html"
    arq.write_text(html, encoding="utf-8")
    import painel_compras as pcm
    assert pcm.contar_concorrente(str(arq), "2026-07-21") == \
        {"acima": 1, "abaixo": 1}


def test_podar_copia_renomeia_kvi_e_esconde_nota(tmp_path):
    arq = tmp_path / "rev.html"
    arq.write_text('<head></head><body><p class="nota">x</p>'
                   '<script>const GRUPOS = [["kvi","KVI"],'
                   '["alinha","Sobe p/ vizinho"],["degrau","Degrau"],'
                   '["recuo","Recuo"]];'
                   'const ITENS = [{"r": "KVI no piso", "g": "kvi"},'
                   '{"r": "KVI", "g": "kvi"}];</script></body>',
                   encoding="utf-8")
    import painel_compras as pcm
    pcm._podar_copia_revisao(str(arq))
    s = arq.read_text(encoding="utf-8")
    assert '["kvi","Itens acima de concorrência"]' in s
    assert '"r": "Acima (no piso)"' in s and '"r": "Acima"' in s
    assert "p.nota,#descricao{display:none!important}" in s
    assert "recuo" not in s                       # aba Recuo fora (22/07)
    assert '["degrau","Degrau"]];' in s           # fechamento integro
