# Custo de entrada, DIFAL e CCI (engenharia reversa, 2026-07-10)

Investigação feita no PC-ponte a pedido do dono, usando a tela *Produto →
NF Recebida* do produto **19047 (PACOQUITA ROLHA EMB 100 UN)** como gabarito
(5 notas: 128502 e 125631 da SANTA HELENA/SP; 5848, 5470 e 5338 do REI DOS
DOCES/RJ). Somente SELECT; tudo conferido ao centavo.

## Custo Unit. (tbNotaItem.CustoUnitario) — FÓRMULA CONFIRMADA

O Solidcon grava o custo unitário da entrada com o **DIFAL embutido "por
dentro", base dupla**:

```
CustoUnitario = (vlItemNota_liquido + IPIvUnid) × (1 − ICMS_interestadual)
                                                ÷ (1 − alíquota_interna_total)
```

- alíquota interna total RJ = **22%** (20% ICMS + 2% FCP/FECP);
- coluna "Difal" da tela = `tbNotaItem.DiferencaAliquota` = 22 − 12 = **10**;
- nota interestadual (SP→RJ, CFOP 2102, ICMS 12%): NF 128502:
  (21,45 + 0,6971) × 0,88 ÷ 0,78 = **24,9865** ✓ (tela 24,99);
  NF 125631 (com desconto 8,525%): (26,6833 + 0,8672) × 0,88 ÷ 0,78 =
  **31,0826** ✓;
- nota local (CFOP 1102, ICMS 20+2 já embutido no preço): custo = preço, sem
  gross-up (Difal 0).

**Efeito do difal**: multiplica (preço+IPI) por 0,88/0,78 = 1,12821 → +12,82%.
Na NF 128502 isso é +R$ 2,8394/un (2.000 un → R$ 5.678,80 embutidos no custo).

Consequências para a ponte:
- `VW_NEOGRID_PRODUTO_PRECO.CUSTO_ULTIMA_ENTRADA` = CustoUnitario da última
  entrada (JÁ com difal, SEM o acréscimo do CCI). É o custo que o
  `produtos.json` da cotação exporta.
- `CUSTO_LIQUIDO` da mesma view = CUSTO_ULTIMA_ENTRADA × (1 − 29,25%)
  (29,25 = 20 ICMS + 9,25 PIS/COFINS de saída).
- `tbVendaPDV.vlCusto` (CMV diário) = CustoUnitario da última entrada vigente
  no dia (vlCustoLogistico e vlQuebra = 0 nesta base).

## Fórmula GERAL do Custo Unit. (validada em 45/48 itens de 7 grupos, 2026-07-10)

Testada em amostras com verba, desconto, IPI, difal, redução de BC, ICMS-ST,
FCP-ST, frete/seguro/outros — tudo ao centavo:

```
liq        = vlItemNota × (1 − Desconto%)                    [por embalagem]
extras     = (IPIvIPI + vFrete + vSeg + vOutro
              + ICMSvICMSST + ICMSvFCPST) / qtItemNota       [por embalagem]
entrada%   = (ICMSpICMS + ICMSpFCP) × (1 − ReducaoBaseICMS%)
fator      = (1 − entrada%) / (1 − entrada% − DiferencaAliquota%)
CustoUnit  = (liq + extras − vlVerbaComercial) × fator ÷ qtEmbalagem
```

Efeito de cada coluna da tela *NF Recebida* no custo (e portanto no CCI):

| Coluna | Campo | Efeito |
|---|---|---|
| Preço Emb./Unit. | vlItemNota | base de tudo |
| Desc. | Desconto | reduz a base ANTES do difal (o difal sobre o desconto some junto) |
| IPI | IPIvIPI/IPIvUnid | soma na base e TAMBÉM é inflado pelo difal |
| Difal | DiferencaAliquota | multiplica a base por (1−ent)/(1−ent−difal); 12→22 = +12,82% |
| Red. BC | ReducaoBaseICMS | reduz a alíquota efetiva de entrada → difal maior. Ex.: compra LOCAL com red. 45,45% sobre 22% → efetiva 12% → mesmo fator 1,1282 da compra interestadual. Sem difal, red. BC não muda o custo (só o crédito) |
| ST$ / FCP-ST | ICMSvICMSST/ICMSvFCPST | somam direto (ST retido é custo, não credita); itens com ST não têm difal (cadeia encerrada) |
| STR / Calc.STR | prSTaRecolher/CalcSTvSTR | antecipação ST com MVA (memo em CalcSTMemo): BaseST = produto×(1+MVA); STR = BaseST×alíq.interna − crédito da NF |
| Verba | vlVerbaComercial | SUBTRAI da base (reduz custo e o difal junto) |
| (frete/seguro/outros) | vFrete/vSeg/vOutro | somam na base e sofrem o gross-up do difal |

Exceções encontradas (3/48): compra de uso/consumo (CFOP 2556), fornecedor
com PIS/COFINS reduzido (0,65+3%) + verba, e item com ICMS desonerado por
benefício fiscal (cBenef RJ820449, ICMSvICMSDeson) — nesses a conta muda.

## CCI — o que se sabe (e o que não)

CCI da tela = CustoUnitario + **acréscimo interno calculado pela aplicação**:

| NF | fornecedor | custo | CCI | acréscimo |
|---|---|---|---|---|
| 128502 (26/06) | Santa Helena | 24,9865 | 26,55 | +1,5635 (6,26%) |
| 125631 (26/05) | Santa Helena | 31,0826 | 31,68 | +0,5974 (1,92%) |
| 5848 (26/06) | Rei dos Doces | 26,0000 | 28,32 | +2,32 (8,92%) |
| 5470 (18/05) | Rei dos Doces | 26,0000 | 28,32 | +2,32 (8,92%) |
| 5338 (04/05) | Rei dos Doces | 26,4793 | 28,64 | +2,1607 (8,16%) |

- **O acréscimo NÃO é difal**: a NF 5848 (local, difal 0, sem IPI, sem frete,
  sem desconto, nota de item único) tem +2,32 mesmo assim.
- Varia por fornecedor e por época (mesmo dia 26/06: +2,32 local vs +1,5635
  interestadual) — não é % fixo da empresa.
- Não está gravado em lugar acessível: as 241 colunas de tbNotaItem foram
  dumpadas; tbNotaReceDesp/tbNotaCTRC/tbWmsEntrada/tbEstoqueMovimento/
  tbPrecoPendente/tbNegociacao/tbCotacaoRespostaItem/tbAcordo/tbFornecedor
  não têm o valor; prQuebra/prLogistico são NULL em produto e em toda a
  hierarquia de classificação; 682/687 módulos SQL do banco são
  criptografados (definition NULL). Candidato conceitual: encargo de
  reposição/frete por fornecedor calculado pelo executável. **Perguntar ao
  suporte Solidcon a composição exata do CCI.**

## Como expurgar SÓ o difal do custo/CCI (receita validada)

Como `Custo = Base × (1−e)/(1−e−d)` (e = alíquota de entrada efetiva,
d = difal), o expurgo é algébrico e usa só o que está na tela:

```
difal embutido (R$)  = Custo Unit. × d ÷ (100 − e)
custo sem difal      = Custo Unit. × (100 − e − d) ÷ (100 − e)
CCI sem difal        = CCI − difal embutido        <- mantém o acréscimo interno
```

- e = (ICMS% + FCP%) × (1 − Red.BC%). Casos típicos: interestadual normal
  e = 12, d = 10 → difal embutido = Custo × 10/88 (= 11,36% do custo).
- Verificação: item local com Red.BC (NF 2352665, prod 102237): custo 14,2492
  → sem difal 12,63 = o preço da nota, exato.
- Se preferir tratar o acréscimo interno do CCI como proporcional:
  `CCI × (100−e−d)/(100−e)` (limite inferior).

SQL pronto (SSMS, somente leitura) — difal embutido de TODAS as entradas:

```sql
SELECT n.Numero, CAST(n.dtEmissao AS date) AS emissao, i.cdProduto,
       sp.nmProdutoPai, i.DiferencaAliquota AS difal_pct,
       i.CustoUnitario AS custo_com_difal,
       CAST(i.CustoUnitario * i.DiferencaAliquota / (100 - x.ent) AS decimal(12,4)) AS difal_embutido,
       CAST(i.CustoUnitario * (100 - x.ent - i.DiferencaAliquota) / (100 - x.ent) AS decimal(12,4)) AS custo_sem_difal
FROM dbo.tbNotaItem i
JOIN dbo.tbNotaEntrada e ON e.cdNotaEntrada = i.cdNota AND e.cdPessoaFilial = i.cdPessoaFilial
JOIN dbo.tbNota n        ON n.cdNota = i.cdNota AND n.cdPessoaFilial = i.cdPessoaFilial
JOIN dbo.tbProduto p     ON p.cdProduto = i.cdProduto
JOIN dbo.tbSuperProduto sp ON sp.cdSuperProduto = p.cdSuperProduto
CROSS APPLY (SELECT (ISNULL(i.ICMSpICMS,0) + ISNULL(i.ICMSpFCP,0))
                    * (1 - ISNULL(i.ReducaoBaseICMS,0)/100.0) AS ent) x
WHERE i.DiferencaAliquota > 0 AND i.CustoUnitario > 0
  AND n.dtEmissao >= '2026-01-01'
ORDER BY n.dtEmissao DESC;
```

Não aplicar em compras de uso/consumo (CFOP x556) nem itens com ICMS
desonerado (cBenef) — nesses a conta do difal é outra.

## Resposta prática (NF 128502, a selecionada na tela)

Decomposição por unidade: 21,45 (preço) + 0,6971 (IPI) + 2,8394 (difal)
= 24,9865 (Custo Unit.) + 1,5635 (acréscimo interno) = **26,55 (CCI)**.

Sem difal: Custo Unit. = 21,45 + 0,6971 = **22,15**; CCI ≈ 26,55 − 2,84 =
**23,71** (mantendo o acréscimo aditivo; se proporcional, 23,53).
