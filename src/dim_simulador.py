# -*- coding: utf-8 -*-
"""Simulacao de eventos discretos da fila de caixas (M/G/c, fila unica FIFO).

Por que simular em vez de usar Erlang-C direto: Erlang-C assume chegada Poisson
e servico exponencial. A loja real nao e nenhum dos dois — gente chega em
rajada, o servico e menos variavel que exponencial, a fila atravessa as faixas
e as operadoras tem velocidades diferentes. Simular com as chegadas REAIS e a
distribuicao empirica ELIMINA esses erros em vez de compensa-los com um chute.

Fila UNICA: modela o cliente indo para a fila mais curta (jockeying), que e o
comportamento real. Fila por caixa, sem troca, seria pior que isto.

Erlang-C continua sendo o oraculo: em tests/test_dim_simulador.py este
simulador tem que reproduzir a formula fechada num caso M/M/c.
"""
import heapq

SLOT_SEG = 1800


def _ajustar_pool(livres, c_novo, agora):
    """Poe o pool em c_novo caixas.

    Abrindo: caixa novo entra livre em 'agora'.
    Fechando: fecha primeiro o OCIOSO (free <= agora — a operadora foi embora);
    se nao houver ocioso suficiente, sai o que termina mais tarde — ele conclui
    o cliente em curso (a espera desse cliente ja foi contabilizada no inicio
    do atendimento) e simplesmente nao pega mais ninguem.
    """
    while len(livres) < c_novo:
        heapq.heappush(livres, agora)
    if len(livres) <= c_novo:
        return
    ordenado = sorted(livres)
    ociosos = [x for x in ordenado if x <= agora]
    ocupados = [x for x in ordenado if x > agora]
    excesso = len(ordenado) - c_novo
    fecha = min(excesso, len(ociosos))
    ociosos = ociosos[fecha:]
    excesso -= fecha
    if excesso > 0:
        ocupados = ocupados[:len(ocupados) - excesso]
    livres[:] = ociosos + ocupados
    heapq.heapify(livres)


def simular(chegadas, servicos, curva, slot_seg=SLOT_SEG):
    """Espera (segundos) de cada cliente, na ordem de chegada.

    chegadas: segundos desde a meia-noite, ORDENADO.
    servicos: tempo de ocupacao do caixa por cliente (mesma ordem).
    curva: {slot: numero de caixas abertos}.
    None = nenhum caixa aberto no slot (cliente nao atendido).
    """
    livres = []
    slot_visto = None
    esperas = []
    for t, s in zip(chegadas, servicos):
        slot = int(t // slot_seg)
        if slot != slot_visto:
            _ajustar_pool(livres, int(curva.get(slot, 0)), slot * slot_seg)
            slot_visto = slot
        if not livres:
            esperas.append(None)
            continue
        livre_em = heapq.heappop(livres)
        inicio = t if livre_em <= t else livre_em
        esperas.append(inicio - t)
        heapq.heappush(livres, inicio + s)
    return esperas
