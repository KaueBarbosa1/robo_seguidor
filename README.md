# Robô seguidor de linha com comando de voz

Teste independente da ESP32-CAM OV2640: [guia de bancada](docs/12_esp32_cam_bancada.md).
Firmware e receptor separados; validação física e decisão sobre CNN ficam em etapas distintas.

## Arquitetura

```
  OV7670 (câmera) ──► Arduino UNO ◄──USB serial 1 Mbaud──► Raspberry Pi 5 (Debian 13.7)
  L298N + motores ◄──────┘                                   ├─ visão (OpenCV) / aprendizado (CNN)
                                                             ├─ controle (único escritor dos motores)
  Headset Bluetooth ───────────────────────────────────────► ├─ voz (sua IA treinada)
  Celular Android (Bluetooth serial) ──────────────────────► └─ controle remoto manual (docs/07)
```
O UNO **envia** a imagem da OV7670 (160x120, 16 tons, ~2,5 quadros/s) ou, no modo sem câmera, envia distância do HC-SR04 e
encoders; também **recebe** comandos de motor (pacotes de 5 bytes com checksum). A proteção ultrassônica no firmware só está
ativa em `USAR_CAMERA=0` (`FIRMWARE_COM_CAMERA = False`, 115200 baud); com a OV7670, ultrassom e encoders ficam desligados
por conflito de pinos. Protocolo em
`arduino/robo_firmware/protocolo.h` (espelho: `motor/protocolo.py`). A ligação Pi⇄Arduino (hoje USB) e a divisão final de
responsabilidades ainda serão definidas. A câmera CSI (Pi Camera Rev 1.3) chegou a ser adotada e foi abandonada; o código fica
como opção (`FONTE_IMAGEM = "csi"`), sem uso.

## Estrutura

```
robo_seguidor/
├── main.py                 # sobe as threads e supervisiona
├── config.py               # todos os parâmetros (porta, câmera, ganhos, limiares, modelo, microfone, aprendizado)
├── estado.py               # EstadoRobo: estado compartilhado protegido por RLock
├── controle.py             # decide e escreve nos motores (único escritor) + hierarquia de voz
├── motor/                  # protocolo.py (espelho do protocolo.h), serial_com.py (ArduinoSerial: imagem, motores, sensores), nulo.py
├── visao/
│   ├── camera_csi.py       # (opção NÃO usada) câmera CSI via picamera2 -> quadro cinza 120x160
│   ├── detector.py         # OpenCV: cinza, blur, threshold, contorno, momentos, erro; ThreadVisao
│   └── fontes.py           # fonte de imagem: "arduino" (OV7670, padrão), "simulada", "nenhuma" ou "csi"
├── remoto/                 # controle pelo celular (Bluetooth serial): comandos.py (interpretador), bluetooth_spp.py (servidor)
├── voz/                    # reconhecimento.py, features.py, vad.py, mistura.py, modelo/*.pkl
├── aprendizado/            # CNN do zero, ciclo de tentativas, supervisor, versões (docs/04); simulador SINTÉTICO
├── tools/                  # testar_motores, ler_sensores, ver_camera, testar_microfone, validar_mistura,
│                           # simulador_arduino, aprendizado_simulado, aprendizado_relatorio
├── tests/                  # test_aprendizado, test_controle, test_serial_imagem, test_remoto, test_integracao_robo, test_camera (CSI, opcional)
├── deploy/                 # serviço systemd de usuário: sobe o robô (voz + Bluetooth) quando a Pi liga
├── arduino/robo_firmware/  # firmware: OV7670 + motores (USAR_CAMERA 1) ou bancada com HC-SR04/encoders (0); teste_host/ (lógica no PC)
├── docs/                   # 00 motores e sensores, 01 ligação da câmera, 02 bring-up da câmera, 03 headset, 04 aprendizado,
│                           # 05 câmera CSI (não usada), 06 revisão técnica, 07 controle pelo celular
└── requirements.txt
```

## Ordem recomendada

1. `docs/01_ligacao_camera.md` e `docs/02_bringup_camera.md` — ligar a OV7670, diagnóstico (`MODO_DIAGNOSTICO 1`), depois
   `python tools/ver_camera.py --salvar foto.png`.
2. `docs/00_motores_e_sensores.md` — `tools/testar_motores.py` e `tools/testar_ultrassom.py` (rodas no ar). Ultrassom/encoders só no modo sem câmera
   (`USAR_CAMERA 0` + `FIRMWARE_COM_CAMERA = False`; pinos da planilha nova).
3. `docs/03_bluetooth_headset.md` — parear o headset e `python tools/testar_microfone.py`.
   `docs/07_controle_bluetooth.md` — controlar o carrinho pelo celular (Android).
4. `python main.py` — "siga" segue a linha, "pare" para.
5. Sem hardware nenhum dá para testar a Pi: `python tools/simulador_arduino.py --sem-imagem` imprime uma porta virtual
   (ponha em `SERIAL_PORTA`) e `FONTE_IMAGEM = "simulada"` dá uma linha falsa.

### Ultrassom e teste da segurança

Para HC-SR04 em D9/D10, grave o firmware com `USAR_CAMERA=0` e mantenha `FIRMWARE_COM_CAMERA = False` e
`SERIAL_BAUD = 115200` em `config.py`. Na Arduino IDE: abra `arduino/robo_firmware/robo_firmware.ino`, selecione Arduino Uno
e a porta do dispositivo, confira `#define USAR_CAMERA 0` em `config.h` e use **Sketch > Upload**. Com `arduino-cli`:

```bash
arduino-cli compile --fqbn arduino:avr:uno arduino/robo_firmware
arduino-cli upload -p /dev/ttyACM0 --fqbn arduino:avr:uno arduino/robo_firmware
```

Na Pi, com a porta em `SERIAL_PORTA`, rode `python tools/ler_sensores.py` para validar distância e encoders. Para ver a
barreira enquanto injeta avanço continuamente (rodas suspensas), use `python tools/testar_ultrassom.py --comando avancar`;
`--comando re` confirma que a ré não é afetada. `python main.py` inicia voz e Bluetooth junto com o controle: teste com
o celular repetindo avanço e acompanhe a saída de `tools/ler_sensores.py` em uma segunda conexão somente se a porta serial
permitir apenas um processo; em geral, use `tools/testar_ultrassom.py` sozinho para telemetria e depois `main.py` para o
teste combinado de Bluetooth. A distância de parada/liberação é espelhada em `config.py` e `arduino/robo_firmware/config.h`:
25 cm / 30 cm.

## Instalação na Raspberry Pi 5 (Debian 13.7 / Raspberry Pi OS "trixie")

```bash
cat /etc/os-release; cat /etc/rpi-issue 2>/dev/null        # confira a versão e se é o Raspberry Pi OS (repositório da Raspberry Pi)
sudo apt update
sudo apt install -y python3-venv libportaudio2 bluez
python3 -m venv --system-site-packages venv && source venv/bin/activate   # Debian 13: pip global é bloqueado (PEP 668)
pip install -r requirements.txt          # scikit-learn precisa ser a 1.8.0 (a do treino)
sudo usermod -aG dialout,audio,video,bluetooth $USER      # depois faça logout/login
python tools/verificar_ambiente.py       # diz o que falta (câmera, áudio, serial, versões)
```

Com a OV7670 no Arduino não precisa de `picamera2`/`rpicam-apps`. A imagem chega pela serial a 1 Mbaud
(`SERIAL_BAUD = 1_000_000`); grave o firmware com `USAR_CAMERA 1` e `MODO_DIAGNOSTICO 0`.

Grave `arduino/robo_firmware/` no UNO pela Arduino IDE (placa UNO; os arquivos `.h/.cpp` ficam na mesma pasta do `.ino`).
Porta serial: `ls /dev/ttyACM*` → `SERIAL_PORTA` em `config.py`. Depois `python main.py` (fique ~1 s em silêncio no início:
calibração do ruído de fundo).

## Como as threads se protegem

- `EstadoRobo` guarda modo e última leitura da visão atrás de um `RLock`; ninguém usa variável global solta.
- Só `ThreadControle` decide o que vai para os motores. A visão apenas publica o erro.
- `aplicar_comando` (chamado pela thread de voz) e o ciclo do controle seguram `estado.lock`
  enquanto leem o modo e enviam ao Arduino, então um "pare" nunca é sobrescrito por um comando de linha atrasado.
- `ArduinoSerial` tem o seu próprio `Lock` para que duas threads nunca escrevam bytes misturados na serial; uma thread
  dedicada lê a serial e entrega o quadro mais recente à visão.
- Se o headset Bluetooth cair, o robô para (`PARAR_SE_SEM_MICROFONE`).
- Se qualquer thread morrer, `main` encerra tudo e manda parar. O Arduino também para sozinho após 400 ms sem comandos.

## Comportamento dos comandos

| Voz | Efeito |
|---|---|
| pare | modo PARADO, motores cortados na hora, visão suspensa |
| siga | modo SEGUINDO, visão retomada |
| esquerda / direita | giro forçado por `TEMPO_GIRO_S`, depois volta a seguir a linha |
| voltar | ré por `TEMPO_RE_S`, depois para |

## Notas sobre a voz

- O modelo só é consultado quando o VAD fecha uma palavra. O "pare" reage depois que a palavra termina
  + `VAD_BLOCOS_FIM` × 64 ms de silêncio + o tempo das features. Reduzir `VAD_BLOCOS_FIM` (ex.: 4) deixa o
  "pare" mais rápido; teste com a sua voz, porque valores baixos podem cortar palavras com pausa no meio.
- Confiança mínima: 50% (a do projeto original); "pare" aceita a partir de 40%.
- O pré-processamento é o mesmo do treino: qualquer mudança em `voz/features.py` invalida o modelo.
- Modelo padrão: `mistura` (LSTM + SVM, média das probabilidades). Para usar só o MLP, `MODELO_TIPO = "mlp"`
  em `config.py`. Não precisa de PyTorch na Pi: o `.pkl` é lido com uma lista de permissões e o LSTM roda em NumPy.
- O LSTM usa pré-ênfase 0,9 e o SVM/MLP usam 0,97. É assim no seu treino (`pre_enfase()` sem argumento no
  `5_extract_sequences.py`), então foi mantido.
- **Antes de confiar no LSTM na Pi, rode uma vez no computador onde você tem PyTorch:**
  `python tools/validar_mistura.py PASTA_DO_PROJETO_ORIGINAL audio1.wav audio2.wav ...`
  (use alguns áudios reais de cada comando). Esperado: diferença < 1e-4 e "APROVADO".

## O que foi e não foi testado

- Testado no PC: o firmware compilado para o ATmega328P com avr-gcc (3 configurações: com câmera, bancada e diagnóstico:
  **só compilou e coube na memória, nunca rodou**); a lógica do modo de bancada com g++ contra um Arduino simulado
  (ultrassom, encoders, comandos de motor, watchdog, checksum); a Pi completa contra o simulador de Arduino, inclusive a
  decodificação da imagem pela serial (perda de bytes, status);
  a voz (extração idêntica à original e a mistura LSTM+SVM validada com os seus 1670 áudios); a hierarquia de voz;
  o pacote `aprendizado/` (32 testes + integração, no simulador sintético).
- **Não testado:** a OV7670 real (I2C, XCLK, captura de linhas: temporização do AVR), o firmware rodando no UNO real, motores/bateria
  reais, o headset Bluetooth real, nem o aprendizado na pista física.

## LEDs e buzzer ativo

No modo atual sem câmera, LEDs verde/amarelo/vermelho em A0/A1/A2 e buzzer ativo em D10 indicam a proteção frontal. Buzina manual pelo Bluetooth: `buzina` e `buzina off` (com Enter). Ligação, comportamento e teste em [docs/10_sinalizacao.md](docs/10_sinalizacao.md).
