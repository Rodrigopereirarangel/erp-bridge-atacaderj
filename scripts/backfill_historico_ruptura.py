# -*- coding: utf-8 -*-
"""Backfill (1x) da serie historica da ruptura — spec §13 do painel.

Replay semanal do detector desde 06/04 (scripts/replay_ruptura.js) e mescla
em painel/historico.json. Rodar NO PONTE:

    python scripts/backfill_historico_ruptura.py

Requer painel.detector_rounds_dir no config.local.json (o dir do detector e o
avo de data/rounds). Idempotente: re-rodar so re-escreve as mesmas datas.
O ponto de HOJE nao entra aqui — vem da rodada real a cada geracao do painel.
"""
import json
import os
import subprocess
import sys
from datetime import date

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
import historico_painel  # noqa: E402


def main():
    arq = next((a for a in ("config.local.json", "config.example.json")
                if os.path.exists(os.path.join(RAIZ, a))), None)
    with open(os.path.join(RAIZ, arq), encoding="utf-8") as f:
        cfgp = json.load(f).get("painel") or {}
    rounds = cfgp.get("detector_rounds_dir") or ""
    destino = cfgp.get("dir_saida") or os.path.join(RAIZ, "saida", "painel")
    det = os.path.dirname(os.path.dirname(rounds))   # <det>/data/rounds -> <det>
    if not det or not os.path.isdir(os.path.join(det, "src")):
        print(f"[ERRO] detector nao encontrado via detector_rounds_dir: {rounds!r}")
        return 1
    hoje = date.today().isoformat()
    dias = [d for d in historico_painel.segundas_desde(
        historico_painel.INICIO_HISTORICO, hoje) if d != hoje]
    r = subprocess.run(
        ["node", os.path.join(RAIZ, "scripts", "replay_ruptura.js"),
         det, ",".join(dias)],
        capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[ERRO] replay: {(r.stderr or r.stdout).strip()[:400]}")
        return 1
    contagens = json.loads(r.stdout)
    serie = [{"s": d, "v": contagens[d]} for d in dias if d in contagens]
    os.makedirs(destino, exist_ok=True)
    historico_painel.mesclar_historico(destino, {"ruptura": serie}, hoje)
    print(f"[OK] ruptura: {len(serie)} semanas mescladas "
          f"({serie[0]['s']} -> {serie[-1]['s']}) em "
          f"{os.path.join(destino, 'historico.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
