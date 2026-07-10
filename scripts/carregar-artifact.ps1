# Carrega o banco de dados num artifact NOVO da cotacao (1 clique, sem depender de sessao do Claude).
# Uso:  ./scripts/carregar-artifact.ps1 [-Link "https://claude.ai/public/artifacts/..."]
# Sem -Link, pede o link no console (cole e Enter). Atualiza robo/config_robo.json e roda o robo.
param([string]$Link)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
$cfgPath = Join-Path $raiz "robo\config_robo.json"

if (-not $Link) { $Link = Read-Host "Cole o link publicado do artifact (claude.ai/public/artifacts/...)" }
if ($Link -notmatch '^https://claude\.ai/public/artifacts/[0-9a-f-]+$') {
  Write-Host "Link invalido: $Link" -ForegroundColor Red
  Write-Host "Tem que ser o link PUBLICADO (botao Publish > Copiar link), nao o link da conversa."
  exit 2
}

$cfg = Get-Content $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
$anterior = $cfg.artifact_url
$cfg.artifact_url = $Link
$cfg | ConvertTo-Json -Depth 5 | Out-File $cfgPath -Encoding utf8
Write-Host "config_robo.json atualizado:"
Write-Host "  antes : $anterior"
Write-Host "  agora : $Link"

$python = @(
  "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
  "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
  "C:\Python312\python.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) { $python = (Get-Command python).Source }

Write-Host "`nRodando o robo (vai abrir uma janela do Chrome — NAO feche, ela se fecha sozinha)..."
& $python (Join-Path $raiz "robo\upload_catalogo.py")
if ($LASTEXITCODE -eq 0) {
  Write-Host "`nOK — banco carregado e conferido no artifact. Pode abrir o link." -ForegroundColor Green
} else {
  Write-Host "`nFALHOU — veja robo\robo_upload.log e robo\ultima_falha.png. As rodadas agendadas vao tentar de novo sozinhas." -ForegroundColor Red
}
exit $LASTEXITCODE
