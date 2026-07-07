# CLAUDE.md — instruções para o Claude no PC-ponte

Você (Claude) está rodando no **PC-ponte** da loja AtacadeRJ, dentro do projeto
`erp-bridge`. Este arquivo te dá o contexto para **continuar a implantação
sozinho** de onde a sessão anterior parou. Leia também **[STATUS.md](STATUS.md)**:
é o checklist vivo — o próximo passo é sempre o primeiro item `[ ]` não marcado.

## O que este projeto faz

Puxa dados do **MySQL do ERP** (usuário `viewer`, **só leitura**) e gera
`produtos.json` + CSVs, **agendado 2-3x/dia**, que alimentam a **cotação (HTML)**
e os **detectores** (`detector-ruptura-atacaderj`, `detector-ruptura-estoque-atacaderj`).
É a única ponte de dados — acaba com a exportação manual de relatórios. Custo R$ 0.
O único ponto amarrado ao ERP são os 4 `SELECT` de `src/queries.py`.

## Onde você está (topologia confirmada)

- **Este PC (ponte)** = `DESKTOP-3BLTBIV`, IP `192.168.0.164`, ligado 24h, na
  rede da loja. Já testado: **alcança** o MySQL
  (`Test-NetConnection 192.168.0.245 -Port 3306` → `True`).
- **Servidor MySQL** = máquina `CONCENTRADOR`, IP `192.168.0.245`, porta `3306`,
  banco **MySQL** (não Oracle, apesar do PL/SQL Developer estar lá). Escuta em `0.0.0.0`.
- **Cenário A**: os usuários da cotação são **locais** → o catálogo (com
  custo/preço) **NUNCA** vai para o GitHub. Fica na rede da loja.

## Regras inegociáveis

- O `viewer` é **só leitura**. Nunca gere nada que não seja `SELECT`/`WITH`
  (o `src/db.py` já tem uma trava que recusa o resto). Nunca instale nada no
  servidor `CONCENTRADOR` — tudo roda **aqui**, no ponte.
- A **senha** do viewer fica **só** em `config.local.json` (que é gitignored).
  **Nunca** commite senha, nem custo, nem preço. Peça a senha ao usuário quando
  precisar; não a escreva em arquivo versionado.

## Planos de implementação pendentes (cotação no claude.ai)

Há **dois planos prontos** para executar com a skill `superpowers:executing-plans`
(roteiro humano completo em **[docs/COMO-IMPLEMENTAR-NO-PC-PONTE.md](docs/COMO-IMPLEMENTAR-NO-PC-PONTE.md)**):

1. Repo `cotacao-auditoria-atacaderj` → `docs/superpowers/plans/2026-07-07-aceitar-catalogo-bridge.md`
   (app aceita o arquivo único; **executar primeiro** — o robô depende dos IDs criados lá).
2. Este repo → `docs/superpowers/plans/2026-07-07-catalogo-bridge-e-robo.md`
   (projeção `catalogo_bridge.json` + robô Playwright + tarefas agendadas).

O design por trás: `docs/superpowers/specs/2026-07-07-estrutura-acesso-cotacao-design.md`.

## Seu trabalho agora (continue pelo STATUS.md)

1. Garanta Git e Python (`git --version`, `python --version`); se faltar:
   `winget install -e --id Git.Git` e `--id Python.Python.3.12`.
2. `pip install -r requirements.txt`.
3. **Testar login do viewer + achar o database** (peça a senha ao usuário):
   `python -c "import pymysql; c=pymysql.connect(host='192.168.0.245',user='viewer',password='<SENHA>',port=3306); cur=c.cursor(); cur.execute('SHOW DATABASES'); print([r[0] for r in cur.fetchall()])"`
   - Se der `Access denied ...@'192.168.0.164'` → o viewer só existe em
     `localhost`. Peça ao usuário para criar na CONCENTRADOR:
     `CREATE USER 'viewer'@'192.168.0.%' ...; GRANT SELECT ON <db>.* ...; FLUSH PRIVILEGES;`
4. `copy config.example.json config.local.json` e preencha a seção `db`
   (host `192.168.0.245`, port `3306`, user `viewer`, senha, database) **e** os
   caminhos de `saida` para pastas **locais deste PC** (o exemplo aponta para a
   máquina de dev).
5. `python src/inspect_schema.py produto preco custo curva venda entrada pedido`
   → use a saída para trocar os `--TODO` dos 4 `SELECT` em `src/queries.py`.
   O contrato das colunas está em `docs/CONTRATO-DE-DADOS.md`.
6. Teste: `python src/bridge.py --only catalogo` → deve gerar `produtos.json`.
7. Agende: em PowerShell (Admin) `./scripts/register-tasks.ps1`
   (catálogo 08/12/15/18h; movimentos 05:00 — este PC fica 24h, ok).
8. Ligue a cotação: o bridge gera o **`catalogo_bridge.json`** (arquivo único) e um
   **robô Playwright agendado** sobe esse arquivo no **artifact do claude.ai** pelo
   botão "📦 Catálogo" do app (o app roda no claude.ai, não local — ver
   `docs/superpowers/specs/2026-07-07-estrutura-acesso-cotacao-design.md`).

## Sempre que avançar

**Atualize o `STATUS.md`**: marque o item `[x]` e acrescente uma linha no
"Log de progresso" com a data. Depois `git add -A && git commit && git push`
(repo privado). Assim a próxima sessão — aqui ou em outro PC — retoma sem perder
nada. Este é o combinado com o usuário: o repositório é a memória do projeto.
