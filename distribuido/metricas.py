"""Estatísticas da janela limitada; p99 apenas com pelo menos 100 amostras."""
import math
from monitoramento import resumo


def estatisticas(valores):
    v=[x for x in valores if type(x) in (int,float) and math.isfinite(x)]
    r=resumo(v)
    if r is None:return dict(n=0,media=None,mediana=None,minimo=None,maximo=None,desvio_padrao=None,p95=None,p99=None,jitter_medio=None)
    a=sorted(v);i=(len(a)-1)*.99;baixo=int(i)
    return dict(r,desvio_padrao=math.sqrt(sum((x-r['media'])**2 for x in v)/len(v)),
        p99=a[baixo]+(a[min(baixo+1,len(a)-1)]-a[baixo])*(i-baixo) if len(v)>=100 else None,
        jitter_medio=sum(abs(x-y) for x,y in zip(v,v[1:]))/(len(v)-1) if len(v)>1 else None)
