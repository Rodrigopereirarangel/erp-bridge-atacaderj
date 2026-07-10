# -*- coding: utf-8 -*-
"""Camada de projecao: recebe a camada bruta (linhas canonicas) e escreve o
formato EXATO que cada consumidor ja espera. Toda escrita e atomica
(.tmp + rename) para nunca deixar um consumidor ler um arquivo pela metade.
"""

import csv
import io
import json
import os
import re


def _escrever_atomico(caminho, conteudo_bytes):
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    tmp = caminho + ".tmp"
    with open(tmp, "wb") as f:
        f.write(conteudo_bytes)
    os.replace(tmp, caminho)


def _csv_ponto_virgula(cabecalho, linhas):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(cabecalho)
    for ln in linhas:
        w.writerow(ln)
    return buf.getvalue().encode("utf-8")


# ---------- Consumidor 1: Cotacao (produtos.json, chaves compactas) ----------

def cotacao_produtos_json(catalogo, caminho, gerado_em):
    produtos = [
        {
            "c": r["codigo"],
            "p": r["descricao"],
            "q": r.get("embalagem"),
            "v": r.get("preco_atacado"),
            "vu": r.get("preco_varejo"),
            "vp": r.get("preco_promocao"),
            "custo": r.get("custo_atual"),
            "cv": r.get("curva"),
        }
        for r in catalogo
    ]
    payload = {"gerado_em": gerado_em, "total": len(produtos), "produtos": produtos}
    data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    _escrever_atomico(caminho, data)
    return len(produtos)


def catalogo_bridge_json(catalogo, pedidos_venda, caminho, gerado_em, janela_dias=7):
    """Arquivo UNICO que o robo de upload sobe no artifact do claude.ai pelo
    botao "📦 Catalogo" do app (design 2026-07-07: o app NAO alcanca a rede da
    loja, entao nada de fetch — os dados viajam por upload).

    Contrato com o app (plano 2026-07-07-aceitar-catalogo-bridge.md):
      {"origem":"erp-bridge","gerado_em":"YYYY-MM-DD HH:MM:SS","total":N,
       "produtos":[{"c","p","q","v","vu"?,"custo"?,"cv"?}]}
    - v  = MENOR preco (varejo/promocao/atacado — mesma mescla do upload manual)
    - vu = preco unitario (varejo ou promo) SO quando o atacado venceu
    - q  = qtde minima do atacado quando ele vence (senao 1)
    O app revalida cada produto (nome>=4, v>0, sem MORTO) e exige
    total == len(produtos) — por isso os MESMOS filtros sao aplicados aqui.

    Extensao (auditoria de desconto, 2026-07-08): "pedidos_venda" leva os
    itens dos pedidos de venda/DAV fechados na janela (7 dias), agrupados por
    pedido, p/ o seletor de dia da aba Auditoria funcionar no artifact:
      {"janela_dias":N,"pedidos":[{"dia","ped","dav","cli","vend",
       "itens":[[codigo,emb,qtde,valor_volume,custo_un],...]}]}
    """
    produtos = []
    for r in catalogo:
        try:
            c = int(r["codigo"])
        except (TypeError, ValueError):
            continue
        nome = str(r.get("descricao") or "").upper().strip()
        # mesmo regex de descarte do app (/MORTO|EXCLUIDO|<<<.*>>>/): qualquer
        # divergencia aqui muda o "total" e faz o app rejeitar o ARQUIVO inteiro
        if len(nome) < 4 or re.search(r"MORTO|EXCLUIDO|<<<.*>>>", nome):
            continue
        varejo = r.get("preco_varejo")
        promo = r.get("preco_promocao")
        atacado = r.get("preco_atacado")
        v = varejo if (varejo or 0) > 0 else None
        if (promo or 0) > 0 and (v is None or promo < v):
            v = promo                      # promocao vence (estrito, como no app)
        vu = None
        q = 1
        if (atacado or 0) > 0 and (v is None or atacado < v):
            vu = v                         # unitario perdedor vira "vu"
            v = atacado                    # atacado vence (estrito)
            qa = r.get("qtde_atacado")
            q = int(qa) if (qa or 0) >= 1 else 1
        if v is None:
            continue
        v = round(v, 2)          # arredondar ANTES de validar: 0.004 -> 0.0
        if v <= 0:               # (o app revalida v>0 sobre o valor arredondado)
            continue
        item = {"c": c, "p": nome, "q": q, "v": v}
        if vu is not None:
            vu = round(vu, 2)
            if vu > 0 and vu != item["v"]:
                item["vu"] = vu
        if (r.get("custo_atual") or 0) > 0:
            item["custo"] = round(r["custo_atual"], 2)
        if r.get("curva"):
            item["cv"] = str(r["curva"]).strip().upper()[:1]
        produtos.append(item)
    produtos.sort(key=lambda x: x["p"])

    por_pedido = {}
    for r in pedidos_venda or []:
        ped = r["pedido"]
        if ped not in por_pedido:
            por_pedido[ped] = {"dia": str(r["emissao"])[:10], "ped": ped,
                               "dav": r.get("dav"), "cli": r.get("cliente"),
                               "vend": r.get("vendedor"), "itens": []}
        por_pedido[ped]["itens"].append([
            r["codigo"], r.get("emb") or "UN", r.get("qtde"),
            r.get("valor"), r.get("custo_un")])
    pedidos = sorted(por_pedido.values(), key=lambda p: (p["dia"], p["ped"]))

    payload = {"origem": "erp-bridge", "gerado_em": gerado_em,
               "total": len(produtos), "produtos": produtos}
    if pedidos:
        payload["pedidos_venda"] = {"janela_dias": janela_dias, "pedidos": pedidos}
    data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    _escrever_atomico(caminho, data)
    return len(produtos), len(pedidos)


# ---------- Consumidor: dashboard de vendas mensais (HTML auto-contido) ----------

def vendas_mensal_dashboard(vendas_mensal, caminho_json, caminho_html, gerado_em):
    """Escreve o JSON de vendas por produto x mes fechado E o dashboard HTML
    auto-contido (dados embutidos — abre com duplo clique, sem servidor e sem
    rede). Template em src/templates/vendas_mensal.html; o placeholder
    /*__DADOS__*/null e trocado pelo payload.

    Payload: {"gerado_em", "unidade":"un", "meses":[desc], "produtos":[
      {"c":codigo, "p":descricao, "m":{"YYYY-MM": qtd_un, ...}}]}
    qtd_un fracionada = item de balanca (kg); o restante e inteiro.
    """
    por_produto = {}
    meses = set()
    for r in vendas_mensal:
        mes = str(r["mes"])
        meses.add(mes)
        p = por_produto.setdefault(r["codigo"], {"c": r["codigo"],
                                                 "p": r["descricao"], "m": {}})
        qtd = float(r["qtd_un"] or 0)
        p["m"][mes] = int(qtd) if qtd == int(qtd) else round(qtd, 3)
    produtos = sorted(por_produto.values(), key=lambda x: str(x["p"]))
    payload = {"gerado_em": gerado_em, "unidade": "un",
               "meses": sorted(meses, reverse=True), "produtos": produtos}
    dados = json.dumps(payload, ensure_ascii=False, default=str)
    _escrever_atomico(caminho_json, dados.encode("utf-8"))

    template = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "templates", "vendas_mensal.html")
    with open(template, encoding="utf-8") as f:
        html = f.read()
    # "</" -> "<\/" (escape valido em JSON): um "</script>" numa descricao de
    # produto nao pode encerrar o <script> do dashboard
    html = html.replace("/*__DADOS__*/null", dados.replace("</", "<\\/"))
    _escrever_atomico(caminho_html, html.encode("utf-8"))
    return len(produtos), len(payload["meses"])


# ---------- Consumidores 2 e 3: Detectores (CSV ;) ----------

def vendas_csv(vendas, caminho, incluir_valor=False, incluir_custo=False):
    cab = ["codigo", "descricao", "data", "qtd_vendida"]
    if incluir_valor:
        cab.append("valor")            # so o detector de ESTOQUE usa R$
    if incluir_custo:
        cab.append("custo_venda")      # CMV congelado no dia -> margem realizada
    linhas = []
    for r in vendas:
        ln = [r["codigo"], r["descricao"], r["data"], r["qtd_vendida"]]
        if incluir_valor:
            ln.append(r.get("valor"))
        if incluir_custo:
            ln.append(r.get("custo_venda"))
        linhas.append(ln)
    _escrever_atomico(caminho, _csv_ponto_virgula(cab, linhas))
    return len(linhas)


def entradas_csv(entradas, caminho):
    """Todas as entregas da janela (~6 meses): uma linha por entrada.
    E o insumo do 'espectro' (giro x ultimas entregas) do detector de estoque."""
    cab = ["codigo", "data", "qtd"]
    linhas = [[r["codigo"], r["data"], r["qtd"]] for r in entradas]
    _escrever_atomico(caminho, _csv_ponto_virgula(cab, linhas))
    return len(linhas)


def recebimentos_csv(entradas, caminho):
    """Deriva a ULTIMA entrega por item (data + qtd dessa entrega) a partir da
    lista de entradas. E o formato que o detector de salao ja espera."""
    ultima = {}
    for r in entradas:
        cod = r["codigo"]
        if cod not in ultima or str(r["data"]) > str(ultima[cod]["data"]):
            ultima[cod] = r
    cab = ["codigo", "data_ultimo_recebimento", "qtd_recebida"]
    linhas = [[cod, u["data"], u["qtd"]] for cod, u in ultima.items()]
    _escrever_atomico(caminho, _csv_ponto_virgula(cab, linhas))
    return len(linhas)


def pedidos_csv(pedidos, caminho):
    cab = ["codigo", "data_pedido", "qtd_pedida", "status", "previsao_entrega"]
    linhas = [[r["codigo"], r["data_pedido"], r["qtd_pedida"], r["status"], r["previsao_entrega"]] for r in pedidos]
    _escrever_atomico(caminho, _csv_ponto_virgula(cab, linhas))
    return len(linhas)


def pedidos_venda_csv(itens, caminho):
    """Itens dos pedidos de venda/DAV emitidos (janela) — insumo da auditoria
    de desconto do app de cotacao (substitui o upload manual do relatorio
    rptPedidosVendaEmitidaDAVPorItens)."""
    cab = ["pedido", "emissao", "dav", "cliente", "vendedor", "codigo", "produto",
           "emb", "unidades_por_emb", "qtde", "valor", "valor_tabela", "custo_un"]
    linhas = [[r["pedido"], r["emissao"], r["dav"], r["cliente"], r["vendedor"],
               r["codigo"], r["produto"], r["emb"], r["unidades_por_emb"],
               r["qtde"], r["valor"], r["valor_tabela"], r["custo_un"]] for r in itens]
    _escrever_atomico(caminho, _csv_ponto_virgula(cab, linhas))
    return len(linhas)


def curva_abc_csv(catalogo, caminho):
    cab = ["codigo", "curva"]
    linhas = [[r["codigo"], r.get("curva")] for r in catalogo if r.get("curva") is not None]
    _escrever_atomico(caminho, _csv_ponto_virgula(cab, linhas))
    return len(linhas)
