@echo off
rem Cria a tarefa "Robos extratos - mensal" no Agendador de Tarefas do Windows (usuario atual, todo dia 13:00).
rem O mes atual fica marcado como ja executado: a primeira execucao automatica sera no dia 1 do proximo mes.
rem Rodar com o usuario que vai ficar conectado na maquina (nao precisa de administrador).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ps1 = Join-Path '%~dp0' 'executar_mensal.ps1';" ^
  "$acao = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Minimized -File \"' + $ps1 + '\"') -WorkingDirectory '%~dp0';" ^
  "$gatilho = New-ScheduledTaskTrigger -Daily -At '13:00';" ^
  "$config = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 12) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew;" ^
  "$config.StartWhenAvailable = $false;" ^
  "$quem = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive;" ^
  "Register-ScheduledTask -TaskName 'Robos extratos - mensal' -Action $acao -Trigger $gatilho -Settings $config -Principal $quem -Force | Out-Null;" ^
  "@{ mes = (Get-Date -Format 'yyyy-MM'); feitos = @('santander','bradesco','caixa','itau','sicredi'); relatorio = $true } | ConvertTo-Json | Set-Content -Path (Join-Path '%~dp0' 'execucao_mensal.json') -Encoding UTF8;" ^
  "Write-Host 'Agendamento criado: todo dia as 13:00 (roda os robos uma vez por mes, no primeiro dia em que a maquina estiver ligada).'"
pause
