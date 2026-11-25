"""Reutiliza Telemetria, Sistema e Registro da Fase 1, sem hardware novo."""
import threading
import time
import platform
from monitoramento import Registro, ativar
from monitoramento.sistema import Sistema


class Amostras:
    def __init__(self, telemetria, hz=10., benchmark=None):
        self.telemetria, self.hz, self.benchmark = telemetria, hz, benchmark
        self.atual = None
        self.sistema = None
        self.sistema_t = None
        self.tempos = {}
        self.pedidos = {}
        self.contadores = {}
        self.fim = threading.Event()
        self.threads = []
        self.erro = None
        self.registro = Registro() if benchmark is None else None
        self.host = platform.node()
        self.plataforma = platform.system()

    def iniciar(self):
        if self.registro:
            ativar(self.registro)
            self.threads.append(threading.Thread(target=self._sistema, name='rede-sistema', daemon=True))
        self.threads.append(threading.Thread(target=self._loop, name='rede-snapshot', daemon=True))
        for t in self.threads:
            t.start()

    def _sistema(self):
        try:
            sistema = Sistema()
        except Exception as exc:
            self.erro = 'sistema: '+type(exc).__name__
            return
        while not self.fim.is_set():
            inicio = time.monotonic()
            try:
                self.sistema = sistema.coletar()
                self.sistema_t = time.monotonic()
                self.tempos, self.contadores, _ = self.registro.drenar()
                self.pedidos = self.registro.ler_pedidos()
            except Exception as exc:
                self.erro = type(exc).__name__
            self.fim.wait(max(0., 1-(time.monotonic()-inicio)))

    def _loop(self):
        while not self.fim.is_set():
            inicio = time.monotonic()
            try:
                self.atual = self.telemetria.coletar(), time.monotonic()
            except Exception as exc:
                self.erro = type(exc).__name__
            self.fim.wait(max(0., 1/self.hz-(time.monotonic()-inicio)))

    def snapshot(self):
        atual = self.atual
        if atual is None:
            return None
        telemetria, instante = atual
        b = self.benchmark.ultima_amostra if self.benchmark else None
        sistema = b.get('sistema') if b else self.sistema
        sistema_t = b.get('monotonic_s') if b else self.sistema_t
        idade_sistema = time.monotonic()-sistema_t if sistema_t is not None else None
        return dict(schema='benchmark_robo_v1', telemetria=telemetria, sistema=sistema,
                    sistema_host=self.host, sistema_plataforma=self.plataforma,
                    sistema_idade_s=idade_sistema,
                    sistema_estado='indisponivel' if sistema is None else
                                   'atual' if idade_sistema is not None and idade_sistema <= 2.5 else 'desatualizado',
                    tempos_s=b.get('tempos_s') if b else self.tempos,
                    contadores=b.get('contadores') if b else self.contadores,
                    pedidos=b.get('pedidos') if b else self.pedidos,
                    coleta_erro=self.erro), instante

    def parar(self):
        self.fim.set()
        for t in self.threads:
            t.join(timeout=1.)
        if self.registro:
            ativar(None)
