# Dimensionamento de caixas e operadoras por dia da semana — design

**Data:** 2026-07-17
**Status:** aprovado pelo dono (brainstorming de 17/07)

## Pergunta a responder

Quantos PDVs (mínimo e máximo ao longo do dia) e quantas operadoras por dia da
semana a loja precisa para escoar os cupons com **95% dos clientes esperando
menos de 3 minutos na fila**, cortando a ociosidade que existe hoje.

**A meta é aplicada POR FAIXA de 30 min, não no agregado do dia.** É o corte
mais rigoroso e é o certo aqui: no agregado, o vale das 6h (fila zero) compensaria
o pico das 10h e o número sairia bonito com fila real no pico — exatamente o que
a pergunta quer evitar.

Decisões do dono no brainstorming:
- Meta de serviço: **95% dos clientes com espera < 3 min** (não 5).
- Margem de segurança: escala dimensionada para o **dia P85** de cada dia da
  semana, com **stress de ±10%** na demanda reportado junto.
- Jornada: **CLT 6h** (6h20 diárias com 20 min de intervalo).
- Entregar **as duas coisas**: a curva de caixas simultâneos por faixa e o
  headcount de operadoras por dia da semana.

## Fatos do schema (levantados e verificados em 2026-07-17)

Descobertos nesta rodada; complementam o cabeçalho de `src/queries.py`.

- **`dbo.tbVendaPDV` (Solidcon) NÃO serve** para esta análise: não tem número de
  PDV nem operador. Só produto/data/hora.
- **`DORSAL.dbo.tbCupom` é a fonte certa.** Colunas que importam:
  `cdFilial`, `cdPDV`, `nrCupom`, `dtCupom` (datetime, só a data),
  `cdOperador`, `HoraInicio`, `HoraUltimoItem`, `HoraFim` (datetimes cheios).
- **Validada contra o próprio ERP:** `COUNT(*)` de `tbCupom` por dia bate
  **exato** com `SUM(qtCupom)` de `DORSAL.dbo.tbConsPDVOperador`
  (10/07=908, 11/07=946, 13/07=555, 14/07=567, 15/07=673, 16/07=750).
- **`DORSAL.dbo.tbCupomCancelado` é uma tabela SEPARADA**, com o mesmo formato
  (inclusive `HoraInicio`/`HoraFim`). Cupom cancelado **consumiu tempo real de
  caixa** → tem que entrar na demanda. Ignorá-la subdimensiona.
- Qualidade dos timestamps (30 dias): 18.708 cupons, **0** sem `HoraInicio`,
  **0** sem `HoraFim`, **0** com `HoraFim < HoraInicio`.
- Histórico disponível: **2026-01-22 a 2026-07-17**, 102.687 cupons, 11 PDVs,
  20 operadores.
- **Fuso conferido**: servidor SQL em UTC-3 (`GETDATE()` 09:25 vs `GETUTCDATE()`
  12:25) e o último cupom do dia bate com o relógio. As horas são locais; não há
  deslocamento a corrigir.
- **Loja opera ~05:30–15:00, segunda a sábado.** Domingo não existe na base
  (`DATEPART(weekday)` nunca retorna 1). Pico às 10h–11h.
- **PDV 10 não existe.**

## Recorte dos dados

| Filtro | Valor | Motivo |
|---|---|---|
| `cdFilial` | 1 | a loja |
| `cdPDV` | **exclui 11 e 12** | atacado, operação que não mistura |
| `cdOperador` | **exclui 7000** | não-operacional |
| Dia da semana | exclui domingo | loja fechada |
| Período | 2026-01-22 → 2026-07-17 | todo o histórico |

**PDV 11/12 — a exclusão pedida pelo dono é confirmada pelos dados:** eles têm
só 2 operadores e **~28-30s por cupom**, contra **~107-136s** dos PDVs 1-9. É
outra operação, com outra distribuição de serviço. Misturar contaminaria o
tempo de atendimento.

**Operador 7000** aparece em 4 dias, span de 1h, 12 cupons/dia — perfil de login
de fiscal/supervisor, não de operadora. Excluído. *A confirmar com o dono; se
for operadora de verdade, reincluir.*

## A armadilha do almoço (confirmada nos dados)

O dono avisou: no almoço abre-se **outro PDV** em vez do mesmo, para não
misturar fundo de caixa. Os dados confirmam com assinatura inequívoca — em
**208 casos operador-dia dos últimos 30 dias**:

- todo operador usou **exatamente 1 PDV** no dia (nenhum caso de 2+);
- todo PDV teve **exatamente 1 operador** no dia (nenhum caso de 2+).

É o mapeamento 1:1 que a troca descrita produz: a rendição senta num PDV novo,
com o fundo dela. **Consequência metodológica:** os 8-9 "PDVs distintos no dia"
**não são** 8-9 caixas simultâneos — PDV 8 e 9 abrem só em parte dos dias
(16 e 12 de 26) e majoritariamente no miolo do dia. Contar PDV distinto por dia
superestima a capacidade. **Toda a análise é por faixa de 30 min.**

## A ociosidade (o que motivou a pergunta)

Ocupação medida nos últimos 30 dias (tempo passando cupom ÷ span do turno):

| Operador | Dias | Span médio | Horas atendendo | Ocupação |
|---|---|---|---|---|
| 4 | 27 | 7,3h | 3,2h | 43,7% |
| 3 | 26 | 7,1h | 2,5h | 35,1% |
| 8 | 26 | 7,1h | 3,1h | 42,4% |
| 20 | 25 | 7,2h | 2,5h | 34,9% |
| 23 | 23 | 6,5h | 2,8h | 45,3% |

**Ressalva que o relatório deve carregar:** 100% de ocupação num caixa é
impossível sem fila infinita — a folga é o que segura a espera baixa. 35% é
folga demais para meta de 3 min, mas o número-alvo sai do modelo, não de uma
meta de ocupação arbitrária.

## Demanda por dia da semana (90 dias, PDV 1-9)

| Dia | Dias | Cupons médio | Cupons máx | PDVs distintos/dia (méd) |
|---|---|---|---|---|
| Segunda | 13 | 532 | 617 | 6,7 |
| Terça | 12 | 607 | 717 | 7,3 |
| Quarta | 13 | 647 | 790 | 7,9 |
| Quinta | 12 | 666 | 839 | 8,0 |
| Sexta | 12 | 710 | 908 | 8,0 |
| Sábado | 13 | 885 | 1.066 | 8,1 |

Gradiente limpo de segunda a sábado. A dispersão dentro do mesmo dia da semana
(sábado de 700 vs sábado de 1.066) é **exatamente o que a margem P85 endereça**.

## Método

### Princípio: eliminar o erro, não paddear em cima dele

Catalogamos 9 fontes de erro. **Oito puxam para subdimensionar**, uma só para
superdimensionar. O erro é **assimétrico** — logo a margem é **de um lado só**.

| # | Fonte de erro | Direção | Tratamento |
|---|---|---|---|
| 1 | Chegada medida no *início do cupom*, não na entrada da fila (demanda censurada) | subdimensiona | **medir** saturação; rotular faixa saturada como piso |
| 2 | `tbCupomCancelado` fora da conta | subdimensiona | **corrigir**: incluir a tabela |
| 3 | Handover (troca de cliente) não medido | subdimensiona | **corrigir**: estimar dos gaps reais |
| 4 | Chegadas em rajada vs Poisson | subdimensiona | **eliminar**: simular chegadas reais |
| 5 | Fila herdada entre faixas | subdimensiona | **eliminar**: simular o dia contínuo |
| 6 | Operadoras heterogêneas (65 a 112 cupons/dia) | subdimensiona | **eliminar**: velocidade individual na simulação |
| 7 | Faixa de 30min esconde rajada de 10min | subdimensiona | **eliminar**: simulação é a evento, não a faixa |
| 8 | Serviço menos variável que exponencial | *super*dimensiona | **eliminar**: distribuição empírica |
| 9 | Dia médio vs dia ruim | subdimensiona | **margem**: dimensionar no P85 |

Uma margem em cima de Erlang-C seria chutar um número para compensar erros que
**dá para simplesmente não cometer**. Com 102 mil cupons timestampados, a
simulação elimina 4, 5, 6, 7 e 8. Sobram 1 (medir), 2 e 3 (corrigir) e 9 (margem).

### Componentes

Unidades pequenas, testáveis isoladamente:

1. **`extracao`** — SELECT em `tbCupom` ∪ `tbCupomCancelado` com o recorte acima.
   Saída: registros `(dia, dow, pdv, operador, hora_inicio, hora_fim, cancelado)`.
   *Depende de:* `src/db.py` (trava de só-leitura já existente).
2. **`servico`** — distribuição empírica do tempo de atendimento
   (`HoraFim - HoraInicio`) **+ handover**.
   **Handover = mediana dos gaps < 120s** entre `HoraFim` de um cupom e
   `HoraInicio` do seguinte no mesmo PDV. Razão do corte: quando há fila, o gap
   *é* a troca de cliente pura; gap acima de 120s é ociosidade (não havia
   próximo cliente), não troca. O relatório reporta a **sensibilidade do
   resultado ao corte de 120s** — se o número de caixas mudar com o corte, o
   corte vira uma decisão a discutir, não um detalhe.
   Saída: distribuição por operador e agregada.
3. **`saturacao`** — fração de folga por faixa × dia. Faixa sem folga em todos os
   PDVs abertos = demanda censurada. Saída: conjunto de faixas rotuladas.
4. **`simulador`** — eventos discretos, M/G/c com chegadas reais (trace-driven).
   Reproduz um dia: chegadas nos horários observados, serviço amostrado da
   distribuição empírica, fila única atravessando faixas.
   Saída: para uma curva de caixas `c(t)`, o % de clientes com espera < 3 min por faixa.
5. **`dimensionador`** — acha a curva mínima `c(t)` que atinge 95% < 3min em cada
   faixa, por iteração de ponto fixo (caixa a menos numa faixa empurra fila para a
   seguinte, então não dá para resolver faixa a faixa isoladamente).
   Saída: `c_d(t)` por dia histórico `d`.
6. **`agregador`** — por (dia da semana, faixa), o **P85** de `c_d(t)` entre os
   dias históricos. Saída: curva P85 → **mínimo** (vale) e **máximo** (pico).
7. **`escala`** — cobertura de turnos: menor número de jornadas de 6h20 (intervalo
   de 20min alocado nos vales) que cobre a curva P85. Saída: **operadoras por dia
   da semana**.
8. **`relatorio`** — tabelas: curva por faixa, min/max, headcount por dia,
   **delta vs. o que esteve aberto de fato** (a ociosidade), **stress ±10%**,
   e as faixas rotuladas como piso.

### Fluxo

```
tbCupom + tbCupomCancelado
   → extracao → servico (+handover)
                saturacao (rótulos)
   → simulador → dimensionador → c_d(t) por dia
   → agregador (P85 por dow×faixa) → curva min/max
   → escala (6h20) → operadoras/dia
   → relatorio (+ stress ±10% + delta ociosidade)
```

## Verificação

**O simulador é validado contra a fórmula fechada de Erlang-C num caso M/M/c
conhecido** (chegadas Poisson + serviço exponencial). Se não reproduzir o
resultado analítico dentro da tolerância de Monte Carlo, o simulador está errado
e o número dele não é usado. Erlang-C também roda como conferência de sanidade
sobre os dados reais — divergência grande entre os dois é sinal para investigar,
não para escolher o que agrada.

Testes por componente:
- `servico`: handover estimado de gaps sintéticos conhecidos.
- `saturacao`: dia sintético saturado e dia folgado → rótulo correto.
- `simulador`: M/M/c vs Erlang-C analítico (o teste de aceitação).
- `dimensionador`: demanda constante conhecida → c previsível.
- `escala`: curva sintética → cobertura mínima conhecida.
- `extracao`: total de cupons bate com `tbConsPDVOperador` no período.

## Entrega

`src/dimensionamento_caixas.py`, executado no PC-ponte (única máquina que
alcança o banco). Saída em tabelas.

**Fora de escopo (YAGNI):** agendamento via `register-tasks.ps1`, envio no
WhatsApp, dashboard HTML. Se virar rotina, liga-se depois.

## Limites conhecidos — o relatório deve declarar

1. **O modelo assume que a operadora é o gargalo do caixa.** Se o empacotador
   falta e ela ensaca, ou se acumula outra função, o tempo real muda e o número
   muda junto. **Isso não está no banco.** *A confirmar com o dono.*
2. **Faixas saturadas dão piso, não estimativa.** Onde a capacidade represou a
   chegada, a demanda real é ≥ a observada.
3. **A escala P85 falha por construção em ~15% dos dias** daquele dia da semana.
   É a margem escolhida, não um defeito.
4. **Não modela abandono de fila** (cliente larga o carrinho). Em supermercado é
   raro; se houver, a demanda real é maior que a observada.
5. **Feriado e véspera de pagamento não são tratados à parte** — entram na
   distribuição do dia da semana e empurram o P85 para cima.

## Relacionados

- `src/queries.py` — cabeçalho documenta os fatos do schema do Solidcon.
- `docs/superpowers/specs/2026-07-11-detector-salao-dados-reais-design.md`
