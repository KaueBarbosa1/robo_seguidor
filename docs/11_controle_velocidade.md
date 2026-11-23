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
- `VELOCIDADE_KP`, `VELOCIDADE_KI`: ganhos PI iniciais de 1 para pedidos acima de8 pulsos/s.
- Ate8 pulsos/s: `VELOCIDADE_KP_BAIXA=0.25`, `VELOCIDADE_KI_BAIXA=0.5`;
  ajustes iniciais verificados em simulacao, ainda pendentes no PI fisico.
- `VELOCIDADE_PWM_MAX`: teto inicial de 180, nao garante tensao adequada ao motor.
- `VELOCIDADE_PWM_PARTIDA`: integral inicial de120 para pedidos acima de8
  pulsos/s, baseada no teste PWM que moveu ambas as rodas. Renovar
  comandos nao reinicia a integral; o PI continua ajustando para cima e para
  baixo, sem impor PWM minimo permanente. Validar em bancada antes de ativar.
- Ate8 pulsos/s, `VELOCIDADE_PWM_PARTIDA_BAIXA=80` reforca cada roda somente
  ate seu primeiro pulso. A integral comeca em32 para E e34 para D
  (`VELOCIDADE_PWM_BASE_BAIXA_ESQ/DIR`), sem carregar o reforco na integral.
  Esses valores sao referencias em avanco com rodas suspensas; validar carga/re.
- Na revisao de sustentacao abaixo, pedidos de avanco entre4 e8 pulsos/s
  ganham piso condicional32/34, com anti-windup; menores, zero e re nao o usam.
- `VELOCIDADE_MAX_PPS`: limite de 120 pulsos/s.
- `VELOCIDADE_FILTRO_BAIXA_PPS=8` e `VELOCIDADE_FILTRO_TAU_MS=400`: até
  8 pulsos/s, suavizam a medição usada pelo PI. Em 4 pulsos/s, contar em
  janelas de 100 ms alternava entre 0 e 10 pulsos/s. A média exponencial reduz
  essa oscilação; alvos maiores continuam com medição direta. O filtro é
  zerado em parada, partida e inversão. Parâmetros iniciais, não calibração.
- `VELOCIDADE_SEM_PULSO_MS`: 1000 ms sem pulsos com alvo diferente de zero
  para as duas rodas e trava o modo de velocidade ate receber parada S.

Comece com alvo baixo, mas suficiente para produzir pulsos. Resolucao baixa ou
alvo muito baixo podem causar falsa deteccao de roda travada. Oscilacao exige
reduzir os ganhos; erro persistente exige ajuste gradual. Nao aumentar os
limites sem observar os motores. Protecoes de obstaculo, servo e watchdog
permanecem prioritarias. No PI, a aproximacao reduz somente os alvos em
pulsos/s; o regulador calcula o PWM necessario para acompanha-los, respeitando
o teto configurado. No comando PWM direto, a aproximacao reduz o PWM.

### Correcao da reducao duplicada no amarelo

Na revisao de baixa velocidade do sonar, com frente simulada constante de
80 cm e pulsos regulares a 4/s, o PWM oscilava de 114 a 125 por quantizacao.
Com filtro de medicao, passou a 121..123 no mesmo ensaio. Nao foi imposto
PWM minimo permanente. Contadores brutos continuam governando deslocamento,
falha por falta de pulsos e paradas; watchdogs nao foram ampliados. Foi
verificado corte por encoder sem pulsos tambem no alvo de 4/s. Melhoria de
suavidade no hardware ainda depende de conferir alimentacao, atrito e ganhos.
Os testes abaixo registram a correcao anterior de reducao duplicada.

Foi reproduzida uma falha de software com leitura valida de 32 cm e servo
centralizado: o PI reduzia o alvo de velocidade e depois atenuava novamente
o PWM. Com alvo de 28 pulsos/s, o PWM inicial caiu para 67, abaixo dos 120
usados como referencia de partida. Numa planta sintetica com esse limiar de
atrito, as rodas nao partiam e o timeout de encoder interrompia o comando.
Isso pode explicar a parada relatada com amarelo, mas nao identifica sozinho
a causa fisica do carrinho.

A correcao aplica a aproximacao uma unica vez aos alvos do PI. A funcao de
seguranca tambem deixa de atenuar sua saida novamente. O alvo e atualizado no
ciclo de 100 ms; a parada por obstaculo continua aplicada imediatamente pelo
loop quando as leituras confirmam o bloqueio. Mantidos watchdog, limite de
PWM, falha de encoder e bloqueio durante sonar/inspecao. Nao foi imposto um
PWM minimo permanente: reduzir o alvo nao dispensa calibracao em baixa
velocidade, da resolucao dos encoders e do atrito real.

O harness compara a partida livre e a reduzida, simula os pulsos com atrito
e confere a parada por obstaculo. Regravar o firmware para testar no hardware,
com rodas suspensas, sonar encerrado e servo centralizado. Confirmar leituras
validas entre 30 e 60 cm e comparar pulsos/segundo; o LED amarelo sozinho
tambem pode indicar falha do ultrassom ou servo indisponivel, com bloqueio.

Verificacao desta correcao: o caso de 32 cm falhou antes da mudanca (PWM
inicial 67/67 e parada na planta sintetica); depois passou com 135/135,
alvo reduzido, pulsos e parada por obstaculo preservada. Os harnesses com/sem
servo passaram, assim como 21 testes Python de controle, decoder e protocolo
de velocidade. Compilacao Uno integrada: 9470 bytes de flash e 167 de RAM.
Nao houve upload nem teste de movimento fisico nesta investigacao.

Com integral inicial zero, um alvo de 28 pulsos/s produzia cerca de PWM 31
na primeira amostra e podia nao vencer o atrito antes do corte de 1 segundo.
O ajuste de partida nao comprova funcionamento dos encoders: com a potencia
desligada, gire cada roda e confira contagens independentes em D2/D3 usando
`python tools/ler_sensores.py`. Depois grave o firmware atualizado e teste
`python tools/testar_velocidade.py --pps 28 --tempo 5` com rodas suspensas.
A ferramenta aponta rodas sem pulsos; uma roda girando com contagem zero
exige revisar o sensor e sua ligacao. Mantenha o controle automatico desativado
ate ambas registrarem pulsos e acompanharem o alvo sem cortes.

## Diagnostico de excesso de velocidade em 4 pulsos/s

No ensaio relatado em 16/11/2026, com rodas suspensas e sonar encerrado,
o pedido de4 pulsos/s produziu E/D=28,9/28,9;65,5/67,5;48/48;21,9/21,9;
9,9/7,9;7,9/7,9;8/10;8/6;7,9/6 pulsos/s. Isso confirma taxas pelos encoders
acima do alvo, sem depender da varredura do sonar. O codigo inicializa a
integral em PWM120 a cada partida e a reduz gradualmente; paradas da guarda
reinicializam esse valor. O excesso de pulsos pode esgotar o orcamento de
100 mm do modo4 antes da proxima frente valida. A resposta medida nao permite
escolher um PWM inicial menor nem novos ganhos com seguranca sem medir a
relacao entre PWM e pulsos; tambem nao valida velocidade/frenagem no piso.

Para medir um ponto dessa relacao, a ferramenta ganhou `--pwm`, exclusivo de
`--pps`. Esse modo envia PWM explicito, independente de
`CONTROLE_VELOCIDADE_ATIVO`, sem editar `config.py`. Aceita valores pares de
0 a120 (resolucao de2 do protocolo), exige a confirmacao de rodas suspensas,
renova o comando e para/fecha a serial ao encerrar ou perder telemetria.
Nao altera o firmware, os ganhos ou a referencia inicial automaticamente.

Com rodas suspensas, frente livre e demais programas da serial encerrados:

```bash
.venv/bin/python tools/testar_velocidade.py --pwm 30 --tempo 3
```

Confirmar `s` e enviar as linhas `PWM direto 30 | E ... | D ...`, informando
se ambas as rodas partiram. Ausencia de movimento nesse PWM e um resultado
util; nao aumentar potencia/ganhos automaticamente. O modo4 recusa PWM
direto; a ferramenta abre a serial e usa o estado de boot centralizado. A
API explicita `ArduinoSerial.pwm` tambem recusa o contexto sonar manual ou
status de modo4. Nenhum ajuste do PI foi aplicado nesta etapa.

Os resultados enviados depois foram zero pulsos em E/D com PWM30 e PWM40,
e PWM60 com taxas E/D de13,9/11,9;34,4/34,4;44/42;45,6/43,6;45,7/45,7;
48/48 pulsos/s. Isso ainda nao mede o PWM necessario para manter uma roda
ja girando. Para distinguir sustentacao de partida, foi acrescentada a opcao:

```bash
.venv/bin/python tools/testar_velocidade.py --pwm 40 --pwm-partida 60 --tempo 3
```

Com rodas suspensas e frente livre, confirmar `s`. A ferramenta aplica60 a
cada roda ate receber o primeiro pulso do encoder daquela roda, entao reduz
somente ela para40. A outra pode continuar em60 ate seu primeiro pulso. O
prazo total para ambas partirem e1 s; sem resposta, encerra e para, sem
repetir a partida. Depois mede a sustentacao em40 por3 s. Imprimir primeiro
pulso comprova recepcao de contagem, nao verifica visualmente o giro.
O corte depende da chegada da telemetria (incluindo sua latencia), e nao e
uma interrupcao fisica instantanea no pulso. Ctrl+C, frente bloqueada durante
a partida, perda de telemetria, reconexao e regressao de contadores abortam.

`--pwm-partida` exige `--pwm` positivo, deve ser par, maior que a sustentacao
e no maximo120. Essa opcao e exclusiva do ensaio, nao muda o PI do firmware
ou suas protecoes. Enviar taxas em40 e informar se as rodas mantiveram o giro
depois da reducao. Testes simulados de prazo/independencia/falhas/encerramento
passaram; sustentacao fisica ainda pendente. Usa o firmware atual.

## PI com partida separada em baixa velocidade

Os ensaios enviados depois distinguiram as duas necessidades. Com reforco60,
somente D partiu em1 s; o usuario confirmou E parada. Reforco80 fez ambas
registrarem pulsos. Depois, PWM40 sustentou aproximadamente16 pulsos/s.
PWM32 sustentou E em4..6 pulsos/s, enquanto D deixou de registrar pulsos.
PWM34 terminou com E em6..8 e D em4..6 pulsos/s. Os resultados estao em
`docs/calibracao/pi_baixa_bancada.json`; sao referencias provisorias, nao
calibracao de velocidade/frenagem no piso.

O firmware agora separa o reforco da integral para pedidos nao nulos ate8
pulsos/s: aplica80 somente ate cada roda produzir seu primeiro pulso. O
loop detecta essa contagem e retira o reforco daquela roda antes da proxima
janela de100 ms, usando a base32/34. Na primeira revisao, essas bases eram
somente valores iniciais. A revisao de sustentacao abaixo acrescenta piso
condicional em avanco na faixa ensaiada. Ganhos baixos
iniciais0.25/0.5 reduzem a retirada excessiva de torque apos o transitorio;
foram escolhidos/verificados em software, nao medidos no carrinho. Alvos
maiores conservam a inicializacao anterior. As referencias tambem sao usadas
em pedidos baixos de re, cujo comportamento fisico continua sem calibracao.

Renovar R nao reinicia o reforco nem a integral. Zero, inversao, parada S e
mudanca de faixa sao tratados explicitamente. Uma roda sem pulsos por1 s
para ambas e trava a falha ate S. Watchdogs, guardas frontais/laterais e
orcamento de100 mm continuam prioritarios; velocidade real nao e garantida
somente pelo alvo4. Treino/CNN e desvio autonomo nao foram ativados.

O harness confere reforco independente, reducao no primeiro pulso, renovacao,
zero/re, falha de encoder e watchdog. Uma planta sintetica com atrito de
partida e inercia gera pulsos a partir do PWM aplicado: no primeiro segundo
de PI4, a revisao anterior gerou65/64 pulsos; a nova gerou8/8. Nos dois
segundos finais, a nova gerou8/8. O mesmo modelo com sonar ativo teve7/7 no
primeiro segundo e8/8 na cauda, sem cortes da guarda apos liberar a frente.
Isso e resultado de simulacao, nao validacao da resposta fisica nem previsao
exata do motor real. Harnesses com/sem servo e perfis alternativos passaram.

**Regravar o Uno para aplicar esta revisao.** Primeiro, com rodas suspensas,
frente livre e outros programas da serial encerrados, medir o PI atualizado:

```bash
.venv/bin/python tools/testar_velocidade.py --pps 4 --tempo 5
```

Enviar as taxas e o comportamento das rodas. Somente depois conferir o modo4
com as mesmas condicoes. Nenhum upload foi feito pelo assistente.

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

A falha de encoder pode ser consultada por `motores_falha_encoder()` e, na
revisao de diagnostico, pelo pacote serial F8 descrito abaixo.
A leitura da ferramenta exibe magnitude, inclusive durante re.
Para converter em RPM: RPM = pulsos/s * 60 / pulsos por volta da roda.

## Perda de sustentacao na primeira revisao e diagnostico F8

O ensaio fisico posterior do PI4 retornou E/D=6/7,9;6/8;3,6/3,6;2/0 e,
depois, ambas em0. A revisao anterior melhorou a arrancada, mas nao sustentou
o giro. O log antigo nao continha PWM aplicado nem a falha de encoder;
portanto, a causa efetiva do corte no hardware ainda nao foi confirmada.

Um caso adicional de simulacao aumenta em1 o limiar de atrito por roda e
reproduz perda de giro seguida de falha latente do encoder. Ele verifica a
parada protetiva e sua exportacao, nao uma correcao da sustentacao. O caso
nominal continua passando. Testar apenas o caso nominal nao valida o motor.
Uma tentativa de reforco durante a regulacao foi descartada por provocar
cortes na guarda integrada; nao foi mantida no firmware.

Esta revisao acrescenta somente diagnostico, mantendo PI, ganhos, prazos e
protecoes da versao que foi testada pelo usuario. No firmware sem camera,
F8 e enviado junto da telemetria a cada50 ms:

```text
FF F8 eL eH dL dH flags
```

Magnitudes de PWM logico aplicado: E=eL|(eH<<7), D=dL|(dH<<7). Bits0/1
indicam sinal negativo E/D; bit2 indica falha de encoder; bit3 PI ativo;
bits4/5 fase de reforco pendente/ativa E/D. Todos os bytes do corpo usam7
bits. FC, FB e os comandos anteriores permanecem compativeis. O quadro F8
e informativo: nao renova watchdog e nao aciona motores.

`ArduinoSerial.estado_motores()` publica esses dados com instante de recepcao.
`tools/testar_velocidade.py` agora mostra PWM, PI, reforco, bloqueio frontal e
falha de sensor. No ensaio PI, uma flag recente de falha de encoder encerra
o teste e solicita parada; nao repete o movimento. Firmware sem F8 ou dado
vencido mostra diagnostico indisponivel, sem inventar a causa. As flags
indicam o estado do software, nao comprovam defeito eletrico no encoder.

Regravar o Uno e, com rodas suspensas, frente livre e demais programas da
serial encerrados, repetir `--pps 4 --tempo 5`. Enviar a saida completa,
incluindo a mensagem final. Sustentacao, integracao no carrinho e piso
continuam pendentes; nao foram ativadas tentativas extras de partida.

## Sustentacao do PI e diagnostico na main

O log F8 posterior mostrou frente liberada e sensor sem falha, com PWM
E31/D33 e depois E30/D32. E deixou de contar pulsos, e o firmware confirmou
falha de encoder. O corte por ausencia de pulsos foi confirmado; o conjunto
dos ensaios e compativel com perda de torque ao reduzir abaixo da sustentacao,
sem comprovar defeito eletrico do encoder.

Agora o PI aplica piso condicional E32/D34 somente quando o alvo efetivo e
de avanco entre4 e8 pulsos/s e a medicao filtrada nao supera duas vezes o
alvo. Se a saida saturar nesse piso, congela a integracao que a reduziria
ainda mais. Nao eleva a integral para compensar o transitorio de partida.
Com excesso de velocidade, o PI pode novamente reduzir abaixo da base.
Zero, pedidos menores que4, re e guardas nao recebem esse piso. Alvos maiores
conservam o perfil anterior. Isso nao garante velocidade fisica maxima4.

Nao ha repeticao automatica do reforco80 para tentar rearmar uma falha. A
falta de pulsos por1 s continua parando ambas as rodas e exigindo S. As
protecoes frontais, laterais e watchdogs continuam prioritarias. No modo4,
o servo antecipa o retorno frontal ao consumir um terco do orcamento de
deslocamento; o limite100 mm permanece. Ver guia14.

`REMOTO_DIAGNOSTICO_MOVIMENTO=True` acrescenta resumos `MANUAL` na main a
cada1 s ou quando o motivo/flags mudam, e registra a saida desse modo. Mostra
pedido da interface, bloqueio frontal, falha do sensor, confirmacao de modo4,
PWM/F8, falha do encoder e contadores. Sao snapshots de recepcao; os pedidos
da interface nao sao PWM aplicado quando o PI esta ativo. Dados vencidos,
ausentes ou futuros aparecem como indisponiveis. O logger nao altera pedidos
nem envia comandos. Desativar essa flag so desativa os resumos.

Na planta sintetica nominal e com atrito extra, a revisao manteve pulsos
na cauda de2 s e nao esgotou a guarda durante a varredura; antes, o caso
de atrito extra terminava parado. Os testes tambem conferem piso desligado
por excesso de velocidade, zero/re, alvo menor, falta de encoder e watchdog.
O resultado fisico da nova revisao permanece pendente. As duas cores de LED
permanecem conforme guia10, com amarelo desligado. Regravar Uno e reiniciar
a main antes do ensaio MANUAL com rodas suspensas.
