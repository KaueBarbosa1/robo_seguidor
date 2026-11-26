"""Inferencia congelada CNN -> RL. Nao treina, nao escreve em motores."""
from dataclasses import dataclass
import hashlib
import json
import logging
import math
from pathlib import Path
import threading
import time

import cv2
import numpy as np

import config as cfg
from aprendizado.cnn import RedeLinha
from aprendizado.dados import normalizar, preparar_entrada
from aprendizado.rl_simulado import ACOES
from estado import AcaoRL
from visao.recorte_esp32 import RecorteESP32
from monitoramento import medir

CONTRATO = 'cnn_rl_esp32_v1'
OBS_GYM = 'rl_cnn_gym_discreto_v1'
OBS_Q = 'rl_sintetico_cnn_referencia_v1'


def sha256(caminho):
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


class Pacote:
    """Carrega par CNN/politica com hashes e contrato explicitos, sem fallback."""
    def __init__(self, caminho):
        caminho = Path(caminho)
        m = json.loads(caminho.read_text(encoding='utf-8'))
        if m.get('contrato') != CONTRATO:
            raise ValueError('Contrato de pacote CNN/RL desconhecido')
        self.meta = m
        self.dominio = m['dominio']
        if self.dominio not in {'sintetico', 'esp32'}:
            raise ValueError('Dominio CNN/RL desconhecido')
        arquivos = []
        for nome in ('cnn', 'politica'):
            p = caminho.parent / m[nome]['arquivo']
            if sha256(p) != m[nome]['sha256']:
                raise ValueError('Hash de arquivo incorreto: ' + nome)
            arquivos.append(p)
        self.rede = RedeLinha.carregar(arquivos[0])
        if self.rede.hash() != m['hash_cnn'] or not all(np.isfinite(p).all() for p in self.rede.parametros()):
            raise ValueError('Pesos/hash da CNN invalidos')
        if m.get('escalas') != dict(dt_s=.1, memoria_s=.6, velocidade_max_m_s=.11):
            raise ValueError('Escalas de observacao diferentes do contrato treinado')
        self.preprocessamento = m['percepcao']['preprocessamento']
        if m['percepcao']['visibilidade_treinada'] is not True:
            raise ValueError('CNN sem visibilidade supervisionada nao pode fornecer validade ao RL')
        if self.preprocessamento == 'simulado_160x120_roi40_v1':
            if cfg.APR_ROI_LINHA_INICIO != 40:
                raise ValueError('ROI legada local diferente da ROI40 do treino sintetico')
            if self.dominio != 'sintetico':
                raise ValueError('Adaptador sintetico e exclusivo do modo sombra')
            self.recorte = None
        elif self.preprocessamento == 'esp32_roi_normalizada_v1':
            self.recorte = RecorteESP32(*m['percepcao']['roi'])
        else:
            raise ValueError('Pre-processamento da CNN desconhecido; fotos y075 nao sao compativeis')
        self.observacao = m['politica']['observacao']
        self.algoritmo = m['politica']['algoritmo']
        if not np.array_equal(np.asarray(m['acoes'], dtype=float), ACOES):
            raise ValueError('Acoes diferentes do contrato treinado')
        if self.algoritmo == 'q':
            if self.observacao != OBS_Q:
                raise ValueError('Observacao incompativel com Q-learning')
            with np.load(arquivos[1], allow_pickle=False) as d:
                self.q = np.array(d['q'], copy=True)
                if (d['contrato'].item() != OBS_Q or d['hash_cnn'].item() != self.rede.hash() or
                        not np.array_equal(d['acoes'], ACOES) or
                        self.q.shape != (7, 5, 3, 3, 11, 11) or not np.isfinite(self.q).all()):
                    raise ValueError('Politica Q incompativel com CNN/contrato')
            self.modelo = None
        elif self.algoritmo in {'dqn', 'ppo'}:
            if self.observacao != OBS_GYM:
                raise ValueError('Observacao incompativel com DQN/PPO')
            try:
                from stable_baselines3 import DQN, PPO
            except ImportError as exc:
                raise ValueError('DQN/PPO exigem requirements-rl.txt no ambiente de inferencia') from exc
            self.modelo = {'dqn': DQN, 'ppo': PPO}[self.algoritmo].load(str(arquivos[1]), device='cpu')
            if (self.modelo.observation_space.shape != (7,) or
                    getattr(self.modelo.action_space, 'n', None) != len(ACOES)):
                raise ValueError('Espacos de observacao/acao incompativeis')
        else:
            raise ValueError('Algoritmo RL desconhecido')
        enc = m['encoders']
        self.mm_pulso = tuple(float(v) for v in enc['mm_por_pulso'])
        if len(self.mm_pulso) != 2 or any(not math.isfinite(v) or v <= 0 for v in self.mm_pulso):
            raise ValueError('Conversao de encoders invalida')

    def validar_motores(self):
        if (self.dominio != 'esp32' or self.preprocessamento != 'esp32_roi_normalizada_v1' or
                self.meta['encoders'].get('calibrados') is not True):
            raise ValueError('Pacote sintetico/sem calibracao e somente sombra; nao habilita motores')
        percepcao = self.meta['percepcao']
        if (percepcao.get('semantica') != 'lateral_a_10cm_dividida_por_12cm' or
                percepcao.get('espelhar_h') is not cfg.IMAGEM_ESPELHAR_H or
                percepcao.get('espelhar_v') is not cfg.IMAGEM_ESPELHAR_V):
            raise ValueError('Semantica/orientacao nao corresponde ao contrato da camera e do RL')

    def entrada(self, frame):
        if frame.shape != (240, 320, 3) or frame.dtype != np.uint8:
            raise ValueError('Esperado JPEG decodificado BGR uint8 320x240')
        if cfg.IMAGEM_ESPELHAR_H or cfg.IMAGEM_ESPELHAR_V:
            eixo = -1 if cfg.IMAGEM_ESPELHAR_H and cfg.IMAGEM_ESPELHAR_V else 1 if cfg.IMAGEM_ESPELHAR_H else 0
            frame = cv2.flip(frame, eixo)
        if self.recorte is None:
            # Compatibilidade EXCLUSIVA para diagnostico dos pesos sinteticos.
            cinza = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            return preparar_entrada(cv2.resize(cinza, (160, 120), interpolation=cv2.INTER_AREA))
        return normalizar(self.recorte.reduzir(frame)[None])

    @medir('rl_s')
    def escolher(self, erro, delta, velocidade, idade, anterior):
        if not all(math.isfinite(v) for v in (erro, delta, velocidade, idade)):
            raise ValueError('Observacao RL nao finita')
        if self.algoritmo == 'q':
            estado = (int(np.digitize(erro, [-.6, -.3, -.1, .1, .3, .6])),
                      int(np.digitize(delta, [-.1, -.02, .02, .1])),
                      int(np.digitize(velocidade, [.035, .065])),
                      int(np.digitize(idade, [.05, .6])), anterior)
            return int(np.argmax(self.q[estado]))  # nenhuma exploracao em operacao
        direcao, fator = ACOES[anterior]
        obs = np.clip([erro, delta/2, 2*velocidade/.11-1,
                       2*min(idade/.6, 1)-1, 1 if idade <= .6 else -1,
                       direcao, 2*fator-1], -1, 1).astype(np.float32)
        acao, _ = self.modelo.predict(obs, deterministic=True)
        acao = np.asarray(acao)
        if acao.size != 1 or not np.isfinite(acao).all() or float(acao.item()) != int(acao.item()) or not 0 <= int(acao.item()) < len(ACOES):
            raise ValueError('Acao RL fora do contrato')
        return int(acao.item())


class VelocidadeEncoder:
    """Estimativa pelo delta de contadores; nao inventa zero sem duas amostras."""
    def __init__(self, mm_pulso):
        self.mm_pulso = mm_pulso
        self.anterior = None
        self.valor = None

    def medir(self, s, agora):
        if (s is None or not math.isfinite(s.timestamp) or
                not 0 <= agora-s.timestamp <= cfg.SENSOR_TIMEOUT_S):
            self.anterior = self.valor = None
            return None
        atual = (s.timestamp, s.ticks_esq, s.ticks_dir)
        if not all(math.isfinite(v) and v >= 0 for v in atual):
            self.anterior = self.valor = None
            return None
        ant = self.anterior
        if ant is None:
            self.anterior = atual
            return None
        if atual == ant:
            return self.valor
        self.anterior = atual
        if atual[0] <= ant[0] or atual[1] < ant[1] or atual[2] < ant[2]:
            self.valor = None
            return None
        self.valor = sum((atual[i+1]-ant[i+1])*self.mm_pulso[i] for i in range(2))/(2000*(atual[0]-ant[0]))
        return self.valor  # modulo; encoders nao medem sentido. Acoes RL sao para avanco.


class ThreadInferencia(threading.Thread):
    def __init__(self, estado, motor, parar, fonte, pacote, sombra=True):
        super().__init__(name='cnn-rl', daemon=True)
        self.estado, self.motor, self.parar, self.fonte = estado, motor, parar, fonte
        if not sombra:
            pacote.validar_motores()
        self.pacote, self.sombra = pacote, sombra
        self.lock = threading.Lock()
        self.diagnostico = dict(modo='sombra' if sombra else 'controle', status='aguardando_camera', dominio=pacote.dominio,
                               geometria_encoder_calibrada=pacote.meta['encoders']['calibrados'])
        self.velocidade = VelocidadeEncoder(pacote.mm_pulso)
        self.sessao = self.geracao = None
        self.resetar()

    def resetar(self):
        self.frame_anterior = None
        self.erro = 0.
        self.aceita_t = None
        self.anterior = 0

    def status(self):
        with self.lock:
            dados = dict(self.diagnostico)
        camera = self.fonte.saude()
        a = self.estado.ler_acao_rl()
        dados['camera'] = camera['status']
        if (camera['status'] != 'ok' or a is None or a.geracao_camera != camera['geracao'] or
                a.sessao != self.estado.sessao_visao or not 0 <= a.idade(time.monotonic()) <= cfg.LEITURA_VALIDADE_S):
            dados['status'] = 'sem_inferencia_recente'
        return dados

    def processar(self, quadro, sessao, velocidade):
        ident, frame, meta = quadro
        geracao = meta['geracao_camera']
        if sessao != self.sessao or geracao != self.geracao:
            self.resetar()
            self.sessao, self.geracao = sessao, geracao
        if self.frame_anterior is not None and ident <= self.frame_anterior:
            return None
        self.frame_anterior = ident
        recebida, idade_inicial = meta['recepcao_monotonica'], meta['idade_captura_s']
        agora = time.monotonic()
        limite = min(cfg.LEITURA_VALIDADE_S, self.fonte.idade_max_s)
        def valida():
            s = self.fonte.saude()
            return (s['status'] == 'ok' and s['geracao'] == geracao and
                    math.isfinite(recebida) and math.isfinite(idade_inicial) and idade_inicial >= 0 and
                    0 <= time.monotonic()-recebida and time.monotonic()-recebida+idade_inicial <= limite)
        if not valida():
            self.resetar()
            return None
        inicio = time.monotonic()
        d, p = self.pacote.rede.prever(self.pacote.entrada(frame))
        erro, visivel = float(d[0]), float(p[0])
        if not (math.isfinite(erro) and -1 <= erro <= 1 and math.isfinite(visivel) and 0 <= visivel <= 1):
            raise ValueError('Saida CNN invalida')
        anterior = self.erro
        if visivel >= .5:
            self.erro, self.aceita_t = erro, recebida-idade_inicial
        idade = math.inf if self.aceita_t is None else agora-self.aceita_t
        acao, motivo = 0, 'sem_referencia_cnn'
        if velocidade is None or not math.isfinite(velocidade) or velocidade < 0:
            motivo = 'velocidade_indisponivel'
        elif 0 <= idade <= min(.6, cfg.PERDA_LINHA_TIMEOUT_S):
            acao = self.pacote.escolher(self.erro, self.erro-anterior, velocidade, idade, self.anterior)
            motivo = 'cnn_rl'
        direcao, fator = (float(v) for v in ACOES[acao])
        if visivel < .5:
            fator *= .5
        if not valida():
            self.resetar()
            return None
        saida = AcaoRL(direcao, fator, recebida, idade_inicial, ident, geracao, sessao,
                       motivo, erro, visivel, acao)
        if not self.estado.publicar_acao_rl(saida):
            self.resetar()
            return None
        self.anterior = acao
        with self.lock:
            self.diagnostico.update(status=motivo, frame_id=ident, erro_cnn=erro,
                                    visibilidade=visivel, acao=acao, direcao=direcao,
                                    fator=fator, velocidade_estimada_m_s=velocidade,
                                    inferencia_ms=(time.monotonic()-inicio)*1000)
        return saida

    def run(self):
        ultimo = 0
        try:
            while not self.parar.is_set():
                autoridade=getattr(self.estado,'_autoridade_rede',None)
                if autoridade is not None and autoridade.processamento=='distribuido':
                    self.resetar();self.parar.wait(.02);continue
                with self.estado.lock:
                    sessao = self.estado.sessao_visao
                q = self.fonte.proximo_quadro_detalhado(ultimo, timeout=.1)
                if q is None:
                    if self.fonte.saude()['status'] != 'ok':
                        self.resetar()
                    continue
                ultimo = q[0]
                s = getattr(self.motor, 'sensores', lambda: None)()
                inicio = time.monotonic()
                v = self.velocidade.medir(s, inicio)
                d = getattr(self.motor, 'estado_motores', lambda: None)()
                motor_ok = (d is not None and 0 <= time.monotonic()-d.timestamp <= cfg.SENSOR_TIMEOUT_S and not d.falha_encoder)
                if (s is None or getattr(s, 'falha_sensor', True) or getattr(s, 'avanco_bloqueado', True) or
                        (not self.sombra and not motor_ok)):
                    self.resetar()
                    v = None
                self.processar(q, sessao, v)
                self.parar.wait(max(0., .1-(time.monotonic()-inicio)))
        except Exception as exc:
            logging.getLogger('cnn-rl').exception('Falha de inferencia; encerrando sem fallback')
            with self.lock:
                self.diagnostico.update(status='erro', erro=str(exc))
            # Inferencia selecionada nunca cai silenciosamente para PD.
            self.parar.set()
        finally:
            self.estado.limpar_acao_rl()
