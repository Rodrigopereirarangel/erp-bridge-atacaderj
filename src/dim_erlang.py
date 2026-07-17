# -*- coding: utf-8 -*-
"""Erlang-B / Erlang-C em forma fechada — o ORACULO que valida o simulador.

Erlang-C responde: com carga 'a' Erlangs e 'c' caixas, qual a chance de um
cliente esperar mais que t segundos. Assume chegada Poisson e servico
exponencial (por isso NAO e o numero final: a loja real nao e nenhum dos dois
— ver o spec). Serve para (1) provar que o simulador esta certo num caso onde
a resposta e conhecida e (2) conferir a sanidade do resultado real.
"""
import math


def erlang_b(c, a):
    """Erlang-B por recursao (estavel numericamente; a formula direta com
    fatorial estoura para c grande). B(0,a)=1; B(n,a)=a*B(n-1,a)/(n+a*B(n-1,a))."""
    if a <= 0:
        return 0.0
    b = 1.0
    for n in range(1, int(c) + 1):
        b = a * b / (n + a * b)
    return b


def erlang_c(c, a):
    """P(cliente ter que esperar) na fila M/M/c. a >= c => fila explode => 1.0."""
    if a <= 0:
        return 0.0
    if a >= c:
        return 1.0
    b = erlang_b(c, a)
    return b / (1.0 - (a / c) * (1.0 - b))


def prob_espera_maior(c, a, t, ts):
    """P(W > t). a = carga em Erlangs (= chegadas/seg * ts), ts = servico medio."""
    if a <= 0:
        return 0.0
    if a >= c:
        return 1.0
    return erlang_c(c, a) * math.exp(-(c - a) * t / ts)


def caixas_minimos(a, ts, meta_pct, meta_seg, c_max):
    """Menor c com P(W > meta_seg) <= 1 - meta_pct. Devolve c_max se nao houver."""
    alvo = 1.0 - meta_pct
    for c in range(1, int(c_max) + 1):
        if prob_espera_maior(c, a, meta_seg, ts) <= alvo:
            return c
    return int(c_max)
