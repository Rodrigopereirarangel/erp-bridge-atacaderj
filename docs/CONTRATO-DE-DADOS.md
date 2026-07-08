# Contrato de Dados — erp-bridge-atacaderj

Este é o documento que a gente preenche **junto**. Ele diz, para cada sistema
consumidor: **qual arquivo** ele lê, **quais colunas** espera e **de onde no ERP**
esse dado vem. A coluna "origem no ERP" é o único ponto em aberto — é o que você
me passa (nome real da tabela/coluna) para eu finalizar os `SELECT`s.

Convenção: o extrator puxa uma **camada bruta** (nomes canônicos abaixo) e a
**camada de projeção** escreve o formato exato que cada consumidor já espera.
Assim o mapeamento do ERP fica **num lugar só** (`src/queries.py`).

---

## Camada bruta (o que os SELECTs devem devolver)

| Extração | Colunas canônicas (devolvidas pelo SQL) | Cadência |
|---|---|---|
| **catalogo**     | `codigo, descricao, embalagem(opc), custo_atual, preco_atacado, preco_varejo, preco_promocao, curva, ativo` | 3–5x/dia |
| **vendas**       | `codigo, descricao, data, qtd_vendida, valor, custo_venda` (últimos `janela_dias`, dia a dia) | diário (05:00) |
| **entradas**     | `codigo, data, qtd` — **todas** as entregas dos últimos ~6 meses (`janela_entradas_dias`) | diário (05:00) |
| **pedidos**      | `codigo, data_pedido, qtd_pedida, status, previsao_entrega` (só abertos) | diário (05:00) |

> **Entrada = proxy de estoque (definição do usuário):** o ERP não tem saldo, então
> puxamos **todas as entregas de ~6 meses** e o detector cruza **giro × últimas
> entregas** para estimar a cobertura restante. Do mesmo dado deriva-se o
> `recebimentos.csv` (a **última** entrega por item) que o detector de salão já lê.

> **Dois custos (definição do usuário):** `custo_atual` vem do **cadastro** (custo de
> hoje → cotação/pricing decidem com ele); `custo_venda` vem do **item do pedido**
> (custo **congelado no dia da venda** → margem realizada correta no BI/priorização).
> `categoria`/`fornecedor` foram **removidos** (não usados).

> **Origem no ERP — PREENCHIDA (2026-07-07)**. ERP = **Solidcon / SQL Server 2014**,
> database `Solidcon`, loja = filial 1 / SEQLOJA 1:
>
> | Dado | Origem real |
> |---|---|
> | Cadastro de produtos | `tbProduto` (código) + **`tbSuperProduto.nmProdutoPai`** (nome — `nmProduto` é NULL no banco inteiro; 1:1 via `cdSuperProduto`) |
> | Preços atacado/varejo/promoção + qtd caixa | **`VW_NEOGRID_PRODUTO_PRECO`** (view que o ERP mantém p/ integradores): `PRECO_ATACADO`, `PRECO_NORMAL`, `PRECO_PROMOCAO`, `QUANTIDADE_CAIXA`. ⚠️ 1 linha POR EMBALAGEM → pegar a linha da maior caixa (ROW_NUMBER) |
> | Custo atual + curva ABC | `CUSTO_ULTIMA_ENTRADA` (mesma view; é a base da margem do ERP) + `VW_NEOGRID_PRODUTO_ESTOQUE.CURVA_ABC` (`'X'` = sem curva → NULL) |
> | Vendas (dia × produto, R$ e CMV) | **`tbVendaPDV`** (1 linha por produto/cupom; desde 2023): `vlVenda`/`vlCusto` são **unitários** → `SUM(qt*vl)`. Prova: bate ao centavo com `DORSAL.tbConsVenda` |
> | Entradas/recebimentos | `tbNotaItem` + `tbNotaEntrada.dtChegada` (`cdNotaEntrada = tbNota.cdNota`). ⚠️ `qtItemNota` vem em **VOLUMES** → unidades = `× qtEmbalagem` |
> | Pedidos de compra abertos | `tbPedido` (`inEntrada=1`, aberto = `dtAtendido IS NULL`) + `tbPedidoItem` (`qtPedidoItem` em volumes) + `tbPedidoCompra.dtEntregaPrevista` (`cdPedidoCompra = cdPedido`) |
> | Unidades | venda do PDV em **unidades**; entradas/pedidos em volumes ×`qtEmbalagem` → tudo sai em **unidades** nos CSVs |
>
> **Descoberta**: o ERP até tem saldo (`tbEstoqueFisico`), mas está negativo em
> vários itens (implantação out/2025) → o **proxy por entradas continua sendo o
> desenho certo**.

---

## Consumidor 1 — Cotação (HTML)  ·  arquivo: `produtos.json`

O HTML oficial usa um catálogo com **chaves compactas**. A projeção escreve:

```json
{
  "gerado_em": "2026-06-30 05:02:11",
  "total": 1234,
  "produtos": [
    { "c": "2411", "p": "KELLOGGS SUCRILHOS 240G", "q": 12,
      "v": 18.90, "vu": 22.50, "vp": 16.90, "custo": 14.20, "cv": "A" }
  ]
}
```

| Chave | Origem canônica | Significado |
|---|---|---|
| `c`     | `codigo`          | código interno |
| `p`     | `descricao`       | descrição |
| `q`     | `embalagem`       | qtd por embalagem (fator) — **opcional** |
| `v`     | `preco_atacado`   | **preço atacado** (base) |
| `vu`    | `preco_varejo`    | **preço varejo** (unitário) |
| `vp`    | `preco_promocao`  | **preço promoção** (guardado no ERP) |
| `custo` | `custo_atual`     | custo corrente (piso de margem / limite de desconto) |
| `cv`    | `curva`           | curva ABC |

> **Como o app recebe o catálogo (design 2026-07-07):** o app roda como **artifact
> no claude.ai**; o bridge gera o **`catalogo_bridge.json`** (arquivo único com
> `gerado_em` + produtos `c,p,q,v,vu,custo,cv`; promo vence: `v = promoção` quando
> menor) e um **robô agendado** o sobe pelo botão "📦 Catálogo" do app → storage
> compartilhado. Ver `superpowers/specs/2026-07-07-estrutura-acesso-cotacao-design.md`.

---

## Consumidor 2 — Detector de Ruptura **de Salão** (reabastecimento)

Repo: `detector-ruptura-atacaderj`  ·  pasta: `data/input/`  ·  separador `;`

`vendas.csv`
```
codigo;descricao;data;qtd_vendida
```
`recebimentos.csv`  (data + volume da última entrega)
```
codigo;data_ultimo_recebimento;qtd_recebida
```

---

## Consumidor 3 — Detector de Ruptura **de Estoque** (comprar)

Repo: `detector-ruptura-estoque-atacaderj`  ·  pasta: `data/input/`  ·  separador `;`

`vendas.csv`  (**com valor R$ e custo do dia**)
```
codigo;descricao;data;qtd_vendida;valor;custo_venda
```
`recebimentos.csv`
```
codigo;data_ultimo_recebimento;qtd_recebida
```
`entradas.csv`  (**todas** as entregas dos últimos ~6 meses — proxy de estoque)
```
codigo;data;qtd
```
`pedidos.csv`  (pedidos abertos de fornecedor)
```
codigo;data_pedido;qtd_pedida;status;previsao_entrega
```
`curva_abc.csv`  (deriva do catálogo)
```
codigo;curva
```
> `recebimentos.csv` (última entrega) é **derivado** do `entradas.csv`, então
> serve os dois detectores sem query extra.

---

## Consumidor 4 — Pricing semanal  *(design; entra depois)*

Repo: `pricing-atacaderj`. Lê MySQL direto per SKU:
`codigo, descricao, custo, preco_praticado, preco_min, giro_semana, giro_ewma90, curva`.
`giro_*` **deriva de `vendas`** — reaproveita a extração 2, não precisa query nova.

---

## Decisões (fechadas)

1. **Promoção (`vp`)**: é um **preço guardado no ERP** → mapear a coluna (não é calculada).
2. **Recebimentos = proxy de estoque**: puxar **todas as entregas dos últimos ~6 meses**
   (`entradas.csv`); o detector cruza **giro × últimas entregas** para estimar cobertura.
   `recebimentos.csv` (última entrega) é derivado.
3. **Dois custos**: `custo_atual` (cadastro) e `custo_venda` (congelado no pedido).
4. **`categoria`/`fornecedor`**: removidos (não usados).

## Ainda em aberto

- **Unidade**: `qtd_vendida` (e `qtd` de entrada) saem na **mesma unidade** de
  `preco/custo`? Se não, trazer o fator em `embalagem` e converter na projeção.
