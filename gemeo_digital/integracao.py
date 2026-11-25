"""Ponte local PC: consome Cliente/Distribuidor e Reprodutor existentes."""
import asyncio
from dataclasses import asdict
from datetime import datetime,timezone
import json
from pathlib import Path
import queue
import secrets
import threading
import time
import uuid

import config as cfg
from comunicacao.cliente import Cliente
from comunicacao.configuracao import Opcoes,url_local
from comunicacao.distribuidor import Distribuidor
from comunicacao.servidor import Servidor
from armazenamento.consultas import Historico
from armazenamento.reproducao import Reprodutor
from gemeo_digital.cinematica import Calibracao
from gemeo_digital.estado_visual import EstadoVisual
from gemeo_digital.simulacao import Cenario,FonteCenario,AmostrasCenario

CAL_SIM=Calibracao(20,20,.065,.065,.18,simulada=True,relacao_disco_roda=1.)


class Fluxo:
    def __init__(self,ponte,epoch,simulado):
        self.ponte,self.epoch,self.simulado=ponte,epoch,simulado
        self.bus=Distribuidor();self.ass=self.bus.assinar({'telemetria','imagens','eventos'},64)
        self.fim=threading.Event();self.pronto=threading.Event();self.loop=None;self.cliente=None
        self.camera=self.servidor=self.gravador=None
        if simulado:
            self.camera=FonteCenario(ponte.cenario);self.camera.iniciar()
            op=Opcoes.central(secrets.token_hex(24),host=cfg.REDE_SIM_HOST,porta=0)
            self.servidor=Servidor(op,AmostrasCenario(ponte.cenario,self.camera),self.camera,True)
            self.servidor.iniciar();self.url=url_local(op.host,self.servidor.porta)
            self.op=op
        else:
            if not ponte.url_real:raise ValueError('Defina --servidor e ROBO_REDE_TOKEN no terminal')
            self.url=ponte.url_real;self.op=Opcoes.central(ponte.token_real)
        if ponte.gravar:
            from armazenamento.gravador import Gravador
            from armazenamento.configuracao import OpcoesArmazenamento
            self.gravador=Gravador(self.bus,OpcoesArmazenamento.central(raiz=ponte.historico.raiz))
            self.gravador.iniciar();self.gravador.nova_gravacao('Gêmeo digital',modo='simulacao' if simulado else 'observacao_embarcada')
        self.thread=threading.Thread(target=self._rede,daemon=True,name='gemeo-cliente');self.thread.start()
        self.pump=threading.Thread(target=self._consumir,daemon=True,name='gemeo-fanout');self.pump.start()
        if not self.pronto.wait(3):raise RuntimeError('Cliente não iniciou')

    def _rede(self):
        async def run():
            self.loop=asyncio.get_running_loop()
            self.cliente=Cliente(self.url,self.op,distribuidor=self.bus)
            self.pronto.set();await self.cliente.executar()
        asyncio.run(run())

    def _consumir(self):
        while not self.fim.is_set():
            try:canal,item=self.ass.fila.get(timeout=.1)
            except queue.Empty:continue
            if canal=='telemetria':
                if self.ponte.receber(item[0],item[2],self.epoch) and self.gravador:
                    pose=self.ponte.estado.pose
                    if pose['validade']=='estimativa':
                        self.bus.publicar('odometria',dict(sessao=item[0]['sessao'],timestamp=item[0]['recepcao_utc'],pose=pose))
            elif canal=='imagens':self.ponte.receber_imagem(item,self.epoch)
            elif item['tipo']=='desconexao':self.ponte.invalidar(self.epoch)

    def fechar(self):
        self.fim.set()
        if self.loop and self.cliente and not self.loop.is_closed():self.loop.call_soon_threadsafe(self.cliente.parar)
        self.thread.join(timeout=7);self.pump.join(timeout=1)
        if self.servidor:self.servidor.parar()
        if self.camera:self.camera.parar()
        if self.gravador:self.gravador.fechar()


class Ponte:
    def __init__(self,raiz_historico,url_real=None,token_real='',gravar=False):
        self.historico=Historico(raiz_historico);self.url_real=url_real;self.token_real=token_real;self.gravar=gravar
        self.lock=threading.RLock();self.modo_lock=threading.Lock()
        self.cenario=Cenario();self.epoch=0;self.modo='simulado';self.fluxo=None
        self.replay=None;self.replay_thread=None;self.replay_pausado=True;self.velocidade=1.
        self.estado=EstadoVisual(CAL_SIM);self.foto=None;self.status='iniciando';self.selecionada=None
        self.eventos=[];self.cal_real=Calibracao()

    def modo_alterar(self,modo):
        if modo not in ('simulado','real','historico'):raise ValueError('Modo inválido')
        if modo=='real' and (not self.url_real or not self.token_real):raise ValueError('Telemetria real não configurada no terminal')
        with self.modo_lock:
            self._parar_fonte()
            with self.lock:
                self.epoch+=1;self.modo=modo;self.estado=EstadoVisual(CAL_SIM if modo=='simulado' else self.cal_real)
                self.foto=None;self.eventos=[];self.status='aguardando dados';self.selecionada=None
            if modo!='historico':self.fluxo=Fluxo(self,self.epoch,modo=='simulado')

    def receber(self,msg,recepcao,epoch):
        with self.lock:
            if epoch!=self.epoch:return False
            ok=self.estado.aceitar(msg,recepcao)
            if ok:
                self.status='histórico' if self.modo=='historico' else 'conectado'
                if self.modo=='simulado':
                    p=self.estado.pose
                    with self.cenario.lock:self.cenario.pose=(p['x_m'],p['y_m'],p['orientacao_rad'])
            return ok

    def receber_imagem(self,item,epoch):
        with self.lock:
            if epoch==self.epoch:self.foto=item

    def invalidar(self,epoch):
        with self.lock:
            if epoch==self.epoch:self.estado.invalidar();self.status='desconectado';self.foto=None

    def snapshot(self):
        with self.lock:
            idade=None;posicao=None
            if self.modo=='historico' and self.replay and self.estado.msg:
                posicao=self.replay.posicao_utc
                gravada=self.estado.msg.get('recepcao_utc',self.estado.msg['timestamp'])
                idade=max(0,datetime.fromisoformat(posicao).timestamp()-datetime.fromisoformat(gravada).timestamp())
            d=self.estado.snapshot(idade)
            imagem=None
            if self.foto and d.get('disponivel'):
                meta,_,recebida=self.foto
                idade_imagem=(max(0,datetime.fromisoformat(posicao).timestamp()-datetime.fromisoformat(meta.get('recepcao_utc',meta['timestamp'])).timestamp())
                              if self.modo=='historico' and posicao else max(0,time.monotonic()-recebida))
                idade_imagem+=meta.get('idade_limite_recepcao_s',0)
                camera_ok=self.estado.msg['dados']['telemetria'].get('visao',{}).get('camera_ok')
                if idade_imagem<=.5 and camera_ok is not False:imagem=dict(meta,idade_visualizacao_s=idade_imagem)
            return dict(modo=self.modo,epoch=self.epoch,status=self.status if d.get('disponivel') else 'sem dados válidos',
                dados=d,simulacao=self.cenario.ler(),replay=dict(pausado=self.replay_pausado,
                velocidade=self.velocidade,posicao_utc=posicao,sessao=self.selecionada),eventos=self.eventos[-40:],
                imagem=imagem)

    def imagem(self):
        with self.lock:
            if not self.snapshot()['dados'].get('disponivel') or not self.foto:return None
            msg,jpeg,instante=self.foto
            if self.modo=='historico':
                idade=datetime.fromisoformat(self.replay.posicao_utc).timestamp()-datetime.fromisoformat(msg.get('recepcao_utc',msg['timestamp'])).timestamp()
            else:idade=time.monotonic()-instante
            if idade+msg.get('idade_limite_recepcao_s',0)>.5:return None
            if self.modo=='simulado' and not self.cenario.ler()['camera']:return None
            return jpeg,msg['dados']['frame_id']

    def sessoes(self):
        try:return self.historico.consultar('sessoes',limite=100)
        except Exception:return []

    def trajeto_sessao(self,sessao):
        uuid.UUID(sessao)
        info=next((s for s in self.sessoes() if s['id']==sessao),None)
        if info is None:raise ValueError('Sessão não encontrada')
        estado=EstadoVisual(CAL_SIM if info['simulado'] else self.cal_real)
        for row in Reprodutor(self.historico,sessao,imagens=False).registros():
            if row['categoria']=='telemetria':estado.aceitar(json.loads(row['mensagem_json']))
            elif row['categoria']=='odometria':estado.restaurar_pose(json.loads(row['mensagem_json']))
        return dict(pontos=estado.odom.trajeto,natureza='Trajetória recalculada com parâmetros simulados' if info['simulado'] else 'Sem calibração física confirmada; trajetória indisponível')

    def simular(self,dados):
        if self.modo!='simulado':raise ValueError('Controles exclusivos da simulação')
        self.cenario.atualizar(dados)
        if self.fluxo and self.fluxo.servidor:self.fluxo.servidor.falhas['atraso_s']=self.cenario.ler()['latencia']

    def _parar_replay(self):
        if self.replay:self.replay.parar()
        if self.replay_thread:self.replay_thread.join(timeout=2)
        self.replay=None;self.replay_thread=None

    def historico_selecionar(self,sessao,instante=None):
        uuid.UUID(sessao)
        if self.modo!='historico':raise ValueError('Escolha o modo histórico')
        with self.modo_lock:
            self._parar_replay()
            info=next((s for s in self.sessoes() if s['id']==sessao),None)
            if info is None:raise ValueError('Sessão não encontrada na base existente')
            novo=EstadoVisual(CAL_SIM if info['simulado'] else self.cal_real)
            alvo=instante or info['inicio_observado_utc']
            alvo=max(info['inicio_observado_utc'],min(info['fim_observado_utc'],datetime.fromisoformat(alvo).astimezone(timezone.utc).isoformat()))
            limite=datetime.fromisoformat(alvo).timestamp()
            foto=None;eventos=[]
            # Restaura o prefixo com memória constante; não acumula rotações do estado anterior.
            reader=Reprodutor(self.historico,sessao,imagens=False)
            for row in reader.registros():
                if datetime.fromisoformat(row['instante']).timestamp()>limite:break
                if row['categoria']=='telemetria':
                    msg=json.loads(row['mensagem_json']);msg['recepcao_utc']=row['instante'];novo.aceitar(msg)
                elif row['categoria']=='odometria':novo.restaurar_pose(json.loads(row['mensagem_json']))
                elif row['categoria']=='imagens':
                    from armazenamento.imagens import seguro,hash_arquivo
                    p=seguro(self.historico.raiz,row['caminho'])
                    if p.is_file() and p.stat().st_size<=4*1024*1024 and hash_arquivo(p)==row['sha256']:
                        msg=json.loads(row['mensagem_json']);msg['recepcao_utc']=row['instante']
                        foto=(msg,p.read_bytes(),time.monotonic())
                elif row['categoria']=='eventos':eventos=(eventos+[dict(timestamp=row['instante'],detalhes=json.loads(row['mensagem_json']))])[-40:]
            with self.lock:
                self.epoch+=1;self.estado=novo;self.foto=foto;self.eventos=eventos[-40:];self.selecionada=sessao
                self.status='histórico'
                self.replay=Reprodutor(self.historico,sessao,self.velocidade);self.replay.buscar(alvo);self.replay.pausar()
                self.replay_pausado=True;epoch=self.epoch
            self.replay_thread=threading.Thread(target=self._reproduzir,args=(epoch,alvo),daemon=True,name='gemeo-replay')
            self.replay_thread.start()

    def _reproduzir(self,epoch,alvo):
        replay=self.replay
        ultimo=alvo
        for item in replay.iniciar():
            if epoch!=self.epoch:break
            ultimo=item['timestamp_utc']
            if datetime.fromisoformat(ultimo)<=datetime.fromisoformat(alvo):continue
            if item['categoria']=='telemetria':
                msg=item['envelope_original'];msg['recepcao_utc']=item['timestamp_utc'];self.receber(msg,time.monotonic(),epoch)
            elif item['categoria']=='odometria':
                with self.lock:
                    if epoch==self.epoch:self.estado.restaurar_pose(item['envelope_original'])
            elif item['categoria']=='imagens' and item['jpeg']:
                msg=item['envelope_original'];msg['recepcao_utc']=item['timestamp_utc']
                self.receber_imagem((msg,item['jpeg'],time.monotonic()),epoch)
            elif item['categoria'] in ('eventos','intervalos'):
                with self.lock:self.eventos=(self.eventos+[dict(timestamp=item['timestamp_utc'],detalhes=item['envelope_original'])])[-40:]
        with self.lock:
            if epoch==self.epoch and replay is self.replay:
                replay.pausar();replay.buscar(ultimo);self.replay_pausado=True

    def controle_replay(self,d):
        if not self.replay:raise ValueError('Selecione uma sessão')
        acao=d.get('acao')
        if acao=='buscar':self.historico_selecionar(self.selecionada,d['instante'])
        elif acao=='reiniciar':self.historico_selecionar(self.selecionada)
        elif acao=='pausar':self.replay.pausar();self.replay_pausado=True
        elif acao=='reproduzir':self.replay.retomar();self.replay_pausado=False
        elif acao=='velocidade':
            self.replay.velocidade(d['fator']);self.velocidade=d['fator']
        else:raise ValueError('Ação histórica inválida')

    def _parar_fonte(self):
        self._parar_replay()
        if self.fluxo:self.fluxo.fechar();self.fluxo=None

    def fechar(self):self._parar_fonte()
