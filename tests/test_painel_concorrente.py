# -*- coding: utf-8 -*-
"""Escolha e copia do revisao_Sxx.html mais recente do pricing."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import painel_compras as pc  # noqa: E402


def test_escolhe_por_ano_e_semana_numerica_nao_lexicografica(tmp_path):
    origem = tmp_path / "dados"; destino = tmp_path / "painel"
    origem.mkdir(); destino.mkdir()
    (origem / "revisao_2026-S9.html").write_text("velho", encoding="utf-8")
    (origem / "revisao_2026-S10.html").write_text("novo", encoding="utf-8")
    r = pc.copiar_revisao_pricing(str(origem), str(destino))
    assert r["rotulo"] == "2026-S10"          # S10 > S9 (lexicografico daria S9)
    assert r["arquivo"] == "revisao_pricing.html"
    copiado = destino / "revisao_pricing.html"
    assert copiado.read_text(encoding="utf-8") == "novo"
    assert r["modificado_em"]


def test_sem_dir_ou_sem_arquivo_devolve_none(tmp_path):
    assert pc.copiar_revisao_pricing(None, str(tmp_path)) is None
    assert pc.copiar_revisao_pricing(str(tmp_path / "x"), str(tmp_path)) is None
    vazio = tmp_path / "dados"; vazio.mkdir()
    assert pc.copiar_revisao_pricing(str(vazio), str(tmp_path)) is None
