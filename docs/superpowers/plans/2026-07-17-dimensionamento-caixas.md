# Dimensionamento de caixas e operadoras — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Responder quantos PDVs (mínimo/máximo por faixa) e quantas operadoras por dia da semana a loja precisa para que **95% dos clientes esperem menos de 3 min na fila**, e quanto de ociosidade existe hoje.

**Architecture:** Extrai cupons reais do `DORSAL.tbCupom` + `tbCupomCancelado`, estima tempo de atendimento + handover, roda uma **simulação de eventos discretos trace-driven** (chegadas reais, serviço empírico, fila única atravessando faixas) para achar a curva mínima de caixas por dia, agrega no **P85** por dia da semana e converte em escala de turnos CLT 6h. **Erlang-C em forma fechada é o oráculo que valida o simulador** — se o simulador não reproduzir a fórmula analítica num caso M/M/c, o número dele não vale.

**Tech Stack:** Python 3.12 (ponte), stdlib apenas (`heapq`, `math`, `statistics`, `random`, `argparse`) + `pyodbc` já existente. **Não adicionar numpy/scipy** — o repo tem só `pyodbc`/`pymysql` e tudo aqui sai em Python puro.

**Spec:** `docs/superpowers/specs/2026-07-17-dimensionamento-caixas-design.md`

## Global Constraints

- **Banco é SOMENTE LEITURA.** Só `SELECT`/`WITH`. `src/db.py` já tem a trava; não contorná-la. Nunca instalar nada no `CONCENTRADOR` (192.168.0.245).
- **Nunca commitar senha, custo ou preço.** A senha vive só em `config.local.json` (gitignored). Esta análise **não usa `vlCupom`** — não extrair valor monetário.
- **Só o PC-ponte alcança o banco.** Rodar via `ssh User@100.99.176.6`; a máquina dev não conecta.
- **Console do ponte é cp1252** → todo `main()` começa com `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` (padrão de `src/abaixo_custo.py:172`).
- **Recorte fixo dos dados:** `cdFilial=1`, `cdPDV NOT IN (11,12)`, `cdOperador <> 7000`, sem domingos, período 2026-01-22 → hoje.
- **Meta:** 95% dos clientes com espera < **180s**, aplicada **por faixa de 30 min** (não no agregado do dia).
- **Margem:** curva agregada no **percentil 85** dos dias de cada dia da semana.
- **Jornada:** CLT 6h — 6h20 de presença, 20 min de intervalo.
- **Padrão de teste:** `pytest` em `tests/` (já existe `tests/test_robo_validacao.py`; `pytest` está em `requirements-dev.txt` e instalado no ponte, versão 9.1.1).
- **Encoding dos fontes:** `# -*- coding: utf-8 -*-` no topo, comentários em português sem acento em identificadores (padrão do repo).

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `src/dim_erlang.py` | Erlang-B/C em forma fechada. Puro. É o oráculo de validação. |
| `src/dim_queries.py` | Os SELECTs (`tbCupom` ∪ `tbCupomCancelado`, conferência `tbConsPDVOperador`). |
| `src/dim_servico.py` | Tempo de atendimento + handover; percentil. Puro. |
| `src/dim_saturacao.py` | Detecção de faixa saturada (demanda censurada). Puro. |
| `src/dim_simulador.py` | Simulação de eventos discretos M/G/c, fila única. Puro. |
| `src/dim_dimensionador.py` | Ponto fixo: curva mínima de caixas por dia. Puro. |
| `src/dim_escala.py` | Agregação P85 + cobertura de turnos 6h20. Puro. |
| `src/dimensionamento_caixas.py` | CLI: orquestra, extrai, imprime relatório. Único com I/O. |
| `tests/test_dim_*.py` | Um arquivo de teste por módulo puro. |

Tudo puro exceto o CLI — é o que torna o miolo testável sem banco, seguindo o padrão de `src/abaixo_custo.py` (funções puras + `main()` com I/O).

---

### Task 1: Erlang-C (o oráculo)

Primeiro porque o simulador (Task 5) é validado contra ele. Sem oráculo, o simulador é inauditável.

**Files:**
- Create: `src/dim_erlang.py`
- Test: `tests/test_dim_erlang.py`

**Interfaces:**
- Consumes: nada.
- Produces: `erlang_b(c: int, a: float) -> float`, `erlang_c(c: int, a: float) -> float`, `prob_espera_maior(c: int, a: float, t: float, ts: float) -> float`, `caixas_minimos(a: float, ts: float, meta_pct: float, meta_seg: float, c_max: int) -> int`.

- [ ] **Step 1: Write the failing test**

```python
# -*- coding: utf-8 -*-
"""Erlang-B/C conferidos contra valores analiticos conhecidos."""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import dim_erlang as e  # noqa: E402


def test_erlang_b_caso_conhecido():
    # B(1, a) = a/(1+a) — derivavel na mao
    assert abs(e.erlang_b(1, 0.5) - (0.5 / 1.5)) < 1e-12
    # B(2, 1) = (1^2/2!)/(1 + 1 + 1/2) = 0.5/2.5 = 0.2
    assert abs(e.erlang_b(2, 1.0) - 0.2) < 1e-12


def test_erlang_c_em_mm1_e_igual_a_rho():
    # M/M/1: P(esperar) = rho. Com c=1 e a=rho, Erlang-C tem que dar exatamente rho.
    for rho in (0.1, 0.5, 0.8):
        assert abs(e.erlang_c(1, rho) - rho) < 1e-12


def test_prob_espera_maior_em_mm1():
    # M/M/1: P(W > t) = rho * exp(-(1-rho) * t / ts)
    rho, ts, t = 0.5, 100.0, 100.0
    esperado = rho * math.exp(-(1 - rho) * t / ts)
    assert abs(e.prob_espera_maior(1, rho, t, ts) - esperado) < 1e-12


def test_saturado_espera_sempre():
    # a >= c: fila explode, P(W > t) = 1
    assert e.erlang_c(2, 2.0) == 1.0
    assert e.prob_espera_maior(2, 3.0, 180, 110) == 1.0


def test_caixas_minimos_monotono_na_carga():
    # mais carga nunca pede menos caixa
    ts, meta_pct, meta_seg = 110.0, 0.95, 180.0
    anterior = 0
    for a in (0.5, 1.0, 2.0, 3.0, 4.0, 5.0):
        c = e.caixas_minimos(a, ts, meta_pct, meta_seg, c_max=20)
        assert c >= anterior
        anterior = c


def test_caixas_minimos_atinge_a_meta():
    ts, meta_pct, meta_seg = 110.0, 0.95, 180.0
    a = 3.36
    c = e.caixas_minimos(a, ts, meta_pct, meta_seg, c_max=20)
    assert e.prob_espera_maior(c, a, meta_seg, ts) <= 1 - meta_pct
    # e c-1 nao atinge (e o MINIMO)
    assert e.prob_espera_maior(c - 1, a, meta_seg, ts) > 1 - meta_pct


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dim_erlang.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dim_erlang'`

- [ ] **Step 3: Write minimal implementation**

```python
# -*- coding: utf-8 -*-
"""Erlang-B / Erlang-C em forma fechada — o ORACULO que valida o simulador.

Erlang-C responde: com carga 'a' Erlangs e 'c' caixas, qual a chance de um
cliente esperar mais que t segundos. Assume chegada Poisson e servico
exponencial (por isso NAO e o numero final: a loja real nao e nenhum dos dois
— ver o spec). Serve para (1) provar que o simulador esta certo num caso onde
a resposta e conhecida e (2) conferir a sanidade do resultado real.
"""
import math


def erlang_b(c, a):
    """Erlang-B por recursao (estavel numericamente; a formula direta com
    fatorial estoura para c grande). B(0,a)=1; B(n,a)=a*B(n-1,a)/(n+a*B(n-1,a))."""
    if a <= 0:
        return 0.0
    b = 1.0
    for n in range(1, int(c) + 1):
        b = a * b / (n + a * b)
    return b


def erlang_c(c, a):
    """P(cliente ter que esperar) na fila M/M/c. a >= c => fila explode => 1.0."""
    if a <= 0:
        return 0.0
    if a >= c:
        return 1.0
    b = erlang_b(c, a)
    return b / (1.0 - (a / c) * (1.0 - b))


def prob_espera_maior(c, a, t, ts):
    """P(W > t). a = carga em Erlangs (= chegadas/seg * ts), ts = servico medio."""
    if a <= 0:
        return 0.0
    if a >= c:
        return 1.0
    return erlang_c(c, a) * math.exp(-(c - a) * t / ts)


def caixas_minimos(a, ts, meta_pct, meta_seg, c_max):
    """Menor c com P(W > meta_seg) <= 1 - meta_pct. Devolve c_max se nao houver."""
    alvo = 1.0 - meta_pct
    for c in range(1, int(c_max) + 1):
        if prob_espera_maior(c, a, meta_seg, ts) <= alvo:
            return c
    return int(c_max)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dim_erlang.py -v`
Expected: PASS — 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/dim_erlang.py tests/test_dim_erlang.py
git commit -m "feat(dim): Erlang-B/C em forma fechada (oraculo do simulador)"
```

---

### Task 2: Extração dos cupons

**Files:**
- Create: `src/dim_queries.py`
- Test: `tests/test_dim_queries.py`

**Interfaces:**
- Consumes: nada (SQL é texto).
- Produces: constantes `CUPONS`, `CONFERENCIA_CONSOLIDADO`. A `CUPONS` devolve colunas exatamente: `dia` (date), `dow` (int, 2=segunda … 7=sábado), `pdv` (int), `operador` (int), `inicio` (datetime), `fim` (datetime), `cancelado` (int 0/1).

- [ ] **Step 1: Write the failing test**

```python
# -*- coding: utf-8 -*-
"""A query e texto: da para travar o RECORTE sem tocar no banco.
O recorte errado (esquecer o PDV 11/12, ou perder tbCupomCancelado) e o
jeito mais facil de esta analise mentir — por isso ele e testado."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import dim_queries as q  # noqa: E402


def test_cupons_exclui_atacado_e_operador_nao_operacional():
    sql = q.CUPONS.upper()
    assert "NOT IN (11, 12)" in sql.replace("  ", " ")
    assert "7000" in sql
    assert "CDFILIAL = 1" in sql.replace("  ", " ")


def test_cupons_inclui_a_tabela_de_cancelados():
    # cupom cancelado consumiu tempo de caixa: fora dele, subdimensiona
    sql = q.CUPONS.upper()
    assert "TBCUPOM" in sql
    assert "TBCUPOMCANCELADO" in sql
    assert "UNION ALL" in sql


def test_cupons_exclui_domingo():
    # loja fechada; DATEPART(weekday) = 1 e domingo no SQL Server
    assert "DATEPART(weekday, dtCupom) <> 1" in q.CUPONS


def test_cupons_nao_extrai_valor_monetario():
    # regra do repo: nada de preco/custo. E a analise nao precisa.
    assert "vlCupom" not in q.CUPONS


def test_queries_sao_somente_leitura():
    import db
    for sql in (q.CUPONS, q.CONFERENCIA_CONSOLIDADO):
        assert db._e_somente_leitura(sql)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dim_queries.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dim_queries'`

- [ ] **Step 3: Write minimal implementation**

```python
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
    CAST(c.dtCupom AS date)      AS dia,
    DATEPART(weekday, c.dtCupom) AS dow,
    c.cdPDV                      AS pdv,
    c.cdOperador                 AS operador,
    c.HoraInicio                 AS inicio,
    c.HoraFim                    AS fim,
    0                            AS cancelado
FROM DORSAL.dbo.tbCupom c
WHERE c.cdFilial = 1
  AND c.cdPDV NOT IN (11, 12)
  AND c.cdOperador <> 7000
  AND DATEPART(weekday, c.dtCupom) <> 1
  AND c.dtCupom >= '{desde}'
  AND c.HoraInicio IS NOT NULL AND c.HoraFim IS NOT NULL
  AND c.HoraFim >= c.HoraInicio
UNION ALL
SELECT
    CAST(x.dtCupom AS date)      AS dia,
    DATEPART(weekday, x.dtCupom) AS dow,
    x.cdPDV                      AS pdv,
    x.cdOperador                 AS operador,
    x.HoraInicio                 AS inicio,
    x.HoraFim                    AS fim,
    1                            AS cancelado
FROM DORSAL.dbo.tbCupomCancelado x
WHERE x.cdFilial = 1
  AND x.cdPDV NOT IN (11, 12)
  AND x.cdOperador <> 7000
  AND DATEPART(weekday, x.dtCupom) <> 1
  AND x.dtCupom >= '{desde}'
  AND x.HoraInicio IS NOT NULL AND x.HoraFim IS NOT NULL
  AND x.HoraFim >= x.HoraInicio
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dim_queries.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/dim_queries.py tests/test_dim_queries.py
git commit -m "feat(dim): SELECTs de cupons (tbCupom + tbCupomCancelado, recorte travado por teste)"
```

---

### Task 3: Tempo de atendimento e handover

**Files:**
- Create: `src/dim_servico.py`
- Test: `tests/test_dim_servico.py`

**Interfaces:**
- Consumes: registros de cupom (dicts com `pdv`, `inicio`, `fim`).
- Produces: `percentil(valores: list[float], p: float) -> float`, `duracoes(cupons: list[dict]) -> list[float]`, `estimar_handover(cupons: list[dict], corte_seg: float = 120.0) -> float`, `servicos_por_operador(cupons: list[dict], handover: float) -> dict[int, list[float]]`.

- [ ] **Step 1: Write the failing test**

```python
# -*- coding: utf-8 -*-
"""Handover = mediana dos gaps < corte entre cupons consecutivos no mesmo PDV.
Razao do corte: com fila, o gap E a troca de cliente pura; gap grande e
ociosidade (nao havia proximo cliente), nao troca."""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import dim_servico as s  # noqa: E402

BASE = datetime(2026, 7, 16, 8, 0, 0)


def _cupom(pdv, offset_ini, dur, operador=1):
    return {"pdv": pdv, "operador": operador,
            "inicio": BASE + timedelta(seconds=offset_ini),
            "fim": BASE + timedelta(seconds=offset_ini + dur)}


def test_percentil_interpola():
    assert s.percentil([1, 2, 3, 4], 0.0) == 1
    assert s.percentil([1, 2, 3, 4], 1.0) == 4
    assert s.percentil([1, 2, 3, 4], 0.5) == 2.5   # (2+3)/2
    assert s.percentil([], 0.85) == 0


def test_duracoes_sao_fim_menos_inicio():
    assert s.duracoes([_cupom(1, 0, 100), _cupom(1, 200, 50)]) == [100.0, 50.0]


def test_handover_e_a_mediana_dos_gaps_curtos():
    # gaps: 10s, 20s, 30s (curtos = troca de cliente) e 600s (ociosidade, ignorar)
    cupons = [
        _cupom(1, 0, 100),      # fim em 100
        _cupom(1, 110, 100),    # gap 10  -> fim 210
        _cupom(1, 230, 100),    # gap 20  -> fim 330
        _cupom(1, 360, 100),    # gap 30  -> fim 460
        _cupom(1, 1060, 100),   # gap 600 -> ociosidade, fora
    ]
    assert s.estimar_handover(cupons, corte_seg=120.0) == 20.0  # mediana de [10,20,30]


def test_handover_nao_mistura_pdvs():
    # o "gap" entre o ultimo cupom do PDV 1 e o primeiro do PDV 2 nao existe
    cupons = [_cupom(1, 0, 100), _cupom(2, 110, 100)]
    assert s.estimar_handover(cupons, corte_seg=120.0) == 0.0  # nenhum gap valido


def test_servico_soma_o_handover():
    cupons = [_cupom(1, 0, 100, operador=7), _cupom(1, 200, 50, operador=7)]
    por_op = s.servicos_por_operador(cupons, handover=15.0)
    assert por_op[7] == [115.0, 65.0]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dim_servico.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dim_servico'`

- [ ] **Step 3: Write minimal implementation**

```python
# -*- coding: utf-8 -*-
"""Tempo de atendimento por cupom + handover (a troca de cliente).

HoraFim - HoraInicio mede so o cupom passando. A troca de cliente (o anterior
sair, o proximo chegar, ensacar) NAO esta la — e usar o valor cru
subdimensiona. O handover e estimado dos dados: quando ha fila, o intervalo
entre o fim de um cupom e o inicio do seguinte NO MESMO PDV *e* a troca pura.
Gap acima do corte e ociosidade (nao havia proximo cliente), nao troca.
"""
import math


def percentil(valores, p):
    """Percentil com interpolacao linear (mesma convencao do numpy)."""
    if not valores:
        return 0
    ordenado = sorted(valores)
    if len(ordenado) == 1:
        return ordenado[0]
    k = (len(ordenado) - 1) * p
    baixo, alto = math.floor(k), math.ceil(k)
    if baixo == alto:
        return ordenado[int(k)]
    return ordenado[baixo] * (alto - k) + ordenado[alto] * (k - baixo)


def duracoes(cupons):
    """Segundos de HoraInicio a HoraFim, na ordem recebida."""
    return [(c["fim"] - c["inicio"]).total_seconds() for c in cupons]


def _gaps_por_pdv(cupons):
    """Intervalos entre cupons consecutivos DENTRO do mesmo PDV, mesmo dia."""
    por_pdv = {}
    for c in cupons:
        por_pdv.setdefault((c["pdv"], c["inicio"].date()), []).append(c)
    gaps = []
    for lista in por_pdv.values():
        lista.sort(key=lambda c: c["inicio"])
        for anterior, atual in zip(lista, lista[1:]):
            gaps.append((atual["inicio"] - anterior["fim"]).total_seconds())
    return gaps


def estimar_handover(cupons, corte_seg=120.0):
    """Mediana dos gaps em (0, corte_seg]. 0.0 se nao houver gap valido."""
    validos = [g for g in _gaps_por_pdv(cupons) if 0 < g <= corte_seg]
    if not validos:
        return 0.0
    return float(percentil(validos, 0.5))


def servicos_por_operador(cupons, handover):
    """Tempo de ocupacao do caixa por cupom (duracao + handover), por operador."""
    por_op = {}
    for c in cupons:
        dur = (c["fim"] - c["inicio"]).total_seconds() + handover
        por_op.setdefault(c["operador"], []).append(dur)
    return por_op
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dim_servico.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/dim_servico.py tests/test_dim_servico.py
git commit -m "feat(dim): tempo de atendimento + handover estimado dos gaps reais"
```

---

### Task 4: Detecção de saturação (demanda censurada)

**Files:**
- Create: `src/dim_saturacao.py`
- Test: `tests/test_dim_saturacao.py`

**Interfaces:**
- Consumes: cupons (dicts com `pdv`, `inicio`, `fim`).
- Produces: `slot_de(dt, slot_seg=1800) -> int`, `folga_por_slot(cupons, slot_seg=1800) -> dict[tuple, float]`, `slots_saturados(cupons, limiar=0.05, slot_seg=1800) -> set[tuple]`.

A chave é `(dia, slot)`. Folga = 1 - (tempo ocupado dos PDVs abertos ÷ tempo-caixa disponível no slot).

- [ ] **Step 1: Write the failing test**

```python
# -*- coding: utf-8 -*-
"""Saturacao: se num slot TODOS os PDVs abertos ficaram colados passando cupom,
a chegada foi represada pela capacidade -> a demanda observada e PISO, nao
estimativa. Isso e medido, nao suposto."""
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import dim_saturacao as sat  # noqa: E402

DIA = date(2026, 7, 16)
BASE = datetime(2026, 7, 16, 10, 0, 0)   # 10:00 = slot 20 (36000s / 1800)


def _cupom(pdv, offset_ini, dur):
    return {"pdv": pdv, "inicio": BASE + timedelta(seconds=offset_ini),
            "fim": BASE + timedelta(seconds=offset_ini + dur)}


def test_slot_de_usa_faixa_de_30min():
    assert sat.slot_de(datetime(2026, 7, 16, 0, 0, 0)) == 0
    assert sat.slot_de(datetime(2026, 7, 16, 0, 29, 59)) == 0
    assert sat.slot_de(datetime(2026, 7, 16, 0, 30, 0)) == 1
    assert sat.slot_de(datetime(2026, 7, 16, 10, 0, 0)) == 20


def test_pdv_colado_o_slot_inteiro_nao_tem_folga():
    # 1 PDV, 18 cupons de 100s = 1800s ocupado num slot de 1800s -> folga 0
    cupons = [_cupom(1, i * 100, 100) for i in range(18)]
    folga = sat.folga_por_slot(cupons)
    assert abs(folga[(DIA, 20)] - 0.0) < 1e-9
    assert (DIA, 20) in sat.slots_saturados(cupons, limiar=0.05)


def test_pdv_com_metade_do_tempo_livre_tem_folga():
    # 1 PDV, 9 cupons de 100s = 900s de 1800s -> folga 0.5
    cupons = [_cupom(1, i * 200, 100) for i in range(9)]
    folga = sat.folga_por_slot(cupons)
    assert abs(folga[(DIA, 20)] - 0.5) < 1e-9
    assert sat.slots_saturados(cupons, limiar=0.05) == set()


def test_folga_considera_todos_os_pdvs_abertos():
    # PDV 1 colado (1800s), PDV 2 quase vazio (100s) -> folga = 1 - 1900/3600
    cupons = [_cupom(1, i * 100, 100) for i in range(18)] + [_cupom(2, 0, 100)]
    folga = sat.folga_por_slot(cupons)
    assert abs(folga[(DIA, 20)] - (1 - 1900.0 / 3600.0)) < 1e-9
    assert sat.slots_saturados(cupons, limiar=0.05) == set()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dim_saturacao.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dim_saturacao'`

- [ ] **Step 3: Write minimal implementation**

```python
# -*- coding: utf-8 -*-
"""Deteccao de saturacao = deteccao de demanda censurada.

A analise mede a chegada pelo INICIO do cupom, nao pela entrada na fila. Se um
slot saturou, as chegadas aparecem represadas pela propria capacidade e o
numero de caixas sai subestimado. Em vez de supor que nao acontece, medimos: um
slot saturado tem todos os PDVs abertos colados, sem folga. Onde isso acontecer,
o resultado e rotulado PISO, nao estimativa.
"""

SLOT_SEG = 1800   # faixa de 30 min


def slot_de(dt, slot_seg=SLOT_SEG):
    """Indice da faixa dentro do dia (0 = 00:00-00:30)."""
    segundos = dt.hour * 3600 + dt.minute * 60 + dt.second
    return int(segundos // slot_seg)


def folga_por_slot(cupons, slot_seg=SLOT_SEG):
    """Fracao do tempo-caixa ocioso em cada (dia, slot).

    Tempo ocupado e recortado no slot: cupom que atravessa a fronteira conta
    so a parte dentro. Tempo disponivel = (PDVs abertos no slot) x slot_seg.
    """
    ocupado, pdvs = {}, {}
    for c in cupons:
        dia = c["inicio"].date()
        ini_s = c["inicio"].hour * 3600 + c["inicio"].minute * 60 + c["inicio"].second
        fim_s = ini_s + (c["fim"] - c["inicio"]).total_seconds()
        primeiro, ultimo = int(ini_s // slot_seg), int(fim_s // slot_seg)
        for s in range(primeiro, ultimo + 1):
            borda_ini, borda_fim = s * slot_seg, (s + 1) * slot_seg
            dentro = min(fim_s, borda_fim) - max(ini_s, borda_ini)
            if dentro > 0:
                ocupado[(dia, s)] = ocupado.get((dia, s), 0.0) + dentro
                pdvs.setdefault((dia, s), set()).add(c["pdv"])
    folgas = {}
    for chave, seg in ocupado.items():
        disponivel = len(pdvs[chave]) * slot_seg
        folgas[chave] = max(0.0, 1.0 - seg / disponivel)
    return folgas


def slots_saturados(cupons, limiar=0.05, slot_seg=SLOT_SEG):
    """(dia, slot) com folga <= limiar: ali a demanda observada e PISO."""
    return {k for k, v in folga_por_slot(cupons, slot_seg).items() if v <= limiar}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dim_saturacao.py -v`
Expected: PASS — 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/dim_saturacao.py tests/test_dim_saturacao.py
git commit -m "feat(dim): deteccao de slot saturado (demanda censurada vira piso)"
```

---

### Task 5: Simulador de eventos discretos

**O teste de aceitação do projeto inteiro.** Se o simulador não reproduzir Erlang-C num caso M/M/c, ele está errado e o resultado dele não vale.

**Files:**
- Create: `src/dim_simulador.py`
- Test: `tests/test_dim_simulador.py`

**Interfaces:**
- Consumes: `dim_erlang` (só no teste).
- Produces: `simular(chegadas: list[float], servicos: list[float], curva: dict[int, int], slot_seg: int = 1800) -> list[float | None]` — devolve a espera de cada cliente na ordem de chegada; `None` se nenhum caixa estava aberto.

Fila **única** FIFO com `c(t)` caixas: modela o cliente escolhendo a fila mais curta (jockeying), que é o que acontece na loja.

- [ ] **Step 1: Write the failing test**

```python
# -*- coding: utf-8 -*-
"""O simulador so vale se reproduzir a resposta ANALITICA num caso conhecido.
Este e o teste de aceitacao: chegada Poisson + servico exponencial = M/M/c,
onde Erlang-C da a resposta exata."""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import dim_erlang as e  # noqa: E402
import dim_simulador as sim  # noqa: E402


def _curva_constante(c, n_slots=200):
    return {s: c for s in range(n_slots)}


def test_fila_vazia_nao_espera():
    # chegadas espacadas de sobra: ninguem espera
    esperas = sim.simular([0, 1000, 2000], [100, 100, 100], _curva_constante(1))
    assert esperas == [0.0, 0.0, 0.0]


def test_fila_unica_fifo_acumula():
    # 1 caixa, 3 clientes juntos, servico 100s: esperas 0, 100, 200
    esperas = sim.simular([0, 0, 0], [100, 100, 100], _curva_constante(1))
    assert esperas == [0.0, 100.0, 200.0]


def test_dois_caixas_atendem_em_paralelo():
    # 2 caixas, 2 clientes juntos: ninguem espera
    esperas = sim.simular([0, 0], [100, 100], _curva_constante(2))
    assert esperas == [0.0, 0.0]


def test_sem_caixa_aberto_o_cliente_nao_e_atendido():
    esperas = sim.simular([0], [100], {0: 0})
    assert esperas == [None]


def test_caixa_que_abre_no_slot_seguinte_entra_no_pool():
    # slot 0 com 1 caixa, slot 1 com 2. O 1o cliente prende o caixa 1 ate 3600.
    # Em t=1800 abre o caixa 2: o cliente 1 pega ele na hora (espera 0) e sai
    # em 1900; o cliente 2 pega o MESMO caixa 2 em 1900 (espera 100) — nao
    # espera o caixa 1, que so vaga em 3600.
    curva = {0: 1, 1: 2}
    esperas = sim.simular([0, 1800, 1800], [3600, 100, 100], curva)
    assert esperas[0] == 0.0
    assert esperas[1] == 0.0
    assert esperas[2] == 100.0


def test_simulador_reproduz_erlang_c_em_mmc():
    """ACEITACAO: M/M/c simulado tem que bater com a formula fechada."""
    rng = random.Random(20260717)
    ts = 110.0          # servico medio
    c = 4               # caixas
    a = 2.8             # carga em Erlangs -> lambda = a/ts
    lam = a / ts
    n = 200000

    t, chegadas, servicos = 0.0, [], []
    for _ in range(n):
        t += rng.expovariate(lam)
        chegadas.append(t)
        servicos.append(rng.expovariate(1.0 / ts))

    n_slots = int(t // 1800) + 2
    esperas = sim.simular(chegadas, servicos, {s: c for s in range(n_slots)})

    # descarta o transiente inicial (fila comeca vazia)
    amostra = [w for w in esperas[1000:] if w is not None]
    for alvo in (0.0, 60.0, 180.0):
        medido = sum(1 for w in amostra if w > alvo) / len(amostra)
        analitico = e.prob_espera_maior(c, a, alvo, ts)
        # Referencia (conferida na mao ao escrever o plano): com c=4, a=2.8,
        # ts=110 -> Erlang-C P(W>0) = 0.4286 e P(W>180) = 0.0601.
        # Tolerancia 0.015 = erro de Monte Carlo (esperas em fila sao
        # autocorrelacionadas, entao a amostra efetiva e menor que 200 mil).
        # NAO e folga para simulador errado: um bug de verdade erra MUITO mais
        # que 1,5 ponto. Se falhar, o defeito e no simulador — nao afrouxe isto.
        assert abs(medido - analitico) < 0.015, (
            "P(W>%.0f): simulado %.4f vs Erlang-C %.4f" % (alvo, medido, analitico))


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dim_simulador.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dim_simulador'`

- [ ] **Step 3: Write minimal implementation**

```python
# -*- coding: utf-8 -*-
"""Simulacao de eventos discretos da fila de caixas (M/G/c, fila unica FIFO).

Por que simular em vez de usar Erlang-C direto: Erlang-C assume chegada Poisson
e servico exponencial. A loja real nao e nenhum dos dois — gente chega em
rajada, o servico e menos variavel que exponencial, a fila atravessa as faixas
e as operadoras tem velocidades diferentes. Simular com as chegadas REAIS e a
distribuicao empirica ELIMINA esses erros em vez de compensa-los com um chute.

Fila UNICA: modela o cliente indo para a fila mais curta (jockeying), que e o
comportamento real. Fila por caixa, sem troca, seria pior que isto.

Erlang-C continua sendo o oraculo: em tests/test_dim_simulador.py este
simulador tem que reproduzir a formula fechada num caso M/M/c.
"""
import heapq

SLOT_SEG = 1800


def _ajustar_pool(livres, c_novo, agora):
    """Poe o pool em c_novo caixas.

    Abrindo: caixa novo entra livre em 'agora'.
    Fechando: fecha primeiro o OCIOSO (free <= agora — a operadora foi embora);
    se nao houver ocioso suficiente, sai o que termina mais tarde — ele conclui
    o cliente em curso (a espera desse cliente ja foi contabilizada no inicio
    do atendimento) e simplesmente nao pega mais ninguem.
    """
    while len(livres) < c_novo:
        heapq.heappush(livres, agora)
    if len(livres) <= c_novo:
        return
    ordenado = sorted(livres)
    ociosos = [x for x in ordenado if x <= agora]
    ocupados = [x for x in ordenado if x > agora]
    excesso = len(ordenado) - c_novo
    fecha = min(excesso, len(ociosos))
    ociosos = ociosos[fecha:]
    excesso -= fecha
    if excesso > 0:
        ocupados = ocupados[:len(ocupados) - excesso]
    livres[:] = ociosos + ocupados
    heapq.heapify(livres)


def simular(chegadas, servicos, curva, slot_seg=SLOT_SEG):
    """Espera (segundos) de cada cliente, na ordem de chegada.

    chegadas: segundos desde a meia-noite, ORDENADO.
    servicos: tempo de ocupacao do caixa por cliente (mesma ordem).
    curva: {slot: numero de caixas abertos}.
    None = nenhum caixa aberto no slot (cliente nao atendido).
    """
    livres = []
    slot_visto = None
    esperas = []
    for t, s in zip(chegadas, servicos):
        slot = int(t // slot_seg)
        if slot != slot_visto:
            _ajustar_pool(livres, int(curva.get(slot, 0)), slot * slot_seg)
            slot_visto = slot
        if not livres:
            esperas.append(None)
            continue
        livre_em = heapq.heappop(livres)
        inicio = t if livre_em <= t else livre_em
        esperas.append(inicio - t)
        heapq.heappush(livres, inicio + s)
    return esperas
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dim_simulador.py -v`
Expected: PASS — 6 passed. O teste de aceitação leva ~10-20s (200 mil clientes).

Se `test_simulador_reproduz_erlang_c_em_mmc` falhar, **o simulador está errado — não afrouxe a tolerância**. Investigue: ordem das chegadas, o `_ajustar_pool`, ou o descarte do transiente.

- [ ] **Step 5: Commit**

```bash
git add src/dim_simulador.py tests/test_dim_simulador.py
git commit -m "feat(dim): simulador M/G/c fila unica, validado contra Erlang-C"
```

---

### Task 6: Dimensionador (ponto fixo)

**Files:**
- Create: `src/dim_dimensionador.py`
- Test: `tests/test_dim_dimensionador.py`

**Interfaces:**
- Consumes: `dim_simulador.simular`.
- Produces: `nivel_por_slot(chegadas, esperas, meta_seg, slot_seg=1800) -> dict[int, float]`, `dimensionar_dia(chegadas, servicos, meta_pct=0.95, meta_seg=180.0, c_max=12, slot_seg=1800) -> tuple[dict[int,int], set[int]]` — devolve `(curva, slots_no_teto)`.

Ponto fixo porque caixa a menos numa faixa empurra fila para a seguinte: não dá para resolver faixa a faixa isoladamente.

- [ ] **Step 1: Write the failing test**

```python
# -*- coding: utf-8 -*-
"""Curva minima de caixas por ponto fixo: sobe caixa nos slots que falham,
resimula o dia inteiro (a fila atravessa faixas), repete ate todos passarem."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import dim_dimensionador as d  # noqa: E402


def test_nivel_por_slot_agrupa_pela_chegada():
    # 2 clientes no slot 0 (1 dentro da meta), 2 no slot 1 (ambos dentro)
    chegadas = [0, 10, 1800, 1810]
    esperas = [0.0, 300.0, 10.0, 20.0]
    nivel = d.nivel_por_slot(chegadas, esperas, meta_seg=180.0)
    assert nivel[0] == 0.5
    assert nivel[1] == 1.0


def test_cliente_nao_atendido_conta_como_fora_da_meta():
    # None = nao havia caixa aberto. Isso e a PIOR falha possivel de nivel de
    # servico; ignorar o None faria um dia sem caixa nenhum parecer 100% de meta.
    nivel = d.nivel_por_slot([0, 10], [0.0, None], meta_seg=180.0)
    assert nivel[0] == 0.5


def test_demanda_folgada_pede_um_caixa():
    # 1 cliente a cada 600s, servico 100s: 1 caixa sobra
    chegadas = [i * 600 for i in range(12)]
    servicos = [100.0] * 12
    curva, teto = d.dimensionar_dia(chegadas, servicos, c_max=8)
    assert curva[0] == 1
    assert teto == set()


def test_demanda_pesada_pede_mais_caixa():
    # 30 clientes juntos no slot 0, servico 100s: 1 caixa da fila de 3000s
    chegadas = [0] * 30
    servicos = [100.0] * 30
    curva, _ = d.dimensionar_dia(chegadas, servicos, meta_pct=0.95, meta_seg=180.0, c_max=40)
    # com c caixas, o k-esimo cliente espera ~(k//c)*100s; para 95% < 180s
    # precisa de c grande o suficiente -> muito mais que 1
    assert curva[0] > 1


def test_curva_atinge_a_meta_que_prometeu():
    import dim_simulador as sim
    chegadas = [i * 40 for i in range(45)]     # 45 clientes num slot
    servicos = [100.0] * 45
    curva, teto = d.dimensionar_dia(chegadas, servicos, meta_pct=0.95, meta_seg=180.0, c_max=20)
    assert teto == set()
    esperas = sim.simular(chegadas, servicos, curva)
    nivel = d.nivel_por_slot(chegadas, esperas, meta_seg=180.0)
    assert all(v >= 0.95 for v in nivel.values())


def test_teto_e_reportado_nao_escondido():
    # demanda absurda com c_max=1: impossivel atingir a meta -> slot no teto
    chegadas = [0] * 50
    servicos = [100.0] * 50
    curva, teto = d.dimensionar_dia(chegadas, servicos, c_max=1)
    assert curva[0] == 1
    assert 0 in teto


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dim_dimensionador.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dim_dimensionador'`

- [ ] **Step 3: Write minimal implementation**

```python
# -*- coding: utf-8 -*-
"""Curva minima de caixas que atinge a meta, dia a dia.

Por ponto fixo, e nao slot a slot: caixa a menos numa faixa empurra fila para a
seguinte, entao os slots nao sao independentes. Sobe +1 caixa em todo slot que
falha, resimula o DIA INTEIRO, repete. A curva so cresce e e limitada por
c_max, entao termina.

Slot que bate no teto (c_max) sem atingir a meta e DEVOLVIDO no conjunto
'no_teto' — nao e escondido atras de um numero limpo.
"""
import dim_simulador as sim

SLOT_SEG = sim.SLOT_SEG


def nivel_por_slot(chegadas, esperas, meta_seg, slot_seg=SLOT_SEG):
    """Fracao dos clientes de cada slot (pela CHEGADA) dentro da meta.
    Cliente nao atendido (espera None) conta como fora da meta."""
    dentro, total = {}, {}
    for t, w in zip(chegadas, esperas):
        s = int(t // slot_seg)
        total[s] = total.get(s, 0) + 1
        if w is not None and w < meta_seg:
            dentro[s] = dentro.get(s, 0) + 1
    return {s: dentro.get(s, 0) / n for s, n in total.items()}


def dimensionar_dia(chegadas, servicos, meta_pct=0.95, meta_seg=180.0,
                    c_max=12, slot_seg=SLOT_SEG):
    """Menor curva {slot: caixas} com meta_pct dos clientes abaixo de meta_seg
    em CADA slot. Devolve (curva, slots_no_teto)."""
    if not chegadas:
        return {}, set()
    slots = sorted({int(t // slot_seg) for t in chegadas})
    curva = {s: 1 for s in slots}
    no_teto = set()
    for _ in range(int(c_max) * len(slots) + 1):
        esperas = sim.simular(chegadas, servicos, curva, slot_seg)
        nivel = nivel_por_slot(chegadas, esperas, meta_seg, slot_seg)
        falhando = [s for s, v in nivel.items() if v < meta_pct and s not in no_teto]
        if not falhando:
            break
        subiu = False
        for s in falhando:
            if curva[s] < c_max:
                curva[s] += 1
                subiu = True
            else:
                no_teto.add(s)
        if not subiu:
            break
    return curva, no_teto
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dim_dimensionador.py -v`
Expected: PASS — 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/dim_dimensionador.py tests/test_dim_dimensionador.py
git commit -m "feat(dim): dimensionador por ponto fixo (fila atravessa faixas)"
```

---

### Task 7: Agregação P85 e escala CLT 6h

**Files:**
- Create: `src/dim_escala.py`
- Test: `tests/test_dim_escala.py`

**Interfaces:**
- Consumes: `dim_servico.percentil`.
- Produces: `curva_percentil(curvas_por_dia: dict, p: float = 0.85) -> dict[int, int]`, `cobertura_minima(curva: dict[int,int], slots_turno: int = 13, slots_produtivos: int = 12) -> tuple[int, dict[int,int]]`.

`cobertura_minima` devolve `(total_de_turnos, {slot_de_inicio: quantos})`.

**Modelagem do turno (declarada, não escondida):** slots de 30 min. Jornada 6h20 com 20 min de intervalo = 6h produtivas. Modelado como **13 slots de presença, 12 produtivos**, com 1 slot (30 min) de intervalo. O intervalo modelado (30 min) é 10 min maior que o real (20 min) — **conservador de propósito**; a alternativa (slots de 10 min) triplicaria o custo da simulação sem mudar a decisão.

- [ ] **Step 1: Write the failing test**

```python
# -*- coding: utf-8 -*-
"""P85 entre os dias (a margem de seguranca) e cobertura de turnos 6h20."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import dim_escala as esc  # noqa: E402


def test_curva_percentil_pega_o_dia_ruim_nao_o_mediano():
    # slot 10: dias com 2,2,2,2,6 caixas. Mediana=2, P85 arredonda pra cima.
    curvas = {
        "d1": {10: 2}, "d2": {10: 2}, "d3": {10: 2}, "d4": {10: 2}, "d5": {10: 6},
    }
    p85 = esc.curva_percentil(curvas, p=0.85)
    assert p85[10] > 2          # nao e o dia mediano
    assert p85[10] <= 6


def test_curva_percentil_arredonda_pra_cima():
    # caixa e inteiro: 2.3 caixas = 3 caixas
    curvas = {"d1": {5: 2}, "d2": {5: 3}}
    assert esc.curva_percentil(curvas, p=0.85) == {5: 3}


def test_dia_sem_o_slot_conta_como_zero():
    # se num dia o slot nem existiu (loja fechada mais cedo), a demanda foi 0
    curvas = {"d1": {5: 4}, "d2": {}, "d3": {}, "d4": {}, "d5": {}}
    p85 = esc.curva_percentil(curvas, p=0.85)
    assert p85[5] <= 4


def test_cobertura_de_um_slot_pede_um_turno():
    total, inicios = esc.cobertura_minima({10: 1}, slots_turno=13, slots_produtivos=12)
    assert total == 1


def test_cobertura_cobre_a_demanda_toda():
    # demanda de 2 caixas em 12 slots seguidos -> 2 turnos bastam
    curva = {s: 2 for s in range(10, 22)}
    total, inicios = esc.cobertura_minima(curva, slots_turno=13, slots_produtivos=12)
    assert total == 2


def test_cobertura_pede_mais_turno_quando_o_dia_e_longo():
    # 19 slots (9h30) com 1 caixa: um turno de 12 produtivos nao cobre -> 2
    curva = {s: 1 for s in range(11, 30)}
    total, inicios = esc.cobertura_minima(curva, slots_turno=13, slots_produtivos=12)
    assert total == 2


def test_cobertura_e_realmente_suficiente():
    curva = {10: 1, 11: 3, 12: 3, 13: 2, 14: 1}
    total, inicios = esc.cobertura_minima(curva, slots_turno=13, slots_produtivos=12)
    cobertura = esc.cobertura_de(inicios, slots_turno=13, slots_produtivos=12)
    for s, exigido in curva.items():
        assert cobertura.get(s, 0) >= exigido
    assert total == sum(inicios.values())


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dim_escala.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dim_escala'`

- [ ] **Step 3: Write minimal implementation**

```python
# -*- coding: utf-8 -*-
"""Agregacao P85 entre os dias + conversao da curva em escala de turnos.

O P85 E a margem de seguranca, e ela e explicita: em vez de inventar um fator
de correcao, dimensiona-se para o dia RUIM (85o percentil) e nao para o dia
mediano. Consequencia declarada: ~15% dos dias daquele dia da semana estouram
a meta. Isso e a escolha, nao um defeito.

Turno CLT 6h em slots de 30min: 13 slots de presenca (6h30), 12 produtivos
(6h), 1 de intervalo. O intervalo modelado (30min) e 10min maior que o real
(20min) — conservador de proposito.
"""
import math

import dim_servico


def curva_percentil(curvas_por_dia, p=0.85):
    """Por slot, o percentil p entre os dias, arredondado pra CIMA (caixa e
    inteiro). Dia em que o slot nao existiu conta como 0 caixa."""
    slots = set()
    for curva in curvas_por_dia.values():
        slots.update(curva.keys())
    saida = {}
    for s in sorted(slots):
        valores = [curva.get(s, 0) for curva in curvas_por_dia.values()]
        saida[s] = int(math.ceil(dim_servico.percentil(valores, p) - 1e-9))
    return saida


def cobertura_de(inicios, slots_turno=13, slots_produtivos=12):
    """Caixas cobertos por slot, dado {slot_inicial: quantos turnos}.

    O turno ocupa slots_turno slots; slots_turno - slots_produtivos deles sao
    intervalo. O intervalo e alocado no ULTIMO slot da presenca: como a
    cobertura e checada contra a curva, por o intervalo no fim e o pior caso e
    portanto seguro (nunca promete cobertura que nao existe no miolo do turno).
    """
    cobertura = {}
    for inicio, n in inicios.items():
        if n <= 0:
            continue
        for i in range(slots_produtivos):
            s = inicio + i
            cobertura[s] = cobertura.get(s, 0) + n
    return cobertura


def cobertura_minima(curva, slots_turno=13, slots_produtivos=12):
    """Menor numero de turnos que cobre a curva. Devolve (total, {inicio: n}).

    Guloso da esquerda para a direita: no primeiro slot descoberto, abre os
    turnos que faltam comecando NELE (comecar antes so desperdicaria os slots
    ja cobertos; comecar depois deixaria este slot descoberto). Para turnos de
    comprimento fixo e demanda por slot, este guloso e otimo.
    """
    exigido = {s: c for s, c in curva.items() if c > 0}
    if not exigido:
        return 0, {}
    inicios = {}
    for s in sorted(exigido):
        cobertura = cobertura_de(inicios, slots_turno, slots_produtivos)
        falta = exigido[s] - cobertura.get(s, 0)
        if falta > 0:
            inicios[s] = inicios.get(s, 0) + falta
    return sum(inicios.values()), inicios
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dim_escala.py -v`
Expected: PASS — 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/dim_escala.py tests/test_dim_escala.py
git commit -m "feat(dim): agregacao P85 (a margem) + cobertura de turnos CLT 6h"
```

---

### Task 8: CLI, relatório e execução no ponte

**Files:**
- Create: `src/dimensionamento_caixas.py`
- Modify: `STATUS.md` (log de progresso — combinado do repo)

**Interfaces:**
- Consumes: todos os módulos `dim_*`, `db.conectar`, `db.consultar`.
- Produces: executável `python src/dimensionamento_caixas.py [--desde YYYY-MM-DD] [--p 0.85] [--stress 0.10] [--corte-handover 120]`.

- [ ] **Step 1: Escrever o CLI**

```python
# -*- coding: utf-8 -*-
"""Dimensionamento de caixas e operadoras por dia da semana.

Responde: quantos PDVs (min/max por faixa) e quantas operadoras por dia da
semana, para 95% dos clientes esperarem menos de 3 min na fila.

Spec: docs/superpowers/specs/2026-07-17-dimensionamento-caixas-design.md
Roda no PC-ponte (unica maquina que alcanca o banco).

Uso:
  python src/dimensionamento_caixas.py
  python src/dimensionamento_caixas.py --desde 2026-01-22 --p 0.85
"""
import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402
import dim_dimensionador  # noqa: E402
import dim_erlang  # noqa: E402
import dim_escala  # noqa: E402
import dim_queries  # noqa: E402
import dim_saturacao  # noqa: E402
import dim_servico  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIAS = {2: "segunda", 3: "terca", 4: "quarta", 5: "quinta", 6: "sexta", 7: "sabado"}
META_PCT, META_SEG = 0.95, 180.0


def _hora(slot):
    return "%02d:%02d" % (slot * 30 // 60, slot * 30 % 60)


def carregar_config(caminho):
    caminho = caminho or os.path.join(RAIZ, "config.local.json")
    if not os.path.exists(caminho):
        raise SystemExit("[ERRO] Preencha config.local.json (secao db) primeiro.")
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def conferir_fonte(conn, desde):
    """Prova contabil: tbCupom tem que bater com o consolidado do ERP."""
    consolidado = {r["dia"]: int(r["cupons"])
                   for r in db.consultar(conn, dim_queries.CONFERENCIA_CONSOLIDADO
                                         .format(desde=desde))}
    return consolidado


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Dimensionamento de caixas por dia da semana")
    ap.add_argument("--desde", default="2026-01-22", help="data inicial YYYY-MM-DD")
    ap.add_argument("--p", type=float, default=0.85, help="percentil do dia (a margem)")
    ap.add_argument("--stress", type=float, default=0.10, help="sensibilidade +-X na demanda")
    ap.add_argument("--corte-handover", type=float, default=120.0)
    ap.add_argument("--c-max", type=int, default=12)
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    cfg = carregar_config(args.config)
    conn = db.conectar(cfg["db"])
    try:
        cupons = db.consultar(conn, dim_queries.CUPONS.format(desde=args.desde))
        consolidado = conferir_fonte(conn, args.desde)
    finally:
        conn.close()
    if not cupons:
        raise SystemExit("[ERRO] Nenhum cupom no periodo.")

    # 1) conferencia da fonte contra o consolidado do ERP
    nao_cancelados = {}
    for c in cupons:
        if not c["cancelado"]:
            nao_cancelados[c["dia"]] = nao_cancelados.get(c["dia"], 0) + 1
    divergentes = [d for d, n in nao_cancelados.items()
                   if d in consolidado and consolidado[d] != n]
    print("== Conferencia da fonte (tbCupom x tbConsPDVOperador) ==")
    print("   dias conferidos: %d | divergentes: %d" % (len(consolidado), len(divergentes)))
    if divergentes:
        print("   [ATENCAO] dias que NAO batem: %s" % sorted(divergentes)[:10])

    # 2) handover + servico
    handover = dim_servico.estimar_handover(cupons, args.corte_handover)
    duracoes = dim_servico.duracoes(cupons)
    print("\n== Servico ==")
    print("   cupons: %d (cancelados: %d)" % (len(cupons), sum(c["cancelado"] for c in cupons)))
    print("   duracao mediana: %.0fs | handover estimado: %.0fs (corte %.0fs)"
          % (dim_servico.percentil(duracoes, 0.5), handover, args.corte_handover))

    # 3) saturacao (demanda censurada)
    saturados = dim_saturacao.slots_saturados(cupons)
    print("\n== Saturacao (demanda censurada) ==")
    print("   slots saturados: %d" % len(saturados))
    if saturados:
        print("   [ATENCAO] nesses slots o numero abaixo e PISO, nao estimativa.")

    # 4) dimensionar cada dia
    por_dia = {}
    for c in cupons:
        por_dia.setdefault((c["dia"], c["dow"]), []).append(c)
    rng = random.Random(20260717)
    curvas, teto_total = {}, set()
    for (dia, dow), lista in por_dia.items():
        lista.sort(key=lambda c: c["inicio"])
        chegadas = [c["inicio"].hour * 3600 + c["inicio"].minute * 60 + c["inicio"].second
                    for c in lista]
        servicos = [(c["fim"] - c["inicio"]).total_seconds() + handover for c in lista]
        curva, teto = dim_dimensionador.dimensionar_dia(
            chegadas, servicos, META_PCT, META_SEG, args.c_max)
        curvas.setdefault(dow, {})[dia] = curva
        teto_total |= {(dia, s) for s in teto}

    # 5) agregar no percentil e montar a escala
    print("\n== Caixas necessarios (P%d dos dias, 95%% < 3min) ==" % int(args.p * 100))
    for dow in sorted(curvas):
        p_curva = dim_escala.curva_percentil(curvas[dow], args.p)
        ativos = {s: c for s, c in p_curva.items() if c > 0}
        if not ativos:
            continue
        total, inicios = dim_escala.cobertura_minima(ativos)
        pico_slot = max(ativos, key=lambda s: ativos[s])
        print("\n   %-8s min %d caixa(s) | max %d caixa(s) (pico %s) | %d operadora(s)"
              % (DIAS.get(dow, dow), min(ativos.values()), max(ativos.values()),
                 _hora(pico_slot), total))
        print("      curva: " + " ".join("%s=%d" % (_hora(s), ativos[s])
                                         for s in sorted(ativos)))

    # 6) ociosidade: exigido x aberto de fato
    print("\n== Ociosidade (exigido x aberto de fato) ==")
    for dow in sorted(curvas):
        p_curva = dim_escala.curva_percentil(curvas[dow], args.p)
        abertos = {}
        for dia in curvas[dow]:
            for c in por_dia[(dia, dow)]:
                s = dim_saturacao.slot_de(c["inicio"])
                abertos.setdefault(s, {}).setdefault(dia, set()).add(c["pdv"])
        deltas = []
        for s in sorted(p_curva):
            if p_curva[s] <= 0 or s not in abertos:
                continue
            medio = sum(len(v) for v in abertos[s].values()) / len(abertos[s])
            deltas.append((s, medio - p_curva[s]))
        if deltas:
            pior = max(deltas, key=lambda x: x[1])
            print("   %-8s excesso medio %.1f caixa(s) | pior faixa %s (+%.1f)"
                  % (DIAS.get(dow, dow), sum(d for _, d in deltas) / len(deltas),
                     _hora(pior[0]), pior[1]))

    # 7) stress: +-X% na demanda
    print("\n== Sensibilidade (demanda %+.0f%%) ==" % (args.stress * 100))
    for fator, rotulo in ((1 + args.stress, "+"), (1 - args.stress, "-")):
        totais = {}
        for dow, por in curvas.items():
            novas = {}
            for dia, _curva in por.items():
                lista = sorted(por_dia[(dia, dow)], key=lambda c: c["inicio"])
                if fator > 1:
                    extras = rng.sample(lista, int(len(lista) * (fator - 1)))
                    lista = sorted(lista + extras, key=lambda c: c["inicio"])
                else:
                    lista = sorted(rng.sample(lista, int(len(lista) * fator)),
                                   key=lambda c: c["inicio"])
                chegadas = [c["inicio"].hour * 3600 + c["inicio"].minute * 60
                            + c["inicio"].second for c in lista]
                servicos = [(c["fim"] - c["inicio"]).total_seconds() + handover
                            for c in lista]
                nc, _ = dim_dimensionador.dimensionar_dia(
                    chegadas, servicos, META_PCT, META_SEG, args.c_max)
                novas[dia] = nc
            pc = dim_escala.curva_percentil(novas, args.p)
            ativos = {s: c for s, c in pc.items() if c > 0}
            if ativos:
                totais[dow] = dim_escala.cobertura_minima(ativos)[0]
        print("   %s%.0f%%: %s" % (rotulo, abs(args.stress * 100),
                                   " | ".join("%s=%d" % (DIAS.get(d, d), t)
                                              for d, t in sorted(totais.items()))))

    if teto_total:
        print("\n[ATENCAO] %d (dia, slot) bateram no teto de %d caixas: ali o numero "
              "e PISO." % (len(teto_total), args.c_max))
    print("\nLimites declarados: o modelo assume a operadora como gargalo do caixa "
          "(empacotador nao esta no banco); a escala P%d falha por construcao em "
          "~%d%% dos dias." % (int(args.p * 100), int((1 - args.p) * 100)))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Rodar a suíte inteira (dev, sem banco)**

Run: `python -m pytest tests/ -v`
Expected: PASS — todos os `test_dim_*` passam. Os módulos puros não tocam no banco.

- [ ] **Step 3: Commit antes de ir ao ponte**

```bash
git add src/dimensionamento_caixas.py
git commit -m "feat(dim): CLI do dimensionamento (curva de caixas + escala + ociosidade + stress)"
git push
```

- [ ] **Step 4: Rodar no ponte (única máquina que alcança o banco)**

```bash
ssh -i ~/.ssh/id_ed25519_ponte User@100.99.176.6 "cd C:\Users\User\erp-bridge-atacaderj && git pull && python -m pytest tests/ -q && python src/dimensionamento_caixas.py"
```

Expected: a conferência da fonte fecha com **0 divergentes** (é a prova de que a extração está certa). Depois as tabelas de caixas por dia da semana, ociosidade e sensibilidade.

**Se houver divergentes, PARE.** A extração está errada e todo número depois dela também. Investigue o recorte antes de reportar qualquer resultado.

- [ ] **Step 5: Registrar no STATUS.md e commitar**

Acrescentar linha no "Log de progresso" com a data (combinado do repo: o repositório é a memória do projeto).

```bash
git add STATUS.md
git commit -m "status: dimensionamento de caixas rodado no ponte (resultado no log)"
git push
```

---

## Self-Review

**Cobertura do spec:** cada componente do spec tem tarefa — `extracao` (T2), `servico`/handover (T3), `saturacao` (T4), `simulador` (T5), `dimensionador` (T6), `agregador`+`escala` (T7), `relatorio` (T8). O Erlang-C (validação, seção "Verificação" do spec) virou T1. Os "Limites conhecidos" do spec são impressos pelo CLI em T8. Min/max de caixas e headcount por dia da semana: T8, passo 1. Ociosidade: T8. Stress ±10%: T8. Sensibilidade ao corte do handover: **exposta via `--corte-handover`** — rodar com 90/120/180 e comparar.

**Tipos:** `curva` é sempre `dict[int, int]` (slot → caixas); `esperas` é `list[float | None]`; chaves de saturação são `(dia, slot)`; `curvas_por_dia` é `{dia: curva}`. `dim_escala.cobertura_de` é usada no teste de T7 e definida no mesmo módulo.

**Fora de escopo (YAGNI):** agendamento, WhatsApp, dashboard HTML.
