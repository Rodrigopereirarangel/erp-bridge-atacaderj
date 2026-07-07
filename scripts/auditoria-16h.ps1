# =============================================================================
# auditoria-16h.ps1 — job diario das 16:00 (Task Scheduler):
#   1. atualiza o historico de pedidos de venda/DAV (bridge --only pedidos-venda)
#   2. roda a auditoria de desconto DO DIA (mesmas regras do app; base = menor
#      preco entre atacado/varejo/promocao) -> xlsx + resumo txt
#   3. envia o resumo (texto) + o xlsx para o WhatsApp configurado em
#      config.local.json > whatsapp.numero_auditoria
#
# Pre-requisitos (uma unica vez):
#   - npm install em scripts/whatsapp/  e  node enviar.mjs --login  (escanear QR)
#   - repo do app clonado em C:\Users\User\cotacao-auditoria-atacaderj (+ npm install)
#
# Teste manual:  powershell -File scripts\auditoria-16h.ps1 [-Dia 2026-07-06] [-SemWhatsApp]
# =============================================================================
param(
  [string]$Dia = (Get-Date -Format 'yyyy-MM-dd'),
  [switch]$SemWhatsApp
)
$ErrorActionPreference = 'Stop'
$raiz    = Split-Path -Parent $PSScriptRoot
$appRepo = 'C:\Users\User\cotacao-auditoria-atacaderj'
$log     = Join-Path $raiz 'auditoria_16h.log'

# Task Scheduler roda sem o PATH do usuario; o alias 'python' da Microsoft
# Store tambem engana o Get-Command. Resolver os executaveis de verdade:
$python = @(
  "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
  "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
  'C:\Python312\python.exe'
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) { $python = 'python' }
$node = @(
  "$env:ProgramFiles\nodejs\node.exe",
  "$env:LOCALAPPDATA\Programs\nodejs\node.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $node) { $node = 'node' }
function Log($m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $m" | Tee-Object -FilePath $log -Append }

try {
  Log "== auditoria-16h dia=$Dia =="

  # 1) historico fresco (pedidos fechados, ultimos 7 dias)
  & $python (Join-Path $raiz 'src\bridge.py') --only pedidos-venda
  if ($LASTEXITCODE -ne 0) { throw "bridge --only pedidos-venda falhou ($LASTEXITCODE)" }

  # 2) auditoria do dia (regras do app, via ferramentas/auditoria-calc.mjs)
  & $node (Join-Path $appRepo 'ferramentas\auditoria-diaria.mjs') --dia $Dia
  if ($LASTEXITCODE -ne 0) { throw "auditoria-diaria.mjs falhou ($LASTEXITCODE)" }

  $txt  = Join-Path $raiz "saida\auditoria\auditoria-$Dia.txt"
  $xlsx = Join-Path $raiz "saida\auditoria\auditoria-$Dia.xlsx"

  # 3) WhatsApp
  if ($SemWhatsApp) { Log 'envio pulado (-SemWhatsApp)'; exit 0 }
  $cfg = Get-Content (Join-Path $raiz 'config.local.json') -Raw -Encoding UTF8 | ConvertFrom-Json
  $numero = $cfg.whatsapp.numero_auditoria
  if (-not $numero) { throw 'config.local.json sem whatsapp.numero_auditoria' }

  $argsWpp = @('enviar.mjs', '--para', $numero, '--texto-arquivo', $txt)
  if (Test-Path $xlsx) { $argsWpp += @('--arquivo', $xlsx) }
  Push-Location (Join-Path $raiz 'scripts\whatsapp')
  try { & $node @argsWpp; if ($LASTEXITCODE -ne 0) { throw "enviar.mjs falhou ($LASTEXITCODE)" } }
  finally { Pop-Location }

  Log "OK: auditoria de $Dia enviada para $numero"
} catch {
  Log "ERRO: $($_.Exception.Message)"
  exit 1
}
