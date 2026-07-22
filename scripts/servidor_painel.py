# -*- coding: utf-8 -*-
"""Servidor do Painel de Compras: estaticos + POST /atualizar (dono, 22/07).

Substitui o `python -m http.server`: serve a pasta do painel e ganha o
endpoint POST /atualizar, que atualiza TUDO de uma vez (dono, 22/07):
1) bridge --only movimentos (vendas/entregas/recebimentos frescos do ERP);
2) rodada nova do detector de ruptura (node src/detect.js);
3) bridge --only painel (as 8 janelas).
Trava anti-concorrencia: uma atualizacao por vez — pedido durante uma em
andamento recebe 429 (o painel espera e recarrega). Roda como SYSTEM no
boot, sem janela (ver register-painel-tasks.ps1).
"""
import json
import os
import shutil
import subprocess
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_trava = threading.Lock()


def _cfg():
    arq = next(a for a in ("config.local.json", "config.example.json")
               if os.path.exists(os.path.join(RAIZ, a)))
    with open(os.path.join(RAIZ, arq), encoding="utf-8") as f:
        cfg = json.load(f)
    p = cfg.get("painel") or {}
    return (p.get("dir_saida") or os.path.join(RAIZ, "saida", "painel"),
            int(p.get("porta_http") or 8477),
            p.get("detector_rounds_dir") or "")


def _atualizar_tudo(detector_rounds_dir):
    """Cadeia completa; cada passo falha SOZINHO (o painel sempre sai no
    fim, com o que houver de mais fresco). Devolve o relato por passo."""
    relato = []

    def roda(rotulo, args, cwd, timeout):
        try:
            r = subprocess.run(args, capture_output=True, text=True,
                               timeout=timeout, cwd=cwd)
            txt = (r.stdout or r.stderr or "").strip()
            relato.append(f"{rotulo}: {'ok' if r.returncode == 0 else 'ERRO'}"
                          f" {txt[-200:]}")
            return r.returncode == 0
        except Exception as e:  # noqa: BLE001
            relato.append(f"{rotulo}: ERRO {str(e)[:150]}")
            return False

    roda("movimentos",
         [sys.executable, os.path.join(RAIZ, "src", "bridge.py"),
          "--only", "movimentos"], RAIZ, 300)
    det = os.path.dirname(os.path.dirname(detector_rounds_dir or ""))
    node = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"
    if det and os.path.isdir(os.path.join(det, "src")):
        roda("detector", [node, os.path.join(det, "src", "detect.js")],
             det, 300)
    ok = roda("painel",
              [sys.executable, os.path.join(RAIZ, "src", "bridge.py"),
               "--only", "painel"], RAIZ, 300)
    return ok, " | ".join(relato)


class Handler(SimpleHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 — nome da stdlib
        if self.path.rstrip("/") != "/atualizar":
            self.send_error(404)
            return
        if not _trava.acquire(blocking=False):
            self._json(429, {"ok": False, "erro": "atualizacao ja em andamento"})
            return
        try:
            ok, saida = _atualizar_tudo(self.server.detector_rounds_dir)
            self._json(200 if ok else 500, {"ok": ok, "saida": saida[-500:]})
        except Exception as e:  # noqa: BLE001 — erro vira resposta, nao crash
            self._json(500, {"ok": False, "erro": str(e)[:300]})
        finally:
            _trava.release()

    def _json(self, status, obj):
        corpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *a):  # noqa: D102
        pass   # roda como SYSTEM, sem console — log so faria buffer crescer


def main():
    destino, porta, rounds = _cfg()
    srv = ThreadingHTTPServer(("0.0.0.0", porta),
                              partial(Handler, directory=destino))
    srv.detector_rounds_dir = rounds
    srv.serve_forever()


if __name__ == "__main__":
    main()
