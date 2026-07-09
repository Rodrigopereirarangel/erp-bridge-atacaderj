# -*- coding: utf-8 -*-
import json
import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from robo import validacao  # noqa: E402


def _escrever(tmp_path, obj):
    caminho = str(tmp_path / "catalogo_bridge.json")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    return caminho


def test_arquivo_de_hoje_passa(tmp_path):
    hoje = datetime.now().strftime("%Y-%m-%d")
    caminho = _escrever(tmp_path, {"origem": "erp-bridge", "gerado_em": f"{hoje} 05:00:00",
                                   "total": 1, "produtos": [{"c": 1, "p": "X", "q": 1, "v": 1.0}]})
    obj = validacao.validar_arquivo(caminho)
    assert obj["total"] == 1


def test_arquivo_velho_falha(tmp_path):
    caminho = _escrever(tmp_path, {"origem": "erp-bridge", "gerado_em": "2020-01-01 05:00:00",
                                   "total": 1, "produtos": [{"c": 1, "p": "X", "q": 1, "v": 1.0}]})
    with pytest.raises(SystemExit):
        validacao.validar_arquivo(caminho)


def test_formato_errado_falha(tmp_path):
    caminho = _escrever(tmp_path, {"qualquer": "coisa"})
    with pytest.raises(SystemExit):
        validacao.validar_arquivo(caminho)


def test_arquivo_inexistente_falha(tmp_path):
    with pytest.raises(SystemExit):
        validacao.validar_arquivo(str(tmp_path / "nao_existe.json"))


def test_config_incompleto_falha(tmp_path):
    with open(tmp_path / "config_robo.json", "w", encoding="utf-8") as f:
        json.dump({"artifact_url": "https://claude.ai/x"}, f)
    with pytest.raises(SystemExit):
        validacao.carregar_config(str(tmp_path))


def test_config_completo_passa(tmp_path):
    cfg = {"artifact_url": "https://claude.ai/x", "arquivo_catalogo": "c:/x.json",
           "perfil_dir": "c:/perfil"}
    with open(tmp_path / "config_robo.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    assert validacao.carregar_config(str(tmp_path)) == cfg


def test_url_placeholder_bloqueia_producao():
    with pytest.raises(SystemExit):
        validacao.exigir_url_real({"artifact_url": "COLE-O-LINK-DO-ARTIFACT-AQUI"})
    validacao.exigir_url_real({"artifact_url": "https://claude.ai/artifacts/abc"})  # nao levanta
