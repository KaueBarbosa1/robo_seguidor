"""Supervisor de segurança: decide, a cada quadro, se a tentativa deve ser interrompida.

Nenhuma regra aqui depende da opinião da CNN: usam o professor (OpenCV), os encoders, o ultrassom e o relógio.
É assim que o sistema sabe que uma tentativa deu errado, mesmo quando é a CNN quem está dirigindo.
"""
from collections import deque
from dataclasses import dataclass

import config as cfg


@dataclass
class Observacao:
    t: float                          # tempo desde o início da tentativa (s)
    quadro_idade_s: float             # quão velho é o quadro usado (s)
    prof_visivel: bool                # o professor (OpenCV) viu a linha neste quadro
    e_prof: float | None              # erro lateral medido pelo professor (-1..1)
    controlador: str                  # 'professor' | 'aluno' | 'mantido' ...
    steer_cmd: float                  # direção enviada aos motores (-1..1)
    movendo: bool                     # há comando de avanço
    ticks_delta: int | None = None    # pulsos dos encoders desde o passo anterior (None = sem encoder)
    obstaculo: bool = False
    sobre_pista: bool | None = None   # sensor independente sob o chassi (opcional); None = não existe


@dataclass
class Veredito:
    parar: bool = False
    motivo: str | None = None
    falha: bool = False               # True = saiu da pista / comportamento inseguro (conta como falha)
    causa_aluno: bool = False         # a CNN dirigia nos quadros imediatamente antes


class Supervisor:
    def __init__(self):
        self.reiniciar()

    def reiniciar(self) -> None:
        self._sem_linha = 0
        self._diverg = 0
        self._parado = 0
        self._fora = 0
        self._ctrl = deque(maxlen=5)
        self._steers = deque(maxlen=cfg.APR_OSC_JANELA)

    def avaliar(self, o: Observacao) -> Veredito:
        self._ctrl.append(o.controlador)
        self._steers.append(o.steer_cmd)
        aluno = sum(c.startswith("aluno") for c in self._ctrl) >= 0.6 * len(self._ctrl)

        def v(motivo, falha):
            return Veredito(True, motivo, falha, falha and aluno)

        if o.quadro_idade_s > cfg.APR_IDADE_MAX_QUADRO_S:
            return v("sem_quadros", False)
        if o.obstaculo:
            return v("obstaculo", False)
        if o.t >= cfg.APR_TEMPO_MAX_S:
            return v("concluida", False)

        self._fora = self._fora + 1 if o.sobre_pista is False else 0
        if self._fora >= 2:
            return v("fora_da_pista", True)

        self._sem_linha = 0 if o.prof_visivel else self._sem_linha + 1
        if self._sem_linha > cfg.APR_MAX_QUADROS_SEM_LINHA:
            return v("linha_perdida", True)

        grande = o.prof_visivel and o.e_prof is not None and abs(o.e_prof) > cfg.APR_ERRO_DIVERGENCIA
        self._diverg = self._diverg + 1 if grande else 0
        if self._diverg >= cfg.APR_QUADROS_DIVERGENCIA:
            return v("divergencia", True)

        s = [x for x in self._steers if abs(x) > 0.3]
        trocas = sum(1 for a, b in zip(s, s[1:]) if a * b < 0)
        if len(self._steers) == cfg.APR_OSC_JANELA and trocas >= cfg.APR_OSC_TROCAS:
            return v("oscilacao", True)

        if o.movendo and o.ticks_delta is not None:
            self._parado = self._parado + 1 if o.ticks_delta < 1 else 0
            if self._parado >= cfg.APR_PARADO_PASSOS:
                return v("parado", False)
        return Veredito()
