# -*- coding: utf-8 -*-
"""Curva minima de caixas por ponto fixo: sobe caixa nos slots que falham,
resimula o dia inteiro (a fila atravessa faixas), repete ate todos passarem."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import dim_dimensionador as d  # noqa: E402


def test_nivel_por_slot_agrupa_pela_chegada():
    # 2 clientes no slot 0 (1 dentro da meta), 2 no slot 1 (ambos dentro)
    chegadas = [0, 10, 1800, 1810]
    esperas = [0.0, 300.0, 10.0, 20.0]
    nivel = d.nivel_por_slot(chegadas, esperas, meta_seg=180.0)
    assert nivel[0] == 0.5
    assert nivel[1] == 1.0


def test_cliente_nao_atendido_conta_como_fora_da_meta():
    # None = nao havia caixa aberto. Isso e a PIOR falha possivel de nivel de
    # servico; ignorar o None faria um dia sem caixa nenhum parecer 100% de meta.
    nivel = d.nivel_por_slot([0, 10], [0.0, None], meta_seg=180.0)
    assert nivel[0] == 0.5


def test_demanda_folgada_pede_um_caixa():
    # 1 cliente a cada 600s, servico 100s: 1 caixa sobra
    chegadas = [i * 600 for i in range(12)]
    servicos = [100.0] * 12
    curva, teto = d.dimensionar_dia(chegadas, servicos, c_max=8)
    assert curva[0] == 1
    assert teto == set()


def test_demanda_pesada_pede_mais_caixa():
    # 30 clientes juntos no slot 0, servico 100s: 1 caixa da fila de 3000s
    chegadas = [0] * 30
    servicos = [100.0] * 30
    curva, _ = d.dimensionar_dia(chegadas, servicos, meta_pct=0.95, meta_seg=180.0, c_max=40)
    # com c caixas, o k-esimo cliente espera ~(k//c)*100s; para 95% < 180s
    # precisa de c grande o suficiente -> muito mais que 1
    assert curva[0] > 1


def test_curva_atinge_a_meta_que_prometeu():
    import dim_simulador as sim
    chegadas = [i * 40 for i in range(45)]     # 45 clientes num slot
    servicos = [100.0] * 45
    curva, teto = d.dimensionar_dia(chegadas, servicos, meta_pct=0.95, meta_seg=180.0, c_max=20)
    assert teto == set()
    esperas = sim.simular(chegadas, servicos, curva)
    nivel = d.nivel_por_slot(chegadas, esperas, meta_seg=180.0)
    assert all(v >= 0.95 for v in nivel.values())


def test_teto_e_reportado_nao_escondido():
    # demanda absurda com c_max=1: impossivel atingir a meta -> slot no teto
    chegadas = [0] * 50
    servicos = [100.0] * 50
    curva, teto = d.dimensionar_dia(chegadas, servicos, c_max=1)
    assert curva[0] == 1
    assert 0 in teto


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
