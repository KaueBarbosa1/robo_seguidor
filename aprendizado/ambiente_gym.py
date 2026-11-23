"""Interface Gymnasium do ensaio sintético com referência CNN congelada."""
import gymnasium as gym
import numpy as np
from gymnasium import spaces

from aprendizado.rl_simulado import ACOES, AmbienteRL

CONTRATO_GYM = 'rl_cnn_gym_discreto_v1'


class AmbienteLinhaGym(gym.Env):
    metadata = {'render_modes': []}

    def __init__(self, referencia, pistas=range(10), max_passos=150):
        super().__init__()
        self.referencia = referencia
        self.pistas = tuple(pistas)
        if not self.pistas or max_passos < 1:
            raise ValueError('Informe pistas e limite de passos positivo')
        self.max_passos = max_passos
        self.action_space = spaces.Discrete(len(ACOES))
        self.observation_space = spaces.Box(-1., 1., shape=(7,), dtype=np.float32)
        self.simulacao = None
        self._finalizado = True

    def observacao(self):
        s = self.simulacao
        direcao, velocidade = ACOES[s.acao_anterior]
        valores = [s.erro, (s.erro - s.anterior) / 2,
                   2 * s.fisica.v / s.fisica.V_MAX - 1,
                   2 * min(s.idade / s.memoria_s, 1.) - 1,
                   1. if s.idade <= s.memoria_s else -1., direcao, 2 * velocidade - 1]
        return np.clip(valores, -1, 1).astype(np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        pista = (options or {}).get('pista')
        if pista is None:
            pista = int(self.np_random.choice(self.pistas))
        if pista not in self.pistas:
            raise ValueError('Pista fora da divisão deste ambiente')
        semente = int(self.np_random.integers(0, 2 ** 31 - 100001))
        self.simulacao = AmbienteRL(self.referencia, pista, semente, self.max_passos)
        self._finalizado = False
        return self.observacao(), {'pista': pista}

    def step(self, action):
        if self._finalizado:
            raise RuntimeError('Execute reset antes do próximo episódio')
        if not self.action_space.contains(action):
            raise ValueError('Ação fora do espaço discreto')
        _, recompensa, _, info = self.simulacao.passo(int(action))
        terminou = info['fora']
        truncado = bool(self.simulacao.passos >= self.max_passos and not terminou)
        self._finalizado = terminou or truncado
        info.update(velocidade_m_s=float(self.simulacao.fisica.v),
                    parado=abs(self.simulacao.fisica.v) < .005)
        return self.observacao(), float(recompensa), terminou, truncado, info

    def close(self):
        if self.simulacao is not None:
            self.simulacao.fisica.parar()
        self._finalizado = True
