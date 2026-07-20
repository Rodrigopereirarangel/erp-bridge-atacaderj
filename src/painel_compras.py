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


def montar_cobranca(pedidos, hoje, limiar_dias=7):
    """Pedidos que merecem cobranca: abertos ha >= limiar OU previsao vencida.
    A query ja cortou na janela maxima (cobranca_max_dias); os mais velhos que
    ela viram so o contador de 'abandonados' (fora daqui)."""
    itens = []
    for r in pedidos or []:
        dias = _dias(r["data_pedido"], hoje)
        prev = str(r["previsao_entrega"])[:10] if r.get("previsao_entrega") else None
        atraso = _dias(prev, hoje) if prev else 0
        atraso = atraso if atraso > 0 else 0
        if dias < limiar_dias and atraso == 0:
            continue
        num = (r.get("telefone") or "").strip()
        ddd = (r.get("ddd") or "").strip()
        dig = re.sub(r"\D", "", num)
        tel = f"({ddd}) {num}" if dig and set(dig) != {"0"} else ""
        itens.append({
            "pedido": r["pedido"],
            "fornecedor": r["fornecedor"],
            "data_pedido": str(r["data_pedido"])[:10],
            "dias_aberto": dias,
            "previsao_entrega": prev,
            "atraso_previsao": atraso,
            "itens_pendentes": int(r.get("itens_pendentes") or 0),
            "valor_pendente": float(r.get("valor_pendente") or 0),
            "telefone": tel,
            "contato": (r.get("contato") or "").strip(),
        })
    itens.sort(key=lambda i: (-i["dias_aberto"], -i["valor_pendente"]))
    return itens


def carregar_ruptura(rounds_dir):
    """Rodada mais recente do detector-estoque, traduzida para o painel.
    Items ja vem ordenados por scorePrioridade desc (detectAll.js)."""
    if not rounds_dir or not os.path.isdir(rounds_dir):
        return None
    arquivos = sorted(glob.glob(os.path.join(rounds_dir, "*.json")))
    if not arquivos:
        return None
    with open(arquivos[-1], encoding="utf-8") as f:
        rodada = json.load(f)
    itens = [{
        "codigo": _cod(i.get("codigo")),
        "descricao": i.get("descricao"),
        "prioridade": i.get("scorePrioridade"),
        "probabilidade": i.get("probabilidade"),
        "tem_pedido": bool(i.get("temPedido")),
        "curva": i.get("curvaABC"),
        "un_mes": i.get("unMes"),
        "rs_hist": i.get("rsHist"),
        "dias_parado": i.get("diasParado"),
        "cobertura_esgotada": bool(i.get("coberturaEsgotada")),
    } for i in rodada.get("items", [])]
    return {"ref": rodada.get("refDate") or rodada.get("id"), "itens": itens}
