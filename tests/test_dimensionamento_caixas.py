# -*- coding: utf-8 -*-
"""Helpers puros extraidos do CLI dimensionamento_caixas.py: o gate de
divergencia (dias_divergentes/deve_abortar), a construcao chegadas+servicos
(chegadas_servicos) e a rotulagem de faixas-piso por dia da semana
(slots_piso_do_dow). Nenhum toca banco/arquivo -- por isso da pra testar aqui,
sem o PC-ponte (unica maquina que alcanca o ERP)."""
import os
import sys
from datetime import date, datetime, time, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import dimensionamento_caixas as dc  # noqa: E402


# --------------------------------------------------------------------------
# dias_divergentes
# --------------------------------------------------------------------------

def test_dias_divergentes_dia_batendo_nao_e_flagado():
    consolidado = {date(2026, 7, 10): 908}
    nao_cancelados = {date(2026, 7, 10): 908}
    assert dc.dias_divergentes(nao_cancelados, consolidado) == set()


def test_dias_divergentes_contagem_diferente_e_flagada():
    consolidado = {date(2026, 7, 10): 908, date(2026, 7, 11): 946}
    nao_cancelados = {date(2026, 7, 10): 900, date(2026, 7, 11): 946}  # 10/07 nao bate
    assert dc.dias_divergentes(nao_cancelados, consolidado) == {date(2026, 7, 10)}


def test_dias_divergentes_dia_ausente_na_extracao_e_flagado_com_zero():
    # Dia todo-cancelado (ou totalmente perdido na extracao): o consolidado
    # oficial tem 555 cupons, mas nao_cancelados nao tem NENHUMA entrada pra
    # esse dia (esperado 555 x obtido 0). Uma comparacao que so olhasse as
    # chaves de nao_cancelados deixaria isso passar batido -- exatamente o
    # edge case que o Finding 1 pede pra fechar.
    consolidado = {date(2026, 7, 13): 555}
    nao_cancelados = {}
    assert dc.dias_divergentes(nao_cancelados, consolidado) == {date(2026, 7, 13)}


def test_dias_divergentes_so_olha_dias_do_consolidado():
    # Dia extra em nao_cancelados que nao esta no consolidado (ex.: fora da
    # janela de {desde} do consolidado) nao entra na comparacao -- so dias
    # PRESENTES em consolidado sao percorridos.
    consolidado = {date(2026, 7, 10): 908}
    nao_cancelados = {date(2026, 7, 10): 908, date(2026, 7, 9): 12345}
    assert dc.dias_divergentes(nao_cancelados, consolidado) == set()


# --------------------------------------------------------------------------
# deve_abortar
# --------------------------------------------------------------------------

def test_deve_abortar_abaixo_do_limiar_nao_aborta():
    # 1/120 = 0.83% < 5%: 1 dia estranho num universo de 120 nao trava a analise.
    assert dc.deve_abortar(1, 120, limiar=0.05) is False


def test_deve_abortar_acima_do_limiar_aborta():
    # 10/120 = 8.3% > 5%: divergencia generalizada, aborta.
    assert dc.deve_abortar(10, 120, limiar=0.05) is True


def test_deve_abortar_exatamente_no_limiar_nao_aborta():
    # 6/120 = 0.05 = o limiar exatamente. Comparacao e estrita (>), entao nao aborta.
    assert dc.deve_abortar(6, 120, limiar=0.05) is False


def test_deve_abortar_zero_comparados_nao_aborta_nem_divide_por_zero():
    assert dc.deve_abortar(0, 0, limiar=0.05) is False


# --------------------------------------------------------------------------
# chegadas_servicos
# --------------------------------------------------------------------------

BASE = datetime(2026, 7, 16, 8, 0, 0)  # 08:00:00 = 28800s desde a meia-noite


def _cupom(offset_ini, dur, pdv=1):
    return {"pdv": pdv, "inicio": BASE + timedelta(seconds=offset_ini),
            "fim": BASE + timedelta(seconds=offset_ini + dur)}


def test_chegadas_servicos_ordena_por_inicio():
    # Entrada fora de ordem: o cupom de offset 200 vem ANTES do de offset 0 na lista.
    lista = [_cupom(200, 50), _cupom(0, 100)]
    chegadas, servicos = dc.chegadas_servicos(lista, handover=10.0)
    # 08:00:00 -> 28800s, 08:03:20 -> 29000s: saida ascendente, nao a ordem de entrada.
    assert chegadas == [28800, 29000]
    # servicos acompanham a MESMA ordem (por chegada), nao a ordem de entrada:
    # offset 0 (dur 100) primeiro -> 100+10=110; offset 200 (dur 50) depois -> 50+10=60.
    assert servicos == [110.0, 60.0]


def test_chegadas_servicos_soma_handover_a_duracao():
    lista = [_cupom(0, 100)]
    chegadas, servicos = dc.chegadas_servicos(lista, handover=15.0)
    assert chegadas == [28800]
    assert servicos == [115.0]  # (fim - inicio) = 100s + handover 15s


def test_chegadas_servicos_nao_muta_a_lista_original():
    # Pura: usa sorted(), nao .sort() -- a lista do chamador (por_dia[...]) fica intacta.
    original = [_cupom(200, 50), _cupom(0, 100)]
    ordem_original = [c["inicio"] for c in original]
    dc.chegadas_servicos(original, handover=0.0)
    assert [c["inicio"] for c in original] == ordem_original


# --------------------------------------------------------------------------
# slots_piso_do_dow
# --------------------------------------------------------------------------

def test_slots_piso_do_dow_marca_slot_com_dia_contribuinte_saturado():
    # d1 e d2 sao os 2 dias que compoem a curva desse dia-da-semana. d1 bateu
    # piso (saturado ou no teto) no slot 20; d2 nao teve piso nenhum. Basta
    # UM dia contribuinte para o slot ser marcado pra esse dow inteiro.
    d1, d2 = date(2026, 7, 6), date(2026, 7, 13)  # 2 segundas-feiras
    dias_do_dow = {d1, d2}
    floor_total = {(d1, 20)}
    assert dc.slots_piso_do_dow(dias_do_dow, floor_total) == {20}


def test_slots_piso_do_dow_ignora_piso_de_dia_de_outro_dow():
    d1 = date(2026, 7, 6)      # segunda: faz parte da curva deste dow
    outro = date(2026, 7, 7)   # terca: NAO faz parte (outro dia-da-semana)
    dias_do_dow = {d1}
    floor_total = {(outro, 20)}
    assert dc.slots_piso_do_dow(dias_do_dow, floor_total) == set()


def test_slots_piso_do_dow_sem_nenhum_piso_devolve_vazio():
    dias_do_dow = {date(2026, 7, 6), date(2026, 7, 13)}
    assert dc.slots_piso_do_dow(dias_do_dow, set()) == set()


# --------------------------------------------------------------------------
# validar_desde (Fix 3 do code review: --desde malformado falha cedo, com
# mensagem clara, antes de virar SQL via .format()).
# --------------------------------------------------------------------------

def test_validar_desde_aceita_yyyy_mm_dd():
    # Nao levanta -- formato correto, mesmo default usado pelo CLI.
    dc.validar_desde("2026-01-22")


def test_validar_desde_rejeita_formato_dd_mm_yyyy():
    with pytest.raises(SystemExit):
        dc.validar_desde("22-01-2026")


def test_validar_desde_rejeita_lixo_nao_data():
    # O caso que fecharia a porta teorica de injecao: uma string que nao e
    # data nenhuma (nem em outro formato) nunca chega a virar SQL.
    with pytest.raises(SystemExit):
        dc.validar_desde("1=1; DROP TABLE tbCupom")


# --------------------------------------------------------------------------
# checar_tipos_cupom (Fix 2 do code review: falha cedo se o driver ODBC
# devolver inicio/fim como algo que nao seja datetime.datetime).
# --------------------------------------------------------------------------

def test_checar_tipos_cupom_aceita_datetime_datetime():
    # Nao levanta -- inicio e fim sao datetime.datetime, como o resto do
    # modulo (chegadas_servicos, dim_saturacao, dim_servico) exige.
    cupom = _cupom(0, 100)
    dc.checar_tipos_cupom(cupom)


def test_checar_tipos_cupom_rejeita_inicio_string():
    # Simula o driver ODBC devolvendo HoraInicio como str em vez de
    # datetime.datetime -- exatamente o cenario que o Fix 2 cobre.
    cupom = {"pdv": 1, "inicio": "2026-07-16 08:00:00", "fim": BASE}
    with pytest.raises(SystemExit):
        dc.checar_tipos_cupom(cupom)


def test_checar_tipos_cupom_rejeita_fim_time():
    # datetime.time NAO e datetime.datetime (sem .date(), sem subtracao
    # direta com outro datetime) -- outro jeito plausivel do driver falhar.
    cupom = {"pdv": 1, "inicio": BASE, "fim": time(8, 5, 0)}
    with pytest.raises(SystemExit):
        dc.checar_tipos_cupom(cupom)


# --------------------------------------------------------------------------
# construir_parser (Fix 1 do code review: default de --c-max tem que ser o
# teto FISICO real da loja -- PDV 1-9 -- e nao um numero maior que nunca
# flagaria piso/floor honestamente).
# --------------------------------------------------------------------------

def test_c_max_default_e_9_pdv_1_a_9():
    args = dc.construir_parser().parse_args([])
    assert args.c_max == 9


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
