# CLAUDE.md — instruções para o Claude no PC-ponte

Você (Claude) está rodando no **PC-ponte** da loja AtacadeRJ, dentro do projeto
`erp-bridge`. Este arquivo te dá o contexto para **continuar a implantação
sozinho** de onde a sessão anterior parou. Leia também **[STATUS.md](STATUS.md)**:
é o checklist vivo — o próximo passo é sempre o primeiro item `[ ]` não marcado.

## O que este projeto faz

Puxa dados do **ERP Solidcon (SQL Server 2014)** com login **só leitura** e gera
`produtos.json` + CSVs, **agendado 2-3x/dia**, que alimentam a **cotação (HTML)**
e os **detectores** (`detector-ruptura-atacaderj`, `detector-ruptura-estoque-atacaderj`).
É a única ponte de dados — acaba com a exportação manual de relatórios. Custo R$ 0.
O único ponto amarrado ao ERP são os 4 `SELECT` de `src/queries.py` (T-SQL,
já preenchidos e validados em 2026-07-07 — cabeçalho do arquivo documenta os
fatos do schema).

## Onde você está (topologia confirmada em produção, 2026-07-07)

- **Este PC (ponte)** = `DESKTOP-3BLTBIV`, IP `192.168.0.164`, ligado 24h, na
  rede da loja. Repo em `C:\Users\User\erp-bridge-atacaderj`.
- **Servidor do ERP** = máquina `CONCENTRADOR`, IP `192.168.0.245`, **SQL Server
  2014 porta 1433** (⚠️ NÃO é MySQL — a porta 3306 aberta lá é outra coisa).
  Databases: **`Solidcon`** (retaguarda — é o que a ponte lê), `SolidconLoja`
  (réplica PDV), `DORSAL` (frente de caixa; `tbConsVenda` = consolidado oficial
  de venda diária, útil como prova contábil).
- Login SQL somente-leitura no `config.local.json` (gitignored). Conecta da rede
  sem configuração extra no servidor.
- **Cenário A** (mantido, mecanismo revisto em 2026-07-07): o catálogo (com
  custo/preço) **NUNCA** vai para o GitHub. Mas os usuários da cotação **NÃO
  acessam a rede da loja** — o app `cotacao-auditoria-atacaderj` roda como
  **artifact no claude.ai** (cada funcionário loga com a própria conta Claude;
  storage compartilhado do artifact, não a rede local). O catálogo chega lá
  por um **robô de upload** no PC-ponte, não por `fetch` — ver seção abaixo.

## Regras inegociáveis

- O login do banco é **só leitura**. Nunca gere nada que não seja `SELECT`/`WITH`
  (o `src/db.py` já tem uma trava que recusa o resto). Nunca instale nada no
  servidor `CONCENTRADOR` — tudo roda **aqui**, no ponte.
- A **senha** fica **só** em `config.local.json` (que é gitignored).
  **Nunca** commite senha, nem custo, nem preço — o repo é público/na nuvem.
  Peça a senha ao usuário quando precisar; não a escreva em arquivo versionado.

## Estado atual (2026-07-07): a ponte FUNCIONA, e o app é artifact do claude.ai

`python src/bridge.py` gera os 9 arquivos do banco real em ~8s (catálogo,
vendas, entradas, recebimentos, pedidos de compra, pedidos de venda/DAV), e as
vendas batem ao centavo com o consolidado oficial. O que falta (ver STATUS.md):

1. **Agendar**: PowerShell (Admin) → `./scripts/register-tasks.ps1`
   (catálogo 08/12/15/18h; movimentos 05:00; auditoria 16:00 — este PC fica
   24h, ok).
2. **Ligar a cotação — o app roda como artifact no claude.ai, NÃO servido na
   rede local**: um `fetch()` relativo (como o da aba Auditoria) não funciona
   na versão publicada, porque o artifact não alcança a rede da loja. O
   caminho certo: bridge gera **`catalogo_bridge.json`** (arquivo único) e um
   **robô Playwright agendado** sobe esse arquivo no artifact pelo botão
   "📦 Catálogo" do app. Planos prontos (skill `superpowers:executing-plans`,
   roteiro humano em
   **[docs/COMO-IMPLEMENTAR-NO-PC-PONTE.md](docs/COMO-IMPLEMENTAR-NO-PC-PONTE.md)**):
   - Repo `cotacao-auditoria-atacaderj` →
     `docs/superpowers/plans/2026-07-07-aceitar-catalogo-bridge.md`
     (app aceita o arquivo único — **executar primeiro**, o robô depende dos IDs de lá)
   - Este repo → `docs/superpowers/plans/2026-07-07-catalogo-bridge-e-robo.md`
     (projeção `catalogo_bridge.json` + robô Playwright + tarefas agendadas)
   - Design: `docs/superpowers/specs/2026-07-07-estrutura-acesso-cotacao-design.md`
   - **Pendência descoberta em 2026-07-07**: esses planos ainda só cobrem o
     catálogo — falta decidir como o `pedidos_venda_dav.csv` (seletor de dia
     da aba Auditoria) chega ao artifact também.
3. Quando os repos dos detectores forem clonados neste PC, apontar
   `saida.detector_*_dir` do `config.local.json` para os `data/input` deles.

Se uma query quebrar (ERP atualizou?): `python src/inspect_schema.py <termos>`
para explorar o schema, e o cabeçalho de `src/queries.py` documenta os fatos
do schema que as queries assumem.

## Sempre que avançar

**Atualize o `STATUS.md`**: marque o item `[x]` e acrescente uma linha no
"Log de progresso" com a data. Depois `git add -A && git commit && git push`
(repo privado). Assim a próxima sessão — aqui ou em outro PC — retoma sem perder
nada. Este é o combinado com o usuário: o repositório é a memória do projeto.
