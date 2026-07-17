# -*- coding: utf-8 -*-
"""P85 entre os dias (a margem de seguranca) e cobertura de turnos 6h20."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import dim_escala as esc  # noqa: E402


def test_curva_percentil_pega_o_dia_ruim_nao_o_mediano():
    # slot 10: dias com 2,2,2,2,6 caixas. Mediana=2, P85 arredonda pra cima.
    curvas = {
        "d1": {10: 2}, "d2": {10: 2}, "d3": {10: 2}, "d4": {10: 2}, "d5": {10: 6},
    }
    p85 = esc.curva_percentil(curvas, p=0.85)
    assert p85[10] > 2          # nao e o dia mediano
    assert p85[10] <= 6


def test_curva_percentil_arredonda_pra_cima():
    # caixa e inteiro: 2.3 caixas = 3 caixas
    curvas = {"d1": {5: 2}, "d2": {5: 3}}
    assert esc.curva_percentil(curvas, p=0.85) == {5: 3}


def test_dia_sem_o_slot_conta_como_zero():
    # se num dia o slot nem existiu (loja fechada mais cedo), a demanda foi 0
    curvas = {"d1": {5: 4}, "d2": {}, "d3": {}, "d4": {}, "d5": {}}
    p85 = esc.curva_percentil(curvas, p=0.85)
    assert p85[5] <= 4


def test_cobertura_de_um_slot_pede_um_turno():
    total, inicios = esc.cobertura_minima({10: 1}, slots_turno=13, slots_produtivos=12)
    assert total == 1


def test_cobertura_cobre_a_demanda_toda():
    # demanda de 2 caixas em 12 slots seguidos -> 2 turnos bastam
    curva = {s: 2 for s in range(10, 22)}
    total, inicios = esc.cobertura_minima(curva, slots_turno=13, slots_produtivos=12)
    assert total == 2


def test_cobertura_pede_mais_turno_quando_o_dia_e_longo():
    # 19 slots (9h30) com 1 caixa: um turno de 12 produtivos nao cobre -> 2
    curva = {s: 1 for s in range(11, 30)}
    total, inicios = esc.cobertura_minima(curva, slots_turno=13, slots_produtivos=12)
    assert total == 2


def test_cobertura_e_realmente_suficiente():
    curva = {10: 1, 11: 3, 12: 3, 13: 2, 14: 1}
    total, inicios = esc.cobertura_minima(curva, slots_turno=13, slots_produtivos=12)
    cobertura = esc.cobertura_de(inicios, slots_turno=13, slots_produtivos=12)
    for s, exigido in curva.items():
        assert cobertura.get(s, 0) >= exigido
    assert total == sum(inicios.values())


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
