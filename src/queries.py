# -*- coding: utf-8 -*-
"""Os 4 SELECTs da ponte.

>>> AQUI e o unico lugar que amarra ao ERP. <<<
Cada query DEVE devolver as colunas canonicas documentadas em
docs/CONTRATO-DE-DADOS.md (use `AS` para renomear). Os nomes de TABELA e
COLUNA abaixo sao PLACEHOLDERS marcados com  --TODO:  — a gente troca juntos
pelos nomes reais do seu banco. Enquanto nao trocar, rode com --demo.

`{janela}` e substituido em runtime pela janela em dias (config.janela_dias).
"""

CATALOGO = """
SELECT
    p.codigo        AS codigo,
    p.descricao     AS descricao,
    p.embalagem     AS embalagem,      -- qtd por caixa / fator (OPCIONAL)      --TODO
    p.custo         AS custo_atual,     -- custo corrente do cadastro (cotacao/pricing) --TODO
    p.preco_atacado AS preco_atacado,                                            --TODO
    p.preco_varejo  AS preco_varejo,                                             --TODO
    p.preco_promo   AS preco_promocao,  -- preco de promocao GUARDADO no ERP     --TODO
    p.curva         AS curva,                                                     --TODO
    p.ativo         AS ativo
FROM produtos p                                                                  --TODO
WHERE p.ativo = 1
ORDER BY p.descricao
"""

VENDAS = """
SELECT
    i.produto_codigo     AS codigo,                                              --TODO
    p.descricao          AS descricao,                                           --TODO
    DATE(v.data_emissao) AS data,                                                --TODO
    SUM(i.quantidade)               AS qtd_vendida,                             --TODO
    SUM(i.valor_total)              AS valor,       -- receita R$ do dia         --TODO
    SUM(i.quantidade * i.custo_no_pedido) AS custo_venda  -- CMV do dia (custo congelado no pedido) --TODO
FROM vendas v                                                                    --TODO
JOIN vendas_itens i ON i.venda_id = v.id                                         --TODO
JOIN produtos p     ON p.codigo = i.produto_codigo                              --TODO
WHERE v.data_emissao >= CURDATE() - INTERVAL {janela} DAY
  AND v.status = 'faturada'                                                      --TODO
GROUP BY i.produto_codigo, p.descricao, DATE(v.data_emissao)
ORDER BY codigo, data
"""

# ENTRADAS: uma linha por entrega (NAO agrega) nos ultimos {janela_entradas} dias
# (~6 meses). E o "proxy de estoque": como o ERP nao tem saldo, cruzar o giro
# (vendas) com as ultimas entregas estima a cobertura restante. Dela tambem se
# deriva o recebimentos.csv (ultima entrega por item) para o detector de salao.
ENTRADAS = """
SELECT
    i.produto_codigo     AS codigo,                                              --TODO
    DATE(e.data_entrada) AS data,                                                --TODO
    i.quantidade         AS qtd                                                  --TODO
FROM entradas e                                                                  --TODO
JOIN entradas_itens i ON i.entrada_id = e.id                                     --TODO
WHERE e.data_entrada >= CURDATE() - INTERVAL {janela_entradas} DAY
ORDER BY i.produto_codigo, e.data_entrada
"""

PEDIDOS = """
SELECT
    i.produto_codigo    AS codigo,                                               --TODO
    pc.data_pedido      AS data_pedido,                                          --TODO
    i.quantidade        AS qtd_pedida,                                           --TODO
    pc.status           AS status,                                               --TODO
    pc.previsao_entrega AS previsao_entrega                                      --TODO
FROM pedidos_compra pc                                                           --TODO
JOIN pedidos_compra_itens i ON i.pedido_id = pc.id                               --TODO
WHERE pc.status IN ('aberto', 'parcial')  -- so o que ainda nao chegou           --TODO
"""
