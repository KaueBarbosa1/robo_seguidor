"""Métricas com dados finitos, unidades explícitas e repetições independentes."""
import math
import numpy as np


def finitos(valores):
    return np.array([v for v in valores if type(v) in (int, float) and math.isfinite(v)], dtype=float)


def resumo(valores):
    x = finitos(valores)
    vazio = dict(n=0, media=None, mediana=None, variancia=None, desvio_padrao=None,
                 minimo=None, maximo=None, q1=None, q3=None, iqr=None, p95=None, p99=None, cv=None)
    if not len(x):return vazio
    q1, q3 = np.percentile(x, [25, 75]);media = float(x.mean())
    dp = float(x.std(ddof=1)) if len(x)>1 else None
    return dict(n=len(x), media=media, mediana=float(np.median(x)),
                variancia=float(x.var(ddof=1)) if len(x)>1 else None, desvio_padrao=dp,
                minimo=float(x.min()), maximo=float(x.max()), q1=float(q1), q3=float(q3),
                iqr=float(q3-q1), p95=float(np.percentile(x,95)),
                p99=float(np.percentile(x,99)) if len(x)>=100 else None,
                cv=dp/abs(media) if dp is not None and abs(media)>1e-12 else None)


def regressao(reais, previstos):
    if len(reais)!=len(previstos):raise ValueError('Pares com tamanhos diferentes')
    pares=[(a,b) for a,b in zip(reais,previstos) if len(finitos([a,b]))==2]
    if not pares:return dict(n=0,mae=None,mse=None,rmse=None,r2=None,erro_absoluto_max=None,residuos=[])
    y,p=np.array(pares).T;r=p-y;mse=float(np.mean(r*r));sst=float(np.sum((y-y.mean())**2))
    return dict(n=len(y),mae=float(np.abs(r).mean()),mse=mse,rmse=math.sqrt(mse),
                r2=1-float(np.sum(r*r))/sst if len(y)>1 and sst>1e-12 else None,
                erro_absoluto_max=float(np.abs(r).max()),residuos=r.tolist())


def diferenca(referencia, avaliado):
    if len(finitos([referencia,avaliado]))!=2:return dict(absoluta=None,reducao_pct=None,speedup=None)
    return dict(absoluta=avaliado-referencia,
                reducao_pct=(referencia-avaliado)/referencia*100 if referencia else None,
                speedup=referencia/avaliado if avaliado>0 and referencia>=0 else None)


def pareado(a,b,semente=7):
    """Bootstrap de diferenças entre execuções pareadas; sem p-valor automático."""
    if len(a)!=len(b) or len(a)<5:raise ValueError('São necessárias ao menos 5 repetições pareadas')
    if len(finitos(a))!=len(a) or len(finitos(b))!=len(b):raise ValueError('Pares devem ser finitos')
    d=np.asarray(b)-np.asarray(a);rng=np.random.default_rng(semente)
    medias=np.mean(rng.choice(d,(5000,len(d)),replace=True),axis=1)
    dp=float(np.std(d,ddof=1))
    return dict(n_pares=len(d),diferenca_media=float(d.mean()),
                ic95_bootstrap=np.percentile(medias,[2.5,97.5]).tolist(),
                efeito_dz=float(d.mean()/dp) if dp>1e-12 else None,semente=semente,
                limite='IC exploratório: pressupõe pares independentes e representativos; não prova equivalência.')


def resposta_degrau(tempos, valores, inicial, alvo, instante_degrau=0., faixa=.02):
    """Subida 10–90%; acomodação ±2% da amplitude até o fim observado."""
    if len(tempos)!=len(valores) or len(tempos)<2:raise ValueError('Série insuficiente')
    if len(finitos([*tempos,*valores,inicial,alvo,instante_degrau,faixa]))!=2*len(tempos)+4:raise ValueError('Série não finita')
    t=np.asarray(tempos);y=np.asarray(valores)
    if np.any(np.diff(t)<=0) or not 0<faixa<1 or inicial==alvo:raise ValueError('Degrau ou tempo inválido')
    mask=t>=instante_degrau;t=t[mask]-instante_degrau;y=y[mask]
    if len(t)<2:raise ValueError('Faltam amostras após o degrau')
    amplitude=alvo-inicial;normal=(y-inicial)/amplitude
    def cruzou(lim):
        ids=np.flatnonzero(normal>=lim);return float(t[ids[0]]) if len(ids) else None
    t10,t90=cruzou(.1),cruzou(.9);fora=np.flatnonzero(np.abs(y-alvo)>faixa*abs(amplitude))
    inicio=int(fora[-1])+1 if len(fora) else 0
    # Não declarar acomodação com uma única amostra terminal.
    acomodacao=float(t[inicio]) if inicio<len(t)-1 else None
    erro=y-alvo;cauda=erro[max(0,int(.9*len(erro))):]
    return dict(subida_10_90_s=t90-t10 if t10 is not None and t90 is not None else None,
                acomodacao_s=acomodacao,sobressinal_pct=max(0.,float(normal.max()-1))*100,
                erro_regime=float(cauda.mean()),mae=float(np.abs(erro).mean()),rmse=float(np.sqrt(np.mean(erro**2))),
                criterio=f'±{faixa*100:g}% da amplitude até o fim observado; resolução dada pela amostragem',
                janela_observada_s=float(t[-1]),estabilidade_fisica='não inferida')


def odometria(estimado, referencia):
    """Pares no mesmo referencial calibrado: x_m, y_m e orientacao_rad."""
    if len(estimado)!=len(referencia) or not estimado:raise ValueError('Referência externa pareada necessária')
    e=np.asarray(estimado,dtype=float);r=np.asarray(referencia,dtype=float)
    if e.shape!=r.shape or e.ndim!=2 or e.shape[1]!=3 or not np.isfinite(e).all() or not np.isfinite(r).all():raise ValueError('Esperados pares x,y,theta finitos')
    dist=np.linalg.norm(e[:,:2]-r[:,:2],axis=1);angulo=(e[:,2]-r[:,2]+np.pi)%(2*np.pi)-np.pi
    percurso=float(np.linalg.norm(np.diff(r[:,:2],axis=0),axis=1).sum())
    return dict(n=len(e),erro_posicao_m=resumo(dist.tolist()),erro_final_m=float(dist[-1]),
                erro_orientacao_rad=resumo(angulo.tolist()),percurso_referencia_m=percurso,
                erro_final_pct_percurso=100*float(dist[-1])/percurso if percurso>0 else None)


def criterios(metricas, limites):
    saida={}
    for k,regra in limites.items():
        v=metricas.get(k);lim=regra.get('maximo');minimo=regra.get('minimo')
        if len(finitos([v]))!=1 or (lim is None and minimo is None):estado='não avaliado'
        else:estado='aprovado' if (lim is None or v<=lim) and (minimo is None or v>=minimo) else 'reprovado'
        saida[k]=dict(valor=v,regra=regra,resultado=estado)
    return saida
