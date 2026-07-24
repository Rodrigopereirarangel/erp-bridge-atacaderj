# -*- coding: utf-8 -*-
"""Integracao fim-a-fim com CSVs sinteticos (formato exato do bridge)."""
import json
import os
import subprocess
import sys
from datetime import date, timedelta

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GERAR = os.path.join(RAIZ, "src", "gerar.py")


def _montar_insumos(tmp_path):
    hoje = date(2026, 7, 20)
    d = lambda n: (hoje - timedelta(days=n)).isoformat()  # noqa: E731
    (tmp_path / "catalogo.csv").write_text(
        "codigo;descricao;embalagem;curva;peso;ean_cx;ean_un;corredor_erp;endereco;ativo\n"
        "15450;OLEO SOJA SOYA 900ML;20;A;0;17891107101628;7891107101621;CORREDOR 60;ATACADO 2;1\n"
        "222;QUEIJO MEIA CURA;;B;1;;;LATICINIO;VAREJO;1\n"
        "333;PRODUTO INATIVO;10;C;0;;;CORREDOR 20;ATACADO 1;0\n", encoding="utf-8")
    # 15450 vende 2/dia nos ultimos 180 dias -> mediana 90 un -> 5 cx
    vendas = "codigo;descricao;data;qtd_vendida\n"
    for n in range(180):
        vendas += f"15450;OLEO;{d(n)};2\n"
    vendas += f"222;QUEIJO;{d(1)};1.5\n"
    (tmp_path / "vendas.csv").write_text(vendas, encoding="utf-8")
    (tmp_path / "entradas.csv").write_text(
        "codigo;data;fornecedor;qtd\n"
        f"222;{d(5)};QUEIJOS DONA ROSA;30\n", encoding="utf-8")
    (tmp_path / "negociacao.csv").write_text(
        "codigo;fornecedor;dt_alteracao\n"
        "15450;COTACAO;\n"
        "15450;WAL MART;2026-05-01\n", encoding="utf-8")
    (tmp_path / "ruas.json").write_text(
        json.dumps({"15450": {"rua": 13, "quando": "x", "origem": "y"},
                    "222": 25}), encoding="utf-8")
    cfg = {"entrada": {
        "catalogo_csv": str(tmp_path / "catalogo.csv"),
        "vendas_csv": str(tmp_path / "vendas.csv"),
        "entradas_csv": str(tmp_path / "entradas.csv"),
        "negociacao_csv": str(tmp_path / "negociacao.csv"),
        "ruas_estado_json": str(tmp_path / "ruas.json")},
        "saida_html": str(tmp_path / "out" / "listagem.html")}
    caminho = tmp_path / "config.json"
    caminho.write_text(json.dumps(cfg), encoding="utf-8")
    return caminho, cfg


def _rodar(config):
    return subprocess.run([sys.executable, GERAR, "--config", str(config)],
                          capture_output=True, text=True)


def test_gera_html_com_tudo(tmp_path):
    config, cfg = _montar_insumos(tmp_path)
    r = _rodar(config)
    assert r.returncode == 0, r.stderr
    html = open(cfg["saida_html"], encoding="utf-8").read()
    assert "OLEO SOJA SOYA 900ML" in html
    assert "5 cx" in html            # 90 un / cx de 20 -> 4,5 -> teto 5
    assert "A13 cons1" in html       # rua como dict
    assert "A25 TERREO" in html      # rua como int direto
    assert "QUEIJOS DONA ROSA" in html
    assert "PRODUTO INATIVO" not in html
    assert "kg" in html              # 222 e de balanca


def test_falha_de_insumo_preserva_html_anterior(tmp_path):
    config, cfg = _montar_insumos(tmp_path)
    assert _rodar(config).returncode == 0
    antes = open(cfg["saida_html"], encoding="utf-8").read()
    os.remove(cfg["entrada"]["vendas_csv"])       # quebra um insumo
    r = _rodar(config)
    assert r.returncode == 1
    assert open(cfg["saida_html"], encoding="utf-8").read() == antes


def test_estado_de_ruas_ausente_nao_derruba(tmp_path):
    config, cfg = _montar_insumos(tmp_path)
    os.remove(cfg["entrada"]["ruas_estado_json"])
    r = _rodar(config)
    assert r.returncode == 0          # sem ruas = coluna corredor vazia
    assert "AVISO" in r.stderr
    assert "OLEO SOJA SOYA 900ML" in open(cfg["saida_html"],
                                          encoding="utf-8").read()


def test_estado_de_ruas_corrompido_nao_derruba(tmp_path):
    config, cfg = _montar_insumos(tmp_path)
    with open(cfg["entrada"]["ruas_estado_json"], "w", encoding="utf-8") as f:
        f.write("{ nao e json")
    r = _rodar(config)
    assert r.returncode == 0          # opcional ilegivel = opcional ausente
    assert "AVISO" in r.stderr
    html = open(cfg["saida_html"], encoding="utf-8").read()
    assert "OLEO SOJA SOYA 900ML" in html


def test_alerta_de_ruptura_marca_item_do_corte(tmp_path):
    # rodada do detector: 15450 passa no corte do painel (prob>0.75,
    # parado>1, sem entrega recente); 222 fica fora (prob baixa)
    config, cfg = _montar_insumos(tmp_path)
    rounds = tmp_path / "rounds"
    rounds.mkdir()
    (rounds / "2026-07-19.json").write_text(json.dumps({"items": []}),
                                            encoding="utf-8")
    (rounds / "2026-07-20.json").write_text(json.dumps({"items": [
        {"codigo": "15450", "probabilidade": 0.9, "diasParado": 5},
        {"codigo": "222", "probabilidade": 0.5, "diasParado": 9},
    ]}), encoding="utf-8")
    cfg["entrada"]["ruptura_rounds_dir"] = str(rounds)
    config.write_text(json.dumps(cfg), encoding="utf-8")
    r = _rodar(config)
    assert r.returncode == 0, r.stderr
    assert "1 com alerta de ruptura" in r.stdout
    html = open(cfg["saida_html"], encoding="utf-8").read()
    # 15450 marcado, 222 nao — blob JSON carrega o flag "rp"
    assert '"codigo": 15450' in html.replace('"codigo":15450', '"codigo": 15450')
    assert '"rp": 1' in html or '"rp":1' in html


def test_guardrail_entrega_recente_com_cobertura_nao_alerta(tmp_path):
    # entrega ha 3 dias com cobertura sobrando -> guardrail do painel corta
    config, cfg = _montar_insumos(tmp_path)
    rounds = tmp_path / "rounds"
    rounds.mkdir()
    (rounds / "r.json").write_text(json.dumps({"items": [
        {"codigo": "15450", "probabilidade": 0.9, "diasParado": 5,
         "receipt": {"date": date.today().isoformat()},
         "coverageRemaining": 4.0},
    ]}), encoding="utf-8")
    cfg["entrada"]["ruptura_rounds_dir"] = str(rounds)
    config.write_text(json.dumps(cfg), encoding="utf-8")
    r = _rodar(config)
    assert r.returncode == 0, r.stderr
    assert "0 com alerta de ruptura" in r.stdout


def test_rounds_dir_configurado_mas_ausente_avisa_e_segue(tmp_path):
    config, cfg = _montar_insumos(tmp_path)
    cfg["entrada"]["ruptura_rounds_dir"] = str(tmp_path / "nao-existe")
    config.write_text(json.dumps(cfg), encoding="utf-8")
    r = _rodar(config)
    assert r.returncode == 0
    assert "AVISO" in r.stderr and "detector" in r.stderr


def test_mediana_zero_vira_ruptura_cronica_sem_numero(tmp_path):
    # caso real 22/07 (cervejas C12): 2 vendas isoladas em 180d -> todas as
    # janelas com ruptura e mediana 0 -> "0 un" leria como estoque zero;
    # tem que sair "—" com etiqueta "ruptura crônica"
    config, cfg = _montar_insumos(tmp_path)
    hoje = date(2026, 7, 20)
    d = lambda n: (hoje - timedelta(days=n)).isoformat()  # noqa: E731
    with open(cfg["entrada"]["catalogo_csv"], "a", encoding="utf-8") as f:
        f.write("35886;CERV BUDWEISER LATAO 473ML C12;;E;0;;;CORREDOR 10(FRIA);ATACADO 1;1\n")
    with open(cfg["entrada"]["vendas_csv"], "a", encoding="utf-8") as f:
        f.write(f"35886;CERV;{d(170)};1\n")
        f.write(f"35886;CERV;{d(80)};1\n")
    r = _rodar(config)
    assert r.returncode == 0, r.stderr
    html = open(cfg["saida_html"], encoding="utf-8").read()
    assert "ruptura crônica" in html
    # piso do dono (23/07): nunca abaixo de 1 un/1 cx
    assert '"minimo": "1 un"' in html


def test_piso_de_1_caixa_mae_quando_tem_caixa(tmp_path):
    # produto com caixa de 20 vendendo pouquissimo -> piso = 1 cx (20 un)
    config, cfg = _montar_insumos(tmp_path)
    hoje = date(2026, 7, 20)
    d = lambda n: (hoje - timedelta(days=n)).isoformat()  # noqa: E731
    with open(cfg["entrada"]["catalogo_csv"], "a", encoding="utf-8") as f:
        f.write("555;REFRI RARO 2L;20;C;0;;;CORREDOR 30;ATACADO 2;1\n")
    with open(cfg["entrada"]["vendas_csv"], "a", encoding="utf-8") as f:
        f.write(f"555;REFRI;{d(100)};1\n")
        f.write(f"555;REFRI;{d(50)};1\n")
    r = _rodar(config)
    assert r.returncode == 0, r.stderr
    html = open(cfg["saida_html"], encoding="utf-8").read()
    assert '"codigo": 555' in html
    assert html.count('"minimo": "1 cx"') >= 1


def test_overrides_embutidos_no_html(tmp_path):
    config, cfg = _montar_insumos(tmp_path)
    ovr = tmp_path / "ovr.json"
    ovr.write_text(json.dumps({"grupos": {"CAMIL SC": "CAMIL SP"},
                               "itens": {"15450": "GARCIA"}}),
                   encoding="utf-8")
    cfg["entrada"]["overrides_json"] = str(ovr)
    config.write_text(json.dumps(cfg), encoding="utf-8")
    r = _rodar(config)
    assert r.returncode == 0, r.stderr
    html = open(cfg["saida_html"], encoding="utf-8").read()
    assert '"CAMIL SC": "CAMIL SP"' in html      # grupos embutidos
    assert '"15450": "GARCIA"' in html           # itens embutidos
    assert '"ro":' in html                       # ordem de rua p/ o JS


def test_ean_e_corredor_do_sistema_saem_no_html(tmp_path):
    config, cfg = _montar_insumos(tmp_path)
    r = _rodar(config)
    assert r.returncode == 0, r.stderr
    html = open(cfg["saida_html"], encoding="utf-8").read()
    # EAN da caixa-mae manda; "CORREDOR 60" vira "60" (corredor_curto)
    assert '"ean": "17891107101628"' in html and '"et": "CX"' in html
    assert '"cor": "AT 2"' in html      # endereco do sistema manda
    # sem EAN de caixa: cai no da unidade marcado, ou vazio
    assert '"ean": ""' in html            # 222 nao tem EAN nenhum
    assert '"cor": "VAREJO"' in html
