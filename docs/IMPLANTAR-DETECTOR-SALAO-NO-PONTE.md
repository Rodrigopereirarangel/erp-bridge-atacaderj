# Roteiro — Implantar o detector de ruptura de SALÃO neste PC-ponte

> **Para o Claude Code rodando no PC-ponte (DESKTOP-3BLTBIV).** Missão: colocar o
> `detector-ruptura-atacaderj` para rodar NESTE PC com dados reais do bridge,
> em **dry-run**, agendado às 05:30 (seg–sáb). Design aprovado:
> `docs/superpowers/specs/2026-07-11-detector-salao-dados-reais-design.md`.
> Regras do `CLAUDE.md` valem: banco só leitura; senha/telefone/custo/preço
> NUNCA no git; atualizar `STATUS.md` + commit + push ao avançar.

## O que já está pronto (não refazer)

- O bridge já roda agendado aqui e a tarefa **Movimentos 05:00** já gera
  `saida\detector-salao\vendas.csv` (+ `recebimentos.csv`) reais todo dia.
- A projeção do salão e a escrita atômica já existem no código.
- Em dry-run o detector NÃO precisa de WhatsApp nem de Apps Script
  (`sendReport` imprime e retorna; `pushRound`/`pullMarks` falham com aviso e
  o fluxo segue — comportamento esperado nesta fase).
- O relatório HTML novo será desenvolvido na máquina de dev e chega depois por
  `git pull` no repo do detector — nada a fazer aqui sobre isso.

## Passos

### 1. Atualizar este repo

```powershell
cd C:\Users\User\erp-bridge-atacaderj
git pull
```

### 2. Clonar o detector (repo PRIVADO — pode pedir autenticação)

```powershell
git ls-remote https://github.com/Rodrigopereirarangel/detector-ruptura-atacaderj.git
```

- Se **negar acesso** (o token deste PC historicamente só alcança o
  `erp-bridge`): peça ao usuário para autenticar — o caminho mais simples é
  `gh auth login` (browser) ou um PAT com acesso ao repo. NÃO invente
  credencial; pergunte.
- Com acesso OK:

```powershell
git clone https://github.com/Rodrigopereirarangel/detector-ruptura-atacaderj.git C:\Users\User\detector-ruptura-atacaderj
cd C:\Users\User\detector-ruptura-atacaderj
node -v    # precisa ser >= 18 (Node já existe neste PC p/ o envio da auditoria)
npm install
npm test   # precisa ficar verde antes de seguir
```

### 3. Config do detector (dry-run)

```powershell
copy config.example.json config.local.json
```

Em `config.local.json` deixe **`"dryRun": true`** (é o default do example).
`supervisorChatId`, `feedback.appsScriptUrl` e `feedback.token` podem ficar
placeholder nesta fase (go-live é rodada futura). `npm run doctor` vai apontar
o Apps Script pendente — esperado, não bloqueia o dry-run.

### 4. Apontar o bridge para o detector (1 linha, com backup)

```powershell
cd C:\Users\User\erp-bridge-atacaderj
copy config.local.json config.local.json.bak-2026-07-11
```

Edite **só** a chave `saida.detector_salao_dir` do `config.local.json` para:

```
C:/Users/User/detector-ruptura-atacaderj/data/input
```

Não toque nas outras chaves — este arquivo alimenta 4 tarefas em produção.

### 5. Materializar os dados reais e validar

```powershell
python src\bridge.py --only vendas
python src\bridge.py --only recebimentos
```

Conferir em `C:\Users\User\detector-ruptura-atacaderj\data\input\`:

- `vendas.csv` → cabeçalho `codigo;descricao;data;qtd_vendida`, dezenas de
  milhares de linhas, datas dia a dia da janela.
- `recebimentos.csv` → cabeçalho `codigo;data_ultimo_recebimento;qtd_recebida`,
  UMA linha por código (última entrega).
- Se sobraram arquivos proxy antigos na pasta, os reais devem tê-los
  substituído (mesmos nomes).

Depois, prova de que o resto da ponte segue intacto:

```powershell
python src\bridge.py --only catalogo   # deve terminar OK como sempre
```

### 6. Primeira rodada real do detector (manual)

```powershell
cd C:\Users\User\detector-ruptura-atacaderj
npm run doctor
npm run daily
```

Esperado: mensagem `[DRY-RUN]` impressa com itens suspeitos reais,
`data\rounds\<data>.json` criado, avisos de pushRound/pullMarks ignoráveis.
FALHA de CSV ausente/formato = parar e investigar (não seguir para o passo 7).

### 7. Agendar (PowerShell como Administrador)

```powershell
cd C:\Users\User\detector-ruptura-atacaderj
./scripts/register-daily-task.ps1
```

⚠️ O script usa `(Get-Command node).Source` — confira que resolve um
`node.exe` real (mesma pegadinha do alias da Store que já pegou o python aqui;
se for alias, edite a action da tarefa com o caminho completo do node.exe).

Teste o disparo real da tarefa:

```powershell
schtasks /Run /TN "DetectorRuptura-Diario"
# aguardar e conferir: novo data\rounds\<data>.json (ou log de execução OK)
```

### 8. Fechar a rodada (obrigatório)

No `STATUS.md` deste repo: marcar o item do checklist "Apontar os caminhos de
`saida` para os detectores" como **parcial (salão ✅ / estoque pendente)** e
registrar no Log de progresso (data, o que entrou no ar, onde). Depois:

```powershell
git add -A
git commit -m "deploy: detector de salao no ar em dry-run (dados reais, tarefa 05:30)"
git push
```

**Nunca** commitar: `config.local.json` (dos dois repos), `data/`, senha,
telefone, custo/preço.

## Critérios de aceite (conferir antes de declarar pronto)

- [ ] `vendas.csv` + `recebimentos.csv` REAIS no `data\input` do detector,
      gerados pelo bridge (não copiados na mão).
- [ ] `npm run daily` dry-run roda com dados reais e salva a rodada.
- [ ] Tarefa `DetectorRuptura-Diario` registrada (05:30 seg–sáb) e testada
      via `schtasks /Run`.
- [ ] Tarefas antigas do bridge intocadas (Catálogo/Movimentos/Auditoria/robô).
- [ ] `STATUS.md` atualizado + push feito.
