# Registra as 2 tarefas agendadas (Windows Task Scheduler).
# Rode em PowerShell (Admin), dentro da pasta do repo:  ./scripts/register-tasks.ps1
# Requer que o PC esteja ligado nos horarios (marque "Despertar" se ele dorme).

$ErrorActionPreference = "Stop"
$raiz   = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python).Source
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

Write-Host "`nPronto. Veja em Agendador de Tarefas. Teste manual: python `"$bridge`" --demo"
