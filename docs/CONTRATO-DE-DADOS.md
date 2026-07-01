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
| **recebimentos** | `codigo, data_ultimo_recebimento, qtd_recebida` | diário (05:00) |
| **pedidos**      | `codigo, data_pedido, qtd_pedida, status, previsao_entrega` (só abertos) | diário (05:00) |

> **Dois custos (definição do usuário):** `custo_atual` vem do **cadastro** (custo de
> hoje → cotação/pricing decidem com ele); `custo_venda` vem do **item do pedido**
> (custo **congelado no dia da venda** → margem realizada correta no BI/priorização).
> `categoria`/`fornecedor` foram **removidos** (não usados).

> **Origem no ERP — A PREENCHER JUNTOS** (por isso os `SELECT`s estão como TODO):
>
> | Preciso de você | Ex. do que responder |
> |---|---|
> | Tabela + coluna do **cadastro de produtos** | `produtos (codigo, descricao, ...)` |
> | Colunas de **preço**: atacado, varejo, promoção | `preco1=atacado, preco2=varejo, preco_promo=promoção?` |
> | **Custo ATUAL** (cadastro) + **curva ABC** | `custo_medio`, `curva` |
> | Tabela de **itens de venda** + **custo no pedido** (`custo_venda`) | `vendas / vendas_itens (custo_no_pedido)` |
> | Tabela de **entradas/recebimentos** | `entradas / entradas_itens` |
> | Tabela de **pedidos de compra** + qual `status` = "aberto" | `pedidos_compra (status IN ...)` |
> | **Unidade** de `qtd_vendida` vs preço/custo | "venda em unidade, preço por caixa de N" |

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
| `vp`    | `preco_promocao`  | **preço promoção** (só se guardado — ver "A confirmar") |
| `custo` | `custo_atual`     | custo corrente (piso de margem / limite de desconto) |
| `cv`    | `curva`           | curva ABC |

> **Dependência conhecida:** falta o `cotacao_ia.html` fazer `fetch("produtos.json")`
> no início (hoje o catálogo é embutido). É um ajuste de 1 linha — fazemos depois.

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
`pedidos.csv`  (pedidos abertos de fornecedor)
```
codigo;data_pedido;qtd_pedida;status;previsao_entrega
```
`curva_abc.csv`  (deriva do catálogo)
```
codigo;curva
```

---

## Consumidor 4 — Pricing semanal  *(design; entra depois)*

Repo: `pricing-atacaderj`. Lê MySQL direto per SKU:
`codigo, descricao, custo, preco_praticado, preco_min, giro_semana, giro_ewma90, curva`.
`giro_*` **deriva de `vendas`** — reaproveita a extração 2, não precisa query nova.

---

## A confirmar (decisões de negócio, não do ERP)

1. **Promoção (`vp`)**: existe um preço de promoção *armazenado* no ERP, ou a
   promoção é **calculada** (como o HTML faz hoje: desconto máx. respeitando piso)?
2. **Recebimentos — espectro, não binário** (definição do usuário): o detector NÃO
   trata "recebeu recente" como sim/não; monta um **espectro de probabilidade**
   cruzando **tempo desde o recebimento × giro no período × quantidade recebida**.
   A ponte já carrega os 3 ingredientes (data + `qtd_recebida`; série diária de
   `vendas`). **Em aberto:** trazer **só a última** entrada por item (simples, casa
   com o detector atual) ou **todas as entradas da janela** (permite estimar
   cobertura ciclo a ciclo → espectro mais rico)?
3. **Unidade**: `qtd_vendida` sai na **mesma unidade** de `preco/custo`? Se não,
   trazer o fator em `embalagem` e converter na projeção.
