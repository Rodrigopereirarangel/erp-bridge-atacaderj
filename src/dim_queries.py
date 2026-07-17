# -*- coding: utf-8 -*-
"""SELECTs do dimensionamento de caixas (SOMENTE LEITURA).

Fonte: DORSAL.tbCupom (frente de caixa). O dbo.tbVendaPDV do Solidcon NAO
serve aqui: nao tem numero de PDV nem operador.

Fatos verificados em 2026-07-17 (ver o spec):
- COUNT(*) de tbCupom por dia bate EXATO com SUM(qtCupom) de
  DORSAL.tbConsPDVOperador (10/07=908, 11/07=946, 13/07=555, 14/07=567,
  15/07=673, 16/07=750). E a prova de que a fonte esta certa.
- tbCupomCancelado e tabela SEPARADA, mesmo formato. O cupom cancelado
  consumiu tempo real de caixa -> entra na demanda.
- HoraInicio/HoraFim 100% preenchidas, nenhuma invertida (18.708 cupons/30d).
- Horas em fuso local (servidor UTC-3); nao ha deslocamento a corrigir.
- PDV 11/12 = atacado (~29s/cupom vs ~110s do varejo): outra operacao.
- Operador 7000: 4 dias, span 1h, 12 cupons/dia -> login de fiscal, nao caixa.
- Domingo nao existe na base (loja fechada); DATEPART(weekday)=1 = domingo.
"""

# {desde} e substituido em runtime (data inicial, 'YYYY-MM-DD').
CUPONS = """
SELECT
    CAST(dtCupom AS date)      AS dia,
    DATEPART(weekday, dtCupom) AS dow,
    cdPDV                      AS pdv,
    cdOperador                 AS operador,
    HoraInicio                 AS inicio,
    HoraFim                    AS fim,
    0                          AS cancelado
FROM DORSAL.dbo.tbCupom
WHERE cdFilial = 1
  AND cdPDV NOT IN (11, 12)
  AND cdOperador <> 7000
  AND DATEPART(weekday, dtCupom) <> 1
  AND dtCupom >= '{desde}'
  AND HoraInicio IS NOT NULL AND HoraFim IS NOT NULL
  AND HoraFim >= HoraInicio
UNION ALL
SELECT
    CAST(dtCupom AS date)      AS dia,
    DATEPART(weekday, dtCupom) AS dow,
    cdPDV                      AS pdv,
    cdOperador                 AS operador,
    HoraInicio                 AS inicio,
    HoraFim                    AS fim,
    1                          AS cancelado
FROM DORSAL.dbo.tbCupomCancelado
WHERE cdFilial = 1
  AND cdPDV NOT IN (11, 12)
  AND cdOperador <> 7000
  AND DATEPART(weekday, dtCupom) <> 1
  AND dtCupom >= '{desde}'
  AND HoraInicio IS NOT NULL AND HoraFim IS NOT NULL
  AND HoraFim >= HoraInicio
ORDER BY dia, inicio
"""

# Prova contabil: o consolidado do proprio ERP. Conferir contra os NAO
# cancelados (tbConsPDVOperador.qtCupom nao conta cancelado).
CONFERENCIA_CONSOLIDADO = """
SELECT CAST(o.dtVenda AS date) AS dia, SUM(o.qtCupom) AS cupons
FROM DORSAL.dbo.tbConsPDVOperador o
WHERE o.cdFilial = 1
  AND o.cdPDV NOT IN (11, 12)
  AND o.cdOperador <> 7000
  AND o.dtVenda >= '{desde}'
GROUP BY CAST(o.dtVenda AS date)
ORDER BY dia
"""
