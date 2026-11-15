"""Localização offline em fotos rotuladas; separada dos episódios do robô.

O mesmo preparar_foto deve ser usado para inferência destes pesos. Não substitui
dados.preparar_entrada nem produz ações para os motores.
"""
import csv
import hashlib
from pathlib import Path

import cv2
import numpy as np

from aprendizado.dados import normalizar
from tools.rotular_linha import carregar_revisoes, validar_anotacao

PREPROCESSAMENTO = 'foto_roi_2por1_y075_v1'
Y_RELATIVO = 0.75

# Inclui vistas próximas e amplas no treino e na validação. Não muda com a
# quantidade de frames anotados. Gravações são do mesmo ambiente: teste exploratório.
DIVISAO = {
    'treino': ['20261103_123529.mp4', '20261103_145305.mp4', '20261103_145818.mp4',
               'IMG_0324.mp4', 'IMG_0327.mp4'],
    'validacao': ['20261103_145411.mp4', '20261103_145514.mp4'],
    'teste': ['20261103_145908.mp4', 'IMG_0329.mp4'],
}


def limites_recorte(altura, largura):
    """Recorte 2:1 na largura inteira, centrado na referência vertical 75%."""
    if largura < 2 or largura % 2 or altura < 2:
        raise ValueError('Esperada largura par >=2 e altura >=2')
    h_roi = largura // 2
    y_ref = Y_RELATIVO * (altura - 1)
    y0 = round(y_ref - h_roi / 2)
    if y0 < 0 or y0 + h_roi > altura:
        raise ValueError('Não cabe o recorte proporcional nesta imagem')
    return y0, y0 + h_roi


def reduzir_foto(imagem):
    """BGR/cinza -> ROI proporcional -> cinza uint8 40x80, sem distorção."""
    h, w = imagem.shape[:2]
    y0, y1 = limites_recorte(h, w)
    roi = imagem[y0:y1]
    if roi.ndim == 3:
        roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    return cv2.resize(roi, (80, 40), interpolation=cv2.INTER_AREA)


def preparar_foto(imagem):
    return normalizar(reduzir_foto(imagem)[None])


def posicao_anotada(revisao):
    """Interpola apenas dentro da extensão humana; sem extrapolar trajetória."""
    w, h = int(revisao['largura']), int(revisao['altura'])
    pts = validar_anotacao(revisao['visibilidade'], revisao['pontos_px'], w, h)
    if revisao['visibilidade'] not in {'visivel', 'parcial'}:
        return None
    y_ref = Y_RELATIVO * (h - 1)
    if not pts[0][1] <= y_ref <= pts[-1][1]:
        return None
    x = float(np.interp(y_ref, [p[1] for p in pts], [p[0] for p in pts]))
    return 2. * x / (w - 1) - 1.


def grupo_video(video, divisao=DIVISAO):
    grupos = [grupo for grupo, videos in divisao.items() if video in videos]
    if len(grupos) != 1:
        raise ValueError(f'Vídeo ausente ou repetido entre divisões: {video}')
    return grupos[0]


def carregar_fotos(base, revisoes):
    base, revisoes = Path(base), Path(revisoes)
    rotulos = carregar_revisoes(revisoes)
    with (base / 'metadados.csv').open(encoding='utf-8-sig', newline='') as arquivo:
        registros = list(csv.DictReader(arquivo, delimiter=';'))
    meta = {r['imagem']: r for r in registros}
    if len(meta) != len(registros):
        raise ValueError('Nomes duplicados no CSV')
    arquivos = {}
    for p in (base / 'imagens').rglob('*'):
        if p.is_file():
            if p.name in arquivos:
                raise ValueError(f'Imagem duplicada: {p.name}')
            arquivos[p.name] = p
    if set(rotulos) - set(meta):
        raise ValueError('Revisões contêm imagem ausente do CSV')
    incluidos, excluidos, reduzidos, alvos = [], [], [], []
    for nome, revisao in sorted(rotulos.items()):
        registro = meta[nome]
        if any(revisao[k] != registro[k] for k in ['video_origem', 'timestamp', 'largura', 'altura']):
            raise ValueError(f'Metadados divergentes: {nome}')
        bruto = arquivos[nome].read_bytes()
        if hashlib.sha256(bruto).hexdigest() != revisao['sha256']:
            raise ValueError(f'Hash divergente: {nome}')
        img = cv2.imdecode(np.frombuffer(bruto, np.uint8), cv2.IMREAD_COLOR)
        if img is None or img.shape[:2] != (int(registro['altura']), int(registro['largura'])):
            raise ValueError(f'Imagem/resolução inválida: {nome}')
        grupo = grupo_video(registro['video_origem'])
        alvo = posicao_anotada(revisao)
        if alvo is None:
            motivo = ('estado_' + revisao['visibilidade'] if revisao['visibilidade'] in {'ausente', 'ambiguo'}
                      else 'pontos_nao_cobrem_y075')
            excluidos.append({**registro, 'motivo': motivo})
            continue
        reduzidos.append(reduzir_foto(img))
        alvos.append(alvo)
        y0, y1 = limites_recorte(*img.shape[:2])
        incluidos.append({**registro, 'grupo': grupo, 'posicao': alvo, 'sha256': revisao['sha256'],
                          'visibilidade': revisao['visibilidade'], 'pontos_px': revisao['pontos_px'],
                          'recorte_y0': y0, 'recorte_y1': y1,
                          'arquivo': str(arquivos[nome].relative_to(base))})
    if not incluidos:
        raise ValueError('Nenhuma anotação utilizável para posição em y=75%')
    return np.stack(reduzidos), np.array(alvos, dtype=np.float32), incluidos, excluidos
