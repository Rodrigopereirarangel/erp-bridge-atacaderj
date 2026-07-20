# -*- coding: utf-8 -*-
"""CATALOGO: o atacado nao pode ressuscitar pela view quando o caixa
suspendeu o degrau (relampago vigente / tier inativo). Caso 2026-07-20:
4 itens em relampago tinham atacado da view MENOR que a relampago — a
cotacao prometia preco que o caixa nao cobra. Regra do dono: o preco de
maior hierarquia sempre vale; a view e fallback SO de item sem linha no PDV."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import queries  # noqa: E402


def test_atacado_so_da_view_quando_item_nao_esta_no_caixa():
    sql = queries.CATALOGO
    assert "WHEN pdv.cdSuperProduto IS NOT NULL" in sql
    assert "ELSE pr.preco_atacado END" in sql


def test_coalesce_que_ressuscitava_atacado_suspenso_nao_volta():
    assert "COALESCE(CASE WHEN pdv.AtacadoQtde" not in queries.CATALOGO


def test_varejo_continua_caixa_primeiro_view_depois():
    # o varejo do caixa ja vem com relampago/promocao/concorrencia
    # materializadas — este fallback e correto e deve permanecer
    assert "COALESCE(NULLIF(pdv.vlVenda, 0)" in queries.CATALOGO
