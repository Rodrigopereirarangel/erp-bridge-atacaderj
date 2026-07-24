# -*- coding: utf-8 -*-
"""Projecoes dos CSVs do alvo `listagem` (sem custo/preco em nenhum)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import projections  # noqa: E402


def _ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        return f.read().strip().split("\n")


def test_negociacao_csv(tmp_path):
    rows = [
        {"codigo": 15450, "fornecedor": "COTACAO", "dt_alteracao": None},
        {"codigo": 15450, "fornecedor": "WAL MART BRASIL LTDA",
         "dt_alteracao": "2026-05-01"},
    ]
    arq = str(tmp_path / "negociacao.csv")
    assert projections.negociacao_csv(rows, arq) == 2
    linhas = _ler(arq)
    assert linhas[0] == "codigo;fornecedor;dt_alteracao"
    assert linhas[1] == "15450;COTACAO;"          # NULL -> vazio
    assert linhas[2] == "15450;WAL MART BRASIL LTDA;2026-05-01"


def test_entradas_fornecedor_csv(tmp_path):
    rows = [{"codigo": 181, "data": "2026-07-22",
             "fornecedor": "QUEIJOS DONA ROSA", "qtd": 32.6}]
    arq = str(tmp_path / "entradas_fornecedor.csv")
    assert projections.entradas_fornecedor_csv(rows, arq) == 1
    linhas = _ler(arq)
    assert linhas[0] == "codigo;data;fornecedor;qtd"
    assert linhas[1] == "181;2026-07-22;QUEIJOS DONA ROSA;32.6"


def test_catalogo_listagem_csv_sem_preco_nem_custo(tmp_path):
    cat = [{"codigo": 15450, "descricao": "OLEO SOJA SOYA 900ML",
            "embalagem": 20, "curva": "A", "peso": 0, "ativo": 1,
            "ean_cx": 17891107101628, "ean_un": 7891107101621,
            "corredor": "CORREDOR 60 ",
            "endereco_atacado": "ATACADO 2",
            "custo_atual": 6.0, "preco_varejo": 8.0}]
    arq = str(tmp_path / "catalogo_listagem.csv")
    assert projections.catalogo_listagem_csv(cat, arq) == 1
    linhas = _ler(arq)
    assert linhas[0] == ("codigo;descricao;embalagem;curva;peso;"
                         "ean_cx;ean_un;corredor_erp;endereco;ativo")
    assert linhas[1] == ("15450;OLEO SOJA SOYA 900ML;20;A;0;"
                         "17891107101628;7891107101621;CORREDOR 60;ATACADO 2;1")
    assert "6.0" not in linhas[1] and "8.0" not in linhas[1]


def test_catalogo_listagem_curva_vazia_sai_vazia(tmp_path):
    cat = [{"codigo": 1, "descricao": "X", "embalagem": None,
            "curva": None, "peso": 0, "ativo": 1}]
    arq = str(tmp_path / "c.csv")
    projections.catalogo_listagem_csv(cat, arq)
    assert _ler(arq)[1] == "1;X;;;0;;;;;1"
