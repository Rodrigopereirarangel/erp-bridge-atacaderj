# -*- coding: utf-8 -*-
"""Servidor do Painel de Compras: estaticos + POST /atualizar (dono, 22/07).

Substitui o `python -m http.server`: serve a pasta do painel e ganha o
endpoint POST /atualizar, que roda `bridge.py --only painel` NA HORA (botao
🔄 do painel). Trava anti-concorrencia: uma geracao por vez — pedido novo
durante uma geracao recebe 429 e o botao espera/recarrega. Roda como SYSTEM
no boot, sem janela (ver register-painel-tasks.ps1).
"""
import json
import os
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
            int(p.get("porta_http") or 8477))


class Handler(SimpleHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 — nome da stdlib
        if self.path.rstrip("/") != "/atualizar":
            self.send_error(404)
            return
        if not _trava.acquire(blocking=False):
            self._json(429, {"ok": False, "erro": "geracao ja em andamento"})
            return
        try:
            r = subprocess.run(
                [sys.executable, os.path.join(RAIZ, "src", "bridge.py"),
                 "--only", "painel"],
                capture_output=True, text=True, timeout=300, cwd=RAIZ)
            ok = r.returncode == 0
            self._json(200 if ok else 500,
                       {"ok": ok,
                        "saida": (r.stdout or r.stderr or "").strip()[-400:]})
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
    destino, porta = _cfg()
    srv = ThreadingHTTPServer(("0.0.0.0", porta),
                              partial(Handler, directory=destino))
    srv.serve_forever()


if __name__ == "__main__":
    main()
