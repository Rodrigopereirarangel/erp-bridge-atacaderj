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


def copiar_revisao_pricing(dados_dir, dir_saida):
    """Copia o revisao_<AAAA>-S<ww>.html MAIS NOVO do pricing para a pasta do
    painel (nome fixo revisao_pricing.html -> link estavel no HTML).
    Ordena por (ano, int(semana)): lexicografico faria S9 > S10."""
    if not dados_dir or not os.path.isdir(dados_dir):
        return None
    padrao = re.compile(r"revisao_(\d{4})-S(\d+)\.html$")
    candidatos = []
    for arq in glob.glob(os.path.join(dados_dir, "revisao_*.html")):
        m = padrao.search(os.path.basename(arq))
        if m:
            candidatos.append((int(m.group(1)), int(m.group(2)), arq))
    if not candidatos:
        return None
    ano, sem, origem = max(candidatos)
    os.makedirs(dir_saida, exist_ok=True)
    shutil.copyfile(origem, os.path.join(dir_saida, "revisao_pricing.html"))
    mtime = datetime.fromtimestamp(os.path.getmtime(origem))
    return {"rotulo": f"{ano}-S{sem}", "arquivo": "revisao_pricing.html",
            "modificado_em": mtime.strftime("%Y-%m-%d %H:%M")}


def renderizar(payload):
    """Embute o payload no template (mesmo padrao do vendas_mensal_dashboard:
    placeholder /*__DADOS__*/null e escape de '</' para nao fechar o <script>)."""
    template = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "templates", "painel_compras.html")
    with open(template, encoding="utf-8") as f:
        html = f.read()
    dados = json.dumps(payload, ensure_ascii=False, indent=1, default=str)
    return html.replace("/*__DADOS__*/null", dados.replace("</", "<\\/"))


def _consulta(conn, sql, quadrante, erros):
    """SELECT com falha isolada: registra o 1o erro do quadrante e devolve None."""
    import db
    try:
        return db.consultar(conn, sql)
    except Exception as e:  # noqa: BLE001 — qualquer falha vira aviso no quadrante
        erros.setdefault(quadrante, str(e))
        return None


def rodar(cfg, usar_demo=False):
    """Gera <dir_saida>/index.html + dados_painel.json a partir das 4 fontes.
    Devolve as linhas de relatorio para o [OK] do bridge."""
    import demo_data
    import projections
    cfgp = dict(PADROES)
    cfgp.update(cfg.get("painel") or {})
    destino = cfgp.get("dir_saida") or os.path.join(RAIZ, "saida", "painel")
    os.makedirs(destino, exist_ok=True)
    gerado_em = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hoje = date.today().isoformat()

    # --- fontes SQL (cada quadrante falha sozinho) ---
    erros = {}
    cat = val = relamp = cob = None
    aband = 0
    if usar_demo:
        cat, val = demo_data.catalogo(), demo_data.validades()
        relamp, cob = demo_data.promo_relampago(), demo_data.pedidos_cobranca()
        aband = 2
    else:
        import db
        import queries
        try:
            conn = db.conectar(cfg["db"])
        except Exception as e:  # noqa: BLE001
            erros["validade_relampago"] = erros["cobranca"] = f"banco inacessivel: {e}"
        else:
            try:
                jan = int(cfg.get("janela_entradas_dias", 180))
                max_d = int(cfgp["cobranca_max_dias"])
                cat = _consulta(conn, queries.CATALOGO, "validade_relampago", erros)
                val = _consulta(conn, queries.VALIDADES.format(janela_entradas=jan),
                                "validade_relampago", erros) or []
                relamp = _consulta(conn, queries.PROMO_RELAMPAGO,
                                   "validade_relampago", erros)
                cob = _consulta(conn, queries.PEDIDOS_COBRANCA.format(
                    cobranca_max_dias=max_d), "cobranca", erros)
                ab = _consulta(conn, queries.PEDIDOS_ABANDONADOS.format(
                    cobranca_max_dias=max_d), "cobranca", erros)
                aband = int(ab[0]["n"]) if ab else 0
            finally:
                conn.close()

    q_validade = {"carimbo": gerado_em, "erro": erros.get("validade_relampago"),
                  "itens": []}
    if relamp is not None and cat is not None:
        q_validade["itens"] = cruzar_validade_relampago(relamp, val, cat, hoje)

    q_cobranca = {"carimbo": gerado_em, "erro": erros.get("cobranca"),
                  "itens": [], "abandonados": aband}
    if cob is not None:
        q_cobranca["itens"] = montar_cobranca(
            cob, hoje, int(cfgp["cobranca_dias_limiar"]))

    q_ruptura = {"carimbo": None, "erro": None, "itens": []}
    try:
        r = carregar_ruptura(cfgp.get("detector_rounds_dir"))
        if r is None:
            q_ruptura["erro"] = "nenhuma rodada do detector encontrada"
        else:
            q_ruptura["carimbo"], q_ruptura["itens"] = r["ref"], r["itens"]
    except Exception as e:  # noqa: BLE001
        q_ruptura["erro"] = f"falha lendo a rodada do detector: {e}"

    q_conc = {"carimbo": None, "erro": None, "rotulo": None, "arquivo": None}
    try:
        rv = copiar_revisao_pricing(cfgp.get("pricing_dados_dir"), destino)
        if rv is None:
            q_conc["erro"] = "nenhum revisao_Sxx.html do pricing encontrado"
        else:
            q_conc.update({"carimbo": rv["modificado_em"], "rotulo": rv["rotulo"],
                           "arquivo": rv["arquivo"]})
    except Exception as e:  # noqa: BLE001
        q_conc["erro"] = f"falha copiando a revisao do pricing: {e}"

    payload = {
        "origem": "erp-bridge-painel", "gerado_em": gerado_em,
        "cfg": {k: cfgp[k] for k in ("rodizio_segundos", "reload_minutos",
                                     "validade_urgente_dias",
                                     "cobranca_dias_limiar",
                                     "detector_dashboard_url")},
        "validade_relampago": q_validade,
        "ruptura": q_ruptura,
        "cobranca": q_cobranca,
        "concorrente": q_conc,
    }
    dados = json.dumps(payload, ensure_ascii=False, indent=1, default=str)
    projections._escrever_atomico(os.path.join(destino, "dados_painel.json"),
                                  dados.encode("utf-8"))
    projections._escrever_atomico(os.path.join(destino, "index.html"),
                                  renderizar(payload).encode("utf-8"))

    avisos = [q for q, e in (("validade", q_validade["erro"]),
                             ("ruptura", q_ruptura["erro"]),
                             ("cobranca", q_cobranca["erro"]),
                             ("concorrente", q_conc["erro"])) if e]
    resumo = (f"painel/index.html: {len(q_validade['itens'])} relampago, "
              f"{len(q_ruptura['itens'])} ruptura, "
              f"{len(q_cobranca['itens'])} cobranca (+{aband} abandonados)"
              + (f" — AVISO em: {', '.join(avisos)}" if avisos else ""))
    return [resumo]
