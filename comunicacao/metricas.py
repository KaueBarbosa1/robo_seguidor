from collections import Counter, deque
import threading
import time
from monitoramento import observar, contar, resumo


class Metricas:
    def __init__(self):
        self.lock = threading.Lock()
        self.contas = Counter()
        self.rtts = deque(maxlen=512)
        self.jitters = deque(maxlen=512)
        self._rtt_anterior = {}
        self.inicio = time.monotonic()
        self.conectado_em = self.ultima_telemetria = None
        self.ultima_sessao = None

    def contar(self, chave, n=1):
        with self.lock:
            self.contas[chave] += n
        contar('rede.'+chave, n)

    def rtt(self, valor, chave='principal'):
        with self.lock:
            if chave in self._rtt_anterior:
                self.jitters.append(abs(valor-self._rtt_anterior[chave]))
            self._rtt_anterior[chave] = valor
            self.rtts.append(valor)
        observar('rede.rtt_s', valor)

    def encerrar_rtt(self, chave='principal'):
        with self.lock:
            self._rtt_anterior.pop(chave, None)

    def snapshot(self):
        with self.lock:
            contas, rtts, jitters = dict(self.contas), list(self.rtts), list(self.jitters)
            conectado, ultima, sessao = self.conectado_em, self.ultima_telemetria, self.ultima_sessao
        agora = time.monotonic()
        duracao = max(agora-self.inicio, .001)
        return dict(contadores=contas, rtt_s=resumo(rtts), jitter_rtt_s=resumo(jitters),
            fps_medio=contas.get('frames', 0)/duracao,
            kb_s_medio=(contas.get('bytes_rx', 0)+contas.get('bytes_tx', 0))/1024/duracao,
            telemetria_hz_medio=contas.get('telemetrias', 0)/duracao,
            conectado=conectado is not None, tempo_conexao_s=agora-conectado if conectado else None,
            idade_ultima_telemetria_s=agora-ultima if ultima is not None else None,
            sessao=sessao, perda_pacotes_rede=None,
            escopo='contadores cumulativos; percentis das ultimas 512 sondas; taxas desde inicio')
