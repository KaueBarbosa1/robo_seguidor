# Contexto do projeto e plano para a CNN

Registro de continuidade em 16/11/2026. Consolida o código disponível e as
decisões propostas pelo usuário. Este documento e os comentários associados
não implementam nem ativam o plano. Os valores de calibração e critérios
numéricos ainda precisam ser definidos em experimentos com o carrinho.

## Objetivo e divisão de responsabilidades

O objetivo é um carrinho que siga uma trajetória pontilhada, atravesse seus
vãos, antecipe curvas e reencontre a linha depois de contornar obstáculos.
Voz e controle remoto Bluetooth permitem comandar e interromper o movimento.

| Componente | Papel atual e evolução pretendida |
|---|---|
| Raspberry Pi 5 | Executar visão, inferência, planejamento e controle; treino apenas parado. |
| ESP32-CAM OV2640 | Fonte de imagem em avaliação: JPEG 320×240 por Wi-Fi, receptor de bancada separado. |
| Arduino Uno e L298N | Acionamento das rodas, leitura de sensores e proteções locais. |
| Encoders | Medir pulsos das rodas; validar e calibrar antes de usá-los como odometria. |
| Ultrassom e servo | Medir distâncias frontal/laterais; alimentar um planejador futuro. |
| CNN de linha | Estimar trajetória e sua validade; não escolher sozinha um contorno de obstáculo. |
| Planejador futuro | Escolher e acompanhar o contorno, procurar e recuperar a trajetória. |
| Controle | Converter decisões em comandos de roda e interromper movimentos inseguros. |

O controle continua sendo o único escritor dos comandos de motor. Visão e
aprendizado publicam resultados no estado compartilhado. Parada manual,
watchdogs, validade dos dados e proteção de obstáculo precisam permanecer
prioritários durante qualquer futura integração.

## Estado atual: implementação não equivale a validação física

- Revisao solicitada para marcha mantida e deteccao apenas proxima: no manual
  continuo, limite frontal/lateral10 cm, liberacao15 cm, re automatica abaixo
  de10 cm. Ausencia/idade do eco continua indicada como falha, mas nao cancela
  o comando manual. Obstaculo confirmado fica travado ate dois ecos livres;
  perder eco nao o apaga. Telemetria serial vencida, watchdogs, botao parar e
  falha de encoder continuam interrompendo. Sem eco nao ha garantia de detectar
  novos obstaculos. Nao houve ensaio fisico ou upload. Requer regravar Uno
  e reiniciar main. Commit indisponivel: pasta sem repositorio Git valido.

- `main.py` reúne controle, visão OpenCV, voz e Bluetooth; a thread de
  aprendizado é opcional. `APRENDIZADO_ATIVO = False` na configuração revisada.
- `FONTE_IMAGEM = "arduino"`, mas `FIRMWARE_COM_CAMERA = False` e a serial está
  em 115200 baud. `main.abrir_fonte` troca essa combinação por fonte sem imagem.
  Portanto, essa configuração não fornece imagem à visão pelo Uno.
- A OV7670 via Uno é o caminho legado. Seu modo com câmera usa 1 Mbaud e
  conflita com ultrassom/encoders. A câmera CSI é uma alternativa antiga sem uso.
  Comentários que chamavam a OV7670 de decisão definitiva são históricos;
  a migração proposta agora considera a ESP32-CAM.
- A ESP32-CAM é testada por `arduino/esp32_cam_bancada/` e
  `tools/testar_esp32_cam.py`. `tools/coletar_esp32_cam.py` reaproveita a
  recepção para guardar JPEGs originais por sessão e mostrar uma ROI 80×40
  para calibração. A captura e a recuperação de JPEG truncado foram testadas
  com servidor HTTP simulado. A coleta e a calibração no hardware, bem como
  a integração com `visao/fontes.py`, CNN e controle, permanecem pendentes.
- O painel web experimental foi removido a pedido do usuario, incluindo
  servidor HTTP/WebSocket, interface de joystick/video, gravador integrado,
  adaptacao PAN e testes exclusivos. O controle permanece pelo aplicativo
  Bluetooth SPP/RFCOMM de `main.py`, sem depender de rede PAN ou navegador.
  Foram revertidos o parametro de neutro exclusivo da interface web e a
  abertura serial exclusiva introduzida para ela. Gravacoes existentes foram
  preservadas como dados locais; ferramentas independentes da ESP32-CAM
  continuam disponiveis. Mantidos sonar durante marcha/curvas, bloqueios
  direcionais, recuo curto, alcance do eco, retry com memoria limitada,
  correcao dos LEDs e filtro PI em baixa velocidade. Nao houve validacao
  fisica dessas melhorias, novo upload ou ativacao de CNN nesta remocao.
  Verificacao da remocao: 71 testes Python de controle, recuo, sonar, servo,
  serial, velocidade, calibracao e sinalizacao passaram, assim como harness
  C++ experimental. Nenhuma dependencia do painel permaneceu nesses caminhos.
  O perfil NetworkManager `painel-celular` nao pode ser removido deste ambiente
  por bloqueio de acesso ao servico; limpeza manual indicada no guia Bluetooth.
  Na retomada de 16/11/2026, a inspecao confirmou que os arquivos e dependencias
  da interface web ja estavam ausentes; nao foi necessario alterar o controle.
  Reexecutados os 71 testes pelos scripts Python e o harness C++ do perfil
  atual: passaram. A suite adicional `tests/test_remoto.py` teve 13 testes
  aprovados e 12 falhas: nove por restricoes de sockets/D-Bus do ambiente e
  tres em expectativas de direcao (curva versus giro e inversao Eletrogate).
  Essas divergencias permanecem pendentes; nao representam validacao do
  Bluetooth real. Nenhum upload foi realizado. O diretorio `.git` disponivel
  nesta retomada esta vazio e sem escrita, impedindo consultar o historico Git
  ou criar o commit solicitado; nao foi inicializado outro repositorio.
- Na investigacao posterior do amarelo/rodas paradas, o log do usuario
  confirmou modo 4 experimental e liberacao frontal intermitente a 145..148 cm,
  mas tambem frente `None` com falha/bloqueio, ecos laterais curtos e termino
  por confirmacao vencida/ausente. O ensaio sem `--pps` nao solicitou movimento;
  E/D zerados nao validam nem refutam motores. Causa fisica permanece pendente.
  `tools/testar_sonar_movimento.py` agora distingue ausencia/idade dos pacotes
  servo/sensores, flags de modo e tentativas de reconexao, e mostra bloqueios
  laterais. Retirada recomendacao generica de regravar apos perder confirmacao.
  Limites de validade/parada mantidos; somente diagnostico Python, sem upload.
  Dois testes de regressao cobrem classificacao e encerramento sem velocidade;
  os 13 testes do arquivo de sonar em movimento passaram. Procedimento e
  interpretacao no guia 14; ainda sem demonstrar resolucao do bloqueio fisico.
  No segundo log, a mensagem detalhada identificou ausencia da flag de modo 4
  no status recebido, com zero tentativas de reconexao. Idades anteriores dos
  sensores estavam em 1..25 ms e do servo em 49..352 ms. Frente a 146 cm
  chegou a aparecer bloqueada sem falha; tambem houve frente desconhecida.
  Nao atribuir o bloqueio somente a distancia ou laterais: estas estavam
  livres nos resumos. Uma sonda temporaria no harness repetiu V4+S a cada
  50 ms por 10 s simulados, sem perder modo e visitando 60/120 graus; retirar
  renovacao por 420 ms cancelou o modo como previsto. Isso nao simula latencia
  real da UART no AVR nem identifica a causa no hardware. Proximo diagnostico:
  conferir processos com a serial aberta (`fuser -v /dev/ttyACM0`) antes de
  novo ensaio. Concorrencia, perda de renovacao e reinicio continuam hipoteses;
  zero reconexoes na Pi nao exclui reinicio do Uno. Nenhuma guarda alterada.
  O usuario informou `fuser` sem saida apos encerrar o ensaio. Investigada a
  fragilidade de RX por polling durante calculos do sonar: teste com pausa
  sintetica de 870 us e fila de hardware limitada perdeu S/V4 antes da mudanca.
  No firmware sem camera, RX agora usa interrupcao/buffer HardwareSerial de
  64 bytes; parser e comandos permanecem no loop, TX direto. Camera legada
  conserva polling. Nenhum timeout/margem/teto alterado. O ensaio de rajadas
  passou apos a mudanca, mantendo modo 4 por 10 s simulados e cancelando
  sem renovacao por 420 ms. Harnesses experimental, desativado, calibrado
  sintetico e sem servo passaram. Uno integrado compilado: 12698 bytes flash,
  385 bytes RAM. Tempo real dos calculos e causa fisica ainda nao confirmados;
  exige regravar Uno e repetir observacao. Nenhum upload realizado.
  A compilacao com camera legada tambem passou (5080 bytes flash/322 RAM),
  sem exercicio fisico desse caminho. Commit indisponivel pela pasta `.git`
  vazia e sem escrita neste ambiente.
- O log posterior a revisao de RX mostrou percursos nominais completos entre
  60/90/120 graus, idades de status de 44..49 ms e sensores de 3..48 ms,
  sem excecao no trecho recebido. Frente a 144..145 cm permaneceu liberada;
  quando caiu a 44/34/29/24 cm, o avanco ficou bloqueado com falha=False.
  Esse bloqueio e compativel com a reserva experimental de aproximadamente
  46,06 cm (25 cm + 10 cm de frenagem configurada + 10 cm de margem +
  1,064 cm de quantizacao), antes de descontar deslocamento. Laterais tambem
  indicaram bloqueios em alguns momentos. O usuario confirmou posteriormente
  que aproximou a mao durante o ensaio; ecos curtos/ausentes laterais nao foram
  validados geometricamente. O ensaio continuou sem pedir velocidade;
  rodas e movimento fisico integrado permanecem sem validacao.
- No ensaio seguinte com pedido de 4 pulsos/s, o usuario relatou que ambas
  as rodas giraram duas ou tres vezes, com pausas. O trecho recebido manteve
  confirmacao recente de modo 4; bloqueios surgiram com frente ainda acima
  de 1 m, falha=False e, inicialmente, laterais livres. Os contadores foram
  E/D=1/1 para21/22 em aproximadamente 0,5 s entre resumos: cerca de40/42
  pulsos/s, acima do alvo. A conversao geometrica provisoria equivale a
  210,5/223,3 mm nesse intervalo, excedendo o orcamento de100 mm sem renovar
  frente. Essa guarda explica as pausas e as liberacoes apos retornar ao
  centro. As taxas sao estimativas pelos logs, nao velocidade no piso medida.
  Os4 pulsos/s limitam o alvo enviado ao PI; nao comprovam que a velocidade
  real esteja limitada a4. Proximo ensaio: PI separado, rodas suspensas,
  sonar encerrado e frente livre, `tools/testar_velocidade.py --pps 4 --tempo 5`.
  Nao aumentar orcamento/margens ou alterar ganhos sem observar esse resultado.
  O ensaio isolado retornou pico E/D=65,5/67,5 pulsos/s, com ultimas janelas
  em6..8 pulsos/s para alvo4. Isso confirma excesso de taxa medida mesmo
  sem sonar. A integral inicial PWM120 e reiniciada a cada partida e decai
  lentamente. Ainda falta medir a relacao PWM/pulsos para escolher a partida
  ou ajustar ganhos; nao foram alterados ganhos/limites/firmware nesta etapa.
  `tools/testar_velocidade.py` agora oferece `--pwm` explicito, exclusivo de
  `--pps`, mantendo configuracao PI do projeto. A API `ArduinoSerial.pwm`
  recusa contexto/status de modo4. Os ensaios PWM30 e PWM40 por3 s enviados
  pelo usuario tiveram contagem zero nos dois canais; PWM60 chegou a48
  pulsos/s em ambos. Ainda nao ha medida de sustentacao apos a partida.
  Testes cobrem unidade PWM com PI ativo, recusa no sonar, comandos R/M e
  encerramento por perda de telemetria; consultar guia11. O relato nao valida
  velocidade nem frenagem no piso e nao autoriza ampliar a guarda por100 mm.
  A ferramenta ganhou `--pwm-partida`, somente junto de `--pwm` positivo e
  menor: aplica o valor maior por roda ate receber o primeiro pulso do canal
  correspondente, depois usa o PWM de sustentacao. Prazo total de1 s para
  ambas partirem; nao repete tentativas automaticamente. Falha de telemetria,
  frente bloqueada, reconexao ou regressao de contadores encerram e param.
  Confirmacao vem pela serial, nao e corte fisico instantaneo no encoder.
  Novo ensaio proposto: `--pwm 40 --pwm-partida 60 --tempo 3`, rodas suspensas,
  para distinguir partida e sustentacao. Resultado fisico pendente. Essa opcao
  existe somente na ferramenta; nenhum ganho, partida do PI ou firmware foi
  alterado nesta etapa. Os16 testes de velocidade/ferramenta passaram, incluindo
  independencia das rodas, prazo, falhas, limpeza e compatibilidade de R/M.
  Resultados posteriores: partida60 acionou apenas D em1 s (E parada,
  confirmado pelo usuario); partida80 acionou ambas. Sustentacao40 ficou
  perto de16 pulsos/s; sustentacao32 deixou E em4..6 e D sem pulsos; em34,
  ultimas janelas E6..8 e D4..6. Registrados em
  `docs/calibracao/pi_baixa_bancada.json`. Sao referencias de bancada em
  avanco, nao calibracao no piso ou em re.
  Implementada revisao de PI para pedidos nao nulos ate8 pulsos/s: reforco80
  por roda ate seu primeiro pulso, retirado pelo loop sem esperar100 ms;
  integral inicial E32/D34, separada do reforco. Ganhos baixos0.25/0.5 sao
  escolhas iniciais de software verificadas em simulacao. As bases nao sao
  pisos de PWM. Renovar R nao rearma; zero/inversao/S/mudanca de faixa e
  falta de pulso por1 s sao tratados, preservando watchdogs e guarda sonar.
  Pedidos maiores conservam inicializacao anterior. Dados de avanco tambem
  parametrizam re baixa, ainda pendente de validar no hardware.
  Na planta sintetica realimentada por PWM, primeiro segundo caiu de65/64
  para8/8 pulsos em alvo4; cauda de2 s teve8/8. Com sonar, primeiro segundo7/7,
  cauda8/8 e zero cortes apos liberacao inicial. Harnesses passaram, incluindo
  controle por roda, falha de encoder e watchdog. Requer regravar Uno e medir
  PI4 separado antes de repetir sonar. Nenhum upload/ensaio fisico da nova
  revisao realizado pelo assistente; nao foi ampliada guarda ou teto de alvo.
  Verificacao final: quatro perfis de harness passaram (experimental, sem
  servo, experimental desativado e calibracao sintetica), mais16 testes Python
  de velocidade/ferramenta. O mesmo harness aplicado a versao anterior falhou
  em10 verificacoes, incluindo cortes repetidos na planta com sonar. Uno
  integrado compilado em13242 bytes flash/391 RAM; camera legada compilou em
  5080/322. Commit indisponivel neste ambiente pela pasta `.git` vazia.
  O ensaio fisico posterior nao sustentou a revisao: E/D=6/7,9;6/8;3,6/3,6;
  2/0 e depois ambas0. Nao considerar o problema resolvido. Um limiar de
  atrito um ponto maior no modelo tambem produz perda de giro e falha de
  encoder; esse caso verifica a parada protetiva, nao sucesso do controle.
  Tentativas de reforco durante regulacao foram descartadas por cortes na
  guarda integrada. O controle foi restaurado exatamente a revisao enviada
  ao usuario; nesta etapa foram acrescentados apenas diagnostico e testes.
  O firmware sem camera transmite F8 com PWM aplicado por roda, sinais,
  falha de encoder, PI e fase de reforco. Python decodifica com timestamp;
  a ferramenta mostra tambem bloqueio frontal/falha do sensor e encerra PI
  ao receber falha recente de encoder. O log antigo nao permite confirmar
  a causa fisica ou qual protecao atuou; requer regravar e repetir PI4
  suspenso para obter esses campos. Nao houve novo upload pelo assistente.
  Verificacao da revisao diagnostica:41 testes Python (velocidade, serial e
  sonar em movimento) e quatro perfis de harness passaram. No caso de atrito
  extra, passar significa confirmar a parada protetiva e F8, nao sustentar o
  giro. Uno compilado em13446 bytes flash/391 RAM; camera legada5080/322.
  O commit segue indisponivel pela pasta `.git` vazia neste ambiente.
  O ultimo ensaio F8 confirmou guarda frontal liberada e sensor sem falha,
  com PWM E31/D33 e depois E30/D32. E perdeu pulsos; em seguida o firmware
  confirmou a falha de encoder e encerrou o ensaio. Isso identifica o corte
  por ausencia de pulsos, nao comprova defeito eletrico do encoder. Torque
  insuficiente apos a reducao do PI e compativel com os ensaios anteriores.
- O usuario mudou o escopo imediato para retirar a indicacao amarela. Agora
  somente verde e vermelho sao usados no firmware e no teste isolado: verde
  com guarda frontal liberada/servo permitido/encoder sem falha; vermelho
  por bloqueio, leitura invalida, obstaculo latente ou falha de encoder.
  A1 e apenas inicializado em LOW para manter o antigo LED apagado. Lateral
  ocupada nao muda o verde se a reta estiver liberada, mas sua curva continua
  bloqueada pela guarda. Buzzer preserva regras anteriores.
  A sinalizacao apenas observa estados, nao aciona nem libera motores. PI,
  watchdogs, encoders, guardas sonar e percurso do servo permanecem como na
  revisao anterior. Piso de torque e retorno antecipado ensaiados durante a
  investigacao nao foram incluidos nesta alteracao. A perda de sustentacao
  continua pendente; remover a cor amarela nao valida nem corrige esse ponto.
  Requer regravar Uno; nenhum upload ou ensaio fisico foi feito pelo assistente.
  Verificacao da remocao do amarelo: cinco testes Python de sinalizacao e
  quatro perfis do harness passaram (padrao, sem servo, sem sinalizacao e
  experimental desativado). Compilaram Uno integrado13432 bytes flash/391
  RAM, teste isolado2426/262 e camera legada5080/322. O caso de atrito extra
  continua verificando parada protetiva; nao e solucao da sustentacao. Commit
  indisponivel pela pasta `.git` vazia neste ambiente.
- O usuario relatou que na main as rodas giram por um instante e param, e
  reiterou que a varredura nao deve interromper a marcha normal: bloquear
  avanco por risco frontal, mantendo parada manual e protecoes de falha.
  Retomada a proposta antes deixada fora da remocao do amarelo. Aplicado
  piso condicional E32/D34 para alvo efetivo positivo4..8 e medicao filtrada
  ate2x alvo; anti-windup congela a integracao que empurraria contra o piso.
  Zero, alvo menor, re e excesso de velocidade nao recebem esse piso.
  Nao ha repeticao automatica da partida80 nem rearmamento da falha; guardas
  e timeout de encoder1 s continuam prioritarios. Teto de alvo4 mantido.
  No modo4, consumir um terco do orcamento faz o servo retornar ao centro
  antes do extremo lateral, reservando restante para revisita; nao libera
  movimento nem renova memoria. Limites100 mm/2 s e margens mantidos. O
  servo girar por si so nao bloqueia marcha MANUAL4. A1 segue desligado.
  `REMOTO_DIAGNOSTICO_MOVIMENTO=True` habilita resumos MANUAL na main (1/s
  ou transicoes) com pedido, guarda, modo4 e F8/PWM/falha de encoder; apenas
  leitura. Dados vencidos/ausentes/futuros ficam indisponiveis. Cinco testes
  verificam logs, cadencia, flags e ausencia de comandos pelo logger.
  Na planta sintetica com/sem atrito extra, as rodas mantiveram pulsos com
  e sem sonar, sem cortes apos liberacao inicial. Isso nao valida o carrinho.
  Regravar Uno e reiniciar main antes do ensaio suspenso; nenhum upload ou
  validacao fisica da nova revisao pelo assistente. CNN segue desativada.
  Verificacao:66 testes Python distintos (controle, recuo, sonar, velocidade,
  sinalizacao e novo diagnostico manual) passaram, assim como cinco perfis
  C++ (padrao, sem servo, sem sinalizacao, experimental desativado e calibrado
  sintetico). Uno integrado13712 bytes flash/391 RAM; camera legada5080/322.
  O resultado e de software/simulacao; aplicacao ao carrinho permanece pendente.
  Commit indisponivel pela pasta `.git` vazia neste ambiente.
- No log da main de14:49..14:50 enviado depois, modo4 permaneceu confirmado
  e falha_encoder=False, mas a guarda frontal alternou bloqueio/liberacao.
  Varias paradas tinham falha_sensor=False; nao atribuir a causa ao LED.
  Distancia frontal/angulo/motivo interno nao estavam registrados. Diferenca
  entre pulsos das rodas pode atingir a guarda de20 mm antes dos100 mm de
  avanco, mas esse log sozinho nao confirma qual limite atuou no hardware.
  O retorno frontal agora tambem e antecipado em um terco do limite de
  divergencia (somente reta) ou do prazo frontal. Guardas e PI preservados;
  sem frente valida continua a varredura anterior, inclusive em re.
  Acrescentado F7 opcional, um byte com motivos da mesma funcao que bloqueia
  as rodas: perfil, memoria ausente/vencida, confirmacao, avanco, divergencia
  e distancia/reserva. Nao ha guarda duplicada no diagnostico. A main mostra
  `guarda`, `frente_cm` e `angulo_nominal`; ausencia/idade invalida informa
  indisponivel. Pacotes distintos sao snapshots recebidos em instantes
  diferentes; motivo da decisao pode preceder o estado exibido no resumo.
  Uma planta sintetica com resposta da roda D50% maior reproduziu cortes
  por divergencia no perfil experimental, mesmo apos antecipar a revisita.
  Nao considerar o giro continuo resolvido: proximo ensaio suspenso da main
  deve identificar `guarda=...` durante as pausas, apos regravar Uno e atualizar
  Python juntos. Perfil calibrado sintetico com1 mm/pulso nao reproduz os
  mesmos cortes; isso nao e calibracao fisica. Testes verificam essa limitacao.
  Nenhum upload ou ensaio fisico executado pelo assistente; CNN desativada.
  Verificacao desta etapa: scripts Python de controle, recuo, sonar, velocidade,
  sinalizacao, diagnostico manual e serial/imagem passaram, assim como os cinco
  perfis C++ (experimental, sem servo, sem sinalizacao, desativado e calibrado
  sintetico). Uno integrado compilou em13872 bytes flash/391 RAM e camera
  legada5080/322. O caso assimetrico experimental passa por reproduzir a
  parada protetiva, nao por demonstrar movimento continuo.
  Commit indisponivel: `git status` retorna que nao ha repositorio Git neste
  ambiente, cuja pasta `.git` esta vazia e sem escrita.
- Na solicitacao seguinte, o usuario rejeitou explicitamente a espera por
  varredura e a sonda presa na frente, autorizando retorno ao comportamento
  simples de obstaculo/vermelho/re. Implementado `SONAR_MOV_CONTINUO=1` como
  padrao do modo4 manual. Servo percorre60..120 sem pausas no centro nem
  retorno provocado por encoder. Copia frente centrada valida preexistente
  ao entrar, com idade original; nao espera outra volta se ja estava livre.
  Ecos no cone nominal80..100 contam como frontais durante movimento;
  lados nao renovam frente. Dois ecos reais abaixo de25 cm bloqueiam e dois
  a partir de30 cm liberam. FC repetido nao e contado pela Pi como eco novo.
  Saem os limites100 mm/20 mm, desconto por encoder/reserva46 cm e rampa
  de aproximacao no manual continuo. Teto de alvo4, PI, encoders, watchdogs,
  parada manual e falhas/validade frontal2 s permanecem. Sem frente valida
  nao inventa caminho livre. Re curta existente na main permanece habilitada
  uma vez por comando, limitada em tempo/pulsos, sem cobertura traseira.
  A1 continua desligado. Nao ativa CNN, treino ou desvio autonomo.
  Perfil anterior de revisita fica compilavel com SONAR_MOV_CONTINUO=0,
  incluindo seus testes de regressao. Guia14 inicia pelo comportamento atual
  e identifica os relatos anteriores como historico. Simulacao com E4/D6 por
  10 s e planta assimetrica nao tiveram cortes no perfil continuo; ensaio de
  ECHO proximo confirmou parada local, e re permaneceu permitida. Nao equivale
  a validacao de frenagem/cobertura angular no carrinho. Requer atualizar
  Python e regravar Uno, primeiro ensaio suspenso. Nenhum upload realizado.
  Verificacao: passaram os scripts Python de controle, recuo, sonar,
  velocidade, sinalizacao e diagnostico. Seis perfis C++ passaram: continuo,
  legado com SONAR_MOV_CONTINUO=0, sem servo, sem sinalizacao, perfil ausente
  e calibracao sintetica. Uno integrado13282 bytes flash/384 RAM; camera
  legada5080/322. Commit impossivel neste ambiente: `git status` informa
  que nao ha repositorio Git; nao foi criado repositorio substituto.
- O servo já tem varredura e inspeção de três direções implementadas.
  O modo separado `sonar` percorre 45 a 135 graus nominais continuamente,
  sem pausa por grau, ate Ctrl+C. Mede durante o movimento e transmite
  angulo comandado no disparo/distancia/sequencia. A coleta respeita intervalo
  minimo de 60 ms; nao ha uma medida em cada grau. A primeira versao parava
  200 ms em cada grau e foi alterada apos relato de movimento aos passos.
  Os logs enviados confirmam comunicacao e comandos de ida/volta, mas nao
  validam movimento real ou distancias. A suavidade dessa revisao ainda precisa
  ser conferida no hardware. Exige
  regravar o firmware e executar `tools/testar_servo.py --modo sonar`.
  Esse modo 3 mantem as rodas bloqueadas; nao e iniciado pelo controle principal.
  Foi acrescentado o modo 4 experimental, com percurso 90/120/90/60,
  estabilizacao frontal e memoria descontada por encoders. O usuario esclareceu
  que esta etapa e MANUAL por Bluetooth; CNN/seguimento autonomo ficam para depois.
  Corrigida a integracao para somente MANUAL, com entrada/saida explicita do
  contexto serial. A revisao atual mantem a varredura durante marcha e curvas/re.
  Parar pelo aplicativo cancela o sonar e solicita centro. Curvas nao resetam
  etapa/memoria; frente limitada a 2 s/100 mm e
  reservas experimentais existentes. Partida exige duas frentes livres, sem
  esperar uma varredura completa. Proximidade/falha frontal nao congela servo.
  Laterais abaixo de 25 cm bloqueiam somente curva para o lado observado,
  preservando reta/curva oposta com frente livre e re reta. FC bits5/6 exportam
  lados independentes. Correspondencia inicial 60=esquerda/120=direita depende
  de confirmar suporte; macro permite inverter. PI usa alvos para direcao.
  Esta revisao exige regravar o Uno; firmware antigo conserva guarda anterior.
  Relato posterior trouxe diagnostico de frente sem leitura valida, pedido
  E/D70/65 e contadores14/14. Os contadores sao acumulados, nao velocidade.
  Reproduzida inconsistencia de alcance: validacao ate400 cm mas timeout do
  ECHO alto14 ms descartava retornos acima de aproximadamente241 cm. Timeout
  passa a24200 us, derivado de400*58+1000, sem alterar validade da memoria,
  margens ou liberar ausencia de eco. Testes sinteticos de240/300/400 cm e
  bloqueio410 cm passaram; teste300 falhou antes. Causa fisica ainda depende
  de leitura com alvo conhecido e comparacao centro/sonar. Requer regravar Uno.
  Usuario esclareceu depois que a distancia alterna numero/sem leitura quando
  servo gira. Reproduzidas interrupcoes com perdas frontais isoladas (uma em
  tres amostras). Nova decisao: com memoria ja liberada, uma perda conserva
  somente a ultima leitura valida dentro dos mesmos 2 s/100 mm/margens;
  nao renova idade/encoders/distancia. Duas perdas frontais consecutivas
  invalidam memoria; partida/recuperacao exigem duas frentes livres seguidas.
  Servo tenta ate quatro amostras por visita ao centro em caso de perda,
  mantendo varredura limitada e guarda independente. Obstaculo valido segue
  bloqueando e confirmado pode acionar re. Harnesses e 34 testes Python
  passaram; Uno11742/210 bytes flash/RAM. Precisa regravar; sem ensaio fisico.
  Diferenca intencional de giro entre rodas nao e tratada como desvio da reta.
  Re manual tambem foi liberada sob teto/watchdogs/encoders, sem prometer
  cobertura traseira pelo sonar frontal. Nenhum contorno automatico foi ativado.
  A pedido do usuario, o controle MANUAL ganhou re automatica curta quando
  ha solicitacao de avanco e obstaculo frontal confirmado abaixo de 25 cm.
  Para antes por 150 ms, solicita -4 pulsos/s por ate 350 ms e corta tambem
  ao contar dois pulsos em qualquer roda, perder telemetria/confirmacao do
  modo 4 ou receber parada. Nao retoma avanco nem repete com botao mantido;
  neutro/pare rearmam. Re explicita do operador prevalece. Nao ha protecao
  traseira. Limites iniciais experimentais, sem distancia ou frenagem validada;
  testes simulados, sem upload ou ensaio fisico. CNN/SEGUINDO nao usam esse recuo.
  O usuario solicitou ativacao antes da validacao no piso. Agora
  SONAR_MOVIMENTO_ATIVO=True e SONAR_MOV_EXPERIMENTAL=1 ativam um perfil
  explicitamente experimental: teto de 4 pulsos/s, reserva inicial de 100 mm
  para frenagem (nao medida), margem de 100 mm e avanco maximo de 100 mm
  sem nova frente. SONAR_MOV_CALIBRADO permanece 0 e frenagem medida 0.
  Telemetria distingue perfil experimental de calibracao; pedidos retos
  acima do teto sao limitados proporcionalmente, preservando sinais e curva.
  Implementacao e testes sinteticos nao validam movimento fisico ou desvio.
  Procedimento: [sonar em movimento](14_sonar_em_movimento.md).
  Como o usuario nao pode colocar o carrinho no piso agora, a calibracao ganhou
  alternativa manual com rodas suspensas (`calibrar_encoders.py --voltas 5`).
  Mede pulsos por volta; com diametros medidos, estima mm/pulso geometricamente.
  Conferencia de rolagem com carga e frenagem no piso continuam pendentes;
  nao foi marcada calibracao por essa alternativa. A posterior liberacao
  experimental foi solicitada separadamente pelo usuario e nao valida o piso.
  O primeiro ensaio suspenso relatado abortou por pulsos no canal direito
  durante a etapa esquerda; a causa ainda nao foi identificada. A ferramenta
  agora mostra deltas E/D e orientacao de referencia, distinguindo somente
  canal oposto de resposta dos dois canais. Nao houve troca de pinagem.
  No ensaio posterior de cinco voltas, o usuario obteve 97 pulsos em D2 e
  96 em D3, sem contagem cruzada, e encerrou a repeticao dos testes manuais.
  Esses dados foram aceitos como referencia provisoria: 19,4/19,2 pulsos por
  volta, registrados em `docs/calibracao/encoders_bancada.json` e no firmware.
  Nao arredondar automaticamente para 20. O usuario informou diametro de
  65 mm, largura de pneu de 26 mm e circunferencia de 20,42 cm para as rodas.
  Aplicados 65 mm a ambas: estimativas geometricas de 10,52595 mm/pulso E e
  10,63560 mm/pulso D. A largura informada e do pneu, nao do carrinho inteiro.
  Frenagem e velocidade validada no piso seguem desconhecidas; os limites
  ativos sao configuracoes iniciais experimentais, nao resultados fisicos.
  A ampliacao fisica para 0 a 180 graus depende de calibracao dos pulsos e
  limites mecanicos. O usuario encontrou mau contato no GND da protoboard;
  ainda e necessario repetir os ensaios fisicos de servo e ultrassom.
  A inspeção automática em SEGUINDO termina em PARADO; ainda não escolhe um
  desvio nem retoma movimento sozinha. A validação física integrada é pendente.
- Existe controle PI por encoders. `CONTROLE_VELOCIDADE_ATIVO = True` está
  marcado como teste com rodas suspensas; isso não comprova calibração ou
  funcionamento na pista. A revisao de diagnostico passa a exportar a falha
  de encoder por F8, com validacao fisica dessa telemetria ainda pendente.
  Apos relato de amarelo constante e rodas irregulares no sonar, reproduzidos
  dois problemas: LED exigia servo frontal parado (verde 0/399 com frente
  livre simulada) e PI em 4 pulsos/s oscilava PWM114..125 por quantizacao de
  janelas de 100 ms. Corrigido LED para usar a guarda, preservando amarelo
  por aproximacao/lateral/falha, e filtro exponencial da medicao ate 8 pulsos/s
  (tau inicial 400 ms). Mesmo ensaio: verde399/399, PWM121..123 e nenhum
  bloqueio frontal na varredura. Contadores brutos/limites/watchdogs mantidos;
  corte por falta de pulsos confirmado no alvo 4. Isso nao identifica por si
  a causa de eventual bloqueio fisico; necessario obter distancia/diagnostico
  reais. Requer regravar Uno; sem upload ou validacao fisica pelo assistente.
  A investigacao da parada com LED amarelo reproduziu reducao duplicada:
  aproximacao atenuava alvo e PWM do PI. Corrigido para reduzir apenas o alvo;
  PWM direto mantem sua reducao. Verificado com planta sintetica de atrito e
  pulsos, sem comprovar a causa fisica do relato. Servo fora do centro, sonar,
  falha de leitura e obstaculo continuam bloqueando conforme as regras atuais;
  a excecao experimental e o modo 4, condicionado a sua propria guarda calibrada.
- `aprendizado/robo_real.py` contém adaptação do ciclo de aprendizado legado;
  sua documentação registra verificação em simuladores, não na pista física.

Guias: [bancada ESP32-CAM](12_esp32_cam_bancada.md),
[servo e inspeção](09_servo_integrado.md),
[velocidade e encoders](11_controle_velocidade.md),
[aprendizado legado](04_aprendizado_online.md),
[dataset e rotulação](08_dataset_linha.md). As notas antigas do README e desses
guias descrevem etapas específicas; não são comprovação do conjunto atual.

## CNN existente e significado dos pesos

`aprendizado/cnn.py` implementa `RedeLinha` em NumPy, com pesos inicialmente
aleatórios: três convoluções, camada densa de 64 e duas saídas. A entrada tem
formato `(N, 1, 40, 80)`, isto é, imagens cinza de largura 80 e altura 40.

O primeiro valor é limitado a [-1, 1]. No ciclo legado representa direção
sugerida; no treino com fotos foi reaproveitado para posição horizontal da
linha em uma única altura, y = 75% da imagem. **Posição não é comando de motor.**
O segundo valor é um logit de visibilidade, convertido em probabilidade em
`prever`. No treino com fotos, `tools/treinar_fotos_linha.py` usa
`lambda_vis=0`: essa saída não foi supervisionada e deve ser ignorada.
O formato da rede permitir calculá-la não a torna uma confiança confiável.

Há dois caminhos de entrada diferentes:

- `aprendizado/dados.py`: quadros legados 160×120, corte a partir de
  `APR_ROI_LINHA_INICIO` e redução por blocos 2×2.
- `aprendizado/dataset_rotulado.py`: recorte proporcional 2:1 na largura
  inteira, centrado em y=75%, seguido de redução para 80×40. O contrato se
  chama `foto_roi_2por1_y075_v1`. Esse recorte não cabe em um quadro 320×240
  com a referência atual; não basta conectar a câmera ao carregador de fotos.

Ambos usam `dados.normalizar`: divide por 255, subtrai a média por imagem,
divide pelo desvio padrão mais 0,08 e limita a [-4, 4]. Treino e inferência
dos mesmos pesos devem usar exatamente o mesmo caminho completo.

Os rótulos humanos contêm pontos e estados `visivel`, `parcial`, `ausente`
e `ambiguo`. O carregador atual só inclui posições cuja extensão anotada
cubra y=75%; ausentes e ambíguos são excluídos do treino de posição.
A divisão já ocorre por vídeo, mas os conjuntos atuais são exploratórios e
do mesmo ambiente. A sugestão de `visao/sugestao.py` é OpenCV para revisão
humana; não é CNN nem gera visibilidade supervisionada automaticamente.

### Experimento offline com BatchNorm

A `RedeLinha` ganhou uma variante opcional com `Convolução → BatchNorm → ReLU`
nos três blocos. O treino calcula médias e variâncias por canal. A inferência
usa as estimativas móveis persistidas no checkpoint, inclusive ao processar
um único quadro. O formato `rede_linha_batchnorm_v1` identifica esses pesos.

`tools/comparar_batchnorm.py` compara a variante e a CNN original para o
mesmo alvo em y=75%. Cada par usa os mesmos dados, inicialização, sequência de
lotes e critério de seleção por validação. O experimento é offline e mede
erro de posição e diferença entre treino e validação. Ainda é preciso avaliar
a generalização em gravações novas da ESP32-CAM montada.

O diagnóstico visual mostra a imagem original, a entrada normalizada, a
previsão de cada variante sobre a anotação e três canais após a ReLU de cada
bloco. Esses mapas exibem ativações intermediárias. Para acompanhar decisões
do carrinho, a integração futura deve registrar a transição de estado, a
validade e a idade da previsão, a leitura dos sensores e o motivo do comando.

Consulte [a reprodução e os artefatos do experimento](08_dataset_linha.md#comparação-offline-com-batchnorm).

### Comparação offline com HoughLinesP

`tools/comparar_hough.py` compara Hough, contornos e CNN nas mesmas fotos
rotuladas. Hough analisa pares de bordas em três faixas locais e estima
a posição em y=75% quando encontra um par na faixa central. O relatório
separa cobertura, erro nos quadros comuns e casos ausentes ou ambíguos.
Nos vídeos exploratórios, houve abstenções e seleção de rejunte como fita.
O experimento roda fora do controle. Consulte
[o método e os resultados](08_dataset_linha.md#referência-offline-com-houghlinesp).

### Comparação offline com MobileNetV2

`tools/comparar_mobilenet.py` usa MobileNetV2 pré-treinada e congelada, com
uma regressão de posição em y=75% ajustada nas mesmas divisões por vídeo
da CNN NumPy. No teste exploratório, a CNN NumPy teve menor erro médio.
O subcomando `latencia` mede pré-processamento e inferência por quadro a
partir do modelo salvo. A medição local foi em CPU no Windows. A execução
na Raspberry e a generalização com a ESP32-CAM montada seguem pendentes.
Consulte [o procedimento e os resultados](08_dataset_linha.md#comparação-offline-com-mobilenetv2).

## Quatro mudanças propostas na CNN — todas pendentes

### 1. Adaptar a entrada à ESP32-CAM

Receber JPEGs 320×240 e calibrar orientação e recorte com a câmera montada no
carrinho, preservando área perto e longe da pista. Começar avaliando 80×40;
medir se os pontos distantes continuam distinguíveis antes de aumentar a rede.
Não deformar a geometria para fazer caber um recorte antigo.

O [coletor de bancada](12_esp32_cam_bancada.md#coletar-imagens-com-a-câmera-montada)
já registra a sessão, o recorte e a orientação. A ROI padrão da prévia é
um ponto inicial para o ajuste físico. A prévia versionada usa cinza e
redução com `INTER_AREA`. A normalização da CNN pertence ao contrato futuro
de treino e inferência.

Criar um pré-processamento compartilhado entre coleta, treino e inferência.
Versionar resolução, ROI, orientação, conversão para cinza e normalização junto
dos pesos. Não substituir silenciosamente o tratamento de pesos antigos.
Rever `dataset_rotulado.py`, `dados.py`, `visao/fontes.py` e o receptor de bancada.

### 2. Prever trajetória em três alturas

Prever posições horizontais perto, no meio e longe, em alturas calibradas
dentro da ROI; elas ainda não têm valores definidos. Usar perto para corrigir
alinhamento e as demais para antecipar curvatura e continuidade do pontilhado.
Altura da imagem só vira distância física após calibração geométrica.

Modificar saída, forward/backward, perdas, aumento de dados, métricas,
carregamento de pesos e consumidores das previsões. Os pesos antigos de duas
saídas não são diretamente compatíveis com a nova cabeça. Registrar versão
e validar formato e semântica ao carregar, evitando erro silencioso.

Gerar alvos pela interpolação dos pontos humanos apenas dentro da extensão
anotada. Usar uma máscara por altura para pontos não identificáveis, sem
extrapolar atrás de um obstáculo ou marcar ausência como posição central.
No espelho horizontal, inverter todos os alvos horizontais e preservar máscaras.

### 3. Supervisionar linha ausente ou ambígua

Incluir exemplos positivos e negativos, oclusões por obstáculos e situações
nas quais não existe trajetória identificável. Definir explicitamente o que
significam parcial, ausente e ambíguo para a nova saída de validade; não
transformar os quatro estados em uma probabilidade binária sem essa decisão.
Avaliar também validade por altura, pois pode haver trecho próximo oculto e
trecho distante visível. A escolha final da cabeça ainda está pendente.

Treinar a validade com rótulos humanos e aplicar perda de posição somente nas
alturas válidas. Medir principalmente falsas aceitações de trajetórias
inválidas, além de falsas rejeições; escolher limiares na validação. Não usar
a saída de visibilidade dos pesos atuais como autorização para movimento.

### 4. Treinar novamente com imagens da câmera real

Coletar com a ESP32-CAM instalada: retas, curvas para ambos os lados, vãos do
pontilhado, sombras, mudanças de luz, linha nas bordas, linha ausente,
cruzamentos ambíguos, obstáculos e retorno após desvio. Preservar originais,
metadados da montagem/câmera e revisões humanas.

Separar gravações/sessões para treino, validação e teste antes de treinar.
Não distribuir quadros vizinhos da mesma gravação entre conjuntos. Reservar
gravações novas para avaliação independente e não ajustar o modelo pelo teste.
Registrar erro por altura, desempenho por cenário e casos de falha, comparando
com referências simples e com o modelo de uma posição quando comparável.

## Vãos do pontilhado: começar com memória no controle

Combinar previsões recentes válidas com os encoders durante um intervalo
limitado. Calibrar pulsos por distância, geometria das rodas e sinais; pulsos
sem direção e derrapagem não fornecem odometria precisa automaticamente.
Definir limites de tempo, distância e incerteza para manter uma estimativa.
Reduzir velocidade conforme a incerteza e parar ao exceder os limites, perder
telemetria ou detectar obstáculo. Invalidar memória em parada, troca de modo
e recuperação da câmera, para não aplicar uma trajetória antiga.

Essa memória ainda precisa ser implementada e validada na pista. A política
legada de `aprendizado/politica.py` não comprova esse comportamento. Uma CNN
com sequência de quadros fica para uma etapa posterior, se os testes mostrarem
necessidade; não é a primeira ampliação proposta.

## Obstáculos: colaboração entre sensores, planejador, CNN e controle

1. Ultrassom e servo avaliam distâncias e registram direção, validade e tempo.
2. O planejador futuro escolhe e acompanha o contorno, com critérios de aborto.
3. A CNN auxilia a reencontrar a trajetória e voltar ao seguimento.
4. O controle ajusta as rodas e interrompe movimentos inseguros.

A inspeção atual é parada. Autorizar contorno exige implementar estados,
transições, tratamento de leituras desconhecidas, acompanhamento do progresso
e recuperação da linha. Eco lateral isolado não autoriza avançar; ausência de
eco não significa passagem livre. Definir como obter medições frontais recentes
durante o contorno respeitando o bloqueio atual de movimento durante a inspeção.

Detectar obstáculos pela imagem é uma ampliação separada: adicionar saída
específica e novos rótulos de obstáculos ou espaço livre, com treinamento e
avaliação próprios. A cabeça de linha não tem essa capacidade por inferência.

## Inferência contínua, desempenho e treino parado

Carregar pesos aprovados na Raspberry e processar continuamente o quadro mais
recente, descartando intermediários para não acumular atraso. Publicar junto
da previsão identificador, idade do quadro, validade e versão do modelo.
Ausência de câmera, pesos incompatíveis ou previsão vencida devem invalidar
a ação; não reaproveitar indefinidamente a última previsão.

Os aproximadamente 12 FPS relatados e os CSVs de bancada se referem à
recepção da câmera, não à execução integrada de CNN e controle. Registrar
captura/recepção, decodificação, pré-processamento, inferência, planejamento e
envio ao motor, além da idade da imagem quando a ação é usada. Medir sob carga
real com sensores, voz e Bluetooth, incluindo falhas e recuperação do Wi-Fi.
Os relógios da ESP e da Pi não devem ser subtraídos como se sincronizados.

Treinar somente com o carrinho parado. Separar treino e inferência, promover
pesos após avaliação e manter possibilidade de voltar à versão anterior.
A infraestrutura legada de versões/ciclo é referência, mas não comprova uma
integração da ESP32-CAM nem compatibilidade com a nova cabeça.

## Ordem de trabalho e evidências necessárias

- [ ] Consolidar montagem e ensaios da ESP32-CAM; documentar orientação, foco,
  alimentação, estabilidade e recuperação das desconexões nos CSVs.
- [ ] Calibrar ROI e alturas; confirmar que 80×40 preserva a trajetória distante.
- [ ] Coletar e revisar dados reais com as situações acima e divisão por sessão.
- [ ] Versionar pré-processamento e contrato de pesos; implementar três posições,
  máscaras e validade supervisionada; verificar perdas/gradientes e persistência.
- [ ] Avaliar offline por gravação e cenário, incluindo ausências e oclusões.
- [ ] Integrar inferência sem comandar rodas e medir latência e descarte de dados.
- [ ] Validar encoders e implementar memória limitada, com aborto e parada.
- [ ] Validar seguimento físico progressivamente; depois implementar e avaliar
  planejamento de contorno e recuperação, preservando as proteções existentes.
- [ ] Decidir, a partir das falhas medidas, sobre sequência temporal ou cabeça
  visual de obstáculos. Não são pré-requisitos da primeira versão.

Atualizar este registro a cada mudança e fazer commit das alterações verificadas,
conforme solicitado pelo usuário. Não marcar itens concluídos só porque foram
documentados, simulados ou tiveram recepção de câmera bem-sucedida.

## Etapa 1 ESP32 — 22/11/2026

Fonte opcional `esp32` integrada à fábrica existente, sem ativação padrão,
sem resize, sem mudar detector, PD, aprendizado ou movimento. Receptor HTTP
extraído da ferramenta para `visao/esp32_cam.py`; ferramenta/coletor preservam
imports existentes. Captura em thread guarda apenas último quadro, invalida em
falha/idade e retenta com timeout. Idade conservadora soma cabeçalho ESP, HTTP
e tempo local desde recepção; não é idade física exata. O socket timeout não
constitui prazo absoluto da transferência; a consulta rejeita quadros vencidos
independentemente da thread receptora. Metadados são vinculados ao id atual.
Firmware local só oferece /capture, não streaming MJPEG. HTTP real sem resposta
(timeout de conexão 2 s); resolução física/FPS/latência da câmera não confirmados.
JPEG continua exigindo 320x240 pelo contrato existente, sem redução escolhida.
A fonte pode ser encerrada enquanto uma operação HTTP termina; a thread é daemon,
a espera de encerramento é limitada e não publica após parada.
Integração de segurança no controle ainda depende da Etapa 3: não usar esta
etapa para liberar autonomia. Etapa 2 autorizada posteriormente (registro abaixo). Git ausente; nenhum
repositório substituto inicializado e commit indisponível.

Verificação da Etapa 1: 5 testes novos com HTTP injetado passaram (reuso do
receptor, resolução sem resize, último quadro, metadados, falha/recuperação,
idade e encerramento, JPEG/cabeçalho inválidos). Regressões: 11 testes de
controle, 8 serial/imagem e 14 sonar passaram, todos com hardware simulado.
CSI: 5 passaram; 1 falhou porque Picamera2 está instalado sem câmera, enquanto
o teste espera mensagem de biblioteca ausente. Módulo CSI não foi alterado.
Recuo manual: 12 testes executados, 15 falhas incluindo subtestes; fixture usa
10 cm e o controle exige distância estritamente menor que o limite atual de
10 cm. Falha reproduzida bloqueando importação da nova fonte, sem correção
fora de escopo. Suíte pytest do coletor não executada: pytest indisponível;
CLI do coletor e da bancada abriram --help corretamente. Não houve instalação.
FPS e latência físicos não medidos: câmera inacessível, HTTP 000 em 2,001 s
(timeout de conexão). Nenhum motor, firmware, rede ou serviço foi acionado.

## Etapa 2 OpenCV — 22/11/2026

Implementado modo explícito `DetectorLinha(tracejado=True)`, sem ativar o
seguimento. Reutiliza segmentação/ROI/polaridade existentes e funções de
segmentos/associação da sugestão offline, com padrões offline preservados.
Acrescenta segmentos, trajetória, direção geométrica e qualidade heurística.
Associação limitada a24 candidatos; ambiguidade/baixa qualidade causam
abstenção. Memória de dois pontos por0,3 s, sem frames nem renovação na ausência;
serve só para associar observações presentes. Não autoriza avanço sem linha.
A thread atual continua no detector legado. A integração com validade de câmera,
estado e movimento aguarda a Etapa3. Não houve mudança em PD, ganhos, CNN,
firmware, fonte ativa, rede, serviço, motores ou sensores.

Ferramenta de bancada existente ganhou `--tracejado`, com sobreposição de
segmentos, trajetória e métricas, sem publicar no estado nem acessar motores.
Procedimento e limitações: `docs/12_esp32_cam_bancada.md`, seção Etapa2.

Validação:15 testes novos e39 regressões selecionadas passaram (15 sugestão
OpenCV offline,11 controle,8 serial/imagem,5 fonte ESP32 simulada). Detector
legado comparado com cópia anterior: mesmos resultados em14 imagens sintéticas
(incluindo máscaras e contornos). Em9 fotos existentes, medidas legadas e
sugestões offline idênticas às anteriores; não é avaliação da acurácia nova.
48 arquivos protegidos (controle/estado/main, fonte ESP32, aprendizado e
firmware) conferidos por SHA256 sem alterações. Os testes de sugestão precisaram
de acesso a diretório temporário fora do sandbox; só usam widgets/arquivos
simulados, sem motores. Nenhuma dependência instalada. Falhas antigas de CSI e
recuo registradas na Etapa1 não foram corrigidas nem usadas para declarar a
suíte completa aprovada.

Medição real de CPU nesta Pi5, com900 frames BGR sintéticos320x240 e50 de
warmup: legado média0,293 ms/P95 0,353 ms; tracejado média1,161 ms/P95 1,878 ms,
vazão isolada860,5 quadros/s. Exclui captura/JPEG/GUI/controle e não comprova
FPS integrado, acurácia ou autonomia física. HTTP real inacessível novamente:
código000/timeout2,002 s; resolução real e métricas físicas pendentes.
GUI com câmera real não exercitada neste ambiente. Etapa3 autorizada posteriormente (abaixo).
Commit indisponível porque não há repositório Git válido; nenhum foi criado.

## Etapa 3 — integração da decisão em software, 22/11/2026

ESP32 selecionável por `--fonte-imagem esp32`, sem mudar a fonte padrão ou o
serviço. `ThreadVisao` usa snapshots atômicos, rejeita imagem vencida e publica
posição, direção, qualidade, recepção, idade estimada, id, geração e sessão.
O controle verifica também a saúde da fonte, separando ausência visual de falha.
Nenhum avanço antes da primeira observação válida. Vãos usam só memória numérica,
por até0,6 s desde a observação real, com frames recentes/câmera saudável e saída
reduzida. Não se renova esse prazo com imagens ausentes ou ciclos do controle.
Reconexão, troca de modo, falha, obstáculo e ambiguidade invalidam a memória.
Ultrassom inválido ou V4 manual ainda ativo impedem `SEGUINDO`; regra histórica
do manual preservada. Voz e comandos manuais continuam prioritários.

PD e filtro mantidos exatamente; KP90/KD25/filtro1 preservados. Antecipação
geométrica inicial0,25 da ROI compõe o erro; fator de saída nos vãos0,5 vezes
qualidade e tempo restante. São parâmetros de software, sem calibração física.
`DecisaoLinha` permite simular as mesmas decisões sem escrever nas rodas.
Main envia parada antes/depois dos joins e fecha recursos mesmo em falha parcial.
Encerramento bloqueia comandos tardios; erro na thread de controle encerra o
estado. Parar uma thread isolada continua permitindo reutilizar o estado em
testes de software, mas zera modo e saídas. Nenhum firmware, protocolo, Wi-Fi,
serviço ou arquivo da CNN foi alterado. Aprendizado próprio permanece desativado;
ESP32 com aprendizado ativo é recusado até existir contrato de entrada compatível.

Validação:25 testes novos e63 regressões selecionadas aprovados. O fluxo com
HTTP/JPEG, threads de visão/controle, estado e sensores/rodas falsos exerceu
linha, vão, timeout, falha/reconexão e nova observação. Baseline confirmou o
problema de avanço inicial sem linha; versão nova não avançou nesse cenário.
As duas funções PD/filtro são idênticas ao baseline;48 arquivos protegidos
(aprendizado, firmware e motor) continuam com os mesmos hashes. Não houve
serial física, treino, movimento, upload ou alteração de rede/serviço.

Desempenho CPU isolado,600 JPEGs sintéticos320x240 após50 de aquecimento:
decode+visão+estado+decisão média1,506 ms/P95 2,156 ms, sem comandos de motor.
Não mede FPS/latência da câmera nem autonomia física. GUI integrada e ensaios
mais amplos da Etapa4 ainda pendentes; seguir somente após solicitação do usuário.
Procedimentos e limitações atualizados no guia12. Commit impossível: pasta
continua sem repositório Git válido; nenhum repositório foi inicializado.

## Etapa 4 — teste visual integrado, 22/11/2026

Adicionada `tools/testar_decisao_esp32.py`, sem modificar módulos de operação.
Reutiliza fonte contínua/snapshot, processamento visual e decisão PD existentes.
Motor obrigatoriamente nulo, sem importação/abertura de serial física, voz ou
Bluetooth. O ultrassom é explicitamente simulado (livre100 cm, obstáculo0 cm,
inválido), passando pela guarda existente. Não há opção de motores reais.
A janela mostra imagem/ROI/segmentos/centro/trajetória/erro, decisão simulada,
qualidade, idade, FPS e motivo; vãos são marcados como estimativa. Em falha,
apaga a imagem anterior. Pausa/retomada exige nova observação. Modo sem janela
elimina desenho e GUI; CSV opcional registra ciclos sem renovar frames antigos.
Estatísticas guardam só números e até600 amostras por métrica, sem fila de imagens.

15 testes novos em `tests/test_visual_decisao_esp32.py` passaram com Python do
venv/OpenCV5 e Python do sistema/OpenCV4.10(Qt5), incluindo fluxo HTTP/JPEG
injetado, GUI simulada, bloqueios, vãos, limpeza e CSV.88 regressões selecionadas
anteriores passaram (103 testes únicos ao todo). Prévia de imagens sintéticas
inspecionada; GUI real com câmera ainda não validada. Falhas antigas de outros
cenários permanecem documentadas, sem declarar a suíte completa aprovada.

Captura real tentada fora do sandbox por5,010 s ativos:0 frames,3 falhas,
FPS0/0, sempre PARAR e retorno2. Sem imagens, não há resolução ou latência
físicas medidas. Nenhum número do servidor HTTP falso foi apresentado como
métrica da câmera. Seguir a pista no piso, frenagem, calibração da antecipação,
robustez da detecção e recuperação no Wi-Fi real continuam pendentes. Não houve
movimento físico, treino, instalação, upload, alteração de firmware/protocolo,
rede, serviço, CNN ou padrão da fonte. Procedimentos/limitações no guia12,
seção Etapa4. Commit impossível: diretório sem Git válido, nenhum inicializado.

GET direto adicional confirmou HTTP000/timeout de conexão2,001 s, sem receber
cabeçalhos; acesso à câmera real segue pendente, sem modificar a rede.

## Orquestração temporária do Wi-Fi — preparada em 22/11/2026

`tools/testar_esp32_wifi.sh` usa os perfis existentes do NetworkManager por UUID,
guarda o UUID doméstico ativo e agenda unidade transitória separada de
`robo.service`. O teste existente roda por30 s sem janela, motor nulo e ultrassom
simulado; CSV/log ficam em pasta exclusiva `resultados_esp32_wifi/`. A captura
roda como o usuário original, e somente a troca/retorno de rede usa privilégio.
Trap e ExecStopPost tentam restaurar o perfil anterior, com prazos/tentativas
limitados; nenhuma senha ou configuração permanente de rede é gravada.
Nome fixo da unidade impede testes simultâneos. `--verificar` apenas consulta.

10 testes em `tests/test_esp32_wifi.py` passaram usando nmcli/systemd/sudo/timeout
falsos; sintaxe Bash aprovada. Verificação real somente de leitura confirmou
wlan0 e perfis existentes, inclusive dois perfis Carrinho-CAM. O perfil com
registro anterior de ativação é de4455a9-67ce-4f25-86f3-221e66e67e92. Nenhuma
ativação real ou ensaio30 s foi iniciado antes de apresentar o script para
revisão do usuário. A ferramenta de visão/decisão, firmware, protocolo e
`robo.service` permanecem intactos. Não há novas métricas da câmera nesta tarefa.
Relatório técnico fornecido na conversa; não foi criado arquivo de relatório.
Commit indisponível pela ausência de Git. Retorno efetivo depende de energia,
NetworkManager e rede doméstica disponíveis; os testes não validam essas
condições físicas nem a execução real da unidade transitória.

A checagem `sudo -n true` informou que é necessária senha local. O ensaio
real não foi iniciado: o usuário deve iniciar o script no terminal da Pi,
autenticando sudo localmente. Nenhuma senha deve ser enviada ao Codex.


## Revisao de bloqueios e ensaio individual — 22/11/2026

Implementacao Python autorizada, sem alterar firmware, protocolo, ganhos,
pinos, Bluetooth, encoders, fontes de imagem ou servico. Controle separa eco
invalido/telemetria vencida, obstaculo, espera por novo comando e falha de
encoder. A guarda tambem cobre o envio imediato do callback manual. Liberar
o sensor nao reaplica o pedido antigo; novo comando seguro pode rearmar sem
reiniciar. Falha de encoder observada fica retida na Pi ate novo comando e F8
recente sem falha, evitando retomada automatica apos S limpar a falha no Uno.
Recuo existente foi preservado; sua trava pode liberar com frente segura,
mantendo descartado o comando anterior. Inspecao concluida centraliza e espera
frente livre/nova linha antes da retomada; timeout continua PARADO. Nao ha
desvio. A retomada exige observacao posterior a liberacao; nao basta memoria
do vao, inclusive quando a acao legada de aprendizado e usada.

A ferramenta existente testar_motores agora exige uma roda e modo explicito:
PWM direto par 2..60 ou alvo PI 1..4 pulsos/s, duracao positiva ate 1 s.
Alvo PI nao limita PWM de partida. Verifica dois escopos do servico e fuser,
recusa consultas inconclusivas, exige telemetria de sensores/F8, aborta falhas
e tenta parar/fechar em erro ou interrupcao. Nenhum ensaio fisico foi executado.
Preflight nao substitui coordenacao para impedir outro processo de abrir a
porta depois da checagem; parada por serial depende do enlace e watchdog local.

Primeira rodada: 19 testes novos aprovados; recuo12, controle11, sonar14,
diagnostico7, velocidade20, serial8, servo11 e calibracao8 aprovados. Fixture
antiga do recuo corrigida de10 para9 cm (condicao e estritamente menor que10).
Falhas iniciais de snapshot/instante corrigidas e verificadas novamente.
Teste ESP32 existente:24/25 passaram; uma expectativa antiga permite eco
invalido no manual e agora contradiz a regra solicitada. Arquivo preservado
por pertencer a integracao de outra sessao. Bluetooth: sockets/D-Bus locais
exigiram execucao fora do sandbox;21/25 passaram. Quatro falhas pendentes:
tres expectativas de direcao e uma sessao Blue Dot cujo valor lateral
calculado283 ultrapassa o limite255 ja existente no callback. Os arquivos
Bluetooth nao foram alterados. Nao declarar a suite completa aprovada.
Resultados posteriores dos testes adicionados constam do relato na conversa.

A protecao por eco invalido foi aplicada somente na Pi. Firmware continuo
ainda pode permitir avanco sem eco, e os limiares10/15 ou25/30 e confirmacoes
reais permanecem os existentes. Nao ha validacao no piso, de frenagem ou de
torque. Nenhuma rede, serial fisica ou servico foi acionado. Nao houve conflito
detectado nos hashes dos arquivos protegidos. Commit indisponivel: .git
ausente; nenhum repositorio criado. Este registro atualiza contexto existente;
o relatorio foi fornecido somente na conversa.


## Revisao das cinco falhas pendentes — 22/11/2026

Reproduzidas as cinco falhas antes da correcao. A expectativa de permitir eco
invalido no manual foi atualizada somente no teste de decisao visual; a guarda
de ultrassom nao mudou. Testes RC/analogico ainda esperavam giro no lugar,
contrariando curvas para frente documentadas. Eletrogate esperava intensidade
linear, apesar da zona morta compartilhada ja implementada. Atualizadas essas
expectativas, sem alterar parser, comandos ou prazos Bluetooth.

Identificado defeito real anterior no misturador: recalcular o raio depois
de introduzir avanco na lateral pura multiplicava a intensidade por raiz de2.
Com teto remoto200, retornava283/113 e o callback limitava apenas a255.
Agora preserva o raio antes da conversao da curva:200/80, mantendo sentidos,
zona morta e fator de curva. Acrescentados dois testes para valores conhecidos,
teto reduzido, quadrantes e Eletrogate. Nenhum ganho ou configuracao alterado.

Validacao desta revisao: decisao visual25, remoto27, seguranca22, controle11
e sonar14:99 testes aprovados, zero falhas. Bluetooth usou sockets locais,
BlueZ falso e D-Bus privado, nao hardware. Mensagens de indisponibilidade do
Bluetooth e recusas de CLI pertencem a cenarios negativos esperados.
A tabela anterior somava173 aprovados, com178 testes e5 falhas; contagem
reconferida pelos metodos/funcoes, sem contar repeticoes nem subtestes.
Nao houve serial fisica, movimento, reinicio de servico ou modificacao de
firmware, pinos, ganhos, protocolo ou arquivos de producao da ESP32. Fontes
protegidas conferidas por hash. Commit indisponivel por ausencia de .git;
nenhum repositorio inicializado. Aguardar autorizacao para testes fisicos.


## Encerramento e pendencia serial — 22/11/2026

As alteracoes locais das sessoes foram comparadas com a main remota
1298493f74f9a2e6d591296b34dfe275b47d252c. Recuperados metadados Git em
area separada, sem checkout/reset sobre arquivos locais ou novo historico.
Preservado link simbolico de bibliografia ja versionado; seu destino externo
nao esta disponivel nesta maquina, sem exclusao ou substituicao do link. Fontes Arduino anteriores sao preservadas como estavam; nenhuma
edicao ou gravacao adicional do firmware nesta recuperacao. CSVs, logs,
ambientes, caches e artefatos nao entram nas alteracoes selecionadas.
Validacao integrada selecionada:210 testes simulados aprovados em15 suites,
incluindo ESP32, controle, bloqueios, Bluetooth falso, serial virtual, radar
e ferramenta de Wi-Fi com comandos falsos. Sem serial fisica nesta validacao.

O ensaio fisico autorizado nao validou os motores: primeira tentativa atingiu
timeout externo; segunda foi recusada antes do pulso por telemetria ausente.
Leitura existente por8 s nao obteve snapshot FC. Captura bruta posterior,
somente leitura115200, manteve porta aberta10,521 s e recebeu zero bytes.
Sem F8 reconhecido; nao ha base para culpar motor ou HC-SR04. Servicos ficaram
parados e serial livre; nao reiniciar autonomia antes de resolver a pendencia.
Identificacao USB compativel com Uno R3, VID/PID2341:0043. Kernel registrou
sobrecorrente e desconexoes de varios perifericos as21:33, sem provar causa
atual. Configuracao local compativel com Uno/ATmega328P16 MHz; cache de
compilacao antigo nao identifica o programa gravado. UART usa txByte/UDR0,
FC/F8 automaticos50 ms. PySerial aplica DTR/RTS e limpa buffer internamente
ao abrir, mesmo sem chamada explicita do script; reset pode centralizar servo.
Proximo passo: inspecao de alimentacao, RESET e fiosD0/RX,D1/TX, mantendo
motores/servo sem potencia. Nenhuma nova abertura, alteracao de baud, upload,
loopback, mudanca de watchdog ou teste de movimento foi autorizada no fechamento.
Push e hash final devem ser conferidos no relato do terminal; estas evidencias
nao demonstram autonomia, frenagem, torque ou seguimento fisico validados.
