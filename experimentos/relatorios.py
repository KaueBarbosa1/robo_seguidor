"""Artefatos científicos a partir de medições; backend Agg, sem valores fictícios."""
import csv
import html
import json
from pathlib import Path


def figuras(pasta,execucao):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    pasta=Path(pasta);arquivo=pasta/'amostras.csv'
    if not arquivo.exists():return []
    with arquivo.open(encoding='utf-8') as f:rows=list(csv.DictReader(f))[-25000:]
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':130})
    nome=f'{execucao["configuracao"]} · repetição {execucao["repeticao"]} · nível {execucao["nivel"]} · {execucao["origem"]}'
    graficos=[]
    def salvar(fig,n):
        fig.tight_layout()
        for ext in ('png','svg'):fig.savefig(pasta/(n+'.'+ext),dpi=240,bbox_inches='tight')
        plt.close(fig);graficos.extend([n+'.png',n+'.svg'])
    for campo,unidade,titulo,fator in [('inferencia_s','ms','Inferência',1000),('ciclo_s','ms','Ciclo Pi virtual → PC → Pi virtual',1000),('cpu_pc_pct','% do processo','CPU do processo no PC',1),('rss_bytes','MiB','Memória do processo no PC',1/1024**2)]:
        pares=[(float(r['t_s']),float(r[campo])*fator) for r in rows if r.get(campo)]
        if not pares:continue
        t,y=zip(*pares);fig,axs=plt.subplots(1,2,figsize=(10,3.5))
        axs[0].plot(t,y,'.-',color='#0e7490',label=f'n={len(y)} amostras internas');axs[0].set(xlabel='Tempo de coleta (s)',ylabel=unidade,title=titulo);axs[0].legend()
        axs[1].hist(y,bins=min(20,max(1,len(y)//2)),color='#0e7490',label='Distribuição observada');axs[1].set(xlabel=unidade,ylabel='Amostras (n)',title='Distribuição');axs[1].legend()
        fig.suptitle(nome);salvar(fig,campo)
    return graficos


def gerar(raiz,ident,interpretacao=''):
    from experimentos.repositorio import obter
    from armazenamento.imagens import seguro
    e=obter(raiz,ident);pasta=seguro(raiz,e['artefato_relativo']);pasta.mkdir(parents=True,exist_ok=True)
    if not isinstance(interpretacao,str) or len(interpretacao)>10000:raise ValueError('Interpretação extensa demais')
    imgs=figuras(pasta,e);r=e['resultado'];metricas=r.get('metricas',{})
    with (pasta/'metricas.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(['metrica','n_amostras','media','mediana','desvio_padrao_amostral','p95','p99','origem','nivel','repeticao'])
        for k,s in metricas.items():w.writerow([k,*[s.get(x) for x in ('n','media','mediana','desvio_padrao','p95','p99')],e['origem'],e['nivel'],e['repeticao']])
    secoes=[('Identificação',dict(id=ident,experimento=e['experimento_id'],sessao=e['sessao_id'],estado=e['estado'])),
      ('Objetivo',e['configuracoes'].get('objetivo')),('Hipótese',e['configuracoes'].get('hipotese')),
      ('Metodologia','Percepção em JPEG sintético fixo, sem movimento; aquecimento separado. Uma execução é uma repetição, não cada mensagem.'),
      ('Configuração efetiva',e['configuracoes']),('Ambiente e hardware',e['ambiente']),
      ('Repetição',e['repeticao']),('Métricas medidas',metricas),('Resultados',r),
      ('Eventos relevantes',r.get('eventos',[])),('Limitações',r.get('limitacoes',['Execução sem resultados disponíveis'])),
      ('Validações pendentes','Bancada, pista, calibração e comparação na Raspberry; nenhum resultado físico foi produzido.'),
      ('Interpretação manual',interpretacao or 'Não preenchida pelo pesquisador. Nenhuma hipótese foi confirmada automaticamente.')]
    md=f'# Relatório experimental — {e["configuracao"]}\n\nOrigem: **{e["origem"]}**, nível **{e["nivel"]}**, categoria **{e["categoria"]}**.\n'
    corpo=f'<h1>Relatório experimental — {html.escape(e["configuracao"])}</h1><p>Origem: {html.escape(e["origem"])} · nível {e["nivel"]}</p>'
    for titulo,valor in secoes:
        texto=valor if isinstance(valor,str) else json.dumps(valor,ensure_ascii=False,indent=2,allow_nan=False)
        md+=f'\n## {titulo}\n\n'+(texto if isinstance(valor,str) else '```json\n'+texto+'\n```')+'\n'
        corpo+=f'<h2>{titulo}</h2><pre>{html.escape(texto)}</pre>'
    md+='\n## Gráficos\n\n'
    for img in imgs:
        if img.endswith('.png'):md+=f'![Medição {img}]({img})\n\n';corpo+=f'<img alt="Medição experimental" src="{img}">'
    (pasta/'relatorio.md').write_text(md,encoding='utf-8')
    (pasta/'relatorio.html').write_text('<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Relatório experimental</title><style>body{max-width:1100px;margin:40px auto;font:16px system-ui;color:#183444}pre{white-space:pre-wrap;background:#edf3f5;padding:16px;overflow-wrap:anywhere}img{max-width:100%}@media print{body{margin:0}h2{break-after:avoid}}</style>'+corpo+'</html>',encoding='utf-8')
    (pasta/'relatorio.json').write_text(json.dumps(dict(execucao=e,interpretacao_manual=interpretacao,graficos=imgs),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    import zipfile
    with zipfile.ZipFile(pasta/'relatorio.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in pasta.iterdir():
            if p.suffix in ('.md','.html','.csv','.json','.png','.svg'):z.write(p,p.name)
    return dict(execucao=ident,arquivos=[n for n in ['relatorio.md','relatorio.html','relatorio.json','metricas.csv','amostras.csv','relatorio.zip',*imgs] if (pasta/n).is_file()])
