param(
 [ValidateSet('central','testes','experimento','visao','relatorio','instalar')][string]$Acao='central',
 [string]$Categoria='rapidos', [string]$Config='experimentos/configuracoes/comparacao_pc.json',
 [string]$Historico='', [string]$Servidor='', [string]$ValidacaoFisica='', [string]$Id='', [string]$Saida='dados_experimentos/visao',
 [ValidateSet('simulacao-embarcada','simulacao-distribuida','monitoramento','distribuido-real')][string]$Perfil='simulacao-embarcada',
 [int]$Porta=8780, [switch]$SemAbrir
)
$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
 $pythonProjeto=if(Test-Path -LiteralPath '.venv/Scripts/python.exe'){Join-Path $PSScriptRoot '.venv/Scripts/python.exe'}else{'python'}
 if($Acao -eq 'central'){
  $parametrosProjeto=@{Perfil=$Perfil;Porta=$Porta;SemAbrir=$SemAbrir}
  if($Historico){$parametrosProjeto.Historico=$Historico}
  if($Servidor){$parametrosProjeto.Servidor=$Servidor}
  if($ValidacaoFisica){$parametrosProjeto.ValidacaoFisica=$ValidacaoFisica}
  & "$PSScriptRoot/iniciar_distribuido.ps1" @parametrosProjeto
 } elseif($Acao -eq 'instalar'){
  & "$PSScriptRoot/instalar_central.ps1"
 } elseif($Acao -eq 'testes') {& $pythonProjeto tools/testes.py $Categoria}
 else {
  $argsProjeto=@('tools/experimentos.py')
  if($Acao -eq 'experimento'){$argsProjeto+=@('executar',$Config)}
  if($Acao -eq 'visao'){$argsProjeto+=@('visao','--saida',$Saida)}
  if($Acao -eq 'relatorio'){$argsProjeto+=@('relatorio',$Id)}
  if($Historico -and $Acao -ne 'visao'){$argsProjeto+=@('--historico',$Historico)}
  & $pythonProjeto @argsProjeto
 }
 if($LASTEXITCODE -ne 0){throw 'A execução terminou com falha; consulte o relatório.'}
} finally {Pop-Location}
