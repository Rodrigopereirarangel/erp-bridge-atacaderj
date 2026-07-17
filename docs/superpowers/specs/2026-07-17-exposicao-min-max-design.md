# Exposição na Prateleira: quantidade MÍN e MÁX por item — AtacadeRJ

- **Data:** 2026-07-17
- **Status:** Aprovado no brainstorming; aguardando revisão do dono
- **Autor:** Rangel (com apoio do Claude Code / skill `superpowers:brainstorming`)
- **Repo de implementação:** `exposicao-atacaderj` (novo) + alterações no `erp-bridge-atacaderj`
- **Relacionados:** `detector-ruptura-atacaderj` (salão), `detector-ruptura-estoque-atacaderj`

---

## 1. Objetivo

Definir, para **cada item da loja**, a quantidade **mínima** e **máxima** que deve ficar
**exposta na prateleira**, expressa em **unidades** e em **caixas-mãe**:

- **MÍN** = quantidade que garante **95% de chance de não haver ruptura de exposição durante
  7 dias corridos**. É o piso: abaixo disso, o cliente encontra buraco na gôndola.
- **MÁX** = quantidade que cobre **95% de 30 dias corridos**. É o teto: acima disso a mercadoria
  fica parada tempo demais na prateleira e passa a correr **risco de avaria e de vencimento**.
  O horizonte de 30 dias é a tradução do critério "o produto tem que estar sempre girando".

Ambos são **arredondados para múltiplos da caixa-mãe**, com **piso de 1 caixa-mãe**.

Entrega: **PDF agrupado por prateleira, enviado no WhatsApp, mensal**.

---

## 2. Decisões-chave

| # | Decisão | Motivo |
|---|---------|--------|
| D1 | **MÍN = P95 da demanda de 7 dias corridos; MÁX = P95 da demanda de 30 dias corridos** | Pedido explícito do dono. O MÁX é teto de rotação (avaria/validade), não alvo de cobertura |
| D2 | **Piso absoluto = 1 caixa-mãe** para MÍN e MÁX, sempre | Decisão do dono. Não se expõe menos que uma caixa. Resolve sozinho os 1.424 itens em que 1 caixa já estoura o teto de 30d |
| D3 | **Giro exclui PDV 11 e 12** (atacado) | Venda de atacado não sai da prateleira; incluí-la infla o giro em ~78% (medido) |
| D4 | **Saldo de estoque INCLUI PDV 11 e 12** | Decisão do dono. A caixa vendida no atacado consome o mesmo estoque. Dois filtros, duas perguntas |
| D5 | Base de vendas = **`DORSAL.tbCupom` + `tbCupomItem`**, não `Solidcon.tbVendaPDV` | É a única com o **número do PDV**. `tbVendaPDV` não tem coluna de PDV (verificado) |
| D6 | **Resolução de EAN obrigatória** via `tbProdutoVenda.qtVenda` | No cupom o produto vem ora como código interno, ora como **EAN**, e cada EAN tem multiplicador. Sem isso, caixa bipada no atacado vira "1 unidade" |
| D7 | **Caixa-mãe = cadastro** (`VW_NEOGRID_PRODUTO_PRECO.QUANTIDADE_CAIXA`), **nunca a nota de entrada** | Decisão do dono (17/07). A nota não participa do cálculo |
| D8 | **Todo o cálculo em UNIDADES**; a caixa-mãe entra **só no último passo** | Decisão do dono (17/07) |
| D9 | **Todo item do cadastro ativo entra na lista**, com piso de 1 caixa | Decisão do dono. Sem lista à parte para item de atacado-only ou sem giro |
| D10 | Modelo = **binomial negativa com peso de dia-da-semana**, P95 por Monte Carlo | Demanda é contagem superdispersa; sábado ≈ 2× segunda. Aguenta o horizonte de 30d com histórico curto |
| D11 | **Censura de ruptura só com 99% de certeza**, exigindo **4 sinais concordantes** | Decisão do dono. Na dúvida o dia FICA (ver §6.2 sobre a direção do viés) |
| D12 | Censura usa a lógica de **ruptura de ESTOQUE**, não de área de venda | Decisão do dono. O que censura a demanda é não ter o que vender |
| D13 | **Bridge é a única porta do banco**; o repo novo consome CSV | Regra vigente do `erp-bridge-atacaderj/CLAUDE.md` |
| D14 | **Primeira rodada em `dryRun: true`** | Mesmo padrão do detector de salão. 4.634 min/máx errados no salão custam caro |
| D15 | Repo novo **standalone em Python** | numpy/scipy/pandas já instalados no ponte; o modelo pede isso |

---

## 3. Descobertas de dados (validadas em produção, 2026-07-17)

Estas descobertas são a fundação da spec. Todas foram verificadas contra o banco real pelo PC-ponte.

### 3.1 `tbVendaPDV` **não serve** — não tem o número do PDV
A tabela que o bridge e os dois detectores usam hoje **não tem coluna de PDV/caixa/terminal**
(colunas conferidas uma a uma). Filtrar atacado por ela é impossível.

### 3.2 O PDV só existe no DORSAL
`DORSAL.tbCupom` (`cdPDV`, `dtCupom`) + `DORSAL.tbCupomItem` (`gdCupom`, `cdProduto`, `qtItem`).
**Histórico disponível: desde 2026-01-22** (~102.681 cupons; ~150 dias úteis).
`Solidcon.tbVendaPDV` tem desde 2023, mas **sem PDV** — histórico longo porém contaminado.
**Decisão: 6 meses limpos > 3 anos contaminados.**

### 3.3 A armadilha do EAN
`tbCupomItem.cdProduto` traz **ora o código interno, ora o EAN**. `tbProdutoVenda` mapeia
`cdEAN → cdProduto` **e carrega o multiplicador `qtVenda`**:

```
produto 18464 (LEITE COND PIRACANJUBA):
  EAN 7898215152002  → qtVenda =  1   (unidade, inCodigoChave=1)
  EAN 17898215152009 → qtVenda = 27   (CAIXA)
```
No atacado bipa-se a caixa. Sem resolver, 1 caixa = "1 unidade" → giro 27× errado.

**Resolução canônica:**
```sql
COALESCE(pv.cdProduto, i.cdProduto)  AS codigo
i.qtItem * COALESCE(pv.qtVenda, 1)   AS unidades
-- LEFT JOIN Solidcon.dbo.tbProdutoVenda pv ON pv.cdEAN = i.cdProduto AND pv.cdEmpresa = 10
```

### 3.4 Prova de que a base está correta
Com a resolução de EAN, o DORSAL reproduz o total oficial **ao decimal**:

| Dia | DORSAL (un) | Solidcon (un) |
|---|---|---|
| 2026-07-14 | 23.406,68 | 23.406,68 |
| 2026-07-15 | 22.293,31 | 22.293,31 |
| 2026-07-16 | 39.474,89 | 39.474,89 |

(O valor em R$ diverge ~0,06% — tratamento de desconto. Irrelevante: o projeto usa unidades.)

### 3.5 O peso do atacado (por que D3 existe)
3 dias medidos: **atacado 37.200 un × salão 47.975 un** → atacado = 44% do volume.
Incluir infla o giro médio em ~78%. Item 18464: 4.386 un atacado × 675 un salão (7,5× de inflação).
**576 itens vendem só no atacado** (caem no piso de 1 caixa por D9).

### 3.6 Calendário
Domingo = **zero venda confirmado** (90 dias). Sábado ≈ **2× a segunda**
(R$ 2,32M × R$ 1,20M) → dia-da-semana é sinal forte, não ruído (justifica D10).

### 3.7 Caixa-mãe
`QUANTIDADE_CAIXA` existe para **100% dos 4.634 itens** (0 nulos). 764 itens têm caixa = 1.
Distribuição: 12 un (954 itens), 24 (474), 6 (465), 20 (324), 10 (313).

### 3.8 Perfil de giro do salão (por que o piso de 1 caixa carrega o projeto)
| Faixa | Itens |
|---|---|
| ≥ 10 un/dia (rápidos) | 273 |
| 1–10 un/dia (médios) | 1.148 |
| < 1 un/dia (lentos) | 1.969 |

**1.424 de 3.390 itens** com caixa > 1 têm 1 caixa-mãe que já estoura o teto de 30 dias;
em **604** deles 1 caixa é mais de 90 dias de venda. Todos caem em **mín = máx = 1 caixa** (D2).
**O modelo estatístico só decide de fato nos ~1.421 itens de giro médio/alto.**

---

## 4. Fontes de dados

O **bridge** exporta; o repo `exposicao-atacaderj` consome (D13).

### 4.1 `vendas_canal.csv` — **query NOVA no bridge** (`VENDAS_CANAL`)
```
codigo;data;canal;unidades
18464;2026-07-14;salao;225
18464;2026-07-14;atacado;1462
```
- `canal` = `atacado` se `cdPDV IN (11,12)`, senão `salao`.
- Unidades já resolvidas por EAN (§3.3). Janela: `{janela_exposicao}` dias (default 400 = tudo).

### 4.2 `catalogo` — **alteração no bridge**
A query `CATALOGO` já expõe `embalagem` (= `QUANTIDADE_CAIXA`) e `prateleira`. Exportar ambos
para `saida/exposicao/`, junto com `descricao` e `curva`.

### 4.3 `entradas.csv` — **já existe** (query `ENTRADAS`)
`codigo;data;qtd` — unidades por dia de chegada (`dtChegada`, já `× qtEmbalagem`). Usada **só**
pela censura de ruptura (§6.2), nunca pela caixa-mãe (D7).

---

## 5. Arquitetura

Componentes isolados, cada um com uma responsabilidade, testável sozinho:

1. **`importar`** — lê os 3 CSVs, valida layout, normaliza para `item × dia × canal → unidades`,
   `item → {caixa_mae, prateleira, descricao, curva}`, `item → [entradas]`. Erro claro se o
   layout divergir.
2. **`calendario`** — constrói a grade de dias abertos: exclui domingo + feriado auto-detectado
   (dia com nº de itens distintos vendidos < `diaFechadoFracao` × mediana). **Porta da lógica já
   em produção** em `detector-ruptura-atacaderj/src/detect/calendar.js`.
3. **`censura`** — marca os dias de ruptura de estoque a descartar (§6.2). Consome **todos os
   canais** (D4).
4. **`dow`** — fatores de dia-da-semana por categoria, encolhidos para a loja (§6.3).
5. **`modelo`** — ajusta a binomial negativa por item sobre os dias limpos (§6.4).
6. **`simular`** — Monte Carlo → P95 dos dois horizontes, **em unidades** (§6.5).
7. **`minmax`** — aplica arredondamento e piso de caixa-mãe (§6.6). **Único lugar que conhece
   caixa-mãe** (D8).
8. **`validar`** — bootstrap + backtest; **trava a entrega** se a promessa de 95% não se sustentar (§7).
9. **`relatorio`** — PDF por prateleira (§8).
10. **`enviar`** — delega ao Baileys do bridge (`scripts/whatsapp/enviar.mjs`); respeita `dryRun`.
11. **`rodar`** — orquestrador; tarefa mensal no ponte.

---

## 6. A lógica

### 6.1 Horizontes, em dias abertos
- **7 dias corridos = 6 dias úteis** = exatamente uma semana seg–sáb (domingo fechado).
  Toda janela de 7 dias corridos contém **um de cada dia da semana** → sem ambiguidade.
- **30 dias corridos = 25 ou 26 dias úteis**, conforme o dia de início (4 ou 5 domingos dentro).
  Para eliminar a ambiguidade, a simulação roda **os 6 dias de início possíveis** (seg..sáb) e
  agrupa os resultados numa distribuição só, ponderados igualmente.

### 6.2 Censura de ruptura — 4 sinais, todos obrigatórios (D11, D12)

Um dia só sai da base de cálculo se **os quatro** valerem:

1. **Zero venda no dia**, somando **todos os canais** (D4).
2. **Silêncio anormal para aquele item**: o comprimento da sequência de dias zerados que contém
   o dia ≥ `k` × intervalo típico do próprio item (EWMA dos gaps — porta de
   `detector-ruptura-atacaderj/src/detect/gapstats.js`). Default `k = 2`.
   *Protege o item lento: quem vende 1×/mês tem zero natural e não é marcado.*
3. **Estoque esgotado** (o critério do dono): vendas acumuladas **de todos os canais** desde a
   última entrega ≥ quantidade entregue (`razaoEsgotamento ≥ 1.0`).
4. **Retro-confirmação**: a sequência **termina com uma entrega** e a venda volta depois dela.

**Por que os 4 e por que 99% é atingível aqui:** os detectores decidem *no presente* e não podem
saber o que vem depois. Este cálculo olha o **passado** — o retrovisor do sinal 4 é uma prova que
eles não têm.

**A direção do viés é deliberada.** Manter por engano um dia fraco encolhe um pouco o mín.
Remover por engano um zero legítimo **infla** o mín e enche a prateleira de mercadoria parada —
exatamente a avaria/validade que o MÁX existe para evitar. **Na dúvida, o dia fica.**

### 6.3 Dia-da-semana
`f_dow` = venda média do dia da semana ÷ venda média geral, calculado por **categoria
(prateleira)** — que tem volume suficiente — e encolhido para o fator da loja:

```
f_cat_final(d) = (n_cat(d) × f_cat(d) + m × f_loja(d)) / (n_cat(d) + m)
```
- `n_cat(d)` = nº de item-dias observados naquela categoria naquele dia-da-semana (o tamanho da
  evidência que a categoria tem para opinar sobre `d`).
- `m = dow.pesoEncolhimento` (default 200 item-dias) = quanta evidência a categoria precisa para
  valer tanto quanto a loja. Categoria magra → `f_cat_final ≈ f_loja`.
- Os 6 fatores são normalizados no fim para que a média dos dias abertos = 1.

### 6.4 Modelo por item (binomial negativa)
Sobre os dias limpos (§6.2), canal **salão** (D3):

- **Média ajustada por DOW:** `μ_i = Σ y_d / Σ f_dow(d)`.
- **Dispersão por momentos:** `Var = μ + μ²/r` → `r_i = μ² / (Var − μ)`.
  Se `Var ≤ μ` (subdisperso) → **Poisson** (`r → ∞`).
- **Encolhimento:** item com < `modelo.minDiasLimpos` (default 30) dias limpos com venda tem
  `r_i` encolhido para a mediana global de `r` da categoria.
- **Item sem nenhuma venda limpa no salão** → `μ_i = 0`; cai no piso de 1 caixa (D9).

### 6.5 Simulação (P95 em unidades)
Para cada horizonte H ∈ {7 dias corridos, 30 dias corridos} e cada dia de início s ∈ {seg..sáb}:
1. Monta a lista de dias úteis da janela e seus dias-da-semana.
2. Sorteia cada dia de `NB(média = μ_i × f_dow(d), dispersão = r_i)`.
3. Soma a janela → uma amostra da demanda do horizonte.

`simulacao.sorteios` (default 20.000) por dia de início; agrupa os 6 conjuntos;
**P95 = percentil 95 do agregado**. Semente fixa (`simulacao.semente`) → rodada reprodutível.

### 6.6 MÍN e MÁX (o único passo que vê caixa-mãe — D8)
```
min_un = max(caixa_mae, ceil_para_multiplo(P95_7d,  caixa_mae))
max_un = max(min_un,    floor_para_multiplo(P95_30d, caixa_mae))
min_cx = min_un / caixa_mae
max_cx = max_un / caixa_mae
```
- **MÍN arredonda para CIMA**: arredondar para baixo quebraria a promessa de 95%.
- **MÁX arredonda para BAIXO**: é teto de validade; passar dele é o risco a evitar.
- Quando os dois caem na mesma caixa, `min = max` e a instrução é honesta: **uma caixa exposta**.

---

## 7. Validação — a entrega é travada por ela

### 7.0 Subconjunto elegível
As duas validações rodam **só nos itens onde o modelo de fato decide** — nos demais o resultado é
o piso de 1 caixa (D2/D9) e não há promessa estatística a verificar. Elegível =
`μ_i ≥ validacao.giroMinimo` (default 1 un/dia útil) **e** ≥ `validacao.minJanelas` (default 12)
janelas de 7 dias corridos limpas no histórico. Pelo perfil de §3.8, isso é da ordem de 1.400 itens.
O nº de elegíveis entra no rodapé do PDF.

### 7.1 Bootstrap (confere o modelo no horizonte curto)
Para cada item elegível, o P95 de 7 dias é recalculado pelo **percentil empírico das janelas
reais de 7 dias corridos** que de fato aconteceram no histórico limpo. Se a binomial negativa e
o bootstrap concordarem no horizonte curto, ganha-se o direito de usar a NB no horizonte de
30 dias — onde o bootstrap não alcança (só ~5 janelas independentes em 6 meses).

**Critério:** a **mediana, sobre os itens elegíveis**, de `|P95_NB − P95_bootstrap| ÷ P95_bootstrap`
≤ `validacao.tolBootstrap` (default 15%).

### 7.2 Backtest (confere a promessa de 95%)
- Separa as últimas `validacao.semanasHoldout` (default 8) semanas.
- Para cada item elegível e cada semana do holdout, calcula o MÍN usando **só** os dados
  anteriores àquela semana (sem espiar o futuro).
- Conta a fração de pares (item × semana) em que a venda real do salão da semana ≤ MÍN.
- **Essa fração — a cobertura medida, agregada sobre todos os pares — tem que ficar em
  `[0,90 ; 0,99]`.**

### 7.3 Trava
Se 7.1 ou 7.2 falharem, a rodada **não envia**: grava o diagnóstico e avisa. Um número com
promessa de 95% que não passa no backtest é retórica, não estatística.

---

## 8. Saída

**PDF agrupado por prateleira** (o endereço físico do ERP: `tbClassificacaoProduto.
nmClassificacaoProduto`, ex. "PRATELEIRA 33"), ordenado por prateleira → descrição, para o
repositor caminhar a gôndola na ordem. Gerado com Edge headless (porta de
`detector-ruptura-atacaderj/src/io/pdf.js`), enviado pelo Baileys do bridge.

Uma linha por item:

| Coluna | Origem |
|---|---|
| Código / Descrição | catálogo |
| Caixa-mãe | cadastro (D7) |
| Giro (un/dia útil, salão) | modelo |
| **MÍN (un / cx)** | §6.6 |
| **MÁX (un / cx)** | §6.6 |

Rodapé de cada rodada, para o número ser auditável: período do histórico, dias úteis usados,
dias censurados, resultado do bootstrap e do backtest, e a nota de que domingo e feriados
não contam.

**Tamanho:** ~4.634 itens. É um documento de referência para a gôndola, não uma lista diária
de ação — diferente do detector de ruptura, que manda ~11 itens/dia.

---

## 9. Configuração (`config.local.json`, gitignored)

| Parâmetro | Default |
|---|---|
| `janela.dias` | 400 (pega todo o DORSAL disponível) |
| `canal.pdvsAtacado` | `[11, 12]` |
| `calendario.diaFechadoFracao` | 0.2 |
| `censura.kIntervalo` | 2 |
| `censura.razaoEsgotamento` | 1.0 |
| `censura.exigeRetroConfirmacao` | true |
| `dow.pesoEncolhimento` | 200 |
| `modelo.minDiasLimpos` | 30 |
| `simulacao.sorteios` | 20000 |
| `simulacao.semente` | 42 |
| `percentil` | 0.95 |
| `horizonte.minDiasCorridos` | 7 |
| `horizonte.maxDiasCorridos` | 30 |
| `validacao.giroMinimo` | 1.0 (un/dia útil, p/ ser elegível — §7.0) |
| `validacao.minJanelas` | 12 |
| `validacao.tolBootstrap` | 0.15 |
| `validacao.semanasHoldout` | 8 |
| `validacao.coberturaAceita` | `[0.90, 0.99]` |
| `whatsapp.destino` | (telefone; nunca versionado) |
| `whatsapp.dryRun` | **true** (D14) |

---

## 10. Erros e resiliência

- **CSV ausente/malformado** → erro claro, **não** gera PDF pela metade.
- **Item sem entrada registrada** → censura cai nos sinais 1+2 apenas; sem os 4, **nada é
  censurado** (D11 conservador).
- **Item novo / sem histórico** → piso de 1 caixa (D9), marcado como "sem histórico" no PDF.
- **Validação reprovada** (§7.3) → não envia; grava diagnóstico.
- **Idempotência** → rodar 2× no mesmo mês não duplica envio.
- **PC desligado** → ao rodar depois, registra atraso no rodapé.

---

## 11. Testes

- **`calendario`** — domingo fora; feriado detectado; loja com dia fraco legítimo não vira feriado.
- **`censura`** — os 4 sinais: cada um sozinho **não** censura; os 4 juntos censuram; item lento
  com zero natural **nunca** censurado; ruptura sem entrega no fim (sinal 4 falha) **não** censura;
  venda de atacado conta no esgotamento (D4).
- **`dow`** — sábado > segunda; categoria magra encolhe p/ loja; fatores normalizam p/ média 1.
- **`modelo`** — superdisperso → NB; subdisperso → Poisson; item sem venda → μ=0; encolhimento
  com poucos dias.
- **`simular`** — reprodutível com semente; P95 cresce com o horizonte; 7d corridos = 6 dias úteis.
- **`minmax`** — MÍN arredonda p/ cima; MÁX p/ baixo; piso de 1 caixa; `max ≥ min` **sempre**;
  item lento → min = max = 1 caixa; caixa-mãe = 1 → arredondamento vira unidade.
- **`importar`** — EAN resolvido; coluna faltando; canal inválido; data inválida.
- **`validar`** — backtest reprovado trava a entrega.
- **Reconciliação (teste de integração)** — a soma de `vendas_canal.csv` bate com
  `Solidcon.tbVendaPDV` no mesmo dia (a prova de §3.4, virada em teste automático).

---

## 12. Riscos registrados

| # | Risco | Tratamento |
|---|---|---|
| R1 | **Histórico de só ~6 meses** (DORSAL desde 22/01/2026) | Aceito (D5). Sem comparação ano-a-ano; sazonalidade anual (Natal, Páscoa) **não** é capturada. A rodada mensal reage ao giro corrente |
| R2 | **Caixa-mãe do cadastro pode estar errada** — 30 itens onde a nota de entrada contradiz o cadastro (TAPIOCA ROSA cadastrada 50 × nota 5; FOFURA REQUEIJAO **C10** cadastrado como caixa **1**) | **Aceito por decisão do dono (D7)**: usa o cadastro. Se o cadastro erra p/ cima, o item é superexposto. Conserto é no ERP, não aqui |
| R3 | Loja pode abrir num domingo atípico | `calendario` deriva os dias abertos **dos dados**, não de regra fixa |
| R4 | Novo PDV de salão (o 9 nasceu em 01/07/2026) | Filtro é `NOT IN (11,12)`, não `IN (1..9)` — PDV novo de salão entra sozinho |
| R5 | Promoção antiga infla o histórico | A NB absorve como superdispersão; o P95 sobe de propósito (a demanda de pico é real) |
| R6 | PDF de ~4.634 itens é grande p/ WhatsApp | Aceito: documento de referência mensal, não lista de ação |

---

## 13. Fora de escopo (YAGNI)

- Capacidade física da gôndola (não existe cadastro de espaço; o MÁX é teto de rotação, não de espaço).
- Validade real por item (o ERP não tem shelf-life confiável; 30 dias é a regra do dono).
- Sugestão de compra / dimensionamento de pedido (isso é dos detectores).
- Ciclo de marcação/feedback (cancelado pelo dono em 16/07 no detector; não renasce aqui).
- Sazonalidade anual (R1) e ML — a NB + DOW resolve o que o dado de 6 meses sustenta.
- Multi-loja.

---

## 14. Critérios de sucesso

1. Todo item do cadastro ativo tem **MÍN e MÁX em unidades e em caixas-mãe**, com piso de 1 caixa.
2. O giro usado **não contém atacado** (PDV 11/12), e a reconciliação com a base oficial é exata.
3. Dias de ruptura de estoque saem da base **só** com os 4 sinais; nenhum item lento é censurado.
4. O **backtest mede ~95%** de cobertura do MÍN — a promessa é verificada, não afirmada.
5. O dono recebe o PDF por prateleira mensalmente e o repositor caminha a gôndola na ordem.
6. Custo recorrente **R$ 0**.
