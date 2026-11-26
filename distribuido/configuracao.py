from dataclasses import dataclass
import math

CONTRATO = 'robo_distribuido_v1'


@dataclass(frozen=True)
class OpcoesDistribuidas:
    resultado_s: float = .3
    comando_s: float = .3
    autorizacao_s: float = .6
    heartbeat_s: float = .15
    inferencia_hz: float = 5.
    velocidade_max_pps: float = 4.
    frames: int = 64
    remoto_real: bool = False
    distribuido_real: bool = False

    def __post_init__(self):
        for k in ('resultado_s','comando_s','autorizacao_s','heartbeat_s','inferencia_hz','velocidade_max_pps'):
            v=getattr(self,k)
            if type(v) not in (int,float) or not math.isfinite(v) or v<=0:raise ValueError('Configuração inválida: '+k)
        if type(self.frames)is not int:raise ValueError('Limite de frames deve ser inteiro')
        if not (.05<=self.resultado_s<=.3 and .05<=self.comando_s<=.5 and
                self.comando_s<=self.autorizacao_s<=2 and .05<=self.heartbeat_s<self.comando_s and
                .2<=self.inferencia_hz<=30 and self.velocidade_max_pps<=4 and 2<=self.frames<=256):
            raise ValueError('Configuração fora dos limites conservadores da etapa 6')
        if type(self.remoto_real)is not bool or type(self.distribuido_real)is not bool:raise ValueError('Flags devem ser booleanas')


def tokens_ambiente():
    import os
    return {p:os.environ['ROBO_TOKEN_'+p.upper()] for p in ('percepcao','controle','administrar') if os.environ.get('ROBO_TOKEN_'+p.upper())}


def opcoes_aprovadas(caminho=None,**opcoes):
    """Registro manual não é certificação: nunca é criado/aprovado pelo programa."""
    if caminho:
        import json
        from pathlib import Path
        from datetime import datetime
        m=json.loads(Path(caminho).read_text(encoding='utf-8'))
        if (m.get('etapa')!=6 or m.get('estado')!='aprovado_pelo_operador' or
            not m.get('responsavel') or not isinstance(m.get('evidencias'),list) or not m['evidencias']):
            raise ValueError('Registro de validação física incompleto')
        datetime.fromisoformat(m['data'])
        for k in ('remoto_real','distribuido_real'):
            if type(m.get(k))is not bool:raise ValueError('Aprovação física deve ser explícita por função')
            opcoes[k]=m[k]
    return OpcoesDistribuidas(**opcoes)
