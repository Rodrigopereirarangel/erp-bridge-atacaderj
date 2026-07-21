# Registra as 2 tarefas do Painel de Compras (Windows Task Scheduler).
# Rode em PowerShell (Admin), dentro da pasta do repo: ./scripts/register-painel-tasks.ps1
# Geracao: 06:00 (apos bridge 05:00 + detector 05:30) e ~10min apos cada
# rodada de catalogo (08/12/15/18h). Servidor HTTP: como SYSTEM, no BOOT,
# SEM janela — em 20/07 o servidor rodava na sessao interativa, abria console
# preto e alguem na loja fechou a janela (exit 0xC000013A = CTRL_C). Como
# SYSTEM nao ha janela para fechar, nao depende de logon e sobrevive a
# logoff; auto-reinicia em falha.

$ErrorActionPreference = "Stop"
$raiz   = Split-Path -Parent $PSScriptRoot
# nao usar (Get-Command python): o alias da Microsoft Store engana e o Task
# Scheduler roda sem o PATH do usuario - apontar para o exe real
$python = @(
  "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
  "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
  "C:\Python312\python.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) { $python = (Get-Command python).Source }
$bridge = Join-Path $raiz "src\bridge.py"

$cfg = Get-Content (Join-Path $raiz "config.local.json") -Raw | ConvertFrom-Json
if (-not $cfg.painel) { throw "config.local.json sem a secao 'painel' - copie do config.example.json" }
$dir   = $cfg.painel.dir_saida
$porta = $cfg.painel.porta_http
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }

# --- Tarefa 1: GERACAO do painel ---
$acaoGer = New-ScheduledTaskAction -Execute $python -Argument "`"$bridge`" --only painel"
$gatGer  = @(
  New-ScheduledTaskTrigger -Daily -At 06:00
  New-ScheduledTaskTrigger -Daily -At 08:10
  New-ScheduledTaskTrigger -Daily -At 12:10
  New-ScheduledTaskTrigger -Daily -At 15:10
  New-ScheduledTaskTrigger -Daily -At 18:10
)
Register-ScheduledTask -TaskName "AtacadeRJ - Painel Compras" -Action $acaoGer `
  -Trigger $gatGer -RunLevel Limited -Force | Out-Null
Write-Host "OK: 'AtacadeRJ - Painel Compras' (06:00/08:10/12:10/15:10/18:10)"

# --- Tarefa 2: SERVIDOR HTTP (rede local) ---

# libera a porta na rede local (sem isso o listener iniciado pelo Agendador
# fica bloqueado para os outros PCs e a TV — e o prompt do Windows nunca
# aparece numa sessao que ninguem esta olhando)
if (-not (Get-NetFirewallRule -DisplayName "AtacadeRJ Painel Compras" -ErrorAction SilentlyContinue)) {
  New-NetFirewallRule -DisplayName "AtacadeRJ Painel Compras" -Direction Inbound `
    -Protocol TCP -LocalPort $porta -Profile Private,Domain -Action Allow | Out-Null
  Write-Host "OK: regra de firewall (TCP $porta, Private/Domain)"
}

$acaoSrv = New-ScheduledTaskAction -Execute $python `
  -Argument "-m http.server $porta --directory `"$dir`" --bind 0.0.0.0"
$gatSrv = New-ScheduledTaskTrigger -AtStartup
$setSrv = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "AtacadeRJ - Painel Compras Servidor" `
  -Action $acaoSrv -Trigger $gatSrv -Settings $setSrv `
  -User "SYSTEM" -RunLevel Highest -Force | Out-Null
Start-ScheduledTask -TaskName "AtacadeRJ - Painel Compras Servidor"
Write-Host "OK: 'AtacadeRJ - Painel Compras Servidor' (SYSTEM, boot, sem janela; ja iniciado)"
Write-Host "`nPainel: http://<ip-do-ponte>:$porta/  (TV: acrescente #tv)"
