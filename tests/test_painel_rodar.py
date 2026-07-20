# -*- coding: utf-8 -*-
"""rodar(): geracao completa em demo + resiliencia por fonte."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import painel_compras as pc  # noqa: E402


def _cfg(tmp_path, **painel):
    base = {"dir_saida": str(tmp_path / "painel")}
    base.update(painel)
    return {"painel": base}


def test_demo_gera_index_e_json(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "RAIZ", str(tmp_path))
    rel = pc.rodar(_cfg(tmp_path), usar_demo=True)
    assert any("painel/index.html" in l for l in rel)
    html = (tmp_path / "painel" / "index.html").read_text(encoding="utf-8")
    assert '"origem": "erp-bridge-painel"' in html
    dados = json.loads((tmp_path / "painel" / "dados_painel.json").read_text(
        encoding="utf-8"))
    # validade x relampago do demo: 2411 com urgencia, 3905 sem validade
    cods = {i["codigo"] for i in dados["validade_relampago"]["itens"]}
    assert {"2411", "3905", "9999"} <= cods
    # cobranca demo: 101 e 102 entram, 103 (recente) fica fora
    peds = {i["pedido"] for i in dados["cobranca"]["itens"]}
    assert peds == {101, 102}


def test_fontes_ausentes_nao_derrubam_a_geracao(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "RAIZ", str(tmp_path))
    cfg = _cfg(tmp_path,
               detector_rounds_dir=str(tmp_path / "nao-existe"),
               pricing_dados_dir=str(tmp_path / "tambem-nao"))
    pc.rodar(cfg, usar_demo=True)
    dados = json.loads((tmp_path / "painel" / "dados_painel.json").read_text(
        encoding="utf-8"))
    assert dados["ruptura"]["erro"]        # avisa, nao quebra
    assert dados["concorrente"]["erro"]


def test_ruptura_e_concorrente_entram_quando_existem(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "RAIZ", str(tmp_path))
    rounds = tmp_path / "rounds"; rounds.mkdir()
    (rounds / "2026-07-19.json").write_text(json.dumps(
        {"id": "2026-07-19", "refDate": "2026-07-19",
         "items": [{"codigo": "3905", "descricao": "SAPOLIO", "scorePrioridade": 0.9,
                    "probabilidade": 0.8, "temPedido": False, "curvaABC": "C",
                    "unMes": 100, "rsHist": 900, "diasParado": 5,
                    "coberturaEsgotada": True}]}), encoding="utf-8")
    pricing = tmp_path / "pricing"; pricing.mkdir()
    (pricing / "revisao_2026-S29.html").write_text("<html>rev</html>", encoding="utf-8")
    cfg = _cfg(tmp_path, detector_rounds_dir=str(rounds),
               pricing_dados_dir=str(pricing))
    pc.rodar(cfg, usar_demo=True)
    dados = json.loads((tmp_path / "painel" / "dados_painel.json").read_text(
        encoding="utf-8"))
    assert dados["ruptura"]["carimbo"] == "2026-07-19"
    assert dados["ruptura"]["itens"][0]["codigo"] == "3905"
    assert dados["concorrente"]["rotulo"] == "2026-S29"
    assert (tmp_path / "painel" / "revisao_pricing.html").exists()


class _DbConectarQuebra:
    @staticmethod
    def conectar(cfg_db):
        raise RuntimeError("sem rota para o servidor")


class _ConnCloseQuebra:
    def close(self):
        raise RuntimeError("conexao ja caida")


class _DbTudoQuebra:
    @staticmethod
    def conectar(cfg_db):
        return _ConnCloseQuebra()

    @staticmethod
    def consultar(conn, sql):
        raise RuntimeError("query falhou")


def test_banco_fora_do_ar_nao_derruba_a_geracao(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "db", _DbConectarQuebra)
    monkeypatch.setattr(pc, "RAIZ", str(tmp_path))
    cfg = {"db": {}, "painel": {"dir_saida": str(tmp_path / "painel")}}
    pc.rodar(cfg, usar_demo=False)          # nao pode levantar
    dados = json.loads((tmp_path / "painel" / "dados_painel.json").read_text(
        encoding="utf-8"))
    assert "banco inacessivel" in dados["validade_relampago"]["erro"]
    assert "banco inacessivel" in dados["cobranca"]["erro"]
    assert (tmp_path / "painel" / "index.html").exists()
    # o aviso precisa deixar trilha no bridge_erros.log (spec §8)
    log = tmp_path / "bridge_erros.log"
    assert log.exists() and "PAINEL validade" in log.read_text(encoding="utf-8")


def test_close_quebrado_e_queries_falhando_nao_derrubam(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "RAIZ", str(tmp_path))
    monkeypatch.setitem(sys.modules, "db", _DbTudoQuebra)
    cfg = {"db": {}, "painel": {"dir_saida": str(tmp_path / "painel")}}
    pc.rodar(cfg, usar_demo=False)          # nem consultar nem close derrubam
    dados = json.loads((tmp_path / "painel" / "dados_painel.json").read_text(
        encoding="utf-8"))
    assert dados["validade_relampago"]["erro"]
    assert dados["cobranca"]["erro"]
    assert (tmp_path / "painel" / "index.html").exists()
