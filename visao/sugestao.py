"""Sugestão offline de trajetória tracejada por OpenCV, sem rede ou pesos.

Agrupa vários segmentos pela orientação e continuidade. É auxílio à revisão
humana: não determina visibilidade e nunca salva rótulos ou comanda motores.
"""
from dataclasses import dataclass
import math

import cv2
import numpy as np

VERSAO = 'segmentos_geometria_v2'


@dataclass
class SugestaoLinha:
    pontos: list
    metodo: str
    segmentos: int
    aviso: str = 'Sugestão automática: confira curvas e cruzamentos antes de confirmar.'
    preprocessamento: str = 'legado'


def tratar_cinza(cinza, modo='normalizado'):
    """Corrige iluminação para segmentar fita escura; não modifica o original.

    Fechamento estima o piso local. A divisão pelo fundo reduz variações lentas
    de iluminação; CLAHE é uma alternativa de comparação, não um modelo treinado.
    """
    if cinza.ndim != 2 or cinza.dtype != np.uint8:
        raise ValueError('Esperada imagem cinza uint8')
    if modo == 'legado':
        return cinza.copy()
    if modo == 'clahe':
        return cv2.createCLAHE(clipLimit=2., tileGridSize=(8, 8)).apply(cinza)
    if modo != 'normalizado':
        raise ValueError(f'Pré-processamento desconhecido: {modo}')
    fundo = cv2.morphologyEx(cinza, cv2.MORPH_CLOSE,
                             cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (51, 51)))
    return cv2.divide(cinza, np.maximum(fundo, 1), scale=220.)


def preparar_imagem(imagem, modo='normalizado'):
    """Imagem de análise proporcional e cinza tratado, na mesma escala da sugestão."""
    h, w = imagem.shape[:2]
    fator = min(1., 640 / max(h, w))
    pequena = cv2.resize(imagem, (round(w * fator), round(h * fator)), interpolation=cv2.INTER_AREA)
    cinza = pequena if pequena.ndim == 2 else cv2.cvtColor(pequena, cv2.COLOR_BGR2GRAY)
    return pequena, tratar_cinza(cinza, modo)


def _segmentos(mascara, *, area_min=12, fracao_area_max=.08,
               fracao_altura_max=.45, alongamento_max=100, max_candidatos=None):
    h, w = mascara.shape
    n, labels, stats, centros = cv2.connectedComponentsWithStats(mascara, connectivity=8)
    candidatos = []
    indices = [i for i in range(1, n)
               if area_min <= stats[i, 4] <= h * w * fracao_area_max
               and stats[i, 2] <= w * .45 and stats[i, 3] <= h * fracao_altura_max]
    # No uso contínuo, excesso de componentes causa abstenção antes da PCA.
    # Padrões do uso offline preservados quando não há limite explícito.
    if max_candidatos is not None and len(indices) > max_candidatos:
        return []
    for i in indices:
        x, y, bw, bh, area = stats[i]
        ys, xs = np.nonzero(labels[y:y + bh, x:x + bw] == i)
        xy = np.column_stack((xs, ys)).astype(np.float32)
        _, (lado_a, lado_b), _ = cv2.minAreaRect(xy)
        menor, maior = sorted((lado_a, lado_b))
        if menor < 3 or maior < 5 or area / max(lado_a * lado_b, 1.) < .55:
            continue
        _, vetores, valores = cv2.PCACompute2(xy, mean=None)
        vx, vy = vetores[0]
        if vy < 0:
            vx, vy = -vx, -vy
        # Rejuntes finos são removidos pela abertura; traços quase horizontais
        # são concorrentes frequentes. Nenhuma dessas regras prova a identidade.
        razao = valores[0, 0] / max(valores[1, 0], .1)
        if vy < .45 or not 1.5 <= razao <= alongamento_max:
            continue
        media = xy.mean(axis=0)
        eixo = np.array([vx, vy])
        projecoes = (xy - media) @ eixo
        extremos = [media + eixo * t + [x, y] for t in np.quantile(projecoes, [.15, .85])]
        candidatos.append({'x': float(centros[i, 0]), 'y': float(centros[i, 1]),
                           'angulo': math.atan2(float(vx), float(vy)), 'area': int(area),
                           'espessura': float(menor),
                           'extremos': [p.tolist() for p in extremos]})
    return sorted(candidatos, key=lambda s: s['y'])


def _trajetoria(segmentos, h, w, referencia=None):
    """Caminho crescente em y; permite vãos, penaliza descontinuidade de ângulo."""
    caminhos, scores, angulos = [], [], []
    for i, s in enumerate(segmentos):
        # Quantidade de pedaços sozinha favorecia rejuntes fragmentados nas
        # bordas. Pondera o suporte de pixels de cada segmento, com teto.
        recompensa = .2 + min(3., s['area'] / (h * w * .002))
        if referencia is not None and referencia[0, 1] <= s['y'] <= referencia[-1, 1]:
            esperado = np.interp(s['y'], referencia[:, 1], referencia[:, 0])
            recompensa -= min(1.5, 2. * abs(s['x'] - esperado) / (w * .25))
        melhor, score, direcao = [i], recompensa, None
        for j in range(i):
            p = segmentos[j]
            dy, dx = s['y'] - p['y'], s['x'] - p['x']
            if not 8 <= dy <= h * .5 or abs(dx) > 1.7 * dy + w * .04:
                continue
            if max(s['espessura'], p['espessura']) > 4 * min(s['espessura'], p['espessura']):
                continue
            angulo = math.atan2(dx, dy)
            diferenca = (abs(angulo - p['angulo']) + abs(angulo - s['angulo'])) / 2
            if diferenca > .9:
                continue
            curva = abs(angulo - angulos[j]) if angulos[j] is not None else 0.
            if curva > .65:
                continue  # evita saltar da fita para fundo/objetos numa mudança brusca
            candidato = scores[j] + recompensa - 1.2 * diferenca - .8 * curva - .25 * dy / h
            if candidato > score:
                melhor, score, direcao = caminhos[j] + [i], candidato, angulo
        caminhos.append(melhor)
        scores.append(score)
        angulos.append(direcao)
    validos = []
    for i, c in enumerate(caminhos):
        span = segmentos[c[-1]]['y'] - segmentos[c[0]]['y']
        if len(c) >= 2 and span >= .08 * h:
            validos.append((scores[i] + span / h, c))
        s = segmentos[i]
        if s['area'] >= h * w * .001 and s['extremos'][1][1] - s['extremos'][0][1] >= .03 * h:
            # Permite que um traço bem definido vença uma sequência de ruído.
            suporte = .2 + min(3., s['area'] / (h * w * .002))
            validos.append((suporte, [i]))
    if not validos:
        return [], 0.
    score, caminho = max(validos, key=lambda item: item[0])
    return [segmentos[i] for i in caminho], score


def sugerir_linha(imagem, referencia=None, preprocessamento='normalizado'):
    """Devolve centros em pixels da imagem original; sem status de visibilidade.

    A redução preserva proporção. Compara limiares escuros e Otsu limitado para
    evitar que regiões grandes do piso dominem a máscara. Não usa a CNN treinada.
    """
    if imagem is None or imagem.dtype != np.uint8 or imagem.ndim not in (2, 3):
        raise ValueError('Esperada imagem cinza/BGR uint8')
    h_original, w_original = imagem.shape[:2]
    if min(h_original, w_original) < 16:
        raise ValueError('Imagem pequena demais para sugerir trajetória')
    pequena, cinza = preparar_imagem(imagem, preprocessamento)
    ref = None
    if referencia:
        ref = np.array(sorted(referencia, key=lambda p: p[1]), dtype=float)
        if ref.ndim != 2 or ref.shape[1] != 2 or len(ref) < 2 or not np.isfinite(ref).all():
            raise ValueError('Referência temporal inválida')
        ref *= [cinza.shape[1] / w_original, cinza.shape[0] / h_original]
    suave = cv2.GaussianBlur(cinza, (3, 3), 0)
    if int(suave.max()) - int(suave.min()) < 25:
        return SugestaoLinha([], '', 0, 'Sem sugestão. Isso não significa que a linha esteja ausente.', preprocessamento)
    otsu, _ = cv2.threshold(suave, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    limiares = sorted(set([80, 100, 120, max(40, min(140, round(otsu)))]))
    melhor, score_melhor, metodo = [], 0., ''
    for limiar in limiares:
        _, mascara = cv2.threshold(suave, limiar, 255, cv2.THRESH_BINARY_INV)
        mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        caminho, score = _trajetoria(_segmentos(mascara), *cinza.shape, referencia=ref)
        if score > score_melhor:
            melhor, score_melhor, metodo = caminho, score, f'{preprocessamento}_limiar_{limiar}_abertura3'
    locais = []
    if melhor:
        locais = [melhor[0]['extremos'][0]] + [[s['x'], s['y']] for s in melhor] + [melhor[-1]['extremos'][1]]
    pontos = [[int(round(x * w_original / cinza.shape[1])),
               int(round(y * h_original / cinza.shape[0]))] for x, y in locais]
    pontos = [[min(w_original - 1, max(0, x)), min(h_original - 1, max(0, y))] for x, y in pontos]
    pontos = [p for i, p in enumerate(pontos) if i == 0 or p[1] != pontos[i - 1][1]]
    if len(pontos) < 2:
        return SugestaoLinha([], '', 0, 'Sem sugestão. Isso não significa que a linha esteja ausente.', preprocessamento)
    aviso = ('Só um segmento aproveitável: confira a extensão da trajetória antes de confirmar.'
             if len(melhor) == 1 else 'Sugestão automática: confira curvas e cruzamentos antes de confirmar.')
    return SugestaoLinha(pontos, metodo, len(melhor), aviso, preprocessamento)
