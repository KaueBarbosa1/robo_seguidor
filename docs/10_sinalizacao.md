# LEDs de sinalizacao

Buzzer removido a pedido do usuario. No perfil `USAR_CAMERA=0`, D10 fica livre:
o firmware nao configura nem escreve nesse pino. Desconecte o buzzer com USB
e bateria desligados. Regrave o Uno para aplicar a alteracao de software.
No perfil legado com OV7670, D10 continua reservado ao motor.

| Componente | Pino |
|---|---|
| LED verde | A0 |
| LED amarelo desativado (LOW) | A1 |
| LED vermelho | A3 |

Use resistor de 330 ohms em serie com cada LED e catodo ao GND.

## Comportamento

- Verde: guarda frontal liberada, servo permitindo movimento e nenhuma falha de encoder. Pode acender durante a varredura do modo 4 e na aproximacao, enquanto a guarda permitir avanco.
- Vermelho: obstaculo confirmado, frente bloqueada/sem leitura valida, servo impedindo movimento ou falha de encoder. Um obstaculo confirmado mantem o vermelho ate novas leituras frontais liberarem o avanco.

O amarelo permanece apagado. Os comandos legados H (buzina) e A (avisos)
sao aceitos sem efeito sonoro, para compatibilidade com o Python existente.
Nao renovam o watchdog dos motores. A temporizacao do controle permanece
inalterada. Protecoes de motor, servo e ultrassom permanecem independentes.

## Verificacao e gravacao

O harness verifica LEDs, preservacao de D10 e watchdog em simulacao.
Compilacao e simulacao nao validam a montagem fisica.

```bash
arduino-cli compile --fqbn arduino:avr:uno arduino/robo_firmware
arduino-cli upload -p /dev/ttyACM0 --fqbn arduino:avr:uno arduino/robo_firmware
```

Feche ferramentas que usam a serial antes do upload. Mantenha a potencia
 dos motores desligada durante a gravacao.


## Indicacao no manual sem ultrassom — 24/11/2026

Com U/F8 manual ativo, a pausa intencional do HC-SR04 nao acende vermelho.
Verde indica modo manual sem falha de encoder, nao caminho livre medido.
Ao restaurar o autonomo, LEDs voltam a refletir sensor/servo/obstaculo/encoder
como antes. A sinalizacao continua sem comandar ou liberar motores.
