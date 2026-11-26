"""Identidade do algoritmo inclui parâmetros e implementação compartilhados."""
import hashlib
import json
from pathlib import Path
import config as cfg


def versao_opencv():
    nomes=('ROI_INICIO','BLUR_KERNEL','LINHA_ESCURA','CONTRASTE_MIN','USAR_OTSU','LIMIAR_FIXO',
           'AREA_MIN','TRACEJADO_MAX_SEGMENTOS','TRACEJADO_MEMORIA_S','TRACEJADO_AMBIGUIDADE',
           'TRACEJADO_CONFIANCA_MIN','IMAGEM_ESPELHAR_H','IMAGEM_ESPELHAR_V')
    dados={n:getattr(cfg,n) for n in nomes}
    h=hashlib.sha256(json.dumps(dados,sort_keys=True,allow_nan=False).encode())
    raiz=Path(__file__).resolve().parents[1]/'visao'
    for nome in ('detector.py','sugestao.py'):
        # Checkouts Windows/Linux podem ter finais de linha diferentes.
        h.update((raiz/nome).read_bytes().replace(b'\r\n',b'\n'))
    return 'opencv_tracejado_existente_v1:'+h.hexdigest()[:16]
