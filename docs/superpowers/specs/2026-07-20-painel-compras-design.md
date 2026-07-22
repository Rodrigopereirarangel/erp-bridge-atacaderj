# Painel de Compras (TV + PC) — Design

**Data:** 2026-07-20 · **Repo:** `erp-bridge-atacaderj` · **Status:** aprovado pelo dono (brainstorming 20/07)

## 1. Objetivo

Dashboard do **setor de compras** exibido numa **TV grande** (sem interação) e aberto
nos **PCs dos compradores** (interativo), com 4 relatórios numa tela única:

1. **Validade × Promoção relâmpago** — o que está em relâmpago e quando vence o estoque.
2. **Ruptura de estoque** — o que provavelmente esgotou e precisa comprar (motor já pronto).
3. **Cobrança de fornecedor** — pedidos fechados há ≥7 dias sem entrega (apoiar a cobrança).
4. **Preço concorrente** — reuso do `revisao_Sxx.html` que o pricing já gera.

Custo recorrente R$ 0, tudo local no PC-ponte, padrão dos demais sistemas AtacadeRJ.

## 2. Decisões de design (respostas do dono)

| Decisão | Escolha |
|---|---|
| Plataforma | HTML local gerado no PC-ponte (custo pode aparecer; rede local) |
| Layout | **Tela única, 4 quadrantes** — não abas; feita para TV grande |
| Interação na TV | **Nenhuma** — rodízio automático; detalhe interativo só nos PCs |
| Fonte da ruptura | **Consumir o detector-ruptura-estoque** (EMA por item, cobertura invertida, pedidos 🛒/✅) — aposenta a regra "curva A = 10 dias sem vender" |
| Preço concorrente | **Reaproveitar o HTML de revisão do pricing** — zero lógica nova |
| Promoção relâmpago | **Achar o local certo no ERP** (investigação de schema; fallback documentado em §10) |
| Onde vive o gerador | **Módulo novo no erp-bridge** (hub que já tem agendamento, SQL e validades) |

## 3. Arquitetura e fluxo de dados

```
                       ┌── PROMO_RELAMPAGO (query nova) ──┐
ERP Solidcon ──SELECT──┤   VALIDADES (query existente)    ├─┐
 (só leitura)          └── PEDIDOS_COBRANCA (query nova) ─┘ │
                                                            ▼
detector-ruptura-estoque  ── data/rounds/<id>.json ──► painel_compras.py ──► painel/index.html
                                                            ▲                (arquivo único,
pricing-atacaderj ── dados/revisao_Sxx.html (cópia) ────────┘                 CSS/JS/dados embutidos)
```

- `src/painel_compras.py` (novo): lê as 4 fontes, monta um JSON por quadrante e
  renderiza `painel/index.html` — **arquivo único, offline** (sem CDN, sem internet),
  mesmo padrão dos HTMLs que a bridge já gera.
- Cada quadrante carrega **carimbo próprio** (`gerado_em` da fonte), exibido na tela.
- O `revisao_Sxx.html` mais recente do pricing é **copiado** para `painel/` a cada
  geração (link estável, pasta autossuficiente para o servidor HTTP).
- `--demo` da bridge também gera o painel com dados falsos (conferir formato sem ERP).

## 4. Os 4 quadrantes

### 4.1 Validade × Relâmpago
- **Fonte:** query nova `PROMO_RELAMPAGO` (§10a) × query `VALIDADES` existente
  (3 fontes unidas, ~82% do catálogo, 2 validades mais recentes por produto).
- **Linha:** código, descrição, preço promo, vigência da promo, validade(s),
  **dias até vencer**, badge de urgência (limiar configurável, padrão ⚠ <30 dias).
- Produto em relâmpago **sem validade registrada** aparece com marca própria
  ("sem validade registrada") — não some; o comprador precisa ver o buraco.
- **TV:** contadores (nº em relâmpago / nº vencendo < limiar) + top urgentes.
- **PC:** tabela completa com busca, filtro (só urgentes / sem validade) e ordenação.

### 4.2 Ruptura de estoque
- **Fonte:** rodada mais recente em `data/rounds/*.json` do
  `detector-ruptura-estoque-atacaderj` (Fase 1 MVP em produção local; formato exato
  confirmado na investigação §10c).
- **Linha:** produto, prioridade (certeza × volume un/mês × R$), status do pedido
  (🛒 sem pedido / ✅ pedido lançado), curva ABC.
- **Read-only** no painel; o feedback (🔴/🟢) continua no dashboard próprio do
  detector — o quadrante linka para lá.
- **TV:** contador de prováveis rupturas **sem pedido** + top da fila.

### 4.3 Cobrança de fornecedor (novo relatório)
- **Fonte:** query nova `PEDIDOS_COBRANCA` — pedidos de compra (`tbPedido`,
  `inEntrada=1`) **abertos** (`dtAtendido IS NULL`), agrupados por **pedido × fornecedor**,
  com `dtPedido`, `tbPedidoCompra.dtEntregaPrevista`, itens/valor pendentes.
- **Entra na lista quando:** dias em aberto ≥ limiar (padrão **7**, configurável)
  — e SÓ isso (dono, 22/07: previsão vencida deixou de ser porta de entrada;
  pedido de 1 dia com previsão de ontem furava a regra. O atraso vs previsão
  continua como coluna) — **dentro de uma janela máxima**
  (`cobranca_max_dias`, padrão **45** — decisão do dono 20/07: acima de 45 dias
  não aparece no relatório). Motivo (medido 2026-07-20): a loja não encerra
  pedido morto no ERP — 534 abertos, 494 com 7+ dias, com pedidos de janeiro
  ainda "abertos". Sem a janela o quadrante nasceria inútil; os mais velhos que
  ela viram só um contador honesto de "abandonados" no card.
- **Ordem CRESCENTE de dias em aberto** (decisão do dono 20/07): trabalhar
  primeiro o que ainda tem salvação; empate = maior valor pendente primeiro.
- **Cores do badge de dias:** amarelo até `cobranca_alerta_dias` (padrão
  **21**), vermelho dali em diante.
- **Linha:** fornecedor, nº do pedido, data do pedido, **dias em aberto**, previsão
  de entrega (e atraso vs previsão), valor pendente; telefone do fornecedor se a
  investigação §10b confirmar o campo em `tbPessoa` (ligar na hora).
- Ordenado por dias em aberto (pior primeiro). **TV:** contador + piores atrasos.

### 4.4 Preço concorrente
- **Fonte:** cópia do `revisao_Sxx.html` mais recente de `pricing-atacaderj/dados/`.
- **PC:** o quadrante abre o HTML de revisão completo (visão do pricing).
- **TV:** só card-resumo (semana vigente + data da extração) — o HTML do pricing
  não é desenhado para TV e não entra no rodízio em tela cheia.
- Atualiza no ritmo semanal do pricing; card mostra a idade do dado.

## 5. Modos de exibição (mesmo `index.html`)

- **Modo TV (`#tv` na URL):** tema escuro, tipografia grande (legível a metros),
  visão geral com 4 quadrantes; **rodízio automático** — destaca cada relatório em
  tela cheia por ~20s e volta à visão geral (concorrente só como card, §4.4).
  Auto-reload da página a cada poucos minutos para pegar novas gerações.
  Zero dependência de mouse/teclado.
- **Modo PC (padrão):** visão geral idêntica; **clicar num quadrante abre o
  detalhe** (tabela com busca, filtros, ordenação); Esc/botão volta. Sem rodízio.
  **Colunas dinâmicas** (20/07): todo cabeçalho é clicável — 1º clique ordena
  crescente (▲), 2º decrescente (▼), 3º volta à ordem original; vale na visão
  geral e no detalhe. Tabela vazia mostra "nenhum item para mostrar" (o detalhe
  de um quadrante indisponível nunca fica idêntico ao card). Clique no card do
  concorrente abre a revisão em nova aba, com fallback na mesma aba se o
  navegador bloquear popup.
- Implementação da UI segue as skills `dataviz` e `frontend-design` na fase de
  implementação (contraste para TV, hierarquia dos contadores, tabelas legíveis).

## 6. Acesso e agendamento (PC-ponte)

- **Servidor HTTP mínimo** servindo a pasta `painel/`, registrado como tarefa
  agendada **no boot** do ponte. URL fixa na rede da loja
  (ex.: `http://192.168.0.164:8477/`, porta em `painel.porta_http`) — bookmark nos PCs; a TV é um PC/stick
  abrindo a URL em tela cheia com `#tv`.
- **Geração** (`register-tasks.ps1`, novas tarefas):
  - **06:00** diário — após bridge movimentos (05:00) e detector (05:30);
  - junto das rodadas de **catálogo** (08/12/15/18h) — promo relâmpago e validade
    ficam frescas ao longo do dia; ruptura/cobrança/concorrente reaproveitam o
    último dado disponível.
- Segurança: nada muda no servidor do ERP; o painel expõe custo **somente na rede
  local** (decisão §2); a pasta servida contém só os artefatos do painel.

## 7. Configuração (`config.local.json`, seção nova `painel`)

```json
"painel": {
  "dir_saida": "C:/.../painel",
  "porta_http": 8477,
  "cobranca_dias_limiar": 7,
  "cobranca_max_dias": 60,
  "validade_urgente_dias": 30,
  "rodizio_segundos": 20,
  "reload_minutos": 5,
  "pricing_dados_dir": "C:/Users/User/pricing-atacaderj/dados",
  "detector_rounds_dir": "C:/Users/User/detector-ruptura-estoque-atacaderj/data/rounds",
  "detector_dashboard_url": "http://localhost:5173"
}
```

## 8. Erros e staleness

- **Isolamento por fonte:** cada uma das 4 fontes tem try/except próprio; falha de
  uma **nunca** aborta a geração. Quadrante afetado mostra
  "indisponível desde \<última geração boa\>" e o erro vai para `bridge_erros.log`.
- **Staleness visível:** todo quadrante exibe o carimbo do seu dado (TV inclusive).
  Rodada do detector mais velha que N horas ganha badge "dado de \<data\>".
- Sem revisão do pricing na semana → card do concorrente mostra a última semana
  disponível com a idade explícita.

## 9. Testes (pytest, padrão do repo)

- Cruzamento relâmpago × validade (fixtures: com 2 validades, com 1, sem validade,
  promo sem produto no catálogo).
- Regras de cobrança: ≥7 dias, previsão vencida, atendimento parcial, pedido novo
  (<7 dias e sem previsão vencida → fora).
- Seleção do `revisao_Sxx.html` mais recente (ordenação por semana, pasta vazia).
- Leitor de rounds do detector: ausente, vazio, malformado → quadrante indisponível
  sem derrubar a geração.
- Render do HTML: JSON inline válido, escaping de descrições, os 4 carimbos presentes.
- Demo de ponta a ponta: `--demo` produz `painel/index.html` válido.

## 10. Investigações pré-implementação — RESOLVIDAS (medidas no ponte, 2026-07-20)

a. **Marcador de relâmpago: `dbo.tbPromocaoRelampago`** (cdProduto, dtInicio,
   dtFim, vlVenda) — 371 linhas, **247 vigentes** na medição. `cdTipoPromocao`
   vem NULL nas linhas vivas; o marcador real é estar na tabela, vigente.
   O fallback (toda promoção vigente do catálogo) ficou desnecessário.
b. **Fornecedor:** NÃO está em `tbPedido` — vem de
   `tbPedidoCompra.cdPessoaComercial → tbPessoa.nmPessoa` (join validado).
   **Telefone:** `dbo.tbTelefone(cdPessoa, cdTelefone=1, DDD, Numero, Contato)`,
   join direto por cdPessoa (há lixo "00/00000000" — a projeção esconde).
   **Valor pendente:** `vlPedidoItem` é POR VOLUME (mesma convenção do
   PEDIDOS_VENDA) → `(qtPedidoItem − qtAtendida) × vlPedidoItem`.
   **Descoberta que virou regra (§4.3):** 534 pedidos abertos, 494 com 7+ dias
   (pedidos de janeiro nunca encerrados) → janela `cobranca_max_dias`.
c. **Round do detector-estoque:** `data/rounds/<YYYY-MM-DD>.json` =
   `{id, refDate, items[]}`, items já ordenados por `scorePrioridade` desc;
   campos usados: codigo, descricao, scorePrioridade, probabilidade, temPedido,
   curvaABC, unMes, rsHist, diasParado, coberturaEsgotada. Dashboard do
   detector: porta 5173.

## 11. Fora de escopo (YAGNI)

- Envio por WhatsApp (visualizador não executa JS; se um resumo estático diário
  for desejado depois, é projeto separado).
- Feedback/edição no painel (feedback de ruptura fica no dashboard do detector).
- Acesso fora da rede local / artifact claude.ai (custo não sai da rede — Cenário A).
- Novas visões de concorrência além do reuso do HTML do pricing.

## 12. Riscos e limites conhecidos

- Cobertura de validade ~82% do catálogo; validades digitadas fora das 3 fontes
  unidas não aparecem (limite documentado na query `VALIDADES`).
- Volume de relâmpago vigente é alto (247 na medição de 20/07) — a TV mostra
  top-N por urgência e os contadores mostram o total; a lista completa fica no
  modo PC.
- O rodízio da TV mostra top-N por quadrante; a lista completa é sempre acessível
  no modo PC (nenhum corte silencioso: contadores mostram o total).

## 13. Histórico semanal por aba (aprovado pelo dono em 21/07)

Ao abrir a lista de uma aba, o ÚLTIMO TERÇO da tela mostra um gráfico de
barras (SVG puro, offline) com amostras SEMANAIS (toda segunda desde 06/04 +
o ponto de hoje) da mesma medida do chip do título. Cobrança e Pré-pedidos
ficam SEM gráfico (dono, 21/07 — as séries continuam gravadas). No
Concorrente os gráficos ficam na TELA CHEIA da revisão (rodapé fixo
injetado na cópia; a prévia do card esconde): DOIS gráficos — itens acima
e abaixo da concorrência (só pesquisa fresca ≤10d, mesma regra da poda).
A cópia também é podada (nota verde e descrição escondidas) e KVI é
renomeado para "Itens acima de concorrência" (chip e selos das linhas);
o original do pricing fica intacto. O gráfico da Ruptura empilha SÓ curva
A (azul) + curva B (âmbar) — hover mostra a contagem de cada curva; curva
usada é a ATUAL aplicada ao passado (não há curva histórica). A mescla
poda dias soltos: só segundas + o ponto mais recente ficam na série.

- **Fonte**: `painel/historico.json` — mantido por `src/historico_painel.py`
  e embutido no payload (`historico`). Merge preservador: mesma data
  substitui, pontos que saíram da janela do ERP são PRESERVADOS (a história
  nunca encolhe).
- **Séries exatas (recomputadas a cada geração, point-in-time)**: relâmpago
  (vigências), cobrança (dtPedido/dtAtendido + regra vigente), sell-out (nº
  de itens com sell-out VIGENTE — dia entre início e fim da promoção; medida
  trocada de R$ em aberto para contagem a pedido do dono em 21/07),
  pré-pedidos (criação ≤ dia <
  criação+21d, não atendidos até o dia; aproximação: `inEncerrado` não tem
  data, usa-se `dtPrePedidoAtendido`).
- **Abaixo do custo**: nº de itens que VENDERAM abaixo do custo na semana
  (realizado, das vendas com custo do dia) — irmã honesta da métrica do chip
  (que é prospectiva, preço de prateleira).
- **Ruptura**: replay do PRÓPRIO motor do detector com refDate em cada
  segunda (`scripts/replay_ruptura.js`, chamado 1x por
  `scripts/backfill_historico_ruptura.py` no ponte); CSVs cortados no
  refDate (nada do futuro vaza). O ponto de cada dia vem da rodada real.
  Régua do corte (>0.75 · >1d · guardrail) duplicada em TRÊS lugares —
  template (`Q.ruptura.corte`), `historico_painel.corte_ruptura` e o wrapper
  — manter em sincronia. Limitações honestas: replays mais antigos têm menos
  histórico de vendas atrás de si (janela ~120d); pedidos/curva não entram
  (o corte não os usa); se a régua mudar, o passado recalcula junto no
  próximo backfill.

## 14. 8ª aba — ♻️ Troca / Avaria (aprovada pelo dono em 22/07)

Saldo PARADO na área de troca/avaria (estoque tipo 3 do ERP; medido em
22/07: 1.369 super-produtos, R$ 664,8 mil ao custo contábil). Fontes vivas
descobertas na sonda: `tbEstoqueFisico` (qt por PRODUTO), `tbEstoqueContabil`
(R$ por SUPERPRODUTO) e `tbEstoqueMovimento` (movimentos diários desde
15/10/2025). A tabela `avaria` (carga inicial morta) e a MIS vazia NÃO servem.

- Lista por superproduto: qtd, R$ parado (contábil, exato), "parado há"
  (dias desde a última movimentação tipo 3); ordena por R$.
- "Esquecido" = sem movimentação há mais de `avaria_esquecido_dias` (60):
  tag vermelha + chip próprio; no detalhe, o terço de baixo é DIVIDIDO —
  gráfico da evolução à esquerda, caixa dos esquecidos (top R$) à direita.
- Série semanal `avaria` (R$ parado): contábil ATUAL menos o líquido dos
  movimentos após cada data. Aproximação documentada: movimentos ao custo
  do movimento vs contábil a custo médio (divergência pequena).
