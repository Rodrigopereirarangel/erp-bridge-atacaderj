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

## Topologia confirmada (CORRIGIDA em 2026-07-07)

- **O ERP é Solidcon sobre SQL SERVER 2014** (12.0.2269), máquina **CONCENTRADOR**
  (`192.168.0.245`), porta **`1433`**. ~~MySQL~~ — o 3306 aberto era outra coisa;
  a suposição inicial estava errada. Databases: **`Solidcon`** (retaguarda, é o
  que a ponte lê), `SolidconLoja` (réplica p/ PDV), `DORSAL` (frente de caixa/
  delivery — dele só usamos o `tbConsVenda` como prova contábil).
- Login **SQL** `rodrigo` (somente leitura, decisão do usuário) funciona do
  PC-ponte **sem precisar mexer no servidor** (SQL Server não restringe host).
- **PC-ponte** = **DESKTOP-3BLTBIV**, IP **`192.168.0.164`**, ligado 24h. ✅
- Máquina de desenvolvimento (onde o código nasceu) está em **outra rede física**
  (`192.168.0.14`, sem alcance ao servidor) — só chega na loja por acesso remoto.

## Checklist de implantação

- [x] Definir arquitetura (Cenário A; PC-ponte separado, servidor intocado)
- [x] Confirmar que o banco é **MySQL** e está aberto na rede (`0.0.0.0:3306`)
- [x] Confirmar o IP do servidor: **192.168.0.245**
- [x] Escolher o PC-ponte: **DESKTOP-3BLTBIV** (24h, rede da loja)
- [x] Teste de rede PC-ponte → servidor (`Test-NetConnection 3306` = `True`)
- [x] Subir o `erp-bridge` no GitHub (repo **privado**) + este STATUS
- [x] ~~Liberar acesso no MySQL~~ → **não era MySQL**: o ERP é SQL Server 1433 e
  o login `rodrigo` entra direto da rede. O "Access denied" do MySQL era porque
  as credenciais eram do SQL Server.
- [x] No PC-ponte: instalar **Git + Python 3.12** (winget) + deps (pymysql 2.2.8, **pyodbc 5.3**)
- [x] No PC-ponte: `git clone` deste repo → `C:\Users\User\erp-bridge-atacaderj`
- [x] Preencher **`config.local.json`** (tipo sqlserver, 192.168.0.245:1433, database `Solidcon`)
- [x] Adaptar o código p/ SQL Server: `db.py` dual-dialeto (pyodbc/pymysql) + `inspect_schema.py`
- [x] Mapear o schema real (Solidcon) → detalhes em `docs/CONTRATO-DE-DADOS.md`
- [x] Preencher os **4 SELECT** em `src/queries.py` (T-SQL) com o schema real
- [x] Testar: `python src/bridge.py` → **8 arquivos gerados do banco real em ~8s**
  (produtos.json 4.600; vendas.csv 153.947; entradas 8.197; recebimentos 3.505;
  pedidos 2.098) — **vendas batem ao centavo** com o consolidado oficial
  (`DORSAL.tbConsVenda`, 06/07: 82.423,04 = 82.423,04)
- [x] 5ª query `PEDIDOS_VENDA` (itens dos pedidos de venda/DAV, filtro por
  `dtAtendido`) → `cotacao/pedidos_venda_dav.csv` — automatiza o insumo da
  auditoria de desconto do app (validada 199/199 vs relatório manual de 06/07)
- [x] Agendar: `scripts/register-tasks.ps1` — **3 tarefas registradas em
  2026-07-07**: Catálogo 08/12/15/18h · Movimentos 05:00 · **Auditoria 16:00**
  (o script resolve o python.exe real; o alias da Store enganava o Get-Command)
- [x] Auditoria de desconto automatizada: `scripts/auditoria-16h.ps1` →
  bridge `--only pedidos-venda` + `auditoria-diaria.mjs` (repo do app) →
  xlsx+resumo em `saida/auditoria/` → WhatsApp (número em
  `config.local.json > whatsapp.numero_auditoria`)
- [ ] **WhatsApp: login pendente (1x)** — `cd scripts/whatsapp` e
  `node enviar.mjs --login`, escanear o QR com o celular do dono. Sem isso o
  job das 16h gera os arquivos mas falha no envio (loga em auditoria_16h.log)
- [ ] Ligar o HTML da cotação: `fetch("produtos.json")` + servir na rede local.
  **Servir a pasta `saida/cotacao/` junto com o app**: o seletor de dias da
  aba Auditoria do app busca `pedidos_venda_dav.csv` por caminho relativo
- [ ] Apontar os caminhos de `saida` para os detectores quando eles forem
  clonados neste PC (hoje escrevem em `saida/` do próprio repo)
- [ ] Loop de feedback (apelidos/correções) → GitHub via serverless (Apps Script)

## Comandos-chave (PC-ponte)

```powershell
# rodar a ponte manualmente
python C:\Users\User\erp-bridge-atacaderj\src\bridge.py                  # tudo
python C:\Users\User\erp-bridge-atacaderj\src\bridge.py --only catalogo  # so catalogo

# explorar o schema (se precisar ajustar uma query)
python src\inspect_schema.py venda nota pedido produto
```

## Dados de conexão (a senha fica SÓ em `config.local.json`, nunca aqui)

- tipo: `sqlserver` (driver ODBC "SQL Server", já vem no Windows)
- host: `192.168.0.245` · port: `1433`
- user: `rodrigo` (somente leitura)
- database: **`Solidcon`**

## Próximo passo imediato

1. **Login do WhatsApp (1x)**: `cd scripts\whatsapp` → `node enviar.mjs --login`
   → escanear o QR. Depois testar:
   `powershell -File scripts\auditoria-16h.ps1 -Dia 2026-07-06`
2. **Ligar o HTML da cotação**: servir `saida/cotacao/` (produtos.json +
   pedidos_venda_dav.csv) junto com o app na rede local — isso liga também o
   seletor de dias da aba Auditoria do app
3. `git push` dos dois repos (precisa de credencial interativa; esta sessão
   não consegue)
4. Quando os detectores forem clonados neste PC, apontar `saida.detector_*_dir`
   do `config.local.json` para as pastas `data/input` deles

## Log de progresso

- **2026-07-06** — Topologia confirmada. PC-ponte **DESKTOP-3BLTBIV** (192.168.0.164)
  alcança o MySQL da CONCENTRADOR (192.168.0.245:3306, `TcpTestSucceeded=True`).
  Repo criado no GitHub (privado) com este STATUS. Próximo: viewer host + inspect_schema.
- **2026-07-06** — Adicionado `CLAUDE.md`: o Claude do PC-ponte lê esse arquivo ao
  abrir na pasta do repo e continua a implantação sozinho, pelo checklist acima.
- **2026-07-07 (manhã)** — Sessão no PC-ponte (DESKTOP-3BLTBIV): repo clonado,
  Python 3.12.10 instalado, config criado. Login no MySQL 3306 recusado.
- **2026-07-07 (AUDITORIA AUTOMÁTICA + AGENDAMENTO)** — Pedido do dono:
  auditoria por dia selecionável, histórico de 7 dias, preço-base = menor
  (atacado/varejo/promo), e envio diário 16h ao WhatsApp (21970117082) com
  resumo por vendedor. O QUE MUDOU E POR QUÊ:
  (a) **App** (repo `cotacao-auditoria-atacaderj`, clonado neste PC em
  `C:\Users\User\cotacao-auditoria-atacaderj`): aba Auditoria ganhou seletor
  dos últimos 7 dias lendo `pedidos_venda_dav.csv` da ponte (pedidos FECHADOS
  no dia = `dtAtendido`); upload manual .xlsx mantido como fallback. Novo
  `ferramentas/auditoria-diaria.mjs` roda a MESMA regra (importa
  `auditoria-calc.mjs`) em Node — por isso os números batem com o app — e o
  catálogo entra com v = MIN(atacado, varejo, promoção) do produtos.json.
  (b) **Ponte**: `scripts/auditoria-16h.ps1` (gera histórico + auditoria do
  dia + envia), `scripts/whatsapp/` (Baileys; sessão em auth/ GITIGNORED por
  ser credencial; login por QR pendente), número do WhatsApp em
  `config.local.json` (gitignored, não versionar telefone em repo),
  `register-tasks.ps1` corrigido (python.exe real, não o alias da Store) e
  **as 3 tarefas registradas no Agendador deste PC**.
  Teste real (dia 06/07): 154 itens auditados, 33 divergências, R$ 105,92 —
  Michele 20×R$54,11 · Elizabeth 9×R$30,89 · Fellipe 4×R$20,92.
  PENDENTE: QR do WhatsApp (1x) e servir saida/cotacao/ com o app.
- **2026-07-07 (PEDIDOS VENDA)** — 5ª query `PEDIDOS_VENDA` adicionada
  (tbPedido inEntrada=0 + tbPedidoItem + tbPedidoVenda/tbPedidoVendedor/
  tbPessoa; período = `dtAtendido`): reproduz o rptPedidosVendaEmitidaDAV
  PorItens item a item (199/199 linhas do dia 06/07). Sai em
  `cotacao/pedidos_venda_dav.csv` (`--only pedidos-venda`, também em
  `movimentos`/`all`; janela default 7 dias). Auditoria de desconto do app
  pode ler esse CSV em vez do upload manual do relatório. Ponte completa:
  9 arquivos em ~8s.
- **2026-07-07 (AUDITORIA)** — Saída da ponte conferida item a item contra 4
  relatórios manuais do ERP (Cadastro Atacado, Gestão Preço, Curva ABC 01–07/07,
  Pedidos DAV 06/07): **dados batem** — custo/promo/curva/vendas/DAV ~100%.
  Divergências têm explicação e estão documentadas em
  `docs/AUDITORIA-2026-07-07.md`: relatórios mostram preço da EMPRESA e a ponte
  o preço da FILIAL (que é o cobrado no caixa); `q` do json é a caixa, não a
  qtde mínima do atacado; `vendas.csv` é bruta (não desconta devoluções — 3 de
  2.731 itens na janela). Repo `cotacao-auditoria-atacaderj` NÃO acessível
  deste PC (token só alcança o erp-bridge).
- **2026-07-07 (VIRADA)** — Usuário revelou que acessa por **SQL Server
  Management Studio**: o ERP é **Solidcon sobre SQL Server 2014**, porta 1433 —
  não MySQL! Login `rodrigo` funcionou na hora, sem tocar no servidor. Mapeado o
  schema real (tbVendaPDV 2,3M linhas; views Neogrid p/ preço/curva; tbNota*/
  tbPedido*; nomes em tbSuperProduto.nmProdutoPai — nmProduto é NULL no banco
  todo; qtItemNota vem em VOLUMES ×qtEmbalagem). `db.py` virou dual-dialeto
  (pyodbc), 4 SELECTs preenchidos em T-SQL e **a ponte rodou de ponta a ponta**:
  8 arquivos em ~8s, vendas **batendo ao centavo** com o consolidado oficial
  (DORSAL.tbConsVenda). Falta: agendar tarefas + ligar o HTML da cotação.
