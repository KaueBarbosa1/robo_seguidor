import numpy as np
import pytest

pytest.importorskip('gymnasium')
from aprendizado.ambiente_gym import AmbienteLinhaGym
from aprendizado.rl_simulado import ACOES


class ReferenciaFalsa:
    def prever(self, x):
        return np.full(len(x), .2), np.ones(len(x))


def test_reset_reproduz_cenario_e_observacao_normalizada():
    env = AmbienteLinhaGym(ReferenciaFalsa(), pistas=(20, 21))
    obs, info = env.reset(seed=7)
    pose = (env.simulacao.fisica.x, env.simulacao.fisica.y)
    assert env.observation_space.contains(obs)
    outro, outra_info = env.reset(seed=7)
    np.testing.assert_array_equal(obs, outro)
    assert info == outra_info and pose == (env.simulacao.fisica.x, env.simulacao.fisica.y)
    for _ in range(3):
        obs, *_ = env.step(0)
        assert env.observation_space.contains(obs)
    with pytest.raises(ValueError, match='divisão'):
        env.reset(options={'pista': 500})
    env.close()


def test_timeout_trunca_e_saida_da_pista_termina():
    env = AmbienteLinhaGym(ReferenciaFalsa(), max_passos=1)
    env.reset(seed=7)
    _, _, terminou, truncado, info = env.step(0)
    assert not terminou and truncado and info['parado']
    with pytest.raises(RuntimeError, match='reset'):
        env.step(0)
    env.reset(seed=7)
    env.simulacao.fisica.fora_verdade = True
    _, _, terminou, truncado, _ = env.step(0)
    assert terminou and not truncado
    env.close()


def test_predicao_vencida_e_acoes_ficam_visiveis_sem_posicao_real():
    env = AmbienteLinhaGym(ReferenciaFalsa())
    env.reset(seed=7)
    env.simulacao.idade = 20
    obs = env.observacao()
    assert obs[3] == 1 and obs[4] == -1
    env.simulacao.fisica.x += .1
    np.testing.assert_array_equal(obs, env.observacao())
    _, _, _, _, info = env.step(len(ACOES) - 1)
    assert info['bloqueada'] and env.simulacao.fisica.cmd_vel == 0
    with pytest.raises(ValueError, match='discreto'):
        env.step(len(ACOES))
    env.close()
