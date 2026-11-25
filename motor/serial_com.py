"""Ponte serial com o Arduino UNO (protocolo binário em motor/protocolo.py).

Uma única porta serial leva:
  Pi -> Arduino : comandos dos motores   (motores(), parar())
  Arduino -> Pi : distância do HC-SR04 e encoders (sempre) e, se a câmera estiver no Arduino,
                  imagem 160x120 de 4 bits linha a linha + avisos de status

Uma thread interna ("serial-rx") lê o fluxo, reconstrói os quadros e guarda o mais recente.
Quem precisa da imagem chama proximo_quadro(). A escrita é protegida por Lock, então a
thread de controle e a de voz podem chamar motores()/parar() sem se atrapalhar.
O Arduino para os motores sozinho se ficar ~400 ms sem comando (watchdog): o controle reenvia
o comando a cada ciclo (20 Hz), o que serve de keep-alive.
"""
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass

import numpy as np
import serial

import config as cfg
from motor import protocolo as P
from monitoramento import medir, observar, contar, publicar_pedido

log = logging.getLogger("serial")


@dataclass
class Sensores:
    distancia_cm: int | None          # None = sem leitura frontal valida; consultar flags
    ticks_esq: int                    # total acumulado de pulsos do encoder esquerdo desde a conexão
    ticks_dir: int
    timestamp: float
    avanco_bloqueado: bool = True
    falha_sensor: bool = True
    obstaculo_confirmado: bool = False
    sonar_nao_calibrado: bool = False
    sonar_experimental: bool = False
    lateral_esq_bloqueada: bool = False
    lateral_dir_bloqueada: bool = False


@dataclass
class StatusServo:
    angulo_nominal: int              # comando enviado; nao ha feedback de angulo fisico
    centro_us: int
    varredura: bool
    centro_pronto: bool
    ativo: bool
    timestamp: float
    inspecao: bool = False
    concluida: bool = False
    sonar: bool = False
    sonar_movimento: bool = False


@dataclass(frozen=True)
class EstadoMotores:
    pwm_esq: int
    pwm_dir: int
    falha_encoder: bool
    pi_ativo: bool
    reforco_esq: bool
    reforco_dir: bool
    timestamp: float
    manual_sem_ultrassom: bool = False


@dataclass(frozen=True)
class MedidaSonar:
    angulo_nominal: int              # comando no disparo do ultrassom, nao posicao fisica
    distancia_cm: int | None
    sequencia: int
    timestamp: float


@dataclass(frozen=True)
class AmostraDirecional:
    angulo_nominal: int
    distancia_cm: int | None
    rodada: int
    timestamp: float


class ArduinoSerial:
    def __init__(self, porta: str = cfg.SERIAL_PORTA, baud: int = cfg.SERIAL_BAUD):
        self._porta = porta
        self._baud = baud
        self._ser: serial.Serial | None = None
        self._lock_tx = threading.Lock()           # só uma thread escreve por vez
        self._parar_rx = threading.Event()
        self._thread: threading.Thread | None = None

        self._cond = threading.Condition()         # protege o quadro publicado
        self._quadro: np.ndarray | None = None
        self._quadro_id = 0
        self._quadro_t = 0.0
        self._status = None                        # último código de status recebido do Arduino
        self._lock_sens = threading.Lock()
        self._sens: Sensores | None = None
        self._servo: StatusServo | None = None
        self._motores: EstadoMotores | None = None
        self._guarda_sonar: tuple[int, float] | None = None
        self._sonar_manual = False
        self._manual_sem_ultrassom = False
        self._manual_saida_apos = None
        self._inspecao: dict[int, AmostraDirecional] = {}
        self._sonar: deque[MedidaSonar] = deque(maxlen=256)
        self._dists: deque = deque(maxlen=10)      # últimas leituras de distância (None = sem eco)
        self._enc_ult: tuple[int, int] | None = None
        self._ticks = [0, 0]
        self.estatisticas = {"quadros": 0, "linhas_ok": 0, "linhas_descartadas": 0,
                             "quadros_incompletos": 0, "reconexoes": 0}

    # ------------------------------------------------------------ conexão
    def conectar(self) -> None:
        """Abre a porta (levanta exceção se não existir) e inicia a thread de leitura."""
        self._abrir()
        self._thread = threading.Thread(target=self._rx_loop, name="serial-rx", daemon=True)
        self._thread.start()

    def _abrir(self) -> None:
        ser = serial.Serial(self._porta, self._baud,
                            timeout=cfg.SERIAL_TIMEOUT_S, write_timeout=cfg.SERIAL_TIMEOUT_S)
        time.sleep(cfg.SERIAL_BOOT_DELAY_S)        # abrir a porta reinicia o UNO
        ser.reset_input_buffer()
        with self._lock_tx:
            self._ser = ser
        log.info("Arduino conectado em %s @ %d baud", self._porta, self._baud)

    def fechar(self) -> None:
        self._parar_rx.set()
        if self._thread:
            self._thread.join(timeout=1.5)
        with self._lock_tx:
            if self._ser and self._ser.is_open:
                self._ser.close()
            self._ser = None

    # ------------------------------------------------------------ envio
    @medir('serial_escrita_s')
    def _escrever(self, pacote: bytes, repetir: int = 1) -> None:
        for i in range(repetir):
            with self._lock_tx:
                if not self._ser or not self._ser.is_open:
                    return                              # a thread de leitura está reconectando
                try:
                    enviados = self._ser.write(pacote)
                    contar('serial_tx_bytes', enviados)
                except (serial.SerialException, OSError) as e:
                    log.error("Erro de escrita serial: %s", e)
                    contar('serial_erros_tx')
                    self._ser = None                    # sinaliza para a thread de leitura reconectar
                    return
            if i + 1 < repetir:
                # O Arduino não escuta enquanto lê uma linha da câmera (~0,6 ms a cada ~3 ms).
                # Repetir espaçado garante que ao menos uma cópia chegue num intervalo livre.
                time.sleep(0.004)

    def usar_sonar_manual(self, ativo: bool) -> None:
        ativo = bool(ativo and cfg.SONAR_MOVIMENTO_ATIVO)
        if self._sonar_manual and not ativo:
            self.parar()
            self.configurar_servo(False)
        self._sonar_manual = ativo

    def usar_manual_sem_ultrassom(self, ativo: bool) -> None:
        ativo = bool(ativo and not cfg.ULTRASSOM_BLUETOOTH_ATIVO)
        d = self.estado_motores()
        confirmado = d is not None and getattr(d, 'manual_sem_ultrassom', False)
        if ativo:
            self._manual_saida_apos = None
        elif (self._manual_sem_ultrassom or confirmado) and self._manual_saida_apos is None:
            self._manual_saida_apos = time.monotonic()
        if ativo and not self._manual_sem_ultrassom:
            self.parar()
            self.configurar_servo(False)
        if ativo or self._manual_sem_ultrassom or confirmado:
            self._escrever(P.comando_manual_sem_ultrassom(ativo))
        if not ativo and self._manual_sem_ultrassom:
            self.parar()
        self._manual_sem_ultrassom = ativo

    def motores(self, esq: int, dir_: int) -> None:
        esq = max(-cfg.VEL_MAX, min(cfg.VEL_MAX, int(esq)))
        dir_ = max(-cfg.VEL_MAX, min(cfg.VEL_MAX, int(dir_)))
        if self._manual_sem_ultrassom:
            if not cfg.CONTROLE_VELOCIDADE_ATIVO or cfg.FIRMWARE_COM_CAMERA:
                raise RuntimeError('Manual sem ultrassom exige PI com encoders no perfil sem camera')
            self.usar_manual_sem_ultrassom(True)
            d = self.estado_motores()
            agora = time.monotonic()
            if (d is None or not getattr(d, 'manual_sem_ultrassom', False) or
                    not 0 <= agora - d.timestamp <= cfg.SENSOR_TIMEOUT_S):
                self.parar()  # espera U/F8 sem descartar a intencao mantida no estado
                return
        else:
            d = self.estado_motores()
            if d is not None and getattr(d, 'manual_sem_ultrassom', False):
                self.usar_manual_sem_ultrassom(False)
            if self._manual_saida_apos is not None:
                if (d is None or getattr(d, 'manual_sem_ultrassom', False) or
                        d.timestamp <= self._manual_saida_apos or
                        not 0 <= time.monotonic()-d.timestamp <= cfg.SENSOR_TIMEOUT_S):
                    self._escrever(P.comando_manual_sem_ultrassom(False))
                    self.parar()
                    return  # aguarda F8 novo confirmando restauracao
                self._manual_saida_apos = None
        if self._sonar_manual and (esq or dir_):
            if not cfg.CONTROLE_VELOCIDADE_ATIVO or cfg.FIRMWARE_COM_CAMERA:
                raise RuntimeError('Sonar em movimento exige PI com encoders e firmware sem OV7670')
            self.iniciar_sonar_movimento()
            status = self.status_servo()
            agora = time.monotonic()
            if (status is None or not status.ativo or not status.sonar_movimento or
                    not 0 <= agora - status.timestamp <= .5):
                # Firmware antigo pode ignorar V4 e aceitar R normal sem o teto.
                # Aguardar confirmacao explicita do modo antes de solicitar movimento.
                self.parar()
                return
        if cfg.CONTROLE_VELOCIDADE_ATIVO:
            if cfg.FIRMWARE_COM_CAMERA:
                raise RuntimeError("Encoders indisponiveis no firmware com camera")
            e = round(esq * cfg.VELOCIDADE_REFERENCIA_PPS / 255)
            d = round(dir_ * cfg.VELOCIDADE_REFERENCIA_PPS / 255)
            if self._manual_sem_ultrassom:
                maior = max(abs(e), abs(d))
                teto = cfg.MANUAL_SEM_ULTRASSOM_MAX_PPS
                if maior > teto:
                    e, d = int(e*teto/maior), int(d*teto/maior)
            self.velocidade(e, d)
        else:
            publicar_pedido('pwm_direto_esq_dir', (esq, dir_))
            self._escrever(P.comando_motores(esq, dir_))

    def velocidade(self, esq: int, dir_: int) -> None:
        if cfg.FIRMWARE_COM_CAMERA:
            raise RuntimeError("Controle de velocidade exige firmware sem camera")
        publicar_pedido('referencia_pps_esq_dir', (esq, dir_))
        self._escrever(P.comando_velocidade(esq, dir_))

    def pwm(self, esq: int, dir_: int) -> None:
        """PWM explicito para bancada, independente da conversao PI de motores()."""
        status = self.status_servo()
        d = self.estado_motores()
        if self._manual_sem_ultrassom or (d is not None and getattr(d, 'manual_sem_ultrassom', False)):
            raise RuntimeError('PWM de bancada indisponivel durante manual sem ultrassom')
        if self._sonar_manual or (status is not None and status.sonar_movimento):
            raise RuntimeError('PWM direto indisponivel no sonar em movimento')
        if any(not isinstance(v, int) or isinstance(v, bool) or abs(v) > 254 for v in (esq, dir_)):
            raise ValueError('PWM deve ser inteiro entre -254 e 254')
        publicar_pedido('pwm_direto_esq_dir', (esq, dir_))
        self._escrever(P.comando_motores(esq, dir_))

    def parar(self, repetir: int = 1) -> None:
        publicar_pedido('parada', True)
        self._escrever(P.comando_parar(), repetir)

    def avisar(self, tipo: int) -> None:
        self._escrever(P.comando_aviso(tipo))

    def buzinar(self, ligada: bool = True) -> None:
        self._escrever(P.comando_buzina(ligada))

    def configurar_servo(self, varrer: bool = False, ajuste_us: int = 0) -> None:
        self._escrever(P.comando_servo(varrer, ajuste_us))

    def inspecionar_obstaculo(self) -> None:
        self._escrever(P.comando_inspecao())

    def iniciar_sonar(self) -> None:
        self._escrever(P.comando_sonar())

    def iniciar_sonar_movimento(self) -> None:
        self._escrever(P.comando_sonar_movimento())

    def consumir_leituras_sonar(self) -> list[MedidaSonar]:
        """Retira as medidas recebidas; timestamp e de recepcao na Pi."""
        with self._lock_sens:
            medidas = list(self._sonar)
            self._sonar.clear()
            return medidas

    def _ao_sonar(self, angulo: int, cm: int, sequencia: int) -> None:
        with self._lock_sens:
            self._sonar.append(MedidaSonar(angulo, cm if 2 <= cm <= 400 else None,
                                           sequencia, time.monotonic()))

    def leituras_inspecao(self) -> list[AmostraDirecional]:
        with self._lock_sens:
            return list(self._inspecao.values())

    def _ao_inspecao(self, angulo: int, cm: int, rodada: int) -> None:
        if angulo not in (45, 90, 135):
            return
        with self._lock_sens:
            if self._inspecao and next(iter(self._inspecao.values())).rodada != rodada:
                self._inspecao.clear()
            self._inspecao[angulo] = AmostraDirecional(
                angulo, cm if 2 <= cm <= 400 else None, rodada, time.monotonic())

    def status_servo(self) -> StatusServo | None:
        with self._lock_sens:
            return self._servo

    def estado_motores(self) -> EstadoMotores | None:
        with self._lock_sens:
            return self._motores

    def guarda_sonar(self) -> tuple[int, float] | None:
        with self._lock_sens:
            return self._guarda_sonar

    def _ao_guarda_sonar(self, motivos: int) -> None:
        with self._lock_sens:
            self._guarda_sonar = (motivos, time.monotonic())

    def _ao_motores(self, esq: int, dir_: int, flags: int) -> None:
        with self._lock_sens:
            self._motores = EstadoMotores(-esq if flags & P.MOTORES_FLAG_NEG_ESQ else esq,
                                          -dir_ if flags & P.MOTORES_FLAG_NEG_DIR else dir_,
                                          bool(flags & P.MOTORES_FLAG_FALHA_ENCODER),
                                          bool(flags & P.MOTORES_FLAG_PI),
                                          bool(flags & P.MOTORES_FLAG_REFORCO_ESQ),
                                          bool(flags & P.MOTORES_FLAG_REFORCO_DIR), time.monotonic(),
                                          bool(flags & P.MOTORES_FLAG_MANUAL_SEM_ULTRASSOM))

    def _ao_servo(self, angulo: int, centro_us: int, flags: int) -> None:
        with self._lock_sens:
            self._servo = StatusServo(angulo, centro_us, bool(flags & P.SERVO_FLAG_VARREDURA),
                                      bool(flags & P.SERVO_FLAG_CENTRO_PRONTO),
                                      bool(flags & P.SERVO_FLAG_ATIVO), time.monotonic(),
                                      bool(flags & P.SERVO_FLAG_INSPECAO),
                                      bool(flags & P.SERVO_FLAG_CONCLUIDA), bool(flags & P.SERVO_FLAG_SONAR),
                                      bool(flags & P.SERVO_FLAG_SONAR_MOVIMENTO))

    # ------------------------------------------------------------ imagem
    @property
    def status(self):
        return self._status

    def id_atual(self) -> int:
        with self._cond:
            return self._quadro_id

    def proximo_quadro(self, apos_id: int, timeout: float = 1.0):
        """Espera um quadro com id > apos_id. Devolve (id, imagem cinza 120x160 uint8) ou None."""
        with self._cond:
            ok = self._cond.wait_for(lambda: self._quadro_id > apos_id, timeout=timeout)
            if not ok or self._quadro is None:
                return None
            return self._quadro_id, self._quadro

    def _publicar(self, img: np.ndarray) -> None:
        with self._cond:
            self._quadro = img
            self._quadro_id += 1
            self._quadro_t = time.monotonic()
            self._cond.notify_all()

    # ------------------------------------------------------------ sensores
    def sensores(self) -> Sensores | None:
        """Última leitura de ultrassom + encoders enviada pelo Arduino (None se nunca chegou)."""
        with self._lock_sens:
            return self._sens

    def obstaculo(self, limite_cm: float, leituras: int) -> bool:
        """True se as últimas `leituras` medidas ficaram TODAS abaixo de `limite_cm`.
        Exigir várias seguidas evita parar por uma leitura isolada errada do HC-SR04."""
        with self._lock_sens:
            ultimas = list(self._dists)[-leituras:]
        return len(ultimas) == leituras and all(d is not None and d < limite_cm for d in ultimas)

    def _ao_sensores(self, dist: int, enc_e: int, enc_d: int, flags: int = 0x03) -> None:
        d = None if dist == P.DIST_SEM_LEITURA else dist
        with self._lock_sens:
            if self._sens is not None:
                observar('serial_intervalo_sensores_s', time.monotonic()-self._sens.timestamp)
            if self._enc_ult is not None:           # soma a diferença, tratando a volta dos 14 bits
                self._ticks[0] += (enc_e - self._enc_ult[0]) % P.ENC_MODULO
                self._ticks[1] += (enc_d - self._enc_ult[1]) % P.ENC_MODULO
            self._enc_ult = (enc_e, enc_d)
            self._dists.append(d)
            self._sens = Sensores(d, self._ticks[0], self._ticks[1], time.monotonic(),
                                  bool(flags & P.SENSOR_FLAG_BLOQUEADO),
                                  bool(flags & P.SENSOR_FLAG_FALHA),
                                  bool(flags & P.SENSOR_FLAG_OBSTACULO),
                                  bool(flags & P.SENSOR_FLAG_SONAR_NAO_CALIBRADO),
                                  bool(flags & P.SENSOR_FLAG_SONAR_EXPERIMENTAL),
                                  bool(flags & P.SENSOR_FLAG_LATERAL_ESQ),
                                  bool(flags & P.SENSOR_FLAG_LATERAL_DIR))

    # ------------------------------------------------------------ leitura
    def _rx_loop(self) -> None:
        dec = DecodificadorQuadros(self._ao_quadro, self._ao_status, self.estatisticas,
                                  self._ao_sensores, self._ao_servo, self._ao_inspecao, self._ao_sonar,
                                  self._ao_motores, self._ao_guarda_sonar)
        while not self._parar_rx.is_set():
            ser = self._ser
            if ser is None:
                self._reconectar()
                continue
            try:
                dados = ser.read(max(1, min(4096, ser.in_waiting or 1)))
            except (serial.SerialException, OSError) as e:
                log.error("Erro de leitura serial: %s", e)
                contar('serial_desconexoes_rx')
                with self._lock_tx:
                    self._ser = None
                continue
            if dados:
                contar('serial_rx_bytes', len(dados))
                dec.alimentar(dados)

    def _reconectar(self) -> None:
        time.sleep(1.0)
        try:
            self.estatisticas["reconexoes"] += 1
            self._abrir()
        except (serial.SerialException, OSError) as e:
            log.error("Falha ao reconectar: %s", e)

    def _ao_quadro(self, img: np.ndarray) -> None:
        self._publicar(img)

    def _ao_status(self, codigo: int) -> None:
        if codigo != self._status:
            self._status = codigo
            texto = P.STATUS_TEXTO.get(codigo, f"código {codigo}")
            (log.info if codigo == P.ST_OK else log.error)("Status da câmera: %s", texto)


class DecodificadorQuadros:
    """Separa o fluxo de bytes em linhas e quadros. Independe da porta serial (fácil de testar).

    Cada linha é  0xFF, idx, 80 bytes  (os bytes de pixel nunca valem 0xFF). Qualquer 0xFF dentro
    de uma linha significa byte perdido: a linha é descartada e a leitura ressincroniza ali.
    """

    def __init__(self, ao_quadro, ao_status=None, estat=None, ao_sensores=None, ao_servo=None, ao_inspecao=None,
                 ao_sonar=None, ao_motores=None, ao_guarda_sonar=None):
        self._ao_quadro = ao_quadro
        self._ao_status = ao_status or (lambda c: None)
        self._ao_sensores = ao_sensores or (lambda d, e, r, f=0: None)
        self._ao_servo = ao_servo or (lambda a, c, f: None)
        self._ao_inspecao = ao_inspecao or (lambda a, d, r: None)
        self._ao_sonar = ao_sonar or (lambda a, d, s: None)
        self._ao_motores = ao_motores or (lambda e, d, f: None)
        self._ao_guarda_sonar = ao_guarda_sonar or (lambda f: None)
        self._est = estat if estat is not None else {
            "quadros": 0, "linhas_ok": 0, "linhas_descartadas": 0, "quadros_incompletos": 0}
        self._buf = bytearray()
        self._img = np.zeros((P.IMG_ALTURA, P.IMG_LARGURA), np.uint8)
        self._recebida = np.zeros(P.IMG_ALTURA, bool)

    def alimentar(self, dados: bytes) -> None:
        self._buf += dados
        buf = self._buf
        i = 0
        n = len(buf)
        while True:
            j = buf.find(b"\xff", i)
            if j < 0 or j + 1 >= n:                      # sem marcador ou sem o byte seguinte
                i = n if j < 0 else j
                break
            idx = buf[j + 1]
            if idx < P.IMG_ALTURA:
                if j + 2 + P.BYTES_LINHA > n:            # linha ainda incompleta
                    i = j
                    break
                corpo = buf[j + 2:j + 2 + P.BYTES_LINHA]
                if 0xFF in corpo:                        # byte perdido no meio: descarta e ressincroniza
                    self._est["linhas_descartadas"] += 1
                    i = j + 1
                    continue
                self._linha(idx, corpo)
                i = j + 2 + P.BYTES_LINHA
            elif idx == P.IDX_FIM_QUADRO:
                self._fim_quadro()
                i = j + 2
            elif idx == P.IDX_STATUS:
                if j + 2 >= n:
                    i = j
                    break
                self._ao_status(buf[j + 2])
                i = j + 3
            elif idx == P.IDX_GUARDA_SONAR:
                if j + 3 > n:
                    i = j
                    break
                if buf[j + 2] > 0x7F:
                    i = j + 1
                    continue
                self._ao_guarda_sonar(buf[j + 2])
                i = j + 3
            elif idx == P.IDX_SONAR:
                if j + 2 + P.BYTES_SONAR > n:
                    i = j
                    break
                c = buf[j + 2:j + 2 + P.BYTES_SONAR]
                if any(b > 0x7F for b in c) or (c[0] | (c[1] << 7)) > 180:
                    i = j + 1
                    continue
                self._ao_sonar(c[0] | (c[1] << 7), c[2] | (c[3] << 7), c[4] | (c[5] << 7))
                i = j + 2 + P.BYTES_SONAR
            elif idx == P.IDX_INSPECAO:
                if j + 2 + P.BYTES_INSPECAO > n:
                    i = j
                    break
                c = buf[j + 2:j + 2 + P.BYTES_INSPECAO]
                if any(b > 0x7F for b in c) or c[0] > 2:
                    i = j + 1
                    continue
                self._ao_inspecao(45 + 45 * c[0], c[1] | (c[2] << 7), c[3] | (c[4] << 7))
                i = j + 2 + P.BYTES_INSPECAO
            elif idx == P.IDX_SERVO:
                if j + 2 + P.BYTES_SERVO > n:
                    i = j
                    break
                c = buf[j + 2:j + 2 + P.BYTES_SERVO]
                if any(b > 0x7F for b in c):
                    i = j + 1
                    continue
                self._ao_servo(c[0] | (c[1] << 7), c[2] | (c[3] << 7), c[4])
                i = j + 2 + P.BYTES_SERVO
            elif idx == P.IDX_MOTORES:
                if j + 2 + P.BYTES_MOTORES > n:
                    i = j
                    break
                c = buf[j + 2:j + 2 + P.BYTES_MOTORES]
                if any(b > 0x7F for b in c) or c[1] > 1 or c[3] > 1:
                    i = j + 1
                    continue
                self._ao_motores(c[0] | (c[1] << 7), c[2] | (c[3] << 7), c[4])
                i = j + 2 + P.BYTES_MOTORES
            elif idx == P.IDX_SENSORES:
                if j + 2 + P.BYTES_SENSORES > n:
                    i = j
                    break
                c = buf[j + 2:j + 2 + P.BYTES_SENSORES]
                if 0xFF in c:                            # byte perdido: ressincroniza
                    i = j + 1
                    continue
                self._ao_sensores(c[0] | (c[1] << 7), c[2] | (c[3] << 7),
                                  c[4] | (c[5] << 7), c[6])
                i = j + 2 + P.BYTES_SENSORES
            else:                                        # lixo depois de 0xFF
                i = j + 1
        del buf[:i]

    def _linha(self, idx: int, corpo) -> None:
        b = np.frombuffer(bytes(corpo), np.uint8)
        linha = self._img[idx]
        linha[0::2] = (b >> 4) * 17                      # 0..15 -> 0..255
        linha[1::2] = (b & 0x0F) * 17
        self._recebida[idx] = True
        self._est["linhas_ok"] += 1

    def _fim_quadro(self) -> None:
        esperadas = np.arange(cfg.FW_LINHA_INICIAL, P.IMG_ALTURA)
        faltando = int((~self._recebida[esperadas]).sum())
        if faltando <= len(esperadas) * 0.2:
            img = self._img.copy()
            for y in esperadas:                          # preenche linhas perdidas com a anterior
                if not self._recebida[y]:
                    img[y] = img[y - 1] if y > 0 else 0
            if cfg.IMAGEM_ESPELHAR_H:
                img = img[:, ::-1]
            if cfg.IMAGEM_ESPELHAR_V:
                img = img[::-1, :]
            self._est["quadros"] += 1
            self._ao_quadro(np.ascontiguousarray(img))
        else:
            self._est["quadros_incompletos"] += 1
        self._recebida[:] = False
