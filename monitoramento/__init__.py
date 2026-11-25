"""Instrumentação opcional: sem hardware, rede, disco ou psutil nas threads produtoras."""
from collections import deque
from functools import wraps
import math
import threading
import time


class Registro:
    """Memória limitada por métrica. Produtores nunca aguardam o lock do consumidor."""
    def __init__(self, capacidade=512):
        self.capacidade = capacidade
        self.lock = threading.Lock()
        self.valores = {}
        self.contadores = {}
        self.ultimo = {}
        self.pedidos = {}
        self.descartados = 0

    def observar(self, nome, valor):
        if not math.isfinite(valor):
            return
        if not self.lock.acquire(False):
            self.descartados += 1
            return
        try:
            fila = self.valores.get(nome)
            if fila is None:
                fila = self.valores[nome] = deque(maxlen=self.capacidade)
            if len(fila) == fila.maxlen:
                self.descartados += 1
            fila.append(float(valor))
        finally:
            self.lock.release()

    def contar(self, nome, quantidade=1):
        if not self.lock.acquire(False):
            self.descartados += 1
            return
        try:
            self.contadores[nome] = self.contadores.get(nome, 0) + quantidade
        finally:
            self.lock.release()

    def ciclo(self, nome, periodo):
        agora = time.perf_counter()
        if not self.lock.acquire(False):
            self.descartados += 1
            return
        try:
            anterior = self.ultimo.get(nome)
            self.ultimo[nome] = agora
        finally:
            self.lock.release()
        if anterior is not None:
            intervalo = agora - anterior
            self.observar(nome + '.periodo_s', intervalo)
            self.observar(nome + '.jitter_s', intervalo - periodo)
        self.contar(nome + '.ciclos')

    def drenar(self):
        with self.lock:
            valores, self.valores = self.valores, {}
            contadores = dict(self.contadores)
            descartados = self.descartados
        return ({k: resumo(list(v)) for k, v in valores.items()}, contadores, descartados)

    def publicar_pedido(self, nome, valor):
        if not self.lock.acquire(False):
            self.descartados += 1
            return
        try:
            self.pedidos[nome] = (valor, time.perf_counter())
        finally:
            self.lock.release()

    def ler_pedidos(self):
        agora = time.perf_counter()
        with self.lock:
            pedidos = dict(self.pedidos)
        return {k: dict(valor=v, idade_s=agora-t, natureza='comandado',
                        estado='ultimo_pedido_observado; nao confirma execucao')
                for k, (v, t) in pedidos.items()}


def resumo(valores):
    if not valores:
        return None
    v = sorted(valores)
    def percentil(p):
        i = (len(v)-1)*p
        a = int(i)
        return v[a] + (v[min(a+1, len(v)-1)]-v[a])*(i-a)
    return dict(n=len(v), media=sum(v)/len(v), minimo=v[0], maximo=v[-1],
                mediana=percentil(.5), p95=percentil(.95))


_registro = None


def ativar(registro):
    global _registro
    _registro = registro


def observar(nome, valor):
    if _registro is not None:
        _registro.observar(nome, valor)


def contar(nome, quantidade=1):
    if _registro is not None:
        _registro.contar(nome, quantidade)


def ciclo(nome, periodo):
    if _registro is not None:
        _registro.ciclo(nome, periodo)


def publicar_pedido(nome, valor):
    if _registro is not None:
        _registro.publicar_pedido(nome, valor)


def medir(nome):
    """Tempo de parede, inclui espera/desescalonamento; não é tempo exclusivo de CPU."""
    def decorar(funcao):
        @wraps(funcao)
        def chamada(*args, **kwargs):
            registro = _registro
            if registro is None:
                return funcao(*args, **kwargs)
            inicio = time.perf_counter()
            try:
                return funcao(*args, **kwargs)
            finally:
                registro.observar(nome, time.perf_counter()-inicio)
        return chamada
    return decorar
