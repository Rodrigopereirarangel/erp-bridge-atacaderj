# Catálogo Bridge (arquivo único) + Robô de Upload — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O bridge passa a gerar o `catalogo_bridge.json` (arquivo único de importação da cotação) e ganha um robô Playwright agendado que sobe esse arquivo no artifact do claude.ai — zero toque humano na rotina.

**Architecture:** Nova projeção em `src/projections.py` (mescla varejo→promo→atacado no formato que o app da cotação consome direto), ligada ao `--only catalogo` do `src/bridge.py`. O robô (`robo/`) é um script Playwright determinístico (sem IA em runtime) que usa um perfil de navegador persistente logado no claude.ai e opera os IDs estáveis do app (`#btnCatalogo`, `#catBridgeArq`, `#catConfirmar` — criados pelo plano do repo `cotacao-auditoria-atacaderj`). Tarefas do Agendador do Windows amarram tudo.

**Tech Stack:** Python 3.12 (stdlib + pymysql já usado), pytest (dev), Playwright Python (só em `robo/`), PowerShell (Agendador de Tarefas).

**Spec:** `docs/superpowers/specs/2026-07-07-estrutura-acesso-cotacao-design.md`

## Global Constraints

- Escrita de arquivo SEMPRE atômica: usar `_escrever_atomico` (tmp + `os.replace`) — já existe em `src/projections.py`.
- Regra de promoção (verbatim da spec): "quando `preco_promocao > 0` e menor que o preço, `v = promoção`".
- Chaves do produto no arquivo único (verbatim da spec): `c, p, q, v, vu, custo, cv`.
- Nunca commitar senha, custo ou preço REAL. Saídas do `--demo` (dados falsos) podem ser commitadas (padrão já existente em `saida/`).
- `config.local.json`, perfil do navegador, logs e backups do robô são gitignored.
- Mensagens de commit em pt-BR, prefixo curto minúsculo (`feat:`, `docs:`, `robo:`) — estilo do histórico existente.
- Ao terminar cada task: commit. Ao terminar o plano: atualizar `STATUS.md` (checklist + log) e `git push`.

---

### Task 1: Projeção `catalogo_bridge_json` em `src/projections.py`

**Files:**
- Create: `tests/test_projections.py`
- Create: `requirements-dev.txt`
- Modify: `src/projections.py` (adicionar ao final)

**Interfaces:**
- Consumes: linhas canônicas do catálogo (dicts com `codigo, descricao, embalagem, custo_atual, preco_atacado, preco_varejo, preco_promocao, curva, ativo`) — mesmo formato de `demo_data.catalogo()`.
- Produces: `projections.catalogo_bridge_json(catalogo: list[dict], caminho: str, gerado_em: str) -> int` (nº de produtos escritos). Arquivo JSON: `{"origem":"erp-bridge","gerado_em":"YYYY-MM-DD HH:MM:SS","total":N,"produtos":[{"c","p","q","v","vu"?,"custo"?,"cv"?}]}`.

- [ ] **Step 1: Criar `requirements-dev.txt` e instalar pytest**

```text
pytest
playwright
```

Run: `pip install pytest`
Expected: instala sem erro (playwright só será usado na Task 4; instalar aqui também é ok).

- [ ] **Step 2: Escrever o teste que falha**

Criar `tests/test_projections.py`:

```python
# -*- coding: utf-8 -*-
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import projections  # noqa: E402

CAT = [
    # promo 16.90 vence o varejo 22.50; atacado 18.90 NAO vence a promo -> v=16.90, q=1, sem vu
    {"codigo": "2411", "descricao": "KELLOGGS SUCRILHOS 240G", "embalagem": 12,
     "custo_atual": 14.20, "preco_atacado": 18.90, "preco_varejo": 22.50,
     "preco_promocao": 16.90, "curva": "A", "ativo": 1},
    # sem promo; atacado 1.79 < varejo 2.49 -> v=1.79, q=24, vu=2.49
    {"codigo": "2795", "descricao": "MINEIRINHO 250ML", "embalagem": 24,
     "custo_atual": 1.05, "preco_atacado": 1.79, "preco_varejo": 2.49,
     "preco_promocao": None, "curva": "B", "ativo": 1},
    # item morto -> fica fora
    {"codigo": "9999", "descricao": "PRODUTO MORTO <<< EXCLUIDO >>>", "embalagem": 1,
     "custo_atual": 1.0, "preco_atacado": 2.0, "preco_varejo": 3.0,
     "preco_promocao": None, "curva": None, "ativo": 1},
    # inativo -> fica fora
    {"codigo": "7777", "descricao": "PRODUTO INATIVO 1KG", "embalagem": 1,
     "custo_atual": 1.0, "preco_atacado": 2.0, "preco_varejo": 3.0,
     "preco_promocao": None, "curva": None, "ativo": 0},
    # so varejo, sem custo/curva -> v=varejo, q=1, sem chaves opcionais
    {"codigo": "8888", "descricao": "SO VAREJO 1KG", "embalagem": None,
     "custo_atual": None, "preco_atacado": None, "preco_varejo": 9.99,
     "preco_promocao": None, "curva": None, "ativo": 1},
]


def test_catalogo_bridge_json(tmp_path):
    caminho = str(tmp_path / "catalogo_bridge.json")
    n = projections.catalogo_bridge_json(CAT, caminho, "2026-07-07 05:00:00")
    with open(caminho, encoding="utf-8") as f:
        obj = json.load(f)
    assert obj["origem"] == "erp-bridge"
    assert obj["gerado_em"] == "2026-07-07 05:00:00"
    assert n == obj["total"] == len(obj["produtos"]) == 3
    por_c = {p["c"]: p for p in obj["produtos"]}
    assert por_c["2411"] == {"c": "2411", "p": "KELLOGGS SUCRILHOS 240G", "q": 1,
                             "v": 16.90, "custo": 14.20, "cv": "A"}
    assert por_c["2795"] == {"c": "2795", "p": "MINEIRINHO 250ML", "q": 24,
                             "v": 1.79, "vu": 2.49, "custo": 1.05, "cv": "B"}
    assert por_c["8888"] == {"c": "8888", "p": "SO VAREJO 1KG", "q": 1, "v": 9.99}
    # ordenado por descricao
    nomes = [p["p"] for p in obj["produtos"]]
    assert nomes == sorted(nomes)
```

- [ ] **Step 3: Rodar o teste e ver falhar**

Run: `python -m pytest tests/test_projections.py -v`
Expected: FAIL com `AttributeError: module 'projections' has no attribute 'catalogo_bridge_json'`

- [ ] **Step 4: Implementar em `src/projections.py`** (adicionar ao final do arquivo)

```python
# ---------- Consumidor 1b: Cotacao no claude.ai (catalogo_bridge.json) ----------

_NOMES_EXCLUIDOS = ("MORTO", "EXCLUIDO", "<<<")


def _preco(x):
    """Numero > 0 ou None (precos/custos vazios ou zerados viram None)."""
    if x is None:
        return None
    try:
        n = float(x)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def catalogo_bridge_json(catalogo, caminho, gerado_em):
    """Arquivo unico de importacao do app da cotacao (artifact no claude.ai).

    Mescla no mesmo criterio do upload manual do app (mesclarCatalogos):
      1) base = preco_varejo (q=1)
      2) promocao vence: se 0 < promo < v, v = promo
      3) atacado vence se menor: v = preco_atacado, q = embalagem, vu = varejo efetivo
    Fora: inativos, sem nenhum preco, e nomes MORTO/EXCLUIDO/<<< >>>.
    """
    produtos = []
    for r in catalogo:
        if not r.get("ativo", 1):
            continue
        cod = r.get("codigo")
        desc = str(r.get("descricao") or "").strip().upper()
        if cod is None or len(desc) < 4 or any(m in desc for m in _NOMES_EXCLUIDOS):
            continue
        v = _preco(r.get("preco_varejo"))
        q = 1
        vu = None
        promo = _preco(r.get("preco_promocao"))
        if promo and v and promo < v:
            v = promo  # promocao vence = desconto zero (spec)
        atacado = _preco(r.get("preco_atacado"))
        if atacado and (v is None or atacado < v):
            vu = v
            v = atacado
            try:
                q = max(1, int(r.get("embalagem") or 1))
            except (TypeError, ValueError):
                q = 1
        if v is None:
            continue
        item = {"c": cod, "p": desc, "q": q, "v": round(v, 2)}
        if vu is not None and round(vu, 2) != item["v"]:
            item["vu"] = round(vu, 2)
        custo = _preco(r.get("custo_atual"))
        if custo:
            item["custo"] = round(custo, 2)
        curva = str(r.get("curva") or "").strip().upper()
        if curva:
            item["cv"] = curva[0]
        produtos.append(item)
    produtos.sort(key=lambda x: x["p"])
    payload = {"origem": "erp-bridge", "gerado_em": gerado_em,
               "total": len(produtos), "produtos": produtos}
    _escrever_atomico(caminho, json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"))
    return len(produtos)
```

- [ ] **Step 5: Rodar o teste e ver passar**

Run: `python -m pytest tests/test_projections.py -v`
Expected: `1 passed`

- [ ] **Step 6: Commit**

```bash
git add tests/test_projections.py requirements-dev.txt src/projections.py
git commit -m "feat: projecao catalogo_bridge_json (arquivo unico da cotacao no claude.ai)"
```

---

### Task 2: Ligar a projeção no `bridge.py` + config

**Files:**
- Modify: `src/bridge.py:75-79` (bloco `if alvo in ("all", "catalogo")`)
- Modify: `config.example.json` (seções `saida` e `_saida_real_sugerida`)

**Interfaces:**
- Consumes: `projections.catalogo_bridge_json(cat, caminho, gerado_em)` (Task 1).
- Produces: chave de config `saida.cotacao_catalogo_bridge_json` (caminho do arquivo). Se ausente no config, a projeção é pulada (retrocompatível).

- [ ] **Step 1: Modificar o bloco `catalogo` em `src/bridge.py`**

Trocar o bloco atual:

```python
    if alvo in ("all", "catalogo"):
        n = projections.cotacao_produtos_json(cat, saida["cotacao_produtos_json"], gerado_em)
        rel.append(f"cotacao/produtos.json: {n}")
        n = projections.curva_abc_csv(cat, os.path.join(estoque, "curva_abc.csv"))
        rel.append(f"detector-estoque/curva_abc.csv: {n}")
```

por:

```python
    if alvo in ("all", "catalogo"):
        n = projections.cotacao_produtos_json(cat, saida["cotacao_produtos_json"], gerado_em)
        rel.append(f"cotacao/produtos.json: {n}")
        alvo_bridge = saida.get("cotacao_catalogo_bridge_json")
        if alvo_bridge:
            n = projections.catalogo_bridge_json(cat, alvo_bridge, gerado_em)
            rel.append(f"cotacao/catalogo_bridge.json: {n}")
        n = projections.curva_abc_csv(cat, os.path.join(estoque, "curva_abc.csv"))
        rel.append(f"detector-estoque/curva_abc.csv: {n}")
```

- [ ] **Step 2: Adicionar a chave no `config.example.json`**

Em `"saida"`, depois de `"cotacao_produtos_json"`, adicionar:

```json
    "cotacao_catalogo_bridge_json": "C:/Users/COMPUTADOR/erp-bridge-atacaderj/saida/cotacao/catalogo_bridge.json",
```

Em `"_saida_real_sugerida"`, depois de `"cotacao_produtos_json"`, adicionar:

```json
    "cotacao_catalogo_bridge_json": "C:/Users/COMPUTADOR/erp-bridge-atacaderj/saida/cotacao/catalogo_bridge.json",
```

- [ ] **Step 3: Testar com o demo**

Run: `python src/bridge.py --demo --only catalogo`
Expected: saída contém a linha `- cotacao/catalogo_bridge.json: 3` e o arquivo `saida/cotacao/catalogo_bridge.json` existe com `"origem": "erp-bridge"`.

- [ ] **Step 4: Rodar todos os testes**

Run: `python -m pytest tests/ -v`
Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add src/bridge.py config.example.json saida/cotacao/catalogo_bridge.json
git commit -m "feat: --only catalogo tambem gera catalogo_bridge.json (config: cotacao_catalogo_bridge_json)"
```

---

### Task 3: Validação do robô (`robo/validacao.py`) — testável sem Playwright

**Files:**
- Create: `robo/__init__.py` (vazio)
- Create: `robo/validacao.py`
- Test: `tests/test_robo_validacao.py`

**Interfaces:**
- Produces: `validacao.validar_arquivo(caminho: str) -> dict` (levanta `SystemExit` com mensagem clara se inválido/velho) e `validacao.carregar_config(pasta_robo: str) -> dict` (exige `artifact_url`, `arquivo_catalogo`, `perfil_dir` em `config_robo.json`).

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_robo_validacao.py`:

```python
# -*- coding: utf-8 -*-
import json
import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from robo import validacao  # noqa: E402


def _escrever(tmp_path, obj):
    caminho = str(tmp_path / "catalogo_bridge.json")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    return caminho


def test_arquivo_de_hoje_passa(tmp_path):
    hoje = datetime.now().strftime("%Y-%m-%d")
    caminho = _escrever(tmp_path, {"origem": "erp-bridge", "gerado_em": f"{hoje} 05:00:00",
                                   "total": 1, "produtos": [{"c": 1, "p": "X", "q": 1, "v": 1.0}]})
    obj = validacao.validar_arquivo(caminho)
    assert obj["total"] == 1


def test_arquivo_velho_falha(tmp_path):
    caminho = _escrever(tmp_path, {"origem": "erp-bridge", "gerado_em": "2020-01-01 05:00:00",
                                   "total": 1, "produtos": [{"c": 1, "p": "X", "q": 1, "v": 1.0}]})
    with pytest.raises(SystemExit):
        validacao.validar_arquivo(caminho)


def test_formato_errado_falha(tmp_path):
    caminho = _escrever(tmp_path, {"qualquer": "coisa"})
    with pytest.raises(SystemExit):
        validacao.validar_arquivo(caminho)


def test_config_incompleto_falha(tmp_path):
    with open(tmp_path / "config_robo.json", "w", encoding="utf-8") as f:
        json.dump({"artifact_url": "https://claude.ai/x"}, f)
    with pytest.raises(SystemExit):
        validacao.carregar_config(str(tmp_path))


def test_config_completo_passa(tmp_path):
    cfg = {"artifact_url": "https://claude.ai/x", "arquivo_catalogo": "c:/x.json",
           "perfil_dir": "c:/perfil"}
    with open(tmp_path / "config_robo.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    assert validacao.carregar_config(str(tmp_path)) == cfg
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_robo_validacao.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'robo'` (ou import de `validacao`).

- [ ] **Step 3: Implementar `robo/validacao.py`** (e criar `robo/__init__.py` vazio)

```python
# -*- coding: utf-8 -*-
"""Validacoes do robo de upload (separadas do Playwright para serem testaveis)."""

import json
import os
from datetime import datetime


def carregar_config(pasta_robo):
    caminho = os.path.join(pasta_robo, "config_robo.json")
    if not os.path.exists(caminho):
        raise SystemExit("[ERRO] Copie robo/config_robo.example.json para robo/config_robo.json e preencha.")
    with open(caminho, encoding="utf-8") as f:
        cfg = json.load(f)
    for chave in ("artifact_url", "arquivo_catalogo", "perfil_dir"):
        if not cfg.get(chave):
            raise SystemExit(f"[ERRO] Falta '{chave}' no robo/config_robo.json")
    return cfg


def validar_arquivo(caminho):
    """O arquivo precisa ser um catalogo_bridge.json gerado HOJE."""
    if not os.path.exists(caminho):
        raise SystemExit(f"[ERRO] Arquivo nao encontrado: {caminho} — rode o bridge antes.")
    with open(caminho, encoding="utf-8") as f:
        obj = json.load(f)
    if obj.get("origem") != "erp-bridge" or not obj.get("produtos"):
        raise SystemExit(f"[ERRO] {caminho} nao parece um catalogo_bridge.json (origem/produtos).")
    hoje = datetime.now().strftime("%Y-%m-%d")
    if not str(obj.get("gerado_em", "")).startswith(hoje):
        raise SystemExit(f"[ERRO] catalogo_bridge.json nao e de hoje (gerado_em={obj.get('gerado_em')}) "
                         f"— rode 'python src/bridge.py --only catalogo' antes.")
    return obj
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_robo_validacao.py -v`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add robo/__init__.py robo/validacao.py tests/test_robo_validacao.py
git commit -m "robo: validacoes (arquivo de hoje + config) com testes"
```

---

### Task 4: Robô Playwright (`robo/upload_catalogo.py`) + config + gitignore + README

**Files:**
- Create: `robo/upload_catalogo.py`
- Create: `robo/config_robo.example.json`
- Create: `robo/README.md`
- Modify: `.gitignore` (acrescentar linhas)

**Interfaces:**
- Consumes: `validacao.carregar_config`, `validacao.validar_arquivo` (Task 3); IDs do app da cotação: `#btnCatalogo` (já existe), `#catBridgeArq` e `#catConfirmar` (criados pelo plano do repo `cotacao-auditoria-atacaderj`). Chip de status: `#catalogBadge` (já existe; mostra "catálogo atualizado em dd/mm/aaaa").
- Produces: comando `python robo/upload_catalogo.py` (exit 0 = sucesso, 1 = falha; log em `robo/robo_upload.log`; screenshot `robo/ultima_falha.png` em falha) e `python robo/upload_catalogo.py --setup` (login único).

- [ ] **Step 1: Criar `robo/config_robo.example.json`**

```json
{
  "_comentario": "Copie para robo/config_robo.json (gitignored) e preencha o link do artifact.",
  "artifact_url": "https://claude.ai/artifacts/COLE-O-LINK-DO-ARTIFACT-AQUI",
  "arquivo_catalogo": "C:/Users/COMPUTADOR/erp-bridge-atacaderj/saida/cotacao/catalogo_bridge.json",
  "perfil_dir": "C:/Users/COMPUTADOR/erp-bridge-atacaderj/robo/perfil_navegador"
}
```

- [ ] **Step 2: Criar `robo/upload_catalogo.py`**

```python
# -*- coding: utf-8 -*-
"""Robo de upload: sobe o catalogo_bridge.json no artifact da cotacao (claude.ai).

Uso:
  python robo/upload_catalogo.py --setup   # abre o navegador para logar no claude.ai (1x)
  python robo/upload_catalogo.py           # rodada normal (agendada)

Requisitos (1x): pip install playwright && playwright install chromium
Config: robo/config_robo.json (copie de config_robo.example.json).
Sai com codigo 0 (sucesso) / 1 (falha). Log: robo/robo_upload.log.
"""
import argparse
import os
import sys
from datetime import datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
from robo import validacao  # noqa: E402


def log(msg):
    linha = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(linha)
    with open(os.path.join(AQUI, "robo_upload.log"), "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def main():
    ap = argparse.ArgumentParser(description="Sobe catalogo_bridge.json no artifact da cotacao")
    ap.add_argument("--setup", action="store_true",
                    help="abre o navegador para logar no claude.ai e salvar o perfil (rodar 1x)")
    args = ap.parse_args()
    cfg = validacao.carregar_config(AQUI)

    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            cfg["perfil_dir"], headless=False, accept_downloads=True,
            viewport={"width": 1280, "height": 900})
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        if args.setup:
            page.goto("https://claude.ai/")
            print("Logue na conta Claude. Quando terminar, FECHE o navegador.")
            print("O perfil fica salvo em:", cfg["perfil_dir"])
            try:
                page.wait_for_event("close", timeout=0)
            except Exception:
                pass
            return

        try:
            obj = validacao.validar_arquivo(cfg["arquivo_catalogo"])
            page.goto(cfg["artifact_url"], wait_until="domcontentloaded", timeout=60000)
            app = page.frame_locator("iframe").last  # o app roda num iframe do artifact
            app.locator("#btnCatalogo").click(timeout=90000)
            # onchange do input ja processa e mostra a previa com o botao de confirmar
            app.locator("#catBridgeArq").set_input_files(cfg["arquivo_catalogo"], timeout=30000)
            # confirmar dispara o download do snapshot da biblioteca — guardamos como backup
            with page.expect_download(timeout=120000) as dl:
                app.locator("#catConfirmar").click(timeout=60000)
            os.makedirs(os.path.join(AQUI, "backups"), exist_ok=True)
            dl.value.save_as(os.path.join(
                AQUI, "backups", f"biblioteca-{datetime.now():%Y%m%d-%H%M%S}.json"))
            # verificacao: o chip do catalogo tem que mostrar a data de HOJE
            chip = app.locator("#catalogBadge")
            chip.wait_for(state="visible", timeout=30000)
            hoje_br = datetime.now().strftime("%d/%m/%Y")
            texto = chip.text_content() or ""
            if hoje_br not in texto:
                raise RuntimeError(f"chip do catalogo nao confirma a data de hoje: {texto!r}")
            log(f"OK  {obj['total']} produtos ({obj['gerado_em']}) enviados ao artifact")
        except (PWTimeout, RuntimeError, SystemExit) as e:
            log(f"FALHA  {e}")
            try:
                page.screenshot(path=os.path.join(AQUI, "ultima_falha.png"), full_page=True)
            except Exception:
                pass
            ctx.close()
            sys.exit(1)
        ctx.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Criar `robo/README.md`**

```markdown
# Robô de upload — cotação no claude.ai

Sobe o `catalogo_bridge.json` (gerado pelo bridge) no artifact da cotação,
pelo botão "📦 Catálogo" do próprio app. Determinístico (Playwright), sem IA.

## Instalação (1x, no PC-ponte)
1. `pip install -r requirements-dev.txt` e `playwright install chromium`
2. `copy robo\config_robo.example.json robo\config_robo.json` e colar o link do artifact
3. `python robo/upload_catalogo.py --setup` → logar na conta Claude → fechar o navegador
4. Testar: `python src/bridge.py --only catalogo` e depois `python robo/upload_catalogo.py`
   (assistir a primeira rodada; ajustar o seletor do iframe se o claude.ai mudar o layout)

## Operação
- Agendado por `scripts/register-tasks.ps1` (20min após cada rodada do catálogo).
- A tarefa PRECISA rodar "somente quando o usuário estiver conectado" (navegador visível).
- Falha → exit 1 + `robo_upload.log` + `ultima_falha.png`. O app acusa banco velho na
  tela (trava de data) — plano B: subir o arquivo manualmente pelo botão 📦 (30s).
- O download salvo em `robo/backups/` é o snapshot da biblioteca que o app exporta ao
  substituir o catálogo (backup dos apelidos/buscas aprendidos).
```

- [ ] **Step 4: Acrescentar ao `.gitignore`**

```text
robo/config_robo.json
robo/perfil_navegador/
robo/robo_upload.log
robo/ultima_falha.png
robo/backups/
```

- [ ] **Step 5: Smoke test (sem navegador)**

Run: `python robo/upload_catalogo.py --help`
Expected: mostra a ajuda e sai. (O import do Playwright acontece dentro de `main`, DEPOIS do
`parse_args` e do `carregar_config` — então `--help` e o erro de config funcionam mesmo sem
o Playwright instalado.)

Run: `python robo/upload_catalogo.py` (sem config_robo.json)
Expected: `[ERRO] Copie robo/config_robo.example.json para robo/config_robo.json e preencha.` e exit ≠ 0.

- [ ] **Step 6: Rodar todos os testes e commit**

Run: `python -m pytest tests/ -v`
Expected: todos passam.

```bash
git add robo/upload_catalogo.py robo/config_robo.example.json robo/README.md .gitignore
git commit -m "robo: upload do catalogo_bridge.json no artifact (Playwright, perfil persistente)"
```

---

### Task 5: Tarefas agendadas (`scripts/register-tasks.ps1`)

**Files:**
- Modify: `scripts/register-tasks.ps1`

**Interfaces:**
- Consumes: `robo/upload_catalogo.py` (Task 4); tarefa existente "AtacadeRJ - Bridge Catalogo".
- Produces: catálogo também às 05:00; nova tarefa "AtacadeRJ - Robo Upload Cotacao" 20min após cada rodada do catálogo.

- [ ] **Step 1: Adicionar o gatilho 05:00 ao catálogo**

No array `$gatCat`, adicionar como primeira linha:

```powershell
  New-ScheduledTaskTrigger -Daily -At 05:00
```

E atualizar o `Write-Host` correspondente para `"OK: 'AtacadeRJ - Bridge Catalogo' (05/08/12/15/18h)"`.

- [ ] **Step 2: Adicionar a Tarefa 3 (robô), antes do `Write-Host` final**

```powershell
# --- Tarefa 3: ROBO UPLOAD COTACAO (sobe catalogo_bridge.json no artifact) ---
# 20min apos cada rodada do catalogo. IMPORTANTE: o robo abre um navegador,
# entao a tarefa roda "somente quando o usuario estiver conectado" (padrao do
# Register-ScheduledTask sem -User/-Password). O PC-ponte fica logado 24h.
$robo = Join-Path $raiz "robo\upload_catalogo.py"
$acaoRobo = New-ScheduledTaskAction -Execute $python -Argument "`"$robo`"" -WorkingDirectory $raiz
$gatRobo = @(
  New-ScheduledTaskTrigger -Daily -At 05:20
  New-ScheduledTaskTrigger -Daily -At 08:20
  New-ScheduledTaskTrigger -Daily -At 12:20
  New-ScheduledTaskTrigger -Daily -At 15:20
  New-ScheduledTaskTrigger -Daily -At 18:20
)
Register-ScheduledTask -TaskName "AtacadeRJ - Robo Upload Cotacao" -Action $acaoRobo `
  -Trigger $gatRobo -RunLevel Limited -Force | Out-Null
Write-Host "OK: 'AtacadeRJ - Robo Upload Cotacao' (05:20/08:20/12:20/15:20/18:20)"
```

- [ ] **Step 3: Validar a sintaxe do script (sem registrar)**

Run: `powershell -NoProfile -Command "[scriptblock]::Create((Get-Content -Raw scripts/register-tasks.ps1)) | Out-Null; 'sintaxe OK'"`
Expected: `sintaxe OK`

- [ ] **Step 4: Commit**

```bash
git add scripts/register-tasks.ps1
git commit -m "robo: tarefa agendada de upload (5x/dia, 20min apos o catalogo) + catalogo as 05:00"
```

---

### Task 6: STATUS.md + push

**Files:**
- Modify: `STATUS.md` (checklist + log)

- [ ] **Step 1: Atualizar o checklist** — marcar `[x]` no item "Ligar a cotação: bridge gera catalogo_bridge.json" e no item do robô escrever `(código pronto — falta implantação no PC-ponte)`.

- [ ] **Step 2: Adicionar linha no Log de progresso** com a data, citando: projeção + robô + tarefas prontos; pendências: executar o plano do repo `cotacao-auditoria-atacaderj` (botão do app) e a implantação manual abaixo.

- [ ] **Step 3: Commit e push**

```bash
git add STATUS.md
git commit -m "docs: status — catalogo_bridge + robo implementados (falta implantacao)"
git push
```

---

## Implantação (manual — fora do escopo de código; guiar pelo `robo/README.md`)

Estes passos são feitos por você (com o Claude Code do PC-ponte ajudando), **depois**
de executar também o plano do repo `cotacao-auditoria-atacaderj` e republicar o app:

- [ ] Publicar/atualizar o app como artifact na conta Claude (com as mudanças do outro
  plano) e copiar o link fixo.
- [ ] No PC-ponte: `git pull`, `pip install -r requirements-dev.txt`,
  `playwright install chromium`.
- [ ] `copy robo\config_robo.example.json robo\config_robo.json` + colar o link do artifact
  (e conferir os caminhos).
- [ ] `python robo/upload_catalogo.py --setup` → logar na conta Claude → fechar.
- [ ] Rodada assistida: `python src/bridge.py --only catalogo` e
  `python robo/upload_catalogo.py` **assistindo** — se o seletor do iframe falhar,
  ajustar `page.frame_locator("iframe").last` em `robo/upload_catalogo.py`.
- [ ] `./scripts/register-tasks.ps1` em PowerShell **Admin**.
- [ ] Marcar os itens no `STATUS.md`, commit e push.
