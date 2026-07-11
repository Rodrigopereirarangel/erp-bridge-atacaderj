# Design — Detector de salão com dados reais (PC-ponte como servidor)

**Data:** 2026-07-11
**Repos afetados:** `erp-bridge-atacaderj` (implantação + SELECTs) e
`detector-ruptura-atacaderj` (relatório HTML; única mudança de código)
**Status:** aprovado pelo usuário em 2026-07-11

## Objetivo

Tirar o detector de ruptura de salão dos dados fictícios (proxy): o **PC-ponte**
(DESKTOP-3BLTBIV, na loja, ligado 24h) passa a ser o **servidor** que roda o
bridge e o detector, agendados, com dados reais do MySQL do ERP. Nesta rodada o
detector roda em **dry-run** (gera, não envia); o go-live (QR do WhatsApp +
Apps Script) fica para uma rodada futura.

## Decisões desta rodada (respostas do usuário)

1. **Onde roda:** tudo no PC-ponte (bridge + detector). A máquina de dev fica
   só para edição de código e git.
2. **Escopo:** só o detector de **salão** (`detector-ruptura-atacaderj`). O de
   estoque entra em rodada própria.
3. **Execução:** remota, desta sessão, via **SSH sobre Tailscale**
   (`100.99.176.6`). O usuário instala o OpenSSH Server no ponte com bloco
   pronto (chave pública `id_ed25519_ponte` da máquina de dev autorizada).
4. **Go-live:** ainda não — dados reais + dry-run; usuário valida a qualidade
   dos alertas por alguns dias antes de ativar envio real.
5. **"HTML por WhatsApp":** o detector ganha um **relatório HTML bonito**
   (leitura, sem botões). A conferência com botões continua no desenho
   original (Apps Script), pendente para o go-live.

## Topologia (papéis)

| Máquina | Papel |
|---|---|
| CONCENTRADOR `192.168.0.245:3306` | MySQL do ERP. Intocado; acesso só leitura (`viewer`). |
| PC-ponte DESKTOP-3BLTBIV `192.168.0.164` / TS `100.99.176.6` | Servidor: roda bridge (05:00) e detector (05:30), agendados. |
| Dev DESKTOP-LQNIKEQ `192.168.0.14` / TS `100.89.110.18` | Edição + git + comando remoto via SSH. Não alcança o MySQL. |

O GitHub continua sendo a memória do projeto: código editado na dev → push →
pull no ponte. Senhas e dados (custo/preço/vendas) **nunca** vão para o git.

## Fluxo diário no PC-ponte

```
05:00  bridge.py (Tarefa Agendada, seg–sáb)
       MySQL → vendas.csv + recebimentos.csv
       gravados DIRETO em <detector>\data\input\   (escrita atômica: temp + rename)
05:30  npm run daily (Tarefa Agendada, seg–sáb, dry-run)
       lê CSVs → detecção → mensagem de texto (impressa) + relatório HTML em data\reports\
```

**Ligação bridge→detector:** o `config.local.json` do bridge aponta
`detector_salao_dir` para o `data/input` do detector — o padrão que o próprio
`config.example.json` já sugeria (`_saida_real_sugerida`). Sem cópias, sem
código novo. Requisito: a projeção deve escrever **temp + rename** (conferir
`src/projections.py`; ajustar se necessário) para o detector nunca ler arquivo
parcial. A folga 05:00→05:30 é a segunda proteção.

## Mudanças no `erp-bridge-atacaderj`

- Preencher os SELECTs de **vendas** e **entradas** em `src/queries.py` com o
  schema real (via `python src/inspect_schema.py ...` rodando no ponte).
  **catalogo** e **pedidos** ficam TODO (rodadas da cotação/estoque).
- `config.local.json` no ponte (gitignored): `db` (host `192.168.0.245`,
  `viewer`, senha, database) + `saida.detector_salao_dir` →
  `C:/Users/<user>/detector-ruptura-atacaderj/data/input`.
- Agendamento: **só movimentos** (05:00) nesta rodada — se
  `scripts/register-tasks.ps1` agendar catálogo junto, ganhar opção/ajuste.
- Atenção: `--only movimentos` hoje cobre vendas+recebimentos+**pedidos**, e o
  SELECT de pedidos fica TODO nesta rodada. O bloco movimentos deve **pular com
  aviso** as extrações ainda-TODO (ou a tarefa agendada usa
  `--only vendas` + `--only recebimentos`) — decidir no plano; o dia agendado
  não pode quebrar por causa de um TODO.
- `STATUS.md`: checklist e log atualizados a cada avanço (regra do repo).

## Mudanças no `detector-ruptura-atacaderj`

**Novo: relatório HTML diário** (única mudança de código da rodada):

- Gerado pelo `npm run daily` em `data/reports/<AAAA-MM-DD>.html` (pasta nova,
  dentro de `data/` que já é gitignored).
- Autocontido (CSS inline, sem internet), mobile-first.
- Conteúdo: cabeçalho (data, total de suspeitos, contagem por faixa
  crítico/alto/médio) + tabela com cor por faixa: código, descrição, dias
  parado, último recebimento (data + qtd), probabilidade.
- Envio: no modo real (futuro), vai como **anexo** (documento) na mesma
  conversa do WhatsApp, com a mensagem de texto atual como legenda/companheira.
  Em **dry-run**, só gera o arquivo (o caminho é impresso no console).
- O dry-run não pode exigir sessão WhatsApp nem Apps Script configurado
  (comportamento atual mantido; se algo bloquear, ajustar para degradar com
  aviso).
- Testes: unidade para a montagem do HTML (contagens, faixas, escape de
  descrição); `npm test` segue verde.

Fora isso, **zero mudança** no detector: detecção, limiares, weekly, dashboard
e doctor ficam como estão.

## Implantação remota (ordem de execução)

1. **SSH de pé** (bloco PowerShell Admin já entregue ao usuário; chave
   ed25519 autorizada; usuário informa o `whoami`).
2. No ponte, via SSH: `winget install` Git + Python 3.12 + Node LTS;
   `git clone` dos 2 repos; `pip install -r requirements.txt`; `npm install`
   (detector).
3. Testar login do `viewer` no MySQL (senha pedida ao usuário na hora, escrita
   só no `config.local.json` do ponte). Se `Access denied ...@'192.168.0.164'`:
   usuário roda na CONCENTRADOR `CREATE USER 'viewer'@'192.168.0.%' ...;
   GRANT SELECT ...; FLUSH PRIVILEGES;` (comando entregue pronto).
4. `inspect_schema` no ponte → saída lida na dev → SELECTs preenchidos na dev
   → commit/push → pull no ponte.
5. `python src/bridge.py --only movimentos` → validar CSVs contra o contrato
   (`docs/CONTRATO-DE-DADOS.md`): separador `;`, colunas, datas dia a dia,
   última entrega por item no `recebimentos.csv`.
6. No detector: `npm run doctor` + `npm run daily` (dry-run) com dados reais →
   conferir mensagem e HTML.
7. Registrar as 2 Tarefas Agendadas (05:00 bridge; 05:30 detector) e atualizar
   `STATUS.md` (+ log do acesso SSH).

## Critérios de aceite

- [ ] `vendas.csv` + `recebimentos.csv` **reais** em `<detector>\data\input`
      no ponte, regenerados pela tarefa das 05:00.
- [ ] `npm run daily` (dry-run) roda sozinho às 05:30 e produz mensagem +
      `data/reports/<data>.html` com dados reais.
- [ ] Relatório HTML abre no celular, legível, cores por faixa.
- [ ] Nenhuma senha/custo/preço commitada; `viewer` segue só leitura
      (trava de `SELECT` do `src/db.py` intacta).
- [ ] `STATUS.md` do bridge reflete o novo estado.
- [ ] `npm test` (detector) verde na dev e no ponte.

## Riscos e respostas

| Risco | Resposta |
|---|---|
| `viewer` só existe em `localhost` | `CREATE USER 'viewer'@'192.168.0.%'` (usuário roda no HeidiSQL; comando pronto). |
| Schema real diferente do imaginado | `inspect_schema` primeiro; SELECTs só depois do schema em mãos. |
| Unidade de `qtd_vendida` ≠ unidade de preço (aberto no contrato) | Irrelevante para o salão (usa só quantidade); registrar o achado no contrato para as próximas rodadas. |
| Detector ler CSV pela metade | Escrita temp+rename no bridge + folga de 30 min. |
| PC-ponte desligado às 05:30 | Já era premissa do projeto (fica 24h); tarefa configurada para rodar assim que possível se perder o horário. |

## Fora de escopo (rodadas futuras)

- Go-live do envio real: QR do WhatsApp no ponte, Apps Script (`/exec` + token),
  `dryRun: false`.
- Detector de **estoque** (entradas/pedidos/curva) e SELECTs de catálogo/pedidos.
- Página de conferência com botões via HTML no WhatsApp (ideia registrada;
  hoje segue Apps Script).
- Cotação (`catalogo_bridge.json` + robô) — plano próprio já commitado.
