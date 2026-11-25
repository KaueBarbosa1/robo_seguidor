import math
import time
import json
from gemeo_digital.cinematica import Calibracao
from comunicacao.protocolo import codificar,decodificar
from gemeo_digital.cinematica import Odometria


def valor(c):
    return c.get('valor') if isinstance(c,dict) else c


def atual(c):
    return isinstance(c,dict) and c.get('estado')=='atual' and c.get('valor') is not None


class EstadoVisual:
    def __init__(self,calibracao):
        self.cal=calibracao;self.odom=Odometria(calibracao)
        self.sessao=None;self.seq=-1;self.msg=None;self.recebida=0.
        self.angulos=[0.,0.];self.base=None;self.imagem=None;self.eventos=[]

    def invalidar(self):
        self.odom.invalidar();self.base=None

    def restaurar_pose(self,p):
        """Usa a estimativa persistida, incluindo sua calibração e resets de referência."""
        try:
            cal=Calibracao(**json.loads(p['calibracao_json']))
            if not cal.valida() or p.get('validade')!='estimativa':return False
            if any(type(p.get(k)) not in (float,int) or not math.isfinite(p[k]) for k in ('x_m','y_m','orientacao_rad','distancia_m')):return False
        except (ValueError,TypeError,KeyError):return False
        if p['distancia_m']<self.odom.distancia-1e-8:self.odom.trajeto=[]
        self.cal=self.odom.cal=cal
        self.odom.x,self.odom.y,self.odom.theta,self.odom.distancia=(p[k] for k in ('x_m','y_m','orientacao_rad','distancia_m'))
        self.pose={k:v for k,v in p.items() if k!='calibracao_json'};self.pose['calibracao']=cal.__dict__
        ponto=[p['x_m'],p['y_m']]
        if not self.odom.trajeto or self.odom.trajeto[-1]!=ponto:self.odom.trajeto=(self.odom.trajeto+[ponto])[-2000:]
        return True

    def aceitar(self,msg,recepcao=None):
        try:
            decodificar(codificar(msg))
            if msg.get('tipo')!='telemetria' or not isinstance(msg['dados'].get('telemetria'),dict):return False
            motores=msg['dados']['telemetria'].get('motores',{})
            for k in ('ticks_esq','ticks_dir','pps_esq','pps_dir','pwm_esq','pwm_dir'):
                v=valor(motores.get(k))
                if v is not None and (type(v) not in (int,float) or not math.isfinite(v)):return False
            sensores=msg['dados']['telemetria'].get('sensores',{})
            for k in ('distancia_cm','angulo_servo_graus'):
                v=valor(sensores.get(k))
                if v is not None and (type(v) not in (int,float) or not math.isfinite(v)):return False
            idade=msg.get('idade_limite_recepcao_s',0)
            if type(idade) not in (float,int) or not math.isfinite(idade) or idade<0:return False
            if idade>msg['validade_s']:self.invalidar();return False
        except (ValueError,TypeError,AttributeError,KeyError):return False
        if self.sessao!=msg['sessao']:
            self.__init__(self.cal);self.sessao=msg['sessao']
        if type(msg.get('sequencia')) is not int or msg['sequencia']<=self.seq:return False
        self.seq=msg['sequencia'];self.msg=msg;self.recebida=recepcao if recepcao is not None else time.monotonic()
        m=msg['dados']['telemetria'].get('motores',{})
        sinais=[]
        for lado in ('esq','dir'):
            p=valor(m.get('pwm_'+lado))
            sinais.append(0 if p is None or p==0 else 1 if p>0 else -1)
        ticks=[valor(m.get('ticks_'+lado)) for lado in ('esq','dir')]
        valida=all(atual(m.get('ticks_'+lado)) and atual(m.get('pwm_'+lado)) for lado in ('esq','dir'))
        t=msg.get('monotonic_s')
        anterior=self.base;self.base=(ticks,t,sinais) if valida else None
        if (valida and anterior and self.cal.valida() and sinais==anterior[2] and
                0<t-anterior[1]<=.5 and all(x>=y for x,y in zip(ticks,anterior[0]))):
            for i,ppr in enumerate((self.cal.ppr_esq,self.cal.ppr_dir)):
                if sinais[i]:self.angulos[i]+=(ticks[i]-anterior[0][i])*2*math.pi/ppr*sinais[i]
        self.pose=self.odom.atualizar(*ticks,t,sinais,valida)
        return True

    def snapshot(self,idade=None):
        if self.msg is None:return dict(disponivel=False,idade_s=None,calibracao=self.cal.__dict__)
        idade=(max(0,time.monotonic()-self.recebida)+self.msg.get('idade_limite_recepcao_s',0)) if idade is None else idade
        valido=0<=idade<=self.msg.get('validade_s',.5)
        if not valido:self.invalidar()
        m=self.msg['dados']['telemetria'].get('motores',{})
        omega=[]
        for lado,ppr in [('esq',self.cal.ppr_esq),('dir',self.cal.ppr_dir)]:
            pps=valor(m.get('pps_'+lado));pwm=valor(m.get('pwm_'+lado))
            omega.append(pps*2*math.pi/ppr*(1 if pwm>0 else -1 if pwm<0 else 0)
                if valido and self.cal.valida() and atual(m.get('pps_'+lado)) and pwm is not None else 0.)
        return dict(disponivel=valido,idade_s=idade,envelope=self.msg,angulos_rad=self.angulos[:],
                    omega_rad_s=omega,pose=getattr(self,'pose',None),trajeto=self.odom.trajeto[:],
                    calibracao=self.cal.__dict__)
