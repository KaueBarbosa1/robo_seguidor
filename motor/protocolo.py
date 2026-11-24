"""Protocolo serial Arduino <-> Raspberry Pi. Espelho de arduino/robo_firmware/protocolo.h.

Se mudar algo aqui, mude lá também (e em config.py: FW_LINHA_INICIAL espelha LINHA_INICIAL).
"""
SYNC = 0xFF
IDX_FIM_QUADRO = 0xFE
IDX_STATUS = 0xFD
IDX_SENSORES = 0xFC                # 7 bytes de 7 bits: distância, encoders, flags de segurança
IDX_SERVO = 0xFB                   # 5 bytes de 7 bits: angulo nominal, centro_us, flags
IDX_INSPECAO = 0xFA               # posicao 0/1/2, cm L/H, rodada L/H; todos de 7 bits
IDX_SONAR = 0xF9                  # angulo L/H, cm L/H, sequencia L/H
IDX_MOTORES = 0xF8                # magnitudes PWM E L/H, D L/H, flags
IDX_GUARDA_SONAR = 0xF7          # um byte com motivos da guarda frontal no modo4
GUARDA_SONAR_MOTIVOS = ('perfil_invalido', 'sem_frente', 'frente_vencida',
                       'confirmando_frente', 'limite_avanco', 'divergencia_rodas', 'distancia_reserva')
BYTES_MOTORES = 5
MOTORES_FLAG_NEG_ESQ = 0x01
MOTORES_FLAG_NEG_DIR = 0x02
MOTORES_FLAG_FALHA_ENCODER = 0x04
MOTORES_FLAG_PI = 0x08
MOTORES_FLAG_REFORCO_ESQ = 0x10
MOTORES_FLAG_REFORCO_DIR = 0x20
MOTORES_FLAG_MANUAL_SEM_ULTRASSOM = 0x40
BYTES_SONAR = 6
SERVO_FLAG_SONAR = 0x20
SERVO_FLAG_SONAR_MOVIMENTO = 0x40
BYTES_INSPECAO = 5
SERVO_FLAG_INSPECAO = 0x08
SERVO_FLAG_CONCLUIDA = 0x10
BYTES_SERVO = 5
SERVO_FLAG_VARREDURA = 0x01
SERVO_FLAG_CENTRO_PRONTO = 0x02
SERVO_FLAG_ATIVO = 0x04
DIST_SEM_LEITURA = 0x3FFF
ENC_MODULO = 0x4000                # contadores de encoder de 14 bits dão a volta em 16384
BYTES_SENSORES = 7
SENSOR_FLAG_BLOQUEADO = 0x01
SENSOR_FLAG_FALHA = 0x02
SENSOR_FLAG_OBSTACULO = 0x04
SENSOR_FLAG_SONAR_NAO_CALIBRADO = 0x08
SENSOR_FLAG_SONAR_EXPERIMENTAL = 0x10
SENSOR_FLAG_LATERAL_ESQ = 0x20
SENSOR_FLAG_LATERAL_DIR = 0x40

CMD_START = 0xAA
CMD_MOTORES = ord("M")
CMD_PARAR = ord("S")
CMD_SERVO = ord("V")
CMD_BUZINA = ord("H")
CMD_AVISO = ord("A")
CMD_VELOCIDADE = ord("R")
CMD_MANUAL_SEM_ULTRASSOM = ord("U")
CMD_XOR = 0x5A

IMG_LARGURA = 160                  # iguais a IMG_LARGURA / IMG_ALTURA do config.h
IMG_ALTURA = 120
BYTES_LINHA = IMG_LARGURA // 2     # 2 pixels de 4 bits por byte

ST_OK = 0
ST_SEM_I2C = 1
ST_ID_ERRADO = 2
ST_REG_FALHOU = 3
ST_SEM_VSYNC = 4

STATUS_TEXTO = {
    ST_OK: "câmera OK",
    ST_SEM_I2C: "a câmera não respondeu no I2C (SIOC/SIOD, pull-ups de 3,3V, XCLK, alimentação)",
    ST_ID_ERRADO: "respondeu no I2C, mas o ID não é de um OV7670 (leitura corrompida ou outro sensor)",
    ST_REG_FALHOU: "falha ao escrever a configuração na câmera",
    ST_SEM_VSYNC: "configurou, mas não chega VSYNC (fio do VSYNC em D3, XCLK, PWDN no GND)",
}


def montar_comando(cmd: int, a: int = 0, b: int = 0) -> bytes:
    """Pacote de 5 bytes Pi -> Arduino. a e b são int8 (-128..127)."""
    a &= 0xFF
    b &= 0xFF
    return bytes([CMD_START, cmd, a, b, cmd ^ a ^ b ^ CMD_XOR])


def comando_motores(esq_pwm: int, dir_pwm: int) -> bytes:
    """PWM -255..255 -> int8 (o firmware multiplica por 2)."""
    def conv(v: int) -> int:
        return max(-127, min(127, int(round(v / 2))))
    return montar_comando(CMD_MOTORES, conv(esq_pwm), conv(dir_pwm))


def comando_parar() -> bytes:
    return montar_comando(CMD_PARAR)


def comando_servo(varrer: bool = False, ajuste_us: int = 0) -> bytes:
    """Servo: modo 0 centro/1 varrer, offset relativo ao centro do firmware.

    A varredura exige motores parados e renovacao em menos de 400 ms.
    """
    if not isinstance(ajuste_us, int) or ajuste_us % 10 or not -250 <= ajuste_us <= 250:
        raise ValueError('ajuste_us deve ser multiplo inteiro de 10, entre -250 e 250')
    return montar_comando(CMD_SERVO, int(bool(varrer)), ajuste_us // 10)


def comando_inspecao() -> bytes:
    """Rodada parada: 45, 90, 135 graus e retorno ao centro; renovar antes de 400 ms."""
    return montar_comando(CMD_SERVO, 2, 0)


def comando_sonar() -> bytes:
    """Sonar continuo parado; renovar antes de 400 ms. Usa o centro do firmware."""
    return montar_comando(CMD_SERVO, 3, 0)


def comando_sonar_movimento() -> bytes:
    """Modo 4: sonar manual durante marcha; perfil selecionado no firmware."""
    return montar_comando(CMD_SERVO, 4, 0)


def comando_buzina(ligada: bool = True) -> bytes:
    """Buzzer ativo: comando limitado pelo Arduino, sem renovar motores."""
    return montar_comando(CMD_BUZINA, int(bool(ligada)), 0)


def comando_aviso(tipo: int) -> bytes:
    """0 cancela, 1 partida (600 ms), 2 linha perdida (renovar antes de 400 ms)."""
    if tipo not in (0, 1, 2):
        raise ValueError("Aviso invalido")
    return montar_comando(CMD_AVISO, tipo, 0)


def comando_velocidade(esq: int, dir_: int) -> bytes:
    """Alvos assinados em pulsos/s; nao sao PWM nem RPM."""
    if any(not isinstance(v, int) or isinstance(v, bool) or abs(v) > 120 for v in (esq, dir_)):
        raise ValueError("Velocidade deve ser inteira entre -120 e 120 pulsos/s")
    return montar_comando(CMD_VELOCIDADE, esq, dir_)


def comando_manual_sem_ultrassom(ativo):
    """U nao renova movimento; modo exige lease e confirmacao F8 bit6."""
    return montar_comando(CMD_MANUAL_SEM_ULTRASSOM, int(bool(ativo)), 0)
