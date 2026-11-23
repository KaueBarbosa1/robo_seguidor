"""Q-learning com referência CNN em pista sintética. Unidades físicas são hipóteses."""
import numpy as np

from aprendizado.cnn import Adam, RedeLinha
from aprendizado.dados import preparar_entrada
from aprendizado.simulador import AmbienteSimulado, PistaSintetica
from visao.detector import DetectorLinha

ACOES = np.array([(0., 0.)] + [(d, v) for v in (.45, .8) for d in (-.7, -.35, 0., .35, .7)])
CONTRATO = 'rl_sintetico_cnn_referencia_v1'


def treinar_referencia(semente=7, amostras=600, passos=250):
    """CNN supervisionada por geometria simulada, com visibilidade OpenCV sintética."""
    rng = np.random.default_rng(semente)
    detector = DetectorLinha()
    entradas, alvos, visiveis = [], [], []
    for i in range(amostras):
        if i % 60 == 0:
            pista = PistaSintetica(i // 60)
            ambiente = AmbienteSimulado(pista, rng)
        ambiente.iniciar()
        deslocamento = rng.uniform(-.10, .10)
        ambiente.x -= np.sin(ambiente.h) * deslocamento
        ambiente.y += np.cos(ambiente.h) * deslocamento
        ambiente.h += rng.uniform(-.4, .4)
        imagem = np.clip(ambiente._renderizar() + rng.normal(0, 5, (120, 160)), 0, 255).astype(np.uint8)
        rel = pista.pontos - (ambiente.x, ambiente.y)
        frente = rel @ np.array([np.cos(ambiente.h), np.sin(ambiente.h)])
        lateral = rel @ np.array([np.sin(ambiente.h), -np.cos(ambiente.h)])
        candidatos = np.flatnonzero((frente > .04) & (frente < .15) & (abs(lateral) < .2))
        alvo = 0.
        if len(candidatos):
            escolhido = candidatos[np.argmin(abs(frente[candidatos] - .10))]
            alvo = float(np.clip(lateral[escolhido] / .12, -1, 1))
        visivel = bool(len(candidatos) and detector.processar(imagem).achou)
        entradas.append(preparar_entrada(imagem)[0])
        alvos.append(alvo)
        visiveis.append(visivel)
    x, y, v = np.array(entradas), np.array(alvos), np.array(visiveis, np.float32)
    rede = RedeLinha(semente)
    opt = Adam(rede)
    for _ in range(passos):
        ids = rng.choice(len(x), min(24, len(x)), replace=False)
        rede.perda_e_gradiente(x[ids], y[ids], v[ids], v[ids], np.ones(len(ids)))
        opt.passo()
    return rede


class AmbienteRL:
    dt = .1
    memoria_s = .6

    def __init__(self, rede, pista_id, semente, max_passos=300):
        self.rede = rede
        self.pista = PistaSintetica(pista_id)
        self.fisica = AmbienteSimulado(self.pista, np.random.default_rng(semente), max_fora_m=.10)
        self.rng = np.random.default_rng(semente + 100000)
        self.max_passos = max_passos
        self.erro = self.anterior = 0.
        self.idade = self.memoria_s + self.dt
        self.acao_anterior = 0
        self.passos = 0
        self.progresso = 0.
        self.indice = self._indice()
        self.observar()

    def _indice(self):
        return int(np.argmin(np.linalg.norm(self.pista.pontos - (self.fisica.x, self.fisica.y), axis=1)))

    def observar(self):
        self.anterior = self.erro
        # Perda de quadro mantém a previsão envelhecendo. Nunca consulta posição real para a política.
        if self.rng.random() < .05:
            self.idade += self.dt
            return
        imagem = np.clip(self.fisica._renderizar() + self.rng.normal(0, 5, (120, 160)), 0, 255).astype(np.uint8)
        direcao, visibilidade = self.rede.prever(preparar_entrada(imagem))
        if visibilidade[0] >= .5:
            self.erro = float(direcao[0])
            self.idade = 0.
        else:
            self.idade += self.dt

    def estado(self):
        return (int(np.digitize(self.erro, [-.6, -.3, -.1, .1, .3, .6])),
                int(np.digitize(self.erro - self.anterior, [-.1, -.02, .02, .1])),
                int(np.digitize(self.fisica.v, [.035, .065])),
                int(np.digitize(self.idade, [.05, self.memoria_s])), self.acao_anterior)

    def passo(self, acao):
        if not 0 <= acao < len(ACOES):
            raise ValueError('Ação fora do contrato')
        direcao, velocidade = ACOES[acao]
        bloqueada = self.idade > self.memoria_s
        if bloqueada:
            direcao, velocidade = 0., 0.
        elif self.idade > 0:
            velocidade *= .5
        anterior = ACOES[self.acao_anterior][0]
        self.fisica.aplicar(direcao, velocidade)
        self.fisica._avancar(self.dt)
        indice = self._indice()
        progresso = self.pista.s[indice] - self.pista.s[self.indice]
        progresso = (progresso + self.pista.comprimento / 2) % self.pista.comprimento - self.pista.comprimento / 2
        self.progresso += progresso
        self.indice = indice
        distancia = self.pista.distancia_ao_tracado(self.fisica.x, self.fisica.y)
        fora = self.fisica.fora_verdade
        recompensa = 20 * progresso - .1 * (distancia / .10) ** 2 - .01 * abs(direcao - anterior)
        recompensa -= 5 * fora
        self.acao_anterior = acao
        self.passos += 1
        self.observar()
        terminou = bool(fora or self.passos >= self.max_passos)
        return self.estado(), recompensa, terminou, {
            'progresso_m': self.progresso, 'erro_real_m': distancia, 'fora': bool(fora),
            'suavidade': abs(direcao - anterior), 'bloqueada': bloqueada,
        }


class AgenteQ:
    def __init__(self, semente=7):
        self.q = np.zeros((7, 5, 3, 3, len(ACOES), len(ACOES)), np.float32)
        self.rng = np.random.default_rng(semente)

    def escolher(self, estado, epsilon=0.):
        if self.rng.random() < epsilon:
            return int(self.rng.integers(len(ACOES)))
        valores = self.q[estado]
        return int(np.argmax(valores))

    def atualizar(self, estado, acao, recompensa, proximo, terminou):
        alvo = recompensa + (0. if terminou else .97 * float(self.q[proximo].max()))
        chave = (*estado, acao)
        self.q[chave] += .15 * (alvo - self.q[chave])


def acao_pd(ambiente):
    """Referência PD com KP/KD do projeto, normalizados pelo teto PWM."""
    from controle import calcular_motores, filtrar_derivada
    derivada = filtrar_derivada(0., ambiente.erro, ambiente.anterior, ambiente.dt, 1.)
    esq, direita = calcular_motores(ambiente.erro, derivada)
    direcao = np.clip((esq - direita) / (2 * 255), -1, 1)
    velocidade = np.clip((esq + direita) / (2 * 255), 0, 1)
    return int(np.argmin((ACOES[:, 0] - direcao) ** 2 + (ACOES[:, 1] - velocidade) ** 2))
