# -*- coding: utf-8 -*-
"""Deteccao de saturacao = deteccao de demanda censurada.

A analise mede a chegada pelo INICIO do cupom, nao pela entrada na fila. Se um
slot saturou, as chegadas aparecem represadas pela propria capacidade e o
numero de caixas sai subestimado. Em vez de supor que nao acontece, medimos: um
slot saturado tem todos os PDVs abertos colados, sem folga. Onde isso acontecer,
o resultado e rotulado PISO, nao estimativa.
"""

SLOT_SEG = 1800   # faixa de 30 min


def slot_de(dt, slot_seg=SLOT_SEG):
    """Indice da faixa dentro do dia (0 = 00:00-00:30)."""
    segundos = dt.hour * 3600 + dt.minute * 60 + dt.second
    return int(segundos // slot_seg)


def folga_por_slot(cupons, slot_seg=SLOT_SEG):
    """Fracao do tempo-caixa ocioso em cada (dia, slot).

    Tempo ocupado e recortado no slot: cupom que atravessa a fronteira conta
    so a parte dentro. Tempo disponivel = (PDVs abertos no slot) x slot_seg.
    """
    ocupado, pdvs = {}, {}
    for c in cupons:
        dia = c["inicio"].date()
        ini_s = c["inicio"].hour * 3600 + c["inicio"].minute * 60 + c["inicio"].second
        fim_s = ini_s + (c["fim"] - c["inicio"]).total_seconds()
        # Guarda: garante que nenhum cupom cruza meia-noite. A loja opera 05:30-15:00
        # e cupons duram ~2min, entao isso nunca acontece em dados reais. Clipeamos
        # para nunca emitir um indice de slot >= 48 (fora do intervalo [0,47]).
        fim_s = min(fim_s, 86400)
        primeiro, ultimo = int(ini_s // slot_seg), int(fim_s // slot_seg)
        for s in range(primeiro, ultimo + 1):
            borda_ini, borda_fim = s * slot_seg, (s + 1) * slot_seg
            dentro = min(fim_s, borda_fim) - max(ini_s, borda_ini)
            if dentro > 0:
                ocupado[(dia, s)] = ocupado.get((dia, s), 0.0) + dentro
                pdvs.setdefault((dia, s), set()).add(c["pdv"])
    folgas = {}
    for chave, seg in ocupado.items():
        disponivel = len(pdvs[chave]) * slot_seg
        folgas[chave] = max(0.0, 1.0 - seg / disponivel)
    return folgas


def slots_saturados(cupons, limiar=0.05, slot_seg=SLOT_SEG):
    """(dia, slot) com folga <= limiar: ali a demanda observada e PISO."""
    return {k for k, v in folga_por_slot(cupons, slot_seg).items() if v <= limiar}
