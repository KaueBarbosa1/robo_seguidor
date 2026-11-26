"""Inferência offline sobre JPEGs já armazenados. Não conecta à rede/hardware."""
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from armazenamento.consultas import Historico
from armazenamento.imagens import seguro,hash_arquivo
from distribuido.percepcao import Pipeline,decodificar_jpeg


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--historico',required=True,type=Path)
    p.add_argument('--sessao',required=True)
    p.add_argument('--algoritmo',choices=('opencv','cnn-fotos','cnn-rl'),default='opencv')
    p.add_argument('--manifesto',type=Path)
    p.add_argument('--saida',type=Path,required=True)
    a=p.parse_args();h=Historico(a.historico)
    pipeline=Pipeline(a.algoritmo,a.manifesto);a.saida.parent.mkdir(parents=True,exist_ok=True)
    n=erros=0;inicio=time.perf_counter()
    campos=['sessao','frame_id','sha256','simulado','algoritmo','versao_modelo','posicao','erro','linha_visivel','confianca','navegavel','inferencia_s','processamento_s','semantica','falha']
    with a.saida.open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=campos);w.writeheader()
        for i in h.iterar('imagens',sessao=a.sessao):
            base=dict(sessao=a.sessao,frame_id=i['frame_id'],sha256=i['sha256'],simulado=i['simulado'],algoritmo=a.algoritmo)
            try:
                caminho=seguro(h.raiz,i['caminho'])
                if not caminho.is_file() or caminho.stat().st_size>4*1024**2 or hash_arquivo(caminho)!=i['sha256']:raise ValueError('JPEG ausente ou hash incorreto')
                frame,_=decodificar_jpeg(caminho.read_bytes());r=pipeline.processar(frame)
                base.update({k:r.get(k) for k in campos if k in r})
            except (ValueError,OSError) as exc:base['falha']=str(exc);erros+=1
            w.writerow(base);n+=1
    meta=dict(sessao=a.sessao,algoritmo=a.algoritmo,imagens=n,falhas=erros,duracao_s=time.perf_counter()-inicio,
        criado_utc=datetime.now(timezone.utc).isoformat(),natureza='Inferência real em JPEGs históricos; não é ambiente RL responsivo nem ensaio físico',
        sem_atuacao=True,sem_treinamento=True)
    a.saida.with_suffix('.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(meta,ensure_ascii=False))


if __name__=='__main__':main()
