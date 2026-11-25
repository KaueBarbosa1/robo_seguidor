import threading
import time
from types import SimpleNamespace
from comunicacao.simulacao import MotorSimulado,CameraSimulada
from comunicacao.amostras import Amostras
from monitoramento.telemetria import Telemetria


class Cenario:
    def __init__(self):
        self.lock=threading.Lock()
        self.dados=dict(esq=0.,dir=0.,servo=90.,distancia=100.,linha=True,camera=True,
                        falha=False,cpu=32.,temperatura=48.,latencia=0.,obstaculo_x=0.,obstaculo_z=-.7,
                        motores=True,geometria=False)
        self.pose=(0.,0.,0.)
    def atualizar(self,dados):
        import math
        limites=dict(esq=(-60,60),dir=(-60,60),servo=(45,135),distancia=(2,400),cpu=(0,100),
                     temperatura=(0,100),latencia=(0,1),obstaculo_x=(-3,3),obstaculo_z=(-3,3))
        with self.lock:
            for k,v in dados.items():
                if k in ('linha','camera','falha','motores','geometria') and type(v)is bool:self.dados[k]=v
                elif k in limites and type(v) in (float,int) and math.isfinite(v) and limites[k][0]<=v<=limites[k][1]:self.dados[k]=v
                else:raise ValueError('Parâmetro simulado inválido: '+k)
    def ler(self):
        with self.lock:return dict(self.dados)

    def distancia(self):
        import math
        with self.lock:d=dict(self.dados);x,y,theta=self.pose
        if not d['geometria']:return d['distancia']
        # Interseção de raio com círculo virtual (raio 6 cm), não mapa ou física do sonar.
        a=theta+math.radians(d['servo']-90)
        ox,oz=-y,-x
        dx,dz=-math.sin(a),-math.cos(a)
        vx,vz=d['obstaculo_x']-ox,d['obstaculo_z']-oz
        proj=vx*dx+vz*dz;perp=vx*vx+vz*vz-proj*proj
        return max(2.,(proj-math.sqrt(max(0,.06**2-perp)))*100) if proj>0 and perp<=.06**2 else 400.


class MotorCenario(MotorSimulado):
    def __init__(self,cenario):
        super().__init__();self.cenario=cenario;self.t=time.monotonic();self.ticks=[0.,0.]
    def sensores(self):
        d=self.cenario.ler();agora=time.monotonic();dt=agora-self.t;self.t=agora
        self.ticks=[t+(abs(d[k]) if d['motores'] else 0)*dt for t,k in zip(self.ticks,('esq','dir'))]
        from comunicacao.simulacao import SensoresSimulados
        import config as cfg
        distancia=self.cenario.distancia();bloqueio=distancia<cfg.OBSTACULO_DIST_CM
        return SensoresSimulados(round(distancia),int(self.ticks[0]),int(self.ticks[1]),agora,bloqueio,False,bloqueio)
    def estado_motores(self):
        d=self.cenario.ler()
        return SimpleNamespace(pwm_esq=round(d['esq']/60*255) if d['motores'] else 0,pwm_dir=round(d['dir']/60*255) if d['motores'] else 0,
            falha_encoder=False,pi_ativo=True,timestamp=time.monotonic())
    def status_servo(self):
        return SimpleNamespace(angulo_nominal=self.cenario.ler()['servo'],timestamp=time.monotonic())


class FonteCenario(CameraSimulada):
    def __init__(self,cenario):super().__init__();self.cenario=cenario
    def proximo_jpeg_detalhado(self,*a,**kw):
        return super().proximo_jpeg_detalhado(*a,**kw) if self.cenario.ler()['camera'] else None


class AmostrasCenario(Amostras):
    def __init__(self,cenario,camera):
        self.cenario=cenario
        super().__init__(Telemetria(camera.estado,MotorCenario(cenario),camera,simulado=True,fonte_simulada=True))
    def snapshot(self):
        import copy
        d=self.cenario.ler()
        if d['falha']:return None
        q=super().snapshot()
        if q is None:return None
        dados,t=q;dados=copy.deepcopy(dados)
        dados['telemetria']['visao']['linha_visivel'].update(valor=d['linha'],estado='atual')
        dados['telemetria']['visao']['camera_ok']=d['camera']
        dados['sistema']={'valores':dict(cpu_total_pct=d['cpu'],ram_pct=None,temperatura_c=d['temperatura'],frequencia_mhz=None)}
        dados['sistema_natureza']='simulado'
        return dados,t
