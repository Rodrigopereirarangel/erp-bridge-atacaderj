# -*- coding: utf-8 -*-
"""Queries do alvo `listagem` (app listagem-fornecedor).

Fatos validados no ERP em 2026-07-22 (amostra real via ponte):
- tbNegociacao liga por cdSuperProduto (NAO tem cdProduto) e dtAlteracao
  vem NULL com frequencia -> dt_alteracao pode sair vazio.
- fornecedor da entrada = tbNota.cdPessoaComercial (join por cdNota +
  cdPessoaFilial), nome em tbPessoa (amostra: QUEIJOS DONA ROSA, JW DOCES)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import queries  # noqa: E402


def test_negociacao_liga_por_cdsuperproduto():
    sql = queries.NEGOCIACAO_FORNECEDOR
    assert "p.cdSuperProduto = n.cdSuperProduto" in sql
    assert "tbNegociacao" in sql
    assert "MAX(n.dtAlteracao)" in sql          # dtAlteracao NULL e comum


def test_negociacao_nao_exporta_valores():
    # regra do repo: nada de custo/preco em arquivo que sai do ponte
    sql = queries.NEGOCIACAO_FORNECEDOR
    assert "vlEmbalagem" not in sql
    assert "vlPreco" not in sql


def test_entradas_fornecedor_join_validado():
    sql = queries.ENTRADAS_FORNECEDOR
    assert "n.cdNota = i.cdNota" in sql
    assert "n.cdPessoaFilial = i.cdPessoaFilial" in sql
    assert "ne.cdNotaEntrada = i.cdNota" in sql
    assert "{janela_listagem}" in sql
    assert "i.cdProduto IS NOT NULL" in sql     # nota com produto NULL existe


def test_entradas_fornecedor_qtd_em_unidades():
    # convencao da nota: qtItemNota em volumes -> x qtEmbalagem = unidades
    assert "SUM(i.qtItemNota * i.qtEmbalagem)" in queries.ENTRADAS_FORNECEDOR
