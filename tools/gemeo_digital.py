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
    ponte=classe_ponte(a.historico,a.servidor,os.environ.get(cfg.REDE_TOKEN_ENV,''),a.gravar)
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
        ponte.modo_alterar('simulado')
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
