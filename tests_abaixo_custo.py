# -*- coding: utf-8 -*-
"""Testes das funcoes puras de src/abaixo_custo.py (sem banco, sem I/O).

Rodavel direto: `python tests_abaixo_custo.py` — asserts diretos, sem pytest;
imprime OK/FALHOU por teste e sai com codigo 1 se algo falhar (padrao do
design doc: docs/superpowers/specs/2026-07-14-abaixo-custo-6h-design.md).
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
import abaixo_custo as ac  # noqa: E402


def _linha(descricao, qtd, venda_un, custo_un, codigo=1):
    """Monta uma linha crua (como viria do SELECT): valor/custo em TOTAIS."""
    return {
        "codigo": codigo,
        "descricao": descricao,
        "qtd": qtd,
        "valor": round(qtd * venda_un, 6),
        "custo": round(qtd * custo_un, 6),
    }


def test_filtro_limites():
    # Regra do dono (14/07, apos a 1a mensagem real): entra APENAS quem vendeu
    # com markup <= -3% (prejuizo de 3% ou mais).
    linhas = [
        _linha("A", 1, 6.51, 10.00),   # -34,9% -> entra
        _linha("B", 1, 9.70, 10.00),   # -3,0%  -> entra (limite exato)
        _linha("C", 1, 9.71, 10.00),   # -2,9%  -> FORA
        _linha("D", 1, 10.00, 10.00),  # 0,0%   -> FORA
        _linha("E", 1, 10.20, 10.00),  # +2,0%  -> FORA
    ]
    itens, sem_custo = ac.filtrar_itens(linhas, -0.03)
    nomes = {i["descricao"] for i in itens}
    assert nomes == {"A", "B"}, f"esperado A,B; veio {nomes}"
    assert sem_custo == 0


def test_custo_zero_vira_sem_custo():
    linhas = [
        _linha("A", 1, 9.50, 10.00),
        {"codigo": 2, "descricao": "SEM_CUSTO_1", "qtd": 5, "valor": 50.0, "custo": 0},
        {"codigo": 3, "descricao": "SEM_CUSTO_2", "qtd": 2, "valor": 20.0, "custo": None},
    ]
    itens, sem_custo = ac.filtrar_itens(linhas, -0.03)
    nomes = {i["descricao"] for i in itens}
    assert nomes == {"A"}
    assert sem_custo == 2


def test_ordenacao_pior_para_melhor():
    linhas = [
        _linha("MENOS_RUIM", 1, 9.65, 10.00),   # -3,5%
        _linha("PIOR", 1, 9.00, 10.00),         # -10,0%
        _linha("MEIO", 1, 9.50, 10.00),         # -5,0%
    ]
    itens, _ = ac.filtrar_itens(linhas, -0.03)
    ordem = [i["descricao"] for i in itens]
    assert ordem == ["PIOR", "MEIO", "MENOS_RUIM"], ordem


def test_titulo_e_linhas_exatas():
    # Exemplo canonico ATUALIZADO para o corte novo (markup <= -3%): 2 itens
    # abaixo do custo, rodape derivado dos proprios numeros do fixture.
    fixture = [
        # (descricao, qtd, venda_un, custo_un)
        ("PAO DE QUEIJO", 12, 6.50, 10.00),   # -35,0%
        ("MINI PIZZA", 30, 9.70, 10.00),      # -3,0% (limite exato)
    ]
    linhas = [_linha(n, q, v, c) for (n, q, v, c) in fixture]
    itens, sem_custo = ac.filtrar_itens(linhas, -0.03)
    msg = ac.montar_mensagem("13/07", itens, sem_custo)
    prejuizo = sum(max(0.0, (c - v) * q) for (_, q, v, c) in fixture)
    rodape_valor = f"{prejuizo:.2f}".replace(".", ",")  # 42,00 + 9,00 = 51,00
    esperado = (
        ">Produtos vendidos abaixo do custo dia 13/07<\n"
        "\n"
        "PAO DE QUEIJO\n"
        "venda 6,50 · custo 10,00 · -35,0%\n"
        "\n"
        "MINI PIZZA\n"
        "venda 9,70 · custo 10,00 · -3,0%\n"
        "\n"
        f"2 itens · prejuízo potencial R$ {rodape_valor}"
    )
    assert msg == esperado, f"\n--- obtido ---\n{msg}\n--- esperado ---\n{esperado}"


def test_zero_itens():
    msg = ac.montar_mensagem("14/07", [], 0)
    assert msg == "✅ nenhum item vendido no/abaixo do custo em 14/07", msg


def test_corte_60_itens():
    linhas = []
    for i in range(65):
        # i=0 -> -3,1% (menos ruim) ... i=64 -> -9,5% (pior); todos <= -3%
        markup = -0.03 - 0.001 * (i + 1)
        venda_un = 10.0 * (1 + markup)
        linhas.append(_linha(f"ITEM {i:02d}", 1, venda_un, 10.00, codigo=i))
    itens, sem_custo = ac.filtrar_itens(linhas, -0.03)
    assert len(itens) == 65
    assert itens[0]["descricao"] == "ITEM 64"   # pior primeiro
    assert itens[-1]["descricao"] == "ITEM 00"  # melhor por ultimo

    msg = ac.montar_mensagem("15/07", itens, sem_custo)
    assert msg.count("ITEM ") == 60, "deveria exibir so os 60 piores"
    assert "… e mais 5 itens" in msg
    # prejuizo = soma de TODOS os 65 (nao so os 60 exibidos):
    # 65*0,30 + 0,01*(1+..+65) = 19,50 + 21,45 = 40,95
    assert msg.strip().endswith("65 itens · prejuízo potencial R$ 40,95"), msg


def test_prejuizo_so_dos_abaixo_do_custo():
    # Com o corte novo todo item listado esta abaixo do custo; o teste vira:
    # prejuizo = soma (custo-venda)*qtd dos listados, e quem tem markup
    # positivo fica FORA da lista e da conta.
    linhas = [
        _linha("ABAIXO_1", 5, 9.50, 10.00),   # -5,0%  -> prejuizo 0,50*5 = 2,50
        _linha("ABAIXO_2", 3, 9.00, 10.00),   # -10,0% -> prejuizo 1,00*3 = 3,00
        _linha("ACIMA", 100, 10.20, 10.00),   # +2,0%  -> FORA (lista e conta)
    ]
    itens, sem_custo = ac.filtrar_itens(linhas, -0.03)
    assert len(itens) == 2
    msg = ac.montar_mensagem("16/07", itens, sem_custo)
    assert "R$ 5,50" in msg, msg


def test_rodape_com_sem_custo():
    linhas = [
        _linha("A", 1, 9.50, 10.00),
        {"codigo": 9, "descricao": "SEM_CUSTO", "qtd": 1, "valor": 10.0, "custo": 0},
    ]
    itens, sem_custo = ac.filtrar_itens(linhas, -0.03)
    msg = ac.montar_mensagem("17/07", itens, sem_custo)
    assert msg.endswith(
        "1 itens · prejuízo potencial R$ 0,50\n"
        "⚠ 1 itens sem custo cadastrado (fora da conta)"
    ), msg


def test_dia_anterior_util_segunda_pula_domingo():
    segunda = date(2024, 1, 1)  # conhecida: 01/01/2024 = segunda-feira
    assert segunda.weekday() == 0
    alvo = ac.dia_anterior_util(segunda)
    assert alvo == date(2023, 12, 30)  # sabado, pula o domingo 12/31
    assert alvo.weekday() == 5


def test_dia_anterior_util_dia_normal():
    quarta = date(2024, 1, 3)
    assert quarta.weekday() == 2
    alvo = ac.dia_anterior_util(quarta)
    assert alvo == date(2024, 1, 2)  # terca, sem pulo


TESTES = [
    test_filtro_limites,
    test_custo_zero_vira_sem_custo,
    test_ordenacao_pior_para_melhor,
    test_titulo_e_linhas_exatas,
    test_zero_itens,
    test_corte_60_itens,
    test_prejuizo_so_dos_abaixo_do_custo,
    test_rodape_com_sem_custo,
    test_dia_anterior_util_segunda_pula_domingo,
    test_dia_anterior_util_dia_normal,
]


def main():
    falhas = 0
    for teste in TESTES:
        nome = teste.__name__
        try:
            teste()
            print(f"OK    {nome}")
        except AssertionError as e:
            falhas += 1
            print(f"FALHOU {nome}: {e}")
        except Exception as e:  # erro inesperado tambem conta como falha
            falhas += 1
            print(f"ERRO   {nome}: {type(e).__name__}: {e}")

    total = len(TESTES)
    print(f"\n{total - falhas}/{total} passaram")
    if falhas:
        sys.exit(1)


if __name__ == "__main__":
    main()
