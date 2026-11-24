# Teste do firmware no PC (sem Arduino, sem avr-gcc)

Compila o firmware com `g++` contra um "Arduino de mentirinha" (`Arduino.h`) e confere: leitura do HC-SR04, parada por
obstáculo/histerese/falha, ré liberada, PWM/direção, watchdog (400 ms), checksum e encoders. É um teste de LÓGICA no PC:
**não compila para o AVR e não prova nada sobre o hardware**.

    cd arduino/teste_host
    g++ -std=c++17 -I. -I../robo_firmware -o teste harness.cpp ../robo_firmware/comandos.cpp \
        ../robo_firmware/motores.cpp ../robo_firmware/sensores.cpp ../robo_firmware/servo.cpp \
        ../robo_firmware/sonar_movimento.cpp ../robo_firmware/sinalizacao.cpp
    ./teste          # termina com TUDO_OK

O simulador usa os pinos do config.h ativo (TRIG D4/ECHO D11); nao altera a montagem.
Com USAR_SERVO=1 tambem verifica limites de pulsos, Timer1 configurado, varredura
somente parado, descarte de eco lateral, estabilizacao, retorno por timeout e
compatibilidade dos pacotes. A inspecao parada verifica tres posicoes com ecos
simulados diferentes, falha lateral, pacote por rodada, bloqueio de ambas as
rodas, cancelamento e timeout. Tambem confere reducao proporcional de PWM. O pulso eletrico real e o movimento nao sao simulados.
Para conferir a opcao sem servo, adicionar `-DUSAR_SERVO=0` a compilacao.

Com sinalizacao habilitada, confere LEDs, falha do sensor, D10 livre apos
remocao do buzzer e independencia do watchdog perante comandos legados.
Para conferir sem sinalização, adicionar `-DUSAR_SINALIZACAO=0`.

O sonar continuo e exercitado por mais de uma ida e volta, com movimento por
todos os graus sem pausas por eco e medidas associadas ao angulo no disparo,
mesmo se o comando mudou antes da resposta. Confere intervalo minimo de
60 ms entre disparos, ausencia de eco, sequencia, enquadramento
da UART, renovacao sem reiniciar o ciclo e bloqueio das rodas inclusive a 90
graus. Tambem verifica cancelamento, timeout e recuperacao da protecao frontal.
A suavidade e o angulo fisico precisam ser validados no hardware.

O modo sem camera agora recebe por interrupcao/buffer de `HardwareSerial`.
O parser continua no loop; TX usa os registradores, sem `Serial.print/write`.
O modelo de RX do harness acrescenta um ensaio de rajadas: dez bytes chegam
durante uma pausa sintetica de 870 us no loop. Sem ISR, o modelo limita o
hardware a dois bytes e perde os pacotes; com buffer, preserva S e V4 sem
executar comandos na ISR. Repetir por 10 s simulados mantem o modo e visita
60/120 graus; suspender renovacao por 420 ms continua cancelando. Esse ensaio
falha na versao anterior por tres verificacoes. Os 870 us sao uma condicao
imposta pelo teste, nao uma medicao da duracao dos calculos no AVR. O modelo
nao mede latencia real de ISR, ruido eletrico nem estabilidade da alimentacao.

O PI baixo separa reforco80 ate primeiro pulso e integral inicial E32/D34.
O harness verifica reducao individual antes da janela de100 ms, renovacao R,
zero/re, parada S, falha de uma roda sem primeiro pulso e watchdog. A planta
sintetica de baixa velocidade tem atrito de partida maior que sustentacao e
inercia: gera pulsos conforme o PWM aplicado. Confere arrancada limitada,
taxa final proxima do alvo4 e ausencia de cortes apos liberar a frente quando
combinada ao modo4. O modelo nao e identificacao do motor real. Valores/ganhos
novos requerem ensaio fisico com rodas suspensas; nao validam frenagem no piso.

A revisao de diagnostico acrescenta quadro F8 (PWM E/D e flags de sinal,
falha de encoder, PI e fase de reforco). O parser valida seu enquadramento.
O caso com atrito adicional reproduzia perda de giro e falha de encoder.
Na revisao de sustentacao, espera pulsos nas duas rodas com piso condicional
e verifica que excesso de velocidade, pedidos menores, zero e re nao ficam
presos ao piso. A revisita frontal antecipada reserva orcamento de retorno;
o teste verifica que solicita-la nao renova memoria nem bloqueia rodas.
As plantas rodam10 s e avaliam os dois segundos finais, com/sem sonar e
atrito adicional. A falta real de pulsos ainda precisa parar e travar a falha.
Passar esses testes nao valida o carrinho fisico ou sua frenagem.

O modo 4 tambem e testado. Por padrao a calibracao ausente bloqueia qualquer
movimento. Uma compilacao separada, somente para a planta SINTETICA, acrescenta:

```text
-DSONAR_MOV_CALIBRADO=1 -DSONAR_MOV_MM_PULSO_ESQ=1.0f -DSONAR_MOV_MM_PULSO_DIR=1.0f
-DSONAR_MOV_MAX_PPS=28 -DSONAR_MOV_FRENAGEM_MM=20 -DSONAR_MOV_AVANCO_MAX_MM=50
```

Esses numeros NAO sao calibracao do carrinho e nao devem ser gravados no Uno.
Esse teste verifica rodas em movimento durante observacao lateral, revisita
frontal, memoria por encoder, timeout e parada local, limites e cancelamento.


O modo manual sem ultrassom acrescenta teste de U/F8: sustenta PWM por2 s
com eco ausente, sem novos disparos TRIG; U sozinho nao renova movimento;
S para; R nao renova o modo; timeout/boot restauram protecao. U0 invalida
frente antiga e exige ecos novos antes de liberar avanco autonomo. Tambem
verifica o teto baixo do PI manual e argumentos U invalidos. Passa nos perfis
padrao e sem servo. Isso valida logica simulada, nao movimento fisico.
