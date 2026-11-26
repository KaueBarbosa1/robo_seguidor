"""Inicia o gêmeo no PC: fonte simulada, ponte local e modelo original."""
import argparse
import os
import json
from pathlib import Path
import sys
import webbrowser

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import config as cfg
from armazenamento.configuracao import validar_pc
from gemeo_digital.integracao import Ponte
from gemeo_digital.servidor import Aplicacao


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--porta',type=int,default=8780);p.add_argument('--historico',type=Path,default=cfg.ARMAZ_DIR)
    p.add_argument('--servidor',help='WebSocket real já configurado; nenhuma conexão automática no modo simulado')
    p.add_argument('--gravar',action='store_true',help='anexa gravador existente e odometria estimada na mesma base')
    p.add_argument('--calibracao',type=Path,help='JSON de calibração física confirmada; parâmetros em metros')
    p.add_argument('--sem-abrir',action='store_true')
    p.add_argument('--central',action='store_true',help='abre a central integrada da etapa 5')
    p.add_argument('--etapa6',action='store_true',help='percepção/controle em simulação pela infraestrutura existente')
    p.add_argument('--perfil',choices=('simulacao-embarcada','simulacao-distribuida','monitoramento','distribuido-real'),default='simulacao-embarcada')
    p.add_argument('--inferencia-hz',type=float,default=5.)
    p.add_argument('--imagens-fps',type=float,default=5.)
    p.add_argument('--camera-fps',type=float,default=30.)
    p.add_argument('--telemetria-hz',type=float,default=10.)
    p.add_argument('--validacao-fisica')
    p.add_argument('--resultado-timeout',type=float,default=.3)
    p.add_argument('--comando-timeout',type=float,default=.3)
    p.add_argument('--heartbeat-operacao',type=float,default=.15)
    p.add_argument('--controle-max-pps',type=float,default=4.)
    a=p.parse_args();validar_pc()
    if not (a.historico/'banco/robo_seguidor.db').exists():
        candidatos=sorted(a.historico.glob('validacao_*/cenario_10hz/banco/robo_seguidor.db'))
        if candidatos:a.historico=candidatos[-1].parent.parent
    raiz=Path(__file__).resolve().parents[1]/'gemeo_digital'
    if not (raiz/'frontend/node_modules/three/build/three.module.js').exists():p.error('Execute npm install em gemeo_digital/frontend')
    if not (raiz/'modelos/carrinho_configurado.glb').exists():p.error('Coloque o GLB original em gemeo_digital/modelos/carrinho_configurado.glb')
    classe_ponte=Ponte;classe_app=Aplicacao
    if a.central:
        from central_monitoramento.central import Central
        from central_monitoramento.servidor import AplicacaoCentral
        classe_ponte=Central;classe_app=AplicacaoCentral
    extras={}
    if a.etapa6:
        if not a.central:p.error('--etapa6 exige --central')
        from distribuido.configuracao import opcoes_aprovadas,tokens_ambiente
        try:op_dist=opcoes_aprovadas(a.validacao_fisica,inferencia_hz=a.inferencia_hz,
            resultado_s=a.resultado_timeout,comando_s=a.comando_timeout,heartbeat_s=a.heartbeat_operacao,velocidade_max_pps=a.controle_max_pps)
        except (ValueError,OSError,KeyError) as exc:p.error(str(exc))
        if a.perfil=='distribuido-real' and not op_dist.distribuido_real:p.error('Modo real distribuído exige aprovação física explícita; bloqueado por padrão')
        extras=dict(etapa6=True,op_distribuida=op_dist,tokens_operacao=tokens_ambiente(),
                    telemetria_hz=a.telemetria_hz,imagens_fps=a.imagens_fps,camera_fps=a.camera_fps)
    ponte=classe_ponte(a.historico,a.servidor,os.environ.get(cfg.REDE_TOKEN_ENV,''),a.gravar,**extras)
    if a.calibracao:
        from gemeo_digital.cinematica import Calibracao
        try:
            cal=Calibracao(**json.loads(a.calibracao.read_text(encoding='utf-8')))
            if not cal.valida() or not cal.confirmada or cal.simulada:raise ValueError('Exige calibração física confirmada, não simulada')
            ponte.cal_real=cal
        except (ValueError,TypeError,OSError) as exc:p.error(str(exc))
    app=None
    try:
        app=classe_app(ponte,a.porta)
        ponte.modo_alterar('real' if a.etapa6 and a.perfil in ('monitoramento','distribuido-real') else 'simulado')
        if a.etapa6 and a.perfil in ('simulacao-distribuida','distribuido-real'):
            import time
            op=ponte.fluxo.operacao;limite=time.monotonic()+5
            while op and time.monotonic()<limite:
                r=op.snapshot()['remoto']
                if r.get('remoto_pronto') and r.get('parada')=='confirmada_pelos_dados':
                    op.comandar({'acao':'modo','modo':'distribuido'});break
                time.sleep(.05)
            else:raise ValueError('Canal operacional/percepção ainda não está pronto; sem habilitar movimento')
        if a.central and a.gravar:ponte.gravacao_comando({'acao':'iniciar'})
        url=f'http://127.0.0.1:{app.server_port}'
        titulo='Central de monitoramento' if a.central else 'Gêmeo digital'
        print(f'{titulo}: {url} | sem atuação física | histórico: {a.historico}',flush=True)
        if not a.sem_abrir:webbrowser.open(url)
        app.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:pass
    finally:
        if app:app.server_close()
        ponte.fechar()


if __name__=='__main__':main()
