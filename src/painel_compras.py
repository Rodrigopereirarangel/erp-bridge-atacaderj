# -*- coding: utf-8 -*-
"""Painel de Compras (TV + PC) — junta 4 fontes e gera painel/index.html.

Quadrantes: validade x promocao relampago (SQL), ruptura de estoque (rounds do
detector-estoque), cobranca de fornecedor (SQL) e preco concorrente (copia do
revisao_Sxx.html do pricing). Cada fonte falha SOZINHA: o quadrante afetado
mostra "indisponivel desde <data>" e a geracao nunca aborta.
Spec: docs/superpowers/specs/2026-07-20-painel-compras-design.md
"""
import glob
import json
import os
import re
import shutil
from datetime import date, datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PADROES = {
    "dir_saida": None,             # default: <repo>/saida/painel
    "porta_http": 8477,
    "cobranca_dias_limiar": 7,
    "cobranca_max_dias": 60,
    "validade_urgente_dias": 30,
    "rodizio_segundos": 20,
    "reload_minutos": 5,
    "pricing_dados_dir": None,
    "detector_rounds_dir": None,
    "detector_dashboard_url": "",
}


def _cod(c):
    """Codigo de produto como string canonica ('18464.0' -> '18464')."""
    s = str(c).strip()
    return s[:-2] if s.endswith(".0") else s


def _dias(de, ate):
    """Dias corridos entre datas ISO (str ou date); positivo se ate > de."""
    d1 = date.fromisoformat(str(de)[:10])
    d2 = date.fromisoformat(str(ate)[:10])
    return (d2 - d1).days


def cruzar_validade_relampago(relampago, validades, catalogo, hoje):
    """Uma linha por produto em relampago VIGENTE, com validades e urgencia.
    Produto sem validade registrada (~18% do catalogo) NAO some: sai com
    dias_ate_vencer=None para o comprador ver o buraco de cobertura."""
    cat = {_cod(r["codigo"]): r for r in catalogo or []}
    vals = {}
    for r in validades or []:
        if r.get("validade"):
            vals.setdefault(_cod(r["codigo"]), []).append(str(r["validade"])[:10])

    escolhido = {}   # codigo -> linha de relampago com promo_fim MAIS PROXIMO
    for r in relampago or []:
        c = _cod(r["codigo"])
        if c not in escolhido or str(r["promo_fim"]) < str(escolhido[c]["promo_fim"]):
            escolhido[c] = r

    itens = []
    for c, r in escolhido.items():
        vs = sorted(vals.get(c, []))
        info = cat.get(c)
        itens.append({
            "codigo": c,
            "descricao": (info or {}).get("descricao") or "(fora do catalogo)",
            "curva": (info or {}).get("curva"),
            "preco_relampago": r.get("preco_relampago"),
            "promo_inicio": str(r.get("promo_inicio"))[:10],
            "promo_fim": str(r.get("promo_fim"))[:10],
            "validades": vs,
            "dias_ate_vencer": _dias(hoje, vs[0]) if vs else None,
        })
    itens.sort(key=lambda i: (i["dias_ate_vencer"] is None,
                              i["dias_ate_vencer"], i["codigo"]))
    return itens
