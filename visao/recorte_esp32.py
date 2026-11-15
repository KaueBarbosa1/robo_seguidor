"""Geometria da prévia para calibrar a ESP32-CAM montada."""
from dataclasses import dataclass

import cv2

RESOLUCAO = (320, 240)  # largura, altura do JPEG
ENTRADA = (80, 40)
VERSAO_PREVIA = "esp32_roi_cinza_area_v1"


@dataclass(frozen=True)
class RecorteESP32:
    x: int = 0
    y: int = 80
    largura: int = 320
    altura: int = 160
    espelhar_h: bool = False
    espelhar_v: bool = False

    def __post_init__(self):
        if not (self.largura == 2 * self.altura > 0
                and 0 <= self.x <= RESOLUCAO[0] - self.largura
                and 0 <= self.y <= RESOLUCAO[1] - self.altura):
            raise ValueError("a ROI deve ser 2:1 e caber na imagem 320x240")

    def orientar(self, imagem):
        if self.espelhar_h and self.espelhar_v:
            return cv2.flip(imagem, -1)
        if self.espelhar_h:
            return cv2.flip(imagem, 1)
        if self.espelhar_v:
            return cv2.flip(imagem, 0)
        return imagem

    def reduzir(self, orientada):
        roi = orientada[self.y:self.y + self.altura, self.x:self.x + self.largura]
        cinza = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        return cv2.resize(cinza, ENTRADA, interpolation=cv2.INTER_AREA)
