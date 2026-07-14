# Design — Relatório diário "vendidos abaixo do custo" (WhatsApp 06:00)

**Data:** 2026-07-14 · **Status:** aprovado pelo dono em 2026-07-14
**Repo:** `erp-bridge-atacaderj` (independe do detector; deploy imediato)

## O que é

Toda manhã, mensagem de WhatsApp para **5521970296224** com os itens vendidos
no **dia anterior útil** (segunda reporta sábado; domingo fechado) com
**markup ≤ 3%** (abaixo do custo + zona de perigo até +3% acima), no formato
minimalista aprovado:

```
>Produtos vendidos abaixo do custo dia 13/07<

QJ MUSSARELA CRIOULO
venda 9,50 · custo 10,00 · -5,0%

OLEO SOJA SOYA 900ML
venda 10,20 · custo 10,00 · +2,0%

2 itens · prejuízo potencial R$ 137,40
```

- Título EXATO: `>Produtos vendidos abaixo do custo dia <dd/MM><` .
- Por item: `NOME` (linha 1) e `venda X,XX · custo Y,YY · ±Z,Z%` (linha 2),
  vírgula decimal, sinal no markup, ordenado do pior markup para o melhor.
- Rodapé: `N itens · prejuízo potencial R$ V` — prejuízo = Σ max(0,
  (custo−venda)×qtd) só dos vendidos abaixo do custo. Se houver itens sem
  custo cadastrado (custo nulo/0), acrescentar linha `⚠ N itens sem custo
  cadastrado (fora da conta)`.
- Zero itens → mensagem `✅ nenhum item vendido no/abaixo do custo em <dd/MM>`
  (confirma que o robô rodou).
- Mais de 60 itens → lista os 60 piores + linha `… e mais N itens`.

## Definições de cálculo

- Fonte: consulta DIRETA ao ERP (SELECT dedicado, só leitura, mesmo estilo da
  query VENDAS de `src/queries.py`), agregada por produto no dia:
  `venda_media = Σ(valor vendido) ÷ Σ(qtd)`; `custo = custo do dia congelado
  na venda` (mesma origem do `custo_venda` da extração do detector-estoque —
  o implementador DEVE verificar em queries.py a semântica unitário×total e
  ponderar corretamente; validar num item conhecido contra o ERP).
- `markup = venda_media/custo − 1` (custo > 0). Filtro: `markup ≤ margemMax`
  (config, default 0.03).

## Entrega e agendamento (atraso de sync do ERP tratado)

- `src/abaixo_custo.py`: CLI `python src/abaixo_custo.py [--dia YYYY-MM-DD]
  [--config ...] [--dry-run]` — monta a mensagem e envia via
  `node scripts/whatsapp/enviar.mjs --para <numero> --texto-arquivo <tmp>`
  (o enviar.mjs já tem lock de sessão e mimetypes). `--dry-run` imprime sem
  enviar (teste).
- Guardas de execução (idempotência do agendador):
  1. carimbo `saida/abaixo-custo/enviado-<dia>.txt` existe → exit 0;
  2. ERP sem NENHUMA venda no dia-alvo → exit 0 SILENCIOSO (retry pega —
     é o atraso de sync das manhãs, verificado em 13-14/07);
  3. dados presentes → monta, envia 1x, grava o carimbo (com a mensagem
     enviada dentro, para auditoria).
- Tarefa Windows **"AtacadeRJ - Abaixo do Custo"** (`scripts/registrar-abaixo-custo.ps1`,
  padrão dos scripts do repo): gatilho diário 06:00 com repetição a cada
  30 min por 6h (até 12:00), StartWhenAvailable.
- Config (`config.local.json`, gitignored):
  `"abaixo_custo": { "numero": "5521970296224", "margemMax": 0.03 }`
  (example com numero vazio → script sai com aviso se não configurado).

## Testes

- Funções puras separadas do I/O: `filtrar_itens(linhas, margemMax)` e
  `montar_mensagem(dia, itens, sem_custo)` — testadas em
  `tests_abaixo_custo.py` (rodável com `python tests_abaixo_custo.py`,
  asserts diretos, padrão simples): filtro nos limites (−5%, +2%, +3%,
  +3,1%), custo 0 separado, ordenação, título/formatos exatos, zero itens,
  corte em 60, prejuízo só dos abaixo.
- Validação real no deploy: `--dia 2026-07-13 --dry-run` conferido a olho +
  1 envio real de teste autorizado pelo dono.

## Riscos

| Risco | Resposta |
|---|---|
| Semântica errada de valor/custo (unitário × total) | verificação obrigatória contra um item conhecido no ERP antes do 1º envio |
| Sync do ERP atrasar além de 12:00 | último retry 12:00; dia sem envio fica visível (sem carimbo); avaliar janela maior se ocorrer |
| Conflito de sessão WhatsApp | enviar.mjs já usa o lock compartilhado (.sessao.lock) |
| Segunda-feira | dia-alvo = sábado (previousBusinessDay pulando domingo) |
