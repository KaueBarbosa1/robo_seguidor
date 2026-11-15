# 2. Fazendo a câmera funcionar (bring-up)

Ordem obrigatória: cada passo depende do anterior. **O firmware nunca foi rodado numa OV7670 real por quem o escreveu**: esse roteiro existe justamente para você achar o problema pelo código de erro.

## Passo A — Diagnóstico (Arduino IDE no seu PC)
1. Em `arduino/robo_firmware/config.h` ponha `#define MODO_DIAGNOSTICO 1`.
2. Abra `robo_firmware.ino` na Arduino IDE (placa Arduino UNO), envie, abra o **Monitor Serial a 115200**.
3. Leia as etapas:

| Etapa | Saída esperada | Se falhar |
|---|---|---|
| [2] Varredura I2C | `achei 0x21  <- OV7670` | Nada: pull-ups 4,7k em 3,3V; SIOC=A5 e SIOD=A4 (troque os dois se estiverem invertidos); XCLK chegando; 3,3V; PWDN no GND; RESET no 3,3V. |
| [3] Identificação | `PID=0x76 VER=0x73` | Valor estranho: fios longos/mau contato, pull-ups fracos; ou não é OV7670. |
| [4] Configuração | `OK` | Código 3: algum registrador não gravou (I2C instável). |
| [5] VSYNC | ~2,5 quadros/s | 0: fio do VSYNC em D3; XCLK; alimentação. |
| [6] PCLK por quadro | `38400` | 0: fio do PCLK em D2. Muito acima: COM10 não pegou ou ruído no PCLK. Abaixo: PCLK rápido demais — suba `CAM_CLKRC` em `config.h` (3 → 4, 5…). |
| [7] Linha de amostra | sugere `CAM_Y_FASE` | Copie o valor sugerido para `config.h`. |

Resumo do que cada falha quer dizer:
- **Não aparece nada no I2C** → problema elétrico/XCLK (80% dos casos: pull-up em 5V, XCLK sem divisor ou sem chegar, SIOD/SIOC trocados).
- **I2C ok, sem VSYNC/PCLK** → fio de sinal solto ou XCLK não chega.
- **PCLK ok, imagem estranha** → só falta ajustar `CAM_Y_FASE`.

## Passo B — Firmware normal
1. `MODO_DIAGNOSTICO 0`, envie de novo. A partir daqui **o Monitor Serial não serve mais** (a serial roda a 1 Mbaud binário).
2. Espete o UNO na Raspberry Pi. Descubra a porta: `ls /dev/ttyACM*`. Ajuste `SERIAL_PORTA` em `config.py`.
3. Na Pi: `python tools/ver_camera.py --salvar foto.png` (via SSH) ou sem `--salvar` (com tela/VNC). O programa mostra a imagem 4× maior e a linha detectada.
4. O log mostra o **status** da câmera enviado pelo Arduino (`Status da câmera: ...`) com o motivo, se houver falha. Com a câmera com defeito os motores **continuam obedecendo** à Pi.

## Passo C — Ajustes de imagem
| Sintoma | Ajuste |
|---|---|
| Imagem listrada/ruído | Troque `CAM_Y_FASE` (0 ↔ 1) em `config.h`. |
| Linhas com falhas / imagem rasgada | Aumente `CAM_CLKRC` (menos pixels perdidos, menos quadros/s). |
| Imagem espelhada ou de cabeça para baixo | `IMAGEM_ESPELHAR_H` / `IMAGEM_ESPELHAR_V` em `config.py`. |
| Quer olhar só a parte de baixo | `LINHA_INICIAL` no firmware **e** `FW_LINHA_INICIAL` no `config.py` (mesmo valor). |
| Imagem muito escura/clara ou borrada | Ajuste a lente (rosca na frente) e a luz. A câmera sem FIFO tem imagem de **16 tons** — contraste forte (fita preta em piso claro) é essencial. |
| Linha não detectada | `LINHA_ESCURA`, `CONTRASTE_MIN`, `AREA_MIN` em `config.py`. |

## Limites que você deve conhecer
- Velocidade: ~2,5 quadros/s com `CAM_CLKRC=3`. Com `2`/`1` fica mais rápido, mas o UNO pode perder pixels — teste com o passo [6] do diagnóstico. Por isso `VEL_BASE` deve ser baixa no início.
- Durante a leitura de cada linha (~0,6 ms) o Arduino não escuta a serial. Um comando pode se perder, e por isso a Pi reenvia comandos 20×/s e manda "pare" 3 vezes.
- Se travar, o watchdog do AVR reinicia a placa em 250 ms e os motores param sozinhos.
