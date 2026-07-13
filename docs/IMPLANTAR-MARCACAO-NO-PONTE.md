# Roteiro — Implantar o ciclo de MARCAÇÃO do operador neste PC-ponte

> **Para o Claude Code rodando no PC-ponte (DESKTOP-3BLTBIV).** Missão: colocar
> no ar o ciclo relatório-com-botões → marcações voltam por WhatsApp → colhedor
> grava → treino semanal aprende. Código já pronto e pushado nos dois repos
> (spec: `detector/docs/superpowers/specs/2026-07-13-marcacao-operador-whatsapp-design.md`).
> Regras do `CLAUDE.md` valem. **O envio diário do relatório permanece
> DESLIGADO (`dryRun: true`) — NÃO ativar; é decisão do dono à parte.**

## Passo 0 — AUTENTICAR O GITHUB (o dono faz junto, 2 min)

O token do `gh` neste PC está inválido (login anterior não completou). Peça ao
dono para rodar num PowerShell comum (com navegador aberto):

```powershell
gh auth login -h github.com -p https -w
# copiar o código exibido, colar no navegador, concluir
gh auth setup-git
```

Verifique (os dois têm que passar):

```powershell
gh auth status
cd C:\Users\User\detector-ruptura-atacaderj; git ls-remote origin HEAD
```

Sem isso o detector não puxa (repo privado) e o histórico não pusha. Se o dono
não puder agora: PARE e reporte — não há plano B neste roteiro.

## Passo 1 — Atualizar os dois repos

```powershell
cd C:\Users\User\erp-bridge-atacaderj
# ATENÇÃO: este repo tem WIP local NÃO COMMITADO (ULTIMO_CUSTO) — preservar:
git stash push -m wip; git pull; git stash pop
cd C:\Users\User\detector-ruptura-atacaderj
git pull   # (origin, agora com auth) — esperado: chega no merge c42189d ou depois
npm test   # 136/136 esperado
node --test C:\Users\User\erp-bridge-atacaderj\scripts\whatsapp\testes-marcas-parser.mjs C:\Users\User\erp-bridge-atacaderj\scripts\whatsapp\testes-sessao-lock.mjs   # 7/7
```

## Passo 2 — Configs (in-place, com backup; NUNCA commitar config.local.json)

**Detector** (`C:\Users\User\detector-ruptura-atacaderj\config.local.json`):
1. `whatsapp.numeroPonte = "5521970000786"` (o número do próprio ponte — para
   onde o botão Concluído aponta).
2. **CHECAGEM OBRIGATÓRIA (condição do review final):** `feedback.appsScriptUrl`
   TEM que ser o placeholder `"<URL_APPS_SCRIPT>"` (ou inválido). Se houver uma
   URL real ali, PARE e pergunte ao dono — uma URL viva faria o daily
   sobrescrever as marcações locais com vazio.
3. `dryRun` continua `true`.

**Bridge** (`C:\Users\User\erp-bridge-atacaderj\config.local.json`): adicionar

```json
  "marcas": {
    "feedbackDir": "C:/Users/User/detector-ruptura-atacaderj/data/feedback",
    "remetentes": ["5521970117082"]
  }
```

## Passo 3 — Semear o gabarito do teste de campo (13/07)

Criar `C:\Users\User\detector-ruptura-atacaderj\data\feedback\2026-07-11.json`
com exatamente:

```json
{
  "36011": {"opcao": "reabastecimento", "origem": "campo-2026-07-13"},
  "39868": {"opcao": "reabastecimento", "origem": "campo-2026-07-13"},
  "40821": {"opcao": "reabastecimento", "origem": "campo-2026-07-13"},
  "14576": {"opcao": "falso", "origem": "campo-2026-07-13"},
  "40980": {"opcao": "falso", "origem": "campo-2026-07-13"},
  "40546": {"opcao": "falso", "origem": "campo-2026-07-13"},
  "14652": {"opcao": "falso", "origem": "campo-2026-07-13"},
  "102748": {"opcao": "falso", "origem": "campo-2026-07-13"},
  "33487": {"opcao": "falso", "origem": "campo-2026-07-13"},
  "34645": {"opcao": "falso", "origem": "campo-2026-07-13"},
  "16438": {"opcao": "falso", "origem": "campo-2026-07-13"},
  "319": {"opcao": "falso", "origem": "campo-2026-07-13"},
  "35990": {"opcao": "falso", "origem": "campo-2026-07-13"},
  "40406": {"opcao": "falso", "origem": "campo-2026-07-13"},
  "34648": {"opcao": "falso", "origem": "campo-2026-07-13"},
  "37255": {"opcao": "falso", "origem": "campo-2026-07-13"}
}
```

## Passo 4 — Treino manual (prova o histórico + push automático)

```powershell
cd C:\Users\User\detector-ruptura-atacaderj
python treino\treinar_modelo.py
```

Conferir: `historico\precisao.csv` ganhou a linha `2026-07-11;...` (precisão da
lista ≈ 3/16, modo proxy) e o commit "historico: precisao ..." foi criado E
pushado (auth do Passo 0). `git log --oneline -1` mostra o commit.

## Passo 5 — Daily dry-run (prova os botões)

```powershell
npm run daily
```

Conferir no `data\reports\<ref>.html` gerado: contém `data-tok="RA"` e
`id="concluido"` (botões renderizados — numeroPonte configurado). NADA foi
enviado (`Enviado=false`).

## Passo 6 — Registrar a tarefa de colheita (PowerShell ADMIN)

Rodar o conteúdo de `C:\Users\User\erp-bridge-atacaderj\scripts\registrar-colheita.ps1`
numa janela Admin (se a execution policy bloquear o arquivo, cole o conteúdo
direto no console). Conferir: `schtasks /Query /TN "AtacadeRJ - Colher Marcas"`
→ Pronto (gatilhos: 05:20 diário + a cada 60 min em HH:40).

## Passo 7 — Teste ponta a ponta COM O DONO (condição do review final)

1. Enviar o HTML atual para o celular do dono (envio manual único, autorizado):
   ```powershell
   cd C:\Users\User\erp-bridge-atacaderj\scripts\whatsapp
   node enviar.mjs --para 5521970117082 --texto "Teste de marcacao - abra o arquivo, marque 2 itens e toque Concluido" --arquivo C:\Users\User\detector-ruptura-atacaderj\data\reports\<ref>.html
   ```
2. O dono abre o HTML, marca 1-2 itens, toca **Concluído** e envia a mensagem
   que o WhatsApp abrir.
3. Colher manualmente: `node colher-marcas.mjs`
4. **ASSERT OBRIGATÓRIO:** `data\feedback\<ref>.json` do detector ganhou as
   marcações do dono. Se NÃO gravou: rode o colhedor de novo olhando o log —
   se a mensagem chegou mas foi filtrada, reporte o remoteJid exato (pode ser
   variação de número; a allowlist compara os últimos 8 dígitos, então
   investigue antes de mexer).
5. Regenerar o dashboard: `cd C:\Users\User\detector-ruptura-atacaderj && node src\dashboard.js` — abrir `data\dashboard\index.html` e conferir que as marcações aparecem.

## Passo 8 — Fechar

`STATUS.md` deste repo: marcar no checklist + linha no Log ("ciclo de marcação
no ar: colheita agendada, gabarito semeado, E2E ok, treino domingos com
histórico versionado"). `git add -A && git commit && git push`. NÃO commitar
config.local.json nem `data/` de nenhum repo.

## O que NÃO fazer

- NÃO mudar `dryRun` (o envio diário do relatório é decisão do dono).
- NÃO mexer no WIP não-commitado deste repo (bridge.py/queries.py/demo_data.py).
- NÃO commitar telefone/senha/custo/preço.
