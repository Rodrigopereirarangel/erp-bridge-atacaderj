# -*- coding: utf-8 -*-
"""O simulador so vale se reproduzir a resposta ANALITICA num caso conhecido.
Este e o teste de aceitacao: chegada Poisson + servico exponencial = M/M/c,
onde Erlang-C da a resposta exata."""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import dim_erlang as e  # noqa: E402
import dim_simulador as sim  # noqa: E402


def _curva_constante(c, n_slots=200):
    return {s: c for s in range(n_slots)}


def test_fila_vazia_nao_espera():
    # chegadas espacadas de sobra: ninguem espera
    esperas = sim.simular([0, 1000, 2000], [100, 100, 100], _curva_constante(1))
    assert esperas == [0.0, 0.0, 0.0]


def test_fila_unica_fifo_acumula():
    # 1 caixa, 3 clientes juntos, servico 100s: esperas 0, 100, 200
    esperas = sim.simular([0, 0, 0], [100, 100, 100], _curva_constante(1))
    assert esperas == [0.0, 100.0, 200.0]


def test_dois_caixas_atendem_em_paralelo():
    # 2 caixas, 2 clientes juntos: ninguem espera
    esperas = sim.simular([0, 0], [100, 100], _curva_constante(2))
    assert esperas == [0.0, 0.0]


def test_sem_caixa_aberto_o_cliente_nao_e_atendido():
    esperas = sim.simular([0], [100], {0: 0})
    assert esperas == [None]


def test_caixa_que_abre_no_slot_seguinte_entra_no_pool():
    # slot 0 com 1 caixa, slot 1 com 2. O 1o cliente prende o caixa 1 ate 3600.
    # Em t=1800 abre o caixa 2: o cliente 1 pega ele na hora (espera 0) e sai
    # em 1900; o cliente 2 pega o MESMO caixa 2 em 1900 (espera 100) — nao
    # espera o caixa 1, que so vaga em 3600.
    curva = {0: 1, 1: 2}
    esperas = sim.simular([0, 1800, 1800], [3600, 100, 100], curva)
    assert esperas[0] == 0.0
    assert esperas[1] == 0.0
    assert esperas[2] == 100.0


def test_encolhe_com_ambos_caixas_ocupados_derruba_o_que_termina_mais_tarde():
    # slot 0: 2 caixas: slot 1: 1 caixa (a loja fecha um caixa as 18:00/1800s).
    # Clientes 1 e 2 chegam juntos em t=0 e pegam os 2 caixas na hora (espera 0):
    #   caixa A atende o cliente 1 (servico 3000) -> livre em 3000
    #   caixa B atende o cliente 2 (servico 5000) -> livre em 5000
    # Em t=1800 o pool tem que encolher de 2 para 1. Nenhum caixa esta ocioso
    # (3000 > 1800 e 5000 > 1800), entao o encolhimento tem que derrubar o
    # OCUPADO que termina mais tarde (5000) e manter o que termina mais cedo
    # (3000) — maximiza a capacidade de curto prazo.
    # Cliente 3 chega em t=1800: so resta o caixa que libera em 3000.
    # espera = 3000 - 1800 = 1200 (se o codigo (erradamente) mantivesse o
    # caixa 5000 em vez do 3000, a espera seria 3200 — os dois valores sao
    # bem distintos, entao o teste marca claramente qual caixa sobreviveu).
    chegadas = [0, 0, 1800]
    servicos = [3000, 5000, 100]
    curva = {0: 2, 1: 1}
    esperas = sim.simular(chegadas, servicos, curva)
    assert esperas[0] == 0.0
    assert esperas[1] == 0.0
    assert esperas[2] == 1200.0


def test_encolhe_para_zero_e_reabre_depois():
    # slot 0: 1 caixa; slot 1: 0 caixas (loja fecha tudo); slot 2: 1 caixa de novo.
    # Cliente A chega em t=0, servico 100 -> caixa livre em 100 (ocioso bem
    # antes do proximo corte de slot).
    # Em t=1800 o pool encolhe de 1 para 0: o unico caixa esta ocioso
    # (100 <= 1800), entao fecha sem drama. Cliente B chega em t=1800 com o
    # pool vazio -> None (ninguem atende).
    # Em t=3600 o pool reabre para 1 caixa, que entra livre em 3600 (o
    # instante do corte). Cliente C chega em t=3600 -> pega esse caixa na
    # hora, espera 0, e libera em 3600+50=3650.
    # Cliente D chega tambem em t=3600 (mesmo slot, sem novo ajuste de pool):
    # so ha 1 caixa, que esta ocupado ate 3650 -> espera = 3650-3600 = 50.
    # Isso confirma que o None do cliente B nao deixou lixo no heap nem
    # corrompeu os clientes seguintes.
    chegadas = [0, 1800, 3600, 3600]
    servicos = [100, 999, 50, 50]
    curva = {0: 1, 1: 0, 2: 1}
    esperas = sim.simular(chegadas, servicos, curva)
    assert esperas[0] == 0.0
    assert esperas[1] is None
    assert esperas[2] == 0.0
    assert esperas[3] == 50.0


def test_encolhe_fecha_ocioso_antes_de_mexer_no_ocupado():
    # slot 0: 2 caixas; slot 1: 1 caixa.
    # Cliente 1 chega em t=0, servico 500 -> caixa A livre em 500 (fica
    # OCIOSO bem antes do corte em 1800).
    # Cliente 2 chega em t=1000 (ainda slot 0): pega o caixa A (livre desde
    # 500 <= 1000), espera 0, e libera o caixa A em 1000+5000=6000 -> agora
    # o caixa A fica OCUPADO ate 6000. O caixa B, que nunca foi usado, segue
    # livre desde t=0 -> em t=1800 ele e o OCIOSO (0 <= 1800).
    # Em t=1800 o pool encolhe de 2 para 1: ha exatamente 1 ocioso (caixa B,
    # livre desde 0) e ele e fechado primeiro — o ocupado (caixa A, livre em
    # 6000) e mantido mesmo terminando muito mais tarde.
    # Cliente 3 chega em t=1800: so resta o caixa A, que libera em 6000.
    # espera = 6000 - 1800 = 4200 (se o codigo (erradamente) fechasse o
    # ocupado e mantivesse o ocioso, a espera seria 0 — valores bem
    # distintos, entao o teste marca claramente qual caixa sobreviveu).
    chegadas = [0, 1000, 1800]
    servicos = [500, 5000, 100]
    curva = {0: 2, 1: 1}
    esperas = sim.simular(chegadas, servicos, curva)
    assert esperas[0] == 0.0
    assert esperas[1] == 0.0
    assert esperas[2] == 4200.0


def test_simulador_reproduz_erlang_c_em_mmc():
    """ACEITACAO: M/M/c simulado tem que bater com a formula fechada."""
    rng = random.Random(20260717)
    ts = 110.0          # servico medio
    c = 4               # caixas
    a = 2.8             # carga em Erlangs -> lambda = a/ts
    lam = a / ts
    n = 200000

    t, chegadas, servicos = 0.0, [], []
    for _ in range(n):
        t += rng.expovariate(lam)
        chegadas.append(t)
        servicos.append(rng.expovariate(1.0 / ts))

    n_slots = int(t // 1800) + 2
    esperas = sim.simular(chegadas, servicos, {s: c for s in range(n_slots)})

    # descarta o transiente inicial (fila comeca vazia)
    amostra = [w for w in esperas[1000:] if w is not None]
    for alvo in (0.0, 60.0, 180.0):
        medido = sum(1 for w in amostra if w > alvo) / len(amostra)
        analitico = e.prob_espera_maior(c, a, alvo, ts)
        # Referencia (conferida na mao ao escrever o plano): com c=4, a=2.8,
        # ts=110 -> Erlang-C P(W>0) = 0.4286 e P(W>180) = 0.0601.
        # Tolerancia 0.015 = erro de Monte Carlo (esperas em fila sao
        # autocorrelacionadas, entao a amostra efetiva e menor que 200 mil).
        # NAO e folga para simulador errado: um bug de verdade erra MUITO mais
        # que 1,5 ponto. Se falhar, o defeito e no simulador — nao afrouxe isto.
        assert abs(medido - analitico) < 0.015, (
            "P(W>%.0f): simulado %.4f vs Erlang-C %.4f" % (alvo, medido, analitico))


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
