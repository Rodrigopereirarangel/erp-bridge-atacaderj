# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import relatorio  # noqa: E402


def _linha(codigo, nome, rua=None, rotulo="", minimo="1 cx", marca=""):
    return {"codigo": codigo, "nome": nome, "curva": "A", "rua": rua,
            "rua_rotulo": rotulo, "minimo": minimo, "marca": marca}


def test_preparar_cotacao_primeiro_sem_fornecedor_ultimo():
    dados = {"GARCIA": [_linha(1, "X")], "SEM FORNECEDOR": [_linha(2, "Y")],
             "COTACAO": [_linha(3, "Z")], "AMBEV": [_linha(4, "W")]}
    nomes = [f["nome"] for f in relatorio.preparar(dados)]
    assert nomes == ["COTACAO", "AMBEV", "GARCIA", "SEM FORNECEDOR"]


def test_preparar_ordena_produtos_por_rua_depois_nome():
    dados = {"GARCIA": [_linha(1, "BBB", rua=None),
                        _linha(2, "AAA", rua=13, rotulo="A13 cons1"),
                        _linha(3, "CCC", rua=1, rotulo="A1 bisc1"),
                        _linha(4, "AAA", rua=13, rotulo="A13 cons1")]}
    prods = relatorio.preparar(dados)[0]["produtos"]
    assert [p["codigo"] for p in prods] == [3, 2, 4, 1]  # rua 1, rua 13 (AAA, AAA), sem rua


def test_montar_html_autocontido_com_busca_e_legenda():
    dados = {"COTACAO": [_linha(15450, "OLEO SOJA SOYA 900ML", rua=13,
                                rotulo="A13 cons1", minimo="7 cx")]}
    html = relatorio.montar(relatorio.preparar(dados), "22/07/2026 06:00")
    assert "OLEO SOJA SOYA 900ML" in html
    assert "A13 cons1" in html
    assert "7 cx" in html
    assert "22/07/2026 06:00" in html
    assert 'id="busca"' in html
    assert "calculado com ruptura" in html      # legenda do *
    assert "http://" not in html and "https://" not in html  # sem dependencia externa


def test_montar_escapa_html_no_nome():
    dados = {"A<B": [_linha(1, "PRODUTO <script> & CIA")]}
    html = relatorio.montar(relatorio.preparar(dados), "x")
    # todo '<' do JSON embutido vira < -> nenhuma tag pode "vazar"
    assert "<script> & CIA" not in html
    assert "\\u003cscript> & CIA" in html


def test_montar_novidades_do_dono_22_07():
    dados = {"COTACAO": [_linha(15450, "OLEO SOJA SOYA 900ML", rua=13,
                                rotulo="A13 cons1", minimo="7 cx")]}
    html = relatorio.montar(relatorio.preparar(dados), "x")
    # busca por produto ao lado da busca de fornecedor
    assert 'id="buscaProd"' in html
    # botao salvar PDF (impressao nativa) nas duas vistas
    assert 'id="pdf"' in html and 'id="pdfRes"' in html
    assert "window.print" in html
    # coluna cx mae presente; coluna curva NAO existe mais na tela
    assert "cx m&atilde;e" in html
    assert '"cx": 1' in html          # _linha nao tem cx_mae -> default 1
    assert '"curva"' not in html      # blob sem curva
    # identidade do painel (tema escuro operacional)
    assert "--bg:#0b0e13" in html


def test_quatro_colunas_de_data_para_preencher_a_mao():
    dados = {"COTACAO": [_linha(1, "X")]}
    html = relatorio.montar(relatorio.preparar(dados), "x")
    assert html.count("data __/__/__") == 4          # 4 cabecalhos iguais
    assert "'<td class=\"mao\"><span class=\"lin\"></span></td>'.repeat(4)" \
        in html                                      # traco em toda linha
