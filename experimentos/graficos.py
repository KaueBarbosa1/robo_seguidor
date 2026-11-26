"""Análise de CSV externo: origem e referência declaradas, sem controle físico."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
from experimentos.analise import resumo,regressao,resposta_degrau,odometria


def analisar(arquivo,saida,tipo,origem,nivel,referencia=None,inicial=None,alvo=None,unidade='adimensional'):
    if origem not in ('real','simulada') or nivel not in range(1,6):raise ValueError('Identifique origem e nível')
    arquivo=Path(arquivo)
    with arquivo.open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    if not rows:raise ValueError('CSV sem dados')
    def coluna(k):
        try:a=np.asarray([float(r[k]) for r in rows])
        except (ValueError,KeyError):raise ValueError('Coluna numérica ausente/inválida: '+k)
        if not np.isfinite(a).all():raise ValueError('Coluna não finita: '+k)
        return a
    if tipo in ('regressao','odometria') and not referencia:raise ValueError('Descreva a referência independente usada no CSV')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axs=plt.subplots(1,2,figsize=(10,4))
    if tipo=='regressao':
        y,p=coluna('real'),coluna('previsto');metricas=regressao(y.tolist(),p.tolist());erro=p-y
        axs[0].scatter(y,p,label=f'n={len(y)} pares');axs[0].plot([min(y),max(y)],[min(y),max(y)],'--',label='Identidade')
        axs[0].set(xlabel=f'Referência ({unidade})',ylabel=f'Previsão ({unidade})',title='Referência versus previsão')
        axs[1].scatter(p,erro,label='Resíduos');axs[1].axhline(0,color='gray');axs[1].set(xlabel=f'Previsão ({unidade})',ylabel=f'Erro ({unidade})',title='Resíduos')
    elif tipo=='degrau':
        t,y=coluna('tempo_s'),coluna('medido');metricas=resposta_degrau(t.tolist(),y.tolist(),inicial,alvo)
        axs[0].plot(t,y,label='Medido');axs[0].axhline(alvo,label='Referência',color='#d97706');axs[0].set(xlabel='Tempo (s)',ylabel=unidade,title='Resposta ao degrau')
        axs[1].plot(t,y-alvo,label='Erro');axs[1].set(xlabel='Tempo (s)',ylabel=unidade,title='Erro de referência')
    elif tipo=='odometria':
        e=np.column_stack([coluna(k) for k in ('x_m','y_m','theta_rad')]);r=np.column_stack([coluna(k) for k in ('ref_x_m','ref_y_m','ref_theta_rad')]);metricas=odometria(e.tolist(),r.tolist())
        axs[0].plot(e[:,0],e[:,1],label='Odometria');axs[0].plot(r[:,0],r[:,1],label='Referência independente');axs[0].set(xlabel='X (m)',ylabel='Y (m)',title='Trajetória 2D');axs[0].axis('equal')
        axs[1].plot(np.linalg.norm(e[:,:2]-r[:,:2],axis=1),label='Erro de posição');axs[1].set(xlabel='Par amostral (índice)',ylabel='Erro (m)',title='Erro ao longo do percurso')
    else:
        t,y=coluna('tempo_s'),coluna('valor');metricas=resumo(y.tolist())
        axs[0].plot(t,y,label=f'n={len(y)} amostras');axs[0].set(xlabel='Tempo (s)',ylabel=unidade,title='Série temporal')
        axs[1].hist(y,bins=min(30,len(y)),label='Distribuição');axs[1].set(xlabel=unidade,ylabel='Amostras (n)',title='Histograma')
    for ax in axs:ax.legend();ax.grid(alpha=.15)
    fig.suptitle(f'{tipo} · {origem} · nível {nivel} · {arquivo.name}');fig.tight_layout()
    saida=Path(saida);saida.mkdir(parents=True,exist_ok=False)
    for ext in ('png','svg'):fig.savefig(saida/('analise.'+ext),dpi=240)
    plt.close(fig)
    r=dict(tipo=tipo,origem=origem,nivel=nivel,unidade=unidade,referencia=referencia,arquivo=str(arquivo),
           sha256=hashlib.sha256(arquivo.read_bytes()).hexdigest(),metricas=metricas,
           limitacao='Referência/origem declaradas pelo operador; ferramenta não comprova calibração ou independência. Sem conclusão automática.')
    (saida/'analise.json').write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return r
