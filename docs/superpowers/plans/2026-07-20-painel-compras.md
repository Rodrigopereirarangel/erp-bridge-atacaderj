# Painel de Compras (TV + PC) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gerar, na bridge, um painel HTML único (TV sem interação + PC interativo) com 4 quadrantes: validade × promoção relâmpago, ruptura de estoque (detector), cobrança de fornecedor e preço concorrente (reuso do pricing).

**Architecture:** Módulo novo `src/painel_compras.py` no erp-bridge lê 4 fontes independentes (2 queries SQL novas + rounds do detector-estoque + HTML do pricing), monta um payload JSON e o embute num template (`src/templates/painel_compras.html`, padrão `/*__DADOS__*/null` do vendas_mensal). Cada fonte falha sozinha (quadrante mostra "indisponível", geração nunca aborta). Servido por `python -m http.server` no PC-ponte.

**Tech Stack:** Python 3.12 stdlib (sem dependência nova; pyodbc já existe via `src/db.py`), T-SQL (SQL Server 2014, SOMENTE SELECT), HTML/CSS/JS vanilla embutido, pytest, Windows Task Scheduler.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-20-painel-compras-design.md` (com resultados das investigações §10 já incorporados — ver "Fatos do schema" abaixo).
- SQL **somente leitura** (`SELECT`/`WITH`) — `src/db.py` já recusa o resto; nunca instalar nada no servidor `CONCENTRADOR`.
- Nunca commitar senha, custo ou preço; `config.local.json` e `saida/` são gitignored.
- Arquivos de saída via `projections._escrever_atomico` (escrita atômica, UTF-8).
- Código e comentários em pt-BR, snake_case, padrão dos módulos existentes.
- HTML 100% offline: zero CDN/fonte externa/fetch; dados embutidos no próprio arquivo.
- Testes: pytest, arquivos `tests/test_*.py`, rodar com `python -m pytest tests/ -q` a partir da raiz do repo.
- Commits frequentes, mensagens em pt (padrão do repo: `feat:`/`fix:`/`docs:`).

## Fatos do schema (medidos no ponte em 2026-07-20 — NÃO re-investigar)

- **Relâmpago:** `dbo.tbPromocaoRelampago(cdProduto, dtInicio, dtFim, vlVenda, ...)`;
  371 linhas, **247 vigentes** (`GETDATE() BETWEEN dtInicio AND dtFim`). `cdTipoPromocao`
  vem NULL nas linhas vivas; o marcador real é a própria tabela.
- **Fornecedor do pedido de compra:** NÃO está em `tbPedido`. Vem de
  `tbPedidoCompra.cdPessoaComercial → tbPessoa.nmPessoa` (join validado com nomes reais).
- **Telefone:** `dbo.tbTelefone(cdPessoa, cdTelefone, DDD, Numero, Contato)`;
  join direto por `cdPessoa`; `cdTelefone = 1` é o principal. Dados imperfeitos
  ("00/00000000") existem — tratar na projeção.
- **Valor pendente:** `vlPedidoItem` é POR VOLUME (mesma convenção do `PEDIDOS_VENDA`):
  valor pendente = `(qtPedidoItem − COALESCE(qtAtendida,0)) × vlPedidoItem`.
- **Pedidos abertos:** 534 no total, **494 com 7+ dias** — a loja não encerra pedido
  morto no ERP (há pedidos de janeiro "abertos"). Por isso a query tem janela máxima
  `{cobranca_max_dias}` (padrão 60) e os mais velhos viram só um contador de
  "abandonados".
- **Round do detector-estoque:** `<repo>/data/rounds/<YYYY-MM-DD>.json` =
  `{"id", "refDate", "items": [...]}`; items JÁ ordenados por `scorePrioridade` desc;
  campos usados: `codigo, descricao, scorePrioridade, probabilidade, temPedido,
  curvaABC, unMes, rsHist, diasParado, coberturaEsgotada`.
- **Pricing:** `revisao_<AAAA>-S<ww>.html` em `pricing-atacaderj/dados/` (ex.:
  `revisao_2026-S29.html`); escolher o mais novo por (ano, int(semana)) — NÃO por
  ordenação lexicográfica (S9 > S10 daria errado).

---

### Task 1: Queries novas + dados demo

**Files:**
- Modify: `src/queries.py` (adicionar ao final, antes de nada que dependa delas — são independentes)
- Modify: `src/demo_data.py` (adicionar após `pedidos()`)
- Test: `tests/test_painel_queries.py` (novo)

**Interfaces:**
- Consumes: nada (folha).
- Produces: `queries.PROMO_RELAMPAGO` (sem placeholder), `queries.PEDIDOS_COBRANCA`
  e `queries.PEDIDOS_ABANDONADOS` (placeholder `{cobranca_max_dias}`);
  `demo_data.promo_relampago() -> list[dict]` com chaves
  `codigo, promo_inicio, promo_fim, preco_relampago`;
  `demo_data.pedidos_cobranca() -> list[dict]` com chaves
  `pedido, data_pedido, fornecedor, previsao_entrega, ddd, telefone, contato,
  itens_pendentes, valor_pendente`.

- [ ] **Step 1: Write the failing test**

Criar `tests/test_painel_queries.py`:

```python
# -*- coding: utf-8 -*-
"""Queries e dados demo do Painel de Compras: forma e placeholders."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import demo_data  # noqa: E402
import queries    # noqa: E402


def test_promo_relampago_e_select_puro_sem_placeholder():
    sql = queries.PROMO_RELAMPAGO
    assert sql.strip().upper().startswith("SELECT")
    assert "tbPromocaoRelampago" in sql
    assert "{" not in sql  # nao tem placeholder — formatar nao pode quebrar


def test_pedidos_cobranca_formata_janela():
    sql = queries.PEDIDOS_COBRANCA.format(cobranca_max_dias=60)
    assert "DATEADD(day, -60" in sql
    assert "cdPessoaComercial" in sql          # fornecedor vem do tbPedidoCompra
    assert "tbTelefone" in sql
    assert "inEntrada = 1" in sql and "dtAtendido IS NULL" in sql


def test_pedidos_abandonados_formata_janela():
    sql = queries.PEDIDOS_ABANDONADOS.format(cobranca_max_dias=60)
    assert "COUNT(*)" in sql and "-60" in sql


def test_demo_promo_relampago_tem_forma_da_query():
    linhas = demo_data.promo_relampago()
    assert len(linhas) >= 3
    for r in linhas:
        assert {"codigo", "promo_inicio", "promo_fim", "preco_relampago"} <= set(r)
    # exercita os 3 casos do cruzamento: com validade urgente (2411),
    # sem validade registrada (3905) e fora do catalogo (9999)
    cods = {str(r["codigo"]) for r in linhas}
    assert {"2411", "3905", "9999"} <= cods


def test_demo_pedidos_cobranca_tem_forma_da_query():
    linhas = demo_data.pedidos_cobranca()
    assert len(linhas) >= 3
    for r in linhas:
        assert {"pedido", "data_pedido", "fornecedor", "previsao_entrega",
                "ddd", "telefone", "contato", "itens_pendentes",
                "valor_pendente"} <= set(r)
    # um deles e recente e sem previsao vencida -> o filtro do quadrante
    # (Task 3) precisa DEIXA-LO DE FORA
    from datetime import date
    hoje = date.today()
    recentes = [r for r in linhas
                if (hoje - date.fromisoformat(r["data_pedido"])).days < 7]
    assert recentes, "demo precisa de 1 pedido recente para exercitar o filtro"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_painel_queries.py -q`
Expected: FAIL — `AttributeError: module 'queries' has no attribute 'PROMO_RELAMPAGO'`

- [ ] **Step 3: Write minimal implementation**

Em `src/queries.py`, adicionar ao FINAL do arquivo:

```python
# PROMO_RELAMPAGO: produtos com promocao relampago VIGENTE agora — quadrante
# validade x relampago do Painel de Compras.
# FONTE (schema confirmado 2026-07-20): dbo.tbPromocaoRelampago
# (cdProduto, dtInicio, dtFim, vlVenda). Medido: 371 linhas, 247 vigentes.
# tbPromocaoTipo.inRelampago existe, mas cdTipoPromocao vem NULL nas linhas
# vivas — o marcador REAL de "relampago" e estar NESTA tabela, vigente.
PROMO_RELAMPAGO = """
SELECT pr.cdProduto                              AS codigo,
       CAST(pr.dtInicio AS date)                 AS promo_inicio,
       CAST(pr.dtFim AS date)                    AS promo_fim,
       CAST(pr.vlVenda AS decimal(14,2))         AS preco_relampago
FROM dbo.tbPromocaoRelampago pr
WHERE GETDATE() BETWEEN pr.dtInicio AND pr.dtFim
ORDER BY pr.cdProduto
"""

# PEDIDOS_COBRANCA: pedidos de compra ABERTOS, por pedido x fornecedor —
# quadrante de cobranca do Painel de Compras.
# FATOS (2026-07-20): fornecedor NAO esta em tbPedido; vem de
# tbPedidoCompra.cdPessoaComercial -> tbPessoa. Telefone em tbTelefone
# (cdPessoa, DDD, Numero, Contato; cdTelefone=1 = principal). vlPedidoItem e
# POR VOLUME (convencao igual ao PEDIDOS_VENDA) -> valor pendente =
# (qtPedidoItem - qtAtendida) * vlPedidoItem.
# JANELA {cobranca_max_dias}: medido 534 abertos, 494 com 7+ dias — a loja NAO
# encerra pedido morto no ERP (ha pedidos de janeiro "abertos"). Sem a janela o
# quadrante nasceria inutil; os fora dela viram o contador de "abandonados".
PEDIDOS_COBRANCA = """
SELECT p.cdPedido                                AS pedido,
       CAST(p.dtPedido AS date)                  AS data_pedido,
       LTRIM(RTRIM(ps.nmPessoa))                 AS fornecedor,
       CAST(pc.dtEntregaPrevista AS date)        AS previsao_entrega,
       COALESCE(RTRIM(t.DDD), '')                AS ddd,
       COALESCE(RTRIM(t.Numero), '')             AS telefone,
       COALESCE(RTRIM(t.Contato), '')            AS contato,
       COUNT(*)                                  AS itens_pendentes,
       CAST(SUM((i.qtPedidoItem - COALESCE(i.qtAtendida, 0)) * i.vlPedidoItem)
            AS decimal(14,2))                    AS valor_pendente
FROM dbo.tbPedido p
JOIN dbo.tbPedidoCompra pc
  ON pc.cdPedidoCompra = p.cdPedido AND pc.cdPessoaFilial = p.cdPessoaFilial
JOIN dbo.tbPessoa ps       ON ps.cdPessoa = pc.cdPessoaComercial
LEFT JOIN dbo.tbTelefone t ON t.cdPessoa = pc.cdPessoaComercial AND t.cdTelefone = 1
JOIN dbo.tbPedidoItem i
  ON i.cdPedido = p.cdPedido AND i.cdPessoaFilial = p.cdPessoaFilial
WHERE p.inEntrada = 1
  AND p.dtAtendido IS NULL
  AND COALESCE(i.inAtendido, 0) = 0
  AND i.qtPedidoItem > 0
  AND p.dtPedido >= DATEADD(day, -{cobranca_max_dias}, CAST(GETDATE() AS date))
GROUP BY p.cdPedido, CAST(p.dtPedido AS date), ps.nmPessoa,
         CAST(pc.dtEntregaPrevista AS date), t.DDD, t.Numero, t.Contato
HAVING SUM((i.qtPedidoItem - COALESCE(i.qtAtendida, 0)) * i.qtEmbalagem) > 0
ORDER BY data_pedido
"""

# PEDIDOS_ABANDONADOS: quantos pedidos abertos ficaram FORA da janela de
# cobranca (lixo historico que ninguem encerrou). So um contador honesto no
# quadrante — nenhum corte silencioso.
PEDIDOS_ABANDONADOS = """
SELECT COUNT(*) AS n
FROM dbo.tbPedido p
WHERE p.inEntrada = 1
  AND p.dtAtendido IS NULL
  AND p.dtPedido < DATEADD(day, -{cobranca_max_dias}, CAST(GETDATE() AS date))
"""
```

Em `src/demo_data.py`, adicionar após a função `pedidos()`:

```python
def promo_relampago():
    """Relampagos vigentes (forma da query PROMO_RELAMPAGO). 2411 casa com a
    validade de 19 dias do validades() -> exercita o alerta; 3905 esta no
    catalogo mas SEM validade registrada; 9999 nao existe no catalogo."""
    hoje = date.today()
    return [
        {"codigo": "2411", "promo_inicio": (hoje - timedelta(days=2)).isoformat(),
         "promo_fim": (hoje + timedelta(days=5)).isoformat(), "preco_relampago": 15.90},
        {"codigo": "3905", "promo_inicio": hoje.isoformat(),
         "promo_fim": (hoje + timedelta(days=3)).isoformat(), "preco_relampago": 2.99},
        {"codigo": "9999", "promo_inicio": hoje.isoformat(),
         "promo_fim": (hoje + timedelta(days=1)).isoformat(), "preco_relampago": 2.00},
    ]


def pedidos_cobranca():
    """Pedidos de compra abertos (forma da query PEDIDOS_COBRANCA).
    101: 12 dias aberto + previsao vencida (entra). 102: 8 dias, sem previsao
    (entra pelo limiar). 103: 2 dias, previsao futura (о filtro deixa FORA)."""
    hoje = date.today()
    return [
        {"pedido": 101, "data_pedido": (hoje - timedelta(days=12)).isoformat(),
         "fornecedor": "DISTRIBUIDORA DEMO LTDA",
         "previsao_entrega": (hoje - timedelta(days=4)).isoformat(),
         "ddd": "21", "telefone": "33334444", "contato": "SR. DEMO",
         "itens_pendentes": 8, "valor_pendente": 4321.50},
        {"pedido": 102, "data_pedido": (hoje - timedelta(days=8)).isoformat(),
         "fornecedor": "ATACADO FAKE SA", "previsao_entrega": None,
         "ddd": "", "telefone": "", "contato": "",
         "itens_pendentes": 3, "valor_pendente": 980.00},
        {"pedido": 103, "data_pedido": (hoje - timedelta(days=2)).isoformat(),
         "fornecedor": "NOVO FORNECEDOR",
         "previsao_entrega": (hoje + timedelta(days=3)).isoformat(),
         "ddd": "21", "telefone": "00000000", "contato": "",
         "itens_pendentes": 5, "valor_pendente": 1500.00},
    ]
```

Atenção: no docstring de `pedidos_cobranca()` acima, garanta que o "o" de
"deixa FORA" é o caractere ASCII normal (digite a linha, não copie de PDF).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_painel_queries.py -q`
Expected: `5 passed`

- [ ] **Step 5: Rodar a suíte inteira (não quebrar nada existente)**

Run: `python -m pytest tests/ -q`
Expected: tudo verde (mesmo total de antes + 5).

- [ ] **Step 6: Commit**

```bash
git add src/queries.py src/demo_data.py tests/test_painel_queries.py
git commit -m "feat(painel): queries PROMO_RELAMPAGO/PEDIDOS_COBRANCA/ABANDONADOS + demo"
```

---

### Task 2: Cruzamento validade × relâmpago (função pura)

**Files:**
- Create: `src/painel_compras.py`
- Test: `tests/test_painel_validade.py` (novo)

**Interfaces:**
- Consumes: linhas nas formas de `queries.PROMO_RELAMPAGO`, `queries.VALIDADES`
  (`{"codigo", "validade"}`) e `queries.CATALOGO` (`{"codigo", "descricao", "curva", ...}`).
- Produces: `painel_compras.cruzar_validade_relampago(relampago, validades, catalogo, hoje)
  -> list[dict]` com chaves `codigo(str), descricao(str), curva(str|None),
  preco_relampago(float|None), promo_inicio(str), promo_fim(str),
  validades(list[str]), dias_ate_vencer(int|None)`; ordenada por urgência
  (menor `dias_ate_vencer` primeiro, `None` por último).
  Também `painel_compras._cod(c) -> str` (normalizador de código usado pelas
  Tasks 3–6).

- [ ] **Step 1: Write the failing test**

Criar `tests/test_painel_validade.py`:

```python
# -*- coding: utf-8 -*-
"""Cruzamento validade x relampago do Painel de Compras."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import painel_compras as pc  # noqa: E402

CATALOGO = [
    {"codigo": "2411", "descricao": "SUCRILHOS 240G", "curva": "A"},
    {"codigo": 3905, "descricao": "SAPOLIO 450ML", "curva": "C"},
]
VALIDADES = [
    {"codigo": "2411", "validade": "2026-08-08"},   # 19 dias a partir de 20/07
    {"codigo": "2411", "validade": "2026-10-01"},
]
RELAMPAGO = [
    {"codigo": "2411", "promo_inicio": "2026-07-18", "promo_fim": "2026-07-25",
     "preco_relampago": 15.9},
    {"codigo": 3905, "promo_inicio": "2026-07-20", "promo_fim": "2026-07-23",
     "preco_relampago": 2.99},
    {"codigo": "9999", "promo_inicio": "2026-07-20", "promo_fim": "2026-07-21",
     "preco_relampago": 2.0},
]


def test_cruza_validade_e_ordena_por_urgencia():
    itens = pc.cruzar_validade_relampago(RELAMPAGO, VALIDADES, CATALOGO, "2026-07-20")
    assert [i["codigo"] for i in itens] == ["2411", "3905", "9999"]
    i0 = itens[0]
    assert i0["descricao"] == "SUCRILHOS 240G" and i0["curva"] == "A"
    assert i0["validades"] == ["2026-08-08", "2026-10-01"]  # menor primeiro
    assert i0["dias_ate_vencer"] == 19


def test_sem_validade_e_fora_do_catalogo_nao_somem():
    itens = pc.cruzar_validade_relampago(RELAMPAGO, VALIDADES, CATALOGO, "2026-07-20")
    por_cod = {i["codigo"]: i for i in itens}
    assert por_cod["3905"]["dias_ate_vencer"] is None      # sem validade registrada
    assert por_cod["3905"]["validades"] == []
    assert por_cod["9999"]["descricao"] == "(fora do catalogo)"


def test_relampago_duplicado_fica_com_o_fim_mais_proximo():
    dupl = RELAMPAGO + [{"codigo": "2411", "promo_inicio": "2026-07-01",
                         "promo_fim": "2026-07-22", "preco_relampago": 14.0}]
    itens = pc.cruzar_validade_relampago(dupl, VALIDADES, CATALOGO, "2026-07-20")
    i0 = [i for i in itens if i["codigo"] == "2411"][0]
    assert i0["promo_fim"] == "2026-07-22" and i0["preco_relampago"] == 14.0


def test_validade_ja_vencida_da_dias_negativos():
    val = [{"codigo": "2411", "validade": "2026-07-15"}]
    itens = pc.cruzar_validade_relampago(RELAMPAGO[:1], val, CATALOGO, "2026-07-20")
    assert itens[0]["dias_ate_vencer"] == -5


def test_normalizador_de_codigo():
    assert pc._cod(18464) == "18464"
    assert pc._cod("18464.0") == "18464"
    assert pc._cod(" 2411 ") == "2411"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_painel_validade.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'painel_compras'`

- [ ] **Step 3: Write minimal implementation**

Criar `src/painel_compras.py`:

```python
# -*- coding: utf-8 -*-
"""Painel de Compras (TV + PC) — junta 4 fontes e gera painel/index.html.

Quadrantes: validade x promocao relampago (SQL), ruptura de estoque (rounds do
detector-estoque), cobranca de fornecedor (SQL) e preco concorrente (copia do
revisao_Sxx.html do pricing). Cada fonte falha SOZINHA: o quadrante afetado
mostra "indisponivel desde <data>" e a geracao nunca aborta.
Spec: docs/superpowers/specs/2026-07-20-painel-compras-design.md
"""
import glob
import json
import os
import re
import shutil
from datetime import date, datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PADROES = {
    "dir_saida": None,             # default: <repo>/saida/painel
    "porta_http": 8477,
    "cobranca_dias_limiar": 7,
    "cobranca_max_dias": 60,
    "validade_urgente_dias": 30,
    "rodizio_segundos": 20,
    "reload_minutos": 5,
    "pricing_dados_dir": None,
    "detector_rounds_dir": None,
    "detector_dashboard_url": "",
}


def _cod(c):
    """Codigo de produto como string canonica ('18464.0' -> '18464')."""
    s = str(c).strip()
    return s[:-2] if s.endswith(".0") else s


def _dias(de, ate):
    """Dias corridos entre datas ISO (str ou date); positivo se ate > de."""
    d1 = date.fromisoformat(str(de)[:10])
    d2 = date.fromisoformat(str(ate)[:10])
    return (d2 - d1).days


def cruzar_validade_relampago(relampago, validades, catalogo, hoje):
    """Uma linha por produto em relampago VIGENTE, com validades e urgencia.
    Produto sem validade registrada (~18% do catalogo) NAO some: sai com
    dias_ate_vencer=None para o comprador ver o buraco de cobertura."""
    cat = {_cod(r["codigo"]): r for r in catalogo or []}
    vals = {}
    for r in validades or []:
        if r.get("validade"):
            vals.setdefault(_cod(r["codigo"]), []).append(str(r["validade"])[:10])

    escolhido = {}   # codigo -> linha de relampago com promo_fim MAIS PROXIMO
    for r in relampago or []:
        c = _cod(r["codigo"])
        if c not in escolhido or str(r["promo_fim"]) < str(escolhido[c]["promo_fim"]):
            escolhido[c] = r

    itens = []
    for c, r in escolhido.items():
        vs = sorted(vals.get(c, []))
        info = cat.get(c)
        itens.append({
            "codigo": c,
            "descricao": (info or {}).get("descricao") or "(fora do catalogo)",
            "curva": (info or {}).get("curva"),
            "preco_relampago": r.get("preco_relampago"),
            "promo_inicio": str(r.get("promo_inicio"))[:10],
            "promo_fim": str(r.get("promo_fim"))[:10],
            "validades": vs,
            "dias_ate_vencer": _dias(hoje, vs[0]) if vs else None,
        })
    itens.sort(key=lambda i: (i["dias_ate_vencer"] is None,
                              i["dias_ate_vencer"], i["codigo"]))
    return itens
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_painel_validade.py -q`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/painel_compras.py tests/test_painel_validade.py
git commit -m "feat(painel): cruzamento validade x relampago (funcao pura)"
```

---

### Task 3: Cobrança de fornecedor (função pura)

**Files:**
- Modify: `src/painel_compras.py` (adicionar após `cruzar_validade_relampago`)
- Test: `tests/test_painel_cobranca.py` (novo)

**Interfaces:**
- Consumes: linhas na forma de `queries.PEDIDOS_COBRANCA` (Task 1) e `_dias` (Task 2).
- Produces: `painel_compras.montar_cobranca(pedidos, hoje, limiar_dias=7) -> list[dict]`
  com chaves `pedido, fornecedor, data_pedido(str), dias_aberto(int),
  previsao_entrega(str|None), atraso_previsao(int, 0 se sem atraso),
  itens_pendentes(int), valor_pendente(float), telefone(str, "" se inutil),
  contato(str)`; ordenada por `dias_aberto` desc.

- [ ] **Step 1: Write the failing test**

Criar `tests/test_painel_cobranca.py`:

```python
# -*- coding: utf-8 -*-
"""Regras do quadrante de cobranca de fornecedor."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import painel_compras as pc  # noqa: E402

HOJE = "2026-07-20"


def _p(**kw):
    base = {"pedido": 1, "data_pedido": "2026-07-01", "fornecedor": "F",
            "previsao_entrega": None, "ddd": "", "telefone": "", "contato": "",
            "itens_pendentes": 1, "valor_pendente": 100.0}
    base.update(kw)
    return base


def test_entra_por_limiar_de_dias():
    itens = pc.montar_cobranca([_p(pedido=1, data_pedido="2026-07-12")], HOJE, 7)
    assert len(itens) == 1 and itens[0]["dias_aberto"] == 8


def test_recente_sem_previsao_vencida_fica_fora():
    itens = pc.montar_cobranca(
        [_p(pedido=2, data_pedido="2026-07-18", previsao_entrega="2026-07-25")],
        HOJE, 7)
    assert itens == []


def test_recente_mas_previsao_vencida_entra():
    itens = pc.montar_cobranca(
        [_p(pedido=3, data_pedido="2026-07-17", previsao_entrega="2026-07-19")],
        HOJE, 7)
    assert len(itens) == 1
    assert itens[0]["dias_aberto"] == 3 and itens[0]["atraso_previsao"] == 1


def test_ordena_pior_primeiro_e_formata_telefone():
    itens = pc.montar_cobranca([
        _p(pedido=1, data_pedido="2026-07-10", ddd="21", telefone="33334444",
           contato="ANA"),
        _p(pedido=2, data_pedido="2026-07-01", ddd="00", telefone="00000000"),
    ], HOJE, 7)
    assert [i["pedido"] for i in itens] == [2, 1]
    assert itens[1]["telefone"] == "(21) 33334444" and itens[1]["contato"] == "ANA"
    assert itens[0]["telefone"] == ""   # 00/00000000 = lixo, nao mostrar
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_painel_cobranca.py -q`
Expected: FAIL — `AttributeError: ... no attribute 'montar_cobranca'`

- [ ] **Step 3: Write minimal implementation**

Adicionar em `src/painel_compras.py`:

```python
def montar_cobranca(pedidos, hoje, limiar_dias=7):
    """Pedidos que merecem cobranca: abertos ha >= limiar OU previsao vencida.
    A query ja cortou na janela maxima (cobranca_max_dias); os mais velhos que
    ela viram so o contador de 'abandonados' (fora daqui)."""
    itens = []
    for r in pedidos or []:
        dias = _dias(r["data_pedido"], hoje)
        prev = str(r["previsao_entrega"])[:10] if r.get("previsao_entrega") else None
        atraso = _dias(prev, hoje) if prev else 0
        atraso = atraso if atraso > 0 else 0
        if dias < limiar_dias and atraso == 0:
            continue
        num = (r.get("telefone") or "").strip()
        ddd = (r.get("ddd") or "").strip()
        tel = f"({ddd}) {num}" if num and set(num) != {"0"} else ""
        itens.append({
            "pedido": r["pedido"],
            "fornecedor": r["fornecedor"],
            "data_pedido": str(r["data_pedido"])[:10],
            "dias_aberto": dias,
            "previsao_entrega": prev,
            "atraso_previsao": atraso,
            "itens_pendentes": int(r.get("itens_pendentes") or 0),
            "valor_pendente": float(r.get("valor_pendente") or 0),
            "telefone": tel,
            "contato": (r.get("contato") or "").strip(),
        })
    itens.sort(key=lambda i: (-i["dias_aberto"], -i["valor_pendente"]))
    return itens
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_painel_cobranca.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add src/painel_compras.py tests/test_painel_cobranca.py
git commit -m "feat(painel): regras do quadrante de cobranca de fornecedor"
```

---

### Task 4: Leitor da rodada do detector-estoque

**Files:**
- Modify: `src/painel_compras.py`
- Test: `tests/test_painel_ruptura.py` (novo)

**Interfaces:**
- Consumes: arquivos `<rounds_dir>/<YYYY-MM-DD>.json` no formato
  `{"id", "refDate", "items": [...]}` (Fatos do schema).
- Produces: `painel_compras.carregar_ruptura(rounds_dir) -> dict|None` —
  `None` se dir vazio/inexistente/None; senão
  `{"ref": str, "itens": [{"codigo", "descricao", "prioridade", "probabilidade",
  "tem_pedido", "curva", "un_mes", "rs_hist", "dias_parado",
  "cobertura_esgotada"}]}` na ordem original (já priorizada). JSON malformado
  LEVANTA exceção (o chamador trata por quadrante).

- [ ] **Step 1: Write the failing test**

Criar `tests/test_painel_ruptura.py`:

```python
# -*- coding: utf-8 -*-
"""Leitor da rodada mais recente do detector-ruptura-estoque."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import painel_compras as pc  # noqa: E402

ITEM = {"codigo": "3905", "descricao": "SAPOLIO 450ML", "scorePrioridade": 0.9,
        "probabilidade": 0.82, "temPedido": False, "curvaABC": "C",
        "unMes": 120.0, "rsHist": 3500.0, "diasParado": 6,
        "coberturaEsgotada": True}


def _grava(dirp, nome, obj):
    with open(os.path.join(dirp, nome), "w", encoding="utf-8") as f:
        json.dump(obj, f)


def test_pega_a_rodada_mais_recente_e_traduz_campos(tmp_path):
    _grava(tmp_path, "2026-07-17.json", {"id": "2026-07-17", "refDate": "2026-07-17",
                                         "items": []})
    _grava(tmp_path, "2026-07-19.json", {"id": "2026-07-19", "refDate": "2026-07-19",
                                         "items": [ITEM]})
    r = pc.carregar_ruptura(str(tmp_path))
    assert r["ref"] == "2026-07-19" and len(r["itens"]) == 1
    i = r["itens"][0]
    assert i["codigo"] == "3905" and i["prioridade"] == 0.9
    assert i["tem_pedido"] is False and i["curva"] == "C"
    assert i["cobertura_esgotada"] is True and i["dias_parado"] == 6


def test_sem_diretorio_ou_vazio_devolve_none(tmp_path):
    assert pc.carregar_ruptura(None) is None
    assert pc.carregar_ruptura(str(tmp_path / "nao-existe")) is None
    assert pc.carregar_ruptura(str(tmp_path)) is None      # dir existe, sem .json


def test_json_malformado_levanta(tmp_path):
    (tmp_path / "2026-07-19.json").write_text("{quebrado", encoding="utf-8")
    with pytest.raises(Exception):
        pc.carregar_ruptura(str(tmp_path))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_painel_ruptura.py -q`
Expected: FAIL — `AttributeError: ... no attribute 'carregar_ruptura'`

- [ ] **Step 3: Write minimal implementation**

Adicionar em `src/painel_compras.py`:

```python
def carregar_ruptura(rounds_dir):
    """Rodada mais recente do detector-estoque, traduzida para o painel.
    Items ja vem ordenados por scorePrioridade desc (detectAll.js)."""
    if not rounds_dir or not os.path.isdir(rounds_dir):
        return None
    arquivos = sorted(glob.glob(os.path.join(rounds_dir, "*.json")))
    if not arquivos:
        return None
    with open(arquivos[-1], encoding="utf-8") as f:
        rodada = json.load(f)
    itens = [{
        "codigo": _cod(i.get("codigo")),
        "descricao": i.get("descricao"),
        "prioridade": i.get("scorePrioridade"),
        "probabilidade": i.get("probabilidade"),
        "tem_pedido": bool(i.get("temPedido")),
        "curva": i.get("curvaABC"),
        "un_mes": i.get("unMes"),
        "rs_hist": i.get("rsHist"),
        "dias_parado": i.get("diasParado"),
        "cobertura_esgotada": bool(i.get("coberturaEsgotada")),
    } for i in rodada.get("items", [])]
    return {"ref": rodada.get("refDate") or rodada.get("id"), "itens": itens}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_painel_ruptura.py -q`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add src/painel_compras.py tests/test_painel_ruptura.py
git commit -m "feat(painel): leitor da rodada do detector-estoque"
```

---

### Task 5: Cópia do revisao_Sxx.html do pricing

**Files:**
- Modify: `src/painel_compras.py`
- Test: `tests/test_painel_concorrente.py` (novo)

**Interfaces:**
- Consumes: arquivos `revisao_<AAAA>-S<ww>.html` em `pricing_dados_dir`.
- Produces: `painel_compras.copiar_revisao_pricing(dados_dir, dir_saida) -> dict|None` —
  `None` se dir/arquivo inexistente; senão copia o MAIS NOVO por (ano, int(semana))
  para `<dir_saida>/revisao_pricing.html` e devolve
  `{"rotulo": "2026-S29", "arquivo": "revisao_pricing.html",
  "modificado_em": "YYYY-MM-DD HH:MM"}` (mtime do original).

- [ ] **Step 1: Write the failing test**

Criar `tests/test_painel_concorrente.py`:

```python
# -*- coding: utf-8 -*-
"""Escolha e copia do revisao_Sxx.html mais recente do pricing."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import painel_compras as pc  # noqa: E402


def test_escolhe_por_ano_e_semana_numerica_nao_lexicografica(tmp_path):
    origem = tmp_path / "dados"; destino = tmp_path / "painel"
    origem.mkdir(); destino.mkdir()
    (origem / "revisao_2026-S9.html").write_text("velho", encoding="utf-8")
    (origem / "revisao_2026-S10.html").write_text("novo", encoding="utf-8")
    r = pc.copiar_revisao_pricing(str(origem), str(destino))
    assert r["rotulo"] == "2026-S10"          # S10 > S9 (lexicografico daria S9)
    assert r["arquivo"] == "revisao_pricing.html"
    copiado = destino / "revisao_pricing.html"
    assert copiado.read_text(encoding="utf-8") == "novo"
    assert r["modificado_em"]


def test_sem_dir_ou_sem_arquivo_devolve_none(tmp_path):
    assert pc.copiar_revisao_pricing(None, str(tmp_path)) is None
    assert pc.copiar_revisao_pricing(str(tmp_path / "x"), str(tmp_path)) is None
    vazio = tmp_path / "dados"; vazio.mkdir()
    assert pc.copiar_revisao_pricing(str(vazio), str(tmp_path)) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_painel_concorrente.py -q`
Expected: FAIL — `AttributeError: ... no attribute 'copiar_revisao_pricing'`

- [ ] **Step 3: Write minimal implementation**

Adicionar em `src/painel_compras.py`:

```python
def copiar_revisao_pricing(dados_dir, dir_saida):
    """Copia o revisao_<AAAA>-S<ww>.html MAIS NOVO do pricing para a pasta do
    painel (nome fixo revisao_pricing.html -> link estavel no HTML).
    Ordena por (ano, int(semana)): lexicografico faria S9 > S10."""
    if not dados_dir or not os.path.isdir(dados_dir):
        return None
    padrao = re.compile(r"revisao_(\d{4})-S(\d+)\.html$")
    candidatos = []
    for arq in glob.glob(os.path.join(dados_dir, "revisao_*.html")):
        m = padrao.search(os.path.basename(arq))
        if m:
            candidatos.append((int(m.group(1)), int(m.group(2)), arq))
    if not candidatos:
        return None
    ano, sem, origem = max(candidatos)
    os.makedirs(dir_saida, exist_ok=True)
    shutil.copyfile(origem, os.path.join(dir_saida, "revisao_pricing.html"))
    mtime = datetime.fromtimestamp(os.path.getmtime(origem))
    return {"rotulo": f"{ano}-S{sem}", "arquivo": "revisao_pricing.html",
            "modificado_em": mtime.strftime("%Y-%m-%d %H:%M")}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_painel_concorrente.py -q`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add src/painel_compras.py tests/test_painel_concorrente.py
git commit -m "feat(painel): copia do revisao_Sxx.html mais recente do pricing"
```

---

### Task 6: Template HTML (TV + PC) e renderização

**Files:**
- Create: `src/templates/painel_compras.html`
- Modify: `src/painel_compras.py` (função `renderizar`)
- Test: `tests/test_painel_render.py` (novo)

**Interfaces:**
- Consumes: payload montado na Task 7 (estrutura abaixo — o template só lê `D`).
- Produces: `painel_compras.renderizar(payload) -> str` (HTML completo);
  template com placeholder `/*__DADOS__*/null` e escape `</` → `<\/`
  (mesmo padrão de `vendas_mensal_dashboard`).

Estrutura do payload (contrato entre Tasks 6 e 7):

```json
{
  "origem": "erp-bridge-painel", "gerado_em": "2026-07-20 06:00:00",
  "cfg": {"rodizio_segundos": 20, "reload_minutos": 5,
           "validade_urgente_dias": 30, "cobranca_dias_limiar": 7,
           "detector_dashboard_url": ""},
  "validade_relampago": {"carimbo": "...", "erro": null, "itens": []},
  "ruptura":            {"carimbo": "...", "erro": null, "itens": []},
  "cobranca":           {"carimbo": "...", "erro": null, "itens": [], "abandonados": 0},
  "concorrente":        {"carimbo": "...", "erro": null, "rotulo": null, "arquivo": null}
}
```

- [ ] **Step 1: Write the failing test**

Criar `tests/test_painel_render.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_painel_render.py -q`
Expected: FAIL — `AttributeError: ... no attribute 'renderizar'`

- [ ] **Step 3: Escrever o template**

Criar `src/templates/painel_compras.html` com exatamente este conteúdo:

```html
<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Painel de Compras — AtacadeRJ</title>
<style>
  :root { --bg:#0e1116; --card:#161b22; --borda:#21262d; --txt:#e6edf3;
          --mut:#8b949e; --ok:#3fb950; --warn:#d29922; --bad:#f85149; --acc:#58a6ff }
  * { box-sizing:border-box; margin:0 }
  body { background:var(--bg); color:var(--txt); padding:1rem;
         font:16px/1.45 "Segoe UI", system-ui, sans-serif }
  h1 { font-size:1.35rem; margin-bottom:.8rem }
  h1 small { color:var(--mut); font-weight:400; font-size:.85rem; margin-left:.6rem }
  .grade { display:grid; grid-template-columns:1fr 1fr; gap:1rem }
  .quadro { background:var(--card); border:1px solid var(--borda); border-radius:12px;
            padding:1rem; cursor:pointer; min-height:15rem }
  .quadro h2 { font-size:1.1rem; margin-bottom:.4rem }
  .carimbo { color:var(--mut); font-size:.75rem; float:right; margin-top:.2rem }
  .erro { background:#3d1d1f; color:var(--bad); padding:.4rem .6rem;
          border-radius:8px; margin:.4rem 0; font-size:.9rem }
  .kpis { display:flex; gap:.7rem; margin:.5rem 0 .7rem; flex-wrap:wrap }
  .kpi { background:#0d1117; border-radius:10px; padding:.4rem .8rem; text-align:center }
  .kpi b { display:block; font-size:1.6rem }
  .kpi span { color:var(--mut); font-size:.75rem }
  .kpi.warn b { color:var(--warn) } .kpi.bad b { color:var(--bad) } .kpi.ok b { color:var(--ok) }
  table { width:100%; border-collapse:collapse; font-size:.9rem }
  th { text-align:left; color:var(--mut); font-weight:600; padding:.25rem .5rem;
       border-bottom:1px solid var(--borda); position:sticky; top:0; background:var(--card) }
  td { padding:.28rem .5rem; border-bottom:1px solid #1c2128; white-space:nowrap }
  td.desc { white-space:normal }
  .num { text-align:right; font-variant-numeric:tabular-nums }
  .tag { border-radius:6px; padding:.05rem .45rem; font-size:.78rem }
  .tag.bad { background:#3d1d1f; color:var(--bad) }
  .tag.warn { background:#3a2d12; color:var(--warn) }
  .tag.ok { background:#12351c; color:var(--ok) }
  .tag.mut { background:var(--borda); color:var(--mut) }
  a { color:var(--acc) }
  #detalhe { position:fixed; inset:0; background:var(--bg); padding:1rem;
             display:none; overflow:auto; z-index:9 }
  #detalhe.aberto { display:block }
  #detalhe .topo { display:flex; gap:.8rem; align-items:center; margin-bottom:.8rem }
  #detalhe h2 { flex-shrink:0 }
  #detalhe input { background:#0d1117; color:var(--txt); border:1px solid #30363d;
                   border-radius:8px; padding:.45rem .7rem; font-size:1rem; flex:1 }
  button { background:var(--borda); color:var(--txt); border:1px solid #30363d;
           border-radius:8px; padding:.45rem 1rem; font-size:1rem; cursor:pointer }
  body.tv { font-size:21px; cursor:none }
  body.tv .quadro { cursor:default }
  body.tv .kpi b { font-size:2.4rem }
  body.tv #detalhe .topo input, body.tv #detalhe .topo button { display:none }
  @media (max-width:900px){ .grade { grid-template-columns:1fr } }
</style>
</head>
<body>
<h1>🛒 Painel de Compras <small id="cab"></small></h1>
<div class="grade" id="grade"></div>
<div id="detalhe"></div>
<script>
const D = /*__DADOS__*/null;
const TV = location.hash.toLowerCase() === "#tv";
if (TV) document.body.classList.add("tv");
const C = D.cfg;
const nf = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const rs = (v) => v == null ? "—" : "R$ " + nf.format(v);
const esc = (s) => String(s == null ? "" : s)
  .replace(/[&<>"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
document.getElementById("cab").textContent =
  "gerado em " + D.gerado_em + (TV ? " · modo TV" : "");

function diasTag(d) {
  if (d == null) return '<span class="tag mut">sem validade registrada</span>';
  const cls = d < 0 ? "bad" : (d <= C.validade_urgente_dias ? "warn" : "ok");
  const txt = d < 0 ? ("vencida ha " + (-d) + "d") : ("vence em " + d + "d");
  return '<span class="tag ' + cls + '">' + txt + "</span>";
}

/* ---- definicao dos quadrantes: kpis(), cab[], linha(item), dados ---- */
const Q = {
  validade_relampago: {
    titulo: "⚡ Validade × Relâmpago", d: D.validade_relampago,
    kpis() {
      const it = this.d.itens, urg = it.filter(
        (i) => i.dias_ate_vencer != null && i.dias_ate_vencer <= C.validade_urgente_dias);
      const sem = it.filter((i) => i.dias_ate_vencer == null);
      return [["", it.length, "em relâmpago"],
              [urg.length ? "warn" : "ok", urg.length, "vencendo ≤" + C.validade_urgente_dias + "d"],
              [sem.length ? "warn" : "ok", sem.length, "sem validade"]];
    },
    cab: ["Código", "Produto", "Curva", "Preço ⚡", "Fim promo", "Validades", "Urgência"],
    linha: (i) => [esc(i.codigo), '<td class="desc">' + esc(i.descricao) + "</td>",
                   esc(i.curva || "—"), '<td class="num">' + rs(i.preco_relampago) + "</td>",
                   esc(i.promo_fim), esc(i.validades.join(", ") || "—"), diasTag(i.dias_ate_vencer)],
  },
  ruptura: {
    titulo: "📉 Ruptura de estoque", d: D.ruptura,
    kpis() {
      const it = this.d.itens, sem = it.filter((i) => !i.tem_pedido);
      return [["", it.length, "prováveis rupturas"],
              [sem.length ? "bad" : "ok", sem.length, "sem pedido"]];
    },
    cab: ["Código", "Produto", "Prob.", "Un/mês", "R$ hist.", "Parado", "Curva", "Pedido"],
    linha: (i) => [esc(i.codigo), '<td class="desc">' + esc(i.descricao) + "</td>",
                   '<td class="num">' + (i.probabilidade == null ? "—" :
                     Math.round(i.probabilidade * 100) + "%") + "</td>",
                   '<td class="num">' + nf.format(i.un_mes || 0) + "</td>",
                   '<td class="num">' + rs(i.rs_hist) + "</td>",
                   '<td class="num">' + (i.dias_parado ?? "—") + "d</td>",
                   esc(i.curva || "—"),
                   i.tem_pedido ? '<span class="tag ok">✅ lançado</span>'
                                : '<span class="tag bad">🛒 sem pedido</span>'],
    rodape: () => D.cfg.detector_dashboard_url && !TV
      ? '<p style="margin-top:.6rem"><a href="' + esc(D.cfg.detector_dashboard_url) +
        '">abrir o dashboard do detector (feedback 🔴/🟢)</a></p>' : "",
  },
  cobranca: {
    titulo: "📞 Cobrança de fornecedor", d: D.cobranca,
    kpis() {
      const it = this.d.itens;
      const total = it.reduce((s, i) => s + (i.valor_pendente || 0), 0);
      return [[it.length ? "warn" : "ok", it.length, "pedidos p/ cobrar"],
              ["", rs(total), "pendente"],
              [this.d.abandonados ? "bad" : "ok", this.d.abandonados || 0,
               "abandonados (fora da janela)"]];
    },
    cab: ["Fornecedor", "Pedido", "Data", "Dias", "Previsão", "Atraso", "Itens", "R$ pendente", "Telefone"],
    linha: (i) => ['<td class="desc">' + esc(i.fornecedor) + "</td>", esc(i.pedido),
                   esc(i.data_pedido),
                   '<td class="num"><span class="tag ' +
                     (i.dias_aberto >= 2 * C.cobranca_dias_limiar ? "bad" : "warn") +
                     '">' + i.dias_aberto + "d</span></td>",
                   esc(i.previsao_entrega || "—"),
                   '<td class="num">' + (i.atraso_previsao ? i.atraso_previsao + "d" : "—") + "</td>",
                   '<td class="num">' + i.itens_pendentes + "</td>",
                   '<td class="num">' + rs(i.valor_pendente) + "</td>",
                   esc(i.telefone ? i.telefone + (i.contato ? " (" + i.contato + ")" : "") : "—")],
  },
  concorrente: {
    titulo: "🏷️ Preço concorrente", d: D.concorrente,
    kpis() {
      return [["", this.d.rotulo || "—", "semana da revisão"]];
    },
    cab: [], linha: null,   // sem tabela: quadrante e so card + link
    corpo() {
      if (!this.d.arquivo) return '<p style="color:var(--mut)">Sem revisão do pricing disponível.</p>';
      return TV ? '<p style="color:var(--mut)">Revisão ' + esc(this.d.rotulo) +
                  " disponível — abra no PC para o detalhe.</p>"
                : '<p><a href="' + esc(this.d.arquivo) +
                  '" target="_blank">abrir a revisão de preços ' + esc(this.d.rotulo) + "</a></p>";
    },
  },
};

/* ---- visao geral (grade 2x2, top-8 por quadrante) ---- */
function tabela(q, itens) {
  if (!q.cab.length) return q.corpo ? q.corpo() : "";
  const linhas = itens.map((i) => "<tr>" + q.linha(i).map(
    (c) => c.startsWith("<td") || c.startsWith("<span") && false ? c :
           (c.startsWith("<td") ? c : "<td>" + c + "</td>")).join("") + "</tr>");
  return '<div style="overflow:auto"><table><tr>' +
    q.cab.map((h) => "<th>" + h + "</th>").join("") + "</tr>" +
    linhas.join("") + "</table></div>";
}
function cartao(id) {
  const q = Q[id], d = q.d;
  let h = '<h2>' + q.titulo + '<span class="carimbo">' + esc(d.carimbo || "—") + "</span></h2>";
  if (d.erro) h += '<div class="erro">indisponível: ' + esc(d.erro) + "</div>";
  h += '<div class="kpis">' + q.kpis().map(
    ([cls, v, rot]) => '<div class="kpi ' + cls + '"><b>' + v + "</b><span>" +
                       rot + "</span></div>").join("") + "</div>";
  h += q.cab.length ? tabela(q, d.itens.slice(0, 8)) : (q.corpo ? q.corpo() : "");
  h += (q.rodape && q.rodape()) || "";
  return h;
}
function pintarGrade() {
  const g = document.getElementById("grade");
  g.innerHTML = "";
  for (const id of Object.keys(Q)) {
    const el = document.createElement("div");
    el.className = "quadro"; el.dataset.id = id; el.innerHTML = cartao(id);
    el.addEventListener("click", () => {
      if (TV) return;
      if (id === "concorrente") { if (Q.concorrente.d.arquivo) window.open(Q.concorrente.d.arquivo); return; }
      abrirDetalhe(id);
    });
    g.appendChild(el);
  }
}

/* ---- detalhe (tabela completa + filtro; na TV entra no rodizio) ---- */
function abrirDetalhe(id, filtro) {
  const q = Q[id], det = document.getElementById("detalhe");
  const itens = filtro
    ? q.d.itens.filter((i) => JSON.stringify(i).toLowerCase().includes(filtro))
    : q.d.itens;
  det.innerHTML = '<div class="topo"><h2>' + q.titulo +
    '<span class="carimbo">' + esc(q.d.carimbo || "—") + "</span></h2>" +
    '<input id="filtro" placeholder="filtrar… (código, produto, fornecedor)">' +
    '<button id="voltar">← voltar (Esc)</button></div>' +
    (q.d.erro ? '<div class="erro">indisponível: ' + esc(q.d.erro) + "</div>" : "") +
    tabela(q, itens);
  det.classList.add("aberto");
  const inp = document.getElementById("filtro");
  if (inp) { inp.value = filtro || ""; if (!TV) inp.focus();
    inp.addEventListener("input", () => abrirDetalhe(id, inp.value.trim().toLowerCase())); }
  const btn = document.getElementById("voltar");
  if (btn) btn.addEventListener("click", fecharDetalhe);
}
function fecharDetalhe() { document.getElementById("detalhe").classList.remove("aberto"); }
document.addEventListener("keydown", (e) => { if (e.key === "Escape") fecharDetalhe(); });

/* ---- modo TV: rodizio automatico + recarga periodica ---- */
pintarGrade();
if (TV) {
  const ordem = [null, "validade_relampago", null, "ruptura", null, "cobranca"];
  let i = 0;
  setInterval(() => {
    i = (i + 1) % ordem.length;
    if (ordem[i] === null) fecharDetalhe(); else abrirDetalhe(ordem[i]);
  }, (C.rodizio_segundos || 20) * 1000);
  setTimeout(() => location.reload(), (C.reload_minutos || 5) * 60000);
}
</script>
</body>
</html>
```

- [ ] **Step 4: Corrigir a função `tabela` (bug proposital do rascunho acima)**

A expressão da `tabela()` acima tem um ternário confuso. Substituir a função
inteira por esta versão simples (célula que já começa com `<td` entra crua;
o resto ganha `<td>`):

```js
function tabela(q, itens) {
  if (!q.cab.length) return q.corpo ? q.corpo() : "";
  const linhas = itens.map((i) => "<tr>" + q.linha(i).map(
    (c) => String(c).startsWith("<td") ? c : "<td>" + c + "</td>").join("") + "</tr>");
  return '<div style="overflow:auto"><table><tr>' +
    q.cab.map((h) => "<th>" + h + "</th>").join("") + "</tr>" +
    linhas.join("") + "</table></div>";
}
```

- [ ] **Step 5: Implementar `renderizar`**

Adicionar em `src/painel_compras.py`:

```python
def renderizar(payload):
    """Embute o payload no template (mesmo padrao do vendas_mensal_dashboard:
    placeholder /*__DADOS__*/null e escape de '</' para nao fechar o <script>)."""
    template = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "templates", "painel_compras.html")
    with open(template, encoding="utf-8") as f:
        html = f.read()
    dados = json.dumps(payload, ensure_ascii=False, indent=1, default=str)
    return html.replace("/*__DADOS__*/null", dados.replace("</", "<\\/"))
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_painel_render.py -q`
Expected: `3 passed`

- [ ] **Step 7: Rodar a suíte de render de novo (após o fix do Step 4)**

Run: `python -m pytest tests/test_painel_render.py -q`
Expected: `3 passed`. A conferência VISUAL (grade 2×2, detalhe, filtro, `#tv`)
fica para o Step 7 da Task 7, que gera `saida/painel/index.html` com dados
demo — não há como olhar o template sem um payload real. Não commitar `saida/`.

- [ ] **Step 8: Commit**

```bash
git add src/templates/painel_compras.html src/painel_compras.py tests/test_painel_render.py
git commit -m "feat(painel): template TV+PC (grade 2x2, rodizio, detalhe com filtro)"
```

---

### Task 7: Orquestração `rodar()` + integração no bridge + config

**Files:**
- Modify: `src/painel_compras.py` (funções `_consulta` e `rodar`)
- Modify: `src/bridge.py` (choices do `--only` + chamada)
- Modify: `config.example.json` (seção `painel`)
- Test: `tests/test_painel_rodar.py` (novo)

**Interfaces:**
- Consumes: TUDO das Tasks 1–6 (queries, demo, cruzar/montar/carregar/copiar/renderizar).
- Produces: `painel_compras.rodar(cfg, usar_demo=False) -> list[str]` (linhas de
  relatório para o `[OK]` do bridge); escreve `<dir_saida>/index.html` e
  `<dir_saida>/dados_painel.json`. `python src/bridge.py --demo` e
  `--only painel` passam a gerar o painel.

- [ ] **Step 1: Write the failing test**

Criar `tests/test_painel_rodar.py`:

```python
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


def test_demo_gera_index_e_json(tmp_path):
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


def test_fontes_ausentes_nao_derrubam_a_geracao(tmp_path):
    cfg = _cfg(tmp_path,
               detector_rounds_dir=str(tmp_path / "nao-existe"),
               pricing_dados_dir=str(tmp_path / "tambem-nao"))
    pc.rodar(cfg, usar_demo=True)
    dados = json.loads((tmp_path / "painel" / "dados_painel.json").read_text(
        encoding="utf-8"))
    assert dados["ruptura"]["erro"]        # avisa, nao quebra
    assert dados["concorrente"]["erro"]


def test_ruptura_e_concorrente_entram_quando_existem(tmp_path):
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_painel_rodar.py -q`
Expected: FAIL — `AttributeError: ... no attribute 'rodar'`

- [ ] **Step 3: Implementar `_consulta` e `rodar`**

Adicionar em `src/painel_compras.py` (no topo, junto aos imports existentes,
NADA de import de `db`/`queries` no nível do módulo — só dentro de `rodar`,
para o `--demo` funcionar sem pyodbc):

```python
def _consulta(conn, sql, quadrante, erros):
    """SELECT com falha isolada: registra o 1o erro do quadrante e devolve None."""
    import db
    try:
        return db.consultar(conn, sql)
    except Exception as e:  # noqa: BLE001 — qualquer falha vira aviso no quadrante
        erros.setdefault(quadrante, str(e))
        return None


def rodar(cfg, usar_demo=False):
    """Gera <dir_saida>/index.html + dados_painel.json a partir das 4 fontes.
    Devolve as linhas de relatorio para o [OK] do bridge."""
    import demo_data
    import projections
    cfgp = dict(PADROES)
    cfgp.update(cfg.get("painel") or {})
    destino = cfgp.get("dir_saida") or os.path.join(RAIZ, "saida", "painel")
    os.makedirs(destino, exist_ok=True)
    gerado_em = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hoje = date.today().isoformat()

    # --- fontes SQL (cada quadrante falha sozinho) ---
    erros = {}
    cat = val = relamp = cob = None
    aband = 0
    if usar_demo:
        cat, val = demo_data.catalogo(), demo_data.validades()
        relamp, cob = demo_data.promo_relampago(), demo_data.pedidos_cobranca()
        aband = 2
    else:
        import db
        import queries
        try:
            conn = db.conectar(cfg["db"])
        except Exception as e:  # noqa: BLE001
            erros["validade_relampago"] = erros["cobranca"] = f"banco inacessivel: {e}"
        else:
            try:
                jan = int(cfg.get("janela_entradas_dias", 180))
                max_d = int(cfgp["cobranca_max_dias"])
                cat = _consulta(conn, queries.CATALOGO, "validade_relampago", erros)
                val = _consulta(conn, queries.VALIDADES.format(janela_entradas=jan),
                                "validade_relampago", erros) or []
                relamp = _consulta(conn, queries.PROMO_RELAMPAGO,
                                   "validade_relampago", erros)
                cob = _consulta(conn, queries.PEDIDOS_COBRANCA.format(
                    cobranca_max_dias=max_d), "cobranca", erros)
                ab = _consulta(conn, queries.PEDIDOS_ABANDONADOS.format(
                    cobranca_max_dias=max_d), "cobranca", erros)
                aband = int(ab[0]["n"]) if ab else 0
            finally:
                conn.close()

    q_validade = {"carimbo": gerado_em, "erro": erros.get("validade_relampago"),
                  "itens": []}
    if relamp is not None and cat is not None:
        q_validade["itens"] = cruzar_validade_relampago(relamp, val, cat, hoje)

    q_cobranca = {"carimbo": gerado_em, "erro": erros.get("cobranca"),
                  "itens": [], "abandonados": aband}
    if cob is not None:
        q_cobranca["itens"] = montar_cobranca(
            cob, hoje, int(cfgp["cobranca_dias_limiar"]))

    q_ruptura = {"carimbo": None, "erro": None, "itens": []}
    try:
        r = carregar_ruptura(cfgp.get("detector_rounds_dir"))
        if r is None:
            q_ruptura["erro"] = "nenhuma rodada do detector encontrada"
        else:
            q_ruptura["carimbo"], q_ruptura["itens"] = r["ref"], r["itens"]
    except Exception as e:  # noqa: BLE001
        q_ruptura["erro"] = f"falha lendo a rodada do detector: {e}"

    q_conc = {"carimbo": None, "erro": None, "rotulo": None, "arquivo": None}
    try:
        rv = copiar_revisao_pricing(cfgp.get("pricing_dados_dir"), destino)
        if rv is None:
            q_conc["erro"] = "nenhum revisao_Sxx.html do pricing encontrado"
        else:
            q_conc.update({"carimbo": rv["modificado_em"], "rotulo": rv["rotulo"],
                           "arquivo": rv["arquivo"]})
    except Exception as e:  # noqa: BLE001
        q_conc["erro"] = f"falha copiando a revisao do pricing: {e}"

    payload = {
        "origem": "erp-bridge-painel", "gerado_em": gerado_em,
        "cfg": {k: cfgp[k] for k in ("rodizio_segundos", "reload_minutos",
                                     "validade_urgente_dias",
                                     "cobranca_dias_limiar",
                                     "detector_dashboard_url")},
        "validade_relampago": q_validade,
        "ruptura": q_ruptura,
        "cobranca": q_cobranca,
        "concorrente": q_conc,
    }
    dados = json.dumps(payload, ensure_ascii=False, indent=1, default=str)
    projections._escrever_atomico(os.path.join(destino, "dados_painel.json"),
                                  dados.encode("utf-8"))
    projections._escrever_atomico(os.path.join(destino, "index.html"),
                                  renderizar(payload).encode("utf-8"))

    avisos = [q for q, e in (("validade", q_validade["erro"]),
                             ("ruptura", q_ruptura["erro"]),
                             ("cobranca", q_cobranca["erro"]),
                             ("concorrente", q_conc["erro"])) if e]
    resumo = (f"painel/index.html: {len(q_validade['itens'])} relampago, "
              f"{len(q_ruptura['itens'])} ruptura, "
              f"{len(q_cobranca['itens'])} cobranca (+{aband} abandonados)"
              + (f" — AVISO em: {', '.join(avisos)}" if avisos else ""))
    return [resumo]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_painel_rodar.py -q`
Expected: `3 passed`

- [ ] **Step 5: Integrar no bridge.py**

Em `src/bridge.py`, DUAS edições:

(1) na lista `choices` do `--only`, acrescentar `"painel"`:

```python
    ap.add_argument("--only", default="all",
                    choices=["all", "catalogo", "movimentos", "vendas", "entradas", "recebimentos", "pedidos", "pedidos-venda", "vendas-mensal", "historico-cliente", "exposicao", "painel"],
                    help="qual bloco gerar (default: all)")
```

(2) no `try` do `main()`, trocar as duas linhas de coleta+escrita por:

```python
        cfg = (json.load(open(os.path.join(RAIZ, "config.example.json"), encoding="utf-8"))
               if args.demo else carregar_config(args.config))
        relatorio = []
        if args.only != "painel":
            cat, ven, ent, ped, pv, vm, hc, vc, val = coletar(cfg, args.demo, args.only)
            relatorio = escrever(cfg, cat, ven, ent, ped, pv, vm, hc, vc, args.only, val)
        if args.only in ("all", "painel"):
            import painel_compras
            relatorio += painel_compras.rodar(cfg, usar_demo=args.demo)
```

(3) no docstring do topo do bridge.py, acrescentar uma linha na lista de
consumidores e uma no bloco "Uso":

```
  painel        -> painel/index.html + dados_painel.json (Painel de Compras
                   TV+PC: validade x relampago, ruptura, cobranca, concorrente)
```
```
  python src/bridge.py --only painel        # painel de compras (06:00 + pos-catalogo)
```

- [ ] **Step 6: Config de exemplo**

Em `config.example.json`, adicionar a seção (entre `"exposicao"` e `"saida"`):

```json
  "painel": {
    "_comentario": "Painel de Compras (TV+PC). dir_saida e servido por http.server (porta_http). cobranca: entra com >= dias_limiar aberto OU previsao vencida, janela maxima cobranca_max_dias (medido 2026-07-20: sem janela seriam 494 pedidos — lixo historico vira contador de abandonados). detector_rounds_dir = <detector-estoque>/data/rounds. detector_dashboard_url = http://localhost:5173 (porta do dashboard do detector).",
    "dir_saida": "C:/Users/COMPUTADOR/erp-bridge-atacaderj/saida/painel",
    "porta_http": 8477,
    "cobranca_dias_limiar": 7,
    "cobranca_max_dias": 60,
    "validade_urgente_dias": 30,
    "rodizio_segundos": 20,
    "reload_minutos": 5,
    "pricing_dados_dir": "",
    "detector_rounds_dir": "",
    "detector_dashboard_url": ""
  },
```

(No ponte, `config.local.json` receberá:
`pricing_dados_dir = C:/Users/User/pricing-atacaderj/dados`,
`detector_rounds_dir = C:/Users/User/detector-ruptura-estoque-atacaderj/data/rounds`,
`detector_dashboard_url = http://localhost:5173` — Task 9.)

- [ ] **Step 7: Demo de ponta a ponta + suíte completa**

Run: `python src/bridge.py --demo`
Expected: sai `[OK] (demo) escrito em ...` com a linha
`painel/index.html: 3 relampago, 0 ruptura, 2 cobranca (+2 abandonados) — AVISO em: ruptura, concorrente`
(ruptura/concorrente avisam porque o config de exemplo não aponta as pastas — é o comportamento certo).

Abrir `saida/painel/index.html` no navegador: grade 2×2 com os dados demo;
clicar em "Validade × Relâmpago" abre o detalhe com filtro; Esc volta;
acrescentar `#tv` na URL e recarregar liga o rodízio.

Run: `python -m pytest tests/ -q`
Expected: tudo verde.

- [ ] **Step 8: Commit**

```bash
git add src/painel_compras.py src/bridge.py config.example.json tests/test_painel_rodar.py
git commit -m "feat(painel): orquestracao rodar() + --only painel no bridge + config"
```

---

### Task 8: Tarefas agendadas + servidor HTTP + README

**Files:**
- Create: `scripts/register-painel-tasks.ps1`
- Modify: `README.md` (nova seção curta)

**Interfaces:**
- Consumes: `--only painel` (Task 7) e `config.local.json > painel` (porta/pasta).
- Produces: tarefas `AtacadeRJ - Painel Compras` (geração) e
  `AtacadeRJ - Painel Compras Servidor` (HTTP no boot).

- [ ] **Step 1: Escrever o script**

Criar `scripts/register-painel-tasks.ps1` (mesmo padrão do register-tasks.ps1
— separado de propósito para não recriar as 4 tarefas existentes):

```powershell
# Registra as 2 tarefas do Painel de Compras (Windows Task Scheduler).
# Rode em PowerShell (Admin), dentro da pasta do repo: ./scripts/register-painel-tasks.ps1
# Geracao: 06:00 (apos bridge 05:00 + detector 05:30) e ~10min apos cada
# rodada de catalogo (08/12/15/18h). Servidor HTTP: no boot, porta/pasta do
# config.local.json > painel.

$ErrorActionPreference = "Stop"
$raiz   = Split-Path -Parent $PSScriptRoot
# nao usar (Get-Command python): o alias da Microsoft Store engana e o Task
# Scheduler roda sem o PATH do usuario — apontar para o exe real
$python = @(
  "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
  "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
  "C:\Python312\python.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) { $python = (Get-Command python).Source }
$bridge = Join-Path $raiz "src\bridge.py"

$cfg = Get-Content (Join-Path $raiz "config.local.json") -Raw | ConvertFrom-Json
if (-not $cfg.painel) { throw "config.local.json sem a secao 'painel' — copie do config.example.json" }
$dir   = $cfg.painel.dir_saida
$porta = $cfg.painel.porta_http
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }

# --- Tarefa 1: GERACAO do painel ---
$acaoGer = New-ScheduledTaskAction -Execute $python -Argument "`"$bridge`" --only painel"
$gatGer  = @(
  New-ScheduledTaskTrigger -Daily -At 06:00
  New-ScheduledTaskTrigger -Daily -At 08:10
  New-ScheduledTaskTrigger -Daily -At 12:10
  New-ScheduledTaskTrigger -Daily -At 15:10
  New-ScheduledTaskTrigger -Daily -At 18:10
)
Register-ScheduledTask -TaskName "AtacadeRJ - Painel Compras" -Action $acaoGer `
  -Trigger $gatGer -RunLevel Limited -Force | Out-Null
Write-Host "OK: 'AtacadeRJ - Painel Compras' (06:00/08:10/12:10/15:10/18:10)"

# --- Tarefa 2: SERVIDOR HTTP (rede local) ---
$acaoSrv = New-ScheduledTaskAction -Execute $python `
  -Argument "-m http.server $porta --directory `"$dir`" --bind 0.0.0.0"
$gatSrv = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName "AtacadeRJ - Painel Compras Servidor" `
  -Action $acaoSrv -Trigger $gatSrv -RunLevel Limited -Force | Out-Null
Start-ScheduledTask -TaskName "AtacadeRJ - Painel Compras Servidor"
Write-Host "OK: 'AtacadeRJ - Painel Compras Servidor' (boot; ja iniciado agora)"
Write-Host "`nPainel: http://<ip-do-ponte>:$porta/  (TV: acrescente #tv)"
```

- [ ] **Step 2: Testar o script em modo local (nesta máquina, sem Admin)**

Run (PowerShell comum — vai falhar SÓ no Register-ScheduledTask por falta de
Admin, provando que o parse/paths estão certos):
`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/register-painel-tasks.ps1`
Expected: erro claro de acesso/Admin no primeiro `Register-ScheduledTask`
(ou sucesso, se rodar como Admin). Erro de sintaxe/parse = corrigir antes de commitar.

- [ ] **Step 3: README**

Em `README.md`, adicionar após a seção "## O que ele gera" uma linha na tabela:

```markdown
| **painel** | `painel/index.html` (Painel de Compras TV+PC: validade×relâmpago, ruptura, cobrança, concorrente) | setor de compras (TV da sala + PCs) |
```

E, após a seção "## Ligar no banco de verdade", nova seção:

```markdown
## Painel de Compras (TV + PC)

Gerado por `python src/bridge.py --only painel` (agendado 06:00 + pós-catálogo;
`./scripts/register-painel-tasks.ps1` registra geração + servidor HTTP).
Acesso: `http://<ip-do-ponte>:8477/` — nos PCs é interativo (clique abre o
detalhe com filtro); na TV use `http://<ip-do-ponte>:8477/#tv` em tela cheia
(rodízio automático, recarrega sozinho). Fontes e regras: spec
`docs/superpowers/specs/2026-07-20-painel-compras-design.md`.
```

- [ ] **Step 4: Commit**

```bash
git add scripts/register-painel-tasks.ps1 README.md
git commit -m "feat(painel): tarefas agendadas (geracao + servidor http) e README"
git push
```

---

### Task 9: Implantação no PC-ponte (validação real)

**Files:**
- Modify (no ponte): `C:\Users\User\erp-bridge-atacaderj\config.local.json`
- Modify: `STATUS.md` (log de progresso, neste repo)

**Interfaces:**
- Consumes: tudo das Tasks 1–8, já no GitHub.
- Produces: painel NO AR na rede da loja.

Acesso ao ponte: `ssh -i ~/.ssh/id_ed25519_ponte User@100.99.176.6`
(shell remoto é **cmd.exe** — use `&&`, não `;`).

- [ ] **Step 1: Atualizar o repo no ponte**

```bash
ssh -i ~/.ssh/id_ed25519_ponte User@100.99.176.6 "cd /d C:\Users\User\erp-bridge-atacaderj && git pull"
```
Expected: fast-forward com os commits das Tasks 1–8.

- [ ] **Step 2: Completar o config.local.json do ponte**

Acrescentar a seção `painel` (copiar do config.example.json e ajustar caminhos
do ponte — NUNCA sobrescrever o arquivo, que tem a senha do banco):

```json
  "painel": {
    "dir_saida": "C:/Users/User/erp-bridge-atacaderj/saida/painel",
    "porta_http": 8477,
    "cobranca_dias_limiar": 7,
    "cobranca_max_dias": 60,
    "validade_urgente_dias": 30,
    "rodizio_segundos": 20,
    "reload_minutos": 5,
    "pricing_dados_dir": "C:/Users/User/pricing-atacaderj/dados",
    "detector_rounds_dir": "C:/Users/User/detector-ruptura-estoque-atacaderj/data/rounds",
    "detector_dashboard_url": "http://localhost:5173"
  },
```
(Se o repo do detector-estoque ainda não estiver clonado no ponte, deixar
`detector_rounds_dir` apontando para o caminho futuro — o quadrante avisa
"nenhuma rodada encontrada" até lá, comportamento previsto na spec §8.)

- [ ] **Step 3: Rodar contra o banco real e conferir os números**

```bash
ssh -i ~/.ssh/id_ed25519_ponte User@100.99.176.6 "cd /d C:\Users\User\erp-bridge-atacaderj && python src\bridge.py --only painel"
```
Expected: `[OK] (banco) ... painel/index.html: ~247 relampago, ... cobranca (+N abandonados)`.
Conferências (contra os números medidos em 2026-07-20 — podem ter variado dias depois):
- relâmpago na casa das centenas (247 na medição);
- cobrança bem MENOR que 494 (a janela de 60 dias corta o lixo de janeiro);
- abandonados na casa das centenas.
Validar 1 produto relâmpago conhecido com o dono (preço e validade batem com o ERP).

- [ ] **Step 4: Registrar as tarefas (PowerShell Admin, no ponte — manual)**

No ponte (RDP/AnyDesk, PowerShell **Admin**):
```powershell
cd C:\Users\User\erp-bridge-atacaderj
./scripts/register-painel-tasks.ps1
```
Expected: as 2 mensagens `OK:` e o servidor já de pé. Testar de outro PC da
rede: `http://192.168.0.164:8477/` (interativo) e `.../#tv` (rodízio).

- [ ] **Step 5: STATUS.md + commit final**

Marcar no `STATUS.md` (Log de progresso):

```markdown
- AAAA-MM-DD: **Painel de Compras NO AR** — `--only painel` na bridge,
  tarefas 06:00 + pós-catálogo, servidor http porta 8477. TV da sala de
  compras aponta para /#tv. Pendências herdadas: rounds do detector-estoque
  (clonar/agendar no ponte) e revisão semanal do pricing (já gera o quadrante
  quando existir arquivo da semana).
```

```bash
git add STATUS.md
git commit -m "docs: painel de compras no ar no ponte (log STATUS)"
git push
```

---

## Self-review (feito em 2026-07-20)

1. **Cobertura da spec:** §3 fluxo → Tasks 2–7; §4.1 → Tasks 1–2; §4.2 → Task 4;
   §4.3 (+ janela máxima, emenda pós-investigação) → Tasks 1 e 3; §4.4 → Task 5;
   §5 modos TV/PC → Task 6; §6 acesso/agendamento → Task 8; §7 config → Task 7;
   §8 erros/staleness → Tasks 6–7 (erro por quadrante + carimbos);
   §9 testes → todos; §10 investigações → resolvidas (Fatos do schema);
   §12 riscos → contadores de abandonados/sem-validade nos quadrantes.
2. **Placeholders:** nenhum TBD/TODO; todo step de código traz o código.
3. **Consistência de tipos:** `_cod`/`_dias` definidos na Task 2 e usados nas 3–7;
   payload da Task 6 = o que `rodar()` monta na Task 7 (conferido campo a campo);
   chaves demo (Task 1) = aliases das queries = entrada das funções puras.
