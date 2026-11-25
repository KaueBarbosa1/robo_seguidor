"""Cliente PC, buffers limitados para futuros consumidores, sem dependências de hardware."""
import asyncio
import ipaddress
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake
from comunicacao.metricas import Metricas
from comunicacao.protocolo import (envelope, codificar, decodificar,
                                  desempacotar_imagem, Sequencia)
from comunicacao.servidor import oferecer


class Cliente:
    def __init__(self, url, opcoes, consumo_lento_s=0, distribuidor=None, receber_imagens=True):
        partes = urlsplit(url)
        if partes.scheme != 'ws' or partes.path not in {'', '/'} or partes.query or partes.fragment or partes.username:
            raise ValueError('Use ws://IP_LOCAL:PORTA sem credenciais/caminho')
        ip = ipaddress.ip_address(partes.hostname)
        if not (ip.is_loopback or ip.is_private) or ip.is_multicast or ip.is_unspecified:
            raise ValueError('Servidor deve usar IP privado explicito')
        self.url, self.op = url.rstrip('/'), opcoes
        self.consumo_lento_s = consumo_lento_s
        self.metricas = {c: Metricas() for c in ('telemetria', 'imagens')}
        self.telemetrias = asyncio.Queue(opcoes.fila)
        self.imagens = asyncio.Queue(opcoes.fila)
        self.fim = asyncio.Event()
        self.ultima = None
        self.ultimo_frame = None
        self.estados = {c: 'desconectado' for c in self.metricas}
        self.simulado = None
        self.distribuidor = distribuidor
        self.receber_imagens = receber_imagens

    def evento(self, tipo, canal, ola):
        if self.distribuidor is not None and ola is not None:
            self.distribuidor.publicar('eventos', dict(tipo=tipo, canal=canal,
                sessao=ola['sessao'], simulado=ola['simulado'], origem=ola['origem'],
                versao=ola['versao'], timestamp=datetime.now(timezone.utc).isoformat(),
                recepcao_mono_s=time.monotonic()))

    async def executar(self):
        tarefas = [asyncio.create_task(self.canal(c)) for c in self.metricas
                   if c != 'imagens' or self.receber_imagens]
        try:
            await self.fim.wait()
        finally:
            for t in tarefas:
                t.cancel()
            await asyncio.gather(*tarefas, return_exceptions=True)

    def parar(self):
        self.fim.set()

    def snapshot(self):
        agora = time.monotonic()
        def valido(item):
            return item is not None and agora-item[1]+item[0].get('idade_limite_recepcao_s', 0) <= self.op.validade_s
        return dict(servidor=self.url, estados=dict(self.estados), simulado=self.simulado,
                    canais={c: m.snapshot() for c, m in self.metricas.items()},
                    ultima_telemetria=self.ultima[0] if valido(self.ultima) else None,
                    ultimo_frame=self.ultimo_frame[0] if valido(self.ultimo_frame) else None)

    async def proxima(self, canal, timeout=1.):
        """Interface de consumo: rejeita item vencido também ao sair da fila local."""
        if canal not in self.metricas:
            raise ValueError('Canal inexistente')
        fila = self.telemetrias if canal == 'telemetria' else self.imagens
        async with asyncio.timeout(timeout):
            while True:
                item = await fila.get()
                msg, _, recepcao = item
                if time.monotonic()-recepcao+msg['idade_limite_recepcao_s'] <= min(self.op.validade_s, msg['validade_s']):
                    return item
                self.metricas[canal].contar('descartes_antigos_consumidor')

    async def canal(self, canal):
        metrica = self.metricas[canal]
        tentativas = 0
        while not self.fim.is_set():
            self.estados[canal] = 'conectando'
            ola = None
            try:
                async with connect(self.url+'/ws/'+canal,
                    additional_headers={'Authorization': 'Bearer '+self.op.token},
                    compression=None, open_timeout=self.op.timeout_s,
                    close_timeout=self.op.timeout_s, ping_interval=None,
                    max_queue=self.op.fila, write_limit=32768,
                    max_size=self.op.max_json+(self.op.max_jpeg+4 if canal == 'imagens' else 0)) as ws:
                    if tentativas:
                        metrica.contar('reconexoes')
                    tentativas += 1
                    metrica.conectado_em = time.monotonic()
                    ola = decodificar(await asyncio.wait_for(ws.recv(), self.op.timeout_s), self.op.max_json)
                    if ola['tipo'] != 'ola' or ola['dados'].get('canal') != canal:
                        raise ValueError('Handshake invalido')
                    metrica.ultima_sessao = ola['sessao']
                    self.estados[canal] = 'sincronizando'
                    self.simulado = ola['simulado']
                    self.evento('conexao_estabelecida' if tentativas == 1 else 'reconexao', canal, ola)
                    self._limpar(canal)
                    await self.receber(ws, canal, ola)
            except (OSError, ConnectionClosed, InvalidHandshake, TimeoutError, ValueError):
                metrica.contar('falhas_conexao')
                self.estados[canal] = 'desconectado'
            finally:
                if metrica.conectado_em is not None:
                    metrica.contar('desconexoes')
                    self.evento('conexao_encerrada' if self.fim.is_set() else 'desconexao', canal, ola)
                metrica.conectado_em = None
                metrica.encerrar_rtt()
                self.estados[canal] = 'desconectado'
                self._limpar(canal)
            try:
                await asyncio.wait_for(self.fim.wait(), self.op.reconexao_s)
            except TimeoutError:
                pass

    def _limpar(self, canal):
        fila = self.telemetrias if canal == 'telemetria' else self.imagens
        while not fila.empty():
            fila.get_nowait()
        if canal == 'telemetria':
            self.ultima = None
        else:
            self.ultimo_frame = None

    async def receber(self, ws, canal, ola):
        metrica = self.metricas[canal]
        sequencia = Sequencia()
        relogio = {'offset_min': None, 'atualizado': None, 'nonce': None,
                   'enviada': None, 'eco': asyncio.Event()}
        async def sondar():
            seq = 0
            while True:
                seq += 1
                relogio['nonce'] = secrets.token_hex(16)
                relogio['enviada'] = time.monotonic()
                relogio['eco'].clear()
                msg = envelope(ola['sessao'], seq, 'sonda', dict(nonce=relogio['nonce']),
                               origem='computador', validade=self.op.validade_s)
                texto = codificar(msg)
                await asyncio.wait_for(ws.send(texto), self.op.timeout_s)
                metrica.contar('mensagens_tx')
                metrica.contar('bytes_tx', len(texto.encode('utf-8')))
                try:
                    await asyncio.wait_for(relogio['eco'].wait(), self.op.timeout_s)
                except TimeoutError:
                    metrica.contar('timeouts')
                    await ws.close(1011, 'Heartbeat sem eco')
                    return
                await asyncio.sleep(self.op.heartbeat_s)
        sonda = asyncio.create_task(sondar())
        try:
            async for pacote in ws:
                agora = time.monotonic()
                metrica.contar('mensagens_rx')
                metrica.contar('bytes_rx', len(pacote.encode('utf-8')) if isinstance(pacote, str) else len(pacote))
                try:
                    if isinstance(pacote, bytes):
                        if canal != 'imagens':
                            raise ValueError('Binario no canal incorreto')
                        msg, jpeg = desempacotar_imagem(pacote, self.op.max_json, self.op.max_jpeg)
                    else:
                        msg, jpeg = decodificar(pacote, self.op.max_json), None
                    if (msg['sessao'] != ola['sessao'] or msg['simulado'] != ola['simulado'] or
                            msg['origem'] != ola['origem']):
                        raise ValueError('Sessao/dominio mudou sem novo handshake')
                    if msg['tipo'] == 'eco':
                        if msg['dados'].get('nonce') != relogio['nonce'] or relogio['eco'].is_set():
                            raise ValueError('Eco nao correlacionado')
                        metrica.rtt(agora-relogio['enviada'])
                        # Limite inferior de offset por causalidade, não latência unidirecional.
                        relogio['offset_min'] = relogio['enviada']-msg['monotonic_s']
                        relogio['atualizado'] = agora
                        relogio['eco'].set()
                        self.estados[canal] = 'conectado'
                        continue
                    if msg['tipo'] != ('imagem' if canal == 'imagens' else 'telemetria'):
                        raise ValueError('Tipo inesperado no canal')
                    if (canal == 'imagens') != (jpeg is not None):
                        raise ValueError('Imagem exige pacote binario')
                    if jpeg is not None:
                        if (type(msg['dados'].get('frame_id')) is not int or msg['dados']['frame_id'] < 0 or
                                msg['dados'].get('jpeg_bytes') != len(jpeg)):
                            raise ValueError('Metadados JPEG invalidos')
                    elif (msg['dados'].get('schema') != 'benchmark_robo_v1' or
                          not isinstance(msg['dados'].get('telemetria'), dict)):
                        raise ValueError('Schema de telemetria invalido')
                    antes = sequencia.lacunas
                    if not sequencia.aceitar(msg):
                        metrica.contar('duplicadas_ou_sessao_antiga')
                        continue
                    metrica.contar('lacunas', sequencia.lacunas-antes)
                    if relogio['offset_min'] is None or agora-relogio['atualizado'] > self.op.timeout_s+self.op.heartbeat_s:
                        metrica.contar('descartes_sem_referencia_temporal')
                        continue
                    idade_superior = agora-msg['monotonic_s']-relogio['offset_min']+msg['idade_envio_s']
                    if idade_superior < 0 or idade_superior > min(self.op.validade_s, msg['validade_s']):
                        metrica.contar('descartes_antigos')
                        continue
                    msg['idade_limite_recepcao_s'] = idade_superior
                    msg['recepcao_utc'] = datetime.now(timezone.utc).isoformat()
                    item = msg, jpeg, agora
                    if self.distribuidor is not None:
                        self.distribuidor.publicar(canal, item)
                    fila = self.imagens if jpeg is not None else self.telemetrias
                    metrica.contar('descartes_fila_local', oferecer(fila, item))
                    if jpeg is None:
                        self.ultima = msg, agora
                        metrica.ultima_telemetria = agora
                        metrica.contar('telemetrias')
                    else:
                        self.ultimo_frame = msg, agora
                        metrica.contar('frames')
                    if self.consumo_lento_s:
                        await asyncio.sleep(self.consumo_lento_s)
                except ValueError:
                    metrica.contar('mensagens_invalidas')
        finally:
            sonda.cancel()
            await asyncio.gather(sonda, return_exceptions=True)
