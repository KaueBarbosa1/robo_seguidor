# LEDs e buzzer ativo integrados

Pinagem confirmada para `USAR_CAMERA=0`, com `USAR_SINALIZACAO=1` (padrão nesse modo).

| Componente | Pino | Ligação |
|---|---|---|
| LED verde | A0 | A0 → resistor de 330 Ω → ânodo; cátodo ao GND |
| Antigo LED amarelo, desativado | A1 | Pino mantido em LOW; o LED pode ser desconectado |
| LED vermelho | A3 | A3 → resistor de 330 Ω → ânodo; cátodo ao GND |
| Buzzer ativo | D10 | Acionamento por transistor, descrito abaixo |

Use um resistor separado para cada LED. Os pinos analógicos funcionam como saídas digitais.
Servo continua em D9; TRIG/ECHO em D4/D11. A sinalização não usa `tone()`, PWM ou os timers do servo/motores.

Para buzzer ativo de dois terminais, use NPN (por exemplo, BC337): D10 → resistor de 1 kΩ → base; emissor ao GND; coletor ao negativo do buzzer; positivo do buzzer à alimentação nominal dele. Confira a ordem dos terminais do transistor no datasheet. Use resistor de 10 kΩ entre base e emissor. Para buzzer magnético, coloque diodo de proteção em paralelo, cátodo no positivo. Una os GNDs. Buzzer passivo exige outra forma de gerar som; este código aciona um buzzer ativo com nível alto.

## Comportamento

- Verde: guarda frontal liberada, servo permitindo movimento e nenhuma falha de encoder. Pode acender durante a varredura do modo 4 e na aproximacao, enquanto a guarda permitir avanco.
- Vermelho: obstaculo confirmado, frente bloqueada/sem leitura valida, servo impedindo movimento ou falha de encoder. Um obstaculo confirmado mantem o vermelho ate novas leituras frontais liberarem o avanco.
- Obstáculo confirmado: bipes de 150 ms a cada 800 ms; têm prioridade sobre a buzina manual.
- Buzina manual: no máximo 1,5 segundo. Repetir ligar não prolonga; envie desligar antes de ligar novamente. Não renova o watchdog dos motores.

O amarelo foi desativado a pedido do usuario. A1 continua inicializado em LOW
para manter apagado um LED que ainda esteja conectado; nunca e aceso pelo
firmware nem pelo teste isolado de sinalizacao.

Na revisao manual com `SONAR_MOV_CONTINUO=1`, a sonda nao para no centro e
as rodas nao dependem do orcamento de encoder/revisita. Vermelho acompanha
obstaculo frontal confirmado ou falha, verde acompanha liberacao. A main
mantem re curta por obstaculo confirmado. O perfil anterior de reservas e
memoria fica disponivel com `SONAR_MOV_CONTINUO=0`; detalhes e limites do
perfil atual no [guia14](14_sonar_em_movimento.md).

As cores apenas mostram o estado. A sinalizacao nao envia comandos de motor
nem libera rodas. As protecoes de ultrassom, servo, encoders e watchdogs
continuam independentes. Um bloqueio lateral pode impedir a curva para esse
lado enquanto a frente liberada continua verde; verde nao garante todas as
direcoes livres. Vermelho por falha sem obstaculo confirmado nao inicia o
bipe de obstaculo. Nao ha espera bloqueante.

## Gravar e conferir

Na pasta do projeto:

```bash
arduino-cli compile --fqbn arduino:avr:uno arduino/robo_firmware
arduino-cli upload -p /dev/ttyACM0 --fqbn arduino:avr:uno arduino/robo_firmware
```

Feche o Monitor Serial e qualquer ferramenta usando a porta antes de executar `main.py`. Mantenha `FIRMWARE_COM_CAMERA = False` no Python (115200 baud).

Com potencia dos motores desligada, confira vermelho no inicio/sem eco,
verde com frente valida e liberada, e vermelho com bipes apos duas leituras
abaixo de25 cm. O amarelo deve permanecer apagado em todos os casos. No
modo4, reservas e memoria podem bloquear antes de25 cm; consulte o guia14.
Ausencia de eco continua bloqueando. Regravar o Uno para aplicar esta revisao;
teste/compilacao nao comprovam funcionamento fisico.

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
Os LEDs mostram liberacao frontal ou bloqueio/falha conforme os dois estados
acima. Buzina e avisos de conducao permanecem independentes das cores.

Protocolo: `A`, argumento 0 cancela, 1 partida, 2 linha perdida;
segundo argumento sempre zero. Pedidos são renovados pelo controle;
sem renovação por 400 ms, o firmware cancela o som. Não renovam
o watchdog dos motores. Prioridade: obstáculo, aviso de condução,
buzina manual. Atualize o firmware e o Python juntos.
