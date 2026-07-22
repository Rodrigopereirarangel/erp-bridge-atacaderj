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
        "codigo;descricao;embalagem;curva;peso;ativo\n"
        "15450;OLEO SOJA SOYA 900ML;20;A;0;1\n"
        "222;QUEIJO MEIA CURA;;B;1;1\n"
        "333;PRODUTO INATIVO;10;C;0;0\n", encoding="utf-8")
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
