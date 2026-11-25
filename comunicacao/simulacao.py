"""Gerador de cenários, não modelo físico. Sem import/abertura de serial real."""
from dataclasses import dataclass
import math
import threading
import time
from types import SimpleNamespace

import cv2
from estado import EstadoRobo
from motor.nulo import ArduinoNulo
from monitoramento.telemetria import Telemetria
from visao.detector import DetectorLinha
from visao.fontes import FonteSimulada


@dataclass
class SensoresSimulados:
    distancia_cm: int
    ticks_esq: int
    ticks_dir: int
    timestamp: float
    avanco_bloqueado: bool
    falha_sensor: bool = False
    obstaculo_confirmado: bool = False


class MotorSimulado(ArduinoNulo):
    def __init__(self):
        super().__init__()
        self.inicio = time.monotonic()

    def sensores(self):
        t = time.monotonic()-self.inicio
        distancia = 10 if int(t) % 12 >= 9 else 100
        return SensoresSimulados(distancia, int(30*t+5*(1-math.cos(t))),
            int(32*t+4*(1-math.cos(t))), time.monotonic(), distancia < 25,
            obstaculo_confirmado=distancia < 25)

    def estado_motores(self):
        t = time.monotonic()-self.inicio
        return SimpleNamespace(pwm_esq=int(70+20*math.sin(t)), pwm_dir=int(70+20*math.cos(t)),
                               falha_encoder=False, pi_ativo=True, timestamp=time.monotonic())

    def status_servo(self):
        return SimpleNamespace(angulo_nominal=round(90+45*math.sin(time.monotonic()-self.inicio)),
                               timestamp=time.monotonic())


class CameraSimulada:
    """Uma geração/encode por quadro; todos os consumidores recebem os mesmos bytes."""
    def __init__(self, fps=30):
        self.fonte = FonteSimulada(fps)
        self.detector = DetectorLinha()
        self.estado = EstadoRobo()
        self.idade_max_s = .3
        self.lock = threading.Lock()
        self.fim = threading.Event()
        self.quadro = None
        self.ident = 0
        self.inicio = time.monotonic()
        self.thread = None

    def iniciar(self):
        self.thread = threading.Thread(target=self._loop, name='camera-simulada', daemon=True)
        self.thread.start()

    def _loop(self):
        while not self.fim.is_set():
            ident, imagem = self.fonte.proximo_quadro(self.ident)
            imagem = cv2.resize(imagem, (320, 240), interpolation=cv2.INTER_NEAREST)
            if int(time.monotonic()-self.inicio) % 8 >= 6:
                imagem[:] = 220
            r = self.detector.processar(imagem)
            self.estado.publicar_leitura(r.erro, r.achou, frame_id=ident, confianca=r.confianca)
            ok, jpeg = cv2.imencode('.jpg', imagem)
            if ok:
                q = SimpleNamespace(jpeg=jpeg.tobytes(), imagem=imagem,
                    recepcao_monotonica=time.monotonic(), idade_recepcao_limite_ms=0.)
                with self.lock:
                    self.ident, self.quadro = ident, q

    def proximo_jpeg_detalhado(self, apos_id, timeout=0):
        with self.lock:
            if self.quadro and self.ident > apos_id and time.monotonic()-self.quadro.recepcao_monotonica <= self.idade_max_s:
                return self.ident, self.quadro

    @property
    def estatisticas(self):
        with self.lock:
            return dict(quadros=self.ident, fps=self.ident/max(.001, time.monotonic()-self.inicio),
                        idade_ms=(time.monotonic()-self.quadro.recepcao_monotonica)*1000 if self.quadro else None)

    def parar(self):
        self.fim.set()
        if self.thread:
            self.thread.join(timeout=1)


def telemetria_simulada(camera):
    return Telemetria(camera.estado, MotorSimulado(), camera,
                      simulado=True, fonte_simulada=True)
