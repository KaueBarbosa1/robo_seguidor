"""Ensaios Windows reais de software sobre imagens sintéticas, sem hardware.

Reutiliza a base existente e a central. Encerre outra instância antes de usar.
Não treina modelos e não afirma desempenho físico da Raspberry.
"""
import argparse
from dataclasses import replace
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
import threading
import time
from urllib.request import urlopen

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
import psutil
import config as cfg
from central_monitoramento.central import Central
from central_monitoramento.servidor import AplicacaoCentral
from distribuido.configuracao import OpcoesDistribuidas
from distribuido.percepcao import Pipeline,PercepcaoLocal,PercepcaoRemota,decodificar_jpeg
from distribuido.metricas import estatisticas


def esperar(fn,prazo=5):
    fim=time.monotonic()+prazo
    while time.monotonic()<fim:
        v=fn()
        if v:return v
        time.sleep(.025)
    raise RuntimeError('Pré-condição não observada no prazo')


def imagens_fixas():
    saida=[]
    for x in (140,220,330):
        imagem=np.full((640,480,3),220,np.uint8)
        cv2.line(imagem,(x,639),(x+12,0),(20,20,20),12)
        for y in range(50,640,80):imagem[y:y+18]=220
        ok,jpeg=cv2.imencode('.jpg',imagem)
        if not ok:raise ValueError('JPEG de teste não pôde ser codificado')
        saida.append((jpeg.tobytes(),decodificar_jpeg(jpeg.tobytes())[0]))
    return saida


def equivalencia(pasta,manifesto):
    amostras=imagens_fixas();resultados=[]
    for algoritmo in ('opencv','cnn-fotos'):
        try:
            a=PercepcaoLocal(Pipeline(algoritmo,manifesto if algoritmo=='cnn-fotos' else None))
            b=PercepcaoRemota(Pipeline(algoritmo,manifesto if algoritmo=='cnn-fotos' else None))
        except (ValueError,OSError) as exc:
            resultados.append(dict(algoritmo=algoritmo,disponivel=False,motivo=str(exc)));continue
        for i,(jpeg,imagem) in enumerate(amostras):
            (pasta/f'imagem_fixa_{i}.jpg').write_bytes(jpeg)
            p=a.processar(imagem);q=b.processar(imagem)
            chaves=('linha_visivel','posicao','erro','roi','entrada','direcao','confianca','semantica')
            diferencas={k:abs(p[k]-q[k]) if type(p[k])in (int,float) and type(q[k])in (int,float) else 0 if p[k]==q[k] else None for k in chaves}
            if any(d is None or d>1e-6 for d in diferencas.values()):raise ValueError('Falha de equivalência')
            resultados.append(dict(algoritmo=algoritmo,imagem=i,sha256=hashlib.sha256(jpeg).hexdigest(),disponivel=True,
                diferencas=diferencas,tolerancia=1e-6,local=p,remoto=q,
                natureza='Algoritmo real sobre imagem sintética fixa; não mede acurácia na pista'))
    return resultados,amostras


def ensaio(caso,historico,saida,duracao,porta,imagem,manifesto):
    opcoes=OpcoesDistribuidas(inferencia_hz=caso['inferencia_hz'])
    c=Central(historico,etapa6=True,op_distribuida=opcoes,telemetria_hz=caso['telemetria_hz'],
        imagens_fps=caso['imagens_fps'],camera_fps=caso['camera_fps'],arquivo_preferencias=saida/'preferencias_benchmark.json')
    app=None;t=None;extras=[];query_ms=[];cpu=[];rss=[]
    try:
        app=AplicacaoCentral(c,porta);t=threading.Thread(target=lambda:app.serve_forever(poll_interval=.05),daemon=True);t.start()
        c.modo_alterar('simulado');op=c.fluxo.operacao;rt=c.fluxo.integrado
        esperar(lambda:op.snapshot()['remoto'].get('remoto_pronto') and op.snapshot()['remoto'].get('parada')=='confirmada_pelos_dados')
        if caso.get('algoritmo')=='cnn-fotos':
            rt.camera.imagem_teste=imagem;op.configurar('cnn-fotos',manifesto)
            esperar(lambda:op.snapshot()['remoto'].get('algoritmo')=='cnn-fotos' and op.snapshot()['remoto'].get('remoto_pronto'))
            time.sleep(.55)
        op.comandar({'acao':'modo','modo':'distribuido'})
        op.atraso_s=caso.get('atraso_s',0.)
        for _ in range(caso.get('consumidores_lentos',0)):extras.append(c.bus.assinar({'imagens'},1))
        c.gravacao_comando({'acao':'iniciar','nome':'Etapa6 · '+caso['nome']})
        inicio=time.monotonic();base=op.contas['frames_processados'];processo=psutil.Process();processo.cpu_percent()
        while time.monotonic()-inicio<duracao:
            t0=time.perf_counter()
            with urlopen(f'http://127.0.0.1:{app.server_port}/api/estado',timeout=2) as resposta:estado=json.load(resposta)
            query_ms.append((time.perf_counter()-t0)*1000)
            cpu.append(processo.cpu_percent());rss.append(processo.memory_info().rss)
            if c.estado.sessao:
                c.consultas.janela(c.estado.sessao,datetime.now(timezone.utc).isoformat(),10,50)
            time.sleep(.1)
        dt=time.monotonic()-inicio;sid=c.estado.sessao
        c.gravacao_comando({'acao':'encerrar'});c.escritor_externo.sincronizar();opinfo=op.snapshot();a=rt.autoridade.snapshot()
        from armazenamento.exportacao import exportar
        pasta,contagens=exportar(c.historico,['percepcao_remota','operacao_rede_eventos'],sessao=sid)
        return dict(configuracao=caso,sessao=sid,duracao_s=dt,fps_inferencia_observado=(op.contas['frames_processados']-base)/dt,
            processamento_pc_s=opinfo['estatisticas_pc_s'],ciclo_pi_pc_pi_s=opinfo['estatisticas_ciclo_s'],
            cpu_processo_pct=estatisticas(cpu),rss_bytes=estatisticas(rss),consultas_http_ms=estatisticas(query_ms),
            servico=opinfo,autoridade=a,fanout_lento=[dict(e.contas) for e in extras],
            gravador=c.escritor_externo.snapshot(),diagnostico_render=app.diagnostico,
            exportacao=dict(pasta=str(pasta),contagens=contagens),
            natureza='Medições Windows sobre simulador; nenhuma Raspberry física; CPU do processo soma núcleos')
    finally:
        for e in extras:c.bus.remover(e)
        if app:app.shutdown();app.server_close()
        c.fechar()
        if t:t.join(2)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--historico',type=Path,default=cfg.ARMAZ_DIR)
    p.add_argument('--saida',type=Path,default=Path('dados_distribuido')/datetime.now(timezone.utc).strftime('validacao_%Y%m%dT%H%M%SZ'))
    p.add_argument('--duracao',type=float,default=6.)
    p.add_argument('--porta',type=int,default=8780)
    args=p.parse_args()
    if not 2<=args.duracao<=60:p.error('Duração por caso: 2 a 60 s')
    if not (args.historico/'banco/robo_seguidor.db').exists():
        candidatos=sorted(args.historico.glob('validacao_*/cenario_10hz/banco/robo_seguidor.db'))
        if candidatos:args.historico=candidatos[-1].parent.parent
    args.saida.mkdir(parents=True,exist_ok=False)
    manifesto=Path(__file__).resolve().parents[1]/'dataset_pista/resultados/treino_posicao_02/experimento.json'
    eq,imgs=equivalencia(args.saida,manifesto)
    casos=[dict(nome='opencv_5fps',algoritmo='opencv',telemetria_hz=10.,imagens_fps=5.,camera_fps=30.,inferencia_hz=5.),
        dict(nome='opencv_carga',algoritmo='opencv',telemetria_hz=30.,imagens_fps=15.,camera_fps=30.,inferencia_hz=10.,consumidores_lentos=2),
        dict(nome='cnn_propria_640x480',algoritmo='cnn-fotos',telemetria_hz=10.,imagens_fps=5.,camera_fps=15.,inferencia_hz=5.),
        dict(nome='sobrecarga_injetada',algoritmo='opencv',telemetria_hz=30.,imagens_fps=15.,camera_fps=30.,inferencia_hz=10.,atraso_s=.4)]
    resultados=[]
    for caso in casos:
        if caso['algoritmo']=='cnn-fotos' and not any(x.get('disponivel') and x['algoritmo']=='cnn-fotos' for x in eq):continue
        print('Ensaio:',caso['nome'],flush=True)
        r=ensaio(caso,args.historico,args.saida,args.duracao,args.porta,imgs[1][1],manifesto)
        resultados.append(r);(args.saida/(caso['nome']+'.json')).write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    rel=dict(criado_utc=datetime.now(timezone.utc).isoformat(),hardware=dict(sistema=platform.platform(),cpu=platform.processor(),nucleos=psutil.cpu_count(),ram_total_bytes=psutil.virtual_memory().total),
             equivalencia=eq,ensaios=resultados,restricoes=['Sem hardware/ensaio físico','Sem treinamento','Não demonstra superioridade de um modo na pista'])
    (args.saida/'relatorio.json').write_text(json.dumps(rel,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print('Relatório:',args.saida/'relatorio.json',flush=True)


if __name__=='__main__':main()
