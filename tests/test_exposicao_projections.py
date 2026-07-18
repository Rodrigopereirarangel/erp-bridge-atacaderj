# -*- coding: utf-8 -*-
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import demo_data    # noqa: E402
import projections  # noqa: E402


def _ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        return f.read()


def test_vendas_canal_csv_cabecalho_e_linhas():
    linhas = [
        {"codigo": 18464, "data": "2026-07-14", "canal": "salao", "unidades": 225.0},
        {"codigo": 18464, "data": "2026-07-14", "canal": "atacado", "unidades": 1462.0},
    ]
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "vendas_canal.csv")
        n = projections.vendas_canal_csv(linhas, caminho)
        assert n == 2
        txt = _ler(caminho)
        assert txt.splitlines()[0] == "codigo;data;canal;unidades"
        assert "18464;2026-07-14;salao;225.0" in txt
        assert "18464;2026-07-14;atacado;1462.0" in txt


def test_catalogo_exposicao_csv_renomeia_embalagem_para_caixa_mae():
    cat = [{"codigo": 34743, "descricao": "QUALY 500G", "embalagem": 12,
            "prateleira": "PRATELEIRA 33", "setor": "CORREDOR 30", "curva": "A"}]
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "catalogo_exposicao.csv")
        n = projections.catalogo_exposicao_csv(cat, caminho)
        assert n == 1
        txt = _ler(caminho)
        assert txt.splitlines()[0] == "codigo;descricao;caixa_mae;setor;prateleira;curva"
        assert "34743;QUALY 500G;12;CORREDOR 30;PRATELEIRA 33;A" in txt


def test_catalogo_exposicao_csv_setor_cai_na_prateleira_sem_pai():
    # classificacao raiz (sem pai no ERP): o setor e a propria classificacao
    cat = [{"codigo": 7, "descricao": "RAIZ", "embalagem": 6,
            "prateleira": "REFRIGERADOS", "setor": None, "curva": "B"}]
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "c.csv")
        assert projections.catalogo_exposicao_csv(cat, caminho) == 1
        assert "7;RAIZ;6;REFRIGERADOS;REFRIGERADOS;B" in _ler(caminho)


def test_catalogo_exposicao_csv_pula_item_sem_caixa_mae():
    # sem caixa-mae o consumidor nao consegue arredondar: melhor faltar a
    # linha do que entregar um numero inventado
    cat = [
        {"codigo": 1, "descricao": "COM", "embalagem": 12, "prateleira": "P1", "curva": "A"},
        {"codigo": 2, "descricao": "SEM", "embalagem": None, "prateleira": "P1", "curva": "B"},
        {"codigo": 3, "descricao": "ZERO", "embalagem": 0, "prateleira": "P1", "curva": "C"},
    ]
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "c.csv")
        assert projections.catalogo_exposicao_csv(cat, caminho) == 1


def test_catalogo_exposicao_csv_aceita_prateleira_vazia():
    # item sem endereco fisico ainda recebe min/max; so nao agrupa
    cat = [{"codigo": 9, "descricao": "X", "embalagem": 6, "prateleira": None, "curva": None}]
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "c.csv")
        assert projections.catalogo_exposicao_csv(cat, caminho) == 1
        assert "9;X;6;;;" in _ler(caminho)


def test_demo_data_vendas_canal_tem_os_dois_canais():
    linhas = demo_data.vendas_canal(30)
    assert linhas
    assert {"codigo", "data", "canal", "unidades"} <= set(linhas[0])
    canais = {r["canal"] for r in linhas}
    assert canais == {"salao", "atacado"}
