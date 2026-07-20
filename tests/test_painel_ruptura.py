# -*- coding: utf-8 -*-
"""Leitor da rodada mais recente do detector-ruptura-estoque."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import painel_compras as pc  # noqa: E402

ITEM = {"codigo": "3905", "descricao": "SAPOLIO 450ML", "scorePrioridade": 0.9,
        "probabilidade": 0.82, "temPedido": False, "curvaABC": "C",
        "unMes": 120.0, "rsHist": 3500.0, "diasParado": 6,
        "coberturaEsgotada": True}


def _grava(dirp, nome, obj):
    with open(os.path.join(dirp, nome), "w", encoding="utf-8") as f:
        json.dump(obj, f)


def test_pega_a_rodada_mais_recente_e_traduz_campos(tmp_path):
    _grava(tmp_path, "2026-07-17.json", {"id": "2026-07-17", "refDate": "2026-07-17",
                                         "items": []})
    _grava(tmp_path, "2026-07-19.json", {"id": "2026-07-19", "refDate": "2026-07-19",
                                         "items": [ITEM]})
    r = pc.carregar_ruptura(str(tmp_path))
    assert r["ref"] == "2026-07-19" and len(r["itens"]) == 1
    i = r["itens"][0]
    assert i["codigo"] == "3905" and i["prioridade"] == 0.9
    assert i["tem_pedido"] is False and i["curva"] == "C"
    assert i["cobertura_esgotada"] is True and i["dias_parado"] == 6


def test_sem_diretorio_ou_vazio_devolve_none(tmp_path):
    assert pc.carregar_ruptura(None) is None
    assert pc.carregar_ruptura(str(tmp_path / "nao-existe")) is None
    assert pc.carregar_ruptura(str(tmp_path)) is None      # dir existe, sem .json


def test_json_malformado_levanta(tmp_path):
    (tmp_path / "2026-07-19.json").write_text("{quebrado", encoding="utf-8")
    with pytest.raises(Exception):
        pc.carregar_ruptura(str(tmp_path))
