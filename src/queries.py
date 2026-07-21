# -*- coding: utf-8 -*-
"""Os 5 SELECTs da ponte — PREENCHIDOS com o schema real (2026-07-07).

Banco: SQL Server 2014, database **Solidcon** (ERP Solidcon; a "loja" e a
filial 1 / SEQLOJA 1). Validado contra o consolidado oficial do PDV
(DORSAL.tbConsVenda): SUM(qtVenda*vlVenda) do dia bate ao centavo.

Fatos do schema que estas queries dependem (conferidos em producao):
- nmProduto e NULL em TODO o banco; o nome real vem de tbSuperProduto.nmProdutoPai
  (tbProduto <-> tbSuperProduto e 1:1 via cdSuperProduto).
- VW_NEOGRID_PRODUTO_PRECO/ESTOQUE (views que o ERP mantem p/ integradores):
  SEQPRODUTO = cdProduto; SEQLOJA 1 = loja. PRECO_ATACADO/QUANTIDADE_ATACADO,
  PRECO_PROMOCAO e CURVA_ABC ja calculados ('X' = sem curva/morto -> vira NULL).
- tbVendaPDV: 1 linha por produto/cupom; vlVenda e vlCusto sao UNITARIOS
  -> valor do dia = SUM(qtVenda*vlVenda); CMV = SUM(qtVenda*vlCusto).
- tbNotaItem.qtItemNota vem em VOLUMES (== qtVolumes); unidades = x qtEmbalagem.
  Entregas: tbNotaEntrada.dtChegada (cdNotaEntrada = tbNota.cdNota, 100% casa).
- Pedidos de compra = tbPedido com inEntrada=1; abertos = dtAtendido IS NULL.
  tbPedidoCompra (cdPedidoCompra = cdPedido) da a dtEntregaPrevista.
  qtPedidoItem em volumes (mesma convencao da nota) -> x qtEmbalagem.
- Pedidos de VENDA (DAV) = tbPedido com inEntrada=0; a "emissao" que o relatorio
  rptPedidosVendaEmitidaDAVPorItens usa e dtAtendido (nao dtPedido!).
  tbPedidoVenda (cdPedidoVenda = cdPedido) da cliente (cdPessoaComercial ->
  tbPessoa) e vendedor (cdVendedor -> tbPedidoVendedor.nmVendedor).
  tbPedidoItem: vlPedidoItem/vlVendaOriginal/vlCusto sao POR VOLUME
  (custo unitario = vlCusto / qtEmbalagem). Validado item a item contra o
  relatorio manual de 06/07: 199/199 linhas, 14/14 pedidos (2026-07-07).
- GRUPO MERCADOLOGICO (familia: DOCES, BISCOITOS, BEBIDAS...) NAO existe como
  FK em tbSuperProduto (nao ha cdGrupo/cdSecao/cdDepartamento; tbDicionarioProduto
  existe mas esta VAZIA). A familia e a RAIZ da arvore tbClassificacaoProduto,
  ja achatada pelo ERP em VW_MGN_PRODUTO (join CodigoProduto = cdProduto):
  Departamento = familia, Secao = corredor, Grupo = prateleira (folha fisica,
  descartada de proposito pelo dono), SubGrupo = sempre NULL. Nomes vem com
  espaco a direita -> RTRIM. Cobertura conferida 2026-07-17: 100% dos itens
  de DAV de 24 meses tem Departamento.
- Cliente ATIVO: o unico flag em tbPessoa e inMorto (bit), NULL na maioria
  (5798 de 6228 em 2026-07-17) -> predicado e COALESCE(inMorto, 0) = 0
  (exclui so os 15 marcados como mortos). Nao ha inAtivo/situacao/dtInativacao.

`{janela}` / `{janela_entradas}` sao substituidos em runtime (config).
"""

CATALOGO = """
SELECT
    p.cdProduto                      AS codigo,
    sp.nmProdutoPai                  AS descricao,
    pr.embalagem,
    pr.qtde_atacado,
    pr.custo_atual,
    -- precos VIGENTES = tabela do CAIXA (DORSAL.tbSuperProduto), onde toda
    -- promocao (tbPromocao, relampago, etc.) ja chega materializada —
    -- validado 13/07: 90% das vendas do dia batem ao centavo; a view e
    -- so o fallback p/ item fora do PDV
    -- atacado: quando o item TEM linha no caixa, so ela decide — relampago
    -- vigente e tier inativo SUSPENDEM o degrau (AtacadoQtde/Preco zerados)
    -- e o fallback antigo da view ressuscitava um atacado que o caixa nao
    -- cobra (4 itens em 20/07, ex. atacado da view MENOR que a relampago
    -- vigente -> cotacao prometia preco abaixo do cobrado). A view so vale
    -- para item SEM linha no PDV.
    CAST(CASE WHEN pdv.cdSuperProduto IS NOT NULL
              THEN CASE WHEN pdv.AtacadoQtde > 0 AND pdv.AtacadoPreco > 0
                        THEN pdv.AtacadoPreco END
              ELSE pr.preco_atacado END AS decimal(14,2)) AS preco_atacado,
    CAST(COALESCE(NULLIF(pdv.vlVenda, 0),
                  pr.preco_varejo) AS decimal(14,2))  AS preco_varejo,
    -- promocao efetiva = menor positivo entre a da view e a VIGENTE hoje em
    -- tbPromocao (a view NAO enxerga essas promos — caso acucar Guarani 2,79
    -- com vp NULL enquanto a loja vendia em promo; descoberto 2026-07-13)
    CAST(CASE WHEN pr.preco_promocao > 0
               AND (promo.promo_vigente IS NULL
                    OR pr.preco_promocao <= promo.promo_vigente)
              THEN pr.preco_promocao
              ELSE promo.promo_vigente END AS decimal(14,2)) AS preco_promocao,
    e.CURVA_ABC                      AS curva,
    -- classificacao mercadologica = endereco fisico na loja ("PRATELEIRA 33")
    -- -> coluna Prateleira do relatorio de ruptura do salao (pedido do dono, 16/07)
    cl.nmClassificacaoProduto        AS prateleira,
    -- A classificacao tem TRES degraus (dono, 17/07): setor > corredor >
    -- prateleira. Ex.: PERFUMARIA > CORREDOR 20 > PRATELEIRA 21.
    -- corredor = PAI, setor = AVO; sem o nivel, o consumidor desce na cascata.
    clp.nmClassificacaoProduto       AS corredor,
    clpp.nmClassificacaoProduto      AS setor,
    -- vendido por PESO (mortadela, queijo, carnes...): kg/g em
    -- tbSuperProduto.cdUnidadeMedida — o relatorio de exposicao mostra kg
    -- em vez de un e marca com balanca (dono, 18/07)
    CASE WHEN LOWER(RTRIM(sp.cdUnidadeMedida)) IN ('kg','g')
         THEN 1 ELSE 0 END           AS peso,
    CAST(p.inAtivo AS int)           AS ativo
FROM (   -- as DUAS views Neogrid tem 1 linha POR EMBALAGEM -> pegar a LINHA
         -- inteira da maior caixa (nao misturar precos de embalagens diferentes)
    SELECT SEQPRODUTO, SEQLOJA,
           QUANTIDADE_CAIXA               AS embalagem,
           QUANTIDADE_ATACADO             AS qtde_atacado,
           CUSTO_ULTIMA_ENTRADA           AS custo_atual,
           NULLIF(PRECO_ATACADO, 0)       AS preco_atacado,
           PRECO_NORMAL                   AS preco_varejo,
           NULLIF(PRECO_PROMOCAO, 0)      AS preco_promocao,
           ROW_NUMBER() OVER (PARTITION BY SEQPRODUTO
                              ORDER BY QUANTIDADE_CAIXA DESC) AS rn
    FROM dbo.VW_NEOGRID_PRODUTO_PRECO
    WHERE SEQLOJA = 1
) pr
JOIN (
    SELECT SEQPRODUTO, SEQLOJA, MIN(NULLIF(CURVA_ABC, 'X')) AS CURVA_ABC
    FROM dbo.VW_NEOGRID_PRODUTO_ESTOQUE
    GROUP BY SEQPRODUTO, SEQLOJA
) e ON e.SEQPRODUTO = pr.SEQPRODUTO AND e.SEQLOJA = pr.SEQLOJA
JOIN dbo.tbProduto p       ON p.cdProduto = pr.SEQPRODUTO
JOIN dbo.tbSuperProduto sp ON sp.cdSuperProduto = p.cdSuperProduto
LEFT JOIN DORSAL.dbo.tbSuperProduto pdv
       ON pdv.cdSuperProduto = p.cdProduto
      AND pdv.cdFilial = 1
      AND (pdv.inAtivo = 1 OR pdv.inAtivo IS NULL)  -- relampago deixa NULL
LEFT JOIN dbo.tbClassificacaoProduto cl
       ON cl.cdClassificacaoProduto = sp.cdClassificacaoProduto
      AND cl.cdEmpresa = sp.cdEmpresa   -- PK composta: sem cdEmpresa duplicaria linhas
LEFT JOIN dbo.tbClassificacaoProduto clp
       ON clp.cdClassificacaoProduto = cl.cdClassificacaoProdutoPai
      AND clp.cdEmpresa = cl.cdEmpresaPai
LEFT JOIN dbo.tbClassificacaoProduto clpp
       ON clpp.cdClassificacaoProduto = clp.cdClassificacaoProdutoPai
      AND clpp.cdEmpresa = clp.cdEmpresaPai
LEFT JOIN (
    SELECT cdProduto, MIN(promo_vigente) AS promo_vigente FROM (
        SELECT pr2.cdProduto, MIN(pi.vlPromocao) AS promo_vigente
        FROM dbo.tbPromocaoItem pi
        JOIN dbo.tbPromocao pm  ON pm.cdPromocao = pi.cdPromocao
        JOIN dbo.tbProduto pr2  ON pr2.cdSuperProduto = pi.cdSuperProduto
        WHERE pi.vlPromocao > 0
          AND pm.inAtiva = 1
          AND CAST(GETDATE() AS date) BETWEEN CAST(pm.dtInicio AS date)
                                          AND CAST(pm.dtFim AS date)
        GROUP BY pr2.cdProduto
        UNION ALL
        SELECT rel.cdProduto, MIN(rel.vlVenda)   -- relampago: PDV aplica por cima
        FROM dbo.tbPromocaoRelampago rel
        WHERE rel.vlVenda > 0
          AND CAST(GETDATE() AS date) BETWEEN CAST(rel.dtInicio AS date)
                                          AND CAST(rel.dtFim AS date)
        GROUP BY rel.cdProduto
    ) uniao GROUP BY cdProduto
) promo ON promo.cdProduto = p.cdProduto
WHERE pr.rn = 1
ORDER BY sp.nmProdutoPai
"""

VENDAS = """
SELECT
    v.cdProduto                                    AS codigo,
    MAX(sp.nmProdutoPai)                           AS descricao,
    CAST(v.dtVenda AS date)                        AS data,
    CAST(SUM(v.qtVenda) AS decimal(14,3))          AS qtd_vendida,
    CAST(SUM(v.qtVenda * v.vlVenda) AS decimal(14,2))  AS valor,
    CAST(SUM(v.qtVenda * v.vlCusto) AS decimal(14,2))  AS custo_venda
FROM dbo.tbVendaPDV v
JOIN dbo.tbProduto p       ON p.cdProduto = v.cdProduto
JOIN dbo.tbSuperProduto sp ON sp.cdSuperProduto = p.cdSuperProduto
WHERE v.cdProduto IS NOT NULL
  AND v.dtVenda >= DATEADD(day, -{janela}, CAST(GETDATE() AS date))
GROUP BY v.cdProduto, CAST(v.dtVenda AS date)
ORDER BY codigo, data
"""

# VENDAS_MENSAL: UNIDADES + VALOR vendidos por produto em cada MES FECHADO
# dos ultimos {meses_fechados} meses (o mes corrente fica de fora de proposito).
# qtVenda do tbVendaPDV ja e em UNIDADES — validado em 2026-07-10: caixa de 12
# vendida no atacado aparece como 12/24 unidades com vlVenda UNITARIO (17,09
# atacado vs 19,49 varejo no mesmo produto); as qtVenda fracionadas (0,264...)
# sao itens de balanca (kg). CODIGO DEFINITIVO conferido contra o relatorio
# oficial do ERP (rptABCdeVendas, 01-30/06/2026): Qtde = SUM(qtVenda) e
# Venda = SUM(qtVenda*vlVenda) batem no total geral (630.551,997 un /
# R$ 3.485.305,48 / 3.576 itens) e item a item; o Vl. Medio do relatorio e
# Venda/Qtde e por isso e CALCULADO no consumidor, nao extraido.
# Alimenta o dashboard saida/dashboard/vendas_mensal.html.
VENDAS_MENSAL = """
SELECT
    v.cdProduto                                    AS codigo,
    MAX(sp.nmProdutoPai)                           AS descricao,
    CONVERT(char(7), v.dtVenda, 126)               AS mes,
    CAST(SUM(v.qtVenda) AS decimal(14,3))          AS qtd_un,
    CAST(SUM(v.qtVenda * v.vlVenda) AS decimal(14,2)) AS valor
FROM dbo.tbVendaPDV v
JOIN dbo.tbProduto p       ON p.cdProduto = v.cdProduto
JOIN dbo.tbSuperProduto sp ON sp.cdSuperProduto = p.cdSuperProduto
WHERE v.cdProduto IS NOT NULL
  AND v.dtVenda >= DATEADD(month, -{meses_fechados},
                           DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1))
  AND v.dtVenda <  DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1)
GROUP BY v.cdProduto, CONVERT(char(7), v.dtVenda, 126)
ORDER BY mes, codigo
"""

# ULTIMO_CUSTO: custo unitario da ULTIMA entrada de cada produto, em 2 versoes:
# com difal (o que o ERP usa em relatorios/PDV) e SEM difal (expurgado pela
# formula validada em docs/CUSTO-DIFAL-CCI.md: custo x (100-e-d)/(100-e), com
# e = (ICMS+FCP)x(1-RedBC) e d = DiferencaAliquota). Exclui devolucoes de
# venda e uso/consumo/ativo (custo daqueles nao e custo de reposicao).
#
# NAO ESTA LIGADA no bridge.py (13/07/2026) — de proposito. A analise de markup
# com/sem DIFAL saiu melhor no repo `analise-venda-difal`, que casa CADA DIA de
# venda com a nota de entrada VIGENTE naquele dia, em vez de usar so a ultima
# entrada do produto. A query fica aqui porque a formula e a mesma, ja validada
# ao centavo, e serve de referencia (e de ponto de partida, se um dia o
# dashboard de vendas mensais quiser as colunas de custo).
ULTIMO_CUSTO = """
SELECT codigo, custo_com_difal, custo_sem_difal, data_entrada
FROM (
    SELECT i.cdProduto AS codigo,
           CAST(i.CustoUnitario AS decimal(14,4)) AS custo_com_difal,
           CAST(i.CustoUnitario * (100 - x.ent - COALESCE(i.DiferencaAliquota, 0))
                / NULLIF(100 - x.ent, 0) AS decimal(14,4)) AS custo_sem_difal,
           CAST(e.dtChegada AS date) AS data_entrada,
           ROW_NUMBER() OVER (PARTITION BY i.cdProduto
                              ORDER BY e.dtChegada DESC, n.dtEmissao DESC,
                                       i.cdNotaItem DESC) AS rn
    FROM dbo.tbNotaItem i
    JOIN dbo.tbNotaEntrada e
      ON e.cdNotaEntrada = i.cdNota AND e.cdPessoaFilial = i.cdPessoaFilial
    JOIN dbo.tbNota n
      ON n.cdNota = i.cdNota AND n.cdPessoaFilial = i.cdPessoaFilial
    CROSS APPLY (SELECT (COALESCE(i.ICMSpICMS, 0) + COALESCE(i.ICMSpFCP, 0))
                        * (1 - COALESCE(i.ReducaoBaseICMS, 0) / 100.0) AS ent) x
    WHERE i.CustoUnitario > 0
      AND i.cdProduto IS NOT NULL
      AND CAST(i.CFOP AS varchar(10)) NOT LIKE '_55_'   -- uso/consumo e ativo
      AND CAST(i.CFOP AS varchar(10)) NOT IN
          ('1201','1202','2201','2202','1410','1411','2410','2411')  -- devolucao de venda
) t
WHERE rn = 1
"""

# ENTRADAS: uma linha por (produto, dia de chegada) nos ultimos {janela_entradas}
# dias (~6 meses). E o "proxy de estoque": o saldo do ERP existe mas esta
# negativo/nao confiavel (implantacao out/2025), entao cruzar giro (vendas) com
# as ultimas entregas continua sendo o desenho certo. Dela deriva o
# recebimentos.csv (ultima entrega por item) para o detector de salao.
ENTRADAS = """
SELECT
    i.cdProduto                                        AS codigo,
    CAST(ne.dtChegada AS date)                         AS data,
    CAST(SUM(i.qtItemNota * i.qtEmbalagem) AS decimal(14,3)) AS qtd
FROM dbo.tbNotaItem i
JOIN dbo.tbNotaEntrada ne
  ON ne.cdNotaEntrada = i.cdNota AND ne.cdPessoaFilial = i.cdPessoaFilial
WHERE ne.dtChegada >= DATEADD(day, -{janela_entradas}, CAST(GETDATE() AS date))
  -- nota com cdProduto NULL existe na base real (achada em 17/07 pelo dry-run
  -- da exposicao: virava linha com codigo vazio no CSV e derrubava o consumidor)
  AND i.cdProduto IS NOT NULL
GROUP BY i.cdProduto, CAST(ne.dtChegada AS date)
ORDER BY codigo, data
"""

# VALIDADES: as 2 validades mais recentes de cada produto, para a cotacao (o app
# mostra as 2 datas por produto e marca com ⚠ a que vence em <45 dias; sem
# validade nao mostra nada; com uma so, mostra uma).
#
# FONTE (schema confirmado + fingerprint 2026-07-17): a validade vem da
# RASTREABILIDADE da NF-e recebida — `dbo.tbNotaFiscalItemRastro.dVal` (grupo
# "rastro" do padrao NF-e: nLote/qLote/dFab/dVal). NAO esta em tbNotaItem, nem no
# WMS (vazio), nem na conferencia cega (vazia). Liga ao produto por
# cdNota + nItem(=cdNotaItem), e a data de chegada vem de tbNotaEntrada.
# Cobertura medida: 241 produtos com dVal (os que o fornecedor declara na NF-e).
#
# LIMITE CONHECIDO: validade DIGITADA a mao no recebimento (ex.: produto 19047 da
# auditoria) NAO entra por aqui — nao gera linha de rastro. Se for preciso cobrir
# as manuais, achar/uni-la a fonte manual e fazer UNION (pendente de decisao).
#
# Desenho: por produto, as 2 validades DISTINTAS mais recentes, unindo TRES fontes
# (medido 2026-07-17 — uniao = 3807 produtos, ~82% do catalogo):
#   1) tbWmsCargaItem.dtValidade — CONFERENCIA do recebimento (a mais completa,
#      3594 produtos; recencia = dtItemConferido, 100% preenchido). ATENCAO: o WMS
#      "Movimento"/"Inventario" esta VAZIO, mas as tabelas "Carga" NAO — e aqui que
#      a validade digitada no recebimento fica (cobre ex. o produto 19047).
#   2) tbGestaoValidade.dtValidade — modulo Gestao Validade (1281; rec = dtInclusao);
#   3) tbNotaFiscalItemRastro.dVal — rastro da NF-e do fornecedor (241; rec = chegada).
# Deduplica por (produto, validade) pela maior recencia; rn<=2 pega as 2 mais
# recentes por produto. A projecao (projections.vd) reordena p/ MENOR primeiro.
VALIDADES = """
WITH carga_dia AS (
    -- fonte AUTORIDADE: conferencia do recebimento, agrupada por DIA. Duas notas
    -- do mesmo dia (ex.: 10cx + 15cx do mesmo fornecedor) = UM recebimento so.
    SELECT ci.cdProduto AS codigo,
           CAST(ci.dtItemConferido AS date) AS dia,
           CAST(ci.dtValidade AS date) AS validade
    FROM dbo.tbWmsCargaItem ci
    WHERE ci.dtValidade IS NOT NULL AND ci.cdProduto IS NOT NULL
      AND ci.dtItemConferido >= DATEADD(day, -{janela_entradas}, CAST(GETDATE() AS date))
    GROUP BY ci.cdProduto, CAST(ci.dtItemConferido AS date), CAST(ci.dtValidade AS date)
),
carga AS (
    -- validades DISTINTAS dos 2 DIAS de recebimento mais recentes. Se os 2 dias
    -- tiverem a mesma validade, sai so 1 (nao volta atras p/ estoque antigo).
    SELECT codigo, validade, MAX(dia) AS recencia
    FROM (
        SELECT codigo, validade, dia,
               DENSE_RANK() OVER (PARTITION BY codigo ORDER BY dia DESC) AS dr
        FROM carga_dia
    ) x
    WHERE dr <= 2
    GROUP BY codigo, validade
),
fallback AS (
    -- RESERVA: so vale para produto que NAO tem conferencia (senao poluiria a
    -- ordem dos "ultimos recebimentos" com recencia de escala diferente).
    SELECT codigo, validade, MAX(recencia) AS recencia
    FROM (
        SELECT gv.cdProduto AS codigo, CAST(gv.dtValidade AS date) AS validade,
               gv.dtInclusao AS recencia
        FROM dbo.tbGestaoValidade gv
        WHERE gv.dtValidade IS NOT NULL AND gv.cdProduto IS NOT NULL
          AND gv.dtInclusao >= DATEADD(day, -{janela_entradas}, CAST(GETDATE() AS date))
        UNION ALL
        SELECT i.cdProduto AS codigo, CAST(r.dVal AS date) AS validade,
               ne.dtChegada AS recencia
        FROM dbo.tbNotaFiscalItemRastro r
        JOIN dbo.tbNotaItem i
          ON i.cdNota = r.cdNota AND i.cdNotaItem = r.nItem
         AND i.cdPessoaFilial = r.cdPessoaFilial
        JOIN dbo.tbNotaEntrada ne
          ON ne.cdNotaEntrada = i.cdNota AND ne.cdPessoaFilial = i.cdPessoaFilial
        WHERE r.dVal IS NOT NULL AND i.cdProduto IS NOT NULL
          AND ne.dtChegada >= DATEADD(day, -{janela_entradas}, CAST(GETDATE() AS date))
    ) u
    GROUP BY codigo, validade
),
todas AS (
    SELECT codigo, validade, recencia FROM carga
    UNION ALL
    SELECT f.codigo, f.validade, f.recencia FROM fallback f
    WHERE NOT EXISTS (SELECT 1 FROM carga c WHERE c.codigo = f.codigo)
)
SELECT codigo, validade FROM (
    SELECT codigo, validade,
           ROW_NUMBER() OVER (PARTITION BY codigo
                              ORDER BY recencia DESC, validade DESC) AS rn
    FROM todas
) t
WHERE rn <= 2
ORDER BY codigo, validade
"""

# PEDIDOS_VENDA: itens dos pedidos de venda/DAV emitidos (dtAtendido) nos
# ultimos {janela_pedidos_venda} dias — replica o rptPedidosVendaEmitidaDAV
# PorItens e alimenta a AUDITORIA DE DESCONTO do app de cotacao (que hoje
# depende de exportar esse relatorio a mao). Precos/custos por volume viram
# por unidade no proprio SELECT quando faz sentido (custo_un).
PEDIDOS_VENDA = """
SELECT
    p.cdPedido                                 AS pedido,
    CAST(p.dtAtendido AS date)                 AS emissao,
    pv.NrDAVPDV                                AS dav,
    ps.nmPessoa                                AS cliente,
    vd.nmVendedor                              AS vendedor,
    i.cdProduto                                AS codigo,
    sp.nmProdutoPai                            AS produto,
    RTRIM(i.cdEmbalagem)
      + CASE WHEN i.qtEmbalagem > 1
             THEN '-' + CAST(CAST(i.qtEmbalagem AS int) AS varchar(10))
             ELSE '' END                       AS emb,
    CAST(i.qtEmbalagem AS int)                 AS unidades_por_emb,
    CAST(i.qtPedidoItem AS decimal(14,2))      AS qtde,
    CAST(i.vlPedidoItem AS decimal(14,2))      AS valor,
    CAST(i.vlVendaOriginal AS decimal(14,2))   AS valor_tabela,
    CAST(i.vlCusto / NULLIF(i.qtEmbalagem, 0) AS decimal(14,4)) AS custo_un
FROM dbo.tbPedido p
JOIN dbo.tbPedidoVenda pv  ON pv.cdPedidoVenda = p.cdPedido
                          AND pv.cdPessoaFilial = p.cdPessoaFilial
JOIN dbo.tbPedidoItem i    ON i.cdPedido = p.cdPedido
                          AND i.cdPessoaFilial = p.cdPessoaFilial
JOIN dbo.tbProduto pr      ON pr.cdProduto = i.cdProduto
JOIN dbo.tbSuperProduto sp ON sp.cdSuperProduto = pr.cdSuperProduto
JOIN dbo.tbPessoa ps       ON ps.cdPessoa = pv.cdPessoaComercial
LEFT JOIN dbo.tbPedidoVendedor vd ON vd.cdVendedor = pv.cdVendedor
WHERE p.inEntrada = 0
  AND p.dtAtendido >= DATEADD(day, -{janela_pedidos_venda}, CAST(GETDATE() AS date))
ORDER BY emissao, vendedor, cliente, pedido, i.cdPedidoItem
"""

# HISTORICO_CLIENTE: itens dos pedidos de venda/DAV por CLIENTE nos ultimos
# {historico_meses} meses — insumo do app recuperacao-itens (Recuperar+Ampliar).
# Mesmas convencoes do PEDIDOS_VENDA (emissao = dtAtendido; vlPedidoItem/vlCusto
# POR VOLUME -> totais da linha = x qtPedidoItem; unidades = x qtEmbalagem).
# grupo = familia mercadologica = VW_MGN_PRODUTO.Departamento (ver cabecalho).
HISTORICO_CLIENTE = """
SELECT
    LTRIM(RTRIM(ps.nmPessoa))                  AS cliente,
    i.cdProduto                                AS codigo,
    sp.nmProdutoPai                            AS produto,
    CAST(p.dtAtendido AS date)                 AS data,
    RTRIM(i.cdEmbalagem)
      + CASE WHEN i.qtEmbalagem > 1
             THEN '-' + CAST(CAST(i.qtEmbalagem AS int) AS varchar(10))
             ELSE '' END                       AS emb,
    CAST(i.qtEmbalagem AS int)                 AS unidades_por_emb,
    CAST(i.qtPedidoItem AS decimal(14,3))      AS qtde_emb,
    CAST(i.qtPedidoItem * i.qtEmbalagem AS decimal(14,3))  AS unidades,
    CAST(i.qtPedidoItem * i.vlPedidoItem AS decimal(14,2)) AS valor,
    CAST(i.qtPedidoItem * i.vlCusto AS decimal(14,2))      AS custo,
    RTRIM(COALESCE(mg.Departamento, ''))       AS grupo
FROM dbo.tbPedido p
JOIN dbo.tbPedidoVenda pv  ON pv.cdPedidoVenda = p.cdPedido
                          AND pv.cdPessoaFilial = p.cdPessoaFilial
JOIN dbo.tbPedidoItem i    ON i.cdPedido = p.cdPedido
                          AND i.cdPessoaFilial = p.cdPessoaFilial
JOIN dbo.tbProduto pr      ON pr.cdProduto = i.cdProduto
JOIN dbo.tbSuperProduto sp ON sp.cdSuperProduto = pr.cdSuperProduto
JOIN dbo.tbPessoa ps       ON ps.cdPessoa = pv.cdPessoaComercial
LEFT JOIN dbo.VW_MGN_PRODUTO mg ON mg.CodigoProduto = i.cdProduto
WHERE p.inEntrada = 0
  AND COALESCE(ps.inMorto, 0) = 0
  AND i.qtPedidoItem > 0  -- item zerado no pedido nao e compra (26% das linhas em 07/2026)
  AND p.dtAtendido >= DATEADD(month, -{historico_meses}, CAST(GETDATE() AS date))
ORDER BY cliente, codigo, data
"""

PEDIDOS = """
SELECT
    i.cdProduto                                        AS codigo,
    CAST(p.dtPedido AS date)                           AS data_pedido,
    CAST(SUM((i.qtPedidoItem - COALESCE(i.qtAtendida, 0)) * i.qtEmbalagem)
         AS decimal(14,3))                             AS qtd_pedida,
    CASE WHEN SUM(COALESCE(i.qtAtendida, 0)) > 0
         THEN 'parcial' ELSE 'aberto' END              AS status,
    CAST(MAX(pc.dtEntregaPrevista) AS date)            AS previsao_entrega
FROM dbo.tbPedidoItem i
JOIN dbo.tbPedido p
  ON p.cdPedido = i.cdPedido AND p.cdPessoaFilial = i.cdPessoaFilial
LEFT JOIN dbo.tbPedidoCompra pc
  ON pc.cdPedidoCompra = p.cdPedido AND pc.cdPessoaFilial = p.cdPessoaFilial
WHERE p.inEntrada = 1
  AND p.dtAtendido IS NULL
  AND COALESCE(i.inAtendido, 0) = 0
GROUP BY i.cdProduto, CAST(p.dtPedido AS date)
HAVING SUM((i.qtPedidoItem - COALESCE(i.qtAtendida, 0)) * i.qtEmbalagem) > 0
ORDER BY codigo, data_pedido
"""

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
# Historico do DORSAL: desde 2026-01-22 (~125 dias uteis). Menor que o do
# tbVendaPDV (2023), mas e o unico que permite excluir o atacado — que e
# 35% do volume (medido em 30 dias; a amostra de 3 dias dava 44%).
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

# PRE_PEDIDOS: pre-pedidos ABERTOS (nao encerrados e ainda sem pedido de
# compra gerado) feitos nos ultimos {prepedido_dias} dias — janela do painel
# (dono, 21/07). FONTE (medida 2026-07-21): tbPrePedido (fornecedor em
# cdPessoaComercial, encerrado em inEncerrado, conversao em cdPedidoCompra)
# + tbPrePedidoItem (valor = qtPedida x vlEmbalagem).
PRE_PEDIDOS = """
SELECT pp.cdPrePedido                              AS pre_pedido,
       LTRIM(RTRIM(COALESCE(ps.nmPessoa, '')))     AS fornecedor,
       CAST(pp.dtPrePedido AS date)                AS data_pre,
       CAST(pp.dtLimite AS date)                   AS limite,
       COUNT(i.cdPrePedidoItem)                    AS itens,
       CAST(SUM(i.qtPedida * i.vlEmbalagem) AS decimal(14,2)) AS valor
FROM dbo.tbPrePedido pp
LEFT JOIN dbo.tbPessoa ps ON ps.cdPessoa = pp.cdPessoaComercial
LEFT JOIN dbo.tbPrePedidoItem i
  ON i.cdPrePedido = pp.cdPrePedido AND i.cdPessoaFilial = pp.cdPessoaFilial
WHERE COALESCE(pp.inEncerrado, 0) = 0
  AND pp.cdPedidoCompra IS NULL
  AND pp.dtPrePedido >= DATEADD(day, -{prepedido_dias}, CAST(GETDATE() AS date))
GROUP BY pp.cdPrePedido, ps.nmPessoa, CAST(pp.dtPrePedido AS date),
         CAST(pp.dtLimite AS date)
ORDER BY data_pre DESC
"""

# REC_SELLOUT: verbas de sell-out por promocao x produto — replica o
# rptReceitaSellOutDetalhe do ERP p/ o quadrante "Verba SellOut" do painel.
# FONTE (medida 2026-07-21): tbPromocaoItem.vlVerbaComercial = verba UNITARIA
# ("SellOut" do relatorio); dtPagamentoReceitaSellOut = VENCIMENTO da receita;
# cdPessoaPagaSellOut -> tbPessoa = fornecedor pagador. O TOTAL acumula em
# tbVendaPDV.vlSellOut a cada cupom vendido na vigencia (medido: 1.119 cupons
# desde 02/2026; ensaio da query = 218 linhas, 193 vencidas, R$ 4.823,81).
# STATUS DE PAGAMENTO (baixa do financeiro) nao foi encontrado no schema —
# o painel mostra vencidas com total > 0; refinamento fica p/ quando a conta
# de baixa for localizada.
REC_SELLOUT = """
WITH verba AS (
    SELECT v.cdPromocao, pr.cdSuperProduto,
           CAST(SUM(v.vlSellOut) AS decimal(14,2)) AS total
    FROM dbo.tbVendaPDV v
    JOIN dbo.tbProduto pr ON pr.cdProduto = v.cdProduto
    WHERE v.vlSellOut > 0
    GROUP BY v.cdPromocao, pr.cdSuperProduto
)
SELECT sp.nmProdutoPai                                 AS produto,
       p.nmPromocao                                    AS promocao,
       RTRIM(COALESCE(tp.nmTipoPromocao, ''))          AS tipo_promocao,
       LTRIM(RTRIM(COALESCE(ps.nmPessoa, '')))         AS fornecedor,
       CAST(p.dtInicio AS date)                        AS inicio,
       CAST(p.dtFim AS date)                           AS fim,
       CAST(pi.dtPagamentoReceitaSellOut AS date)      AS vencimento,
       CAST(pi.vlVerbaComercial AS decimal(14,2))      AS verba_un,
       COALESCE(ve.total, 0)                           AS total
FROM dbo.tbPromocaoItem pi
JOIN dbo.tbPromocao p
  ON p.cdPromocao = pi.cdPromocao AND p.cdEmpresa = pi.cdEmpresa
LEFT JOIN dbo.tbPromocaoTipo tp ON tp.cdTipoPromocao = p.cdTipoPromocao
LEFT JOIN dbo.tbPessoa ps ON ps.cdPessoa = pi.cdPessoaPagaSellOut
JOIN dbo.tbSuperProduto sp ON sp.cdSuperProduto = pi.cdSuperProduto
LEFT JOIN verba ve
  ON ve.cdPromocao = pi.cdPromocao AND ve.cdSuperProduto = pi.cdSuperProduto
WHERE pi.dtPagamentoReceitaSellOut IS NOT NULL
ORDER BY vencimento, produto
"""
