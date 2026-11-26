# Resultados observados — Etapa 7

Data local:26/11/2026. Origem das medições: Windows11, Python3.13.2, CPU Intel64
Family6 Model142 Stepping12,8 processadores lógicos,8.415.662.080 bytes de RAM.
Não são resultados da Raspberry Pi. Sem acesso ao carrinho ou medições de pista.
Os manifestos registram o commit-base `ab01861` e árvore modificada durante o
desenvolvimento. Estes ensaios verificam o software; não constituem estudo
confirmatório em ambiente controlado. Nenhuma hipótese H1–H8 foi confirmada.

## Testes automatizados

| Execução | Resultado real | Escopo / limite |
|---|---|---|
| Linha de base ampla |469 aprovados,13 falhas,1 skip,56 subtestes;154,17s | PTY integral não coletado no Windows; falhas Linux/BlueZ/mocks/legado identificadas |
| Suíte ampla após correções |478 aprovados,1 falha,13 skips,56 subtestes;139,80s | `dados_experimentos/testes_entrega`; antes dos quatro casos adicionais de timeout/recuperação/CSV/API |
| Integração dirigida |114 aprovados;56,85s | Experimentos, armazenamento, benchmark, central e distribuído |
| Persistência e benchmark após ajuste de confirmação |55 aprovados;23,60s | Encerramento, migração/backup e worker de métricas |
| Novos casos e API |26 aprovados;33,12s na repetição final | Inclui timeout sem cancelar pedido, execução órfã sem fim inventado, CSV científico e CSRF/real bloqueado |
| Canal operacional após tratar fechamento normal |46 aprovados;7,74s | Revogação e validade preservadas, fechamento WebSocket sem traceback espúrio |
| JavaScript final |19 aprovados |7 testes de núcleo,3 controle,5 gêmeo,4 experimentos/inicialização |
| Firmware host C++ |TUDO_OK, falhas=0 | g++/Arduino falso; não é compilação AVR, upload ou ensaio elétrico |

Falha remanescente: `tests/test_aprendizado.py::test_ciclo_completo_sintetico`
não promove um campeão com o cenário/configuração atual. Não foi removida,
marcada como aprovação ou contornada relaxando critérios. `todos` retorna1
por essa falha; CI pode ficar vermelha. Testes rápidos podem não incluir esse
ensaio lento, e isso é explicitamente uma seleção, não toda a suíte aprovada.

Skips: shell Wi-Fi/PTY requerem Linux; BlueZ/D-Bus requer dependências específicas;
o motivo de cada caso está no XML/log. O roteiro PTY com execução ao importar
é mantido e executado isoladamente pelo runner no Linux. Sem cobertura de código
anunciada, sem teste físico certificado. Sintaxe Python/JS/PowerShell e diff
também verificados. `pip check` acusou conflito global giddy/esda alheio ao projeto.

## Vinte repetições de percepção A–D

Experimento:`1ed5ff70-99cf-45fb-97de-7a6d329c3b11`.
Cinco repetições por configuração,5s de coleta cada,1s de aquecimento, ordem
aleatória em blocos,seed7. Mesma imagem sintética JPEG480×640,telemetria10Hz,
transmissão5FPS,inferência alvo5Hz,sem movimento. As20 execuções ficaram
`concluida`, com sessões distintas. Parte do ensaio coincidiu com testes no PC;
isso limita comparações de desempenho e está registrado como limitação.

| Configuração virtual | Repetições | Processamento total médio por imagem (ms) | Rotina de inferência/agregada (ms) | Ciclo de retorno médio (ms) | Controle médio (Hz) |
|---|---:|---:|---:|---:|---:|
| A OpenCV local |5|5,882|5,859|indisponível / não aplicável|19,658|
| B CNN local diagnóstica |5|2,049|0,974|indisponível / não aplicável|19,771|
| C OpenCV remoto |5|5,613|5,597|68,795|19,781|
| D CNN remota diagnóstica |5|1,709|0,982|78,958|19,717|

As tabelas agregam **uma média por execução**, não todos os frames como
repetições independentes. A rotina OpenCV inclui detecção agregada; a inferência
CNN corresponde ao forward depois do seu pré-processamento, por isso existe
a coluna de processamento total. Saídas/ROI dos algoritmos têm semânticas
diferentes; esses tempos não comparam precisão nem provam superioridade física.
CPU/RAM são do processo inteiro no PC, não uma Pi isolada. R²/MAE não se aplicam
a esta imagem sintética sem rótulo humano de avaliação de pista.

Tabela numérica e boxplot por execução:
`dados_experimentos/entrega/comparacao_A_D.json`,
`comparacao_inferencia.png` e `.svg`.
Exemplo completo de relatório D, repetição5:
`<raiz_historico>/experimentos/7b5fb9e5-63c6-4f37-a272-fb11dda7153f/`.
Contém amostras.csv,metricas.csv,relatorio.md/html/json/zip e gráficos PNG/SVG.

## Carga integrada de cinco minutos

Experimento:`30cd647d-ecc5-4300-8c1e-293acb0dc9d9`.
Execução:`2d676a17-699f-449c-aa87-234df41e20a4`.
OpenCV remoto virtual, JPEG fixo480×640,30Hz de telemetria,15FPS de transmissão,
inferência alvo10Hz, gravação JPEG e consultas simultâneas. Dashboard/gêmeo
abertos; navegação das páginas ocorreu durante parte da coleta. Nenhuma referência
de movimento foi habilitada. Duração de coleta **300,212s**,2630 linhas de CSV.

| Métrica observada | Resultado | Definição / limite |
|---|---:|---|
| Processamento OpenCV |16,566ms média|2439 frames distintos amostrados; p95=51,398ms |
| Ciclo Pi virtual→PC→Pi virtual |137,723ms média|mediana136,426ms;p95=204,789ms;p99=241,622ms;n=2439 |
| CPU do processo PC |110,799% média|292 amostras; soma núcleos, pode superar100%; não é CPU da Pi |
| RSS do processo PC |69,21–95,08MiB|faixa observada, não prova ausência/presença de vazamento |
| Controle efetivo |19,187Hz média|estimativas periódicas amostradas; mínimo15,731Hz; alvo20Hz não garantido |
| Mediana corrente de RTT amostrada |4,370ms média|não é média de sondas independentes nem latência unilateral |
| Consulta local de sessões |42,403ms média|286 consultas; p95=85,904ms; leitura na base existente |
| Telemetrias persistidas |7202|sem duplicadas/falhas SQLite observadas pelo gravador |
| JPEGs persistidos |2917|626 descartes na fila de imagens durante a gravação;265 descartes por política |
| Integridade SQLite |ok|`PRAGMA integrity_check`; `foreign_key_check` vazio |

O processamento e as filas continuam limitados; houve descarte intencional sob
carga, portanto não há alegação de perda zero. Os contadores cumulativos do
serviço incluem aquecimento/intervalos anteriores e, nessa execução, o período
de checagem posterior; não dividi-los por300s para inventar FPS de coleta.
O CSV registra a janela de coleta. Os contadores fora de gravação não são perda
de mensagens da rede. A base existente tinha aproximadamente1,00GiB ao final,
incluindo dados anteriores; esse tamanho não é o crescimento exclusivo deste ensaio.

A verificação integral da base demorou além dos cinco minutos e é posterior
à coleta, não latência de inferência/controle. Foi preparado um estado explícito
de finalização e sua duração para execuções futuras. O último estado confirmado
é **gravação inativa, operação parada e autorização ausente**.

Uma tentativa anterior,`e4693865-f21f-4c9d-8000-fd57b4bea05e`, produziu300s de
CSV mas falhou ao confirmar o encerramento. Seu estado ficou falha/recuperado,
sem resultado final inventado. O prazo de confirmação da drenagem e a persistência
de evidência parcial foram corrigidos; timeout não significa cancelamento da
transação. Essa tentativa não integra as execuções aprovadas.

15/30/60min permanecem **configuráveis, não executados**. Não extrapolar5min
para afirmar estabilidade de uma hora.

## Reavaliação offline da CNN própria

Pesos CNN02 originais:hash`c3a865f28c9de7ff`,55.090 parâmetros,entrada1×40×80.
Snapshot de rótulos/metadados e hashes de imagens conferidos; diferenças CRLF/LF
foram registradas.77 imagens utilizadas das87 revisadas;58/10/9 por conjunto,
divisão por vídeos,sem sobreposição de vídeo ou hash entre grupos.

| Conjunto | Frames | MAE | MSE | RMSE | R² | Máximo absoluto |
|---|---:|---:|---:|---:|---:|---:|
| Treino |58|0,034922|0,001979|0,044488|0,984292|0,108870|
| Validação |10|0,102605|0,014566|0,120689|0,836299|0,204362|
| Teste |9|0,072481|0,009623|0,098097|0,898966|0,246231|

Unidade: posição normalizada na largura da imagem; **não centímetros** e não
acurácia de classificação. A avaliação reproduz os pesos existentes, não houve
novo treinamento, promoção ou ajuste. Teste de dois vídeos do mesmo ambiente,
já explorado anteriormente; não é evidência definitiva de generalização.
Visibilidade não foi supervisionada; navegação pela CNN continua bloqueada.

Mesmo conjunto usado para velocidade OpenCV/CNN. Na passagem observada no PC:
decode médio21,377ms,pré-processamento CNN3,263ms,forward1,597ms,totalCNN4,944ms,
OpenCV agregado38,364ms. Resolução original variável e apenas uma passagem por
frame; valores não são comparáveis diretamente aos ensaios JPEG fixo A–D.
Fração de frames com detecção OpenCV=0,64935 não é acurácia nem ground truth.
Robustez estratificada por sombra/curva/iluminação ainda depende de rótulos adequados.

Artefatos:`dados_experimentos/visao_reavaliada/{avaliacao.json,predicoes.csv,
regressao_cnn.png,regressao_cnn.svg,historico_original.png,historico_original.svg}`.
O histórico original foi lido do treino existente, não recriado artificialmente.

## Interface, GLB e pendências

As15 páginas foram navegadas e seus títulos conferidos. Console sem erros/warnings
na verificação final. Evidência em `dados_experimentos/interface/paginas.json` e
capturas JPEG. A inicialização antes da primeira telemetria mantém indisponíveis,
sem exception nem zero fictício. Formulários científicos são vinculados antes
de consultas assíncronas; filtros/reports/export/replay reutilizam os serviços.
Exportações SVG e PNG foram baixadas pelo navegador em Downloads como
`robo_grafico-ciencia.svg` e `.png`. Relatório gerado pela interface com quatro
gráficos e links de CSV/ZIP. Reprodução confirmou sessão histórica carregada e
pausada; em seguida a fonte voltou à simulação parada. Responsividade: viewport
1440px com conteúdo1425px e móvel390px com conteúdo375px, sem overflow horizontal.

Diagnóstico do renderer:13 verificações estruturais aprovadas,sem erros,
313 nós/37 materiais originais,363 objetos/143.594 triângulos no renderer,
carga133,5ms,600 amostras finais,custoCPU médio6,3625ms,60FPS informados,
memóriaJS41.780.260bytes. Viewport de diagnóstico360×598. CustoCPU de submissão
não é tempo GPU nem latência física; fidelidade de pivôs/sentidos/escala aguarda
comparação com o carrinho. O hash do GLB original permanece preservado.

Pendências: hardware Pi/Uno/ESP e pista; calibração/ground truth; respostaPI/PD
e frenagem; CNN320×240/validade supervisionada; checkpointsRL; GPU/energia;
carga≥15min e execução do workflow no GitHub. O roteiro A–M e a matriz de
aprovação estão nos guias26–28. Nenhum movimento físico, upload ou push realizado.
