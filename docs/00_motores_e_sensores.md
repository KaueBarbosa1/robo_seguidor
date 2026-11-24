# 0. Motores, ultrassom e encoders no Arduino (a câmera OV7670 também está nele)

> **Dois mapas de pinos, conforme `USAR_CAMERA` em `arduino/robo_firmware/config.h`:**
> - **`USAR_CAMERA 1` (padrão, é o robô):** a OV7670 ocupa D2..D7, D11, A4, A5. Motores: ENA=D9, ENB=D10, IN1=D8, IN2=D12,
>   IN3=D13, IN4=A0. **Ultrassom e encoders ficam DESLIGADOS** (os pinos deles são da câmera). Serial a **1 Mbaud**
>   (`SERIAL_BAUD = 1_000_000`). Ligação da câmera: `docs/01_ligacao_camera.md`; testes: `docs/02_bringup_camera.md`.
> - **`USAR_CAMERA 0` (sem câmera; é o modo da semana sem a OV7670):** motores, HC-SR04 e encoders; mapa da tabela abaixo; **115200 baud**.
>   No `config.py` ponha `FIRMWARE_COM_CAMERA = False`: o baud vira 115200 e a Pi não espera imagem.
>
> **PROVISÓRIO:** a divisão final entre Arduino e Raspberry Pi (quem controla o quê) e a ligação entre as placas ainda não
> foram decididas (`docs/06_revisao_tecnica.md`). Pinos do modo de bancada conforme a planilha nova (`Planilha_Conexoes_Carrinho_Robotico_1.xlsx`).

## Mapa de pinos do modo de bancada (`USAR_CAMERA 0`)
Vem da planilha `Planilha_Conexoes_Carrinho_Robotico_1.xlsx` (aba "Mapa de pinos"), que é uma **proposta**: confira os fios.
A sinalização atual usa LEDs verde/amarelo/vermelho em **A0/A1/A3** sem buzzer; **D10 livre** no perfil sem camera. D4 permanece no TRIG. Ligação e teste: [10_sinalizacao.md](10_sinalizacao.md).

| Componente | Pino do componente | Arduino UNO | Observação |
|---|---|---|---|
| L298N | ENA | D5 (PWM) | canal logico direito; tirar o jumper do ENA |
| L298N | ENB | D6 (PWM) | canal logico esquerdo; tirar o jumper do ENB |
| L298N | IN1 / IN2 | D7 / D8 | motor direito |
| L298N | IN3 / IN4 | **D13** / D12 | motor esquerdo. A planilha se contradiz (D11 em duas abas, D13 em "L298N e motores"); **você confirmou D13 e D12 na montagem**, e o firmware usa isso |
| L298N | GND | GND do Arduino | comum com a bateria |
| HC-SR04 | TRIG / ECHO | **D4 / D11** | ligação atual; ECHO é 5 V: ok no UNO, nunca direto na Pi |
| HC-SR04 | VCC / GND | 5V / GND | |
| Encoder esquerdo / direito | sinal | D2 / D3 | confirmar saída compatível com 5 V |
| Arduino | USB | Raspberry Pi 5 | `/dev/ttyACM0` |

> **Energia (da planilha, e vale mais com a Pi):** com o Arduino ligado por USB à Pi (é por onde vão os comandos), **não** conecte o XL4015 (5 V)
> ao pino 5V do Arduino ao mesmo tempo. A planilha prevê "5 V no pino 5V, USB desconectado" para o uso final, o que **não funciona** com
> a serial por USB: a ligação final entre Pi e Arduino e a alimentação ainda precisam ser decididas (`docs/06_revisao_tecnica.md`).
> A tensão dos motores ainda é desconhecida (motores TT costumam ser 3–6 V, e a bateria 2S chega a 8,4 V): comece com PWM baixo e rodas no ar.

O HC-05 (A0/A1 do projeto antigo) não é usado: a comunicação com a Pi é pela USB.

## Cuidados antes de alimentar os motores

1. **Desligue USB e bateria antes de mexer em fios.**
2. Retire os jumpers de **ENA** e **ENB** do L298N (senão não há controle de velocidade).
3. **Bateria:** identifique a tensão dos motores e a do módulo antes de ligar. Os motores usam a bateria no borne
   de alimentação do L298N. **Nunca** alimente motores pelo 5V do Arduino ou da Pi.
4. **GND comum:** GND do L298N, do Arduino e da bateria precisam estar ligados entre si.
5. Resistores de **10 kΩ de IN1, IN2, IN3 e IN4 para o GND** (opcional, mas evita os motores dispararem
   enquanto o Arduino reinicia).
6. A polaridade eletrica e ajustada em `MOTOR_ESQ_INVERTIDO`/`MOTOR_DIR_INVERTIDO` no firmware. Na revisao de24/11, esquerda=0 e direita=`!USAR_CAMERA`: o usuario relatou esquerda em re e direita em frente ao pedir avanco. Requer regravar o Uno e conferir com rodas suspensas; nao troque tambem os fios ao aplicar essa correcao.
7. Encoders: confirme o tipo de saída e a tensão (precisa ser no máximo 5V no UNO). O firmware usa pull-up interno.

## Ordem de testes (cada passo só depois do anterior)

**A. Só a USB, sem bateria (modo de bancada)**
1. Em `config.h` ponha `USAR_CAMERA 0` e grave `arduino/robo_firmware/robo_firmware.ino` (os `.h`/`.cpp` ficam na mesma pasta).
2. Na Pi: `python tools/ler_sensores.py --baud 115200`. Aproxime a mão do HC-SR04 (a distância tem que cair)
   e gire cada roda à mão (os pulsos dos encoders sobem). Sem eco aparece "sem eco (>2,4 m)".

**B. Motores com as rodas no ar**
1. Carrinho sobre uma caixa, rodas livres. Ligue a bateria.
2. `python tools/testar_motores.py` (com câmera: pinos de motor do modo `USAR_CAMERA 1`; PWM 120, 1 s por passo; use `--pwm 100` para começar mais fraco).
   Ele testa cada roda frente/trás, depois as duas e os giros, e mostra os pulsos dos encoders.
3. Confira o sentido de cada roda e corrija trocando os fios no L298N.
4. Os comandos precisam ser reenviados a cada ~50 ms: se a Pi parar de mandar, o Arduino para os motores
   sozinho em 400 ms.

**C. Robô completo (com a câmera)**
Firmware com `USAR_CAMERA 1`, `SERIAL_BAUD = 1_000_000` e a câmera funcionando (`docs/02_bringup_camera.md`). `python main.py`:
"siga" segue a linha, "pare" para. Para ver o carrinho se mexer com uma linha falsa e sem câmera, use temporariamente
`FONTE_IMAGEM = "simulada"` em `config.py` (com as rodas no ar).

## Ultrassom: parada por obstáculo
Só existe no modo sem câmera (`USAR_CAMERA 0`), com o HC-SR04 em D4/D11. Com a câmera OV7670 o ultrassom está desligado. No firmware
`USAR_CAMERA=0`, o Arduino aplica a parada no próprio controle dos motores. O avanço para abaixo de
`OBSTACULO_DIST_CM = 25` e só libera após leituras a partir de `OBSTACULO_LIBERACAO_CM = 30` (`config.py` e
`arduino/robo_firmware/config.h` devem permanecer iguais). Duas leituras confirmam cada transição. Leituras inválidas
persistentes ou telemetria vencida bloqueiam o avanço. Ré permanece habilitada; qualquer comando com uma roda para frente
é tratado como avanço. Use `python tools/ler_sensores.py` e `python tools/testar_ultrassom.py` para diagnóstico.

## Baud
Com câmera, o firmware fala a **1 Mbaud** (`UART_U2X_UBRR 1` em `config.h`); sem câmera, 115200 (`UART_U2X_UBRR 16`). O
`config.py` precisa coincidir com o firmware gravado (`SERIAL_BAUD`).
