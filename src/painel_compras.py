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

import historico_painel

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PADROES = {
    "dir_saida": None,             # default: <repo>/saida/painel
    "porta_http": 8477,
    "cobranca_dias_limiar": 7,
    "cobranca_max_dias": 30,
    "cobranca_alerta_dias": 21,
    "prepedido_dias": 21,
    "avaria_esquecido_dias": 60,
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
            # sobra de validade quando a promocao acabar (negativo = vence antes)
            "dias_pos_promo": (_dias(str(r.get("promo_fim"))[:10], vs[0])
                               if vs and r.get("promo_fim") else None),
            # dono (21/07): "dias para vencer" = dias para FINALIZAR A REBAIXA
            "dias_fim_promo": (_dias(hoje, str(r.get("promo_fim"))[:10])
                               if r.get("promo_fim") else None),
        })
    itens.sort(key=lambda i: (i["dias_fim_promo"] is None,
                              i["dias_fim_promo"], i["codigo"]))
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
    # ordem CRESCENTE de dias (decisao do dono, 20/07): trabalhar primeiro o
    # que ainda tem salvacao; empate = maior valor pendente primeiro
    itens.sort(key=lambda i: (i["dias_aberto"], -i["valor_pendente"]))
    return itens


def _pedido_dias(item, hoje):
    """Dias desde a data do pedido de compra do item (None se nao ha pedido
    ou a data vier ilegivel — round e arquivo externo, nunca derruba)."""
    ped = item.get("pedido") or {}
    data = str(ped.get("dataPedido") or "")[:10]
    if not item.get("temPedido") or not data:
        return None
    try:
        return _dias(data, hoje)
    except ValueError:
        return None


def montar_prepedidos(linhas, hoje):
    """Pre-pedidos abertos normalizados: dias desde a criacao; mais novo
    primeiro (a query ja filtra abertos e a janela de dias)."""
    itens = []
    for r in linhas or []:
        data = str(r.get("data_pre"))[:10]
        itens.append({
            "pre_pedido": r.get("pre_pedido"),
            "fornecedor": r.get("fornecedor") or "",
            "data_pre": data,
            "dias": _dias(data, hoje),
            "limite": (str(r.get("limite"))[:10] if r.get("limite") else None),
            "itens": int(r.get("itens") or 0),
            "valor": float(r.get("valor") or 0),
        })
    itens.sort(key=lambda i: (i["dias"], -i["valor"]))
    return itens


def montar_avaria(linhas, hoje, esquecido_dias=60):
    """Saldo parado na area de troca/avaria: idade = dias desde a ultima
    movimentacao (tipo 3); "esquecido" = acima de esquecido_dias (dono,
    22/07: regua de 60d). Ordena por R$ parado, maior primeiro."""
    itens = []
    for r in linhas or []:
        ult = str(r.get("ultima_mov"))[:10] if r.get("ultima_mov") else None
        idade = _dias(ult, hoje) if ult else None
        itens.append({
            "codigo": _cod(r.get("codigo")),
            "descricao": r.get("descricao") or "",
            "qtd": float(r.get("qtd") or 0),
            "valor": float(r.get("valor") or 0),
            "idade": idade,
            "esquecido": idade is not None and idade > esquecido_dias,
        })
    itens.sort(key=lambda i: -i["valor"])
    return itens


def montar_abaixo_custo(catalogo, vendas):
    """Produtos cujo preco VIGENTE (hierarquia do caixa: promocao vigente
    MANDA; senao varejo) esta abaixo do custo — so quem teve venda na janela
    recebida (ultimos 5 dias). Ordena pelo maior prejuizo estimado no periodo."""
    qtd5 = {}
    for v in vendas or []:
        c = _cod(v.get("codigo"))
        try:
            qtd5[c] = qtd5.get(c, 0.0) + float(v.get("qtd_vendida") or 0)
        except (TypeError, ValueError):
            pass
    itens = []
    for r in catalogo or []:
        c = _cod(r.get("codigo"))
        if c not in qtd5:
            continue
        promo = r.get("preco_promocao")
        varejo = r.get("preco_varejo")
        if promo is not None and float(promo) > 0:
            preco, origem = float(promo), "promo"
        elif varejo is not None and float(varejo) > 0:
            preco, origem = float(varejo), "varejo"
        else:
            continue
        custo = float(r.get("custo_atual") or 0)
        if custo <= 0 or preco >= custo:
            continue
        qtd = qtd5[c]
        itens.append({
            "codigo": c,
            "descricao": r.get("descricao"),
            "preco": round(preco, 2),
            "origem": origem,
            "custo": round(custo, 2),
            "margem_pct": round((preco - custo) / custo * 100, 1),
            "qtd_5d": round(qtd, 2),
            "prejuizo_5d": round((custo - preco) * qtd, 2),
            "curva": r.get("curva"),
        })
    itens.sort(key=lambda i: -i["prejuizo_5d"])
    return itens


def montar_sellout(linhas, hoje):
    """Verbas sell-out normalizadas p/ o quadrante: dias_vencida (positivo =
    vencimento ja passou) e ordenacao vencidas-com-valor primeiro, maior R$
    no topo. O corte visual (so vencidas com total > 0) e do template."""
    itens = []
    for r in linhas or []:
        venc = str(r.get("vencimento") or "")[:10]
        try:
            dias = _dias(venc, hoje) if venc else None
        except ValueError:
            dias = None
        itens.append({
            "produto": r.get("produto"),
            "promocao": r.get("promocao"),
            "tipo_promocao": r.get("tipo_promocao") or "",
            "fornecedor": r.get("fornecedor") or "",
            "inicio": str(r.get("inicio"))[:10],
            "fim": str(r.get("fim"))[:10],
            "vencimento": venc or None,
            "verba_un": float(r["verba_un"]) if r.get("verba_un") is not None else None,
            "total": float(r.get("total") or 0),
            "dias_vencida": dias,
        })
    # dono (21/07): universo = EM ABERTO (Status Pag.) — e como o sellout de
    # promocao nao tem baixa no financeiro, tudo aqui esta em aberto;
    # ordena pelo maior valor a receber
    itens.sort(key=lambda i: -i["total"])
    return itens


def carregar_ruptura(rounds_dir, hoje=None):
    """Rodada mais recente do detector-estoque, traduzida para o painel.
    Items ja vem ordenados por scorePrioridade desc (detectAll.js)."""
    if not rounds_dir or not os.path.isdir(rounds_dir):
        return None
    arquivos = sorted(glob.glob(os.path.join(rounds_dir, "*.json")))
    if not arquivos:
        return None
    hoje = hoje or date.today().isoformat()
    with open(arquivos[-1], encoding="utf-8") as f:
        rodada = json.load(f)

    def _entrega_dias(i):
        """Dias desde a ULTIMA entrega (None se sem entrega/data ilegivel)."""
        data = str((i.get("receipt") or {}).get("date") or "")[:10]
        if not data:
            return None
        try:
            return _dias(data, hoje)
        except ValueError:
            return None

    itens = []
    for i in rodada.get("items", []):
        tem_pedido = bool(i.get("temPedido"))
        pedido_dias = _pedido_dias(i, hoje)
        # dono (21/07): pedido feito ha MAIS de 20 dias e nao entregue e
        # IGNORADO por completo — vira "sem pedido" (badge, coluna e contagem)
        if pedido_dias is not None and pedido_dias > 20:
            tem_pedido = False
            pedido_dias = None
        itens.append({
            "codigo": _cod(i.get("codigo")),
            "descricao": i.get("descricao"),
            "prioridade": i.get("scorePrioridade"),
            "probabilidade": i.get("probabilidade"),
            "tem_pedido": tem_pedido,
            "pedido_dias": pedido_dias,
            "curva": i.get("curvaABC"),
            "un_mes": i.get("unMes"),
            "rs_hist": i.get("rsHist"),
            "dias_parado": i.get("diasParado"),
            "cobertura_esgotada": bool(i.get("coberturaEsgotada")),
            # guardrail do dono (21/07): entrega recente com cobertura sobrando
            "entrega_dias": _entrega_dias(i),
            "entrega_qtd": (i.get("receipt") or {}).get("qty"),
            "cobertura_restante": i.get("coverageRemaining"),
        })
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
    destino_arq = os.path.join(dir_saida, "revisao_pricing.html")
    shutil.copyfile(origem, destino_arq)
    _podar_copia_revisao(destino_arq)
    mtime = datetime.fromtimestamp(os.path.getmtime(origem))
    return {"rotulo": f"{ano}-S{sem}", "arquivo": "revisao_pricing.html",
            "modificado_em": mtime.strftime("%Y-%m-%d %H:%M")}


def _podar_copia_revisao(arquivo):
    """Ajustes do dono (21/07) feitos NA COPIA (o original do pricing fica
    intacto): esconde a nota verde de re-leitura e a descricao de zona
    tambem na tela cheia, e renomeia KVI -> "Itens acima de concorrência"
    (chip de filtro e selos das linhas)."""
    with open(arquivo, encoding="utf-8") as f:
        html = f.read()
    html = html.replace('["kvi","KVI"]',
                        '["kvi","Itens acima de concorrência"]')
    html = html.replace('"r": "KVI no piso"', '"r": "Acima (no piso)"')
    html = html.replace('"r": "KVI"', '"r": "Acima"')
    html = html.replace(
        "</head>",
        '<style id="poda-copia">p.nota,#descricao{display:none!important}'
        "</style></head>", 1)
    with open(arquivo, "w", encoding="utf-8") as f:
        f.write(html)


def contar_concorrente(arquivo, hoje, frescor_dias=10):
    """Conta os itens da revisao copiada por zona — acima (g=kvi: estavam
    mais caros que o vizinho) e abaixo (g=alinha: sobem ate empatar) — so
    com pesquisa fresca (coleta mais recente <= frescor_dias, MESMA regra
    da poda da previa). Devolve None se o HTML nao tiver os dados."""
    with open(arquivo, encoding="utf-8") as f:
        html = f.read()
    m = re.search(r"const ITENS = (\[.*?\]);", html, re.S)
    if not m:
        return None
    hoje_d = date.fromisoformat(hoje)
    cont = {"kvi": 0, "alinha": 0}
    for it in json.loads(m.group(1)):
        datas = []
        for vz in it.get("v") or []:
            try:
                dd, mm, aa = (vz.get("dt") or "").split("/")
                datas.append(date(int(aa), int(mm), int(dd)))
            except (ValueError, AttributeError):
                pass
        if not datas or (hoje_d - max(datas)).days > frescor_dias:
            continue
        g = it.get("g")
        if g in cont:
            cont[g] += 1
    return {"acima": cont["kvi"], "abaixo": cont["alinha"]}


def previa_concorrente(arquivo, hoje, frescor_dias=10):
    """Linhas da previa DIVIDIDA do card (dono, 22/07): metade "Itens acima
    de concorrencia" (g=kvi), metade "Sobe p/ vizinho" (g=alinha), so com
    pesquisa fresca (<= frescor_dias, mesma regra da poda). Mantem a ordem
    do proprio relatorio. Devolve None se o HTML nao tiver os dados."""
    with open(arquivo, encoding="utf-8") as f:
        html = f.read()
    m = re.search(r"const ITENS = (\[.*?\]);", html, re.S)
    if not m:
        return None
    hoje_d = date.fromisoformat(hoje)
    out = {"acima": [], "abaixo": []}
    zonas = {"kvi": "acima", "alinha": "abaixo"}
    for it in json.loads(m.group(1)):
        zona = zonas.get(it.get("g"))
        if not zona:
            continue
        datas, ref = [], None
        for vz in it.get("v") or []:
            try:
                dd, mm, aa = (vz.get("dt") or "").split("/")
                datas.append(date(int(aa), int(mm), int(dd)))
            except (ValueError, AttributeError):
                pass
            if ref is None or (vz.get("d") and not ref.get("d")):
                ref = vz
        if not datas or (hoje_d - max(datas)).days > frescor_dias:
            continue
        atual, sug = it.get("a"), it.get("s")
        delta = (round((float(sug) - float(atual)) / float(atual) * 100, 1)
                 if atual and sug else None)
        out[zona].append({
            "produto": it.get("p") or "",
            "ref_nome": (ref or {}).get("n") or "",
            "ref_preco": (ref or {}).get("p"),
            "ref_data": (ref or {}).get("dt"),
            "atual": atual, "sugerido": sug, "delta_pct": delta,
        })
    return out


RODAPE_CONCORRENTE = """
<div id="historico-concorrente" style="position:fixed;left:0;right:0;bottom:0;
height:30vh;background:#0b0e13;border-top:1px solid #232b38;display:flex;
gap:12px;padding:8px 10px;z-index:50;box-sizing:border-box"></div>
<script id="historico-concorrente-js">
(function(){
  var S = /*__SERIES__*/null;
  var box = document.getElementById("historico-concorrente");
  if (!S || !box) return;
  document.body.style.paddingBottom = "32vh";
  function um(titulo, s){
    if (!s || !s.length) return;
    var W=800,H=260,MT=24,MB=22,max=1,i;
    for(i=0;i<s.length;i++) if(s[i].v>max) max=s[i].v;
    var bw=W/s.length,b="";
    for(i=0;i<s.length;i++){
      var h=Math.max(s[i].v/max*(H-MT-MB), s[i].v>0?2:0), y=H-MB-h;
      var xc=(i*bw+bw/2).toFixed(1);
      b+='<rect x="'+(i*bw+bw*0.12).toFixed(1)+'" y="'+y.toFixed(1)+
        '" width="'+(bw*0.76).toFixed(1)+'" height="'+h.toFixed(1)+
        '" fill="'+(i===s.length-1?"#58a6ff":"#2e4a74")+'" data-t="'+s[i].s+
        " \\u00b7 "+Math.round(s[i].v)+'"></rect>'+
        '<text x="'+xc+'" y="'+(y-6).toFixed(1)+
        '" fill="#8e99a8" font-size="13" text-anchor="middle">'+
        Math.round(s[i].v)+'</text>';
      if(i===0||i===s.length-1||i%4===0){
        var p=s[i].s.split("-");
        b+='<text x="'+xc+'" y="'+(H-6)+
          '" fill="#5c6572" font-size="13" text-anchor="middle">'+
          p[2]+"/"+p[1]+'</text>';
      }
    }
    var d=document.createElement("div");
    d.style.cssText="flex:1;display:flex;flex-direction:column;min-width:0";
    d.innerHTML='<div style="font-size:11px;color:#5c6572;'+
      'text-transform:uppercase;letter-spacing:.06em;margin:0 0 4px 4px">'+
      titulo+" \\u00b7 amostras semanais</div>"+
      '<svg style="flex:1;width:100%" viewBox="0 0 '+W+" "+H+
      '" preserveAspectRatio="none">'+b+"</svg>";
    box.appendChild(d);
  }
  um("Itens acima de concorr\\u00eancia", S.acima);
  um("Itens abaixo de concorr\\u00eancia", S.abaixo);
  var t=document.createElement("div");
  t.style.cssText="position:fixed;display:none;z-index:99;pointer-events:none;"+
    "background:#1b2330;border:1px solid #232b38;border-radius:8px;"+
    "padding:4px 10px;font-size:13px;color:#e8edf4;white-space:nowrap";
  document.body.appendChild(t);
  document.addEventListener("mousemove",function(ev){
    var r=ev.target.closest&&ev.target.closest("rect[data-t]");
    if(!r){t.style.display="none";return;}
    t.textContent=r.getAttribute("data-t");
    t.style.display="block";
    t.style.left=Math.min(ev.clientX+14,innerWidth-t.offsetWidth-8)+"px";
    t.style.top=Math.max(ev.clientY-36,6)+"px";
  });
})();
</script>
"""


def injetar_grafico_concorrente(arquivo, series):
    """Anexa na COPIA da revisao o rodape fixo (ultimo terco da tela) com os
    DOIS graficos semanais — itens acima e abaixo da concorrencia (dono,
    21/07). A previa do painel esconde o rodape (poda do iframe)."""
    with open(arquivo, encoding="utf-8") as f:
        html = f.read()
    if "historico-concorrente" in html:
        return
    dados = json.dumps(series, ensure_ascii=False).replace("</", "<\\/")
    html = html.replace(
        "</body>",
        RODAPE_CONCORRENTE.replace("/*__SERIES__*/null", dados) + "</body>", 1)
    with open(arquivo, "w", encoding="utf-8") as f:
        f.write(html)


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
    cat = val = relamp = cob = sellout = ven5 = prep = avaria = None
    aband = 0
    hist_sql = {}
    ven_hist = None
    dias_hist = historico_painel.segundas_desde(
        historico_painel.INICIO_HISTORICO, hoje)
    if usar_demo:
        cat, val = demo_data.catalogo(), demo_data.validades()
        relamp, cob = demo_data.promo_relampago(), demo_data.pedidos_cobranca()
        sellout = demo_data.receita_sellout()
        ven5 = demo_data.vendas(5)
        prep = demo_data.pre_pedidos()
        avaria = demo_data.avaria_saldo()
        aband = 2
        ven_hist = demo_data.vendas(120)
        hist_sql = demo_data.historico_series(dias_hist)
    else:
        import db
        import queries
        try:
            conn = db.conectar(cfg["db"])
        except Exception as e:  # noqa: BLE001
            erros["validade_relampago"] = erros["cobranca"] = \
                erros["sellout"] = erros["abaixo_custo"] = \
                erros["prepedidos"] = f"banco inacessivel: {e}"
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
                sellout = _consulta(conn, queries.REC_SELLOUT, "sellout", erros)
                # abaixo do custo: reusa a query VENDAS com janela de 5 dias
                ven5 = _consulta(conn, queries.VENDAS.format(janela=5),
                                 "abaixo_custo", erros)
                prep = _consulta(conn, queries.PRE_PEDIDOS.format(
                    prepedido_dias=int(cfgp["prepedido_dias"])),
                    "prepedidos", erros)
                avaria = _consulta(conn, queries.AVARIA_SALDO,
                                   "avaria", erros)
                # series historicas semanais (spec §13) — point-in-time
                for nome, sql in historico_painel.sql_series(
                        dias_hist, max_d, int(cfgp["cobranca_dias_limiar"]),
                        int(cfgp["prepedido_dias"])).items():
                    rs = _consulta(conn, sql, "historico", erros)
                    if rs is not None:
                        hist_sql[nome] = [{"s": str(r["dia"])[:10],
                                           "v": float(r["v"] or 0)} for r in rs]
                ven_hist = _consulta(
                    conn, queries.VENDAS.format(
                        janela=int(cfg.get("janela_dias", 120))),
                    "historico", erros)
            finally:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001 — conexao ja caida nao pode abortar a geracao
                    pass

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
        r = carregar_ruptura(cfgp.get("detector_rounds_dir"), hoje)
        if r is None:
            q_ruptura["erro"] = "nenhuma rodada do detector encontrada"
        else:
            q_ruptura["carimbo"], q_ruptura["itens"] = r["ref"], r["itens"]
    except Exception as e:  # noqa: BLE001
        q_ruptura["erro"] = f"falha lendo a rodada do detector: {e}"

    q_sellout = {"carimbo": gerado_em, "erro": erros.get("sellout"), "itens": []}
    if sellout is not None:
        q_sellout["itens"] = montar_sellout(sellout, hoje)

    q_abaixo = {"carimbo": gerado_em,
                "erro": erros.get("abaixo_custo") or
                (None if cat is not None else erros.get("validade_relampago")),
                "itens": []}
    if cat is not None and ven5 is not None:
        q_abaixo["itens"] = montar_abaixo_custo(cat, ven5)

    q_prep = {"carimbo": gerado_em, "erro": erros.get("prepedidos"), "itens": []}
    if prep is not None:
        q_prep["itens"] = montar_prepedidos(prep, hoje)

    q_avaria = {"carimbo": gerado_em, "erro": erros.get("avaria"),
                "itens": [], "esquecido_dias": int(cfgp["avaria_esquecido_dias"])}
    if avaria is not None:
        q_avaria["itens"] = montar_avaria(
            avaria, hoje, int(cfgp["avaria_esquecido_dias"]))

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
                                     "cobranca_alerta_dias",
                                     "detector_dashboard_url")},
        "validade_relampago": q_validade,
        "ruptura": q_ruptura,
        "cobranca": q_cobranca,
        "sellout": q_sellout,
        "abaixo_custo": q_abaixo,
        "prepedidos": q_prep,
        "avaria": q_avaria,
        "concorrente": q_conc,
    }

    # historico semanal (spec §13): SQL point-in-time recomputado + realizado
    # do abaixo-custo + ponto do dia da ruptura (o passado dela vem do
    # backfill scripts/backfill_historico_ruptura.py). Mescla preservando
    # pontos que ja sairam da janela do ERP.
    novas = dict(hist_sql)
    if ven_hist is not None:
        novas["abaixo_custo"] = historico_painel.serie_abaixo_custo(
            ven_hist, dias_hist)
    if not q_ruptura["erro"]:
        c = historico_painel.corte_ruptura(q_ruptura["itens"])
        novas["ruptura"] = [{"s": hoje, "a": c["a"], "b": c["b"]}]
    if q_conc.get("arquivo") and not q_conc["erro"]:
        try:
            pv = previa_concorrente(
                os.path.join(destino, q_conc["arquivo"]), hoje)
            if pv is not None:
                q_conc["previa"] = pv
                novas["concorrente_acima"] = [
                    {"s": hoje, "v": len(pv["acima"])}]
                novas["concorrente_abaixo"] = [
                    {"s": hoje, "v": len(pv["abaixo"])}]
        except Exception as e:  # noqa: BLE001
            erros["historico"] = f"previa concorrente: {e}"
    try:
        hist = historico_painel.mesclar_historico(destino, novas, gerado_em)
        payload["historico"] = hist.get("series") or {}
    except Exception as e:  # noqa: BLE001 — historico nunca derruba o painel
        erros["historico"] = str(e)
        payload["historico"] = {}
    if q_conc.get("arquivo") and not q_conc["erro"]:
        try:
            injetar_grafico_concorrente(
                os.path.join(destino, q_conc["arquivo"]),
                {"acima": payload["historico"].get("concorrente_acima") or [],
                 "abaixo": payload["historico"].get("concorrente_abaixo") or []})
        except Exception as e:  # noqa: BLE001
            erros["historico"] = f"grafico concorrente: {e}"

    dados = json.dumps(payload, ensure_ascii=False, indent=1, default=str)
    projections._escrever_atomico(os.path.join(destino, "dados_painel.json"),
                                  dados.encode("utf-8"))
    projections._escrever_atomico(os.path.join(destino, "index.html"),
                                  renderizar(payload).encode("utf-8"))

    avisos = [q for q, e in (("validade", q_validade["erro"]),
                             ("ruptura", q_ruptura["erro"]),
                             ("cobranca", q_cobranca["erro"]),
                             ("sellout", q_sellout["erro"]),
                             ("abaixo_custo", q_abaixo["erro"]),
                             ("prepedidos", q_prep["erro"]),
                             ("avaria", q_avaria["erro"]),
                             ("concorrente", q_conc["erro"])) if e]

    # spec §8: falha de fonte nao aborta, mas deixa trilha no log do bridge —
    # sob o Agendador o stdout se perde, e "quadrante fora ha 3 dias" precisa
    # ser depuravel. Falha do proprio log nunca derruba a geracao.
    if avisos:
        try:
            with open(os.path.join(RAIZ, "bridge_erros.log"), "a",
                      encoding="utf-8") as f:
                for quad, e in (("validade", q_validade["erro"]),
                                ("ruptura", q_ruptura["erro"]),
                                ("cobranca", q_cobranca["erro"]),
                                ("sellout", q_sellout["erro"]),
                                ("abaixo_custo", q_abaixo["erro"]),
                                ("prepedidos", q_prep["erro"]),
                                ("avaria", q_avaria["erro"]),
                                ("concorrente", q_conc["erro"])):
                    if e:
                        f.write(f"{gerado_em}  PAINEL {quad}: {e}\n")
        except OSError:
            pass

    so_abertas = [i for i in q_sellout["itens"] if (i.get("total") or 0) > 0]
    resumo = (f"painel/index.html: {len(q_validade['itens'])} relampago, "
              f"{len(q_ruptura['itens'])} ruptura, "
              f"{len(q_cobranca['itens'])} cobranca (+{aband} abandonados), "
              f"{len(so_abertas)} sellout em aberto, "
              f"{len(q_abaixo['itens'])} abaixo do custo, "
              f"{len(q_prep['itens'])} pre-pedidos, "
              f"{len(q_avaria['itens'])} avaria "
              f"(R$ {sum(i['valor'] for i in q_avaria['itens']):,.0f})"
              + (f" — AVISO em: {', '.join(avisos)}" if avisos else ""))
    return [resumo]
