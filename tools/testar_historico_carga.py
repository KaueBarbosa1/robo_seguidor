"""Ensaio local das Etapas 2+3. Todos os cenários operacionais são SIMULADOS."""
import argparse
from dataclasses import replace
from datetime import datetime,timezone
import json
import math
from pathlib import Path
import secrets
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import config as cfg
from comunicacao.amostras import Amostras
from comunicacao.configuracao import Opcoes,url_local
from comunicacao.servidor import Servidor
from comunicacao.simulacao import CameraSimulada,telemetria_simulada
from armazenamento.configuracao import OpcoesArmazenamento
from armazenamento.receptor import ReceptorPC
from armazenamento.banco import conectar,tamanho_banco
from armazenamento.consultas import Historico
from armazenamento.exportacao import exportar
from armazenamento.backup import criar
from monitoramento import resumo


class Cenarios(Amostras):
    """Sobrescreve somente dados sintéticos; nunca apresenta CPU fictícia como medida."""
    def __init__(self,*args,**kw):
        super().__init__(*args,**kw)
        self.inicio=time.monotonic()

    def snapshot(self):
        resultado=super().snapshot()
        if resultado is None:return None
        original,instante=resultado
        d=json.loads(json.dumps(original))
        t=time.monotonic()-self.inicio
        d['sistema']={'valores':dict(cpu_total_pct=40+20*math.sin(t),ram_pct=35+5*math.sin(t),
            temperatura_c=55+5*math.sin(t),processo_rss_bytes=None,frequencia_mhz=None)}
        d['sistema_natureza']='simulado'
        d['sistema_monotonic_s']=float(int(time.monotonic()))
        d['telemetria']['operacao']['modo']='SEGUINDO' if t>=1 else 'PARADO'
        for k in ('obstaculo_confirmado','avanco_bloqueado'):
            d['telemetria']['sensores'][k].update(valor=1.5<t<2.5,estado='atual')
        d['telemetria']['visao']['linha_visivel'].update(valor=not 2<t<3,estado='atual')
        return d,instante


def ensaio(pasta,hz,fps,duracao,falhas=None):
    pasta.mkdir(parents=True)
    c=conectar(pasta,True);c.close()
    base=tamanho_banco(pasta)
    op=Opcoes.central(secrets.token_hex(24),host=cfg.REDE_SIM_HOST,porta=0,
        telemetria_hz=hz,imagens_fps=fps,reconexao_s=.15,heartbeat_s=.25,timeout_s=1.)
    camera=CameraSimulada()
    servidor=Servidor(op,Cenarios(telemetria_simulada(camera),hz),camera,True,falhas)
    ar=OpcoesArmazenamento.central(raiz=pasta,imagens=True,imagens_fps=2.)
    camera.iniciar();servidor.iniciar()
    receptor=ReceptorPC(url_local(op.host,servidor.porta),op,ar)
    inicio=time.monotonic(); pico=0
    try:
        receptor.iniciar(True,nome=f'SIMULADO {hz}Hz {fps}FPS',modo='simulacao',
                         observacoes='Transporte real localhost; sensores e CPU servidor artificiais identificados')
        gravacao=receptor.g.gravacao
        while time.monotonic()-inicio<duracao:
            time.sleep(.1)
            pico=max(pico,receptor.g.snapshot()['banco_bytes'])
    finally:
        receptor.fechar();servidor.parar();camera.parar()
    h=Historico(pasta)
    sid=h.consultar('sessoes')[0]['id']
    inicio_consulta=time.perf_counter(); resumo_sessao=h.resumo(simulado=True)
    tempo_consulta=time.perf_counter()-inicio_consulta
    inicio_export=time.perf_counter()
    exportacao,contagens=exportar(h,['consolidado','telemetria','motores','sensores','visao_computacional',
        'inteligencia_artificial','desempenho','comunicacao','eventos','sessoes','gravacoes','imagens','dataset','odometria'],sessao=sid)
    tempo_export=time.perf_counter()-inicio_export
    backup=criar(pasta)
    db=tamanho_banco(pasta)
    imgs=h.consultar('imagens',limite=1000)
    media_jpeg=sum(r['tamanho_bytes'] for r in imgs)/len(imgs) if imgs else None
    duracao_real=time.monotonic()-inicio
    return dict(simulado=True,telemetria_hz_alvo=hz,imagens_fps_alvo=fps,duracao_coleta_s=duracao,
        raiz=str(pasta),gravacao=gravacao,sessao=sid,resumo=resumo_sessao,gravador=receptor.g.snapshot(),
        escrita_lotes_s=resumo(list(receptor.g.tempos)),banco_final_bytes=db,base_schema_bytes=base,
        pico_db_wal_observado_bytes=pico,imagens_bytes=receptor.g.arquivos.bytes_imagens,imagens=len(imgs),
        jpeg_medio_bytes=media_jpeg,consulta_s=tempo_consulta,exportacao_s=tempo_export,
        linhas_exportadas=contagens,exportacao=str(exportacao),backup=str(backup),
        projecao_db_bytes_h=max(0,db-base)/duracao*3600,
        projecao_imagens_bytes_h=media_jpeg*ar.imagens_fps*3600 if media_jpeg is not None else None,
        projecoes='Extrapolacao linear deste ensaio sintetico curto; nao previsao de producao',
        integridade=h.integridade(),servidor=servidor.metricas.snapshot())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--duracao',type=float,default=5.)
    p.add_argument('--saida',type=Path,default=cfg.ARMAZ_DIR)
    a=p.parse_args()
    if not math.isfinite(a.duracao) or not 4<=a.duracao<=120:p.error('Duracao entre 4 e 120 s por cenario')
    raiz=a.saida/('validacao_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    resultados=[]
    for hz,fps,falhas in [(10,5,None),(50,15,None),(100,30,{'atraso_s':.08,'descartar_cada':7,'desconectar_s':2.})]:
        r=ensaio(raiz/f'cenario_{hz}hz',hz,fps,a.duracao,falhas)
        resultados.append(r)
        print(json.dumps({k:r[k] for k in ('telemetria_hz_alvo','resumo','banco_final_bytes','imagens','consulta_s','exportacao_s')},ensure_ascii=False),flush=True)
    (raiz/'resultado.json').write_text(json.dumps(resultados,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Exemplos e resultados SIMULADOS: {raiz}',flush=True)


if __name__=='__main__':main()
