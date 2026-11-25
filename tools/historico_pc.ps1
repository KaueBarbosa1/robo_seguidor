param([Parameter(Mandatory=$true)][string]$Servidor,[string]$Python='python',[switch]$Automatico)
$ErrorActionPreference='Stop'
$raizProjeto=Split-Path -Parent $PSScriptRoot
if (-not $env:ROBO_REDE_TOKEN) { throw 'Defina ROBO_REDE_TOKEN igual ao servidor.' }
$argumentos=@((Join-Path $raizProjeto 'tools/historico.py'),'gravar','--servidor',$Servidor)
if ($Automatico) { $argumentos+='--automatico' }
& $Python @argumentos
