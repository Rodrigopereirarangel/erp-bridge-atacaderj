# -*- coding: utf-8 -*-
"""Camada de projecao: recebe a camada bruta (linhas canonicas) e escreve o
formato EXATO que cada consumidor ja espera. Toda escrita e atomica
(.tmp + rename) para nunca deixar um consumidor ler um arquivo pela metade.
"""

import csv
import io
import json
import os


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


def curva_abc_csv(catalogo, caminho):
    cab = ["codigo", "curva"]
    linhas = [[r["codigo"], r.get("curva")] for r in catalogo if r.get("curva") is not None]
    _escrever_atomico(caminho, _csv_ponto_virgula(cab, linhas))
    return len(linhas)
