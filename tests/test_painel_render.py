# -*- coding: utf-8 -*-
"""Renderizacao do template do painel: dados embutidos, escape, carimbos."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import painel_compras as pc  # noqa: E402


def _payload():
    return {
        "origem": "erp-bridge-painel", "gerado_em": "2026-07-20 06:00:00",
        "cfg": {"rodizio_segundos": 20, "reload_minutos": 5,
                "validade_urgente_dias": 30, "cobranca_dias_limiar": 7,
                "detector_dashboard_url": ""},
        "validade_relampago": {"carimbo": "2026-07-20 06:00:00", "erro": None,
                               "itens": [{"codigo": "1", "descricao": "X</script>Y",
                                          "curva": "A", "preco_relampago": 1.0,
                                          "promo_inicio": "2026-07-19",
                                          "promo_fim": "2026-07-25",
                                          "validades": ["2026-08-08"],
                                          "dias_ate_vencer": 19}]},
        "ruptura": {"carimbo": "2026-07-19", "erro": None, "itens": []},
        "cobranca": {"carimbo": "2026-07-20 06:00:00",
                     "erro": "banco inacessivel", "itens": [], "abandonados": 3},
        "concorrente": {"carimbo": "2026-07-14 07:00", "erro": None,
                        "rotulo": "2026-S29", "arquivo": "revisao_pricing.html"},
    }


def test_embute_payload_e_remove_placeholder():
    html = pc.renderizar(_payload())
    assert "/*__DADOS__*/null" not in html
    assert '"origem": "erp-bridge-painel"' in html


def test_escapa_fechamento_de_script_na_descricao():
    html = pc.renderizar(_payload())
    assert "X</script>Y" not in html          # cru quebraria o <script> do painel
    assert "X<\\/script>Y" in html


def test_template_tem_os_4_quadrantes_e_modo_tv():
    html = pc.renderizar(_payload())
    for marca in ("id=\"grade\"", "id=\"detalhe\"", "#tv", "rodizio_segundos"):
        assert marca in html
