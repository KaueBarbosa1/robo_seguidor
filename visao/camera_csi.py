"""Fonte de imagem: câmera no conector CSI da Raspberry Pi 5 (Raspberry Pi Camera Rev 1.3 = sensor OV5647).

Usa a biblioteca picamera2 (no Raspberry Pi OS: sudo apt install python3-picamera2). Entrega ao resto do robô a MESMA
coisa que antes vinha do Arduino: um quadro cinza uint8 de 120x160, com  id_atual()  e  proximo_quadro(apos_id, timeout).

Como o quadro é obtido: o ISP da Pi reduz a imagem (stream "lores", YUV420, 320x240); pegamos só o plano Y (luminância,
já em tons de cinza de 8 bits) e reduzimos para 160x120 com média de área. O sensor roda a CAMERA_FPS (ex.: 30).

NÃO testado com a câmera real (não havia hardware): foi testado só com uma câmera falsa que imita a interface do picamera2.
"""
import logging
import threading
import time

import cv2
import numpy as np

import config as cfg

log = logging.getLogger("camera")

ALTURA, LARGURA = 120, 160


def y_do_yuv420(yuv: np.ndarray, altura: int, largura: int) -> np.ndarray:
    """Plano Y de um quadro YUV420 do picamera2 (forma (altura*3//2, largura_com_stride))."""
    return yuv[:altura, :largura]


def para_quadro_cinza(y: np.ndarray) -> np.ndarray:
    """Plano Y (qualquer tamanho) -> 120x160 uint8, com espelhamento opcional (config)."""
    q = cv2.resize(np.ascontiguousarray(y), (LARGURA, ALTURA), interpolation=cv2.INTER_AREA)
    if cfg.IMAGEM_ESPELHAR_H:
        q = cv2.flip(q, 1)
    if cfg.IMAGEM_ESPELHAR_V:
        q = cv2.flip(q, 0)
    return q


class CameraCSI:
    def __init__(self, fabrica=None):
        """fabrica: função sem argumentos que devolve um objeto com a interface do Picamera2 (usado em testes)."""
        self._fabrica = fabrica
        self._cam = None
        self._cond = threading.Condition()
        self._quadro: np.ndarray | None = None
        self._quadro_id = 0
        self._quadro_t = 0.0
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None
        self.status = "parada"
        self.estatisticas = {"quadros": 0, "erros": 0, "reaberturas": 0}

    # ------------------------------------------------------------ ciclo de vida
    def iniciar(self) -> None:
        self._abrir()
        self._thread = threading.Thread(target=self._loop, name="camera-csi", daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._parar.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._fechar_camera()

    def _criar(self):
        if self._fabrica is not None:
            return self._fabrica()
        try:
            from picamera2 import Picamera2
        except ImportError as e:
            raise RuntimeError("picamera2 não encontrado. Instale com:  sudo apt install -y python3-picamera2 "
                               "(e use o Python do sistema, não um venv sem --system-site-packages)") from e
        return Picamera2()

    def _abrir(self) -> None:
        cam = self._criar()
        lw, lh = cfg.CAMERA_LORES
        config = cam.create_video_configuration(
            main={"size": cfg.CAMERA_PRINCIPAL},
            lores={"size": (lw, lh), "format": "YUV420"},
            controls=self._controles(),
            buffer_count=4,
        )
        cam.configure(config)
        cam.start()
        self._cam = cam
        self.status = "ok"
        log.info("Câmera CSI aberta: lores %dx%d, %s fps", lw, lh, cfg.CAMERA_FPS)

    def _controles(self) -> dict:
        c = {"FrameRate": float(cfg.CAMERA_FPS)}
        if cfg.CAMERA_EXPOSICAO_US:                     # exposição fixa (evita o brilho "respirar" na pista)
            c["AeEnable"] = False
            c["ExposureTime"] = int(cfg.CAMERA_EXPOSICAO_US)
            if cfg.CAMERA_GANHO:
                c["AnalogueGain"] = float(cfg.CAMERA_GANHO)
        return c

    def _fechar_camera(self) -> None:
        cam, self._cam = self._cam, None
        if cam is not None:
            try:
                cam.stop()
                cam.close()
            except Exception:                           # câmera já caída: nada a fazer
                log.debug("erro ao fechar a câmera", exc_info=True)

    # ------------------------------------------------------------ captura
    def _loop(self) -> None:
        lw, lh = cfg.CAMERA_LORES
        falhas = 0
        while not self._parar.is_set():
            try:
                yuv = self._cam.capture_array("lores")
                self._publicar(para_quadro_cinza(y_do_yuv420(yuv, lh, lw)))
                falhas = 0
            except Exception:
                self.estatisticas["erros"] += 1
                falhas += 1
                self.status = "erro"
                if falhas == 1 or falhas % 20 == 0:
                    log.exception("Falha ao capturar quadro (%d seguidas)", falhas)
                if falhas >= 3:                         # tenta reabrir a câmera
                    self._fechar_camera()
                    time.sleep(1.0)
                    try:
                        self._abrir()
                        self.estatisticas["reaberturas"] += 1
                        falhas = 0
                    except Exception:
                        log.exception("Não foi possível reabrir a câmera")
                else:
                    time.sleep(0.2)

    def _publicar(self, img: np.ndarray) -> None:
        with self._cond:
            self._quadro = img
            self._quadro_id += 1
            self._quadro_t = time.monotonic()
            self.estatisticas["quadros"] += 1
            self._cond.notify_all()

    # ------------------------------------------------------------ interface de "fonte"
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
