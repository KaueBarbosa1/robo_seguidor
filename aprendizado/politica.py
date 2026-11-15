"""Quem dirige a cada quadro: o professor (OpenCV) ou a CNN, com portão de segurança.

Níveis de autonomia (config.APR_NIVEIS / APR_PORTAO):
  0      só o professor dirige (coleta de dados). É o nível inicial, antes de existir uma CNN.
  1..3   a CNN dirige em parte dos quadros, mas só quando concorda com o professor dentro do portão;
         se discorda além do portão, o professor assume (isso conta como INTERVENÇÃO e vira dado de treino).
  4      sem portão: a CNN dirige sozinha; o professor continua medindo o erro (supervisor de segurança).
Nos vãos do pontilhado o professor fica cego; aí a CNN é quem conduz, se achar que ainda há linha à frente.
"""
from dataclasses import dataclass

import numpy as np

import config as cfg


@dataclass
class Decisao:
    steer: float
    origem: str                       # professor | professor_portao | aluno | aluno_vao | mantido
    steer_prof: float | None = None
    steer_aluno: float | None = None
    p_visivel: float | None = None
    vel_fator: float = 1.0


def direcao_do_professor(e_prof: float) -> float:
    return float(np.clip(cfg.APR_GANHO_PROF * e_prof, -1.0, 1.0))


def direcao_para_pwm(steer: float, vel_fator: float = 1.0) -> tuple[int, int]:
    """direção [-1,1] (positivo = linha à direita = virar à direita) -> PWM (esquerda, direita)."""
    base = cfg.APR_VEL * vel_fator
    esq = base + steer * cfg.APR_GANHO_DIRECAO
    dir_ = base - steer * cfg.APR_GANHO_DIRECAO
    return (int(max(-cfg.VEL_MAX, min(cfg.VEL_MAX, esq))), int(max(-cfg.VEL_MAX, min(cfg.VEL_MAX, dir_))))


class PoliticaAprendiz:
    def __init__(self, rede, nivel: int, rng: np.random.Generator):
        self.rede = rede if nivel > 0 else None
        self.nivel = nivel if rede is not None else 0
        self.rng = rng
        self.ultimo_steer = 0.0

    def decidir(self, entrada: np.ndarray | None, e_prof: float | None, prof_visivel: bool) -> Decisao:
        steer_prof = direcao_do_professor(e_prof) if prof_visivel and e_prof is not None else None
        steer_aluno = p_vis = None
        if self.rede is not None and entrada is not None:
            d, p = self.rede.prever(entrada)
            steer_aluno, p_vis = float(d[0]), float(p[0])
        frac = cfg.APR_NIVEIS[self.nivel]
        portao = cfg.APR_PORTAO[self.nivel]
        quer_aluno = steer_aluno is not None and self.rng.random() < frac

        if steer_prof is not None:
            if quer_aluno and abs(steer_aluno - steer_prof) <= portao:
                steer, origem = steer_aluno, "aluno"
            elif quer_aluno:
                steer, origem = steer_prof, "professor_portao"        # intervenção
            else:
                steer, origem = steer_prof, "professor"
        else:                                                         # vão do pontilhado: o professor não vê
            if quer_aluno and p_vis >= 0.5:
                steer, origem = steer_aluno, "aluno_vao"
            else:
                steer, origem = self.ultimo_steer, "mantido"
        self.ultimo_steer = steer
        return Decisao(steer, origem, steer_prof, steer_aluno, p_vis, vel_fator=1.0 - 0.4 * abs(steer))
