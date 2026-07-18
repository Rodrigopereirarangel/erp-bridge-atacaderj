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
        assert txt.splitlines()[0] == "codigo;descricao;caixa_mae;setor;corredor;prateleira;curva;peso;caixa_origem"
        assert "34743;QUALY 500G;12;LIMPEZA;CORREDOR 30;PRATELEIRA 33;A;0;cadastro" in txt


def test_catalogo_exposicao_csv_cascata_de_niveis_faltando():
    # classificacao raiz (sem pai/avo no ERP): os niveis descem na cascata
    cat = [{"codigo": 7, "descricao": "RAIZ", "embalagem": 6,
            "prateleira": "REFRIGERADOS", "corredor": None, "setor": None,
            "curva": "B"}]
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "c.csv")
        assert projections.catalogo_exposicao_csv(cat, caminho) == 1
        assert "7;RAIZ;6;REFRIGERADOS;;;B;0;cadastro" in _ler(caminho)


def test_catalogo_exposicao_csv_so_sem_avo_cai_no_corredor():
    cat = [{"codigo": 8, "descricao": "MEIO", "embalagem": 6,
            "prateleira": "CONGELADOS (CLASSIFICAR)", "corredor": "CONGELADOS",
            "setor": None, "curva": "C"}]
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "c.csv")
        assert projections.catalogo_exposicao_csv(cat, caminho) == 1
        assert "8;MEIO;6;CONGELADOS;CONGELADOS (CLASSIFICAR);;C;0;cadastro" in _ler(caminho)


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
        assert "9;X;6;;;;;0;cadastro" in _ler(caminho)


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
        assert "3;QJ MUSSARELA;1;LATICINIO;LATICINIO;LATICINIO;A;1;cadastro" in _ler(caminho)


def test_caixa_aproximada_quando_testemunhas_concordam():
    # dono (18/07): item sem QUANTIDADE_CAIXA ganha caixa APROXIMADA quando as
    # fontes medidas (nota/pedido/nfe/emb) concordam; marca origem p/ o emoji
    cat = [{"codigo": 38519, "descricao": "FOFURA REQUEIJAO 60G C10",
            "embalagem": 1, "prateleira": "P", "corredor": "C", "setor": "S",
            "curva": "B", "ativo": 1}]
    cmt = [{"codigo": 38519, "fonte": "nota", "fator": 10},
           {"codigo": 38519, "fonte": "pedido", "fator": 10}]
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "c.csv")
        assert projections.catalogo_exposicao_csv(cat, caminho, cmt) == 1
        assert "38519;FOFURA REQUEIJAO 60G C10;10;S;C;P;B;0;aproximada" in _ler(caminho)


def test_caixa_aproximada_resgata_item_sem_embalagem_nenhuma():
    # embalagem NULL era pulado; com testemunha concordante agora ENTRA
    cat = [{"codigo": 1, "descricao": "X", "embalagem": None,
            "prateleira": "P", "curva": None, "ativo": 1}]
    cmt = [{"codigo": 1, "fonte": "pedido", "fator": 12}]
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "c.csv")
        assert projections.catalogo_exposicao_csv(cat, caminho, cmt) == 1
        assert "1;X;12;P;;;;0;aproximada" in _ler(caminho)


def test_testemunhas_discordantes_fica_verificar():
    # qualquer discordancia entre fontes = sem presuncao: fica p/ ajuste manual
    cat = [{"codigo": 2, "descricao": "Y", "embalagem": 1,
            "prateleira": "P", "curva": None, "ativo": 1}]
    cmt = [{"codigo": 2, "fonte": "nota", "fator": 6},
           {"codigo": 2, "fonte": "nfe", "fator": 12}]
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "c.csv")
        assert projections.catalogo_exposicao_csv(cat, caminho, cmt) == 1
        assert "2;Y;1;P;;;;0;verificar" in _ler(caminho)


def test_cadastro_com_caixa_nunca_e_sobrescrito():
    cat = [{"codigo": 3, "descricao": "Z", "embalagem": 12,
            "prateleira": "P", "curva": "A", "ativo": 1}]
    cmt = [{"codigo": 3, "fonte": "pedido", "fator": 24}]
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "c.csv")
        projections.catalogo_exposicao_csv(cat, caminho, cmt)
        assert "3;Z;12;P;;;A;0;cadastro" in _ler(caminho)


def test_peso_nao_ganha_caixa_aproximada():
    # carne moida: NF em kg, venda em bandeja — fator de conversao nao e caixa
    cat = [{"codigo": 4, "descricao": "CARNE MOIDA 500G", "embalagem": 1,
            "prateleira": "ACOUGUE", "curva": "A", "ativo": 1, "peso": 1}]
    cmt = [{"codigo": 4, "fonte": "nfe", "fator": 2}]
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "c.csv")
        projections.catalogo_exposicao_csv(cat, caminho, cmt)
        assert "4;CARNE MOIDA 500G;1;ACOUGUE;;;A;1;cadastro" in _ler(caminho)


def test_sem_caixa_e_sem_testemunha_fica_verificar():
    cat = [{"codigo": 5, "descricao": "W", "embalagem": 1,
            "prateleira": "P", "curva": None, "ativo": 1}]
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "c.csv")
        projections.catalogo_exposicao_csv(cat, caminho, None)
        assert "5;W;1;P;;;;0;verificar" in _ler(caminho)


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
        assert "1523;AYMORE SALPET 100G;42;BISCOITOS;CORREDOR 140;;B;0;cadastro" in _ler(caminho)
