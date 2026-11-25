"""Etapa 3 no PC: gravação, consultas, CSV, backup e replay; nenhum comando físico."""
import argparse
import json
import math
import os
import sqlite3
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import config as cfg
from armazenamento.configuracao import OpcoesArmazenamento,validar_pc
from armazenamento.banco import Exclusivo,conectar
from armazenamento.consultas import Historico,CATEGORIAS
from armazenamento.exportacao import exportar
from armazenamento.backup import criar,restaurar
from armazenamento.gestao import criar_experimento,anotar
from armazenamento.receptor import ReceptorPC
from armazenamento.reproducao import Reprodutor
from comunicacao.configuracao import Opcoes


def imprimir(dado):
    print(json.dumps(dado,ensure_ascii=False,indent=2,allow_nan=False,default=str),flush=True)


def filtros(args):
    d={k:getattr(args,k,None) for k in ('sessao','gravacao','experimento','inicio','fim','modo','dispositivo','lado')}
    if getattr(args,'dominio',None):
        d['simulado']=args.dominio=='simulado'
    return {k:v for k,v in d.items() if v is not None}


def adicionar_filtros(p):
    for nome in ('sessao','gravacao','experimento','inicio','fim','modo','dispositivo','lado'):
        p.add_argument('--'+nome)
    p.add_argument('--dominio',choices=('real','simulado'))


def gravar(args):
    if not math.isfinite(args.duracao) or args.duracao < 0 or (args.duracao and not args.automatico):
        raise ValueError('Duracao finita >=0; ensaio temporizado exige --automatico')
    op=Opcoes.central(os.environ.get(cfg.REDE_TOKEN_ENV,''))
    ar=OpcoesArmazenamento.central(raiz=args.raiz,imagens=args.imagens,
        imagens_eventos=args.imagens_eventos,imagens_fps=args.imagens_fps)
    receptor=ReceptorPC(args.servidor,op,ar)
    try:
        receptor.iniciar(args.automatico,nome=args.nome,experimento=args.experimento,modo=args.modo,
                         observacoes=args.observacoes,versao_software=args.revisao)
        print('PC: gravacao de imagens '+('habilitada' if args.imagens else 'continua desabilitada'),flush=True)
        if args.duracao:
            fim=time.monotonic()+args.duracao
            while time.monotonic()<fim:
                time.sleep(min(1.,max(0.,fim-time.monotonic())))
                imprimir(receptor.g.snapshot())
        else:
            print('Comandos: iniciar NOME | pausar | retomar | encerrar | status | sair',flush=True)
            while True:
                try:
                    comando=input('historico> ').strip()
                except EOFError:
                    break
                tipo,_,resto=comando.partition(' ')
                try:
                    if tipo=='sair':break
                    elif tipo=='iniciar':imprimir(receptor.g.nova_gravacao(resto or args.nome,modo=args.modo,experimento=args.experimento))
                    elif tipo=='pausar':imprimir(receptor.g.pausar())
                    elif tipo=='retomar':imprimir(receptor.g.retomar())
                    elif tipo=='encerrar':imprimir(receptor.g.encerrar())
                    elif tipo=='status':imprimir(receptor.g.snapshot())
                    elif tipo:print('Comando desconhecido')
                except (ValueError,RuntimeError) as exc:
                    print(str(exc),flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        receptor.fechar()
    imprimir(receptor.g.snapshot())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raiz',type=Path,default=cfg.ARMAZ_DIR)
    s=p.add_subparsers(dest='acao',required=True)
    s.add_parser('inicializar');s.add_parser('estado');s.add_parser('integridade')
    s.add_parser('recuperar')
    q=s.add_parser('consultar');q.add_argument('categoria',choices=sorted(CATEGORIAS));adicionar_filtros(q)
    q.add_argument('--limite',type=int,default=100);q.add_argument('--pagina',type=int,default=0)
    st=s.add_parser('estatisticas');st.add_argument('categoria');st.add_argument('coluna');adicionar_filtros(st)
    r=s.add_parser('resumo');adicionar_filtros(r)
    e=s.add_parser('exportar');e.add_argument('--categorias',default='consolidado,eventos,imagens,sessoes,gravacoes')
    e.add_argument('--destino',type=Path);adicionar_filtros(e)
    b=s.add_parser('backup');b.add_argument('--destino',type=Path);b.add_argument('--sem-imagens',action='store_true')
    rr=s.add_parser('restaurar');rr.add_argument('--backup',type=Path,required=True);rr.add_argument('--destino',type=Path,required=True)
    rr.add_argument('--confirmar',action='store_true')
    ex=s.add_parser('experimento');ex.add_argument('--nome',required=True);ex.add_argument('--objetivo')
    ex.add_argument('--modo');ex.add_argument('--algoritmo');ex.add_argument('--condicoes');ex.add_argument('--repeticao',type=int)
    ex.add_argument('--observacoes')
    an=s.add_parser('anotar');an.add_argument('--gravacao',required=True);an.add_argument('--nome');an.add_argument('--observacoes');an.add_argument('--experimento-id')
    rp=s.add_parser('reproduzir');rp.add_argument('--sessao',required=True);rp.add_argument('--velocidade',type=float,default=1.)
    rp.add_argument('--inicio');rp.add_argument('--limite',type=int,default=100)
    g=s.add_parser('gravar');g.add_argument('--servidor',required=True);g.add_argument('--automatico',action='store_true')
    g.add_argument('--nome',default='Gravacao');g.add_argument('--modo');g.add_argument('--experimento');g.add_argument('--observacoes')
    g.add_argument('--revisao');g.add_argument('--imagens',action='store_true');g.add_argument('--imagens-eventos',action='store_true')
    g.add_argument('--imagens-fps',type=float,default=cfg.ARMAZ_IMAGENS_FPS);g.add_argument('--duracao',type=float,default=0.)
    a=p.parse_args()
    try:
        validar_pc()
        h=Historico(a.raiz)
        if a.acao=='inicializar':
            with Exclusivo(a.raiz):
                c=conectar(a.raiz,True);c.close()
            imprimir(h.estado())
        elif a.acao=='recuperar':
            from armazenamento.gravador import Gravador
            from comunicacao.distribuidor import Distribuidor
            g=Gravador(Distribuidor(),OpcoesArmazenamento.central(raiz=a.raiz))
            g.iniciar();g.fechar();imprimir(h.consultar('gravacoes'))
        elif a.acao=='gravar':gravar(a)
        elif a.acao=='estado':imprimir(h.estado())
        elif a.acao=='integridade':imprimir(h.integridade())
        elif a.acao=='consultar':imprimir(h.consultar(a.categoria,a.limite,a.pagina,**filtros(a)))
        elif a.acao=='estatisticas':imprimir(h.estatistica(a.categoria,a.coluna,**filtros(a)))
        elif a.acao=='resumo':imprimir(h.resumo(**filtros(a)))
        elif a.acao=='exportar':imprimir(exportar(h,a.categorias.split(','),a.destino,**filtros(a)))
        elif a.acao=='backup':imprimir(criar(a.raiz,a.destino,not a.sem_imagens))
        elif a.acao=='restaurar':imprimir(restaurar(a.backup,a.destino,a.confirmar))
        elif a.acao=='experimento':imprimir(criar_experimento(a.raiz,**{k:getattr(a,k) for k in
            ('nome','objetivo','modo','algoritmo','condicoes','repeticao','observacoes')}))
        elif a.acao=='anotar':anotar(a.raiz,a.gravacao,a.nome,a.observacoes,a.experimento_id)
        elif a.acao=='reproduzir':
            r=Reprodutor(h,a.sessao,a.velocidade)
            if a.inicio:r.buscar(a.inicio)
            for i,item in enumerate(r.iniciar()):
                jpeg=item.pop('jpeg');item['jpeg_bytes']=len(jpeg) if jpeg else None;imprimir(item)
                if i+1>=a.limite:break
    except (ValueError,RuntimeError,OSError,sqlite3.Error) as exc:
        p.error(str(exc))


if __name__=='__main__':main()
