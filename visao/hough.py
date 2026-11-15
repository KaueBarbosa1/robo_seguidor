"""Referência geométrica offline para fita escura sobre piso claro."""
from dataclasses import dataclass
from itertools import combinations

import cv2
import numpy as np


PARAMETROS = dict(canny=(50, 120), votos=10, comprimento_minimo=12, vao_maximo=8,
                  meia_faixa=28, largura_fita=(4, 30), contraste_minimo=20,
                  inclinacao_maxima=2.0, diferenca_inclinacao=0.35)


@dataclass
class FaixaHough:
    y: float
    segmentos: list[tuple[int, int, int, int]]
    aceitos: tuple[int, ...] = ()
    x: float | None = None
    motivo: str = 'sem_par_compativel'


@dataclass
class ResultadoHough:
    bordas: np.ndarray
    faixas: list[FaixaHough]

    @property
    def central(self):
        return self.faixas[1]


def _x_no_segmento(segmento, y):
    x1, y1, x2, y2 = segmento
    return x1 + (x2 - x1) * (y - y1) / (y2 - y1)


def _contraste(roi, esquerda, direita, inicio, fim):
    """Mediana do contraste entre o interior e os dois lados do par."""
    contrastes = []
    largura = roi.shape[1]
    for y in np.linspace(inicio, fim, 7).round().astype(int):
        x1, x2 = _x_no_segmento(esquerda, y), _x_no_segmento(direita, y)
        distancia = x2 - x1
        xs = np.round(x1 + distancia * np.array([-.4, .3, .5, .7, 1.4])).astype(int)
        if not 0 <= xs[0] < xs[-1] < largura:
            continue
        intensidades = roi[y, xs].astype(float)
        contrastes.append(min(intensidades[0], intensidades[4]) - np.median(intensidades[1:4]))
    return float(np.median(contrastes)) if len(contrastes) >= 4 else 0.0


def _analisar_faixa(cinza, bordas, y):
    p = PARAMETROS
    y0 = max(0, int(y) - p['meia_faixa'])
    y1 = min(bordas.shape[0], int(y) + p['meia_faixa'] + 1)
    linhas = cv2.HoughLinesP(bordas[y0:y1].copy(), 1, np.pi / 180, p['votos'],
                             minLineLength=p['comprimento_minimo'], maxLineGap=p['vao_maximo'])
    segmentos = []
    if linhas is not None:
        for x1, a, x2, b in linhas.reshape(-1, 4).tolist():
            if a > b:
                x1, a, x2, b = x2, b, x1, a
            segmentos.append((x1, a + y0, x2, b + y0))
    faixa = FaixaHough(y, segmentos, motivo='sem_segmentos' if not segmentos else 'sem_par_compativel')
    bordas_candidatas = []
    for i, s in enumerate(segmentos):
        x1, a, x2, b = s
        if a < b and a <= y <= b:
            inclinacao = (x2 - x1) / (b - a)
            if abs(inclinacao) <= p['inclinacao_maxima']:
                bordas_candidatas.append((_x_no_segmento(s, y), i, inclinacao))
    bordas_candidatas.sort()
    pares = []
    for (x1, i, d1), (x2, j, d2) in combinations(bordas_candidatas, 2):
        if not p['largura_fita'][0] <= x2 - x1 <= p['largura_fita'][1]:
            continue
        if abs(d1 - d2) > p['diferenca_inclinacao']:
            continue
        esquerda, direita = segmentos[i], segmentos[j]
        a, b = max(esquerda[1], direita[1]), min(esquerda[3], direita[3])
        if b - a < 6:
            continue
        contraste = _contraste(cinza, esquerda, direita, a, b)
        if contraste >= p['contraste_minimo']:
            pares.append((contraste * (b - a), (x1 + x2) / 2, i, j))
    if not pares:
        return faixa
    nota, x, i, j = max(pares)
    if any(n >= .85 * nota and abs(outro_x - x) >= 12 for n, outro_x, _, _ in pares):
        faixa.motivo = 'pares_ambiguos'
        return faixa
    faixa.x, faixa.aceitos, faixa.motivo = x, (i, j), 'par_aceito'
    return faixa


def detectar_hough(roi: np.ndarray, y_ref: float) -> ResultadoHough:
    """Analisa três faixas de um recorte cinza de 320 × 160 pixels.

    As estimativas são locais a cada altura. Os extremos não preenchem
    a altura central quando ela não tem um par de bordas válido.
    """
    if roi.shape != (160, 320) or roi.dtype != np.uint8 or not 40 <= y_ref < 120:
        raise ValueError('Esperado recorte cinza uint8 320 × 160 com referência na metade central')
    suave = cv2.GaussianBlur(roi, (3, 3), 0)
    bordas = cv2.Canny(suave, *PARAMETROS['canny'])
    faixas = [_analisar_faixa(suave, bordas, y) for y in (y_ref - 40, y_ref, y_ref + 40)]
    return ResultadoHough(bordas, faixas)
