# Execucao mensal dos robos de extratos.
# O Agendador de Tarefas chama este arquivo TODO DIA as 13:00. Ele so roda os robos uma vez por mes:
# no primeiro dia do mes em que a maquina estiver ligada as 13:00 (dia 1; se for feriado/fim de semana
# e a maquina estiver desligada, roda no proximo dia em que ela estiver ligada as 13:00).
# Os robos rodam um por vez, cada um na sua janela (que fica aberta no fim com o relatorio).
# Se a maquina for desligada no meio, no proximo dia roda so os robos que faltaram naquele mes.
param([switch]$Agora)   # -Agora: ignora o controle do mes (para testar)

$ErrorActionPreference = "Continue"
$raiz = $PSScriptRoot
$estado = Join-Path $raiz "execucao_mensal.json"
$logArq = Join-Path $raiz "execucao_mensal_log.txt"
$mes = Get-Date -Format "yyyy-MM"
$bancos = @("santander", "bradesco", "caixa", "itau", "sicredi")

function Log($txt) {
    $linha = "{0}  {1}" -f (Get-Date -Format "dd/MM/yyyy HH:mm:ss"), $txt
    Add-Content -Path $logArq -Value $linha -Encoding UTF8
    Write-Host $linha
}

$relatorioEnviado = $false
function Salvar($feitos) {
    @{ mes = $mes; feitos = @($feitos); relatorio = $relatorioEnviado } | ConvertTo-Json |
        Set-Content -Path $estado -Encoding UTF8
}

$feitos = @()
if (Test-Path $estado) {
    try {
        $e = Get-Content $estado -Raw | ConvertFrom-Json
        if ($e.mes -eq $mes) {
            $feitos = @($e.feitos)
            # estado antigo (sem o campo): mes ja feito antes do relatorio geral existir -> nao envia
            $relatorioEnviado = if ($null -eq $e.relatorio) { $true } else { [bool]$e.relatorio }
        }
    } catch { }
}
if ($Agora) { $feitos = @(); $relatorioEnviado = $false }
$faltam = @($bancos | Where-Object { $feitos -notcontains $_ })
if ($faltam.Count -eq 0 -and $relatorioEnviado) { exit 0 }      # este mes ja foi executado

if ($faltam.Count) { Log "=== Execucao mensal $mes - robos: $($faltam -join ', ')" }
foreach ($b in $faltam) {
    $pasta = Join-Path $raiz $b
    $exe = Join-Path $pasta "$b.exe"
    if (-not (Test-Path $exe)) {
        Log "$b : NAO ENCONTRADO ($exe) - pulado"
        continue
    }
    Log "$b : iniciando"
    # janela classica propria (conhost) que continua aberta no fim (o relatorio da execucao fica visivel)
    # abre já na pasta dos robôs e usa só nomes curtos (sem aspas): o caminho completo pode ter espaço
    Start-Process -FilePath "conhost.exe" -WorkingDirectory $raiz -ArgumentList "cmd.exe /k .\rodar_robo.bat $b.exe $b --todas"
    # espera o robo comecar e depois terminar
    $inicio = Get-Date
    $robo = $null
    while (-not $robo -and ((Get-Date) - $inicio).TotalSeconds -lt 120) {
        Start-Sleep -Seconds 3
        $robo = Get-Process -Name $b -ErrorAction SilentlyContinue | Select-Object -First 1
    }
    if (-not $robo) {
        Log "$b : NAO INICIOU (a janela do robo nao abriu o programa) - fica para a proxima execucao"
        continue
    }
    while (Get-Process -Id $robo.Id -ErrorAction SilentlyContinue) { Start-Sleep -Seconds 10 }
    $min = [int]((Get-Date) - $inicio).TotalMinutes
    Log "$b : terminou ($min min)"
    $feitos += $b
    Salvar $feitos
}

# Relatorio geral do mes (todos os bancos) + e-mail para a equipe: uma vez, quando nenhum robo existente faltar
$aindaFaltam = @($bancos | Where-Object { $feitos -notcontains $_ -and (Test-Path (Join-Path $raiz "$_\$_.exe")) })
if ($aindaFaltam.Count -eq 0 -and -not $relatorioEnviado) {
    $sant = Join-Path $raiz "santander\santander.exe"
    Log "relatorio geral: gerando e enviando por e-mail"
    Start-Process -FilePath "conhost.exe" -WorkingDirectory $raiz `
        -ArgumentList "cmd.exe /k .\rodar_robo.bat santander.exe santander --relatorio-geral"
    Start-Sleep -Seconds 5
    while (Get-Process -Name "santander" -ErrorAction SilentlyContinue) { Start-Sleep -Seconds 5 }
    $relatorioEnviado = $true
    Salvar $feitos
    Log "relatorio geral: concluido (ver a janela / o e-mail)"
}
Log "=== Execucao mensal $mes concluida. Pendencias: ver o relatorio geral e o 'Relatorio de envios de extratos' de cada empresa no BPO."
