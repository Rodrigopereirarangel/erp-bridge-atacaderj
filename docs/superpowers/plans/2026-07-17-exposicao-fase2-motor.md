# Exposição MÍN/MÁX — Fase 2: o motor (`exposicao-atacaderj`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repo novo `exposicao-atacaderj` que lê os CSVs da Fase 1 e entrega, por item, a quantidade **MÍN** e **MÁX** de exposição na prateleira — em unidades e em caixas-mãe — num PDF agrupado por prateleira, enviado no WhatsApp, mensal.

**Architecture:** Pipeline linear de módulos isolados. A venda diária limpa (sem domingo, sem feriado, sem dia de ruptura) alimenta uma **binomial negativa por item** com peso de dia-da-semana; o Monte Carlo devolve a distribuição da demanda de 7 e de 30 dias corridos; um **backtest calibra** a otimismo do modelo num fator `λ`; e a **escada** sobe caixa a caixa até a confiança cruzar 95%. A caixa-mãe só aparece no último passo.

**Tech Stack:** Python 3.12, numpy 2.5, scipy 1.18, pandas 3.0 (todos já instalados no ponte), pytest. PDF via Edge headless. WhatsApp via o Baileys já logado do bridge.

**Spec:** `erp-bridge-atacaderj/docs/superpowers/specs/2026-07-17-exposicao-min-max-design.md`

## Global Constraints

- **Pré-requisito:** a Fase 1 (`2026-07-17-exposicao-fase1-bridge.md`) tem que estar **inteira pronta**, com a reconciliação batendo no ponte. Sem isso o modelo é construído sobre número errado.
- **Este repo NUNCA toca o banco.** Só lê CSV. A porta do banco é o bridge (spec D13).
- **Todo o cálculo em UNIDADES.** A caixa-mãe entra **só** no módulo `escada`/`minmax` (spec D8). Nenhum outro módulo importa `caixa_mae`.
- **Dois filtros, duas perguntas** (spec D3/D4): o **giro** usa só `canal == "salao"`; o **saldo de estoque** (censura) usa **todos os canais**. Confundir os dois é o erro mais caro possível aqui — o atacado é 44% do volume.
- **Nada trava a entrega** (spec D16). Calibração que não alcança o limiar → entrega com `λ = lambdaMax` e a cobertura real estampada. Item que não cruza em `escada.maxCaixas` → entrega no teto, marcado.
- **Piso de 1 caixa-mãe sempre** (spec D2), para todo item do cadastro (spec D9).
- **Nunca commitar** telefone, senha, custo ou preço. Segredo só em `config.local.json` (gitignored).
- **Reprodutibilidade:** toda amostragem usa `numpy.random.default_rng(cfg["simulacao"]["semente"])`. Rodar 2× dá o mesmo número.
- **Testes:** `tests/test_*.py`, rodados com `python -m pytest tests/ -v`.

## Estrutura de arquivos

| Arquivo | Responsabilidade única |
|---|---|
| `src/config.py` | carrega `config.local.json` sobre os defaults de `config.example.json` |
| `src/importar.py` | lê os 3 CSVs → estruturas internas; valida layout |
| `src/calendario.py` | grade de dias abertos (sem domingo, sem feriado) |
| `src/censura.py` | marca dias de ruptura de estoque (4 sinais) |
| `src/dow.py` | fatores de dia-da-semana por categoria, encolhidos |
| `src/modelo.py` | ajusta binomial negativa por item |
| `src/simular.py` | Monte Carlo → distribuição da demanda do horizonte |
| `src/escada.py` | **função pura**: menor nº de caixas com confiança ≥ limiar |
| `src/calibrar.py` | backtest → fator `λ`; bootstrap → aferição |
| `src/minmax.py` | monta a linha final de cada item |
| `src/relatorio.py` | HTML → PDF por prateleira |
| `src/enviar.py` | delega ao Baileys do bridge; respeita `dryRun` |
| `src/rodar.py` | orquestrador (CLI) |

**Ordem de dependência (não inverter):** `escada` não importa ninguém. `calibrar` **chama** `escada`. `minmax` **chama** `escada`. Se `calibrar` e `minmax` se importarem, há ciclo.

---

### Task 1: Scaffold + `config` + `importar`

**Files:**
- Create: `README.md`, `.gitignore`, `config.example.json`, `src/config.py`, `src/importar.py`
- Test: `tests/test_importar.py`

**Interfaces:**
- Produces:
  - `config.carregar(caminho: str | None = None) -> dict` — defaults do `config.example.json` sobrepostos pelo `config.local.json`.
  - `importar.ler_vendas(caminho) -> dict[int, dict[str, dict[str, float]]]` — `{codigo: {data_iso: {"salao": un, "atacado": un}}}`.
  - `importar.ler_catalogo(caminho) -> dict[int, dict]` — `{codigo: {"descricao", "caixa_mae": int, "prateleira": str, "curva": str|None}}`.
  - `importar.ler_entradas(caminho) -> dict[int, list[dict]]` — `{codigo: [{"data": iso, "qtd": float}, ...]}` ordenado por data.

- [ ] **Step 1: Write the failing test**

Crie `tests/test_importar.py`:

```python
# -*- coding: utf-8 -*-
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import importar  # noqa: E402
import pytest    # noqa: E402


def _csv(d, nome, texto):
    caminho = os.path.join(d, nome)
    with open(caminho, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)
    return caminho


def test_ler_vendas_separa_os_dois_canais():
    with tempfile.TemporaryDirectory() as d:
        c = _csv(d, "v.csv",
                 "codigo;data;canal;unidades\n"
                 "18464;2026-07-14;salao;225\n"
                 "18464;2026-07-14;atacado;1462\n"
                 "18464;2026-07-15;salao;200\n")
        v = importar.ler_vendas(c)
        assert v[18464]["2026-07-14"] == {"salao": 225.0, "atacado": 1462.0}
        assert v[18464]["2026-07-15"] == {"salao": 200.0, "atacado": 0.0}


def test_ler_vendas_soma_linhas_repetidas():
    with tempfile.TemporaryDirectory() as d:
        c = _csv(d, "v.csv",
                 "codigo;data;canal;unidades\n"
                 "1;2026-07-14;salao;10\n"
                 "1;2026-07-14;salao;5\n")
        assert importar.ler_vendas(c)[1]["2026-07-14"]["salao"] == 15.0


def test_ler_vendas_recusa_canal_desconhecido():
    with tempfile.TemporaryDirectory() as d:
        c = _csv(d, "v.csv", "codigo;data;canal;unidades\n1;2026-07-14;loja;10\n")
        with pytest.raises(ValueError, match="canal"):
            importar.ler_vendas(c)


def test_ler_vendas_recusa_coluna_faltando():
    with tempfile.TemporaryDirectory() as d:
        c = _csv(d, "v.csv", "codigo;data;unidades\n1;2026-07-14;10\n")
        with pytest.raises(ValueError, match="canal"):
            importar.ler_vendas(c)


def test_ler_catalogo():
    with tempfile.TemporaryDirectory() as d:
        c = _csv(d, "c.csv",
                 "codigo;descricao;caixa_mae;prateleira;curva\n"
                 "34743;QUALY 500G;12;PRATELEIRA 33;A\n"
                 "9;SEM ENDERECO;6;;\n")
        cat = importar.ler_catalogo(c)
        assert cat[34743] == {"descricao": "QUALY 500G", "caixa_mae": 12,
                              "prateleira": "PRATELEIRA 33", "curva": "A"}
        assert cat[9]["caixa_mae"] == 6
        assert cat[9]["prateleira"] == ""
        assert cat[9]["curva"] is None


def test_ler_catalogo_recusa_caixa_mae_invalida():
    with tempfile.TemporaryDirectory() as d:
        c = _csv(d, "c.csv", "codigo;descricao;caixa_mae;prateleira;curva\n1;X;0;P;A\n")
        with pytest.raises(ValueError, match="caixa_mae"):
            importar.ler_catalogo(c)


def test_ler_entradas_ordenado_por_data():
    with tempfile.TemporaryDirectory() as d:
        c = _csv(d, "e.csv",
                 "codigo;data;qtd\n1;2026-07-10;100\n1;2026-06-01;50\n")
        e = importar.ler_entradas(c)
        assert [x["data"] for x in e[1]] == ["2026-06-01", "2026-07-10"]
        assert e[1][0]["qtd"] == 50.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_importar.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'importar'`

- [ ] **Step 3: Write minimal implementation**

Crie `.gitignore`:

```
config.local.json
data/
saida/
__pycache__/
*.pyc
```

Crie `config.example.json`:

```json
{
  "_comentario": "Copie para config.local.json e preencha. config.local.json NAO e versionado (tem o telefone).",

  "entrada": {
    "_comentario": "os CSVs que o erp-bridge-atacaderj gera com --only exposicao",
    "vendas_canal_csv": "C:/Users/User/erp-bridge-atacaderj/saida/exposicao/vendas_canal.csv",
    "catalogo_csv": "C:/Users/User/erp-bridge-atacaderj/saida/exposicao/catalogo_exposicao.csv",
    "entradas_csv": "C:/Users/User/erp-bridge-atacaderj/saida/detector-salao/entradas.csv"
  },

  "calendario": { "diaFechadoFracao": 0.2 },

  "censura": {
    "_comentario": "ruptura de ESTOQUE. So censura com os 4 sinais (99% de certeza): na duvida o dia FICA. Remover um zero legitimo INFLA o min e enche a prateleira — o erro caro.",
    "kIntervalo": 2,
    "razaoEsgotamento": 1.0,
    "exigeRetroConfirmacao": true
  },

  "dow": { "pesoEncolhimento": 200 },
  "modelo": { "minDiasLimpos": 30 },
  "simulacao": { "sorteios": 20000, "semente": 42 },

  "percentil": 0.95,
  "horizonte": { "minDiasCorridos": 7, "maxDiasCorridos": 30 },
  "escada": { "maxCaixas": 500 },
  "calibracao": { "lambdaMax": 3.0, "tol": 0.01 },

  "validacao": {
    "giroMinimo": 1.0,
    "minJanelas": 12,
    "tolBootstrap": 0.15,
    "semanasHoldout": 8
  },

  "whatsapp": {
    "_comentario": "dryRun true = NAO envia (padrao ate o dono validar os numeros). enviarMjs = o Baileys ja logado do bridge.",
    "dryRun": true,
    "destino": "",
    "enviarMjs": "C:/Users/User/erp-bridge-atacaderj/scripts/whatsapp/enviar.mjs"
  },

  "saida": { "dir": "saida" }
}
```

Crie `src/config.py`:

```python
# -*- coding: utf-8 -*-
"""Config: defaults do config.example.json, sobrepostos pelo config.local.json."""
import json
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _mesclar(base, sobre):
    for k, v in sobre.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _mesclar(base[k], v)
        else:
            base[k] = v
    return base


def carregar(caminho=None):
    with open(os.path.join(RAIZ, "config.example.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    caminho = caminho or os.path.join(RAIZ, "config.local.json")
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            _mesclar(cfg, json.load(f))
    return cfg
```

Crie `src/importar.py`:

```python
# -*- coding: utf-8 -*-
"""Le os CSVs do bridge. Valida layout e da erro CLARO se divergir — melhor
quebrar aqui do que entregar min/max errado para o salao executar."""
import csv

CANAIS = ("salao", "atacado")


def _abrir(caminho, obrigatorias):
    f = open(caminho, encoding="utf-8", newline="")
    leitor = csv.DictReader(f, delimiter=";")
    faltando = [c for c in obrigatorias if c not in (leitor.fieldnames or [])]
    if faltando:
        f.close()
        raise ValueError(
            f"{caminho}: faltam as colunas {faltando}. "
            f"Achei: {leitor.fieldnames}. O bridge mudou de layout?")
    return f, leitor


def ler_vendas(caminho):
    """{codigo: {data_iso: {"salao": un, "atacado": un}}}

    Os dois canais ficam SEPARADOS de proposito: o giro da prateleira usa so
    'salao' (a venda de atacado nao sai da gondola — sao 44% do volume, e
    incluir infla o giro ~78%), mas o saldo de estoque da censura usa OS DOIS
    (a caixa vendida no atacado consome o mesmo estoque). Spec D3/D4."""
    f, leitor = _abrir(caminho, ("codigo", "data", "canal", "unidades"))
    try:
        out = {}
        for ln in leitor:
            canal = (ln["canal"] or "").strip()
            if canal not in CANAIS:
                raise ValueError(
                    f"{caminho}: canal desconhecido {canal!r} (esperado {CANAIS})")
            cod = int(ln["codigo"])
            dia = (ln["data"] or "")[:10]
            d = out.setdefault(cod, {}).setdefault(dia, {"salao": 0.0, "atacado": 0.0})
            d[canal] += float(ln["unidades"])
        return out
    finally:
        f.close()


def ler_catalogo(caminho):
    """{codigo: {descricao, caixa_mae, prateleira, curva}}

    caixa_mae vem do CADASTRO (spec D7) — nunca da nota de entrada."""
    f, leitor = _abrir(caminho, ("codigo", "descricao", "caixa_mae", "prateleira", "curva"))
    try:
        out = {}
        for ln in leitor:
            caixa = int(float(ln["caixa_mae"]))
            if caixa <= 0:
                raise ValueError(
                    f"{caminho}: item {ln['codigo']} com caixa_mae={caixa}. "
                    f"O bridge deveria ter filtrado — sem caixa-mae nao da para arredondar.")
            out[int(ln["codigo"])] = {
                "descricao": ln["descricao"],
                "caixa_mae": caixa,
                "prateleira": (ln["prateleira"] or "").strip(),
                "curva": (ln["curva"] or "").strip() or None,
            }
        return out
    finally:
        f.close()


def ler_entradas(caminho):
    """{codigo: [{"data": iso, "qtd": un}, ...]} ordenado por data.
    So a censura usa isto (nunca a caixa-mae — spec D7)."""
    f, leitor = _abrir(caminho, ("codigo", "data", "qtd"))
    try:
        out = {}
        for ln in leitor:
            out.setdefault(int(ln["codigo"]), []).append(
                {"data": (ln["data"] or "")[:10], "qtd": float(ln["qtd"])})
        for v in out.values():
            v.sort(key=lambda r: r["data"])
        return out
    finally:
        f.close()
```

Crie `README.md`:

```markdown
# exposicao-atacaderj

Calcula a quantidade **MÍN** e **MÁX** de exposição na prateleira de cada item da loja,
em unidades e em caixas-mãe. Entrega um PDF por prateleira no WhatsApp, mensal.

- **MÍN** = menor nº de caixas com ≥95% de confiança de cobrir **7 dias corridos**.
- **MÁX** = menor nº de caixas com ≥95% de confiança de cobrir **30 dias corridos**
  (o horizonte de 30d é o critério de rotação do dono: acima disso, avaria/validade).
- Piso absoluto: **1 caixa-mãe**.

Não toca o banco: lê os CSVs que o `erp-bridge-atacaderj` gera com `--only exposicao`.

**Spec (fonte da verdade):**
`erp-bridge-atacaderj/docs/superpowers/specs/2026-07-17-exposicao-min-max-design.md`

## Rodar

    cp config.example.json config.local.json   # e preencher
    python src/rodar.py                        # calcula e (se dryRun=false) envia
    python src/rodar.py --dry-run              # forca dryRun

## Testes

    python -m pytest tests/ -v
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_importar.py -v`
Expected: PASS — 7 passed

- [ ] **Step 5: Commit**

```bash
git init 2>/dev/null; git add -A
git commit -m "feat: scaffold + config + importar (le os CSVs do bridge)"
```

---

### Task 2: `calendario` — dias abertos

**Files:**
- Create: `src/calendario.py`
- Test: `tests/test_calendario.py`

**Interfaces:**
- Consumes: `importar.ler_vendas` (Task 1).
- Produces:
  - `calendario.construir(vendas: dict, cfg: dict) -> dict` com `{"dias": list[str] (ISO, ordenado), "indice": dict[str, int], "fechados": list[str]}`.
  - `calendario.janela_do_item(vendas_item: dict, cal: dict) -> tuple[int, int] | None` — índices (inclusivos) do primeiro e do último dia de venda do item em `cal["dias"]`; `None` se nunca vendeu.

**Contexto:** porta da lógica já em produção em `detector-ruptura-atacaderj/src/detect/calendar.js`. Domingo fora (verificado: **zero venda em 90 dias**). Feriado = dia cujo nº de itens distintos vendidos < `diaFechadoFracao` × mediana dos dias com venda. Detectar dos **dados**, não de regra fixa — a loja pode abrir num domingo atípico.

- [ ] **Step 1: Write the failing test**

Crie `tests/test_calendario.py`:

```python
# -*- coding: utf-8 -*-
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import calendario  # noqa: E402

CFG = {"calendario": {"diaFechadoFracao": 0.2}}


def _vendas(dias_itens):
    """dias_itens: {data_iso: n_itens_distintos} -> estrutura de vendas."""
    v = {}
    for dia, n in dias_itens.items():
        for cod in range(n):
            v.setdefault(cod, {})[dia] = {"salao": 1.0, "atacado": 0.0}
    return v


def test_domingo_fica_de_fora():
    # 2026-07-12 e um domingo
    v = _vendas({"2026-07-10": 100, "2026-07-11": 100, "2026-07-12": 100,
                 "2026-07-13": 100})
    cal = calendario.construir(v, CFG)
    assert "2026-07-12" not in cal["dias"]
    assert "2026-07-11" in cal["dias"] and "2026-07-13" in cal["dias"]


def test_feriado_detectado_pelo_movimento():
    dias = {}
    d = date(2026, 6, 1)
    while d <= date(2026, 6, 30):
        if d.weekday() != 6:
            dias[d.isoformat()] = 100
        d += timedelta(days=1)
    dias["2026-06-15"] = 3          # feriado: quase nada vendeu
    cal = calendario.construir(_vendas(dias), CFG)
    assert "2026-06-15" in cal["fechados"]
    assert "2026-06-15" not in cal["dias"]


def test_dia_fraco_legitimo_nao_vira_feriado():
    # 30% da mediana esta acima do corte de 20% -> continua sendo dia aberto
    dias = {}
    d = date(2026, 6, 1)
    while d <= date(2026, 6, 30):
        if d.weekday() != 6:
            dias[d.isoformat()] = 100
        d += timedelta(days=1)
    dias["2026-06-15"] = 30
    cal = calendario.construir(_vendas(dias), CFG)
    assert "2026-06-15" in cal["dias"]


def test_indice_e_contiguo_e_ordenado():
    v = _vendas({"2026-07-13": 10, "2026-07-14": 10, "2026-07-15": 10})
    cal = calendario.construir(v, CFG)
    assert cal["dias"] == sorted(cal["dias"])
    assert [cal["indice"][d] for d in cal["dias"]] == list(range(len(cal["dias"])))


def test_janela_do_item_vai_da_primeira_a_ultima_venda():
    dias = ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04", "2026-06-05"]
    cal = {"dias": dias, "indice": {d: i for i, d in enumerate(dias)}, "fechados": []}
    item = {"2026-06-02": {"salao": 1.0, "atacado": 0.0},
            "2026-06-04": {"salao": 2.0, "atacado": 0.0}}
    assert calendario.janela_do_item(item, cal) == (1, 3)


def test_janela_do_item_conta_venda_de_qualquer_canal():
    # o item existiu no dia em que so o atacado o levou
    dias = ["2026-06-01", "2026-06-02", "2026-06-03"]
    cal = {"dias": dias, "indice": {d: i for i, d in enumerate(dias)}, "fechados": []}
    item = {"2026-06-01": {"salao": 0.0, "atacado": 5.0},
            "2026-06-03": {"salao": 1.0, "atacado": 0.0}}
    assert calendario.janela_do_item(item, cal) == (0, 2)


def test_janela_do_item_none_se_nunca_vendeu():
    dias = ["2026-06-01", "2026-06-02"]
    cal = {"dias": dias, "indice": {d: i for i, d in enumerate(dias)}, "fechados": []}
    assert calendario.janela_do_item({}, cal) is None
    assert calendario.janela_do_item(
        {"2026-06-01": {"salao": 0.0, "atacado": 0.0}}, cal) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_calendario.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'calendario'`

- [ ] **Step 3: Write minimal implementation**

Crie `src/calendario.py`:

```python
# -*- coding: utf-8 -*-
"""Grade de dias ABERTOS. Porta de detector-ruptura-atacaderj/src/detect/calendar.js
(logica ja em producao).

Domingo fora: verificado em 17/07/2026 que a loja tem ZERO venda em domingo nos
ultimos 90 dias. Feriado nao vem de lista fixa — sai dos DADOS (dia com poucos
itens distintos vendidos), porque a loja pode abrir num feriado ou fechar num
dia qualquer, e uma lista fixa mentiria."""
from datetime import date, timedelta


def _d(iso):
    a, m, di = iso.split("-")
    return date(int(a), int(m), int(di))


def construir(vendas, cfg):
    fracao = cfg["calendario"]["diaFechadoFracao"]

    distintos = {}
    for por_dia in vendas.values():
        for dia, canais in por_dia.items():
            if canais["salao"] + canais["atacado"] > 0:
                distintos[dia] = distintos.get(dia, 0) + 1
    if not distintos:
        return {"dias": [], "indice": {}, "fechados": []}

    contagens = sorted(distintos.values())
    mediana = contagens[len(contagens) // 2]
    corte = fracao * mediana

    dias, fechados = [], []
    cur, fim = _d(min(distintos)), _d(max(distintos))
    while cur <= fim:
        iso = cur.isoformat()
        if cur.weekday() != 6:  # 6 = domingo
            if mediana > 0 and distintos.get(iso, 0) >= corte:
                dias.append(iso)
            else:
                fechados.append(iso)
        cur += timedelta(days=1)

    return {"dias": dias, "indice": {d: i for i, d in enumerate(dias)},
            "fechados": fechados}


def janela_do_item(vendas_item, cal):
    """(i_inicio, i_fim) INCLUSIVO em cal["dias"], da primeira a ultima venda do
    item. None se nunca vendeu.

    Existe para nao contar ZERO FANTASMA: um item cadastrado mes passado nao
    "vendeu zero" nos 150 dias anteriores — ele nao existia. Sem esta janela, o
    giro dele sairia diluido por 150 dias, o min travaria em 1 caixa e o item
    novo nunca ganharia prateleira.

    Conta venda de QUALQUER canal: se so o atacado levou naquele dia, o item
    existia igual."""
    idx = [i for i, d in enumerate(cal["dias"])
           if (vendas_item.get(d) or {"salao": 0.0, "atacado": 0.0})["salao"]
           + (vendas_item.get(d) or {"salao": 0.0, "atacado": 0.0})["atacado"] > 0]
    return (idx[0], idx[-1]) if idx else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_calendario.py -v`
Expected: PASS — 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/calendario.py tests/test_calendario.py
git commit -m "feat: calendario (sem domingo, feriado detectado dos dados)"
```

---

### Task 3: `censura` — ruptura de estoque, 4 sinais

**Files:**
- Create: `src/censura.py`
- Test: `tests/test_censura.py`

**Interfaces:**
- Consumes: `importar.ler_vendas`, `importar.ler_entradas` (Task 1); `calendario.construir` (Task 2).
- Produces: `censura.dias_censurados(codigo, vendas_item: dict, entradas_item: list, cal: dict, cfg: dict) -> set[str]` — conjunto de datas ISO a **descartar** do cálculo do giro.

**Contexto (spec §6.2 — leia antes de codar):** um dia só sai com **os 4 sinais**:
1. Zero venda no dia, somando **todos os canais** (D4 — a caixa do atacado consome o mesmo estoque).
2. A sequência de zeros que contém o dia é longa **para aquele item**: `≥ kIntervalo × intervalo típico` (EWMA dos gaps do próprio item).
3. Estoque esgotado: vendas acumuladas de **todos os canais** desde a última entrega `≥ razaoEsgotamento ×` quantidade entregue.
4. Retro-confirmação: a sequência **termina com uma entrega** e a venda volta depois.

**Por que os 4:** os detectores decidem *no presente* e não sabem o que vem depois. Este cálculo olha o **passado** — o retrovisor do sinal 4 é a prova que eles não têm, e é o que torna 99% de certeza real.

**A direção do viés é deliberada e não deve ser "melhorada":** manter por engano um dia fraco encolhe um pouco o mín. Remover por engano um zero legítimo **infla** o mín e enche a prateleira de mercadoria parada — a avaria/validade que o MÁX existe para evitar. **Na dúvida, o dia fica.**

- [ ] **Step 1: Write the failing test**

Crie `tests/test_censura.py`:

```python
# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import censura  # noqa: E402

CFG = {"censura": {"kIntervalo": 2, "razaoEsgotamento": 1.0, "exigeRetroConfirmacao": True}}


def _cal(dias):
    return {"dias": dias, "indice": {d: i for i, d in enumerate(dias)}, "fechados": []}


DIAS = [f"2026-06-{d:02d}" for d in range(1, 29) if d % 7 != 0]  # ~24 dias uteis


def _vendas(por_dia):
    return {d: {"salao": v, "atacado": 0.0} for d, v in por_dia.items()}


def test_os_4_sinais_juntos_censuram():
    # vende todo dia, entrega de 20 un no dia 1 (esgota em 20 dias de 1/dia),
    # some por muito tempo, e a venda so volta depois de nova entrega
    v = {d: 1.0 for d in DIAS[:6]}
    for d in DIAS[6:18]:
        v[d] = 0.0
    for d in DIAS[18:]:
        v[d] = 1.0
    ent = [{"data": DIAS[0], "qtd": 6.0}, {"data": DIAS[17], "qtd": 20.0}]
    fora = censura.dias_censurados(1, _vendas(v), ent, _cal(DIAS), CFG)
    assert DIAS[10] in fora
    assert DIAS[0] not in fora and DIAS[20] not in fora


def test_item_lento_com_zero_natural_nunca_e_censurado():
    # vende 1x a cada ~10 dias: o zero e o estado normal dele
    v = {d: (1.0 if i % 10 == 0 else 0.0) for i, d in enumerate(DIAS)}
    ent = [{"data": DIAS[0], "qtd": 100.0}]
    assert censura.dias_censurados(1, _vendas(v), ent, _cal(DIAS), CFG) == set()


def test_sem_retro_confirmacao_nao_censura():
    # parou e NUNCA voltou: pode ser fora de linha, nao ruptura
    v = {d: 1.0 for d in DIAS[:6]}
    for d in DIAS[6:]:
        v[d] = 0.0
    ent = [{"data": DIAS[0], "qtd": 6.0}]
    assert censura.dias_censurados(1, _vendas(v), ent, _cal(DIAS), CFG) == set()


def test_estoque_nao_esgotado_nao_censura():
    # entregou 1000 un e vendeu 6: ainda tem estoque -> o silencio e outra coisa
    v = {d: 1.0 for d in DIAS[:6]}
    for d in DIAS[6:18]:
        v[d] = 0.0
    for d in DIAS[18:]:
        v[d] = 1.0
    ent = [{"data": DIAS[0], "qtd": 1000.0}, {"data": DIAS[17], "qtd": 20.0}]
    assert censura.dias_censurados(1, _vendas(v), ent, _cal(DIAS), CFG) == set()


def test_venda_de_atacado_conta_no_esgotamento():
    # o salao vendeu pouco, mas o atacado levou a entrega inteira -> esgotou
    v = {}
    for d in DIAS[:6]:
        v[d] = {"salao": 1.0, "atacado": 0.0}
    v[DIAS[0]] = {"salao": 1.0, "atacado": 100.0}   # atacado levou tudo
    for d in DIAS[6:18]:
        v[d] = {"salao": 0.0, "atacado": 0.0}
    for d in DIAS[18:]:
        v[d] = {"salao": 1.0, "atacado": 0.0}
    ent = [{"data": DIAS[0], "qtd": 100.0}, {"data": DIAS[17], "qtd": 20.0}]
    fora = censura.dias_censurados(1, v, ent, _cal(DIAS), CFG)
    assert DIAS[10] in fora, "o atacado consome o mesmo estoque (spec D4)"


def test_sem_entrada_registrada_nao_censura():
    v = {d: 1.0 for d in DIAS[:6]}
    for d in DIAS[6:18]:
        v[d] = 0.0
    for d in DIAS[18:]:
        v[d] = 1.0
    assert censura.dias_censurados(1, _vendas(v), [], _cal(DIAS), CFG) == set()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_censura.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'censura'`

- [ ] **Step 3: Write minimal implementation**

Crie `src/censura.py`:

```python
# -*- coding: utf-8 -*-
"""Censura de RUPTURA DE ESTOQUE (spec §6.2 / D11 / D12).

Zero de venda tem duas causas muito diferentes: "ninguem quis" (demanda real,
tem que ficar na base) e "nao tinha o que vender" (demanda CENSURADA, tem que
sair). Confundir as duas envenena o giro.

So censura com os 4 sinais juntos — 99% de certeza, por ordem do dono:
  1. zero venda no dia (TODOS os canais)
  2. silencio anormal PARA AQUELE ITEM (>= k x intervalo tipico dele)
  3. estoque esgotado (vendas acumuladas desde a ultima entrega >= o entregue)
  4. retro-confirmacao: o silencio termina com uma entrega e a venda volta

O sinal 4 e o que os detectores NAO tem: eles decidem no presente; aqui olhamos
o passado e sabemos como a historia terminou.

VIES DELIBERADO — na duvida, o dia FICA. Manter um dia fraco por engano encolhe
um pouco o min. Remover um zero legitimo INFLA o min e enche a prateleira de
mercadoria parada, que e exatamente a avaria/validade que o MAX combate."""


def _intervalo_tipico(idx_com_venda, meia_vida=5.0):
    """EWMA dos gaps entre vendas, em dias uteis. Porta de
    detector-ruptura-atacaderj/src/detect/gapstats.js."""
    gaps = [idx_com_venda[i] - idx_com_venda[i - 1] for i in range(1, len(idx_com_venda))]
    if not gaps:
        return None
    soma = pesos = 0.0
    n = len(gaps)
    for i, g in enumerate(gaps):
        w = 0.5 ** ((n - 1 - i) / meia_vida)
        soma += g * w
        pesos += w
    return soma / pesos


def dias_censurados(codigo, vendas_item, entradas_item, cal, cfg):
    c = cfg["censura"]
    dias = cal["dias"]
    if not dias or not entradas_item:
        return set()   # sem entrega nao da para provar esgotamento (sinal 3)

    total = []
    for d in dias:
        v = vendas_item.get(d) or {"salao": 0.0, "atacado": 0.0}
        total.append(v["salao"] + v["atacado"])   # TODOS os canais (D4)

    com_venda = [i for i, t in enumerate(total) if t > 0]
    if len(com_venda) < 2:
        return set()
    tipico = _intervalo_tipico(com_venda)
    if not tipico or tipico <= 0:
        return set()
    minimo = c["kIntervalo"] * tipico

    # acumulado desde a ultima entrega, por dia (sinal 3)
    entregas = {e["data"]: e["qtd"] for e in entradas_item}
    entregue = 0.0
    acumulado = 0.0
    esgotado_no_dia = []
    for i, d in enumerate(dias):
        if d in entregas:
            entregue = entregas[d]
            acumulado = 0.0
        acumulado += total[i]
        esgotado_no_dia.append(entregue > 0 and acumulado >= c["razaoEsgotamento"] * entregue)

    # varre as sequencias de zeros
    fora = set()
    i = 0
    n = len(dias)
    while i < n:
        if total[i] > 0:
            i += 1
            continue
        j = i
        while j < n and total[j] == 0:
            j += 1
        comprimento = j - i                       # sinal 1 (o bloco todo e zero)

        if comprimento >= minimo:                 # sinal 2
            esgotou = any(esgotado_no_dia[i:j])   # sinal 3
            # sinal 4: entregou DENTRO/no fim do silencio e a venda voltou depois
            houve_entrega = any(d in entregas for d in dias[i:j])
            voltou = j < n and total[j] > 0
            retro_ok = (houve_entrega and voltou) if c["exigeRetroConfirmacao"] else True
            if esgotou and retro_ok:
                fora.update(dias[i:j])
        i = j
    return fora
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_censura.py -v`
Expected: PASS — 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/censura.py tests/test_censura.py
git commit -m "feat: censura de ruptura de estoque (4 sinais, 99% de certeza)"
```

---

### Task 4: `dow` — peso do dia da semana

**Files:**
- Create: `src/dow.py`
- Test: `tests/test_dow.py`

**Interfaces:**
- Consumes: `importar` (Task 1), `calendario` (Task 2), `censura` (Task 3).
- Produces: `dow.fatores(vendas, catalogo, cal, censurados_por_item, cfg) -> dict[str, list[float]]` — `{categoria: [f_seg, f_ter, f_qua, f_qui, f_sex, f_sab]}` mais a chave `"__loja__"`. Média dos 6 = 1.

**Contexto (spec §6.3):** medido em 17/07 — **sábado ≈ 2× a segunda** (R$ 2,32M × R$ 1,20M). É sinal forte, não ruído. Por item o dado é ralo; por **categoria (prateleira)** há volume. Encolhimento:
`f_cat_final(d) = (n_cat(d)·f_cat(d) + m·f_loja(d)) / (n_cat(d) + m)`, `m = dow.pesoEncolhimento`.

- [ ] **Step 1: Write the failing test**

Crie `tests/test_dow.py`:

```python
# -*- coding: utf-8 -*-
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import calendario  # noqa: E402
import dow         # noqa: E402

CFG = {"calendario": {"diaFechadoFracao": 0.2}, "dow": {"pesoEncolhimento": 200}}
PESO = {0: 0.7, 1: 0.8, 2: 0.9, 3: 1.1, 4: 1.3, 5: 1.6}   # seg..sab


def _cenario(n_itens, categoria="P1", dias=180):
    vendas, cat = {}, {}
    hoje = date(2026, 7, 17)
    for cod in range(n_itens):
        cat[cod] = {"descricao": f"IT{cod}", "caixa_mae": 12,
                    "prateleira": categoria, "curva": "A"}
        for k in range(dias):
            d = hoje - timedelta(days=k)
            if d.weekday() == 6:
                continue
            vendas.setdefault(cod, {})[d.isoformat()] = {
                "salao": 10.0 * PESO[d.weekday()], "atacado": 0.0}
    return vendas, cat


def test_sabado_pesa_mais_que_segunda():
    vendas, cat = _cenario(30)
    cal = calendario.construir(vendas, CFG)
    f = dow.fatores(vendas, cat, cal, {}, CFG)
    assert f["__loja__"][5] > f["__loja__"][0]
    assert f["__loja__"][5] / f["__loja__"][0] > 1.8


def test_fatores_normalizam_para_media_1():
    vendas, cat = _cenario(30)
    cal = calendario.construir(vendas, CFG)
    f = dow.fatores(vendas, cat, cal, {}, CFG)
    assert abs(sum(f["__loja__"]) / 6 - 1.0) < 1e-9
    assert abs(sum(f["P1"]) / 6 - 1.0) < 1e-9


def test_categoria_magra_encolhe_para_a_loja():
    # P1 e gorda; P2 tem 1 item com padrao invertido e pouco dado
    vendas, cat = _cenario(40, "P1")
    hoje = date(2026, 7, 17)
    cod = 999
    cat[cod] = {"descricao": "RARO", "caixa_mae": 12, "prateleira": "P2", "curva": "C"}
    for k in range(12):
        d = hoje - timedelta(days=k)
        if d.weekday() == 6:
            continue
        # invertido: segunda forte, sabado fraco
        vendas.setdefault(cod, {})[d.isoformat()] = {
            "salao": (5.0 if d.weekday() == 0 else 0.1), "atacado": 0.0}
    cal = calendario.construir(vendas, CFG)
    f = dow.fatores(vendas, cat, cal, {}, CFG)
    # com so ~12 item-dias contra m=200, P2 tem que ficar perto da loja
    for i in range(6):
        assert abs(f["P2"][i] - f["__loja__"][i]) < 0.15


def test_dia_censurado_nao_entra_no_fator():
    vendas, cat = _cenario(30)
    cal = calendario.construir(vendas, CFG)
    # zera um sabado no item 0 e censura o dia: nao pode puxar o fator do sabado
    sab = [d for d in cal["dias"] if date.fromisoformat(d).weekday() == 5][0]
    vendas[0][sab] = {"salao": 0.0, "atacado": 0.0}
    f_com = dow.fatores(vendas, cat, cal, {0: {sab}}, CFG)
    f_sem = dow.fatores(vendas, cat, cal, {}, CFG)
    assert f_com["__loja__"][5] > f_sem["__loja__"][5]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dow.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dow'`

- [ ] **Step 3: Write minimal implementation**

Crie `src/dow.py`:

```python
# -*- coding: utf-8 -*-
"""Peso do dia-da-semana (spec §6.3).

Medido em 17/07/2026: sabado ~2x a segunda (R$2,32M x R$1,20M). Ignorar isso
seria supor que a semana e plana — e ela nao e, nem de longe.

Por ITEM o dado e ralo; por CATEGORIA (prateleira) ha volume. Entao estima-se
por categoria e encolhe-se para o padrao da loja proporcionalmente a evidencia
que a categoria tem. Categoria magra vira a loja; categoria gorda fala por si.

So conta dias DENTRO DA VIDA de cada item (calendario.janela_do_item): senao um
item novo entraria com dezenas de zeros de antes de existir, inflando n_cat com
evidencia falsa e enfraquecendo o encolhimento justo onde ele mais importa."""
from datetime import date

import calendario

LOJA = "__loja__"


def _normalizar(v):
    m = sum(v) / len(v)
    return [x / m for x in v] if m > 0 else [1.0] * len(v)


def fatores(vendas, catalogo, cal, censurados_por_item, cfg):
    m = cfg["dow"]["pesoEncolhimento"]

    # soma e contagem de item-dias LIMPOS por (categoria, dia-da-semana)
    soma_loja = [0.0] * 6
    n_loja = [0] * 6
    soma_cat, n_cat = {}, {}

    for cod, por_dia in vendas.items():
        info = catalogo.get(cod)
        if not info:
            continue
        janela = calendario.janela_do_item(por_dia, cal)
        if janela is None:
            continue                    # nunca vendeu: nao opina sobre dia-da-semana
        ini, fim = janela
        categoria = info["prateleira"] or "(sem prateleira)"
        fora = censurados_por_item.get(cod, set())
        soma_cat.setdefault(categoria, [0.0] * 6)
        n_cat.setdefault(categoria, [0] * 6)
        for i in range(ini, fim + 1):    # SO a vida do item (sem zero fantasma)
            dia = cal["dias"][i]
            if dia in fora:
                continue
            wd = date.fromisoformat(dia).weekday()
            if wd == 6:
                continue
            un = (por_dia.get(dia) or {"salao": 0.0})["salao"]   # SO salao (D3)
            soma_loja[wd] += un
            n_loja[wd] += 1
            soma_cat[categoria][wd] += un
            n_cat[categoria][wd] += 1

    media_loja = [(soma_loja[i] / n_loja[i]) if n_loja[i] else 0.0 for i in range(6)]
    f_loja = _normalizar(media_loja)

    out = {LOJA: f_loja}
    for categoria, soma in soma_cat.items():
        f_cat = []
        for i in range(6):
            n = n_cat[categoria][i]
            media = (soma[i] / n) if n else 0.0
            f_cat.append(media)
        f_cat = _normalizar(f_cat) if any(f_cat) else list(f_loja)
        encolhido = [((n_cat[categoria][i] * f_cat[i] + m * f_loja[i])
                      / (n_cat[categoria][i] + m)) for i in range(6)]
        out[categoria] = _normalizar(encolhido)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dow.py -v`
Expected: PASS — 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/dow.py tests/test_dow.py
git commit -m "feat: fatores de dia-da-semana por categoria com encolhimento"
```

---

### Task 5: `modelo` — binomial negativa por item

**Files:**
- Create: `src/modelo.py`
- Test: `tests/test_modelo.py`

**Interfaces:**
- Consumes: `dow.fatores` (Task 4), `calendario` (Task 2), `censura` (Task 3).
- Produces: `modelo.ajustar(cod, vendas_item, cal, fora: set, f_dow: list[float], cfg, r_global: float | None = None) -> dict` com `{"mu": float, "r": float | None, "dias_limpos": int}`. `r is None` ⇒ Poisson. E `modelo.r_global(ajustes: list[dict]) -> float` (mediana dos `r` finitos).

**A matemática (spec §6.4) — não improvise:**
- Média ajustada por DOW: `μ = Σ y_d / Σ f_dow(d)` sobre os dias limpos.
- Esperado do dia: `e_d = μ × f_dow(d)`.
- Dispersão por momentos: para a NB, `Var(y_d) = e_d + e_d²/r`. Somando: `Σ(y_d − e_d)² = Σe_d + Σe_d²/r` ⇒ **`r = Σe_d² / (Σ(y_d−e_d)² − Σe_d)`**.
- Se o denominador `≤ 0` (subdisperso) ⇒ **Poisson** (`r = None`).
- Item com `< modelo.minDiasLimpos` dias limpos **com venda** ⇒ `r` encolhido para `r_global`.
- Item sem venda limpa ⇒ `μ = 0` (cai no piso de 1 caixa, spec D9).

- [ ] **Step 1: Write the failing test**

Crie `tests/test_modelo.py`:

```python
# -*- coding: utf-8 -*-
import os
import sys
from datetime import date, timedelta

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import modelo  # noqa: E402

CFG = {"modelo": {"minDiasLimpos": 30}}
F_PLANO = [1.0] * 6


def _cal(n):
    """n dias ABERTOS consecutivos (sem domingo). Se deixasse domingo entrar,
    ajustar() os puliria e dias_limpos nunca bateria com n."""
    dias = []
    d = date(2026, 1, 5)          # uma segunda-feira
    while len(dias) < n:
        if d.weekday() != 6:
            dias.append(d.isoformat())
        d += timedelta(days=1)
    return {"dias": dias, "indice": {x: i for i, x in enumerate(dias)}, "fechados": []}


def _vendas(dias, valores):
    return {d: {"salao": float(v), "atacado": 0.0} for d, v in zip(dias, valores)}


def test_media_bate_quando_o_fator_e_plano():
    cal = _cal(60)
    v = _vendas(cal["dias"], [10] * 60)
    a = modelo.ajustar(1, v, cal, set(), F_PLANO, CFG)
    assert abs(a["mu"] - 10.0) < 1e-9
    assert a["dias_limpos"] == 60


def test_dia_censurado_sai_da_conta():
    cal = _cal(60)
    vals = [10] * 59 + [0]
    v = _vendas(cal["dias"], vals)
    a = modelo.ajustar(1, v, cal, {cal["dias"][59]}, F_PLANO, CFG)
    assert abs(a["mu"] - 10.0) < 1e-9
    assert a["dias_limpos"] == 59


def test_superdisperso_devolve_r_finito():
    rng = np.random.default_rng(1)
    cal = _cal(200)
    # NB com mu=10, r=2 -> variancia 10 + 100/2 = 60 >> 10
    amostras = rng.negative_binomial(2, 2 / (2 + 10), size=200)
    a = modelo.ajustar(1, _vendas(cal["dias"], amostras), cal, set(), F_PLANO, CFG)
    assert a["r"] is not None
    assert 1.0 < a["r"] < 5.0, f"r estimado {a['r']}"


def test_subdisperso_vira_poisson():
    cal = _cal(60)
    v = _vendas(cal["dias"], [10] * 60)   # variancia zero
    assert modelo.ajustar(1, v, cal, set(), F_PLANO, CFG)["r"] is None


def test_item_sem_venda_tem_mu_zero():
    cal = _cal(60)
    a = modelo.ajustar(1, _vendas(cal["dias"], [0] * 60), cal, set(), F_PLANO, CFG)
    assert a["mu"] == 0.0


def test_poucos_dias_encolhe_r_para_o_global():
    cal = _cal(10)
    rng = np.random.default_rng(2)
    amostras = rng.negative_binomial(2, 2 / (2 + 10), size=10)
    a = modelo.ajustar(1, _vendas(cal["dias"], amostras), cal, set(), F_PLANO, CFG,
                       r_global=7.0)
    assert a["r"] == 7.0


def test_fator_dow_corrige_a_media():
    # vende 20 no sabado e 5 na segunda; com o fator certo a media base e a mesma
    cal = {"dias": ["2026-07-13", "2026-07-18"],  # segunda, sabado
           "indice": {"2026-07-13": 0, "2026-07-18": 1}, "fechados": []}
    v = {"2026-07-13": {"salao": 5.0, "atacado": 0.0},
         "2026-07-18": {"salao": 20.0, "atacado": 0.0}}
    f = [0.5, 1.0, 1.0, 1.0, 1.0, 2.0]     # segunda 0.5x, sabado 2x
    a = modelo.ajustar(1, v, cal, set(), f, CFG)
    assert abs(a["mu"] - 10.0) < 1e-9      # (5+20)/(0.5+2.0)


def test_r_global_e_a_mediana_dos_finitos():
    assert modelo.r_global([{"r": 2.0}, {"r": None}, {"r": 4.0}, {"r": 6.0}]) == 4.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_modelo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'modelo'`

- [ ] **Step 3: Write minimal implementation**

Crie `src/modelo.py`:

```python
# -*- coding: utf-8 -*-
"""Binomial negativa por item (spec §6.4).

Por que NB e nao normal: venda diaria e CONTAGEM, assimetrica e superdispersa
(variancia >> media). A normal subestima a cauda justo onde o min/max vive — no
percentil 95. Por que nao Poisson puro: Poisson exige var == media, e a venda
real tem var muito maior (promocao, pico de fim de semana, cliente que leva 10).

Parametrizacao: media mu, dispersao r, com Var = mu + mu^2/r. r -> infinito
recai em Poisson.

So conta dias DENTRO DA VIDA do item (calendario.janela_do_item). Um item
cadastrado mes passado nao vendeu zero nos 150 dias anteriores — ele nao
existia; diluir o giro por esses dias travaria o min dele em 1 caixa p/ sempre."""
import statistics
from datetime import date

import calendario


def ajustar(cod, vendas_item, cal, fora, f_dow, cfg, r_global=None):
    janela = calendario.janela_do_item(vendas_item, cal)
    if janela is None:
        return {"mu": 0.0, "r": None, "dias_limpos": 0}   # nunca vendeu (D9: piso de 1 cx)
    ini, fim = janela

    ys, es = [], []
    for i in range(ini, fim + 1):        # SO a vida do item (sem zero fantasma)
        dia = cal["dias"][i]
        if dia in fora:
            continue
        wd = date.fromisoformat(dia).weekday()
        if wd == 6:
            continue
        y = (vendas_item.get(dia) or {"salao": 0.0})["salao"]   # SO salao (D3)
        ys.append(y)
        es.append(f_dow[wd])

    n = len(ys)
    if n == 0 or sum(es) == 0:
        return {"mu": 0.0, "r": None, "dias_limpos": 0}

    mu = sum(ys) / sum(es)
    if mu <= 0:
        return {"mu": 0.0, "r": None, "dias_limpos": n}

    esperado = [mu * e for e in es]
    soma_e = sum(esperado)
    soma_e2 = sum(e * e for e in esperado)
    residuo2 = sum((y - e) ** 2 for y, e in zip(ys, esperado))

    denom = residuo2 - soma_e
    r = (soma_e2 / denom) if denom > 0 else None   # denom <= 0 -> subdisperso -> Poisson

    # pouco dado limpo COM venda -> nao confie no r proprio; use o do grupo
    dias_com_venda = sum(1 for y in ys if y > 0)
    if r_global is not None and dias_com_venda < cfg["modelo"]["minDiasLimpos"]:
        r = r_global

    return {"mu": mu, "r": r, "dias_limpos": n}


def r_global(ajustes):
    finitos = [a["r"] for a in ajustes if a.get("r") is not None]
    return statistics.median(finitos) if finitos else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_modelo.py -v`
Expected: PASS — 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/modelo.py tests/test_modelo.py
git commit -m "feat: binomial negativa por item (momentos, Poisson se subdisperso)"
```

---

### Task 6: `simular` — Monte Carlo do horizonte

**Files:**
- Create: `src/simular.py`
- Test: `tests/test_simular.py`

**Interfaces:**
- Consumes: `modelo.ajustar` (Task 5).
- Produces:
  - `simular.dias_uteis_do_horizonte(dias_corridos: int) -> list[list[int]]` — para cada dia de início (seg..sáb), a lista de dias-da-semana (0..5) dos dias abertos da janela.
  - `simular.distribuicao(mu, r, f_dow, dias_corridos, cfg, rng) -> numpy.ndarray` — amostras da demanda total do horizonte, **em unidades**.

**A matemática (spec §6.1 e §6.5):**
- 7 dias corridos = **6 dias úteis** (um de cada, seg–sáb — o domingo cai fora).
- 30 dias corridos = **25 ou 26** dias úteis conforme o dia de início (4 ou 5 domingos dentro). Por isso simula-se **os 6 dias de início** e agrupa-se tudo numa distribuição só: elimina o "começou numa terça ou num sábado?".
- NB do `scipy`/`numpy` usa `(n, p)`; a conversão de `(μ, r)` é **`n = r`, `p = r/(r+μ)`**. Confira: média `= n(1−p)/p = μ` ✔, variância `= n(1−p)/p² = μ + μ²/r` ✔.
- `r is None` ⇒ Poisson com média `μ×f_dow(d)`.

- [ ] **Step 1: Write the failing test**

Crie `tests/test_simular.py`:

```python
# -*- coding: utf-8 -*-
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import simular  # noqa: E402

CFG = {"simulacao": {"sorteios": 4000, "semente": 42}}
F_PLANO = [1.0] * 6


def test_7_dias_corridos_sao_6_dias_uteis_um_de_cada():
    for inicio in simular.dias_uteis_do_horizonte(7):
        assert len(inicio) == 6
        assert sorted(inicio) == [0, 1, 2, 3, 4, 5]


def test_30_dias_corridos_dao_25_ou_26_dias_uteis():
    tamanhos = {len(x) for x in simular.dias_uteis_do_horizonte(30)}
    assert tamanhos <= {25, 26}
    assert len(simular.dias_uteis_do_horizonte(30)) == 6   # 6 dias de inicio


def test_media_da_semana_bate_com_mu_vezes_6():
    rng = np.random.default_rng(1)
    d = simular.distribuicao(10.0, None, F_PLANO, 7, CFG, rng)
    assert abs(d.mean() - 60.0) < 2.0


def test_fator_dow_puxa_a_media():
    rng = np.random.default_rng(1)
    f = [0.5, 1.0, 1.0, 1.0, 1.0, 2.0]     # soma 6.5 -> media 65 com mu=10
    d = simular.distribuicao(10.0, None, f, 7, CFG, rng)
    assert abs(d.mean() - 65.0) < 2.5


def test_horizonte_maior_tem_demanda_maior():
    rng = np.random.default_rng(1)
    d7 = simular.distribuicao(10.0, 5.0, F_PLANO, 7, CFG, rng)
    d30 = simular.distribuicao(10.0, 5.0, F_PLANO, 30, CFG, rng)
    assert d30.mean() > d7.mean() * 3


def test_nb_tem_mais_cauda_que_poisson():
    rng = np.random.default_rng(1)
    pois = simular.distribuicao(10.0, None, F_PLANO, 7, CFG, rng)
    nb = simular.distribuicao(10.0, 2.0, F_PLANO, 7, CFG, rng)
    assert np.percentile(nb, 95) > np.percentile(pois, 95)


def test_reprodutivel_com_a_mesma_semente():
    a = simular.distribuicao(10.0, 2.0, F_PLANO, 7, CFG, np.random.default_rng(42))
    b = simular.distribuicao(10.0, 2.0, F_PLANO, 7, CFG, np.random.default_rng(42))
    assert np.array_equal(a, b)


def test_mu_zero_devolve_tudo_zero():
    d = simular.distribuicao(0.0, None, F_PLANO, 7, CFG, np.random.default_rng(1))
    assert d.max() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_simular.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'simular'`

- [ ] **Step 3: Write minimal implementation**

Crie `src/simular.py`:

```python
# -*- coding: utf-8 -*-
"""Monte Carlo da demanda do horizonte (spec §6.1 e §6.5).

Horizonte em dias CORRIDOS (como o dono pensa), traduzido para dias uteis:
  - 7 corridos  = 6 uteis = uma semana seg..sab (o domingo cai fora). Toda
    janela de 7 dias tem UM de cada dia da semana -> sem ambiguidade.
  - 30 corridos = 25 ou 26 uteis, conforme o dia de inicio (4 ou 5 domingos
    dentro). Por isso simulamos OS 6 dias de inicio possiveis e agrupamos numa
    distribuicao so — em vez de escolher a dedo um inicio conveniente.

Conversao (mu, r) -> (n, p) da binomial negativa: n = r, p = r/(r+mu).
  media    = n(1-p)/p  = mu           OK
  variancia= n(1-p)/p^2= mu + mu^2/r  OK
"""
import numpy as np


def dias_uteis_do_horizonte(dias_corridos):
    """Para cada dia de inicio (0=seg .. 5=sab), os dias-da-semana dos dias
    ABERTOS da janela de `dias_corridos` dias."""
    out = []
    for inicio in range(6):
        dias = []
        for k in range(dias_corridos):
            wd = (inicio + k) % 7
            if wd != 6:          # domingo: loja fechada
                dias.append(wd)
        out.append(dias)
    return out


def distribuicao(mu, r, f_dow, dias_corridos, cfg, rng):
    n_por_inicio = max(1, cfg["simulacao"]["sorteios"])
    janelas = dias_uteis_do_horizonte(dias_corridos)

    if mu <= 0:
        return np.zeros(n_por_inicio * len(janelas))

    partes = []
    for dias in janelas:
        medias = np.array([mu * f_dow[wd] for wd in dias])
        if r is None:                       # Poisson
            amostras = rng.poisson(
                np.tile(medias, (n_por_inicio, 1))).sum(axis=1)
        else:
            p = r / (r + medias)            # vetor: um p por dia da janela
            amostras = rng.negative_binomial(
                r, np.tile(p, (n_por_inicio, 1))).sum(axis=1)
        partes.append(amostras)
    return np.concatenate(partes).astype(float)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_simular.py -v`
Expected: PASS — 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/simular.py tests/test_simular.py
git commit -m "feat: Monte Carlo do horizonte (7d=6 uteis; 30d agrega os 6 inicios)"
```

---

### Task 7: `escada` — função pura

**Files:**
- Create: `src/escada.py`
- Test: `tests/test_escada.py`

**Interfaces:**
- Consumes: nada. **Função pura — não importa nenhum outro módulo deste repo.**
- Produces:
  - `escada.confianca(amostras: np.ndarray, q: int, caixa_mae: int) -> float`
  - `escada.subir(amostras: np.ndarray, caixa_mae: int, limiar: float, max_caixas: int, piso: int = 1) -> tuple[int, bool]` — `(q, estourou_o_teto)`.

**A definição (spec §6.6):** `subir` devolve **o menor `q ≥ piso` com `confianca(q) ≥ limiar`**. É a escada que o dono pediu: se 2 caixas dão 60%, tenta 3; se 3 dão 88%, tenta 4; para na primeira que cruza.

**Implementação eficiente e por que ela é equivalente:** varrer `q = 1..500` recalculando a confiança seria 500 × 120.000 comparações × 4.634 itens. Em vez disso, ordena-se as amostras uma vez: `confianca(q) ≥ limiar` ⟺ `q × caixa_mae ≥ ordenadas[k]`, com `k = ceil(limiar × n) − 1`. Logo `q = ceil(ordenadas[k] / caixa_mae)`. O Step 1 tem um teste que prova essa equivalência contra a escada ingênua — se alguém "otimizar" isso errado, o teste pega.

- [ ] **Step 1: Write the failing test**

Crie `tests/test_escada.py`:

```python
# -*- coding: utf-8 -*-
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import escada  # noqa: E402


def _escada_ingenua(amostras, caixa, limiar, max_caixas, piso=1):
    """A definicao literal, O(n*max_caixas). So p/ provar a equivalencia."""
    for q in range(piso, max_caixas + 1):
        if float((amostras <= q * caixa).mean()) >= limiar:
            return q
    return max_caixas


def test_confianca_e_a_fracao_coberta():
    a = np.array([1.0, 2.0, 3.0, 4.0])
    assert escada.confianca(a, 1, 2) == 0.5     # <=2 cobre 1 e 2
    assert escada.confianca(a, 2, 2) == 1.0     # <=4 cobre tudo


def test_para_na_PRIMEIRA_caixa_que_cruza_o_limiar():
    # demanda 0..99; caixa=10. P95 = 95 -> 10 caixas (100 un) cobrem 96%
    a = np.arange(100, dtype=float)
    q, _ = escada.subir(a, caixa_mae=10, limiar=0.95, max_caixas=500)
    assert q == 10
    assert escada.confianca(a, 9, 10) < 0.95    # 9 caixas NAO bastam
    assert escada.confianca(a, 10, 10) >= 0.95


def test_sobe_quando_a_confianca_nao_basta():
    # o exemplo do dono: 2cx=60%, 3cx=88%, 4cx=96% -> devolve 4
    a = np.array([10.0] * 60 + [25.0] * 28 + [35.0] * 8 + [95.0] * 4)
    caixa = 10
    assert escada.confianca(a, 2, caixa) < 0.95
    assert escada.confianca(a, 3, caixa) < 0.95
    q, _ = escada.subir(a, caixa, 0.95, 500)
    assert q == 4


def test_piso_de_1_caixa_mesmo_com_demanda_zero():
    a = np.zeros(1000)
    q, estourou = escada.subir(a, caixa_mae=12, limiar=0.95, max_caixas=500)
    assert q == 1 and not estourou


def test_piso_customizado_para_o_max_nunca_ficar_abaixo_do_min():
    a = np.zeros(1000)
    q, _ = escada.subir(a, caixa_mae=12, limiar=0.95, max_caixas=500, piso=7)
    assert q == 7


def test_teto_marca_em_vez_de_estourar():
    a = np.array([10_000.0] * 100)
    q, estourou = escada.subir(a, caixa_mae=1, limiar=0.95, max_caixas=5)
    assert q == 5 and estourou


def test_equivale_a_escada_ingenua():
    rng = np.random.default_rng(7)
    for caixa in (1, 6, 12, 27):
        for _ in range(15):
            a = rng.negative_binomial(3, 0.2, size=2000).astype(float)
            esperado = _escada_ingenua(a, caixa, 0.95, 500)
            obtido, _ = escada.subir(a, caixa, 0.95, 500)
            assert obtido == esperado, f"caixa={caixa}: {obtido} != {esperado}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_escada.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'escada'`

- [ ] **Step 3: Write minimal implementation**

Crie `src/escada.py`:

```python
# -*- coding: utf-8 -*-
"""A escada de caixas (spec §6.6). FUNCAO PURA: nao importa nada deste repo.

A definicao do dono, literal: "se 2 caixas so me dao 60% de confianca, aumentar
para 3 ou 4 ate me dar meu limiar". Nao e "arredonda o percentil" — e subir a
escada ate cruzar o limiar. Da o mesmo numero, mas diz o que faz.

Implementacao: varrer q=1..500 recalculando a confianca seria O(n*500) por item
(x4.634 itens). Ordenando uma vez:
    confianca(q) >= limiar  <=>  q*caixa >= ordenadas[k],  k = ceil(limiar*n)-1
logo q = ceil(ordenadas[k]/caixa). O teste test_equivale_a_escada_ingenua prova
a equivalencia contra a definicao literal."""
import math

import numpy as np


def confianca(amostras, q, caixa_mae):
    """P(demanda <= q caixas)."""
    return float((np.asarray(amostras) <= q * caixa_mae).mean())


def subir(amostras, caixa_mae, limiar, max_caixas, piso=1):
    """Menor q >= piso com confianca(q) >= limiar.
    Devolve (q, estourou_o_teto)."""
    a = np.asarray(amostras, dtype=float)
    n = a.size
    if n == 0:
        return piso, False

    ordenadas = np.sort(a)
    k = min(n - 1, max(0, math.ceil(limiar * n) - 1))
    necessario = ordenadas[k]

    q = max(piso, math.ceil(necessario / caixa_mae)) if necessario > 0 else piso
    if q > max_caixas:
        return max_caixas, True
    return int(q), False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_escada.py -v`
Expected: PASS — 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/escada.py tests/test_escada.py
git commit -m "feat: escada de caixas ate o limiar de confianca (funcao pura)"
```

---

### Task 8: `calibrar` — o backtest é régua, não juiz

**Files:**
- Create: `src/calibrar.py`
- Test: `tests/test_calibrar.py`

**Interfaces:**
- Consumes: `escada.subir` (Task 7), `modelo.ajustar` (Task 5), `simular.distribuicao` (Task 6).
- Produces:
  - `calibrar.elegiveis(ajustes: dict[int, dict], janelas_por_item: dict[int, int], cfg) -> list[int]`
  - `calibrar.cobertura(lam: float, pares: list[dict], cfg) -> float` — `pares` = `[{"amostras": np.ndarray, "caixa_mae": int, "real": float}, ...]`
  - `calibrar.buscar_lambda(pares, cfg) -> tuple[float, float]` — `(λ, cobertura_atingida)`

**Contexto (spec §7 / D16) — o dono corrigiu isto explicitamente:** o backtest **NÃO veta** a entrega. Ele mede a otimismo do modelo e devolve `λ ≥ 1` que infla a distribuição (`D* = λ × D`) até a cobertura medida cruzar o limiar.

- **`λ` só infla, nunca deflaciona.** A folga é unilateral, por ordem do dono.
- **`λ` é global, não por item:** com 8 semanas de holdout, um `λ` por item seria ajustado em 8 pontos — ruído. Agregado dá ~1.400 itens × 8 semanas ≈ 11.000 pares.
- **Se nem `lambdaMax` alcançar: entrega assim mesmo** com `λ = lambdaMax` e a cobertura real estampada. **Nada trava.**
- `cobertura(λ)` é monótona crescente em `λ` ⇒ busca binária é válida.

- [ ] **Step 1: Write the failing test**

Crie `tests/test_calibrar.py`:

```python
# -*- coding: utf-8 -*-
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import calibrar  # noqa: E402

CFG = {"percentil": 0.95, "escada": {"maxCaixas": 500},
       "calibracao": {"lambdaMax": 3.0, "tol": 0.01},
       "validacao": {"giroMinimo": 1.0, "minJanelas": 12}}


def _pares(n, amostras, caixa, reais):
    return [{"amostras": amostras, "caixa_mae": caixa, "real": r} for r in reais]


def test_elegiveis_exige_giro_e_janelas():
    ajustes = {1: {"mu": 5.0}, 2: {"mu": 0.2}, 3: {"mu": 9.0}}
    janelas = {1: 20, 2: 20, 3: 3}
    assert calibrar.elegiveis(ajustes, janelas, CFG) == [1]


def test_modelo_ja_honesto_devolve_lambda_1():
    a = np.arange(100, dtype=float)          # P95 = 95 -> 10 caixas de 10 = 100 un
    reais = list(np.arange(100, dtype=float))  # 100% <= 100
    lam, cob = calibrar.buscar_lambda(_pares(100, a, 10, reais), CFG)
    assert lam == 1.0
    assert cob >= 0.95


def test_modelo_otimista_infla_o_lambda():
    a = np.arange(100, dtype=float)          # o modelo acha que o teto e 100
    # a realidade e pior: metade das semanas passa de 100
    reais = [50.0] * 50 + [150.0] * 50
    lam, cob = calibrar.buscar_lambda(_pares(100, a, 10, reais), CFG)
    assert lam > 1.0, "modelo otimista tem que inflar"
    assert cob >= 0.95 or lam == 3.0


def test_lambda_nunca_deflaciona():
    a = np.arange(100, dtype=float)
    reais = [1.0] * 100                       # cobertura 100%: sobraria folga
    lam, _ = calibrar.buscar_lambda(_pares(100, a, 10, reais), CFG)
    assert lam == 1.0, "a folga e unilateral (ordem do dono)"


def test_limiar_inalcancavel_entrega_com_lambda_max_e_NAO_trava():
    a = np.arange(100, dtype=float)
    reais = [10_000.0] * 100                  # nem 3x cobre
    lam, cob = calibrar.buscar_lambda(_pares(100, a, 10, reais), CFG)
    assert lam == 3.0                         # lambdaMax
    assert cob < 0.95                         # e a verdade sai junto
    # o teste que importa: nao levantou excecao


def test_cobertura_e_monotona_em_lambda():
    a = np.arange(100, dtype=float)
    reais = [50.0] * 30 + [150.0] * 70
    pares = _pares(100, a, 10, reais)
    cobs = [calibrar.cobertura(l, pares, CFG) for l in (1.0, 1.5, 2.0, 3.0)]
    assert cobs == sorted(cobs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_calibrar.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'calibrar'`

- [ ] **Step 3: Write minimal implementation**

Crie `src/calibrar.py`:

```python
# -*- coding: utf-8 -*-
"""Calibracao (spec §7 / D16): o backtest e REGUA, nao juiz.

O desenho anterior travava a entrega quando o backtest reprovava. O dono
corrigiu: nao veta — MEDE a otimismo do modelo e corrige, subindo a escada ate
a confianca prometida virar a confianca real.

  lambda >= 1 infla a distribuicao: D* = lambda x D
  lambda SO INFLA, nunca deflaciona — a folga e unilateral, por ordem do dono
  lambda e GLOBAL: com 8 semanas de holdout, um lambda por item seria ajustado
    em 8 pontos (ruido). Agregado sao ~1.400 itens x 8 semanas ~ 11.000 pares.
  Se nem lambdaMax alcancar o limiar: ENTREGA MESMO ASSIM, com a cobertura real
    estampada. Nada trava (D16)."""
import numpy as np

import escada


def elegiveis(ajustes, janelas_por_item, cfg):
    """So os itens onde o modelo de fato decide. Nos demais o resultado e o piso
    de 1 caixa e nao ha promessa estatistica a aferir."""
    v = cfg["validacao"]
    return sorted(
        cod for cod, a in ajustes.items()
        if a["mu"] >= v["giroMinimo"] and janelas_por_item.get(cod, 0) >= v["minJanelas"])


def cobertura(lam, pares, cfg):
    """Fracao dos pares (item x semana) em que a venda real <= min calculado
    com a distribuicao inflada por lambda."""
    if not pares:
        return 1.0
    ok = 0
    for p in pares:
        q, _ = escada.subir(np.asarray(p["amostras"]) * lam, p["caixa_mae"],
                            cfg["percentil"], cfg["escada"]["maxCaixas"])
        if p["real"] <= q * p["caixa_mae"]:
            ok += 1
    return ok / len(pares)


def buscar_lambda(pares, cfg):
    """Menor lambda em [1, lambdaMax] com cobertura >= percentil.
    Devolve (lambda, cobertura_atingida). cobertura(lambda) e monotona
    crescente -> busca binaria vale."""
    alvo = cfg["percentil"]
    lam_max = cfg["calibracao"]["lambdaMax"]
    tol = cfg["calibracao"]["tol"]

    cob1 = cobertura(1.0, pares, cfg)
    if cob1 >= alvo:
        return 1.0, cob1                      # ja honesto: nao deflaciona

    cob_max = cobertura(lam_max, pares, cfg)
    if cob_max < alvo:
        return lam_max, cob_max               # nao alcanca: entrega assim mesmo

    lo, hi = 1.0, lam_max
    while hi - lo > tol:
        meio = (lo + hi) / 2
        if cobertura(meio, pares, cfg) >= alvo:
            hi = meio
        else:
            lo = meio
    return hi, cobertura(hi, pares, cfg)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_calibrar.py -v`
Expected: PASS — 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/calibrar.py tests/test_calibrar.py
git commit -m "feat: calibracao por backtest (lambda so infla; nada trava)"
```

---

### Task 9: `minmax` — a linha final do item

**Files:**
- Create: `src/minmax.py`
- Test: `tests/test_minmax.py`

**Interfaces:**
- Consumes: `escada.subir` (Task 7), `simular.distribuicao` (Task 6).
- Produces: `minmax.calcular(cod, info: dict, ajuste: dict, f_dow, lam: float, cfg, rng) -> dict` com as chaves `codigo, descricao, prateleira, curva, caixa_mae, giro_dia, min_cx, min_un, max_cx, max_un, sem_historico, estourou_teto`.

**Regras (spec §6.6):**
- `min_cx = escada.subir(D*_7d, caixa_mae, 0.95, maxCaixas, piso=1)`
- `max_cx = escada.subir(D*_30d, caixa_mae, 0.95, maxCaixas, piso=min_cx)` ← o `piso=min_cx` é o que garante `max ≥ min` **sempre**, sem gambiarra depois.
- `D* = λ × D`.
- Item sem histórico ⇒ `μ = 0` ⇒ ambos caem no piso de 1 caixa, e `sem_historico = True`.

- [ ] **Step 1: Write the failing test**

Crie `tests/test_minmax.py`:

```python
# -*- coding: utf-8 -*-
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import minmax  # noqa: E402

CFG = {"percentil": 0.95, "escada": {"maxCaixas": 500},
       "simulacao": {"sorteios": 3000, "semente": 42},
       "horizonte": {"minDiasCorridos": 7, "maxDiasCorridos": 30}}
F = [1.0] * 6
INFO = {"descricao": "X", "caixa_mae": 12, "prateleira": "P1", "curva": "A"}


def _rng():
    return np.random.default_rng(42)


def test_max_nunca_fica_abaixo_do_min():
    for mu in (0.0, 0.01, 0.5, 3.0, 50.0, 500.0):
        r = minmax.calcular(1, INFO, {"mu": mu, "r": 2.0, "dias_limpos": 100},
                            F, 1.0, CFG, _rng())
        assert r["max_cx"] >= r["min_cx"], f"mu={mu}"
        assert r["max_un"] >= r["min_un"]


def test_item_lento_cai_no_piso_de_1_caixa():
    r = minmax.calcular(1, INFO, {"mu": 0.01, "r": None, "dias_limpos": 100},
                        F, 1.0, CFG, _rng())
    assert r["min_cx"] == 1 and r["max_cx"] == 1
    assert r["min_un"] == 12 and r["max_un"] == 12


def test_item_sem_historico_e_marcado_e_cai_no_piso():
    r = minmax.calcular(1, INFO, {"mu": 0.0, "r": None, "dias_limpos": 0},
                        F, 1.0, CFG, _rng())
    assert r["sem_historico"] is True
    assert r["min_cx"] == 1 and r["max_cx"] == 1


def test_item_rapido_tem_max_bem_maior_que_min():
    r = minmax.calcular(1, INFO, {"mu": 30.0, "r": 5.0, "dias_limpos": 150},
                        F, 1.0, CFG, _rng())
    assert r["max_cx"] > r["min_cx"] * 3   # 30d corridos ~ 4.3x a semana


def test_lambda_maior_empurra_os_dois_para_cima():
    base = minmax.calcular(1, INFO, {"mu": 10.0, "r": 3.0, "dias_limpos": 150},
                           F, 1.0, CFG, _rng())
    inflado = minmax.calcular(1, INFO, {"mu": 10.0, "r": 3.0, "dias_limpos": 150},
                              F, 2.0, CFG, _rng())
    assert inflado["min_cx"] > base["min_cx"]
    assert inflado["max_cx"] > base["max_cx"]


def test_caixa_mae_1_faz_a_escada_virar_unidades():
    info = dict(INFO, caixa_mae=1)
    r = minmax.calcular(1, info, {"mu": 10.0, "r": None, "dias_limpos": 150},
                        F, 1.0, CFG, _rng())
    assert r["min_un"] == r["min_cx"]


def test_un_e_sempre_cx_vezes_caixa_mae():
    r = minmax.calcular(1, INFO, {"mu": 7.0, "r": 3.0, "dias_limpos": 150},
                        F, 1.0, CFG, _rng())
    assert r["min_un"] == r["min_cx"] * 12
    assert r["max_un"] == r["max_cx"] * 12


def test_reprodutivel():
    a = minmax.calcular(1, INFO, {"mu": 7.0, "r": 3.0, "dias_limpos": 150},
                        F, 1.0, CFG, _rng())
    b = minmax.calcular(1, INFO, {"mu": 7.0, "r": 3.0, "dias_limpos": 150},
                        F, 1.0, CFG, _rng())
    assert a == b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_minmax.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'minmax'`

- [ ] **Step 3: Write minimal implementation**

Crie `src/minmax.py`:

```python
# -*- coding: utf-8 -*-
"""A linha final de cada item (spec §6.6).

UNICO modulo que conhece caixa_mae (spec D8): todo o calculo antes daqui roda em
UNIDADES; a caixa so aparece no ultimo passo, e vem sempre do CADASTRO (D7).

max_cx usa piso=min_cx: e o que garante max >= min SEMPRE, por construcao, sem
precisar de um "if max < min" remendado depois."""
import escada
import simular


def calcular(cod, info, ajuste, f_dow, lam, cfg, rng):
    caixa = info["caixa_mae"]
    mu, r = ajuste["mu"], ajuste["r"]

    d7 = simular.distribuicao(mu, r, f_dow, cfg["horizonte"]["minDiasCorridos"], cfg, rng) * lam
    d30 = simular.distribuicao(mu, r, f_dow, cfg["horizonte"]["maxDiasCorridos"], cfg, rng) * lam

    limiar = cfg["percentil"]
    teto = cfg["escada"]["maxCaixas"]

    min_cx, estourou_min = escada.subir(d7, caixa, limiar, teto, piso=1)
    max_cx, estourou_max = escada.subir(d30, caixa, limiar, teto, piso=min_cx)

    return {
        "codigo": cod,
        "descricao": info["descricao"],
        "prateleira": info["prateleira"],
        "curva": info["curva"],
        "caixa_mae": caixa,
        "giro_dia": round(mu, 3),
        "min_cx": min_cx,
        "min_un": min_cx * caixa,
        "max_cx": max_cx,
        "max_un": max_cx * caixa,
        "sem_historico": ajuste["dias_limpos"] == 0 or mu <= 0,
        "estourou_teto": bool(estourou_min or estourou_max),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_minmax.py -v`
Expected: PASS — 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/minmax.py tests/test_minmax.py
git commit -m "feat: minmax (escada 7d/30d, piso=min_cx garante max>=min)"
```

---

### Task 10: `relatorio` — PDF por prateleira

**Files:**
- Create: `src/relatorio.py`
- Test: `tests/test_relatorio.py`

**Interfaces:**
- Consumes: `minmax.calcular` (Task 9).
- Produces:
  - `relatorio.html(linhas: list[dict], resumo: dict) -> str`
  - `relatorio.pdf(caminho_html: str, caminho_pdf: str) -> bool` — Edge headless; `False` se falhar (o HTML continua valendo).

**Contexto (spec §8):** agrupado por **prateleira** (o endereço físico do ERP, ex. "PRATELEIRA 33"), ordenado por prateleira → descrição, para o repositor caminhar a gôndola na ordem. ~4.634 itens: é documento de referência, não lista de ação.

**O rodapé é obrigatório e não é enfeite** (spec §8, §7.4): período, dias úteis, dias censurados, `λ`, **cobertura real medida**, resultado do bootstrap, nº de elegíveis, e a nota de que domingo/feriado não contam. É o que torna o número auditável em vez de mágico. Se a cobertura ficou abaixo do limiar, sai **destacado no cabeçalho** (D16/§7.4).

- [ ] **Step 1: Write the failing test**

Crie `tests/test_relatorio.py`:

```python
# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import relatorio  # noqa: E402

LINHAS = [
    {"codigo": 2, "descricao": "BANANA", "prateleira": "PRATELEIRA 10", "curva": "A",
     "caixa_mae": 12, "giro_dia": 5.0, "min_cx": 3, "min_un": 36, "max_cx": 11,
     "max_un": 132, "sem_historico": False, "estourou_teto": False},
    {"codigo": 1, "descricao": "ABACAXI", "prateleira": "PRATELEIRA 10", "curva": "B",
     "caixa_mae": 6, "giro_dia": 0.01, "min_cx": 1, "min_un": 6, "max_cx": 1,
     "max_un": 6, "sem_historico": False, "estourou_teto": False},
    {"codigo": 3, "descricao": "CACAU", "prateleira": "PRATELEIRA 2", "curva": None,
     "caixa_mae": 1, "giro_dia": 0.0, "min_cx": 1, "min_un": 1, "max_cx": 1,
     "max_un": 1, "sem_historico": True, "estourou_teto": False},
]
RESUMO = {"periodo": "2026-01-22 a 2026-07-17", "dias_uteis": 150,
          "dias_censurados": 812, "lam": 1.0, "cobertura": 0.96,
          "bootstrap": 0.08, "elegiveis": 1421, "itens": 3,
          "gerado_em": "2026-08-01 04:00:00"}


def test_agrupa_por_prateleira_em_ordem():
    h = relatorio.html(LINHAS, RESUMO)
    assert h.index("PRATELEIRA 2") < h.index("PRATELEIRA 10")


def test_ordena_por_descricao_dentro_da_prateleira():
    h = relatorio.html(LINHAS, RESUMO)
    assert h.index("ABACAXI") < h.index("BANANA")


def test_mostra_min_e_max_em_un_e_cx():
    h = relatorio.html(LINHAS, RESUMO)
    assert "36" in h and "3" in h and "132" in h and "11" in h


def test_marca_item_sem_historico():
    assert "sem histórico" in relatorio.html(LINHAS, RESUMO).lower()


def test_rodape_tem_a_auditoria_completa():
    h = relatorio.html(LINHAS, RESUMO)
    for pedaco in ("2026-01-22", "150", "812", "1421", "domingo"):
        assert pedaco in h, f"falta {pedaco} no rodape"
    assert "96" in h        # a cobertura medida


def test_cobertura_abaixo_do_limiar_sai_destacada_no_cabecalho():
    resumo = dict(RESUMO, cobertura=0.71, lam=3.0)
    h = relatorio.html(LINHAS, resumo)
    cabecalho = h[:h.index("PRATELEIRA 2")]
    assert "71" in cabecalho
    assert "atenção" in cabecalho.lower() or "atencao" in cabecalho.lower()


def test_bootstrap_ruim_avisa():
    h = relatorio.html(LINHAS, dict(RESUMO, bootstrap=0.40))
    assert "40" in h


def test_html_escapa_a_descricao():
    linhas = [dict(LINHAS[0], descricao="A & <B>")]
    h = relatorio.html(linhas, RESUMO)
    assert "&amp;" in h and "&lt;B&gt;" in h
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_relatorio.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'relatorio'`

- [ ] **Step 3: Write minimal implementation**

Crie `src/relatorio.py`:

```python
# -*- coding: utf-8 -*-
"""PDF por prateleira (spec §8).

Agrupado pelo ENDERECO FISICO do ERP ("PRATELEIRA 33") e ordenado por
prateleira -> descricao: o repositor caminha a gondola na ordem, sem ficar
procurando item na lista.

O rodape NAO e enfeite (spec §8/§7.4): periodo, dias uteis, dias censurados,
lambda, COBERTURA REAL MEDIDA, bootstrap e nº de elegiveis. E o que torna o
numero auditavel em vez de magico. Cobertura abaixo do limiar sai destacada no
cabecalho — o dono le o numero, o sistema nao esconde nem trava (D16)."""
import html as _html
import os
import re
import shutil
import subprocess


def _chave_natural(s):
    """PRATELEIRA 2 antes de PRATELEIRA 10 — ordem em que o repositor caminha,
    nao a ordem lexicografica ("10" < "2" em string)."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]

CSS = """
body{font-family:Segoe UI,Arial,sans-serif;font-size:11px;margin:18px;color:#111}
h1{font-size:17px;margin:0 0 2px}
.sub{color:#555;margin-bottom:10px}
.alerta{background:#fde8e8;border:1px solid #e11;padding:8px;margin:8px 0;border-radius:4px}
h2{font-size:13px;margin:14px 0 4px;background:#eee;padding:4px 6px;border-radius:3px}
table{border-collapse:collapse;width:100%}
th,td{border:1px solid #ccc;padding:3px 5px;text-align:right}
th:nth-child(1),td:nth-child(1),th:nth-child(2),td:nth-child(2){text-align:left}
th{background:#f5f5f5}
tr:nth-child(even){background:#fafafa}
.mm{font-weight:bold}
.nota{color:#a00;font-size:10px}
footer{margin-top:16px;border-top:1px solid #ccc;padding-top:6px;color:#555;font-size:10px}
"""


def html(linhas, resumo):
    e = _html.escape
    por_prat = {}
    for ln in linhas:
        por_prat.setdefault(ln["prateleira"] or "(sem prateleira)", []).append(ln)

    p = [f"<style>{CSS}</style>",
         "<h1>Exposição na prateleira — mínimo e máximo</h1>",
         f"<div class='sub'>Gerado em {e(str(resumo['gerado_em']))} · "
         f"{resumo['itens']} itens</div>"]

    cob = resumo["cobertura"]
    if cob < 0.95:
        p.append(
            f"<div class='alerta'><b>Atenção:</b> a cobertura real medida no backtest foi de "
            f"<b>{cob * 100:.0f}%</b>, abaixo dos 95% pretendidos, mesmo com a folga máxima "
            f"(λ={resumo['lam']:.2f}). Os números abaixo estão entregues assim mesmo — "
            f"trate o mínimo como otimista.</div>")

    tol = resumo.get("tol_bootstrap")
    if tol is not None and resumo["bootstrap"] > tol:
        p.append(
            f"<div class='alerta'><b>Atenção:</b> o modelo divergiu "
            f"{resumo['bootstrap'] * 100:.0f}% do histórico real no teste de 7 dias "
            f"(tolerância {tol * 100:.0f}%). O MÍN está aferido pelo backtest; "
            f"o MÁX de 30 dias depende mais do modelo — confira os itens grandes.</div>")

    for prat in sorted(por_prat, key=_chave_natural):
        p.append(f"<h2>{e(prat)}</h2>")
        p.append("<table><tr><th>Código</th><th>Descrição</th><th>Cx-mãe</th>"
                 "<th>Giro un/dia</th><th>MÍN un</th><th>MÍN cx</th>"
                 "<th>MÁX un</th><th>MÁX cx</th></tr>")
        for ln in sorted(por_prat[prat], key=lambda x: str(x["descricao"])):
            nota = ""
            if ln["sem_historico"]:
                nota = " <span class='nota'>(sem histórico)</span>"
            elif ln["estourou_teto"]:
                nota = " <span class='nota'>(acima do teto de busca)</span>"
            p.append(
                f"<tr><td>{ln['codigo']}</td><td>{e(str(ln['descricao']))}{nota}</td>"
                f"<td>{ln['caixa_mae']}</td><td>{ln['giro_dia']:.2f}</td>"
                f"<td class='mm'>{ln['min_un']}</td><td>{ln['min_cx']}</td>"
                f"<td class='mm'>{ln['max_un']}</td><td>{ln['max_cx']}</td></tr>")
        p.append("</table>")

    p.append(
        "<footer>"
        f"Histórico: {e(str(resumo['periodo']))} · {resumo['dias_uteis']} dias úteis · "
        f"{resumo['dias_censurados']} dias descartados por ruptura de estoque.<br>"
        f"MÍN = menor nº de caixas com ≥95% de confiança de cobrir 7 dias corridos; "
        f"MÁX = idem para 30 dias corridos. Piso de 1 caixa-mãe.<br>"
        f"Folga da calibração λ={resumo['lam']:.2f} · "
        f"cobertura real medida no backtest: <b>{cob * 100:.0f}%</b> "
        f"sobre {resumo['elegiveis']} itens elegíveis · "
        f"erro mediano vs bootstrap: {resumo['bootstrap'] * 100:.0f}%.<br>"
        f"Giro do salão apenas — a venda do atacado (PDV 11/12) não entra, "
        f"porque não sai da prateleira. Domingo e feriados não contam como dia."
        "</footer>")
    return "\n".join(p)


def _edge():
    for c in (shutil.which("msedge"),
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if c and os.path.exists(c):
            return c
    return None


def pdf(caminho_html, caminho_pdf):
    """Edge headless. Devolve False se nao rolar — o HTML continua valendo, e o
    envio cai para ele (o Chromium do puppeteer NAO baixa no ponte: allow-scripts)."""
    exe = _edge()
    if not exe:
        return False
    try:
        subprocess.run(
            [exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
             f"--print-to-pdf={os.path.abspath(caminho_pdf)}",
             f"file:///{os.path.abspath(caminho_html)}"],
            check=True, timeout=180,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return os.path.exists(caminho_pdf)
    except (subprocess.SubprocessError, OSError):
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_relatorio.py -v`
Expected: PASS — 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/relatorio.py tests/test_relatorio.py
git commit -m "feat: relatorio HTML/PDF por prateleira com rodape auditavel"
```

---

### Task 11: `rodar` + `enviar` — o pipeline e o envio

**Files:**
- Create: `src/enviar.py`, `src/rodar.py`
- Test: `tests/test_rodar.py`

**Interfaces:**
- Consumes: **todos** os módulos anteriores.
- Produces:
  - `enviar.ja_enviou_este_mes(saida_dir, hoje_iso) -> bool` e `enviar.marcar_enviado(saida_dir, hoje_iso) -> None` — idempotência (spec §10).
  - `enviar.whatsapp(caminho_anexo, texto, cfg) -> bool` — `False` (sem enviar) se `dryRun`.
  - `rodar.pipeline(cfg, rng) -> dict` — `{"linhas": [...], "resumo": {...}}`.
  - CLI: `python src/rodar.py [--dry-run] [--forcar-envio] [--config X]`.

**Contexto:** `dryRun: true` é o default e **assim fica** até o dono validar os números contra a gôndola (spec D14) — mesmo padrão do detector de salão. O envio delega ao `enviar.mjs` do bridge (a sessão Baileys já está logada; **não** gerar QR novo).

**O bootstrap (spec §7.3):** para os itens elegíveis, compara o P95 da NB com o percentil empírico das janelas de 7 dias corridos reais. **Não trava nada** — vai para o rodapé como aferição.

- [ ] **Step 1: Write the failing test**

Crie `tests/test_rodar.py`:

```python
# -*- coding: utf-8 -*-
import json
import os
import sys
import tempfile
from datetime import date, timedelta

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import config as cfgmod  # noqa: E402
import enviar            # noqa: E402
import rodar             # noqa: E402

PESO = {0: 0.7, 1: 0.8, 2: 0.9, 3: 1.1, 4: 1.3, 5: 1.6}


def _montar(d):
    """Gera os 3 CSVs de entrada num diretorio temporario."""
    hoje = date(2026, 7, 17)
    v = ["codigo;data;canal;unidades"]
    for k in range(200):
        dia = hoje - timedelta(days=k)
        if dia.weekday() == 6:
            continue
        for cod, base in ((1, 30.0), (2, 0.02)):
            v.append(f"{cod};{dia.isoformat()};salao;{base * PESO[dia.weekday()]:.3f}")
        v.append(f"1;{dia.isoformat()};atacado;600")
    c = ["codigo;descricao;caixa_mae;prateleira;curva",
         "1;RAPIDO;12;PRATELEIRA 1;A",
         "2;LENTO;27;PRATELEIRA 2;C"]
    e = ["codigo;data;qtd", f"1;{(hoje - timedelta(days=30)).isoformat()};5000"]
    for nome, linhas in (("v.csv", v), ("c.csv", c), ("e.csv", e)):
        with open(os.path.join(d, nome), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(linhas) + "\n")


def _cfg(d):
    cfg = cfgmod.carregar(os.path.join(d, "inexistente.json"))
    cfg["entrada"] = {"vendas_canal_csv": os.path.join(d, "v.csv"),
                      "catalogo_csv": os.path.join(d, "c.csv"),
                      "entradas_csv": os.path.join(d, "e.csv")}
    cfg["saida"] = {"dir": os.path.join(d, "out")}
    cfg["simulacao"]["sorteios"] = 2000
    return cfg


def test_pipeline_ponta_a_ponta():
    with tempfile.TemporaryDirectory() as d:
        _montar(d)
        out = rodar.pipeline(_cfg(d), np.random.default_rng(42))
        assert len(out["linhas"]) == 2
        por_cod = {l["codigo"]: l for l in out["linhas"]}
        assert por_cod[2]["min_cx"] == 1 and por_cod[2]["max_cx"] == 1   # lento -> piso
        assert por_cod[1]["min_cx"] > 1                                   # rapido
        assert por_cod[1]["max_cx"] >= por_cod[1]["min_cx"]


def test_o_atacado_nao_entra_no_giro():
    # o item 1 leva 600 un/dia de atacado contra ~30 de salao: se vazasse, o
    # giro estouraria
    with tempfile.TemporaryDirectory() as d:
        _montar(d)
        out = rodar.pipeline(_cfg(d), np.random.default_rng(42))
        giro = {l["codigo"]: l["giro_dia"] for l in out["linhas"]}[1]
        assert giro < 60, f"giro {giro} contaminado pelo atacado (spec D3)"


def test_todo_item_do_catalogo_recebe_min_max():
    with tempfile.TemporaryDirectory() as d:
        _montar(d)
        # item 3 esta no catalogo e nunca vendeu: tem que sair com piso de 1 cx
        with open(os.path.join(d, "c.csv"), "a", encoding="utf-8", newline="\n") as f:
            f.write("3;NUNCA VENDEU;6;PRATELEIRA 3;\n")
        out = rodar.pipeline(_cfg(d), np.random.default_rng(42))
        l3 = {l["codigo"]: l for l in out["linhas"]}[3]
        assert l3["min_cx"] == 1 and l3["max_cx"] == 1
        assert l3["sem_historico"] is True


def test_resumo_tem_o_que_o_rodape_precisa():
    with tempfile.TemporaryDirectory() as d:
        _montar(d)
        r = rodar.pipeline(_cfg(d), np.random.default_rng(42))["resumo"]
        for k in ("periodo", "dias_uteis", "dias_censurados", "lam", "cobertura",
                  "bootstrap", "tol_bootstrap", "elegiveis", "itens", "gerado_em"):
            assert k in r, f"falta {k}"
        assert r["lam"] >= 1.0


def test_dry_run_nao_envia():
    cfg = {"whatsapp": {"dryRun": True, "destino": "5521999999999",
                        "enviarMjs": "nao/existe.mjs"}}
    assert enviar.whatsapp("x.pdf", "oi", cfg) is False


def test_sem_destino_nao_envia():
    cfg = {"whatsapp": {"dryRun": False, "destino": "", "enviarMjs": "nao/existe.mjs"}}
    assert enviar.whatsapp("x.pdf", "oi", cfg) is False


def test_idempotencia_rodar_2x_no_mes_nao_envia_2x():
    with tempfile.TemporaryDirectory() as d:
        assert enviar.ja_enviou_este_mes(d, "2026-08-01") is False
        enviar.marcar_enviado(d, "2026-08-01")
        assert enviar.ja_enviou_este_mes(d, "2026-08-15") is True   # mesmo mes
        assert enviar.ja_enviou_este_mes(d, "2026-09-01") is False  # mes novo
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_rodar.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rodar'`

- [ ] **Step 3: Write minimal implementation**

Crie `src/enviar.py`:

```python
# -*- coding: utf-8 -*-
"""Envio pelo WhatsApp — delega ao Baileys JA LOGADO do bridge.

Nao gerar QR novo: a sessao do bridge (scripts/whatsapp/enviar.mjs) ja esta
conectada, e foi essa a decisao no detector de salao. O Chromium do puppeteer
nao baixa no ponte (allow-scripts), entao esta e a unica via.

dryRun=true e o DEFAULT e assim fica ate o dono validar os numeros contra a
gondola (spec D14): 4.634 min/max errados executados no salao custam caro."""
import os
import subprocess

MARCA = "ultimo_envio.txt"


def ja_enviou_este_mes(saida_dir, hoje_iso):
    """Idempotencia (spec §10): a tarefa e mensal, mas o Agendador pode
    disparar de novo (PC religado, rodada manual). Nao mandar o mesmo PDF duas
    vezes para o dono."""
    caminho = os.path.join(saida_dir, MARCA)
    if not os.path.exists(caminho):
        return False
    with open(caminho, encoding="utf-8") as f:
        return f.read().strip()[:7] == hoje_iso[:7]


def marcar_enviado(saida_dir, hoje_iso):
    os.makedirs(saida_dir, exist_ok=True)
    with open(os.path.join(saida_dir, MARCA), "w", encoding="utf-8") as f:
        f.write(hoje_iso)


def whatsapp(caminho_anexo, texto, cfg):
    w = cfg["whatsapp"]
    if w.get("dryRun", True):
        print(f"[dry-run] NAO enviado. Anexo pronto em: {caminho_anexo}")
        return False
    destino = (w.get("destino") or "").strip()
    if not destino:
        print("[aviso] whatsapp.destino vazio: nao enviei.")
        return False
    mjs = w.get("enviarMjs") or ""
    if not os.path.exists(mjs):
        print(f"[aviso] enviar.mjs nao encontrado em {mjs}: nao enviei.")
        return False
    try:
        subprocess.run(["node", mjs, destino, texto, os.path.abspath(caminho_anexo)],
                       check=True, timeout=300)
        return True
    except (subprocess.SubprocessError, OSError) as e:
        print(f"[aviso] falha no envio: {e}")
        return False
```

Crie `src/rodar.py`:

```python
# -*- coding: utf-8 -*-
"""Orquestrador (spec §5). Encadeia: importar -> calendario -> censura -> dow
-> modelo -> calibrar -> minmax -> relatorio -> enviar.

Ordem de dependencia (nao inverter): escada nao chama ninguem; calibrar chama
escada; minmax chama escada. Se calibrar e minmax se importarem, ha ciclo."""
import argparse
import os
import sys
from datetime import date, datetime, timedelta

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calendario  # noqa: E402
import calibrar    # noqa: E402
import censura     # noqa: E402
import config as cfgmod  # noqa: E402
import dow         # noqa: E402
import enviar      # noqa: E402
import importar    # noqa: E402
import minmax      # noqa: E402
import modelo      # noqa: E402
import relatorio   # noqa: E402
import simular     # noqa: E402


def _janelas_de_7_dias(vendas_item, cal, fora, a_partir_de=None):
    """Soma do salao em cada janela de 7 dias corridos LIMPA (nenhum dia
    censurado dentro), restrita a VIDA do item (1a a ultima venda). Sem essa
    restricao, um item novo contribuiria janelas de zero de ANTES de existir —
    deflacionando o P95 empirico do bootstrap e inflando a cobertura do
    backtest com acertos triviais. `a_partir_de` (ISO) restringe o INICIO
    (usado p/ pegar so as janelas do holdout)."""
    vida = calendario.janela_do_item(vendas_item, cal)
    if vida is None:
        return []
    dias = cal["dias"]
    ini = date.fromisoformat(dias[vida[0]])
    fim = date.fromisoformat(dias[vida[1]])
    if a_partir_de:
        apd = date.fromisoformat(a_partir_de)
        if apd > ini:
            ini = apd
    idx = set(dias)
    out = []
    d = ini
    while d + timedelta(days=6) <= fim:
        janela = [(d + timedelta(days=k)).isoformat() for k in range(7)]
        abertos = [x for x in janela if x in idx]
        if abertos and not any(x in fora for x in abertos):
            out.append((janela[0], sum((vendas_item.get(x) or {"salao": 0.0})["salao"]
                                       for x in abertos)))
        d += timedelta(days=1)
    return out


def pipeline(cfg, rng):
    vendas = importar.ler_vendas(cfg["entrada"]["vendas_canal_csv"])
    catalogo = importar.ler_catalogo(cfg["entrada"]["catalogo_csv"])
    entradas = importar.ler_entradas(cfg["entrada"]["entradas_csv"])

    cal = calendario.construir(vendas, cfg)

    fora_por_item = {}
    for cod in catalogo:
        f = censura.dias_censurados(cod, vendas.get(cod, {}), entradas.get(cod, []), cal, cfg)
        if f:
            fora_por_item[cod] = f

    f_dow = dow.fatores(vendas, catalogo, cal, fora_por_item, cfg)

    # 1a passada: ajustes sem r_global (p/ poder calcular a mediana)
    def _f(cod):
        return f_dow.get(catalogo[cod]["prateleira"] or "(sem prateleira)", f_dow[dow.LOJA])

    brutos = {cod: modelo.ajustar(cod, vendas.get(cod, {}), cal,
                                  fora_por_item.get(cod, set()), _f(cod), cfg)
              for cod in catalogo}
    rg = modelo.r_global(list(brutos.values()))
    ajustes = {cod: modelo.ajustar(cod, vendas.get(cod, {}), cal,
                                   fora_por_item.get(cod, set()), _f(cod), cfg, r_global=rg)
               for cod in catalogo}

    # elegiveis + backtest -> lambda
    janelas = {cod: _janelas_de_7_dias(vendas.get(cod, {}), cal, fora_por_item.get(cod, set()))
               for cod in catalogo}
    n_janelas = {cod: len(v) for cod, v in janelas.items()}
    eleg = calibrar.elegiveis(ajustes, n_janelas, cfg)

    # Backtest SEM ESPIAR O FUTURO (spec §7.1): o modelo usado na medicao e
    # ajustado SO com os dias anteriores ao holdout (as ultimas N semanas);
    # as janelas do holdout sao a prova. Sem esse corte, o modelo teria visto
    # as proprias semanas que deveria prever — cobertura inflada, lambda
    # otimista, e a folga que o dono pediu sairia menor do que a real.
    # O modelo de PRODUCAO (as linhas finais) segue usando o periodo inteiro;
    # o corte existe apenas para medir a otimismo honestamente.
    semanas = cfg["validacao"]["semanasHoldout"]
    n_dias = len(cal["dias"])
    corte = max(0, n_dias - semanas * 6)          # ~6 dias uteis por semana
    cal_treino = {"dias": cal["dias"][:corte],
                  "indice": {d: i for i, d in enumerate(cal["dias"][:corte])},
                  "fechados": cal["fechados"]}
    inicio_holdout = cal["dias"][corte] if corte < n_dias else None

    pares = []
    if inicio_holdout:
        for cod in eleg:
            aj_t = modelo.ajustar(cod, vendas.get(cod, {}), cal_treino,
                                  fora_por_item.get(cod, set()), _f(cod), cfg,
                                  r_global=rg)
            if aj_t["mu"] <= 0:
                continue                # item novo demais: nasceu dentro do holdout
            d7_t = simular.distribuicao(aj_t["mu"], aj_t["r"], _f(cod),
                                        cfg["horizonte"]["minDiasCorridos"], cfg, rng)
            for _, real in _janelas_de_7_dias(vendas.get(cod, {}), cal,
                                              fora_por_item.get(cod, set()),
                                              a_partir_de=inicio_holdout):
                pares.append({"amostras": d7_t,
                              "caixa_mae": catalogo[cod]["caixa_mae"], "real": real})
    lam, cobertura = calibrar.buscar_lambda(pares, cfg) if pares else (1.0, 1.0)

    # bootstrap: so aferição de rodape (nao trava — spec §7.3)
    erros = []
    for cod in eleg:
        reais = [x[1] for x in janelas[cod]]
        if len(reais) < cfg["validacao"]["minJanelas"]:
            continue
        emp = float(np.percentile(reais, cfg["percentil"] * 100))
        d7 = simular.distribuicao(ajustes[cod]["mu"], ajustes[cod]["r"], _f(cod),
                                  cfg["horizonte"]["minDiasCorridos"], cfg, rng)
        nb = float(np.percentile(d7, cfg["percentil"] * 100))
        if emp > 0:
            erros.append(abs(nb - emp) / emp)
    bootstrap = float(np.median(erros)) if erros else 0.0

    linhas = [minmax.calcular(cod, catalogo[cod], ajustes[cod], _f(cod), lam, cfg, rng)
              for cod in sorted(catalogo)]

    resumo = {
        "periodo": f"{cal['dias'][0]} a {cal['dias'][-1]}" if cal["dias"] else "(sem dados)",
        "dias_uteis": len(cal["dias"]),
        "dias_censurados": sum(len(v) for v in fora_por_item.values()),
        "lam": lam,
        "cobertura": cobertura,
        "bootstrap": bootstrap,
        "tol_bootstrap": cfg["validacao"]["tolBootstrap"],
        "elegiveis": len(eleg),
        "itens": len(linhas),
        "gerado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    return {"linhas": linhas, "resumo": resumo}


def main():
    ap = argparse.ArgumentParser(description="MIN/MAX de exposicao na prateleira")
    ap.add_argument("--config", default=None)
    ap.add_argument("--dry-run", action="store_true", help="forca dryRun mesmo se o config disser false")
    ap.add_argument("--forcar-envio", action="store_true",
                    help="reenvia mesmo se ja enviou este mes")
    args = ap.parse_args()

    cfg = cfgmod.carregar(args.config)
    if args.dry_run:
        cfg["whatsapp"]["dryRun"] = True

    rng = np.random.default_rng(cfg["simulacao"]["semente"])
    out = pipeline(cfg, rng)

    saida = cfg["saida"]["dir"]
    os.makedirs(saida, exist_ok=True)
    caminho_html = os.path.join(saida, "exposicao_min_max.html")
    caminho_pdf = os.path.join(saida, "exposicao_min_max.pdf")
    with open(caminho_html, "w", encoding="utf-8") as f:
        f.write(relatorio.html(out["linhas"], out["resumo"]))
    anexo = caminho_pdf if relatorio.pdf(caminho_html, caminho_pdf) else caminho_html

    r = out["resumo"]
    texto = (f"Exposicao na prateleira — MIN/MAX ({r['gerado_em'][:10]})\n"
             f"{r['itens']} itens · cobertura medida {r['cobertura'] * 100:.0f}% "
             f"(folga λ={r['lam']:.2f})")
    print(texto)
    print(f"  periodo {r['periodo']} · {r['dias_uteis']} dias uteis · "
          f"{r['dias_censurados']} dias descartados por ruptura")
    print(f"  relatorio: {anexo}")

    hoje = r["gerado_em"][:10]
    if not args.forcar_envio and enviar.ja_enviou_este_mes(saida, hoje):
        print("  [idempotencia] ja enviei este mes; nao reenviei "
              "(use --forcar-envio se quiser mesmo assim).")
        return
    if enviar.whatsapp(anexo, texto, cfg):
        enviar.marcar_enviado(saida, hoje)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_rodar.py -v`
Expected: PASS — 7 passed

Suíte inteira:

Run: `python -m pytest tests/ -v`
Expected: PASS — todos (≈65 testes)

- [ ] **Step 5: Commit**

```bash
git add src/enviar.py src/rodar.py tests/test_rodar.py
git commit -m "feat: pipeline completo + envio via Baileys do bridge (dryRun default)"
```

---

### Task 12: Implantar no ponte (dry-run) e entregar ao dono

**Files:**
- Modify: `README.md` (secção "Estado")
- Test: manual, no PC-ponte

**Contexto:** o repo é privado e o token do ponte não alcança repo novo — o detector foi clonado por **git bundle + scp** (o `git pull` só funciona no bridge). Use o mesmo caminho.

- [ ] **Step 1: Levar o repo ao ponte**

```bash
cd /c/Users/COMPUTADOR/exposicao-atacaderj
git bundle create /tmp/exposicao.bundle --all
scp -i ~/.ssh/id_ed25519_ponte /tmp/exposicao.bundle User@100.99.176.6:C:/Users/User/exposicao.bundle
ssh -i ~/.ssh/id_ed25519_ponte User@100.99.176.6 "git clone C:\Users\User\exposicao.bundle C:\Users\User\exposicao-atacaderj"
```
Expected: `Cloning into 'C:\Users\User\exposicao-atacaderj'... done.`

- [ ] **Step 2: Configurar e rodar a suíte lá**

```bash
ssh -i ~/.ssh/id_ed25519_ponte User@100.99.176.6 "cd C:\Users\User\exposicao-atacaderj && copy config.example.json config.local.json && python -m pytest tests\ -q"
```
Expected: todos passam. O `config.example.json` já aponta para os caminhos do ponte (`C:/Users/User/erp-bridge-atacaderj/saida/...`) e já vem com `dryRun: true`.

**⚠️ Confira o caminho do `entradas.csv` antes de rodar.** O default aponta para
`.../erp-bridge-atacaderj/saida/detector-salao/entradas.csv`, mas no ponte o `config.local.json`
do bridge redireciona `saida.detector_salao_dir` para o `data/input` do detector — o arquivo
real provavelmente está em `C:/Users/User/detector-ruptura-atacaderj/data/input/entradas.csv`.
Leia o config do bridge no ponte e ajuste `entrada.entradas_csv` no `config.local.json` da
exposicao para onde o arquivo de fato existe:

```bash
ssh -i ~/.ssh/id_ed25519_ponte User@100.99.176.6 "python -c \"import json; print(json.load(open(r'C:\Users\User\erp-bridge-atacaderj\config.local.json', encoding='utf-8'))['saida']['detector_salao_dir'])\""
```
Se o `importar` não achar o arquivo, ele dá erro claro — mas melhor acertar agora do que na
rodada agendada do mês seguinte.

- [ ] **Step 3: Rodar com os dados REAIS (ainda dry-run)**

```bash
ssh -i ~/.ssh/id_ed25519_ponte User@100.99.176.6 "cd C:\Users\User\exposicao-atacaderj && python src\rodar.py"
```
Expected:
- `~4.634 itens`
- `[dry-run] NAO enviado. Anexo pronto em: ...exposicao_min_max.pdf`
- **Confira contra a spec §3.8** — se estes números destoarem muito, algo está errado:
  - a maioria esmagadora dos itens com `min_cx = max_cx = 1` (spec previu ~1.424 só entre os de caixa > 1, mais os 1.969 lentos)
  - `cobertura` em torno de 95%
  - `dias_censurados` **baixo** — os 4 sinais são restritivos de propósito. Se vier alto (dezenas de milhares), a censura está solta e vai inflar o mín.

- [ ] **Step 4: Entregar ao dono e PARAR**

Traga o PDF para a dev e mande ao dono junto com o `cadastro_caixa_mae_suspeito.csv` (Fase 1, Task 5):

```bash
scp -i ~/.ssh/id_ed25519_ponte User@100.99.176.6:C:/Users/User/exposicao-atacaderj/saida/exposicao_min_max.pdf /tmp/
```

**Não ligue o envio.** `dryRun` vira `false` **só** depois de o dono validar os números contra a gôndola (spec D14). É uma linha no `config.local.json` do ponte, e é decisão dele, não sua.

- [ ] **Step 5: Agendar (mensal, dia 1 às 06:00) e commitar**

Depois da validação do dono, e só então:

```bash
ssh -i ~/.ssh/id_ed25519_ponte User@100.99.176.6 "schtasks /Create /TN \"AtacadeRJ - Exposicao MinMax\" /TR \"python C:\Users\User\exposicao-atacaderj\src\rodar.py\" /SC MONTHLY /D 1 /ST 06:00 /F && schtasks /Run /TN \"AtacadeRJ - Exposicao MinMax\" && timeout /t 300 && schtasks /Query /TN \"AtacadeRJ - Exposicao MinMax\" /FO LIST | findstr /C:\"Last Result\""
```
Expected: `Last Result: 0`

Por que 06:00: o `--only exposicao` das 04:00 já gerou os CSVs, o Movimentos das 05:00 já
atualizou o `entradas.csv`, e o DetectorRuptura-Diario das 05:30 (seg–sáb, mesmo PC) já passou —
a simulação é pesada de CPU e não deve disputar com ele.

```bash
git add README.md
git commit -m "docs: estado - fase 2 no ar em dry-run no ponte"
```

---

## Definição de pronto (Fase 2)

- [ ] `python -m pytest tests/ -v` passa inteiro (≈60 testes) na dev **e** no ponte
- [ ] `python src/rodar.py` roda no ponte com dados reais e gera o PDF
- [ ] Os números batem com o que a spec previu (§3.8): maioria no piso de 1 caixa; `dias_censurados` baixo
- [ ] O dono recebeu o PDF **e** a lista de caixa-mãe suspeita
- [ ] `dryRun` **continua true** até o dono validar
- [ ] Tarefa `AtacadeRJ - Exposicao MinMax` com `Last Result: 0`
- [ ] `git status --short` vazio na dev e no ponte

## Depois (não é escopo deste plano)

- Ligar o envio (`dryRun: false`) — decisão do dono, 1 linha.
- Atualizar a memória do projeto (`STATUS.md` do bridge + a memória do Claude).
- `λ` por faixa de giro, **se** o backtest mostrar cauda ruim concentrada (spec R8) — com dado na mão, não por palpite.
