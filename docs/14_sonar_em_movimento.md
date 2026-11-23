# Sonar com um sensor e rodas em movimento — modo 4 experimental

## Comportamento atual: manual com varredura continua

Esta secao substitui o perfil de revisita descrito no historico abaixo.
A pedido explicito do usuario, `SONAR_MOV_CONTINUO=1` passou a ser o padrao
no Uno. A main continua solicitando V4 pelo Bluetooth; nao precisa de um
comando novo. E necessario **regravar o Uno**, alem de atualizar o Python.

- A sonda percorre60..120 graus continuamente em passos de1 grau/20 ms.
  Nao aguarda no centro, nao retorna por contagem de encoder e nao espera
  uma volta inteira para liberar um comando.
- Ao iniciar, aproveita a frente centrada valida ja medida enquanto estava
  parado, conservando sua idade e seu estado ocupado/livre. Sem leitura
  frontal valida, o comando manual continua permitido; isso nao comprova frente livre.
- Considera frontais os disparos no cone nominal80..100 graus. Nao exige
  estabilizacao parada para esses ecos; angulo nominal nao e feedback fisico.
  Laterais nao renovam a frente. Uma travessia frontal ocorre aproximadamente
  a cada1,2 s. Um sensor movel nao observa a frente continuamente.
- Dois ecos frontais reais abaixo de10 cm confirmam obstaculo e param avanco.
  Dois ecos a partir de15 cm liberam novamente. A Pi nao conta repeticoes de
  FC como ecos novos. O vermelho acompanha o bloqueio; amarelo segue apagado.
- A re curta automatica existente permanece na main: apos obstaculo frontal
  confirmado abaixo de10 cm, repouso0,15 s e re limitada a0,35 s ou2 pulsos,
  uma vez por comando. Soltar/parar cancela; liberar o botao rearma. Nao ha
  sensor traseiro nem desvio autonomo.
- Neste perfil manual foram retirados o desconto de odometria, os bloqueios
  por100 mm/divergencia20 mm, a reserva frontal de46 cm e a rampa que
  reduzia o alvo4 antes de chegar ao obstaculo. Mantido teto experimental de
  alvo4 pulsos/s, PI, watchdogs, parada manual e falta de pulsos dos encoders.
- No manual continuo, frente ausente ou vencida informa falha no diagnostico,
  mas nao cancela o comando. Um obstaculo confirmado permanece bloqueando
  ate dois ecos livres reais, mesmo se o eco desaparecer depois. A Pi continua
  parando por perda de comunicacao; falha de eco nao inicia re automatica.
  Sem eco, obstaculos novos podem deixar de ser detectados.

Isso implementa o controle manual solicitado, sem demonstrar frenagem no
piso ou ausencia de colisao. Os limiares e o cone ainda precisam de avaliacao
fisica; a cobertura intermitente do sensor permanece uma limitacao.
Validacao de software inclui marcha e varredura por10 s com E4/D6 pulsos/s,
sem cortes, planta assimetrica realimentada por PWM, obstaculo pelo ECHO
simulado, parada local, permissao de re, falha de eco e watchdogs. Ensaio
fisico desta revisao permanece pendente; primeiro teste com rodas suspensas.

Para compilar o perfil anterior de memoria/odometria, usar
`-DSONAR_MOV_CONTINUO=0`. Ele permanece separado para regressao, sem ser o
padrao solicitado na main. Os relatos e limites abaixo descrevem esse perfil
anterior; nao devem ser usados para interpretar o novo manual continuo.

## Historico do perfil anterior de revisita

Implementado em software e testado em simulacao. Nao ha validacao fisica do
movimento integrado, da frenagem ou da precisao angular. O modo 3 continua
sendo o sonar de diagnostico, com rodas bloqueadas. Este novo modo 4 nao
implementa contorno de obstaculos. Esta etapa e controle manual por Bluetooth;
CNN e seguimento autonomo ficam para depois. Curvas e re manuais sao permitidas
com o teto experimental e as condicoes descritas a seguir.

A indicacao amarela foi posteriormente desativada a pedido do usuario. O
firmware agora usa verde para frente liberada e vermelho para bloqueio/falha,
conforme o [guia de sinalizacao](10_sinalizacao.md). As mencoes abaixo a
revisoes do amarelo sao historicas. Retirar a indicacao nao altera as guardas
ou soluciona a perda de sustentacao do PI ainda pendente.

## Ativacao experimental solicitada pelo usuario

O modo foi ativado no codigo a pedido do usuario, antes da validacao no piso:
`SONAR_MOVIMENTO_ATIVO=True` na Pi e `SONAR_MOV_EXPERIMENTAL=1` no Uno.
`SONAR_MOV_CALIBRADO` continua em 0. A frenagem medida continua desconhecida;
o perfil experimental usa uma reserva inicial configurada de 100 mm, sem
apresenta-la como medicao. Demais limites: 4 pulsos/s, 100 mm de avanco maximo
sem renovar frente e 100 mm de margem. Pela geometria informada, o alvo de
4 pulsos/s equivale aproximadamente a 4,3 cm/s; velocidade real nao validada.

Para aplicar ao carrinho, regravar `arduino/robo_firmware/robo_firmware.ino`
no Uno e reiniciar `main.py`/servico. Nenhum upload foi feito pelo assistente.
O modo nao inicia deslocamento sozinho: precisa de um comando de avanco.
O Python exige confirmacao recente do modo 4 antes de enviar velocidade;
firmware antigo que ignore V4 nao recebe comandos R por esse caminho.
Pedidos mais altos sao limitados proporcionalmente ao teto por roda,
preservando sinais e proporcao da curva. A parada pode acontecer antes dos 25 cm:
a guarda preserva tambem reserva de frenagem, margem e quantizacao.

O bit3 do pacote FC continua informando ausencia de calibracao, enquanto o
novo bit4 indica a liberacao experimental. A ferramenta reconhece ambos;
um firmware apenas nao calibrado e sem perfil experimental continua bloqueado.
As secoes de calibracao abaixo permanecem como procedimento para substituir
o perfil inicial por parametros validados. Nao foram executados ensaios fisicos.

Na ativacao passaram 53 testes Python de controle, servo, sonar, decoder,
velocidade e calibracao. Os harnesses passaram com perfil experimental,
perfil desativado e calibracao sintetica. A compilacao Uno integrada usou
11138 bytes de flash e 199 de RAM; sem servo, 7558/122; camera legada,
5072/321. Ha teste especifico que impede enviar velocidade se o Arduino nao
confirmar o modo 4 ou se a confirmacao estiver vencida.

Na correcao de escopo para Bluetooth manual passaram 55 testes Python e os
harnesses nos perfis experimental, desativado e sintetico. Foram verificados
curva com sensor no centro, parada por leitura frontal vencida na curva,
re com frente sem eco, sinais dos motores, cancelamento e saida do contexto
manual sem ativar sonar no seguidor. A compilacao integrada para Uno usou
11458 bytes de flash e 200 de RAM. Isso nao valida Bluetooth ou movimento reais.

## Funcionamento

Revisao do alcance do eco: o codigo aceitava 2..400 cm, mas encerrava ECHO
alto em 14000 us (aproximadamente 241 cm). Assim, parede distante a 3 m
era classificada como leitura desconhecida, bloqueando avanco. Agora o
timeout de duracao e derivado de `ULTRASSOM_DIST_MAX_CM=400`: 24200 us,
incluindo 1000 us de folga. Nao muda a espera de subida do eco (6 ms), o
intervalo minimo de disparo (60 ms), a validade frontal (2 s) ou as margens.
Ausencia de eco e medida acima de 400 cm continuam invalidas/bloqueadas.
O teste de parede simulada de 3 m falhou antes da correcao e passou depois;
tambem passaram ecos a 240/400 cm e recusa a 410 cm, com e sem sonar.
Isso nao confirma o alcance fisico ou a causa unica do relato do usuario.
Para conferir recepcao, usar alvo plano aproximadamente a 80 cm, motores
desligados, e observar a distancia com `tools/testar_sonar_movimento.py --tempo 10`. Sem numero nessa condicao,
comparar sensor centralizado e sonar antes de atribuir o problema ao alcance.
Regravar Uno para aplicar; nenhum upload foi feito pelo assistente.

Revisao de indicacao e baixa velocidade: o LED amarelo permanecia ligado
durante qualquer sonar por ainda exigir centro parado. Agora usa a guarda:
frente liberada a partir de 60 cm e sem lateral bloqueada pode mostrar verde
durante a varredura. Amarelo tambem pode significar aproximacao ou lateral
ocupada, sem bloqueio total das rodas. A medicao do PI ate 8 pulsos/s ganhou
filtro de quantizacao; nao foram ampliadas margens nem prazos de seguranca.
No ensaio com frente constante de 80 cm e pulsos regulares a 4/s, o verde
passou de 0/399 a 399/399, PWM114..125 para121..123 e a guarda frontal teve
zero bloqueios. Esses resultados sao sinteticos, nao validacao do carrinho.
Harnesses experimental e calibrado sintetico passaram; testes de sinalizacao
e velocidade tambem passaram nessa revisao. Uno:11630 bytes flash/208 RAM.
Se houver bloqueio real, conferir a telemetria das ferramentas de teste; ausencia
de obstaculo visivel nao garante que o ultrassom esteja recebendo eco valido.

O servo repete `90 -> 120 -> 90 -> 60 -> 90` em passos de um grau/20 ms.
Na revisao de marcha continua, uma excursao lateral retorna antecipadamente
a90 se os encoders consumirem um terco do orcamento desde a ultima frente
valida (aproximadamente33,3 mm no perfil100 mm). Reserva o restante para
voltar, estabilizar e obter ecos; nao exige completar a lateral para andar.
Assim,60/120 sao alvos maximos, nem toda excursao alcanca o extremo. Esse
pedido de retorno nao renova memoria, nao libera rodas e nao muda a guarda.
Sem deslocamento, o percurso nominal permanece. Valores iniciais de software,
sem calibracao fisica da revisita ou frenagem.
Nos retornos a 90, aguarda 200 ms de estabilizacao e procura duas leituras
livres consecutivas. Se houver falha isolada, tenta novamente no centro,
limitando a quatro amostras por visita (`SONAR_MOV_AMOSTRAS_FRENTE_MAX`).
Obstaculo frontal ja confirmado tambem permite encerrar a visita, com rodas
bloqueadas para avanco. As rodas podem continuar andando durante a
varredura, inclusive em curvas e re, sob a memoria frontal limitada.
Frente proxima/sem eco bloqueia avanco, mas nao congela a varredura.
A partida exige duas leituras frontais livres; nao espera uma volta completa.
Durante um pedido manual mantido, os pacotes renovam o sonar sem reiniciar
essa validacao. Parar pelo aplicativo cancela o sonar e solicita centro;
novo pedido de movimento exige novamente frente valida. Os numeros sao parametros
iniciais: calibrar alinhamento, estabilizacao, revisita e deslocamento reais.

Depois de memoria frontal liberada, uma perda isolada de eco conserva somente
a ultima leitura valida dentro da validade de 2 s, orcamento de 100 mm,
desconto dos encoders e margens existentes. A perda nao renova nenhum desses
limites nem conta como leitura livre. Duas perdas frontais consecutivas
invalidam memoria e bloqueiam avanco; sem memoria previa, nenhuma perda libera
movimento. Recuperacao exige duas frentes livres consecutivas. Eco proximo
valido bloqueia imediatamente pela guarda; confirmacao para re continua com
duas leituras proximas. Laterais nao renovam memoria nem limpam falhas frontais.

Essa revisao trata o relato de alternancia numero/sem leitura ao girar servo.
Um ensaio com perda em uma de cada tres amostras frontais reproduziu as
interrupcoes antes da mudanca e passou depois. Tambem passaram falha dupla,
partida sem leitura, vencimento da memoria, limite de deslocamento e obstaculo
real. Harnesses experimental, calibrado sintetico e desativado passaram;
34 testes Python de sonar/servo/recuo passaram. Uno:11742 bytes flash/210 RAM.
Sem upload ou validacao fisica. Perdas frequentes continuam exigindo conferir
alimentacao, GND e encaixes; nao foram marcadas como resolvidas no hardware.

A leitura frontal e registrada com o instante e contadores de encoder no
disparo. Durante a observacao lateral, o firmware calcula:

```
espaco_restante = distancia_frontal - maior_deslocamento_das_rodas
reserva = 25 cm + frenagem_medida_ou_reserva_experimental + margem + um_pulso_de_quantizacao
```

O avanco e bloqueado se faltar um perfil valido (calibrado ou experimental), vencer a idade da leitura, exceder
o deslocamento permitido, houver divergencia excessiva entre rodas ou o
espaco restante nao superar a reserva. Leituras laterais nunca renovam o
tempo ou a distancia frontal; uma lateral abaixo de 25 cm bloqueia a curva
para esse lado, ate uma nova leitura valida do mesmo lado a partir de 30 cm.
Frente livre permite reta e curva para o outro lado. Ausencia de
eco nao libera uma direcao anteriormente bloqueada.

Comandos PI manuais de frente, curva, giro e re sao aceitos. Curvas/re nao
reiniciam a etapa do servo nem invalidam a frente a cada mudanca de comando.
A memoria frontal vale ate 2 s, limitada tambem a 100 mm de deslocamento e
reserva de parada; divergir rodas intencionalmente em curva nao e erro de
reta. Sem modelagem calibrada da rotacao do chassi, trata-se de perfil
experimental: nao valida precisao espacial em curvas. Pode haver parada se
vencer memoria, faltar eco ou se esgotarem as margens; nao se promete movimento
ininterrupto em qualquer cena ou velocidade. Um sensor mede uma direcao por vez.

A correspondencia inicial e 60 graus nominais = esquerda e 120 = direita,
configurada por `SONAR_MOV_ESQUERDA_MENOR_90` em `config.h`. Conferir no hardware
com rodas suspensas: alvo em cada lado deve bloquear apenas a curva para ele.
Se o suporte estiver invertido, alterar o macro para 0 e regravar. As flags
FC bits5/6 informam esquerda/direita; bit0 permanece referente a frente.
O PI usa a direcao dos alvos, nao diferencas do PWM de compensacao das rodas.

Re reta com ambas as rodas nao positivas pode recuar mesmo com frente bloqueada
ou sem eco, mantendo perfil valido, velocidade limitada, encoders e watchdogs.
Curvas em re tambem respeitam o bloqueio lateral correspondente.
**Nao ha sensor atras: a re manual nao tem protecao contra obstaculos traseiros.**
Se alguma roda avanca, continuam valendo as protecoes frontais. PWM direto
permanece recusado no modo 4. Encoders de um canal nao medem sentido real ou derrapagem:
isso limita a estimativa e nao transforma esta guarda em garantia de colisao
evitada. O limite de velocidade depende de encoders e PI funcionando.

Sem renovacao do comando V por 400 ms, o servo retorna ao centro, invalida a
memoria e as rodas param. O watchdog independente dos motores continua ativo.
Cancelar com centro para as rodas antes de sair do modo 4. Novas leituras
nao religam os motores sem novo comando de velocidade. A ferramenta pode
renovar uma solicitacao enquanto a guarda volta a obter dados validos.

## Re automatica curta no Bluetooth

`RECUO_MANUAL_ATIVO=True` em `config.py` habilita somente no controle MANUAL
com sonar em movimento e PI ativos. Durante um pedido de avanco (inclusive
curva com roda avancando), exige telemetria e confirmacao do modo 4 recentes,
leitura frontal valida, bloqueio e obstaculo confirmado abaixo de 25 cm.
Eco lateral isolado, ausencia de eco ou telemetria vencida nao iniciam re.
A guarda pode parar o avanco antes dos 25 cm; isso sozinho nao inicia recuo.

O controle para por 150 ms e solicita re a 4 pulsos/s por ate 350 ms.
Encerra antes se qualquer roda acumular dois pulsos desde a parada inicial,
os contadores regredirem, faltar comunicacao recente ou chegar parada.
Tempo e pulsos sao limites do comando; inercia e intervalos de amostragem
impedem tratar isso como distancia fisica garantida. Os valores sao iniciais
experimentais, nao calibracao de recuo ou frenagem.

Depois fica parado mesmo que o botao de avanco continue apertado ou a frente
fique livre. Soltar para neutro/enviar S ou dizer "pare" rearma; um novo pedido
de avanco pode iniciar outro recuo se ainda houver obstaculo confirmado.
Perda do prazo Bluetooth cancela e nao rearma sozinha. Pacotes repetidos de
avanco nao sobrescrevem a re automatica. Trocar a direcao cancela esse recuo;
re manual explicita permanece disponivel. O servo continua varrendo na re.

**Nao existe sensor traseiro: nem a re automatica nem a manual detectam
obstaculos atras.** Primeiro conferir com chassi apoiado e rodas suspensas,
usando o controle Bluetooth e um alvo frontal; conferir tambem S/pare e
perda de conexao. Nenhum ensaio fisico foi executado pelo assistente.
Esta alteracao e no Python: reiniciar `main.py`/servico. Requer o firmware
modo 4 ja descrito neste guia; nao foi alterado o firmware nesta adicao.
O recuo nao e ativado no seguidor/CNN nem pelas ferramentas isoladas de sonar.

Verificacao desta adicao: 12 testes simulados de recuo e 55 testes existentes
de controle, sonar, servo, serial, velocidade e calibracao passaram. Incluem
limites de tempo/pulsos, comunicacao vencida, contadores reiniciados, prioridade
de parada, timeout Bluetooth, ausencia de repeticao e encerramento da thread.
Nao houve mudanca no firmware, upload ou validacao fisica desta adicao.

## 1. Calibrar distancia por pulso, sem ligar os motores

Pare `main.py`, `robo.service`, testes e Monitor Serial. Mantenha a potencia
dos motores desligada; Arduino por USB, encoders ligados. Marque no chao
uma distancia reta que consiga medir e empurrar sem levantar as rodas.
Exemplo com **500 mm medidos**, nao uma distancia presumida:

```bash
.venv/bin/python tools/calibrar_encoders.py --distancia-mm 500 --saida calibracao_encoders_01.json
```

A ferramenta pede Enter no inicio, le os contadores, pede para empurrar e
le novamente depois de parar. Recusa zero pulsos em qualquer roda e reconexao
durante o ensaio. Nao envia comandos de movimento. Os encoders nao detectam
sentido: empurrar apenas para frente em linha reta, sem ir e voltar. Repita
com outro arquivo e compare os resultados; inconsistencias exigem revisar
fios, discos, contagens e a medicao antes de usar a media.

### Se nao puder colocar no chao

Com o chassi apoiado firmemente e rodas suspensas, mantenha a potencia dos
motores desligada e os encoders alimentados. Marque um ponto em cada pneu e
execute:

```bash
.venv/bin/python tools/calibrar_encoders.py --voltas 5
```

A ferramenta orienta a girar manualmente primeiro somente a esquerda por
cinco voltas completas, depois somente a direita por cinco voltas completas,
sempre no sentido de avanco. Mantenha a outra roda parada em cada etapa;
contagem cruzada causa erro para revisar montagem/fios antes de calibrar.
Sao registrados pulsos por volta para cada roda, sem inventar distancia.

Esquerda/direita sao vistas de quem esta atras do carrinho olhando para a
frente, nao de quem esta olhando de frente para ele. A ferramenta mostra
as variacoes dos dois canais em cada etapa: E/D2 e D/D3. Se somente o canal
oposto responder, conferir primeiro a roda fisica; se estiver correta,
investigar a correspondencia dos encoders. Se os dois canais responderem,
conferir movimento da outra roda, maus contatos e ruido. O programa aborta
nesses casos sem inverter pinagem ou aceitar uma calibracao contaminada.
Para diagnostico curto, pode usar `--voltas 1` e enviar as contagens exibidas;
depois repetir cinco voltas para conferir consistencia.

Se medir o diametro externo de cada pneu em mm, informe tambem
`--diametro-esq-mm` e `--diametro-dir-mm` com os valores medidos. A ferramenta
calcula uma **estimativa geometrica**: `mm/pulso = pi * diametro / pulsos_por_volta`.
Sem os diametros, nao produz mm/pulso. Repita a contagem para verificar
consistencia e confira depois por rolagem no piso com carga: deformacao do
pneu e escorregamento nao sao avaliados com rodas no ar. Esta alternativa
adianta a medicao dos encoders, mas **nao mede frenagem nem libera o modo 4**.

## 2. Parametros medidos do firmware

### Referencia ja aceita nesta sessao

O usuario encerrou os testes manuais e aceitou o ensaio de cinco voltas:
97 pulsos na esquerda e 96 na direita, sem contagem cruzada. Foram registrados
como referencias **provisorias** de 19,4 e 19,2 pulsos por volta em
`docs/calibracao/encoders_bancada.json` e nos macros
`ENCODER_PULSOS_POR_VOLTA_ESQ/DIR` do firmware. Nao sao uma validacao no piso.
Nao e necessario repetir os giros para continuar a preparacao do software.

O usuario informou 65 mm de diametro, 26 mm de largura do pneu e 20,42 cm
de circunferencia. Os diametros foram aplicados a ambas as rodas em
`RODA_DIAMETRO_ESQ_MM` e `RODA_DIAMETRO_DIR_MM`, no `config.h` do Uno.
Pi * 65 mm resulta em 204,2035 mm, consistente com a circunferencia informada.
A conversao geometrica automatica produz 10,52595 mm/pulso na esquerda e
10,63560 mm/pulso na direita. Essas estimativas usam as contagens provisorias
aceitas, sem arredondar para 20 pulsos/volta. A largura de 26 mm e do pneu e
nao substitui a largura total do chassi em um futuro planejador.

Diametros zero continuariam produzindo distancia por pulso zero e bloqueio.
Velocidade maxima, frenagem e orcamento de avanco tambem seguem sem valores
medidos. O perfil permanece nao calibrado, mas esta ativo como experimental.

| Parametro | Dado necessario |
|---|---|
| `SONAR_MOV_MM_PULSO_ESQ` / `DIR` | Calculados com diametros medidos e as referencias provisorias aceitas por roda |
| `SONAR_MOV_MAX_PPS` | Teto de pulsos/s que o PI consegue acompanhar na montagem |
| `SONAR_MOV_FRENAGEM_MM` | Maior deslocamento medido depois de solicitar parada nesse teto, com carga |
| `SONAR_MOV_AVANCO_MAX_MM` | Deslocamento maximo permitido sem renovar a leitura frontal |
| `SONAR_MOV_CALIBRADO` | Manter 0 ate preencher e verificar a calibracao completa |

Nao copiar os valores sinteticos de testes: nao correspondem ao carrinho.
Os parametros iniciais adicionais sao timeout frontal de 2000 ms, margem de
100 mm e divergencia maxima de 20 mm entre rodas. Tambem precisam ser
revisados com a montagem, resolucao dos encoders, carga e piso. O orcamento
de avanco precisa comportar a revisita frontal na velocidade escolhida sem
consumir a reserva de parada. Diminuir a velocidade se isso nao for possivel.

A ferramenta `tools/testar_velocidade.py` existente permite avaliar o PI
com rodas suspensas e sonar encerrado. Isso nao mede frenagem no piso.
Medir a parada em area desobstruida, com baixa velocidade e parada manual,
sem usar um obstaculo como metodo para parar o primeiro ensaio.

## 3. Conferir a varredura sem movimento

Regrave `arduino/robo_firmware/robo_firmware.ino` no Uno com `USAR_CAMERA=0`.
Com potencia dos motores desligada e um alvo frontal que produza ecos validos:

```bash
.venv/bin/python tools/testar_sonar_movimento.py --tempo 15
```

Por padrao nao solicita velocidade. No perfil atual mostra
`sem calibracao=True` e `experimental=True`; o bloqueio depende das leituras
e limites da guarda. Sem perfil valido fica bloqueado. Se a frente nao tiver
ecos validos, bloqueia as rodas e faz retries limitados antes de continuar
a varredura. Flags do protocolo confirmam
comandos, nao a posicao fisica do servo. A distancia FC exibida neste modo e
frontal descontada pelos encoders, nao o ultimo eco lateral.

### Diagnostico da interrupcao relatada em 16/11/2026

O log enviado pelo usuario confirmou modo 4 experimental, com frente em
145..148 cm e periodos de `bloqueado=False, falha=False`. Tambem registrou
uma frente sem leitura (`None`, bloqueio e falha ativos), ecos curtos em
angulos laterais e encerramento por falta de confirmacao recente. Isso
mostra uma interrupcao ainda pendente; nao identifica falha de alimentacao,
USB, sensor ou firmware como causa. Distancias fisicas nao foram conferidas.
Ecos laterais abaixo de 25 cm podem acender amarelo e bloquear uma curva,
mesmo enquanto a frente esta livre. O comando sem `--pps` nao solicita
movimento; encoders E/D zerados nesse ensaio nao demonstram falha dos motores.

A ferramenta agora mostra bloqueios laterais e idades de recepcao dos
pacotes servo/sensores. Ao encerrar, distingue pacote nunca recebido,
timestamp vencido/futuro, servo inativo e ausencia da flag de modo 4, e
informa o numero de tentativas de reconexao serial. A mensagem anterior
recomendava regravar mesmo depois de confirmar o modo; foi substituida por
esses dados. Tentativa de reconexao nao comprova reinicio do Uno. Os limites
de validade e a parada imediata foram mantidos. Esta mudanca e somente no
diagnostico Python e nao exige regravar o Uno.

Para obter o proximo log, encerrar os demais programas que usam a serial e,
com motores desligados e alvo frontal plano a aproximadamente 80 cm, repetir:

```bash
.venv/bin/python tools/testar_sonar_movimento.py --tempo 10
```

Enviar tambem a mensagem final caso o teste encerre. Nao aumentar os timeouts
ou liberar ausencia de eco para tentar contornar esta interrupcao.

O segundo log identificou `servo: modo 4 nao confirmado`, com zero tentativas
de reconexao serial. Isso significa que o status recebido estava sem a flag
do modo 4, nao que o eco frontal sozinho causou a excecao. No codigo atual,
comando de outro modo ou falta de renovacao V por mais de 400 ms encerram o
modo; reinicio da placa ou erro no pacote tambem precisam ser considerados.
Ausencia de reconexao na Pi nao exclui reinicio do Uno. O harness manteve V4
com S a cada 50 ms por 10 s simulados, sem perder o modo; 420 ms sem renovar
cancelaram como previsto. Isso nao reproduz o tempo real da UART no AVR.

Antes de repetir, com o teste encerrado e Uno conectado, conferir:

```bash
fuser -v /dev/ttyACM0
```

Se houver processos, identificar e encerrar o programa/servico correspondente
antes do ensaio. A porta deve ter somente um programa de controle. Nao matar
processos desconhecidos automaticamente. Saida vazia nao exclui falhas de
renovacao por outras causas; enviar a saida para orientar a proxima etapa.

### Recepcao serial com buffer no firmware sem camera

O usuario informou saida vazia do `fuser` apos encerrar o teste. Nao foi
identificado processo concorrente nesse momento. A investigacao encontrou
uma fragilidade na recepcao por polling: os bytes chegam a aproximadamente
cada 87 us, enquanto a guarda de sonar faz calculos float repetidos no AVR.
Uma pausa de 870 us imposta ao loop no modelo de RX limitado a dois bytes
reproduziu perda de comandos e impossibilidade de manter o modo 4. A duracao
real dos calculos no Uno nao foi medida; o teste nao confirma causa fisica.

O caminho `USAR_CAMERA=0` agora usa `Serial.begin(115200)` e o buffer RX de
64 bytes do core AVR Arduino por interrupcao. O loop consome esse buffer e
continua sendo o local de execucao do parser e dos comandos; a ISR recebe
somente bytes. TX continua direto nos registradores. Os timeouts dos motores
e servo, validade frontal, margens, limite de velocidade e guardas permanecem.
O caminho de camera legada conserva sua recepcao por polling.

No ensaio de rajadas, as tres verificacoes que falharam antes passaram:
S/V4 completos apos a pausa, renovacao por 10 s simulados e visitas a ambos
os lados. A falta de renovacao por 420 ms continuou encerrando o modo. Os
harnesses experimental, desativado, calibrado sintetico e sem servo passaram.
Isso verifica software, sem afirmar resolucao do bloqueio no carrinho.

**Esta revisao exige regravar o Uno**, diferente da melhoria anterior apenas
no diagnostico Python. Depois, com motores desligados, repetir o comando
de observacao por 10 s acima e verificar se termina sem perda do modo 4.
Ainda e necessario avaliar ecos invalidos e o funcionamento real das rodas.

No log posterior enviado pelo usuario, o sonar completou percursos nominais
ate 60 e 120 graus com status em 44..49 ms, sem excecao no trecho recebido.
Frente em 144..145 cm ficou liberada. A 44 cm passou a bloqueada sem falha,
e continuou assim a 34/29/24 cm. O limite atual nao e apenas 25 cm: soma
25 cm de obstaculo, 10 cm de reserva de frenagem experimental, 10 cm de
margem e aproximadamente 1,064 cm de quantizacao, totalizando 46,06 cm.
Com encoders parados e demais condicoes satisfeitas, leituras inteiras de
47 cm ou mais superam essa reserva; ainda sao necessarias duas leituras
livres consecutivas. O amarelo pode permanecer abaixo de 60 cm ou por
bloqueio lateral. Nenhum desses numeros e frenagem medida no piso.
O usuario confirmou ter aproximado a mao nesse ensaio. Esse ensaio sem
`--pps` nao valida giro de rodas nem resolucao do conjunto no hardware.

No ensaio posterior com `--pps 4 --tempo 5`, o usuario relatou rodas girando
em duas ou tres partidas, com pausas. O modo 4 permaneceu confirmado no
trecho recebido; a frente ainda distante ficou bloqueada sem falha. Entre
os primeiros resumos, E/D subiram de1/1 para21/22 em aproximadamente0,5 s:
40/42 pulsos/s estimados, acima do alvo4. Com a geometria provisoria, esses
pulsos correspondem a210,5/223,3 mm, acima do orcamento de100 mm entre
frentes validas. O retorno ao centro renova a frente e permite outra partida.
Isso e compativel com a guarda por deslocamento, nao com um simples bloqueio
causado pela cor do LED. Os contadores nao provam deslocamento no piso.

O limite configurado de4 pulsos/s e aplicado ao alvo do PI, nao e uma
velocidade real validada. Antes de modificar ganhos ou ampliar o orcamento,
encerrar os programas da serial e medir o PI separado, com rodas suspensas,
sonar encerrado e frente livre. O script abre a serial/reinicia o Uno e nao
inicia o modo4:

```bash
.venv/bin/python tools/testar_velocidade.py --pps 4 --tempo 5
```

Confirmar `s` somente com rodas suspensas. Enviar as linhas de alvo e taxas
E/D. O resultado permitira avaliar a resposta do PI sem o ciclo de parada e
reinicio da guarda por100 mm. Ainda falta distinguir regulagem de velocidade,
inercia sem carga e eventuais contagens incorretas de encoder.

O ensaio separado relatado depois confirmou pico de65,5/67,5 pulsos/s e
ultimas janelas em6..8 pulsos/s para alvo4, com sonar encerrado. A proxima
medicao e a resposta a PWM direto30 por3 s com rodas suspensas, usando
`tools/testar_velocidade.py --pwm 30 --tempo 3`. Veja o guia11 para escopo
e confirmacao. O PI e a guarda permanecem sem novos ajustes nesta etapa.

A etapa posterior usou partida80 e constatou sustentacao diferente por roda:
E em4..6 pulsos/s com PWM32, D sem pulsos em32 e em4..6 nas ultimas janelas
com PWM34. O firmware ganhou partida separada em baixa velocidade (reforco80
ate primeiro pulso, integral inicial E32/D34 e ganhos baixos0.25/0.5).
Ver [o procedimento e limites do PI revisado](11_controle_velocidade.md#pi-com-partida-separada-em-baixa-velocidade).
Requer regravar Uno e medir PI4 isolado com rodas suspensas antes de repetir
o ensaio de sonar. O modelo realimentado por PWM passou sem cortes da guarda
apos liberacao, mas ainda nao demonstra isso no carrinho. Orcamento100 mm,
margens e teto de alvo4 mantidos; nao marcar calibracao ou validacao no piso.

O ensaio fisico seguinte do PI4 perdeu pulsos e terminou com ambas as rodas
paradas. A sustentacao permanece pendente; nao repetir o sonar como se essa
revisao estivesse validada. A atualizacao seguinte acrescenta quadro F8 com
PWM e estado dos motores, preservando o controle anterior. A ferramenta PI
mostra bloqueio frontal, falha do sensor e falha de encoder, encerrando quando
o firmware confirma esta ultima. Regravar e obter esse diagnostico no teste
isolado descrito no guia11 antes de novos ajustes. Nenhum reforco automatico
durante a regulacao foi ativado nesta atualizacao.

Depois do relato de que a main girava as rodas por um instante e parava, a
investigacao de sustentacao foi retomada. Aplicados piso condicional do PI e
retorno frontal antecipado descritos acima/no guia11. O modo MANUAL4 mantem
rodas e varredura simultaneas: a posicao lateral do servo nao e por si so
motivo de parada. Em operacao normal, a guarda frontal decide o avanco com
risco de colisao. Parada manual, falhas, watchdogs e validade limitada dos
dados continuam protegidos; ausencia de eco nao autoriza avancar.
Na main, resumos `MANUAL` agora mostram motivo, guarda e diagnostico F8;
dados vencidos nao sao apresentados como confirmacao. Sem ativar CNN ou
desvio autonomo. O amarelo permanece desativado. Requer regravar o Uno;
validacao fisica desta revisao ainda pendente.

## 4. Ensaio integrado e ativacao explicita

### Pausas no log da main de 16/11, 14:49..14:50

O trecho confirmou modo4 e ausencia de falha de encoder, com alternancia da
guarda frontal. Ainda nao identifica se distancia, deslocamento ou divergencia
causaram cada corte. Com aproximadamente10,6 mm/pulso, a diferenca entre rodas
pode ultrapassar20 mm antes de esgotar100 mm de avanco. A frente pode continuar
distante nesse caso. Nao e bloqueio imposto pelo LED nem pela posicao lateral
do servo por si so.

O retorno antecipado agora considera tambem um terco do prazo frontal e um
terco da divergencia maxima em reta. Nao amplia limites nem renova a memoria
sem eco frontal. Simulacao com resposta assimetrica das rodas ainda reproduz
cortes por divergencia; essa mudanca nao comprova solucao do giro intermitente.

Regravar Uno e atualizar Python juntos. No proximo ensaio da main com rodas
suspensas, observar `guarda=...`, `frente_cm` e `angulo_nominal` nos resumos:

| Valor de `guarda` | Condicao no firmware |
|---|---|
| `livre` | Nenhuma condicao frontal de bloqueio nesse snapshot |
| `perfil_invalido` | Perfil de movimento ausente/invalido |
| `sem_frente` / `frente_vencida` | Memoria frontal ausente ou vencida |
| `confirmando_frente` | Ainda faltam leituras frontais livres consecutivas |
| `limite_avanco` | Deslocamento sem renovar frente atingiu o limite |
| `divergencia_rodas` | Diferenca entre rodas excedeu limite de reta |
| `distancia_reserva` | Distancia descontada atingiu reserva/margens |
| `indisponivel` | Sem F7 recente ou sem confirmacao recente de modo4 |

F7 e opcional: `FF F7 motivos`, sete bits na ordem acima (exceto livre e
indisponivel). Zero significa livre; varios bits podem coexistir. O firmware
o envia somente em modo4, junto do diagnostico de motores. Pacotes e decisao
de controle nao sao uma captura atomica; o motivo textual da decisao pode
preceder uma mudanca de estado exibida na mesma linha. A1 continua apagado.

Somente apos medir os campos, revisar os demais limites, marcar calibrado e
regravar o Uno: primeiro ensaio com rodas suspensas. Use `--pps` com valor
positivo **dentro do teto que voce mediu**, por exemplo, se 12 estiver dentro
dele:

```bash
.venv/bin/python tools/testar_sonar_movimento.py --pps 12 --tempo 5
```

Observe rodas e encoders enquanto o servo olha para os lados. Confira parada
por eco frontal invalido, alvo proximo, desconexao e Ctrl+C antes de ensaiar
no piso. Nao executar esta ferramenta junto de `main.py` ou outra serial.

No programa principal ha uma opcao separada em `config.py`:

```python
SONAR_MOVIMENTO_ATIVO = True
```

Foi ativada a pedido do usuario com `CONTROLE_VELOCIDADE_ATIVO=True` e perfil
experimental identificado no firmware. O controle renova o
modo 4 somente em MANUAL, mesmo enquanto espera leituras. A interface serial
envia o modo antes do comando de velocidade. Parada manual continua
prioritaria. Ao sair de MANUAL, a interface para, cancela o modo 4 e nao o
renova no seguidor. APRENDIZADO_ATIVO continua False. Isso ainda nao e
seguimento ou desvio autonomo validado.

Os pulsos/s solicitados pelo app sao limitados ao teto configurado pelo Uno.

## Protocolo e verificacao

`AA V 4 0 chk` inicia/renova o modo 4; aceita renovacao durante movimento,
mas so permite entrar a partir de motores parados. `FB` bit6 indica modo 4;
bit5 continua indicando sonar. `FC` bit3 indica calibracao ausente/invalida.
Tamanhos dos pacotes e modos anteriores sao preservados. Regravar firmware
e atualizar Python juntos. O bit de modo nao significa liberacao das rodas.

O harness usa configuracoes separadas: calibracao ausente e valores
**sinteticos** de mm/pulso/frenagem. Confere rodas ativas fora do centro,
revisita frontal, timeout, limite de avanco, divergencia, lateral incapaz de
renovar frente vencida, ausencia de eco, limite de velocidade, recusa de
PWM, varredura durante curvas/re, bloqueios direcionais e ausencia de cobertura
traseira, cancelamento e watchdogs. Os testes Python verificam protocolo,
integracao opcional, prioridade de parada, ausencia de movimento por padrao,
recusa de comando sem calibracao e validacao dos dados dos encoders.

Nesta implementacao passaram 43 testes Python dessas areas, os harnesses com
calibracao ausente, calibracao sintetica e sem servo. Compilacao para Uno:
padrao 10646/197 bytes de flash/RAM; configuracao sintetica 11072/199;
sem servo 7324/122; camera legada 5072/321. Nao houve upload ou teste fisico.

A suite adicional `tests/test_remoto.py` nao passou integralmente: nove casos
encontraram restricoes de sockets/D-Bus deste ambiente, e tres testes de
mistura/direcao esperam giro no lugar ou outra escala enquanto a implementacao
atual usa curvas para frente/zona morta. `remoto/comandos.py` e esses testes
foram conferidos por hash contra o commit base e nao foram modificados nesta
tarefa. Essas divergencias preexistentes nao foram corrigidas como parte do sonar;
a operacao completa via Bluetooth continua precisando de verificacao separada.
