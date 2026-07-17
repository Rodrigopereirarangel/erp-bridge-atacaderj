# -*- coding: utf-8 -*-
"""Curva minima de caixas que atinge a meta, dia a dia.

Por ponto fixo, e nao slot a slot: caixa a menos numa faixa empurra fila para a
seguinte, entao os slots nao sao independentes. Sobe +1 caixa em todo slot que
falha, resimula o DIA INTEIRO, repete. A curva so cresce e e limitada por
c_max, entao termina.

Slot que bate no teto (c_max) sem atingir a meta e DEVOLVIDO no conjunto
'no_teto' — nao e escondido atras de um numero limpo.
"""
import dim_simulador as sim

SLOT_SEG = sim.SLOT_SEG


def nivel_por_slot(chegadas, esperas, meta_seg, slot_seg=SLOT_SEG):
    """Fracao dos clientes de cada slot (pela CHEGADA) dentro da meta.
    Cliente nao atendido (espera None) conta como fora da meta."""
    dentro, total = {}, {}
    for t, w in zip(chegadas, esperas):
        s = int(t // slot_seg)
        total[s] = total.get(s, 0) + 1
        if w is not None and w < meta_seg:
            dentro[s] = dentro.get(s, 0) + 1
    return {s: dentro.get(s, 0) / n for s, n in total.items()}


def dimensionar_dia(chegadas, servicos, meta_pct=0.95, meta_seg=180.0,
                    c_max=12, slot_seg=SLOT_SEG):
    """Menor curva {slot: caixas} com meta_pct dos clientes abaixo de meta_seg
    em CADA slot. Devolve (curva, slots_no_teto)."""
    if not chegadas:
        return {}, set()
    slots = sorted({int(t // slot_seg) for t in chegadas})
    curva = {s: 1 for s in slots}
    no_teto = set()
    for _ in range(int(c_max) * len(slots) + 1):
        esperas = sim.simular(chegadas, servicos, curva, slot_seg)
        nivel = nivel_por_slot(chegadas, esperas, meta_seg, slot_seg)
        falhando = [s for s, v in nivel.items() if v < meta_pct and s not in no_teto]
        if not falhando:
            break
        subiu = False
        for s in falhando:
            if curva[s] < c_max:
                curva[s] += 1
                subiu = True
            else:
                no_teto.add(s)
        if not subiu:
            break
    return curva, no_teto
