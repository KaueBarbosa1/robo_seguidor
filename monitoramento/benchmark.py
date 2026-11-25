"""Worker opcional de benchmark local. Saída limitada, sem canal de comandos."""
from datetime import datetime, timezone
import json
import hashlib
import logging
import math
from pathlib import Path
import platform
import threading
import time
import uuid

from monitoramento import Registro, ativar
from monitoramento.sistema import Sistema

log = logging.getLogger('benchmark')
TEMPOS = ('opencv_s', 'cnn_s', 'rl_s', 'voz_s', 'camera_http_s', 'camera_decode_s',
          'serial_escrita_s', 'serial_intervalo_sensores_s', 'controle.trabalho_s',
          'controle.periodo_s', 'controle.jitter_s', 'controle.idade_frame_s', 'rede.rtt_s')


def utc():
    return datetime.now(timezone.utc).isoformat()


class Benchmark:
    def __init__(self, diretorio, telemetria=None, intervalo=1., capacidade=512,
                 max_bytes=50_000_000, sistema=None, condicoes=None):
        if not math.isfinite(intervalo) or intervalo < 1 or capacidade < 1 or max_bytes < 1024:
            raise ValueError('intervalo >=1 s, capacidade positiva, max_bytes >=1024')
        self.raiz = Path(diretorio)
        self.telemetria = telemetria
        self.intervalo, self.max_bytes = intervalo, max_bytes
        self.registro = Registro(capacidade)
        self.sistema = sistema  # criado no worker: não prepara psutil no controle
        self.condicoes = condicoes or {}
        self.id = str(uuid.uuid4())
        self.fim = threading.Event()
        self.thread = None
        self.erro = None
        self.amostras = 0
        self.bytes = 0
        self._ciclos = self._quadros = None
        self._anterior_t = None
        self.ultima_amostra = None
        self.diagnostico_rede = None

    def iniciar(self):
        if self.thread is not None:
            raise RuntimeError('Benchmark ja iniciado')
        self.raiz.mkdir(parents=True, exist_ok=True)
        self.pasta = self.raiz / self.id
        self.pasta.mkdir()
        self.manifesto = dict(schema='benchmark_robo_v1', sessao=self.id, inicio_utc=utc(),
            host=platform.node(), plataforma=platform.platform(), python=platform.python_version(),
            condicoes=self.condicoes, intervalo_s=self.intervalo,
            capacidade_por_metrica=self.registro.capacidade, max_bytes=self.max_bytes,
            estado='iniciando', fim_utc=None,
            natureza_sistema='medido no host executor, inclusive quando carga e simulada',
            indisponiveis_fixos=dict(serial_rtt_s='protocolo nao tem ACK/eco correlacionado',
                computador_rtt_s='null se canal WebSocket nao ativo; RTT por sonda, nunca sentido unico',
                mensagens_perdidas='nao ha sequencia ponta a ponta no protocolo atual',
                frames_perdidos_na_camera='ESP32 nao exporta sequencia de captura'))
        import config as cfg
        self.manifesto['config_sha256'] = hashlib.sha256(Path(cfg.__file__).read_bytes()).hexdigest()
        self._manifesto()
        ativar(self.registro)
        self.thread = threading.Thread(target=self._loop, name='benchmark', daemon=True)
        self.thread.start()
        return self.pasta

    def _manifesto(self):
        destino = self.pasta/'manifesto.json'
        temporario = self.pasta/'manifesto.tmp'
        temporario.write_text(json.dumps(self.manifesto, ensure_ascii=False, indent=2), encoding='utf-8')
        temporario.replace(destino)

    def amostrar(self):
        inicio = time.perf_counter()
        tempos, contadores, descartados = self.registro.drenar()
        telemetria = self.telemetria.coletar() if self.telemetria else None
        ciclos = contadores.get('controle.ciclos', 0)
        dt = inicio-self._anterior_t if self._anterior_t is not None else None
        hz = (ciclos-self._ciclos)/dt if dt and self._ciclos is not None else None
        camera = (telemetria or {}).get('camera', {})
        quadros = camera.get('quadros')
        fps = ((quadros-self._quadros)/dt if dt and quadros is not None and
               self._quadros is not None and quadros >= self._quadros else None)
        self._anterior_t, self._ciclos, self._quadros = inicio, ciclos, quadros
        dados = dict(schema='benchmark_robo_v1', sessao=self.id, sequencia=self.amostras,
            timestamp_utc=utc(), monotonic_s=time.monotonic(),
            tempos_s={nome: tempos.get(nome) for nome in TEMPOS},
            contadores=contadores, amostras_instrumentacao_descartadas=descartados,
            pedidos=self.registro.ler_pedidos(),
            controle_hz=hz, camera_fps_janela=fps, telemetria=telemetria,
            sistema=self.sistema.coletar(), serial_rtt_s=None, computador_rtt_s=None,
            mensagens_perdidas=None, frames_perdidos_na_camera=None)
        dados['amostragem_trabalho_s'] = time.perf_counter()-inicio
        # n=0/null distingue modulo inativo de processamento com duração zero.
        dados['tempos_indisponiveis'] = {k: 'sem execucao observada nesta janela ou instrumentacao descartada'
                                       for k, v in dados['tempos_s'].items() if v is None}
        periodo = tempos.get('controle.periodo_s')
        dados['controle_hz_por_periodo'] = (1/periodo['media'] if periodo and periodo['media'] > 0 else None)
        dados['comunicacao'] = self.diagnostico_rede() if self.diagnostico_rede else None
        dados['computador_rtt_s'] = (dados['comunicacao']['rtt_s']['mediana']
            if dados['comunicacao'] and dados['comunicacao']['rtt_s'] else None)
        self.ultima_amostra = dados
        return dados

    def _loop(self):
        try:
            self.sistema = self.sistema or Sistema()
            self.manifesto['estado'] = 'gravando'
            self._manifesto()
            with (self.pasta/'amostras.jsonl').open('x', encoding='utf-8') as arquivo:
                while not self.fim.is_set():
                    inicio = time.perf_counter()
                    dados = self.amostrar()
                    linha = json.dumps(dados, ensure_ascii=False, allow_nan=False)+'\n'
                    tamanho = len(linha.encode('utf-8'))
                    if self.bytes+tamanho > self.max_bytes:
                        self.manifesto['estado'] = 'limite_arquivo'
                        break
                    arquivo.write(linha)
                    arquivo.flush()
                    self.bytes += tamanho
                    self.amostras += 1
                    self.fim.wait(max(0., self.intervalo-(time.perf_counter()-inicio)))
        except Exception as exc:
            self.erro = f'{type(exc).__name__}: {exc}'
            self.manifesto['estado'] = 'erro'
            log.error('Benchmark encerrado sem alterar controle: %s', self.erro)
        finally:
            ativar(None)
            if self.manifesto['estado'] == 'gravando':
                self.manifesto['estado'] = 'encerrado'
            self.manifesto.update(fim_utc=utc(), amostras=self.amostras, bytes=self.bytes, erro=self.erro)
            try:
                self._manifesto()
            except OSError:
                log.error('Nao foi possivel finalizar manifesto do benchmark')

    def parar(self):
        ativar(None)
        self.fim.set()
        if self.thread:
            self.thread.join(timeout=2.)
        if self.thread and self.thread.is_alive():
            log.warning('Worker benchmark ainda encerrando I/O; nao aguardar no controle')
