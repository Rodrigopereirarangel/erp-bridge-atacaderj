# -*- coding: utf-8 -*-
"""Quadrante Troca/Avaria: query, demo, montagem e serie historica."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import demo_data  # noqa: E402
import historico_painel as hp  # noqa: E402
import painel_compras as pc  # noqa: E402
import queries    # noqa: E402


def test_query_filtra_tipo3_com_saldo_e_ordena_por_valor():
    sql = queries.AVARIA_SALDO.format(avaria_desde="2026-03-01")
    assert "cdEstoqueTipo = 3" in sql and "qtEstoqueFisico > 0" in sql
    assert "tbEstoqueContabil" in sql and "tbEstoqueMovimento" in sql
    assert "ORDER BY valor DESC" in sql
    # dono, 22/07: so quem ENTROU na area de marco em diante
    assert "HAVING MAX(m.ult_entrada) >= '2026-03-01'" in sql
    assert "inEntrada = 1" in sql


def test_demo_tem_forma_da_query():
    for r in demo_data.avaria_saldo():
        assert {"codigo", "descricao", "qtd", "valor", "ultima_mov"} <= set(r)


def test_montar_avaria_idade_esquecido_e_ordem():
    linhas = [
        {"codigo": 1, "descricao": "A", "qtd": 10, "valor": 100.0,
         "ultima_mov": "2026-07-15"},
        {"codigo": 2, "descricao": "B", "qtd": 5, "valor": 900.0,
         "ultima_mov": "2026-03-01"},          # 142d -> esquecido
        {"codigo": 3, "descricao": "C", "qtd": 2, "valor": 50.0,
         "ultima_mov": None},                  # sem mov -> idade None
    ]
    itens = pc.montar_avaria(linhas, "2026-07-22", 60)
    assert [i["codigo"] for i in itens] == ["2", "1", "3"]   # maior R$ 1o
    assert itens[0]["esquecido"] and itens[0]["idade"] == 143
    assert not itens[1]["esquecido"] and itens[1]["idade"] == 7
    assert itens[2]["idade"] is None and not itens[2]["esquecido"]


def test_serie_avaria_no_sql_series():
    sqls = hp.sql_series(["2026-07-20"])
    assert "avaria" in sqls
    assert "tbEstoqueContabil" in sqls["avaria"]
    assert "tbEstoqueMovimento" in sqls["avaria"]


def test_rodar_demo_inclui_avaria(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "RAIZ", str(tmp_path))
    pc.rodar({"painel": {"dir_saida": str(tmp_path / "painel")}},
             usar_demo=True)
    dados = json.loads((tmp_path / "painel" / "dados_painel.json").read_text(
        encoding="utf-8"))
    q = dados["avaria"]
    assert len(q["itens"]) == 3 and q["esquecido_dias"] == 60
    assert q["itens"][0]["descricao"].startswith("PEITO")   # maior valor
    assert q["itens"][0]["esquecido"] is True
    assert "avaria" in dados["historico"]
