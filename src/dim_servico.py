# -*- coding: utf-8 -*-
"""Tempo de atendimento por cupom + handover (a troca de cliente).

HoraFim - HoraInicio mede so o cupom passando. A troca de cliente (o anterior
sair, o proximo chegar, ensacar) NAO esta la — e usar o valor cru
subdimensiona. O handover e estimado dos dados: quando ha fila, o intervalo
entre o fim de um cupom e o inicio do seguinte NO MESMO PDV *e* a troca pura.
Gap acima do corte e ociosidade (nao havia proximo cliente), nao troca.
"""
import math


def percentil(valores, p):
    """Percentil com interpolacao linear (mesma convencao do numpy)."""
    if not valores:
        return 0
    ordenado = sorted(valores)
    if len(ordenado) == 1:
        return ordenado[0]
    k = (len(ordenado) - 1) * p
    baixo, alto = math.floor(k), math.ceil(k)
    if baixo == alto:
        return ordenado[int(k)]
    return ordenado[baixo] * (alto - k) + ordenado[alto] * (k - baixo)


def duracoes(cupons):
    """Segundos de HoraInicio a HoraFim, na ordem recebida."""
    return [(c["fim"] - c["inicio"]).total_seconds() for c in cupons]


def _gaps_por_pdv(cupons):
    """Intervalos entre cupons consecutivos DENTRO do mesmo PDV, mesmo dia."""
    por_pdv = {}
    for c in cupons:
        por_pdv.setdefault((c["pdv"], c["inicio"].date()), []).append(c)
    gaps = []
    for lista in por_pdv.values():
        lista.sort(key=lambda c: c["inicio"])
        for anterior, atual in zip(lista, lista[1:]):
            gaps.append((atual["inicio"] - anterior["fim"]).total_seconds())
    return gaps


def estimar_handover(cupons, corte_seg=120.0):
    """Mediana dos gaps em (0, corte_seg]. 0.0 se nao houver gap valido."""
    validos = [g for g in _gaps_por_pdv(cupons) if 0 < g <= corte_seg]
    if not validos:
        return 0.0
    return float(percentil(validos, 0.5))


def servicos_por_operador(cupons, handover):
    """Tempo de ocupacao do caixa por cupom (duracao + handover), por operador."""
    por_op = {}
    for c in cupons:
        dur = (c["fim"] - c["inicio"]).total_seconds() + handover
        por_op.setdefault(c["operador"], []).append(dur)
    return por_op
