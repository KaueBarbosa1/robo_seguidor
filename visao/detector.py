"""Módulo de visão: acha a linha no frame e mede o erro de direção.

Esta thread NÃO fala com o Arduino. Ela só publica no EstadoRobo o erro medido;
quem converte erro em comando e escreve na serial é o controle (controle.py).
Assim existe um único ponto de decisão e a hierarquia "voz > visão" fica garantida.
"""
import logging
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np

import config as cfg
from estado import EstadoRobo, Modo

log = logging.getLogger("visao")


@dataclass
class ResultadoLinha:
    achou: bool
    erro: float = 0.0                 # normalizado -1..+1 (positivo = linha à direita)
    cx: float = 0.0
    cy: float = 0.0                   # em coordenadas do frame inteiro
    binaria: np.ndarray | None = None
    contorno: np.ndarray | None = None
    y0: int = 0


class DetectorLinha:
    def __init__(self):
        k = cfg.BLUR_KERNEL | 1       # garante ímpar
        self._k = (k, k)
        self._kernel = np.ones((3, 3), np.uint8)
        self._tipo = cv2.THRESH_BINARY_INV if cfg.LINHA_ESCURA else cv2.THRESH_BINARY

    def processar(self, frame: np.ndarray) -> ResultadoLinha:
        h, w = frame.shape[:2]
        y0 = int(h * cfg.ROI_INICIO)
        roi = frame[y0:, :]

        cinza = roi if roi.ndim == 2 else cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        suave = cv2.GaussianBlur(cinza, self._k, 0)
        if int(suave.max()) - int(suave.min()) < cfg.CONTRASTE_MIN:   # piso liso: não há linha
            return ResultadoLinha(False, binaria=np.zeros_like(suave), y0=y0)
        if cfg.USAR_OTSU:
            _, binaria = cv2.threshold(suave, 0, 255, self._tipo + cv2.THRESH_OTSU)
        else:
            _, binaria = cv2.threshold(suave, cfg.LIMIAR_FIXO, 255, self._tipo)
        binaria = cv2.morphologyEx(binaria, cv2.MORPH_OPEN, self._kernel)   # tira ruído fino

        contornos, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contornos:
            return ResultadoLinha(False, binaria=binaria, y0=y0)

        maior = max(contornos, key=cv2.contourArea)
        if cv2.contourArea(maior) < cfg.AREA_MIN:
            return ResultadoLinha(False, binaria=binaria, y0=y0)

        m = cv2.moments(maior)
        if m["m00"] == 0:
            return ResultadoLinha(False, binaria=binaria, y0=y0)

        # a mancha precisa ser de fato diferente do piso: sem isto, ruído + vinheta da lente viram "linha" falsa
        mascara = np.zeros(suave.shape, np.uint8)
        cv2.drawContours(mascara, [maior], -1, 255, -1)
        dentro, fora = suave[mascara > 0], suave[mascara == 0]
        if fora.size and abs(float(fora.mean()) - float(dentro.mean())) < cfg.CONTRASTE_MIN:
            return ResultadoLinha(False, binaria=binaria, y0=y0)

        cx = m["m10"] / m["m00"]
        cy = m["m01"] / m["m00"] + y0
        centro = w / 2.0
        erro = (cx - centro) / centro
        return ResultadoLinha(True, erro, cx, cy, binaria, maior, y0)


def desenhar_debug(frame: np.ndarray, r: ResultadoLinha) -> np.ndarray:
    saida = frame.copy() if frame.ndim == 3 else cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    h, w = saida.shape[:2]
    cv2.line(saida, (w // 2, 0), (w // 2, h), (255, 0, 0), 1)           # centro da tela
    cv2.line(saida, (0, r.y0), (w, r.y0), (0, 255, 255), 1)             # início da ROI
    if r.achou:
        cv2.drawContours(saida[r.y0:, :], [r.contorno], -1, (0, 255, 0), 2)
        cv2.circle(saida, (int(r.cx), int(r.cy)), 5, (0, 0, 255), -1)
        cv2.putText(saida, f"erro={r.erro:+.2f}", (5, 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    return saida


class ThreadVisao(threading.Thread):
    """fonte: ArduinoSerial (OV7670), FonteSimulada ou CameraCSI. Só processa quando o modo é SEGUINDO."""

    def __init__(self, estado: EstadoRobo, parar: threading.Event, fonte):
        super().__init__(name="visao", daemon=True)
        self._estado = estado
        self._parar = parar
        self._fonte = fonte

    def run(self) -> None:
        try:
            self._loop()
        except Exception:
            log.exception("Thread de visão caiu")
            self._parar.set()                      # main para o robô todo

    def _loop(self) -> None:
        detector = DetectorLinha()
        ultimo_id = self._fonte.id_atual()
        suspensa = True
        sem_quadro = 0
        while not self._parar.is_set():
            if self._estado.modo is not Modo.SEGUINDO:
                suspensa = True
                time.sleep(0.05)
                continue

            if suspensa:                           # acabou de retomar: o quadro em andamento é velho
                ultimo_id = self._fonte.id_atual() + 1
                suspensa = False

            q = self._fonte.proximo_quadro(ultimo_id, timeout=0.5)
            if q is None:
                sem_quadro += 1
                if sem_quadro == 1 or sem_quadro % 10 == 0:
                    log.warning("Sem quadros da câmera (status=%s)", getattr(self._fonte, "status", None))
                self._estado.publicar_leitura(0.0, False)
                continue
            sem_quadro = 0
            ultimo_id, frame = q

            r = detector.processar(frame)
            self._estado.publicar_leitura(r.erro, r.achou)

            if cfg.MOSTRAR_DEBUG:
                cv2.imshow("visao", cv2.resize(desenhar_debug(frame, r), None, fx=3, fy=3,
                                               interpolation=cv2.INTER_NEAREST))
                cv2.waitKey(1)
