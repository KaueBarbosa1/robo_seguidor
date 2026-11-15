# ESP32-CAM OV2640: teste de bancada

Esta etapa usa somente ESP32-CAM e um receptor separado. Não altera main.py,
robo.service, configuração da câmera existente, Uno ou CNN. Validação física pendente.

## Gravar na Raspberry Pi

1. Carrinho parado, alimentação dos motores desligada. Pare o serviço para impedir
   comandos ao Uno: `systemctl --user stop robo.service` (se instalado como serviço
   de sistema, use `sudo systemctl stop robo.service`). Não execute main.py.
2. Desconecte os jumpers de **5 V e GND dos bornes** da ESP32-CAM antes de ligar
   o micro-USB da base programadora. Nesta bancada, mantenha a câmera alimentada
   só pelo USB; não combine as duas fontes. O Uno pode continuar no seu USB.
3. Identifique a porta por comparação: execute `ls -l /dev/serial/by-id/` e
   `ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null`, retire **somente o USB da base da
   ESP32-CAM**, repita e reconecte. A porta que desaparece e reaparece é a base.
   Uno e base podem usar conversores semelhantes: não deduza pela numeração nem
   apenas pelo nome CH340/CP210x. A porta pode mudar ao reconectar.
4. Na Arduino IDE instale **esp32 by Espressif Systems** pelo Gerenciador de Placas
   (índice adicional, se necessário:
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`).
   Use core 3.x e abra `arduino/esp32_cam_bancada/esp32_cam_bancada.ino`.
   Selecione **AI Thinker ESP32-CAM** e a porta identificada em Ferramentas > Porta.
   Use PSRAM habilitada se houver essa opção. Altere `PASSWORD` (8–63 caracteres).
   A pinagem já está selecionada por `CAMERA_MODEL_AI_THINKER`.
5. Grave. Se a base não entrar automaticamente em gravação, mantenha IO0 em GND
   e pressione RESET antes da gravação; depois remova IO0–GND e pressione RESET
   para executar. Use os botões equivalentes da sua base, se disponíveis.
   Abra Monitor Serial em **115200 baud**; pressione RESET e confira a rede
   `Carrinho-CAM` e `http://192.168.4.1/capture`. Erros de PSRAM/câmera/Wi-Fi/HTTP
   aparecem no monitor. Falta de permissão na porta requer acesso ao grupo dialout
   e nova sessão de login. Feche outros monitores que estejam usando essa porta.

## Receber e exibir

Com internet ainda disponível, instale OpenCV **com interface gráfica** e NumPy:

```bash
sudo apt update
sudo apt install python3-opencv python3-numpy
```

O requirements.txt geral usa opencv-python-headless, que não abre janela. Para este
script use `/usr/bin/python3` com os pacotes apt acima, fora do venv existente.
Use desktop local ou VNC com sessão gráfica; SSH sem display não exibe a janela.

Na Pi, conecte pelo menu Wi-Fi à rede **Carrinho-CAM** com a senha do sketch.
Ou consulte `nmcli device status` e use (substitua wlan0 se necessário):

```bash
nmcli device wifi connect Carrinho-CAM password 'Carrinho123' ifname wlan0
ip -4 addr show wlan0
/usr/bin/python3 tools/testar_esp32_cam.py --csv esp32_cam_bancada.csv
```

Espere endereço 192.168.4.x/24 na Pi. A ESP é 192.168.4.1 e fornece DHCP;
nenhum roteador ou internet é necessário. Aceite permanecer na rede sem internet.
A troca de Wi-Fi pode derrubar SSH/VNC: prefira monitor local ou Ethernet para
acesso remoto. Use a senha alterada no comando. `q` ou Ctrl+C encerra o teste.

Cada quadro usa um GET /capture, sem requisições paralelas. Timeout padrão 3 s;
em falhas HTTP, desconexão ou JPEG inválido há registro e nova tentativa após 1 s.
A janela fica preta durante falhas para não apresentar uma imagem antiga como atual.
O CSV é sobrescrito ao iniciar: escolha outro nome para preservar ensaios.

## Coletar imagens com a câmera montada

Conecte a Pi à rede `Carrinho-CAM`. Com os motores desligados, ajuste
foco, inclinação e orientação da câmera olhando a prévia.

```bash
/usr/bin/python3 tools/coletar_esp32_cam.py --previa --roi 0 80 320 160
```

A janela mostra o quadro orientado com o retângulo da ROI e, ao lado, o
recorte em cinza reduzido a 80×40 e ampliado para inspeção. `--roi X Y L A`
usa pixels do quadro após a orientação, com origem no canto superior
esquerdo. O recorte deve caber no quadro e ter proporção 2:1. `0 80 320 160`
é um ponto de partida. Mude os valores até conseguir ver a fita perto e
longe na prévia. Use `--espelhar-h` para inverter esquerda e direita e
`--espelhar-v` para inverter cima e baixo. Repita as mesmas opções na coleta.

```bash
/usr/bin/python3 tools/coletar_esp32_cam.py \
  --saida coletas_esp32/curvas_luz_natural_01 --roi 0 80 320 160 \
  --duracao 30 --nota 'Câmera montada, luz natural, curvas e vãos'
```

Use uma pasta nova por sessão. `q`, fechar a janela ou `Ctrl+C` encerra a
captura. `--quadros N` limita a quantidade de JPEGs válidos e `--duracao S`
limita o tempo para iniciar novas capturas. Por SSH, acrescente
`--sem-janela`. A pausa padrão após um quadro válido é 0,2 s. Ajuste com
`--intervalo` para variar a frequência de amostragem. Falhas de rede ou de
JPEG são registradas e a captura é retomada quando a câmera responde.

- `quadros/` guarda os JPEGs originais de 320×240, byte a byte. Orientação e
  recorte aparecem na prévia e no manifesto.
- `capturas.csv` registra cada tentativa, com sequência, arquivo e horário
  UTC de recepção para os quadros válidos. Inclui tempos HTTP, duração
  monotônica desde o início e as estimativas de idade da bancada.
- `sessao.json` registra o identificador único da sessão, início e fim,
  nota da montagem, versão da prévia, ROI, orientação e contadores.

Guarde a pasta inteira. Separe sessões completas na avaliação. O formato
da coleta preserva a origem de cada JPEG para a futura rotulação. Os
experimentos anteriores continuam usando seus respectivos formatos de entrada.

## Métricas e aceitação

- `HTTP`: tempo monotônico desde antes do GET até terminar de receber o corpo;
  inclui ida, espera de captura e transferência, exclui decodificação/exibição.
  Em falhas, o tempo é até a exceção. O timeout limita operações de socket,
  não é um prazo absoluto para toda a transferência.
- `idade_envio`: diferença no relógio da ESP entre início da captura (timestamp
  do driver) e preparação da resposta. Dois buffers com CAMERA_GRAB_LATEST
  mantêm quadros recentes sem fila crescente; o buffer é sempre devolvido após envio.
- `idade_recepcao_limite`: idade_envio + HTTP. É um **limite superior estimado**
  da idade desde o início da captura até receber o JPEG na Pi, incluindo exposição,
  leitura e codificação. Não é latência exata: inclui também o trecho anterior ao
  instante em que a idade foi medida. Não subtraímos relógios de placas diferentes.
  Não inclui atraso do monitor; para latência visual completa, filme um cronômetro
  e sua imagem exibida na Pi juntos e compare os tempos visíveis.
- `FPS`: quadros válidos por tempo decorrido em janelas de cerca de 5 s, incluindo
  pausas e falhas; cada solicitação e sua idade ficam no CSV.

Com motores desligados, aponte a câmera para a pista e mova um objeto pelo campo:
confira 320×240, orientação, foco, luz, linha e área à frente do carrinho. A imagem
é mostrada sem recorte nem transformação para CNN.

Mantenha a recepção por pelo menos 5 minutos: procure ausência de congelamento,
JPEGs inválidos e reinicializações; FPS não deve colapsar e a idade não deve crescer
continuamente. Registre as faixas de FPS, HTTP e idade no CSV, pois dependem da luz,
alimentação e sinal. Aproxime Pi e câmera no primeiro teste.

Com o script aberto, retire o USB **da câmera** por 10 s e religue. Devem aparecer
falhas, a rede deve voltar e imagens novas devem reaparecer sem reiniciar o script.
Confira a reconexão automática do Wi-Fi da Pi; se o sistema escolher outra rede,
reconecte Carrinho-CAM pelo menu/nmcli. Repita três vezes e observe a recuperação.
Se houver resets espontâneos, confira cabo USB, alimentação e encaixe do flex com
energia desligada. Não desabilite o detector de brownout para esconder falhas.

Encerre esta etapa somente após receber e exibir imagens estáveis e validar essas
recuperações no hardware. Anote data, duração, métricas e resultado; não avance para
mudanças na CNN nesta etapa.

Referências oficiais: [pinagem AI Thinker](https://github.com/espressif/arduino-esp32/blob/master/libraries/ESP32/examples/Camera/CameraWebServer/camera_pins.h),
[driver e timestamps](https://github.com/espressif/esp32-camera/blob/master/driver/include/esp_camera.h).
