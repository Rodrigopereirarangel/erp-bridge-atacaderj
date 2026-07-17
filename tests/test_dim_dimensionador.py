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


def test_curva_atravessa_faixa_fila_de_slot_anterior_afeta_o_seguinte():
    # Espalhamento (spillover) entre slots: e a razao de existir o ponto fixo
    # em vez de um dimensionador ingenuo slot a slot.
    #
    # slot_seg=10 -> slot 0 cobre [0,10), slot 1 cobre [10,20). 2 clientes
    # chegam JUNTOS em t=0 (slot 0), servico 200s cada. 1 cliente chega sozinho
    # em t=10 (bem no inicio do slot 1), servico curto de 5s.
    #
    # Slot 0 SOZINHO (nada o precede, entao aqui o ingenuo bate com o real):
    #   1 caixa -> esperas 0,200s -> so 1/2=50% dentro de 180s -> falha.
    #   2 caixas -> ambos comecam em t=0 -> esperas 0,0 -> 100% -> passa.
    #   minimo do slot 0 = 2.
    #
    # Slot 1 SOZINHO, na visao de um dimensionador ingenuo (fila zerada no
    # inicio do slot): 1 cliente, servico 5s, comeca livre -> espera 0 -> 1
    # caixa basta. Confirmado abaixo por execucao: dimensionar_dia so com o
    # cliente do slot 1 devolve curva={1: 1}.
    #
    # Mas dim_simulador.simular NAO zera a fila entre slots: o slot 1 HERDA o
    # estado dos caixas do slot 0. Com 2 caixas abertos no slot 0, ambos ficam
    # ocupados ate t=200 (cada um atende 1 cliente de 200s). Ao entrar no
    # slot 1 (t=10), _ajustar_pool so abre caixa GENUINAMENTE livre quando
    # curva[1] > numero de caixas ja abertos (aqui, > 2) -- com curva[1] igual
    # a 1 ou a 2 nenhum caixa novo aparece, o cliente do slot 1 cai atras do
    # atendimento em curso e espera 200-10=190s (> meta de 180s) -> FALHA.
    # So com curva[1]=3 um caixa realmente livre surge em t=10 -> espera 0.
    #
    # Provado por execucao direta (nao so por raciocinio, ver scratch previo):
    # simular(chegadas, servicos, {0:2,1:1}) e {0:2,1:2}) dao espera=190.0 pro
    # cliente do slot 1 (nivel 0.0) -- e exatamente esse acoplamento que o
    # ponto fixo (resimula o DIA INTEIRO a cada rodada) detecta e um
    # dimensionador ingenuo, isolado por slot, nao detectaria.
    import dim_simulador as sim

    chegadas = [0, 0, 10]
    servicos = [200.0, 200.0, 5.0]

    curva_ingenua_slot1, _ = d.dimensionar_dia([10], [5.0], meta_pct=0.95,
                                               meta_seg=180.0, c_max=12, slot_seg=10)
    assert curva_ingenua_slot1 == {1: 1}  # confirma a subestimativa ingenua

    curva, teto = d.dimensionar_dia(chegadas, servicos, meta_pct=0.95, meta_seg=180.0,
                                     c_max=12, slot_seg=10)
    assert teto == set()
    assert curva[0] == 2
    assert curva[1] == 3  # 1 a mais que curva[0]: so assim sobra caixa livre

    # Consistencia fim a fim (mesmo estilo de test_curva_atinge_a_meta_que_prometeu):
    # resimula com a curva DEVOLVIDA e confere que TODO slot atinge a meta,
    # inclusive o slot 1 que sofreu o espalhamento.
    esperas = sim.simular(chegadas, servicos, curva, slot_seg=10)
    nivel = d.nivel_por_slot(chegadas, esperas, meta_seg=180.0, slot_seg=10)
    assert all(v >= 0.95 for v in nivel.values())
    assert nivel[1] == 1.0  # cliente do slot 1 agora comeca em t=10, espera 0


def test_nivel_por_slot_com_slot_inteiro_sem_atendimento():
    # Um slot inteiro em que TODOS os clientes tem espera None (nenhum caixa
    # aberto) deve valer exatamente 0.0 -- nao pode estourar KeyError (por
    # faltar entrada em 'dentro'), nem virar 1.0 por engano, nem ser omitido.
    chegadas = [0, 10, 1800, 1810]
    esperas = [None, None, 50.0, 60.0]
    nivel = d.nivel_por_slot(chegadas, esperas, meta_seg=180.0)
    assert nivel[0] == 0.0
    assert nivel[1] == 1.0  # slot vizinho normal, so pra provar que o 0.0 nao "vazou"


def test_curva_bate_exatamente_no_c_max_e_passa():
    # 20 clientes juntos no slot 0, servico 100s cada: com c caixas, o cliente
    # de indice i (0-based) espera floor(i/c)*100s. Para 95% dentro de 180s e
    # preciso floor(i/c) <= 1 para pelo menos ceil(0.95*20)=19 clientes, ou
    # seja min(20, 2c) >= 19.
    #   c=9  -> min(20,18)=18 -> 90%  -> FALHA (confirmado: com c_max=9 cai no teto)
    #   c=10 -> min(20,20)=20 -> 100% -> PASSA
    # 10 e portanto o minimo exato: usando c_max=10, a curva deve bater
    # EXATAMENTE no teto e ainda assim passar -- ao contrario de
    # test_teto_e_reportado_nao_escondido, onde o teto e insuficiente.
    chegadas = [0] * 20
    servicos = [100.0] * 20
    curva, teto = d.dimensionar_dia(chegadas, servicos, meta_pct=0.95, meta_seg=180.0, c_max=10)
    assert curva[0] == 10
    assert 0 not in teto  # passou, mesmo estando no teto


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
