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
- [x] **WhatsApp CONECTADO (2026-07-10 11:35)** — QR escaneado com o celular
  remetente (5521970000786); teste de envio OK ("enviado para 5521970000786").
  O job das 16h agora envia sozinho o Excel + resumo da auditoria para
  5521970117082 (config.local.json > whatsapp.numero_auditoria). Se a sessão
  expirar um dia: `cd scripts/whatsapp` → `node enviar.mjs --login` de novo.
- [x] **Arquivo único `catalogo_bridge.json` (2026-07-08)** — a ponte gera em
  `saida/cotacao/catalogo_bridge.json` o arquivo que o robô sobe no artifact:
  catálogo mesclado (v = MENOR preço varejo/promo/atacado; vu = unitário
  quando o atacado vence; q = **QUANTIDADE_ATACADO**, a qtde mínima real do
  atacado — coluna adicionada à query CATALOGO) **+ seção `pedidos_venda`**
  (itens dos pedidos fechados nos últimos 7 dias, p/ a aba Auditoria).
  Contrato validado contra a revalidação do app: 4.600/4.600 produtos aceitos,
  0 rejeições, promoção vencendo em 26/26, mescla conferida nos casos de
  banco conhecidos. Sai nos alvos `catalogo`, `pedidos-venda` e `movimentos`.
- [x] **App aceita o arquivo único (2026-07-08)** — plano
  `2026-07-07-aceitar-catalogo-bridge.md` implementado no repo do app, com
  extensão: o histórico `pedidos_venda` é salvo no storage compartilhado e a
  aba 🔍 Auditoria lê **storage → fetch local → .xlsx manual** (nessa ordem).
  Um upload do robô alimenta cotação E auditoria de todos os usuários.
- [x] **Robô de upload (Playwright) — código pronto e TESTADO (2026-07-09)** —
  `robo/upload_catalogo.py` (3 modos: `--setup` login 1x · `--teste` fluxo
  completo contra o HTML publicável local · rodada normal agendada) +
  `robo/validacao.py` (7 testes pytest). Teste de ponta a ponta com o arquivo
  REAL de hoje passou: XLSX via cdnjs OK, 📦 upload 4.606 produtos, 285
  pedidos no storage, auditoria com 7 dias/713 itens no dia mais recente,
  trava anti-sobrescrita ativa. Tarefa agendada REGISTRADA:
  "AtacadeRJ - Robo Upload Cotacao" 08:05/12:05/15:05/16:05/18:05.
  **Falta só (depois de publicar o artifact)**: colar o link em
  `robo/config_robo.json`, `--setup` p/ logar, e assistir a 1ª rodada —
  ver `robo/README.md`.
- [x] **Dashboard de vendas mensais em UNIDADES (2026-07-10)** — 6ª query
  `VENDAS_MENSAL` (unidades por produto × mês FECHADO, 6 meses; mês corrente
  fica fora) + projeção `vendas_mensal_dashboard` → `saida/dashboard/
  vendas_mensal.json` + `vendas_mensal.html` (auto-contido, dados embutidos,
  abre com duplo clique): seletor de mês, busca, ordenação por qtd/descrição/
  código (select + clique no cabeçalho), tiles com Δ vs mês anterior.
  Validado: totais dos 6 meses batem ao milésimo com SUM(qtVenda) direto no
  banco; 10/10 testes de interação (Playwright). Sai nos alvos `all`,
  `movimentos` e `--only vendas-mensal` (refresh diário às 05:00 já cobre).
  **v2 (2026-07-10): + valor de venda e Vl. médio, CÓDIGO DEFINITIVO
  homologado contra o rptABCdeVendas do ERP** — ver log.
- [ ] Apontar os caminhos de `saida` para os detectores quando eles forem
  clonados neste PC (hoje escrevem em `saida/` do próprio repo)
- [x] ~~Loop de feedback (apelidos/correções) → GitHub via serverless~~ —
  **descartado** por decisão de 2026-07-07 (ver log); bridge fica só extração

## Comandos-chave (PC-ponte)

```powershell
# rodar a ponte manualmente
python C:\Users\User\erp-bridge-atacaderj\src\bridge.py                  # tudo
python C:\Users\User\erp-bridge-atacaderj\src\bridge.py --only catalogo  # so catalogo

# explorar o schema (se precisar ajustar uma query)
python src\inspect_schema.py venda nota pedido produto

# dashboard de vendas mensais (unidades por item, meses fechados)
python C:\Users\User\erp-bridge-atacaderj\src\bridge.py --only vendas-mensal
# abrir: C:\Users\User\erp-bridge-atacaderj\saida\dashboard\vendas_mensal.html
```

## Dados de conexão (a senha fica SÓ em `config.local.json`, nunca aqui)

- tipo: `sqlserver` (driver ODBC "SQL Server", já vem no Windows)
- host: `192.168.0.245` · port: `1433`
- user: `rodrigo` (somente leitura)
- database: **`Solidcon`**

## Próximo passo imediato

0. **Detector de salão neste PC (roteiro pronto)**: seguir
   `docs/IMPLANTAR-DETECTOR-SALAO-NO-PONTE.md` (clonar o detector, apontar
   `detector_salao_dir`, dry-run, tarefa 05:30). Design:
   `docs/superpowers/specs/2026-07-11-detector-salao-dados-reais-design.md`.
1. **Login do WhatsApp (1x)**: `cd scripts\whatsapp` → `node enviar.mjs --login`
   → escanear o QR. Depois testar:
   `powershell -File scripts\auditoria-16h.ps1 -Dia 2026-07-06`
2. **Robô de upload**: executar o plano
   `docs/superpowers/plans/2026-07-07-catalogo-bridge-e-robo.md` (a parte do
   app e o arquivo único JÁ estão prontos — repare que a projeção aqui se
   chama `catalogo_bridge_json` em `src/projections.py` e o arquivo já inclui
   `pedidos_venda`; ajustar o plano se ele previa gerar isso do zero).
   Passos manuais: republicar o artifact com o app novo + logar o navegador.
3. Quando os detectores forem clonados neste PC, apontar `saida.detector_*_dir`
   do `config.local.json` para as pastas `data/input` deles

## Log de progresso

- **2026-07-10 (DIFAL/CCI DECIFRADOS)** — Engenharia reversa do custo de
  entrada, validada ao centavo no produto 19047: **CustoUnitario da nota =
  (preço+IPI) × (1−ICMS interestadual) ÷ (1−22%)** — DIFAL "por dentro" base
  dupla (22% = 20 ICMS + 2 FCP do RJ; coluna Difal = DiferencaAliquota = 10).
  Difal encarece a compra interestadual em **+12,82%**. Confirmado que
  `CUSTO_ULTIMA_ENTRADA` (Neogrid → produtos.json) e `tbVendaPDV.vlCusto`
  (CMV) são esse custo COM difal. O **CCI da tela = custo + acréscimo interno
  da aplicação** (não é difal — nota local sem difal também tem; varia por
  fornecedor/época; procs criptografadas; perguntar ao suporte Solidcon).
  Tudo documentado em **docs/CUSTO-DIFAL-CCI.md**. **Parte 2 (mesma data)**:
  fórmula GERAL do Custo Unit. fechada e validada em 45/48 itens de 7 grupos
  (verba, desconto, IPI, difal, redução de BC, ICMS-ST+FCP-ST, frete/seguro/
  outros) — cada coluna da tela NF Recebida mapeada no doc, com 3 exceções
  identificadas (uso/consumo, PIS/COFINS reduzido, ICMS desonerado cBenef).
- **2026-07-10 (v2 — HOMOLOGADO CONTRA O RELATÓRIO OFICIAL)** ✅ O dono gerou
  o **rptABCdeVendas** do ERP (01–30/06/2026, Qtde, sem descontar devoluções,
  sem vendas por NF) como gabarito. Resultado: o código já era o definitivo —
  **Qtde = SUM(qtVenda)** e **Venda = SUM(qtVenda*vlVenda)** do tbVendaPDV
  (com cdProduto IS NOT NULL) reproduzem o relatório EXATAMENTE: total geral
  630.551,997 un / R$ 3.485.305,48 / 3.576 itens, e 7/7 itens-amostra idênticos
  ao centavo, inclusive balança (cód. 42: 495,922 kg / 22.934,87 / Vl.M 46,25).
  A pedido do dono, a query VENDAS_MENSAL passou a extrair **qtd + valor**
  (payload `m: {mes: [qtd_un, valor]}`) e o **preço médio unitário é CALCULADO
  no dashboard (valor ÷ qtd)**, igual ao Vl. Médio do relatório — conferido
  também na UI (nº1 por valor = OLEO SOJA SOYA 6.910/48.424,79/7,01; maiores
  Vl.M 169,00 e 139,90 = MARGARINA SOFITELI e CIG DUNHILL, como no PDF).
  Dashboard ganhou colunas Valor (R$) e Vl. médio (ordenáveis), tile de
  faturamento com Δ, e "% do mês" virou participação no VALOR (= Partic. do
  relatório). 10/10 testes Playwright. Notas técnicas: (1) o valor por item é
  gravado com 2 casas (como o relatório), então a soma do arquivo difere da
  soma exata do banco em centavos (±R$0,08 em R$3,7M) — esperado; (2) existem
  linhas de tbVendaPDV com **cdProduto NULL** em alguns meses (jan/mai ~R$66k)
  que o relatório do ERP também ignora — o filtro `cdProduto IS NOT NULL` é
  parte do contrato.
- **2026-07-10** — **DASHBOARD DE VENDAS MENSAIS (unidades, não caixas)** ✅
  Pedido do dono: quantidade vendida em UN de cada item por mês fechado
  (junho/maio/abril...), com escolha de mês e lista ordenável. Antes de
  codificar, sondado o `tbVendaPDV`: **qtVenda já é em UNIDADES** (caixa de 12
  vendida no atacado sai como 12/24 un com vlVenda unitário — 17,09 atacado vs
  19,49 varejo no mesmo produto; qtVenda fracionada = balança/kg). Histórico
  disponível: ago/2025→hoje. Feito: 6ª query `VENDAS_MENSAL` ({meses_fechados}
  via config `vendas_mensal_meses`, default 6; mês corrente excluído),
  projeção `vendas_mensal_dashboard` (JSON + HTML auto-contido com template em
  `src/templates/vendas_mensal.html`, dados embutidos — funciona em file://
  sem servidor), alvo `--only vendas-mensal` (incluso em all/movimentos, então
  a tarefa das 05:00 mantém o dashboard fresco). Saída:
  `saida/dashboard/vendas_mensal.html` — seletor de mês (6 meses fechados),
  busca, ordenar por qtd/descrição/código, tiles (total un, itens, top item)
  com Δ vs mês anterior, barras de magnitude, claro/escuro. VALIDADO: totais
  dos 6 meses batem ao milésimo com o banco (jun=630.551,997 un; produto-teste
  17380 = 65 un em junho — atenção: JOIN com VW_NEOGRID duplica linhas por
  embalagem, a query agrega SEM join de preço); rodada completa real OK (11
  arquivos, 11s); 10/10 testes de interação Playwright; screenshots claro/
  escuro conferidos. Detalhe: modo `--demo` completo falha neste PC por causa
  dos caminhos `C:\Users\COMPUTADOR` do config.example (pré-existente, não
  relacionado).
- **2026-07-09 20:43** — **SISTEMA NO AR DE VERDADE, VERIFICADO** ✅ Artifact
  DEFINITIVO: `https://claude.ai/public/artifacts/d2e4ed88-38fe-42cc-b889-e829ec6f5418`
  (os 4 anteriores devem ser despublicados: e0cd803f, e507cf94, 1fe17c79,
  78fbe300 — este último com chaves PRESAS no servidor, sem conserto).
  Estado medido ao abrir: 4.606 produtos carregam sozinhos, origem robô
  18:00, envio manual ESCONDIDO (aviso azul "Catálogo automático"; os campos
  só aparecem em erro de importação — regra definitiva pedida pelo dono).
  **5 fatos de produção do window.storage** (todos medidos por sonda, cada
  um causou uma rodada de correção): (1) get/set devolvem ENVELOPE
  {key,value,shared}; (2) operações concorrentes corrompem a chave;
  (3) reload/fechar com escrita em andamento corrompe a chave; (4) escrita
  GRANDE (~390KB) que falha no meio deixa a chave PRESA sem cura — solução:
  gravar gz64 (gzip+base64, ~109KB) com retry, valores >64KB; (5) sobras
  de localStorage de junho ressuscitavam banco de 16/06 — fallback local
  agora só em file://, localhost e 192.168.x. Robô: fila drenada antes do
  reload, autocura (reler e regravar até 3x) e verificação de persistência
  pós-reload. PENDENTE: dono despublicar os 4 artifacts antigos; QR do
  WhatsApp; teste de cotação com FOTO na conta de um vendedor.
- **2026-07-09 13:53** — **PIPELINE COMPLETO NO AR** 🎉: artifact publicado
  (`https://claude.ai/public/artifacts/e0cd803f-ac4b-4878-8e4a-f64d2093b851`,
  link colado no `config_robo.json`), login do robô feito, e a primeira
  rodada real enviou **4.606 produtos + 285 pedidos** ao storage compartilhado
  (verificado: CATALOG embutido 0 = publicável correto; XLSX cdnjs OK; badge
  de hoje OK). **Pegadinha resolvida**: o Chrome lançado pelo Playwright vem
  marcado como automação e o Cloudflare recusa o "confirme que é humano"
  MESMO com clique manual — o robô agora abre um Chrome comum (sem marcas)
  com `--remote-debugging-port` e conecta via CDP; com o perfil logado o
  desafio nem aparece. Falta: teste do artifact nas contas dos vendedores
  (storage compartilhado) + cotação com FOTO (IA do plano) + QR do WhatsApp.
- **2026-07-09 (tarde)** — **ROBÔ DE UPLOAD PRONTO E TESTADO** (`robo/`):
  Playwright em Python, perfil Chrome persistente, 3 modos (`--setup`/`--teste`/
  normal). O `--teste` roda o fluxo completo contra o
  `cotacao-auditoria-atacaderj.publicavel.html` LOCAL com o arquivo real do dia
  e passou 100%: XLSX-cdnjs, upload 📦 (4.606 produtos), storage da auditoria
  (285 pedidos), seletor de 7 dias auditando 713 itens, trava anti-sobrescrita.
  Isso prova que o publicável se comporta como o app original. Tarefa
  "AtacadeRJ - Robo Upload Cotacao" registrada (08:05/12:05/15:05/16:05/18:05;
  inofensiva enquanto o config tiver o link placeholder). No app (repo da
  cotação, commit 8c34762): catálogo agora se atualiza sozinho na aba aberta
  (polling 3min do marcador `atacaderj_catalogo_versao`; carrinho vazio troca
  direto, carrinho ocupado ganha aviso "Atualizar agora") e o upload manual
  trava enquanto o robô está saudável (<5h), destravando sozinho se a
  automação parar. Falta SÓ: publicar o artifact, colar o link no
  `robo/config_robo.json`, `--setup` (login) e assistir a 1ª rodada.
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
- **2026-07-07 (sessão dev, sem acesso a este PC)** — **Decisão:** loop de
  feedback (apelidos/correções) **descartado** — removido do escopo e do
  checklist. O bridge fica só extração → arquivos.
- **2026-07-07 (sessão dev)** — **Planos de implementação escritos e
  commitados** (um por repo) + roteiro copiar-e-colar para o PC-ponte em
  `docs/COMO-IMPLEMENTAR-NO-PC-PONTE.md` (pré-requisitos, prompts prontos para
  o Claude Code das 2 sessões e os 4 passos manuais da implantação). Ordem: 1º
  o plano do app (`cotacao-auditoria-atacaderj`), 2º o deste repo (robô
  depende dos IDs do app).
- **2026-07-07 (sessão dev)** — **Design aprovado e revisado** (estrutura de
  acesso): descoberto que o app da cotação roda como **artifact no claude.ai**
  (IA via sessão + storage compartilhado) — a injeção no HTML foi descartada.
  Modelo final: bridge gera **arquivo único** (`catalogo_bridge.json`) →
  **robô Playwright agendado** no PC-ponte sobe no artifact pelo botão do app
  → storage compartilhado distribui a todos. Falha do robô é visível (trava
  de data do app); plano B = upload manual do arquivo (30s); plano C = 3
  relatórios do ERP. Migração documentada (app local + injeção + API paga) se
  o claude.ai inviabilizar o robô. Spec:
  `docs/superpowers/specs/2026-07-07-estrutura-acesso-cotacao-design.md`.
- **2026-07-09 (ARQUITETURA CONFIRMADA COM O DONO)** — Fatos que corrigem a
  premissa das sessões anteriores: (1) até hoje o app SEMPRE rodou como
  **arquivo .html local** no PC da loja — nunca foi artifact; por isso o
  upload manual dos 3 relatórios "sempre funcionou" (file:// não tem CSP);
  (2) no modo local **a IA nunca respondeu** (sem chave + CORS — documentado
  no cabeçalho de ferramentas/proxy-teste/servir.mjs do repo do app); o que
  funcionava era a busca local; (3) o dono confirmou que **os vendedores usam
  foto/lista manuscrita → IA obrigatória → IA tem que ser a do PLANO Claude
  (não API paga)** → o app TEM que ser publicado como **artifact no claude.ai**
  (única forma de usar a sessão/plano de cada vendedor). Decisão: artifact é o
  caminho para os vendedores; o arquivo publicável enxuto já existe
  (`npm run publicavel` no repo do app → 365KB, XLSX via cdnjs que é liberado,
  CATALOG embutido removido — jsdelivr é BLOQUEADO em artifact e foi por isso
  que a primeira tentativa de publicar "quebrou funções"). Dados entram no
  artifact SÓ por upload (📦 catalogo_bridge.json — fluxo já implementado em
  2026-07-08); robô Playwright automatiza isso depois. Pendências do dono:
  publicar o artifact (anexar o .publicavel.html numa conversa do claude.ai),
  testar IA/foto + upload + storage compartilhado em 2 contas, distribuir o
  link; QR do WhatsApp (envio das 16h segue falhando por falta do login).
- **2026-07-08 (AUDITORIA NO MODELO DO ROBÔ)** — Pedido do dono: "adapte a aba
  Auditoria para funcionar dentro desse modelo de robô". Feito nos dois repos:
  (a) **ponte**: query CATALOGO ganhou `QUANTIDADE_ATACADO` (qtde mínima real
  do atacado — a correção apontada na auditoria de 07/07, conferida 995/995) e
  nasceu a projeção `catalogo_bridge_json` (contrato do plano da sessão dev +
  seção `pedidos_venda` com os pedidos fechados da janela de 7 dias), escrita
  em `saida/cotacao/catalogo_bridge.json` nos alvos catalogo/pedidos-venda/
  movimentos; (b) **app**: plano `aceitar-catalogo-bridge` implementado
  (seção "Arquivo único do bridge" no modal 📦, `processarCatalogoBridge` com
  as validações do contrato, IDs `#catBridgeArq`/`#catConfirmar` p/ o robô) +
  `confirmarCatalogoBridge` persiste o histórico no storage compartilhado
  (`atacaderj_pedidos_venda`, ~158KB) e a aba Auditoria passou a ler
  storage → fetch local → xlsx manual. Testado de ponta a ponta em Node com o
  arquivo REAL: auditoria de 06/07 via storage = 199 linhas/154 auditados/33
  divergências/R$ 105,92, idêntico ao motor validado contra o relatório
  manual. Falta só o robô Playwright (+ republicar o artifact e logar o
  navegador) — aí o ciclo fecha sem toque humano.
- **2026-07-07 (RECONCILIAÇÃO — merge das duas sessões)** — Esta sessão (PC-
  ponte, acesso direto ao banco) e a sessão de dev (sem acesso a este PC, só
  planejamento) trabalharam em paralelo e divergiram no GitHub. Ao dar
  `git push`, veio à tona que **a "aba Auditoria com seletor de dia" e o
  `fetch("pedidos_venda_dav.csv")` implementados aqui hoje partiram da
  premissa errada de que o app é servido localmente** — na real, ele é
  artifact do claude.ai (fato só documentado no lado da sessão dev) e não
  alcança a rede da loja. Ou seja: **o seletor de dia funciona só se alguém
  abrir o HTML localmente num navegador; na versão publicada real (o link que
  os funcionários usam), ele não vai aparecer** até o robô de upload (ou uma
  adaptação do `catalogo_bridge.json` para incluir os pedidos de venda) entrar
  no ar. Nada foi revertido — os dois lados do trabalho foram mantidos no
  merge — mas fica registrado que **a integração final ainda depende de
  decidir/executar os planos de `docs/superpowers/plans/`**. Ver item revisto
  no checklist acima.
