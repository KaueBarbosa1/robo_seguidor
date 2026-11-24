# ESP32-CAM OV2640: teste de bancada

Esta etapa usa somente ESP32-CAM e um receptor separado. Não altera main.py,
robo.service, configuração da câmera existente, Uno ou CNN. Validação física pendente.

## Gravar na Raspberry Pi

1. Carrinho parado, alimentação dos motores desligada. Pare o serviço para impedir
   comandos ao Uno: `systemctl --user stop robo.service` (se instalado como serviço
   de sistema, use `sudo systemctl stop robo.service`). Não execute main.py.
2. Desconecte os jumpers de **5 V e GND dos bornes** da ESP32-CAM antes de ligar
   o micro-USB da base programadora. Nesta bancada, mantenha a câmera alimentada
   só pelo USB; não combine as duas fontes. O Uno pode continuar no seu USB.
3. Identifique a porta por comparação: execute `ls -l /dev/serial/by-id/` e
   `ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null`, retire **somente o USB da base da
   ESP32-CAM**, repita e reconecte. A porta que desaparece e reaparece é a base.
   Uno e base podem usar conversores semelhantes: não deduza pela numeração nem
   apenas pelo nome CH340/CP210x. A porta pode mudar ao reconectar.
4. Na Arduino IDE instale **esp32 by Espressif Systems** pelo Gerenciador de Placas
   (índice adicional, se necessário:
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`).
   Use core 3.x e abra `arduino/esp32_cam_bancada/esp32_cam_bancada.ino`.
   Selecione **AI Thinker ESP32-CAM** e a porta identificada em Ferramentas > Porta.
   Use PSRAM habilitada se houver essa opção. Altere `PASSWORD` (8–63 caracteres).
   A pinagem já está selecionada por `CAMERA_MODEL_AI_THINKER`.
5. Grave. Se a base não entrar automaticamente em gravação, mantenha IO0 em GND
   e pressione RESET antes da gravação; depois remova IO0–GND e pressione RESET
   para executar. Use os botões equivalentes da sua base, se disponíveis.
   Abra Monitor Serial em **115200 baud**; pressione RESET e confira a rede
   `Carrinho-CAM` e `http://192.168.4.1/capture`. Erros de PSRAM/câmera/Wi-Fi/HTTP
   aparecem no monitor. Falta de permissão na porta requer acesso ao grupo dialout
   e nova sessão de login. Feche outros monitores que estejam usando essa porta.

## Receber e exibir

Com internet ainda disponível, instale OpenCV **com interface gráfica** e NumPy:

```bash
sudo apt update
sudo apt install python3-opencv python3-numpy
```

O requirements.txt geral usa opencv-python-headless, que não abre janela. Para este
script use `/usr/bin/python3` com os pacotes apt acima, fora do venv existente.
Use desktop local ou VNC com sessão gráfica; SSH sem display não exibe a janela.

Na Pi, conecte pelo menu Wi-Fi à rede **Carrinho-CAM** com a senha do sketch.
Ou consulte `nmcli device status` e use (substitua wlan0 se necessário):

```bash
nmcli device wifi connect Carrinho-CAM password 'Carrinho123' ifname wlan0
ip -4 addr show wlan0
/usr/bin/python3 tools/testar_esp32_cam.py --csv esp32_cam_bancada.csv
```

Espere endereço 192.168.4.x/24 na Pi. A ESP é 192.168.4.1 e fornece DHCP;
nenhum roteador ou internet é necessário. Aceite permanecer na rede sem internet.
A troca de Wi-Fi pode derrubar SSH/VNC: prefira monitor local ou Ethernet para
acesso remoto. Use a senha alterada no comando. `q` ou Ctrl+C encerra o teste.

Cada quadro usa um GET /capture, sem requisições paralelas. Timeout padrão 3 s;
em falhas HTTP, desconexão ou JPEG inválido há registro e nova tentativa após 1 s.
A janela fica preta durante falhas para não apresentar uma imagem antiga como atual.
O CSV é sobrescrito ao iniciar: escolha outro nome para preservar ensaios.

## Coletar imagens com a câmera montada

Conecte a Pi à rede `Carrinho-CAM`. Com os motores desligados, ajuste
foco, inclinação e orientação da câmera olhando a prévia.

```bash
/usr/bin/python3 tools/coletar_esp32_cam.py --previa --roi 0 80 320 160
```

A janela mostra o quadro orientado com o retângulo da ROI e, ao lado, o
recorte em cinza reduzido a 80×40 e ampliado para inspeção. `--roi X Y L A`
usa pixels do quadro após a orientação, com origem no canto superior
esquerdo. O recorte deve caber no quadro e ter proporção 2:1. `0 80 320 160`
é um ponto de partida. Mude os valores até conseguir ver a fita perto e
longe na prévia. Use `--espelhar-h` para inverter esquerda e direita e
`--espelhar-v` para inverter cima e baixo. Repita as mesmas opções na coleta.

```bash
/usr/bin/python3 tools/coletar_esp32_cam.py \
  --saida coletas_esp32/curvas_luz_natural_01 --roi 0 80 320 160 \
  --duracao 30 --nota 'Câmera montada, luz natural, curvas e vãos'
```

Use uma pasta nova por sessão. `q`, fechar a janela ou `Ctrl+C` encerra a
captura. `--quadros N` limita a quantidade de JPEGs válidos e `--duracao S`
limita o tempo para iniciar novas capturas. Por SSH, acrescente
`--sem-janela`. A pausa padrão após um quadro válido é 0,2 s. Ajuste com
`--intervalo` para variar a frequência de amostragem. Falhas de rede ou de
JPEG são registradas e a captura é retomada quando a câmera responde.

- `quadros/` guarda os JPEGs originais de 320×240, byte a byte. Orientação e
  recorte aparecem na prévia e no manifesto.
- `capturas.csv` registra cada tentativa, com sequência, arquivo e horário
  UTC de recepção para os quadros válidos. Inclui tempos HTTP, duração
  monotônica desde o início e as estimativas de idade da bancada.
- `sessao.json` registra o identificador único da sessão, início e fim,
  nota da montagem, versão da prévia, ROI, orientação e contadores.

Guarde a pasta inteira. Separe sessões completas na avaliação. O formato
da coleta preserva a origem de cada JPEG para a futura rotulação. Os
experimentos anteriores continuam usando seus respectivos formatos de entrada.

## Métricas e aceitação

- `HTTP`: tempo monotônico desde antes do GET até terminar de receber o corpo;
  inclui ida, espera de captura e transferência, exclui decodificação/exibição.
  Em falhas, o tempo é até a exceção. O timeout limita operações de socket,
  não é um prazo absoluto para toda a transferência.
- `idade_envio`: diferença no relógio da ESP entre início da captura (timestamp
  do driver) e preparação da resposta. Dois buffers com CAMERA_GRAB_LATEST
  mantêm quadros recentes sem fila crescente; o buffer é sempre devolvido após envio.
- `idade_recepcao_limite`: idade_envio + HTTP. É um **limite superior estimado**
  da idade desde o início da captura até receber o JPEG na Pi, incluindo exposição,
  leitura e codificação. Não é latência exata: inclui também o trecho anterior ao
  instante em que a idade foi medida. Não subtraímos relógios de placas diferentes.
  Não inclui atraso do monitor; para latência visual completa, filme um cronômetro
  e sua imagem exibida na Pi juntos e compare os tempos visíveis.
- `FPS`: quadros válidos por tempo decorrido em janelas de cerca de 5 s, incluindo
  pausas e falhas; cada solicitação e sua idade ficam no CSV.

Com motores desligados, aponte a câmera para a pista e mova um objeto pelo campo:
confira 320×240, orientação, foco, luz, linha e área à frente do carrinho. A imagem
é mostrada sem recorte nem transformação para CNN.

Mantenha a recepção por pelo menos 5 minutos: procure ausência de congelamento,
JPEGs inválidos e reinicializações; FPS não deve colapsar e a idade não deve crescer
continuamente. Registre as faixas de FPS, HTTP e idade no CSV, pois dependem da luz,
alimentação e sinal. Aproxime Pi e câmera no primeiro teste.

Com o script aberto, retire o USB **da câmera** por 10 s e religue. Devem aparecer
falhas, a rede deve voltar e imagens novas devem reaparecer sem reiniciar o script.
Confira a reconexão automática do Wi-Fi da Pi; se o sistema escolher outra rede,
reconecte Carrinho-CAM pelo menu/nmcli. Repita três vezes e observe a recuperação.
Se houver resets espontâneos, confira cabo USB, alimentação e encaixe do flex com
energia desligada. Não desabilite o detector de brownout para esconder falhas.

Encerre esta etapa somente após receber e exibir imagens estáveis e validar essas
recuperações no hardware. Anote data, duração, métricas e resultado; não avance para
mudanças na CNN nesta etapa.

Referências oficiais: [pinagem AI Thinker](https://github.com/espressif/arduino-esp32/blob/master/libraries/ESP32/examples/Camera/CameraWebServer/camera_pins.h),
[driver e timestamps](https://github.com/espressif/esp32-camera/blob/master/driver/include/esp_camera.h).

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

## Painel local de gravacao — 24/11/2026

Na Pi, dentro do projeto e com acesso HTTP a ESP32:

```bash
python3 tools/painel_coleta.py --saida dados_pista/sessao_01 --duracao 180
```

No PC, abra `http://IP_DA_PI:8080`. Consulte `hostname -I` na Pi e use o
endereco acessivel ao PC, nao o IP da camera. Ambos precisam de conectividade
entre si; por exemplo, na mesma rede Carrinho-CAM, se ela permitir acesso
entre clientes. Nao requer VNC nem interface grafica na Pi. Use Python com
OpenCV e NumPy, como no coletor existente.

A coleta inicia no terminal; nao ha botoes de movimento, inicio ou parada no
navegador. Ctrl+C no terminal encerra a captura e o servidor. Ao terminar o
prazo, o painel permanece consultavel como COLETA ENCERRADA ate Ctrl+C.
Abrir/fechar abas nao inicia nem interrompe a coleta. O coletor consulta a
camera uma vez por captura; os navegadores recebem a ultima imagem em memoria,
sem abrir outras capturas na ESP32. JPEGs originais, CSV e manifesto ficam na
pasta nova escolhida. Nao produz MP4 nem rotulos de treino.

GRAVANDO significa que houve JPEG salvo ha menos de dois segundos e a ultima
tentativa nao falhou. A imagem apresentada e publicada somente depois da
escrita do JPEG e registro CSV; representa o ultimo quadro salvo, nao video
sem atraso. Falha HTTP, atraso, erro de disco ou perda da conexao do navegador
exibem aviso; previa antiga e ocultada. Escrita concluida nao e garantia de
persistencia contra queda de energia. Ultimo JPEG permanece em memoria;
nao se acumula fila de imagens.

Servidor HTTP sem autenticacao, destinado apenas a rede local confiavel;
nao encaminhe a porta para a internet. Padrao 0.0.0.0:8080; `--host 127.0.0.1`
restringe ao computador local. Nenhum acesso serial, alteracao de servico,
rede, firmware ou controle foi acrescentado. Para dirigir, use o controle
Bluetooth existente separadamente e acompanhe o carrinho diretamente: a
previa pode atrasar. Treinar somente com o carrinho parado.

Validacao simulada: quatro testes de gravacao antes da publicacao, falha e
recuperacao, parada solicitada, erro de disco e respostas HTTP sem cache.
Navegador, Wi-Fi, camera e percurso reais ainda pendentes.
