"""Somente leitura de evidências locais já existentes. Nunca executa treino."""
from pathlib import Path
from collections import Counter
import csv,json,math

def listar():
    raiz=Path(__file__).resolve().parents[1]/'Relatorio/evidencias'
    saida=[]
    for p in sorted(raiz.glob('treino_posicao_*/experimento.json'))[:20]:
        if p.stat().st_size>2*1024**2:continue
        e=json.loads(p.read_text(encoding='utf-8'));curva=[];dataset={}
        c=p.parent/'historico.csv';d=p.parent/'dataset.json'
        if c.is_file():
            with c.open(encoding='utf-8-sig',newline='') as f:
                for i,r in enumerate(csv.DictReader(f)):
                    if i>=5000:break
                    row={}
                    for k in ['passo','perda_lote','mse_treino','mse_validacao','mae_treino','mae_validacao']:
                        try:v=float(r[k]);row[k]=v if math.isfinite(v) else None
                        except (ValueError,KeyError,TypeError):row[k]=None
                    curva.append(row)
        if d.is_file() and d.stat().st_size<=5*1024**2:
            ds=json.loads(d.read_text(encoding='utf-8'));dataset=dict(grupos=dict(Counter(r.get('grupo','não informado') for r in ds.get('incluidos',[]))),revisoes_unicas=ds.get('revisoes_unicas'),arquivo=d.relative_to(raiz.parent.parent).as_posix())
        saida.append(dict(id=p.parent.name,origem=p.relative_to(raiz.parent.parent).as_posix(),tarefa=e.get('tarefa'),
            entrada=e.get('entrada'),preprocessamento=e.get('preprocessamento'),hash_pesos=e.get('hash_pesos'),
            criado_utc=e.get('criado_utc'),melhor_passo=e.get('melhor_passo'),criterio=e.get('criterio_checkpoint'),
            uso_no_robo_aprovado=e.get('uso_no_robo_aprovado'),
            parametros={k:v for k,v in e.get('parametros',{}).items() if k in ('passos','lote','lr','avaliar_cada','semente')},
            metricas={k:v.get('cnn') for k,v in e.get('metricas',{}).items()},dataset=dataset,curva=curva))
    return saida
