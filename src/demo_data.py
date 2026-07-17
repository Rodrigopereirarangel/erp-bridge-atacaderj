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
    itens = [
        {"codigo": c, "descricao": d, "embalagem": q, "custo_atual": cu,
         "preco_atacado": pa, "preco_varejo": pv, "preco_promocao": pp,
         "curva": cv, "ativo": 1}
        for (c, d, q, cu, pa, pv, pp, cv) in base
    ]
    # itens DE EXPOSICAO: codigo em INT, no mesmo tipo de demo_data.vendas_canal()
    # e da query real VENDAS_CANAL (codigo sai limpo, sem sufixo .0 -- conferido
    # no CSV real do ponte em 2026-07-17). Sem isto, vendas_canal.csv e
    # catalogo_exposicao.csv nao compartilhavam NENHUM codigo e o join do
    # calculo de exposicao nunca exercitava nada no --demo. embalagem = caixa-mae
    # REAL desses codigos (ver comentario de VENDAS_CANAL em queries.py para o
    # 18464); prateleira preenchida p/ exercitar catalogo_exposicao_csv.
    exposicao = [
        (18464, "LEITE COND PIRACANJUBA 395G", 27, 3.50, 4.20, 4.99, None, "A", "PRATELEIRA 1"),
        (34743, "ITEM EXPOSICAO DEMO 2", 12, 2.10, 2.80, 3.50, None, "B", "PRATELEIRA 2"),
        (16416, "ITEM EXPOSICAO DEMO 3", 10, 5.00, 6.20, 7.50, None, "C", "PRATELEIRA 1"),
        (42309, "ITEM EXPOSICAO DEMO 4", 52, 1.20, 1.60, 1.99, None, "B", "PRATELEIRA 2"),
    ]
    itens += [
        {"codigo": c, "descricao": d, "embalagem": q, "custo_atual": cu,
         "preco_atacado": pa, "preco_varejo": pv, "preco_promocao": pp,
         "curva": cv, "prateleira": pr, "ativo": 1}
        for (c, d, q, cu, pa, pv, pp, cv, pr) in exposicao
    ]
    return itens


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


def validades(janela_dias=180):
    """Validade das 2 ultimas notas por produto (forma da query VALIDADES).
    2411: uma vence em 19 dias (ALERTA <45) e outra em 73 dias (ok).
    2795: uma so validade. 3905: nenhuma (fica sem validade na cotacao)."""
    hoje = date.today()
    plano = [
        ("2411", [19, 73]),
        ("2795", [140]),
    ]
    linhas = []
    for cod, dias in plano:
        for d in dias:
            linhas.append({"codigo": cod,
                           "validade": (hoje + timedelta(days=d)).isoformat()})
    return linhas


def vendas_mensal(meses=3):
    """Unidades por produto x mes FECHADO (mesma forma da query VENDAS_MENSAL)."""
    hoje = date.today().replace(day=1)
    linhas = []
    for k in range(1, meses + 1):
        m = (hoje.month - k - 1) % 12 + 1
        a = hoje.year - (1 if hoje.month - k < 1 else 0)
        mes = f"{a:04d}-{m:02d}"
        for cod, desc, base, preco in [("2411", "KELLOGGS SUCRILHOS 240G", 180, 18.9),
                                       ("2795", "MINEIRINHO 250ML", 960, 1.79),
                                       ("3905", "SAPOLIO RADIUM 450ML", 55, 3.49)]:
            qtd = base + k * 7
            linhas.append({"codigo": cod, "descricao": desc, "mes": mes,
                           "qtd_un": qtd, "valor": round(qtd * preco, 2)})
    return linhas


def ultimo_custo():
    """Custo da ultima entrada por produto (com/sem difal), forma da ULTIMO_CUSTO."""
    hoje = date.today()
    return [
        {"codigo": "2411", "custo_com_difal": 16.02, "custo_sem_difal": 14.20,
         "data_entrada": (hoje - timedelta(days=9)).isoformat()},
        {"codigo": "2795", "custo_com_difal": 1.05, "custo_sem_difal": 1.05,
         "data_entrada": (hoje - timedelta(days=2)).isoformat()},
    ]


def historico_cliente(meses=24):
    """Compras por cliente (forma da HISTORICO_CLIENTE): itens de pedido de
    venda/DAV com valor/custo TOTAIS da linha. Cobre os casos do consumidor:
    item regular, item que parou, grupo "INATIVOS OU FORA DO MIX" (deve virar
    vazio no CSV) e grupo ja vazio."""
    hoje = date.today()

    def linha(cli, cod, nome, dias_atras, emb, upe, qtde_emb, vu, cu, grupo):
        un = qtde_emb * upe
        return {"cliente": cli, "codigo": cod, "produto": nome,
                "data": (hoje - timedelta(days=dias_atras)).isoformat(),
                "emb": emb, "unidades_por_emb": upe, "qtde_emb": qtde_emb,
                "unidades": un, "valor": round(un * vu, 2),
                "custo": round(un * cu, 2), "grupo": grupo}

    linhas = []
    # MERCADO DEMO: sucrilhos regular (~10 em 10 dias) + refri que PAROU (60d+)
    for k in (5, 15, 25, 35):
        linhas.append(linha("MERCADO DEMO LTDA", 2411, "KELLOGGS SUCRILHOS 240G",
                            k, "CX-12", 12, 2, 18.90, 14.20, "MATINAIS"))
    for k in (60, 75, 90, 105):
        linhas.append(linha("MERCADO DEMO LTDA", 2795, "MINEIRINHO 250ML",
                            k, "CX-24", 24, 3, 1.79, 1.05, "BEBIDAS"))
    # BAR DEMO: item fora do mix (grupo deve sair vazio) + item sem familia
    linhas.append(linha("BAR DEMO ME", 3905, "SAPOLIO RADIUM 450ML",
                        10, "CX-12", 12, 1, 3.49, 2.30, "INATIVOS OU FORA DO MIX"))
    linhas.append(linha("BAR DEMO ME", 4001, "ITEM SEM FAMILIA 1UN",
                        20, "UN", 1, 5, 2.00, 1.50, ""))
    return linhas


def pedidos():
    hoje = date.today()
    return [
        {"codigo": "2411", "data_pedido": (hoje - timedelta(days=3)).isoformat(),
         "qtd_pedida": 240, "status": "aberto",
         "previsao_entrega": (hoje + timedelta(days=4)).isoformat(), "fornecedor": "Kelloggs"},
    ]


def vendas_canal(janela_dias=400):
    """Venda por item/dia/canal falsa. Sabado pesa ~2,3x a segunda (como na loja
    real) e domingo nao vende — assim o --demo exercita o calendario e o fator
    de dia-da-semana do consumidor."""
    from datetime import date, timedelta
    hoje = date.today()
    itens = [(18464, 30.0), (34743, 8.0), (16416, 3.0), (42309, 0.05)]
    peso_dia = {0: 0.7, 1: 0.8, 2: 0.9, 3: 1.1, 4: 1.3, 5: 1.6}  # seg..sab
    linhas = []
    for d in range(janela_dias):
        dia = hoje - timedelta(days=d)
        if dia.weekday() == 6:  # domingo: loja fechada
            continue
        for cod, base in itens:
            un = round(base * peso_dia[dia.weekday()], 3)
            if un > 0:
                linhas.append({"codigo": cod, "data": dia.isoformat(),
                               "canal": "salao", "unidades": un})
            if cod in (18464, 34743) and d % 3 == 0:   # atacado e esporadico e grande
                linhas.append({"codigo": cod, "data": dia.isoformat(),
                               "canal": "atacado", "unidades": round(base * 20, 3)})
    return linhas
