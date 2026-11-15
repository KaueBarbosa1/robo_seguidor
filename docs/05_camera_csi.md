# 5. (NÃO USADA) Câmera: Raspberry Pi Camera Rev 1.3 (OV5647) no conector CSI da Pi 5

> **Decisão de 21/10/2026: o projeto voltou para a OV7670 no Arduino. Esta página e o código CSI (`visao/camera_csi.py`,
> `FONTE_IMAGEM = "csi"`) ficam só como alternativa guardada; nada aqui vale para o robô atual.**
> A câmera do projeto: `docs/01_ligacao_camera.md` e `docs/02_bringup_camera.md`.

> Foi adotada no lugar da OV7670 e depois abandonada. Nada aqui foi testado com a câmera real: o código foi testado só com uma
> câmera falsa que imita o `picamera2`. Quando ela chegar, siga a ordem abaixo e me diga o que apareceu.

## A câmera (pela foto)
Placa "Raspberry Pi Camera Rev 1.3": sensor **OV5647** (5 MP), **foco fixo ajustável à mão** (anel da lente), obturador
*rolling shutter*, com filtro de infravermelho. Cabo flat de **15 pinos** (o que aparece na foto).

## 1. Ligação física (com a Pi DESLIGADA)
- A Raspberry Pi 5 tem **dois conectores de câmera pequenos de 22 pinos** (rotulados CAM/DISP 0 e 1). O cabo da foto é de
  15 pinos, então você precisa de um **cabo adaptador 15 pinos ⇄ 22 pinos para Pi 5** (vendido à parte; a câmera sozinha não
  encaixa direto). Sem ele não liga.
- Levante a trava plástica do conector, encaixe o cabo **reto e até o fundo**, abaixe a trava. Faça igual na câmera.
- O lado dos contatos metálicos importa e é diferente nas duas pontas; confira a figura do guia oficial da Raspberry Pi
  para câmeras. Se na etapa 2 a câmera não aparecer, desligue e reposicione o cabo (lado e profundidade) antes de suspeitar de outra coisa.

## 2. A Pi enxerga a câmera?
```
sudo apt update && sudo apt install -y python3-picamera2
rpicam-hello --list-cameras          # deve listar "ov5647"  (em sistema mais antigo: libcamera-hello)
rpicam-still -o teste.jpg            # tira uma foto
```
Se não listar: em `/boot/firmware/config.txt` acrescente `dtoverlay=ov5647` (se usar o 2º conector: `dtoverlay=ov5647,cam0`)
e reinicie.

## 3. Ver o que o robô vê, e focar
```
python tools/ver_camera.py                    # janela (monitor/VNC)     |   python tools/ver_camera.py --salvar foto.png
```
Mostra o quadro cinza 120x160 (ampliado 4x), a região analisada e a linha detectada.
- **Foco:** de fábrica o foco é para longe (~1 m). Para o chão a 10–20 cm, gire levemente o anel da lente (pinça/ferramenta
  plástica; pode ter cola) até a linha ficar nítida na imagem. Faça com a câmera já na posição final.
- **Posição:** presa ao carrinho olhando para frente e para baixo, ~15–20 cm do chão. O campo de visão do OV5647 é de cerca de
  54°x41°, então o chão visível tem largura aproximadamente igual à altura da câmera (conferir na imagem). Não deixe a
  frente do carrinho cortar a vista, e evite sombras e reflexos fortes.
- Imagem espelhada/de cabeça para baixo: `IMAGEM_ESPELHAR_H` / `IMAGEM_ESPELHAR_V` em `config.py`.
- Linha não detectada: `LINHA_ESCURA`, `CONTRASTE_MIN`, `AREA_MIN`, `ROI_INICIO`.
- Brilho "respirando" na pista: fixe a exposição (`CAMERA_EXPOSICAO_US`, `CAMERA_GANHO`).

## 4. Parâmetros (`config.py`)
`FONTE_IMAGEM="csi"`, `CAMERA_FPS=30`, `CAMERA_PRINCIPAL=(640,480)`, `CAMERA_LORES=(320,240)`, `CAMERA_EXPOSICAO_US`,
`CAMERA_GANHO`. O quadro final é sempre cinza 120x160 (o resto do robô e a CNN não mudam). No aprendizado,
`APR_PERIODO_MIN_S=0.4` faz o robô usar no máximo 1 quadro a cada 0,4 s (o ritmo em que tudo foi dimensionado); reduza só
depois de medir na pista, e então revise `APR_MAX_BURACO`, `APR_MAX_QUADROS_SEM_LINHA` e `APR_PARADO_PASSOS` (contam passos).

## O que muda em relação à OV7670
Some: os 16 tons de cinza (agora 8 bits), os ~2,5 quadros/s do sensor, a captura lenta de 0,4 s com deformação, a perda de
linhas na serial e o conflito de pinos com os motores. Continua: o *rolling shutter* (deformação pequena a 30 fps), a
latência do ciclo (captura + processamento + resposta do motor) e a dependência de boa luz e foco.

## Ligação Pi ⇄ Arduino (ainda a definir)
O código atual (herdado do projeto anterior) usa **USB** (`/dev/ttyACM0`, 115200). Se usar a UART dos GPIO (14/15), o Arduino é 5 V e a Pi é 3,3 V: use
conversor de nível, e ajuste `SERIAL_PORTA` (por ex. `/dev/ttyAMA0`).
O firmware atual só tem motores + HC-SR04 + encoders (mapa provisório de `docs/00_motores_e_sensores.md`).

## Alimentação
A Pi 5 precisa de fonte própria de 5 V (a oficial é 5 V/5 A). Não alimente a Pi pelo 5 V do L298N. GND em comum com o Arduino.
