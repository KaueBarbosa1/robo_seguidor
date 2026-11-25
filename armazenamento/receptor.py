"""Uma instância do Cliente da Etapa 2; escritor e demais consumidores usam fan-out."""
import asyncio
import threading

from comunicacao.cliente import Cliente
from comunicacao.distribuidor import Distribuidor
from armazenamento.gravador import Gravador
from monitoramento.sistema import Sistema


class ReceptorPC:
    def __init__(self,url,opcoes_rede,opcoes_armazenamento):
        self.url,self.op = url,opcoes_rede
        self.bus=Distribuidor()
        self.cliente=None
        self.loop=None
        self.pronto=threading.Event()
        self.thread=None
        self.erro=None
        self.g=Gravador(self.bus,opcoes_armazenamento,
            diagnostico=lambda:self.cliente.snapshot() if self.cliente else {},sistema_pc=Sistema())

    def iniciar(self,automatico=False,**gravacao):
        if self.thread:
            raise RuntimeError('Receptor ja iniciado')
        self.g.iniciar()
        try:
            if automatico:
                self.g.nova_gravacao(**gravacao)
            self.thread=threading.Thread(target=self._rodar,name='pc-receptor',daemon=True)
            self.thread.start()
            if not self.pronto.wait(3) or self.erro:
                raise RuntimeError(self.erro or 'Cliente nao iniciou')
        except Exception:
            self.g.fechar()
            raise

    def _rodar(self):
        async def executar():
            self.loop=asyncio.get_running_loop()
            self.cliente=Cliente(self.url,self.op,distribuidor=self.bus,
                receber_imagens=self.g.op.imagens or self.g.op.imagens_eventos)
            self.pronto.set()
            await self.cliente.executar()
        try:
            asyncio.run(executar())
        except Exception as exc:
            self.erro=str(exc)
            self.pronto.set()

    def fechar(self):
        try:
            if self.loop and self.cliente and not self.loop.is_closed():
                self.loop.call_soon_threadsafe(self.cliente.parar)
            if self.thread:
                self.thread.join(self.op.timeout_s+3)
                if self.thread.is_alive():
                    raise RuntimeError('Cliente ainda encerrando')
        finally:
            self.g.fechar()
