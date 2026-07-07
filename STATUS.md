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
- [ ] **BLOQUEADO AQUI →** Liberar acesso de rede no MySQL para o `rodrigo`
  (já é somente-leitura; faz o papel do `viewer`). Recusado vindo do PC-ponte
  (`Access denied for 'rodrigo'@'DESKTOP-3BLTBIV'`) — existe só como
  `@'localhost'`. Comandos prontos na seção "Próximo passo imediato"
- [x] No PC-ponte: instalar **Git + Python 3.12** (winget) + `pip install -r requirements.txt` (Python 3.12.10, pymysql 2.2.8)
- [x] No PC-ponte: `git clone` deste repo → `C:\Users\User\erp-bridge-atacaderj`
- [x] Preencher **`config.local.json`** (host/porta/user/senha ok; **`database` pendente** — sai do `SHOW DATABASES` pós-liberação)
- [ ] `python src/inspect_schema.py ...` → obter tabelas/colunas reais
- [ ] Preencher os **4 SELECT** em `src/queries.py` com o schema real
- [ ] Testar: `python src/bridge.py --only catalogo` → gera `produtos.json` real
- [ ] Agendar: `scripts/register-tasks.ps1` (catálogo 08/12/15/18h; movimentos 05:00)
- [ ] Ligar o HTML da cotação: `fetch("produtos.json")` + servir na rede local
- [ ] Loop de feedback (apelidos/correções) → GitHub via serverless (Apps Script)

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

## Próximo passo imediato — DESBLOQUEIO (rodar NA CONCENTRADOR)

**Decisão do usuário (2026-07-07): usar o próprio `rodrigo`** — ele já é
somente-leitura (faz o papel do `viewer`). Falta só permitir que ele conecte
**vindo da rede** (hoje só existe como `@localhost`).

Na CONCENTRADOR, abrir o cliente MySQL (HeidiSQL / linha de comando, logado
como `root` ou usuário com privilégio de GRANT):

**1) Diagnóstico — ver de quais hosts o `rodrigo` pode conectar:**
```sql
SELECT user, host FROM mysql.user WHERE user = 'rodrigo';
```

**2a) Se só aparecer `rodrigo | localhost`** → criar a entrada de rede
(mesma senha; `@localhost` continua intocado):
```sql
CREATE USER 'rodrigo'@'192.168.0.%' IDENTIFIED BY '<MESMA_SENHA>';
GRANT SELECT ON *.* TO 'rodrigo'@'192.168.0.%';
FLUSH PRIVILEGES;
```

**2b) Se já existir `rodrigo | %` (ou `192.168.%`)** → a senha da entrada de
rede é outra; igualar:
```sql
ALTER USER 'rodrigo'@'%' IDENTIFIED BY '<MESMA_SENHA>';
FLUSH PRIVILEGES;
```

> `<MESMA_SENHA>` = a senha que já está no `config.local.json` do PC-ponte.
> **Nunca** escrever a senha neste arquivo (repo público).

Feito isso, no PC-ponte: testar conexão, `SHOW DATABASES` → preencher
`database` no `config.local.json`, e seguir para o `inspect_schema` +
preencher os 4 `SELECT` de `src/queries.py`.

## Log de progresso

- **2026-07-06** — Topologia confirmada. PC-ponte **DESKTOP-3BLTBIV** (192.168.0.164)
  alcança o MySQL da CONCENTRADOR (192.168.0.245:3306, `TcpTestSucceeded=True`).
  Repo criado no GitHub (privado) com este STATUS. Próximo: viewer host + inspect_schema.
- **2026-07-06** — Adicionado `CLAUDE.md`: o Claude do PC-ponte lê esse arquivo ao
  abrir na pasta do repo e continua a implantação sozinho, pelo checklist acima.
- **2026-07-07** — Sessão no PC-ponte (DESKTOP-3BLTBIV): repo clonado em
  `C:\Users\User\erp-bridge-atacaderj`; Python 3.12.10 + pymysql 2.2.8 instalados
  (winget); `config.local.json` criado (gitignored, confirmado). Teste de login no
  MySQL 192.168.0.245 com o usuário fornecido (`rodrigo`) → **`Access denied for
  'rodrigo'@'DESKTOP-3BLTBIV'`** = usuário só existe em `localhost`. **Bloqueado
  aguardando** o `CREATE USER 'viewer'@'192.168.0.%'` na CONCENTRADOR (comando
  pronto na seção "Próximo passo imediato").
