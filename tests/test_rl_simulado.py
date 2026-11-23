import numpy as np

from aprendizado.rl_simulado import ACOES, AgenteQ, AmbienteRL


class ReferenciaFalsa:
    def __init__(self, visibilidade):
        self.visibilidade = visibilidade

    def prever(self, x):
        return np.array([.2]), np.array([self.visibilidade])


def test_q_aprende_recompensa_e_nao_bootstrap_terminal():
    agente = AgenteQ()
    estado = (0, 0, 0, 0, 0)
    proximo = (1, 0, 0, 0, 0)
    agente.q[proximo] = 100
    agente.atualizar(estado, 3, 2, proximo, True)
    np.testing.assert_allclose(agente.q[estado][3], .3)
    assert agente.escolher(estado) == 3


def test_guarda_abstencao_descarta_avanco_e_reset_limpa_memoria():
    ambiente = AmbienteRL(ReferenciaFalsa(0), 21, 71, 2)
    _, _, fim, info = ambiente.passo(len(ACOES) - 1)
    assert info['bloqueada'] and ambiente.fisica.cmd_vel == 0 and not fim
    assert ambiente.fisica.dist_percorrida == 0
    _, _, fim, _ = ambiente.passo(0)
    assert fim
    novo = AmbienteRL(ReferenciaFalsa(1), 21, 71, 2)
    assert novo.acao_anterior == 0 and novo.idade == 0


def test_estado_nao_contem_geometria_de_recompensa():
    ambiente = AmbienteRL(ReferenciaFalsa(1), 21, 71, 2)
    antes = ambiente.estado()
    ambiente.fisica.x += 1
    assert ambiente.estado() == antes
