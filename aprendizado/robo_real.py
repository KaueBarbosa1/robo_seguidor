"""Adaptador do aprendizado para o robô REAL (Pi 5 + Arduino com a OV7670 e os motores) e a thread que roda as tentativas.

Divisão de responsabilidades (a hierarquia voz > resto é mantida):
  * esta thread NUNCA escreve nos motores: ela publica a ação (direção, fator de velocidade) no EstadoRobo;
    o ThreadControle é o único que fala com o Arduino e para os motores se a ação ficar velha;
  * voz "siga"  -> começa uma tentativa;  voz "pare"/giro/ré -> a tentativa termina como 'parada_manual';
  * o supervisor interrompe a tentativa por conta própria (linha perdida, divergência, obstáculo...);
  * o TREINO só roda com o robô parado, entre tentativas, nesta mesma thread (com prioridade baixa).
O carrinho não se reposiciona sozinho: depois de cada tentativa, um humano o coloca no início e diz "siga".

ATENÇÃO: este arquivo foi verificado só contra o simulador do Arduino e o simulador sintético. Nunca rodou no
robô físico nem na pista real.
"""
import logging
import os
import threading
import time
from pathlib import Path

import numpy as np

import config as cfg
from aprendizado.ciclo import CicloAprendizado, TentativaAbortada, executar_tentativa
from controle import aplicar_comando
from estado import EstadoRobo, Modo
from visao.detector import DetectorLinha

log = logging.getLogger("aprendizado")


class AmbienteReal:
    """Interface de ambiente de executar_tentativa(): motor/sensores = ArduinoSerial, imagem = fonte (OV7670 via serial)."""

    def __init__(self, estado: EstadoRobo, motor, parar: threading.Event, fonte):
        self._estado, self._motor, self._parar, self._fonte = estado, motor, parar, fonte
        self._ultimo_id = 0
        self._t0 = time.monotonic()
        self._t_quadro = self._t0
        self._ult = None
        self._ticks_ant = None
        self._t_ultimo_passo = -1e9

    def iniciar(self) -> None:
        self._t0 = self._t_quadro = time.monotonic()
        self._ultimo_id = self._fonte.id_atual() + 1          # o quadro em andamento é velho: espera o próximo
        self._t_ultimo_passo = -1e9
        self._ult = None
        s = self._motor.sensores()
        self._ticks_ant = (s.ticks_esq, s.ticks_dir) if s else None

    def _continua(self) -> bool:
        return self._estado.modo is Modo.SEGUINDO and not self._parar.is_set()

    def quadro(self):
        """Espera o próximo quadro; devolve (imagem, idade_s, t). Sem quadros, devolve o velho com idade crescente."""
        while True:
            if not self._continua():
                raise TentativaAbortada()
            q = self._fonte.proximo_quadro(self._ultimo_id, timeout=0.25)
            agora = time.monotonic()
            if q is not None:
                self._ultimo_id, img = q
                self._t_quadro, self._ult = agora, img
                if agora - self._t_ultimo_passo < cfg.APR_PERIODO_MIN_S:
                    continue                                     # câmera rápida: descarta quadros entre os passos
                self._t_ultimo_passo = agora
                return img, 0.0, agora - self._t0
            if self._ult is not None and agora - self._t_quadro > cfg.APR_IDADE_MAX_QUADRO_S:
                return self._ult, agora - self._t_quadro, agora - self._t0       # o supervisor encerra: sem_quadros
            if self._ult is None and agora - self._t0 > 3.0:
                raise TentativaAbortada()                                        # câmera nunca entregou nada

    def aplicar(self, steer: float, vel_fator: float) -> None:
        self._estado.publicar_acao(steer, vel_fator)

    def ticks_delta(self):
        s = self._motor.sensores()
        if s is None or self._ticks_ant is None:
            return None
        d = (s.ticks_esq - self._ticks_ant[0]) + (s.ticks_dir - self._ticks_ant[1])
        self._ticks_ant = (s.ticks_esq, s.ticks_dir)
        return d // 2

    def obstaculo(self) -> bool:
        return bool(cfg.OBSTACULO_ATIVO and self._motor.obstaculo(cfg.OBSTACULO_DIST_CM, cfg.OBSTACULO_LEITURAS))

    def sobre_pista(self):
        return None                                  # sem sensor de piso sob o chassi (opcional, veja docs/04)

    def parar(self) -> None:
        aplicar_comando(self._estado, self._motor, "pare")


class ThreadAprendizado(threading.Thread):
    def __init__(self, estado: EstadoRobo, motor, parar: threading.Event, fonte):
        super().__init__(name="aprendizado", daemon=True)
        self._estado, self._motor, self._parar, self._fonte = estado, motor, parar, fonte

    def run(self) -> None:
        try:
            os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 10)       # treino não atrapalha voz/controle
        except (AttributeError, OSError, PermissionError):
            pass
        try:
            self._loop()
        except Exception:
            log.exception("Thread de aprendizado caiu")
            self._parar.set()

    def _loop(self) -> None:
        rng = np.random.default_rng()
        ciclo = CicloAprendizado(Path(cfg.APR_DIR), rng)
        det = DetectorLinha()
        amb = AmbienteReal(self._estado, self._motor, self._parar, self._fonte)
        log.info("Aprendizado ativo (nível %d, campeão %s). Posicione o carrinho no início da pista e diga 'siga'.",
                 ciclo.e["nivel"], ciclo.reg.campeao_id())
        while not self._parar.is_set():
            if self._estado.modo is not Modo.SEGUINDO:
                time.sleep(0.1)
                continue
            resumo = executar_tentativa(amb, ciclo, det, rng)
            for e in ciclo.registrar_resultado(resumo):
                log.warning("%s", e)
            log.info("Tentativa %s: %s (%s), %d passos, erro médio %.2f, autonomia %.0f%%, pontuação %.3f",
                     resumo.get("episodio"), resumo["tipo"], resumo["motivo"], resumo["n_passos"],
                     resumo["erro_medio"], 100 * resumo["autonomia"], resumo["pontuacao"])
            if self._estado.modo is not Modo.PARADO:
                continue                                       # o operador já mandou outra coisa
            for e in ciclo.treinar_se_preciso():
                log.warning("%s", e)
            log.info("Reposicione o carrinho no início da pista e diga 'siga' para a próxima tentativa.")
            while self._estado.modo is Modo.SEGUINDO and not self._parar.is_set():
                time.sleep(0.1)                                # (se já disse 'siga' durante o treino, começa)
