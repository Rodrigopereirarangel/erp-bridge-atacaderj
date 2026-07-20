# -*- coding: utf-8 -*-
"""Queries e dados demo do Painel de Compras: forma e placeholders."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import demo_data  # noqa: E402
import queries    # noqa: E402


def test_promo_relampago_e_select_puro_sem_placeholder():
    sql = queries.PROMO_RELAMPAGO
    assert sql.strip().upper().startswith("SELECT")
    assert "tbPromocaoRelampago" in sql
    assert "{" not in sql  # nao tem placeholder — formatar nao pode quebrar


def test_pedidos_cobranca_formata_janela():
    sql = queries.PEDIDOS_COBRANCA.format(cobranca_max_dias=60)
    assert "DATEADD(day, -60" in sql
    assert "cdPessoaComercial" in sql          # fornecedor vem do tbPedidoCompra
    assert "tbTelefone" in sql
    assert "inEntrada = 1" in sql and "dtAtendido IS NULL" in sql


def test_pedidos_abandonados_formata_janela():
    sql = queries.PEDIDOS_ABANDONADOS.format(cobranca_max_dias=60)
    assert "COUNT(*)" in sql and "-60" in sql


def test_demo_promo_relampago_tem_forma_da_query():
    linhas = demo_data.promo_relampago()
    assert len(linhas) >= 3
    for r in linhas:
        assert {"codigo", "promo_inicio", "promo_fim", "preco_relampago"} <= set(r)
    # exercita os 3 casos do cruzamento: com validade urgente (2411),
    # sem validade registrada (3905) e fora do catalogo (9999)
    cods = {str(r["codigo"]) for r in linhas}
    assert {"2411", "3905", "9999"} <= cods


def test_demo_pedidos_cobranca_tem_forma_da_query():
    linhas = demo_data.pedidos_cobranca()
    assert len(linhas) >= 3
    for r in linhas:
        assert {"pedido", "data_pedido", "fornecedor", "previsao_entrega",
                "ddd", "telefone", "contato", "itens_pendentes",
                "valor_pendente"} <= set(r)
    # um deles e recente e sem previsao vencida -> o filtro do quadrante
    # (Task 3) precisa DEIXA-LO DE FORA
    from datetime import date
    hoje = date.today()
    recentes = [r for r in linhas
                if (hoje - date.fromisoformat(r["data_pedido"])).days < 7]
    assert recentes, "demo precisa de 1 pedido recente para exercitar o filtro"
