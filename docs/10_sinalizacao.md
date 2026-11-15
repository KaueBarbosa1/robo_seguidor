# LEDs e buzzer ativo integrados

Pinagem confirmada para `USAR_CAMERA=0`, com `USAR_SINALIZACAO=1` (padrão nesse modo).

| Componente | Pino | Ligação |
|---|---|---|
| LED verde | A0 | A0 → resistor de 330 Ω → ânodo; cátodo ao GND |
| LED amarelo | A1 | A1 → resistor de 330 Ω → ânodo; cátodo ao GND |
| LED vermelho | A3 | A3 → resistor de 330 Ω → ânodo; cátodo ao GND |
| Buzzer ativo | D10 | Acionamento por transistor, descrito abaixo |

Use um resistor separado para cada LED. Os pinos analógicos funcionam como saídas digitais.
Servo continua em D9; TRIG/ECHO em D4/D11. A sinalização não usa `tone()`, PWM ou os timers do servo/motores.

Para buzzer ativo de dois terminais, use NPN (por exemplo, BC337): D10 → resistor de 1 kΩ → base; emissor ao GND; coletor ao negativo do buzzer; positivo do buzzer à alimentação nominal dele. Confira a ordem dos terminais do transistor no datasheet. Use resistor de 10 kΩ entre base e emissor. Para buzzer magnético, coloque diodo de proteção em paralelo, cátodo no positivo. Una os GNDs. Buzzer passivo exige outra forma de gerar som; este código aciona um buzzer ativo com nível alto.

## Comportamento

- Verde: leitura frontal válida, liberada e a pelo menos 60 cm.
- Amarelo: aproximação abaixo de 60 cm, falha/ausência de leitura, bloqueio inicial ou servo fora do centro, sem obstáculo previamente confirmado.
- Vermelho: obstáculo confirmado pelo ultrassom. Mantém o vermelho durante falha, inspeção ou histerese até novas leituras frontais liberarem o avanço.
- Obstáculo confirmado: bipes de 150 ms a cada 800 ms; têm prioridade sobre a buzina manual.
- Buzina manual: no máximo 1,5 segundo. Repetir ligar não prolonga; envie desligar antes de ligar novamente. Não renova o watchdog dos motores.

As cores representam a proteção frontal, não o modo de condução ou a detecção da linha. O processamento não usa esperas bloqueantes.

## Gravar e conferir

Na pasta do projeto:

```bash
arduino-cli compile --fqbn arduino:avr:uno arduino/robo_firmware
arduino-cli upload -p /dev/ttyACM0 --fqbn arduino:avr:uno arduino/robo_firmware
```

Feche o Monitor Serial e qualquer ferramenta usando a porta antes de executar `main.py`. Mantenha `FIRMWARE_COM_CAMERA = False` no Python (115200 baud).

Com a potência dos motores desligada, confira amarelo no início/sem eco, verde com frente livre a mais de 60 cm, amarelo aproximando entre 30 e 60 cm, vermelho e bipes abaixo de 25 cm após duas leituras. Afaste para mais de 30 cm para liberar; entre 30 e 60 cm fica amarelo. Evite tomar ausência de eco como passagem livre.

No terminal Bluetooth do celular, envie cada comando com Enter:

```text
buzina
buzina off
```

Para ligar novamente, envie `buzina off` mesmo se o limite de duração já tiver desligado o som. A desconexão também solicita desligamento. Botões de apps RC precisam ter seus bytes de pressionar/soltar observados em `Bluetooth RX` e configurados em `REMOTO_BUZINA_LIGAR`/`REMOTO_BUZINA_DESLIGAR` de `config.py`; permanecem vazios até identificar os bytes do app.

## Validação

O harness de `arduino/teste_host` cobre LEDs, falha de sensor, aviso intermitente, liberação, buzina manual, payload inválido, duração máxima e independência do watchdog. O teste Python `tests/test_sinalizacao.py` verifica protocolo e encaminhamento remoto sem Bluetooth real. Testes no computador e compilação não validam a montagem física.

## Avisos de condução

No Arduino Bluetooth Control, o botao de buzina observado envia `Y`.
`REMOTO_BUZINA_PULSO="Y"` mapeia cada recebimento para desligar/rearmar e
ligar a buzina, limitada a 1,5 s pelo firmware. Nao exige byte de soltura
e nao altera modo, movimento ou watchdog. Nao e necessario regravar o
Arduino para esse mapeamento; atualizar Python e reiniciar o servico.

Ao aceitar `siga` fora do modo seguidor, o controle para os motores por
600 ms e solicita três bipes de 100 ms, separados por 100 ms.
Repetir `siga` durante a sequência não reinicia o prazo. Parar ou trocar
de modo cancela o aviso. Depois da sequência, continuam valendo as
barreiras de obstáculo e a lógica de controle existente.

Linha ausente ou leitura vencida por mais de `PERDA_LINHA_TIMEOUT_S`
gera dois bipes de 100 ms a cada 1,2 s enquanto segue sem linha.
A recuperação da leitura ou saída do modo cancela o aviso.
Os LEDs continuam indicando exclusivamente a proteção frontal.

Protocolo: `A`, argumento 0 cancela, 1 partida, 2 linha perdida;
segundo argumento sempre zero. Pedidos são renovados pelo controle;
sem renovação por 400 ms, o firmware cancela o som. Não renovam
o watchdog dos motores. Prioridade: obstáculo, aviso de condução,
buzina manual. Atualize o firmware e o Python juntos.
