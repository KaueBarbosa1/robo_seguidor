"""Compara sugestões de rotulagem em marcações de treino/validação, sem treinar.

Na Raspberry Pi com a .venv: python tools/comparar_sugestoes.py
--anterior aceita o fonte Python anterior deste projeto para comparação histórica.
"""
import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import cv2
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from aprendizado.dataset_rotulado import DIVISAO  # noqa: E402
from tools.rotular_linha import referencia_anterior  # noqa: E402
from visao.sugestao import preparar_imagem, sugerir_linha  # noqa: E402


def medir(revisao, pontos):
    """Erro somente na interseção das extensões, acompanhado da cobertura."""
    humanos = np.array(revisao['pontos_px'], float)
    ys = np.linspace(humanos[0, 1], humanos[-1, 1], 25)
    xs = np.interp(ys, humanos[:, 1], humanos[:, 0])
    validos = np.zeros(25, bool)
    erros = np.zeros(25)
    if pontos:
        p = np.array(pontos, float)
        validos = (ys >= p[0, 1]) & (ys <= p[-1, 1])
        erros[validos] = abs(np.interp(ys[validos], p[:, 1], p[:, 0]) - xs[validos]) * 2 / (int(revisao['largura']) - 1)
    return {'cobertura': float(validos.mean()),
            'mae': float(erros[validos].mean()) if validos.any() else None,
            'validos': validos.tolist(), 'erros': erros.tolist()}


def painel(img, titulo):
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    h, w = img.shape[:2]
    fator = min(240 / w, 427 / h)
    p = cv2.resize(img, (round(w * fator), round(h * fator)), interpolation=cv2.INTER_AREA)
    canvas = np.full((465, 250, 3), 240, np.uint8)
    canvas[30:30 + p.shape[0], :p.shape[1]] = p
    cv2.putText(canvas, titulo, (4, 20), cv2.FONT_HERSHEY_SIMPLEX, .43, (0, 0, 0), 1)
    return canvas


def sobrepor(img, humanos, pontos):
    vis = img.copy()
    h, w = vis.shape[:2]
    for pts, cor in [(humanos, (0, 180, 0)), (pontos, (0, 0, 255))]:
        p = np.array([[round(x * w), round(y * h)] for x, y in pts], np.int32)
        if len(p) > 1:
            cv2.polylines(vis, [p], False, cor, 2)
        for xy in p:
            cv2.circle(vis, tuple(xy), 3, cor, -1)
    return vis


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dataset', type=Path, default=RAIZ / 'dataset_pista')
    ap.add_argument('--revisoes', type=Path, default=RAIZ / 'dataset_pista/rotulos/revisoes.jsonl')
    ap.add_argument('--saida', type=Path, default=RAIZ / 'dataset_pista/resultados/preprocessamento_01')
    ap.add_argument('--anterior', type=Path)
    a = ap.parse_args()
    original = a.revisoes.read_bytes()
    rev = {r['imagem']: r for r in (json.loads(linha) for linha in original.decode('utf-8').splitlines())}
    estrategias = {'sem_correcao': lambda img, ref: sugerir_linha(img, ref, preprocessamento='legado'),
                   'normalizado': lambda img, ref: sugerir_linha(img, ref, preprocessamento='normalizado'),
                   'clahe': lambda img, ref: sugerir_linha(img, ref, preprocessamento='clahe')}
    if a.anterior:
        spec = importlib.util.spec_from_file_location('sugestao_anterior_auditoria', a.anterior)
        modulo = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = modulo
        spec.loader.exec_module(modulo)
        estrategias = {'anterior': modulo.sugerir_linha, **estrategias}
    a.saida.mkdir(parents=True, exist_ok=False)
    (a.saida / 'diagnosticos').mkdir()
    (a.saida / 'revisoes_snapshot.jsonl').write_bytes(original)
    for fonte in [RAIZ / 'visao/sugestao.py', Path(__file__)] + ([a.anterior] if a.anterior else []):
        (a.saida / ('fonte_' + fonte.name)).write_bytes(fonte.read_bytes())
    arquivos = {p.name: p for p in (a.dataset / 'imagens').rglob('*.jpg')}
    resultados = []
    # Evita ajustar a assistência com os vídeos reservados ao teste da CNN.
    for r in rev.values():
        if r['video_origem'] not in DIVISAO['treino'] + DIVISAO['validacao'] or r['visibilidade'] not in {'visivel', 'parcial'}:
            continue
        bruto = arquivos[r['imagem']].read_bytes()
        if hashlib.sha256(bruto).hexdigest() != r['sha256']:
            raise ValueError(f'Hash divergente: {r["imagem"]}')
        img = cv2.imdecode(np.frombuffer(bruto, np.uint8), cv2.IMREAD_COLOR)
        h, w = img.shape[:2]
        ref = referencia_anterior(r, rev)
        pontos_ref = ref['pontos_px'] if ref else None
        saidas = {nome: fn(img, pontos_ref) for nome, fn in estrategias.items()}
        med = {nome: {**medir(r, s.pontos), 'pontos': s.pontos, 'metodo': s.metodo} for nome, s in saidas.items()}
        resultados.append({'imagem': r['imagem'], 'video_origem': r['video_origem'], 'comparacoes': med})
        pequena, tratada = preparar_imagem(img, 'normalizado')
        humanos = [[x / w, y / h] for x, y in r['pontos_px']]
        nome_base = 'anterior' if 'anterior' in saidas else 'sem_correcao'
        paineis = [painel(sobrepor(pequena, humanos, []), 'Marcacao humana: verde')]
        for nome, titulo in [(nome_base, 'Antes: sugestao vermelha'), ('normalizado', 'Depois: sugestao vermelha')]:
            pontos = [[x / w, y / h] for x, y in saidas[nome].pontos]
            paineis.append(painel(sobrepor(pequena, humanos, pontos), titulo))
        paineis.append(painel(tratada, 'Iluminacao corrigida'))
        s = saidas['normalizado']
        mascara = np.zeros_like(tratada)
        if s.metodo:
            limiar = int(s.metodo.split('_limiar_')[1].split('_')[0])
            _, mascara = cv2.threshold(cv2.GaussianBlur(tratada, (3, 3), 0), limiar, 255, cv2.THRESH_BINARY_INV)
            mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        paineis.append(painel(mascara, 'Mascara selecionada'))
        if not cv2.imwrite(str(a.saida / 'diagnosticos' / r['imagem']), np.hstack(paineis)):
            raise OSError('Falha ao salvar diagnóstico')
    resumo = {}
    for nome in estrategias:
        medias = [r['comparacoes'][nome]['mae'] for r in resultados if r['comparacoes'][nome]['mae'] is not None]
        resumo[nome] = {'frames_comparaveis': len(medias), 'mae_condicional_por_frame': float(np.mean(medias)),
                        'cobertura_media_25_alturas': float(np.mean([r['comparacoes'][nome]['cobertura'] for r in resultados])),
                        'frames_mae_acima_02': sum(v > .2 for v in medias)}
    base = 'anterior' if 'anterior' in estrategias else 'sem_correcao'
    pares = {base: [], 'normalizado': []}
    for r in resultados:
        med = r['comparacoes']
        validos = np.array(med[base]['validos']) & np.array(med['normalizado']['validos'])
        if validos.any():
            for nome in pares:
                pares[nome].append(float(np.array(med[nome]['erros'])[validos].mean()))
    comparacao_pareada = {'frames': len(pares[base]), 'mae_mesmas_alturas_por_frame':
                          {nome: float(np.mean(v)) for nome, v in pares.items()}}
    manifesto = {'rotulos_gerados': False, 'treino_cnn_executado': False,
                 'hash_revisoes': hashlib.sha256(original).hexdigest(), 'n': len(resultados),
                 'resumo': resumo, 'comparacao_pareada': comparacao_pareada, 'resultados': resultados,
                 'limites': ['Comparação exploratória em revisões de treino/validação; não é teste independente.',
                             'Parte das revisões teve auxílio OpenCV; não são anotações cegas ao algoritmo.',
                             'MAE é normalizado; 0.1 equivale a 5% da largura. Não é acurácia.',
                             'Erro calculado só onde as extensões se sobrepõem; consultar cobertura.']}
    (a.saida / 'comparacao.json').write_text(json.dumps(manifesto, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'n': len(resultados), 'resumo': resumo, 'pareada': comparacao_pareada}, indent=2), flush=True)
    print('Diagnósticos em', a.saida)


if __name__ == '__main__':
    main()
