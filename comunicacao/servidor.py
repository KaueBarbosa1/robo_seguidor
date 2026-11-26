"""Dois WebSockets independentes, sem import de serial/controle ou comandos reais."""
import asyncio
from dataclasses import dataclass
from http import HTTPStatus
import logging
import secrets
import threading
import time
import uuid

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed
from comunicacao.metricas import Metricas
from comunicacao.protocolo import codificar, decodificar, envelope, empacotar_imagem, Sequencia

log = logging.getLogger('rede')


@dataclass(eq=False)
class Consumidor:
    canal: str
    fila: asyncio.Queue


def oferecer(fila, item):
    """Latest wins; não aguarda consumidor, socket ou disco."""
    descartados = 0
    while fila.full():
        fila.get_nowait()
        descartados += 1
    fila.put_nowait(item)
    return descartados


class Servidor:
    def __init__(self, opcoes, amostras, fonte=None, simulado=False, falhas=None, operacao=None):
        self.op, self.amostras, self.fonte = opcoes, amostras, fonte
        self.simulado, self.falhas = simulado, falhas or {}
        if self.falhas and not simulado:
            raise ValueError('Injecao de falhas permitida somente em simulacao')
        self.sessao = str(uuid.uuid4())
        self.metricas = Metricas()
        self.consumidores = set()
        self.pronto = threading.Event()
        self.erro = None
        self.thread = self.loop = self.fim = None
        self.porta = None
        self.operacao=operacao
        if operacao:operacao.autoridade.ligar(self.sessao)

    def iniciar(self):
        if self.thread:
            raise RuntimeError('Servidor ja iniciado')
        self.amostras.iniciar()
        self.thread = threading.Thread(target=self._thread, name='rede-websocket', daemon=True)
        self.thread.start()
        if not self.pronto.wait(3.) or self.erro:
            self.parar()
            raise RuntimeError(self.erro or 'Servidor nao iniciou no prazo')
        return self.porta

    def _thread(self):
        try:
            asyncio.run(self.executar())
        except Exception as exc:
            self.erro = f'{type(exc).__name__}: {exc}'
            log.error('Servidor observacional indisponivel: %s', self.erro)
        finally:
            self.pronto.set()

    def autorizar(self, conexao, pedido):
        if pedido.path not in ({'/ws/telemetria', '/ws/imagens','/ws/operacao'} if self.operacao else {'/ws/telemetria','/ws/imagens'}):
            return conexao.respond(HTTPStatus.NOT_FOUND, 'Endpoint inexistente\n')
        try:
            cabecalhos = pedido.headers.get_all('Authorization')
            autorizado = len(cabecalhos) == 1 and secrets.compare_digest(cabecalhos[0],
                                                 'Bearer '+self.op.token)
        except (ValueError, TypeError):
            autorizado = False
        if not autorizado:
            return conexao.respond(HTTPStatus.UNAUTHORIZED, 'Autenticacao necessaria\n')
        if pedido.path=='/ws/operacao':
            rejeicao=self.operacao.autorizar(conexao,pedido)
            if rejeicao:return rejeicao
        if len(self.consumidores) >= self.op.max_clientes:
            return conexao.respond(HTTPStatus.SERVICE_UNAVAILABLE, 'Limite de consumidores\n')

    async def executar(self):
        self.loop = asyncio.get_running_loop()
        self.fim = asyncio.Event()
        async with serve(self.conectar, self.op.host, self.op.porta,
                         process_request=self.autorizar, origins=[None], compression=None,
                         max_size=self.op.max_json, max_queue=self.op.fila,
                         write_limit=32768, open_timeout=self.op.timeout_s,
                         close_timeout=self.op.timeout_s, ping_interval=None,
                         backlog=16) as servidor:
            self.porta = servidor.sockets[0].getsockname()[1]
            produtores = [asyncio.create_task(self.produzir_telemetria()),
                          asyncio.create_task(self.produzir_imagens())]
            self.pronto.set()
            try:
                await self.fim.wait()
            finally:
                for tarefa in produtores:
                    tarefa.cancel()
                await asyncio.gather(*produtores, return_exceptions=True)
        # O contexto fecha conexões e aguarda seus handlers.

    def parar(self):
        if self.loop and self.fim and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self.fim.set)
        if self.thread:
            self.thread.join(timeout=self.op.timeout_s+2)
        self.amostras.parar()

    def distribuir(self, canal, item):
        for consumidor in tuple(self.consumidores):
            if consumidor.canal == canal:
                n = oferecer(consumidor.fila, item)
                if n:
                    self.metricas.contar('descartes_fila_'+canal, n)

    async def produzir_telemetria(self):
        seq = 0
        while True:
            inicio = time.monotonic()
            if any(c.canal == 'telemetria' for c in self.consumidores):
                snapshot = self.amostras.snapshot()
                if snapshot:
                    dados, instante = snapshot
                    seq += 1
                    if self.falhas.get('descartar_cada', 0) and seq % self.falhas['descartar_cada'] == 0:
                        self.metricas.contar('descartes_injetados')
                    else:
                        self.distribuir('telemetria', (seq, dados, instante))
            await asyncio.sleep(max(0., 1/self.op.telemetria_hz-(time.monotonic()-inicio)))

    async def produzir_imagens(self):
        ultimo, seq = 0, 0
        while True:
            inicio = time.monotonic()
            if self.fonte and any(c.canal == 'imagens' for c in self.consumidores):
                q = self.fonte.proximo_jpeg_detalhado(ultimo, timeout=0)
                if q:
                    ident, quadro = q
                    if ultimo and ident > ultimo+1:
                        self.metricas.contar('frames_nao_encaminhados_por_amostragem', ident-ultimo-1)
                    ultimo, seq = ident, seq+1
                    self.distribuir('imagens', (seq, (ident, quadro), quadro.recepcao_monotonica))
            await asyncio.sleep(max(0., 1/self.op.imagens_fps-(time.monotonic()-inicio)))

    def mensagem(self, seq, tipo, dados, idade=0.):
        return envelope(self.sessao, seq, tipo, dados, self.simulado,
                        'simulador' if self.simulado else 'raspberry', idade, self.op.validade_s)

    async def conectar(self, ws):
        if len(self.consumidores) >= self.op.max_clientes:
            await ws.close(1013, 'Limite de consumidores')
            return
        if ws.request.path=='/ws/operacao':
            await self.operacao.conectar(self,ws)
            return
        canal = ws.request.path.rsplit('/', 1)[-1]
        consumidor = Consumidor(canal, asyncio.Queue(self.op.fila))
        self.consumidores.add(consumidor)
        self.metricas.contar('conexoes')
        self.metricas.conectado_em = time.monotonic()
        self.metricas.ultima_sessao = self.sessao
        lock_envio = asyncio.Lock()
        async def enviar(dados):
            async with lock_envio:
                await asyncio.wait_for(ws.send(dados), self.op.timeout_s)
            self.metricas.contar('mensagens_tx')
            self.metricas.contar('bytes_tx', len(dados.encode('utf-8')) if isinstance(dados, str) else len(dados))
        tarefas = []
        try:
            await enviar(codificar(self.mensagem(0, 'ola', dict(canal=canal, comandos_habilitados=False))))
            tarefas = [asyncio.create_task(self.enviar_fluxo(consumidor, enviar)),
                       asyncio.create_task(self.receber(ws, enviar)),
                       asyncio.create_task(self.heartbeat(ws))]
            if self.falhas.get('desconectar_s'):
                async def desconectar():
                    await asyncio.sleep(self.falhas['desconectar_s'])
                    await ws.close(1012, 'Desconexao simulada')
                tarefas.append(asyncio.create_task(desconectar()))
            _, pendentes = await asyncio.wait(tarefas, return_when=asyncio.FIRST_COMPLETED)
            for t in pendentes:
                t.cancel()
        except (ConnectionClosed, TimeoutError, ValueError):
            self.metricas.contar('erros_conexao')
        finally:
            for t in tarefas:
                t.cancel()
            resultados = await asyncio.gather(*tarefas, return_exceptions=True)
            if any(isinstance(r, TimeoutError) for r in resultados):
                self.metricas.contar('timeouts')
            await ws.close()
            self.consumidores.discard(consumidor)
            self.metricas.encerrar_rtt(id(ws))
            self.metricas.contar('desconexoes')
            if not self.consumidores:
                self.metricas.conectado_em = None

    async def enviar_fluxo(self, consumidor, enviar):
        while True:
            seq, dados, instante = await consumidor.fila.get()
            atraso = self.falhas.get('atraso_s', 0)
            if atraso:
                await asyncio.sleep(atraso)
            idade = time.monotonic()-instante
            if consumidor.canal == 'telemetria':
                if idade > self.op.validade_s:
                    self.metricas.contar('descartes_antigos_telemetria')
                    continue
                msg = self.mensagem(seq, 'telemetria', dict(dados, comunicacao=self.metricas.snapshot()), idade)
                if self.falhas.get('invalida_cada', 0) and seq % self.falhas['invalida_cada'] == 0:
                    pacote = '{"simulacao":"json quebrado"'
                else:
                    pacote = codificar(msg)
                if len(pacote.encode('utf-8')) > self.op.max_json:
                    self.metricas.contar('descartes_tamanho')
                    continue
                await enviar(pacote)
                self.metricas.contar('telemetrias')
            else:
                ident, q = dados
                idade += q.idade_recepcao_limite_ms/1000
                limite = min(self.op.validade_s, getattr(self.fonte, 'idade_max_s', self.op.validade_s))
                if idade > limite:
                    self.metricas.contar('descartes_antigos_imagens')
                    continue
                meta=self.operacao.autoridade.registrar_frame(ident,q) if self.operacao else {}
                msg = self.mensagem(seq, 'imagem', dict(frame_id=ident, jpeg_bytes=len(q.jpeg),**meta), idade)
                try:
                    pacote = empacotar_imagem(msg, q.jpeg, self.op.max_json, self.op.max_jpeg)
                except ValueError:
                    self.metricas.contar('descartes_tamanho')
                    continue
                await enviar(pacote)
                self.metricas.contar('frames')

    async def receber(self, ws, enviar):
        sequencia = Sequencia()
        inicio_janela, recebidas = time.monotonic(), 0
        async for texto in ws:
            self.metricas.contar('mensagens_rx')
            self.metricas.contar('bytes_rx', len(texto.encode('utf-8')) if isinstance(texto, str) else len(texto))
            try:
                agora = time.monotonic()
                if agora-inicio_janela >= 1:
                    inicio_janela, recebidas = agora, 0
                recebidas += 1
                if recebidas > 32:
                    raise ValueError('Limite de mensagens diagnosticas excedido')
                msg = decodificar(texto, self.op.max_json)
                if msg['sessao'] != self.sessao or not sequencia.aceitar(msg):
                    raise ValueError('Sessao/sequencia invalida')
                if msg['idade_envio_s'] > msg['validade_s']:
                    raise ValueError('Mensagem vencida na origem')
                # Nenhum dispatch de comandos: única mensagem admitida é uma sonda diagnóstica.
                nonce = msg['dados'].get('nonce')
                if msg['tipo'] != 'sonda' or msg['origem'] != 'computador' or not isinstance(nonce, str) or len(nonce) != 32:
                    raise ValueError('Somente sonda diagnostica permitida')
                async with asyncio.timeout(self.op.timeout_s):
                    await enviar(codificar(self.mensagem(0, 'eco', dict(nonce=nonce))))
            except ValueError:
                self.metricas.contar('mensagens_invalidas')
                await ws.close(1008, 'Mensagem rejeitada; comandos desabilitados')
                return

    async def heartbeat(self, ws):
        while True:
            async with asyncio.timeout(self.op.timeout_s):
                pong = await ws.ping()
                rtt = await pong
            self.metricas.rtt(rtt, id(ws))
            await asyncio.sleep(self.op.heartbeat_s)
