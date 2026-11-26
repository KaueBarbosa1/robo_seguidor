# Metodologia experimental — Etapa 7

## Escopo e níveis de evidência

N1: funções/algoritmos isolados; N2: integração de módulos; N3: sistema com
dispositivos virtuais; N4: hardware em bancada; N5: percurso físico. Registrar
também `origem` (simulada/real) e `categoria` (benchmark isolado/integrado ou
experimento completo). Imagens reais arquivadas não tornam o benchmark no PC
uma avaliação de hardware Pi. Nunca agrupar níveis/categorias incompatíveis.

## Questões e hipóteses

Todas as hipóteses estão **em investigação**. As nove questões do planejamento
correspondem a recursos, latência, algoritmos, rede, falhas, odometria, gêmeo,
sobrecarga observacional e compromisso desempenho/segurança. Autonomia energética
exige medidor adequado e ensaio de bateria; CPU não fornece watts ou autonomia.

| Hipótese | Independente | Dependentes/métricas | Controles e dados necessários | Procedimento / avaliação / limitações |
|---|---|---|---|---|
| H1 distribuição reduz CPU Pi | local × distribuído | CPU host/processo/núcleos, RSS/RAM, temperatura | Mesma Pi, imagem, taxa, ganho, refrigeração e serviços; CPU medida na Pi | Alternar A/C e B/D; comparar médias por execução. PC virtual não testa H1 |
| H2 CNN PC reduz inferência | hardware executor | tempo de inferência, dispersão, speedup | Mesmos pesos/hash, ROI, frames, lote=1, versões, aquecimento | Reproduzir mesmos frames Pi/PC; inferência isolada não representa latência total |
| H3 rede compensa ganho | arquitetura/taxa | ciclo percepção/retorno, filas, controle | Mesmos frames/seed, algoritmo, rede/taxas; tempos no mesmo relógio | Parear A/C e B/D; registrar etapas observáveis. Não subtrair relógios não sincronizados |
| H4 atraso prejudica seguimento | atraso/falhas controlados | erro externo, perdas/paradas, conclusão | Mesma pista, velocidade, bateria/iluminação; ground truth calibrado | Primeiro simular expiração; depois pista progressiva. Motor virtual atual não prova estabilidade dinâmica |
| H5 robustez difere | algoritmo × condição | MAE/RMSE, detecção/perda, estratos | Mesmos frames humanos e sessões independentes; rótulos por condição | Iluminação/sombra/ruído/curva anotados; saída de outro algoritmo não é verdade |
| H6 limites mantêm operação adequada | idade/heartbeat/rede | rejeições, segurança, erro, conclusão | Limites explícitos, frame IDs, comando/eventos e referência externa | Injetar atraso, perda/reconexão; não retomar movimento. Confirmar frenagem só no físico |
| H7 gêmeo representa estados | evento/telemetria | correspondência visual, atraso recepção→render, FPS | GLB original/hash, câmera visual, gravação/replay | Comparar estados, pivôs/sinais, frame timestamp local; geometria não implica fidelidade dinâmica |
| H8 odometria acumula erro | distância/manobra | erro final/trajetória/orientação, deriva | Rodas/bitola/PPR/relação medidos, mesma referência calibrada | Reto/ré/curva/giro/fechado; sem referência externa não há erro absoluto |

## Configurações A–D e unidade experimental

| ID | Execução física prevista | Situação atual |
|---|---|---|
| A | OpenCV Pi; controle Pi; serial Uno; central PC | Executável virtualmente parado; físico pendente |
| B | CNN própria Pi, controle local | Diagnóstico virtual; ROI/visibilidade impedem navegação atual |
| C | captura Pi → OpenCV PC → validade Pi → controle Uno | Executável virtualmente parado; físico pendente |
| D | captura Pi → CNN própria PC → validade Pi → controle Uno | Diagnóstico virtual; não liberar navegação |

O executor usa um JPEG sintético fixo largura480×altura640 em todos os modos.
Isso garante igualdade de entrada e compatibilidade com a ROI y075 original.
Não reduz silenciosamente a imagem da CNN para um domínio incompatível.
Os nomes “embarcado” nos resultados N3 representam a **rota virtual**, executada
no mesmo PC. CPU/RAM do processo incluem os serviços locais e não separam uma Pi.

Cada repetição cria UUID e sessão operacional novos, preserva configuração,
ambiente/commit/árvore modificada/hash de fontes, pesos e imagem. A ordem A–D é
embaralhada por blocos de repetição com semente fixa. Disponíveis 5/10 ou até100
repetições; esses números não garantem poder estatístico. Uma execução é a
unidade experimental; milhares de telemetrias não são milhares de repetições.

Antes da coleta: verificar parado/sem lease, inicializar fonte e modelo, esperar
parada confirmada, estabilizar trocas administrativas, aquecer. Registrar carga
e inicialização separadamente. Depois: gravação, benchmark reutilizado, consultas
concorrentes, CSV; finalizar, verificar SQLite/FK e parar a autoridade. Nenhum
ensaio habilita movimento. Alterações de fonte/configuração ficam bloqueadas
até cancelar; parada/emergência continuam prioritárias.

## Manifesto e fatores controlados

Configuração versionada: `experimentos/configuracoes/comparacao_pc.json`.
Resolução, FPS de captura/transmissão, inferência/telemetria, duração, warmup,
repetição/seed, cenário, atraso e gravação de imagens são registrados. Frequência
de controle atual20Hz e ganhos vêm dos fontes/config preservados e seus hashes;
não são reajustados. Para hardware preencher manualmente firmware **gravado**,
modelo da placa, rede/topologia/adaptador, pista, iluminação medida ou descrita,
baterias/tensão verificável, temperatura inicial, operadores, montagem e calibração.
Campos não medidos ficam NULL. Não confundir fonte em disco com firmware gravado.

## Métricas e referências temporais

- Recursos: `Sistema` no worker, CPU do host vs processo/múltiplos núcleos, RSS,
  RAM, frequência, temperatura/flags Pi só quando disponíveis. GPU/VRAM indisponíveis
  no coletor atual; não preencher zero. Medir consumo com instrumento externo.
- Comunicação: RTT por sonda, mediana/p95/p99 somente n≥100, jitter, contadores
  por canal, substituições de filas, lacunas, reconexões. Lacuna de sequência não
  comprova pacote perdido. Falhas e descartes intencionais ficam distintos.
- Percepção: decode, pré-processamento CNN, inferência, total; segmentação/detecção
  OpenCV agregadas. Mesmas imagens por algoritmo; velocidade separada de qualidade.
- Ciclo distribuído: frame/inferência IDs, Pi recepção original→aceitação Pi no
  mesmo relógio monotônico, idades/geração. O total não é resposta física do motor.
  Captura ESP, envio UART→motor e ACK físico correlacionado indisponíveis no
  contrato atual; não criar fases fictícias ou calcular “rede unilateral”.
- Controle: período/frequência e jitter da instrumentação existente. PI físico
  precisa de série `tempo, referência_pps, medido_pps, PWM` por roda. PD precisa
  de erro/derivada/ação e referência externa. Ganhos não são modificados.
- Linha: posição normalizada na imagem não é erro lateral em cm. Para MAE/RMSE
  físico, usar régua/marcação/câmera externa calibrada. Conclusão/perda/intervenção
  são eventos por percurso anotados, não inventados a partir de previsões da CNN.
- Gêmeo: FPS/tempo CPU de render, cargaGLB e sincronização disponíveis na interface;
  tempo CPU de submissão não é tempo GPU. CPU não mede energia.

## Análise implementada

`experimentos.analise.resumo`: n, média/mediana, variância/desvio amostrais,
extremos/quartis/IQR/p95, p99 condicionado, CV quando média não nula.
`regressao`: MAE/MSE/RMSE/R² (NULL para alvo constante/n<2), máximo e resíduos.
`diferenca`: diferença absoluta, redução percentual, speedup, sem dividir por zero.
`pareado`: mínimo5 pares independentes, bootstrap5000 com seed, IC95 exploratório
da diferença e efeito dz quando definido; não gera p-valor ou conclusão automática.
Análise confirmatória/t/ANOVA/Wilcoxon não aplicada sem desenho e amostra adequados.
Ausência de significância não prova equivalência.

`resposta_degrau`: primeira amostra que cruza10% e90%; acomodação exige permanecer
em ±2% da amplitude até o fim observado e ao menos duas amostras terminais;
sobressinal, erro final na cauda10%, MAE/RMSE. Registrar duração e resolução de
amostragem; não inferir estabilidade física fora desse horizonte.
`odometria`: pares x,y,θ no mesmo referencial, orientação circular, erro final e
percentual pelo percurso externo não nulo. A calibração física é pré-requisito.

## CNN e RL

Reavaliação usa snapshot humano02 e metadados com hashes conferidos; divisão
por vídeos existente (58/10/9 frames usados), sem treinar. Verifica sobreposição
de vídeo/hash entre conjuntos. Teste já explorado anteriormente e do mesmo
ambiente; nova coleta por sessão independente é necessária para avaliação final.
Não usar acurácia de classificação para posição contínua. Visibilidade não foi
supervisionada; não reportar confiança ou taxa de detecção da CNN inventadas.

RL é opcional: separar treino/validação/teste/seeds, política congelada, cenários
de avaliação distintos e recompensa/progresso/conclusão/perdas por episódio.
Os ambientes sintéticos próprios existentes não são o simulador de telemetria,
nem dinâmica física identificada. Checkpoint ausente → bloqueado. Nenhum modelo
pré-treinado substitui a CNN e nenhum treinamento online é habilitado.

## Gráficos e relatórios

PNG240dpi/SVG com título, eixos/unidades, configuração/repetição, origem/nível e n;
séries/histogramas de inferência/ciclo/CPU/RAM, dispersão real×previsto, resíduos,
histórico original de treino/validação. MD/HTML/JSON/CSV/ZIP incluem configurações,
hardware, versão, métricas, eventos, limites e campo de interpretação manual.
HTML pode ser impresso para PDF; geração PDF automática não foi adicionada.
Gráficos de energia, temperatura, recompensa ou trajetória física só quando
existirem dados adequados; não preencher exemplos com resultados fictícios.

## Carga e aprovação

`carga_5min.json`:300s, telemetria30Hz, JPEG15FPS, inferência10Hz, gravação de
imagens e consultas a1Hz. Trocar duração para900/1800/3600s prepara15/30/60min;
não afirmar execução dessas durações sem evidência. CSV em fluxo limitado50MB,
estatísticas últimas25000 amostras/métrica, benchmark com limite50MB; filas
existentes limitadas. Monitorar crescimento RSS/SQLite/arquivos, erros, FPS,
conexões/filas e encerramento. Variação de RSS não basta para concluir vazamento.

Critérios obrigatórios: inicialização parada, simulação isolada, único controlador,
rejeição de mensagens/resultados antigos, exclusividade, expiração/sem retomada,
integridade e proteções preservadas. Limites atuais de validade da Etapa6 são
contrato de software, não distância de frenagem validada. Limites de temperatura,
RSS, erro físico, jitter e conclusão devem ser preenchidos pelo pesquisador em
`criterios` como provisórios ou físicos após medir a dinâmica; ausente→não avaliado.
