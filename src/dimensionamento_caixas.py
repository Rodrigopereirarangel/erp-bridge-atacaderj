# -*- coding: utf-8 -*-
"""Dimensionamento de caixas e operadoras por dia da semana.

Responde: quantos PDVs (min/max por faixa) e quantas operadoras por dia da
semana, para 95% dos clientes esperarem menos de 3 min na fila.

Spec: docs/superpowers/specs/2026-07-17-dimensionamento-caixas-design.md
Roda no PC-ponte (unica maquina que alcanca o banco).

Uso:
  python src/dimensionamento_caixas.py
  python src/dimensionamento_caixas.py --desde 2026-01-22 --p 0.85
"""
import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402
import dim_dimensionador  # noqa: E402
import dim_erlang  # noqa: E402
import dim_escala  # noqa: E402
import dim_queries  # noqa: E402
import dim_saturacao  # noqa: E402
import dim_servico  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIAS = {2: "segunda", 3: "terca", 4: "quarta", 5: "quinta", 6: "sexta", 7: "sabado"}
META_PCT, META_SEG = 0.95, 180.0


def _hora(slot):
    return "%02d:%02d" % (slot * 30 // 60, slot * 30 % 60)


def carregar_config(caminho):
    caminho = caminho or os.path.join(RAIZ, "config.local.json")
    if not os.path.exists(caminho):
        raise SystemExit("[ERRO] Preencha config.local.json (secao db) primeiro.")
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def conferir_fonte(conn, desde):
    """Prova contabil: tbCupom tem que bater com o consolidado do ERP."""
    consolidado = {r["dia"]: int(r["cupons"])
                   for r in db.consultar(conn, dim_queries.CONFERENCIA_CONSOLIDADO
                                         .format(desde=desde))}
    return consolidado


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Dimensionamento de caixas por dia da semana")
    ap.add_argument("--desde", default="2026-01-22", help="data inicial YYYY-MM-DD")
    ap.add_argument("--p", type=float, default=0.85, help="percentil do dia (a margem)")
    ap.add_argument("--stress", type=float, default=0.10, help="sensibilidade +-X na demanda")
    ap.add_argument("--corte-handover", type=float, default=120.0)
    ap.add_argument("--c-max", type=int, default=12)
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    cfg = carregar_config(args.config)
    conn = db.conectar(cfg["db"])
    try:
        cupons = db.consultar(conn, dim_queries.CUPONS.format(desde=args.desde))
        consolidado = conferir_fonte(conn, args.desde)
    finally:
        conn.close()
    if not cupons:
        raise SystemExit("[ERRO] Nenhum cupom no periodo.")

    # 1) conferencia da fonte contra o consolidado do ERP
    nao_cancelados = {}
    for c in cupons:
        if not c["cancelado"]:
            nao_cancelados[c["dia"]] = nao_cancelados.get(c["dia"], 0) + 1
    divergentes = [d for d, n in nao_cancelados.items()
                   if d in consolidado and consolidado[d] != n]
    print("== Conferencia da fonte (tbCupom x tbConsPDVOperador) ==")
    print("   dias conferidos: %d | divergentes: %d" % (len(consolidado), len(divergentes)))
    if divergentes:
        print("   [ATENCAO] dias que NAO batem: %s" % sorted(divergentes)[:10])

    # 2) handover + servico
    handover = dim_servico.estimar_handover(cupons, args.corte_handover)
    duracoes = dim_servico.duracoes(cupons)
    print("\n== Servico ==")
    print("   cupons: %d (cancelados: %d)" % (len(cupons), sum(c["cancelado"] for c in cupons)))
    print("   duracao mediana: %.0fs | handover estimado: %.0fs (corte %.0fs)"
          % (dim_servico.percentil(duracoes, 0.5), handover, args.corte_handover))

    # 3) saturacao (demanda censurada)
    saturados = dim_saturacao.slots_saturados(cupons)
    print("\n== Saturacao (demanda censurada) ==")
    print("   slots saturados: %d" % len(saturados))
    if saturados:
        print("   [ATENCAO] nesses slots o numero abaixo e PISO, nao estimativa.")

    # 4) dimensionar cada dia
    por_dia = {}
    for c in cupons:
        por_dia.setdefault((c["dia"], c["dow"]), []).append(c)
    rng = random.Random(20260717)
    curvas, teto_total = {}, set()
    for (dia, dow), lista in por_dia.items():
        lista.sort(key=lambda c: c["inicio"])
        chegadas = [c["inicio"].hour * 3600 + c["inicio"].minute * 60 + c["inicio"].second
                    for c in lista]
        servicos = [(c["fim"] - c["inicio"]).total_seconds() + handover for c in lista]
        curva, teto = dim_dimensionador.dimensionar_dia(
            chegadas, servicos, META_PCT, META_SEG, args.c_max)
        curvas.setdefault(dow, {})[dia] = curva
        teto_total |= {(dia, s) for s in teto}

    # 5) agregar no percentil e montar a escala
    print("\n== Caixas necessarios (P%d dos dias, 95%% < 3min) ==" % int(args.p * 100))
    for dow in sorted(curvas):
        p_curva = dim_escala.curva_percentil(curvas[dow], args.p)
        ativos = {s: c for s, c in p_curva.items() if c > 0}
        if not ativos:
            continue
        total, inicios = dim_escala.cobertura_minima(ativos)
        pico_slot = max(ativos, key=lambda s: ativos[s])
        print("\n   %-8s min %d caixa(s) | max %d caixa(s) (pico %s) | %d operadora(s)"
              % (DIAS.get(dow, dow), min(ativos.values()), max(ativos.values()),
                 _hora(pico_slot), total))
        print("      curva: " + " ".join("%s=%d" % (_hora(s), ativos[s])
                                         for s in sorted(ativos)))

    # 6) ociosidade: exigido x aberto de fato
    print("\n== Ociosidade (exigido x aberto de fato) ==")
    for dow in sorted(curvas):
        p_curva = dim_escala.curva_percentil(curvas[dow], args.p)
        abertos = {}
        for dia in curvas[dow]:
            for c in por_dia[(dia, dow)]:
                s = dim_saturacao.slot_de(c["inicio"])
                abertos.setdefault(s, {}).setdefault(dia, set()).add(c["pdv"])
        deltas = []
        for s in sorted(p_curva):
            if p_curva[s] <= 0 or s not in abertos:
                continue
            medio = sum(len(v) for v in abertos[s].values()) / len(abertos[s])
            deltas.append((s, medio - p_curva[s]))
        if deltas:
            pior = max(deltas, key=lambda x: x[1])
            print("   %-8s excesso medio %.1f caixa(s) | pior faixa %s (+%.1f)"
                  % (DIAS.get(dow, dow), sum(d for _, d in deltas) / len(deltas),
                     _hora(pior[0]), pior[1]))

    # 7) stress: +-X% na demanda
    print("\n== Sensibilidade (demanda %+.0f%%) ==" % (args.stress * 100))
    for fator, rotulo in ((1 + args.stress, "+"), (1 - args.stress, "-")):
        totais = {}
        for dow, por in curvas.items():
            novas = {}
            for dia, _curva in por.items():
                lista = sorted(por_dia[(dia, dow)], key=lambda c: c["inicio"])
                if fator > 1:
                    extras = rng.sample(lista, int(len(lista) * (fator - 1)))
                    lista = sorted(lista + extras, key=lambda c: c["inicio"])
                else:
                    lista = sorted(rng.sample(lista, int(len(lista) * fator)),
                                   key=lambda c: c["inicio"])
                chegadas = [c["inicio"].hour * 3600 + c["inicio"].minute * 60
                            + c["inicio"].second for c in lista]
                servicos = [(c["fim"] - c["inicio"]).total_seconds() + handover
                            for c in lista]
                nc, _ = dim_dimensionador.dimensionar_dia(
                    chegadas, servicos, META_PCT, META_SEG, args.c_max)
                novas[dia] = nc
            pc = dim_escala.curva_percentil(novas, args.p)
            ativos = {s: c for s, c in pc.items() if c > 0}
            if ativos:
                totais[dow] = dim_escala.cobertura_minima(ativos)[0]
        print("   %s%.0f%%: %s" % (rotulo, abs(args.stress * 100),
                                   " | ".join("%s=%d" % (DIAS.get(d, d), t)
                                              for d, t in sorted(totais.items()))))

    if teto_total:
        print("\n[ATENCAO] %d (dia, slot) bateram no teto de %d caixas: ali o numero "
              "e PISO." % (len(teto_total), args.c_max))
    print("\nLimites declarados: o modelo assume a operadora como gargalo do caixa "
          "(empacotador nao esta no banco); a escala P%d falha por construcao em "
          "~%d%% dos dias." % (int(args.p * 100), int((1 - args.p) * 100)))


if __name__ == "__main__":
    main()
