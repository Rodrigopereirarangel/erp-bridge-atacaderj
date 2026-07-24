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
    # 4 na tabela da tela + 4 no gerador da impressao multipla
    assert html.count("data __/__/__") == 8
    # celula totalmente VAZIA, sem traco (dono, 22/07)
    assert "'<td class=\"mao\"></td>'.repeat(4)" in html
    assert 'class="lin"' not in html


def test_impressao_sem_emoji_nem_avisos():
    dados = {"COTACAO": [_linha(1, "X")]}
    html = relatorio.montar(relatorio.preparar(dados), "x")
    # emoji de ruptura ganha classe propria e o print esconde junto c/ marcas
    assert 'class="rupt"' in html
    assert ".rupt, .marca { display:none !important }" in html
    # cabecalho de impressao sem legenda de avisos
    assert html.count("dados de x &middot; AtacadeRJ</div>") >= 1


def test_ui_de_agrupamento_e_overrides():
    dados = {"COTACAO": [_linha(1, "X")]}
    ovr = {"grupos": {"COCA COLA": "COCA COLA RJ ANDINA"}, "itens": {}}
    html = relatorio.montar(relatorio.preparar(dados), "x", ovr)
    # overrides embutidos como fallback + endpoint de persistencia
    assert '"COCA COLA": "COCA COLA RJ ANDINA"' in html
    assert html.count("/listagem/overrides") >= 2      # GET no boot + POST
    # controles: flags de agrupar, definir mae, mover itens, dialogo com
    # caixa de PESQUISA, barra fixa (UX v2 do dono, 23/07)
    for eid in ("btnMae", "btnMover", "dlg", "barra", "dlgBusca", "dlgLista"):
        assert 'id="%s"' % eid in html
    assert "fl.className='flag'" in html     # flag sempre visivel na lista
    # o JS resolve corrente filho->mae e reordena por rua (campo ro)
    assert "function resolve(" in html
    assert "a.ro-b.ro" in html


def test_ordenacao_arrasto_todos_e_contraste():
    dados = {"COTACAO": [_linha(1, "X")]}
    html = relatorio.montar(relatorio.preparar(dados), "x")
    # cabecalhos ordenaveis nas DUAS tabelas (asc/desc/padrao)
    assert html.count('data-k="mv"') == 2
    assert html.count('data-k="ro"') == 2
    assert 'data-k="forn"' in html           # so na busca de produto
    assert "ligaOrdenacao('cabDet'" in html
    assert "ligaOrdenacao('cabRes'" in html
    # arrastar para marcar + selecionar todos/nenhum
    assert "onmousedown" in html and "onmouseenter" in html
    assert "bTodos" in html and "bNenhum" in html
    assert 'id="btnTodosForn"' in html    # marcar todos os fornecedores visiveis
    # contraste: selecao de texto legivel
    assert "::selection" in html


def test_coluna_ean_linhas_e_impressao_multipla():
    dados = {"COTACAO": [_linha(1, "X")], "GARCIA": [_linha(2, "Y")]}
    html = relatorio.montar(relatorio.preparar(dados), "x")
    # coluna EAN nas duas tabelas + ordenavel
    assert html.count('data-k="ean"') == 2
    # linhas verticais separando colunas (tela e papel)
    assert "th, td { border-right:1px solid var(--linha) }" in html
    assert "th, td { border-right:1px solid #bbb }" in html
    # imprimir varios fornecedores num PDF so, sem quebra de folha entre eles
    assert "function imprimirVarios(" in html
    assert 'id="multi"' in html
    assert "body.multi #multi { display:block !important }" in html
    assert "page-break-after:avoid" in html      # faixa do grupo nao se separa
    # corredor do sistema + rua do deposito em cinza
    assert "function celCorredor(" in html


def test_arrastar_marca_varios_fornecedores():
    dados = {"COTACAO": [_linha(1, "X")], "GARCIA": [_linha(2, "Y")]}
    html = relatorio.montar(relatorio.preparar(dados), "x")
    # arrasto na lista de fornecedores (mesma mecanica dos itens)
    assert "window._dragF=true" in html
    assert "c.onmouseenter=function(){ if(window._dragF)" in html
    assert "function marcaForn(" in html
    # mouseup solta os dois arrastos (itens e fornecedores)
    assert "window._drag=false; window._dragF=false;" in html


def test_impressao_compacta_economiza_papel():
    dados = {"COTACAO": [_linha(1, "X")], "GARCIA": [_linha(2, "Y")]}
    html = relatorio.montar(relatorio.preparar(dados), "x")
    # margens curtas + fonte compacta + larguras fixas (dono, 24/07)
    assert "@page { size:A4 portrait; margin:6mm 5mm 7mm }" in html
    assert "font:var(--fp,9.4pt)/1.18" in html
    assert "table-layout:fixed" in html
    assert html.count('col class="c-mao"') >= 8      # colgroups das 2 tabelas
    # multi-fornecedor = UMA tabela com faixa de grupo (sem thead repetido)
    assert "tr.grupo" in html
    assert "function linhasImpressao(" in html
    assert "thead { display:table-header-group }" in html


def test_ean_nao_vaza_e_tem_selo():
    dados = {"COTACAO": [_linha(1, "X")]}
    html = relatorio.montar(relatorio.preparar(dados), "x")
    assert "function celEan(" in html
    assert 'class="eant"' in html                 # selo CX/UN
    # overflow:hidden impede o EAN de trepar na coluna vizinha no papel
    assert "overflow:hidden }" in html
    assert "col.c-ean { width:29mm }" in html


def test_fonte_confortavel_com_teto_de_100_folhas():
    dados = {"COTACAO": [_linha(1, "X")]}
    html = relatorio.montar(relatorio.preparar(dados), "x")
    # padrao confortavel + variavel que o JS ajusta pelo volume
    assert "font:var(--fp,9.4pt)/1.18" in html
    assert "var TETO_FOLHAS=100, FONTE_MAX=14, FONTE_MIN=8.2;" in html
    assert "function ajustaFonte(" in html
    assert "pt>FONTE_MIN" in html               # piso de legibilidade
    assert "function folhasMedidas(" in html     # mede a folha real
    # os 3 caminhos de impressao chamam o ajuste antes de imprimir
    assert "ajustaFontePorMedida(alvo)" in html  # mede antes de imprimir


def test_fonte_medida_de_verdade_e_fornecedor_proporcional():
    dados = {"COTACAO": [_linha(1, "X")]}
    html = relatorio.montar(relatorio.preparar(dados), "x")
    # regua de medicao fora da tela + busca binaria pela maior fonte
    assert ".medindo {" in html
    assert "function ajustaFontePorMedida(" in html
    assert "el.scrollHeight/ALT_FOLHA_PX" in html
    # nome do fornecedor cresce junto (proporcional ao corpo)
    assert html.count("calc(var(--fp,9.4pt) * 1.12)") == 2   # regua + papel
    # o PDF de um fornecedor usa o mesmo caminho medido
    assert "if(abertoNome)imprimirVarios([abertoNome])" in html
