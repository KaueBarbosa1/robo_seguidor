"""Configurações centrais do robô. Ajuste os valores aqui, não no meio do código."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# ------------------------------------------------- Serial (Pi <-> Arduino: imagem da OV7670 + comandos dos motores)
# A câmera é a OV7670 ligada ao Arduino (decisão definitiva): a imagem chega pela serial. A ligação física entre as
# placas (hoje USB) e quem controla cada sensor ainda podem mudar: veja docs/06_revisao_tecnica.md.
SERIAL_PORTA = "/dev/ttyACM0"      # Arduino UNO via USB costuma ser ttyACM0 (clones: ttyUSB0)
FIRMWARE_COM_CAMERA = False       # True = firmware com USAR_CAMERA 1 (OV7670, 1 Mbaud, sem ultrassom/encoders);
                                   # False = USAR_CAMERA 0 (sem câmera: 115200 baud, COM ultrassom e encoders). Igual ao que foi gravado!
SERIAL_BAUD = 115200    # igual ao firmware gravado (UART_U2X_UBRR em config.h)
SERIAL_TIMEOUT_S = 0.1
FW_LINHA_INICIAL = 0               # primeira linha da imagem enviada: igual a LINHA_INICIAL em config.h do firmware
SERIAL_BOOT_DELAY_S = 2.5          # o UNO reinicia ao abrir a porta serial

# ---------------------------------------------------------------- Motores
VEL_BASE = 140                     # PWM 0-255 em linha reta
VEL_MAX = 255
VEL_GIRO = 150                     # PWM do giro forçado (voz)
VEL_RE = 130                       # PWM do "voltar"
KP = 90.0                          # ganho proporcional (erro normalizado -1..1 -> PWM)
KD = 25.0                          # ganho derivativo
KD_FILTRO = 1.0                    # filtro da derivada (0..1; 1 = sem filtro). A OV7670 dá ~2,5 quadros/s: sem filtro.
                                   # (Se um dia a câmera for rápida, ~30 quadros/s, use ~0.3 para o ruído não virar tremor.)
TEMPO_GIRO_S = 0.6                 # duração do giro forçado por "esquerda"/"direita"
TEMPO_RE_S = 1.0                   # duração da ré por "voltar"
PERDA_LINHA_TIMEOUT_S = 0.6        # sem ver a linha por este tempo -> para
LEITURA_VALIDADE_S = 0.3           # leitura de visão mais velha que isto é descartada
FREQ_CONTROLE_HZ = 20

# Ultrassom HC-SR04 (Arduino): os limites espelham OBSTACULO_* em firmware/config.h.
OBSTACULO_ATIVO = True
# Primeira etapa: inspecao parada somente em SEGUINDO; nunca desvia sozinho.
INSPECAO_OBSTACULO_ATIVA = True
INSPECAO_REPOUSO_S = 0.4          # espera inicial; validar inercia real
INSPECAO_TIMEOUT_S = 8.0         # aborta e permanece PARADO se faltar resposta
OBSTACULO_DIST_CM = 25             # distância de parada
OBSTACULO_LIBERACAO_CM = 30       # precisa afastar até aqui para liberar (igual ao firmware)
OBSTACULO_LEITURAS = 2             # leituras consecutivas para confirmar bloqueio/liberação
SENSOR_TIMEOUT_S = 0.25            # sem pacote recente, diagnóstico remoto considera segurança indisponível

# ------------------------------------------------------- Controle remoto pelo celular (Bluetooth, Android)
# O celular conecta no Bluetooth da Pi como "porta serial" (SPP/RFCOMM). Veja docs/07_controle_bluetooth.md.
REMOTO_BT_ATIVO = True             # False = não sobe o servidor Bluetooth
REMOTO_ADAPTADOR = "hci0"          # adaptador Bluetooth da Pi (o servidor tenta ligá-lo ao subir)
REMOTO_NOME = "Robo Carrinho"      # nome do serviço serial (aparece em alguns apps)
REMOTO_MACS_PERMITIDOS: list[str] = []   # ex.: ["AA:BB:CC:DD:EE:FF"]; vazio = qualquer celular JÁ PAREADO
REMOTO_TIMEOUT_S = 1.5             # sem novo comando de movimento por este tempo -> o carrinho PARA (anti-fuga).
REMOTO_BOTOES_ATE_SOLTAR = True    # app envia F/B/L/R ao apertar e S ao soltar; mantem enquanto conectado
                                   # Apps que repetem o comando enquanto o botão está apertado mantêm o movimento.
                                   # Apps que mandam uma vez só: ande no máximo isto por toque (ou aumente com cuidado).
REMOTO_BLUEDOT_TIMEOUT_S = 2.0     # app Blue Dot (analógico): sem NENHUMA mensagem por este tempo com o dedo na tela -> PARA
                                   # (o app só avisa quando o dedo se mexe ou solta; isto cobre a conexão que cai com o dedo apertado)
REMOTO_BLUEDOT_ZONA_MORTA = 0.15   # raio no centro do analógico (0..1) em que o carrinho fica parado
REMOTO_ELETROGATE_TIMEOUT_S = 0.4  # app Robô Eletrogate envia atualizações contínuas; silêncio do joystick para rapidamente
# Preencher APOS observar Bluetooth RX ao apertar/soltar a buzina.
# Por enquanto nenhum caractere avulso e presumido. Aceitos: W w U u V v X x.
REMOTO_BUZINA_LIGAR = ""
REMOTO_BUZINA_DESLIGAR = ""
REMOTO_BUZINA_PULSO = "Y"          # byte observado no app; toque limitado pelo firmware a 1,5 s
REMOTO_LOG_BYTES = True           # True registra cada bloco Bluetooth em hexadecimal e texto legível (diagnóstico)
REMOTO_VEL_INICIAL = 6             # nível 0..10 ao conectar (10 = REMOTO_VEL_MAX)
REMOTO_VEL_MAX = 200               # PWM no nível 10 e no analógico todo para o lado (limite de segurança do remoto; máx. 255)
REMOTO_CURVA_FATOR = 0.4           # curvas (G/I/H/J): a roda de dentro anda esta fração da de fora

# ----------------------------------------------------------------- Visão
# Câmera: OV7670 no Arduino (QQVGA 160x120, 4 bits de cinza, ~2,5 quadros/s). O robô trabalha com quadros cinza
# 120x160 (uint8). Veja docs/01_ligacao_camera.md e docs/02_bringup_camera.md.
FONTE_IMAGEM = "arduino"           # "arduino" (OV7670, pela serial), "simulada" (linha falsa), "nenhuma" ou "csi" (NÃO usada)
# --- só para FONTE_IMAGEM = "csi" (Pi Camera Rev 1.3 no conector CSI; código mantido, mas a câmera não é a do projeto) ---
CAMERA_FPS = 30                    # quadros por segundo pedidos ao sensor
CAMERA_PRINCIPAL = (640, 480)      # stream principal (não usado, mas o picamera2 exige); modo nativo do OV5647
CAMERA_LORES = (320, 240)          # stream de onde sai o cinza (largura múltipla de 32); depois reduz p/ 160x120
CAMERA_EXPOSICAO_US = None         # None = exposição automática; ou um valor fixo em microssegundos (ex.: 8000)
CAMERA_GANHO = None                # ganho analógico fixo (só vale junto com CAMERA_EXPOSICAO_US)
# --- vale para as duas câmeras ---
IMAGEM_ESPELHAR_H = False          # True se a imagem sair espelhada na horizontal (câmera de cabeça p/ baixo etc.)
IMAGEM_ESPELHAR_V = False          # True se estiver de cabeça para baixo
ROI_INICIO = 0.50                  # a análise usa só a parte de baixo do frame (fração da altura)
BLUR_KERNEL = 3                    # ímpar; imagem pequena e ruidosa, mas 3 basta
LINHA_ESCURA = True                # True: linha preta em piso claro; False: linha clara em piso escuro
USAR_OTSU = True                   # limiar automático; False usa LIMIAR_FIXO
LIMIAR_FIXO = 100
CONTRASTE_MIN = 40                 # (máx-mín) da ROI abaixo disto = sem linha (Otsu em piso liso inventa linha)
AREA_MIN = 40                      # contornos menores que isto (em pixels de 160x120) são ruído
MOSTRAR_DEBUG = False              # True abre janela do OpenCV (precisa de monitor/VNC)

# ------------------------------------------------------ Aprendizado online (pasta aprendizado/)
# Veja docs/04_aprendizado_online.md. Desligado por padrão: precisa da câmera e da pista.
APRENDIZADO_ATIVO = False
APR_DIR = BASE_DIR / "dados_aprendizado"   # episódios gravados, versões do modelo, estado do ciclo

APR_ROI_LINHA_INICIO = 40          # linhas do topo do quadro 120x160 descartadas antes da CNN
APR_GANHO_PROF = 1.2               # direção do professor (OpenCV) = clip(ganho * erro, -1, 1)
APR_GANHO_DIRECAO = 90.0           # direção [-1,1] -> diferença de PWM entre as rodas
APR_VEL = 110                      # PWM base durante o aprendizado (comece devagar)
APR_PERIODO_MIN_S = 0.4            # o aprendizado usa no máximo 1 quadro a cada tanto tempo (0,4 s = 2,5 passos/s, o ritmo
                                   # em que tudo foi dimensionado e testado no simulador). Só reduza depois de medir na pista.
APR_MAX_BURACO = 4                 # passos seguidos sem linha (vão do pontilhado) reparados por interpolação
APR_JANELA_FALHA = 8               # quadros antes de uma falha que ganham mais peso no treino
APR_BUFFER_MAX = 15000             # máximo de quadros mantidos em memória para treinar

# Níveis de autonomia: fração dos quadros em que a CNN pode conduzir, e o quanto ela pode divergir do
# professor (portão de segurança). Nível 0 = só o professor dirige (coleta de dados).
APR_NIVEIS = [0.0, 0.25, 0.5, 0.75, 1.0]
APR_PORTAO = [0.0, 0.25, 0.30, 0.40, 9.0]   # último nível: sem portão (a CNN dirige sozinha; o professor só vigia)
APR_NIVEL_SUBIR_TENT = 3           # tentativas do campeão no nível atual antes de poder subir
APR_NIVEL_SUBIR_FALHAS = 0.2       # ... com no máximo esta fração de falhas
APR_NIVEL_DESCER_FALHAS = 2        # falhas seguidas causadas pela CNN que fazem voltar um nível

# Segurança: uma tentativa é interrompida quando...
APR_MAX_QUADROS_SEM_LINHA = 4      # ...a linha some por tantos quadros seguidos (além do vão normal)
APR_ERRO_DIVERGENCIA = 0.85        # ...|erro| fica acima disto...
APR_QUADROS_DIVERGENCIA = 3        # ...por tantos quadros seguidos
APR_OSC_JANELA = 6                 # ...a direção troca de sinal (com amplitude) APR_OSC_TROCAS vezes na janela
APR_OSC_TROCAS = 4
APR_IDADE_MAX_QUADRO_S = 1.5       # ...ou ficam sem quadro novo por este tempo
APR_PARADO_PASSOS = 3              # ...ou os encoders não mexem apesar de comandar movimento
APR_TEMPO_MAX_S = 120              # ...ou passa deste tempo (tentativa "concluída", não falha)

# Treino
APR_MIN_QUADROS_PRIMEIRO = 600     # quadros (com rótulo) antes de treinar a primeira CNN
APR_NOVOS_PARA_TREINAR = 300       # quadros novos para treinar um candidato
APR_PASSOS_TREINO = 400
APR_LOTE = 32
APR_LR = 1e-3
APR_AVALIAR_A_CADA_PASSOS = 50
APR_MIN_PASSOS_TREINO = 100
APR_PACIENCIA_TREINO = 4
APR_TOL_OFFLINE = 0.10             # candidato pode ter erro de validação até 10% maior que o campeão
# Comparação A/B entre campeão e candidato (tentativas alternadas, mesmo nível de autonomia)
APR_AB_MIN = 3
APR_AB_MAX = 8
APR_AB_PROB = 0.80                 # confiança (bootstrap) para promover ou descartar
APR_ACAO_VALIDADE_S = 1.5             # ação do aprendizado mais velha que isso = o controle para os motores
APR_NAO_INFERIOR_MARGEM = 0.05      # pontuação: pior que isso no IC95 = não é "não-inferior"
APR_GANHO_OFFLINE_MIN = 0.15         # redução relativa do erro na validação offline p/ promover sem diferença no A/B
APR_MANTER_VERSOES = 8

# ------------------------------------------------------------------- Voz
COMANDOS = ["siga", "esquerda", "direita", "pare", "voltar"]

MODELO_TIPO = "mistura"            # "mistura" (LSTM + SVM, média das probabilidades) ou "mlp"
MODELO_MISTURA = BASE_DIR / "voz" / "modelo" / "modelo_mistura.pkl"   # 6_lstm_classification.py
MODELO_MLP = BASE_DIR / "voz" / "modelo" / "modelo.pkl"               # 4_classification.py

# Microfone = headset Bluetooth pareado na Pi (veja docs/03_bluetooth_headset.md).
MIC_DEVICE = None                  # None = padrão do sistema; ou parte do NOME (ex.: "JBL") ou o índice
MIC_SR = 16000                     # taxa que o MODELO espera (a do treino). Não mude.
MIC_SR_TENTATIVAS = [16000, 48000, 44100, 32000, 8000]   # taxas tentadas no headset, nessa ordem;
                                   # o sinal é reamostrado para MIC_SR antes das features
PARAR_SE_SEM_MICROFONE = True      # headset caiu -> robô para (sem voz não há como mandar "pare")
MIC_REABRIR_S = 3.0                # espera entre tentativas se o headset desconectar

# VAD (detector de fala): quantos blocos de ~64 ms de silêncio fecham a palavra.
# Menor = "pare" reage mais rápido, mas pode cortar palavras com pausa no meio.
VAD_BLOCOS_FIM = 8

# Confiança mínima (0..1). O projeto original usava 50%. "pare" é mais permissivo de propósito:
# um "pare" falso só para o robô, um "pare" perdido deixa ele andando.
LIMIAR_PADRAO = 0.50
LIMIAR_CONFIANCA = {"pare": 0.40}


# Habilitar apos conferir pulsos e ajustar PI com rodas suspensas.
# Mantem a interface do controle: escala -255..255 para -referencia..+referencia.
CONTROLE_VELOCIDADE_ATIVO = True  # teste do PI com encoders e rodas suspensas
VELOCIDADE_REFERENCIA_PPS = 60
