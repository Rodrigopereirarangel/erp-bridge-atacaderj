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
| **catalogo**     | `codigo, descricao, embalagem, custo, preco_atacado, preco_varejo, preco_promocao, curva, fornecedor, categoria, ativo` | 3–5x/dia |
| **vendas**       | `codigo, descricao, data, qtd_vendida, valor` (últimos `janela_dias`, dia a dia) | diário (05:00) |
| **recebimentos** | `codigo, data_ultimo_recebimento, qtd_recebida` | diário (05:00) |
| **pedidos**      | `codigo, data_pedido, qtd_pedida, status, previsao_entrega, fornecedor` (só abertos) | diário (05:00) |

> **Origem no ERP — A PREENCHER JUNTOS** (por isso os `SELECT`s estão como TODO):
>
> | Preciso de você | Ex. do que responder |
> |---|---|
> | Tabela + coluna do **cadastro de produtos** | `produtos (codigo, descricao, ...)` |
> | Colunas de **preço**: atacado, varejo, promoção | `preco1=atacado, preco2=varejo, preco_promo=promoção?` |
> | Coluna de **custo** e de **curva ABC** | `custo_medio`, `curva` |
> | Tabela de **itens de venda** (nota + item) | `vendas / vendas_itens` |
> | Tabela de **entradas/recebimentos** | `entradas / entradas_itens` |
> | Tabela de **pedidos de compra** + campo de status "aberto" | `pedidos_compra (status IN ...)` |
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
| `q`     | `embalagem`       | qtd por embalagem (fator) |
| `v`     | `preco_atacado`   | **preço atacado** (base) |
| `vu`    | `preco_varejo`    | **preço varejo** (unitário) |
| `vp`    | `preco_promocao`  | **preço promoção** (novo — ver "A confirmar") |
| `custo` | `custo`           | custo (piso de margem) |
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

`vendas.csv`  (**com valor R$**)
```
codigo;descricao;data;qtd_vendida;valor
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
2. **"Última entrega"**: `recebimentos` traz **só a última** entrada por item, ou
   **todas** as entradas da janela? (Os detectores usam a data da última.)
3. **Unidade**: `qtd_vendida` sai na **mesma unidade** de `preco/custo`? Se não,
   trazer o fator em `embalagem` e converter na projeção.
