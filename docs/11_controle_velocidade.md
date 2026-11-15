# Controle de velocidade com encoders

O Arduino regula cada roda por PI, medindo pulsos por segundo em D2/D3.
Nao e necessario conhecer o modelo do sensor para usar essa unidade.
O hardware atual tem um canal por roda: mede magnitude, nao o sentido real.
O sentido e determinado pelo comando. Discos com resolucoes diferentes precisam
de calibracao antes de usar o mesmo alvo para obter rotacoes iguais.

## Primeiro teste

A montagem sem camera tem os dois motores com polaridade invertida em relacao
ao acionamento original. `MOTOR_ESQ_INVERTIDO` e `MOTOR_DIR_INVERTIDO` em
`config.h` corrigem isso somente na saida da ponte H, tanto para PWM como PI.
Nao inverter novamente os fios sem revisar essas opcoes. Encoders permanecem
E=D2 e D=D3. Essa correcao de sentido nao resolve por si so a oscilacao do PI.

O teste individual posterior confirmou canais de potencia trocados: a roda
esquerda esta no canal fisico B (ENB D6, IN3 D13, IN4 D12); a direita no
canal fisico A (ENA D5, IN1 D7, IN2 D8). O mapa logico de `config.h` foi
corrigido para cada PI usar o encoder da propria roda, sem trocar fios.

1. Grave novamente o firmware `arduino/robo_firmware` no Uno.
2. Mantenha `USAR_CAMERA=0` e `FIRMWARE_COM_CAMERA=False`.
3. Com os motores desligados, use `python tools/ler_sensores.py` e gire cada roda:
   somente a contagem correspondente deve aumentar.
4. Feche essa ferramenta e o main.py. Suspenda as rodas, ligue a alimentacao
   dos motores e mantenha a frente livre.
5. Execute `python tools/testar_velocidade.py --pps 20 --tempo 5`.
   A ferramenta pede confirmacao e exibe a velocidade medida de cada roda.
   Nao execute duas ferramentas na mesma porta.
6. Compare alvo e leitura. Os ganhos iniciais nao foram calibrados fisicamente.

O firmware amostra a cada 100 ms. Parametros em `arduino/robo_firmware/config.h`:
- `VELOCIDADE_KP`, `VELOCIDADE_KI`: ganhos PI iniciais de 1.
- `VELOCIDADE_PWM_MAX`: teto inicial de 180, nao garante tensao adequada ao motor.
- `VELOCIDADE_PWM_PARTIDA`: integral inicial de 120 ao iniciar cada roda ou
  inverter sentido, baseada no teste PWM que moveu ambas as rodas. Renovar
  comandos nao reinicia a integral; o PI continua ajustando para cima e para
  baixo, sem impor PWM minimo permanente. Validar em bancada antes de ativar.
- `VELOCIDADE_MAX_PPS`: limite de 120 pulsos/s.
- `VELOCIDADE_SEM_PULSO_MS`: 1000 ms sem pulsos com alvo diferente de zero
  para as duas rodas e trava o modo de velocidade ate receber parada S.

Comece com alvo baixo, mas suficiente para produzir pulsos. Resolucao baixa ou
alvo muito baixo podem causar falsa deteccao de roda travada. Oscilacao exige
reduzir os ganhos; erro persistente exige ajuste gradual. Nao aumentar os
limites sem observar os motores. Protecoes de obstaculo, servo e watchdog
permanecem prioritarias. Aproximacao reduz os alvos e a potencia.

Com integral inicial zero, um alvo de 28 pulsos/s produzia cerca de PWM 31
na primeira amostra e podia nao vencer o atrito antes do corte de 1 segundo.
O ajuste de partida nao comprova funcionamento dos encoders: com a potencia
desligada, gire cada roda e confira contagens independentes em D2/D3 usando
`python tools/ler_sensores.py`. Depois grave o firmware atualizado e teste
`python tools/testar_velocidade.py --pps 28 --tempo 5` com rodas suspensas.
A ferramenta aponta rodas sem pulsos; uma roda girando com contagem zero
exige revisar o sensor e sua ligacao. Mantenha o controle automatico desativado
ate ambas registrarem pulsos e acompanharem o alvo sem cortes.

## Ativar no programa principal

Apos validar, em `config.py`:
```python
CONTROLE_VELOCIDADE_ATIVO = True
VELOCIDADE_REFERENCIA_PPS = 60
```

A interface antiga continua recebendo valores -255..255, mas com a opcao ativa
eles passam a representar uma proporcao da referencia de pulsos/s.
Por exemplo, 127 representa aproximadamente 30 pulsos/s com referencia 60.
Isso altera a resposta do seguidor e exige reajustar velocidade/ganhos na pista.
O modo padrao permanece PWM ate a validacao. Desative a opcao para diagnosticos
que precisam enviar PWM, como `tools/testar_motores.py`.

API explicita: `ArduinoSerial.velocidade(esq, dir)`, em pulsos/s assinados.
Protocolo: comando R com dois int8, entre -120 e 120. S para e rearma falha;
M troca para PWM direto. Comandos precisam ser renovados antes de 400 ms.
O firmware com camera rejeita movimento por velocidade porque nao possui encoders.

A falha de encoder pode ser consultada internamente por
`motores_falha_encoder()`; ainda nao e enviada na telemetria serial.
A leitura da ferramenta exibe magnitude, inclusive durante re.
Para converter em RPM: RPM = pulsos/s * 60 / pulsos por volta da roda.
