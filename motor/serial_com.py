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
        self._inspecao: dict[int, AmostraDirecional] = {}
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
    def _escrever(self, pacote: bytes, repetir: int = 1) -> None:
        for i in range(repetir):
            with self._lock_tx:
                if not self._ser or not self._ser.is_open:
                    return                              # a thread de leitura está reconectando
                try:
                    self._ser.write(pacote)
                except (serial.SerialException, OSError) as e:
                    log.error("Erro de escrita serial: %s", e)
                    self._ser = None                    # sinaliza para a thread de leitura reconectar
                    return
            if i + 1 < repetir:
                # O Arduino não escuta enquanto lê uma linha da câmera (~0,6 ms a cada ~3 ms).
                # Repetir espaçado garante que ao menos uma cópia chegue num intervalo livre.
                time.sleep(0.004)

    def motores(self, esq: int, dir_: int) -> None:
        esq = max(-cfg.VEL_MAX, min(cfg.VEL_MAX, int(esq)))
        dir_ = max(-cfg.VEL_MAX, min(cfg.VEL_MAX, int(dir_)))
        if cfg.CONTROLE_VELOCIDADE_ATIVO:
            if cfg.FIRMWARE_COM_CAMERA:
                raise RuntimeError("Encoders indisponiveis no firmware com camera")
            self.velocidade(round(esq * cfg.VELOCIDADE_REFERENCIA_PPS / 255),
                            round(dir_ * cfg.VELOCIDADE_REFERENCIA_PPS / 255))
        else:
            self._escrever(P.comando_motores(esq, dir_))

    def velocidade(self, esq: int, dir_: int) -> None:
        if cfg.FIRMWARE_COM_CAMERA:
            raise RuntimeError("Controle de velocidade exige firmware sem camera")
        self._escrever(P.comando_velocidade(esq, dir_))

    def parar(self, repetir: int = 1) -> None:
        self._escrever(P.comando_parar(), repetir)

    def avisar(self, tipo: int) -> None:
        self._escrever(P.comando_aviso(tipo))

    def buzinar(self, ligada: bool = True) -> None:
        self._escrever(P.comando_buzina(ligada))

    def configurar_servo(self, varrer: bool = False, ajuste_us: int = 0) -> None:
        self._escrever(P.comando_servo(varrer, ajuste_us))

    def inspecionar_obstaculo(self) -> None:
        self._escrever(P.comando_inspecao())

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

    def _ao_servo(self, angulo: int, centro_us: int, flags: int) -> None:
        with self._lock_sens:
            self._servo = StatusServo(angulo, centro_us, bool(flags & P.SERVO_FLAG_VARREDURA),
                                      bool(flags & P.SERVO_FLAG_CENTRO_PRONTO),
                                      bool(flags & P.SERVO_FLAG_ATIVO), time.monotonic(),
                                      bool(flags & P.SERVO_FLAG_INSPECAO),
                                      bool(flags & P.SERVO_FLAG_CONCLUIDA))

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
            if self._enc_ult is not None:           # soma a diferença, tratando a volta dos 14 bits
                self._ticks[0] += (enc_e - self._enc_ult[0]) % P.ENC_MODULO
                self._ticks[1] += (enc_d - self._enc_ult[1]) % P.ENC_MODULO
            self._enc_ult = (enc_e, enc_d)
            self._dists.append(d)
            self._sens = Sensores(d, self._ticks[0], self._ticks[1], time.monotonic(),
                                  bool(flags & P.SENSOR_FLAG_BLOQUEADO),
                                  bool(flags & P.SENSOR_FLAG_FALHA),
                                  bool(flags & P.SENSOR_FLAG_OBSTACULO))

    # ------------------------------------------------------------ leitura
    def _rx_loop(self) -> None:
        dec = DecodificadorQuadros(self._ao_quadro, self._ao_status, self.estatisticas,
                                  self._ao_sensores, self._ao_servo, self._ao_inspecao)
        while not self._parar_rx.is_set():
            ser = self._ser
            if ser is None:
                self._reconectar()
                continue
            try:
                dados = ser.read(max(1, min(4096, ser.in_waiting or 1)))
            except (serial.SerialException, OSError) as e:
                log.error("Erro de leitura serial: %s", e)
                with self._lock_tx:
                    self._ser = None
                continue
            if dados:
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

    def __init__(self, ao_quadro, ao_status=None, estat=None, ao_sensores=None, ao_servo=None, ao_inspecao=None):
        self._ao_quadro = ao_quadro
        self._ao_status = ao_status or (lambda c: None)
        self._ao_sensores = ao_sensores or (lambda d, e, r, f=0: None)
        self._ao_servo = ao_servo or (lambda a, c, f: None)
        self._ao_inspecao = ao_inspecao or (lambda a, d, r: None)
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
