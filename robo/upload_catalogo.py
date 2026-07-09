# -*- coding: utf-8 -*-
"""Robo de upload: sobe o catalogo_bridge.json no artifact da cotacao (claude.ai).

O arquivo unico carrega o catalogo (banco de precos) E o historico de pedidos
de venda (aba Auditoria) — um upload alimenta as duas coisas para todos os
usuarios do artifact (storage compartilhado).

Uso:
  python robo/upload_catalogo.py --setup        # abre o navegador p/ logar no claude.ai (1x)
  python robo/upload_catalogo.py --teste        # fluxo completo contra o HTML publicavel LOCAL
  python robo/upload_catalogo.py                # rodada normal (agendada, sobe no artifact)

Requisitos (1x): pip install playwright  (usa o Chrome ja instalado — channel="chrome")
Config: robo/config_robo.json (copie de config_robo.example.json).
Sai com codigo 0 (sucesso) / 1 (falha). Log: robo/robo_upload.log; em falha
tambem salva robo/ultima_falha.png.
"""
import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
from robo import validacao  # noqa: E402


def log(msg):
    linha = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(linha)
    with open(os.path.join(AQUI, "robo_upload.log"), "a", encoding="utf-8") as f:
        f.write(linha + "\n")


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
    """Rodada agendada: abre o artifact no Chrome logado (perfil persistente) e sobe o arquivo."""
    from playwright.sync_api import sync_playwright

    validacao.exigir_url_real(cfg)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            cfg["perfil_dir"], channel="chrome", headless=False,
            accept_downloads=True, viewport={"width": 1280, "height": 900})
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(cfg["artifact_url"], wait_until="domcontentloaded", timeout=60000)
            if "/login" in page.url:
                raise RuntimeError("caiu na tela de login — rode: python robo/upload_catalogo.py --setup")
            frame = achar_frame_do_app(page, timeout_s=90)
            n_cat, n_ped = subir_catalogo(page, frame, arquivo, obj)
            page.wait_for_timeout(5000)  # folga p/ o storage compartilhado sincronizar
            log(f"OK  {n_cat} produtos + {n_ped} pedidos ({obj['gerado_em']}) enviados ao artifact")
        except Exception as e:
            log(f"FALHA  {e}")
            try:
                page.screenshot(path=os.path.join(AQUI, "ultima_falha.png"), full_page=True)
            except Exception:
                pass
            ctx.close()
            sys.exit(1)
        ctx.close()


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
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                cfg["perfil_dir"], channel="chrome", headless=False,
                viewport={"width": 1280, "height": 900})
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://claude.ai/")
            print("Logue na conta Claude (a DONA do artifact). Quando terminar, FECHE o navegador.")
            print("O perfil fica salvo em:", cfg["perfil_dir"])
            try:
                page.wait_for_event("close", timeout=0)
            except Exception:
                pass
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
