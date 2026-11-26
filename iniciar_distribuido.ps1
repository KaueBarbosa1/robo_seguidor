param(
    [ValidateSet('simulacao-embarcada','simulacao-distribuida','monitoramento','distribuido-real')]
    [string]$Perfil='simulacao-embarcada',
    [int]$Porta=8780,
    [string]$Historico='',
    [string]$Servidor='',
    [double]$InferenciaHz=5,
    [double]$ImagensFPS=5,
    [double]$CameraFPS=30,
    [double]$TelemetriaHz=10,
    [double]$TimeoutResultado=0.3,
    [double]$TimeoutComando=0.3,
    [double]$Heartbeat=0.15,
    [double]$VelocidadeMaxPPS=4,
    [string]$ValidacaoFisica='',
    [switch]$SemAbrir
)
$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
    $pythonDistribuido=if(Test-Path -LiteralPath '.venv/Scripts/python.exe'){Join-Path $PSScriptRoot '.venv/Scripts/python.exe'}else{'python'}
    $parametrosDistribuidos=@('tools/gemeo_digital.py','--central','--etapa6','--perfil',$Perfil,'--porta',$Porta,
        '--inferencia-hz',$InferenciaHz.ToString([cultureinfo]::InvariantCulture),
        '--imagens-fps',$ImagensFPS.ToString([cultureinfo]::InvariantCulture),
        '--camera-fps',$CameraFPS.ToString([cultureinfo]::InvariantCulture),
        '--telemetria-hz',$TelemetriaHz.ToString([cultureinfo]::InvariantCulture),
        '--resultado-timeout',$TimeoutResultado.ToString([cultureinfo]::InvariantCulture),
        '--comando-timeout',$TimeoutComando.ToString([cultureinfo]::InvariantCulture),
        '--heartbeat-operacao',$Heartbeat.ToString([cultureinfo]::InvariantCulture),
        '--controle-max-pps',$VelocidadeMaxPPS.ToString([cultureinfo]::InvariantCulture))
    if($Historico){$parametrosDistribuidos+=@('--historico',$Historico)}
    if($Servidor){$parametrosDistribuidos+=@('--servidor',$Servidor)}
    if($ValidacaoFisica){$parametrosDistribuidos+=@('--validacao-fisica',$ValidacaoFisica)}
    if($SemAbrir){$parametrosDistribuidos+='--sem-abrir'}
    & $pythonDistribuido @parametrosDistribuidos
    if($LASTEXITCODE -ne 0){throw 'A central distribuída foi encerrada com erro.'}
} finally {Pop-Location}
