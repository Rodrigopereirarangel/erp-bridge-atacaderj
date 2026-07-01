# -*- coding: utf-8 -*-
"""Dados sinteticos (fakes) para validar o formato de saida SEM tocar no banco.
Roda com `python src/bridge.py --demo`. Serve para conferir se produtos.json e
os CSVs saem no formato que cada consumidor espera, antes de termos o SQL real.
"""

from datetime import date, timedelta


def catalogo():
    base = [
        ("2411", "KELLOGGS SUCRILHOS 240G", 12, 14.20, 18.90, 22.50, 16.90, "A", "Kelloggs", "Matinais"),
        ("2795", "MINEIRINHO 250ML", 24, 1.05, 1.79, 2.49, None, "B", "Mineirinho", "Limpeza"),
        ("3905", "SAPOLIO RADIUM 450ML", 12, 2.30, 3.49, 4.20, 2.99, "C", "Bombril", "Limpeza"),
    ]
    return [
        {"codigo": c, "descricao": d, "embalagem": q, "custo": cu,
         "preco_atacado": pa, "preco_varejo": pv, "preco_promocao": pp,
         "curva": cv, "fornecedor": fo, "categoria": ca, "ativo": 1}
        for (c, d, q, cu, pa, pv, pp, cv, fo, ca) in base
    ]


def vendas(janela_dias=120):
    hoje = date.today()
    linhas = []
    for cod, desc in [("2411", "KELLOGGS SUCRILHOS 240G"), ("2795", "MINEIRINHO 250ML")]:
        for k in range(0, min(janela_dias, 90), 3):
            d = hoje - timedelta(days=k)
            qtd = 5 + (k % 7)
            linhas.append({"codigo": cod, "descricao": desc, "data": d.isoformat(),
                           "qtd_vendida": qtd, "valor": round(qtd * 18.9, 2)})
    return linhas


def recebimentos():
    hoje = date.today()
    return [
        {"codigo": "2411", "data_ultimo_recebimento": (hoje - timedelta(days=9)).isoformat(), "qtd_recebida": 120},
        {"codigo": "2795", "data_ultimo_recebimento": (hoje - timedelta(days=2)).isoformat(), "qtd_recebida": 480},
    ]


def pedidos():
    hoje = date.today()
    return [
        {"codigo": "2411", "data_pedido": (hoje - timedelta(days=3)).isoformat(),
         "qtd_pedida": 240, "status": "aberto",
         "previsao_entrega": (hoje + timedelta(days=4)).isoformat(), "fornecedor": "Kelloggs"},
    ]
