"""Fan-out local; nenhuma conexão adicional, callbacks ou espera por consumidores."""
from collections import Counter
import queue
import threading


class Assinatura:
    def __init__(self, canais, capacidade):
        self.canais = frozenset(canais)
        self.fila = queue.Queue(capacidade)
        self.contas = Counter()

    def oferecer(self, canal, item):
        if canal not in self.canais:
            return
        self.contas['recebidas'] += 1
        try:
            self.fila.put_nowait((canal, item))
        except queue.Full:
            # Preserva eventos/amostras já enfileirados; contabiliza rejeição nova.
            self.contas['descartadas'] += 1


class Distribuidor:
    def __init__(self):
        self._lock = threading.Lock()
        self._assinaturas = ()

    def assinar(self, canais, capacidade=256):
        if not 1 <= capacidade <= 100000:
            raise ValueError('Capacidade fora da faixa')
        assinatura = Assinatura(canais, capacidade)
        with self._lock:
            if len(self._assinaturas) >= 16:
                raise ValueError('Limite de assinantes')
            self._assinaturas += (assinatura,)
        return assinatura

    def remover(self, assinatura):
        with self._lock:
            self._assinaturas = tuple(a for a in self._assinaturas if a is not assinatura)

    def publicar(self, canal, item):
        # Tuple publicada atomicamente; produtores não aguardam lock de assinaturas.
        for assinatura in self._assinaturas:
            assinatura.oferecer(canal, item)
