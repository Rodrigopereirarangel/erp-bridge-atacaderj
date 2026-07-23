# -*- coding: utf-8 -*-
"""Regra 2 do spec: estoque minimo = mediana das somas de janelas rolantes
de 45 dias sobre 180 dias de vendas diarias.

- janela com N+ dias SEGUIDOS sem venda e descartada (ruptura); N por curva
  ABC (A=10, B=20, C=30; sem curva = 20) — decisao do dono 22/07;
- janelas anteriores a primeira venda nao contam (novo nao e ruptura);
- nenhuma janela limpa -> mediana de TODAS (marca "*", dono 22/07);
- produto novo (1a venda ha menos de `janela` dias) -> media diaria desde a
  1a venda x janela (marca "novo");
- sem venda no historico -> (None, "sem_venda")."""
from datetime import timedelta
from statistics import median

LIMIAR_POR_CURVA = {"A": 10, "B": 20, "C": 30}
LIMIAR_PADRAO = 20


def calcular(vendas, fim, curva, janela=45, historico=180, limiares=None):
    """vendas: {"YYYY-MM-DD": unidades}; fim: date. -> (unidades, marca)."""
    tabela = limiares if limiares is not None else LIMIAR_POR_CURVA
    limiar = tabela.get((curva or "").strip().upper() or None, LIMIAR_PADRAO)

    serie = []
    for i in range(historico):
        dia = (fim - timedelta(days=historico - 1 - i)).isoformat()
        serie.append(float(vendas.get(dia, 0.0)))

    primeira = next((i for i, v in enumerate(serie) if v > 0), None)
    if primeira is None:
        return None, "sem_venda"

    if primeira > len(serie) - janela:
        desde = serie[primeira:]
        media = sum(desde) / len(desde)
        return media * janela, "novo"

    somas_limpas, somas_todas = [], []
    for inicio in range(primeira, len(serie) - janela + 1):
        w = serie[inicio:inicio + janela]
        soma = sum(w)
        somas_todas.append(soma)
        if _maior_streak_zero(w) < limiar:
            somas_limpas.append(soma)

    if somas_limpas:
        return float(median(somas_limpas)), ""
    return float(median(somas_todas)), "*"


def _maior_streak_zero(valores):
    maior = atual = 0
    for v in valores:
        atual = atual + 1 if v == 0 else 0
        maior = max(maior, atual)
    return maior
