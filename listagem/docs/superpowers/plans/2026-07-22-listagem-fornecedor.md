# Listagem de Produtos por Fornecedor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Relatório HTML único com barra de fornecedor: código · produto · curva · corredor (ruas do depósito) · estoque mínimo (mediana de janelas rolantes de 45 dias, ruptura por curva).

**Architecture:** O `erp-bridge-atacaderj` ganha um alvo novo `--only listagem` que exporta 4 CSVs (catálogo enxuto, vendas diárias 180d, entradas com fornecedor 180d, negociação). Este repo (`listagem-fornecedor-atacaderj`) lê esses CSVs + o estado de ruas do `deposito-atacaderj`, calcula fornecedor e estoque mínimo por produto e gera `saida/listagem-fornecedores.html` (arquivo único, dados embutidos, JS inline).

**Tech Stack:** Python 3 stdlib apenas (csv, json, statistics, math, datetime, argparse, html). pytest para testes. Sem dependência nova.

**Spec:** `docs/superpowers/specs/2026-07-22-listagem-fornecedor-design.md` (decisões do dono registradas lá).

## Global Constraints

- SEM tarefa agendada — geração manual durante o teste (decisão do dono 22/07).
- Bridge: login SQL SÓ LEITURA; apenas SELECT/WITH; nunca commitar senha/custo/preço (os CSVs novos NÃO têm preço nem custo).
- NÃO mexer em `janela_dias` (120) global do ponte — os detectores dependem dela; a listagem usa janela própria de 180 dias.
- CSVs no padrão do bridge: separador `;`, escrita atômica (`_escrever_atomico`), UTF-8.
- Ruptura por curva: A=10, B=20, C=30 dias seguidos sem venda; sem curva = 20.
- "COTACAO" (tbPessoa cd 164259) é exclusivo: produto com negociação COTACAO vai só para COTACAO.
- Fatos validados no ERP em 22/07 (via ssh ponte, dados reais): `tbNegociacao` usa `cdSuperProduto` (não cdProduto) e tem `dtAlteracao` frequentemente NULL; join de entradas com fornecedor = `tbNotaItem` × `tbNotaEntrada` (cdNotaEntrada=cdNota, + cdPessoaFilial) × `tbNota` (cdNota + cdPessoaFilial) → `tbNota.cdPessoaComercial` → `tbPessoa`.
- Commits: cada repo commita em separado; erp-bridge tem remote (push); listagem ainda só commit local.

---

## Repo A: erp-bridge-atacaderj (`C:\Users\COMPUTADOR\erp-bridge-atacaderj`)

### Task 1: Queries novas (NEGOCIACAO_FORNECEDOR e ENTRADAS_FORNECEDOR)

**Files:**
- Modify: `src/queries.py` (acrescentar as duas constantes no fim do arquivo)
- Test: `tests/test_listagem_queries.py` (novo)

**Interfaces:**
- Produces: `queries.NEGOCIACAO_FORNECEDOR` (sem placeholder) → colunas `codigo, fornecedor, dt_alteracao`; `queries.ENTRADAS_FORNECEDOR` (placeholder `{janela_listagem}`) → colunas `codigo, data, fornecedor, qtd`. Task 3 as executa; Task 2 projeta as linhas.

- [ ] **Step 1: Write the failing test**

Criar `tests/test_listagem_queries.py` (padrão do repo: asserts de substring no SQL — ver `tests/test_catalogo_query.py`):

```python
# -*- coding: utf-8 -*-
"""Queries do alvo `listagem` (app listagem-fornecedor).

Fatos validados no ERP em 2026-07-22 (amostra real via ponte):
- tbNegociacao liga por cdSuperProduto (NAO tem cdProduto) e dtAlteracao
  vem NULL com frequencia -> dt_alteracao pode sair vazio.
- fornecedor da entrada = tbNota.cdPessoaComercial (join por cdNota +
  cdPessoaFilial), nome em tbPessoa (amostra: QUEIJOS DONA ROSA, JW DOCES)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import queries  # noqa: E402


def test_negociacao_liga_por_cdsuperproduto():
    sql = queries.NEGOCIACAO_FORNECEDOR
    assert "p.cdSuperProduto = n.cdSuperProduto" in sql
    assert "tbNegociacao" in sql
    assert "MAX(n.dtAlteracao)" in sql          # dtAlteracao NULL e comum


def test_negociacao_nao_exporta_valores():
    # regra do repo: nada de custo/preco em arquivo que sai do ponte
    sql = queries.NEGOCIACAO_FORNECEDOR
    assert "vlEmbalagem" not in sql
    assert "vlPreco" not in sql


def test_entradas_fornecedor_join_validado():
    sql = queries.ENTRADAS_FORNECEDOR
    assert "n.cdNota = i.cdNota" in sql
    assert "n.cdPessoaFilial = i.cdPessoaFilial" in sql
    assert "ne.cdNotaEntrada = i.cdNota" in sql
    assert "{janela_listagem}" in sql
    assert "i.cdProduto IS NOT NULL" in sql     # nota com produto NULL existe


def test_entradas_fornecedor_qtd_em_unidades():
    # convencao da nota: qtItemNota em volumes -> x qtEmbalagem = unidades
    assert "SUM(i.qtItemNota * i.qtEmbalagem)" in queries.ENTRADAS_FORNECEDOR
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:\Users\COMPUTADOR\erp-bridge-atacaderj && python -m pytest tests/test_listagem_queries.py -v`
Expected: FAIL — `AttributeError: module 'queries' has no attribute 'NEGOCIACAO_FORNECEDOR'`

- [ ] **Step 3: Write minimal implementation**

No FIM de `src/queries.py`, acrescentar:

```python
# NEGOCIACAO_FORNECEDOR: produto x fornecedor da tela de NEGOCIACAO — e o
# campo que o dono usa para marcar "esse produto e de cotacao" (pessoa
# "COTACAO", cd 164259; validado 2026-07-22: oleo Soya 15450 = COTACAO).
# tbNegociacao NAO tem cdProduto: liga por cdSuperProduto. Um produto pode
# ter negociacao com varios fornecedores (uma linha por par). dtAlteracao
# vem NULL com frequencia -> MAX() e o CSV sai vazio nesses casos.
# Alimenta o app listagem-fornecedor (Regra 1 do spec de la).
NEGOCIACAO_FORNECEDOR = """
SELECT
    p.cdProduto                                 AS codigo,
    LTRIM(RTRIM(ps.nmPessoa))                   AS fornecedor,
    CONVERT(char(10), MAX(n.dtAlteracao), 126)  AS dt_alteracao
FROM dbo.tbNegociacao n
JOIN dbo.tbProduto p ON p.cdSuperProduto = n.cdSuperProduto
JOIN dbo.tbPessoa ps ON ps.cdPessoa = n.cdPessoaComercial
GROUP BY p.cdProduto, LTRIM(RTRIM(ps.nmPessoa))
ORDER BY codigo, fornecedor
"""

# ENTRADAS_FORNECEDOR: igual a ENTRADAS (entregas por produto x dia, qtd em
# UNIDADES = volumes x embalagem da nota), mas com o FORNECEDOR da nota —
# join validado com dados reais em 2026-07-22 (tbNota.cdPessoaComercial por
# cdNota + cdPessoaFilial; amostra: QUEIJOS DONA ROSA, JW DOCES).
# Nota sem pessoa -> fornecedor '' (o consumidor ignora na dominancia).
# Janela propria ({janela_listagem}, 180d) — NAO usa a janela dos detectores.
ENTRADAS_FORNECEDOR = """
SELECT
    i.cdProduto                                        AS codigo,
    CAST(ne.dtChegada AS date)                         AS data,
    LTRIM(RTRIM(COALESCE(ps.nmPessoa, '')))            AS fornecedor,
    CAST(SUM(i.qtItemNota * i.qtEmbalagem) AS decimal(14,3)) AS qtd
FROM dbo.tbNotaItem i
JOIN dbo.tbNotaEntrada ne
  ON ne.cdNotaEntrada = i.cdNota AND ne.cdPessoaFilial = i.cdPessoaFilial
JOIN dbo.tbNota n
  ON n.cdNota = i.cdNota AND n.cdPessoaFilial = i.cdPessoaFilial
LEFT JOIN dbo.tbPessoa ps ON ps.cdPessoa = n.cdPessoaComercial
WHERE ne.dtChegada >= DATEADD(day, -{janela_listagem}, CAST(GETDATE() AS date))
  AND i.cdProduto IS NOT NULL
GROUP BY i.cdProduto, CAST(ne.dtChegada AS date),
         LTRIM(RTRIM(COALESCE(ps.nmPessoa, '')))
ORDER BY codigo, data
"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_listagem_queries.py -v`
Expected: 4 passed

- [ ] **Step 5: Rodar a suíte inteira do repo (nada pode quebrar)**

Run: `python -m pytest tests/ -q`
Expected: tudo verde (mesmo total de antes + 4)

- [ ] **Step 6: Commit**

```bash
git add src/queries.py tests/test_listagem_queries.py
git commit -m "feat(listagem): queries negociacao-fornecedor e entradas com fornecedor"
```

### Task 2: Projections dos 4 CSVs da listagem

**Files:**
- Modify: `src/projections.py` (acrescentar 3 funções no fim; vendas reusa `vendas_csv` existente)
- Test: `tests/test_listagem_projections.py` (novo)

**Interfaces:**
- Consumes: linhas dict das queries da Task 1 e do `CATALOGO` existente (`codigo, descricao, embalagem, curva, peso, ativo`); helpers internos `_escrever_atomico` e `_csv_ponto_virgula` (já existem em projections.py).
- Produces: `projections.negociacao_csv(rows, caminho) -> int`; `projections.entradas_fornecedor_csv(rows, caminho) -> int`; `projections.catalogo_listagem_csv(cat, caminho) -> int`. CSVs sep `;` com cabeçalhos exatos: `codigo;fornecedor;dt_alteracao` · `codigo;data;fornecedor;qtd` · `codigo;descricao;embalagem;curva;peso;ativo`. Vendas: reusar `projections.vendas_csv` (cabeçalho `codigo;descricao;data;qtd_vendida`).

- [ ] **Step 1: Write the failing test**

Criar `tests/test_listagem_projections.py`:

```python
# -*- coding: utf-8 -*-
"""Projecoes dos CSVs do alvo `listagem` (sem custo/preco em nenhum)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import projections  # noqa: E402


def _ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        return f.read().strip().split("\n")


def test_negociacao_csv(tmp_path):
    rows = [
        {"codigo": 15450, "fornecedor": "COTACAO", "dt_alteracao": None},
        {"codigo": 15450, "fornecedor": "WAL MART BRASIL LTDA",
         "dt_alteracao": "2026-05-01"},
    ]
    arq = str(tmp_path / "negociacao.csv")
    assert projections.negociacao_csv(rows, arq) == 2
    linhas = _ler(arq)
    assert linhas[0] == "codigo;fornecedor;dt_alteracao"
    assert linhas[1] == "15450;COTACAO;"          # NULL -> vazio
    assert linhas[2] == "15450;WAL MART BRASIL LTDA;2026-05-01"


def test_entradas_fornecedor_csv(tmp_path):
    rows = [{"codigo": 181, "data": "2026-07-22",
             "fornecedor": "QUEIJOS DONA ROSA", "qtd": 32.6}]
    arq = str(tmp_path / "entradas_fornecedor.csv")
    assert projections.entradas_fornecedor_csv(rows, arq) == 1
    linhas = _ler(arq)
    assert linhas[0] == "codigo;data;fornecedor;qtd"
    assert linhas[1] == "181;2026-07-22;QUEIJOS DONA ROSA;32.6"


def test_catalogo_listagem_csv_sem_preco_nem_custo(tmp_path):
    cat = [{"codigo": 15450, "descricao": "OLEO SOJA SOYA 900ML",
            "embalagem": 20, "curva": "A", "peso": 0, "ativo": 1,
            "custo_atual": 6.0, "preco_varejo": 8.0}]
    arq = str(tmp_path / "catalogo_listagem.csv")
    assert projections.catalogo_listagem_csv(cat, arq) == 1
    linhas = _ler(arq)
    assert linhas[0] == "codigo;descricao;embalagem;curva;peso;ativo"
    assert linhas[1] == "15450;OLEO SOJA SOYA 900ML;20;A;0;1"
    assert "6.0" not in linhas[1] and "8.0" not in linhas[1]


def test_catalogo_listagem_curva_vazia_sai_vazia(tmp_path):
    cat = [{"codigo": 1, "descricao": "X", "embalagem": None,
            "curva": None, "peso": 0, "ativo": 1}]
    arq = str(tmp_path / "c.csv")
    projections.catalogo_listagem_csv(cat, arq)
    assert _ler(arq)[1] == "1;X;;;0;1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_listagem_projections.py -v`
Expected: FAIL — `AttributeError: ... no attribute 'negociacao_csv'`

- [ ] **Step 3: Write minimal implementation**

No FIM de `src/projections.py`, acrescentar (mesmo estilo de `entradas_csv`):

```python
# ---------- Consumidor: listagem-fornecedor ----------

def negociacao_csv(rows, caminho):
    """Produto x fornecedor da tela de negociacao (dt_alteracao pode ser
    NULL -> vazio). Regra 1 do app listagem-fornecedor."""
    cab = ["codigo", "fornecedor", "dt_alteracao"]
    linhas = [[r["codigo"], r["fornecedor"], r.get("dt_alteracao") or ""]
              for r in rows]
    _escrever_atomico(caminho, _csv_ponto_virgula(cab, linhas))
    return len(linhas)


def entradas_fornecedor_csv(rows, caminho):
    """Entregas por produto x dia x fornecedor, qtd em UNIDADES."""
    cab = ["codigo", "data", "fornecedor", "qtd"]
    linhas = [[r["codigo"], r["data"], r["fornecedor"], r["qtd"]]
              for r in rows]
    _escrever_atomico(caminho, _csv_ponto_virgula(cab, linhas))
    return len(linhas)


def catalogo_listagem_csv(cat, caminho):
    """Catalogo enxuto p/ a listagem: SEM custo e SEM preco (regra do repo:
    valores nunca saem em arquivo de consumidor fora da cotacao)."""
    cab = ["codigo", "descricao", "embalagem", "curva", "peso", "ativo"]
    linhas = [[r["codigo"], r["descricao"],
               r.get("embalagem") if r.get("embalagem") is not None else "",
               r.get("curva") or "", r.get("peso"), r.get("ativo")]
              for r in cat]
    _escrever_atomico(caminho, _csv_ponto_virgula(cab, linhas))
    return len(linhas)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_listagem_projections.py -v`
Expected: 4 passed

- [ ] **Step 5: Suíte inteira**

Run: `python -m pytest tests/ -q`
Expected: tudo verde

- [ ] **Step 6: Commit**

```bash
git add src/projections.py tests/test_listagem_projections.py
git commit -m "feat(listagem): projections dos 4 CSVs (sem custo/preco)"
```

### Task 3: Alvo `--only listagem` no bridge + demo + config

**Files:**
- Modify: `src/bridge.py` (funções novas `coletar_listagem`/`escrever_listagem` + choice `listagem` no argparse + despacho no `main()`)
- Modify: `src/demo_data.py` (funções `negociacao()` e `entradas_fornecedor()`)
- Modify: `config.example.json` (chaves novas)
- Test: manual via `--demo` (o repo não tem teste de bridge.py; padrão é validar pelo run)

**Interfaces:**
- Consumes: `queries.NEGOCIACAO_FORNECEDOR`, `queries.ENTRADAS_FORNECEDOR` (Task 1); `projections.negociacao_csv`, `entradas_fornecedor_csv`, `catalogo_listagem_csv`, `vendas_csv` (Task 2); `queries.CATALOGO` e `queries.VENDAS` existentes.
- Produces: `python src/bridge.py --only listagem [--demo]` escreve em `saida.listagem_dir`: `catalogo_listagem.csv`, `vendas_diarias.csv`, `entradas_fornecedor.csv`, `negociacao.csv`. Config: `listagem.janela_dias` (default 180), `saida.listagem_dir` (default `<repo>\saida\listagem`). O alvo NÃO entra no `all` (agenda própria, mesmo espírito do `exposicao`; roda manual durante o teste).

- [ ] **Step 1: Demo data**

Em `src/demo_data.py`, acrescentar no fim (produtos coerentes com o `catalogo()` demo existente — abra o arquivo e use 3 códigos que já existam lá; os valores abaixo assumem os códigos 101, 102, 103; ajuste se o demo usar outros):

```python
def negociacao():
    """Demo da tela de negociacao: 101 e de COTACAO (exclusivo), 102 tem
    dois fornecedores reais, 103 nao tem negociacao nenhuma."""
    return [
        {"codigo": 101, "fornecedor": "COTACAO", "dt_alteracao": None},
        {"codigo": 102, "fornecedor": "RICLAN SA", "dt_alteracao": "2026-06-01"},
        {"codigo": 102, "fornecedor": "GARCIA", "dt_alteracao": "2026-04-01"},
    ]


def entradas_fornecedor(janela):
    """Demo de entregas com fornecedor (datas dentro da janela)."""
    from datetime import date, timedelta
    d = lambda n: (date.today() - timedelta(days=n)).isoformat()  # noqa: E731
    return [
        {"codigo": 102, "data": d(10), "fornecedor": "RICLAN SA", "qtd": 120.0},
        {"codigo": 102, "data": d(40), "fornecedor": "GARCIA", "qtd": 60.0},
        {"codigo": 103, "data": d(20), "fornecedor": "JW DOCES", "qtd": 30.0},
    ]
```

- [ ] **Step 2: bridge.py — coletar/escrever da listagem**

Em `src/bridge.py`, depois da função `escrever(...)` (antes do `main()`), acrescentar:

```python
def coletar_listagem(cfg, usar_demo):
    """Alvo `listagem` tem agenda propria (janela 180d) e NAO roda no `all`:
    nao pagar 180d de vendas nos jobs de catalogo/movimentos dos detectores."""
    janela = int(cfg.get("listagem", {}).get("janela_dias", 180))
    if usar_demo:
        return (demo_data.catalogo(), demo_data.vendas(janela),
                demo_data.entradas_fornecedor(janela), demo_data.negociacao())
    import db
    conn = db.conectar(cfg["db"])
    try:
        cat = db.consultar(conn, queries.CATALOGO)
        ven = db.consultar(conn, queries.VENDAS.format(janela=janela))
        entf = db.consultar(conn, queries.ENTRADAS_FORNECEDOR.format(
            janela_listagem=janela))
        neg = db.consultar(conn, queries.NEGOCIACAO_FORNECEDOR)
    finally:
        conn.close()
    return cat, ven, entf, neg


def escrever_listagem(cfg, cat, ven, entf, neg):
    destino = cfg["saida"].get("listagem_dir") or os.path.join(
        RAIZ, "saida", "listagem")
    os.makedirs(destino, exist_ok=True)
    rel = []
    n = projections.catalogo_listagem_csv(cat, os.path.join(destino, "catalogo_listagem.csv"))
    rel.append(f"listagem/catalogo_listagem.csv: {n}")
    n = projections.vendas_csv(ven, os.path.join(destino, "vendas_diarias.csv"))
    rel.append(f"listagem/vendas_diarias.csv: {n}")
    n = projections.entradas_fornecedor_csv(entf, os.path.join(destino, "entradas_fornecedor.csv"))
    rel.append(f"listagem/entradas_fornecedor.csv: {n}")
    n = projections.negociacao_csv(neg, os.path.join(destino, "negociacao.csv"))
    rel.append(f"listagem/negociacao.csv: {n}")
    return rel
```

No `main()`: adicionar `"listagem"` na lista `choices=[...]` do `--only`, e no corpo (onde os outros alvos despacham — siga o fluxo existente do arquivo: localize onde `coletar`/`escrever` são chamados) inserir o desvio ANTES da coleta padrão:

```python
    if args.only == "listagem":
        cfg = carregar_config(args.config)
        cat, ven, entf, neg = coletar_listagem(cfg, args.demo)
        for linha in escrever_listagem(cfg, cat, ven, entf, neg):
            print(linha)
        return
```

- [ ] **Step 3: config.example.json**

Acrescentar (ao lado do bloco `exposicao`, mesmo padrão de comentário):

```json
  "listagem": {
    "_comentario": "app listagem-fornecedor: janela PROPRIA de vendas/entradas (180d = 6 meses de janelas rolantes de 45d). NAO usa janela_dias dos detectores.",
    "janela_dias": 180
  },
```

e dentro de `"saida"`:

```json
    "listagem_dir": "saida/listagem",
```

- [ ] **Step 4: Validar com --demo**

Run: `python src/bridge.py --demo --only listagem`
Expected (4 linhas, contagens do demo):

```
listagem/catalogo_listagem.csv: <N produtos demo>
listagem/vendas_diarias.csv: <N linhas>
listagem/entradas_fornecedor.csv: 3
listagem/negociacao.csv: 3
```

Conferir: `saida/listagem/negociacao.csv` começa com `codigo;fornecedor;dt_alteracao` e a linha do 101 termina em `;` (dt vazio).

- [ ] **Step 5: Suíte inteira + commit**

Run: `python -m pytest tests/ -q` → verde.

```bash
git add src/bridge.py src/demo_data.py config.example.json
git commit -m "feat(listagem): alvo --only listagem exporta os 4 CSVs (janela propria 180d)"
git push
```

(Push: repo privado, é o combinado do CLAUDE.md do bridge.)

---

## Repo B: listagem-fornecedor-atacaderj (`C:\Users\COMPUTADOR\listagem-fornecedor-atacaderj`)

### Task 4: Scaffold + Regra 1 (fornecedor de cada produto)

**Files:**
- Create: `.gitignore`, `config.example.json`, `requirements-dev.txt`
- Create: `src/fornecedor.py`
- Test: `tests/test_fornecedor.py`

**Interfaces:**
- Produces: `fornecedor.atribuir(negociacoes, entradas) -> dict[int, str]` — mapa código→nome do fornecedor. `negociacoes`: list de dict `{"codigo": int, "fornecedor": str, "dt_alteracao": str}` (dt pode ser `""`). `entradas`: list de dict `{"codigo": int, "data": "YYYY-MM-DD", "fornecedor": str, "qtd": float}`. Constante `fornecedor.SEM_FORNECEDOR = "SEM FORNECEDOR"`. Task 8 consome.

- [ ] **Step 1: Scaffold**

`.gitignore`:

```
__pycache__/
config.local.json
saida/
```

`requirements-dev.txt`:

```
pytest
```

`config.example.json` (caminhos do PONTE como exemplo; no PC de dev usar config.local.json com caminhos locais):

```json
{
  "_comentario": "copie para config.local.json e ajuste. ruas_estado_json = estado do deposito-atacaderj no ponte (conferir o caminho real no start do servidor de la).",
  "entrada": {
    "catalogo_csv": "C:\\Users\\User\\erp-bridge-atacaderj\\saida\\listagem\\catalogo_listagem.csv",
    "vendas_csv": "C:\\Users\\User\\erp-bridge-atacaderj\\saida\\listagem\\vendas_diarias.csv",
    "entradas_csv": "C:\\Users\\User\\erp-bridge-atacaderj\\saida\\listagem\\entradas_fornecedor.csv",
    "negociacao_csv": "C:\\Users\\User\\erp-bridge-atacaderj\\saida\\listagem\\negociacao.csv",
    "ruas_estado_json": "C:\\Users\\User\\deposito-atacaderj\\saida\\estado_ruas.json"
  },
  "saida_html": "saida\\listagem-fornecedores.html"
}
```

- [ ] **Step 2: Write the failing test**

`tests/test_fornecedor.py`:

```python
# -*- coding: utf-8 -*-
"""Regra 1 do spec: COTACAO exclusivo > quem mais entregou em 6m >
negociacao mais recente > SEM FORNECEDOR."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import fornecedor  # noqa: E402


def test_cotacao_e_exclusivo_mesmo_com_entregas_de_outro():
    neg = [{"codigo": 15450, "fornecedor": "COTACAO", "dt_alteracao": ""},
           {"codigo": 15450, "fornecedor": "WAL MART", "dt_alteracao": "2026-05-01"}]
    ent = [{"codigo": 15450, "data": "2026-07-01",
            "fornecedor": "WAL MART", "qtd": 999.0}]
    assert fornecedor.atribuir(neg, ent)[15450] == "COTACAO"


def test_cotacao_casa_sem_diferenciar_caixa_e_espacos():
    neg = [{"codigo": 1, "fornecedor": "  Cotacao ", "dt_alteracao": ""}]
    assert fornecedor.atribuir(neg, [])[1] == "COTACAO"


def test_dominante_por_soma_de_unidades_nos_6m():
    ent = [{"codigo": 2, "data": "2026-07-01", "fornecedor": "RICLAN", "qtd": 60.0},
           {"codigo": 2, "data": "2026-06-01", "fornecedor": "GARCIA", "qtd": 50.0},
           {"codigo": 2, "data": "2026-05-01", "fornecedor": "RICLAN", "qtd": 10.0}]
    # RICLAN 70 > GARCIA 50
    assert fornecedor.atribuir([], ent)[2] == "RICLAN"


def test_empate_na_soma_vence_a_entrega_mais_recente():
    ent = [{"codigo": 3, "data": "2026-07-10", "fornecedor": "A1", "qtd": 50.0},
           {"codigo": 3, "data": "2026-06-01", "fornecedor": "B2", "qtd": 50.0}]
    assert fornecedor.atribuir([], ent)[3] == "A1"


def test_entrada_sem_fornecedor_nao_conta_na_dominancia():
    ent = [{"codigo": 4, "data": "2026-07-10", "fornecedor": "", "qtd": 999.0},
           {"codigo": 4, "data": "2026-06-01", "fornecedor": "JW DOCES", "qtd": 1.0}]
    assert fornecedor.atribuir([], ent)[4] == "JW DOCES"


def test_sem_entrada_cai_na_negociacao_mais_recente():
    neg = [{"codigo": 5, "fornecedor": "GARCIA", "dt_alteracao": "2026-01-01"},
           {"codigo": 5, "fornecedor": "RICLAN", "dt_alteracao": "2026-06-01"}]
    assert fornecedor.atribuir(neg, [])[5] == "RICLAN"


def test_negociacao_com_dt_vazia_perde_para_dt_preenchida():
    neg = [{"codigo": 6, "fornecedor": "GARCIA", "dt_alteracao": ""},
           {"codigo": 6, "fornecedor": "RICLAN", "dt_alteracao": "2026-06-01"}]
    assert fornecedor.atribuir(neg, [])[6] == "RICLAN"


def test_negociacoes_todas_sem_dt_desempata_por_ordem_alfabetica():
    neg = [{"codigo": 7, "fornecedor": "ZAMBONI", "dt_alteracao": ""},
           {"codigo": 7, "fornecedor": "AMBEV", "dt_alteracao": ""}]
    assert fornecedor.atribuir(neg, [])[7] == "AMBEV"


def test_sem_nada_vira_sem_fornecedor():
    assert fornecedor.atribuir([], []) == {}
    # quem consulta usa .get(codigo, SEM_FORNECEDOR)
    assert fornecedor.SEM_FORNECEDOR == "SEM FORNECEDOR"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd C:\Users\COMPUTADOR\listagem-fornecedor-atacaderj && python -m pytest tests/ -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fornecedor'`

- [ ] **Step 4: Write minimal implementation**

`src/fornecedor.py`:

```python
# -*- coding: utf-8 -*-
"""Regra 1 do spec (docs/superpowers/specs/2026-07-22-...-design.md):
1) negociacao com "COTACAO" -> COTACAO, exclusivo (decisao do dono 22/07);
2) senao, fornecedor com MAIOR soma de unidades entregues na janela do CSV
   (6 meses, ja recortada pelo bridge); empate -> entrega mais recente;
   empate de novo -> alfabetico (determinismo);
3) senao, negociacao alterada por ultimo (dt vazia = mais antiga;
   todas vazias -> alfabetico);
4) senao, o consumidor usa SEM_FORNECEDOR."""

SEM_FORNECEDOR = "SEM FORNECEDOR"
COTACAO = "COTACAO"


def _norm(nome):
    return (nome or "").strip().upper()


def atribuir(negociacoes, entradas):
    """-> {codigo: nome do fornecedor} (so codigos presentes nos insumos)."""
    resultado = {}

    neg_por_cod = {}
    for n in negociacoes:
        neg_por_cod.setdefault(n["codigo"], []).append(n)

    ent_por_cod = {}
    for e in entradas:
        if _norm(e["fornecedor"]):
            ent_por_cod.setdefault(e["codigo"], []).append(e)

    for codigo in set(neg_por_cod) | set(ent_por_cod):
        negs = neg_por_cod.get(codigo, [])
        if any(_norm(n["fornecedor"]) == COTACAO for n in negs):
            resultado[codigo] = COTACAO
            continue
        ents = ent_por_cod.get(codigo, [])
        if ents:
            por_forn = {}
            for e in ents:
                nome = e["fornecedor"].strip()
                total, recente = por_forn.get(nome, (0.0, ""))
                por_forn[nome] = (total + float(e["qtd"]),
                                  max(recente, str(e["data"])))
            # maior soma primeiro; empate -> entrega mais recente; e o nome
            # alfabetico como ultimo desempate (determinismo)
            melhor = sorted(por_forn.items(),
                            key=lambda kv: (-kv[1][0],
                                            _data_desc(kv[1][1]), kv[0]))[0]
            resultado[codigo] = melhor[0]
            continue
        if negs:
            escolhido = sorted(
                negs, key=lambda n: (_data_desc(str(n.get("dt_alteracao") or "")),
                                     n["fornecedor"].strip()))[0]
            resultado[codigo] = escolhido["fornecedor"].strip()
    return resultado


def _data_desc(data_iso):
    """Chave de ordenacao: data ISO mais RECENTE primeiro; vazia por ultimo.
    Truque sem datetime: nega cada caractere pelo complemento de ord()."""
    if not data_iso:
        return "~"                      # depois de qualquer data invertida
    return "".join(chr(255 - ord(c)) for c in data_iso)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: 9 passed. Se `test_empate_na_soma...` falhar, o bug está na chave de ordenação `_data_desc` — a data mais recente tem que vir PRIMEIRO no sorted crescente.

- [ ] **Step 6: Commit**

```bash
git add .gitignore requirements-dev.txt config.example.json src/fornecedor.py tests/test_fornecedor.py
git commit -m "feat: Regra 1 - fornecedor por produto (COTACAO exclusivo > dominante 6m > negociacao)"
```

### Task 5: Regra 2 (janelas rolantes, ruptura por curva, mediana)

**Files:**
- Create: `src/minimo.py`
- Test: `tests/test_minimo.py`

**Interfaces:**
- Produces: `minimo.calcular(vendas, fim, curva, janela=45, historico=180, limiares=None) -> (unidades: float | None, marca: str)`. `vendas`: dict `{"YYYY-MM-DD": float}` (dias sem chave = 0). `fim`: `datetime.date` (último dia do histórico). `curva`: `"A"|"B"|"C"|None|""`. `marca` ∈ `""` (normal), `"*"` (só janelas com ruptura), `"novo"` (estimativa proporcional), `"sem_venda"` (unidades=None). Constantes `minimo.LIMIAR_POR_CURVA = {"A": 10, "B": 20, "C": 30}` e `minimo.LIMIAR_PADRAO = 20`. Task 8 consome.

- [ ] **Step 1: Write the failing test**

`tests/test_minimo.py` (casos de brinquedo com janela=5/historico=10 conferíveis à mão + um caso realista 45/180):

```python
# -*- coding: utf-8 -*-
"""Regra 2 do spec: mediana de janelas rolantes; ruptura por curva
(A=10, B=20, C=30 dias seguidos sem venda; sem curva = 20)."""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import minimo  # noqa: E402

FIM = date(2026, 7, 20)


def _serie(valores, fim=FIM):
    """valores[i] = venda do dia (fim - (len-1-i)) — ultimo item = dia `fim`."""
    n = len(valores)
    return {(fim - timedelta(days=n - 1 - i)).isoformat(): v
            for i, v in enumerate(valores) if v}


def test_limiares_oficiais():
    assert minimo.LIMIAR_POR_CURVA == {"A": 10, "B": 20, "C": 30}
    assert minimo.LIMIAR_PADRAO == 20


def test_venda_constante_mediana_e_a_soma_da_janela():
    vendas = _serie([2] * 10)
    # 6 janelas de 5 dias, todas somam 10
    assert minimo.calcular(vendas, FIM, "A", janela=5, historico=10) == (10.0, "")


def test_mediana_par_usa_media_dos_dois_do_meio():
    vendas = _serie([10, 8, 0, 12, 9, 11, 0, 10])
    # janelas de 5 em 8 dias: somas 39, 40, 32, 42 -> mediana (39+40)/2 = 39.5
    u, m = minimo.calcular(vendas, FIM, "A", janela=5, historico=8,
                           limiares={"A": 99})
    assert (u, m) == (39.5, "")


def test_janela_com_ruptura_e_descartada():
    # dias: 5,5,0,0,0,5,5,5 ; limiar 3 -> janelas com >=3 zeros seguidos caem
    vendas = _serie([5, 5, 0, 0, 0, 5, 5, 5])
    # janelas (5d): [5,5,0,0,0]=10 (streak 3, cai) [5,0,0,0,5]=10 (cai)
    #              [0,0,0,5,5]=10 (cai) [0,0,5,5,5]=15 (streak 2, fica)
    u, m = minimo.calcular(vendas, FIM, "A", janela=5, historico=8,
                           limiares={"A": 3})
    assert (u, m) == (15.0, "")


def test_curva_c_tolera_streak_que_derruba_curva_a():
    vendas = _serie([5, 5, 0, 0, 0, 5, 5, 5])
    ua, _ = minimo.calcular(vendas, FIM, "A", janela=5, historico=8,
                            limiares={"A": 3, "C": 4})
    uc, _ = minimo.calcular(vendas, FIM, "C", janela=5, historico=8,
                            limiares={"A": 3, "C": 4})
    assert ua == 15.0
    assert uc == 10.0      # so a janela do meio tem streak 3 <4? nao: todas
    # ficam -> somas 10,10,10,15 -> mediana (10+10)/2 = 10.0


def test_todas_com_ruptura_usa_todas_e_marca_asterisco():
    vendas = _serie([5, 0, 0, 0, 0, 0, 0, 5])
    # toda janela de 5 tem streak >=3 -> fallback: somas 5,0,0,5 -> mediana 2.5
    u, m = minimo.calcular(vendas, FIM, "A", janela=5, historico=8,
                           limiares={"A": 3})
    assert (u, m) == (2.5, "*")


def test_janelas_antes_da_primeira_venda_nao_contam():
    # primeira venda no dia 4 (indice 3): janelas comecam ali
    vendas = _serie([0, 0, 0, 4, 4, 4, 4, 4])
    u, m = minimo.calcular(vendas, FIM, "A", janela=5, historico=8,
                           limiares={"A": 99})
    assert (u, m) == (20.0, "")   # unica janela pos-1a-venda: [4,4,4,4,4]


def test_produto_novo_estimativa_proporcional():
    # primeira venda ha 3 dias (nao cabe janela de 5): media diaria x janela
    vendas = _serie([0, 0, 0, 0, 0, 6, 0, 6])
    u, m = minimo.calcular(vendas, FIM, "A", janela=5, historico=8,
                           limiares={"A": 99})
    # desde a 1a venda: dias [6,0,6] -> media 4 -> 4 x 5 = 20
    assert (u, m) == (20.0, "novo")


def test_sem_venda_nenhuma():
    assert minimo.calcular({}, FIM, "A", janela=5, historico=8) == (None, "sem_venda")


def test_realista_180_dias_gap_de_25_derruba_b_mas_nao_c():
    # venda 1/dia, com buraco de 25 dias no meio (dias 80..104 zerados)
    valores = [1] * 180
    for i in range(80, 105):
        valores[i] = 0
    vendas = _serie(valores)
    ub, mb = minimo.calcular(vendas, FIM, "B")     # limiar 20: gap derruba
    uc, mc = minimo.calcular(vendas, FIM, "C")     # limiar 30: gap fica
    assert mb == "" and mc == ""
    assert ub == 45.0        # janelas limpas vendem 1/dia -> soma 45
    assert uc < ub           # com as janelas do buraco, a mediana cai


def test_curva_desconhecida_usa_limiar_padrao():
    vendas = _serie([1] * 40)
    u1, _ = minimo.calcular(vendas, FIM, None, janela=5, historico=40)
    u2, _ = minimo.calcular(vendas, FIM, "B", janela=5, historico=40)
    assert u1 == u2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_minimo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'minimo'`

- [ ] **Step 3: Write minimal implementation**

`src/minimo.py`:

```python
# -*- coding: utf-8 -*-
"""Regra 2 do spec: estoque minimo = mediana das somas de janelas rolantes
de 45 dias sobre 180 dias de vendas diarias.

- janela com N+ dias SEGUIDOS sem venda e descartada (ruptura); N por curva
  ABC (A=10, B=20, C=30; sem curva = 20) — decisao do dono 22/07;
- janelas anteriores a primeira venda nao contam (novo nao e ruptura);
- nenhuma janela limpa -> mediana de TODAS (marca "*", dono 22/07);
- produto novo (1a venda ha menos de `janela` dias) -> media diaria desde a
  1a venda x janela (marca "novo");
- sem venda no historico -> (None, "sem_venda")."""
from datetime import timedelta
from statistics import median

LIMIAR_POR_CURVA = {"A": 10, "B": 20, "C": 30}
LIMIAR_PADRAO = 20


def calcular(vendas, fim, curva, janela=45, historico=180, limiares=None):
    """vendas: {"YYYY-MM-DD": unidades}; fim: date. -> (unidades, marca)."""
    tabela = limiares if limiares is not None else LIMIAR_POR_CURVA
    limiar = tabela.get((curva or "").strip().upper() or None, LIMIAR_PADRAO)

    serie = []
    for i in range(historico):
        dia = (fim - timedelta(days=historico - 1 - i)).isoformat()
        serie.append(float(vendas.get(dia, 0.0)))

    primeira = next((i for i, v in enumerate(serie) if v > 0), None)
    if primeira is None:
        return None, "sem_venda"

    if primeira > len(serie) - janela:
        desde = serie[primeira:]
        media = sum(desde) / len(desde)
        return media * janela, "novo"

    somas_limpas, somas_todas = [], []
    for inicio in range(primeira, len(serie) - janela + 1):
        w = serie[inicio:inicio + janela]
        soma = sum(w)
        somas_todas.append(soma)
        if _maior_streak_zero(w) < limiar:
            somas_limpas.append(soma)

    if somas_limpas:
        return float(median(somas_limpas)), ""
    return float(median(somas_todas)), "*"


def _maior_streak_zero(valores):
    maior = atual = 0
    for v in valores:
        atual = atual + 1 if v == 0 else 0
        maior = max(maior, atual)
    return maior
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_minimo.py -v`
Expected: 11 passed. Conferência manual se algo falhar: os números dos testes de brinquedo estão comentados caso a caso.

- [ ] **Step 5: Commit**

```bash
git add src/minimo.py tests/test_minimo.py
git commit -m "feat: Regra 2 - mediana de janelas rolantes com ruptura por curva"
```

### Task 6: Formato (cx/un/kg + rótulo e ordem das ruas)

**Files:**
- Create: `src/formato.py`
- Test: `tests/test_formato.py`

**Interfaces:**
- Consumes: `(unidades, marca)` da Task 5; `embalagem` (float|None) e `peso` (0/1) do catálogo; rua interna (int 1-26 | None) do estado do depósito.
- Produces: `formato.exibir(unidades, embalagem, peso) -> str` ("7 cx" / "40 un" / "12 kg" / "—"); `formato.rotulo_rua(rua) -> str` ("A13 cons1", "A24 vitrine" p/ 26, "" p/ None); `formato.ordem_rua(rua) -> tuple` (chave de sort: ruas 1..26 na ordem, None no fim). Task 7/8 consomem.

- [ ] **Step 1: Write the failing test**

`tests/test_formato.py`:

```python
# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import formato  # noqa: E402


def test_caixa_mae_arredonda_para_cima():
    assert formato.exibir(130.0, 20, 0) == "7 cx"     # 6,5 -> 7
    assert formato.exibir(40.0, 20, 0) == "2 cx"      # exato nao sobe


def test_sem_caixa_mae_sai_em_unidades():
    assert formato.exibir(39.5, None, 0) == "40 un"
    assert formato.exibir(39.5, 1, 0) == "40 un"      # embalagem 1 = sem caixa


def test_balanca_sai_em_kg_e_ignora_embalagem():
    assert formato.exibir(11.2, 20, 1) == "12 kg"


def test_sem_dado():
    assert formato.exibir(None, 20, 0) == "—"


def test_rotulo_rua_igual_ao_deposito():
    assert formato.rotulo_rua(1) == "A1 bisc1"
    assert formato.rotulo_rua(9) == "A9"              # sem nome
    assert formato.rotulo_rua(26) == "A24 vitrine"    # rotulo especial
    assert formato.rotulo_rua(None) == ""


def test_ordem_rua_sem_rua_vai_para_o_fim():
    assert formato.ordem_rua(1) < formato.ordem_rua(26)
    assert formato.ordem_rua(26) < formato.ordem_rua(None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_formato.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'formato'`

- [ ] **Step 3: Write minimal implementation**

`src/formato.py`:

```python
# -*- coding: utf-8 -*-
"""Exibicao: quantidade (cx-mae teto / un / kg) e ruas do deposito.

RUAS copiadas VERBATIM de deposito-atacaderj/src/ruas.py (fonte da verdade:
docs/RUAS.md daquele repo, dono 20-22/07). Se o dono mudar rua la, atualizar
aqui tambem — sao 26 linhas, copia consciente em vez de import entre repos."""
import math

RUAS = [
    (1, "bisc1"), (2, "bisc1"), (3, "bisc2"), (4, "bebidas"),
    (5, "balas1"), (6, "balas2"), (7, "confeit"), (8, "perf/desc"),
    (9, ""), (10, "mat1"), (11, "mat2"), (12, "mat3"),
    (13, "cons1"), (14, "cons1/limp1"), (15, "cons2/limp2"),
    (16, "foodsvc/limp3"), (17, "jirau"), (18, ""), (19, ""), (20, ""),
    (21, ""), (22, ""), (23, "jirau"), (24, "ROTATIVO"), (25, "TERREO"),
    (26, "vitrine"),
]
ROTULO_ESPECIAL = {26: "A24 vitrine"}   # dono 22/07: 26 e EXIBIDA como 24
_NOMES = dict(RUAS)


def exibir(unidades, embalagem, peso):
    if unidades is None:
        return "—"
    if peso:
        return f"{math.ceil(unidades)} kg"
    if embalagem and float(embalagem) > 1:
        return f"{math.ceil(unidades / float(embalagem))} cx"
    return f"{math.ceil(unidades)} un"


def rotulo_rua(rua):
    if rua is None:
        return ""
    if rua in ROTULO_ESPECIAL:
        return ROTULO_ESPECIAL[rua]
    nome = _NOMES.get(rua, "")
    return f"A{rua} {nome}" if nome else f"A{rua}"


def ordem_rua(rua):
    return (1, 0) if rua is None else (0, rua)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_formato.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/formato.py tests/test_formato.py
git commit -m "feat: formato de exibicao (cx teto/un/kg) e ruas do deposito"
```

### Task 7: Relatório HTML (preparar + montar)

**Files:**
- Create: `src/relatorio.py`
- Test: `tests/test_relatorio.py`

**Interfaces:**
- Consumes: `formato.ordem_rua` (Task 6).
- Produces: `relatorio.preparar(por_fornecedor) -> list` e `relatorio.montar(fornecedores, dados_de) -> str` (HTML completo). `por_fornecedor`: dict `{nome: [linha,...]}` com linha = dict `{"codigo": int, "nome": str, "curva": str, "rua": int|None, "rua_rotulo": str, "minimo": str, "marca": str}` (`marca` ∈ `""|"*"|"novo"|"sem_venda"`). `preparar` devolve list de `{"nome", "qtd", "produtos"}` ordenada: COTACAO primeiro, alfabético no meio, SEM FORNECEDOR por último; produtos por (ordem_rua, nome). Task 8 consome.

- [ ] **Step 1: Write the failing test**

`tests/test_relatorio.py`:

```python
# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
import relatorio  # noqa: E402


def _linha(codigo, nome, rua=None, rotulo="", minimo="1 cx", marca=""):
    return {"codigo": codigo, "nome": nome, "curva": "A", "rua": rua,
            "rua_rotulo": rotulo, "minimo": minimo, "marca": marca}


def test_preparar_cotacao_primeiro_sem_fornecedor_ultimo():
    dados = {"GARCIA": [_linha(1, "X")], "SEM FORNECEDOR": [_linha(2, "Y")],
             "COTACAO": [_linha(3, "Z")], "AMBEV": [_linha(4, "W")]}
    nomes = [f["nome"] for f in relatorio.preparar(dados)]
    assert nomes == ["COTACAO", "AMBEV", "GARCIA", "SEM FORNECEDOR"]


def test_preparar_ordena_produtos_por_rua_depois_nome():
    dados = {"GARCIA": [_linha(1, "BBB", rua=None),
                        _linha(2, "AAA", rua=13, rotulo="A13 cons1"),
                        _linha(3, "CCC", rua=1, rotulo="A1 bisc1"),
                        _linha(4, "AAA", rua=13, rotulo="A13 cons1")]}
    prods = relatorio.preparar(dados)[0]["produtos"]
    assert [p["codigo"] for p in prods] == [3, 2, 4, 1]  # rua 1, rua 13 (AAA, AAA), sem rua


def test_montar_html_autocontido_com_busca_e_legenda():
    dados = {"COTACAO": [_linha(15450, "OLEO SOJA SOYA 900ML", rua=13,
                                rotulo="A13 cons1", minimo="7 cx")]}
    html = relatorio.montar(relatorio.preparar(dados), "22/07/2026 06:00")
    assert "OLEO SOJA SOYA 900ML" in html
    assert "A13 cons1" in html
    assert "7 cx" in html
    assert "22/07/2026 06:00" in html
    assert 'id="busca"' in html
    assert "calculado com ruptura" in html      # legenda do *
    assert "http://" not in html and "https://" not in html  # sem dependencia externa


def test_montar_escapa_html_no_nome():
    dados = {"A<B": [_linha(1, "PRODUTO <script> & CIA")]}
    html = relatorio.montar(relatorio.preparar(dados), "x")
    # todo '<' do JSON embutido vira < -> nenhuma tag pode "vazar"
    assert "<script> & CIA" not in html
    assert "\\u003cscript> & CIA" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_relatorio.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'relatorio'`

- [ ] **Step 3: Write minimal implementation**

`src/relatorio.py` — pontos obrigatórios (código completo abaixo): dados embutidos como JSON num `<script>`, render em JS puro inline, busca que filtra a lista, tabela por fornecedor, marcas `*`/`novo`/`sem venda 6m`, legenda, mobile-first, zero URL externa. `json.dumps(..., ensure_ascii=False)` dentro de `<script>` precisa escapar `</` (usar `.replace("</", "<\\/")`).

```python
# -*- coding: utf-8 -*-
"""HTML unico da listagem: dados embutidos + JS inline (sem rede).

ARMADILHA conhecida (memoria do projeto): visualizador do WhatsApp nao
executa JavaScript — este arquivo e para abrir no NAVEGADOR."""
import html as _html
import json

import formato

COTACAO = "COTACAO"
SEM_FORNECEDOR = "SEM FORNECEDOR"
MARCAS_TXT = {"*": "*", "novo": "novo", "sem_venda": "sem venda 6m"}


def preparar(por_fornecedor):
    """dict {fornecedor: [linhas]} -> lista ordenada p/ o template."""
    def chave_forn(nome):
        if nome == COTACAO:
            return (0, "")
        if nome == SEM_FORNECEDOR:
            return (2, "")
        return (1, nome)

    saida = []
    for nome in sorted(por_fornecedor, key=chave_forn):
        produtos = sorted(por_fornecedor[nome],
                          key=lambda p: (formato.ordem_rua(p["rua"]),
                                         p["nome"]))
        saida.append({"nome": nome, "qtd": len(produtos),
                      "produtos": produtos})
    return saida


def montar(fornecedores, dados_de):
    dados = [{"nome": f["nome"], "qtd": f["qtd"],
              "produtos": [{"codigo": p["codigo"],
                            "nome": p["nome"],
                            "curva": p.get("curva") or "",
                            "rua": p.get("rua_rotulo") or "",
                            "minimo": p["minimo"],
                            "marca": MARCAS_TXT.get(p.get("marca") or "", "")}
                           for p in f["produtos"]]}
             for f in fornecedores]
    # todo '<' do JSON vira a sequencia backslash-u003c: nenhum
    # "</script>" nem tag alguma consegue escapar do blob embutido
    blob = json.dumps(dados, ensure_ascii=False).replace("<", "\\u003c")
    return _TEMPLATE.replace("__DADOS__", blob) \
                    .replace("__DADOS_DE__", _html.escape(dados_de))


_TEMPLATE = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Listagem por fornecedor</title>
<style>
 body{font-family:system-ui,Arial,sans-serif;margin:0;background:#f5f5f2;color:#222}
 header{position:sticky;top:0;background:#1a3c34;color:#fff;padding:10px 12px}
 header h1{font-size:16px;margin:0 0 6px}
 header small{opacity:.8}
 #busca{width:100%;box-sizing:border-box;padding:10px;font-size:16px;
        border:none;border-radius:6px;margin-top:6px}
 #lista button{display:block;width:100%;text-align:left;padding:12px;
        font-size:15px;border:none;border-bottom:1px solid #ddd;
        background:#fff;cursor:pointer}
 #lista button b{float:right;color:#666;font-weight:normal}
 #volta{margin:8px 12px;padding:8px 14px;font-size:14px}
 table{border-collapse:collapse;width:100%;background:#fff}
 th,td{padding:8px 10px;border-bottom:1px solid #e5e5e5;font-size:14px;
       text-align:left;vertical-align:top}
 th{background:#eee;position:sticky;top:0}
 td.num{text-align:right;white-space:nowrap}
 .marca{color:#b3541e;font-size:12px}
 footer{padding:10px 12px;color:#666;font-size:12px}
</style></head><body>
<header><h1>Listagem por fornecedor</h1>
<small>dados de __DADOS_DE__</small>
<input id="busca" type="search" placeholder="buscar fornecedor...">
</header>
<div id="lista"></div>
<div id="detalhe" style="display:none">
 <button id="volta">&larr; fornecedores</button>
 <h2 id="titulo" style="margin:4px 12px;font-size:16px"></h2>
 <table><thead><tr><th>c&oacute;digo</th><th>produto</th><th>curva</th>
 <th>corredor</th><th>est. m&iacute;nimo</th></tr></thead>
 <tbody id="corpo"></tbody></table>
</div>
<footer>* = calculado com ruptura (pode estar subestimado) &middot;
 novo = estimativa proporcional (produto recente) &middot;
 sem venda 6m = nenhuma venda no hist&oacute;rico</footer>
<script>
var DADOS = __DADOS__;
var lista = document.getElementById('lista'),
    det = document.getElementById('detalhe'),
    corpo = document.getElementById('corpo');
function esc(s){var d=document.createElement('div');
  d.appendChild(document.createTextNode(String(s)));return d.innerHTML;}
function renderLista(filtro){
  lista.innerHTML='';
  DADOS.forEach(function(f,i){
    if(filtro && f.nome.toUpperCase().indexOf(filtro.toUpperCase())<0)return;
    var b=document.createElement('button');
    b.innerHTML=esc(f.nome)+' <b>'+f.qtd+'</b>';
    b.onclick=function(){abrir(i);};
    lista.appendChild(b);});
}
function abrir(i){
  var f=DADOS[i];
  document.getElementById('titulo').textContent=f.nome+' — '+f.qtd+' produtos';
  corpo.innerHTML='';
  f.produtos.forEach(function(p){
    var tr=document.createElement('tr');
    tr.innerHTML='<td>'+esc(p.codigo)+'</td><td>'+esc(p.nome)+
      (p.marca?' <span class="marca">'+esc(p.marca)+'</span>':'')+
      '</td><td>'+esc(p.curva)+'</td><td>'+esc(p.rua)+
      '</td><td class="num">'+esc(p.minimo)+'</td>';
    corpo.appendChild(tr);});
  lista.style.display='none';det.style.display='block';
  window.scrollTo(0,0);
}
document.getElementById('volta').onclick=function(){
  det.style.display='none';lista.style.display='block';};
document.getElementById('busca').oninput=function(){renderLista(this.value);};
renderLista('');
</script></body></html>
"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_relatorio.py -v`
Expected: 4 passed. (Duas camadas de defesa contra HTML em nome de produto/fornecedor: o blob escapa todo `<` como a sequência backslash-u003c, e o `esc()` do JS escapa de novo na renderização.)

- [ ] **Step 5: Commit**

```bash
git add src/relatorio.py tests/test_relatorio.py
git commit -m "feat: relatorio HTML unico (busca, COTACAO primeiro, ordem por corredor)"
```

### Task 8: gerar.py (integração fim-a-fim) + .bat + README

**Files:**
- Create: `src/gerar.py`, `gerar-listagem.bat`, `README.md`
- Test: `tests/test_gerar.py`

**Interfaces:**
- Consumes: `fornecedor.atribuir` + `SEM_FORNECEDOR` (Task 4); `minimo.calcular` (Task 5); `formato.exibir/rotulo_rua` (Task 6); `relatorio.preparar/montar` (Task 7); CSVs da Task 3 (cabeçalhos exatos: `codigo;descricao;embalagem;curva;peso;ativo` · `codigo;descricao;data;qtd_vendida` · `codigo;data;fornecedor;qtd` · `codigo;fornecedor;dt_alteracao`); estado de ruas do depósito: JSON `{"15450": {"rua": 13, ...}}` (valor pode ser dict com chave `rua` OU int direto — ler defensivo).
- Produces: `python src/gerar.py [--config config.local.json]` → escreve `saida_html` atômico (tmp + `os.replace`); falha em qualquer insumo → exit 1 SEM tocar no HTML anterior.

- [ ] **Step 1: Write the failing test**

`tests/test_gerar.py`:

```python
# -*- coding: utf-8 -*-
"""Integracao fim-a-fim com CSVs sinteticos (formato exato do bridge)."""
import json
import os
import subprocess
import sys
from datetime import date, timedelta

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GERAR = os.path.join(RAIZ, "src", "gerar.py")


def _montar_insumos(tmp_path):
    hoje = date(2026, 7, 20)
    d = lambda n: (hoje - timedelta(days=n)).isoformat()  # noqa: E731
    (tmp_path / "catalogo.csv").write_text(
        "codigo;descricao;embalagem;curva;peso;ativo\n"
        "15450;OLEO SOJA SOYA 900ML;20;A;0;1\n"
        "222;QUEIJO MEIA CURA;;B;1;1\n"
        "333;PRODUTO INATIVO;10;C;0;0\n", encoding="utf-8")
    # 15450 vende 2/dia nos ultimos 180 dias -> mediana 90 un -> 5 cx
    vendas = "codigo;descricao;data;qtd_vendida\n"
    for n in range(180):
        vendas += f"15450;OLEO;{d(n)};2\n"
    vendas += f"222;QUEIJO;{d(1)};1.5\n"
    (tmp_path / "vendas.csv").write_text(vendas, encoding="utf-8")
    (tmp_path / "entradas.csv").write_text(
        "codigo;data;fornecedor;qtd\n"
        f"222;{d(5)};QUEIJOS DONA ROSA;30\n", encoding="utf-8")
    (tmp_path / "negociacao.csv").write_text(
        "codigo;fornecedor;dt_alteracao\n"
        "15450;COTACAO;\n"
        "15450;WAL MART;2026-05-01\n", encoding="utf-8")
    (tmp_path / "ruas.json").write_text(
        json.dumps({"15450": {"rua": 13, "quando": "x", "origem": "y"},
                    "222": 25}), encoding="utf-8")
    cfg = {"entrada": {
        "catalogo_csv": str(tmp_path / "catalogo.csv"),
        "vendas_csv": str(tmp_path / "vendas.csv"),
        "entradas_csv": str(tmp_path / "entradas.csv"),
        "negociacao_csv": str(tmp_path / "negociacao.csv"),
        "ruas_estado_json": str(tmp_path / "ruas.json")},
        "saida_html": str(tmp_path / "out" / "listagem.html")}
    caminho = tmp_path / "config.json"
    caminho.write_text(json.dumps(cfg), encoding="utf-8")
    return caminho, cfg


def _rodar(config):
    return subprocess.run([sys.executable, GERAR, "--config", str(config)],
                          capture_output=True, text=True)


def test_gera_html_com_tudo(tmp_path):
    config, cfg = _montar_insumos(tmp_path)
    r = _rodar(config)
    assert r.returncode == 0, r.stderr
    html = open(cfg["saida_html"], encoding="utf-8").read()
    assert "OLEO SOJA SOYA 900ML" in html
    assert "5 cx" in html            # 90 un / cx de 20 -> 4,5 -> teto 5
    assert "A13 cons1" in html       # rua como dict
    assert "A25 TERREO" in html      # rua como int direto
    assert "QUEIJOS DONA ROSA" in html
    assert "PRODUTO INATIVO" not in html
    assert "kg" in html              # 222 e de balanca


def test_falha_de_insumo_preserva_html_anterior(tmp_path):
    config, cfg = _montar_insumos(tmp_path)
    assert _rodar(config).returncode == 0
    antes = open(cfg["saida_html"], encoding="utf-8").read()
    os.remove(cfg["entrada"]["vendas_csv"])       # quebra um insumo
    r = _rodar(config)
    assert r.returncode == 1
    assert open(cfg["saida_html"], encoding="utf-8").read() == antes


def test_estado_de_ruas_ausente_nao_derruba(tmp_path):
    config, cfg = _montar_insumos(tmp_path)
    os.remove(cfg["entrada"]["ruas_estado_json"])
    r = _rodar(config)
    assert r.returncode == 0          # sem ruas = coluna corredor vazia
    assert "OLEO SOJA SOYA 900ML" in open(cfg["saida_html"],
                                          encoding="utf-8").read()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gerar.py -v`
Expected: FAIL — gerar.py não existe (`FileNotFoundError`/returncode != 0)

- [ ] **Step 3: Write minimal implementation**

`src/gerar.py`:

```python
# -*- coding: utf-8 -*-
"""Le os 4 CSVs do bridge + estado de ruas do deposito e escreve o HTML.

Manual por enquanto (decisao do dono 22/07: SEM tarefa agendada ate ele
validar os numeros). Falha de insumo -> exit 1 e o HTML anterior fica."""
import argparse
import csv
import json
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import formato      # noqa: E402
import fornecedor   # noqa: E402
import minimo       # noqa: E402
import relatorio    # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ler_csv(caminho):
    with open(caminho, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


def _ler_ruas(caminho):
    """Estado do deposito: {"15450": {"rua": 13, ...}} ou {"15450": 13}."""
    if not caminho or not os.path.exists(caminho):
        return {}
    with open(caminho, encoding="utf-8") as f:
        bruto = json.load(f)
    ruas = {}
    for cod, v in bruto.items():
        rua = v.get("rua") if isinstance(v, dict) else v
        if isinstance(rua, int):
            ruas[int(cod)] = rua
    return ruas


def main():
    ap = argparse.ArgumentParser(description="Listagem por fornecedor (HTML)")
    ap.add_argument("--config", default=os.path.join(RAIZ, "config.local.json"))
    args = ap.parse_args()
    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    ent = cfg["entrada"]

    cat = _ler_csv(ent["catalogo_csv"])
    vendas_rows = _ler_csv(ent["vendas_csv"])
    entradas = [{"codigo": int(r["codigo"]), "data": r["data"],
                 "fornecedor": r["fornecedor"], "qtd": float(r["qtd"])}
                for r in _ler_csv(ent["entradas_csv"])]
    negociacoes = [{"codigo": int(r["codigo"]), "fornecedor": r["fornecedor"],
                    "dt_alteracao": r["dt_alteracao"]}
                   for r in _ler_csv(ent["negociacao_csv"])]
    ruas = _ler_ruas(ent.get("ruas_estado_json"))

    vendas_por_cod = {}
    datas = []
    for r in vendas_rows:
        cod = int(r["codigo"])
        vendas_por_cod.setdefault(cod, {})[r["data"]] = \
            vendas_por_cod.get(cod, {}).get(r["data"], 0.0) + float(r["qtd_vendida"])
        datas.append(r["data"])
    fim = date.fromisoformat(max(datas)) if datas else date.today()

    mapa_forn = fornecedor.atribuir(negociacoes, entradas)

    por_fornecedor = {}
    for p in cat:
        if str(p.get("ativo")) != "1":
            continue
        cod = int(p["codigo"])
        unidades, marca = minimo.calcular(
            vendas_por_cod.get(cod, {}), fim, p.get("curva") or None)
        embalagem = float(p["embalagem"]) if p.get("embalagem") else None
        peso = str(p.get("peso")) == "1"
        rua = ruas.get(cod)
        linha = {"codigo": cod, "nome": p["descricao"],
                 "curva": p.get("curva") or "", "rua": rua,
                 "rua_rotulo": formato.rotulo_rua(rua),
                 "minimo": formato.exibir(unidades, embalagem, peso),
                 "marca": marca}
        nome_forn = mapa_forn.get(cod, fornecedor.SEM_FORNECEDOR)
        por_fornecedor.setdefault(nome_forn, []).append(linha)

    dados_de = datetime.fromtimestamp(
        os.path.getmtime(ent["vendas_csv"])).strftime("%d/%m/%Y %H:%M")
    html = relatorio.montar(relatorio.preparar(por_fornecedor), dados_de)

    destino = cfg["saida_html"]
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    tmp = destino + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, destino)
    print(f"OK: {destino} ({sum(len(v) for v in por_fornecedor.values())} "
          f"produtos, {len(por_fornecedor)} fornecedores, dados de {dados_de})")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:                      # noqa: BLE001
        print(f"[ERRO] listagem NAO gerada (a anterior fica): {e}",
              file=sys.stderr)
        sys.exit(1)
```

`gerar-listagem.bat` (na raiz do repo):

```bat
@echo off
cd /d "%~dp0"
python src\gerar.py %* >> saida\gerar.log 2>&1
if errorlevel 1 echo ERRO - veja saida\gerar.log & exit /b 1
echo OK - abra saida\listagem-fornecedores.html
```

(Antes do `python`: `if not exist saida mkdir saida` — acrescentar como primeira linha após o `cd`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -q`
Expected: TODOS os testes do repo verdes (Tasks 4-8).

- [ ] **Step 5: README.md**

```markdown
# listagem-fornecedor-atacaderj

Relatório HTML único: produtos por FORNECEDOR com código, nomenclatura,
curva, corredor (ruas do depósito) e estoque mínimo (mediana de janelas
rolantes de 45 dias; ruptura por curva A=10/B=20/C=30 dias sem venda).
Spec: docs/superpowers/specs/2026-07-22-listagem-fornecedor-design.md

## Como gerar (manual — SEM agendamento por enquanto, decisão do dono)

No PC-ponte:

1. `cd C:\Users\User\erp-bridge-atacaderj && git pull && python src\bridge.py --only listagem`
   (gera saida\listagem\*.csv — 4 arquivos)
2. `cd C:\Users\User\listagem-fornecedor-atacaderj && git pull && gerar-listagem.bat`
3. Abrir `saida\listagem-fornecedores.html` no navegador (PC ou celular).

Config: copie `config.example.json` -> `config.local.json`. O caminho
`ruas_estado_json` é o estado do deposito-atacaderj — confira o caminho real
no start do servidor de lá (parâmetro `estado_json`).

ARMADILHA: o visualizador do WhatsApp NÃO executa JavaScript — este HTML é
para abrir no navegador.
```

- [ ] **Step 6: Commit**

```bash
git add src/gerar.py tests/test_gerar.py gerar-listagem.bat README.md
git commit -m "feat: gerador fim-a-fim (CSVs bridge + ruas deposito -> HTML unico)"
```

### Task 9: Ensaio com dados REAIS no ponte (validação, sem agendar)

**Files:**
- Nenhum arquivo novo — ensaio operacional + ajustes que ele revelar.

**Interfaces:**
- Consumes: tudo das Tasks 1-8, já commitado (bridge com push; listagem precisa chegar ao ponte — ver Step 2).

- [ ] **Step 1: Bridge real no ponte**

```bash
ssh User@100.99.176.6 "cd C:\Users\User\erp-bridge-atacaderj && git pull && python src\bridge.py --only listagem"
```

Expected: 4 linhas `listagem/*.csv: N` com N reais (catálogo ~4-5 mil; negociação ~10 mil pares; vendas 180d = centenas de milhares de linhas — a query VENDAS com janela 180 pode levar mais que os ~8s habituais; se estourar timeout do ssh, rodar direto no ponte).

- [ ] **Step 2: Levar o repo listagem ao ponte**

O repo ainda não tem remote. Escolher com o dono: criar repo privado no GitHub (`gh repo create listagem-fornecedor-atacaderj --private --source . --push`, padrão dos outros) e `git clone` no ponte; OU copiar a pasta via scp. Registrar a escolha no README.

- [ ] **Step 3: Gerar com dados reais**

No ponte: copiar `config.example.json` → `config.local.json` (caminhos do example já são os do ponte; conferir o caminho real do estado de ruas no start do servidor do depósito) e rodar `gerar-listagem.bat`.
Expected: `OK - abra saida\listagem-fornecedores.html`.

- [ ] **Step 4: Conferência de sanidade com o dono (guiada)**

Abrir o HTML via Tailscale/celular e conferir juntos:
- óleo Soya 15450 está em COTACAO (e só lá);
- um produto de fornecedor conhecido (ex. RICLAN) caiu no fornecedor esperado;
- corredores batem com o app do depósito;
- 2-3 estoques mínimos fazem sentido de barriga (dono conhece o giro);
- contagem de SEM FORNECEDOR não é absurda (se >30% do catálogo, investigar).

- [ ] **Step 5: Registrar o resultado**

Atualizar o README (seção "Estado") com data do ensaio e pendências que o dono apontar. Commit + (se houver remote) push. **NÃO criar tarefa agendada** — fica para depois da validação do dono.

---

## Self-review (feita em 22/07)

- **Cobertura do spec:** Regra 1 → Task 4; Regra 2 (janelas/curva/casos-limite) → Task 5; conversão cx/un/kg → Task 6; layout/ordenação/marcas/legenda → Task 7; arquivo único + atômico + falha preserva anterior + "dados de" → Task 8; exports do bridge → Tasks 1-3; teste manual sem agendamento → Task 9. "Sem venda 6m" → coluna "—" com marca (Tasks 5/7/8). ✔
- **Placeholders:** nenhum TBD; todos os passos têm código/comando completo. Único ponto aberto de propósito: caminho real do `estado_json` do depósito no ponte (Task 9 Step 3 diz onde conferir) e a escolha GitHub × scp (Task 9 Step 2, decisão do dono). ✔
- **Consistência de tipos:** cabeçalhos de CSV idênticos entre Task 2 (escrita) e Task 8 (leitura, testes usam os mesmos); `(unidades, marca)` da Task 5 = consumo da Task 8; `rua_rotulo`/`minimo`/`marca` da Task 8 = contrato da Task 7; `SEM_FORNECEDOR` importado de `fornecedor` na Task 8 e literal idêntico em `relatorio.py`. ✔
