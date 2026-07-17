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
