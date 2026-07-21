# -*- coding: utf-8 -*-
"""Series historicas semanais do Painel de Compras (spec §13).

Amostras TODA SEGUNDA-FEIRA desde 2026-04-06 (primeira segunda >= 01/04) +
o ponto de hoje. As 4 series SQL sao recomputadas point-in-time a cada
geracao (sempre fieis as regras vigentes de cada aba); o "abaixo do custo"
historico e o REALIZADO (itens que venderam abaixo do custo na semana); a
ruptura vem do replay do detector (scripts/replay_ruptura.js via
scripts/backfill_historico_ruptura.py, rodado 1x) + o ponto de cada dia.
Pontos que sairem da janela do ERP ficam PRESERVADOS no historico.json —
a historia nunca encolhe.
"""
import json
import os
from datetime import date, timedelta

INICIO_HISTORICO = "2026-04-06"   # primeira segunda-feira >= 01/04/2026


def segundas_desde(inicio, hoje):
    """Datas ISO de todas as segundas de `inicio` ate `hoje`, mais o proprio
    `hoje` como ultimo ponto (se ja nao for uma delas)."""
    d = date.fromisoformat(inicio)
    fim = date.fromisoformat(hoje)
    d += timedelta(days=(7 - d.weekday()) % 7)   # proxima segunda (ou ela mesma)
    dias = []
    while d <= fim:
        dias.append(d.isoformat())
        d += timedelta(days=7)
    if hoje not in dias:
        dias.append(hoje)
    return dias


def _values_dias(dias):
    """Tabela T-SQL `(VALUES ...) s(dia)` com as datas do replay. As datas
    sao GERADAS internamente; ainda assim cada uma e validada como ISO antes
    de entrar no SQL (ValueError se nao for data)."""
    for d in dias:
        date.fromisoformat(d)
    return "(VALUES " + ", ".join(f"('{d}')" for d in dias) + ") s(dia)"


def sql_series(dias, cobranca_max_dias=30, cobranca_dias_limiar=7,
               prepedido_dias=21):
    """SQLs point-in-time (dia -> valor) das 4 series exatas. Cada subquery
    replica a regra VIGENTE da aba aplicada aquela data.
    Aproximacoes documentadas: pre-pedidos usa dtPrePedidoAtendido como fim
    de vida (inEncerrado nao tem data no schema); na cobranca, o "tem item
    pendente" usa o estado ATUAL dos itens (nao ha data de atendimento por
    item) — hoje bate exato com o quadrante, no passado pode subcontar
    pedidos parcialmente atendidos depois; no relampago a serie compara so
    a DATA (a query do quadrante usa GETDATE() com hora — diferenca ~1%)."""
    v = _values_dias(dias)
    return {
        "validade_relampago": f"""
SELECT s.dia, (SELECT COUNT(*) FROM dbo.tbPromocaoRelampago pr
    WHERE CAST(s.dia AS date) BETWEEN pr.dtInicio AND pr.dtFim) AS v
FROM {v}""",
        "cobranca": f"""
SELECT s.dia, (SELECT COUNT(DISTINCT p.cdPedido)
    FROM dbo.tbPedido p
    JOIN dbo.tbPedidoCompra pc
      ON pc.cdPedidoCompra = p.cdPedido AND pc.cdPessoaFilial = p.cdPessoaFilial
    WHERE p.inEntrada = 1
      AND p.dtPedido <= CAST(s.dia AS date)
      AND p.dtPedido > DATEADD(day, -{int(cobranca_max_dias)}, CAST(s.dia AS date))
      AND (p.dtAtendido IS NULL OR p.dtAtendido > CAST(s.dia AS date))
      AND EXISTS (SELECT 1 FROM dbo.tbPedidoItem i
                  WHERE i.cdPedido = p.cdPedido
                    AND i.cdPessoaFilial = p.cdPessoaFilial
                    AND COALESCE(i.inAtendido, 0) = 0
                    AND i.qtPedidoItem > COALESCE(i.qtAtendida, 0))
      AND (DATEDIFF(day, p.dtPedido, CAST(s.dia AS date)) >= {int(cobranca_dias_limiar)}
           OR pc.dtEntregaPrevista < CAST(s.dia AS date))) AS v
FROM {v}""",
        "sellout": f"""
SELECT s.dia, (SELECT CAST(COALESCE(SUM(vd.vlSellOut), 0) AS decimal(14,2))
    FROM dbo.tbVendaPDV vd
    JOIN dbo.tbProduto pr2 ON pr2.cdProduto = vd.cdProduto
    JOIN dbo.tbPromocaoItem pi
      ON pi.cdPromocao = vd.cdPromocao AND pi.cdSuperProduto = pr2.cdSuperProduto
    WHERE vd.vlSellOut > 0 AND vd.dtVenda <= CAST(s.dia AS date)
      AND pi.dtPagamentoReceitaSellOut IS NOT NULL) AS v
FROM {v}""",
        "prepedidos": f"""
SELECT s.dia, (SELECT COUNT(*) FROM dbo.tbPrePedido pp
    WHERE pp.dtPrePedido <= CAST(s.dia AS date)
      AND pp.dtPrePedido > DATEADD(day, -{int(prepedido_dias)}, CAST(s.dia AS date))
      AND (pp.dtPrePedidoAtendido IS NULL
           OR pp.dtPrePedidoAtendido > CAST(s.dia AS date))) AS v
FROM {v}""",
    }


def serie_abaixo_custo(vendas, dias):
    """Itens DISTINTOS que VENDERAM abaixo do custo na semana que termina em
    cada amostra (7 dias, inclusive). Fonte: linhas da query VENDAS
    (valor e custo_venda sao TOTAIS do item no dia)."""
    por_dia = {}
    for r in vendas or []:
        try:
            if (float(r.get("qtd_vendida") or 0) > 0
                    and float(r.get("valor") or 0) < float(r.get("custo_venda") or 0)):
                por_dia.setdefault(str(r["data"])[:10], set()).add(str(r["codigo"]))
        except (TypeError, ValueError):
            pass
    serie = []
    for d in dias:
        fim = date.fromisoformat(d)
        ini = fim - timedelta(days=6)
        cods = set()
        for dia_v, s in por_dia.items():
            try:
                if ini <= date.fromisoformat(dia_v) <= fim:
                    cods |= s
            except ValueError:
                pass
        serie.append({"s": d, "v": len(cods)})
    return serie


def corte_ruptura(itens):
    """MESMA regra do quadrante (Q.ruptura.corte do template e do wrapper
    scripts/replay_ruptura.js — manter os TRES em sincronia): prob > 0.75,
    parado > 1 dia, e guardrail (entrega <=30d com cobertura sobrando)."""
    n = 0
    for i in itens or []:
        if (i.get("probabilidade") or 0) <= 0.75:
            continue
        if (i.get("dias_parado") or 0) <= 1:
            continue
        ent = i.get("entrega_dias")
        if (ent is not None and ent <= 30
                and (i.get("cobertura_restante") or 0) > 0):
            continue
        n += 1
    return n


def mesclar_historico(destino, novas, carimbo):
    """Mescla pontos novos no painel/historico.json: mesma data substitui,
    datas antigas ausentes das novas sao PRESERVADAS. Grava atomico e
    devolve o dict final."""
    arq = os.path.join(destino, "historico.json")
    atual = {"series": {}}
    if os.path.exists(arq):
        try:
            with open(arq, encoding="utf-8") as f:
                atual = json.load(f)
        except (OSError, ValueError):
            atual = {"series": {}}
    series = atual.get("series") or {}
    for nome, pontos in (novas or {}).items():
        por_data = {p["s"]: p for p in series.get(nome, [])}
        for p in pontos or []:
            por_data[p["s"]] = p
        series[nome] = sorted(por_data.values(), key=lambda p: p["s"])
    out = {"gerado_em": carimbo, "series": series}
    tmp = arq + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    os.replace(tmp, arq)
    return out
