# Auditoria da ponte × relatórios manuais do ERP (2026-07-07)

Comparação da saída da ponte (gerada às 10:21) com 4 relatórios exportados
manualmente do Solidcon (~11:50–11:56 do mesmo dia), item a item, por script.

| Relatório (PDF)                        | Arquivo da ponte           | Resultado |
|----------------------------------------|----------------------------|-----------|
| rptCadastroProdutoAtacadoPaisagem      | `cotacao/produtos.json`    | Preço atacado: **1010/1012** itens vivos batem. Venda: 841/1012 (ver "preço filial" abaixo). Qtde: mede outra coisa (ver `q`) |
| rptGestaoPreco (filial 1)              | `cotacao/produtos.json`    | Custo: **4463/4463** (diferenças só de arredondamento). Promo: **4461/4463**. Venda: 3889/4463 (idem "preço filial") |
| rptCurvaABC50 (01–07/07)               | `vendas.csv`, `curva_abc.csv` | Qtde: **2728/2731** exatas; Valor/Custo idem (±R$ 0,02 de arredondamento por dia). Curva da ponte = coluna **\*CF** do relatório (2711/2731) |
| rptPedidosVendaEmitidaDAVPorItens (06/07) | `vendas.csv`            | **142/142 produtos, 1.464/1.464 unidades** batem com `tbVendaDAV`; todas cobertas em `vendas.csv`. Total do dia 06/07 = **82.423,04** (re-conferido) |

## Fatos descobertos (conferidos no banco)

1. **Preço "Venda" dos relatórios ≠ preço da ponte em ~13% dos itens — e a
   PONTE é que reflete o caixa.** O ERP tem dois preços: o da **empresa**
   (`tbSuperProdutoVenda.vlVenda` — é o que rptCadastro/rptGestaoPreco imprimem)
   e o da **filial 1** (`tbSuperProdutoVendaFilial.vlVenda`, inclui "preço de
   concorrência" com vigência). A view `VW_NEOGRID_PRODUTO_PRECO` (fonte da
   ponte) traz o preço da filial, e `tbVendaPDV.vlVenda` confirma que **o PDV
   cobra o preço da filial** (ex.: 42165 vendido a 4,79 = filial; cadastro
   empresa = 5,49).

2. **`produtos.json.q` = QUANTIDADE_CAIXA (embalagem), NÃO a quantidade mínima
   do atacado.** O relatório de atacado mostra Qtde=6/3 (mínimo p/ preço
   atacado = `QUANTIDADE_ATACADO` da view, hoje não exportado); a ponte exporta
   a caixa (12/24…). Se o HTML da cotação apresentar "a partir de `q` un paga
   `v`", precisa trocar para `QUANTIDADE_ATACADO`. As linhas da view por
   embalagem têm preços idênticos, então o `ROW_NUMBER` por maior caixa não
   afeta preço nenhum.

3. **`vendas.csv` é BRUTA — não desconta devoluções de venda.** A Curva ABC
   desconta. Na janela 01–07/07 afetou só 3 de 2.731 produtos (ex.: 13555 teve
   120 un/R$ 430,80 devolvidas em 03/07). A view
   `VW_2D_VENDAS_&_DEVOLUÇÕES` dá o líquido: `SUM(QtdeVenda)` já é líquida e
   valor líquido = `SUM(ValorVenda − vlVendaDevolvido)`. Se um dia importar,
   trocar a fonte da query VENDAS.

4. **Mortos ficam fora do `produtos.json`** (2.138 mortos do relatório de
   atacado não estão no json) — correto para a cotação. Exceção: **102115
   CROKISSIMO CHOCOLATE 45G** está vivo mas não aparece em NENHUMA das duas
   views Neogrid (o próprio ERP não o expõe a integradores); único caso em 4.600.

5. **Curva da ponte = coluna \*CF do relatório** (curva "fixa" do cadastro),
   não a \*CR (recalculada no período do relatório). 20/2731 divergências são
   produtos com curva X/ausente nas views (viram NULL por design) ou mortos
   vendidos na janela.

6. `tbVendaPDV` é agregada por produto/dia (campo `qtCupons`); DAVs entram
   nela no dia da emissão — nada a corrigir para os detectores.

## Parte 2 — cruzamento com o app de cotação (`cotacao-auditoria-atacaderj`)

O repo do app ficou público na mesma data e foi auditado. O app **não lê
`produtos.json` hoje**: o catálogo entra por upload manual de 3 relatórios +
a auditoria lê um 4º — exatamente os 4 PDFs conferidos acima:

| Insumo do app                       | Relatório manual              | Como o app usa |
|-------------------------------------|-------------------------------|----------------|
| Planilha ATACADO                    | rptCadastroProdutoAtacado…    | `q`,`v` = Qtde/Preço do box **Atacado 1**; ignora mortos |
| Planilha VAREJO                     | rptGestaoPreco                | `v` = Venda (promo vence se menor); custo; exige rodapé "total de produtos" e data de HOJE |
| Planilha CURVA                      | rptCurvaABC50                 | curva A = coluna **\*CR** (recalculada no período!) |
| Relatório de VENDAS (auditoria)     | rptPedidosVendaEmitidaDAV…    | por pedido/vendedor: Cód, Emb, Qtde, Valor, **Custo Un.** |
| Preço final `v` do app = **menor** entre varejo, promo e atacado 1; `q` = qtde mínima do atacado quando o atacado é o menor. |||

**Para a ponte substituir os uploads manuais (fetch `produtos.json`):**

1. **`q` deve virar `QUANTIDADE_ATACADO`** (hoje exporta `QUANTIDADE_CAIXA`).
   Conferido no banco: `QUANTIDADE_ATACADO` da view = box Atacado 1 do
   relatório em **995/995** produtos. Correção de 1 linha em `queries.py`.
2. **Curva**: a ponte exporta a \*CF (cadastro/Neogrid); o app usa a \*CR do
   relatório do período (só 1.453/2.731 coincidem). Decidir qual vale para o
   teto de desconto (3% A / 5% resto) antes de trocar a fonte.
3. **Preço**: em 424/4.468 produtos o preço mínimo da ponte é MENOR que o dos
   relatórios — é o preço da filial (concorrência), que é o que o PDV cobra.
   Auditar desconto contra o preço da EMPRESA (como o app faz hoje via
   relatórios) pode gerar falsas divergências nesses itens; a ponte melhora isso.
4. **Auditoria de desconto AUTOMATIZADA (feito em 2026-07-07)**: a 5ª query
   `PEDIDOS_VENDA` reproduz o rptPedidosVendaEmitidaDAVPorItens item a item —
   validada contra o PDF de 06/07: **199/199 linhas, 14/14 pedidos**, qtde/
   valor/custo idênticos (única diferença: o relatório mostra o custo de
   cadastro na hora da impressão; a query usa `tbPedidoItem.vlCusto`,
   congelado na emissão — 2 produtos com ±R$ 0,10). Detalhes do schema:
   - o período do relatório filtra por **`dtAtendido`** (emissão), não `dtPedido`;
   - `vlPedidoItem`/`vlVendaOriginal`/`vlCusto` são **por volume**
     (`custo_un = vlCusto/qtEmbalagem`);
   - cliente = `tbPedidoVenda.cdPessoaComercial → tbPessoa`; vendedor =
     `cdVendedor → tbPedidoVendedor.nmVendedor`; nº DAV = `NrDAVPDV` (a coluna
     "Nota" do relatório fica deslocada de −1 vs `NrDAVPDV`; cosmético).
   Saída: `cotacao/pedidos_venda_dav.csv` (janela `janela_pedidos_venda_dias`,
   default 7). Rodando as regras do app (piso 10%, teto 3% A / 5%) sobre o dia
   06/07: 154 itens auditados, 33 divergências, R$ 105,79 de impacto.
