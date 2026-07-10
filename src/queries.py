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

`{janela}` / `{janela_entradas}` sao substituidos em runtime (config).
"""

CATALOGO = """
SELECT
    p.cdProduto                      AS codigo,
    sp.nmProdutoPai                  AS descricao,
    pr.embalagem,
    pr.qtde_atacado,
    pr.custo_atual,
    pr.preco_atacado,
    pr.preco_varejo,
    pr.preco_promocao,
    e.CURVA_ABC                      AS curva,
    1                                AS ativo
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

# VENDAS_MENSAL: total de UNIDADES vendidas por produto em cada MES FECHADO
# dos ultimos {meses_fechados} meses (o mes corrente fica de fora de proposito).
# qtVenda do tbVendaPDV ja e em UNIDADES — validado em 2026-07-10: caixa de 12
# vendida no atacado aparece como 12/24 unidades com vlVenda UNITARIO (17,09
# atacado vs 19,49 varejo no mesmo produto); as qtVenda fracionadas (0,264...)
# sao itens de balanca (kg). Alimenta o dashboard saida/dashboard/vendas_mensal.html.
VENDAS_MENSAL = """
SELECT
    v.cdProduto                                    AS codigo,
    MAX(sp.nmProdutoPai)                           AS descricao,
    CONVERT(char(7), v.dtVenda, 126)               AS mes,
    CAST(SUM(v.qtVenda) AS decimal(14,3))          AS qtd_un
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
GROUP BY i.cdProduto, CAST(ne.dtChegada AS date)
ORDER BY codigo, data
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
