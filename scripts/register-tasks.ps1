# Registra as 2 tarefas agendadas (Windows Task Scheduler).
# Rode em PowerShell (Admin), dentro da pasta do repo:  ./scripts/register-tasks.ps1
# Requer que o PC esteja ligado nos horarios (marque "Despertar" se ele dorme).

$ErrorActionPreference = "Stop"
$raiz   = Split-Path -Parent $PSScriptRoot
# nao usar (Get-Command python): o alias da Microsoft Store engana e o Task
# Scheduler roda sem o PATH do usuario — apontar para o exe real
$python = @(
  "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
  "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
  "C:\Python312\python.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) { $python = (Get-Command python).Source }
$bridge = Join-Path $raiz "src\bridge.py"

# --- Tarefa 1: CATALOGO (custo/precos mudam quase diario) — 4x/dia ---
$acaoCat = New-ScheduledTaskAction -Execute $python -Argument "`"$bridge`" --only catalogo"
$gatCat  = @(
  New-ScheduledTaskTrigger -Daily -At 08:00
  New-ScheduledTaskTrigger -Daily -At 12:00
  New-ScheduledTaskTrigger -Daily -At 15:00
  New-ScheduledTaskTrigger -Daily -At 18:00
)
Register-ScheduledTask -TaskName "AtacadeRJ - Bridge Catalogo" -Action $acaoCat `
  -Trigger $gatCat -RunLevel Limited -Force | Out-Null
Write-Host "OK: 'AtacadeRJ - Bridge Catalogo' (08/12/15/18h)"

# --- Tarefa 2: MOVIMENTOS (vendas+recebimentos+pedidos) — 1x/dia, 05:00 ---
# 05:00 para os arquivos estarem prontos antes do detector 'daily' das 05:30.
$acaoMov = New-ScheduledTaskAction -Execute $python -Argument "`"$bridge`" --only movimentos"
$gatMov  = New-ScheduledTaskTrigger -Daily -At 05:00
Register-ScheduledTask -TaskName "AtacadeRJ - Bridge Movimentos" -Action $acaoMov `
  -Trigger $gatMov -RunLevel Limited -Force | Out-Null
Write-Host "OK: 'AtacadeRJ - Bridge Movimentos' (05:00)"

# --- Tarefa 3: AUDITORIA DE DESCONTO -> WhatsApp — 1x/dia, 16:00 ---
# (pedidos fechados do proprio dia; resumo + xlsx para whatsapp.numero_auditoria)
$aud16   = Join-Path $PSScriptRoot "auditoria-16h.ps1"
$acaoAud = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$aud16`""
$gatAud  = New-ScheduledTaskTrigger -Daily -At 16:00
Register-ScheduledTask -TaskName "AtacadeRJ - Auditoria Desconto 16h" -Action $acaoAud `
  -Trigger $gatAud -RunLevel Limited -Force | Out-Null
Write-Host "OK: 'AtacadeRJ - Auditoria Desconto 16h' (16:00 -> WhatsApp)"

Write-Host "`nPronto. Veja em Agendador de Tarefas. Teste manual: python `"$bridge`" --demo"
