param([string]$Python = 'python', [int]$Porta = 8765)
$ErrorActionPreference = 'Stop'
$raizProjeto = Split-Path -Parent $PSScriptRoot
if (-not $env:ROBO_REDE_TOKEN) { throw 'Defina ROBO_REDE_TOKEN com pelo menos 24 caracteres nos dois terminais.' }
& $Python (Join-Path $raizProjeto 'tools/rede_servidor_simulado.py') --porta $Porta
