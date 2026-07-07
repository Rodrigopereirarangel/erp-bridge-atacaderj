# STATUS — Implantação da ponte (erp-bridge)

> **Documento vivo.** Atualizado conforme a sessão evolui, para retomar o setup
> depois (inclusive de outro PC ou de outra sessão do Claude). Veja o **Log de
> progresso** no fim.

## Objetivo

Este **PC-ponte** (na loja, ligado 24h, na rede local) puxa do **MySQL do ERP**
com o usuário **`viewer`** (só leitura) e gera `produtos.json` + CSVs, **agendado
2-3x/dia**, que alimentam a **cotação (HTML)** e os **detectores**.

**Cenário A** (escolhido): usuários da cotação são **locais**; o catálogo (com
custo/preço) **NÃO** vai para o GitHub — fica na rede da loja. O GitHub guarda
**só o código e este status**.

## Topologia confirmada

- **Servidor MySQL** = máquina **CONCENTRADOR**, IP de rede **`192.168.0.245`**,
  porta **`3306`**, escutando em `0.0.0.0` (aberto na rede). Banco = **MySQL**
  (não Oracle, apesar do PL/SQL Developer estar instalado na CONCENTRADOR).
- **PC-ponte** = **DESKTOP-3BLTBIV**, IP **`192.168.0.164`** (Ethernet 2),
  ligado 24h. **Alcança** o MySQL — `Test-NetConnection ... -Port 3306` = `True`. ✅
- Máquina de desenvolvimento (onde o código nasceu) está em **outra rede física**
  (`192.168.0.14`, sem alcance ao servidor) — só chega na loja por acesso remoto.

## Checklist de implantação

- [x] Definir arquitetura (Cenário A; PC-ponte separado, servidor intocado)
- [x] Confirmar que o banco é **MySQL** e está aberto na rede (`0.0.0.0:3306`)
- [x] Confirmar o IP do servidor: **192.168.0.245**
- [x] Escolher o PC-ponte: **DESKTOP-3BLTBIV** (24h, rede da loja)
- [x] Teste de rede PC-ponte → servidor (`Test-NetConnection 3306` = `True`)
- [x] Subir o `erp-bridge` no GitHub (repo **privado**) + este STATUS
- [ ] Confirmar o **host do `viewer`** (tem que aceitar `192.168.0.%`, não só `localhost`)
- [ ] No PC-ponte: instalar **Git + Python 3.12** (winget) + `pip install -r requirements.txt`
- [ ] No PC-ponte: `git clone` deste repo
- [ ] Preencher **`config.local.json`** (host `192.168.0.245`, viewer, senha, database)
- [ ] `python src/inspect_schema.py ...` → obter tabelas/colunas reais
- [ ] Preencher os **4 SELECT** em `src/queries.py` com o schema real
- [ ] Testar: `python src/bridge.py --only catalogo` → gera `produtos.json` real
- [ ] Agendar: `scripts/register-tasks.ps1` (catálogo 08/12/15/18h; movimentos 05:00)
- [ ] Ligar a cotação: bridge gera **`catalogo_bridge.json`** (arquivo único:
  atacado+varejo+promo+curva+custo+`gerado_em`) — design em
  `docs/superpowers/specs/2026-07-07-estrutura-acesso-cotacao-design.md`
- [ ] App da cotação: aceitar o arquivo único no botão "📦 Catálogo" (3 relatórios
  viram plano C) — repo `cotacao-auditoria-atacaderj`
- [ ] Publicar o app como **artifact no claude.ai** (uma vez; link fixo p/ funcionários)
- [ ] No PC-ponte: **robô de upload** (Playwright agendado, sessão logada) sobe o
  arquivo no artifact diariamente — zero toque; trava do app cobre falhas

## Comandos-chave (rodar no PC-ponte)

```powershell
# 1) instalar (uma vez)
winget install -e --id Git.Git
winget install -e --id Python.Python.3.12

# 2) clonar o repo
git clone https://github.com/Rodrigopereirarangel/erp-bridge-atacaderj.git
cd erp-bridge-atacaderj
pip install -r requirements.txt

# 3) copiar config.example.json -> config.local.json e preencher a seção "db"
#    (host 192.168.0.245, port 3306, user viewer, senha, database)

# 4) testar conexão + descobrir o schema real (é também o teste de login do viewer)
python src/inspect_schema.py produto preco custo curva venda entrada pedido
```

## Dados de conexão (a senha fica SÓ em `config.local.json`, nunca aqui)

- host: `192.168.0.245`
- port: `3306`
- user: `viewer`
- database: *(a preencher — se não souber, `SHOW DATABASES` no HeidiSQL revela)*

## Próximo passo imediato

Confirmar o host do `viewer` e rodar o `inspect_schema` no PC-ponte; colar a
saída para preencher os 4 `SELECT` de `src/queries.py`.

## Log de progresso

- **2026-07-06** — Topologia confirmada. PC-ponte **DESKTOP-3BLTBIV** (192.168.0.164)
  alcança o MySQL da CONCENTRADOR (192.168.0.245:3306, `TcpTestSucceeded=True`).
  Repo criado no GitHub (privado) com este STATUS. Próximo: viewer host + inspect_schema.
- **2026-07-06** — Adicionado `CLAUDE.md`: o Claude do PC-ponte lê esse arquivo ao
  abrir na pasta do repo e continua a implantação sozinho, pelo checklist acima.
- **2026-07-07** — **Decisão:** loop de feedback (apelidos/correções) **descartado**
  — removido do escopo e do checklist. O bridge fica só extração → arquivos.
- **2026-07-07** — **Planos de implementação escritos e commitados** (um por repo) +
  roteiro copiar-e-colar para o PC-ponte em `docs/COMO-IMPLEMENTAR-NO-PC-PONTE.md`
  (pré-requisitos, prompts prontos para o Claude Code das 2 sessões e os 4 passos
  manuais da implantação). Ordem: 1º o plano do app (`cotacao-auditoria-atacaderj`),
  2º o deste repo (robô depende dos IDs do app).
- **2026-07-07** — **Design aprovado e revisado** (estrutura de acesso): descoberto
  que o app da cotação roda como **artifact no claude.ai** (IA via sessão + storage
  compartilhado) — a injeção no HTML foi descartada. Modelo final: bridge gera
  **arquivo único** (`catalogo_bridge.json`) → **robô Playwright agendado** no
  PC-ponte sobe no artifact pelo botão do app → storage compartilhado distribui a
  todos. Falha do robô é visível (trava de data do app); plano B = upload manual do
  arquivo (30s); plano C = 3 relatórios do ERP. Migração documentada (app local +
  injeção + API paga) se o claude.ai inviabilizar o robô. Spec:
  `docs/superpowers/specs/2026-07-07-estrutura-acesso-cotacao-design.md`.
