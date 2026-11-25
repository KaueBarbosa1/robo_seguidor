$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
    $pythonCentral=if(Test-Path -LiteralPath '.venv/Scripts/python.exe'){Join-Path $PSScriptRoot '.venv/Scripts/python.exe'}else{'python'}
    & $pythonCentral -m pip install -r requirements-gemeo-pc.txt
    if($LASTEXITCODE -ne 0){throw 'Falha nas dependências Python'}
    & npm.cmd ci --prefix gemeo_digital/frontend
    if($LASTEXITCODE -ne 0){throw 'Falha nas dependências Three.js'}
    Write-Output 'Instalação concluída. Execute .\iniciar_central.ps1'
} finally {Pop-Location}
