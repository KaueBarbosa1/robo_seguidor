# 7. Controlar o carrinho pelo celular (Bluetooth, Android)

## Modo atual — ultrassom somente no autonomo, 24/11/2026

A pedido do usuario, `ULTRASSOM_BLUETOOTH_ATIVO=False` e o padrao. No
Bluetooth MANUAL nao ha disparos do HC-SR04, varredura, bloqueios por distancia,
eco ausente ou lateral, nem recuo automatico por obstaculo. O operador controla
frente/re/curvas. Parar pelo app/voz, prazo do Bluetooth, telemetria serial,
watchdogs e falha de encoder continuam interrompendo o movimento. O alvo PI
manual conserva o teto anterior de4 pulsos/s, na Pi e no Uno; nao e garantia
de velocidade fisica. Ganhos PI e polaridade das rodas nao mudaram.

O Uno precisa do firmware desta revisao, e a main precisa ser reiniciada.
Com o carrinho imobilizado, antes do upload na IDE:

```bash
systemctl --user stop robo.service
```

Grave `arduino/robo_firmware` como Arduino Uno na porta correta, feche o
Monitor Serial e depois execute:

```bash
systemctl --user start robo.service
```

Esses comandos de servico e o upload NAO foram executados nesta alteracao.
A simples mudanca de config.py nao remove a guarda local de um firmware antigo.
A main aguarda F8 confirmando o novo modo antes de pedir movimento; firmware
antigo fica em `aguardando_manual_sem_ultrassom`, sem cair num modo diferente.
A confirmacao inicial e aguardada sem exigir outro toque no app.

Na serial, `U,1,0` dentro do pacote existente de5 bytes inicia/renova o modo;
F8 bit6 confirma. `U,0,0` para e restaura o ultrassom. O modo exige renovacao
em menos de400 ms. U nao alimenta o watchdog dos motores: R/M continuam tendo
seu proprio prazo, e S continua parando imediatamente. Boot ou vencimento do
modo restaura protecao e zera motores. A ida para "siga" encerra o modo manual,
aguarda F8 novo confirmando saida e leituras frontais novas. Nenhuma distancia
anterior ao manual libera automaticamente o autonomo.

No seguimento autonomo OpenCV/PD ou CNN/RL, ultrassom, inspecao parada e
bloqueios por obstaculo/leitura invalida permanecem. O painel de camera nao
comanda esse modo nem altera motores. No manual, FC pode mostrar distancia
DESCONHECIDA/falha por medicao propositalmente pausada; F8 diferencia isso de
falha de encoder. LED verde no manual considera o modo sem sonar e ausencia
de falha de encoder; nao representa verificacao de caminho livre.

As secoes historicas abaixo sobre modo4/recuo descrevem o perfil anterior,
ainda disponivel em ferramentas de bancada e testes com ativacao explicita,
mas nao acionado pelo Bluetooth na configuracao atual. A persistencia fisica
do giro deve ser repetida com rodas suspensas apos upload; nao atribuir todas
as pausas ao ultrassom sem observar telemetria de encoder/comunicacao.


> **O que foi testado e o que não foi.** O código foi testado só em **simulação**: interpretador de comandos, modo manual do controle,
> sessões de celular e o servidor registrado num BlueZ **falso** (`python tests/test_remoto.py`). **Não foi testado** com o Bluetooth
> real da Pi, com o BlueZ real do Debian 13.7, nem com um celular, nem com o carrinho andando. A parte mais sujeita a surpresa é o
> pareamento e o app escolhido (o que cada app realmente envia).

## Como funciona
A Pi registra no BlueZ um serviço de **porta serial Bluetooth (SPP/RFCOMM)**. O celular **pareia** com a Pi, abre esse serviço
serial e manda comandos curtos. O programa principal (`python main.py`) sobe o servidor sozinho (`REMOTO_BT_ATIVO = True`) e pode subir no boot (seção 5).
O comando do celular entra no controle pelo **modo MANUAL**; a voz continua valendo ("pare" de voz corta tudo na hora).

O controle usa o aplicativo Bluetooth serial original. Nao depende de painel
web, navegador ou compartilhamento de internet por Bluetooth. Para retomar
apos remover a interface web, encerre qualquer processo antigo dela com
Ctrl+C e execute `.venv/bin/python main.py`. As ferramentas independentes
de camera/coleta continuam disponiveis em `tools/`.

No perfil anterior, as melhorias do ultrassonico eram: sonar durante marcha/curvas,
bloqueio da curva para lateral ocupada, memoria frontal limitada com retry,
recuo curto por obstaculo frontal confirmado e PI de baixa velocidade.
Parar pelo app cancela movimento e sonar. Veja o
[guia do sonar](14_sonar_em_movimento.md) para limites e validacao pendente.
O teto experimental permanece em 4 pulsos/s; nao foi elevado nesta remocao.

A revisao posterior de sustentacao mantem a marcha MANUAL durante a
varredura e antecipa a revisita frontal por deslocamento. Exige regravar Uno.
Com `REMOTO_DIAGNOSTICO_MOVIMENTO=True`, a main mostra linhas `MANUAL`
com pedido, frente, confirmacao do modo4 e PWM/falha de encoder lidos por F8.
`aguardando_modo4` indica falta de confirmacao recente; `falha_encoder_no_arduino`
indica flag recente de falha; `comando_expirado` indica prazo do aplicativo.
Os contadores sao acumulados, nao velocidade. Para investigar uma parada,
enviar essas linhas e os bytes Bluetooth RX correspondentes. O logger e
somente leitura. LED amarelo permanece apagado; protecoes continuam ativas.

Se foi criado o perfil NetworkManager `painel-celular` exclusivamente para a
interface web, ele pode ser removido na Raspberry com
`sudo nmcli connection delete painel-celular`. Isso remove o perfil PAN,
preservando o pareamento e o servico Bluetooth serial do aplicativo.

## 1. Preparar a Pi (uma vez)
```bash
sudo apt install -y bluez
sudo systemctl enable --now bluetooth
sudo usermod -aG bluetooth $USER          # depois faça logout/login
source venv/bin/activate && pip install dbus-fast
python tools/verificar_ambiente.py        # a seção "Bluetooth" deve ficar sem FALTA
```

## 2. Parear o celular (uma vez)
```bash
bluetoothctl
  power on
  system-alias "Robo"          # o nome que o celular vai ver (opcional)
  agent on
  default-agent
  pairable on
  discoverable on              # fica visível por alguns minutos
```
No celular: Configurações → Bluetooth → procure "Robo" (ou o nome da Pi) → parear. Confirme o código **nos dois** (na Pi, digite `yes`
no `bluetoothctl`; se a Pi tem área de trabalho, aparece uma janela). Depois, no `bluetoothctl`:
```
  trust AA:BB:CC:DD:EE:FF      # o endereço do celular que apareceu
  discoverable off
  quit
```
Se quiser que só o seu celular controle, ponha o endereço em `REMOTO_MACS_PERMITIDOS` no `config.py`.

## 3. Rodar e conectar
```bash
python main.py
```
Deve aparecer `Controle por Bluetooth pronto`. No celular, abra um app e conecte no dispositivo pareado "Robo":
quando conectar, o log da Pi mostra `Celular conectado: AA:BB:...`. No Android 12 ou mais novo, o app precisa da permissão
"Dispositivos próximos".

## 4. Apps e comandos
Qualquer app que fale **Bluetooth clássico serial (SPP)** serve. Três jeitos:

**Blue Dot (analógico, o mesmo app que a outra equipe usa).** O robô fala o protocolo do app **sem precisar da biblioteca `bluedot`**
(eu li o código da biblioteca 2.0.0, protocolo versão 2, para isso). Abra o app, escolha a Pi na lista de dispositivos pareados e conecte.
Pelo analógico: para cima = frente, para baixo = ré, para os lados = curvas para frente; diagonais combinam avanço e curva. Quanto mais longe do centro, mais rápido
(`REMOTO_VEL_MAX`, hoje 200 de PWM na borda). O centro (`REMOTO_BLUEDOT_ZONA_MORTA`, 15%) é parado. **Soltar o dedo para.**
Como o app só manda mensagem quando o dedo se mexe ou solta, o carrinho também **para se ficar `REMOTO_BLUEDOT_TIMEOUT_S` (2 s) sem nenhuma
mensagem** com o dedo apertado: é a proteção para a conexão que cai com o dedo na tela. Dedo parado por mais que isso: encoste de novo.
> **Não use o programa da biblioteca `bluedot` e o `main.py` ao mesmo tempo**: os dois querem o mesmo serviço serial. Escolha um.
> Se a outra equipe usa um script com `from bluedot import BlueDot`, ele é independente deste projeto; aqui o servidor já faz esse papel.
> Não testei com o app real; só com mensagens iguais às que a biblioteca lê.

**A) App de "carrinho RC"** (ex.: *Arduino Bluetooth RC Car*, controles com setas ou joystick): eles costumam mandar **uma letra
maiúscula** por toque. O programa entende o conjunto padrão desses apps (confira no app o que cada botão manda):

| Letra | Ação | Letra | Ação |
|---|---|---|---|
| F | frente | G / I | frente-esquerda / frente-direita |
| B | trás | H / J | trás-esquerda / trás-direita |
| L | curva para a esquerda (roda interna mais lenta) | S ou D | parar |
| R | curva para a direita (roda interna mais lenta) | 0 a 9 / q | velocidade 0% a 90% / 100% |

(W, w, U, u, V, v, X, x — luz e buzina desses apps — são aceitos e ignorados.)

**Robô Eletrogate.** A documentação da Eletrogate descreve linhas no formato `F<frente>T<trás>D<direita>E<esquerda>\n`, com intensidades de 0 a 255.
A captura real deste app também mostrou `F0T0D0E0` no centro e letras avulsas `F`, `T`, `E`, `D` durante o movimento. Após detectar o pacote estruturado,
essas letras são interpretadas como frente, trás, esquerda e direita do Eletrogate. Neste carrinho, a captura de uso mostrou `F` acionando a ré; por isso,
frente/ré são invertidas somente nesse modo detectado. Fora dele, `F/B/L/R/S/D` preservam os significados do protocolo RC. Pacote inválido/incompleto não atualiza o comando. Sem atualização válida
por `REMOTO_ELETROGATE_TIMEOUT_S` (0,4 s por padrão), o controle para; uma conexão ainda aberta não é tratada como desconectada.
Referência do formato e dos eixos: [apostila Eletrogate de Robótica Iniciante com App](https://pt.scribd.com/document/1013874744/Apostila-Eletrogate-Robotica-Iniciante-APP)
e [artigo Eletrogate sobre o app](https://blog.eletrogate.com/robo-controle-remoto-por-app/).

Para inspecionar exatamente o que seu aplicativo envia, defina temporariamente `REMOTO_LOG_BYTES = True` em `config.py`, inicie `python main.py`,
conecte o app e mova o joystick. O log exibirá cada bloco recebido em hexadecimal e ASCII legível (pontos representam bytes não imprimíveis).
Depois da captura, volte para `False`, pois o app gera atualizações frequentes.

**B) App de terminal serial** (ex.: *Serial Bluetooth Terminal*, com botões/macros): mande texto **minúsculo com Enter**:
`frente`, `tras`, `esquerda`, `direita`, `pare`, `vel 6` (0 a 10), `status`, `ajuda`. Esses comandos recebem resposta no terminal.

## 5. Ligar sozinho quando a Pi liga
O Bluetooth do robô sobe junto com o `main.py`. Para o `main.py` subir sozinho quando a Pi liga (como o servidor do Blue Dot da outra equipe):
```bash
bash deploy/instalar_servico.sh              # instala e ativa um serviço de usuário do systemd (pede sudo só para o "linger")
systemctl --user start robo.service           # liga agora, sem reiniciar
journalctl --user -u robo.service -f          # log ao vivo (procure "Controle por Bluetooth pronto")
systemctl --user stop robo.service            # antes de rodar python main.py à mão (senão os dois brigam pela serial)
bash deploy/instalar_servico.sh remover       # desinstala
```
O serviço **não foi executado** (nem o `systemctl` existe neste ambiente de teste). Ele reinicia sozinho se o programa cair, e o robô sempre começa
**parado**. O servidor Bluetooth tenta de novo a cada 5 s se o `bluetoothd` ainda não tiver subido no boot e tenta ligar o adaptador (`REMOTO_ADAPTADOR`).
O pareamento (passo 2) é feito **uma vez**; depois o celular reconecta sozinho.

## 6. Segurança (leia)
- **Anti-fuga:** o carrinho só se move enquanto chegam comandos: sem novo comando de movimento por `REMOTO_TIMEOUT_S` (1,5 s) ele **para**.
  App que repete a letra enquanto o botão está apertado: anda contínuo. App que manda só uma vez por toque: anda no máximo 1,5 s por toque
  (se precisar, aumente o valor com cuidado, de preferência em pequenos passos e com o carrinho no ar).
- Conexão Bluetooth cair ou o app fechar com o carrinho em movimento: **para**. Mesmo antes, o Arduino para os motores sozinho se a Pi parar de enviar por 400 ms.
- "pare" de voz e `S` do celular param na hora. Um comando de movimento do celular troca o modo (por exemplo, interrompe o "siga").
- A velocidade começa no nível 6 (`REMOTO_VEL_INICIAL`) e o nível 10 vale `REMOTO_VEL_MAX = 200` de PWM (não 255). **Esses números não foram medidos no seu
  carrinho**: teste primeiro **com as rodas no ar**, nível baixo, e depois no chão. Em PWM muito baixo o motor pode nem sair do lugar.
- Só celular **pareado** conecta (o BlueZ exige autenticação). Uma conexão por vez: a nova derruba a anterior.
- Mantenha um jeito físico de cortar a bateria dos motores.

## 7. Na semana sem a câmera
Pela planilha `Planilha_Conexoes_Carrinho_Robotico_1.xlsx`, o carrinho está (ou será) ligado **sem a câmera**, com HC-SR04, encoders e o L298N nos pinos do
**modo sem câmera** (`docs/00_motores_e_sensores.md`; LEDs e buzzer: veja `docs/10_sinalizacao.md`). Então:
1. Em `arduino/robo_firmware/config.h`, `#define USAR_CAMERA 0` (e `MODO_DIAGNOSTICO 0`), e grave no UNO.
2. Em `config.py`: `FIRMWARE_COM_CAMERA = False` (o baud vira 115200 e a Pi não espera imagem). `FONTE_IMAGEM` pode ficar como está.
3. Confira antes de ligar a bateria, **com as rodas no ar**, se cada roda gira no sentido certo. O IN3 está no **D13** e o IN4 no D12 (confirmado por você;
   a planilha tem uma contradição aí, e o firmware segue a montagem real). Roda direita só andando para um lado = IN3 ou IN4 no pino errado.
4. Nesse modo o ultrassom funciona: com algo a menos de 25 cm à frente (2 leituras seguidas), o controle remoto **não deixa andar para frente** (ré e giro continuam livres). O avanço só é liberado depois de 2 leituras a partir de 30 cm.
   Teste com `python tools/ler_sensores.py` antes de confiar (aproxime a mão do HC-SR04).
Se um dia o L298N estiver nos pinos do modo com câmera (D9, D10, D8, D12, D13, A0), use `USAR_CAMERA 1` e `FIRMWARE_COM_CAMERA = True` (`docs/01_ligacao_camera.md`).

## 8. Problemas comuns
| Sintoma | O que verificar |
|---|---|
| O log mostra `Bluetooth indisponível (...)` | `systemctl status bluetooth`; `bluetoothctl show` mostra `Powered: yes`?; usuário no grupo `bluetooth` (verificar_ambiente); `rfkill list` |
| Log mostra `DESLIGADO: falta dbus-fast` | `pip install dbus-fast` no venv do projeto |
| O celular pareia mas o app não conecta | rode `python main.py` antes (o serviço serial só existe com ele rodando); `trust` do celular; apague o pareamento nos dois lados e refaça |
| Conecta, mas nada se move | veja o log da Pi: aparece "Celular conectado"? O app manda letras maiúsculas? Teste `status` pelo app de terminal. Motor: `docs/00_motores_e_sensores.md` |
| Blue Dot: anda e para sozinho com o dedo parado | é o prazo de 2 s sem mensagem (`REMOTO_BLUEDOT_TIMEOUT_S`); mexa o dedo ou encoste de novo |
| Blue Dot não conecta mas o terminal serial conecta | feche qualquer script `bluedot` rodando; confira no log "App Blue Dot conectado" |
| Eletrogate conecta, mas não controla | selecione o modo **Robótica** no app; habilite `REMOTO_LOG_BYTES` e confira linhas no padrão `F...T...D...E...` terminadas em `0a` |
| Anda e para sozinho a cada toque | é o anti-fuga (`REMOTO_TIMEOUT_S`): o app não repete o comando |
| Giro e curva para o lado errado | troque os dois fios do motor no L298N (não mexa no código) |
| Uma roda só anda para um lado | IN1..IN4 no pino errado — veja a seção 7 (IN3 = D13, IN4 = D12) |
| Voz e celular juntos | a voz continua valendo; o headset Bluetooth usa o mesmo adaptador e **não foi testado junto** com o celular |
# Botoes de pressionar e soltar

Na montagem atual, Arduino Bluetooth Control envia F/B/L/R uma vez ao
pressionar e S ao soltar. `REMOTO_BOTOES_ATE_SOLTAR=True` mantem esses
comandos sem o prazo de 1,5 s, inclusive apos mudar velocidade. S, comando
de parada e desconexao encerram o movimento. Texto com Enter continua
usando `REMOTO_TIMEOUT_S`; Blue Dot e Eletrogate mantem seus prazos.
Se S se perder e a conexao continuar aberta, o movimento permanece;
o app deve enviar S ao soltar. Para voltar a exigir repeticao dos botoes,
defina `REMOTO_BOTOES_ATE_SOLTAR=False`.

