"""Estudo offline dos frames; não produz rótulos e não acessa o carrinho.

Na Raspberry Pi, com a .venv: python tools/estudar_linha.py
"""
import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from visao.detector import DetectorLinha, desenhar_debug  # noqa: E402


def selecionar(registros, quantidade):
    """Amostra temporal determinística: inclui extremos, sem sorteio de frames."""
    grupos = defaultdict(list)
    for registro in registros:
        grupos[registro['video_origem']].append(registro)
    escolhidos = []
    for grupo in grupos.values():
        grupo.sort(key=lambda r: float(r['timestamp']))
        indices = np.linspace(0, len(grupo) - 1, min(quantidade, len(grupo)))
        escolhidos.extend(grupo[i] for i in sorted(set(indices.round().astype(int))))
    return escolhidos


def mascaras(cinza, limiar, bloco, constante):
    suave = cv2.GaussianBlur(cinza, (3, 3), 0)
    _, fixa = cv2.threshold(suave, limiar, 255, cv2.THRESH_BINARY_INV)
    valor, otsu = cv2.threshold(suave, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    adaptativa = cv2.adaptiveThreshold(suave, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                      cv2.THRESH_BINARY_INV, bloco, constante)
    return {'fixo': fixa, 'otsu': otsu, 'adaptativo': adaptativa}, valor


def componentes(mascara, area_min):
    n, ids, estat, centros = cv2.connectedComponentsWithStats(mascara, connectivity=8)
    validos = [i for i in range(1, n) if estat[i, cv2.CC_STAT_AREA] >= area_min]
    return ids, estat, centros, validos


def painel(imagem, titulo):
    if imagem.ndim == 2:
        imagem = cv2.cvtColor(imagem, cv2.COLOR_GRAY2BGR)
    h, w = imagem.shape[:2]
    fator = min(240 / w, 427 / h)
    pequena = cv2.resize(imagem, (round(w * fator), round(h * fator)), interpolation=cv2.INTER_AREA)
    saida = np.full((460, 260, 3), 245, np.uint8)
    saida[30:30 + pequena.shape[0], 10:10 + pequena.shape[1]] = pequena
    cv2.putText(saida, titulo, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, .45, (0, 0, 0), 1)
    return saida


def salvar_imagem(caminho, imagem):
    if not cv2.imwrite(str(caminho), imagem):
        raise OSError(f'Não foi possível salvar {caminho}')


def executar(args):
    base = args.dataset.resolve()
    csv_origem = base / 'metadados.csv'
    with csv_origem.open(encoding='utf-8-sig', newline='') as arquivo:
        registros = list(csv.DictReader(arquivo, delimiter=';'))
    if not registros:
        raise ValueError('CSV vazio')
    por_nome = defaultdict(list)
    for caminho in (base / 'imagens').rglob('*'):
        if caminho.is_file():
            por_nome[caminho.name].append(caminho)
    amostras = selecionar(registros, args.por_video)
    # Uma nova pasta por execução; nunca substituir diagnóstico anterior.
    saida = args.saida.resolve()
    if saida == base or base.is_relative_to(saida):
        raise ValueError('A saída deve ser uma pasta nova, separada das imagens originais')
    saida.mkdir(parents=True, exist_ok=False)
    (saida / 'diagnosticos').mkdir()
    detector = DetectorLinha()
    kernel = np.ones((3, 3), np.uint8)
    medicoes, inventario = [], []
    for numero, registro in enumerate(amostras, 1):
        encontrados = por_nome[registro['imagem']]
        if len(encontrados) != 1:
            raise ValueError(f"Esperado um arquivo para {registro['imagem']}: {len(encontrados)}")
        caminho = encontrados[0]
        original = cv2.imread(str(caminho))
        if original is None:
            raise ValueError(f'Imagem ilegível: {caminho}')
        h, w = original.shape[:2]
        if (w, h) != (int(registro['largura']), int(registro['altura'])):
            raise ValueError(f'Resolução divergente: {caminho}')
        # Preserva proporção 9:16; não usa o pré-processamento da CNN aqui.
        fator = min(1., args.altura / h)
        imagem = cv2.resize(original, (round(w * fator), round(h * fator)), interpolation=cv2.INTER_AREA)
        cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
        masks, valor_otsu = mascaras(cinza, args.limiar, args.bloco, args.constante)
        abertas = cv2.morphologyEx(masks['otsu'], cv2.MORPH_OPEN, kernel)
        fechadas = cv2.morphologyEx(masks['otsu'], cv2.MORPH_CLOSE, kernel)
        colorida = imagem.copy()
        _, estat, centros, validos = componentes(masks['otsu'], args.area_min)
        for i in validos:
            x, y, largura, altura, _ = estat[i]
            cv2.rectangle(colorida, (x, y), (x + largura, y + altura), (0, 180, 255), 1)
            cv2.putText(colorida, str(i), tuple(centros[i].astype(int)),
                        cv2.FONT_HERSHEY_SIMPLEX, .35, (0, 0, 255), 1)
        roi_debug = imagem.copy()
        for fracao, cor in [(0.35, (255, 100, 0)), (0.50, (0, 180, 0))]:
            y = round(imagem.shape[0] * fracao)
            cv2.line(roi_debug, (0, y), (imagem.shape[1] - 1, y), cor, 2)
        # Apenas referência do algoritmo existente, não verdade nem rótulo.
        referencia = detector.processar(imagem)
        itens = [(imagem, 'Original proporcional'), (cinza, 'Cinza'),
                 (masks['fixo'], f'Fixo = {args.limiar}'),
                 (masks['otsu'], f'Otsu = {valor_otsu:.0f}'),
                 (masks['adaptativo'], f'Adaptativo {args.bloco}/{args.constante:g}'),
                 (abertas, 'Otsu + abertura 3x3'), (fechadas, 'Otsu + fechamento 3x3'),
                 (colorida, 'Componentes: sem escolher'), (roi_debug, 'ROIs candidatas 35%/50%'),
                 (desenhar_debug(imagem, referencia), 'Detector atual: referencia')]
        paineis = [painel(img, titulo) for img, titulo in itens]
        mosaico = np.vstack([np.hstack(paineis[:5]), np.hstack(paineis[5:])])
        destino = saida / 'diagnosticos' / (caminho.stem + '.jpg')
        salvar_imagem(destino, mosaico)
        inventario.append({**registro, 'arquivo': str(caminho.relative_to(base)),
                           'sha256': hashlib.sha256(caminho.read_bytes()).hexdigest(),
                           'diagnostico': str(destino.relative_to(saida)),
                           'baseline_achou': bool(referencia.achou),
                           'baseline_erro': referencia.erro if referencia.achou else None})
        for metodo, mascara in masks.items():
            for morfologia in ['nenhuma', 'abertura', 'fechamento']:
                for roi in [0., .35, .50]:
                    # Limiares calculados na imagem inteira; o corte serve para
                    # comparar componentes na ROI, não para recalcular threshold.
                    recorte = mascara[int(roi * mascara.shape[0]):]
                    if morfologia != 'nenhuma':
                        op = cv2.MORPH_OPEN if morfologia == 'abertura' else cv2.MORPH_CLOSE
                        recorte = cv2.morphologyEx(recorte, op, kernel)
                    _, st, _, ids = componentes(recorte, args.area_min)
                    areas = [int(st[i, cv2.CC_STAT_AREA]) for i in ids]
                    medicoes.append({'imagem': registro['imagem'], 'video_origem': registro['video_origem'],
                                     'timestamp': registro['timestamp'], 'metodo': metodo,
                                     'morfologia': morfologia, 'roi_inicio': roi,
                                     'fracao_preta': float(np.mean(recorte > 0)),
                                     'componentes': len(ids), 'maior_area': max(areas, default=0),
                                     'limiar_otsu': valor_otsu if metodo == 'otsu' else ''})
        print(f'{numero}/{len(amostras)} {registro["imagem"]}', flush=True)
    with (saida / 'comparacao.csv').open('w', encoding='utf-8', newline='') as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(medicoes[0]))
        escritor.writeheader()
        escritor.writerows(medicoes)
    parametros = vars(args).copy()
    parametros = {k: str(v) if isinstance(v, Path) else v for k, v in parametros.items()}
    import config as cfg
    manifesto = {'criado_utc': datetime.now(timezone.utc).isoformat(), 'parametros': parametros,
                 'opencv': cv2.__version__, 'numpy': np.__version__,
                 'csv_sha256': hashlib.sha256(csv_origem.read_bytes()).hexdigest(),
                 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 'detector_sha256': hashlib.sha256((RAIZ / 'visao/detector.py').read_bytes()).hexdigest(),
                 'config_sha256': hashlib.sha256((RAIZ / 'config.py').read_bytes()).hexdigest(),
                 'baseline_config': {k: getattr(cfg, k) for k in ['ROI_INICIO', 'BLUR_KERNEL', 'LINHA_ESCURA',
                                      'USAR_OTSU', 'LIMIAR_FIXO', 'AREA_MIN', 'CONTRASTE_MIN']},
                 'amostras': inventario, 'rotulos_gerados': False}
    (saida / 'manifesto.json').write_text(json.dumps(manifesto, indent=2, ensure_ascii=False), encoding='utf-8')
    (saida / 'LEIA-ME.md').write_text(
        '# Estudo offline da linha\n\n'
        f'{len(amostras)} amostras temporais; {len(medicoes)} combinações medidas.\n\n'
        'Comparação de fixo, Otsu e adaptativo, sem morfologia/com abertura/com fechamento, '
        'e recortes inferiores a partir de 0%, 35% e 50%. Coordenadas são candidatas de estudo. '
        'Limiarização usa a imagem inteira; ROI recorta as máscaras. '
        'Redução proporcional, sem distorção. Kernel 3x3 e área mínima são na resolução de análise.\n\n'
        'Os dez painéis mostram original, cinza, três thresholds, abertura e fechamento Otsu, '
        'componentes sem seleção, ROIs candidatas e detector atual como referência. '
        'Componentes/quantidade de pixels pretos não medem acurácia. '
        'Não existe vencedor automático sem rótulos revisados. O erro do detector não é rótulo.\n\n'
        'Amostras foram usadas para exploração: não tratá-las depois como teste independente intocado. '
        'Manifesto registra parâmetros, hashes e origem; comparacao.csv não é dataset supervisionado.\n',
        encoding='utf-8')
    print(f'Resultados: {saida}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=RAIZ / 'dataset_pista')
    parser.add_argument('--saida', type=Path, default=RAIZ / 'dataset_pista/resultados/estudo_01')
    parser.add_argument('--por-video', type=int, default=5)
    parser.add_argument('--altura', type=int, default=640)
    parser.add_argument('--limiar', type=int, default=100)
    parser.add_argument('--bloco', type=int, default=31)
    parser.add_argument('--constante', type=float, default=7.)
    parser.add_argument('--area-min', type=int, default=20)
    args = parser.parse_args()
    if args.por_video < 1 or args.altura < 64 or args.area_min < 1:
        parser.error('por-video e area-min devem ser positivos; altura deve ser >=64')
    if not 0 <= args.limiar <= 255 or args.bloco < 3 or args.bloco % 2 == 0:
        parser.error('limiar deve ser 0..255; bloco deve ser ímpar e >=3')
    if not np.isfinite(args.constante):
        parser.error('constante deve ser finita')
    executar(args)


if __name__ == '__main__':
    main()
