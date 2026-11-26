"""Executor/análise no PC, sem hardware. Reutiliza Central e SQLite existentes."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import config as cfg


def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='acao',required=True)
    rodar=sub.add_parser('executar');rodar.add_argument('config',type=Path);rodar.add_argument('--historico',type=Path,default=cfg.ARMAZ_DIR)
    listar=sub.add_parser('listar');listar.add_argument('--historico',type=Path,default=cfg.ARMAZ_DIR)
    rel=sub.add_parser('relatorio');rel.add_argument('id');rel.add_argument('--historico',type=Path,default=cfg.ARMAZ_DIR);rel.add_argument('--interpretacao',default='')
    vis=sub.add_parser('visao');vis.add_argument('--saida',type=Path,required=True)
    ana=sub.add_parser('analisar');ana.add_argument('csv',type=Path);ana.add_argument('--saida',type=Path,required=True)
    ana.add_argument('--tipo',choices=['serie','regressao','degrau','odometria'],required=True)
    ana.add_argument('--origem',choices=['real','simulada'],required=True);ana.add_argument('--nivel',type=int,choices=range(1,6),required=True)
    ana.add_argument('--referencia');ana.add_argument('--inicial',type=float);ana.add_argument('--alvo',type=float);ana.add_argument('--unidade',default='adimensional')
    a=p.parse_args()
    if a.acao=='analisar':
        from experimentos.graficos import analisar
        print(json.dumps(analisar(a.csv,a.saida,a.tipo,a.origem,a.nivel,a.referencia,a.inicial,a.alvo,a.unidade),ensure_ascii=False,indent=2));return
    if a.acao=='visao':
        from experimentos.visao import avaliar
        r=avaliar(a.saida);print(json.dumps(r,ensure_ascii=False,indent=2));return
    if not (a.historico/'banco/robo_seguidor.db').exists():
        candidatos=sorted(a.historico.glob('validacao_*/cenario_10hz/banco/robo_seguidor.db'))
        if candidatos:a.historico=candidatos[-1].parent.parent
    if a.acao=='executar':
        from central_monitoramento.central import Central
        c=Central(a.historico,etapa6=True)
        try:
            c.modo_alterar('simulado');time.sleep(.5);c.experimentos.iniciar(json.loads(a.config.read_text(encoding='utf-8-sig')))
            while c.experimentos.snapshot()['ativo']:
                print(json.dumps(c.experimentos.snapshot(),ensure_ascii=False),flush=True);time.sleep(1)
            r=c.experimentos.snapshot();print(json.dumps(r,ensure_ascii=False,indent=2))
            if r['estado']!='concluido':raise SystemExit(1)
        except KeyboardInterrupt:c.experimentos.parar()
        finally:c.fechar()
    elif a.acao=='listar':
        from experimentos.repositorio import listar
        print(json.dumps(listar(a.historico),ensure_ascii=False,indent=2))
    else:
        from experimentos.relatorios import gerar
        print(json.dumps(gerar(a.historico,a.id,a.interpretacao),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
