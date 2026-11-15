"""Motor "nulo": mesma interface do ArduinoSerial, mas sem hardware. Só registra o que seria enviado.

Serve para testar na Pi, SEM Arduino ligado, a câmera, a visão, a voz e o controle (python main.py --sem-arduino).
Não move nada e não lê sensores (sensores() = None, obstaculo() = False).
"""
import logging
import threading
import time

log = logging.getLogger("motor-nulo")


class ArduinoNulo:
    def __init__(self):
        self.estatisticas = {"comandos": 0}
        self.ultimo = (0, 0)
        self._lock = threading.Lock()
        self._t_log = 0.0

    def conectar(self) -> None:
        log.warning("MODO SEM ARDUINO: nenhum comando chega a motor nenhum (só registro em log).")

    def fechar(self) -> None:
        pass

    def motores(self, esq: int, dir_: int) -> None:
        with self._lock:
            self.ultimo = (int(esq), int(dir_))
            self.estatisticas["comandos"] += 1
        agora = time.monotonic()
        if agora - self._t_log > 1.0:                      # no máximo 1 linha por segundo
            self._t_log = agora
            log.info("motores esq=%+d dir=%+d (simulado)", esq, dir_)

    def parar(self, repetir: int = 1) -> None:
        with self._lock:
            ja_parado = self.ultimo == (0, 0)
            self.ultimo = (0, 0)
        if not ja_parado:
            log.info("PARAR (simulado)")

    def avisar(self, tipo: int) -> None:
        pass

    def buzinar(self, ligada: bool = True) -> None:
        log.info("Buzina %s (simulada)", "ligada" if ligada else "desligada")

    def sensores(self):
        return None

    def obstaculo(self, limite_cm: float, leituras: int) -> bool:
        return False
