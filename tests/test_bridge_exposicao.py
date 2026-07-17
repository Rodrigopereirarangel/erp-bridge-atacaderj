# -*- coding: utf-8 -*-
"""--only exposicao ponta a ponta no modo demo.

Este teste existe por causa do incidente de 11/07/2026: coletar() devolve
uma tupla posicional que escrever() desempacota; quem acrescenta um
elemento e esquece um call site quebra o bridge silenciosamente, e a
tarefa agendada falha todo dia sem ninguem ver."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import bridge  # noqa: E402


def _cfg_demo(destino):
    cfg = json.load(open(os.path.join(RAIZ, "config.example.json"), encoding="utf-8"))
    cfg["saida"]["exposicao_dir"] = destino
    return cfg


def test_only_exposicao_escreve_os_dois_csvs():
    with tempfile.TemporaryDirectory() as d:
        cfg = _cfg_demo(d)
        dados = bridge.coletar(cfg, True, "exposicao")
        rel = bridge.escrever(cfg, *dados, alvo="exposicao")
        assert os.path.exists(os.path.join(d, "vendas_canal.csv"))
        assert os.path.exists(os.path.join(d, "catalogo_exposicao.csv"))
        assert any("vendas_canal.csv" in r for r in rel)
        assert any("catalogo_exposicao.csv" in r for r in rel)


def test_only_exposicao_nao_paga_as_outras_queries():
    # a janela e de 400 dias: nao pode rodar junto com catalogo/movimentos
    with tempfile.TemporaryDirectory() as d:
        cfg = _cfg_demo(d)
        cat, ven, ent, ped, pv, vm, hc, vc = bridge.coletar(cfg, True, "exposicao")
        assert vc, "vendas_canal deveria vir preenchido"
        assert ven == [] and ent == [] and ped == [] and pv == [] and vm == [] and hc == []


def test_movimentos_nao_paga_a_query_de_exposicao():
    with tempfile.TemporaryDirectory() as d:
        cfg = _cfg_demo(d)
        _, ven, _, _, _, _, _, vc = bridge.coletar(cfg, True, "movimentos")
        assert ven, "movimentos deveria trazer vendas"
        assert vc == [], "movimentos NAO deve pagar a janela de 400 dias da exposicao"


def test_demo_completo_nao_quebra():
    # a regressao do incidente de 11/07: --demo com alvo all tem que passar
    # por TODOS os call sites de escrever()
    with tempfile.TemporaryDirectory() as d:
        cfg = _cfg_demo(d)
        cfg["saida"]["cotacao_produtos_json"] = os.path.join(d, "produtos.json")
        cfg["saida"]["detector_salao_dir"] = os.path.join(d, "salao")
        cfg["saida"]["detector_estoque_dir"] = os.path.join(d, "estoque")
        cfg["saida"]["dashboard_dir"] = os.path.join(d, "dash")
        cfg["saida"]["upload_manual_dir"] = os.path.join(d, "up")
        cfg["saida"]["upload_manual_auditoria_dir"] = os.path.join(d, "upa")
        cfg["saida"]["historico_cliente_csv"] = os.path.join(d, "hc.csv")
        dados = bridge.coletar(cfg, True, "all")
        rel = bridge.escrever(cfg, *dados, alvo="all")
        assert any("vendas_canal.csv" in r for r in rel)
