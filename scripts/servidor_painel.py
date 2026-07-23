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
import base64
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

# arquivos servidos SEM login (dono, 22/07): a listagem por fornecedor e
# aberta para qualquer um da rede/Tailscale — o RESTO do painel continua
# atras do Basic auth. So GET/HEAD; POST /atualizar segue protegido.
# /listagem/overrides (GET+POST, dono 23/07): agrupamento de fornecedores
# (filho->mae) e itens movidos a mao pela pagina da listagem — persiste em
# JSON (painel.listagem_overrides_json) que o gerar.py da listagem tambem le.
PUBLICOS = {"/listagem-fornecedores.html", "/listagem/overrides"}
OVERRIDES_MAX = 2_000_000   # 2 MB: ~10x o tamanho plausivel do JSON


def _cfg():
    arq = next(a for a in ("config.local.json", "config.example.json")
               if os.path.exists(os.path.join(RAIZ, a)))
    with open(os.path.join(RAIZ, arq), encoding="utf-8") as f:
        cfg = json.load(f)
    p = cfg.get("painel") or {}
    # usuarios+senhas (dono, 22/07): acesso_usuario/acesso_senha (1o login)
    # e acesso_usuarios [{usuario, senha}] (demais). Nenhum definido = sem
    # login. Credenciais SO no config.local.json (gitignored).
    pares = []
    if (p.get("acesso_usuario") or "").strip() and \
            (p.get("acesso_senha") or "").strip():
        pares.append((p["acesso_usuario"].strip(), p["acesso_senha"].strip()))
    for u in p.get("acesso_usuarios") or []:
        if (u.get("usuario") or "").strip() and (u.get("senha") or "").strip():
            pares.append((u["usuario"].strip(), u["senha"].strip()))
    creds = {base64.b64encode(f"{us}:{se}".encode()).decode()
             for us, se in pares} or None
    return (p.get("dir_saida") or os.path.join(RAIZ, "saida", "painel"),
            int(p.get("porta_http") or 8477),
            p.get("detector_rounds_dir") or "", creds,
            p.get("listagem_overrides_json") or "")


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
    def _autorizado(self):
        creds = getattr(self.server, "credenciais", None)
        if not creds:
            return True
        auth = self.headers.get("Authorization") or ""
        return auth.startswith("Basic ") and auth[6:] in creds

    def _pede_login(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate",
                         'Basic realm="Painel de Compras AtacadeRJ"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _publico(self):
        return self.path.split("?", 1)[0] in PUBLICOS

    def _e_overrides(self):
        return self.path.split("?", 1)[0] == "/listagem/overrides"

    def _overrides_get(self):
        arq = getattr(self.server, "overrides_json", "")
        if not arq:
            self.send_error(404)
            return
        dados = {"grupos": {}, "itens": {}}
        if os.path.exists(arq):
            try:
                with open(arq, encoding="utf-8") as f:
                    dados = json.load(f)
            except (OSError, ValueError):
                pass                      # ilegivel -> devolve vazio
        self._json(200, dados)

    def _overrides_post(self):
        arq = getattr(self.server, "overrides_json", "")
        if not arq:
            self.send_error(404)
            return
        tam = int(self.headers.get("Content-Length") or 0)
        if not 0 < tam <= OVERRIDES_MAX:
            self._json(413, {"ok": False, "erro": "tamanho invalido"})
            return
        try:
            corpo = json.loads(self.rfile.read(tam).decode("utf-8"))
            grupos = corpo.get("grupos") or {}
            itens = corpo.get("itens") or {}
            ok = (isinstance(grupos, dict) and isinstance(itens, dict)
                  and all(isinstance(k, str) and isinstance(v, str)
                          for k, v in grupos.items())
                  and all(isinstance(k, str) and isinstance(v, str)
                          for k, v in itens.items()))
            if not ok:
                raise ValueError("formato: grupos/itens devem ser str->str")
        except (ValueError, UnicodeDecodeError) as e:
            self._json(400, {"ok": False, "erro": str(e)[:200]})
            return
        os.makedirs(os.path.dirname(arq), exist_ok=True)
        tmp = arq + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"grupos": grupos, "itens": itens}, f,
                      ensure_ascii=False, indent=1)
        os.replace(tmp, arq)
        self._json(200, {"ok": True, "grupos": len(grupos),
                         "itens": len(itens)})

    def do_GET(self):  # noqa: N802 — nome da stdlib
        if self._e_overrides():
            return self._overrides_get()
        if not self._publico() and not self._autorizado():
            return self._pede_login()
        return super().do_GET()

    def do_HEAD(self):  # noqa: N802
        if not self._publico() and not self._autorizado():
            return self._pede_login()
        return super().do_HEAD()

    def do_POST(self):  # noqa: N802 — nome da stdlib
        if self._e_overrides():           # publico, como a pagina que o usa
            return self._overrides_post()
        if not self._autorizado():
            return self._pede_login()
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
    destino, porta, rounds, creds, overrides = _cfg()
    srv = ThreadingHTTPServer(("0.0.0.0", porta),
                              partial(Handler, directory=destino))
    srv.detector_rounds_dir = rounds
    srv.credenciais = creds
    srv.overrides_json = overrides
    srv.serve_forever()


if __name__ == "__main__":
    main()
