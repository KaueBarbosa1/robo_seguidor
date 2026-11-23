# Teste isolado de LEDs e buzzer

Para Arduino UNO com a montagem sem câmera descrita em ../../docs/10_sinalizacao.md.
Desligue a potência dos motores antes de gravar. O sketch mantém a ponte H
nos pinos 5, 6, 7, 8, 13 e 12 em LOW. Não use com o mapa da câmera.

- Verde: A0; vermelho: A3. Cada LED usa resistor de 330 Ω e catodo no GND. O antigo amarelo em A1 permanece desligado e pode ser desconectado.
- Buzzer ativo: D10 via transistor, conforme a documentação de sinalização.

```bash
arduino-cli compile --fqbn arduino:avr:uno arduino/teste_sinalizacao
arduino-cli upload -p /dev/ttyACM0 --fqbn arduino:avr:uno arduino/teste_sinalizacao
```

Ajuste a porta conforme seu Arduino. Feche main.py, o serviço do robô e outros
programas usando a serial antes de gravar. Abra o Monitor Serial em 115200 baud.

O ciclo repete: cada LED acende por 1 segundo, o buzzer emite três bipes,
e ambos os LEDs acendem com um bipe curto. Há uma pausa de 2 segundos.
Buzzer passivo não é compatível com este teste de nível alto.

Este sketch substitui temporariamente o firmware do robô. Ao terminar, grave
novamente arduino/robo_firmware para voltar à operação normal.
