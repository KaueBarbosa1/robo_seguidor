"""Um pipeline compartilhado pelos provedores local e remoto. Sem treinamento."""
import hashlib
import json
import math
from pathlib import Path
import time

import cv2
import numpy as np
import config as cfg
from visao.detector import DetectorLinha
from aprendizado.cnn import RedeLinha
from aprendizado.dataset_rotulado import preparar_foto,PREPROCESSAMENTO,limites_recorte
from distribuido.contratos import versao_opencv


class Pipeline:
    def __init__(self, algoritmo='opencv', manifesto=None):
        self.algoritmo=algoritmo;self.detector=DetectorLinha(tracejado=True)
        self.rede=self.pacote=None;self.versao=versao_opencv()
        self.navegavel=algoritmo=='opencv'
        if algoritmo=='cnn-fotos':
            if not manifesto:raise ValueError('Informe o experimento JSON dos pesos próprios')
            caminho=Path(manifesto);m=json.loads(caminho.read_text(encoding='utf-8'))
            if m.get('preprocessamento')!=PREPROCESSAMENTO or m.get('entrada')!=[1,40,80]:raise ValueError('Contrato CNN offline incompatível')
            pesos=caminho.parent/'pesos_posicao.npz'
            if not pesos.is_file():raise ValueError('Pesos CNN ausentes')
            self.rede=RedeLinha.carregar(pesos)
            if not all(np.isfinite(p).all() for p in self.rede.parametros()) or self.rede.hash()!=m['hash_pesos']:raise ValueError('Pesos/hash CNN inválidos')
            self.versao=self.rede.hash();self.navegavel=False
        elif algoritmo=='cnn-rl':
            if not manifesto:raise ValueError('Pacote pareado CNN/RL ausente')
            from aprendizado.inferencia_esp32 import Pacote
            self.pacote=Pacote(manifesto);self.versao=self.pacote.rede.hash()
            # Domínio sintético só fornece diagnóstico. Aprovação física nunca é inferida.
            self.navegavel=False
        elif algoritmo!='opencv':raise ValueError('Algoritmo desconhecido')

    def resetar(self):
        self.detector.limpar_historico()

    def processar(self, frame, observacao=None):
        inicio=time.perf_counter()
        if not isinstance(frame,np.ndarray) or frame.dtype!=np.uint8 or frame.ndim not in (2,3) or min(frame.shape[:2])<2:
            raise ValueError('Imagem deve ser uint8 cinza ou BGR')
        if frame.ndim==3 and frame.shape[2]!=3:raise ValueError('BGR precisa de três canais')
        h,w=frame.shape[:2]
        # Orientação igual à ThreadVisao; a CNN offline usa seu próprio contrato original.
        if self.algoritmo=='opencv':
            if cfg.IMAGEM_ESPELHAR_H or cfg.IMAGEM_ESPELHAR_V:
                frame=cv2.flip(frame,-1 if cfg.IMAGEM_ESPELHAR_H and cfg.IMAGEM_ESPELHAR_V else 1 if cfg.IMAGEM_ESPELHAR_H else 0)
            antes=time.perf_counter();r=self.detector.processar(frame);fim=time.perf_counter()
            saida=dict(linha_visivel=bool(r.achou),posicao=float(r.erro) if r.achou else None,
                       erro=float(r.erro) if r.achou else None,confianca=float(r.confianca),
                       direcao=float(r.direcao),escala_direcao=(h-r.y0)/(w/2),motivo=r.motivo,
                       roi=[0,r.y0,w,h-r.y0],entrada=[h,w],preprocessamento_s=None,
                       inferencia_s=fim-antes,acao=None,semantica='erro_lateral_normalizado')
        elif self.algoritmo=='cnn-fotos':
            antes=time.perf_counter();x=preparar_foto(frame);pre=time.perf_counter()-antes
            if x.shape!=(1,1,40,80) or not np.isfinite(x).all():raise ValueError('Entrada CNN inválida')
            antes=time.perf_counter();d,_=self.rede.prever(x,lote=1);inf=time.perf_counter()-antes
            if not np.isfinite(d).all() or not -1<=float(d[0])<=1:raise ValueError('Saída CNN inválida')
            y0,y1=limites_recorte(h,w)
            saida=dict(linha_visivel=None,posicao=float(d[0]),erro=None,confianca=None,
                       direcao=None,escala_direcao=None,motivo='diagnostico_offline_sem_validade_supervisionada',
                       roi=[0,y0,w,y1-y0],entrada=[1,40,80],preprocessamento_s=pre,inferencia_s=inf,acao=None,
                       semantica='posicao_horizontal_y075_sem_ganho_de_controle')
        else:
            antes=time.perf_counter();x=self.pacote.entrada(frame);pre=time.perf_counter()-antes
            antes=time.perf_counter();d,v=self.pacote.rede.prever(x,lote=1);inf=time.perf_counter()-antes
            if not np.isfinite(d).all() or not np.isfinite(v).all():raise ValueError('Saída CNN/RL inválida')
            acao=None
            if observacao is not None:
                # Observação calibrada fornecida explicitamente; nunca inventa velocidade.
                i=self.pacote.escolher(float(d[0]),observacao['delta'],observacao['velocidade'],observacao['idade'],observacao['anterior'])
                from aprendizado.rl_simulado import ACOES
                steer,fator=ACOES[i];acao=dict(indice=i,steer=float(steer),vel_fator=float(fator))
            saida=dict(linha_visivel=None,posicao=float(d[0]),erro=None,confianca=None,
                       direcao=None,escala_direcao=None,motivo='pacote_em_diagnostico_sem_autorizacao_de_navegacao',
                       roi=None,entrada=[1,40,80],preprocessamento_s=pre,inferencia_s=inf,acao=acao,
                       semantica=self.pacote.meta['percepcao']['semantica'])
        return dict(saida,algoritmo=self.algoritmo,versao_modelo=self.versao,navegavel=self.navegavel,
                    processamento_s=time.perf_counter()-inicio,dimensoes=[h,w])


class PercepcaoLocal:
    def __init__(self,pipeline):self.pipeline=pipeline
    def processar(self,frame,observacao=None):return self.pipeline.processar(frame,observacao)


class PercepcaoRemota(PercepcaoLocal):
    """O serviço remoto passa a mesma matriz decodificada ao mesmo pipeline."""

def decodificar_jpeg(jpeg):
    inicio=time.perf_counter()
    # Limita dimensões antes de aceitar o resultado da decodificação.
    if not isinstance(jpeg,bytes) or len(jpeg)>4*1024**2:raise ValueError('JPEG fora do limite')
    if not jpeg.startswith(b'\xff\xd8'):raise ValueError('Cabeçalho JPEG inválido')
    pos=2;dimensoes=None
    while pos+4<=len(jpeg):
        if jpeg[pos]!=255:raise ValueError('Marcador JPEG inválido')
        while pos<len(jpeg) and jpeg[pos]==255:pos+=1
        if pos>=len(jpeg):break
        marcador=jpeg[pos];pos+=1
        if marcador in (0xD9,0xDA):break
        if marcador==0x01 or 0xD0<=marcador<=0xD8:continue
        if pos+2>len(jpeg):break
        tamanho=int.from_bytes(jpeg[pos:pos+2],'big')
        if tamanho<2 or pos+tamanho>len(jpeg):raise ValueError('Segmento JPEG inválido')
        if marcador in (0xC0,0xC1,0xC2,0xC3,0xC5,0xC6,0xC7,0xC9,0xCA,0xCB,0xCD,0xCE,0xCF):
            if tamanho<8:raise ValueError('Dimensões JPEG ausentes')
            h=int.from_bytes(jpeg[pos+3:pos+5],'big');w=int.from_bytes(jpeg[pos+5:pos+7],'big')
            dimensoes=(h,w);break
        pos+=tamanho
    if dimensoes is None or min(dimensoes)<2 or max(dimensoes)>4096 or dimensoes[0]*dimensoes[1]>8*1024**2:
        raise ValueError('Resolução JPEG excessiva ou inválida antes do decode')
    frame=cv2.imdecode(np.frombuffer(jpeg,np.uint8),cv2.IMREAD_COLOR)
    if frame is None or max(frame.shape[:2])>4096:raise ValueError('JPEG inválido/resolução excessiva')
    return frame,time.perf_counter()-inicio
