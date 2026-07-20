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
            "prateleira": "PRATELEIRA 33", "corredor": "CORREDOR 30",
            "setor": "LIMPEZA", "curva": "A"}]
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "catalogo_exposicao.csv")
        n = projections.catalogo_exposicao_csv(cat, caminho)
        assert n == 1
        txt = _ler(caminho)
        assert txt.splitlines()[0] == "codigo;descricao;caixa_mae;setor;corredor;prateleira;curva;peso"
        assert "34743;QUALY 500G;12;LIMPEZA;CORREDOR 30;PRATELEIRA 33;A;0" in txt


def test_catalogo_exposicao_csv_cascata_de_niveis_faltando():
    # classificacao raiz (sem pai/avo no ERP): os niveis descem na cascata
    cat = [{"codigo": 7, "descricao": "RAIZ", "embalagem": 6,
            "prateleira": "REFRIGERADOS", "corredor": None, "setor": None,
            "curva": "B"}]
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "c.csv")
        assert projections.catalogo_exposicao_csv(cat, caminho) == 1
        assert "7;RAIZ;6;REFRIGERADOS;;;B;0" in _ler(caminho)


def test_catalogo_exposicao_csv_so_sem_avo_cai_no_corredor():
    cat = [{"codigo": 8, "descricao": "MEIO", "embalagem": 6,
            "prateleira": "CONGELADOS (CLASSIFICAR)", "corredor": "CONGELADOS",
            "setor": None, "curva": "C"}]
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "c.csv")
        assert projections.catalogo_exposicao_csv(cat, caminho) == 1
        assert "8;MEIO;6;CONGELADOS;CONGELADOS (CLASSIFICAR);;C;0" in _ler(caminho)


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
        assert "9;X;6;;;;;0" in _ler(caminho)


def test_demo_data_vendas_canal_tem_os_dois_canais():
    linhas = demo_data.vendas_canal(30)
    assert linhas
    assert {"codigo", "data", "canal", "unidades"} <= set(linhas[0])
    canais = {r["canal"] for r in linhas}
    assert canais == {"salao", "atacado"}


def test_catalogo_exposicao_exclui_inativos():
    # dono (18/07): so produto ativo ganha min/max — inAtivo=0 do cadastro e
    # a classificacao 'INATIVOS OU FORA DO MIX' ficam fora
    cat = [
        {"codigo": 1, "descricao": "ATIVO", "embalagem": 12, "prateleira": "P1",
         "setor": "S", "corredor": "C", "curva": "A", "ativo": 1},
        {"codigo": 2, "descricao": "DESLIGADO", "embalagem": 12, "prateleira": "P1",
         "setor": "S", "corredor": "C", "curva": "A", "ativo": 0},
        {"codigo": 3, "descricao": "FORA DO MIX", "embalagem": 12,
         "prateleira": "INATIVOS OU FORA DO MIX",
         "setor": "INATIVOS OU FORA DO MIX", "corredor": "INATIVOS OU FORA DO MIX",
         "curva": None, "ativo": 1},
    ]
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "c.csv")
        assert projections.catalogo_exposicao_csv(cat, caminho) == 1
        txt = _ler(caminho)
        assert "ATIVO" in txt and "DESLIGADO" not in txt and "FORA DO MIX" not in txt


def test_catalogo_exposicao_marca_item_por_peso():
    # mortadela/queijo (cdUnidadeMedida kg/g): coluna peso=1
    cat = [{"codigo": 3, "descricao": "QJ MUSSARELA", "embalagem": 1,
            "prateleira": "LATICINIO", "setor": "LATICINIO",
            "corredor": "LATICINIO", "curva": "A", "ativo": 1, "peso": 1}]
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "c.csv")
        assert projections.catalogo_exposicao_csv(cat, caminho) == 1
        assert "3;QJ MUSSARELA;1;LATICINIO;LATICINIO;LATICINIO;A;1" in _ler(caminho)


def test_item_pendurado_no_corredor_nao_desliza_a_trilha():
    # bug do print do dono (18/07): AYMORE SALPET esta classificada DIRETO em
    # CORREDOR 140 (pai BISCOITOS, sem prateleira). A trilha ancorada na folha
    # mostrava "setor BISCOITOS, corredor BISCOITOS, prateleira CORREDOR 140".
    # Ancorada na RAIZ: setor=BISCOITOS, corredor=CORREDOR 140, prateleira vazia.
    cat = [{"codigo": 1523, "descricao": "AYMORE SALPET 100G", "embalagem": 42,
            "prateleira": "CORREDOR 140", "corredor": "BISCOITOS",
            "setor": None, "curva": "B", "ativo": 1}]
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "c.csv")
        assert projections.catalogo_exposicao_csv(cat, caminho) == 1
        assert "1523;AYMORE SALPET 100G;42;BISCOITOS;CORREDOR 140;;B;0" in _ler(caminho)
