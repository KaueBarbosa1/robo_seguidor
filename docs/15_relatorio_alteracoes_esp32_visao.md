# Relatório completo das alterações: ESP32-CAM, visão e decisão

Data do registro: 22/11/2026. Projeto: `robo_seguidor`.

Este documento consolida **as quatro etapas desta conversa**, não alterações
históricas anteriores do projeto. Antes deste relatório foram **6 arquivos
adicionados e 10 modificados**, sem exclusão de arquivos. O próprio relatório
é uma adição documental desta solicitação: **17 arquivos no escopo consolidado**.

A implementação e os testes de software estão disponíveis. O seguimento físico
no piso e a integração com a câmera real **não estão validados**: a câmera não
respondeu às tentativas de captura. Não houve movimento físico pelo assistente.

## Como ler este relatório

1. O inventário lista todos os arquivos desta tarefa, separados entre novos e modificados.
2. As seções seguintes explicam o que mudou, o que foi preservado, os parâmetros,
   os testes e as limitações.
3. Os anexos incluem o conteúdo integral dos seis arquivos novos, diffs dos cinco
   módulos para os quais há cópia anterior à primeira edição nesta tarefa, o
   conteúdo atual dos outros três arquivos Python modificados e os registros
   documentais acrescentados aos guias.

Os anexos são cópias documentais para consulta, não implementações adicionais.
Eles representam o estado no momento deste registro; os links apontam aos
arquivos de trabalho. O projeto não tem `.git`, portanto **não há um diff Git
completo ou commits**. Não foi inicializado outro repositório. As diferenças
incluídas foram calculadas a partir de cópias temporárias feitas durante as
etapas; o texto dos diffs está embutido aqui e não depende de preservar `/tmp`.
Onde não havia cópia inicial, o relatório identifica a limitação em vez de
inventar uma versão anterior.

## Inventário dos arquivos adicionados

| Arquivo | Etapa e finalidade |
|---|---|
| [visao/esp32_cam.py](../visao/esp32_cam.py) | 1 e 3 — receptor HTTP compartilhado e fonte contínua com metadados e geração de conexão. |
| [tests/test_esp32_fonte.py](../tests/test_esp32_fonte.py) | 1 — cinco testes da recepção/fonte e compatibilidade da ferramenta anterior. |
| [tests/test_detector_tracejado.py](../tests/test_detector_tracejado.py) | 2 — quinze testes de segmentos, direção, polaridade, ROI e memória visual. |
| [tests/test_decisao_visao.py](../tests/test_decisao_visao.py) | 3 — vinte e cinco testes da integração visual/PD e segurança, sem hardware físico. |
| [tools/testar_decisao_esp32.py](../tools/testar_decisao_esp32.py) | 4 — teste visual/sem janela com motor nulo e ultrassom simulado. |
| [tests/test_visual_decisao_esp32.py](../tests/test_visual_decisao_esp32.py) | 4 — quinze testes da prévia, CSV, decisões e encerramento. |

## Inventário dos arquivos modificados

| Arquivo | Etapa e finalidade |
|---|---|
| [visao/fontes.py](../visao/fontes.py) | 1 — registra a opção esp32 na fábrica existente. |
| [tools/testar_esp32_cam.py](../tools/testar_esp32_cam.py) | 1 e 2 — importa o receptor compartilhado e acrescenta --tracejado. |
| [config.py](../config.py) | 1, 2 e 3 — parâmetros opcionais da ESP32, detecção e continuidade; padrões de operação preservados. |
| [visao/detector.py](../visao/detector.py) | 2 e 3 — modo tracejado, depuração, vínculo com idade/sessão/geração e publicação dos resultados. |
| [visao/sugestao.py](../visao/sugestao.py) | 2 — parametriza a extração geométrica compartilhada sem alterar os padrões offline. |
| [estado.py](../estado.py) | 3 — metadados imutáveis, sessão visual e proteção de encerramento. |
| [controle.py](../controle.py) | 3 — integra o erro visual ao PD, bloqueios de segurança e continuidade temporal limitada. |
| [main.py](../main.py) | 3 — seleção da fonte por argumento, passagem da fonte ao controle e limpeza segura. |
| [docs/12_esp32_cam_bancada.md](12_esp32_cam_bancada.md) | 1 a 4 — guias, comandos, métricas, testes e limitações da integração. |
| [docs/13_contexto_e_plano_cnn.md](13_contexto_e_plano_cnn.md) | 1 a 4 — registros de continuidade e distinção entre implementação e validação física. |

## Arquivo acrescentado nesta solicitação

- [docs/15_relatorio_alteracoes_esp32_visao.md](15_relatorio_alteracoes_esp32_visao.md):
  este relatório. Sua criação não modifica código, configuração, serviços ou hardware.

## Etapa 1 — integração da fonte ESP32-CAM

### `visao/esp32_cam.py`

- O receptor HTTP já existente na ferramenta de bancada foi extraído para um
  módulo compartilhado. Não foi criada uma segunda implementação do receptor.
- `QuadroESP32`, `receber_quadro()` e `receber()` mantêm JPEG, imagem decodificada,
  recepção monotônica/UTC, tempo HTTP e estimativa de idade.
- `CameraESP32` executa GETs sucessivos em uma thread, com timeout e retentativas,
  mantendo somente o último quadro. Não há fila de imagens.
- Valida resposta JPEG, integridade, cabeçalho de idade e resolução 320×240,
  conforme o contrato que o receptor anterior já exigia. Não redimensiona.
- Oferece `iniciar()`, `parar()`, `id_atual()` e `proximo_quadro()`, compatíveis
  com as fontes existentes.
- A Etapa 3 acrescentou `saude()`, geração de conexão,
  `proximo_quadro_detalhado()` e metadados associados atomicamente ao mesmo id.
  Uma falha ou expiração invalida o quadro e impede reutilizar memória após recuperar.
- Idade usada no controle = estimativa na recepção + tempo monotônico na Pi
  desde a recepção. Não são subtraídos relógios não sincronizados.
- O timeout de socket não é um prazo absoluto para a transferência inteira;
  a validade do quadro é verificada independentemente da conclusão da captura.

### `visao/fontes.py`

`criar_fonte("esp32")` instancia a nova fonte usando `ESP32_*`. Arduino, CSI,
simulada e nenhuma continuam disponíveis. Não foi alterado o protocolo serial.

### `tools/testar_esp32_cam.py`

A ferramenta passou a importar o receptor de `visao/esp32_cam.py`, preservando
os nomes que o coletor e os testes anteriores importam. A Etapa 2 acrescentou
`--tracejado`, com segmentos/ROI/trajetória/erro e tempo da visão na prévia.
O modo original de recepção continua disponível. Falha HTTP limpa a memória
visual. O formato anterior de CSV da bancada foi preservado.

## Etapa 2 — detecção leve do tracejado

### `visao/detector.py`

- `DetectorLinha(tracejado=True)` acrescenta um modo explícito de tracejado.
  `DetectorLinha()` permanece no caminho legado.
- Reutiliza ROI, escala de cinza, contraste, Otsu/limiar fixo e abertura 3×3.
  Linha clara/escura continua controlada por `LINHA_ESCURA`.
- `BLUR_KERNEL=1` permite dispensar suavização; o padrão 3 foi preservado.
- Usa a extração de segmentos e associação geométrica existentes na sugestão
  offline, sem executar a normalização de fundo 51×51, CLAHE ou vários limiares.
- Limita candidatos e se abstém quando há ambiguidade ou suporte insuficiente.
- `ResultadoLinha` ganhou `segmentos`, `trajetoria`, `direcao`, `confianca` e
  `motivo`, mantendo os campos anteriores.
- `cx/cy` usa o meio da ROI limitado à extensão sustentada no modo tracejado;
  o erro horizontal mantém a convenção positivo = linha à direita.
- Direção é geométrica (`dx/dy` para o alto da imagem). Qualidade é uma
  heurística de contraste/extensão/suporte, **não probabilidade calibrada**.
- A memória visual guarda somente dois pontos e um horário, por até 0,3 s,
  para associar observações presentes. Ausência retorna `achou=False` e não
  renova a referência. `limpar_historico()` permite invalidá-la explicitamente.
- A depuração desenha segmentos aceitos, trajetória, centro e qualidade.

### `visao/sugestao.py`

`_segmentos()` ganhou parâmetros opcionais de área, altura, alongamento e limite
de candidatos. O agrupamento `_trajetoria()` existente foi reutilizado. Os
padrões usados pela revisão offline foram preservados. Os limites em tempo de
execução são escolhidos pelo detector, sem duplicar o algoritmo geométrico.

## Etapa 3 — integração com estado e tomada de decisão

### `estado.py`

- `Leitura` ganhou idade estimada na captura/recepção, id, saúde da câmera,
  geração, sessão, direção, escala geométrica, qualidade e motivo.
- `Leitura.idade(agora)` calcula a idade crescente sem renovar o frame.
- `publicar_leitura()` aceita metadados, timestamp explícito e sessão opcional,
  mantendo a chamada antiga de dois argumentos.
- Mudanças de modo invalidam a sessão visual. Um resultado de uma sessão
  anterior não pode reativar movimento após pare/manual/giro.
- `encerrar()` e a flag de encerramento recusam comandos/publicações tardios.
  O estado compartilhado continua protegido pelo mesmo RLock.

### Ponte visual em `visao/detector.py`

`ThreadVisao` seleciona o modo tracejado quando a fonte oferece o snapshot com
metadados. `_camera_valida()` e `_processar_detalhado()` verificam idade/geração
antes e depois do processamento e publicam o resultado para a sessão correta.
Mudança de sessão/geração limpa a referência visual. Os espelhamentos existentes
são respeitados. Esperar um id novo não fabrica ausência de linha nem renova
uma observação anterior. Exceção visual sinaliza parada do sistema.

### `controle.py`

- Acrescenta `DecisaoLinha` e `ThreadControle.decidir_linha()`, permitindo testar
  a decisão sem escrever nos motores. O loop operacional mantém a decisão/envio
  sob o lock e combina as guardas de ultrassom/inspeção já existentes.
- **Não avança sem uma observação inicial válida.** Corrige o comportamento
  anterior que podia manter avanço dentro da tolerância inicial sem ver a linha.
- Confere saúde/geração da câmera em cada decisão, independentemente de uma nova
  publicação visual; falha e recuperação entre dois ciclos invalidam memória.
- Rejeita idade vencida, números inválidos, sessão antiga e baixa qualidade.
- Usa posição e direção no erro que entra no PD. A antecipação geométrica é
  limitada e não é conversão para deslocamento ou velocidade física.
- Durante ausência visual curta, conserva a última geometria confiável, somente
  com câmera saudável e frames recentes. O prazo vem da última observação real,
  não do ciclo do controle ou de um novo frame sem linha.
- A saída nos vãos é reduzida por fator configurado, qualidade e tempo restante.
  Após vão, zera a derivada ao recuperar a linha, evitando salto por ausência.
- Falha, obstáculo, ambiguidade e perda prolongada limpam a memória. Liberar o
  bloqueio exige nova observação; não retoma por estimativa antiga.
- Em `SEGUINDO`, eco inválido/telemetria vencida ou modo manual V4 ainda ativo
  bloqueiam o avanço. A exceção histórica de eco ausente no manual foi preservada.
- Voz e manual mantêm prioridade; encerramento/exceção enviam parada.

As funções `calcular_motores()` e `filtrar_derivada()` foram comparadas com a
cópia anterior e permanecem **textualmente idênticas**. Os ganhos foram mantidos.
A proteção inicial/por idade e a composição geométrica do erro são mudanças
intencionais do comportamento, não mera troca de câmera.

### `main.py`

- Acrescenta `--fonte-imagem`, sem mudar `FONTE_IMAGEM` por padrão.
- Passa a fonte ao controle, permitindo observar saúde e geração.
- ESP32 com aprendizado ativo é recusada antes de criar/abrir o Arduino,
  pois os contratos de imagem/pesos atuais ainda não são compatíveis.
- Preserva as threads de visão, controle, voz e Bluetooth existentes.
- Garante limpeza mesmo em inicialização parcial; envia parada antes de esperar
  threads e novamente antes de fechar a serial. Sinais de encerramento invalidam
  o estado para impedir comandos tardios.

## Etapa 4 — teste visual e coleta de métricas sem motores

### `tools/testar_decisao_esp32.py`

- Usa `CameraESP32`, o processamento visual da Etapa 3, a orientação existente
  e `ThreadControle.decidir_linha()`. Não implementa um segundo controlador.
- `MotorTeste` herda de `ArduinoNulo`; o ultrassom é fictício e identificado
  na janela/terminal/CSV. Não existe opção para habilitar motores reais.
- Não inicia voz/Bluetooth nem abre serial física. Os valores E/D calculados
  são mostrados sem envio de comandos de movimento.
- Mostra frame, ROI, segmentos, trajetória, centro, erro horizontal/de controle,
  direção, qualidade, decisão esquerda/direita/reto/parar, motivo, conexão,
  FPS de captura/visão, tempos HTTP/visão/decisão e idades.
- Distingue observação da estimativa nos vãos; apaga imagem inválida/vencida.
- Permite pausa/retomada e cenários fictícios de ultrassom por teclas.
- `--sem-janela` elimina desenho/GUI; `--duracao` limita o ensaio.
- CSV opcional não sobrescreve arquivo existente. Repetir um ciclo sem frame
  novo não incrementa o contador de processamento nem renova a observação.
- Médias usam amostras válidas; P95 usa até 600 amostras recentes por métrica.
  Esse histórico contém apenas números, não imagens.
- Encerramento por q, Ctrl+C ou exceção fecha a fonte e mantém saída nula.

## Parâmetros acrescentados em `config.py`

Valores lidos do código no momento deste relatório. São parâmetros iniciais,
sem calibração de seguimento/frenagem no piso.

| Parâmetro novo | Valor atual |
|---|---|
| `ESP32_URL` | `'http://192.168.4.1/capture'` |
| `ESP32_TIMEOUT_S` | `1.0` |
| `ESP32_IDADE_MAX_S` | `0.3` |
| `ESP32_RECONEXAO_S` | `0.5` |
| `TRACEJADO_MAX_SEGMENTOS` | `24` |
| `TRACEJADO_MEMORIA_S` | `0.3` |
| `TRACEJADO_AMBIGUIDADE` | `0.85` |
| `TRACEJADO_CONFIANCA_MIN` | `0.25` |
| `TRACEJADO_ANTECIPACAO` | `0.25` |
| `TRACEJADO_VAO_FATOR` | `0.5` |

A antecipação normaliza direção × altura da ROI pela meia largura do frame e
limita o erro a [-1, 1]. Nos vãos, o fator de saída é:

```text
TRACEJADO_VAO_FATOR × qualidade_anterior × (1 − idade_da_observação / prazo)
```

Essa expressão reduz o pedido calculado, não comprova uma velocidade física.

## Configurações e componentes preservados

| Configuração existente | Valor mantido |
|---|---|
| `FONTE_IMAGEM` | `'arduino'` |
| `APRENDIZADO_ATIVO` | `False` |
| `FIRMWARE_COM_CAMERA` | `False` |
| `SERIAL_BAUD` | `115200` |
| `KP` | `90.0` |
| `KD` | `25.0` |
| `KD_FILTRO` | `1.0` |
| `PERDA_LINHA_TIMEOUT_S` | `0.6` |
| `LEITURA_VALIDADE_S` | `0.3` |
| `ROI_INICIO` | `0.5` |
| `LINHA_ESCURA` | `True` |
| `BLUR_KERNEL` | `3` |
| `USAR_OTSU` | `True` |
| `LIMIAR_FIXO` | `100` |
| `CONTRASTE_MIN` | `40` |
| `AREA_MIN` | `40` |
| `MOSTRAR_DEBUG` | `False` |

Não foram modificados nesta tarefa:

- Arquivos da CNN e do aprendizado em `aprendizado/`; não houve treino ou troca de pesos.
- Firmware do Uno/ESP32, pinagens ou implementação da ponte H, encoders, ultrassom e servo.
- Protocolo serial e módulos de comunicação/acionamento em `motor/`.
- Serviço `deploy/robo.service`, configurações Wi-Fi ou firmware gravado.
- Voz e Bluetooth, fontes Arduino/CSI/simulada/nenhuma e o coletor existente.

O código-fonte ESP32 disponível oferece `/capture`, não streaming MJPEG.
Nenhum firmware foi alterado para adicionar streaming. A arquitetura continua
fonte → visão → estado → controle → Arduino; o teste visual usa somente motor nulo.

Na conferência da Etapa 4, 61 arquivos de operação foram comparados por SHA256
com o estado anterior àquela etapa e permaneceram intactos. Isso não significa
que controle/visão não mudaram nas etapas anteriores; significa que a Etapa 4
acrescentou apenas ferramenta, testes e documentação.

## Testes executados e limites das evidências

### Arquivos de testes novos

| Arquivo | Testes |
|---|---:|
| `tests/test_esp32_fonte.py` | 5 |
| `tests/test_detector_tracejado.py` | 15 |
| `tests/test_decisao_visao.py` | 25 |
| `tests/test_visual_decisao_esp32.py` | 15 |
| Total de testes novos | 60 |

Ao final da Etapa 4, **103 testes selecionados únicos passaram**: os 60 novos e
43 existentes (11 controle, 8 serial virtual/imagem, 14 sonar, 7 diagnóstico
manual e 3 sinalização). A suíte nova da prévia também passou com Python do
sistema/OpenCV 4.10.0 Qt5 e com venv/OpenCV 5.0.0.

Na Etapa 2, mais 15 testes da sugestão offline passaram; o agrupador foi
comparado com sua versão anterior. O detector legado produziu resultados
idênticos em 14 quadros sintéticos; em 9 fotos existentes, as medições legadas e
as sugestões offline permaneceram idênticas. Essas comparações não medem a
acurácia da nova detecção em uma pista independente.

Comparação do avanço inicial: a versão anterior solicitou avanço sem uma
observação visual no cenário simulado; a versão nova manteve saída zero.
O fluxo HTTP/JPEG → visão → estado → PD foi exercitado com câmera/sensores/
motores falsos, incluindo perda, reconexão, vãos e nova observação.
A prévia de imagens sintéticas foi inspecionada. Janela/teclas/limpeza foram
testadas com GUI simulada; não houve sessão gráfica real recebendo a câmera.

**Não se declarou a suíte completa do projeto aprovada.** Nas primeiras etapas,
a suíte CSI apresentou uma falha porque Picamera2 estava instalado sem câmera,
mas o teste esperava mensagem de biblioteca ausente. A suíte de recuo registrou
15 falhas, incluindo subtestes, por cenário com 10 cm enquanto o controle usa
limite estritamente menor que 10 cm. Essas pendências anteriores não foram
corrigidas. Os testes pytest do coletor não foram executados por indisponibilidade
de pytest; suas interfaces/imports foram preservados. Nenhuma dependência foi instalada.

## Métricas efetivamente medidas

| Ensaio | Ambiente/entrada | Resultado | O que não mede |
|---|---|---|---|
| Etapa 2: detector legado | Pi 5, 900 BGR sintéticos 320×240, após 50 de aquecimento | Média 0,293 ms; P95 0,353 ms; 3406,2 quadros/s de processamento | Captura, JPEG, GUI, controle ou acurácia |
| Etapa 2: detector tracejado | Mesmo ensaio | Média 1,161 ms; P95 1,878 ms; 860,5 quadros/s de processamento | FPS da câmera ou autonomia |
| Etapa 3: JPEG + visão + estado + decisão | Pi 5, 600 JPEGs sintéticos 320×240, após 50 de aquecimento | Média 1,506 ms; P95 2,156 ms; 663,4 passos/s de CPU | Rede/câmera/GUI/escalonamento entre threads |
| Etapa 4: tentativa de câmera real fora do sandbox | 5,010 s ativos, motor nulo | 0 frames, 3 falhas, sempre PARAR, retorno 2 | Sem amostras para resolução ou latência físicas |
| GET direto adicional fora do sandbox | `/capture` | HTTP 000; timeout de conexão em 2,001 s, sem cabeçalhos | Não confirma formato/resolução do firmware gravado |

Os tempos CPU foram medidos na Raspberry Pi 5 Model B Rev 1.1, Python 3.13.5,
OpenCV 5.0.0 com quatro threads. São medições locais com imagens sintéticas,
não FPS integrado ou prova de seguimento físico. O resumo da câmera real
manteve HTTP/idade/resolução nulos por falta de imagens. Não se usaram medidas
de HTTP falso como resultado da ESP32 real.

## Comandos para consultar e testar sem movimentar hardware

Com sessão gráfica e a Raspberry já conectada à rede da câmera:

```bash
cd /home/carrasco/Downloads/robo_seguidor
/usr/bin/python3 tools/testar_decisao_esp32.py --csv esp32_decisao_01.csv
```

Sem janela, para registrar métricas:

```bash
/usr/bin/python3 tools/testar_decisao_esp32.py \
  --sem-janela --duracao 30 --csv esp32_decisao_sem_janela_01.csv
```

Teclas: 1 livre fictício, 2 obstáculo fictício, 3 leitura fictícia inválida,
p/espaço pausar e q sair. Escolha nomes novos para CSV, pois não há sobrescrita.
O teste não lê ultrassom real nem executa manobras físicas.

Testes novos:

```bash
PYTHONDONTWRITEBYTECODE=1 venv/bin/python tests/test_esp32_fonte.py
PYTHONDONTWRITEBYTECODE=1 venv/bin/python tests/test_detector_tracejado.py
PYTHONDONTWRITEBYTECODE=1 venv/bin/python tests/test_decisao_visao.py
PYTHONDONTWRITEBYTECODE=1 venv/bin/python tests/test_visual_decisao_esp32.py
```

A aplicação principal aceita `--fonte-imagem esp32`, mas o padrão não foi
trocado. O teste seguro acima é a ferramenta de simulação, não uma autorização
para lançar a aplicação com motores reais. Na main com `--sem-arduino`, o
ArduinoNulo não tem ultrassom e bloqueia seguimento; a ferramenta visual injeta
sensores fictícios explicitamente para permitir observar a decisão.

## O que continua pendente

- Acessibilidade, resolução e estabilidade da ESP32 física; reconexão no Wi-Fi real.
- Ajuste da câmera montada, foco, orientação, ROI, limiares e qualidade na pista real.
- FPS e latência integrados com captura real e demais componentes ativos.
- Calibração da antecipação/velocidade, avaliação de falsos positivos e vãos reais.
- Frenagem, seguimento físico no piso, proteção integrada e autonomia física.
- Contrato de entrada e visibilidade dos pesos próprios antes de integrar a CNN.
- Correção das pendências antigas de testes, quando autorizada como tarefa separada.

Não foi feita movimentação física, treino, upload, mudança de rede/serviço ou
instalação de dependências. O relatório é documentação; sua criação não executa
testes físicos nem altera o comportamento implementado.

## Anexo A — diferenças recuperadas de cópias anteriores

Os cinco arquivos abaixo têm cópia anterior à sua primeira edição nesta tarefa.
Os diffs embutidos mostram as alterações até o estado deste relatório. Não são
extraídos de Git. Nomes e datas temporários foram substituídos por rótulos para
facilitar a leitura, sem alterar as linhas comparadas.

<details>
<summary>visao/detector.py — diferença completa disponível</summary>

```diff
--- antes/visao/detector.py
+++ atual/visao/detector.py
@@ -4,11 +4,10 @@
 quem converte erro em comando e escreve na serial é o controle (controle.py).
 Assim existe um único ponto de decisão e a hierarquia "voz > visão" fica garantida.
 
-Integração CNN/ESP32-CAM pendente: carregar pesos compatíveis, usar o quadro
-mais recente com pré-processamento idêntico ao treino e publicar trajetória,
-validade e idade sem escrever nos motores. Esta thread ainda usa OpenCV.
-Memória para vãos e planejamento de desvio pertencem a etapas próprias;
-ver docs/13_contexto_e_plano_cnn.md.
+ESP32 usa snapshots com idade e geração de conexão; o OpenCV tracejado publica
+posição/direção/qualidade para o PD e sua memória limitada em controle.py.
+A integração de pesos CNN compatíveis e o planejamento de desvio permanecem
+pendentes; ver docs/13_contexto_e_plano_cnn.md.
 """
 import logging
 import threading
@@ -33,10 +32,18 @@
     binaria: np.ndarray | None = None
     contorno: np.ndarray | None = None
     y0: int = 0
+    segmentos: tuple[tuple[float, float, float, float], ...] = ()             # extremos (x1,y1,x2,y2) no frame inteiro
+    trajetoria: tuple[tuple[float, float], ...] = ()            # pontos (x,y) medidos/associados, sem frames
+    direcao: float = 0.0              # dx/dy para frente (alto da imagem); + = direita
+    confianca: float = 0.0            # qualidade geométrica heurística, não probabilidade
+    motivo: str = "legado"
 
 
 class DetectorLinha:
-    def __init__(self):
+    def __init__(self, tracejado: bool = False):
+        # Opt-in até a integração de segurança da Etapa 3. Caminho legado intacto.
+        self._tracejado = tracejado
+        self.limpar_historico()
         k = cfg.BLUR_KERNEL | 1       # garante ímpar
         self._k = (k, k)
         self._kernel = np.ones((3, 3), np.uint8)
@@ -48,15 +55,25 @@
         roi = frame[y0:, :]
 
         cinza = roi if roi.ndim == 2 else cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
-        suave = cv2.GaussianBlur(cinza, self._k, 0)
+        suave = cinza if self._k == (1, 1) else cv2.GaussianBlur(cinza, self._k, 0)
+        if self._tracejado:
+            agora = time.monotonic()
+            if (self._forma != frame.shape or agora < self._referencia_t or
+                    agora - self._referencia_t > cfg.TRACEJADO_MEMORIA_S):
+                self.limpar_historico()
+            self._forma = frame.shape
         if int(suave.max()) - int(suave.min()) < cfg.CONTRASTE_MIN:   # piso liso: não há linha
-            return ResultadoLinha(False, binaria=np.zeros_like(suave), y0=y0)
+            return ResultadoLinha(False, binaria=np.zeros_like(suave), y0=y0,
+                                  motivo="contraste_insuficiente" if self._tracejado else "legado")
         if cfg.USAR_OTSU:
             _, binaria = cv2.threshold(suave, 0, 255, self._tipo + cv2.THRESH_OTSU)
         else:
             _, binaria = cv2.threshold(suave, cfg.LIMIAR_FIXO, 255, self._tipo)
         binaria = cv2.morphologyEx(binaria, cv2.MORPH_OPEN, self._kernel)   # tira ruído fino
 
+        if self._tracejado:
+            return self._processar_segmentos(suave, binaria, y0, agora)
+
         contornos, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
         if not contornos:
             return ResultadoLinha(False, binaria=binaria, y0=y0)
@@ -81,6 +98,76 @@
         centro = w / 2.0
         erro = (cx - centro) / centro
         return ResultadoLinha(True, erro, cx, cy, binaria, maior, y0)
+
+
+    def limpar_historico(self):
+        """Descarta só referência geométrica: nunca guarda frames/máscaras."""
+        self._referencia = None
+        self._referencia_t = 0.0
+        self._forma = None
+
+    def _processar_segmentos(self, cinza, binaria, y0, agora):
+        from visao.sugestao import _segmentos, _trajetoria
+
+        h, w = binaria.shape
+        def ausente(motivo):
+            return ResultadoLinha(False, binaria=binaria, y0=y0, motivo=motivo)
+
+        # Mesmo limiar/ROI do detector original; contraste com sinal de polaridade.
+        primeiro = binaria != 0
+        if not primeiro.any() or primeiro.all():
+            return ausente("sem_contraste_com_piso")
+        contraste = float(cinza[~primeiro].mean()) - float(cinza[primeiro].mean())
+        if not cfg.LINHA_ESCURA:
+            contraste = -contraste
+        if contraste < cfg.CONTRASTE_MIN:
+            return ausente("contraste_insuficiente")
+        candidatos = _segmentos(binaria, area_min=cfg.AREA_MIN,
+                                fracao_area_max=.35, fracao_altura_max=1.,
+                                alongamento_max=10000,
+                                max_candidatos=cfg.TRACEJADO_MAX_SEGMENTOS)
+        if not candidatos:
+            return ausente("sem_segmentos_compativeis_ou_excesso")
+        caminho, score = _trajetoria(candidatos, h, w, self._referencia)
+        if not caminho:
+            return ausente("sem_trajetoria")
+        # Uma alternativa independente de qualidade próxima é ambígua.
+        usados = {id(s) for s in caminho}
+        outro, nota = _trajetoria([s for s in candidatos if id(s) not in usados],
+                                  h, w, self._referencia)
+        if outro and nota >= cfg.TRACEJADO_AMBIGUIDADE * score:
+            separacao = abs(np.mean([s['x'] for s in outro]) -
+                            np.mean([s['x'] for s in caminho]))
+            if separacao > max(4., w * .02):
+                return ausente("trajetorias_ambiguas")
+        pontos = np.array([caminho[0]['extremos'][0]] +
+                          [[s['x'], s['y']] for s in caminho] +
+                          [caminho[-1]['extremos'][1]], dtype=float)
+        pontos = pontos[np.argsort(pontos[:, 1])]
+        extensao = pontos[-1, 1] - pontos[0, 1]
+        if extensao <= 0:
+            return ausente("extensao_insuficiente")
+        # Referência no meio da ROI, limitada à extensão realmente sustentada.
+        y = float(np.clip(h / 2., pontos[0, 1], pontos[-1, 1]))
+        x = float(np.interp(y, pontos[:, 1], pontos[:, 0]))
+        direcao = float((pontos[0, 0] - pontos[-1, 0]) / extensao)
+        confianca = float(min(1., contraste / max(2 * cfg.CONTRASTE_MIN, 1)) *
+                          min(1., extensao / max(.5 * h, 1)) *
+                          min(1., sum(s['area'] for s in caminho) / max(3 * cfg.AREA_MIN, 1)))
+        if confianca < cfg.TRACEJADO_CONFIANCA_MIN:
+            return ausente("suporte_insuficiente")
+        # Memória fixa: só dois pontos da última observação válida. Não renova
+        # na ausência e nunca converte referência histórica em detecção nova.
+        self._referencia = pontos[[0, -1]].copy()
+        self._referencia_t = agora
+        extremos = tuple((float(a[0]), float(a[1] + y0),
+                          float(b[0]), float(b[1] + y0))
+                         for s in caminho for a, b in [s['extremos']])
+        trajetoria = tuple((float(px), float(py + y0)) for px, py in pontos)
+        return ResultadoLinha(True, (x - w / 2.) / (w / 2.), x, y + y0,
+                              binaria=binaria, y0=y0, segmentos=extremos,
+                              trajetoria=trajetoria, direcao=direcao,
+                              confianca=confianca, motivo="observada")
 
 
 def desenhar_debug(frame: np.ndarray, r: ResultadoLinha) -> np.ndarray:
@@ -89,58 +176,123 @@
     cv2.line(saida, (w // 2, 0), (w // 2, h), (255, 0, 0), 1)           # centro da tela
     cv2.line(saida, (0, r.y0), (w, r.y0), (0, 255, 255), 1)             # início da ROI
     if r.achou:
-        cv2.drawContours(saida[r.y0:, :], [r.contorno], -1, (0, 255, 0), 2)
+        if r.contorno is not None:
+            cv2.drawContours(saida[r.y0:, :], [r.contorno], -1, (0, 255, 0), 2)
+        for x1, y1, x2, y2 in r.segmentos:
+            cv2.line(saida, (round(x1), round(y1)), (round(x2), round(y2)), (0, 255, 0), 3)
+        if r.trajetoria:
+            cv2.polylines(saida, [np.rint(r.trajetoria).astype(np.int32)], False, (0, 180, 255), 1)
         cv2.circle(saida, (int(r.cx), int(r.cy)), 5, (0, 0, 255), -1)
         cv2.putText(saida, f"erro={r.erro:+.2f}", (5, 15),
                     cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
+    if r.motivo != "legado":
+        texto = f"{r.motivo} conf={r.confianca:.2f} dir={r.direcao:+.2f}"
+        cv2.putText(saida, texto, (5, h - 8), cv2.FONT_HERSHEY_SIMPLEX, .34, (0, 0, 255), 1)
     return saida
 
 
 class ThreadVisao(threading.Thread):
-    """fonte: ArduinoSerial (OV7670), FonteSimulada ou CameraCSI. Só processa quando o modo é SEGUINDO."""
+    """Fontes legadas ou ESP32 com metadados; processa apenas em SEGUINDO."""
 
     def __init__(self, estado: EstadoRobo, parar: threading.Event, fonte):
         super().__init__(name="visao", daemon=True)
         self._estado = estado
         self._parar = parar
         self._fonte = fonte
+        self._detalhada = callable(getattr(fonte, 'proximo_quadro_detalhado', None))
+        self._geracao_processada = None
 
     def run(self) -> None:
         try:
             self._loop()
         except Exception:
             log.exception("Thread de visão caiu")
+            self._estado.publicar_leitura(0.0, False, camera_ok=False, motivo="excecao_visao")
             self._parar.set()                      # main para o robô todo
 
+    def _camera_valida(self, meta):
+        camera = self._fonte.saude()
+        agora = time.monotonic()
+        recebida = meta['recepcao_monotonica']
+        idade = meta['idade_captura_s']
+        limite = min(cfg.LEITURA_VALIDADE_S, self._fonte.idade_max_s)
+        return (camera['status'] == 'ok' and camera['geracao'] == meta['geracao_camera']
+                and np.isfinite(recebida) and np.isfinite(idade) and idade >= 0
+                and agora >= recebida and agora - recebida + idade <= limite)
+
+    def _processar_detalhado(self, detector, quadro, sessao):
+        quadro_id, frame, meta = quadro
+        if not self._camera_valida(meta):
+            detector.limpar_historico()
+            self._estado.publicar_leitura(0.0, False, camera_ok=False,
+                                         motivo="camera_indisponivel", sessao=sessao)
+            return None
+        if self._geracao_processada != meta['geracao_camera']:
+            detector.limpar_historico()
+            self._geracao_processada = meta['geracao_camera']
+        resultado = detector.processar(frame)
+        # A captura pode falhar/recuperar ou envelhecer durante o processamento.
+        if not self._camera_valida(meta):
+            detector.limpar_historico()
+            self._estado.publicar_leitura(0.0, False, camera_ok=False,
+                                         motivo="camera_indisponivel", sessao=sessao)
+            return None
+        publicada = self._estado.publicar_leitura(
+            resultado.erro, resultado.achou, sessao=sessao,
+            timestamp=meta['recepcao_monotonica'], idade_captura_s=meta['idade_captura_s'],
+            frame_id=quadro_id, geracao_camera=meta['geracao_camera'], camera_ok=True,
+            direcao=resultado.direcao, escala_direcao=(frame.shape[0] - resultado.y0) / (frame.shape[1] / 2.),
+            confianca=resultado.confianca, motivo=resultado.motivo)
+        if not publicada:
+            detector.limpar_historico()
+            return None
+        return resultado
+
     def _loop(self) -> None:
-        detector = DetectorLinha()
+        detector = DetectorLinha(tracejado=self._detalhada)
         ultimo_id = self._fonte.id_atual()
-        suspensa = True
+        sessao_anterior = None
         sem_quadro = 0
         while not self._parar.is_set():
-            if self._estado.modo is not Modo.SEGUINDO:
-                suspensa = True
-                time.sleep(0.05)
+            with self._estado.lock:
+                modo, sessao = self._estado.modo, self._estado.sessao_visao
+            if modo is not Modo.SEGUINDO:
+                sessao_anterior = None
+                detector.limpar_historico()
+                self._parar.wait(.05)
                 continue
-
-            if suspensa:                           # acabou de retomar: o quadro em andamento é velho
-                ultimo_id = self._fonte.id_atual() + 1
-                suspensa = False
-
-            q = self._fonte.proximo_quadro(ultimo_id, timeout=0.5)
+            if sessao != sessao_anterior:
+                ultimo_id = self._fonte.id_atual() + (0 if self._detalhada else 1)
+                detector.limpar_historico()
+                sessao_anterior = sessao
+            if self._detalhada:
+                q = self._fonte.proximo_quadro_detalhado(ultimo_id, timeout=.1)
+            else:
+                q = self._fonte.proximo_quadro(ultimo_id, timeout=.5)
             if q is None:
-                sem_quadro += 1
-                if sem_quadro == 1 or sem_quadro % 10 == 0:
-                    log.warning("Sem quadros da câmera (status=%s)", getattr(self._fonte, "status", None))
-                self._estado.publicar_leitura(0.0, False)
+                # Esperar o próximo id não é um vão. Não renova a leitura anterior.
+                saudavel = self._detalhada and self._fonte.saude()['status'] == 'ok'
+                if not saudavel:
+                    sem_quadro += 1
+                    detector.limpar_historico()
+                    if sem_quadro == 1 or sem_quadro % 10 == 0:
+                        log.warning("Sem quadros da câmera (status=%s)", getattr(self._fonte, 'status', None))
+                    self._estado.publicar_leitura(0.0, False, camera_ok=False,
+                                                 motivo="sem_quadros", sessao=sessao)
                 continue
             sem_quadro = 0
-            ultimo_id, frame = q
-
-            r = detector.processar(frame)
-            self._estado.publicar_leitura(r.erro, r.achou)
-
-            if cfg.MOSTRAR_DEBUG:
+            ultimo_id, frame = q[:2]
+            if self._detalhada:
+                if cfg.IMAGEM_ESPELHAR_H or cfg.IMAGEM_ESPELHAR_V:
+                    eixo = -1 if cfg.IMAGEM_ESPELHAR_H and cfg.IMAGEM_ESPELHAR_V else 1 if cfg.IMAGEM_ESPELHAR_H else 0
+                    frame = cv2.flip(frame, eixo)
+                    q = (ultimo_id, frame, q[2])
+                r = self._processar_detalhado(detector, q, sessao)
+            else:
+                r = detector.processar(frame)
+                if not self._estado.publicar_leitura(r.erro, r.achou, sessao=sessao):
+                    r = None
+            if cfg.MOSTRAR_DEBUG and r is not None:
                 cv2.imshow("visao", cv2.resize(desenhar_debug(frame, r), None, fx=3, fy=3,
                                                interpolation=cv2.INTER_NEAREST))
                 cv2.waitKey(1)
```

</details>

<details>
<summary>visao/sugestao.py — diferença completa disponível</summary>

```diff
--- antes/visao/sugestao.py
+++ atual/visao/sugestao.py
@@ -49,14 +49,20 @@
     return pequena, tratar_cinza(cinza, modo)
 
 
-def _segmentos(mascara):
+def _segmentos(mascara, *, area_min=12, fracao_area_max=.08,
+               fracao_altura_max=.45, alongamento_max=100, max_candidatos=None):
     h, w = mascara.shape
     n, labels, stats, centros = cv2.connectedComponentsWithStats(mascara, connectivity=8)
     candidatos = []
-    for i in range(1, n):
+    indices = [i for i in range(1, n)
+               if area_min <= stats[i, 4] <= h * w * fracao_area_max
+               and stats[i, 2] <= w * .45 and stats[i, 3] <= h * fracao_altura_max]
+    # No uso contínuo, excesso de componentes causa abstenção antes da PCA.
+    # Padrões do uso offline preservados quando não há limite explícito.
+    if max_candidatos is not None and len(indices) > max_candidatos:
+        return []
+    for i in indices:
         x, y, bw, bh, area = stats[i]
-        if area < 12 or area > h * w * .08 or bw > w * .45 or bh > h * .45:
-            continue
         ys, xs = np.nonzero(labels[y:y + bh, x:x + bw] == i)
         xy = np.column_stack((xs, ys)).astype(np.float32)
         _, (lado_a, lado_b), _ = cv2.minAreaRect(xy)
@@ -70,7 +76,7 @@
         # Rejuntes finos são removidos pela abertura; traços quase horizontais
         # são concorrentes frequentes. Nenhuma dessas regras prova a identidade.
         razao = valores[0, 0] / max(valores[1, 0], .1)
-        if vy < .45 or not 1.5 <= razao <= 100:
+        if vy < .45 or not 1.5 <= razao <= alongamento_max:
             continue
         media = xy.mean(axis=0)
         eixo = np.array([vx, vy])
```

</details>

<details>
<summary>estado.py — diferença completa disponível</summary>

```diff
--- antes/estado.py
+++ atual/estado.py
@@ -27,7 +27,19 @@
     """Última medição da visão (imutável, então pode ser lida fora do lock)."""
     erro: float            # -1.0 (linha à esquerda) .. +1.0 (linha à direita)
     linha_visivel: bool
-    timestamp: float       # time.monotonic() de quando foi medida
+    timestamp: float       # recepção na Pi (ou medição para fontes legadas)
+    idade_captura_s: float = 0.0     # limite estimado na recepção; nunca renovado no controle
+    frame_id: int | None = None
+    camera_ok: bool = True
+    geracao_camera: int = 0
+    sessao: int = 0
+    direcao: float = 0.0             # dx/dy em direção ao alto da imagem
+    escala_direcao: float = 0.0      # altura ROI / meia largura do frame
+    confianca: float = 1.0
+    motivo: str = "legado"
+
+    def idade(self, agora: float) -> float:
+        return agora - self.timestamp + self.idade_captura_s
 
 
 @dataclass(frozen=True)
@@ -42,6 +54,8 @@
     def __init__(self):
         self.lock = threading.RLock()
         self._modo = Modo.PARADO            # começa parado: só anda depois de ouvir "siga"
+        self._encerrando = False
+        self._sessao_visao = 0
         self._partida_ate = 0.0
         self._fim_manobra = 0.0
         self._leitura = Leitura(0.0, False, 0.0)
@@ -58,18 +72,44 @@
 
     def definir_modo(self, modo: Modo, duracao_s: float | None = None) -> None:
         with self.lock:
-            self._modo = modo
+            if self._encerrando and modo is not Modo.PARADO:
+                return
+            self._trocar_modo(modo)
             if modo is not Modo.SEGUINDO:
                 self._acao = None                 # uma ação velha nunca sobrevive a um "pare"
             if modo is not Modo.MANUAL:
                 self._manual = None               # nem um comando remoto velho
             self._fim_manobra = time.monotonic() + duracao_s if duracao_s else 0.0
 
+    @property
+    def encerrando(self) -> bool:
+        with self.lock:
+            return self._encerrando
+
+    def encerrar(self) -> None:
+        with self.lock:
+            self._encerrando = True
+            self.definir_modo(Modo.PARADO)
+            self._partida_ate = 0.0
+
+    @property
+    def sessao_visao(self) -> int:
+        with self.lock:
+            return self._sessao_visao
+
+    def _trocar_modo(self, modo: Modo) -> None:
+        # Chamado sob lock: até um pare/siga entre dois ciclos invalida a visão.
+        if self._modo is not modo:
+            self._sessao_visao += 1
+            self._leitura = Leitura(0.0, False, 0.0, camera_ok=False,
+                                    sessao=self._sessao_visao)
+        self._modo = modo
+
     def atualizar_manobra(self) -> Modo:
         """Encerra manobras temporizadas. Giro volta a seguir a linha; ré termina parado."""
         with self.lock:
             if self._modo in MANOBRAS and time.monotonic() >= self._fim_manobra:
-                self._modo = Modo.PARADO if self._modo is Modo.RE else Modo.SEGUINDO
+                self._trocar_modo(Modo.PARADO if self._modo is Modo.RE else Modo.SEGUINDO)
                 self._acao = None
             return self._modo
 
@@ -78,10 +118,12 @@
         """Comando do celular: entra em MANUAL (ou renova o prazo, se já estiver) com estes PWM.
         validade_s: por quanto tempo vale sem novo comando (None = REMOTO_TIMEOUT_S)."""
         with self.lock:
+            if self._encerrando:
+                return
             if esq == 0 and dir_ == 0:
                 self._recuo_bloqueia_avanco = False
                 self._parada_manual_id += 1
-            self._modo = Modo.MANUAL
+            self._trocar_modo(Modo.MANUAL)
             self._acao = None
             self._partida_ate = 0.0
             self._fim_manobra = 0.0
@@ -92,10 +134,18 @@
             return self._manual
 
     # ---------------------------------------------------------- leitura
-    def publicar_leitura(self, erro: float, linha_visivel: bool) -> None:
-        nova = Leitura(erro, linha_visivel, time.monotonic())
+    def publicar_leitura(self, erro: float, linha_visivel: bool, *,
+                         timestamp: float | None = None, sessao: int | None = None,
+                         **metadados) -> bool:
         with self.lock:
-            self._leitura = nova
+            if self._encerrando:
+                return False
+            if sessao is not None and (sessao != self._sessao_visao or self._modo is not Modo.SEGUINDO):
+                return False
+            self._leitura = Leitura(erro, linha_visivel,
+                                    time.monotonic() if timestamp is None else timestamp,
+                                    sessao=self._sessao_visao, **metadados)
+            return True
 
     def ler_leitura(self) -> Leitura:
         with self.lock:
@@ -105,7 +155,7 @@
     def publicar_acao(self, steer: float | None, vel_fator: float = 1.0) -> bool:
         """Só vale enquanto o modo é SEGUINDO (checado sob o lock: um 'pare' de voz não é desfeito)."""
         with self.lock:
-            if steer is None or self._modo is not Modo.SEGUINDO:
+            if self._encerrando or steer is None or self._modo is not Modo.SEGUINDO:
                 self._acao = None
                 return False
             self._acao = Acao(float(steer), float(vel_fator), time.monotonic())
```

</details>

<details>
<summary>controle.py — diferença completa disponível</summary>

```diff
--- antes/controle.py
+++ atual/controle.py
@@ -10,6 +10,8 @@
 nunca pode ser desfeito por um comando de linha que já estava a caminho.
 """
 import logging
+import math
+from dataclasses import dataclass
 import threading
 import time
 
@@ -23,6 +25,8 @@
 def aplicar_comando(estado: EstadoRobo, motor, comando: str) -> None:
     """Chamado pela thread de voz. Prioridade absoluta sobre a visão."""
     with estado.lock:
+        if estado.encerrando and comando != "pare":
+            return
         if comando in {"pare", "siga", "esquerda", "direita", "voltar"}:
             getattr(motor, 'usar_sonar_manual', lambda ativo: None)(False)
         if comando in {"pare", "esquerda", "direita", "voltar"}:
@@ -77,6 +81,8 @@
     esq = max(-cfg.VEL_MAX, min(cfg.VEL_MAX, int(esq)))
     dir_ = max(-cfg.VEL_MAX, min(cfg.VEL_MAX, int(dir_)))
     with estado.lock:
+        if estado.encerrando:
+            return
         getattr(motor, 'usar_sonar_manual', lambda ativo: None)(bool(esq or dir_))
         centrar = getattr(motor, "configurar_servo", None)
         if centrar and (not cfg.SONAR_MOVIMENTO_ATIVO or not (esq or dir_)):
@@ -90,12 +96,28 @@
             motor.motores(esq, dir_)
 
 
+@dataclass(frozen=True)
+class DecisaoLinha:
+    esq: int
+    dir: int
+    motivo: str
+    erro: float = 0.0
+    estimada: bool = False
+    idade_observacao_s: float | None = None
+
+
 class ThreadControle(threading.Thread):
-    def __init__(self, estado: EstadoRobo, motor, parar: threading.Event):
+    def __init__(self, estado: EstadoRobo, motor, parar: threading.Event, fonte=None):
         super().__init__(name="controle", daemon=True)
         self._estado = estado
         self._motor = motor
         self._parar = parar
+        self._fonte = fonte
+        self._linha_geracao = None
+        self._linha_sessao = -1
+        self._linha_min_t = 0.0
+        self._limpar_linha()
+        self.decisao_linha = DecisaoLinha(0, 0, "aguardando_observacao")
         self._obst_ant = False
         self._inspecao_inicio = None
         self._recuo = None  # (inicio, comando de origem, ticks E/D)
@@ -109,13 +131,108 @@
         except Exception:
             log.exception("Thread de controle caiu")
             self._parar.set()
+            self._estado.encerrar()
         finally:
+            self._parar.set()
             with self._estado.lock:
-                if self._recuo is not None:
-                    self._motor.parar()
-                    self._recuo = None
+                self._estado.definir_modo(Modo.PARADO)
+                self._motor.parar(repetir=3)
+                self._recuo = None
+                self._limpar_linha()
+                self.decisao_linha = DecisaoLinha(0, 0, "encerrado")
                 self._cancelar_inspecao()
                 getattr(self._motor, "avisar", lambda tipo: None)(0)
+
+    def _limpar_linha(self):
+        self._linha_ultima = None
+        self._linha_erro = 0.0
+        self._linha_derivada = 0.0
+        self._linha_em_vao = False
+
+    def _parar_linha(self, motivo, agora):
+        self._limpar_linha()
+        self._linha_min_t = max(self._linha_min_t, agora)
+        return DecisaoLinha(0, 0, motivo)
+
+    def decidir_linha(self, agora: float, bloqueado: bool = False) -> DecisaoLinha:
+        """Sob estado.lock. Só calcula: não escreve em motores ou sensores.
+
+        `bloqueado` vem da inspeção/guarda de ultrassom já existentes no loop.
+        Recebe a mesma leitura usada na operação; permite teste sem hardware.
+        A memória guarda apenas números de uma observação, nunca frames.
+        """
+        sessao = self._estado.sessao_visao
+        if sessao != self._linha_sessao:
+            self._limpar_linha()
+            self._linha_sessao, self._linha_min_t = sessao, 0.0
+        if self._parar.is_set() or self._estado.modo is not Modo.SEGUINDO:
+            return self._parar_linha("parado", agora)
+        if bloqueado:
+            return self._parar_linha("obstaculo_ou_sensor", agora)
+        leitura = self._estado.ler_leitura()
+        saude = getattr(self._fonte, 'saude', None)
+        monitorada = callable(saude)
+        if monitorada:
+            if cfg.APRENDIZADO_ATIVO:
+                return self._parar_linha("cnn_sem_contrato_esp32", agora)
+            camera = saude()
+            if camera['geracao'] != self._linha_geracao:
+                self._limpar_linha()
+                self._linha_geracao = camera['geracao']
+            if camera['status'] != 'ok' or leitura.geracao_camera != camera['geracao']:
+                return self._parar_linha("camera_indisponivel", agora)
+        if not leitura.camera_ok:
+            return self._parar_linha("camera_indisponivel", agora)
+        if leitura.sessao != sessao:
+            return self._parar_linha("sessao_visual_invalida", agora)
+        numeros = (leitura.erro, leitura.timestamp, leitura.idade_captura_s,
+                   leitura.direcao, leitura.escala_direcao, leitura.confianca)
+        if (not all(math.isfinite(v) for v in numeros) or
+                leitura.idade_captura_s < 0 or not -1 <= leitura.erro <= 1 or
+                not 0 <= leitura.confianca <= 1):
+            return self._parar_linha("leitura_invalida", agora)
+        limite = min(cfg.LEITURA_VALIDADE_S,
+                     getattr(self._fonte, 'idade_max_s', cfg.LEITURA_VALIDADE_S))
+        if agora < leitura.timestamp or not 0 <= leitura.idade(agora) <= limite:
+            return self._parar_linha("frame_vencido", agora)
+        if leitura.timestamp < self._linha_min_t:
+            return DecisaoLinha(0, 0, "aguardando_observacao")
+        if leitura.linha_visivel:
+            if leitura.confianca < cfg.TRACEJADO_CONFIANCA_MIN:
+                return self._parar_linha("deteccao_nao_confiavel", agora)
+            erro = max(-1., min(1., leitura.erro + cfg.TRACEJADO_ANTECIPACAO *
+                               leitura.direcao * leitura.escala_direcao))
+            anterior = self._linha_ultima
+            if anterior is None or leitura.timestamp > anterior.timestamp:
+                if (anterior is not None and not self._linha_em_vao and
+                        leitura.timestamp - anterior.timestamp <= cfg.LEITURA_VALIDADE_S):
+                    self._linha_derivada = filtrar_derivada(
+                        self._linha_derivada, erro, self._linha_erro,
+                        leitura.timestamp - anterior.timestamp, cfg.KD_FILTRO)
+                else:
+                    self._linha_derivada = 0.0
+                self._linha_ultima, self._linha_erro = leitura, erro
+            self._linha_em_vao = False
+            esq, dir_ = calcular_motores(self._linha_erro, self._linha_derivada)
+            return DecisaoLinha(esq, dir_, "observada", self._linha_erro,
+                               idade_observacao_s=leitura.idade(agora))
+        if leitura.motivo in {"trajetorias_ambiguas", "suporte_insuficiente"}:
+            return self._parar_linha("deteccao_nao_confiavel", agora)
+        ultima = self._linha_ultima
+        if ultima is None:
+            return DecisaoLinha(0, 0, "aguardando_observacao")
+        idade = ultima.idade(agora)
+        if not 0 <= idade < cfg.PERDA_LINHA_TIMEOUT_S:
+            return self._parar_linha("linha_perdida", agora)
+        # Mantém a última geometria confiável; não inventa velocidade lateral.
+        # Tempo sem observação aumenta continuamente, mesmo com frames repetidos.
+        self._linha_em_vao = True
+        self._linha_derivada = 0.0
+        esq, dir_ = calcular_motores(self._linha_erro, 0.0)
+        fator = max(0., min(1., cfg.TRACEJADO_VAO_FATOR)) * ultima.confianca
+        fator *= 1. - idade / cfg.PERDA_LINHA_TIMEOUT_S
+        return DecisaoLinha(int(esq * fator), int(dir_ * fator), "vao_limitado",
+                           self._linha_erro, True, idade)
 
     def _diagnosticar_manual(self, manual, motivo):
         """Somente leitura/log: nao altera o pedido nem envia comandos de motor."""
@@ -163,18 +280,25 @@
         if not cfg.OBSTACULO_ATIVO:
             return False
         sensores = getattr(self._motor, "sensores", lambda: None)()
-        if sensores is None or time.monotonic() - sensores.timestamp > cfg.SENSOR_TIMEOUT_S:
+        if sensores is None or not 0 <= time.monotonic() - sensores.timestamp <= cfg.SENSOR_TIMEOUT_S:
             return True
         if sensores.avanco_bloqueado:
             return True
         status = getattr(self._motor, 'status_servo', lambda: None)()
-        if (status is not None and status.ativo and status.sonar_movimento and
+        if (self._estado.modo is not Modo.SEGUINDO and
+                status is not None and status.ativo and status.sonar_movimento and
                 0 <= time.monotonic() - status.timestamp <= .5):
             # FC repete a ultima amostra entre ecos. Contar esses pacotes como
             # leituras distintas inventaria uma confirmacao de obstaculo.
             return False  # no manual, ausencia de eco nao cancela o pedido
         if sensores.falha_sensor:
             return True
+        if self._estado.modo is Modo.SEGUINDO:
+            if status is not None and status.ativo and status.sonar_movimento:
+                return True  # aguarda confirmação do fim do contexto manual V4
+            distancia = sensores.distancia_cm
+            if distancia is None or not math.isfinite(distancia) or distancia < 0:
+                return True
         checar = getattr(self._motor, "obstaculo", None)
         obst = bool(checar and checar(cfg.OBSTACULO_DIST_CM, cfg.OBSTACULO_LEITURAS))
         if obst != self._obst_ant:
@@ -293,9 +417,6 @@
         periodo = 1.0 / cfg.FREQ_CONTROLE_HZ
         modo_ant = None
         aviso_ant = 0
-        erro_ant = 0.0
-        t_leitura_ant = 0.0
-        derivada = 0.0
         t_ultima_linha = time.monotonic()
 
         while not self._parar.is_set():
@@ -310,6 +431,7 @@
                     self._recuar_manual(inicio, None)
 
                 if modo is not Modo.SEGUINDO:
+                    self.decisao_linha = DecisaoLinha(0, 0, "modo_" + modo.name.lower())
                     self._cancelar_inspecao()
                 getattr(self._motor, 'usar_sonar_manual', lambda ativo: None)(modo is Modo.MANUAL)
 
@@ -320,8 +442,10 @@
 
                 leitura_aviso = self._estado.ler_leitura()
                 partida = modo is Modo.SEGUINDO and inicio < self._estado._partida_ate
-                if fresca_aviso := (inicio - leitura_aviso.timestamp <= cfg.LEITURA_VALIDADE_S and leitura_aviso.linha_visivel):
-                    t_ultima_linha = inicio
+                if fresca_aviso := (leitura_aviso.camera_ok and
+                                    0 <= leitura_aviso.idade(inicio) <= cfg.LEITURA_VALIDADE_S and
+                                    leitura_aviso.linha_visivel):
+                    t_ultima_linha = leitura_aviso.timestamp - leitura_aviso.idade_captura_s
                 aviso = (1 if partida else 2 if modo is Modo.SEGUINDO and
                          modo_ant is Modo.SEGUINDO and not fresca_aviso and
                          inicio - t_ultima_linha > cfg.PERDA_LINHA_TIMEOUT_S else 0)
@@ -329,6 +453,7 @@
                     getattr(self._motor, "avisar", lambda tipo: None)(aviso)
                 aviso_ant = aviso
                 if partida:
+                    self.decisao_linha = DecisaoLinha(0, 0, "partida")
                     self._motor.parar()
                     modo_ant = None
                     self._estado.lock.release()
@@ -373,42 +498,27 @@
                     self._diagnosticar_manual(manual, motivo_manual)
 
                 elif modo is Modo.SEGUINDO:
-                    if modo_ant is not Modo.SEGUINDO:        # acabou de entrar: zera memória do PD
-                        erro_ant, derivada = 0.0, 0.0
-                        t_leitura_ant = 0.0
+                    if modo_ant is not Modo.SEGUINDO:
                         t_ultima_linha = inicio
                     bloqueado = self._inspecionar_obstaculo(inicio) or self._obstaculo()
-                    leitura = self._estado.ler_leitura()
-                    fresca = (inicio - leitura.timestamp) <= cfg.LEITURA_VALIDADE_S
-
                     if cfg.APRENDIZADO_ATIVO:
                         from aprendizado.politica import direcao_para_pwm   # import tardio: só o aprendizado precisa
                         # quem decide a direção é a thread de aprendizado (professor/CNN); aqui só se executa,
                         # e sem ação recente ou com obstáculo os motores PARAM (nunca mantém comando velho)
                         acao = self._estado.ler_acao()
-                        if bloqueado or acao is None or inicio - acao.timestamp > cfg.APR_ACAO_VALIDADE_S:
+                        if (bloqueado or callable(getattr(self._fonte, 'saude', None)) or
+                                acao is None or inicio - acao.timestamp > cfg.APR_ACAO_VALIDADE_S):
                             self._motor.parar()
                         else:
                             esq, dir_ = direcao_para_pwm(acao.steer, acao.vel_fator)
                             self._motor.motores(esq, dir_)
-                    elif bloqueado:
-                        self._motor.parar()                  # algo à frente: espera sumir
-                        t_ultima_linha = inicio              # parar por obstáculo não é "linha perdida"
-                    elif fresca and leitura.linha_visivel:
-                        t_ultima_linha = inicio
-                        if t_leitura_ant and leitura.timestamp > t_leitura_ant:
-                            dt = leitura.timestamp - t_leitura_ant
-                            derivada = filtrar_derivada(derivada, leitura.erro, erro_ant, dt, cfg.KD_FILTRO)
-                        erro_ant, t_leitura_ant = leitura.erro, leitura.timestamp
-                        esq, dir_ = calcular_motores(leitura.erro, derivada)
-                        self._motor.motores(esq, dir_)
-                    elif inicio - t_ultima_linha > cfg.PERDA_LINHA_TIMEOUT_S:
-                        log.warning("Linha perdida: parando")
-                        self._motor.parar()
                     else:
-                        # perdeu por pouco tempo: mantém a última correção em vez de parar
-                        esq, dir_ = calcular_motores(erro_ant, 0.0)
-                        self._motor.motores(esq, dir_)
+                        decisao = self.decidir_linha(time.monotonic(), bloqueado)
+                        self.decisao_linha = decisao
+                        if decisao.esq == 0 and decisao.dir == 0:
+                            self._motor.parar()
+                        else:
+                            self._motor.motores(decisao.esq, decisao.dir)
 
                 modo_ant = modo
```

</details>

<details>
<summary>main.py — diferença completa disponível</summary>

```diff
--- antes/main.py
+++ atual/main.py
@@ -4,12 +4,11 @@
     voz      -> classifica comandos e chama aplicar_comando() (prioridade absoluta)
     controle -> único que escreve nos motores (via ArduinoSerial)
     remoto   -> (opcional) celular Android por Bluetooth serial: anda/para pelo modo MANUAL (remoto/)
-    A imagem vem da OV7670 ligada ao Arduino (pela serial); o mesmo Arduino aciona os motores (L298N).
+    Imagem pela fonte selecionada (inclui ESP32 HTTP); motores e sensores continuam no Arduino.
 """
 import argparse
 import logging
 import signal
-import sys
 import threading
 import time
 
@@ -37,7 +36,7 @@
     try:
         fonte = criar_fonte(nome, motor)
         if hasattr(fonte, "iniciar"):
-            fonte.iniciar()                                 # só a câmera CSI (opcional) precisa abrir
+            fonte.iniciar()                                 # fontes com captura em segundo plano
     except Exception as e:
         log.error("CÂMERA INDISPONÍVEL (%s). Sem imagem o robô NÃO segue linha; comandos de voz continuam. "
                   "Confira docs/02_bringup_camera.md e python tools/verificar_ambiente.py", e)
@@ -49,58 +48,76 @@
     ap = argparse.ArgumentParser(description="Robô seguidor de linha com voz")
     ap.add_argument("--sem-arduino", action="store_true",
                     help="não abre a serial: motores/sensores simulados (testa câmera, visão e voz sem o Arduino)")
+    ap.add_argument("--fonte-imagem", choices=("arduino", "csi", "nenhuma", "simulada", "esp32"),
+                    default=cfg.FONTE_IMAGEM, help="seleciona a fonte sem alterar config.py")
     args = ap.parse_args()
+    if args.fonte_imagem == "esp32" and cfg.APRENDIZADO_ATIVO:
+        ap.error("ESP32 com aprendizado ativo exige contrato CNN compatível; mantenha APRENDIZADO_ATIVO=False")
 
     parar = threading.Event()
     estado = EstadoRobo()
     motor = ArduinoNulo() if args.sem_arduino else ArduinoSerial()
+    fonte = None
+    iniciadas = []
     try:
-        motor.conectar()
-    except Exception as e:
-        log.error("Não consegui abrir o Arduino em %s (%s). Confira a porta (ls /dev/ttyACM*) e SERIAL_PORTA em config.py; "
-                  "para testar sem ele: python main.py --sem-arduino", cfg.SERIAL_PORTA, e)
-        sys.exit(1)
-    fonte = abrir_fonte(cfg.FONTE_IMAGEM, motor)
+        try:
+            motor.conectar()
+        except Exception as e:
+            log.error("Não consegui abrir o Arduino em %s (%s). Para testar sem ele: --sem-arduino",
+                      cfg.SERIAL_PORTA, e)
+            raise SystemExit(1)
+        fonte = abrir_fonte(args.fonte_imagem, motor)
 
-    def ao_comando_de_voz(comando: str) -> None:
-        aplicar_comando(estado, motor, comando)
+        def ao_comando_de_voz(comando: str) -> None:
+            aplicar_comando(estado, motor, comando)
 
-    threads = [
-        ThreadControle(estado, motor, parar),
-        ThreadVisao(estado, parar, fonte),
-        ThreadVoz(ao_comando_de_voz, parar),
-    ]
+        threads = [
+            ThreadControle(estado, motor, parar, fonte),
+            ThreadVisao(estado, parar, fonte),
+            ThreadVoz(ao_comando_de_voz, parar),
+        ]
+        if cfg.APRENDIZADO_ATIVO:
+            from aprendizado.robo_real import ThreadAprendizado
+            threads.append(ThreadAprendizado(estado, motor, parar, fonte))
+        opcionais = []
+        if cfg.REMOTO_BT_ATIVO:
+            from remoto.bluetooth_spp import ThreadBluetooth
+            opcionais.append(ThreadBluetooth(estado, motor, parar))
+        def solicitar_parada(*_):
+            parar.set()
+            estado.encerrar()
 
-    if cfg.APRENDIZADO_ATIVO:
-        from aprendizado.robo_real import ThreadAprendizado
-        threads.append(ThreadAprendizado(estado, motor, parar, fonte))
-
-    opcionais = []                                          # falha aqui não derruba o robô (só avisa)
-    if cfg.REMOTO_BT_ATIVO:
-        from remoto.bluetooth_spp import ThreadBluetooth
-        opcionais.append(ThreadBluetooth(estado, motor, parar))
-
-    signal.signal(signal.SIGINT, lambda *_: parar.set())
-    signal.signal(signal.SIGTERM, lambda *_: parar.set())
-
-    for t in threads + opcionais:
-        t.start()
-    log.info("Robô pronto. Parado até ouvir 'siga'%s.", " ou receber comando do celular" if opcionais else "")
-
-    try:
+        signal.signal(signal.SIGINT, solicitar_parada)
+        signal.signal(signal.SIGTERM, solicitar_parada)
+        for t in threads + opcionais:
+            t.start()
+            iniciadas.append(t)
+        log.info("Robô pronto. Parado até ouvir 'siga'%s.",
+                 " ou receber comando do celular" if opcionais else "")
         while not parar.is_set():
-            if not all(t.is_alive() for t in threads):      # qualquer thread morta = parada de segurança
+            if not all(t.is_alive() for t in threads):
                 log.error("Uma thread morreu; encerrando.")
                 break
             time.sleep(0.2)
     finally:
         parar.set()
-        for t in threads + opcionais:
-            t.join(timeout=2.0)
-        motor.parar(repetir=3)
-        motor.fechar()
-        if hasattr(fonte, "parar"):
-            fonte.parar()
+        estado.encerrar()
+        # Parar antes de aguardar threads, inclusive se inicialização falhar.
+        try:
+            motor.parar(repetir=3)
+        finally:
+            try:
+                for t in iniciadas:
+                    t.join(timeout=2.0)
+            finally:
+                try:
+                    motor.parar(repetir=3)
+                finally:
+                    try:
+                        motor.fechar()
+                    finally:
+                        if fonte is not None and hasattr(fonte, "parar"):
+                            fonte.parar()
         log.info("Encerrado.")
```

</details>

## Anexo B — conteúdo integral dos arquivos adicionados

Cópias dos seis arquivos novos, para consultar tudo em um só documento. Os
códigos continuam tendo como fontes executáveis os caminhos do inventário.

<details>
<summary>visao/esp32_cam.py — arquivo novo completo</summary>

```python
"""Recepção HTTP compartilhada e fonte contínua ESP32, sem acesso aos motores."""
import threading
import time
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from http.client import HTTPException
from urllib.request import build_opener, ProxyHandler, Request
from urllib.error import URLError

import cv2
import numpy as np

MAX_JPEG = 2 * 1024 * 1024
URL_PADRAO = "http://192.168.4.1/capture"
ERROS_RECEPCAO = (URLError, OSError, HTTPException, ValueError, TypeError, cv2.error)


@dataclass(frozen=True)
class QuadroESP32:
    jpeg: bytes
    imagem: np.ndarray
    recepcao_monotonica: float
    recepcao_utc: str
    http_ms: float
    idade_envio_ms: float

    @property
    def idade_recepcao_limite_ms(self):
        return self.idade_envio_ms + self.http_ms


def receber_quadro(opener, url, timeout):
    inicio = time.monotonic()
    req = Request(url, headers={"Cache-Control": "no-cache"})
    with opener.open(req, timeout=timeout) as resposta:
        if resposta.status != 200:
            raise ValueError(f"HTTP {resposta.status}")
        if resposta.headers.get_content_type() != "image/jpeg":
            raise ValueError("Resposta nao e image/jpeg")
        idade_envio = float(resposta.headers["X-Frame-Age-Us"]) / 1000
        dados = resposta.read(MAX_JPEG + 1)
        recepcao = time.monotonic()
        recepcao_utc = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    if not np.isfinite(idade_envio) or idade_envio < 0:
        raise ValueError("Idade do quadro invalida")
    if len(dados) > MAX_JPEG or not dados.startswith(b"\xff\xd8") or not dados.endswith(b"\xff\xd9"):
        raise ValueError("JPEG truncado ou invalido")
    imagem = cv2.imdecode(np.frombuffer(dados, dtype=np.uint8), cv2.IMREAD_COLOR)
    if imagem is None or imagem.shape[:2] != (240, 320):
        raise ValueError("JPEG invalido ou resolucao diferente de 320x240")
    return QuadroESP32(dados, imagem, recepcao, recepcao_utc, (recepcao - inicio) * 1000, idade_envio)


def receber(opener, url, timeout):
    quadro = receber_quadro(opener, url, timeout)
    return quadro.imagem, quadro.http_ms, quadro.idade_envio_ms, quadro.idade_recepcao_limite_ms

class CameraESP32:
    """Um único quadro, sem fila. A API legada entrega (id, imagem).

    Metadados são consultados pelo mesmo id; nunca se associa uma idade nova
    a uma imagem antiga. Não há redimensionamento nem alteração de orientação.
    """

    def __init__(self, url=URL_PADRAO, timeout=1., idade_max_s=.3,
                 reconexao_s=.5, opener=None):
        if any(not math.isfinite(v) or v <= 0 for v in
               (timeout, idade_max_s, reconexao_s)):
            raise ValueError("Prazos devem ser positivos e finitos")
        self.url, self.timeout = url, timeout
        self.idade_max_s, self.reconexao_s = idade_max_s, reconexao_s
        self._opener = opener or build_opener(ProxyHandler({}))
        self._cond = threading.Condition()
        self._fim = threading.Event()
        self._thread = None
        self._geracao = 0
        self._id = 0
        self._quadro = None
        self._status = "parada"
        self._inicio = None
        self._validos = self._erros = self._vencidos = 0
        self._http_ms = None
        self._resolucao = None

    def iniciar(self):
        with self._cond:
            if self._thread is not None:
                raise RuntimeError("Fonte já iniciada; crie outra após encerrar")
            self._inicio = time.monotonic()
            self._status = "conectando"
            self._thread = threading.Thread(target=self._loop, name="camera-esp32", daemon=True)
            self._thread.start()

    def parar(self):
        self._fim.set()
        with self._cond:
            self._quadro = None
            self._status = "parada"
            self._cond.notify_all()
        if self._thread:
            self._thread.join(timeout=self.timeout + .5)

    def _idade(self, q):
        return q.idade_recepcao_limite_ms / 1000 + max(0., time.monotonic() - q.recepcao_monotonica)

    def _invalidar(self, status):
        # Sob _cond. Uma falha seguida de recuperação não ressuscita a trajetória.
        if self._status != status or self._quadro is not None:
            self._geracao += 1
        self._quadro = None
        self._status = status
        self._cond.notify_all()

    def _status_atual(self):
        if self._status == "ok" and self._quadro is not None and self._idade(self._quadro) > self.idade_max_s:
            self._invalidar("vencida")
        if self._thread is not None and not self._thread.is_alive() and not self._fim.is_set():
            self._invalidar("erro")
        return self._status

    @property
    def status(self):
        with self._cond:
            return self._status_atual()

    def saude(self):
        with self._cond:
            return dict(status=self._status_atual(), geracao=self._geracao)

    @property
    def estatisticas(self):
        with self._cond:
            tempo = time.monotonic() - self._inicio if self._inicio is not None else 0.
            return dict(quadros=self._validos, erros=self._erros, vencidos=self._vencidos,
                        fps=self._validos / tempo if tempo > 0 else 0.,
                        http_ms=self._http_ms, resolucao=self._resolucao,
                        idade_ms=self._idade(self._quadro) * 1000 if self._quadro else None)

    def _loop(self):
        while not self._fim.is_set():
            try:
                q = receber_quadro(self._opener, self.url, self.timeout)
                with self._cond:
                    if self._fim.is_set():
                        return
                    self._status_atual()
                    self._http_ms = q.http_ms
                    self._resolucao = (q.imagem.shape[1], q.imagem.shape[0])
                    if self._idade(q) > self.idade_max_s:
                        self._vencidos += 1
                        self._invalidar("vencida")
                    else:
                        self._id += 1
                        self._quadro = q
                        self._validos += 1
                        self._status = "ok"
                    self._cond.notify_all()
            except ERROS_RECEPCAO:
                with self._cond:
                    if self._fim.is_set():
                        return
                    self._erros += 1
                    self._invalidar("erro")
                    self._cond.notify_all()
                self._fim.wait(self.reconexao_s)

    def id_atual(self):
        with self._cond:
            return self._id

    def _metadados(self, q):
        return dict(recepcao_monotonica=q.recepcao_monotonica,
                    idade_limite_ms=self._idade(q) * 1000, http_ms=q.http_ms,
                    idade_captura_s=q.idade_recepcao_limite_ms / 1000,
                    geracao_camera=self._geracao)

    def metadados(self, quadro_id):
        """Metadados do id atual, sem associar um frame antigo a um horário novo."""
        with self._cond:
            if self._status_atual() != "ok" or quadro_id != self._id or self._quadro is None:
                return None
            return self._metadados(self._quadro)

    def proximo_quadro_detalhado(self, apos_id, timeout=1.):
        """Snapshot atômico (id, imagem, metadados); a imagem não é copiada."""
        with self._cond:
            self._cond.wait_for(lambda: self._fim.is_set() or
                                (self._id > apos_id and self._quadro is not None), timeout)
            if (self._fim.is_set() or self._status_atual() != "ok" or
                    self._quadro is None or self._id <= apos_id):
                return None
            return self._id, self._quadro.imagem, self._metadados(self._quadro)

    def proximo_quadro(self, apos_id, timeout=1.):
        quadro = self.proximo_quadro_detalhado(apos_id, timeout)
        return quadro[:2] if quadro is not None else None
```

</details>

<details>
<summary>tests/test_esp32_fonte.py — arquivo novo completo</summary>

```python
"""Testes da fonte com HTTP injetado: não abrem serial nem motores."""
import sys
import time
import threading
import unittest
from pathlib import Path
from email.message import Message
from io import BytesIO
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cv2
import numpy as np
from visao.esp32_cam import CameraESP32, receber_quadro
from visao.fontes import criar_fonte
from tools.testar_esp32_cam import receber_quadro as receptor_legado

class Resposta(BytesIO):
    status = 200
    def __init__(self, dados, idade):
        super().__init__(dados)
        self.headers = Message()
        self.headers['Content-Type'] = 'image/jpeg'
        self.headers['X-Frame-Age-Us'] = str(idade)

class HTTPFalso:
    def __init__(self):
        self.falhar = False
        self.idade = 1000
        self.dados = cv2.imencode('.jpg', np.full((240,320,3), 150, np.uint8))[1].tobytes()
        self.pedidos = 0
    def open(self, req, timeout):
        time.sleep(.005)
        self.pedidos += 1
        if self.falhar:
            raise OSError('desconectada')
        return Resposta(self.dados, self.idade)

class TestFonte(unittest.TestCase):
    def esperar(self, cond):
        fim = time.monotonic() + 2
        while not cond() and time.monotonic() < fim:
            time.sleep(.005)
        self.assertTrue(cond())
    def test_reuso_e_resolucao_sem_resize(self):
        self.assertIs(receptor_legado, receber_quadro)
        self.assertIsInstance(criar_fonte('esp32'), CameraESP32)
        h = HTTPFalso()
        q = receber_quadro(h, 'http://teste/capture', 1)
        self.assertEqual(q.imagem.shape, (240,320,3))
        self.assertEqual(q.jpeg, h.dados)
        h.dados = cv2.imencode('.jpg', np.zeros((120,160,3), np.uint8))[1].tobytes()
        with self.assertRaisesRegex(ValueError, '320x240'):
            receber_quadro(h, 'http://teste/capture', 1)
    def test_ultimo_frame_metadados_e_encerramento(self):
        h = HTTPFalso(); c = CameraESP32(opener=h)
        c.iniciar()
        try:
            primeiro = c.proximo_quadro(0, 1)
            self.assertIsNotNone(primeiro)
            self.esperar(lambda: c.id_atual() > primeiro[0] + 3)
            with c._cond:
                atual = c.proximo_quadro(primeiro[0], 0)
                self.assertEqual(atual[0], c.id_atual())
                self.assertIs(atual[1], c._quadro.imagem)
                self.assertIsNone(c.metadados(primeiro[0]))
                self.assertGreaterEqual(c.metadados(atual[0])['idade_limite_ms'], 1)
            self.assertGreater(c.estatisticas['fps'], 0)
        finally:
            c.parar()
        self.assertFalse(c._thread.is_alive())
        self.assertIsNone(c.proximo_quadro(0, 0))
    def test_falha_invalida_e_recupera(self):
        h = HTTPFalso(); c = CameraESP32(opener=h, reconexao_s=.01)
        c.iniciar()
        try:
            self.assertIsNotNone(c.proximo_quadro(0, 1))
            h.falhar = True
            self.esperar(lambda: c.status == 'erro')
            self.assertIsNone(c.proximo_quadro(0, .01))
            h.falhar = False
            self.esperar(lambda: c.status == 'ok')
            self.assertGreater(c.estatisticas['erros'], 0)
        finally:
            c.parar()
    def test_idade_esp_http_e_tempo_local(self):
        h = HTTPFalso(); h.idade = 500000
        c = CameraESP32(opener=h, idade_max_s=.1)
        c.iniciar()
        try:
            self.esperar(lambda: c.estatisticas['vencidos'] > 0)
            self.assertIsNone(c.proximo_quadro(0, .02))
            h.idade = 1000
            self.assertIsNotNone(c.proximo_quadro(0, 1))
            with c._cond:
                c._quadro = type(c._quadro)(c._quadro.jpeg, c._quadro.imagem,
                    time.monotonic()-1, c._quadro.recepcao_utc, 5, 1)
                self.assertIsNone(c.proximo_quadro(0, 0))
                self.assertEqual(c.status, 'vencida')
            h.idade = 0
            c.idade_max_s = .001  # HTTP falso leva >=5 ms, mesmo sem idade na ESP.
            self.esperar(lambda: c.status == 'vencida')
        finally:
            c.parar()
    def test_jpeg_truncado_e_cabecalho_invalido(self):
        h = HTTPFalso(); h.dados = h.dados[:-2]
        with self.assertRaisesRegex(ValueError, 'truncado'):
            receber_quadro(h, 'http://teste/capture', 1)
        h = HTTPFalso(); h.idade = 'nan'
        with self.assertRaisesRegex(ValueError, 'Idade'):
            receber_quadro(h, 'http://teste/capture', 1)

if __name__ == '__main__':
    unittest.main()
```

</details>

<details>
<summary>tests/test_detector_tracejado.py — arquivo novo completo</summary>

```python
"""Detecção sintética em ROI, sem câmera, serial, modelos ou motores."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg
from visao.detector import DetectorLinha, desenhar_debug


def imagem(xs=(160,), direcao=0., clara=False, altura=240, largura=320):
    fundo, tinta = (20, 220) if clara else (220, 20)
    a = np.full((altura, largura), fundo, np.uint8)
    escala = altura / 240.
    for x in xs:
        for y in (130, 172, 214):
            y = round(y * escala)
            cx = round(x + direcao * (altura * .75 - y))
            cv2.line(a, (cx, y), (round(cx - 20 * escala * direcao), round(y + 20 * escala)),
                     tinta, max(3, round(9 * escala)))
    return a


class TestTracejado(unittest.TestCase):
    def test_centro_deslocamento_e_multiplos_segmentos(self):
        for x in (40, 90, 160, 230, 280):
            with self.subTest(x=x):
                r = DetectorLinha(True).processar(imagem((x,)))
                self.assertTrue(r.achou)
                self.assertEqual(len(r.segmentos), 3)
                self.assertAlmostEqual(r.erro, (x-160)/160, places=2)
                self.assertGreater(r.confianca, 0)
                self.assertTrue(all(y >= 120 for _, y in r.trajetoria))
    def test_direcao_geométrica(self):
        for direcao in (-.3, .3):
            r = DetectorLinha(True).processar(imagem(direcao=direcao))
            self.assertTrue(r.achou)
            self.assertAlmostEqual(r.direcao, direcao, delta=.05)
    def test_linha_clara_e_limiar_fixo(self):
        with patch.object(cfg, 'LINHA_ESCURA', False), patch.object(cfg, 'USAR_OTSU', False):
            r = DetectorLinha(True).processar(imagem((230,), clara=True))
        self.assertTrue(r.achou)
        self.assertGreater(r.erro, .3)
    def test_ausencia_nunca_e_observacao_historica(self):
        d = DetectorLinha(True)
        with patch('visao.detector.time.monotonic', return_value=10.):
            self.assertTrue(d.processar(imagem()).achou)
        with patch('visao.detector.time.monotonic', return_value=10.1):
            r = d.processar(imagem(()))
        self.assertFalse(r.achou)
        self.assertEqual(r.segmentos, ())
        self.assertEqual(d._referencia_t, 10.)
        self.assertEqual(d._referencia.shape, (2, 2))
    def test_memoria_associa_e_expira_sem_guardar_frames(self):
        d = DetectorLinha(True)
        with patch('visao.detector.time.monotonic', return_value=10.):
            d.processar(imagem((240,)))
        with patch('visao.detector.time.monotonic', return_value=10.1):
            r = d.processar(imagem((80, 240)))
        self.assertTrue(r.achou)
        self.assertGreater(r.erro, .4)
        with patch('visao.detector.time.monotonic', return_value=11.):
            r = d.processar(imagem((80, 240)))
        self.assertFalse(r.achou)
        self.assertEqual(r.motivo, 'trajetorias_ambiguas')
        self.assertIsNone(d._referencia)
    def test_formato_tempo_regressivo_e_reset_invalidam_memoria(self):
        for reset in ('forma', 'tempo', 'explicito'):
            d = DetectorLinha(True)
            with patch('visao.detector.time.monotonic', return_value=10.):
                d.processar(imagem((240,)))
            if reset == 'explicito':
                d.limpar_historico()
            quadro = cv2.cvtColor(imagem((80, 240)), cv2.COLOR_GRAY2BGR) if reset == 'forma' else imagem((80, 240))
            with patch('visao.detector.time.monotonic', return_value=9. if reset == 'tempo' else 10.1):
                r = d.processar(quadro)
            self.assertFalse(r.achou)
    def test_ruido_fino_piso_uniforme_e_baixo_contraste(self):
        for brilho in (0, 128, 255):
            self.assertFalse(DetectorLinha(True).processar(np.full((240, 320), brilho, np.uint8)).achou)
        ruido = np.full((240, 320), 220, np.uint8)
        cv2.line(ruido, (80, 120), (100, 239), 20, 1)
        self.assertFalse(DetectorLinha(True).processar(ruido).achou)
        baixo = imagem(); baixo[baixo < 200] = 200
        self.assertFalse(DetectorLinha(True).processar(baixo).achou)
    def test_ambiguidade_sem_historico_abstem(self):
        r = DetectorLinha(True).processar(imagem((80, 240)))
        self.assertFalse(r.achou)
        self.assertEqual(r.motivo, 'trajetorias_ambiguas')
    def test_roi_ignora_linha_acima_do_recorte(self):
        a = imagem(())
        a[10:100, 155:166] = 20
        r = DetectorLinha(True).processar(a)
        self.assertFalse(r.achou)
        self.assertEqual(r.binaria.shape, (120, 320))
    def test_continua_e_quadro_menor_sem_resize(self):
        for altura, largura in ((240, 320), (120, 160)):
            a = np.full((altura, largura), 220, np.uint8)
            a[:, largura//2-4:largura//2+5] = 20
            r = DetectorLinha(True).processar(a)
            self.assertTrue(r.achou)
            self.assertAlmostEqual(r.erro, 0, places=2)
            self.assertEqual(r.binaria.shape, (altura//2, largura))
    def test_limite_de_candidatos_abstem(self):
        a = imagem(())
        for y in (130, 160, 190, 220):
            for x in range(15, 310, 30):
                cv2.rectangle(a, (x, y), (x+5, y+13), 20, -1)
        r = DetectorLinha(True).processar(a)
        self.assertFalse(r.achou)
        self.assertEqual(r.motivo, 'sem_segmentos_compativeis_ou_excesso')
    def test_blur_desativavel_e_debug_nao_alteram_frame(self):
        a = imagem(); antes = a.copy()
        with patch.object(cfg, 'BLUR_KERNEL', 1), patch('visao.detector.cv2.GaussianBlur', side_effect=AssertionError):
            r = DetectorLinha(True).processar(a)
        self.assertTrue(r.achou)
        vis = desenhar_debug(a, r)
        self.assertEqual(vis.shape, (240, 320, 3))
        np.testing.assert_array_equal(a, antes)
        desenhar_debug(a, DetectorLinha(True).processar(imagem(())))
    def test_tracos_colineares_muito_separados_nao_viram_ambiguidade(self):
        a = imagem(())
        cv2.rectangle(a, (155, 122), (165, 152), 20, -1)
        cv2.rectangle(a, (155, 207), (165, 237), 20, -1)
        r = DetectorLinha(True).processar(a)
        self.assertTrue(r.achou)
        self.assertAlmostEqual(r.erro, 0., places=2)
    def test_reaparecimento_corrige_posicao_e_qualidade_baixa_abstem(self):
        d = DetectorLinha(True)
        with patch('visao.detector.time.monotonic', return_value=10.):
            self.assertTrue(d.processar(imagem((160,))).achou)
        with patch('visao.detector.time.monotonic', return_value=10.1):
            self.assertFalse(d.processar(imagem(())).achou)
        with patch('visao.detector.time.monotonic', return_value=10.2):
            r = d.processar(imagem((190,)))
        self.assertTrue(r.achou)
        self.assertGreater(r.erro, .1)
        with patch.object(cfg, 'TRACEJADO_CONFIANCA_MIN', 1.1):
            r = DetectorLinha(True).processar(imagem())
        self.assertFalse(r.achou)
        self.assertEqual(r.motivo, 'suporte_insuficiente')
    def test_padrao_permanece_legado(self):
        r = DetectorLinha().processar(imagem())
        self.assertTrue(r.achou)
        self.assertIsNotNone(r.contorno)
        self.assertEqual(r.segmentos, ())
        self.assertEqual(r.motivo, 'legado')

if __name__ == '__main__':
    unittest.main()
```

</details>

<details>
<summary>tests/test_decisao_visao.py — arquivo novo completo</summary>

```python
"""Etapa 3: decisões e captura injetada, sem serial, áudio, rede ou motores reais."""
import sys
import time
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

import cv2
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as cfg
from estado import EstadoRobo, Modo
from controle import ThreadControle, aplicar_comando, aplicar_movimento_manual, calcular_motores
from visao.detector import ThreadVisao, DetectorLinha
from visao.esp32_cam import CameraESP32, receber_quadro
from test_detector_tracejado import imagem
from test_esp32_fonte import HTTPFalso


class CameraFalsa:
    idade_max_s = .3
    def __init__(self):
        self.status, self.geracao = 'ok', 0
    def saude(self): return dict(status=self.status, geracao=self.geracao)
    def proximo_quadro_detalhado(self, *_a, **_k): return None


class MotorFalso:
    def __init__(self):
        self.cmds = []
        self.eventos = []
        self.distancia = 50
        self.falha = False
        self.status = None
    def motores(self, e, d): self.cmds.append((e, d))
    def parar(self, repetir=1):
        self.cmds.append((0, 0)); self.eventos.append('parar')
    def sensores(self):
        return SimpleNamespace(timestamp=time.monotonic(), distancia_cm=self.distancia,
                               falha_sensor=self.falha, avanco_bloqueado=False)
    def status_servo(self): return self.status
    def obstaculo(self, *_): return False
    def conectar(self): self.eventos.append('conectar')
    def fechar(self): self.eventos.append('fechar')


class TestDecisao(unittest.TestCase):
    def setUp(self):
        self.e = EstadoRobo(); self.e.definir_modo(Modo.SEGUINDO)
        self.m = MotorFalso(); self.f = CameraFalsa(); self.stop = threading.Event()
        self.c = ThreadControle(self.e, self.m, self.stop, self.f)
        self.n = 0
    def publicar(self, t, visivel=True, erro=.4, **kw):
        self.n += 1
        dados = dict(timestamp=t, frame_id=self.n, geracao_camera=self.f.geracao,
                     camera_ok=True, confianca=1., motivo='observada' if visivel else 'sem_linha')
        dados.update(kw)
        self.e.publicar_leitura(erro, visivel, **dados)
    def decidir(self, t, bloqueado=False):
        with self.e.lock: return self.c.decidir_linha(t, bloqueado)
    def parado(self, d): self.assertEqual((d.esq, d.dir), (0, 0))
    def test_nunca_avanca_sem_observacao_inicial(self):
        self.parado(self.decidir(10.))
        for t in (10.1, 10.3, 10.7):
            self.publicar(t, False)
            self.parado(self.decidir(t+.01))
        self.publicar(11.)
        self.assertGreater(self.decidir(11.01).esq, 0)
    def test_pd_e_ganhos_preservados_e_direcao_considerada(self):
        self.assertEqual((cfg.KP, cfg.KD, cfg.KD_FILTRO), (90., 25., 1.))
        self.publicar(10.)
        d = self.decidir(10.01)
        self.assertEqual((d.esq, d.dir), calcular_motores(.4, 0.))
        self.publicar(10.1, erro=0., direcao=.3, escala_direcao=.75)
        self.assertGreater(self.decidir(10.11).erro, 0.)
        self.assertEqual(self.m.cmds, [])  # cálculo não aciona saída
    def test_vao_limitado_desacelera_e_nao_renova_observacao(self):
        self.publicar(10.); observado = self.decidir(10.01)
        for t in (10.1, 10.3, 10.55):
            self.publicar(t, False)
            d = self.decidir(t+.01)
            self.assertTrue(d.estimada)
            self.assertGreater(d.esq, 0)
            self.assertLess(d.esq, observado.esq)
            self.assertEqual(self.c._linha_ultima.timestamp, 10.)
        self.publicar(10.61, False)
        d = self.decidir(10.62); self.parado(d)
        self.assertEqual(d.motivo, 'linha_perdida')
        self.publicar(10.7, False); self.parado(self.decidir(10.71))
    def test_frame_antigo_nao_usa_tolerancia_do_tracejado(self):
        self.publicar(10.); self.decidir(10.01)
        d = self.decidir(10.31); self.parado(d)
        self.assertEqual(d.motivo, 'frame_vencido')
        self.publicar(10.4, False); self.parado(self.decidir(10.41))
    def test_idade_total_inclui_esp_e_http(self):
        self.publicar(10., idade_captura_s=.25)
        d = self.decidir(10.1); self.parado(d)
        self.assertEqual(d.motivo, 'frame_vencido')
        self.publicar(11., idade_captura_s=.1); self.decidir(11.01)
        self.publicar(11.51, False); self.parado(self.decidir(11.52))
    def test_camera_falha_independente_da_publicacao_da_visao(self):
        self.publicar(10.); self.decidir(10.01)
        self.f.status = 'erro'
        d = self.decidir(10.02); self.parado(d)
        self.assertEqual(d.motivo, 'camera_indisponivel')
    def test_recuperacao_entre_ciclos_nao_reaproveita_memoria(self):
        self.publicar(10.); self.decidir(10.01)
        self.f.geracao += 1  # falha e recuperação antes do próximo ciclo
        self.publicar(10.1, False)
        self.parado(self.decidir(10.11))
        self.publicar(10.2, erro=-.3)
        d = self.decidir(10.21); self.assertLess(d.esq, d.dir)
    def test_resultado_de_geracao_antiga_e_descartado(self):
        self.publicar(10.); self.f.geracao += 1
        self.parado(self.decidir(10.01))
    def test_modo_pare_siga_e_publicacao_atrasada(self):
        self.publicar(10.); self.decidir(10.01)
        antiga = self.e.sessao_visao
        aplicar_comando(self.e, self.m, 'pare')
        self.e.definir_modo(Modo.SEGUINDO)
        self.assertFalse(self.e.publicar_leitura(.4, True, sessao=antiga))
        self.parado(self.decidir(10.1))
        self.publicar(10.2, False); self.parado(self.decidir(10.21))
    def test_manual_prevalece_e_nao_recebe_resultado_visual_atrasado(self):
        antiga = self.e.sessao_visao
        aplicar_movimento_manual(self.e, self.m, 50, 60)
        self.assertFalse(self.e.publicar_leitura(.4, True, sessao=antiga))
        self.parado(self.decidir(10.))
        self.assertEqual(self.m.cmds[-1], (50, 60))
    def test_bloqueio_exige_nova_observacao_apos_liberar(self):
        self.publicar(10.); self.decidir(10.01)
        self.parado(self.decidir(10.1, True))
        self.parado(self.decidir(10.11))
        self.publicar(10.2, False); self.parado(self.decidir(10.21))
        self.publicar(10.3); self.assertGreater(self.decidir(10.31).esq, 0)
    def test_ambiguidade_baixa_confianca_e_numeros_invalidos_param(self):
        for kw in (dict(confianca=.1), dict(erro=float('nan')),
                   dict(direcao=float('inf')), dict(idade_captura_s=-.1),
                   dict(confianca=float('nan'))):
            self.publicar(10., **kw); self.parado(self.decidir(10.01))
        self.publicar(11.); self.decidir(11.01)
        self.publicar(11.1, False, motivo='trajetorias_ambiguas')
        self.parado(self.decidir(11.11))
    def test_reaparecimento_zera_derivada_apos_vao(self):
        self.publicar(10.); self.decidir(10.01)
        self.publicar(10.1, False); self.decidir(10.11)
        self.publicar(10.2, erro=-.4)
        d = self.decidir(10.21)
        self.assertEqual((d.esq, d.dir), calcular_motores(-.4, 0.))
    def test_sensor_invalido_bloqueia_seguir_sem_mudar_manual_v4(self):
        self.m.falha = True; self.m.distancia = None
        self.m.status = SimpleNamespace(ativo=True, sonar_movimento=True, timestamp=time.monotonic())
        self.assertTrue(self.c._obstaculo())
        self.e.definir_manual(50, 50)
        self.assertFalse(self.c._obstaculo())
        self.e.definir_modo(Modo.SEGUINDO); self.m.falha = False
        for distancia in (None, float('nan'), -1):
            self.m.distancia = distancia; self.assertTrue(self.c._obstaculo())
    def test_acao_legada_nao_substitui_validacao_esp32(self):
        self.publicar(10.)
        with patch.object(cfg, 'APRENDIZADO_ATIVO', True):
            self.parado(self.decidir(10.01))
    def test_ultrassom_vencido_e_modo4_ainda_ativo_bloqueiam_seguir(self):
        with patch.object(self.m, 'sensores', return_value=None):
            self.assertTrue(self.c._obstaculo())
        antigo = SimpleNamespace(timestamp=time.monotonic()-1, distancia_cm=50,
                                 falha_sensor=False, avanco_bloqueado=False)
        with patch.object(self.m, 'sensores', return_value=antigo):
            self.assertTrue(self.c._obstaculo())
        self.m.status = SimpleNamespace(ativo=True, sonar_movimento=True, timestamp=time.monotonic())
        self.assertTrue(self.c._obstaculo())
    def test_encerramento_recusa_comandos_tardios(self):
        self.e.encerrar()
        aplicar_movimento_manual(self.e, self.m, 100, 100)
        aplicar_comando(self.e, self.m, 'siga')
        aplicar_comando(self.e, self.m, 'voltar')
        self.assertEqual(self.m.cmds, [])
        self.assertEqual(self.e.modo, Modo.PARADO)
        self.assertFalse(self.e.publicar_leitura(.4, True))
        self.assertFalse(self.e.publicar_acao(.4))
    def test_encerramento_e_excecao_sempre_param(self):
        self.publicar(10.); self.stop.set(); self.parado(self.decidir(10.01))
        self.c.run(); self.assertEqual(self.m.cmds[-1], (0, 0))
        self.stop.clear()
        with patch.object(self.c, '_loop', side_effect=RuntimeError('falha simulada')), self.assertLogs('controle', level='ERROR'):
            self.c.run()
        self.assertTrue(self.stop.is_set())
        self.assertEqual(self.m.cmds[-1], (0, 0))


class TestPublicacao(unittest.TestCase):
    def setUp(self):
        self.e = EstadoRobo(); self.e.definir_modo(Modo.SEGUINDO)
        self.f = CameraFalsa(); self.stop = threading.Event()
        self.v = ThreadVisao(self.e, self.stop, self.f)
        self.d = DetectorLinha(True)
        self.meta = dict(recepcao_monotonica=10., idade_captura_s=.02, geracao_camera=0)
    def test_publica_metadados_sem_renovar_recebimento(self):
        with patch('visao.detector.time.monotonic', return_value=10.05):
            r = self.v._processar_detalhado(self.d, (7, imagem(), self.meta), self.e.sessao_visao)
        self.assertTrue(r.achou)
        l = self.e.ler_leitura()
        self.assertEqual((l.timestamp, l.frame_id), (10., 7))
        self.assertAlmostEqual(l.idade(10.1), .12)
        self.assertEqual(l.escala_direcao, .75)
    def test_falha_ou_pare_durante_processamento_descarta_resultado(self):
        original = self.d.processar
        for evento in ('camera', 'modo'):
            def processar(a):
                r = original(a)
                if evento == 'camera': self.f.geracao += 1
                else: self.e.definir_modo(Modo.PARADO)
                return r
            with patch('visao.detector.time.monotonic', return_value=10.05), patch.object(self.d, 'processar', side_effect=processar):
                self.assertIsNone(self.v._processar_detalhado(self.d, (7, imagem(), self.meta), self.e.sessao_visao))
            self.assertFalse(self.e.ler_leitura().linha_visivel)
            self.f.geracao = 0; self.e.definir_modo(Modo.SEGUINDO)
    def test_frame_velho_nem_e_processado(self):
        with patch('visao.detector.time.monotonic', return_value=11.), patch.object(self.d, 'processar') as processar:
            self.assertIsNone(self.v._processar_detalhado(self.d, (7, imagem(), self.meta), self.e.sessao_visao))
            processar.assert_not_called()
        self.assertFalse(self.e.ler_leitura().camera_ok)


class TestIntegracaoSemHardware(unittest.TestCase):
    def esperar(self, cond, prazo=2.):
        limite = time.monotonic()+prazo
        while not cond() and time.monotonic() < limite: time.sleep(.005)
        self.assertTrue(cond())
    def test_http_falso_visao_estado_pd_vãos_falha_e_retomada(self):
        h = HTTPFalso(); h.dados = cv2.imencode('.jpg', imagem())[1].tobytes()
        fonte = CameraESP32(opener=h, reconexao_s=.02)
        e=EstadoRobo();e.definir_modo(Modo.SEGUINDO)
        m=MotorFalso();stop=threading.Event()
        v=ThreadVisao(e, stop, fonte);c=ThreadControle(e,m,stop,fonte)
        fonte.iniciar();v.start();c.start()
        try:
            self.esperar(lambda: c.decisao_linha.motivo == 'observada')
            self.assertTrue(any(a != (0,0) for a in m.cmds))
            h.falhar=True;self.esperar(lambda: fonte.status == 'erro')
            self.esperar(lambda: c.decisao_linha.motivo == 'camera_indisponivel')
            h.dados=cv2.imencode('.jpg', imagem(()))[1].tobytes()
            h.falhar=False
            self.esperar(lambda: fonte.status == 'ok')
            time.sleep(.08);self.assertEqual((c.decisao_linha.esq,c.decisao_linha.dir),(0,0))
            h.dados=cv2.imencode('.jpg', imagem((230,)))[1].tobytes()
            self.esperar(lambda: c.decisao_linha.motivo == 'observada')
            self.assertGreater(c.decisao_linha.esq,c.decisao_linha.dir)
            h.dados=cv2.imencode('.jpg', imagem(()))[1].tobytes()
            self.esperar(lambda: c.decisao_linha.estimada)
            self.esperar(lambda: c.decisao_linha.esq == c.decisao_linha.dir == 0)
        finally:
            stop.set();c.join(2);v.join(2);fonte.parar()
        self.assertFalse(c.is_alive() or v.is_alive())
        self.assertEqual(m.cmds[-1],(0,0))
    def test_main_recusa_cnn_incompativel_antes_de_criar_motor(self):
        import main
        with patch.object(sys, 'argv', ['main.py', '--fonte-imagem', 'esp32']), patch.object(cfg, 'APRENDIZADO_ATIVO', True), patch.object(main, 'ArduinoSerial') as serial, patch.object(main, 'ArduinoNulo') as nulo:
            with self.assertRaises(SystemExit) as erro: main.main()
            self.assertEqual(erro.exception.code, 2)
            serial.assert_not_called(); nulo.assert_not_called()
    def test_snapshot_atomico_e_geracao_da_fonte(self):
        f=CameraESP32();q=receber_quadro(HTTPFalso(),'http://falso/capture',1)
        with f._cond:
            f._status='ok';f._quadro=q;f._id=1
        a=f.proximo_quadro_detalhado(0,0)
        self.assertIs(a[1],q.imagem)
        self.assertEqual(a[2]['recepcao_monotonica'],q.recepcao_monotonica)
        with f._cond: f._invalidar('erro')
        self.assertGreater(f.saude()['geracao'],a[2]['geracao_camera'])
        self.assertIsNone(f.metadados(1))
    def test_main_falha_parcial_para_antes_de_join_e_fecha_recursos(self):
        import main
        m=MotorFalso();fonte=Mock()
        tc=Mock();tv=Mock();voz=Mock()
        tc.join.side_effect=lambda **_: m.eventos.append('join')
        voz.start.side_effect=RuntimeError('falha inicial simulada')
        with patch.object(sys,'argv',['main.py','--sem-arduino','--fonte-imagem','esp32']), patch.object(cfg,'REMOTO_BT_ATIVO',False), patch.object(main,'ArduinoNulo',return_value=m), patch.object(main,'ArduinoSerial',side_effect=AssertionError('serial proibida')), patch.object(main,'abrir_fonte',return_value=fonte), patch.object(main,'ThreadControle',return_value=tc), patch.object(main,'ThreadVisao',return_value=tv), patch.object(main,'ThreadVoz',return_value=voz), patch.object(main.signal,'signal'):
            with self.assertRaisesRegex(RuntimeError,'falha inicial'):main.main()
        self.assertLess(m.eventos.index('parar'),m.eventos.index('join'))
        self.assertIn('fechar',m.eventos);fonte.parar.assert_called_once()

if __name__ == '__main__': unittest.main()
```

</details>

<details>
<summary>tools/testar_decisao_esp32.py — arquivo novo completo</summary>

```python
"""Teste da ESP32 + visão + PD com ultrassom simulado; nunca abre serial física."""
import argparse
import csv
import json
import math
import sys
import threading
import time
from collections import deque
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg
from controle import ThreadControle
from estado import EstadoRobo, Modo
from motor.nulo import ArduinoNulo
from visao.detector import DetectorLinha, ThreadVisao, desenhar_debug
from visao.esp32_cam import CameraESP32
from visao.recorte_esp32 import RecorteESP32

JANELA = 'ESP32 - decisao SIMULADA - q sai'
CAMPOS = ('tempo_s', 'frame_id', 'novo_frame', 'camera', 'geracao', 'ultrassom_simulado',
          'linha_visivel', 'erro_horizontal', 'erro_controle', 'direcao', 'confianca',
          'estimada', 'decisao', 'motivo', 'esq_simulado', 'dir_simulado',
          'idade_frame_ms', 'idade_observacao_ms', 'http_ms', 'visao_ms', 'decisao_ms',
          'fps_captura', 'fps_visao')


class MotorTeste(ArduinoNulo):
    """Somente nesta ferramenta: leituras fictícias, guardas reais preservadas."""
    def __init__(self, ultrassom):
        super().__init__()
        self.ultrassom = ultrassom

    def sensores(self):
        distancia = {'livre': 100, 'obstaculo': 0, 'invalido': None}[self.ultrassom]
        return SimpleNamespace(timestamp=time.monotonic(), distancia_cm=distancia,
                               falha_sensor=distancia is None,
                               avanco_bloqueado=self.ultrassom == 'obstaculo')

    def obstaculo(self, *_):
        return self.ultrassom == 'obstaculo'


class Medidas:
    """Estatísticas numéricas limitadas; não armazena imagens."""
    def __init__(self):
        self.n = 0
        self.soma = 0.
        self.ultimas = deque(maxlen=600)

    def adicionar(self, valor):
        if valor is not None and math.isfinite(valor):
            self.n += 1
            self.soma += valor
            self.ultimas.append(valor)

    def resumo(self):
        return dict(amostras=self.n, media_ms=self.soma / self.n if self.n else None,
                    p95_ultimas_600_ms=float(np.percentile(self.ultimas, 95)) if self.n else None)


def nome_decisao(decisao):
    if decisao.esq == decisao.dir == 0:
        return 'PARAR'
    if decisao.esq > decisao.dir:
        return 'DIREITA'
    if decisao.esq < decisao.dir:
        return 'ESQUERDA'
    return 'RETO'


class SimuladorVisao:
    def __init__(self, fonte, ultrassom='livre'):
        self.fonte = fonte
        self.estado = EstadoRobo()
        self.estado.definir_modo(Modo.SEGUINDO)
        self.parar = threading.Event()
        self.motor = MotorTeste(ultrassom)  # não há opção de Arduino real
        self.controle = ThreadControle(self.estado, self.motor, self.parar, fonte)
        self.visao = ThreadVisao(self.estado, self.parar, fonte)
        self.detector = DetectorLinha(tracejado=True)
        self.orientacao = RecorteESP32(espelhar_h=cfg.IMAGEM_ESPELHAR_H,
                                      espelhar_v=cfg.IMAGEM_ESPELHAR_V)
        self.ultimo_id = fonte.id_atual()
        self.frame = self.resultado = self.meta = None
        self.processados = 0
        self.inicio = time.monotonic()
        self.medidas = {n: Medidas() for n in ('http', 'visao', 'decisao', 'idade_no_uso')}

    def atualizar(self):
        quadro = self.fonte.proximo_quadro_detalhado(self.ultimo_id, timeout=0.)
        novo, visao_ms = False, None
        if quadro is not None:
            self.ultimo_id, frame, meta = quadro
            if self.estado.modo is Modo.SEGUINDO:
                inicio = time.perf_counter()
                frame = self.orientacao.orientar(frame)
                r = self.visao._processar_detalhado(
                    self.detector, (self.ultimo_id, frame, meta), self.estado.sessao_visao)
                visao_ms = (time.perf_counter() - inicio) * 1000
                if r is not None:
                    self.frame, self.resultado, self.meta = frame, r, meta
                    self.processados += 1
                    novo = True
                    self.medidas['visao'].adicionar(visao_ms)
                    self.medidas['http'].adicionar(meta['http_ms'])
        if self.meta is not None and not self.visao._camera_valida(self.meta):
            self.frame = self.resultado = self.meta = None
        saude = self.fonte.saude()
        if saude['status'] != 'ok':
            self.detector.limpar_historico()
            self.estado.publicar_leitura(0., False, camera_ok=False,
                                         motivo='sem_quadros', sessao=self.estado.sessao_visao)
        inicio = time.perf_counter()
        with self.estado.lock:
            bloqueado = self.controle._inspecionar_obstaculo(time.monotonic()) or self.controle._obstaculo()
            decisao = self.controle.decidir_linha(time.monotonic(), bloqueado)
            leitura = self.estado.ler_leitura()
        decisao_ms = (time.perf_counter() - inicio) * 1000
        self.medidas['decisao'].adicionar(decisao_ms)
        agora = time.monotonic()
        idade = leitura.idade(agora) * 1000 if self.meta is not None else None
        self.medidas['idade_no_uso'].adicionar(idade)
        captura = self.fonte.estatisticas
        return dict(tempo_s=agora-self.inicio, frame_id=leitura.frame_id if self.meta is not None else None, novo_frame=novo,
                    camera=saude['status'], geracao=saude['geracao'],
                    ultrassom_simulado=self.motor.ultrassom,
                    linha_visivel=bool(self.meta is not None and leitura.linha_visivel),
                    erro_horizontal=leitura.erro if leitura.linha_visivel and self.meta is not None else None,
                    erro_controle=decisao.erro, direcao=leitura.direcao if self.meta is not None else 0.,
                    confianca=leitura.confianca if self.meta is not None else 0.,
                    estimada=decisao.estimada, decisao=nome_decisao(decisao), motivo=decisao.motivo,
                    esq_simulado=decisao.esq, dir_simulado=decisao.dir,
                    idade_frame_ms=idade,
                    idade_observacao_ms=decisao.idade_observacao_s*1000 if decisao.idade_observacao_s is not None else None,
                    http_ms=self.meta['http_ms'] if self.meta is not None else None,
                    visao_ms=visao_ms if novo else None, decisao_ms=decisao_ms,
                    fps_captura=captura['fps'], fps_visao=self.processados/max(agora-self.inicio, 1e-9))

    def tecla(self, tecla):
        if tecla == ord('q'):
            return False
        if tecla in (ord('1'), ord('2'), ord('3')):
            self.motor.ultrassom = {ord('1'): 'livre', ord('2'): 'obstaculo', ord('3'): 'invalido'}[tecla]
        if tecla in (ord('p'), ord(' ')):
            self.estado.definir_modo(Modo.PARADO if self.estado.modo is Modo.SEGUINDO else Modo.SEGUINDO)
            self.detector.limpar_historico()
            self.ultimo_id = self.fonte.id_atual()
            self.frame = self.resultado = self.meta = None
        return True

    def resumo(self):
        tempo = time.monotonic()-self.inicio
        captura = self.fonte.estatisticas
        return dict(motores='NULOS', ultrassom='SIMULADO', tempo_s=tempo,
                    frames_processados=self.processados, fps_visao=self.processados/max(tempo, 1e-9),
                    captura=captura, medidas={n: m.resumo() for n, m in self.medidas.items()})

    def encerrar(self):
        self.parar.set()
        self.estado.encerrar()
        try:
            self.motor.parar(repetir=3)
        finally:
            self.fonte.parar()


def formatar(valor, casas=1):
    return '--' if valor is None else f'{valor:.{casas}f}'


def montar_painel(simulador, dados):
    painel = np.zeros((390, 750, 3), np.uint8)
    cv2.putText(painel, 'SIMULACAO - NENHUM MOTOR REAL - ULTRASSOM FICTICIO',
                (10, 22), cv2.FONT_HERSHEY_SIMPLEX, .49, (0, 220, 255), 1)
    if simulador.frame is not None and simulador.resultado is not None:
        imagem = desenhar_debug(simulador.frame, simulador.resultado)
        if dados['estimada']:
            h, w = imagem.shape[:2]
            x = int(np.clip((1+dados['erro_controle'])*w/2, 0, w-1))
            cv2.line(imagem, (x, simulador.resultado.y0), (x, h-1), (255, 0, 255), 2)
            cv2.putText(imagem, 'ESTIMADA', (5, 50), cv2.FONT_HERSHEY_SIMPLEX, .45, (255, 0, 255), 1)
        painel[38:278, 10:330] = imagem
    else:
        cv2.putText(painel, 'SEM FRAME ATUAL', (35, 150), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 0, 255), 1)
    linhas = [
        'Decisao simulada: '+dados['decisao'],
        'Motivo: '+dados['motivo'],
        'Camera: '+dados['camera']+' | geracao='+str(dados['geracao']),
        'ULTRASSOM SIMULADO: '+dados['ultrassom_simulado'],
        f"Saidas E/D (sim): {dados['esq_simulado']}/{dados['dir_simulado']}",
        'Erro horizontal: '+formatar(dados['erro_horizontal'], 3),
        'Erro controle: '+formatar(dados['erro_controle'], 3),
        'Direcao: '+formatar(dados['direcao'], 3)+' | qualidade: '+formatar(dados['confianca'], 2),
        'Idade frame <= '+formatar(dados['idade_frame_ms'])+' ms',
        'Ultima observacao <= '+formatar(dados['idade_observacao_ms'])+' ms',
        'HTTP: '+formatar(dados['http_ms'])+' ms',
        'Visao/decisao: '+formatar(dados['visao_ms'])+'/'+formatar(dados['decisao_ms'])+' ms',
        'FPS captura/visao: '+formatar(dados['fps_captura'])+'/'+formatar(dados['fps_visao']),
    ]
    for i, linha in enumerate(linhas):
        cv2.putText(painel, linha, (345, 50+i*22), cv2.FONT_HERSHEY_SIMPLEX, .42, (220, 220, 220), 1)
    for i, linha in enumerate(('Verde: tracos | amarelo: trajetoria',
                               'Magenta: estimativa limitada no vao',
                               '1 livre | 2 obstaculo | 3 invalido', 'p/espaco: pausar | q: sair')):
        cv2.putText(painel, linha, (10, 302+i*22), cv2.FONT_HERSHEY_SIMPLEX, .42, (200, 200, 200), 1)
    return painel


def argumentos(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default=cfg.ESP32_URL)
    parser.add_argument('--timeout', type=float, default=cfg.ESP32_TIMEOUT_S)
    parser.add_argument('--ultrassom', choices=('livre', 'obstaculo', 'invalido'), default='livre',
                        help='cenário fictício; não lê o Arduino')
    parser.add_argument('--sem-janela', action='store_true')
    parser.add_argument('--duracao', type=float, help='limite em segundos; Ctrl+C também encerra')
    parser.add_argument('--csv', type=Path, help='arquivo novo; recusa sobrescrever')
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error('timeout deve ser positivo e finito')
    if args.duracao is not None and (not math.isfinite(args.duracao) or args.duracao <= 0):
        parser.error('duracao deve ser positiva e finita')
    return args


def executar(args, fonte=None):
    fonte = fonte if fonte is not None else CameraESP32(
        args.url, args.timeout, cfg.ESP32_IDADE_MAX_S, cfg.ESP32_RECONEXAO_S)
    simulador = SimuladorVisao(fonte, args.ultrassom)
    print('SIMULACAO: motor nulo, sem serial, voz ou Bluetooth; ultrassom SIMULADO='+args.ultrassom, flush=True)
    resumo = None
    with ExitStack() as recursos:
        recursos.callback(simulador.encerrar)
        escritor = None
        if args.csv is not None:
            arquivo = recursos.enter_context(args.csv.open('x', newline='', encoding='utf-8', buffering=1))
            escritor = csv.DictWriter(arquivo, fieldnames=CAMPOS)
            escritor.writeheader()
        if not args.sem_janela:
            cv2.namedWindow(JANELA, cv2.WINDOW_NORMAL)
            recursos.callback(cv2.destroyAllWindows)
        fonte.iniciar()
        proximo_log = simulador.inicio
        try:
            while args.duracao is None or time.monotonic()-simulador.inicio < args.duracao:
                inicio = time.monotonic()
                dados = simulador.atualizar()
                if escritor is not None:
                    escritor.writerow(dados)
                if not args.sem_janela:
                    cv2.imshow(JANELA, montar_painel(simulador, dados))
                    if not simulador.tecla(cv2.waitKey(1) & 0xFF) or cv2.getWindowProperty(JANELA, cv2.WND_PROP_VISIBLE) < 1:
                        break
                if time.monotonic() >= proximo_log:
                    print(f"{dados['decisao']} ({dados['motivo']}) camera={dados['camera']} "
                          f"FPS captura/visao={dados['fps_captura']:.2f}/{dados['fps_visao']:.2f} "
                          f"idade<={formatar(dados['idade_frame_ms'])} ms", flush=True)
                    proximo_log = time.monotonic()+1
                simulador.parar.wait(max(0., 1/cfg.FREQ_CONTROLE_HZ-(time.monotonic()-inicio)))
        except KeyboardInterrupt:
            pass
        resumo = simulador.resumo()
    return resumo


def main():
    args = argumentos()
    try:
        resumo = executar(args)
    except (OSError, ValueError, cv2.error) as erro:
        print(f'Erro no teste: {erro}', file=sys.stderr)
        return 1
    print(json.dumps(resumo, ensure_ascii=False, sort_keys=True))
    return 0 if resumo['frames_processados'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
```

</details>

<details>
<summary>tests/test_visual_decisao_esp32.py — arquivo novo completo</summary>

```python
"""Prévia integrada: câmera/GUI injetadas; nenhuma serial ou atuação física."""
import csv
import io
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tools import testar_decisao_esp32 as ferramenta
from visao.esp32_cam import CameraESP32, QuadroESP32
from test_detector_tracejado import imagem
from test_esp32_fonte import HTTPFalso


class TestSimulador(unittest.TestCase):
    def setUp(self):
        self.tempo = 10.
        self.relogio = patch('time.monotonic', side_effect=lambda: self.tempo)
        self.relogio.start()
        self.fonte = CameraESP32()
        self.fonte._inicio = 9.5
        self.sim = ferramenta.SimuladorVisao(self.fonte)
    def tearDown(self):
        self.sim.encerrar()
        self.relogio.stop()
    def publicar(self, t, xs=(160,), idade_ms=1.):
        self.tempo = t
        with self.fonte._cond:
            self.fonte._id += 1
            self.fonte._validos += 1
            self.fonte._status = 'ok'
            self.fonte._quadro = QuadroESP32(b'', imagem(xs), t, '', 2., idade_ms)
        return self.sim.atualizar()
    def test_centro_esquerda_direita_e_motores_nulos(self):
        for i, (xs, nome) in enumerate([((80,), 'ESQUERDA'), ((160,), 'RETO'), ((240,), 'DIREITA')]):
            self.sim.tecla(ord('p'));self.sim.tecla(ord('p'))
            dados = self.publicar(10.1+i*.1, xs)
            self.assertEqual(dados['decisao'], nome)
            self.assertEqual(dados['motivo'], 'observada')
            self.assertTrue(dados['novo_frame'])
            self.assertEqual(self.sim.motor.ultimo, (0, 0))
            self.assertEqual(self.sim.motor.estatisticas['comandos'], 0)
    def test_sem_linha_inicial_fica_parado(self):
        dados = self.publicar(10.1, ())
        self.assertEqual(dados['decisao'], 'PARAR')
        self.assertFalse(dados['linha_visivel'])
    def test_vao_limitado_e_reaparecimento(self):
        self.publicar(10.1, (240,))
        dados = self.publicar(10.2, ())
        self.assertTrue(dados['estimada'])
        self.assertEqual(dados['decisao'], 'DIREITA')
        self.assertIsNone(dados['erro_horizontal'])
        dados = self.publicar(10.75, ())
        self.assertEqual(dados['decisao'], 'PARAR')
        self.assertEqual(dados['motivo'], 'linha_perdida')
        dados = self.publicar(10.85, (80,))
        self.assertEqual(dados['decisao'], 'ESQUERDA')
    def test_frames_repetidos_nao_inflam_fps_ou_renovam_idade(self):
        self.publicar(10.1)
        for t in (10.12, 10.16, 10.2):
            self.tempo=t;dados=self.sim.atualizar()
            self.assertFalse(dados['novo_frame'])
            self.assertEqual(self.sim.processados, 1)
            self.assertAlmostEqual(dados['fps_visao'], 1/(t-10.))
        self.assertGreater(dados['idade_frame_ms'], 90.)
    def test_expiracao_ou_desconexao_apaga_imagem_e_para(self):
        self.publicar(10.1)
        self.tempo=10.5;dados=self.sim.atualizar()
        self.assertEqual(dados['decisao'], 'PARAR')
        self.assertIsNone(self.sim.frame)
        self.assertIsNone(dados['idade_frame_ms'])
        self.assertIsNone(dados['frame_id'])
        self.assertEqual(dados['direcao'], 0.)
        self.publicar(10.6)
        with self.fonte._cond:self.fonte._invalidar('erro')
        self.tempo=10.61;dados=self.sim.atualizar()
        self.assertEqual(dados['camera'], 'erro')
        self.assertEqual(dados['decisao'], 'PARAR')
        self.assertIsNone(self.sim.frame)
        dados=self.publicar(10.7, ())
        self.assertEqual(dados['decisao'], 'PARAR')
    def test_ultrassom_simulado_bloqueia_e_exige_nova_observacao(self):
        self.publicar(10.1)
        for tecla in (ord('2'), ord('3')):
            self.sim.tecla(tecla);self.tempo+=.01
            dados=self.sim.atualizar()
            self.assertEqual(dados['decisao'], 'PARAR')
            self.assertEqual(dados['motivo'], 'obstaculo_ou_sensor')
        self.sim.tecla(ord('1'));self.tempo+=.01
        self.assertEqual(self.sim.atualizar()['decisao'], 'PARAR')
        self.assertEqual(self.publicar(10.2)['decisao'], 'RETO')
    def test_pausa_e_retomada_nao_usam_frame_anterior(self):
        self.publicar(10.1)
        self.sim.tecla(ord('p'));self.tempo=10.11
        self.assertEqual(self.sim.atualizar()['decisao'], 'PARAR')
        self.sim.tecla(ord('p'));self.tempo=10.12
        self.assertEqual(self.sim.atualizar()['decisao'], 'PARAR')
        self.assertEqual(self.publicar(10.2)['decisao'], 'RETO')
    def test_painel_mostra_dados_sem_alterar_frame(self):
        dados=self.publicar(10.1)
        original=self.sim.frame.copy()
        with patch.object(cv2,'putText',wraps=cv2.putText) as texto:
            painel=ferramenta.montar_painel(self.sim,dados)
        frases=' '.join(c.args[1] for c in texto.call_args_list)
        self.assertIn('NENHUM MOTOR REAL',frases)
        self.assertIn('ULTRASSOM SIMULADO',frases)
        self.assertIn('Decisao simulada: RETO',frases)
        self.assertIn('FPS captura/visao',frases)
        self.assertEqual(painel.shape,(390,750,3))
        np.testing.assert_array_equal(original,self.sim.frame)
    def test_painel_estimada_e_marcada_separadamente(self):
        self.publicar(10.1,(240,));dados=self.publicar(10.2,())
        with patch.object(cv2,'putText',wraps=cv2.putText) as texto:
            ferramenta.montar_painel(self.sim,dados)
        self.assertIn('ESTIMADA',[c.args[1] for c in texto.call_args_list])
    def test_estatisticas_tem_historico_numerico_limitado(self):
        medida=ferramenta.Medidas()
        for i in range(1000):medida.adicionar(float(i))
        medida.adicionar(None)
        self.assertEqual(len(medida.ultimas),600)
        self.assertEqual(medida.resumo()['amostras'],1000)
        self.assertEqual(medida.resumo()['media_ms'],499.5)


class TestExecucao(unittest.TestCase):
    def fonte(self):
        http=HTTPFalso()
        http.dados=cv2.imencode('.jpg',imagem())[1].tobytes()
        return CameraESP32(opener=http,reconexao_s=.01)
    def test_sem_janela_csv_e_encerramento_sem_serial(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho=Path(pasta)/'medicoes.csv'
            args=ferramenta.argumentos(['--sem-janela','--duracao','.2','--csv',str(caminho)])
            fonte=self.fonte()
            with patch.object(ferramenta,'montar_painel',side_effect=AssertionError('GUI proibida')), patch.object(cv2,'namedWindow',side_effect=AssertionError('GUI proibida')), patch('serial.Serial',side_effect=AssertionError('serial proibida')), redirect_stdout(io.StringIO()):
                resumo=ferramenta.executar(args,fonte)
            self.assertGreater(resumo['frames_processados'],0)
            self.assertIsNotNone(resumo['medidas']['http']['media_ms'])
            self.assertEqual(resumo['motores'],'NULOS')
            self.assertFalse(fonte._thread.is_alive())
            with caminho.open() as arq:linhas=list(csv.DictReader(arq))
            self.assertEqual(set(linhas[0]),set(ferramenta.CAMPOS))
            self.assertTrue(all(l['ultrassom_simulado']=='livre' for l in linhas))
    def test_nao_sobrescreve_csv_existente(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho=Path(pasta)/'preservar.csv';caminho.write_text('original')
            args=ferramenta.argumentos(['--sem-janela','--csv',str(caminho)])
            fonte=self.fonte()
            with patch.object(fonte,'iniciar') as iniciar, redirect_stdout(io.StringIO()):
                with self.assertRaises(FileExistsError):ferramenta.executar(args,fonte)
            iniciar.assert_not_called()
            self.assertEqual(caminho.read_text(),'original')
    def test_q_fecha_janela_e_fonte_com_gui_simulada(self):
        args=ferramenta.argumentos([]);fonte=self.fonte()
        with patch.object(cv2,'namedWindow'),patch.object(cv2,'imshow') as mostrar,patch.object(cv2,'waitKey',return_value=ord('q')),patch.object(cv2,'destroyAllWindows') as fechar,redirect_stdout(io.StringIO()):
            ferramenta.executar(args,fonte)
        mostrar.assert_called_once();fechar.assert_called_once()
        self.assertFalse(fonte._thread.is_alive())
    def test_excecao_gui_tambem_encerra(self):
        args=ferramenta.argumentos([]);fonte=self.fonte()
        with patch.object(cv2,'namedWindow'),patch.object(cv2,'imshow',side_effect=RuntimeError('GUI simulada')),patch.object(cv2,'destroyAllWindows') as fechar,redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError,'GUI simulada'):ferramenta.executar(args,fonte)
        fechar.assert_called_once();self.assertFalse(fonte._thread.is_alive())
    def test_argumentos_invalidos(self):
        for arg in (['--timeout','nan'],['--duracao','0'],['--duracao','inf']):
            with redirect_stdout(io.StringIO()),patch('sys.stderr',new=io.StringIO()):
                with self.assertRaises(SystemExit):ferramenta.argumentos(arg)

if __name__=='__main__':unittest.main()
```

</details>

## Anexo C — outros arquivos Python modificados

Não há cópia inicial completa destes três arquivos para um diff integral desde
a Etapa 1. As alterações estão descritas acima; seguem cópias do conteúdo
atual. Elas não significam que todo o código desses arquivos foi criado nesta
tarefa: código preexistente foi preservado.

<details>
<summary>visao/fontes.py — conteúdo atual</summary>

```python
"""Fontes de imagem para a visão. Todas oferecem  id_atual()  e  proximo_quadro(apos_id, timeout).

  arduino  : OV7670 ligada ao Arduino; a imagem chega pela serial (ArduinoSerial já tem id_atual/proximo_quadro) <- a atual.
  csi      : câmera no conector CSI da Pi (Raspberry Pi Camera Rev 1.3), via picamera2. Código mantido, NÃO é a câmera do projeto.
  esp32    : JPEG HTTP contínuo, somente o quadro recente.
  nenhuma  : sem câmera.
  simulada : linha sintética que serpenteia, para testar visão/controle sem câmera.
"""
import threading
import time

import cv2
import numpy as np

from motor import protocolo as P


class FonteSimulada:
    def __init__(self, fps: float = 10.0):
        self._periodo = 1.0 / fps
        self._id = 0
        self._t0 = time.monotonic()
        self._ultimo = 0.0
        self._lock = threading.Lock()

    def id_atual(self) -> int:
        return self._id

    def _gerar(self) -> np.ndarray:
        t = time.monotonic() - self._t0
        img = np.full((P.IMG_ALTURA, P.IMG_LARGURA), 220, np.uint8)
        for y in range(P.IMG_ALTURA):
            x = int(P.IMG_LARGURA / 2 + 40 * np.sin(t * 0.8 + y / 25.0))
            cv2.line(img, (x, y), (x, y), 20, 9)
        img = (img // 17) * 17                        # simula os 4 bits da câmera
        return (img + np.random.randint(-8, 9, img.shape)).clip(0, 255).astype(np.uint8)

    def proximo_quadro(self, apos_id: int, timeout: float = 1.0):
        falta = self._ultimo + self._periodo - time.monotonic()
        if falta > 0:
            time.sleep(min(falta, timeout))
        with self._lock:
            self._id += 1
            self._ultimo = time.monotonic()
            return self._id, self._gerar()


class FonteNenhuma:
    """Sem câmera: nunca entrega quadro. A visão fica avisando 'sem quadros' e o robô não segue linha
    (comandos de voz de manobra e testes de motor continuam funcionando)."""

    def id_atual(self) -> int:
        return 0

    def proximo_quadro(self, apos_id: int, timeout: float = 1.0):
        time.sleep(timeout)
        return None


def criar_fonte(nome: str, motor=None):
    if nome == "arduino":
        if motor is None or not hasattr(motor, "proximo_quadro"):
            raise ValueError("FONTE_IMAGEM='arduino' precisa do ArduinoSerial (sem --sem-arduino)")
        return motor
    if nome == "esp32":
        import config as cfg
        from visao.esp32_cam import CameraESP32
        return CameraESP32(cfg.ESP32_URL, cfg.ESP32_TIMEOUT_S,
                           cfg.ESP32_IDADE_MAX_S, cfg.ESP32_RECONEXAO_S)
    if nome == "csi":
        from visao.camera_csi import CameraCSI
        return CameraCSI()
    if nome == "nenhuma":
        return FonteNenhuma()
    if nome == "simulada":
        return FonteSimulada()
    raise ValueError(f"FONTE_IMAGEM inválida: {nome!r} (use 'arduino', 'csi', 'nenhuma', 'simulada' ou 'esp32')")
```

</details>

<details>
<summary>config.py — conteúdo atual</summary>

```python
"""Configurações centrais do robô. Ajuste os valores aqui, não no meio do código."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# ------------------------------------------------- Serial (Pi <-> Arduino: imagem da OV7670 + comandos dos motores)
# Caminho legado: OV7670 ligada ao Arduino, com imagem pela serial no modo com câmera.
# O Uno está no modo sem câmera. ESP32 é fonte HTTP opcional, selecionável na main;
# contrato da CNN para ESP32 ainda pendente: docs/13_contexto_e_plano_cnn.md.
SERIAL_PORTA = "/dev/ttyACM0"      # Arduino UNO via USB costuma ser ttyACM0 (clones: ttyUSB0)
FIRMWARE_COM_CAMERA = False       # True = firmware com USAR_CAMERA 1 (OV7670, 1 Mbaud, sem ultrassom/encoders);
                                   # False = USAR_CAMERA 0 (sem câmera: 115200 baud, COM ultrassom e encoders). Igual ao que foi gravado!
SERIAL_BAUD = 115200    # igual ao firmware gravado (UART_U2X_UBRR em config.h)
SERIAL_TIMEOUT_S = 0.1
FW_LINHA_INICIAL = 0               # primeira linha da imagem enviada: igual a LINHA_INICIAL em config.h do firmware
SERIAL_BOOT_DELAY_S = 2.5          # o UNO reinicia ao abrir a porta serial

# ---------------------------------------------------------------- Motores
VEL_BASE = 140                     # PWM 0-255 em linha reta
VEL_MAX = 255
VEL_GIRO = 150                     # PWM do giro forçado (voz)
VEL_RE = 130                       # PWM do "voltar"
KP = 90.0                          # ganho proporcional (erro normalizado -1..1 -> PWM)
KD = 25.0                          # ganho derivativo
KD_FILTRO = 1.0                    # filtro da derivada (0..1; 1 = sem filtro). A OV7670 dá ~2,5 quadros/s: sem filtro.
                                   # (Se um dia a câmera for rápida, ~30 quadros/s, use ~0.3 para o ruído não virar tremor.)
TEMPO_GIRO_S = 0.6                 # duração do giro forçado por "esquerda"/"direita"
TEMPO_RE_S = 1.0                   # duração da ré por "voltar"
PERDA_LINHA_TIMEOUT_S = 0.6        # sem ver a linha por este tempo -> para
LEITURA_VALIDADE_S = 0.3           # leitura de visão mais velha que isto é descartada
FREQ_CONTROLE_HZ = 20

# Ultrassom HC-SR04 (Arduino): os limites espelham OBSTACULO_* em firmware/config.h.
OBSTACULO_ATIVO = True
# Primeira etapa: inspecao parada somente em SEGUINDO; nunca desvia sozinho.
INSPECAO_OBSTACULO_ATIVA = True
INSPECAO_REPOUSO_S = 0.4          # espera inicial; validar inercia real
INSPECAO_TIMEOUT_S = 8.0         # aborta e permanece PARADO se faltar resposta
OBSTACULO_DIST_CM = 25             # distância de parada
OBSTACULO_LIBERACAO_CM = 30       # precisa afastar até aqui para liberar (igual ao firmware)
OBSTACULO_LEITURAS = 2             # leituras consecutivas para confirmar bloqueio/liberação
SENSOR_TIMEOUT_S = 0.25            # sem pacote recente, diagnóstico remoto considera segurança indisponível
# Modo 4 manual: varredura continua e obstaculo frontal no Uno (SONAR_MOV_CONTINUO=1).
# Integracao exclusiva do controle MANUAL/Bluetooth; CNN/seguidor sao etapas futuras.
SONAR_MOVIMENTO_ATIVO = True  # ativado pelo usuario; perfil experimental, sem validacao no piso
RECUO_MANUAL_ATIVO = True  # somente Bluetooth com sonar 4; nao ha sensor traseiro
RECUO_MANUAL_DIST_CM = 10
RECUO_MANUAL_REPOUSO_S = 0.15
RECUO_MANUAL_TEMPO_S = 0.35
RECUO_MANUAL_PPS = 4
RECUO_MANUAL_MAX_PULSOS = 2  # por roda; limites iniciais, nao distancia validada

# ------------------------------------------------------- Controle remoto pelo celular (Bluetooth, Android)
# O celular conecta no Bluetooth da Pi como "porta serial" (SPP/RFCOMM). Veja docs/07_controle_bluetooth.md.
REMOTO_BT_ATIVO = True             # False = não sobe o servidor Bluetooth
REMOTO_ADAPTADOR = "hci0"          # adaptador Bluetooth da Pi (o servidor tenta ligá-lo ao subir)
REMOTO_NOME = "Robo Carrinho"      # nome do serviço serial (aparece em alguns apps)
REMOTO_MACS_PERMITIDOS: list[str] = []   # ex.: ["AA:BB:CC:DD:EE:FF"]; vazio = qualquer celular JÁ PAREADO
REMOTO_TIMEOUT_S = 1.5             # sem novo comando de movimento por este tempo -> o carrinho PARA (anti-fuga).
REMOTO_BOTOES_ATE_SOLTAR = True    # app envia F/B/L/R ao apertar e S ao soltar; mantem enquanto conectado
                                   # Apps que repetem o comando enquanto o botão está apertado mantêm o movimento.
                                   # Apps que mandam uma vez só: ande no máximo isto por toque (ou aumente com cuidado).
REMOTO_BLUEDOT_TIMEOUT_S = 2.0     # app Blue Dot (analógico): sem NENHUMA mensagem por este tempo com o dedo na tela -> PARA
                                   # (o app só avisa quando o dedo se mexe ou solta; isto cobre a conexão que cai com o dedo apertado)
REMOTO_BLUEDOT_ZONA_MORTA = 0.15   # raio no centro do analógico (0..1) em que o carrinho fica parado
REMOTO_ELETROGATE_TIMEOUT_S = 0.4  # app Robô Eletrogate envia atualizações contínuas; silêncio do joystick para rapidamente
# Preencher APOS observar Bluetooth RX ao apertar/soltar a buzina.
# Por enquanto nenhum caractere avulso e presumido. Aceitos: W w U u V v X x.
REMOTO_BUZINA_LIGAR = ""
REMOTO_BUZINA_DESLIGAR = ""
REMOTO_BUZINA_PULSO = "Y"          # byte observado no app; toque limitado pelo firmware a 1,5 s
REMOTO_LOG_BYTES = True           # True registra cada bloco Bluetooth em hexadecimal e texto legível (diagnóstico)
REMOTO_DIAGNOSTICO_MOVIMENTO = True  # estado do pedido, guarda e PWM/F8 na main, no maximo 1/s salvo transicoes
REMOTO_VEL_INICIAL = 6             # nível 0..10 ao conectar (10 = REMOTO_VEL_MAX)
REMOTO_VEL_MAX = 200               # PWM no nível 10 e no analógico todo para o lado (limite de segurança do remoto; máx. 255)
REMOTO_CURVA_FATOR = 0.4           # curvas (G/I/H/J): a roda de dentro anda esta fração da de fora

# ----------------------------------------------------------------- Visão
# Câmera: OV7670 no Arduino (QQVGA 160x120, 4 bits de cinza, ~2,5 quadros/s). O robô trabalha com quadros cinza
# 120x160 (uint8). Veja docs/01_ligacao_camera.md e docs/02_bringup_camera.md.
FONTE_IMAGEM = "arduino"           # "arduino" (OV7670, pela serial), "simulada" (linha falsa), "nenhuma", "esp32" (opcional) ou "csi" (NÃO usada)
# --- só para FONTE_IMAGEM = "csi" (Pi Camera Rev 1.3 no conector CSI; código mantido, mas a câmera não é a do projeto) ---
CAMERA_FPS = 30                    # quadros por segundo pedidos ao sensor
CAMERA_PRINCIPAL = (640, 480)      # stream principal (não usado, mas o picamera2 exige); modo nativo do OV5647
CAMERA_LORES = (320, 240)          # stream de onde sai o cinza (largura múltipla de 32); depois reduz p/ 160x120
CAMERA_EXPOSICAO_US = None         # None = exposição automática; ou um valor fixo em microssegundos (ex.: 8000)
CAMERA_GANHO = None                # ganho analógico fixo (só vale junto com CAMERA_EXPOSICAO_US)
# --- vale para as duas câmeras ---
IMAGEM_ESPELHAR_H = False          # True se a imagem sair espelhada na horizontal (câmera de cabeça p/ baixo etc.)
IMAGEM_ESPELHAR_V = False          # True se estiver de cabeça para baixo
ROI_INICIO = 0.50                  # a análise usa só a parte de baixo do frame (fração da altura)
BLUR_KERNEL = 3                    # ímpar; imagem pequena e ruidosa, mas 3 basta
LINHA_ESCURA = True                # True: linha preta em piso claro; False: linha clara em piso escuro
USAR_OTSU = True                   # limiar automático; False usa LIMIAR_FIXO
LIMIAR_FIXO = 100
CONTRASTE_MIN = 40                 # (máx-mín) da ROI abaixo disto = sem linha (Otsu em piso liso inventa linha)
AREA_MIN = 40                      # contornos menores que isto (em pixels de 160x120) são ruído
MOSTRAR_DEBUG = False              # True abre janela do OpenCV (precisa de monitor/VNC)

# Tracejado: usado na visão quando a fonte oferece metadados (ESP32).
TRACEJADO_MAX_SEGMENTOS = 24       # excesso de candidatos provoca abstenção
TRACEJADO_MEMORIA_S = 0.3          # associação visual; nunca autoriza avanço sem observação
TRACEJADO_AMBIGUIDADE = 0.85       # alternativa com nota próxima provoca abstenção
TRACEJADO_CONFIANCA_MIN = 0.25     # qualidade heurística inicial, não calibrada no piso

# ------------------------------------------------------ Aprendizado online (pasta aprendizado/)
# Veja docs/04_aprendizado_online.md. Desligado por padrão: precisa da câmera e da pista.
APRENDIZADO_ATIVO = False
APR_DIR = BASE_DIR / "dados_aprendizado"   # episódios gravados, versões do modelo, estado do ciclo

APR_ROI_LINHA_INICIO = 40          # linhas do topo do quadro 120x160 descartadas antes da CNN
APR_GANHO_PROF = 1.2               # direção do professor (OpenCV) = clip(ganho * erro, -1, 1)
APR_GANHO_DIRECAO = 90.0           # direção [-1,1] -> diferença de PWM entre as rodas
APR_VEL = 110                      # PWM base durante o aprendizado (comece devagar)
APR_PERIODO_MIN_S = 0.4            # o aprendizado usa no máximo 1 quadro a cada tanto tempo (0,4 s = 2,5 passos/s, o ritmo
                                   # em que tudo foi dimensionado e testado no simulador). Só reduza depois de medir na pista.
APR_MAX_BURACO = 4                 # passos seguidos sem linha (vão do pontilhado) reparados por interpolação
APR_JANELA_FALHA = 8               # quadros antes de uma falha que ganham mais peso no treino
APR_BUFFER_MAX = 15000             # máximo de quadros mantidos em memória para treinar

# Níveis de autonomia: fração dos quadros em que a CNN pode conduzir, e o quanto ela pode divergir do
# professor (portão de segurança). Nível 0 = só o professor dirige (coleta de dados).
APR_NIVEIS = [0.0, 0.25, 0.5, 0.75, 1.0]
APR_PORTAO = [0.0, 0.25, 0.30, 0.40, 9.0]   # último nível: sem portão (a CNN dirige sozinha; o professor só vigia)
APR_NIVEL_SUBIR_TENT = 3           # tentativas do campeão no nível atual antes de poder subir
APR_NIVEL_SUBIR_FALHAS = 0.2       # ... com no máximo esta fração de falhas
APR_NIVEL_DESCER_FALHAS = 2        # falhas seguidas causadas pela CNN que fazem voltar um nível

# Segurança: uma tentativa é interrompida quando...
APR_MAX_QUADROS_SEM_LINHA = 4      # ...a linha some por tantos quadros seguidos (além do vão normal)
APR_ERRO_DIVERGENCIA = 0.85        # ...|erro| fica acima disto...
APR_QUADROS_DIVERGENCIA = 3        # ...por tantos quadros seguidos
APR_OSC_JANELA = 6                 # ...a direção troca de sinal (com amplitude) APR_OSC_TROCAS vezes na janela
APR_OSC_TROCAS = 4
APR_IDADE_MAX_QUADRO_S = 1.5       # ...ou ficam sem quadro novo por este tempo
APR_PARADO_PASSOS = 3              # ...ou os encoders não mexem apesar de comandar movimento
APR_TEMPO_MAX_S = 120              # ...ou passa deste tempo (tentativa "concluída", não falha)

# Treino
APR_MIN_QUADROS_PRIMEIRO = 600     # quadros (com rótulo) antes de treinar a primeira CNN
APR_NOVOS_PARA_TREINAR = 300       # quadros novos para treinar um candidato
APR_PASSOS_TREINO = 400
APR_LOTE = 32
APR_LR = 1e-3
APR_AVALIAR_A_CADA_PASSOS = 50
APR_MIN_PASSOS_TREINO = 100
APR_PACIENCIA_TREINO = 4
APR_TOL_OFFLINE = 0.10             # candidato pode ter erro de validação até 10% maior que o campeão
# Comparação A/B entre campeão e candidato (tentativas alternadas, mesmo nível de autonomia)
APR_AB_MIN = 3
APR_AB_MAX = 8
APR_AB_PROB = 0.80                 # confiança (bootstrap) para promover ou descartar
APR_ACAO_VALIDADE_S = 1.5             # ação do aprendizado mais velha que isso = o controle para os motores
APR_NAO_INFERIOR_MARGEM = 0.05      # pontuação: pior que isso no IC95 = não é "não-inferior"
APR_GANHO_OFFLINE_MIN = 0.15         # redução relativa do erro na validação offline p/ promover sem diferença no A/B
APR_MANTER_VERSOES = 8

# ------------------------------------------------------------------- Voz
COMANDOS = ["siga", "esquerda", "direita", "pare", "voltar"]

MODELO_TIPO = "mistura"            # "mistura" (LSTM + SVM, média das probabilidades) ou "mlp"
MODELO_MISTURA = BASE_DIR / "voz" / "modelo" / "modelo_mistura.pkl"   # 6_lstm_classification.py
MODELO_MLP = BASE_DIR / "voz" / "modelo" / "modelo.pkl"               # 4_classification.py

# Microfone = headset Bluetooth pareado na Pi (veja docs/03_bluetooth_headset.md).
MIC_DEVICE = None                  # None = padrão do sistema; ou parte do NOME (ex.: "JBL") ou o índice
MIC_SR = 16000                     # taxa que o MODELO espera (a do treino). Não mude.
MIC_SR_TENTATIVAS = [16000, 48000, 44100, 32000, 8000]   # taxas tentadas no headset, nessa ordem;
                                   # o sinal é reamostrado para MIC_SR antes das features
PARAR_SE_SEM_MICROFONE = True      # headset caiu -> robô para (sem voz não há como mandar "pare")
MIC_REABRIR_S = 3.0                # espera entre tentativas se o headset desconectar

# VAD (detector de fala): quantos blocos de ~64 ms de silêncio fecham a palavra.
# Menor = "pare" reage mais rápido, mas pode cortar palavras com pausa no meio.
VAD_BLOCOS_FIM = 8

# Confiança mínima (0..1). O projeto original usava 50%. "pare" é mais permissivo de propósito:
# um "pare" falso só para o robô, um "pare" perdido deixa ele andando.
LIMIAR_PADRAO = 0.50
LIMIAR_CONFIANCA = {"pare": 0.40}


# Habilitar apos conferir pulsos e ajustar PI com rodas suspensas.
# Mantem a interface do controle: escala -255..255 para -referencia..+referencia.
CONTROLE_VELOCIDADE_ATIVO = True  # teste do PI com encoders e rodas suspensas
VELOCIDADE_REFERENCIA_PPS = 60

# ESP32 opcional: --fonte-imagem esp32 seleciona captura/visão/PD, sem alterar o padrão.
# Sem resize: receptor confirma JPEG 320x240; hardware ainda deve ser conferido.
ESP32_URL = "http://192.168.4.1/capture"
ESP32_TIMEOUT_S = 1.0
ESP32_IDADE_MAX_S = 0.3
ESP32_RECONEXAO_S = 0.5

# Antecipação geométrica em fração da altura da ROI, não velocidade física.
TRACEJADO_ANTECIPACAO = 0.25
TRACEJADO_VAO_FATOR = 0.5          # reduz saída nos vãos; prazo continua PERDA_LINHA_TIMEOUT_S
```

</details>

<details>
<summary>tools/testar_esp32_cam.py — conteúdo atual</summary>

```python
"""Recepcao de bancada independente do controle do robo. q ou Ctrl+C sai."""
import argparse
import csv
import time
from urllib.request import build_opener, ProxyHandler

import cv2
import numpy as np

# Compatibilidade: coletor e testes continuam importando estas funções daqui.
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from visao.esp32_cam import (MAX_JPEG, URL_PADRAO, ERROS_RECEPCAO,
                             QuadroESP32, receber_quadro, receber)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=URL_PADRAO)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--intervalo", type=float, default=0.05)
    parser.add_argument("--csv", default="esp32_cam_bancada.csv")
    parser.add_argument("--tracejado", action="store_true",
                        help="mostra segmentos OpenCV e trajetória, sem comandos de motor")
    args = parser.parse_args()
    detector = None
    if args.tracejado:
        from visao.detector import DetectorLinha, desenhar_debug
        detector = DetectorLinha(tracejado=True)
    if args.timeout <= 0 or args.intervalo < 0:
        parser.error("timeout deve ser positivo e intervalo nao negativo")
    opener = build_opener(ProxyHandler({})) # Rede local, sem proxy do ambiente.
    janela = "Carrinho-CAM - q sai"
    cv2.namedWindow(janela)
    inicio = time.monotonic()
    janela_inicio = inicio
    total = falhas = quadros = 0
    try:
        with open(args.csv, "w", newline="", buffering=1) as arquivo:
            log = csv.writer(arquivo)
            log.writerow(["tempo_s", "status", "http_ms", "idade_envio_ms",
                          "idade_recepcao_limite_ms", "fps", "erro"])
            while True:
                tentativa = time.monotonic()
                try:
                    imagem, http, idade, limite = receber(opener, args.url, args.timeout)
                except ERROS_RECEPCAO as erro:
                    falhas += 1
                    if detector is not None:
                        detector.limpar_historico()
                    decorrido = (time.monotonic() - tentativa) * 1000
                    print(f"FALHA ({decorrido:.1f} ms): {erro}; tentando novamente", flush=True)
                    log.writerow([time.monotonic()-inicio, "falha", f"{decorrido:.2f}", "", "", "", str(erro)])
                    cv2.imshow(janela, np.zeros((240, 320, 3), dtype=np.uint8))
                    espera = 1.0
                else:
                    total += 1
                    quadros += 1
                    agora = time.monotonic()
                    fps = quadros / max(agora - janela_inicio, 1e-9)
                    print(f"quadro={total} HTTP={http:.1f} ms idade_envio={idade:.1f} ms "
                          f"idade_recepcao<={limite:.1f} ms FPS={fps:.2f} falhas={falhas}", flush=True)
                    log.writerow([agora-inicio, "ok", f"{http:.2f}", f"{idade:.2f}", f"{limite:.2f}", f"{fps:.2f}", ""])
                    if detector is not None:
                        processamento_inicio = time.monotonic()
                        resultado = detector.processar(imagem)
                        processamento_ms = (time.monotonic() - processamento_inicio) * 1000
                        imagem = desenhar_debug(imagem, resultado)
                        cv2.putText(imagem, f"HTTP OK FPS={fps:.1f} visao={processamento_ms:.1f}ms",
                                    (5, 33), cv2.FONT_HERSHEY_SIMPLEX, .4, (0, 0, 255), 1)
                        print(f"visao={processamento_ms:.2f} ms segmentos={len(resultado.segmentos)} "
                              f"erro={resultado.erro:+.3f} direcao={resultado.direcao:+.3f} "
                              f"confianca={resultado.confianca:.2f} motivo={resultado.motivo}", flush=True)
                    cv2.imshow(janela, imagem)
                    if agora - janela_inicio >= 5:
                        janela_inicio, quadros = agora, 0
                    espera = args.intervalo
                # Mantem a janela responsiva durante o intervalo e as retentativas.
                fim = time.monotonic() + espera
                while True:
                    if cv2.waitKey(10) & 0xFF == ord("q") or cv2.getWindowProperty(janela, cv2.WND_PROP_VISIBLE) < 1:
                        return
                    if time.monotonic() >= fim:
                        break
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
        print(f"Fim: {total} quadros validos, {falhas} falhas; CSV: {args.csv}")


if __name__ == "__main__":
    main()
```

</details>

## Anexo D — registros acrescentados à documentação

Somente as seções desta integração, sem reproduzir o histórico anterior inteiro
do projeto. Atualizações de estado dentro desses registros refletem a evolução
entre etapas e não devem ser interpretadas como validação física.

<details>
<summary>docs/12_esp32_cam_bancada.md — registros das etapas 1 a 4</summary>

````markdown
## Fonte integrada opcional — Etapa 1

`visao.fontes.criar_fonte("esp32")` agora cria uma fonte compatível com
`id_atual()` e `proximo_quadro()`. `iniciar()` captura em segundo plano e
`parar()` encerra. Apenas o último quadro é mantido. `metadados(id)` retorna
recepção monotônica, tempo HTTP e limite estimado de idade, ou None se o
quadro venceu/foi substituído. `estatisticas` informa resolução, FPS desde
início (inclui falhas), erros e rejeições por idade. Prazos e URL ficam em
`ESP32_*` no config.py. Não houve ativação padrão nem mudança no controlador.

Teste de software sem serial ou motores:

```bash
PYTHONDONTWRITEBYTECODE=1 venv/bin/python tests/test_esp32_fonte.py
```

O teste visual de captura existente continua disponível, usando o mesmo receptor:

```bash
/usr/bin/python3 tools/testar_esp32_cam.py --url http://192.168.4.1/capture --csv esp32_etapa1.csv
```

A janela acima testa recepção, não decisões de movimento. A ferramenta requer
OpenCV com GUI, conforme as instruções anteriores. Não executar main.py para
validar autonomia nesta etapa: a distinção entre falha da câmera e vão visual
no controle pertence à Etapa 3. Hardware não respondeu no ambiente de análise;
320x240 ainda precisa ser confirmado na câmera física, sem resize automático.

## Etapa 2 — detector tracejado opt-in

`DetectorLinha(tracejado=True)` reutiliza a ROI, a conversão cinza, o limiar
Otsu/fixo, a polaridade e a abertura 3x3 existentes. O agrupador geométrico de
`visao/sugestao.py` é compartilhado: apenas seus limites são parametrizados,
preservando os valores padrão da revisão offline. Não se executam CLAHE,
normalização com kernel 51x51 ou busca de vários limiares no modo contínuo.
Não há resize; testa-se a resolução recebida. `BLUR_KERNEL=1` permite dispensar
suavização. Os valores atuais de ROI, área, contraste, polaridade e blur foram
mantidos. A ROI real ainda precisa ser calibrada com a câmera montada.

O resultado acrescenta segmentos aceitos e pontos de trajetória no frame,
direção geométrica `dx/dy` para o alto da imagem (positivo: direita) e uma
qualidade heurística, não uma probabilidade calibrada. `cx/cy` usa o meio da
ROI limitado à extensão sustentada por segmentos; o erro horizontal mantém
a convenção -1..+1. Não há extrapolação ilimitada para fora da extensão.

A qualidade combina contraste, extensão vertical e suporte de pixels. O limite
inicial é 0,25; trajetória concorrente com nota >=85% e separação horizontal
relevante causa abstenção. Excesso de candidatos (>24 após filtros básicos)
também causa abstenção antes da PCA/associação; não se tenta seguir um candidato
arbitrário. Os parâmetros `TRACEJADO_*` são iniciais, sem calibração na pista.
Sombras/rejuntes ainda podem parecer fita; testes sintéticos não provam identidade.

O histórico guarda somente dois pontos e um horário da última observação
válida por até 0,3 s. Ajuda a associar candidatos presentes. Ausência não
renova essa memória e sempre retorna `achou=False`, sem fabricar posição
observada. Mudança de formato, relógio regressivo e `limpar_historico()`
invalidam a referência. Esse histórico não autoriza motores nos vãos; a
continuidade de movimento e a validação de câmera pertencem à Etapa 3.

A thread de visão continua criando `DetectorLinha()` no modo legado. Não
houve ativação do tracejado no controle nem alteração de estado, PD ou CNN.

Teste sintético, sem câmera ou motores:

```bash
cd /home/carrasco/Downloads/robo_seguidor
PYTHONDONTWRITEBYTECODE=1 venv/bin/python tests/test_detector_tracejado.py
```

Prévia de segmentos, ROI, trajetória, centro, erro, qualidade, direção e métricas:

```bash
/usr/bin/python3 tools/testar_esp32_cam.py --tracejado \
  --url http://192.168.4.1/capture --csv esp32_etapa2.csv
```

Requer GUI conforme as instruções anteriores. O CSV mantém seu formato de
captura; o tempo da visão e o resultado são mostrados na tela/terminal. A
prévia usa o receptor de bancada e não publica medições no controle. Não
simula nem autoriza movimento; a decisão simulada e os bloqueios integrados
serão tratados nas etapas seguintes. `q` ou Ctrl+C encerra. O modo original,
sem `--tracejado`, permanece disponível. Falha HTTP limpa a memória visual.

### Medições locais da Etapa 2

Na Raspberry Pi 5 Model B Rev 1.1, Python 3.13.5, OpenCV 5.0.0 (4 threads),
processados 900 frames BGR sintéticos de 320x240 após 50 de aquecimento.
Nove cenas: cinco posições, ausência, duas trajetórias e duas inclinações.
Resultados de uma execução, sem HTTP/JPEG/exibição/controle:

| Modo | Média | Mediana | P95 | Vazão de processamento |
|---|---|---|---|---|
| Legado | 0,293 ms | 0,314 ms | 0,353 ms | 3406,2 quadros/s |
| Tracejado | 1,161 ms | 1,179 ms | 1,878 ms | 860,5 quadros/s |

A vazão acima não é FPS da câmera ou do robô integrado; a detecção de vários
segmentos custa mais que a de um contorno. Não comprova acurácia nem autonomia.
A tentativa HTTP real retornou código 000 por timeout de conexão em 2,002 s;
resolução, FPS e latência físicos da câmera continuam sem confirmação.

Reprodução da medição (não abre serial, câmera ou GUI):

```bash
PYTHONDONTWRITEBYTECODE=1 venv/bin/python - <<'PY'
import sys, time
import cv2, numpy as np
sys.path.insert(0, 'tests')
from test_detector_tracejado import imagem
from visao.detector import DetectorLinha
casos = [imagem((x,)) for x in (40, 90, 160, 230, 280)]
casos += [imagem(()), imagem((80, 240)), imagem(direcao=.3), imagem(direcao=-.3)]
casos = [cv2.cvtColor(a, cv2.COLOR_GRAY2BGR) for a in casos]
for tracejado in (False, True):
    d = DetectorLinha(tracejado)
    for i in range(50):
        d.processar(casos[i % 9])
    tempos = []
    inicio = time.perf_counter()
    for i in range(900):
        t = time.perf_counter()
        d.processar(casos[i % 9])
        tempos.append((time.perf_counter() - t) * 1000)
    total = time.perf_counter() - inicio
    print('tracejado=', tracejado, 'media/mediana/p95 ms=',
          np.mean(tempos), np.median(tempos), np.percentile(tempos, 95),
          'quadros/s de processamento=', 900 / total)
PY
```

## Etapa 3 — visão ligada à decisão, sem validação física

A seleção de fonte é opcional: `main.py --fonte-imagem esp32` conecta a
captura HTTP ao detector tracejado e ao controlador existente. O padrão de
`FONTE_IMAGEM` não foi trocado. Nenhuma execução com motores reais foi feita.
Para manter a serial física fechada numa execução da aplicação, acrescente
`--sem-arduino`. Nesse modo o ArduinoNulo não oferece ultrassom: a guarda
bloqueia o seguimento, mesmo que a câmera detecte linha. Os testes abaixo
injetam sensores falsos explicitamente, sem alterar guardas de produção.

O snapshot `(id, imagem, metadados)` é obtido atomicamente, sem copiar a imagem.
A recepção monotônica e a idade estimada na recepção acompanham a observação
até o controle. O processamento não torna recente uma imagem velha. Valida-se
idade antes/depois da visão e em cada decisão; usam-se os mesmos limites de
0,3 s existentes (ou um limite menor da fonte). Desconexão não precisa esperar
a thread visual publicar: o controle consulta saúde a cada ciclo de20 Hz.
Detecção de falha/idade depende de timeout e escalonamento; não é tempo real rígido.

Falha, expiração ou recuperação alteram a geração da câmera. Assim, uma falha
seguida de reconexão entre dois ciclos não permite usar a trajetória anterior.
Mudanças de modo também alteram a sessão visual; resultados processados antes
de pare/manual/giro e publicados depois são recusados. A visão limpa sua
referência de associação na mudança de sessão/geração. Espelhamentos existentes
são aplicados somente quando configurados, com a mesma orientação na depuração.

### Regras do seguimento

- Sem observação inicial válida: saída zero, inclusive dentro da antiga tolerância.
- Linha observada: confiança mínima da Etapa2, erro/direção finitos e frame recente.
- A direção entra como antecipação de0,25 da altura da ROI, normalizada pela
  meia largura do frame; o erro resultante é limitado a[-1,1]. É geometria de
  imagem, não estimativa de deslocamento físico. Parâmetro inicial para calibrar.
- PD preservado: KP90, KD25 e filtro1. As funções de cálculo/filtro não mudaram.
- Ausência com câmera saudável e frames recentes: mantém por no máximo0,6 s a
  última geometria confiável, desde o instante conservador da observação real.
  A saída é multiplicada por0,5, pela qualidade anterior e pela fração restante
  do prazo. Isso reduz o pedido às rodas; não comprova uma velocidade física.
- Frame sem linha não renova o instante da última linha. Imagem vencida ou
  falha de câmera interrompe imediatamente na próxima decisão, sem tolerância
  de vão. Ambiguidade/baixa qualidade também limpa a estimativa.
- Ao reaparecer, usa a nova observação e zera o D após o vão, evitando um salto
  derivativo causado pela ausência. Obstáculo/falha exige nova observação depois
  da liberação; não há retorno usando memória antiga.
- Telemetria/ultrassom inválidos e modo manual V4 ainda ativo bloqueiam
  `SEGUINDO`. A exceção histórica de falta de eco no manual foi preservada.
- Voz/manual/parada mantêm prioridade. Encerramento/erro envia parada; o sistema
  recusa comandos tardios, para antes de aguardar threads e repete antes de fechar.

`ThreadControle.decidir_linha()` calcula `DecisaoLinha` (saídas, erro, motivo,
estimativa e idade), sem escrever nos motores. O loop continua sendo o ponto
que combina inspeção/ultrassom e envia o resultado sob o lock do estado.
Essa mesma função está disponível para a futura visualização simulada, evitando
um segundo algoritmo de decisão. Ainda não foi criada a interface da Etapa4.

A CNN própria e o aprendizado legado não foram modificados. Combinar ESP32 e
`APRENDIZADO_ATIVO=True` é recusado antes de abrir o Arduino, porque os contratos
de imagem/pesos/visibilidade atuais não são compatíveis. Isso não impede uma
integração futura com contrato explícito; não houve substituição de modelo.

### Validação sem hardware

```bash
cd /home/carrasco/Downloads/robo_seguidor
PYTHONDONTWRITEBYTECODE=1 venv/bin/python tests/test_decisao_visao.py
```

25 testes novos cobrem aquisição, idade total, partida, vãos/reaparecimento,
falha/recuperação, gerações/sessões, pare/manual, ultrassom, encerramento parcial
e recusa de CNN incompatível. Um teste executa as threads reais com GET/JPEG
injetados e motor/sensores falsos. A guarda da produção permanece ativa.
63 regressões selecionadas passaram (11 controle,5 fonte,15 detector,8 serial
virtual/imagem,14 sonar,7 diagnóstico,3 sinalização). Não é a suíte completa;
falhas antigas de CSI/recuo registradas antes não foram corrigidas nesta tarefa.
Comparação com baseline: antes havia pedido de avanço sem observação inicial;
agora todos os pedidos desse cenário são zero. Cálculo PD e filtro idênticos.
48 arquivos de aprendizado, firmware e motor conferidos por SHA256 intactos.

Medição local adicional:600 JPEGs sintéticos BGR320x240 após50 de aquecimento,
Pi5 Rev1.1/Python3.13.5/OpenCV5.0.0 com4 threads. Decodificação JPEG + visão +
publicação + decisão com ultrassom falso: média1,506 ms, mediana1,618 ms,
P95 2,156 ms;663,4 passos/s de CPU isolada. Nenhum comando de motor enviado.
Exclui rede/câmera/GUI/escalonamento entre threads; não é FPS integrado nem
latência de captura. Métricas físicas da ESP32 não foram medidas nesta etapa.
Os testes e a medição não comprovam seguimento ou frenagem no piso.

## Etapa 4 — prévia da decisão com motores nulos

Ferramenta: `tools/testar_decisao_esp32.py`. Reutiliza `CameraESP32`,
`ThreadVisao._processar_detalhado`, `DetectorLinha`, as guardas de ultrassom e
`ThreadControle.decidir_linha()`. Não cria outro controlador nem modifica a
operação do projeto. Não inicia threads de voz/Bluetooth e não importa ou
abre ArduinoSerial. O motor é obrigatoriamente ArduinoNulo; as saídas exibidas
são somente números calculados, sem envio de movimento, mesmo simulado.
O ultrassom é fictício e está identificado na tela, no terminal e no CSV.

Com a Raspberry já conectada à Carrinho-CAM e em desktop local/VNC:

```bash
cd /home/carrasco/Downloads/robo_seguidor
/usr/bin/python3 tools/testar_decisao_esp32.py --csv esp32_decisao_01.csv
```

O Python do sistema possui OpenCV 4.10.0 com Qt5 neste ambiente; o venv possui
OpenCV headless. Não é necessário instalar novas dependências para este teste.
SSH sem display deve usar `--sem-janela`. O teste inicia apenas o seguimento
SIMULADO e continua indefinidamente até q, fechar a janela ou Ctrl+C.

A janela mostra o frame em resolução nativa 320x240, a ROI, segmentos aceitos,
trajetória, centro, posição/erro, direção e qualidade. A decisão é classificada
pelas saídas do PD efetivamente calculadas: E>D direita, E<D esquerda, E=D reto;
duas saídas zero indicam parar. A estimativa durante o vão aparece em magenta
com a palavra ESTIMADA, separada da observação. Câmera inválida/vencida apaga o
frame anterior e mostra SEM FRAME ATUAL; não conserva imagem antiga como atual.

Teclas:

- `q`: encerrar.
- `p` ou espaço: pausar/retomar a simulação; exige novo frame na retomada.
- `1`: ultrassom SIMULADO livre (100 cm fictícios).
- `2`: obstáculo SIMULADO (0 cm fictícios).
- `3`: leitura SIMULADA inválida.

A mudança do ultrassom usa a guarda existente. Liberar o cenário após um
bloqueio não reaproveita a observação anterior. Sem imagem inicial válida,
a simulação permanece em PARAR. Pausa, falha e recuperação mantêm as regras
de sessão/geração da Etapa3. Nenhum desses cenários testa o sensor físico.
Não existe opção desta ferramenta para habilitar motores reais.

### Sem janela e cenários de segurança

```bash
/usr/bin/python3 tools/testar_decisao_esp32.py \
  --sem-janela --duracao 30 --csv esp32_decisao_sem_janela_01.csv
/usr/bin/python3 tools/testar_decisao_esp32.py \
  --sem-janela --duracao 10 --ultrassom obstaculo
/usr/bin/python3 tools/testar_decisao_esp32.py \
  --sem-janela --duracao 10 --ultrassom invalido
```

`--sem-janela` não desenha nem chama a GUI. Nenhuma configuração global é
alterada; a operação normal continua com `MOSTRAR_DEBUG=False`. `--url` e
`--timeout` permitem testar o mesmo receptor com parâmetros explícitos sem
alterar o Wi-Fi. `--duracao` limita o tempo ativo de medição; a limpeza pode
acrescentar o prazo limitado de encerramento da fonte. CSV é opcional, criado
exclusivamente e nunca sobrescrito: escolha outro nome para repetir ensaios.

CSV registra cada ciclo: id/novo frame, estado/geração da câmera, cenário
ultrassônico fictício, visibilidade, erro horizontal/controle, direção,
qualidade, estimativa, decisão/motivo, saídas simuladas, idades e tempos.
Frames intermediários são descartados pela fonte, não enfileirados. Repetir
um ciclo sem frame novo não incrementa FPS de visão nem renova a observação.
O teste guarda apenas a última imagem e estatísticas numéricas limitadas.

Métricas:

- FPS captura: frames aceitos pela fonte por tempo desde seu início; inclui
  pausas/falhas. Pode superar FPS visão, pois o consumidor só usa o mais recente.
- FPS visão: frames realmente processados por tempo ativo, incluindo pausas/falhas.
- HTTP: requisição até receber o JPEG, excluindo decodificação; medido pelo receptor.
- Visão: orientação, detecção, validação e publicação de um frame novo; exclui
  HTTP/decodificação no receptor e desenho da janela.
- Decisão: guardas fictícias e cálculo do controlador, sem envio às rodas.
- Idade do frame/observação: limite conservador que soma idade no envio,
  tempo HTTP e tempo local desde recepção. Não mede exposição ou monitor
  separadamente nem subtrai relógios não sincronizados.

Ao sair, o resumo JSON informa contagens, FPS, média e P95 das últimas até600
amostras. Médias usam todas as amostras válidas; o histórico numérico é limitado.
Valores sem amostras ficam nulos/--, nunca são inventados. Retorno0 significa
que houve frames processados;2 indica nenhum frame;1 erro de execução/arquivo/GUI.

### Verificação executada em 22/11/2026

```bash
PYTHONDONTWRITEBYTECODE=1 venv/bin/python tests/test_visual_decisao_esp32.py
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 tests/test_visual_decisao_esp32.py
```

15 testes novos passaram em ambos os intérpretes (OpenCV5.0.0 e4.10.0), com
HTTP/JPEG, GUI e sensores injetados. Cobrem decisões central/deslocadas,
ausência inicial, vãos/reaparecimento, idade, falha/reconexão, pausa, ultrassom,
CSV, contagem real de frames, limpeza e recusa de sobrescrita. O modo sem janela
é testado com desenho/GUI/serial proibidos. A prévia sintética foi inspecionada;
o teste de janela é simulado, não uma sessão real de Qt com a câmera.
88 regressões das etapas anteriores também passaram:103 testes selecionados
únicos. Não é declaração de aprovação da suíte completa; pendências anteriores
de CSI/recuo continuam registradas no documento de contexto.

Tentativa física apenas de captura, sem serial, fora do sandbox:

```bash
PYTHONDONTWRITEBYTECODE=1 venv/bin/python tools/testar_decisao_esp32.py \
  --sem-janela --duracao 5
```

Resultado medido:5,010 s ativos,0 frames recebidos/processados,3 falhas,
FPS captura/visão0 e retorno2. A decisão permaneceu PARAR. Resolução e HTTP/idade
ficaram nulos por ausência de imagens. Portanto não foi possível confirmar
resolução, FPS operacional ou latência física; repetir com a ESP32 acessível.
Não se usaram métricas de HTTP simulado como resultados da câmera real.
Nenhum motor, ultrassom, servo ou firmware físico foi acionado por estes testes.
Nenhuma rede ou serviço foi alterado. Todos os módulos de operação foram
preservados; somente ferramenta/testes/documentação foram acrescentados nesta etapa.

Confirmação adicional por GET direto, fora do sandbox: HTTP000 e timeout de
conexão em2,001 s. Nesta tentativa nem cabeçalhos HTTP foram recebidos; não foi
uma rejeição de resolução ou JPEG pelo detector. Não se alterou a rede para
contornar essa indisponibilidade.
````

</details>

<details>
<summary>docs/13_contexto_e_plano_cnn.md — registros das etapas 1 a 4</summary>

````markdown
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
````

</details>

## Anexo E — identificação das versões consultadas

SHA256 dos 16 arquivos de implementação/testes/documentação consolidados.
Esses hashes identificam os conteúdos copiados neste relatório, não substituem
histórico Git. O relatório não inclui seu próprio hash para evitar autorreferência.

| Arquivo | SHA256 |
|---|---|
| `visao/esp32_cam.py` | `eef4c66942634c5d884cf66feae336b704cc4b286e23d315e0c0c8ba581afe1a` |
| `tests/test_esp32_fonte.py` | `cc5e452aff771ba6ec17340a155f993fa282e4bc377ed7c1ce3d2d257edb1dfa` |
| `tests/test_detector_tracejado.py` | `754409839603125e11ff01c02309e1b11b1b858c7be83b28c88fe2ba8bfb1b71` |
| `tests/test_decisao_visao.py` | `bf58153f454bb66d0f73c262829b07a675b57c3cecdfce4bb3244b3e12226b28` |
| `tools/testar_decisao_esp32.py` | `64cc6d4035a0bd30208be85d1b204bfb4fbcf7b40b1a207b49ca2a5ee8405a9f` |
| `tests/test_visual_decisao_esp32.py` | `9f37b7cb17b1ae1838736867ac7a2f7862cddcc245644f5dc8512f3f49644d0b` |
| `visao/fontes.py` | `055e183f43e39c9badfc95812803662c4f68fb24c7ea39a6528bd555d89e293e` |
| `tools/testar_esp32_cam.py` | `20469fda1e62e2ac7e5fd995b098ff2b84ab31f21454b938cab97b98aa5f78c5` |
| `config.py` | `19d74666aef82b91af634b94b80d0b869a0eee6267736d512992cbd3283e7701` |
| `visao/detector.py` | `cc6d0b7d5cea685e7de1427308ac7972baf429b88d37212b713bc290e5cf8718` |
| `visao/sugestao.py` | `b4c42a0c75dee4f62affc82eac2a08160b5e575987bebd2fac3d657f5a262f8a` |
| `estado.py` | `4eda9cdaef378cbe9078341bb931463fda87235e22cc31c0cdba02b5616c3e63` |
| `controle.py` | `c259410327790a6d60077d109f3dea9d1d18160b0f8b1cfcb38ac35bb0d6a16c` |
| `main.py` | `ae31ffb04d0b825e6b6e8142652ad0b96d3614a1926088c9b73bb4f264a9bfaa` |
| `docs/12_esp32_cam_bancada.md` | `b46695cc3b027a5fe60b069bb8572a407f34579fb12ee2ba3dde6eeafdd79c14` |
| `docs/13_contexto_e_plano_cnn.md` | `8d4932005f8f1815db6d48370c499d738c4940309a4f078e376e178748305e1e` |
