# CNN e RL conectados a ESP32-CAM

Implementacao de24/11/2026. Inferencia congelada, sem treino durante operacao.
A cadeia e: CameraESP32 compartilhada -> recorte/normalizacao -> RedeLinha ->
politica Q, DQN ou PPO -> estado -> ThreadControle -> Arduino. O painel e a
visao OpenCV continuam consumindo a mesma fonte, sem nova captura HTTP.

A integracao de software existe; nao foi validada com camera ou motores reais.
Nao ha checkpoint RL nesta copia do projeto. As CNNs disponiveis em
`dataset_pista/resultados/treino_posicao_01` e `treino_posicao_02` sao de
localizacao offline: outra semantica e visibilidade nao supervisionada.
Elas nao podem ser ligadas aos agentes sinteticos como se fossem a mesma CNN.
O recorte offline y075 tambem nao cabe diretamente no JPEG320x240. Os novos
carregadores recusam esses contratos, sem adaptar silenciosamente a tarefa.

## Escolha na main

O padrao continua `POLITICA_LINHA = "opencv"` e `CNN_RL_PACOTE = None`.
A fonte ESP32 e o painel permanecem selecionados como na revisao anterior.
Nao reiniciamos servico, nao abrimos serial e nao ativamos movimento nesta tarefa.

Quando os pesos estiverem presentes, com somente uma main/servico usando o Uno:

```bash
python3 main.py --politica cnn-rl-sombra --pacote-cnn-rl modelos/pacote_01/pacote.json
```

Sombra calcula previsoes e acoes e mostra diagnosticos no painel: modo, dominio,
status, acao e tempo de inferencia. Em SEGUINDO, a saida dos motores e zero,
sem fallback para PD. Controle Bluetooth MANUAL continua sendo controle manual.
A main abre serial normalmente; para teste SEM serial use a ferramenta isolada
abaixo. Sem telemetria/duas amostras de encoder, a CNN pode ser calculada,
mas o RL nao recebe velocidade inventada e nao pede movimento.

```bash
python3 tools/testar_cnn_rl_esp32.py \
  --pacote modelos/pacote_01/pacote.json \
  --velocidade-simulada 0 --duracao 10
```

Essa ferramenta nunca cria ArduinoSerial ou escritor de motores. Usa camera
real se ela responder, mas a velocidade e FICTICIA, informada explicitamente
em m/s. Saida JSON marca `velocidade_simulada=true`; nao mede deslocamento.
Retorno2 significa nenhum quadro inferido. Nao execute junto de outra captura
ESP32/main: a ferramenta independente tem sua propria fonte. Nenhuma troca
de Wi-Fi e feita por esses comandos.

Para persistir uma escolha apos os ensaios, use `POLITICA_LINHA` e
`CNN_RL_PACOTE` no config.py; a main do servico usa os mesmos valores.
Nao habilite `APRENDIZADO_ATIVO`: ele pertence ao aprendizado online legado.

## Preparar pesos dos experimentos existentes

Copie a pasta COMPLETA do experimento realizado no outro computador, incluindo
manifesto, CNN e checkpoints, sem escolher politica pelo resultado de teste.
O empacotador nao treina nem modifica esses arquivos e cria uma pasta nova.

Para Q-learning:

```bash
python3 tools/preparar_pacote_cnn_rl.py \
  --experimento dataset_pista/resultados/rl_cnn_simulado_01 \
  --algoritmo q --saida modelos/pacote_q_01
```

Para DQN (PPO usa `--algoritmo ppo` e seu checkpoint):

```bash
python3 tools/preparar_pacote_cnn_rl.py \
  --experimento dataset_pista/resultados/comparacao_dqn_ppo_01 \
  --algoritmo dqn \
  --checkpoint dataset_pista/resultados/comparacao_dqn_ppo_01/dqn_7/melhor.zip \
  --saida modelos/pacote_dqn_01
```

Semente7 e apenas exemplo de caminho; conferir a selecao por validacao.
O empacotador verifica contrato do experimento, hash da CNN e correspondencia
Q/CNN, ou hash do ZIP e algoritmo/semente registrados no experimento DQN/PPO.
Copia os artefatos e grava `pacote.json` com SHA256 de cada arquivo e hash dos
parametros da CNN. Pacotes de simulacao sao marcados `dominio=sintetico` e so
podem operar em sombra. Adaptar resolucao para ver uma previsao em imagem
real nao demonstra transferencia do modelo para o hardware.

Q-learning usa NumPy. Carregar DQN/PPO requer o ambiente opcional de
`requirements-rl.txt`, incluindo Stable-Baselines3/PyTorch. As dependencias
nao foram instaladas nesta tarefa. DQN/PPO carregam em CPU e usam
`predict(..., deterministic=True)`; Q usa argmax sem exploracao. Nenhum chama
learn, atualizacao Q, backpropagation ou salvamento de pesos durante inferencia.
O ensaio real de ZIP DQN/PPO na Pi permanece pendente; os testes de adaptador
usam API injetada por ausencia das dependencias e dos checkpoints locais.

## Contrato de percepcao e observacao

`aprendizado/inferencia_esp32.py` carrega `cnn_rl_esp32_v1`. Sao verificacoes
obrigatorias: par de arquivos com SHA256, hash de parametros CNN, onze acoes
exatas e observacao compativel com o algoritmo. Q tambem guarda e verifica o
hash CNN dentro do checkpoint. Pesos e observacoes nao finitos sao recusados.

Para sombra sintetica: BGR320x240 -> cinza ->160x120 INTER_AREA -> recorte
legado a partir da linha40 -> media2x2 ->40x80 -> normalizacao existente.
Esse adaptador tem nome `simulado_160x120_roi40_v1` e nunca habilita motores.

O contrato para pesos REALMENTE treinados/avaliados na ESP32 e
`esp32_roi_normalizada_v1`: ROI2:1 explicita `[x,y,largura,altura]` no frame
320x240 orientado, cinza, INTER_AREA para80x40 e `dados.normalizar`.
A orientacao e a mesma de `IMAGEM_ESPELHAR_H/V` usada pelo OpenCV e precisa
coincidir com os metadados de treino. A CNN precisa fornecer referencia lateral
normalizada e visibilidade supervisionada; no contrato dos agentes existentes,
a semantica e lateral a10 cm dividida por12 cm. Posicao de pixel em y075 nao
e essa grandeza. Para usar outra representacao, tambem sera necessario treinar
o RL nessa representacao e versionar seu contrato, sem reaproveitar os pesos
atuais como equivalentes. O novo treino real nao foi implementado nesta tarefa.

Q conserva os bins da simulacao. DQN/PPO conservam o vetor de sete valores,
com previsao, delta/2, velocidade normalizada por0,11 m/s, idade por0,6 s,
memoria vigente e direcao/velocidade pedidas anteriormente. Inferencia no
maximo10 Hz; frames intermediarios sao descartados, sem fila. Essas escalas
sao parte do contrato e devem corresponder ao treino, nao uma calibracao fisica.

A velocidade e ESTIMADA pelo delta de contadores E/D e tempo dos pacotes,
com conversao mm/pulso por roda declarada no pacote. Exige duas amostras,
telemetria recente e contadores sem regressao. E modulo medio, sem odometria
direcional; encoders nao fornecem sentido. A conversao65 mm e19,4/19,2 pulsos
por volta dos pacotes sinteticos e provisoria, identificada como nao calibrada.
A validade da velocidade nao substitui as guardas de encoder/ultrassom.

## Controle e bloqueios

`--politica cnn-rl` seleciona o caminho de motores, mas e recusado ANTES de
abrir a serial quando o pacote e sintetico, usa recorte legado, nao tem
visibilidade supervisionada ou encoders calibrados/orientacao correspondente.
Um pacote de dominio real precisa ser produzido a partir do treino real
pareado e da calibracao: mudar o nome do dominio ou marcar booleanos nao
adapta nem valida os pesos. O manifesto e contrato de dados, nao prova de
validacao fisica. Nenhum pacote real foi gerado aqui.

No caminho de controle, RL escolhe direcao/fator de velocidade. O misturador
existente `direcao_para_pwm` converte para pedidos das rodas, sem mudar ganhos
ou limites do projeto. OpenCV permanece SOMENTE como veto de validade visual;
sua direcao PD nao substitui uma acao RL ausente ou invalida. A politica ainda
nao aprende nem planeja um desvio de obstaculo.

Prioridades preservadas:

- Modo PARADO, comando pare/manual, falha de encoder e guardas de sonar.
- Diagnostico F8 recente e sem falha, exigido adicionalmente no controle RL.
- Inspecao de obstaculo parada, sem contorno automatico.
- Falha de camera, geracao de reconexao e idade maxima0,3 s.
- Sessao de modo: resultados anteriores a pare/siga ou manual nao sao aceitos.
- Frame anterior ao inicio da sessao nao vira acao da sessao nova.
- Depois de bloqueio, exige nova observacao visual e nova acao posteriores.
- Vao conserva o prazo0,6 s e reducao existente; nao renova a referencia.
- Sem primeira referencia CNN aceita ou sem velocidade valida: saida zero.
- Erro da inferencia solicita encerramento da main, sem fallback para PD.

Inferencia publica `AcaoRL` imutavel com recepcao ORIGINAL, idade de captura,
id, geracao e sessao. O controle valida esses dados outra vez antes de enviar.
Processar uma imagem nao a torna recente. O tempo indicado no painel mede
pre-processamento/CNN/escolha da acao, nao latencia completa de camera/frenagem.
Gravacao continua sob os botoes do painel, independente da politica selecionada.

## Verificacao e pendencias

26 testes novos passaram: pacote/hashes, CNN incompatível, Q deterministico,
API DQN/PPO injetada, normalizacao, velocidade, inferencia lenta, NaN, troca de
sessao, modo sombra, erro sem fallback, startup da main e ferramenta sem serial.
O fluxo integrado com HTTP/JPEG falsos e threads de visao/CNN/RL/controle
exerceu acao, obstaculo, recuperacao, falha de camera, retorno sem linha e pare.
Todos os motores desse fluxo eram objetos simulados; pesos eram fixtures
artificiais em pasta temporaria, nunca modelos de producao.

Regressoes selecionadas:25 decisao visual,15 simulador visual,11 controle,
22 seguranca,5 fonte ESP32,14 sonar em movimento,13 painel HTTP e3 RL simulado.
Total134 testes aprovados. Nao e uma declaracao de toda a suite aprovada.
CLI, compilacao de sintaxe Python e diff conferidos. Sem treino, abertura de
serial, upload, ensaio fisico, reinicio de servico ou alteracao de rede.

Faltam os checkpoints treinados, dados/avaliacao da CNN real, politica pareada,
calibracao e ensaio de inferencia com a camera fisica. Depois: rodas suspensas,
correcao de direcao, corte pelo obstaculo, perda da camera e parada manual;
so entao ensaio curto no piso. Treinamento somente com o carrinho parado.
