# -*- coding: utf-8 -*-
"""Exibicao: quantidade (cx-mae teto / un / kg) e ruas do deposito.

RUAS copiadas VERBATIM de deposito-atacaderj/src/ruas.py (fonte da verdade:
docs/RUAS.md daquele repo, dono 20-22/07). Se o dono mudar rua la, atualizar
aqui tambem — sao 26 linhas, copia consciente em vez de import entre repos."""
import math

RUAS = [
    (1, "bisc1"), (2, "bisc1"), (3, "bisc2"), (4, "bebidas"),
    (5, "balas1"), (6, "balas2"), (7, "confeit"), (8, "perf/desc"),
    (9, ""), (10, "mat1"), (11, "mat2"), (12, "mat3"),
    (13, "cons1"), (14, "cons1/limp1"), (15, "cons2/limp2"),
    (16, "foodsvc/limp3"), (17, "jirau"), (18, ""), (19, ""), (20, ""),
    (21, ""), (22, ""), (23, "jirau"), (24, "ROTATIVO"), (25, "TERREO"),
    (26, "vitrine"),
]
ROTULO_ESPECIAL = {26: "A24 vitrine"}   # dono 22/07: 26 e EXIBIDA como 24
_NOMES = dict(RUAS)


def exibir(unidades, embalagem, peso):
    if unidades is None:
        return "—"
    if peso:
        return f"{math.ceil(unidades)} kg"
    if embalagem and float(embalagem) > 1:
        return f"{math.ceil(unidades / float(embalagem))} cx"
    return f"{math.ceil(unidades)} un"


def rotulo_rua(rua):
    if rua is None:
        return ""
    if rua in ROTULO_ESPECIAL:
        return ROTULO_ESPECIAL[rua]
    nome = _NOMES.get(rua, "")
    return f"A{rua} {nome}" if nome else f"A{rua}"


def ordem_rua(rua):
    return (1, 0) if rua is None else (0, rua)
