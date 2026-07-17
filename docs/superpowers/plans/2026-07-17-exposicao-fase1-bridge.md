# Exposição MÍN/MÁX — Fase 1: o bridge exporta `vendas_canal` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer o `erp-bridge-atacaderj` exportar a venda diária por item **em unidades e separada por canal (salão × atacado)** — a base que hoje não existe em lugar nenhum e sem a qual o cálculo de MÍN/MÁX é impossível.

**Architecture:** Uma query T-SQL nova (`VENDAS_CANAL`) lê `DORSAL.tbCupom` + `tbCupomItem` (as únicas tabelas com o número do PDV), resolve o código de barras via `tbProdutoVenda` para converter caixa bipada em unidades, e classifica cada cupom em `salao`/`atacado`. Uma projeção nova escreve `vendas_canal.csv`; outra escreve `catalogo_exposicao.csv` (caixa-mãe + prateleira). Ambas entram no bridge sob um alvo novo `--only exposicao`, seguindo o mesmo padrão que `historico-cliente` já usa para extração pesada de agenda própria.

**Tech Stack:** Python 3.12, pyodbc, SQL Server 2014 (bancos `Solidcon` + `DORSAL`), pytest.

**Spec:** `docs/superpowers/specs/2026-07-17-exposicao-min-max-design.md` (§3, §4, D3–D8, D13)

## Global Constraints

- **O login do banco é SOMENTE LEITURA.** Só `SELECT`/`WITH`. `src/db.py` tem trava que recusa o resto. Nunca instalar nada no servidor `CONCENTRADOR`.
- **Nunca commitar senha, custo ou preço.** Segredo só em `config.local.json` (gitignored).
- **O ERP é Solidcon sobre SQL Server 2014**, não MySQL. Database conectado = `Solidcon`; `DORSAL` exige prefixo explícito (`DORSAL.dbo.tbCupom`).
- **A dev não alcança o banco.** Só o PC-ponte alcança (`ssh User@100.99.176.6`, chave `~/.ssh/id_ed25519_ponte`). Testes unitários rodam em qualquer máquina (não tocam o banco); a reconciliação real (Task 4) roda **no ponte**.
- **Convenção de testes deste repo:** só `tests/test_*.py` é coletado pelo pytest. Arquivos `tests_*.py` na raiz **não são coletados** — não seguir esse padrão.
- **CSV do repo:** separador `;`, UTF-8, `lineterminator="\n"`, escrita atômica. Use sempre `projections._escrever_atomico(caminho, projections._csv_ponto_virgula(cab, linhas))`.
- **Atualize `STATUS.md`** ao fim: marque o item e acrescente uma linha no "Log de progresso" com a data.

## ⚠️ Hazard de concorrência (ler antes de começar)

Em 17/07/2026 **outra sessão está commitando neste mesmo repo** (frente "dimensionamento de caixas/operadoras": `src/dim_erlang.py`, `tests/test_dim_erlang.py`) e mexe nos mesmos arquivos que esta fase toca (`src/queries.py`, `src/bridge.py`, `src/projections.py`, `config.example.json`). O repo também estava **6 commits à frente do origin** (push pendente).

**Antes da Task 1:** `git status` e `git pull --rebase`. **Depois da Task 5:** commit e **push imediato** — não deixe esta fase parada como WIP. Em 11/07/2026 um WIP não commitado neste repo derrubou a tarefa Movimentos 05:00 por dois dias sem ninguém ver.

**Todas as edições desta fase são aditivas** (funções novas, chaves novas de config, um alvo novo). Não renomeie nem reordene nada existente — é o que mantém o conflito trivial.

---

### Task 1: Query `VENDAS_CANAL`

**Files:**
- Modify: `src/queries.py` (acrescentar no fim, depois de `PEDIDOS`)
- Test: `tests/test_vendas_canal.py` (criar)

**Interfaces:**
- Produces: `queries.VENDAS_CANAL` — string T-SQL com dois campos de substituição: `{janela_exposicao}` (int, dias) e `{pdvs_atacado}` (lista de int já formatada como `11, 12`). Colunas devolvidas: `codigo` (int), `data` (date), `canal` (`'salao'`|`'atacado'`), `unidades` (decimal).

**Contexto que o implementador precisa saber (descoberto e validado em 17/07/2026):**

1. `Solidcon.tbVendaPDV` — a tabela que todo o resto do repo usa — **não tem coluna de PDV**. Por isso esta query não pode sair dela.
2. `DORSAL.tbCupomItem.cdProduto` vem **ora como código interno, ora como EAN de barras**. `Solidcon.tbProdutoVenda` mapeia `cdEAN → cdProduto` e carrega `qtVenda` = **quantas unidades aquele código de barras representa**. Exemplo real: produto `18464` (LEITE COND PIRACANJUBA) tem EAN `7898215152002` com `qtVenda=1` (unidade) e EAN `17898215152009` com `qtVenda=27` (a caixa). No atacado bipa-se a caixa. **Sem o `COALESCE`/multiplicação, uma caixa vira "1 unidade" e o giro sai 27× errado.**
3. `cdEmpresa = 10` é a empresa da loja em `tbProdutoVenda` (verificado).

- [ ] **Step 1: Write the failing test**

Crie `tests/test_vendas_canal.py`:

```python
# -*- coding: utf-8 -*-
"""A query VENDAS_CANAL e a unica base com PDV. Estes testes travam as 3
armadilhas que a fizeram existir (spec 2026-07-17, §3):
  - tbVendaPDV nao tem PDV  -> tem que sair do DORSAL
  - cdProduto do cupom pode ser EAN -> tem que resolver por tbProdutoVenda
  - EAN de caixa multiplica -> tem que multiplicar por qtVenda
Nao tocam o banco: validam a FORMA do SQL (a dev nao alcanca o ERP)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import queries  # noqa: E402


def _sql():
    return queries.VENDAS_CANAL.format(janela_exposicao=400, pdvs_atacado="11, 12")


def test_sai_do_dorsal_e_nao_do_tbvendapdv():
    sql = _sql()
    assert "DORSAL.dbo.tbCupom" in sql
    assert "DORSAL.dbo.tbCupomItem" in sql
    assert "tbVendaPDV" not in sql  # nao tem coluna de PDV


def test_resolve_ean_para_codigo_interno():
    sql = _sql()
    assert "tbProdutoVenda" in sql
    assert "pv.cdEAN = i.cdProduto" in sql
    assert "COALESCE(pv.cdProduto, i.cdProduto)" in sql


def test_multiplica_pelo_fator_do_ean():
    # sem isto, caixa bipada no atacado vira 1 unidade
    assert "i.qtItem * COALESCE(pv.qtVenda, 1)" in _sql()


def test_classifica_canal_pelos_pdvs_do_config():
    sql = queries.VENDAS_CANAL.format(janela_exposicao=400, pdvs_atacado="11, 12")
    assert "c.cdPDV IN (11, 12)" in sql
    assert "'atacado'" in sql and "'salao'" in sql


def test_janela_e_parametrizavel():
    assert "DATEADD(day, -30," in queries.VENDAS_CANAL.format(
        janela_exposicao=30, pdvs_atacado="11, 12")


def test_e_somente_leitura():
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
    import db  # noqa
    assert db._e_somente_leitura(_sql())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_vendas_canal.py -v`
Expected: FAIL — `AttributeError: module 'queries' has no attribute 'VENDAS_CANAL'`

- [ ] **Step 3: Write minimal implementation**

Acrescente no **fim** de `src/queries.py`:

```python
# VENDAS_CANAL: venda diaria por item em UNIDADES, separada por canal
# (salao x atacado). E a base do calculo de MIN/MAX de exposicao
# (spec 2026-07-17). Tres fatos do schema que ela existe para contornar,
# todos verificados em producao em 2026-07-17:
#
# 1. tbVendaPDV NAO TEM o numero do PDV. Nenhuma coluna. O PDV so existe
#    em DORSAL.tbCupom.cdPDV -> por isso esta query sai do DORSAL, e nao
#    da tabela que o resto do bridge usa.
# 2. tbCupomItem.cdProduto vem ora como codigo interno, ora como EAN de
#    barras. tbProdutoVenda mapeia cdEAN -> cdProduto.
# 3. Cada EAN carrega qtVenda = quantas UNIDADES ele representa. O
#    produto 18464 (LEITE COND PIRACANJUBA) tem EAN 7898215152002
#    (qtVenda=1, a unidade) e 17898215152009 (qtVenda=27, a CAIXA). No
#    atacado bipa-se a caixa: sem multiplicar por qtVenda, 1 caixa vira
#    "1 unidade" e o giro sai 27x errado.
#
# PROVA (2026-07-17): com a resolucao de EAN, o total desta query bate ao
# decimal com Solidcon.tbVendaPDV (a base oficial ja validada contra o
# consolidado do PDV): 23.406,68 / 22.293,31 / 39.474,89 unidades em
# 14, 15 e 16/07. O script scripts/verificar-reconciliacao-canal.py
# reproduz essa prova no ponte.
#
# Historico do DORSAL: desde 2026-01-22 (~150 dias uteis). Menor que o do
# tbVendaPDV (2023), mas e o unico que permite excluir o atacado — que e
# 44% do volume.
VENDAS_CANAL = """
SELECT
    COALESCE(pv.cdProduto, i.cdProduto)              AS codigo,
    CAST(c.dtCupom AS date)                          AS data,
    CASE WHEN c.cdPDV IN ({pdvs_atacado})
         THEN 'atacado' ELSE 'salao' END             AS canal,
    CAST(SUM(i.qtItem * COALESCE(pv.qtVenda, 1)) AS decimal(14,3)) AS unidades
FROM DORSAL.dbo.tbCupom c
JOIN DORSAL.dbo.tbCupomItem i ON i.gdCupom = c.gdCupom
LEFT JOIN dbo.tbProdutoVenda pv
       ON pv.cdEAN = i.cdProduto
      AND pv.cdEmpresa = 10          -- empresa da loja (verificado)
WHERE c.dtCupom >= DATEADD(day, -{janela_exposicao}, CAST(GETDATE() AS date))
GROUP BY COALESCE(pv.cdProduto, i.cdProduto),
         CAST(c.dtCupom AS date),
         CASE WHEN c.cdPDV IN ({pdvs_atacado})
              THEN 'atacado' ELSE 'salao' END
ORDER BY codigo, data, canal
"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_vendas_canal.py -v`
Expected: PASS — 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/queries.py tests/test_vendas_canal.py
git commit -m "feat(exposicao): query VENDAS_CANAL (venda por item/dia/canal em unidades)"
```

---

### Task 2: Projeções `vendas_canal_csv` e `catalogo_exposicao_csv`

**Files:**
- Modify: `src/projections.py` (acrescentar no fim)
- Modify: `src/demo_data.py` (acrescentar no fim)
- Test: `tests/test_exposicao_projections.py` (criar)

**Interfaces:**
- Consumes: nada de tasks anteriores (recebe listas de dict como as outras projeções).
- Produces:
  - `projections.vendas_canal_csv(vendas_canal: list[dict], caminho: str) -> int` — escreve `codigo;data;canal;unidades`, devolve nº de linhas.
  - `projections.catalogo_exposicao_csv(catalogo: list[dict], caminho: str) -> int` — escreve `codigo;descricao;caixa_mae;prateleira;curva`, devolve nº de linhas. Pula item sem `embalagem > 0`.
  - `demo_data.vendas_canal(janela_dias: int = 400) -> list[dict]` — dados falsos com as chaves `codigo`, `data`, `canal`, `unidades`.

**Contexto:** a caixa-mãe vem de `catalogo["embalagem"]` (que a query `CATALOGO` já traz de `VW_NEOGRID_PRODUTO_PRECO.QUANTIDADE_CAIXA`) e sai renomeada para `caixa_mae` no CSV — o nome que o repo consumidor usa. **É o cadastro, nunca a nota de entrada** (spec D7). Verificado em 17/07: existe para 100% dos 4.634 itens.

- [ ] **Step 1: Write the failing test**

Crie `tests/test_exposicao_projections.py`:

```python
# -*- coding: utf-8 -*-
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import demo_data    # noqa: E402
import projections  # noqa: E402


def _ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        return f.read()


def test_vendas_canal_csv_cabecalho_e_linhas():
    linhas = [
        {"codigo": 18464, "data": "2026-07-14", "canal": "salao", "unidades": 225.0},
        {"codigo": 18464, "data": "2026-07-14", "canal": "atacado", "unidades": 1462.0},
    ]
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "vendas_canal.csv")
        n = projections.vendas_canal_csv(linhas, caminho)
        assert n == 2
        txt = _ler(caminho)
        assert txt.splitlines()[0] == "codigo;data;canal;unidades"
        assert "18464;2026-07-14;salao;225.0" in txt
        assert "18464;2026-07-14;atacado;1462.0" in txt


def test_catalogo_exposicao_csv_renomeia_embalagem_para_caixa_mae():
    cat = [{"codigo": 34743, "descricao": "QUALY 500G", "embalagem": 12,
            "prateleira": "PRATELEIRA 33", "curva": "A"}]
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "catalogo_exposicao.csv")
        n = projections.catalogo_exposicao_csv(cat, caminho)
        assert n == 1
        txt = _ler(caminho)
        assert txt.splitlines()[0] == "codigo;descricao;caixa_mae;prateleira;curva"
        assert "34743;QUALY 500G;12;PRATELEIRA 33;A" in txt


def test_catalogo_exposicao_csv_pula_item_sem_caixa_mae():
    # sem caixa-mae o consumidor nao consegue arredondar: melhor faltar a
    # linha do que entregar um numero inventado
    cat = [
        {"codigo": 1, "descricao": "COM", "embalagem": 12, "prateleira": "P1", "curva": "A"},
        {"codigo": 2, "descricao": "SEM", "embalagem": None, "prateleira": "P1", "curva": "B"},
        {"codigo": 3, "descricao": "ZERO", "embalagem": 0, "prateleira": "P1", "curva": "C"},
    ]
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "c.csv")
        assert projections.catalogo_exposicao_csv(cat, caminho) == 1


def test_catalogo_exposicao_csv_aceita_prateleira_vazia():
    # item sem endereco fisico ainda recebe min/max; so nao agrupa
    cat = [{"codigo": 9, "descricao": "X", "embalagem": 6, "prateleira": None, "curva": None}]
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "c.csv")
        assert projections.catalogo_exposicao_csv(cat, caminho) == 1
        assert "9;X;6;;" in _ler(caminho)


def test_demo_data_vendas_canal_tem_os_dois_canais():
    linhas = demo_data.vendas_canal(30)
    assert linhas
    assert {"codigo", "data", "canal", "unidades"} <= set(linhas[0])
    canais = {r["canal"] for r in linhas}
    assert canais == {"salao", "atacado"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_exposicao_projections.py -v`
Expected: FAIL — `AttributeError: module 'projections' has no attribute 'vendas_canal_csv'`

- [ ] **Step 3: Write minimal implementation**

Acrescente no fim de `src/projections.py`:

```python
def vendas_canal_csv(vendas_canal, caminho):
    """Venda diaria por item em UNIDADES, separada por canal (salao x atacado).
    Base do calculo de MIN/MAX de exposicao (spec 2026-07-17).

    O canal ja vem resolvido da query (queries.VENDAS_CANAL): o consumidor
    nunca ve numero de PDV. Duas perguntas diferentes usam filtros diferentes
    deste mesmo arquivo — o giro da prateleira usa SO 'salao' (atacado nao sai
    da gondola), e o saldo de estoque usa OS DOIS (a caixa do atacado consome
    o mesmo estoque)."""
    cab = ["codigo", "data", "canal", "unidades"]
    linhas = [[r["codigo"], r["data"], r["canal"], r["unidades"]] for r in vendas_canal]
    _escrever_atomico(caminho, _csv_ponto_virgula(cab, linhas))
    return len(linhas)


def catalogo_exposicao_csv(catalogo, caminho):
    """Atributos que o calculo de exposicao precisa do cadastro.

    caixa_mae = catalogo["embalagem"] = VW_NEOGRID_PRODUTO_PRECO.QUANTIDADE_CAIXA.
    E o CADASTRO — nunca a nota de entrada (decisao do dono, spec D7): o
    calculo roda todo em unidades e so converte para caixa no ultimo passo.
    Item sem caixa-mae fica de fora: sem ela nao da para arredondar."""
    cab = ["codigo", "descricao", "caixa_mae", "prateleira", "curva"]
    linhas = []
    for r in catalogo:
        emb = r.get("embalagem")
        if not emb or float(emb) <= 0:
            continue
        linhas.append([
            r["codigo"],
            r.get("descricao"),
            int(float(emb)),
            str(r.get("prateleira") or "").strip(),
            r.get("curva"),
        ])
    _escrever_atomico(caminho, _csv_ponto_virgula(cab, linhas))
    return len(linhas)
```

Acrescente no fim de `src/demo_data.py`:

```python
def vendas_canal(janela_dias=400):
    """Venda por item/dia/canal falsa. Sabado pesa ~2x a segunda (como na loja
    real) e domingo nao vende — assim o --demo exercita o calendario e o fator
    de dia-da-semana do consumidor."""
    from datetime import date, timedelta
    hoje = date.today()
    itens = [(18464, 30.0), (34743, 8.0), (16416, 3.0), (42309, 0.05)]
    peso_dia = {0: 0.7, 1: 0.8, 2: 0.9, 3: 1.1, 4: 1.3, 5: 1.6}  # seg..sab
    linhas = []
    for d in range(janela_dias):
        dia = hoje - timedelta(days=d)
        if dia.weekday() == 6:  # domingo: loja fechada
            continue
        for cod, base in itens:
            un = round(base * peso_dia[dia.weekday()], 3)
            if un > 0:
                linhas.append({"codigo": cod, "data": dia.isoformat(),
                               "canal": "salao", "unidades": un})
            if cod in (18464, 34743) and d % 3 == 0:   # atacado e esporadico e grande
                linhas.append({"codigo": cod, "data": dia.isoformat(),
                               "canal": "atacado", "unidades": round(base * 20, 3)})
    return linhas
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_exposicao_projections.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/projections.py src/demo_data.py tests/test_exposicao_projections.py
git commit -m "feat(exposicao): projecoes vendas_canal_csv e catalogo_exposicao_csv + demo"
```

---

### Task 3: Ligar no `bridge.py` sob `--only exposicao`

**Files:**
- Modify: `src/bridge.py` (`coletar`, `escrever`, `main`)
- Modify: `config.example.json`
- Test: `tests/test_bridge_exposicao.py` (criar)

**Interfaces:**
- Consumes: `queries.VENDAS_CANAL` (Task 1); `projections.vendas_canal_csv`, `projections.catalogo_exposicao_csv`, `demo_data.vendas_canal` (Task 2).
- Produces: `python src/bridge.py --only exposicao` escreve `<saida.exposicao_dir>/vendas_canal.csv` e `<saida.exposicao_dir>/catalogo_exposicao.csv`.

**⚠️ O bug que este Task existe para não repetir.** Em 11/07/2026 alguém mudou a assinatura de uma função em `bridge.py` sem atualizar `projections.py`; a tarefa **Movimentos 05:00 falhou todo dia por 2 dias** e ninguém viu, porque a quebra era na última etapa do `escrever()`. `coletar()` devolve uma **tupla posicional** e `escrever()` a desempacota — acrescentar um elemento **exige** mexer nos dois, mais as duas chamadas do `main()`, mais o ramo `--demo`. O Step 1 trava exatamente isso com um teste ponta-a-ponta.

**Padrão a seguir:** `historico-cliente` já resolve o caso "extração pesada com agenda própria" (`quer_hc` / `so_hc`). Copie a forma: `exposicao` é mensal e tem janela longa (400 dias), então **não deve rodar** nos agendamentos de catálogo/movimentos, e o job mensal não deve pagar as outras queries.

- [ ] **Step 1: Write the failing test**

Crie `tests/test_bridge_exposicao.py`:

```python
# -*- coding: utf-8 -*-
"""--only exposicao ponta a ponta no modo demo.

Este teste existe por causa do incidente de 11/07/2026: coletar() devolve
uma tupla posicional que escrever() desempacota; quem acrescenta um
elemento e esquece um call site quebra o bridge silenciosamente, e a
tarefa agendada falha todo dia sem ninguem ver."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import bridge  # noqa: E402


def _cfg_demo(destino):
    cfg = json.load(open(os.path.join(RAIZ, "config.example.json"), encoding="utf-8"))
    cfg["saida"]["exposicao_dir"] = destino
    return cfg


def test_only_exposicao_escreve_os_dois_csvs():
    with tempfile.TemporaryDirectory() as d:
        cfg = _cfg_demo(d)
        dados = bridge.coletar(cfg, True, "exposicao")
        rel = bridge.escrever(cfg, *dados, alvo="exposicao")
        assert os.path.exists(os.path.join(d, "vendas_canal.csv"))
        assert os.path.exists(os.path.join(d, "catalogo_exposicao.csv"))
        assert any("vendas_canal.csv" in r for r in rel)
        assert any("catalogo_exposicao.csv" in r for r in rel)


def test_only_exposicao_nao_paga_as_outras_queries():
    # a janela e de 400 dias: nao pode rodar junto com catalogo/movimentos
    with tempfile.TemporaryDirectory() as d:
        cfg = _cfg_demo(d)
        cat, ven, ent, ped, pv, vm, hc, vc = bridge.coletar(cfg, True, "exposicao")
        assert vc, "vendas_canal deveria vir preenchido"
        assert ven == [] and ent == [] and ped == [] and pv == [] and vm == [] and hc == []


def test_movimentos_nao_paga_a_query_de_exposicao():
    with tempfile.TemporaryDirectory() as d:
        cfg = _cfg_demo(d)
        _, ven, _, _, _, _, _, vc = bridge.coletar(cfg, True, "movimentos")
        assert ven, "movimentos deveria trazer vendas"
        assert vc == [], "movimentos NAO deve pagar a janela de 400 dias da exposicao"


def test_demo_completo_nao_quebra():
    # a regressao do incidente de 11/07: --demo com alvo all tem que passar
    # por TODOS os call sites de escrever()
    with tempfile.TemporaryDirectory() as d:
        cfg = _cfg_demo(d)
        cfg["saida"]["cotacao_produtos_json"] = os.path.join(d, "produtos.json")
        cfg["saida"]["detector_salao_dir"] = os.path.join(d, "salao")
        cfg["saida"]["detector_estoque_dir"] = os.path.join(d, "estoque")
        cfg["saida"]["dashboard_dir"] = os.path.join(d, "dash")
        cfg["saida"]["upload_manual_dir"] = os.path.join(d, "up")
        cfg["saida"]["upload_manual_auditoria_dir"] = os.path.join(d, "upa")
        cfg["saida"]["historico_cliente_csv"] = os.path.join(d, "hc.csv")
        dados = bridge.coletar(cfg, True, "all")
        rel = bridge.escrever(cfg, *dados, alvo="all")
        assert any("vendas_canal.csv" in r for r in rel)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_bridge_exposicao.py -v`
Expected: FAIL — `ValueError: not enough values to unpack (expected 8, got 7)`

- [ ] **Step 3: Write minimal implementation**

**3a.** Em `src/bridge.py`, docstring do módulo — acrescente à lista de saídas, depois da linha `historico-cliente`:

```
  vendas-canal  -> exposicao/vendas_canal.csv + exposicao/catalogo_exposicao.csv
                   (venda por item/dia/canal em unidades + caixa-mae/prateleira;
                    base do calculo de MIN/MAX de exposicao — janela longa,
                    agenda MENSAL propria, como o historico-cliente)
```

E ao bloco de `Uso:`:

```
  python src/bridge.py --only exposicao      # base do MIN/MAX de exposicao (mensal)
```

**3b.** Substitua a função `coletar` inteira por:

```python
def coletar(cfg, usar_demo, alvo="all"):
    """Devolve as 8 tabelas brutas, do banco ou do demo. Duas sao condicionadas
    ao alvo porque tem janela longa e agenda propria: o historico de cliente
    (~24 meses de DAV) e a exposicao (~400 dias de cupom do DORSAL). Nenhuma
    das duas roda nos agendamentos de catalogo/movimentos — e vice-versa, os
    jobs delas nao pagam as outras queries."""
    janela = cfg.get("janela_dias", 120)
    janela_ent = cfg.get("janela_entradas_dias", 180)
    janela_pv = cfg.get("janela_pedidos_venda_dias", 7)
    meses_vm = cfg.get("vendas_mensal_meses", 6)
    meses_hc = cfg.get("historico_cliente_meses", 24)
    janela_exp = cfg.get("exposicao", {}).get("janela_dias", 400)
    pdvs_atacado = cfg.get("exposicao", {}).get("pdvs_atacado", [11, 12])
    quer_hc = alvo in ("all", "historico-cliente")
    quer_exp = alvo in ("all", "exposicao")
    so_hc = alvo == "historico-cliente"
    so_exp = alvo == "exposicao"
    leve = so_hc or so_exp          # alvos de janela longa: nao pagam o resto

    if usar_demo:
        vc = demo_data.vendas_canal(janela_exp) if quer_exp else []
        if leve:
            hc = demo_data.historico_cliente() if quer_hc else []
            cat = demo_data.catalogo() if quer_exp else []
            return cat, [], [], [], [], [], hc, vc
        return (demo_data.catalogo(), demo_data.vendas(janela),
                demo_data.entradas(janela_ent), demo_data.pedidos(), [],
                demo_data.vendas_mensal(),
                demo_data.historico_cliente() if quer_hc else [], vc)

    import db
    conn = db.conectar(cfg["db"])
    try:
        cat = ven = ent = ped = pv = vm = []
        # a exposicao precisa do catalogo (caixa-mae/prateleira), mas nao das
        # queries de movimento
        if so_exp:
            cat = db.consultar(conn, queries.CATALOGO)
        elif not so_hc:
            cat = db.consultar(conn, queries.CATALOGO)
            ven = db.consultar(conn, queries.VENDAS.format(janela=int(janela)))
            ent = db.consultar(conn, queries.ENTRADAS.format(janela_entradas=int(janela_ent)))
            ped = db.consultar(conn, queries.PEDIDOS)
            pv = db.consultar(conn, queries.PEDIDOS_VENDA.format(janela_pedidos_venda=int(janela_pv)))
            vm = db.consultar(conn, queries.VENDAS_MENSAL.format(meses_fechados=int(meses_vm)))
        hc = (db.consultar(conn, queries.HISTORICO_CLIENTE.format(historico_meses=int(meses_hc)))
              if quer_hc else [])
        vc = (db.consultar(conn, queries.VENDAS_CANAL.format(
                  janela_exposicao=int(janela_exp),
                  pdvs_atacado=", ".join(str(int(p)) for p in pdvs_atacado)))
              if quer_exp else [])
    finally:
        conn.close()
    return cat, ven, ent, ped, pv, vm, hc, vc
```

**3c.** Mude a assinatura de `escrever` (a linha `def escrever(...)`) para incluir `vc`:

```python
def escrever(cfg, cat, ven, ent, ped, pv, vm, hc, vc, alvo):
```

**3d.** Em `escrever`, acrescente **imediatamente antes** do bloco `if alvo in ("all", "movimentos", "vendas-mensal"):`

```python
    if alvo in ("all", "exposicao"):
        exp_dir = saida.get("exposicao_dir") or os.path.join(RAIZ, "saida", "exposicao")
        n = projections.vendas_canal_csv(vc, os.path.join(exp_dir, "vendas_canal.csv"))
        rel.append(f"exposicao/vendas_canal.csv: {n}")
        n = projections.catalogo_exposicao_csv(cat, os.path.join(exp_dir, "catalogo_exposicao.csv"))
        rel.append(f"exposicao/catalogo_exposicao.csv: {n}")
```

**3e.** Em `main()`, acrescente `"exposicao"` à lista `choices` do `--only`:

```python
    ap.add_argument("--only", default="all",
                    choices=["all", "catalogo", "movimentos", "vendas", "entradas", "recebimentos", "pedidos", "pedidos-venda", "vendas-mensal", "historico-cliente", "exposicao"],
                    help="qual bloco gerar (default: all)")
```

**3f.** Em `main()`, atualize as **duas** linhas que desempacotam/repassam:

```python
        cat, ven, ent, ped, pv, vm, hc, vc = coletar(cfg, args.demo, args.only)
        relatorio = escrever(cfg, cat, ven, ent, ped, pv, vm, hc, vc, args.only)
```

**3g.** Em `config.example.json`, acrescente depois do bloco `"marcas"`:

```json
  "exposicao": {
    "_comentario": "base do MIN/MAX de exposicao na prateleira (job MENSAL). janela_dias 400 = todo o historico do DORSAL (que so comeca em 2026-01-22). pdvs_atacado = PDVs cujas vendas NAO saem da prateleira (atacado): ficam fora do giro, mas contam no saldo de estoque.",
    "janela_dias": 400,
    "pdvs_atacado": [11, 12]
  },
```

e dentro do bloco `"saida"`, acrescente:

```json
    "exposicao_dir": "C:/Users/COMPUTADOR/erp-bridge-atacaderj/saida/exposicao",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_bridge_exposicao.py -v`
Expected: PASS — 4 passed

Rode a suíte inteira (a mudança de assinatura pode ter quebrado vizinho):

Run: `python -m pytest tests/ -v`
Expected: PASS — todos, incluindo `test_dim_erlang.py` e `test_robo_validacao.py`

E o smoke real do demo:

Run: `python src/bridge.py --demo --only exposicao`
Expected: `[OK] (demo) escrito em ...s:` com as linhas `exposicao/vendas_canal.csv: <n>` e `exposicao/catalogo_exposicao.csv: <n>`, ambos com n > 0

- [ ] **Step 5: Commit**

```bash
git add src/bridge.py config.example.json tests/test_bridge_exposicao.py
git commit -m "feat(exposicao): --only exposicao no bridge (vendas_canal + catalogo)"
```

---

### Task 4: Script de reconciliação (a prova, rodando no ponte)

**Files:**
- Create: `scripts/verificar-reconciliacao-canal.py`
- Test: manual, **no PC-ponte** (a dev não alcança o banco)

**Interfaces:**
- Consumes: `queries.VENDAS_CANAL` (Task 1), `src/db.py`.
- Produces: script executável que imprime a comparação e sai com código 0 (bate) ou 1 (não bate).

**Por que existe:** a spec (§3.4, §11) exige que a soma de `vendas_canal.csv` bata com `Solidcon.tbVendaPDV` — a base oficial já validada ao centavo contra o consolidado do PDV. Esse é o único teste que prova que a resolução de EAN está certa, e **ele não pode rodar no pytest** porque precisa do banco. Vira script, rodado no ponte a cada mudança na query.

- [ ] **Step 1: Escrever o script**

Crie `scripts/verificar-reconciliacao-canal.py`:

```python
# -*- coding: utf-8 -*-
"""PROVA de que VENDAS_CANAL esta correta: a soma das unidades por dia tem
que bater EXATO com Solidcon.tbVendaPDV (a base oficial, ja validada contra
o consolidado do PDV em DORSAL.tbConsVenda).

Se nao bater, a causa quase certa e a resolucao de EAN (tbProdutoVenda):
o cupom traz ora codigo interno, ora EAN, e cada EAN tem multiplicador.

Uso (NO PC-PONTE — a dev nao alcanca o banco):
  python scripts/verificar-reconciliacao-canal.py
  python scripts/verificar-reconciliacao-canal.py --dias 7
"""
import argparse
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
import db       # noqa: E402
import queries  # noqa: E402

TOLERANCIA = 0.001  # unidades: tem que bater ao decimal, nao "mais ou menos"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=3, help="dias a conferir (default 3)")
    ap.add_argument("--config", default=os.path.join(RAIZ, "config.local.json"))
    args = ap.parse_args()

    cfg = json.load(open(args.config, encoding="utf-8"))
    pdvs = cfg.get("exposicao", {}).get("pdvs_atacado", [11, 12])
    conn = db.conectar(cfg["db"])
    try:
        canal = db.consultar(conn, queries.VENDAS_CANAL.format(
            janela_exposicao=args.dias,
            pdvs_atacado=", ".join(str(int(p)) for p in pdvs)))
        oficial = db.consultar(conn, f"""
            SELECT CAST(v.dtVenda AS date) AS data,
                   CAST(SUM(v.qtVenda) AS decimal(14,3)) AS unidades
            FROM dbo.tbVendaPDV v
            WHERE v.dtVenda >= DATEADD(day, -{int(args.dias)}, CAST(GETDATE() AS date))
              AND v.cdProduto IS NOT NULL
            GROUP BY CAST(v.dtVenda AS date)
            ORDER BY data
        """)
    finally:
        conn.close()

    por_dia = {}
    for r in canal:
        por_dia[str(r["data"])] = por_dia.get(str(r["data"]), 0.0) + float(r["unidades"])

    print(f"{'dia':<12} {'VENDAS_CANAL':>14} {'tbVendaPDV':>14} {'dif':>10}")
    falhou = False
    for r in oficial:
        dia = str(r["data"])
        a, b = por_dia.get(dia, 0.0), float(r["unidades"])
        dif = a - b
        marca = "OK" if abs(dif) <= TOLERANCIA else "<<< NAO BATE"
        if abs(dif) > TOLERANCIA:
            falhou = True
        print(f"{dia:<12} {a:>14.3f} {b:>14.3f} {dif:>10.3f}  {marca}")

    # o motivo de tudo isto existir: quanto o atacado distorceria o giro
    salao = sum(float(r["unidades"]) for r in canal if r["canal"] == "salao")
    atacado = sum(float(r["unidades"]) for r in canal if r["canal"] == "atacado")
    print(f"\nsalao   : {salao:12.1f} un")
    print(f"atacado : {atacado:12.1f} un  ({atacado / (salao + atacado) * 100:.1f}% do volume)")
    if salao:
        print(f"incluir o atacado inflaria o giro em {atacado / salao * 100:.0f}%")

    if falhou:
        print("\n[FALHOU] A resolucao de EAN esta errada. NAO use esta base.", file=sys.stderr)
        sys.exit(1)
    print("\n[OK] Reconciliacao exata: a base esta correta.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Rodar no ponte e conferir**

Run (da dev):
```bash
ssh -i ~/.ssh/id_ed25519_ponte User@100.99.176.6 "cd C:\Users\User\erp-bridge-atacaderj && git pull && python scripts\verificar-reconciliacao-canal.py --dias 3"
```
Expected: uma linha `OK` por dia, `[OK] Reconciliacao exata`, exit 0, e o atacado em torno de **40–45% do volume**.

Se sair `NAO BATE`: **pare**. A query está errada; não siga para a Fase 2 com base furada.

- [ ] **Step 3: Rodar a extração real no ponte**

Run:
```bash
ssh -i ~/.ssh/id_ed25519_ponte User@100.99.176.6 "cd C:\Users\User\erp-bridge-atacaderj && python src\bridge.py --only exposicao"
```
Expected: `exposicao/vendas_canal.csv: <n>` com n na casa das centenas de milhares, e `exposicao/catalogo_exposicao.csv: ~4634`

- [ ] **Step 4: Commit**

```bash
git add scripts/verificar-reconciliacao-canal.py
git commit -m "test(exposicao): script de reconciliacao VENDAS_CANAL x tbVendaPDV (roda no ponte)"
```

---

### Task 5: Script de diagnóstico "caixa-mãe suspeita" (D17, spec §8.1)

**Files:**
- Create: `scripts/cadastro-caixa-mae-suspeito.py`
- Test: manual, **no PC-ponte**

**Interfaces:**
- Consumes: `src/db.py`.
- Produces: script que escreve `saida/exposicao/cadastro_caixa_mae_suspeito.csv` com
  `codigo;descricao;caixa_cadastro;caixa_nota;vezes_que_chegou_assim` e imprime o resumo.

**Por que existe e por que é script, não pipeline (spec §8.1):** o dono pediu ver, no primeiro
teste, os itens onde o cadastro da caixa-mãe é duvidoso. É a **única** coisa no projeto que olha a
nota de entrada — o cálculo em si nunca a usa (D7). Uso pontual ⇒ script, não estágio mensal.

**A lógica do desempate (medida em 17/07/2026, não invente outra):** três fontes do ERP dizem
quantas unidades tem na caixa e **discordam**. A nota (`tbNotaItem.qtEmbalagem`) diz `1` em 1.291
itens porque o fornecedor faturou **em unidade** — isso **não é opinião sobre caixa**, é ausência
de opinião, e por isso `qtEmbalagem = 1` **tem que ser filtrado fora**. Quando a nota diz `> 1`,
ela é testemunha: nesse recorte ela confirma o cadastro Neogrid **933 vezes** contra 240 do EAN —
foi assim que o cadastro ganhou o posto de fonte (D7). Sobram **30 itens** em que a nota fala de
caixa de verdade e mesmo assim discorda do cadastro. São esses os 30.

- [ ] **Step 1: Escrever o script**

Crie `scripts/cadastro-caixa-mae-suspeito.py`:

```python
# -*- coding: utf-8 -*-
"""DIAGNOSTICO (spec 2026-07-17 §8.1 / D17): itens cuja caixa-mae cadastrada
e duvidosa.

NAO altera calculo nenhum. O MIN/MAX usa SEMPRE o cadastro (decisao do dono,
D7); este script so mostra onde o cadastro cheira mal, p/ o dono consertar no
ERP.

Criterio (medido em 17/07/2026):
  - A nota de entrada so vale como testemunha quando qtEmbalagem > 1. Em 1.291
    itens ela diz 1 porque o fornecedor faturou EM UNIDADE — ausencia de
    opiniao, nao discordancia. Ex.: QUALY 500G vem com nota=1, mas a caixa
    tem 12 (confirmado pelo dono).
  - Nesse recorte, a nota confirma o cadastro 933x contra 240 do EAN -> o
    cadastro e a fonte (D7).
  - Sobram ~30 itens onde a nota fala de caixa real e discorda do cadastro.
    Ex.: TAPIOCA ROSA 500G cadastro=50 nota=5 (chegou 5x assim);
         FOFURA REQUEIJAO 60G C10 cadastro=1 (!) nota=10.
  - 23 dos 30 tem a nota MENOR que o cadastro — a direcao que superexpoe a
    prateleira (mais mercadoria parada = a avaria/validade que o MAX combate).

Uso (NO PC-PONTE):
  python scripts/cadastro-caixa-mae-suspeito.py
"""
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
import db           # noqa: E402
import projections  # noqa: E402

SQL = """
WITH nota AS (
    SELECT codigo, caixa_nota, entradas FROM (
        SELECT i.cdProduto AS codigo, i.qtEmbalagem AS caixa_nota,
               COUNT(*) AS entradas,
               ROW_NUMBER() OVER (PARTITION BY i.cdProduto
                                  ORDER BY COUNT(*) DESC, i.qtEmbalagem DESC) AS rn
        FROM dbo.tbNotaItem i
        JOIN dbo.tbNotaEntrada ne
          ON ne.cdNotaEntrada = i.cdNota AND ne.cdPessoaFilial = i.cdPessoaFilial
        WHERE ne.dtChegada >= DATEADD(month, -12, CAST(GETDATE() AS date))
          AND i.qtEmbalagem > 1        -- SO nota informativa: =1 e faturamento em unidade
          AND i.cdProduto IS NOT NULL
        GROUP BY i.cdProduto, i.qtEmbalagem
    ) t WHERE rn = 1
), cadastro AS (
    SELECT SEQPRODUTO AS codigo, MAX(QUANTIDADE_CAIXA) AS caixa_cadastro
    FROM dbo.VW_NEOGRID_PRODUTO_PRECO WHERE SEQLOJA = 1 GROUP BY SEQPRODUTO
)
SELECT c.codigo, sp.nmProdutoPai AS descricao,
       CAST(c.caixa_cadastro AS int) AS caixa_cadastro,
       CAST(n.caixa_nota AS int)     AS caixa_nota,
       n.entradas                    AS vezes_que_chegou_assim
FROM cadastro c
JOIN nota n ON n.codigo = c.codigo
LEFT JOIN dbo.tbProduto p       ON p.cdProduto = c.codigo
LEFT JOIN dbo.tbSuperProduto sp ON sp.cdSuperProduto = p.cdSuperProduto
WHERE n.caixa_nota <> c.caixa_cadastro
ORDER BY n.entradas DESC, c.codigo
"""


def main():
    cfg = json.load(open(os.path.join(RAIZ, "config.local.json"), encoding="utf-8"))
    conn = db.conectar(cfg["db"])
    try:
        linhas = db.consultar(conn, SQL)
    finally:
        conn.close()

    exp_dir = cfg["saida"].get("exposicao_dir") or os.path.join(RAIZ, "saida", "exposicao")
    caminho = os.path.join(exp_dir, "cadastro_caixa_mae_suspeito.csv")
    cab = ["codigo", "descricao", "caixa_cadastro", "caixa_nota", "vezes_que_chegou_assim"]
    projections._escrever_atomico(caminho, projections._csv_ponto_virgula(
        cab, [[r["codigo"], r["descricao"], r["caixa_cadastro"],
               r["caixa_nota"], r["vezes_que_chegou_assim"]] for r in linhas]))

    menor = sum(1 for r in linhas if r["caixa_nota"] < r["caixa_cadastro"])
    print(f"{len(linhas)} itens com caixa-mae suspeita -> {caminho}")
    print(f"  {menor} tem a nota MENOR que o cadastro (direcao que SUPEREXPOE a prateleira)\n")
    print(f"{'codigo':>8} {'cadastro':>9} {'nota':>6} {'vezes':>6}  descricao")
    for r in linhas[:30]:
        print(f"{r['codigo']:>8} {r['caixa_cadastro']:>9} {r['caixa_nota']:>6} "
              f"{r['vezes_que_chegou_assim']:>6}  {r['descricao']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Rodar no ponte**

Run:
```bash
ssh -i ~/.ssh/id_ed25519_ponte User@100.99.176.6 "cd C:\Users\User\erp-bridge-atacaderj && git pull && python scripts\cadastro-caixa-mae-suspeito.py"
```
Expected: cerca de **30 itens**, com ~23 tendo a nota menor que o cadastro. `TAPIOCA ROSA 500G`
(cadastro 50, nota 5, 7×) e `FOFURA REQUEIJAO 60G C10` (cadastro 1, nota 10) devem aparecer.

Se vierem centenas de itens: o filtro `qtEmbalagem > 1` caiu — sem ele, os ~1.291 casos de
faturamento em unidade entram como falso conflito.

- [ ] **Step 3: Entregar a lista ao dono**

Mande o `cadastro_caixa_mae_suspeito.csv` para o dono (D17: ele pediu para analisar). Não conserte
cadastro por conta própria — o conserto é no ERP e é decisão dele.

- [ ] **Step 4: Commit**

```bash
git add scripts/cadastro-caixa-mae-suspeito.py
git commit -m "feat(exposicao): script de diagnostico da caixa-mae suspeita (D17)"
```

---

### Task 6: Agendar no ponte, STATUS e push

**Files:**
- Modify: `STATUS.md`
- Test: manual (Agendador de Tarefas do Windows)

**Interfaces:**
- Consumes: `--only exposicao` (Task 3), validado pela Task 4.
- Produces: tarefa agendada `AtacadeRJ - Exposicao Mensal` no PC-ponte.

- [ ] **Step 1: Registrar a tarefa mensal no ponte**

A extração é mensal (dia 1, 04:00 — antes do Movimentos das 05:00, para não disputar o banco).

Run:
```bash
ssh -i ~/.ssh/id_ed25519_ponte User@100.99.176.6 "schtasks /Create /TN \"AtacadeRJ - Exposicao Mensal\" /TR \"python C:\Users\User\erp-bridge-atacaderj\src\bridge.py --only exposicao\" /SC MONTHLY /D 1 /ST 04:00 /F"
```
Expected: `SUCCESS: The scheduled task "AtacadeRJ - Exposicao Mensal" has successfully been created.`

- [ ] **Step 2: Testar a tarefa agendada de verdade**

Run:
```bash
ssh -i ~/.ssh/id_ed25519_ponte User@100.99.176.6 "schtasks /Run /TN \"AtacadeRJ - Exposicao Mensal\" && timeout /t 90 && schtasks /Query /TN \"AtacadeRJ - Exposicao Mensal\" /FO LIST | findstr /C:\"Last Result\""
```
Expected: `Last Result: 0`

Qualquer outro valor = a tarefa não roda. Investigue antes de seguir (é exatamente assim que a Movimentos ficou quebrada 2 dias em 11/07 sem ninguém ver).

- [ ] **Step 3: Atualizar o STATUS.md**

Acrescente ao "Log de progresso" (mantenha o formato das linhas vizinhas):

```markdown
- 2026-07-17: **Fase 1 da exposicao MIN/MAX no ar.** Query `VENDAS_CANAL`
  (DORSAL.tbCupom + tbCupomItem + resolucao de EAN por tbProdutoVenda) ->
  `saida/exposicao/vendas_canal.csv` (venda por item/dia/canal em unidades) e
  `catalogo_exposicao.csv` (caixa-mae do cadastro + prateleira). Alvo novo
  `--only exposicao`, tarefa `AtacadeRJ - Exposicao Mensal` (dia 1, 04:00,
  LastTaskResult 0). Reconciliacao exata com tbVendaPDV conferida no ponte por
  `scripts/verificar-reconciliacao-canal.py`. Descoberta que motivou tudo:
  `tbVendaPDV` NAO tem o numero do PDV, e o cupom do DORSAL traz o produto ora
  como codigo interno ora como EAN (com multiplicador de caixa). Atacado (PDV
  11/12) = ~44% do volume. Spec: `docs/superpowers/specs/2026-07-17-exposicao-min-max-design.md`.
  Proximo: Fase 2 (repo `exposicao-atacaderj`).
```

- [ ] **Step 4: Commit e PUSH (não deixe WIP)**

```bash
git add STATUS.md
git commit -m "docs: STATUS - fase 1 da exposicao MIN/MAX no ar"
git push
```

Expected: push aceito. **Se o push falhar, resolva agora** — o repo é a memória do projeto e a sessão do ponte lê de lá.

- [ ] **Step 5: Sincronizar o ponte**

Run:
```bash
ssh -i ~/.ssh/id_ed25519_ponte User@100.99.176.6 "cd C:\Users\User\erp-bridge-atacaderj && git pull && git status --short"
```
Expected: `Already up to date.` ou o merge limpo, e `git status --short` **vazio** (nenhum WIP pendurado lá).

---

## Definição de pronto (Fase 1)

- [ ] `python -m pytest tests/ -v` passa inteiro na dev
- [ ] `python src/bridge.py --demo --only exposicao` gera os 2 CSVs
- [ ] `scripts/verificar-reconciliacao-canal.py` sai `[OK] Reconciliacao exata` **no ponte**
- [ ] `saida/exposicao/vendas_canal.csv` existe no ponte com dados reais
- [ ] `scripts/cadastro-caixa-mae-suspeito.py` rodou e a lista (~30) foi entregue ao dono
- [ ] Tarefa `AtacadeRJ - Exposicao Mensal` com `Last Result: 0`
- [ ] `STATUS.md` atualizado, commitado **e pushado**
- [ ] `git status --short` vazio na dev **e** no ponte

**A Fase 2 não começa antes disto tudo.** Se a reconciliação não bater, a base está furada e todo
o modelo da Fase 2 seria construído sobre número errado.
