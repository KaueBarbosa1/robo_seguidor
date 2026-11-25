param([int]$Porta=8780,[string]$Historico='',[string]$Servidor='',[switch]$SemAbrir)
$parametrosCentral=@{Central=$true;Porta=$Porta;Historico=$Historico;Servidor=$Servidor;SemAbrir=$SemAbrir}
& (Join-Path $PSScriptRoot 'iniciar_gemeo.ps1') @parametrosCentral
