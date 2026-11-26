"""Raspberry/Arduino virtuais com ThreadControle real, sem ArduinoSerial."""
from dataclasses import replace
from datetime import datetime,timezone
import threading
import time
from types import SimpleNamespace

import cv2
import config as cfg
from estado import EstadoRobo
from motor.nulo import ArduinoNulo
from controle import ThreadControle
from comunicacao.simulacao import CameraSimulada,SensoresSimulados
from comunicacao.amostras import Amostras
from monitoramento.telemetria import Telemetria
from distribuido.autoridade import Autoridade
from distribuido.percepcao import Pipeline,decodificar_jpeg


class CameraIntegrada(CameraSimulada):
    """Mesmo gerador/captura JPEG compartilhada; sem detector duplicado."""
    def __init__(self,cenario,estado,fps=30):
        super().__init__(fps);self.cenario=cenario;self.estado=estado;self.geracao=0;self.imagem_teste=None

    def _loop(self):
        while not self.fim.is_set():
            ident,imagem=self.fonte.proximo_quadro(self.ident)
            d=self.cenario.ler()
            if not d['camera']:
                self.geracao+=1;self.fim.wait(.05);continue
            imagem=cv2.resize(imagem,(320,240),interpolation=cv2.INTER_NEAREST)
            # A pista virtual da etapa6 tem fita tracejada, como o detector
            # embarcado atual. Altera o cenário, não os parâmetros do detector.
            for y in range(35,240,55):imagem[y:y+12]=220
            if self.imagem_teste is not None:imagem=self.imagem_teste.copy()
            if not d['linha']:imagem[:]=220
            ok,jpeg=cv2.imencode('.jpg',imagem)
            if ok:
                dados=jpeg.tobytes();dec,_=decodificar_jpeg(dados)
                q=SimpleNamespace(jpeg=dados,imagem=dec,recepcao_monotonica=time.monotonic(),
                    idade_recepcao_limite_ms=d.get('idade_frame_s',0.)*1000,geracao=self.geracao)
                with self.lock:self.ident,self.quadro=ident,q

    def proximo_jpeg_detalhado(self,*a,**kw):
        if not self.cenario.ler()['camera']:return None
        return super().proximo_jpeg_detalhado(*a,**kw)

    def saude(self):
        with self.lock:
            ok=self.cenario.ler()['camera'] and self.quadro is not None and time.monotonic()-self.quadro.recepcao_monotonica<=self.idade_max_s
            return dict(status='ok' if ok else 'indisponivel',geracao=self.geracao)


class MotorIntegrado(ArduinoNulo):
    def __init__(self,cenario):
        super().__init__();self.cenario=cenario;self.t=time.monotonic();self.ticks=[0.,0.];self.pps=(0.,0.)
        self.autor_escrita=set()

    def velocidade(self,esq,dir_):
        with self._lock:
            self.autor_escrita.add(threading.current_thread().name)
            self.pps=(float(esq),float(dir_));self.ultimo=(round(esq/cfg.VELOCIDADE_REFERENCIA_PPS*255),round(dir_/cfg.VELOCIDADE_REFERENCIA_PPS*255))
            self.estatisticas['comandos']+=1

    def motores(self,esq,dir_):self.velocidade(esq*cfg.VELOCIDADE_REFERENCIA_PPS/255,dir_*cfg.VELOCIDADE_REFERENCIA_PPS/255)

    def parar(self,repetir=1):
        with self._lock:self.pps=(0.,0.);self.ultimo=(0,0)

    def sensores(self):
        d=self.cenario.ler();a=time.monotonic()
        with self._lock:
            dt=a-self.t;self.t=a
            if not d['arduino']:self.pps=(0.,0.);self.ultimo=(0,0);return None
            if d.get('emergencia') or not d['motores']:self.pps=(0.,0.);self.ultimo=(0,0)
            self.ticks=[t+abs(v)*dt for t,v in zip(self.ticks,self.pps)]
            distancia=self.cenario.distancia();bloqueado=distancia<cfg.OBSTACULO_DIST_CM
            return SensoresSimulados(round(distancia),int(self.ticks[0]),int(self.ticks[1]),a,bloqueado,d.get('falha_sensor',False),bloqueado)

    def estado_motores(self):
        if not self.cenario.ler()['arduino']:return None
        with self._lock:return SimpleNamespace(pwm_esq=self.ultimo[0],pwm_dir=self.ultimo[1],falha_encoder=False,pi_ativo=True,timestamp=time.monotonic(),manual_sem_ultrassom=False)

    def status_servo(self):return SimpleNamespace(angulo_nominal=self.cenario.ler()['servo'],timestamp=time.monotonic(),ativo=False,sonar_movimento=False)


class RuntimeSimulado:
    def __init__(self,cenario,opcoes=None,camera_fps=30):
        self.cenario=cenario;self.estado=EstadoRobo();self.motor=MotorIntegrado(cenario)
        self.camera=CameraIntegrada(cenario,self.estado,camera_fps);self.fim=threading.Event()
        self.autoridade=Autoridade(self.estado,self.motor,self.camera,opcoes,simulado=True)
        self.controle=ThreadControle(self.estado,self.motor,self.fim,self.camera)
        self.pipeline=Pipeline();self.thread=threading.Thread(target=self._local,name='percepcao-local-simulada',daemon=True)

    def iniciar(self):
        self.controle.start();self.thread.start()

    def _local(self):
        ultimo=0;geracao=None
        while not self.fim.is_set():
            d=self.cenario.ler()
            if d['emergencia'] and not self.autoridade.emergencia:self.autoridade.parar('cenario_emergencia',True)
            if self.autoridade.processamento!='embarcado' or self.autoridade.algoritmo!='opencv':self.fim.wait(.02);continue
            q=self.camera.proximo_jpeg_detalhado(ultimo)
            if q:
                ident,quadro=q;ultimo=ident
                if geracao!=self.autoridade.geracao:self.pipeline.resetar();geracao=self.autoridade.geracao
                try:
                    r=self.pipeline.processar(quadro.imagem);self.autoridade.local_publicar(ident,quadro,r)
                except Exception as exc:self.autoridade.parar('falha_percepcao_local');self.autoridade.evento('falha_percepcao_local',motivo=str(exc))
            self.fim.wait(1/self.autoridade.op.inferencia_hz)

    def fechar(self):
        self.fim.set()
        for t in (self.thread,self.controle):
            if t.ident:t.join(2)
        self.motor.parar()


class AmostrasIntegradas(Amostras):
    def __init__(self,runtime,hz=10):
        self.runtime=runtime
        super().__init__(Telemetria(runtime.estado,runtime.motor,runtime.camera,runtime.controle,
                                   simulado=True,fonte_simulada=True),hz)

    def snapshot(self):
        if self.runtime.cenario.ler()['falha']:return None
        q=super().snapshot()
        if q is None:return None
        dados,t=q
        # CPU medida neste processo é do PC, jamais da Raspberry física.
        dados=dict(dados,sistema_natureza='observado_no_PC_da_simulacao')
        dados['telemetria']=dict(dados['telemetria'],distribuido=self.runtime.autoridade.snapshot())
        return dados,t
