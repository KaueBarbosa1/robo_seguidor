param([Parameter(Mandatory=$true)][string]$Servidor, [string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$raizProjeto = Split-Path -Parent $PSScriptRoot
if (-not $env:ROBO_REDE_TOKEN) { throw 'Defina ROBO_REDE_TOKEN igual ao do servidor.' }
& $Python (Join-Path $raizProjeto 'tools/rede_cliente.py') --servidor $Servidor
