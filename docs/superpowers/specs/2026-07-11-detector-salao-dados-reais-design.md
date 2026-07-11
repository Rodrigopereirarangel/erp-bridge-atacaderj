# Design — Detector de salão com dados reais (PC-ponte como servidor)

**Data:** 2026-07-11 (revisado após sincronizar com o estado real do PC-ponte)
**Repos afetados:** `erp-bridge-atacaderj` (1 linha de config no ponte + STATUS) e
`detector-ruptura-atacaderj` (clone no ponte + relatório HTML, única mudança de código)
**Status:** aprovado pelo usuário em 2026-07-11

## Objetivo

Tirar o detector de ruptura de salão dos dados fictícios (proxy): o **PC-ponte**
(DESKTOP-3BLTBIV, na loja, ligado 24h) passa a ser o **servidor** que roda o
bridge e o detector, agendados, com dados reais do ERP. Nesta rodada o detector
roda em **dry-run** (gera, não envia); o go-live fica para uma rodada futura.

## Decisões desta rodada (respostas do usuário)

1. **Onde roda:** tudo no PC-ponte (bridge + detector). A máquina de dev fica
   só para edição de código e git.
2. **Escopo:** só o detector de **salão** (`detector-ruptura-atacaderj`). O de
   estoque entra em rodada própria.
3. **Execução:** remota, desta sessão, via **SSH sobre Tailscale**
   (`100.99.176.6`). O usuário instala o OpenSSH Server no ponte com bloco
   pronto (chave `id_ed25519_ponte` da dev autorizada).
4. **Go-live:** ainda não — dados reais + dry-run; usuário valida a qualidade
   dos alertas por alguns dias antes de ativar envio real.
5. **"HTML por WhatsApp":** o detector ganha um **relatório HTML bonito**
   (leitura, sem botões). A conferência com botões continua no desenho
   original (Apps Script), pendente para o go-live.

## Estado real do PC-ponte (fatos que ENCOLHEM esta rodada)

Descoberto ao sincronizar com o `STATUS.md` atualizado pela sessão do ponte
(o retrato da sessão dev estava defasado):

- O ERP é **Solidcon sobre SQL Server 2014** (`192.168.0.245:1433`, database
  `Solidcon`, login `rodrigo` só-leitura) — **não MySQL**. Nada de viewer,
  `inspect_schema` ou SELECTs a preencher: **as queries já estão prontas,
  validadas ao centavo** contra o consolidado oficial.
- O bridge **já roda agendado** no ponte (`C:\Users\User\erp-bridge-atacaderj`):
  Movimentos **05:00** (gera `vendas.csv` real com ~154 mil linhas,
  `recebimentos.csv` ~3,5 mil), Catálogo 08/12/15/18h, Auditoria 16h, robô de
  upload. Hoje os CSVs do salão caem em `saida\detector-salao\` do próprio repo.
- A projeção do salão (`vendas.csv` sem valor + `recebimentos.csv`) **já existe**
  e a escrita **já é atômica** (`.tmp` + `os.replace`) — zero código novo no bridge.
- **Node.js já existe** no ponte (o envio da auditoria roda em Node/Baileys) e o
  **WhatsApp do ponte já está conectado** (QR escaneado em 10/07, envio testado).
- Usuário Windows do ponte: **`User`** (SSH: `User@100.99.176.6`; confirmar com
  o `whoami`).
- Checklist do STATUS já previa exatamente isto: *"Apontar os caminhos de
  `saida` para os detectores quando eles forem clonados neste PC"*.

## Topologia (papéis)

| Máquina | Papel |
|---|---|
| CONCENTRADOR `192.168.0.245:1433` | SQL Server do Solidcon. Intocado; login `rodrigo` só leitura. |
| PC-ponte DESKTOP-3BLTBIV `192.168.0.164` / TS `100.99.176.6` | Servidor: bridge (05:00, já no ar) + detector (05:30, novo), agendados. |
| Dev DESKTOP-LQNIKEQ `192.168.0.14` / TS `100.89.110.18` | Edição + git + comando remoto via SSH. Não alcança o banco. |

GitHub segue sendo a memória: código editado na dev → push → pull no ponte.
Senha/custo/preço/telefones **nunca** vão para o git.

## Fluxo diário no PC-ponte (alvo desta rodada)

```
05:00  bridge --only movimentos (tarefa JÁ registrada)
       SQL Server → vendas.csv + recebimentos.csv
       gravados DIRETO em C:\Users\User\detector-ruptura-atacaderj\data\input\
       (escrita atômica já embutida)
05:30  npm run daily (tarefa NOVA, seg–sáb, dry-run)
       lê CSVs → detecção → mensagem de texto (impressa, não enviada)
       + relatório HTML novo em data\reports\<AAAA-MM-DD>.html
```

**Ligação bridge→detector:** editar `config.local.json` do bridge NO PONTE:
`saida.detector_salao_dir` → `C:/Users/User/detector-ruptura-atacaderj/data/input`.
É o padrão que o próprio `config.example.json` sempre sugeriu
(`_saida_real_sugerida`). Sem cópias, sem código novo.

## O que muda em cada repo

**`erp-bridge-atacaderj`** (só no ponte, nada de código):
- 1 linha no `config.local.json` (o `detector_salao_dir` acima). Backup do
  arquivo antes de editar — é infraestrutura viva.
- `STATUS.md`: marcar o item do checklist (parcial: salão feito, estoque
  pendente) + log (incluindo o acesso SSH novo).

**`detector-ruptura-atacaderj`**:
- **Clone novo no ponte** (`C:\Users\User\detector-ruptura-atacaderj`) +
  `npm install` + `config.local.json` com `dryRun: true` (QR/Apps Script
  ficam para o go-live; `npm run doctor` valida o setup).
- **Novo: relatório HTML diário** (única mudança de código da rodada, feita na
  dev com testes, push → pull no ponte):
  - Gerado pelo `npm run daily` em `data/reports/<AAAA-MM-DD>.html` (pasta
    nova dentro de `data/`, que já é gitignored).
  - Autocontido (CSS inline, sem internet), mobile-first.
  - Conteúdo: cabeçalho (data, total de suspeitos, contagem por faixa
    crítico/alto/médio) + tabela com cor por faixa: código, descrição, dias
    parado, último recebimento (data + qtd), probabilidade.
  - Em **dry-run** só gera o arquivo (caminho impresso no console). No modo
    real (go-live futuro), vai como **anexo** (documento) na conversa do
    WhatsApp, junto da mensagem de texto atual.
  - O dry-run não pode exigir sessão WhatsApp nem Apps Script (comportamento
    atual mantido; se algo bloquear, degradar com aviso).
  - Testes de unidade da montagem do HTML (contagens, faixas, escape de
    descrição); `npm test` segue verde.
- **Tarefa agendada** no ponte: daily **05:30 seg–sáb** (domingo a loja fecha;
  `scripts/register-daily-task.ps1` já existe — conferir dias/python↔node do
  script no ambiente de lá). A weekly (segunda 06:00) é opcional nesta rodada —
  decidir no plano.

Fora isso, **zero mudança** no detector: detecção, limiares, weekly, dashboard
e doctor ficam como estão.

## Implantação remota (ordem de execução)

1. **SSH de pé** (bloco PowerShell Admin já entregue; usuário informa `whoami`).
2. Via SSH no ponte: `git clone` do detector + `npm install` + config
   (`dryRun: true`) + `npm run doctor`.
3. Editar `config.local.json` do bridge (backup antes): `detector_salao_dir` →
   `data/input` do detector. Rodar `python src/bridge.py --only vendas` e
   `--only recebimentos` para materializar na hora.
4. Validar os CSVs reais contra o contrato (`docs/CONTRATO-DE-DADOS.md`):
   separador `;`, cabeçalhos, datas dia a dia, última entrega por item.
5. `npm run daily` (dry-run) com dados reais → conferir mensagem + HTML
   (código do relatório já pushado da dev e pullado no ponte).
6. Registrar a tarefa 05:30 e conferir na manhã seguinte (ou disparar a tarefa
   manualmente via `schtasks /Run`) que o ciclo 05:00→05:30 fecha sozinho.
7. Atualizar `STATUS.md` + commit + push (lá), pull na dev.

## Critérios de aceite

- [ ] `vendas.csv` + `recebimentos.csv` **reais** em
      `C:\Users\User\detector-ruptura-atacaderj\data\input`, regenerados pela
      tarefa das 05:00 (sem cópia manual).
- [ ] `npm run daily` (dry-run) roda sozinho às 05:30 no ponte e produz
      mensagem + `data/reports/<data>.html` com dados reais.
- [ ] Relatório HTML abre no celular, legível, cores por faixa.
- [ ] Nenhuma senha/custo/preço/telefone commitado.
- [ ] Tarefas em produção do ponte (Catálogo, Auditoria 16h, robô) intocadas
      e funcionando depois da mudança.
- [ ] `STATUS.md` do bridge reflete o novo estado (checklist + log + SSH).
- [ ] `npm test` (detector) verde na dev e no ponte.

## Riscos e respostas

| Risco | Resposta |
|---|---|
| Mexer em infra viva (config.local.json alimenta 4 tarefas em produção) | Backup do arquivo antes; mudar SÓ a chave `detector_salao_dir`; rodar `--only catalogo` depois para provar que o resto continua ok. |
| Detector ler CSV pela metade | Escrita atômica já embutida no bridge + folga 05:00→05:30. |
| `vendas.csv` real (~154 mil linhas) revelar lentidão/erro no detector | Rodar o daily manualmente primeiro (passo 5) antes de agendar. |
| Formato real divergir do contrato em algum detalhe | Passo 4 valida ANTES de rodar o detector; divergência → corrigir projeção no bridge (na dev, com teste). |
| PC-ponte desligado às 05:30 | Premissa do projeto (fica 24h); tarefa com "rodar assim que possível" se perder o horário. |

## Go-live (rodada futura, já facilitado)

- O WhatsApp do ponte **já está conectado** (Baileys, no repo do bridge). No
  go-live, decidir: escanear um segundo QR para o `whatsapp-web.js` do detector
  **ou** o detector delegar o envio ao remetente Baileys já logado (evita duas
  sessões de WhatsApp no mesmo PC). Decisão fica para a rodada do go-live.
- Apps Script (`/exec` + token) para a conferência com botões + `dryRun: false`.

## Fora de escopo (rodadas futuras)

- Go-live do envio real (acima).
- Detector de **estoque** (o bridge já gera os arquivos dele em
  `saida\detector-estoque\`; falta clonar/apontar/agendar — mesmo movimento
  desta rodada).
- Página de conferência com botões via HTML no WhatsApp (ideia registrada;
  hoje segue Apps Script).
