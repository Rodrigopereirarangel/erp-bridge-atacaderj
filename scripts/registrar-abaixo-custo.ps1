# Executar uma vez, em PowerShell como Administrador, na pasta do repo erp-bridge.
# Registra a tarefa "AtacadeRJ - Abaixo do Custo": roda src/abaixo_custo.py todo
# dia as 06:00, com retry a cada 30 min ate 12:00 (atraso de sync do ERP nas
# manhas — o guarda de "zero vendas no dia" do proprio script sai calado nos
# retries ate os dados chegarem). Idempotencia entre retries: o carimbo
# saida/abaixo-custo/enviado-<dia>.txt (o proprio abaixo_custo.py cuida disso).
#
# Teste manual (sem esperar o gatilho): powershell -File scripts\registrar-abaixo-custo.ps1
$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot

# Task Scheduler roda sem o PATH do usuario; o alias 'python' da Microsoft
# Store tambem engana o Get-Command (mesmo problema de auditoria-16h.ps1 /
# register-tasks.ps1) — resolver o executavel real:
$python = @(
  "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
  "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
  "C:\Python312\python.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) { $python = (Get-Command python).Source }

$script = Join-Path $raiz "src\abaixo_custo.py"
$acao = New-ScheduledTaskAction -Execute $python -Argument "`"$script`"" -WorkingDirectory $raiz
$gatilho = New-ScheduledTaskTrigger -Daily -At 06:00 `
  -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Hours 6)
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable

Register-ScheduledTask -TaskName "AtacadeRJ - Abaixo do Custo" -Action $acao -Trigger $gatilho `
  -Settings $config -RunLevel Limited -Force `
  -Description "Relatorio diario (06:00, retry a cada 30 min ate 12:00) dos itens vendidos abaixo do custo, via WhatsApp" `
  | Out-Null
Write-Host "OK: 'AtacadeRJ - Abaixo do Custo' registrada (06:00, repete a cada 30 min por 6h ate 12:00)."
Write-Host "Antes do 1o envio real: preencher abaixo_custo.numero em config.local.json e validar com --dry-run."
