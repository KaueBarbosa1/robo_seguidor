# Teste do firmware no PC (sem Arduino, sem avr-gcc)

Compila o firmware com `g++` contra um "Arduino de mentirinha" (`Arduino.h`) e confere: leitura do HC-SR04, parada por
obstáculo/histerese/falha, ré liberada, PWM/direção, watchdog (400 ms), checksum e encoders. É um teste de LÓGICA no PC:
**não compila para o AVR e não prova nada sobre o hardware**.

    cd arduino/teste_host
    g++ -std=c++17 -I. -I../robo_firmware -o teste harness.cpp ../robo_firmware/comandos.cpp \
        ../robo_firmware/motores.cpp ../robo_firmware/sensores.cpp ../robo_firmware/servo.cpp \
        ../robo_firmware/sinalizacao.cpp
    ./teste          # termina com TUDO_OK

O simulador usa os pinos do config.h ativo (TRIG D4/ECHO D11); nao altera a montagem.
Com USAR_SERVO=1 tambem verifica limites de pulsos, Timer1 configurado, varredura
somente parado, descarte de eco lateral, estabilizacao, retorno por timeout e
compatibilidade dos pacotes. A inspecao parada verifica tres posicoes com ecos
simulados diferentes, falha lateral, pacote por rodada, bloqueio de ambas as
rodas, cancelamento e timeout. Tambem confere reducao proporcional de PWM. O pulso eletrico real e o movimento nao sao simulados.
Para conferir a opcao sem servo, adicionar `-DUSAR_SERVO=0` a compilacao.

Com sinalização habilitada, confere LEDs, aviso intermitente, falha do sensor,
buzina manual, limite de duração e independência do watchdog dos motores.
Para conferir sem sinalização, adicionar `-DUSAR_SINALIZACAO=0`.
