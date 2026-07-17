# Escala de caixas — banco de horas (decisão do dono, 17/07/2026)

> **MOVIDO (17/07):** a escala oficial e viva agora mora no repo
> [`escala`](https://github.com/Rodrigopereirarangel/escala) —
> `frente-de-loja-pdv/ESCALA.md` (estrutura completa da frente: 12 postos /
> 13 pessoas, com balcão de atacado, conferência e gerência) e `DECISOES.md`
> (histórico do porquê). Este arquivo fica como registro histórico do
> dimensionamento dos caixas do varejo; o motor de cálculo continua aqui
> (`src/dimensionamento_caixas.py` + `src/dim_*.py`).

Meta: **95% dos clientes com espera < 5min**, todos os dias, dimensionado no
P85 (dia forte) sobre 6 meses de cupons reais. Quadro: **11 operadoras**
(mínimo 10), banco de horas já vigente na loja. Férias (~1 sempre fora) e
faltas medidas (7,4%) já estão na conta: ~10 ativas por dia.

**Regra de véspera:** véspera e emenda de feriado usam a grade de SÁBADO
(comprovado no backtest: 05/06 pós-Corpus Christi e 10/07 tiveram volume de
sábado e estouraram a grade de sexta).

**Dezembro:** fora desta escala — camada de temporárias (dados de dez não
estão na amostra).

## Grade de entradas por dia (postos de caixa)

| Dia | Entradas (hora × quantas) | No caixa | Salão/compensação |
|---|---|---|---|
| Segunda | 05:30×2 · 06:00×1 · 09:30×1c · 10:30×2c | 6 | ~4 |
| Terça | 05:30×2 · 06:00×1 · 06:30×1 · 09:30×2 | 6 | ~4 |
| Quarta | 05:30×2 · 06:00×1 · 06:30×1 · 09:00×1 · 10:00×1 | 6 | ~4 |
| Quinta | 05:30×3 · 06:30×1 · 08:00×1 · 09:30×2c | 7 | ~3 |
| Sexta | 05:30×2 · 06:00×1 · 06:30×1 · 08:00×1 · 09:30×2c | 7 | ~3 |
| **Sábado** | 05:30×3L · 06:00×1L · 06:30×1 · 07:30×1 · 09:30×2c | 8 | ~2 |

`L` = dia longo (gera crédito no banco) · `c` = dia curto (compensação/débito).

**Grades VALIDADAS POR SIMULAÇÃO contra os dias históricos (17/07)** — % de
dias que batem 95%<5min: seg-6 88% · ter-6 96% · qua-6 96% (com 7 dava os
MESMOS 96%: a 7ª era redundante) · qui-7 88% · sex-7 92% · sáb-8 88%.
Enxugar mais degrada: seg-5 79%, ter-5 65%, sáb-7 com almoço legal 79%.
**O 8º do sábado é o almoço**: sáb-7 sem almoço dá os mesmos 88% do sáb-8 —
ou seja, tirar o 8º = voltar a suprimir o intervalo (ilegal, prática antiga).
A 1ª versão da grade de sexta (8 pessoas) tinha um buraco às 06:30 que a
simulação pegou — grade à mão sem simular não vale.

## Sábado em detalhe (o dia que dita tudo)

| Entrada | Quantas | Jornada | Banco |
|---|---|---|---|
| 05:30 | 3 | 9h trabalho + 1h almoço (sai 15:30) | **+1h40** cada |
| 06:00 | 1 | 8h30 + 1h almoço | +1h10 |
| 06:30 | 1 | 8h + 1h almoço | +0h40 |
| 07:30 | 1 | 7h20 + 1h almoço | 0 |
| 09:30 | 2 | 5h30 + pausa 15min (sai 15:15) | −1h50 cada |

Cobre a curva inteira: 3 caixas às 5:30 → 7 no pico (10:00–11:30) → 6 à tarde
→ 5 no fechamento. **Almoços de 1h SEMPRE no vale 12:00–15:00, revezados
(máx. 2 fora ao mesmo tempo), NUNCA entre 10:00 e 11:30.** Jornada máxima 9h
(teto legal 2h extra/dia respeitado com folga de 20min).

## Regras do banco de horas

1. Quem fez sábado LONGO entra 2h mais tarde na segunda seguinte (zera).
2. Quem fez sábado curto quita o débito nos floats de qui/sex da semana.
3. Papéis giram em rodízio semanal (controle no ponto, saldo zera no mês).
4. **Almoço de 1h acima de 6h de trabalho é inegociável** — não entra no
   banco. (Hoje o registro mostra jornadas de sábado sem pausa visível; esta
   escala corrige isso.)
5. Semana típica por pessoa: ~44h (5 dias cheios de 7h20 + 1 papel variável).

## Conferência da conta

- Sábado consome ~57,5 horas-caixa; esta grade entrega ~58 — desperdício ~0
  (a grade antiga de turnos fixos entregava 84h: 31% de sobra).
- Semana: 40 postos-dia de caixa ÷ ~10 ativas = 4 dias de caixa por pessoa;
  o resto (~20 pessoa-dias/semana) vai para reposição/salão — a polivalência
  (sem limpeza pesada; função registrada em contrato).
- Abertura corrigida: 2–3 caixas às 05:30–06:30 (hoje abrem 5–6; sobravam
  até +3).

## Origem dos números

`src/dimensionamento_caixas.py` (5min/95%, P85, handover 36s) + probes de
17/07: validado contra Erlang-C, itens×tempo, faturamento frente×retaguarda
(30/30 dias a 0,00%), backtest jan-abr→mai-jul e jackknife mensal.
Spec: `docs/superpowers/specs/2026-07-17-dimensionamento-caixas-design.md`.
