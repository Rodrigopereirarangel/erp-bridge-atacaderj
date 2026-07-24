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


def corredor_curto(nome):
    """Endereco do sistema (tela Pega) enxuto p/ a coluna corredor:
    "ATACADO 1" -> "AT 1", "ATACADO 2" -> "AT 2", "VAREJO" -> "VAREJO"
    (dono, 24/07). Serve tambem p/ o corredor mercadologico antigo
    ("CORREDOR 130(DOCE)" -> "130(DOCE)"), caso volte a ser usado."""
    txt = str(nome or "").strip()
    if not txt or txt.upper() in ("SEM CLASSIFICACAO", "VAREJO"):
        # VAREJO nao e corredor de deposito (dono, 24/07): sai vazio,
        # igual a quem nao tem endereco nenhum cadastrado
        return ""
    sem = txt.upper()
    if sem.startswith("ATACADO"):
        return "AT " + txt[len("ATACADO"):].strip()
    if sem.startswith("CORREDOR"):
        return txt[len("CORREDOR"):].strip()
    return txt


def ean_exibir(ean_cx, ean_un):
    """EAN p/ conferencia (dono, 24/07): SO um por linha — o da CAIXA-MAE
    manda; sem ele, o da unidade. Devolve (numero, tipo) com tipo "CX" ou
    "UN" p/ o operador saber o que esta bipando; sem EAN -> ("", "")."""
    cx = str(ean_cx or "").strip()
    if cx:
        return cx, "CX"
    un = str(ean_un or "").strip()
    return (un, "UN") if un else ("", "")


def ordem_rua(rua):
    """Ordena pelo NUMERO EXIBIDO: a rua interna 26 aparece como "A24
    vitrine" e por isso ordena logo apos a 24 ROTATIVO e ANTES da A25
    TERREO (dono, 22/07). Sem rua vai para o fim."""
    if rua is None:
        return (1, 0, 0)
    if rua == 26:
        return (0, 24, 1)
    return (0, rua, 0)
