"""Estimativa diferencial: não é localização absoluta ou controle do carrinho."""
from dataclasses import dataclass,asdict
import math


@dataclass(frozen=True)
class Calibracao:
    ppr_esq: float | None = None
    ppr_dir: float | None = None
    diametro_esq_m: float | None = None
    diametro_dir_m: float | None = None
    bitola_m: float | None = None
    confirmada: bool = False
    simulada: bool = False
    relacao_disco_roda: float | None = None

    def valida(self):
        if self.relacao_disco_roda is not None and (type(self.relacao_disco_roda) not in (int,float) or not math.isfinite(self.relacao_disco_roda) or self.relacao_disco_roda<=0):return False
        return type(self.confirmada)is bool and type(self.simulada)is bool and (self.confirmada or self.simulada) and all(type(v) in (int,float) and math.isfinite(v) and v>0
            for v in (self.ppr_esq,self.ppr_dir,self.diametro_esq_m,self.diametro_dir_m,self.bitola_m))


class Odometria:
    def __init__(self,calibracao):
        self.cal=calibracao
        self.resetar()

    def resetar(self):
        self.x=self.y=self.theta=self.distancia=0.
        self.anterior=None
        self.trajeto=[]

    def invalidar(self):
        self.anterior=None

    def atualizar(self,ticks_e,ticks_d,tempo,sinais,valida=True):
        saida=dict(x_m=self.x,y_m=self.y,orientacao_rad=self.theta,distancia_m=self.distancia,
                   velocidade_linear_m_s=None,velocidade_angular_rad_s=None,
                   validade='sem_calibracao' if not self.cal.valida() else 'sem_delta',
                   natureza='simulada' if self.cal.simulada else 'estimada_por_pulsos_e_sentido_comandado',
                   calibracao=asdict(self.cal))
        if (not valida or not self.cal.valida() or any(not isinstance(v,(int,float)) or not math.isfinite(v)
            for v in (ticks_e,ticks_d,tempo)) or any(s not in (-1,0,1) for s in sinais)):
            self.invalidar();return saida
        atual=(ticks_e,ticks_d,tempo,tuple(sinais))
        ant=self.anterior;self.anterior=atual
        if ant is None:return saida
        dt=tempo-ant[2];de=ticks_e-ant[0];dd=ticks_d-ant[1]
        if dt<=0 or dt>.5 or min(de,dd)<0 or tuple(sinais)!=ant[3] or (de and not sinais[0]) or (dd and not sinais[1]):
            return saida
        le=de*math.pi*self.cal.diametro_esq_m/self.cal.ppr_esq*sinais[0]
        ld=dd*math.pi*self.cal.diametro_dir_m/self.cal.ppr_dir*sinais[1]
        ds=(le+ld)/2;da=(ld-le)/self.cal.bitola_m
        if abs(da)<1e-9:
            self.x+=ds*math.cos(self.theta);self.y+=ds*math.sin(self.theta)
        else:
            r=ds/da
            self.x+=r*(math.sin(self.theta+da)-math.sin(self.theta))
            self.y-=r*(math.cos(self.theta+da)-math.cos(self.theta))
        self.theta=(self.theta+da+math.pi)%(2*math.pi)-math.pi
        self.distancia+=abs(ds)
        self.trajeto.append([self.x,self.y]);self.trajeto=self.trajeto[-2000:]
        saida.update(x_m=self.x,y_m=self.y,orientacao_rad=self.theta,distancia_m=self.distancia,
            velocidade_linear_m_s=ds/dt,velocidade_angular_rad_s=da/dt,validade='estimativa')
        return saida
