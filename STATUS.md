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
- [x] Apontar os caminhos de `saida` para os detectores — **salão FEITO
  (2026-07-11)**: detector clonado em `C:\Users\User\detector-ruptura-atacaderj`,
  `detector_salao_dir` apontado p/ o `data\input` dele, dados reais fluindo,
  tarefa **DetectorRuptura-Diario 05:30 seg–sáb** registrada e testada
  (dry-run). **Estoque ainda pendente** (segue em `saida/` do próprio repo).
- [x] ~~Loop de feedback (apelidos/correções) → GitHub via serverless~~ —
  **descartado** por decisão de 2026-07-07 (ver log); bridge fica só extração
- [x] **Ciclo de marcação do operador implantado no ponte (2026-07-14)** —
  colheita agendada ("AtacadeRJ - Colher Marcas" 05:20 + HH:40), gabarito do
  teste de campo semeado, treino manual provou o histórico versionado com push
  automático, daily dry-run com botões A/RA/RC + Concluído. **Falta só o dono
  fechar o E2E** (marcar no HTML enviado ao celular dele e tocar Concluído —
  a colheita agendada grava sozinha). dryRun segue true.

- [x] **Relatório "abaixo do custo" 06:00 (2026-07-14)** — `src/abaixo_custo.py`
  (markup ≤3%, dia anterior útil, consulta direta ao ERP) → WhatsApp
  5521970296224 via enviar.mjs. Tarefa **"AtacadeRJ - Abaixo do Custo"**
  (06:00 + retry 30min até 12:00 — cobre o atraso de sync do PDV). Semântica
  validada no ERP cru (PAO DE QUEIJO 41622: 5un, venda 9,29, custo 14,27) e
  1º envio real OK (30 itens de 13/07). Config: `abaixo_custo` no config.local.
- [x] **7ª query `HISTORICO_CLIENTE` (2026-07-17)** — compras por cliente
  (itens de DAV, janela `historico_cliente_meses` = 24) → CSV de 11 colunas
  p/ o app `recuperacao-itens-atacaderj` (`--only historico-cliente`, job
  01:00 registrado pelo repo do app). Descobertas do schema: **grupo
  mercadológico = `VW_MGN_PRODUTO.Departamento`** (raiz da árvore de
  classificação; não há cdGrupo em tbSuperProduto e tbDicionarioProduto está
  vazia); **cliente ativo = `COALESCE(tbPessoa.inMorto,0)=0`** (único flag;
  NULL na maioria); itens com `qtPedidoItem = 0` (26%!) são pedido zerado,
  não compra → filtrados. DAV só existe desde 2026-01-15 (módulo novo) — o
  histórico engorda sozinho. 1ª extração real: 95.644 linhas / 354 clientes
  em 9,3s. Testes: `tests_historico_cliente.py` (6).

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

-1. **FECHAR O E2E DA MARCAÇÃO (só falta o dono)**: o relatório
    `2026-07-13.html` foi enviado ao celular do dono em 14/07 ~13:26. Ele abre
    o arquivo, marca 1–2 itens e toca **Concluído** (envia a mensagem que o
    WhatsApp abrir). A colheita agendada (HH:40) grava sozinha em
    `data/feedback/2026-07-13.json` do detector — ou rode
    `node scripts/whatsapp/colher-marcas.mjs`. Conferir o arquivo e regenerar
    o dashboard (`node src/dashboard.js` no detector). Se a mensagem chegar
    mas for filtrada, investigar o remoteJid no log antes de mexer na allowlist.

0. **Detector de salão: NO AR em dry-run (2026-07-11)** — validar a qualidade
   dos alertas por alguns dias (1ª rodada real: 1.845 suspeitos — limiares
   provavelmente precisam de calibragem via revisão semanal). Go-live
   (WhatsApp/Apps Script) e relatório HTML chegam nas próximas rodadas.
   Design: `docs/superpowers/specs/2026-07-11-detector-salao-dados-reais-design.md`.
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

- 2026-07-20 (4ª rodada): **Painel: ajustes do dono após 1ª olhada na TV** —
  colunas ordenáveis (clique no cabeçalho: ▲/▼/original, visão geral e
  detalhe), estado-vazio "nenhum item para mostrar" (o "não abre" da ruptura
  era detalhe vazio idêntico ao card — diagnosticado no navegador via CDP),
  fallback de popup no concorrente, cobrança em ordem CRESCENTE com badge
  amarela ≤21d/vermelha >21d e janela 45d (202 p/ cobrar +220 abandonados na
  rodada real). Commit b2f5ce5, redeployado e verificado ao vivo no ponte.
- 2026-07-20 (4ª rodada): **fix CATALOGO — atacado não ressuscita pela view**
  quando o item tem linha no caixa (relâmpago vigente/tier inativo suspendem o
  degrau; auditoria achou 4 itens em que a cotação prometia atacado MENOR que
  a relâmpago cobrada). Regra do dono registrada: *o preço de maior hierarquia
  sempre vale*. View segue como fallback só de item SEM linha no PDV (hoje: 0
  itens). +3 testes (134 no total). Do mesmo dia, no pricing: relatório de
  concorrência re-lê o caixa na geração (caso Piraquê 15985: 3,49 congelado
  na extração de 17/07 vs 2,99 no caixa).
- 2026-07-20 (3ª rodada): **Painel de Compras NO AR no ponte** — 9 tasks
  executadas via subagentes (fixes de review em 3/6/7/8 + 3 Important do
  review final: servidor no logon sem limite 72h, firewall TCP 8477,
  trilha PAINEL no bridge_erros.log), merge `618cb43` no master, 131 testes.
  Implantado via ssh: config.local.json + rodada real (5,1s: **247 relâmpago,
  252 cobrança +167 abandonados**, concorrente S29; item 35887 conferido ao
  centavo no ERP cru) + tarefas registradas + servidor respondendo **200 em
  http://192.168.0.164:8477/** (TV: `#tv`). Pendências herdadas: quadrante
  ruptura avisa "indisponível" até clonar/agendar o detector-estoque no ponte
  (`detector_rounds_dir` já aponta); revisão do pricing segue semanal.
  Follow-ups aceitos (Minors do review final): "indisponível desde" usa
  carimbo atual; falha só de VALIDADES zera validades com banner; bloco painel
  fora do CONTRATO-DE-DADOS.md; badge de idade da rodada.
- 2026-07-20 (2ª rodada): **Painel de Compras: plano de implementação pronto**
  (`docs/superpowers/plans/2026-07-20-painel-compras.md`, 9 tasks TDD) com as
  3 investigações §10 RESOLVIDAS no schema real via ssh: relâmpago =
  `tbPromocaoRelampago` (247 vigentes); fornecedor =
  `tbPedidoCompra.cdPessoaComercial→tbPessoa` + telefone em `tbTelefone`;
  descoberta: 494/534 pedidos abertos com 7+ dias (loja não encerra pedido
  morto) → janela `cobranca_max_dias=60` + contador de abandonados (spec
  emendada §4.3/§7/§10/§12).
- 2026-07-20: **Painel de Compras (TV + PC): design aprovado** — spec em
  `docs/superpowers/specs/2026-07-20-painel-compras-design.md`. Tela única com 4
  quadrantes (validade×relâmpago, ruptura via detector-estoque, cobrança de
  fornecedor ≥7 dias, concorrente = reuso do revisao_Sxx.html do pricing), modo
  TV sem interação (rodízio) + modo PC interativo, gerador novo
  `src/painel_compras.py` na bridge. Próximo: writing-plans (pendem 3
  investigações de schema no ponte — spec §10).
- 2026-07-17 (3ª rodada): **Decisão final do quadro: 11 operadoras (mín 10) com
  BANCO DE HORAS, zero parciais** — o banco (já vigente na loja) dissolve a
  rigidez dos turnos fixos: sábado com 8 pessoas em jornadas 5h30-9h (era 12
  turnos fixos; 31% de desperdício eliminado), compensação na segunda (o vale).
  Escala completa em `docs/ESCALA-CAIXAS.md`. Anti-overfitting rodado:
  itens×tempo (12s/item monotônico), faturamento frente×retaguarda 30/30 dias
  a 0,00%, throughput físico, backtest jan-abr→mai-jul (5/6 dias generalizam)
  e jackknife mensal (sáb pico=7 estável). Backtest revelou REGRA DE VÉSPERA:
  véspera/emenda de feriado escala como sábado (05/06 pós-Corpus e 10/07
  estouraram a grade de sexta com 26-30% de nível). Pendências da escala:
  almoço de 1h real no sábado (hoje suprimido em várias jornadas — passivo) e
  teto de 10h/dia nos spans longos.

- 2026-07-17 (2ª rodada): **Meta oficial revisada para 5min/95% todos os dias**
  (decisão do dono após análise de sensibilidade: o sábado exige 12 turnos com
  3min OU 5min — a meta apertada só encarecia os dias de semana). CLI ganhou
  `--meta-seg`/`--meta-pct` (default 300s/0.95). Relatório oficial 5min/95%
  (jornada 6h20): turnos/dia seg=8 ter=9 qua=9 qui=10 sex=10 **sáb=12**
  (semana 58; em 44h: seg=7 ter=9 qua=9 qui=9 sex=9 sáb=12, semana 55).
  Pico simultâneo continua ≤7 caixas. Stress +10%: sáb=13. Ociosidade da
  abertura ficou ainda mais visível (06:30 sobra +2,1 a +3,0 caixas).
  Quadro (férias 0,085N + faltas medidas 7,4%): mínimo 13-14, fixo pleno 15,
  ou **mista 11-12 fixas + 3 tempo-parcial sex/sáb**. Medido nos sábados: span
  mediano no caixa 7,7h (69% >7,5h, máx 9,7h) — é assim que 8-9 pessoas cobrem
  hoje o que o modelo divide em 12 turnos legais.

- 2026-07-17: **Dimensionamento de caixas/operadoras por dia da semana RODADO
  no ponte contra o banco real** (`src/dimensionamento_caixas.py` + 7 modulos
  `dim_*` puros, ~1600 linhas, 73 testes, TDD subagente-a-subagente com review
  por tarefa + review final da branch). Meta: **95% dos clientes com espera
  < 3min na fila**, por faixa de 30min. Fonte `DORSAL.tbCupom` ∪
  `tbCupomCancelado` (tbVendaPDV NAO serve: sem PDV/operador). Recorte: filial 1,
  exclui PDV 11/12 (atacado), operador 7000 (fiscal), domingos. Metodo:
  **simulacao de eventos discretos** (M/G/c fila unica, chegadas reais)
  validada contra Erlang-C (deltas <=0.0052, tol 0.015); dimensionador por
  ponto fixo; margem = **P85** do dia da semana; escala CLT 6h20. Confere
  tbCupom x tbConsPDVOperador (145 dias, 1 divergente=2026-06-19, <5% -> avisa
  e segue). Resultado real (6 meses, 94.789 cupons, servico mediano 65s +
  handover 36s, **0 slots saturados** = demanda nao censurada, numeros sao
  estimativa e nao piso):
  operadoras/dia seg=8 ter=9 qua=10 qui=10 sex=11 sab=13; caixas simultaneos
  min/max seg 2/5, ter 2/6, qua 3/6, qui 3/6, sex 3/7, sab 4/7 (pico 10-11h).
  Ociosidade: no pico ~0 excesso; **06:30 sobra 1,5-2,6 caixas** (abertura
  superdimensionada). NAO agendado (analise sob demanda). Spec+plano em
  `docs/superpowers/`.

- 2026-07-17: **Fase 1 da exposicao MIN/MAX no ar.** Query `VENDAS_CANAL`
  (DORSAL.tbCupom + tbCupomItem + resolucao de EAN por tbProdutoVenda) ->
  `saida/exposicao/vendas_canal.csv` (venda por item/dia/canal em unidades) e
  `catalogo_exposicao.csv` (caixa-mae do cadastro + prateleira). Alvo novo
  `--only exposicao`, tarefa `AtacadeRJ - Exposicao Mensal` (dia 1, 04:00,
  LastTaskResult 0, testada de verdade no ponte). Reconciliacao com
  tbVendaPDV via `scripts/verificar-reconciliacao-canal.py`: **26 dias
  mutuos exatos em `--dias 30` (diff 0.000)**; extracao real da tarefa
  agendada: **272.373 linhas / 4.636 itens**; atacado (PDV 11/12) = **35,0%
  do volume**. Descoberta que motivou tudo: `tbVendaPDV` NAO tem o numero do
  PDV, e o cupom do DORSAL traz o produto ora como codigo interno ora como
  EAN (com multiplicador de caixa). `scripts/cadastro-caixa-mae-suspeito.py`
  rodou no ponte e gerou os ~30 itens de cadastro suspeito (CSV) para o dono
  analisar (D17). Spec:
  `docs/superpowers/specs/2026-07-17-exposicao-min-max-design.md`.
  Proximo: Fase 2 (repo `exposicao-atacaderj`).

- **2026-07-14 (RELATÓRIO "ABAIXO DO CUSTO" 06:00 — spec
  `docs/superpowers/specs/2026-07-14-abaixo-custo-6h-design.md`)** ✅
  Implementado `src/abaixo_custo.py` (CLI `--dia/--config/--dry-run`; funções
  puras separadas do I/O; guardas: carimbo → exit 0, dia sem vendas → exit 0
  silencioso, número não configurado → aviso + exit 1; envio via
  `enviar.mjs`; carimbo `saida/abaixo-custo/enviado-<dia>.txt` com a mensagem
  dentro) + `tests_abaixo_custo.py` (10/10) + `scripts/registrar-abaixo-custo.ps1`
  (tarefa 06:00, retry 30 min por 6h, StartWhenAvailable) + bloco
  `abaixo_custo` no config.example. **Correção do dono após a 1ª mensagem
  real**: o corte virou `markup <= -3%` (só prejuízo de 3% ou mais;
  `margemMax: -0.03`) — os de markup positivo/zero/levemente negativo saem.
  Pendências no ponte: rodar `registrar-abaixo-custo.ps1` (Admin), preencher
  `abaixo_custo.numero` no config.local.json e validar a semântica
  valor/custo contra 1 item conhecido do ERP antes do 1º envio.

- **2026-07-14 (CICLO DE MARCAÇÃO NO PONTE — roteiro `docs/IMPLANTAR-MARCACAO-NO-PONTE.md`)** ✅
  Sessão no próprio ponte executou o roteiro: (0) gh auth válido — repo privado
  do detector alcançável e push funcionando. (1) Repos atualizados (detector
  chegou em c42189d e, durante a sessão, 38aebe2 — quarentena do Abastecido
  vinda da dev); suíte do detector **144/144**, testes do bridge (parser+lock)
  **7/7**. Achado/consertado: o teste do `runDemo` quebrava SÓ neste PC porque
  a demo carregava o modelo GLM real de `data/modelo/` via CWD — demo agora é
  hermética (detector `a8eda9a`). (2) Configs: `numeroPonte` adicionado ao
  config do detector; checagem obrigatória ok (`appsScriptUrl` segue
  placeholder); `dryRun` segue `true`; a seção `marcas` do bridge já estava
  pronta. **Limpeza importante**: o bloco `detection` do config local do
  detector era snapshot da config v1 (11/07) e sobrescrevia o piso
  `minDiasParado` do motor v2 de 5 para 1 — removido, o example v2 volta a
  valer (backup `.bak-2026-07-14`, agora gitignored no detector). (3) Gabarito
  do teste de campo semeado em `data/feedback/2026-07-11.json` (3
  reabastecimento + 13 falso). (4) Treino manual: `historico/precisao.csv`
  ganhou `2026-07-11;30;10;7;3;0;0.3;proxy;3` e o commit do histórico foi
  criado e **pushado sozinho** (identidade git repo-local configurada nos 2
  repos — não havia global e o treino commita). (5) Daily dry-run: rodada
  2026-07-13 com **42 itens REPOR**, 42 botões `data-tok` + rodapé Concluído
  apontando ao ponte, `Enviado=false`. (6) Tarefa **"AtacadeRJ - Colher
  Marcas"** registrada e Pronto (05:20 diário + a cada 60 min em HH:40;
  registrou sem precisar de janela admin). (7) E2E: relatório enviado ao
  celular do dono (envio manual único autorizado, ~13:26); 3 colheitas manuais
  em ~30 min = 0 mensagens — o dono ainda não marcou; **pendente só a resposta
  dele**, a colheita agendada fecha o ciclo sozinha. Dashboard regenerado
  refletindo o gabarito.
- **2026-07-13 (MOTOR v2 + MODELO v3 NO AR — dry-run, deploy por SSH da dev)** ✅
  Detector de salão atualizado para a **detecção v2 por intervalo próprio**
  (spec/plano no repo do detector; 16 tasks TDD, review por task + review
  final, suíte 114/114): scoreRuptura = (diasParado ÷ intervalo típico EWMA) ×
  confiança, teto 30d, feriado auto-detectado, seções **REPOR (topo) ×
  COMPRAR (só curva A)** com % do **GLM calibrado** (treinado aqui:
  150.308 amostras, base-rate 0,163 → `data/modelo/repor_comprar.json`) e
  fallback de heurística. Bridge ganhou `entradas.csv` + `curva_abc.csv` p/ o
  salão (commits 25536cb/1842107; WIP local do ULTIMO_CUSTO preservado via
  stash/pop, segue não commitado). 1ª rodada real v2 (ref 11/07): **479 fora
  do padrão → 30 REPOR + 13 COMPRAR-A (de 45); 13 recém-abastecidos fora**;
  HTML em `data\reports\`. Tarefas: DetectorRuptura-Diario 05:30 (rodou
  sozinha às 05:00/05:30 de hoje) + **DetectorRuptura-TreinoModelo dom 06:00
  (nova)**. Pendências: go-live (QR/Apps Script) e calibragem com marcações.
- **2026-07-11 (DETECTOR DE SALÃO NO AR — dry-run, executado por SSH da dev)** ✅
  A sessão da máquina de dev implantou o detector NESTE PC de ponta a ponta,
  por **SSH sobre Tailscale** (OpenSSH Server instalado hoje aqui pelo dono;
  chave da dev autorizada — acesso `ssh User@100.99.176.6` fica permanente
  para as próximas rodadas). Passos: (1) detector clonado via **git bundle +
  scp** (o token deste PC não alcança o repo privado `detector-ruptura-atacaderj`
  — origin já aponta p/ o GitHub, autenticar quando precisar de pull direto);
  (2) `npm install` + **90/90 testes verdes** (obs: postinstall do puppeteer
  bloqueado por allow-scripts — Chromium não baixou; irrelevante em dry-run,
  resolver no go-live OU delegar envio ao Baileys daqui); (3) config do
  detector = example (dry-run, placeholders de WhatsApp/Apps Script — doctor
  acusa os 3, esperado); (4) `detector_salao_dir` do config vivo apontado p/
  `C:/Users/User/detector-ruptura-atacaderj/data/input` (backup
  `config.local.json.bak-2026-07-11`, agora coberto pelo .gitignore);
  (5) `--only vendas` + `--only recebimentos` = **153.928 vendas + 3.531
  recebimentos reais** no data\input (headers conferidos com o contrato;
  achado: 1 linha de recebimento com **código vazio** vinda do ERP — o
  detector descarta sozinho, mas vale filtrar na query como já se faz com
  `cdProduto IS NOT NULL`); (6) 1ª rodada real dry-run: **1.845 suspeitos**
  (159 crítico / 398 alto / 1.288 médio) — volume alto, calibrar limiares na
  validação; (7) tarefa **DetectorRuptura-Diario** (node src/daily.js, 05:30
  seg–sáb, StartWhenAvailable) registrada e TESTADA via `schtasks /Run`
  (LastTaskResult 0, rodada regravada). Próximo: dono valida alertas alguns
  dias; relatório HTML (código na dev → git pull aqui); go-live depois.
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

- 2026-07-17 (revisão profunda): HISTORICO_CLIENTE ganha LTRIM(RTRIM(nmPessoa)) (13 clientes tinham espaço na borda do nome) e normalização de grafia de família ("CONSERVAS 2"→"CONSERVAS", que partia a família no lookalike do app). tests_historico_cliente: 7.
