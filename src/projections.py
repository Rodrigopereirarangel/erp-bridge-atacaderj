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


def catalogo_bridge_json(catalogo, pedidos_venda, caminho, gerado_em, janela_dias=7,
                         validades=None):
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
    # codigo -> ["YYYY-MM-DD", ...] (no maximo 2, MENOR primeiro: a menor e a
    # data mais provavel da mercadoria, e e ela que o app destaca)
    _vd = {}
    for r in (validades or []):
        try:
            cod = int(r["codigo"])
        except (TypeError, ValueError):
            continue
        val = r.get("validade")
        if not val:
            continue
        iso = val.isoformat()[:10] if hasattr(val, "isoformat") else str(val)[:10]
        _vd.setdefault(cod, [])
        if iso not in _vd[cod]:
            _vd[cod].append(iso)
    for cod in _vd:
        _vd[cod] = sorted(_vd[cod])[:2]

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
        # vd = as 2 validades das ultimas notas de entrada (menor primeiro).
        # Ausente quando o produto nao tem validade registrada — o app so
        # exibe/imprime a linha de validade quando este campo existe.
        vd = _vd.get(c)
        if vd:
            item["vd"] = vd
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

    Payload: {"gerado_em", "unidade":"un", "campos":["qtd_un","valor"],
      "meses":[desc], "produtos":[{"c":codigo, "p":descricao,
      "m":{"YYYY-MM": [qtd_un, valor], ...}}]}
    qtd_un fracionada = item de balanca (kg); o restante e inteiro.
    O preco medio unitario (Vl. Medio do rptABCdeVendas) NAO e extraido:
    o dashboard calcula valor/qtd_un, igual ao relatorio do ERP.
    """
    por_produto = {}
    meses = set()
    for r in vendas_mensal:
        mes = str(r["mes"])
        meses.add(mes)
        p = por_produto.setdefault(r["codigo"], {"c": r["codigo"],
                                                 "p": r["descricao"], "m": {}})
        qtd = float(r["qtd_un"] or 0)
        p["m"][mes] = [int(qtd) if qtd == int(qtd) else round(qtd, 3),
                       round(float(r.get("valor") or 0), 2)]
    produtos = sorted(por_produto.values(), key=lambda x: str(x["p"]))
    payload = {"gerado_em": gerado_em, "unidade": "un",
               "campos": ["qtd_un", "valor"],
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


# ---------- Consumidor: app recuperacao-itens (Recuperar + Ampliar) ----------

# Valor de Departamento que e STATUS DE MIX, nao familia mercadologica: vira
# grupo vazio no CSV (o app trata como "SEM GRUPO" e nao gera par de cross-sell).
GRUPO_FORA_DO_MIX = "INATIVOS OU FORA DO MIX"

# Grafias divergentes da arvore do ERP que sao a MESMA familia (descoberto na
# revisao de 2026-07-17: "CONSERVAS 2" partia a familia CONSERVAS em duas e
# enfraquecia o lookalike do app).
GRUPO_NORMALIZA = {"CONSERVAS 2": "CONSERVAS"}


def historico_cliente_csv(itens, caminho):
    """Historico de compras por cliente (itens de pedido de venda/DAV, ~24
    meses) — insumo do app recuperacao-itens. Contrato: 11 colunas, `;` como
    separador, terminando em `grupo` (familia mercadologica; vazio = SEM GRUPO).
    valor/custo sao TOTAIS da linha; unidades = qtde_emb x unidades_por_emb."""
    cab = ["cliente", "codigo", "produto", "data", "emb", "unidades_por_emb",
           "qtde_emb", "unidades", "valor", "custo", "grupo"]
    linhas = []
    for r in itens:
        grupo = str(r.get("grupo") or "").strip()
        if grupo.upper() == GRUPO_FORA_DO_MIX:
            grupo = ""
        grupo = GRUPO_NORMALIZA.get(grupo.upper(), grupo)
        linhas.append([r["cliente"], r["codigo"], r["produto"], r["data"],
                       r["emb"], r["unidades_por_emb"], r["qtde_emb"],
                       r["unidades"], r["valor"], r["custo"], grupo])
    _escrever_atomico(caminho, _csv_ponto_virgula(cab, linhas))
    return len(linhas)


def curva_abc_csv(catalogo, caminho):
    cab = ["codigo", "curva"]
    linhas = [[r["codigo"], r.get("curva")] for r in catalogo if r.get("curva") is not None]
    _escrever_atomico(caminho, _csv_ponto_virgula(cab, linhas))
    return len(linhas)


def prateleira_csv(catalogo, caminho):
    """Endereco fisico do item no salao (classificacao mercadologica do ERP,
    ex. "PRATELEIRA 33") — coluna Prateleira do relatorio de ruptura."""
    cab = ["codigo", "prateleira"]
    linhas = [[r["codigo"], str(r["prateleira"]).strip()]
              for r in catalogo if str(r.get("prateleira") or "").strip()]
    _escrever_atomico(caminho, _csv_ponto_virgula(cab, linhas))
    return len(linhas)


# ---------- Consumidor: exposicao (calc. MIN/MAX) ----------

def vendas_canal_csv(vendas_canal, caminho):
    """Venda diaria por item em UNIDADES, separada por canal (salao x atacado).
    Base do calculo de MIN/MAX de exposicao (spec 2026-07-17).

    O canal ja vem resolvido da query (queries.VENDAS_CANAL): o consumidor
    nunca ve numero de PDV. Duas perguntas diferentes usam filtros diferentes
    deste mesmo arquivo — o giro da prateleira usa SO 'salao' (atacado nao sai
    da gondola), e o saldo de estoque usa OS DOIS (a caixa do atacado consome
    o mesmo estoque)."""
    cab = ["codigo", "data", "canal", "unidades"]
    linhas = [[r["codigo"], r["data"], r["canal"], r["unidades"]] for r in vendas_canal]
    _escrever_atomico(caminho, _csv_ponto_virgula(cab, linhas))
    return len(linhas)


def catalogo_exposicao_csv(catalogo, caminho):
    """Atributos que o calculo de exposicao precisa do cadastro.

    caixa_mae = catalogo["embalagem"] = VW_NEOGRID_PRODUTO_PRECO.QUANTIDADE_CAIXA.
    E o CADASTRO — nunca a nota de entrada (decisao do dono, spec D7): o
    calculo roda todo em unidades e so converte para caixa no ultimo passo.
    Item sem caixa-mae nenhuma (embalagem NULL/0) fica de fora; caixa=1
    entra e o relatorio marca p/ ajuste manual. (A "caixa aproximada" por
    testemunhas de 18-20/07 foi REMOVIDA a pedido do dono em 20/07.)

    Tres degraus da classificacao (dono, 17/07): setor > corredor >
    prateleira (ex.: PERFUMARIA > CORREDOR 20 > PRATELEIRA 21)."""
    cab = ["codigo", "descricao", "caixa_mae", "setor", "corredor",
           "prateleira", "curva", "peso"]
    linhas = []
    for r in catalogo:
        emb = r.get("embalagem")
        peso = 1 if r.get("peso") else 0
        caixa = int(float(emb)) if emb and float(emb) > 0 else 0
        if caixa <= 0:
            # sem caixa nao da para arredondar
            continue
        # SO produto ATIVO ganha min/max de prateleira (dono, 18/07):
        # inAtivo=0 do cadastro fora; classificacao 'INATIVOS OU FORA DO MIX'
        # tambem fora (5 itens tem inAtivo=1 com essa classificacao — o
        # cadastro se contradiz e a classificacao expressa a intencao).
        if not r.get("ativo", 1):
            continue
        # ANCORA NA RAIZ (bug achado pelo dono, 18/07): a query traz a trilha
        # ancorada na FOLHA (item -> pai -> avo). Produto pendurado num nivel
        # raso (ex.: AYMORE SALPET direto em CORREDOR 140; 122 no corredor e
        # 806 direto no setor) deslizava a trilha inteira — "prateleira:
        # CORREDOR 140, setor: BISCOITOS BISCOITOS". O degrau de CIMA e sempre
        # o setor; o que faltar EMBAIXO fica vazio (o relatorio mostra
        # "(sem prateleira)"), nunca escorrega.
        folha = str(r.get("prateleira") or "").strip()
        pai = str(r.get("corredor") or "").strip()
        avo = str(r.get("setor") or "").strip()
        if avo:                       # 3 degraus completos
            setor, corredor, prateleira = avo, pai, folha
        elif pai:                     # item pendurado no corredor
            setor, corredor, prateleira = pai, folha, ""
        else:                         # item pendurado direto no setor/raiz
            setor, corredor, prateleira = folha, "", ""
        if "INATIVOS OU FORA DO MIX" in (setor, corredor, prateleira):
            continue
        linhas.append([
            r["codigo"],
            r.get("descricao"),
            caixa,
            setor,
            corredor,
            prateleira,
            r.get("curva"),
            peso,
        ])
    _escrever_atomico(caminho, _csv_ponto_virgula(cab, linhas))
    return len(linhas)


# ---------- Consumidor: listagem-fornecedor ----------

def negociacao_csv(rows, caminho):
    """Produto x fornecedor da tela de negociacao (dt_alteracao pode ser
    NULL -> vazio). Regra 1 do app listagem-fornecedor."""
    cab = ["codigo", "fornecedor", "dt_alteracao"]
    linhas = [[r["codigo"], r["fornecedor"], r.get("dt_alteracao") or ""]
              for r in rows]
    _escrever_atomico(caminho, _csv_ponto_virgula(cab, linhas))
    return len(linhas)


def entradas_fornecedor_csv(rows, caminho):
    """Entregas por produto x dia x fornecedor, qtd em UNIDADES."""
    cab = ["codigo", "data", "fornecedor", "qtd"]
    linhas = [[r["codigo"], r["data"], r["fornecedor"], r["qtd"]]
              for r in rows]
    _escrever_atomico(caminho, _csv_ponto_virgula(cab, linhas))
    return len(linhas)


def catalogo_listagem_csv(cat, caminho):
    """Catalogo enxuto p/ a listagem: SEM custo e SEM preco (regra do repo:
    valores nunca saem em arquivo de consumidor fora da cotacao)."""
    cab = ["codigo", "descricao", "embalagem", "curva", "peso", "ativo"]
    linhas = [[r["codigo"], r["descricao"],
               r.get("embalagem") if r.get("embalagem") is not None else "",
               r.get("curva") or "", r.get("peso"), r.get("ativo")]
              for r in cat]
    _escrever_atomico(caminho, _csv_ponto_virgula(cab, linhas))
    return len(linhas)
