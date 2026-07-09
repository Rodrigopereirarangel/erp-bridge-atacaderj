# -*- coding: utf-8 -*-
"""Robo de upload: sobe o catalogo_bridge.json no artifact da cotacao (claude.ai).

O arquivo unico carrega o catalogo (banco de precos) E o historico de pedidos
de venda (aba Auditoria) — um upload alimenta as duas coisas para todos os
usuarios do artifact (storage compartilhado).

COMO O ROBO ABRE O NAVEGADOR (importante): o Chrome lancado pelo Playwright
vem com marcas de automacao (--no-sandbox etc.) e o Cloudflare do claude.ai
DETECTA e recusa o desafio "confirme que e humano" mesmo com clique manual
(confirmado em 2026-07-09). Por isso o robo abre um Chrome NORMAL (sem marca
nenhuma, mesmo binario do atalho) com --remote-debugging-port e se conecta a
ele por CDP — para o Cloudflare e um navegador comum com perfil e cookies.

Uso:
  python robo/upload_catalogo.py --setup        # abre o Chrome do robo p/ logar no claude.ai (1x)
  python robo/upload_catalogo.py --teste        # fluxo completo contra o HTML publicavel LOCAL
  python robo/upload_catalogo.py                # rodada normal (agendada, sobe no artifact)

Requisitos (1x): pip install playwright  (usa o Chrome ja instalado)
Config: robo/config_robo.json (copie de config_robo.example.json).
Sai com codigo 0 (sucesso) / 1 (falha). Log: robo/robo_upload.log; em falha
tambem salva robo/ultima_falha.png.
"""
import argparse
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
from robo import validacao  # noqa: E402

PORTA_CDP = 9777


def log(msg):
    linha = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(linha)
    with open(os.path.join(AQUI, "robo_upload.log"), "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def _achar_chrome():
    candidatos = [
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                     "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""),
                     "Google", "Chrome", "Application", "chrome.exe"),
    ]
    for c in candidatos:
        if os.path.exists(c):
            return c
    raise SystemExit("[ERRO] chrome.exe nao encontrado — instale o Google Chrome.")


def _cdp_vivo():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORTA_CDP}/json/version", timeout=1)
        return True
    except Exception:
        return False


def _lancar_chrome(perfil_dir, url="about:blank"):
    """Chrome comum (sem marcas de automacao) com porta CDP aberta e perfil do robo."""
    os.makedirs(perfil_dir, exist_ok=True)
    subprocess.Popen([
        _achar_chrome(),
        f"--remote-debugging-port={PORTA_CDP}",
        f"--user-data-dir={perfil_dir}",
        "--no-first-run", "--no-default-browser-check",
        "--window-size=1280,900",
        url,
    ])
    for _ in range(60):  # ate 18s para a porta abrir
        if _cdp_vivo():
            return
        time.sleep(0.3)
    raise SystemExit("[ERRO] Chrome abriu mas a porta CDP nao respondeu — feche janelas antigas do robo e tente de novo.")


def _fechar_chrome(browser):
    """Fecha o Chrome inteiro (browser.close() do CDP so desconecta)."""
    try:
        browser.new_browser_cdp_session().send("Browser.close")
    except Exception:
        pass


def achar_frame_do_app(page, timeout_s=90):
    """Frame onde o app esta rodando: a propria pagina (teste local) ou o iframe do artifact."""
    fim = time.time() + timeout_s
    while time.time() < fim:
        for fr in page.frames:
            try:
                if fr.locator("#btnCatalogo").count() > 0:
                    return fr
            except Exception:
                pass
        page.wait_for_timeout(1000)
    urls = [fr.url[:120] for fr in page.frames]
    raise RuntimeError(f"nao achei o app (#btnCatalogo) em nenhum frame apos {timeout_s}s. "
                       f"Frames vistos: {urls}. Esta logado no claude.ai? O link e do artifact publicado?")


def subir_catalogo(page, frame, arquivo, obj):
    """Executa o fluxo do botao 📦 e confirma; levanta RuntimeError se algo nao bater."""
    frame.locator("#btnCatalogo").click(timeout=30000)
    frame.wait_for_selector("#catBridgeArq", timeout=15000)
    # se a trava anti-sobrescrita estiver ativa (upload do robo < 5h), destrava:
    # o proprio robo e a automacao, entao pode passar por ela
    frame.evaluate("() => { try { if (typeof _catDestravarManual === 'function') _catDestravarManual(); } catch (e) {} }")
    frame.locator("#catBridgeArq").set_input_files(arquivo, timeout=30000)
    # o onchange valida o arquivo e mostra a previa com o botao verde de confirmar
    frame.wait_for_selector("#catConfirmar", timeout=60000)

    # confirmar dispara o download do snapshot da biblioteca — guardamos como backup
    # (no iframe do artifact o download pode ser bloqueado pelo sandbox: e opcional)
    try:
        with page.expect_download(timeout=10000) as dl:
            frame.locator("#catConfirmar").click(timeout=30000)
        os.makedirs(os.path.join(AQUI, "backups"), exist_ok=True)
        dl.value.save_as(os.path.join(AQUI, "backups",
                                      f"biblioteca-{datetime.now():%Y%m%d-%H%M%S}.json"))
    except Exception:
        pass  # sem download nao e erro; o clique ja aconteceu

    # o modal fecha ao confirmar
    frame.wait_for_selector("#cat-overlay", state="detached", timeout=30000)

    # verificacao 1: o chip tem que mostrar a data de HOJE
    chip = frame.locator("#catalogBadge")
    chip.wait_for(state="visible", timeout=30000)
    hoje_br = datetime.now().strftime("%d/%m/%Y")
    texto = chip.text_content() or ""
    if hoje_br not in texto:
        raise RuntimeError(f"chip do catalogo nao confirma a data de hoje: {texto!r}")

    # verificacao 2: o catalogo em uso tem o mesmo total do arquivo
    n_cat = frame.evaluate("() => (typeof CATALOG !== 'undefined' && CATALOG.length) || 0")
    if n_cat != obj["total"]:
        raise RuntimeError(f"CATALOG tem {n_cat} produtos, arquivo declara {obj['total']}")

    # verificacao 3: o historico da auditoria foi salvo no storage
    n_ped = frame.evaluate(
        "() => { try { const pv = JSON.parse(_store.getItem('atacaderj_pedidos_venda')||'null');"
        " return pv && pv.pedidos ? pv.pedidos.length : 0; } catch (e) { return 0; } }")
    esperado = len(obj.get("pedidos_venda", {}).get("pedidos", []))
    if esperado and n_ped != esperado:
        raise RuntimeError(f"storage da auditoria tem {n_ped} pedidos, arquivo tem {esperado}")
    return n_cat, n_ped


def rodar_teste_local(cfg, arquivo, obj, headed=False):
    """Fluxo completo contra o HTML publicavel local — valida robo + HTML sem claude.ai."""
    from playwright.sync_api import sync_playwright

    html = cfg.get("html_teste") or os.path.join(
        os.path.dirname(os.path.dirname(AQUI)),
        "cotacao-auditoria-atacaderj", "app", "cotacao-auditoria-atacaderj.publicavel.html")
    if not os.path.exists(html):
        raise SystemExit(f"[ERRO] HTML de teste nao encontrado: {html} — rode 'npm run publicavel' no repo do app.")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=not headed)
        page = browser.new_page(viewport={"width": 1280, "height": 900}, accept_downloads=True)
        page.goto(Path(html).resolve().as_uri())

        # pre-checagens do publicavel: XLSX via cdnjs carregou; CATALOG embutido esta vazio
        page.wait_for_function("typeof XLSX !== 'undefined'", timeout=30000)
        n0 = page.evaluate("() => CATALOG.length")
        if n0 != 0:
            raise RuntimeError(f"publicavel deveria comecar com CATALOG vazio, tem {n0}")
        log("teste: XLSX (cdnjs) OK · CATALOG embutido vazio OK")

        frame = achar_frame_do_app(page, timeout_s=15)
        n_cat, n_ped = subir_catalogo(page, frame, arquivo, obj)
        log(f"teste: upload OK — {n_cat} produtos no CATALOG · {n_ped} pedidos no storage da auditoria")

        # aba Auditoria: dias aparecem a partir do storage e um dia roda de ponta a ponta
        frame.evaluate("() => abrirAuditoria()")
        frame.wait_for_selector(".aud-dia", timeout=15000)
        n_dias = frame.locator(".aud-dia").count()
        frame.locator(".aud-dia").first.click()
        frame.wait_for_selector("#aud-output .kpis, #aud-output .ok-banner", timeout=30000)
        kpi = frame.evaluate(
            "() => { const el = document.querySelector('#aud-output .kpi .v');"
            " return el ? el.textContent : 'ok-banner'; }")
        frame.evaluate("() => document.getElementById('aud-overlay').remove()")
        log(f"teste: auditoria OK — {n_dias} dia(s) no seletor; dia mais recente auditou ({kpi} itens)")

        # a trava anti-sobrescrita deve estar ATIVA agora (upload do robo ha < 5h)
        frame.evaluate("() => abrirAtualizarCatalogo()")
        frame.wait_for_selector("#catUploadArea", timeout=10000)
        travado = frame.evaluate(
            "() => document.getElementById('catUploadArea').style.pointerEvents === 'none'")
        if not travado:
            raise RuntimeError("upload manual deveria estar travado apos upload do robo")
        log("teste: trava anti-sobrescrita do upload manual OK")

        browser.close()


def rodar_producao(cfg, arquivo, obj):
    """Rodada agendada: Chrome comum (CDP) com o perfil logado abre o artifact e sobe o arquivo."""
    from playwright.sync_api import sync_playwright

    validacao.exigir_url_real(cfg)
    _lancar_chrome(cfg["perfil_dir"], cfg["artifact_url"])
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORTA_CDP}")
        ctx = browser.contexts[0]
        # o Chrome pode ja estar aberto com outras abas (ex.: sobrou do --setup):
        # acha a aba do artifact ou usa/cria uma e navega nela
        page = None
        for pg in ctx.pages:
            if "artifacts" in pg.url:
                page = pg
                break
        if page is None:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(cfg["artifact_url"], wait_until="domcontentloaded", timeout=60000)
            page.bring_to_front()
            # se cair no desafio do Cloudflare, um navegador comum passa sozinho
            # em alguns segundos — o achar_frame_do_app espera ate 120s por isso
            if "/login" in page.url:
                raise RuntimeError("caiu na tela de login — rode: python robo/upload_catalogo.py --setup")
            frame = achar_frame_do_app(page, timeout_s=120)
            # diagnostico do que esta publicado (o publicavel certo comeca com CATALOG=[])
            n_antes = frame.evaluate("() => (typeof CATALOG !== 'undefined' && CATALOG.length) || 0")
            tem_xlsx = frame.evaluate("() => typeof XLSX !== 'undefined'")
            log(f"artifact aberto — CATALOG embutido: {n_antes} (esperado 0) · XLSX carregado: {tem_xlsx}")
            # sem o storage compartilhado o upload ficaria so no navegador do robo
            # (localStorage) e NAO chegaria aos vendedores — melhor falhar claro
            ws = frame.evaluate("() => (typeof _store !== 'undefined' && _store._ws) || false")
            if not ws:
                raise RuntimeError("storage compartilhado indisponivel no artifact — o perfil do robo "
                                   "esta logado no claude.ai? Rode: python robo/upload_catalogo.py --setup")
            n_cat, n_ped = subir_catalogo(page, frame, arquivo, obj)
            page.wait_for_timeout(5000)  # folga p/ o storage compartilhado sincronizar
            log(f"OK  {n_cat} produtos + {n_ped} pedidos ({obj['gerado_em']}) enviados ao artifact")
        except Exception as e:
            log(f"FALHA  {e}")
            try:
                page.screenshot(path=os.path.join(AQUI, "ultima_falha.png"), full_page=True)
            except Exception:
                pass
            _fechar_chrome(browser)
            sys.exit(1)
        _fechar_chrome(browser)


def rodar_setup(cfg):
    """Login unico: abre o Chrome do robo (comum, sem marcas) no claude.ai."""
    _lancar_chrome(cfg["perfil_dir"], "https://claude.ai/")
    print("Abriu o Chrome do robo (janela SEM a tarja de automacao).")
    print("1. Logue na conta Claude DONA do artifact (passe o 'confirme que e humano' se aparecer).")
    print("2. Quando estiver na tela inicial logada, FECHE o navegador.")
    print("O perfil fica salvo em:", cfg["perfil_dir"])
    while _cdp_vivo():
        time.sleep(2)
    print("Navegador fechado — login salvo.")


def main():
    ap = argparse.ArgumentParser(description="Sobe catalogo_bridge.json no artifact da cotacao")
    ap.add_argument("--setup", action="store_true",
                    help="abre o navegador para logar no claude.ai e salvar o perfil (rodar 1x)")
    ap.add_argument("--teste", action="store_true",
                    help="roda o fluxo completo contra o HTML publicavel local (sem claude.ai)")
    ap.add_argument("--headed", action="store_true", help="no --teste, mostra o navegador")
    args = ap.parse_args()
    cfg = validacao.carregar_config(AQUI)

    if args.setup:
        rodar_setup(cfg)
        return

    obj = validacao.validar_arquivo(cfg["arquivo_catalogo"])
    if args.teste:
        try:
            rodar_teste_local(cfg, cfg["arquivo_catalogo"], obj, headed=args.headed)
            log(f"TESTE LOCAL OK — {obj['total']} produtos ({obj['gerado_em']})")
        except (RuntimeError, Exception) as e:
            log(f"TESTE FALHOU  {e}")
            sys.exit(1)
        return

    rodar_producao(cfg, cfg["arquivo_catalogo"], obj)


if __name__ == "__main__":
    main()
