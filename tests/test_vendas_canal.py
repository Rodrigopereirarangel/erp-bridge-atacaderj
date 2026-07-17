# -*- coding: utf-8 -*-
"""A query VENDAS_CANAL e a unica base com PDV. Estes testes travam as 3
armadilhas que a fizeram existir (spec 2026-07-17, §3):
  - tbVendaPDV nao tem PDV  -> tem que sair do DORSAL
  - cdProduto do cupom pode ser EAN -> tem que resolver por tbProdutoVenda
  - EAN de caixa multiplica -> tem que multiplicar por qtVenda
Nao tocam o banco: validam a FORMA do SQL (a dev nao alcanca o ERP)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import queries  # noqa: E402


def _sql():
    return queries.VENDAS_CANAL.format(janela_exposicao=400, pdvs_atacado="11, 12")


def test_sai_do_dorsal_e_nao_do_tbvendapdv():
    sql = _sql()
    assert "DORSAL.dbo.tbCupom" in sql
    assert "DORSAL.dbo.tbCupomItem" in sql
    assert "tbVendaPDV" not in sql  # nao tem coluna de PDV


def test_resolve_ean_para_codigo_interno():
    sql = _sql()
    assert "tbProdutoVenda" in sql
    assert "pv.cdEAN = i.cdProduto" in sql
    assert "COALESCE(pv.cdProduto, i.cdProduto)" in sql


def test_multiplica_pelo_fator_do_ean():
    # sem isto, caixa bipada no atacado vira 1 unidade
    assert "i.qtItem * COALESCE(pv.qtVenda, 1)" in _sql()


def test_classifica_canal_pelos_pdvs_do_config():
    sql = queries.VENDAS_CANAL.format(janela_exposicao=400, pdvs_atacado="11, 12")
    assert "c.cdPDV IN (11, 12)" in sql
    assert "'atacado'" in sql and "'salao'" in sql


def test_janela_e_parametrizavel():
    assert "DATEADD(day, -30," in queries.VENDAS_CANAL.format(
        janela_exposicao=30, pdvs_atacado="11, 12")


def test_e_somente_leitura():
    import db  # noqa
    assert db._e_somente_leitura(_sql())
