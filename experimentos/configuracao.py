"""Configurações versionadas; execução exclusivamente virtual nesta etapa."""
import hashlib
import importlib.metadata
import json
import math
import platform
from pathlib import Path
import subprocess
import sys

RAIZ=Path(__file__).resolve().parents[1]
CONFIGURACOES={
 'A':dict(nome='OpenCV embarcado',algoritmo='opencv',processamento='embarcado'),
 'B':dict(nome='CNN embarcada',algoritmo='cnn-fotos',processamento='embarcado'),
 'C':dict(nome='OpenCV distribuído',algoritmo='opencv',processamento='distribuido'),
 'D':dict(nome='CNN distribuída',algoritmo='cnn-fotos',processamento='distribuido'),
}
PADRAO=dict(schema='experimento_v1',nome='Comparação A–D no PC',objetivo='Medir custos de software, sem inferir comportamento físico',
 hipotese='H3',configuracoes=['A','B','C','D'],duracao_s=5.,aquecimento_s=1.,repeticoes=5,semente=7,
 cenario='imagem_fixa_sintetica',resolucao=[480,640],camera_fps=15.,imagens_fps=5.,telemetria_hz=10.,inferencia_hz=5.,
 atraso_s=0.,gravar_imagens=False,origem='simulada',nivel=3,categoria='benchmark_integrado',
 manifesto='dataset_pista/resultados/treino_posicao_02/experimento.json',
 condicoes=dict(pista='JPEG sintético fixo compartilhado',iluminacao='pixels fixos',bateria=None,rede='loopback',
 velocidade_referencia_pps=0.,calibracao='simulada, sem medidas físicas'),criterios={})


def validar(d):
    if not isinstance(d,dict) or set(d)-set(PADRAO):raise ValueError('Configuração desconhecida')
    c={**PADRAO,**d}
    if c['schema']!='experimento_v1' or c['origem']!='simulada' or c['nivel']!=3:raise ValueError('Executor somente para nível 3 simulado; hardware não é iniciado')
    if c['categoria']!='benchmark_integrado' or c['cenario']!='imagem_fixa_sintetica':raise ValueError('Cenário não implementado no executor integrado')
    for k in ('nome','objetivo','hipotese','manifesto'):
        if not isinstance(c[k],str) or not 1<=len(c[k])<=1000:raise ValueError('Texto inválido: '+k)
    if not isinstance(c['configuracoes'],list) or not 1<=len(c['configuracoes'])<=4 or len(set(c['configuracoes']))!=len(c['configuracoes']) or any(x not in CONFIGURACOES for x in c['configuracoes']):raise ValueError('Selecione A, B, C ou D sem duplicidade')
    for k,lo,hi in [('duracao_s',1,86400),('aquecimento_s',0,3600),('camera_fps',.2,60),('imagens_fps',.2,60),('telemetria_hz',.2,200),('inferencia_hz',.2,30),('atraso_s',0,2)]:
        if type(c[k]) not in (int,float) or not math.isfinite(c[k]) or not lo<=c[k]<=hi:raise ValueError('Valor inválido: '+k)
    if type(c['repeticoes'])is not int or not 1<=c['repeticoes']<=100:raise ValueError('Repetições: 1–100')
    if type(c['semente'])is not int or not 0<=c['semente']<2**32:raise ValueError('Semente inválida')
    if type(c['gravar_imagens'])is not bool:raise ValueError('Booleano esperado')
    if c['resolucao']!=[480,640]:raise ValueError('Ensaio pareado A–D usa largura 480 e altura 640, compatíveis com a ROI original')
    if not isinstance(c['condicoes'],dict) or not isinstance(c['criterios'],dict):raise ValueError('Condições/critérios devem ser objetos')
    if c['condicoes'].get('velocidade_referencia_pps')!=0:raise ValueError('Ensaio de percepção parado; não avalia seguimento físico')
    if len(json.dumps(c,allow_nan=False))>32000:raise ValueError('Configuração extensa demais')
    for regra in c['criterios'].values():
        if not isinstance(regra,dict) or set(regra)-{'minimo','maximo','natureza'}:raise ValueError('Critério inválido')
        for k in ('minimo','maximo'):
            if regra.get(k)is not None and (type(regra[k])not in (float,int) or not math.isfinite(regra[k])):raise ValueError('Limiar não finito')
    return c


def ambiente():
    import psutil
    def git(*args):
        try:return subprocess.check_output(['git',*args],cwd=RAIZ,text=True,timeout=3,stderr=subprocess.DEVNULL).strip()
        except (OSError,subprocess.SubprocessError):return None
    dependencias={}
    for nome in ('numpy','opencv-python-headless','opencv-python','psutil','websockets','matplotlib','pytest','scipy'):
        try:dependencias[nome]=importlib.metadata.version(nome)
        except importlib.metadata.PackageNotFoundError:dependencias[nome]=None
    fontes=['config.py','controle.py','arduino/robo_firmware/config.h','arduino/robo_firmware/motores.cpp','arduino/esp32_cam_bancada/esp32_cam_bancada.ino','aprendizado/cnn.py','aprendizado/dataset_rotulado.py']
    for pasta in ('experimentos','distribuido','central_monitoramento','monitoramento','comunicacao','armazenamento','gemeo_digital'):
        fontes.extend(p.relative_to(RAIZ).as_posix() for p in (RAIZ/pasta).glob('*.py'))
    return dict(commit=git('rev-parse','HEAD'),arvore_modificada=bool(git('status','--porcelain')),
                python=sys.version,sistema=platform.platform(),cpu=platform.processor(),nucleos=psutil.cpu_count(),
                ram_total_bytes=psutil.virtual_memory().total,dependencias=dependencias,
                hashes={p:hashlib.sha256((RAIZ/p).read_bytes()).hexdigest() for p in sorted(set(fontes))},
                firmware_gravado=None,hardware_fisico=None,
                limitacao='Hardware medido é o PC executor. Firmware em disco não comprova versão gravada no Arduino.')
