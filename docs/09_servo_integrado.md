# Servo SG90 integrado ao firmware principal

O teste isolado foi incorporado como um modulo proprio (`servo.h`/`servo.cpp`)
em `arduino/robo_firmware`, mantendo a organizacao existente. Nao foi copiada a
rotina bloqueante de `arduino/teste_servo`. O controle Bluetooth/Python principal
e o treinamento da CNN nao foram alterados para iniciar varreduras.

## Funcionamento desta etapa

- No boot, o servo fica centralizado. A varredura nao inicia automaticamente.
- O sinal continua em **D9**, ultrassom TRIG/ECHO em **D4/D11**, motores e encoders
  permanecem nos pinos existentes.
- Timer1/OC1A gera os pulsos em hardware, a aproximadamente 50 Hz. O loop continua
  atendendo UART, sensores, encoders e watchdog; nao usa `delay` para o servo.
- A varredura nominal e de **45 a 135 graus**, em passos de um grau a cada 20 ms.
  Nao e uma garantia de 180 graus de cobertura ou de angulo fisico calibrado.
- Esta primeira integracao permite varrer apenas com saidas de motor zeradas.
  Durante a varredura, comandos de movimento, inclusive re, ficam bloqueados.
- A distancia frontal e invalidada durante a varredura e o retorno ao centro;
  nenhum eco lateral e aproveitado como autorizacao para avancar.
- Apos retornar ao centro, aguarda 200 ms de estabilizacao e novas medicoes
  frontais. A liberacao continua exigindo as leituras/configuracoes existentes.
- O watchdog dos motores continua em 400 ms e o watchdog de hardware em 250 ms.
  A varredura tem tambem renovacao de comando: sem comando de servo por mais
  de 400 ms, o servo retorna ao centro. Esse retorno nao reutiliza leitura antiga.

**Ainda nao implementado:** mapa do ambiente, desvio autonomo e
varredura com o carrinho andando. Isso exige associar distancia, direcao e tempo,
medir latencia e definir a politica de seguranca antes de liberar movimento.
O ultrassom continua exercendo a funcao de protecao frontal quando o servo esta
centralizado. O modo continuo `varrer` descarta os ecos; o novo modo `inspecionar`
registra tres direcoes, como descrito a seguir.

## Aproximacao e inspecao de obstaculo — primeira etapa

Implementado, ainda sem validacao fisica integrada:

1. Arduino reduz proporcionalmente os dois PWM quando a frente fica abaixo de
   60 cm. Preserva a proporcao da curva. O fator vai de 100% do comando a 60 cm
   ate 40% a 25 cm; isso nao corresponde a uma velocidade medida em cm/s.
2. A barreira anterior permanece: duas leituras abaixo de 25 cm bloqueiam
   avanco; duas a partir de 30 cm liberam. Falha de sensor continua bloqueando.
3. Com novas leituras, a protecao pode reduzir uma saida ativa sem esperar a Pi.
   Nao aumenta PWM nem retoma movimento sem novo comando. Re nao recebe essa
   reducao frontal; todos os movimentos sao bloqueados durante a inspecao.
4. Somente no modo SEGUINDO, com obstaculo confirmado e telemetria frontal
   recente e valida, a Pi para e aguarda 0,4 s antes de iniciar a inspecao.
   Esse repouso e temporal: nao comprova que a inercia cessou.
5. O servo percorre 45, 90 e 135 graus nominais, com movimentos graduais.
   Aguarda 200 ms apos chegar a cada alvo e coleta tres ecos separados.
   Guarda a menor distancia somente se os tres forem validos; qualquer falha
   deixa aquela direcao DESCONHECIDA. Sem eco nunca significa passagem livre.
6. Volta ao centro e permanece com os motores bloqueados ate o comando de
   encerramento. A Pi registra os resultados e muda para PARADO. Mesmo com a
   frente livre ou uma nova previsao da CNN, nao retoma sozinha.
7. Sem conclusao em 8 s, a Pi cancela e fica PARADO. Sem renovacao do comando
   por 400 ms, o Arduino abandona a inspecao e recentraliza. Nenhum desses
   caminhos envia movimento. O watchdog dos motores continua independente.

No controle MANUAL ha reducao de PWM e parada frontal, mas nao se inicia
inspecao ou desvio automaticamente. Comandos manuais e `pare` interrompem a
inspecao e solicitam centro; o Arduino aguarda estabilizacao antes de mover.
Para retomar a autonomia apos uma inspecao e necessario um novo `siga`, e as
regras existentes de imagem/acao recente e obstaculo continuam valendo.

**Calibracao pendente:** 60 cm, 40%, repouso de 0,4 s e estabilizacao de 200 ms
sao parametros iniciais, nao distancias/tempos de frenagem medidos. A parada de
25 cm e a histerese de 30 cm foram preservadas do projeto. Validar em baixa
velocidade antes de usar no chao. Nao alterar pinagem. Os extremos 45/135 nao
recebem nomes esquerda/direita ate conferir a orientacao real do suporte.

Arquivos: `motores.cpp` aplica reducao e protecao; `servo.cpp`/`sensores.cpp`
fazem a inspecao sem bloqueio do loop; `protocolo.h`/`.ino` enviam resultados;
`motor/protocolo.py`/`serial_com.py` decodificam; `controle.py` supervisiona.
Parametros de PWM ficam no `config.h` do Arduino; habilitacao, repouso e timeout
ficam em `config.py` (`INSPECAO_OBSTACULO_*` e `INSPECAO_REPOUSO_S`/`INSPECAO_TIMEOUT_S`).
Nenhuma mudanca em pesos, treinamento, entradas ou saidas da CNN.

## Configuracao

Em `arduino/robo_firmware/config.h`:

```cpp
#define USAR_CAMERA 0
#define SERVO_CENTRO_US 1500
```

`USAR_SERVO` e habilitado por padrao apenas no modo sem a OV7670. Ele pode ser
desabilitado com `#define USAR_SERVO 0` antes do `#ifndef USAR_SERVO`.
O servo e incompativel com o mapa legado USAR_CAMERA=1; essa combinacao e recusada.

Se o centro foi ajustado pelo Monitor Serial do teste isolado, esse valor estava
so na RAM e nao pode ser recuperado do sketch. Copiar o valor que voce conferiu
para `SERVO_CENTRO_US` antes de gravar o principal; nao inventar compensacao.
O valor inicial mantido aqui e 1500 us, como no arquivo de teste atual.

Os pulsos ficam dentro de 1000-2000 us. O ajuste fino permitido do centro e
1250-1750 us. A amplitude e reduzida igualmente nos dois lados quando necessario
para permanecer na faixa. Simetria de pulsos nao comprova simetria mecanica.

## Enviar — Arduino IDE no Windows ou Raspberry Pi

1. Manter a potencia dos motores desligada no primeiro teste integrado.
2. Confirmar alimentacao externa do servo e GND comum, como no teste isolado;
   a fonte exata nao foi documentada nesta conversa. Nao mudar os fios de motores/sensores.
3. Se o Arduino estiver conectado a Pi com o servico ativo, parar no terminal
   da **Raspberry Pi**: `sudo systemctl stop robo.service`.
4. Na **Arduino IDE**, abrir `arduino/robo_firmware/robo_firmware.ino`, selecionar
   **Arduino Uno**, escolher a porta e enviar. Nao abrir o sketch `teste_servo`.
5. Fechar o Monitor Serial antes de usar a porta pela Raspberry.

## Testar — terminal da Raspberry Pi com a .venv

```bash
cd /home/carrasco/Downloads/robo_seguidor
.venv/bin/python tools/testar_servo.py --modo varrer --tempo 10
```

O script envia apenas comandos de parada dos motores e do servo, confirma o
estado retornado pelo firmware e mostra o angulo **comandado**, nao medido.
Ao terminar ou receber Ctrl+C, solicita retorno ao centro e fecha a porta.
Se o programa/conexao morrer antes disso, o timeout do servo deve recentralizar.
Sem resposta recente, o script informa erro em vez de anunciar sucesso.

Para testar as tres medicoes sem camera, CNN ou movimento dos motores:

```bash
.venv/bin/python tools/testar_servo.py --modo inspecionar --tempo 10
```

Esperado: tres resultados de posicao nominal (45/90/135) e retorno ao centro.
Uma distancia DESCONHECIDA pode representar falha ou ausencia de eco; nao e
caminho livre. Colocar um alvo em frente a cada direcao e comparar com uma regua.
Conferir qual extremo e esquerdo/direito e se o suporte estabiliza antes do eco.
A ferramenta so confirma a resposta do firmware, nao a exatidao fisica.

Depois dessa verificacao, com rodas suspensas e controle manual em baixa
potencia, aproximar um alvo de frente: abaixo de 60 cm o PWM deve diminuir;
abaixo de 25 cm, apos confirmacao, as rodas devem parar. Retirar o alvo e repetir
cada lado. Nao iniciar teste no chao antes de validar a parada e a alimentacao.
A inspecao automatica pertence ao modo SEGUINDO, nao ao controle MANUAL.
Sem camera, a protecao frontal e o teste `inspecionar` funcionam sem a CNN;
o seguimento real de linha continua dependendo de imagens validas.

Para manter o centro e conferir alinhamento:

```bash
.venv/bin/python tools/testar_servo.py --modo centro --tempo 10
```

Para ajuste fino temporario, exemplo **+20 us relativos ao centro do firmware**:

```bash
.venv/bin/python tools/testar_servo.py --modo centro --ajuste-us 20 --tempo 10
```

O sentido fisico do ajuste depende da montagem. O valor nao e salvo em EEPROM.
Para torna-lo padrao, alterar SERVO_CENTRO_US para o centro real conferido e
gravar novamente o firmware. Deixar `--ajuste-us 0` ao usar esse novo padrao.

No firmware principal a serial e **binaria a 115200**. Os comandos de texto
`c`, `v`, `+`, `-` pertencem somente ao teste isolado e nao sao interpretados aqui.
Nao executar o script e `main.py`/robo.service/Monitor Serial simultaneamente
na mesma porta.

Depois de encerrar o teste e confirmar o retorno ao centro, retomar o servico
no terminal da Raspberry: `sudo systemctl start robo.service`.

## Protocolo e compatibilidade

Os comandos antigos M/S e o tamanho dos pacotes de sensores permanecem.
O pacote FC acrescenta o bit2 de flags: obstaculo confirmado por leituras reais
consecutivas. Isso evita iniciar inspecao por bloqueio de boot ou falha. Os bits
anteriores continuam iguais. Firmware antigo sem esse bit nao inicia a nova
inspecao automatica; atualizar firmware e Python juntos.
O comando opcional V usa o mesmo pacote de cinco bytes e checksum:
`AA V modo ajuste chk`, modo 0 centro / 1 varrer / 2 inspecionar; ajuste assinado em passos de 10 us.
So e aceito com saidas de motor zeradas. Renovar V antes de 400 ms durante varredura.

A resposta nova usa `FF FB` e cinco bytes de 7 bits: angulo L/H, centro_us L/H,
flags (bit0 varrendo, bit1 tempo de centro cumprido, bit2 modulo habilitado).
Bit3 indica inspecao; bit4 indica conclusao com retorno ao centro estabilizado.
O pacote `FF FA pos cmL cmH rodadaL rodadaH` tem cinco bytes de 7 bits: posicao
0/1/2 corresponde a 45/90/135 graus; distancia 0x3FFF significa desconhecida.
A rodada permite agrupar os tres resultados; cada amostra recebe timestamp na
Pi. Amostras anteriores ao inicio da inspecao nao sao aceitas como conclusao.
A resposta FB e enviada em resposta a comandos V aceitos e ao retorno por timeout;
nao acrescenta mensagens de texto nem modifica o fluxo dos comandos antigos.
O decoder Python foi estendido com callback opcional para essa resposta.

## Verificacao e limites

Compilacao confirmada para Arduino Uno nos modos integrado, sem servo e camera
legada. A versao integrada desta etapa usa 5368 bytes de flash e 97 bytes de RAM
global; sem servo, 3644/63; camera legada, 5056/321.
Os testes de host passaram com servo habilitado e desabilitado, incluindo UART
simulada com tempo de transmissao. Durante a espera da UART, o firmware continua
amostrando o ultrassom e aplicando a protecao dos motores.

Compilacao para Uno e testes no computador nao comprovam o pulso eletrico,
consumo, movimento ou seguranca fisica do conjunto. O usuario validou movimentos
do teste isolado, mas a integracao precisa de teste fisico separado.

Os testes de host exercitam Timer1 configurado, limites, comando aceito/recusado,
checksum, watchdog, bloqueio dos motores em varredura, invalidacao de distancia
frontal, retorno ao centro, offset negativo e novas leituras para liberar avanco.
Os testes Python conferem protocolo, fragmentacao, ressincronizacao, callbacks,
compatibilidade e encerramento seguro da ferramenta com Arduino falso.
Nesta etapa passaram 11 testes de servo/protocolo/ferramenta, 11 de controle,
7 de decoder offline e 3 de controle manual remoto (32 verificacoes Python).
Nao foi executado teste com porta serial, Bluetooth ou motores reais.

O harness antigo esperava TRIG/ECHO D9/D10 e nao compilava com os pinos atuais.
Foi corrigido para usar os macros do config.h ativo. A pinagem do hardware nao mudou.
