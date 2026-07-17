# -*- coding: utf-8 -*-
"""Agregacao P85 entre os dias + conversao da curva em escala de turnos.

O P85 e a margem de seguranca, e ela e explicita: em vez de inventar um fator
de correcao, dimensiona-se para o dia RUIM (85o percentil) e nao para o dia
mediano. Consequencia declarada: ~15% dos dias daquele dia da semana estouram
a meta. Isso e a escolha, nao um defeito.

Turno CLT 6h em slots de 30min: 13 slots de presenca (6h30), 12 produtivos
(6h), 1 de intervalo. O intervalo modelado (30min) e 10min maior que o real
(20min) — conservador de proposito.
"""
import math

import dim_servico


def curva_percentil(curvas_por_dia, p=0.85):
    """Por slot, o percentil p entre os dias, arredondado pra CIMA (caixa e
    inteiro). Dia em que o slot nao existiu conta como 0 caixa."""
    slots = set()
    for curva in curvas_por_dia.values():
        slots.update(curva.keys())
    saida = {}
    for s in sorted(slots):
        valores = [curva.get(s, 0) for curva in curvas_por_dia.values()]
        saida[s] = int(math.ceil(dim_servico.percentil(valores, p) - 1e-9))
    return saida


def cobertura_de(inicios, slots_turno=13, slots_produtivos=12):
    """Caixas cobertos por slot, dado {slot_inicial: quantos turnos}.

    O turno ocupa slots_turno slots; slots_turno - slots_produtivos deles sao
    intervalo. O intervalo e alocado no ULTIMO slot da presenca: como a
    cobertura e checada contra a curva, por o intervalo no fim e o pior caso e
    portanto seguro (nunca promete cobertura que nao existe no miolo do turno).
    """
    cobertura = {}
    for inicio, n in inicios.items():
        if n <= 0:
            continue
        for i in range(slots_produtivos):
            s = inicio + i
            cobertura[s] = cobertura.get(s, 0) + n
    return cobertura


def cobertura_minima(curva, slots_turno=13, slots_produtivos=12):
    """Menor numero de turnos que cobre a curva. Devolve (total, {inicio: n}).

    Guloso da esquerda para a direita: no primeiro slot descoberto, abre os
    turnos que faltam comecando NELE (comecar antes so desperdicaria os slots
    ja cobertos; comecar depois deixaria este slot descoberto). Para turnos de
    comprimento fixo e demanda por slot, este guloso e otimo.
    """
    exigido = {s: c for s, c in curva.items() if c > 0}
    if not exigido:
        return 0, {}
    inicios = {}
    for s in sorted(exigido):
        cobertura = cobertura_de(inicios, slots_turno, slots_produtivos)
        falta = exigido[s] - cobertura.get(s, 0)
        if falta > 0:
            inicios[s] = inicios.get(s, 0) + falta
    return sum(inicios.values()), inicios
