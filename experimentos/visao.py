"""Reavaliação offline da CNN própria e velocidade nos mesmos frames reais."""
import csv
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from experimentos.analise import regressao,resumo
from experimentos.configuracao import RAIZ,ambiente


def avaliar(saida,base=None,manifesto=None):
    from aprendizado.dataset_rotulado import carregar_fotos,preparar_foto
    from distribuido.percepcao import Pipeline,decodificar_jpeg
    base=Path(base or RAIZ/'dataset_pista');manifesto=Path(manifesto or base/'resultados/treino_posicao_02/experimento.json')
    meta=json.loads(manifesto.read_text(encoding='utf-8'));snapshot=RAIZ/meta['parametros']['revisoes']
    # Verifica os hashes originais antes de analisar qualquer rótulo.
    verificacao_hashes={}
    for p,chave in [(snapshot,'hash_revisoes'),(base/'metadados.csv','hash_metadados')]:
        bruto=p.read_bytes();h=hashlib.sha256(bruto).hexdigest();lf=hashlib.sha256(bruto.replace(b'\r\n',b'\n')).hexdigest()
        if meta[chave] not in (h,lf):raise ValueError('Snapshot ou metadados diferem do treino registrado')
        verificacao_hashes[chave]=dict(bruto=h,lf=lf,registrado=meta[chave],equivalencia='bytes' if h==meta[chave] else 'somente finais de linha CRLF→LF')
    _,_,incluidos,excluidos=carregar_fotos(base,snapshot)
    grupos={};videos={};hashes={}
    for item in incluidos:
        for indice,chave in [(videos,'video_origem'),(hashes,'sha256')]:
            valor=item[chave]
            if valor in indice and indice[valor]!=item['grupo']:raise ValueError('Vazamento entre grupos: '+chave)
            indice[valor]=item['grupo']
    cnn=Pipeline('cnn-fotos',manifesto);opencv=Pipeline();rows=[]
    # Aquecimento fora das estatísticas, mesma imagem; sem treinamento.
    frame,_=decodificar_jpeg((base/incluidos[0]['arquivo']).read_bytes());cnn.processar(frame);opencv.processar(frame)
    for item in incluidos:
        jpeg=(base/item['arquivo']).read_bytes();frame,dec=decodificar_jpeg(jpeg)
        cnn.resetar();opencv.resetar();r=cnn.processar(frame);o=opencv.processar(frame)
        rows.append(dict(imagem=item['imagem'],video=item['video_origem'],grupo=item['grupo'],sha256=item['sha256'],
            alvo=item['posicao'],previsto=r['posicao'],residuo=r['posicao']-item['posicao'],decodificacao_s=dec,
            preprocessamento_cnn_s=r['preprocessamento_s'],inferencia_cnn_s=r['inferencia_s'],total_cnn_s=r['processamento_s'],
            opencv_s=o['processamento_s'],opencv_linha=o['linha_visivel']))
    for grupo in ('treino','validacao','teste'):
        g=[r for r in rows if r['grupo']==grupo];grupos[grupo]=regressao([r['alvo'] for r in g],[r['previsto'] for r in g])
    resultado=dict(origem='frames_reais_previamente_coletados',nivel=1,categoria='benchmark_isolado_offline',
        ambiente=ambiente(),verificacao_hashes=verificacao_hashes,parametros=cnn.rede.n_parametros(),entrada=[1,40,80],hash_modelo=cnn.versao,
        arquitetura='Conv(1,8,5,2) → ReLU → Conv(8,16,3,2) → ReLU → Conv(16,16,3,2) → ReLU → 800 → 64 → 2; tanh posição',
        normalizacao='cinza/255; (x-média)/(desvio+0,08), clip [-4,4] por imagem; ROI 2:1 centrada em y=75%',
        metrica_por_grupo=grupos,divisao_sem_sobreposicao_de_video_e_hash=True,excluidos=len(excluidos),
        velocidade={k:resumo([r[k] for r in rows]) for k in ('decodificacao_s','preprocessamento_cnn_s','inferencia_cnn_s','total_cnn_s','opencv_s')},
        opencv_fracao_frames_com_deteccao=sum(r['opencv_linha'] for r in rows)/len(rows),
        limitacoes=['Teste de apenas dois vídeos do mesmo ambiente, já explorados anteriormente; não é conjunto final intocado.',
            'Uma passagem por frame no PC: não representa inferência da Raspberry nem independência estatística dos frames.',
            'OpenCV usa outra altura/ROI; sua posição não é verdade nem comparável ao alvo CNN y075. Fração de detecção não é acurácia.',
            'Segmentação e detecção OpenCV permanecem agregadas; tempos individuais indisponíveis.',
            'Não houve treino, ajuste de pesos ou seleção de checkpoint nesta avaliação.',
            'Curvas, sombras e iluminação não têm estratos independentes anotados; robustez estratificada pendente.'])
    saida=Path(saida);saida.mkdir(parents=True,exist_ok=False)
    with (saida/'predicoes.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (saida/'avaliacao.json').write_text(json.dumps(resultado,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    graficos(saida,rows,manifesto.parent)
    return resultado


def graficos(saida,rows,treino):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axs=plt.subplots(1,3,figsize=(13,4));cores={'treino':'#0e7490','validacao':'#d97706','teste':'#7c3aed'}
    for grupo,cor in cores.items():
        g=[r for r in rows if r['grupo']==grupo];y=[r['alvo'] for r in g];p=[r['previsto'] for r in g];e=[r['residuo'] for r in g]
        axs[0].scatter(y,p,label=f'{grupo} n={len(g)}',c=cor,alpha=.8);axs[1].hist(e,bins=10,label=grupo,color=cor,alpha=.45);axs[2].scatter(p,e,label=grupo,c=cor)
    axs[0].plot([-1,1],[-1,1],'--',color='gray');axs[0].set(xlabel='Posição humana (normalizada)',ylabel='Previsão CNN (normalizada)',title='Real versus previsto')
    axs[1].set(xlabel='Previsão − alvo (normalizado)',ylabel='Frames (n)',title='Distribuição dos resíduos')
    axs[2].axhline(0,color='gray');axs[2].set(xlabel='Previsão (normalizada)',ylabel='Resíduo (normalizado)',title='Resíduos')
    for ax in axs:ax.legend();ax.grid(alpha=.15)
    fig.suptitle('CNN própria · frames reais de vídeos · avaliação offline no PC');fig.tight_layout()
    for ext in ('png','svg'):fig.savefig(saida/('regressao_cnn.'+ext),dpi=240)
    plt.close(fig)
    hist=treino/'historico.csv'
    if hist.exists():
        with hist.open(encoding='utf-8-sig') as f:linhas=list(csv.DictReader(f,delimiter=';'))
        # O separador é descoberto somente no arquivo existente.
        if linhas and len(linhas[0])==1:
            with hist.open(encoding='utf-8-sig') as f:linhas=list(csv.DictReader(f))
        fig,ax=plt.subplots(figsize=(8,4))
        for coluna in ('mse_treino','mse_validacao','perda_lote'):
            if linhas and coluna in linhas[0]:ax.plot([float(r['passo']) for r in linhas],[float(r[coluna]) for r in linhas],label=coluna)
        if ax.lines:
            ax.set(xlabel='Passo de treinamento registrado',ylabel='Perda / MSE (adimensional)',title='Histórico original existente; nenhum novo treino');ax.legend();fig.tight_layout()
            for ext in ('png','svg'):fig.savefig(saida/('historico_original.'+ext),dpi=240)
        plt.close(fig)
