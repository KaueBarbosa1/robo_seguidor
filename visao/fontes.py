"""Fontes de imagem para a visão. Todas oferecem  id_atual()  e  proximo_quadro(apos_id, timeout).

  arduino  : OV7670 ligada ao Arduino; a imagem chega pela serial (ArduinoSerial já tem id_atual/proximo_quadro) <- a atual.
  csi      : câmera no conector CSI da Pi (Raspberry Pi Camera Rev 1.3), via picamera2. Código mantido, NÃO é a câmera do projeto.
  esp32    : JPEG HTTP contínuo, somente o quadro recente.
  nenhuma  : sem câmera.
  simulada : linha sintética que serpenteia, para testar visão/controle sem câmera.
"""
import threading
import time

import cv2
import numpy as np

from motor import protocolo as P


class FonteSimulada:
    def __init__(self, fps: float = 10.0):
        self._periodo = 1.0 / fps
        self._id = 0
        self._t0 = time.monotonic()
        self._ultimo = 0.0
        self._lock = threading.Lock()

    def id_atual(self) -> int:
        return self._id

    def _gerar(self) -> np.ndarray:
        t = time.monotonic() - self._t0
        img = np.full((P.IMG_ALTURA, P.IMG_LARGURA), 220, np.uint8)
        for y in range(P.IMG_ALTURA):
            x = int(P.IMG_LARGURA / 2 + 40 * np.sin(t * 0.8 + y / 25.0))
            cv2.line(img, (x, y), (x, y), 20, 9)
        img = (img // 17) * 17                        # simula os 4 bits da câmera
        return (img + np.random.randint(-8, 9, img.shape)).clip(0, 255).astype(np.uint8)

    def proximo_quadro(self, apos_id: int, timeout: float = 1.0):
        falta = self._ultimo + self._periodo - time.monotonic()
        if falta > 0:
            time.sleep(min(falta, timeout))
        with self._lock:
            self._id += 1
            self._ultimo = time.monotonic()
            return self._id, self._gerar()


class FonteNenhuma:
    """Sem câmera: nunca entrega quadro. A visão fica avisando 'sem quadros' e o robô não segue linha
    (comandos de voz de manobra e testes de motor continuam funcionando)."""

    def id_atual(self) -> int:
        return 0

    def proximo_quadro(self, apos_id: int, timeout: float = 1.0):
        time.sleep(timeout)
        return None


def criar_fonte(nome: str, motor=None):
    if nome == "arduino":
        if motor is None or not hasattr(motor, "proximo_quadro"):
            raise ValueError("FONTE_IMAGEM='arduino' precisa do ArduinoSerial (sem --sem-arduino)")
        return motor
    if nome == "esp32":
        import config as cfg
        from visao.esp32_cam import CameraESP32
        return CameraESP32(cfg.ESP32_URL, cfg.ESP32_TIMEOUT_S,
                           cfg.ESP32_IDADE_MAX_S, cfg.ESP32_RECONEXAO_S)
    if nome == "csi":
        from visao.camera_csi import CameraCSI
        return CameraCSI()
    if nome == "nenhuma":
        return FonteNenhuma()
    if nome == "simulada":
        return FonteSimulada()
    raise ValueError(f"FONTE_IMAGEM inválida: {nome!r} (use 'arduino', 'csi', 'nenhuma', 'simulada' ou 'esp32')")
