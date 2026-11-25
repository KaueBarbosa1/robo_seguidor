param(
    [int]$Porta = 8780,
    [string]$Historico = '',
    [string]$Servidor = '',
    [string]$Calibracao = '',
    [switch]$Gravar,
    [switch]$SemAbrir,
    [switch]$Central
)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $pythonGemeo = if (Test-Path -LiteralPath '.venv/Scripts/python.exe') { Join-Path $PSScriptRoot '.venv/Scripts/python.exe' } else { 'python' }
    & $pythonGemeo -c 'import websockets, cv2, numpy, psutil'
    if ($LASTEXITCODE -ne 0) { throw 'Instale as dependências: python -m pip install -r requirements-gemeo-pc.txt' }
    if (-not (Test-Path -LiteralPath 'gemeo_digital/frontend/node_modules/three/build/three.module.js')) {
        & npm.cmd ci --prefix gemeo_digital/frontend
        if ($LASTEXITCODE -ne 0) { throw 'Não foi possível instalar o Three.js pelo lockfile.' }
    }
    $argumentosGemeo = @('tools/gemeo_digital.py', '--porta', $Porta)
    if ($Historico) { $argumentosGemeo += @('--historico', $Historico) }
    if ($Servidor) { $argumentosGemeo += @('--servidor', $Servidor) }
    if ($Calibracao) { $argumentosGemeo += @('--calibracao', $Calibracao) }
    if ($Gravar) { $argumentosGemeo += '--gravar' }
    if ($SemAbrir) { $argumentosGemeo += '--sem-abrir' }
    if ($Central) { $argumentosGemeo += '--central' }
    & $pythonGemeo @argumentosGemeo
    if ($LASTEXITCODE -ne 0) { throw 'O visualizador foi encerrado com erro.' }
} finally { Pop-Location }
