# -*- coding: utf-8 -*-
"""Dados sinteticos (fakes) para validar o formato de saida SEM tocar no banco.
Roda com `python src/bridge.py --demo`. Serve para conferir se produtos.json e
os CSVs saem no formato que cada consumidor espera, antes de termos o SQL real.
"""

from datetime import date, timedelta


def catalogo():
    base = [
        ("2411", "KELLOGGS SUCRILHOS 240G", 12, 14.20, 18.90, 22.50, 16.90, "A"),
        ("2795", "MINEIRINHO 250ML", 24, 1.05, 1.79, 2.49, None, "B"),
        ("3905", "SAPOLIO RADIUM 450ML", 12, 2.30, 3.49, 4.20, 2.99, "C"),
    ]
    return [
        {"codigo": c, "descricao": d, "embalagem": q, "custo_atual": cu,
         "preco_atacado": pa, "preco_varejo": pv, "preco_promocao": pp,
         "curva": cv, "ativo": 1}
        for (c, d, q, cu, pa, pv, pp, cv) in base
    ]


def vendas(janela_dias=120):
    hoje = date.today()
    linhas = []
    for cod, desc in [("2411", "KELLOGGS SUCRILHOS 240G"), ("2795", "MINEIRINHO 250ML")]:
        for k in range(0, min(janela_dias, 90), 3):
            d = hoje - timedelta(days=k)
            qtd = 5 + (k % 7)
            linhas.append({"codigo": cod, "descricao": desc, "data": d.isoformat(),
                           "qtd_vendida": qtd, "valor": round(qtd * 18.9, 2),
                           "custo_venda": round(qtd * 14.2, 2)})
    return linhas


def entradas(janela_dias=180):
    """Varias entregas por item ao longo de ~6 meses (uma linha por entrada)."""
    hoje = date.today()
    plano = [
        ("2411", [(150, 100), (70, 100), (9, 120)]),   # 3 entregas
        ("2795", [(120, 480), (30, 480), (2, 480)]),
        ("3905", [(150, 60)]),                          # so 1 entrega (ex.: item de ruptura)
    ]
    linhas = []
    for cod, entregas in plano:
        for dias_atras, qtd in entregas:
            if dias_atras <= janela_dias:
                linhas.append({"codigo": cod,
                               "data": (hoje - timedelta(days=dias_atras)).isoformat(),
                               "qtd": qtd})
    return linhas


def pedidos():
    hoje = date.today()
    return [
        {"codigo": "2411", "data_pedido": (hoje - timedelta(days=3)).isoformat(),
         "qtd_pedida": 240, "status": "aberto",
         "previsao_entrega": (hoje + timedelta(days=4)).isoformat(), "fornecedor": "Kelloggs"},
    ]
