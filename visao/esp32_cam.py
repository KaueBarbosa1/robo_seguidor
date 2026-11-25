"""Recepção HTTP compartilhada e fonte contínua ESP32, sem acesso aos motores."""
import threading
import time
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from http.client import HTTPException
from urllib.request import build_opener, ProxyHandler, Request
from urllib.error import URLError

import cv2
import numpy as np
from monitoramento import observar, contar

MAX_JPEG = 2 * 1024 * 1024
URL_PADRAO = "http://192.168.4.1/capture"
ERROS_RECEPCAO = (URLError, OSError, HTTPException, ValueError, TypeError, cv2.error)


@dataclass(frozen=True)
class QuadroESP32:
    jpeg: bytes
    imagem: np.ndarray
    recepcao_monotonica: float
    recepcao_utc: str
    http_ms: float
    idade_envio_ms: float

    @property
    def idade_recepcao_limite_ms(self):
        return self.idade_envio_ms + self.http_ms


def receber_quadro(opener, url, timeout):
    inicio = time.monotonic()
    req = Request(url, headers={"Cache-Control": "no-cache"})
    with opener.open(req, timeout=timeout) as resposta:
        if resposta.status != 200:
            raise ValueError(f"HTTP {resposta.status}")
        if resposta.headers.get_content_type() != "image/jpeg":
            raise ValueError("Resposta nao e image/jpeg")
        idade_envio = float(resposta.headers["X-Frame-Age-Us"]) / 1000
        dados = resposta.read(MAX_JPEG + 1)
        recepcao = time.monotonic()
        recepcao_utc = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    if not np.isfinite(idade_envio) or idade_envio < 0:
        raise ValueError("Idade do quadro invalida")
    if len(dados) > MAX_JPEG or not dados.startswith(b"\xff\xd8") or not dados.endswith(b"\xff\xd9"):
        raise ValueError("JPEG truncado ou invalido")
    observar('camera_http_s', recepcao-inicio)
    contar('camera_jpeg_rx_bytes', len(dados))
    inicio_decode = time.perf_counter()
    imagem = cv2.imdecode(np.frombuffer(dados, dtype=np.uint8), cv2.IMREAD_COLOR)
    observar('camera_decode_s', time.perf_counter()-inicio_decode)
    if imagem is None or imagem.shape[:2] != (240, 320):
        raise ValueError("JPEG invalido ou resolucao diferente de 320x240")
    return QuadroESP32(dados, imagem, recepcao, recepcao_utc, (recepcao - inicio) * 1000, idade_envio)


def receber(opener, url, timeout):
    quadro = receber_quadro(opener, url, timeout)
    return quadro.imagem, quadro.http_ms, quadro.idade_envio_ms, quadro.idade_recepcao_limite_ms

class CameraESP32:
    """Um único quadro, sem fila. A API legada entrega (id, imagem).

    Metadados são consultados pelo mesmo id; nunca se associa uma idade nova
    a uma imagem antiga. Não há redimensionamento nem alteração de orientação.
    """

    def __init__(self, url=URL_PADRAO, timeout=1., idade_max_s=.3,
                 reconexao_s=.5, opener=None):
        if any(not math.isfinite(v) or v <= 0 for v in
               (timeout, idade_max_s, reconexao_s)):
            raise ValueError("Prazos devem ser positivos e finitos")
        self.url, self.timeout = url, timeout
        self.idade_max_s, self.reconexao_s = idade_max_s, reconexao_s
        self._opener = opener or build_opener(ProxyHandler({}))
        self._cond = threading.Condition()
        self._fim = threading.Event()
        self._thread = None
        self._geracao = 0
        self._id = 0
        self._quadro = None
        self._status = "parada"
        self._inicio = None
        self._validos = self._erros = self._vencidos = 0
        self._http_ms = None
        self._resolucao = None

    def iniciar(self):
        with self._cond:
            if self._thread is not None:
                raise RuntimeError("Fonte já iniciada; crie outra após encerrar")
            self._inicio = time.monotonic()
            self._status = "conectando"
            self._thread = threading.Thread(target=self._loop, name="camera-esp32", daemon=True)
            self._thread.start()

    def parar(self):
        self._fim.set()
        with self._cond:
            self._quadro = None
            self._status = "parada"
            self._cond.notify_all()
        if self._thread:
            self._thread.join(timeout=self.timeout + .5)

    def _idade(self, q):
        return q.idade_recepcao_limite_ms / 1000 + max(0., time.monotonic() - q.recepcao_monotonica)

    def _invalidar(self, status):
        # Sob _cond. Uma falha seguida de recuperação não ressuscita a trajetória.
        if self._status != status or self._quadro is not None:
            self._geracao += 1
        self._quadro = None
        self._status = status
        self._cond.notify_all()

    def _status_atual(self):
        if self._status == "ok" and self._quadro is not None and self._idade(self._quadro) > self.idade_max_s:
            self._invalidar("vencida")
        if self._thread is not None and not self._thread.is_alive() and not self._fim.is_set():
            self._invalidar("erro")
        return self._status

    @property
    def status(self):
        with self._cond:
            return self._status_atual()

    def saude(self):
        with self._cond:
            return dict(status=self._status_atual(), geracao=self._geracao)

    @property
    def estatisticas(self):
        with self._cond:
            tempo = time.monotonic() - self._inicio if self._inicio is not None else 0.
            return dict(quadros=self._validos, erros=self._erros, vencidos=self._vencidos,
                        fps=self._validos / tempo if tempo > 0 else 0.,
                        http_ms=self._http_ms, resolucao=self._resolucao,
                        idade_ms=self._idade(self._quadro) * 1000 if self._quadro else None)

    def _loop(self):
        while not self._fim.is_set():
            try:
                q = receber_quadro(self._opener, self.url, self.timeout)
                with self._cond:
                    if self._fim.is_set():
                        return
                    self._status_atual()
                    self._http_ms = q.http_ms
                    self._resolucao = (q.imagem.shape[1], q.imagem.shape[0])
                    if self._idade(q) > self.idade_max_s:
                        self._vencidos += 1
                        self._invalidar("vencida")
                    else:
                        self._id += 1
                        self._quadro = q
                        self._validos += 1
                        self._status = "ok"
                    self._cond.notify_all()
            except ERROS_RECEPCAO:
                with self._cond:
                    if self._fim.is_set():
                        return
                    self._erros += 1
                    contar('camera_erros_recepcao')
                    self._invalidar("erro")
                    self._cond.notify_all()
                self._fim.wait(self.reconexao_s)

    def id_atual(self):
        with self._cond:
            return self._id

    def _metadados(self, q):
        return dict(recepcao_monotonica=q.recepcao_monotonica,
                    idade_limite_ms=self._idade(q) * 1000, http_ms=q.http_ms,
                    idade_captura_s=q.idade_recepcao_limite_ms / 1000,
                    geracao_camera=self._geracao)

    def metadados(self, quadro_id):
        """Metadados do id atual, sem associar um frame antigo a um horário novo."""
        with self._cond:
            if self._status_atual() != "ok" or quadro_id != self._id or self._quadro is None:
                return None
            return self._metadados(self._quadro)

    def proximo_quadro_detalhado(self, apos_id, timeout=1.):
        """Snapshot atômico (id, imagem, metadados); a imagem não é copiada."""
        with self._cond:
            self._cond.wait_for(lambda: self._fim.is_set() or
                                (self._id > apos_id and self._quadro is not None), timeout)
            if (self._fim.is_set() or self._status_atual() != "ok" or
                    self._quadro is None or self._id <= apos_id):
                return None
            return self._id, self._quadro.imagem, self._metadados(self._quadro)

    def proximo_jpeg_detalhado(self, apos_id, timeout=.2):
        """Snapshot original para coleta; compartilha captura, id e validade da visao."""
        with self._cond:
            self._cond.wait_for(lambda: self._fim.is_set() or
                                (self._id > apos_id and self._quadro is not None), timeout)
            if (self._fim.is_set() or self._status_atual() != "ok" or
                    self._quadro is None or self._id <= apos_id):
                return None
            return self._id, self._quadro

    def proximo_quadro(self, apos_id, timeout=1.):
        quadro = self.proximo_quadro_detalhado(apos_id, timeout)
        return quadro[:2] if quadro is not None else None
