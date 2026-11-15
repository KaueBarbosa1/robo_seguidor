# 6. Revisão técnica (Pi 5 + Debian 13.7 + Arduino com a OV7670)

Atualizado em 21/10/2026, **depois da decisão de voltar definitivamente para a OV7670 no Arduino** (a Pi Camera Rev 1.3 / OV5647 no
CSI chegou a ser adotada e foi abandonada). Base: os arquivos reais do projeto. **Nada foi validado em hardware** (câmera, Arduino,
motores, microfone, pista). "Corrigido" quer dizer *código alterado e testado em simulação ou compilado*, não *funcionando no robô*.

## Legenda dos testes
- **EXECUTADO**: rodou de verdade neste ambiente (Ubuntu 24.04 x86_64, Python 3.13, sem hardware).
- **SIMULADO**: rodou contra um falso (Arduino virtual, pista sintética, motor falso). Prova a lógica do código, não o hardware.
- **COMPILADO**: o firmware passou pelo avr-gcc 7.3 (ATmega328P) com o core oficial do Arduino. Prova que compila e cabe; **não** prova que roda.
- **PENDENTE FÍSICO**: só dá para fazer no robô.

## 1. Estado atual
Voz → controle → motores via Arduino por serial; visão por OpenCV (`DetectorLinha`) sobre a imagem da OV7670 que o Arduino envia pela
serial (1 Mbaud, 160x120, 16 tons, ~2,5 quadros/s); aprendizado online da CNN (código + simulação). Pi⇄Arduino é USB, **provisório**.
Não existe nenhum treino da CNN com dados reais.

## 2. A volta para a OV7670: o que foi feito
- Firmware: o código da câmera (`ov7670.*`, `captura.h`, `diagnostico.*`) voltou para `arduino/robo_firmware/` (byte a byte igual ao
  que estava guardado); `.ino` e `config.h` restaurados com `USAR_CAMERA 1` como padrão (`#ifndef`, para o teste no PC poder usar `-DUSAR_CAMERA=0`);
  `sensores.cpp` voltou a ter o guard `USAR_SENSORES` (sem câmera) com funções vazias no modo câmera.
- Python: nova fonte `"arduino"` em `visao/fontes.py` (o `ArduinoSerial` já entrega os quadros); `main.py` a usa e cai para "sem imagem"
  com aviso em `--sem-arduino`; `config.py`: `FONTE_IMAGEM = "arduino"`, `SERIAL_BAUD = 1_000_000`, `KD_FILTRO = 1.0` (sem filtro: a 2,5 quadros/s
  o filtro só atrasaria o termo D). `tools/ver_camera.py` volta a mostrar a imagem do Arduino; `tools/verificar_ambiente.py` só cobra `picamera2` se a fonte for `csi`.
- Mantido por ser inofensivo: `visao/camera_csi.py` + `tests/test_camera.py` (opção `csi`, não usada) e a checagem de contraste do detector
  (ajuda contra falso positivo em piso liso). `docs/05_camera_csi.md` ficou com aviso de "não usada".
- Docs: `01_ligacao_camera.md` e `02_bringup_camera.md` voltaram para `docs/`; `00`, `04`, README e `requirements.txt` atualizados. `legado_ov7670/` foi removido (tudo voltou ao lugar).

## 3. Consequências de usar a OV7670 (limites reais, não testados no robô)
- ~2,5 quadros/s e 16 tons: o robô enxerga a pista a cada ~0,4 s. `VEL_BASE = 140` provavelmente é rápida demais: comece baixa.
- **Pontilhado:** o controle segura a última correção por até `PERDA_LINHA_TIMEOUT_S = 0,6 s` sem linha e depois **para**. Com 2,5 quadros/s isso
  são ~1,5 quadros: dois quadros seguidos sem nenhum traço visível já param o robô. Os vãos do pontilhado (e o cruzamento do 8, onde o detector só pega a maior mancha) são o ponto crítico do seguidor por PD. Não alterei esse valor sem medir.
- Com a câmera, **ultrassom e encoders ficam desligados** (pinos em conflito): sem parada por obstáculo (`OBSTACULO_ATIVO` fica sem efeito) e sem odometria; os giros de voz continuam por tempo (`TEMPO_GIRO_S`).
- Durante a leitura de cada linha da imagem (~0,6 ms) o Arduino não escuta a serial: comandos podem se perder (a Pi reenvia 20×/s e manda "pare" 3×).
- O firmware com câmera **nunca rodou numa OV7670 real**: o roteiro de diagnóstico (`docs/02`) existe para achar o problema pelo código de erro.

## 4. Problemas encontrados e corrigidos (nesta revisão toda)
- `sensores.cpp` podia sair compilado sem sensores → guard recolocado com stubs, testado no harness e compilado em 3 configurações.
- Detector marcava linha em chão liso com ruído → checagem de contraste.
- Derivada do PD: filtro criado para 30 fps; para a OV7670 fica desligado (`KD_FILTRO = 1.0`).
- `main.py` morria com traceback se a serial ou a câmera falhassem → mensagem clara, `--sem-arduino`, fallback.
- Aprendizado: A/B travando o nível, notas saturadas bloqueando promoção, rollback que nunca disparava → corrigidos e testados.
- Cobertura que não existia: decodificador da imagem serial (`tests/test_serial_imagem.py`), controle (`tests/test_controle.py`).

## 5. Funciona (código/simulação) × falta
**CNN:** CNN em NumPy do zero (55.090 parâmetros), gravação de episódios, reparo de rótulos, níveis de autonomia, supervisor independente da CNN,
A/B com bootstrap, promoção, rollback, versionamento com hash: **tudo só em simulação sintética**. **Parcial:** `robo_real.py` só com Arduino virtual e
fonte simulada. **Falta:** treino com dados reais; "saiu da pista" real (`sobre_pista()` devolve `None`); calibração na pista. A pista sintética não substitui o treino real.
**Voz:** `modelo_mistura.pkl` carrega e classifica (validado por você: 1670 áudios, 0 divergências); microfone/Bluetooth pendentes.

## 6. Decisões pendentes Pi⇄Arduino (não presumidas)
1. Enlace físico: USB (atual) ou UART dos GPIO (exige conversor de nível 5 V↔3,3 V; a imagem a 1 Mbaud tem de caber).
2. Quem controla L298N, sensores e câmera (hoje: o Arduino, com a OV7670 e os motores).
3. Protocolo: o atual (`0xAA…` / `0xFF…`) é herdado e provisório.
4. Pinos: os do modo com câmera vêm do seu esquema de ligação; confira na montagem real. Os do modo sem câmera vêm da planilha nova (seção 11.2).
5. Alimentação: Pi 5 em fonte própria 5 V/5 A, nunca pelo L298N; GND comum. Câmera em 3,3 V pelo regulador AMS1117 (conferir com multímetro).
6. Resistores de 10 kΩ nos IN1–IN4 para GND (motores não disparam no reset/watchdog).
7. Ultrassom/encoders: se forem necessários com a câmera, precisam de outros pinos ou de outra placa (decisão de arquitetura).
8. Sensor de chão (infravermelho) para "saiu da pista", `PERDA_LINHA_TIMEOUT_S`, ganhos PD e `APR_PERIODO_MIN_S`: só ajustáveis com o robô.
Risco elétrico: GPIO da Pi é 3,3 V e **não tolera 5 V**; qualquer sinal de 5 V (HC-SR04, encoders, UART do UNO) para a Pi precisa de conversão de nível. A câmera OV7670 é 3,3 V; só o XCLK e o I2C precisam de cuidado no lado do UNO (divisor e pull-ups em 3,3 V).

## 7. Debian 13.7: dependências
`README.md` e `python tools/verificar_ambiente.py`. Resumo: `python3-venv libportaudio2`; venv com `--system-site-packages` (PEP 668); Python 3.13;
scikit-learn **1.8.0**; grupos `dialout,audio,video`. **Não** precisa de `picamera2` nem `rpicam-apps`. Wheels aarch64/cp313 de numpy/scipy/scikit-learn/opencv existem no PyPI
(só a existência foi conferida, não a instalação na Pi). Arduino IDE no PC (ou na Pi) para gravar o firmware.

## 8. Testes e resultados
| Teste | Tipo | Resultado |
|---|---|---|
| `compileall` + `pyflakes` em todo o projeto | EXECUTADO | sem erros nem avisos |
| imports de `main` e `controle` | EXECUTADO | OK |
| `tests/test_aprendizado.py` | SIMULADO | 32/32 |
| `tests/test_serial_imagem.py` (decodificador + simulador de Arduino + detector) | SIMULADO | 7/7 |
| `tests/test_controle.py` (motor falso) | SIMULADO | 8/8 |
| `tests/test_integracao_robo.py` (Arduino virtual, aprendizado ativo) | SIMULADO | INTEGRACAO_OK, 99 comandos de motor |
| `tests/test_camera.py` (picamera2 falsa; opção CSI não usada) | SIMULADO | 6/6 |
| `tests/test_remoto.py` (interpretador, protocolo Blue Dot, modo MANUAL, sessões em socketpair, servidor em BlueZ FALSO num dbus-daemon privado) | SIMULADO | 20/20 |
| Firmware com câmera (USAR_CAMERA 1), avr-gcc 7.3, core Arduino AVR | COMPILADO | OK: 6.686 B de flash (20,4 %), 515 B de RAM (25,1 %) |
| Firmware modo bancada (USAR_CAMERA 0) e modo diagnóstico (MODO_DIAGNOSTICO 1) | COMPILADO | OK: 5.020 B / 350 B e 10.838 B / 755 B |
| Lógica do firmware de bancada no PC (`arduino/teste_host`, g++) | SIMULADO | TUDO_OK (não cobre a câmera) |
| `main.py` com Arduino simulado (porta virtual, 1 Mbaud nominal), 8 s | EXECUTADO | sobe, conecta, carrega a voz, encerra limpo; sem microfone aqui |
| `main.py --sem-arduino` | EXECUTADO | sobe com aviso "sem imagem da OV7670" |
| `tools/verificar_ambiente.py` | EXECUTADO | 9 OK, 4 avisos, 1 falta, todos esperados neste ambiente |
Limites: compilar não prova o tempo real da captura (`lerLinha` depende de ciclos do AVR, ~640 µs/linha) nem o I2C/XCLK. A porta virtual ignora o baud: 1 Mbaud real USB só se confirma na Pi com o UNO.

## 9. Testes físicos pendentes (ordem sugerida)
1. Ligar a OV7670 (`docs/01`), firmware com `MODO_DIAGNOSTICO 1`, ler as etapas no Monitor Serial a 115200 (`docs/02`, passo A).
2. Firmware normal (`MODO_DIAGNOSTICO 0`), `python tools/ver_camera.py --salvar foto.png`: imagem, foco, `CAM_Y_FASE`, `CAM_CLKRC`, taxa de quadros e linhas perdidas.
3. `python tools/testar_microfone.py` e voz com o headset.
4. Motores com rodas no ar (`tools/testar_motores.py`), sentido, parada por watchdog e por "pare".
5. Seguir linha com PD na pista (velocidade baixa), medir vãos do pontilhado e ajustar `PERDA_LINHA_TIMEOUT_S`, `ROI_INICIO`, ganhos; ver o cruzamento do 8.
6. Só depois: `APRENDIZADO_ATIVO=True` supervisionado, coleta real, avaliar se aprende.

## 10. Prontidão
Código Python e testes de software: prontos para receber hardware. Firmware: compila para o UNO nas 3 configurações; **nunca rodou**. Câmera OV7670: **não validada**
e é a parte mais arriscada (ligação 3,3 V/5 V, XCLK, I2C, temporização). Robô: **não validado**. Aprendizado em dados reais: **inexistente**. Antes de qualquer ligação
elétrica, feche as decisões do item 6.

## 11. Controle remoto pelo celular (adicionado em 27/10/2026; detalhes em `docs/07_controle_bluetooth.md`)
- Escolha: Android, Bluetooth clássico serial (SPP/RFCOMM). O servidor (`remoto/bluetooth_spp.py`) registra um perfil no BlueZ pelo D-Bus
  (`dbus-fast`); o celular pareado abre o serviço serial e manda comandos (`remoto/comandos.py`): letras de apps de carrinho RC (F, B, L, R, G, I, H, J, S, 0-9, q) ou texto com Enter.
- Controle: novo modo `MANUAL` (`estado.py`, `controle.py`): anda só enquanto chegam comandos (`REMOTO_TIMEOUT_S = 1,5 s`), para ao desconectar andando,
  "pare" de voz e `S` do celular cortam na hora; obstáculo (se houver sensor) só barra a frente. A thread é opcional: falhar não derruba o robô.
- **Não testado:** BlueZ real, Bluetooth real da Pi, celular, app, pareamento, e o carrinho se movendo por esse caminho. Velocidades (nível 6 = 120 de PWM; teto 200) são suposições.
- Pendente de decisão: qual mapa de pinos do L298N está montado na semana sem câmera (define `USAR_CAMERA 1` sem a câmera ou `0`, e o baud).
- Voz e celular ao mesmo tempo, com o headset no mesmo adaptador Bluetooth: não testado.

### 11.1 App Blue Dot e início automático (27/10/2026)
- O servidor também fala o protocolo do app **Blue Dot** (analógico): linhas `op,col,row,x,y` (0 soltar, 1 apertar, 2 mover) e `3,versão,nome`, lidas do código da
  biblioteca `bluedot` 2.0.0 (protocolo 2). Responde ao `3,...` com a configuração `4,...` como a biblioteca. Mistura diferencial do analógico em PWM, curvas laterais e diagonais, zona morta de 15%, e parada
  se ficar 2 s sem mensagem com o dedo apertado (`REMOTO_BLUEDOT_TIMEOUT_S`), porque o app só avisa quando o dedo se mexe ou solta. **Não testado com o app real.**
- A biblioteca `bluedot` **não** é usada (nem pode rodar junto: mesmo serviço serial).
- Início automático: `deploy/robo.service` + `deploy/instalar_servico.sh` (serviço de usuário do systemd, `enable-linger`). **Não executado**: sem systemd neste ambiente (`systemd-analyze verify` não roda aqui).
- O servidor tenta ligar o adaptador (`Powered`) ao subir: testado só contra um adaptador falso.

### 11.2 Planilha de conexões nova (31/10/2026)
- `Planilha_Conexoes_Carrinho_Robotico_1.xlsx` (proposta, não confirma os fios): ENA D5, ENB D6, IN1 D7, IN2 D8, IN3 D11 na planilha (na montagem real: D13), IN4 D12, HC-SR04 TRIG D9/ECHO D10,
  encoders D2/D3; LEDs (A0, A1) e buzzer (D4) **não ligados e não usados** (o firmware nunca teve código para eles). O modo `USAR_CAMERA 0` do firmware passou a usar esse mapa
  (antes era o da planilha antiga). Compilado para AVR e testado no harness do PC (que agora usa os macros de pino); **nada disso foi verificado nos fios do carrinho**.
- A planilha **não inclui a OV7670**: os pinos dela (D2..D7, D11, A4, A5) conflitam com este mapa, por isso o modo com câmera tem outro mapa (`docs/01`).
- **Contradição na planilha:** IN3 = D11 ("Mapa de pinos", "Testes e checklist") × D13 ("L298N e motores"). **Resolvida pelo usuário: IN3 = D13, IN4 = D12**; o firmware usa isso.
- **Conflito de arquitetura:** a planilha prevê, para o uso final, o Arduino alimentado pelo XL4015 no pino 5V com a USB desconectada; mas a ligação atual com a Pi é a própria USB
  (dados e energia). Os dois juntos são desaconselhados pela própria planilha. Decisão pendente: ligação final Pi⇄Arduino (USB × UART com conversor de nível) e como alimentar cada placa. A Pi 5 precisa de fonte própria de 5 V/5 A.
- Motores de tensão desconhecida (TT: 3–6 V) com bateria 2S (8,4 V): manter PWM baixo; `VEL_BASE = 140` e `REMOTO_VEL_MAX = 200` são suposições.
- Novo botão de configuração: `FIRMWARE_COM_CAMERA` em `config.py` liga o baud (1 Mbaud/115200) ao firmware gravado e evita esperar imagem que não vem.
