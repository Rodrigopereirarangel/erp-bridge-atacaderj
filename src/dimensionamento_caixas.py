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
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402
import dim_dimensionador  # noqa: E402
import dim_escala  # noqa: E402
import dim_queries  # noqa: E402
import dim_saturacao  # noqa: E402
import dim_servico  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIAS = {2: "segunda", 3: "terca", 4: "quarta", 5: "quinta", 6: "sexta", 7: "sabado"}
META_PCT, META_SEG = 0.95, 180.0


def _hora(slot):
    return "%02d:%02d" % (slot * 30 // 60, slot * 30 % 60)


# --------------------------------------------------------------------------
# Helpers puros (sem I/O) — testados isoladamente em
# tests/test_dimensionamento_caixas.py.
# --------------------------------------------------------------------------

def dias_divergentes(nao_cancelados, consolidado):
    """Dias em que o extraido (tbCupom, nao cancelados) diverge do consolidado
    oficial do ERP (tbConsPDVOperador).

    Percorre TODO dia presente em `consolidado` (a fonte de verdade contabil).
    Um dia que esta em `consolidado` mas esta AUSENTE de `nao_cancelados`
    conta como divergente com esperado consolidado[d] contra obtido 0 — cobre
    o dia todo-cancelado ou totalmente ausente da extracao, que uma
    comparacao so sobre as chaves de `nao_cancelados` deixaria passar.
    """
    divergentes = set()
    for dia, esperado in consolidado.items():
        obtido = nao_cancelados.get(dia, 0)
        if esperado != obtido:
            divergentes.add(dia)
    return divergentes


def deve_abortar(n_divergentes, n_comparados, limiar=0.05):
    """True quando a fracao de dias divergentes excede `limiar`.

    1 dia estranho num universo de 120 nao deveria travar a analise inteira;
    divergencia generalizada indica bug sistemico de extracao e os numeros
    nao sao confiaveis. `n_comparados == 0` nunca aborta (nada foi conferido,
    nao ha base para decidir — e evita divisao por zero).
    """
    if n_comparados <= 0:
        return False
    return (n_divergentes / n_comparados) > limiar


def chegadas_servicos(lista, handover):
    """(chegadas, servicos) de uma lista de cupons, ordenados pelo horario de
    INICIO (ascendente). chegadas = segundos desde a meia-noite; servicos =
    duracao do cupom (fim - inicio) + handover, na mesma ordem de chegadas.

    Pura: nao muta `lista` (usa `sorted`, nao `.sort()`).
    """
    ordenada = sorted(lista, key=lambda c: c["inicio"])
    chegadas = [c["inicio"].hour * 3600 + c["inicio"].minute * 60 + c["inicio"].second
                for c in ordenada]
    servicos = [(c["fim"] - c["inicio"]).total_seconds() + handover for c in ordenada]
    return chegadas, servicos


def slots_piso_do_dow(dias_do_dow, floor_set):
    """Slots (so o indice, sem o dia) que sao PISO para um dia-da-semana: pelo
    menos um dos dias que compoem a curva desse dow bateu no piso (saturado
    ou no teto de c_max) naquele slot.

    `dias_do_dow` = dias (date) que contribuiram para a curva do dow.
    `floor_set` = uniao global de (dia, slot) saturados ou no teto.
    """
    return {s for (dia, s) in floor_set if dia in dias_do_dow}


def validar_desde(desde):
    """Valida --desde no formato YYYY-MM-DD antes de ser interpolado nas
    duas SQLs (CUPONS e CONFERENCIA_CONSOLIDADO, via .format(desde=...)).

    args.desde e controlado pelo operador (argparse) atras de um login
    somente-leitura -- risco de injecao e quase nulo -- mas hoje um valor
    malformado (ex.: "22-01-2026" ou lixo) so aparece la na frente como um
    erro de SQL opaco. Validar aqui falha cedo com mensagem clara e, de
    quebra, fecha a porta teorica de injecao: uma string que nao seja
    data no formato esperado nunca chega a virar SQL.
    """
    try:
        datetime.strptime(desde, "%Y-%m-%d")
    except ValueError:
        raise SystemExit(
            "[ERRO] --desde invalido (%r): use o formato YYYY-MM-DD." % (desde,))


def checar_tipos_cupom(cupom):
    """Guarda de tipo: falha cedo e com mensagem clara se o driver ODBC
    devolver `inicio`/`fim` (HoraInicio/HoraFim, ver dim_queries.py) como
    algo que nao seja datetime.datetime -- por exemplo str ou datetime.time.

    O fato "sao datetime" foi conferido em 2026-07-17 com uma ferramenta de
    consulta (ver dim_queries.py), nao necessariamente atraves DESTE driver
    ODBC especifico. Todo modulo dim_* faz .hour/.date()/(fim - inicio)
    direto em cima desses campos (chegadas_servicos acima inclusive); sem
    essa guarda, o tipo errado so aparece bem mais fundo, como um
    AttributeError opaco dentro de um dim_*.py. So um guarda -- nao tenta
    converter/coagir o valor.
    """
    for campo in ("inicio", "fim"):
        valor = cupom[campo]
        if not isinstance(valor, datetime):
            raise SystemExit(
                "[ERRO] tbCupom.%s veio como %s (esperado datetime.datetime). "
                "O driver ODBC esta devolvendo HoraInicio/HoraFim no tipo errado -- "
                "confira o driver em config.local.json antes de rodar de novo."
                % (campo, type(valor).__name__))


def construir_parser():
    ap = argparse.ArgumentParser(description="Dimensionamento de caixas por dia da semana")
    ap.add_argument("--desde", default="2026-01-22", help="data inicial YYYY-MM-DD")
    ap.add_argument("--p", type=float, default=0.85, help="percentil do dia (a margem)")
    ap.add_argument("--stress", type=float, default=0.10, help="sensibilidade +-X na demanda")
    ap.add_argument("--corte-handover", type=float, default=120.0)
    # 9 = PDV 1-9 (varejo, o unico grupo dimensionado aqui). PDV 10 nao
    # existe na loja; 11/12 sao atacado e ja saem excluidos das queries
    # (ver dim_queries.py) -- 9 e o teto FISICO real de caixas simultaneos.
    ap.add_argument("--c-max", type=int, default=9,
                     help="numero de PDVs (caixas) de varejo que dao pra abrir ao mesmo "
                          "tempo na loja (default 9 = PDV 1-9); um slot que precisar de "
                          "mais que isso e flagado como piso/floor (fisicamente inviavel), "
                          "nao impresso como estimativa limpa")
    ap.add_argument("--limiar-divergencia", type=float, default=0.05,
                     help="fracao maxima de dias divergentes antes de abortar (default 0.05)")
    ap.add_argument("--config", default=None)
    return ap


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
    args = construir_parser().parse_args()
    validar_desde(args.desde)

    cfg = carregar_config(args.config)
    conn = db.conectar(cfg["db"])
    try:
        cupons = db.consultar(conn, dim_queries.CUPONS.format(desde=args.desde))
        consolidado = conferir_fonte(conn, args.desde)
    finally:
        conn.close()
    if not cupons:
        raise SystemExit("[ERRO] Nenhum cupom no periodo.")
    checar_tipos_cupom(cupons[0])

    # 1) conferencia da fonte contra o consolidado do ERP
    nao_cancelados = {}
    for c in cupons:
        if not c["cancelado"]:
            nao_cancelados[c["dia"]] = nao_cancelados.get(c["dia"], 0) + 1
    divergentes = dias_divergentes(nao_cancelados, consolidado)
    n_comparados = len(consolidado)
    print("== Conferencia da fonte (tbCupom x tbConsPDVOperador) ==")
    print("   dias conferidos: %d | divergentes: %d" % (n_comparados, len(divergentes)))
    if divergentes:
        print("   [ATENCAO] dias que NAO batem (extraido x consolidado): %s"
              % sorted(divergentes)[:10])
        if deve_abortar(len(divergentes), n_comparados, args.limiar_divergencia):
            raise SystemExit(
                "[ERRO] %d/%d dias divergentes (%.1f%%) passam do limiar de %.1f%%: "
                "extracao nao confiavel, abortando antes do resto do relatorio."
                % (len(divergentes), n_comparados,
                   100.0 * len(divergentes) / n_comparados,
                   100.0 * args.limiar_divergencia))
        print("   [ATENCAO] divergencia abaixo do limiar (%.1f%%): relatorio continua, "
              "mas os dias acima nao sao confiaveis." % (100.0 * args.limiar_divergencia))

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
        chegadas, servicos = chegadas_servicos(lista, handover)
        curva, teto = dim_dimensionador.dimensionar_dia(
            chegadas, servicos, META_PCT, META_SEG, args.c_max)
        curvas.setdefault(dow, {})[dia] = curva
        teto_total |= {(dia, s) for s in teto}

    # 5) agregar no percentil e montar a escala
    floor_total = saturados | teto_total
    print("\n== Caixas necessarios (P%d dos dias, 95%% < 3min) ==" % int(args.p * 100))
    teve_piso = False
    for dow in sorted(curvas):
        p_curva = dim_escala.curva_percentil(curvas[dow], args.p)
        ativos = {s: c for s, c in p_curva.items() if c > 0}
        if not ativos:
            continue
        total, inicios = dim_escala.cobertura_minima(ativos)
        pico_slot = max(ativos, key=lambda s: ativos[s])
        piso_dow = slots_piso_do_dow(set(curvas[dow]), floor_total)
        print("\n   %-8s min %d caixa(s) | max %d caixa(s) (pico %s) | %d operadora(s)"
              % (DIAS.get(dow, dow), min(ativos.values()), max(ativos.values()),
                 _hora(pico_slot), total))
        print("      curva: " + " ".join(
            "%s=%d%s" % (_hora(s), ativos[s], "*" if s in piso_dow else "")
            for s in sorted(ativos)))
        if piso_dow & ativos.keys():
            teve_piso = True
    if teve_piso:
        print("\n   * = piso (demanda censurada ou no teto de c_max): o numero e "
              "minimo, nao estimativa.")

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
                # sort fixo antes de amostrar: preserva a mesma sequencia (logo
                # o mesmo consumo do rng) que a versao anterior desta funcao.
                lista = sorted(por_dia[(dia, dow)], key=lambda c: c["inicio"])
                if fator > 1:
                    extras = rng.sample(lista, int(len(lista) * (fator - 1)))
                    lista = lista + extras
                else:
                    lista = rng.sample(lista, int(len(lista) * fator))
                chegadas, servicos = chegadas_servicos(lista, handover)
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
