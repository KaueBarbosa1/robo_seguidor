"""Serviço PC: assinante da captura existente, fila latest=1 e canal de retorno.

A inferência roda fora do navegador e fora do loop de rede. Comandos não
sobrevivem ao prazo na fila; a reconexão nunca reenvia intenções anteriores.
"""
import asyncio
from collections import Counter,deque
from concurrent.futures import Future
import queue
import threading
import time
import uuid

from websockets.asyncio.client import connect
from comunicacao.protocolo import envelope,codificar,decodificar
from distribuido.configuracao import CONTRATO,OpcoesDistribuidas
from distribuido.percepcao import Pipeline,decodificar_jpeg


class ServicoPC:
    def __init__(self,url,opcoes,bus,tokens,config=None):
        self.url,self.op,self.bus,self.tokens=url,opcoes,bus,dict(tokens)
        self.cfg=config or OpcoesDistribuidas();self.lock=threading.RLock();self.fim=threading.Event()
        self.ass=bus.assinar({'imagens'},1);self.pedidos=queue.Queue(16);self.resultados=queue.Queue(1)
        self.contas=Counter();self.tempos=deque(maxlen=512);self.remoto={};self.autorizacao=None
        self.sessao=None;self.simulado=None;self.status='desconectado';self.erro=None;self.pipeline=Pipeline()
        self.pausa_inferencia=False;self.atraso_s=0.;self.falha_inferencia=False
        self.threads=[];self.epoch=0;self.operador_ui=None
        self.inicio=time.monotonic();self.chave_pipeline=None;self.frame_decodificado=None

    def iniciar(self):
        self.threads=[threading.Thread(target=self._rede,name='retorno-operacional',daemon=True),
                      threading.Thread(target=self._inferir,name='inferencia-PC',daemon=True)]
        for t in self.threads:t.start()

    def configurar(self,algoritmo,manifesto=None):
        with self.lock:
            if self.remoto.get('operacao')!='parado':raise ValueError('Pare antes de trocar o algoritmo')
        novo=Pipeline(algoritmo,manifesto)
        self.comandar({'acao':'algoritmo','algoritmo':algoritmo})
        with self.lock:self.pipeline=novo;self.epoch+=1;self.erro=None;self.tempos.clear();self.ultimo=None

    def comandar(self,d,operador=None,timeout=2.):
        with self.lock:
            if self.status!='conectado':raise ValueError('Canal operacional desconectado')
            acao=d.get('acao')
            if operador is not None:
                if acao=='habilitar':
                    if self.operador_ui not in (None,operador):raise ValueError('Outra aba possui a autorização')
                    self.operador_ui=operador
                elif acao=='movimento' and self.operador_ui!=operador:raise ValueError('Aba sem autorização exclusiva')
            dados=dict(d,contrato=CONTRATO,geracao=self.remoto.get('geracao'))
            if acao=='movimento':dados['autorizacao']=self.autorizacao
            if acao in ('liberar','parar','emergencia'):self.operador_ui=None
            futuro=Future()
            if acao in ('parar','emergencia'):
                # Parada tem prioridade também na fila do PC.
                while True:
                    try:
                        _,_,ant=self.pedidos.get_nowait()
                        if ant and not ant.done():ant.set_exception(ValueError('Cancelado por parada prioritária'))
                    except queue.Empty:break
            try:self.pedidos.put_nowait((time.monotonic()+self.cfg.comando_s,dados,futuro))
            except queue.Full:raise ValueError('Fila de comandos ocupada')
        try:return futuro.result(timeout)
        except TimeoutError:
            futuro.cancel();raise ValueError('Sem confirmação do pedido; movimento não confirmado')

    def _oferecer_resultado(self,item):
        while True:
            try:self.resultados.put_nowait(item);return
            except queue.Full:
                try:self.resultados.get_nowait();self.contas['resultados_substituidos']+=1
                except queue.Empty:pass

    def _inferir(self):
        proximo=0.
        while not self.fim.is_set():
            if self.fim.wait(max(0.,proximo-time.monotonic())):break
            try:_,item=self.ass.fila.get(timeout=.1)
            except queue.Empty:continue
            msg,jpeg,recepcao=item
            with self.lock:pipeline=self.pipeline;ep=self.epoch;remoto=dict(self.remoto)
            if self.status!='conectado' or remoto.get('processamento')!='distribuido' or self.pausa_inferencia:continue
            if not self.simulado and not self.cfg.distribuido_real:continue
            if msg['sessao']!=self.sessao:continue
            proximo=time.monotonic()+1/self.cfg.inferencia_hz
            inicio=time.perf_counter()
            try:
                if self.atraso_s:self.fim.wait(self.atraso_s)
                if self.falha_inferencia:raise ValueError('Falha de inferência injetada em simulação')
                if time.monotonic()-recepcao+msg['idade_limite_recepcao_s']>self.cfg.resultado_s:
                    self.contas['frames_vencidos']+=1;continue
                chave=(msg['sessao'],msg['dados'].get('geracao'),msg['dados'].get('geracao_camera'),msg['dados'].get('sessao_visao'),ep)
                if chave!=self.chave_pipeline:pipeline.resetar();self.chave_pipeline=chave
                frame,dec=decodificar_jpeg(jpeg)
                with self.lock:self.frame_decodificado=(msg['dados']['frame_id'],frame)
                r=pipeline.processar(frame)
                r['decodificacao_s']=dec;r['tempo_pc_s']=time.perf_counter()-inicio
                with self.lock:
                    if ep!=self.epoch or msg['sessao']!=self.sessao:continue
                    dados=dict(contrato=CONTRATO,frame_id=msg['dados']['frame_id'],
                        geracao=msg['dados'].get('geracao'),sessao_visao=msg['dados'].get('sessao_visao'),
                        inferencia_id=str(uuid.uuid4()),resultado=r)
                    self._oferecer_resultado((msg['sessao'],dados));self.contas['frames_processados']+=1
                    self.tempos.append(r['tempo_pc_s']);self.ultimo=r;self.erro=None
            except Exception as exc:
                with self.lock:self.erro=type(exc).__name__+': '+str(exc);self.contas['falhas_inferencia']+=1
                self._oferecer_resultado((msg['sessao'],dict(contrato=CONTRATO,falha=self.erro)))

    def _rede(self):
        asyncio.run(self._executar())

    async def _executar(self):
        while not self.fim.is_set():
            try:
                headers={'Authorization':'Bearer '+self.op.token,**{'X-Robo-'+p:t for p,t in self.tokens.items()}}
                async with connect(self.url+'/ws/operacao',additional_headers=headers,compression=None,
                    max_size=self.op.max_json,max_queue=1,ping_interval=None,open_timeout=2,close_timeout=.5) as ws:
                    ola=decodificar(await asyncio.wait_for(ws.recv(),2))
                    if ola['tipo']!='ola' or ola['dados'].get('contrato')!=CONTRATO:raise ValueError('Handshake operacional inválido')
                    with self.lock:
                        self.sessao=ola['sessao'];self.simulado=ola['simulado'];self.remoto=ola['dados']['estado']
                        self.status='conectado';self.autorizacao=None;self.epoch+=1;self.operador_ui=None
                        self.desafio=ola['dados']['desafio']
                        self.permissoes=ola['dados']['permissoes']
                    self.contas['conexoes']+=1
                    seq=0;ultimo_heartbeat=0.;pronto=None
                    while not self.fim.is_set():
                        futuro=None;tipo='comando';dados=None
                        try:
                            prazo,dados,futuro=self.pedidos.get_nowait()
                            if futuro.cancelled() or time.monotonic()>prazo:
                                if not futuro.done():futuro.set_exception(ValueError('Comando expirou antes do envio'))
                                self.contas['comandos_vencidos']+=1;continue
                        except queue.Empty:pass
                        if dados is None:
                            with self.lock:p=self.pipeline
                            identidade=(p.algoritmo,p.versao,self.remoto.get('algoritmo'))
                            if 'percepcao' in self.tokens and identidade!=pronto and p.algoritmo==self.remoto.get('algoritmo'):
                                dados=dict(acao='pronto',algoritmo=p.algoritmo,versao_modelo=p.versao);pronto=identidade
                            elif time.monotonic()-ultimo_heartbeat>=self.cfg.heartbeat_s:
                                dados=dict(acao='heartbeat' if 'percepcao' in self.tokens else 'consulta');ultimo_heartbeat=time.monotonic()
                            else:
                                try:
                                    sessao,dados=self.resultados.get_nowait()
                                    if sessao!=self.sessao:continue
                                    if 'falha' in dados:dados=dict(acao='falha_percepcao',motivo=dados['falha'])
                                    else:tipo='inferencia'
                                except queue.Empty:
                                    await asyncio.sleep(.01);continue
                        seq+=1;dados=dict(dados,contrato=CONTRATO,desafio=self.desafio)
                        texto=codificar(envelope(self.sessao,seq,tipo,dados,self.simulado,'computador',validade=self.cfg.comando_s))
                        t=time.monotonic()
                        try:
                            await asyncio.wait_for(ws.send(texto),.5)
                            recebida=decodificar(await asyncio.wait_for(ws.recv(),.6))
                            if recebida['sessao']!=self.sessao or recebida['simulado']!=self.simulado or recebida['tipo']!='referencia' or recebida['origem']!=ola['origem']:raise ValueError('Confirmação de sessão/domínio incorreta')
                            resposta=recebida['dados']
                            if resposta.get('sequencia')!=seq:raise ValueError('Confirmação não correlacionada')
                            with self.lock:
                                self.remoto=resposta['estado'];self.autorizacao=self.remoto.pop('autorizacao',None)
                                self.desafio=resposta['desafio']
                                if not self.remoto.get('autorizacao_ativa'):self.operador_ui=None
                            self.contas['mensagens_tx']+=1;self.contas['bytes_tx']+=len(texto.encode())
                            self.ultimo_rtt_s=time.monotonic()-t
                            if not resposta['ok']:
                                self.contas['rejeitadas']+=1;self.erro=resposta['erro']
                                if futuro and not futuro.done():futuro.set_exception(ValueError(resposta['erro']))
                            elif futuro and not futuro.done():futuro.set_result(self.snapshot())
                        except Exception as exc:
                            if futuro and not futuro.done():futuro.set_exception(ValueError('Canal interrompido; confirmação ausente'))
                            raise exc
            except Exception as exc:
                with self.lock:self.erro=type(exc).__name__+': '+str(exc);self.contas['falhas_conexao']+=1
            finally:
                with self.lock:
                    self.status='desconectado';self.sessao=None;self.autorizacao=None;self.operador_ui=None;self.epoch+=1
                    self.frame_decodificado=None;self.ultimo=None
                    self.remoto=dict(self.remoto,autorizacao_ativa=False,remoto_pronto=False,ultimo_resultado=None,
                        frame_id=None,idade_resultado_s=None,fase='CONEXAO_PERDIDA',operacao='indisponivel',fonte_controle='indisponivel')
                while True:
                    try:
                        _,_,f=self.pedidos.get_nowait()
                        if not f.done():f.set_exception(ValueError('Conexão encerrada; pedido descartado'))
                    except queue.Empty:break
            for _ in range(30):
                if self.fim.is_set():break
                await asyncio.sleep(.01)

    def snapshot(self):
        with self.lock:
            from distribuido.metricas import estatisticas
            return dict(status=self.status,erro=self.erro,remoto=dict(self.remoto),contadores=dict(self.contas),
                permissoes=list(getattr(self,'permissoes',[])),
                ultimo_resultado=getattr(self,'ultimo',None),tempos_pc_s=list(self.tempos),
                rtt_operacao_s=getattr(self,'ultimo_rtt_s',None),fila_frames=self.ass.fila.qsize(),
                estatisticas_pc_s=estatisticas(list(self.tempos)),estatisticas_ciclo_s=estatisticas(self.remoto.get('latencias_s',[])),
                fila_comandos=self.pedidos.qsize(),fila_resultados=self.resultados.qsize(),
                descartes_frames=self.ass.contas['descartadas'],inferencia_hz_alvo=self.cfg.inferencia_hz,
                frequencia_efetiva_hz=self.contas['frames_processados']/max(.001,time.monotonic()-self.inicio),
                duracao_s=time.monotonic()-self.inicio)

    def fechar(self):
        self.fim.set()
        for t in self.threads:t.join(timeout=3)
        self.bus.remover(self.ass)
