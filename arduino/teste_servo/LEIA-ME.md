# Teste isolado do microservo SG90

Arquivo: `teste_servo.ino`. Arduino Uno, sinal em D9. Sem biblioteca adicional.
O servo tambem tem uma integracao opcional no firmware principal.
Este arquivo continua sendo um teste isolado; veja `docs/09_servo_integrado.md`
para gravar o principal e testar sem as esperas desta rotina.
O usuario relatou movimento curto no teste inicial de 1400 a 1600 us.
Depois foi ampliado para 1200 a 1800 us. A versao atual permite conferir/ajustar o
centro pelo Monitor Serial e iniciar a varredura continua na faixa nominal de 45 a 135 graus.
Os angulos fisicos ainda precisam ser conferidos.

## Antes de energizar

- Definir e conferir a alimentacao externa do seu servo. A fonte ainda nao foi
  confirmada nesta conversa; nao conectar o vermelho diretamente a bateria ou
  assumir que o 5 V do Arduino pode alimentar a carga.
- Marrom: negativo da fonte do servo, com GND comum ao Arduino.
- Vermelho: positivo da fonte externa regulada, compativel com o modelo real.
- Amarelo: sinal D9 do Arduino Uno. Conectores femea precisam de jumpers macho.
- Desligar a potencia dos motores. O teste tambem coloca em LOW os pinos de motor
  do mapa ativo USAR_CAMERA=0 (ENA D5, ENB D6, IN1 D7, IN2 D8, IN3 D13, IN4 D12).
- Montar sem interferencias mecanicas; comecar pelo servo sem o sensor instalado.
- Fazer as conexoes com alimentacao desligada.

Referencia de alimentacao do SG90 TowerPro: 4,8 V e fonte externa, conferir a
versao real: https://towerpro.com.tw/product/sg90-analog/

## Arduino IDE — Windows ou Raspberry Pi

1. Abrir `arduino/teste_servo/teste_servo.ino` na Arduino IDE.
2. Selecionar a placa **Arduino Uno** e a porta correspondente ao seu Arduino.
3. Se a placa estiver conectada a Raspberry com `robo.service` ativo, parar o
   servico antes do upload. No terminal da Raspberry: `sudo systemctl stop robo.service`.
4. Conferir a montagem/alimentacao e enviar o sketch pela Arduino IDE.
5. Abrir o Monitor Serial em **115200 baud**. Ao abrir, o Uno pode reiniciar e
   executar novamente o ciclo.

O servo inicia e permanece no centro. No Monitor Serial, envie **v** para iniciar:
vai gradualmente de 90 ate 45 graus nominais, depois varre ate 135 e volta a 45,
repetindo continuamente. Envie **c** para interromper a varredura e centralizar.
Passa pelas posicoes intermediarias em passos nominais de um grau, com cerca de
20 ms de pulsos por passo. Nao fica mais parado no centro ao terminar um ciclo.
Os pulsos continuam limitados a 1000-2000 us, com centro inicial em 1500 us.

## Se girar mais para um lado

Primeiro conferir a referencia mecanica, sem concluir que o servo esta defeituoso:

1. Enviar **c** e observar se o braco/suporte aponta para a frente do carrinho.
2. Se o braco foi instalado fora do alinhamento, desligar a alimentacao antes de
   soltar e reposicionar o braco no eixo. Nao forcar o eixo com a mao.
3. Para ajuste fino por software, com o servo no centro, enviar **+** ou **-**.
   Cada caractere muda o centro em 10 us. Observar qual sinal o aproxima da frente;
   o sentido fisico depende da montagem. Nao assumir que + significa direita.
4. Enviar **v** para conferir os dois lados. Se o centro esta correto mas um lado
   continua limitado, verificar interferencias mecanicas e medir os deslocamentos
   antes de alterar os limites. Centro eletrico nao garante simetria angular real.

O ajuste pelo monitor vale so ate reiniciar. Anotar o valor mostrado e coloca-lo
em `CENTRO_US` para usa-lo como centro inicial no proximo upload. A faixa de ajuste
fino do centro foi limitada a 1250-1750 us. O programa reduz a amplitude igualmente
nos dois lados quando necessario para manter todos os pulsos dentro de 1000-2000 us.

`ANGULO_MIN` e `ANGULO_MAX` definem os limites e `PULSOS_POR_PASSO` ajusta o
tempo em cada passo: aumentar esse valor deixa a varredura mais lenta.
`US_POR_45_GRAUS` define a correspondencia provisoria entre angulo e pulso.
Os 500 us por 45 graus nao foram calibrados: compare com um transferidor.
A faixa inicial cobre nominalmente 90 graus; nao chamar isso de cobertura
completa dos 180 graus da frente. Para ampliar, primeiro calibrar o servo e
conferir os limites mecanicos e o suporte. O lado fisico depende da montagem.
Nao testar os extremos mecanicos sem conferir deslocamento e interferencias.

Este teste movimenta apenas o servo: ainda nao mede distancias nem implementa
desvio de obstaculos. Envie **c** para interromper a varredura e manter o centro.
Desligar a alimentacao interrompe os pulsos; apos reset o teste volta ao centro inicial.

Se houver travamento mecanico, aquecimento, ruido continuo de esforco ou reinicio
do Arduino, desligar a alimentacao e investigar antes de repetir.

Enviar este teste substitui temporariamente o programa gravado no Uno; o controle
do carrinho nao funciona durante o teste. Para restaurar, enviar novamente
`arduino/robo_firmware/robo_firmware.ino` com suas configuracoes atuais e, se o
servico foi parado, iniciar na Raspberry: `sudo systemctl start robo.service`.

## Limites

Este sketch usa esperas para produzir os pulsos e nao deve ser incorporado ao
controle dos motores. A futura varredura integrada precisara de temporizacao
adequada para manter o atendimento dos comandos, sensores e watchdog.
Compilacao nao comprova movimento, alimentacao, amplitude ou funcionamento fisico.
