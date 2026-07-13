# Executar uma vez, em PowerShell como Administrador, na pasta do repo erp-bridge.
$node = (Get-Command node.exe -ErrorAction SilentlyContinue | Where-Object { $_.Source -notmatch "WindowsApps" } | Select-Object -First 1).Source
if (-not $node) { throw "node.exe real nao encontrado" }
$wa = Join-Path (Get-Location).Path "scripts\whatsapp"
$det = "C:\Users\User\detector-ruptura-atacaderj"
$a1 = New-ScheduledTaskAction -Execute $node -Argument "colher-marcas.mjs" -WorkingDirectory $wa
$a2 = New-ScheduledTaskAction -Execute $node -Argument "src/dashboard.js" -WorkingDirectory $det
$t1 = New-ScheduledTaskTrigger -Daily -At 5:20am
$t2 = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)
$s = New-ScheduledTaskSettingsSet -StartWhenAvailable
Register-ScheduledTask -TaskName "AtacadeRJ - Colher Marcas" -Action @($a1, $a2) -Trigger @($t1, $t2) -Settings $s -Description "Colhe marcacoes A/RA/RC do WhatsApp e regenera o dashboard" -Force
Write-Host "Tarefa de colheita registrada (05:20 + a cada 60 min)."
