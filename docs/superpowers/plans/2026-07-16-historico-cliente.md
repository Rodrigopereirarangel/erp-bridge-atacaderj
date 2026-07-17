# Extração de Histórico de Cliente no Bridge — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar ao `erp-bridge-atacaderj` uma extração nova que grava
`historico_cliente.csv` — os itens dos pedidos de venda/DAV por cliente numa
janela longa (~24 meses) — insumo do app `recuperacao-itens-atacaderj`.

**Architecture:** Segue o padrão do bridge (queries → projeção atômica → wiring
em `bridge.py`, com `--demo` sem banco). Uma query nova reusa a cadeia de tabelas
já validada do `PEDIDOS_VENDA`; a projeção escreve o CSV; um novo alvo
`--only historico-cliente` dispara só esse bloco (é o que roda às 01:00).

**Tech Stack:** Python 3 (stdlib: `csv`, `json`), pyodbc (SQL Server 2014, via
`src/db.py` existente). Testes no estilo da casa: asserts diretos, sem pytest.

## Global Constraints

- Banco é **SÓ LEITURA**: apenas `SELECT`/`WITH` (trava em `src/db.py`). Nunca
  instalar nada no servidor `CONCENTRADOR`; tudo roda no PC-ponte.
- **Senha só em `config.local.json`** (gitignored). Nunca commitar senha/custo/preço.
- O `historico_cliente.csv` contém **nome de cliente + valores** → é gravado na
  pasta `data/input` do repo consumidor (gitignored lá), **nunca** versionado.
- Convenção de unidade herdada do `PEDIDOS_VENDA`: `vlPedidoItem`/`vlCusto` são
  **POR VOLUME**; a query já entrega `valor`/`custo` em **TOTAL da linha**
  (`vl * qtPedidoItem`) e `unidades = qtPedidoItem * qtEmbalagem`.
- Emissão do pedido de venda = **`dtAtendido`** (não `dtPedido`).

---

### Task 1: Query, demo, projeção e wiring do histórico de cliente

**Files:**
- Modify: `src/queries.py` (adicionar constante `HISTORICO_CLIENTE`)
- Modify: `src/demo_data.py` (adicionar `historico_cliente()`)
- Modify: `src/projections.py` (adicionar `historico_cliente_csv()`)
- Modify: `src/bridge.py` (coletar/escrever/main + `--only historico-cliente`)
- Modify: `config.example.json` (`historico_cliente_meses` + `saida.historico_cliente_csv`)
- Test: `tests_historico_cliente.py` (novo, na raiz, estilo asserts diretos)

**Interfaces:**
- Produces: `queries.HISTORICO_CLIENTE` (string com `{janela_meses}`),
  `demo_data.historico_cliente() -> list[dict]`,
  `projections.historico_cliente_csv(itens, caminho) -> int`.
- Cada linha bruta (dict) tem as chaves: `cliente, codigo, produto, data, emb,
  unidades_por_emb, qtde_emb, unidades, valor, custo` — `valor`/`custo` em TOTAL.

- [ ] **Step 1: Escrever o teste da projeção (falha)**

Criar `tests_historico_cliente.py`:

```python
# -*- coding: utf-8 -*-
"""Testes da projecao historico_cliente_csv (sem banco). Roda direto:
`python tests_historico_cliente.py` — asserts, imprime OK/FALHOU, exit 1 se falhar.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
import projections  # noqa: E402
import demo_data     # noqa: E402


def test_projecao_escreve_cabecalho_e_linhas():
    itens = [
        {"cliente": "MERCADO ZE", "codigo": 2411, "produto": "ARROZ 5KG",
         "data": "2026-05-12", "emb": "CX-20", "unidades_por_emb": 20,
         "qtde_emb": 2, "unidades": 40, "valor": 720.0, "custo": 560.0},
    ]
    with tempfile.TemporaryDirectory() as d:
        caminho = os.path.join(d, "historico_cliente.csv")
        n = projections.historico_cliente_csv(itens, caminho)
        assert n == 1, f"esperado 1 linha, veio {n}"
        with open(caminho, encoding="utf-8") as f:
            texto = f.read()
    linhas = texto.strip().splitlines()
    assert linhas[0] == ("cliente;codigo;produto;data;emb;unidades_por_emb;"
                         "qtde_emb;unidades;valor;custo"), linhas[0]
    assert linhas[1].startswith("MERCADO ZE;2411;ARROZ 5KG;2026-05-12;CX-20;20;"), linhas[1]


def test_demo_gera_clientes_e_itens():
    linhas = demo_data.historico_cliente()
    assert len(linhas) > 10, "demo deve ter historico suficiente p/ o motor testar"
    clientes = {r["cliente"] for r in linhas}
    assert len(clientes) >= 2, f"esperado >=2 clientes, veio {clientes}"
    # toda linha tem as chaves do contrato
    chaves = {"cliente", "codigo", "produto", "data", "emb", "unidades_por_emb",
              "qtde_emb", "unidades", "valor", "custo"}
    assert chaves <= set(linhas[0]), f"faltam chaves: {chaves - set(linhas[0])}"


def _run():
    falhas = 0
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {nome}")
            except AssertionError as e:
                falhas += 1
                print(f"FALHOU {nome}: {e}")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    _run()
```

- [ ] **Step 2: Rodar o teste e ver falhar**

Run: `python tests_historico_cliente.py`
Expected: FALHA — `AttributeError: module 'projections' has no attribute 'historico_cliente_csv'` (e `demo_data` sem `historico_cliente`).

- [ ] **Step 3: Adicionar a projeção**

Em `src/projections.py`, ao final (junto das outras projeções de CSV):

```python
def historico_cliente_csv(itens, caminho):
    """Uma linha por item de pedido de venda/DAV na janela longa (~24 meses),
    por cliente. Insumo do app recuperacao-itens-atacaderj (motor de analise).
    valor/custo ja em TOTAIS da linha (vlPedidoItem*qt, vlCusto*qt)."""
    cab = ["cliente", "codigo", "produto", "data", "emb", "unidades_por_emb",
           "qtde_emb", "unidades", "valor", "custo"]
    linhas = [[r["cliente"], r["codigo"], r["produto"], r["data"], r["emb"],
               r["unidades_por_emb"], r["qtde_emb"], r["unidades"],
               r["valor"], r["custo"]] for r in itens]
    _escrever_atomico(caminho, _csv_ponto_virgula(cab, linhas))
    return len(linhas)
```

- [ ] **Step 4: Adicionar o demo**

Em `src/demo_data.py`, ao final. Gera 2 clientes; MERCADO ZE **parou** o arroz e
**caiu** o açúcar; PADARIA mantém ritmo — casos que o motor vai exercitar:

```python
def historico_cliente(janela_meses=24):
    """Historico sintetico de pedidos de venda por cliente (~4 meses de dados,
    como o banco real hoje). MERCADO ZE: parou ARROZ (comprava quinzenal, sumiu
    ha ~2 meses) e caiu ACUCAR (de ~8cx/quinzena p/ 2cx). PADARIA: ritmo estavel."""
    hoje = date.today()

    def compra(cliente, cod, prod, dias_atras, emb, upe, qtde_emb, venda_un, custo_un):
        d = hoje - timedelta(days=dias_atras)
        unidades = qtde_emb * upe
        return {"cliente": cliente, "codigo": cod, "produto": prod,
                "data": d.isoformat(), "emb": emb, "unidades_por_emb": upe,
                "qtde_emb": qtde_emb, "unidades": unidades,
                "valor": round(unidades * venda_un, 2),
                "custo": round(unidades * custo_un, 2)}

    linhas = []
    # MERCADO ZE — ARROZ: comprava a cada ~15d entre 120 e 60 dias atras, e PAROU
    for k in (120, 104, 90, 74, 60):
        linhas.append(compra("MERCADO ZE", 2411, "ARROZ TIO JOAO 5KG", k,
                             "CX-20", 20, 2, 4.30, 3.30))
    # MERCADO ZE — ACUCAR: comprava ~8cx/quinzena e CAIU p/ 2cx nas ultimas semanas
    for k, q in [(120, 8), (105, 8), (90, 8), (75, 7), (30, 2), (15, 2)]:
        linhas.append(compra("MERCADO ZE", 3080, "ACUCAR GUARANI 1KG", k,
                             "FD-10", 10, q, 3.19, 2.60))
    # PADARIA SAO JOAO — OLEO: ritmo estavel a cada ~20d, ultima recente (em dia)
    for k in (110, 90, 70, 50, 30, 10):
        linhas.append(compra("PADARIA SAO JOAO", 4500, "OLEO SOJA LIZA 900ML", k,
                             "CX-20", 20, 3, 5.20, 4.40))
    return linhas
```

- [ ] **Step 5: Ligar no `bridge.py`**

Em `src/bridge.py`:

(a) No `coletar()`, ler a janela e a nova tabela. Trocar o retorno do demo e do banco para incluir `hc`:

```python
def coletar(cfg, usar_demo):
    """Devolve as tabelas brutas (agora 7), do banco ou do demo."""
    janela = cfg.get("janela_dias", 120)
    janela_ent = cfg.get("janela_entradas_dias", 180)
    janela_pv = cfg.get("janela_pedidos_venda_dias", 7)
    meses_vm = cfg.get("vendas_mensal_meses", 6)
    meses_hc = cfg.get("historico_cliente_meses", 24)
    if usar_demo:
        return (demo_data.catalogo(), demo_data.vendas(janela),
                demo_data.entradas(janela_ent), demo_data.pedidos(), [],
                demo_data.vendas_mensal(), demo_data.historico_cliente(meses_hc))

    import db
    conn = db.conectar(cfg["db"])
    try:
        cat = db.consultar(conn, queries.CATALOGO)
        ven = db.consultar(conn, queries.VENDAS.format(janela=int(janela)))
        ent = db.consultar(conn, queries.ENTRADAS.format(janela_entradas=int(janela_ent)))
        ped = db.consultar(conn, queries.PEDIDOS)
        pv = db.consultar(conn, queries.PEDIDOS_VENDA.format(janela_pedidos_venda=int(janela_pv)))
        vm = db.consultar(conn, queries.VENDAS_MENSAL.format(meses_fechados=int(meses_vm)))
        hc = db.consultar(conn, queries.HISTORICO_CLIENTE.format(janela_meses=int(meses_hc)))
    finally:
        conn.close()
    return cat, ven, ent, ped, pv, vm, hc
```

(b) Na assinatura de `escrever()`, receber `hc` e adicionar o bloco. Trocar a
linha `def escrever(cfg, cat, ven, ent, ped, pv, vm, alvo):` por
`def escrever(cfg, cat, ven, ent, ped, pv, vm, hc, alvo):` e, logo antes de
`return rel`, inserir:

```python
    if alvo in ("all", "historico-cliente"):
        caminho = saida.get("historico_cliente_csv") or os.path.join(
            RAIZ, "saida", "recuperacao", "historico_cliente.csv")
        n = projections.historico_cliente_csv(hc, caminho)
        rel.append(f"recuperacao/historico_cliente.csv: {n}")
```

(c) No `main()`, incluir `historico-cliente` nas escolhas do `--only` e passar `hc`:

```python
    ap.add_argument("--only", default="all",
                    choices=["all", "catalogo", "movimentos", "vendas", "entradas",
                             "recebimentos", "pedidos", "pedidos-venda",
                             "vendas-mensal", "historico-cliente"],
                    help="qual bloco gerar (default: all)")
```
e trocar as duas linhas da coleta/escrita por:
```python
        cat, ven, ent, ped, pv, vm, hc = coletar(cfg, args.demo)
        relatorio = escrever(cfg, cat, ven, ent, ped, pv, vm, hc, args.only)
```

- [ ] **Step 6: Adicionar a query**

Em `src/queries.py`, ao final. Reusa a cadeia do `PEDIDOS_VENDA` (validada
item-a-item), **uma linha por item de pedido**, janela em meses, valor/custo já
em TOTAL:

```python
# HISTORICO_CLIENTE: itens dos pedidos de venda/DAV (inEntrada=0, emissao =
# dtAtendido) numa janela LONGA (~24 meses -> hoje ~= desde marco/2026, que e o
# que o banco tem). Uma linha por item de pedido; valor/custo ja em TOTAL da
# linha (vl*qt) e unidades = qtPedidoItem*qtEmbalagem. Insumo do app
# recuperacao-itens-atacaderj. Mesma cadeia de tabelas do PEDIDOS_VENDA.
# OBS (a confirmar no schema): para restringir a clientes ATIVOS no cadastro,
# adicionar o predicado do flag de tbPessoa aqui (ver README do app). Sem ele,
# o universo e "clientes com pedido na janela", que ja e o conjunto ativo na
# pratica.
HISTORICO_CLIENTE = """
SELECT
    ps.nmPessoa                                AS cliente,
    i.cdProduto                                AS codigo,
    sp.nmProdutoPai                            AS produto,
    CAST(p.dtAtendido AS date)                 AS data,
    RTRIM(i.cdEmbalagem)
      + CASE WHEN i.qtEmbalagem > 1
             THEN '-' + CAST(CAST(i.qtEmbalagem AS int) AS varchar(10))
             ELSE '' END                       AS emb,
    CAST(i.qtEmbalagem AS int)                 AS unidades_por_emb,
    CAST(i.qtPedidoItem AS decimal(14,2))      AS qtde_emb,
    CAST(i.qtPedidoItem * i.qtEmbalagem AS decimal(14,3)) AS unidades,
    CAST(i.vlPedidoItem * i.qtPedidoItem AS decimal(14,2)) AS valor,
    CAST(i.vlCusto      * i.qtPedidoItem AS decimal(14,2)) AS custo
FROM dbo.tbPedido p
JOIN dbo.tbPedidoVenda pv  ON pv.cdPedidoVenda = p.cdPedido
                          AND pv.cdPessoaFilial = p.cdPessoaFilial
JOIN dbo.tbPedidoItem i    ON i.cdPedido = p.cdPedido
                          AND i.cdPessoaFilial = p.cdPessoaFilial
JOIN dbo.tbProduto pr      ON pr.cdProduto = i.cdProduto
JOIN dbo.tbSuperProduto sp ON sp.cdSuperProduto = pr.cdSuperProduto
JOIN dbo.tbPessoa ps       ON ps.cdPessoa = pv.cdPessoaComercial
WHERE p.inEntrada = 0
  AND p.dtAtendido >= DATEADD(month, -{janela_meses}, CAST(GETDATE() AS date))
ORDER BY cliente, codigo, data
"""
```

- [ ] **Step 7: Adicionar a config**

Em `config.example.json`: dentro do objeto raiz, ao lado de `vendas_mensal_meses`,
adicionar `"historico_cliente_meses": 24,` e, dentro de `"saida"`, adicionar a
linha (aponta para o `data/input` do repo consumidor, gitignored lá):

```json
    "historico_cliente_csv": "C:/Users/COMPUTADOR/recuperacao-itens-atacaderj/data/input/historico_cliente.csv",
```

- [ ] **Step 8: Rodar os testes e ver passar**

Run: `python tests_historico_cliente.py`
Expected: `OK test_demo_gera_clientes_e_itens` e `OK test_projecao_escreve_cabecalho_e_linhas`, exit 0.

- [ ] **Step 9: Smoke test do bridge em modo demo**

Run: `python src/bridge.py --demo --only historico-cliente`
Expected: `[OK] (demo) ... - recuperacao/historico_cliente.csv: 17` (17 linhas do
demo), gravado em `saida/recuperacao/historico_cliente.csv`. Conferir o
cabeçalho do arquivo bate com o contrato.

- [ ] **Step 10: Commit**

```bash
git add src/queries.py src/demo_data.py src/projections.py src/bridge.py config.example.json tests_historico_cliente.py
git commit -m "feat: extracao historico_cliente para o app de recuperacao de itens

Query HISTORICO_CLIENTE (pedidos de venda/DAV por cliente, ~24 meses,
uma linha por item, valor/custo em total) + projecao CSV + demo + wiring
--only historico-cliente. Insumo do recuperacao-itens-atacaderj.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

- **Cobertura da spec:** a spec pede "query nova `HISTORICO_CLIENTE` no bridge,
  janela ~24 meses, por cliente×produto×data, valor/custo/embalagem". Coberto
  (Steps 3–7). O flag de cliente ativo fica documentado como refinamento (comentário
  na query + Global Constraints do Plan B), não hardcodado — decisão consciente.
- **Placeholders:** nenhum passo com TBD; todo código está escrito.
- **Consistência de tipos:** o contrato de colunas (`cliente…custo`) é idêntico na
  query (Step 6), no demo (Step 4), na projeção (Step 3) e nos testes (Step 1). O
  app (Plan B) consome exatamente essas 10 colunas.

## Operação (fora do escopo de código; ver Plan B do app)

O job das **01:00** do app chama `python src/bridge.py --only historico-cliente`
antes de rodar o motor. O agendamento fica no `scripts/register-tasks.ps1` do
repo do app (Plan B, Task 10).

---

## Adendo (2026-07-16): coluna `grupo` para a capacidade "Ampliar a cesta"

O app ganhou a aba **Ampliar** (cross-sell por pares), que precisa do **grupo
mercadológico** de cada produto (BISCOITO, BEBIDA, DESCARTÁVEL…) — **NÃO** a
`tbClassificacaoProduto` (prateleira/localização física). Adicionar uma **11ª
coluna `grupo`** ao `historico_cliente.csv`. O app já lê `grupo` como **coluna
opcional** (se vier vazia, a aba Ampliar simplesmente não gera sugestões), então
esta mudança é aditiva e não quebra o consumidor.

**Passo A — confirmar o campo no schema (no ponte):**
`python src/inspect_schema.py grupo departamento secao mercadolog`
Achar a tabela/coluna do **grupo mercadológico** ligada a `tbSuperProduto`
(candidatos típicos do Solidcon: `cdGrupo`→`tbGrupo.nmGrupo`,
`cdDepartamento`→`tbDepartamento`, ou uma hierarquia `cdSecao`/`cdCategoria`).
Registrar o nome real encontrado.

**Passo B — query `HISTORICO_CLIENTE`:** adicionar a coluna e o LEFT JOIN
(exemplo assumindo `tbSuperProduto.cdGrupo` → `tbGrupo`; **trocar pelos nomes
confirmados no Passo A**):
```sql
    -- ...colunas existentes...
    RTRIM(gr.nmGrupo)                          AS grupo
-- ...
LEFT JOIN dbo.tbGrupo gr ON gr.cdGrupo = sp.cdGrupo   -- CONFIRMAR no schema
```
(fica antes do `ORDER BY`; `grupo` sai NULL/vazio para item sem grupo — ok.)

**Passo C — projeção:** em `historico_cliente_csv`, acrescentar `"grupo"` ao
final do `cab` e `r.get("grupo")` ao final de cada linha.

**Passo D — demo:** em `demo_data.historico_cliente`, acrescentar `"grupo"` a cada
dict (ex.: ARROZ/AÇÚCAR→`"MERCEARIA"`, itens de bebida→`"BEBIDA"`), para o
`--demo` exercitar o formato.

**Passo E — teste:** no `tests_historico_cliente.py`, o cabeçalho esperado passa a
terminar em `;grupo` e a checagem de chaves inclui `grupo`.

**Contrato atualizado:** 11 colunas — `cliente, codigo, produto, data, emb,
unidades_por_emb, qtde_emb, unidades, valor, custo, grupo`.
