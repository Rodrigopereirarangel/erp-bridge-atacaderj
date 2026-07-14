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
    linhas = [
        _linha("A", 1, 9.50, 10.00),   # -5,0%  -> entra
        _linha("B", 1, 10.20, 10.00),  # +2,0%  -> entra
        _linha("C", 1, 10.30, 10.00),  # +3,0%  -> entra (limite)
        _linha("D", 1, 10.31, 10.00),  # +3,1%  -> fora
    ]
    itens, sem_custo = ac.filtrar_itens(linhas, 0.03)
    nomes = {i["descricao"] for i in itens}
    assert nomes == {"A", "B", "C"}, f"esperado A,B,C; veio {nomes}"
    assert sem_custo == 0


def test_custo_zero_vira_sem_custo():
    linhas = [
        _linha("A", 1, 9.50, 10.00),
        {"codigo": 2, "descricao": "SEM_CUSTO_1", "qtd": 5, "valor": 50.0, "custo": 0},
        {"codigo": 3, "descricao": "SEM_CUSTO_2", "qtd": 2, "valor": 20.0, "custo": None},
    ]
    itens, sem_custo = ac.filtrar_itens(linhas, 0.03)
    nomes = {i["descricao"] for i in itens}
    assert nomes == {"A"}
    assert sem_custo == 2


def test_ordenacao_pior_para_melhor():
    linhas = [
        _linha("MENOS_RUIM", 1, 9.90, 10.00),   # -1,0%
        _linha("PIOR", 1, 9.00, 10.00),         # -10,0%
        _linha("MEIO", 1, 9.50, 10.00),         # -5,0%
    ]
    itens, _ = ac.filtrar_itens(linhas, 0.03)
    ordem = [i["descricao"] for i in itens]
    assert ordem == ["PIOR", "MEIO", "MENOS_RUIM"], ordem


def test_titulo_e_linhas_exatas():
    # Reproduz o exemplo CANONICO do design doc ao pe da letra.
    linhas = [
        _linha("QJ MUSSARELA CRIOULO", 274.8, 9.50, 10.00),
        _linha("OLEO SOJA SOYA 900ML", 30, 10.20, 10.00),
    ]
    itens, sem_custo = ac.filtrar_itens(linhas, 0.03)
    msg = ac.montar_mensagem("13/07", itens, sem_custo)
    esperado = (
        ">Produtos vendidos abaixo do custo dia 13/07<\n"
        "\n"
        "QJ MUSSARELA CRIOULO\n"
        "venda 9,50 · custo 10,00 · -5,0%\n"
        "\n"
        "OLEO SOJA SOYA 900ML\n"
        "venda 10,20 · custo 10,00 · +2,0%\n"
        "\n"
        "2 itens · prejuízo potencial R$ 137,40"
    )
    assert msg == esperado, f"\n--- obtido ---\n{msg}\n--- esperado ---\n{esperado}"


def test_zero_itens():
    msg = ac.montar_mensagem("14/07", [], 0)
    assert msg == "✅ nenhum item vendido no/abaixo do custo em 14/07", msg


def test_corte_60_itens():
    linhas = []
    for i in range(65):
        markup = -0.001 * (i + 1)  # i=0 -> -0,1% (menos ruim) ... i=64 -> -6,5% (pior)
        venda_un = 10.0 * (1 + markup)
        linhas.append(_linha(f"ITEM {i:02d}", 1, venda_un, 10.00, codigo=i))
    itens, sem_custo = ac.filtrar_itens(linhas, 0.03)
    assert len(itens) == 65
    assert itens[0]["descricao"] == "ITEM 64"   # pior primeiro
    assert itens[-1]["descricao"] == "ITEM 00"  # melhor por ultimo

    msg = ac.montar_mensagem("15/07", itens, sem_custo)
    assert msg.count("ITEM ") == 60, "deveria exibir so os 60 piores"
    assert "… e mais 5 itens" in msg
    # prejuizo = soma de TODOS os 65 (nao so os 60 exibidos): 0,01*(1+..+65) = 21,45
    assert msg.strip().endswith("65 itens · prejuízo potencial R$ 21,45"), msg


def test_prejuizo_so_dos_abaixo_do_custo():
    linhas = [
        _linha("ACIMA_1", 5, 10.10, 10.00),   # +1,0% -> entra, sem prejuizo
        _linha("ACIMA_2", 3, 10.30, 10.00),   # +3,0% -> entra (limite), sem prejuizo
    ]
    itens, sem_custo = ac.filtrar_itens(linhas, 0.03)
    assert len(itens) == 2
    msg = ac.montar_mensagem("16/07", itens, sem_custo)
    assert "R$ 0,00" in msg, msg


def test_rodape_com_sem_custo():
    linhas = [
        _linha("A", 1, 9.50, 10.00),
        {"codigo": 9, "descricao": "SEM_CUSTO", "qtd": 1, "valor": 10.0, "custo": 0},
    ]
    itens, sem_custo = ac.filtrar_itens(linhas, 0.03)
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
