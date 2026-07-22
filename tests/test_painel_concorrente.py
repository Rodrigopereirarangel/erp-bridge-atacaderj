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


def test_previa_concorrente_divide_zonas_e_filtra_frescor(tmp_path):
    html = ('<script>const ITENS = ['
            '{"g": "kvi", "p": "CACHACA", "a": 2.68, "s": 2.29,'
            ' "v": [{"n": "Rio", "p": 2.19, "d": true, "dt": "15/07/2026"}]}, '
            '{"g": "kvi", "p": "VELHO", "a": 5.0, "s": 4.0,'
            ' "v": [{"n": "Rio", "p": 3.9, "d": true, "dt": "01/07/2026"}]}, '
            '{"g": "alinha", "p": "AMACIANTE", "a": 8.79, "s": 9.49,'
            ' "v": [{"n": "Rio", "p": 9.49, "d": true, "dt": "20/07/2026"}]}, '
            '{"g": "degrau", "p": "OUTRA", "a": 1, "s": 2,'
            ' "v": [{"n": "Rio", "p": 2, "d": true, "dt": "20/07/2026"}]}'
            '];</script>')
    arq = tmp_path / "rev.html"
    arq.write_text(html, encoding="utf-8")
    pv = pc.previa_concorrente(str(arq), "2026-07-22")
    assert [i["produto"] for i in pv["acima"]] == ["CACHACA"]   # VELHO velho
    assert [i["produto"] for i in pv["abaixo"]] == ["AMACIANTE"]
    c = pv["acima"][0]
    assert c["ref_nome"] == "Rio" and c["ref_preco"] == 2.19
    assert c["ref_data"] == "15/07/2026" and c["delta_pct"] == -14.6
    assert pv["abaixo"][0]["delta_pct"] == 8.0
