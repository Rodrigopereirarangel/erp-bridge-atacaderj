# -*- coding: utf-8 -*-
"""Validacoes do robo de upload (separadas do Playwright para serem testaveis)."""

import json
import os
from datetime import datetime

PLACEHOLDER_URL = "COLE-O-LINK-DO-ARTIFACT-AQUI"


def carregar_config(pasta_robo):
    caminho = os.path.join(pasta_robo, "config_robo.json")
    if not os.path.exists(caminho):
        raise SystemExit("[ERRO] Copie robo/config_robo.example.json para robo/config_robo.json e preencha.")
    with open(caminho, encoding="utf-8") as f:
        cfg = json.load(f)
    for chave in ("artifact_url", "arquivo_catalogo", "perfil_dir"):
        if not cfg.get(chave):
            raise SystemExit(f"[ERRO] Falta '{chave}' no robo/config_robo.json")
    return cfg


def exigir_url_real(cfg):
    """A rodada de producao precisa do link do artifact ja publicado."""
    if PLACEHOLDER_URL in cfg["artifact_url"]:
        raise SystemExit("[ERRO] robo/config_robo.json ainda esta com o link placeholder — "
                         "publique o artifact no claude.ai e cole o link em 'artifact_url'.")


def validar_arquivo(caminho):
    """O arquivo precisa ser um catalogo_bridge.json gerado HOJE."""
    if not os.path.exists(caminho):
        raise SystemExit(f"[ERRO] Arquivo nao encontrado: {caminho} — rode o bridge antes.")
    with open(caminho, encoding="utf-8") as f:
        obj = json.load(f)
    if obj.get("origem") != "erp-bridge" or not obj.get("produtos"):
        raise SystemExit(f"[ERRO] {caminho} nao parece um catalogo_bridge.json (origem/produtos).")
    hoje = datetime.now().strftime("%Y-%m-%d")
    if not str(obj.get("gerado_em", "")).startswith(hoje):
        raise SystemExit(f"[ERRO] catalogo_bridge.json nao e de hoje (gerado_em={obj.get('gerado_em')}) "
                         f"— rode 'python src/bridge.py --only catalogo' antes.")
    return obj
