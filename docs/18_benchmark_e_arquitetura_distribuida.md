# Fase 1: diagnóstico e benchmark

Implementação de 25/11/2026 sobre a revisão `d16c55a`. Somente Fase 1.
Não há processamento externo, WebSocket, banco de dados nem novo dashboard.
Nenhum firmware, pino, ganho, limite, configuração de rede ou modelo foi alterado.
Não houve abertura de serial física, upload, reinício de serviço ou teste no piso.

## Diagnóstico da arquitetura

| Área | Implementação atual | Habilitação e limites |
|---|---|---|
| Orquestração | `main.py`, threads Python no mesmo processo | Começa PARADO; supervisiona threads essenciais e para ao encerrar |
| Estado | `estado.py`, `RLock`, leituras/ações imutáveis, sessão visual | Não há barramento externo nem histórico global de eventos |
| Uno | `motor/serial_com.py`, RX dedicado, TX protegido por lock, protocolo binário | USB 115200, `/dev/ttyACM0`, perfil sem câmera; getters reutilizados pelo benchmark |
| Sensores | FC: distância, pulsos acumulados e flags; F8: PWM calculado e flags do PI; servo/sonar/inspeção | Timestamps são de recepção na Pi; pacotes distintos não formam uma amostra física simultânea |
| Controle | `controle.py`, nominal 20 Hz; PD da linha na Pi; PI por roda no Uno | Um caminho de decisão, com callbacks prioritários de parada/manual no módulo controle; o monitor nunca escreve comandos |
| Câmera | `visao/esp32_cam.py`, JPEG 320×240 por HTTP, cabeçalho de idade | Fonte padrão ESP32; thread única, último quadro, geração de reconexão, timeout e invalidação por idade |
| OpenCV | `visao/detector.py`, ROI, cinza, GaussianBlur, Otsu, abertura, contornos/segmentos e associação | Tracejado no caminho ESP32; segue somente após comando; qualidade é heurística |
| CNN | `aprendizado/cnn.py`, NumPy, três convoluções, densa, entrada 1×40×80, BatchNorm opcional | Pesos de fotos y075 são offline e incompatíveis com o contrato dos agentes; visibilidade desses pesos não supervisionada |
| RL | `rl_simulado.py`, `ambiente_gym.py`, Q-learning e adaptadores DQN/PPO | Experimentos sintéticos; integração `inferencia_esp32.py` opt-in; padrão `POLITICA_LINHA=opencv`, pacote ausente |
| Aprendizado legado | `robo_real.py`, ciclo, versões, supervisor, treino e avaliação | `APRENDIZADO_ATIVO=False`; ESP32 com esse aprendizado é recusada na main; não ativado pelo benchmark |
| Voz | `voz/reconhecimento.py`, áudio → VAD → features → mistura LSTM/SVM NumPy ou MLP | Thread criada pela main; classificação apenas com segmento; falha de voz participa da parada |
| Bluetooth | `remoto/bluetooth_spp.py`, BlueZ/D-Bus, SPP/RFCOMM e sessões de socket | Ativo na configuração; pareamento/lista opcional; desconexão encerra movimento manual |
| Painel existente | `tools/painel_coleta.py`, HTTP local 8080, worker de coleta | Preview/JPEG compartilham câmera; gravação por clique; preservado integralmente |
| Simulação | `FonteSimulada`, `ArduinoNulo`, `AmbienteSimulado`, Gym e `tools/simulador_arduino.py` | Fonte e motor nulos são portáveis; serial virtual PTY exige Linux/Unix; dinâmica sintética não é calibração |
| Segurança | Watchdogs do Uno, validade de sensores/câmera/ações, encoders, sessões, parada/inspeção | Implementada em software; validação física integrada permanece pendente |
| Gêmeo digital | Arquivos esperados `gemeo_digital/modelos/carrinho_configurado.glb` e `_eixos.json` | Não encontrados nesta cópia; nenhum modelo substituto criado |

O fluxo padrão permanece ESP32 → snapshot → OpenCV → estado → controle/PD →
serial → Uno/PI → ponte H. Sensores retornam pela mesma serial. Voz e Bluetooth
interrompem ou alteram o estado por funções do controle. A integração CNN/RL
possui caminho próprio validado por contratos, mas depende de pesos pareados
e validação; ver guia 17. Inferência integrada em código não comprova autonomia.

### Divergência de segurança que deve permanecer explícita

O projeto recebido tem `ULTRASSOM_BLUETOOTH_ATIVO=False` e um bypass manual
confirmado no Uno. Portanto, **o Bluetooth manual atual não tem prevenção de
colisão por ultrassom**. O autônomo conserva sua guarda frontal. Isso foi
autorizado anteriormente e não foi revertido nesta Fase 1. A nova exigência de
proteção por ultrassom em eventual controle externo deverá ser atendida antes
de habilitá-lo; qualquer mudança dessa política depende de aprovação do usuário.
Ausência de eco/telemetria não é registrada como caminho livre pelo benchmark.

## Gargalos e riscos encontrados

São pontos identificados no código, não uma declaração de saturação da Pi:

1. O controle mantém `estado.lock` durante decisão e escrita serial. O timeout
   de TX é 100 ms; várias escritas podem exceder o orçamento nominal de 50 ms
   e atrasar outro callback que precise desse lock. Foi instrumentado, não refeito.
2. `time.sleep` e threads Python não garantem periodicidade de tempo real.
   OpenCV/NumPy/BLAS e eventual PyTorch podem disputar núcleos e gerar jitter;
   não foram mudados afinidade, prioridade, número de threads BLAS ou ganhos.
3. A fila de áudio em `ThreadVoz._escutar` é ilimitada. Classificação lenta pode
   acumular blocos e comandos antigos; medir classificação nesta fase. Limitar
   a fila/redefinir descarte exige avaliar VAD e segurança em alteração específica.
4. A captura HTTP sequencial mantém somente o último quadro e decodifica JPEG
   uma vez. Timeout de socket não é prazo absoluto de uma transferência lenta.
   O controle já rejeita idade vencida; benchmark distingue HTTP e decode.
5. Painel e coleta fazem disco/HTTP em threads próprias, mas compartilham CPU,
   memória e disco. A carga cresce com gravação e clientes; comparar ligado e
   desligado sem duplicar captura. O benchmark não abre cliente extra do painel.
6. Logs Bluetooth por bloco estão habilitados. I/O de log frequente pode aumentar
   a carga; a configuração foi preservada para uma comparação identificável.
7. Não há ACK/timestamp correlacionado de comandos no Uno nem sequência de
   captura da ESP32. Não é possível medir RTT serial ou perda ponta a ponta
   somente por intervalos de chegada. Não foram inventadas essas métricas.
8. Telemetria FC/F8 é protegida por locks curtos; o snapshot não é atomicamente
   simultâneo entre pacotes. Pulsos são magnitudes, sem sentido medido.
9. Treino pesado no processo de operação pode competir com supervisão, mesmo
   parado. Permanece desativado; nenhuma rotina de treino é chamada pelo benchmark.

## Implementação

Arquivos novos:

- `monitoramento/__init__.py`: temporizadores opcionais com `perf_counter`,
  contadores, último pedido comandado, buffer limitado e aquisição não bloqueante.
- `monitoramento/sistema.py`: psutil opcional, sysfs CPU/SoC e flags do Pi.
- `monitoramento/telemetria.py`: snapshots de getters existentes e classificação
  de valores medidos, estimados, comandados, simulados, indisponíveis e vencidos.
- `monitoramento/benchmark.py`: worker local, sessões JSONL/manifesto, limites e falhas.
- `tools/benchmark.py`: bancada sistema/sintético/ESP32, sem Arduino, e exportação CSV.
- `requirements-benchmark.txt`: psutil opcional.
- `tests/test_benchmark.py`: testes de instrumentação, falhas, serial/câmera falsas,
  classificação de dados, exportação e limpeza da main.
- Este guia e o plano das próximas fases abaixo.

Arquivos existentes modificados: `main.py` (flags e ciclo de vida opt-in),
`config.py` (parâmetros do benchmark), `.gitignore` (resultados locais),
`controle.py`, `motor/serial_com.py`, `visao/detector.py`, `visao/esp32_cam.py`,
`aprendizado/cnn.py`, `aprendizado/inferencia_esp32.py`, `voz/reconhecimento.py`
(somente ganchos de observação), README e contexto de continuidade.

### Custo e isolamento

Sem `--benchmark`, o registro global é `None`. Não há worker, psutil, arquivo
ou processo novo. Decoradores preservam retorno e exceções da função original.
Com benchmark, produtores apenas registram números/tuplas com lock não bloqueante;
nenhum produtor espera disco, comando externo ou rede. Cada métrica guarda no
máximo 512 amostras por janela; excedentes antigos e disputa de lock são
contabilizados como descarte de instrumentação, nunca como perda da rede.

O worker faz SO e snapshots inicialmente a 1 Hz. `BENCHMARK_INTERVALO_S`
configura a publicação (mínimo 1 s), `BENCHMARK_CAPACIDADE` limita a retenção
por métrica e `BENCHMARK_MAX_BYTES` limita JSONL a 50 MB por sessão. Tempos
internos são observados por execução, sem mudar a frequência de cada módulo.
No Pi, `vcgencmd get_throttled` executa no máximo uma vez por amostra, com
timeout de 200 ms, apenas no worker. Não há subprocesso no ciclo de controle.

Snapshot de estado ocupado é descartado e informado. Outros getters têm locks
curtos de cópia. Resumos/JSON/disco são feitos fora dos locks dos produtores.
Disco cheio, limite de arquivo ou falha do monitor encerram somente o benchmark.
A gravação é síncrona dentro do worker, sem fila ilimitada de gravação. Não
há histórico de rede/offline nesta fase; os buffers são apenas de instrumentação.
O limite vale por sessão; limpar/transferir sessões é responsabilidade do operador.

## Métricas e interpretação

| Grupo | Dados registrados | Natureza/limite |
|---|---|---|
| CPU | total (média dos núcleos), por núcleo, processo | psutil não bloqueante; primeira amostra de CPU é null; CPU do processo pode superar 100% |
| Memória | RAM usada/percentual e RSS deste processo | Não inclui memória de outros processos como se fosse do robô |
| Pi | temperatura CPU/SoC, frequência, subtensão e throttling atuais/desde boot | Null com motivo fora da Pi/sem interface/permissão; flags desde boot não indicam necessariamente problema nesta sessão |
| Rede | bytes RX/TX do host, taxa por delta, erros/descartes da interface | Todas as interfaces; não representa tráfego exclusivo do robô nem perda de mensagem da aplicação |
| OpenCV | `opencv_s` | Tempo de parede de `DetectorLinha.processar`, sem captura/debug |
| CNN | `cnn_s` | `RedeLinha.prever`, incluindo todos os lotes da chamada; não inclui ROI externa; null se inativa |
| RL | `rl_s` | Escolha da política Q/DQN/PPO em `Pacote.escolher`; não é tempo de treinamento |
| Voz | `voz_s` | Features/classificação/tratamento do segmento; não inclui espera por fala ou latência acústica completa |
| Câmera | HTTP, decode, JPEG recebido, válidos/erros/vencidos, FPS acumulado e por janela, idade | HTTP inclui request/cabeçalhos/corpo, não decode; idade é limite conservador, não relógios sincronizados |
| Controle | trabalho do ciclo, período, Hz efetivo e jitter assinado | Trabalho inclui espera pelo lock/serial; jitter = intervalo entre inícios − período nominal; não é latência física de frenagem |
| Visão usada pelo controle | idade da última leitura consultada no ciclo | Não prova que esse frame gerou movimento; conferir modo e motivo |
| Serial | bytes aceitos pela escrita/recebidos, falhas TX/desconexões RX e reconexões existentes, intervalo entre FC | Tempo de escrita inclui lock e repetições; não é RTT nem confirmação de execução |
| Comandos | último alvo PPS ou PWM explícito e pedido de parada, com idade | `pedidos` são intenções observadas, inclusive se serial ausente; pares E/D podem ser antigos; não confirmam ação física |
| Sensores/motores | snapshots FC/F8, flags, ticks, magnitude PPS por delta, servo nominal | F8 informa PWM calculado pelo firmware, não tensão medida; PPS estimado não é leitura interna filtrada do PI |
| Identidade | UUID, sequência, UTC, monotônico, condições, hash do config | Sequência local de amostras; UTC não sincroniza relógios de dispositivos |

`erro_pi`, velocidade em m/s sem calibração apropriada, sentido medido,
recompensa de operação, RTT serial, latência Pi↔PC, perda de mensagens e perda
de capturas na ESP32 ficam `null` com justificativa quando não observáveis.
Não calcular erro interno do PI pela PPS média de 1 s: o Uno usa outra janela
e filtro. Ausência de CNN/RL/voz na janela é null, não tempo zero. No JSON,
`tempos_indisponiveis` explica campos sem observação. No CSV, null vira célula
vazia e os campos de motivo/estado permanecem disponíveis.

Os tempos têm n, média, mínimo, máximo, mediana e p95 **da janela**, não da
sessão inteira. Não obter p95 global fazendo média dos p95. Buffers saturados
enviesam resumos; conferir descartes e aumentar capacidade/publicar menos
eventos antes de usar esses números como evidência acadêmica. O overhead de
`amostragem_trabalho_s` exclui serialização/flush e não mede todo o custo do monitor.

## Executar na Raspberry Pi

Na pasta real do projeto, com o ambiente Python já usado pelo robô ativado:

```bash
python3 -m pip install -r requirements-benchmark.txt

# Sistema operacional; não abre câmera, microfone, Bluetooth ou serial.
python3 tools/benchmark.py --modo sistema --duracao 60 --nota "Pi5; repouso; repeticao 1"

# Reutiliza FonteSimulada e ArduinoNulo; controle permanece PARADO.
python3 tools/benchmark.py --modo simulado --duracao 60 --fps 10 --nota "Pi5; sintetico; repeticao 1"

# Câmera física e OpenCV de bancada; motores nulos e controle PARADO.
python3 tools/benchmark.py --modo esp32 --duracao 60 --url http://192.168.4.1/capture --nota "Pi5; ESP32; bancada"

# Exportação posterior, sem iniciar nenhuma captura ou operação.
python3 tools/benchmark.py --exportar dados_benchmark/UUID_DA_SESSAO
```

Não executar `--modo esp32` ao mesmo tempo que outra main/coleta que já esteja
capturando essa câmera. A ferramenta isolada possui a própria captura; use a
opção abaixo para observar a captura operacional existente, sem duplicá-la:

```bash
# Somente uma main/serviço por Uno. Pare a instância existente antes de usar esta.
python3 main.py --benchmark --benchmark-nota "Pi5; configuracao atual; repeticao 1"
```

A main mantém sua inicialização e espera por comando; `--benchmark` não manda
`siga`, não habilita CNN/RL e não altera rede. Essa execução usa os periféricos
normais do projeto. Encerre com Ctrl+C: o caminho de parada existente tem
prioridade e o worker é encerrado na limpeza. Não execute os comandos neste
PC esperando medir a Raspberry: os recursos são sempre do host executor.

Resultados em `dados_benchmark/UUID/`: `manifesto.json`, `amostras.jsonl` e,
após exportar, `amostras.csv`. A ferramenta informa o UUID. Arquivos não são
versionados. RSS de `--modo sistema` é do script, enquanto `main --benchmark`
mede o processo completo do robô. Se psutil faltar, tempos continuam disponíveis,
mas métricas dependentes dele ficam null; não é equivalente a medir CPU zero.

## Verificações desta entrega

Ambiente: Windows, Python 3.13.2, sem Raspberry, câmera ou motores físicos.
18 testes novos aprovados: temporizador/exceção, buffer limitado, não bloqueio,
jitter, pedido serial sem conexão, HTTP/JPEG falso, null sem psutil, flags Pi
injetadas, sensor vencido, servo comandado, PPS com duas amostras, domínios mistos,
sessão/CSV, falha de disco, teto de arquivo, CLI sem serial/movimento e limpeza da main.

Ensaio local de cinco segundos com `--modo simulado`: seis amostras exportadas,
CPU real do Windows, OpenCV sobre frames sintéticos, controle PARADO com motor
nulo; nenhuma amostra de instrumentação descartada nessa execução. É validação
da ferramenta, não medição de desempenho da Raspberry ou da pista.

A suíte ampla não está integralmente verde. Foram encontrados:

- Integração serial PTY (`test_integracao_robo` e caso de `test_serial_imagem`):
  dependem de `termios`/PTY, indisponíveis no Windows.
- `test_esp32_wifi`: scripts e comandos falsos de Linux, não executam corretamente aqui.
- Um caso de `test_remoto`: espera thread BlueZ viva; `dbus-fast` está ausente neste Python.
- `test_ciclo_completo_sintetico` e `TestAvisos.test_partida_e_cancelamento`:
  falham também em cópia isolada da revisão original `d16c55a`, antes dos ganchos.
  A primeira não produz campeão; a segunda usa Mock sem timestamp numérico.

As falhas anteriores não foram corrigidas fora do escopo. Resultado final da
regressão compatível e comandos de verificação são registrados no contexto de
continuidade; os testes excluídos não contam como aprovados. Nenhuma compilação
ou gravação do Arduino foi necessária, pois nenhum arquivo de firmware mudou.

Resultado da regressão compatível: **349 passed, 1 skipped, 4 deselected,
44 subtests passed** (os 18 testes novos estão incluídos). Reproduzir no Windows:

```bash
python -m unittest discover -s tests -p test_benchmark.py -v
python -m pytest tests -q --ignore=tests/test_integracao_robo.py --ignore=tests/test_esp32_wifi.py -k "not test_ciclo_completo_sintetico and not test_sem_bluez_o_servidor_nao_derruba_nada and not test_cadeia_completa_com_simulador and not test_partida_e_cancelamento" --disable-warnings
```

No ensaio local foram instalados psutil 7.2.2 e pytest 9.2.0 para verificação;
isso não instala dependências nem executa nada na Raspberry. O bit de throttling
é o indicador informado pelo firmware do Pi; isoladamente não identifica a
causa térmica em vez de alimentação. Interpretar com temperatura e subtensão.

## Plano técnico: fases seguintes, ainda não implementadas

| Fase | Entrega proposta | Condição para avançar |
|---|---|---|
| 2 Comunicação | Telemetria somente leitura, sessão/seq/heartbeat, autenticação, reconexão, prazos e filas limitadas; canal de imagens separado com JPEG original | Aprovação do usuário e benchmark real; validar rede com motores parados; sem comandos de movimento |
| 3 Armazenamento | Receptor no PC, SQLite em lotes/worker, sessões/eventos, CSV e descarte documentado | Comunicação medida e esquema versionado com natureza/idade de cada valor |
| 4 Gêmeo | Three.js no PC; GLB original e JSON de eixos, picking, câmera, animações e replay simulado identificado | Arquivos reais presentes; conferir nomes/eixos/pivôs/transformações; pulsos/volta calibrados; sem modelo genérico |
| 5 Dashboard | Integrar gêmeo, gráficos, vídeo, alarmes e histórico em português | Não substituir painel de coleta; comprovar consumo e isolamento dos canais |
| 6 Distribuído | PC fornece percepção/referência; Pi valida sessão, idade, integridade e guarda; controle atual permanece único caminho dos motores | Benchmark justifica a tarefa transferida; RTT/jitter/perda medidos; contrato de pesos; política de segurança aprovada; modo trocado parado e sem retomada automática |
| 7 Experimentos | Repetições embarcado/distribuído, condições e modelos iguais, CSV, FPS/latência/jitter/erro/falhas | Validação progressiva de bancada e piso; separar simulado/real; não selecionar modelo pelo teste |

Para fase 2, comparar servidor leve sobre infraestrutura HTTP existente com
um serviço assíncrono dedicado (por exemplo FastAPI/WebSocket). A escolha
definitiva depende do consumo medido e dos requisitos de múltiplos clientes;
não adicionar ambos de antemão. Endereços, portas, identidade, token e prazos
deverão ser centrais. Monitoramento deve continuar útil sem PC.

Alternativas de rede a avaliar sem alterar a ESP automaticamente:

- **Ethernet PC↔Pi em bancada:** manter Wi-Fi da Pi na Carrinho-CAM e usar uma
  rota separada para o PC; IP/sub-rede devem ser configurados explicitamente.
- **PC e Pi na rede da ESP32:** verificar se SoftAP permite associação dos dois,
  alcance, isolamento entre clientes e banda; não presumir que funcionará.
- **Adaptador Wi-Fi adicional:** interfaces/sub-redes distintas para câmera e PC;
  registrar consumo USB e alimentação, sem assumir capacidade ilimitada.
- **Roteador comum:** exige avaliar modo estação da ESP e, portanto, autorização
  para modificar sua configuração/firmware; não aplicado nesta entrega.

A comparação futura deve registrar versão do código, fonte/resolução/ROI,
modelo e hash, ganhos/limites, pista/iluminação, alimentação/refrigeração,
clientes do painel, duração, aquecimento e número da repetição. Usar várias
repetições, preservar dados brutos e critérios anteriores ao teste. Carga
sintética e uso do host Windows não são resultados experimentais do carrinho.

**Fase 2 aguarda aprovação.** Nenhuma dependência FastAPI, Three.js, banco,
canal de comandos ou modelo de controle externo foi adicionada nesta fase.
