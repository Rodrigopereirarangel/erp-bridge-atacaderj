# Design — Estrutura geral: bridge → arquivo único → artifact no claude.ai (robô de upload)

**Data:** 2026-07-07 · **Status:** aprovado pelo usuário (brainstorm de 2026-07-07)
**Substitui** a versão anterior desta spec (injeção no HTML + pasta compartilhada),
descartada ao constatar que o app da cotação roda como **artifact no claude.ai**.

## Contexto e fatos que moldaram o design

- O bridge (este repo) extrai do MySQL do ERP (viewer só-leitura) no PC-ponte
  (`DESKTOP-3BLTBIV`, 24h, rede da loja) — agendado pelo Agendador de Tarefas.
- O app da cotação (`cotacao-auditoria-atacaderj`) **não é um HTML estático**:
  chama a IA do Claude (leitura de listas manuscritas, interpretação, busca
  semântica) via proxy do claude.ai e usa `window.storage`. **Ele roda como
  artifact no claude.ai** — é isso que dá IA sem API key paga (consome a sessão
  Claude de cada usuário) e storage compartilhado entre os funcionários.
- Limites do claude.ai (verificados): artifact não enxerga a rede da loja; não
  existe API para escrever no storage ou editar artifact (nem via skill, MCP,
  Cowork ou chat); republicar o HTML (~646KB) diariamente estoura limite de
  saída e arrisca corromper o app. **A única porta de escrita é um navegador
  logado usando o próprio app.**
- Decisões anteriores mantidas: loop de feedback descartado; funcionário nunca
  acessa repositório; custo/preço **nunca vão para o GitHub** (Cenário A).

## Princípio central

**Separar o app dos dados.** O app publica-se como artifact **uma vez** (link
fixo). Os dados (banco de preços) viajam todo dia como **um arquivo pequeno**,
pela porta que o app já tem: o botão de upload, que grava no storage
compartilhado e distribui a todos os usuários do artifact.

## Arquitetura (rotina diária, zero toque humano)

1. **Bridge** (agendado, ex. 05:00): extrai do MySQL e grava na pasta da loja o
   **arquivo único de importação** — catálogo unificado (atacado + varejo +
   promoção + curva ABC + custo) com data/hora de geração. Escrita atômica.
2. **Robô de upload** (agendado, ex. 05:30, mesmo PC-ponte): script
   **Playwright determinístico** (sem IA em runtime; Claude só o escreve uma
   vez) abre o link do artifact num navegador com sessão claude.ai persistente
   e sobe o arquivo pelo botão "📦 Catálogo" do app → storage compartilhado
   distribui a todos.
3. **Funcionário**: abre o link fixo do artifact (logado na própria conta
   Claude, como já é hoje) e cota. Nunca atualiza nada.
4. **Rede de segurança**: a trava `verificarBancoAtualizado()` do app acusa na
   tela se o banco não for de hoje — falha do robô **nunca é silenciosa**.

## Contingências (hierarquia)

- **Plano A (rotina):** robô agendado — zero toque.
- **Plano B (dia de falha do robô):** upload manual do mesmo arquivo — abrir o
  artifact, botão 📦, escolher o arquivo da pasta (~30s). Disparado pelo aviso
  da trava, não por vigilância humana.
- **Plano C (falha do próprio bridge/MySQL):** fluxo atual do app — upload
  manual dos 3 relatórios exportados do ERP (atacado, varejo, curva ABC).
  Permanece intacto no app.

## O arquivo único de importação

- Formato: JSON (`catalogo_bridge.json`), contendo `gerado_em`
  (data/hora) e `produtos` com as chaves que o app já usa:
  `c, p, q, v, vu, custo, cv`.
- **Regra de promoção igual à do upload manual atual** (`mesclarCatalogos`):
  quando `preco_promocao > 0` e menor que o preço, `v = promoção` — coerente
  com a spec "promoção vence = desconto zero".
- Mescla: varejo é a base completa; produto presente no atacado usa preço/qtde
  do Atacado 1; curva A marca `cv:'A'` (teto de desconto 3%, demais 5%).
- Validações antes de gravar: total de produtos plausível, data = hoje. Se a
  extração falhar, **não grava** — o arquivo anterior permanece e a trava do
  app fará seu papel.

## Mudanças concretas

### Repo `erp-bridge-atacaderj` (este)
- Nova projeção: `catalogo_bridge.json` (mescla acima + `gerado_em`), gravado
  em caminho configurável no `config.local.json`.
- Novo componente: **robô de upload** (`robo/` — script Playwright + tarefa
  agendada no `register-tasks.ps1`), com log local de sucesso/falha. Usa perfil
  de navegador persistente logado na conta claude.ai do usuário.
- O `produtos.json` e os CSVs dos detectores continuam exatamente como estão.

### Repo `cotacao-auditoria-atacaderj` (app da cotação)
- Aceitar o **arquivo único** no fluxo de atualização: além dos 3 relatórios, o
  botão "📦 Catálogo" reconhece `catalogo_bridge.json`, valida `gerado_em`
  (tem que ser de hoje) e grava direto no storage compartilhado.
- O fluxo dos 3 relatórios não muda (é o plano C).
- Sem mexer em `CATALOG` embutido, precedência de storage ou trava de data — o
  storage continua sendo a fonte, como hoje; a trava já valida por data.

### Setup único (manual, uma vez)
- Publicar o app como artifact na conta Claude do usuário; distribuir o link
  aos funcionários (cada um loga com a própria conta Claude).
- No PC-ponte: instalar Playwright, criar o perfil de navegador logado no
  claude.ai, registrar as tarefas agendadas (bridge e robô).

## Segurança

- Custo/preço não vão para o GitHub (inalterado). Eles já residem no storage
  do artifact no claude.ai — realidade atual do app, não uma mudança.
- Nenhuma porta da rede da loja é exposta à internet (sem túnel, sem MCP
  remoto). O tráfego é sempre de saída, pelo navegador do PC-ponte.
- Viewer segue só-`SELECT` com a trava do `src/db.py`; servidor do ERP intocado.

## Riscos e mitigação

- **Robô é o elo frágil** (sessão expira, claude.ai muda a interface): falha é
  visível pela trava do app; plano B leva 30s; log local do robô registra o
  motivo. O alvo dos cliques é majoritariamente o **nosso** app (DOM sob nosso
  controle), reduzindo a superfície exposta a mudanças do claude.ai.
- **Consumo de sessão dos funcionários** (limites do plano Claude de cada um):
  característica do app atual, fora do escopo desta spec.

## Plano de migração documentado (se o claude.ai inviabilizar o robô)

Caminho B: o app sai do claude.ai e roda na rede da loja; o bridge injeta o
catálogo direto no HTML (design da versão anterior desta spec); IA passa a API
key paga (custo por cotação); storage compartilhado reimplementado localmente.
Zero-toque estrutural, ao custo de abandonar o custo zero de IA.

## Fora de escopo

- Loop de feedback (apelidos/correções) — descartado em 2026-07-07.
- Auditoria (`dashboard.html`) — ferramenta do usuário, não dos funcionários.
- Pricing semanal — design separado, entra depois.
