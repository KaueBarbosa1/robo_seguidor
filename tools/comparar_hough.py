"""Compara HoughLinesP, contornos e CNN em quadros rotulados, offline."""
import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import config as cfg  # noqa: E402
from aprendizado.cnn import RedeLinha  # noqa: E402
from aprendizado.dataset_rotulado import (PREPROCESSAMENTO, Y_RELATIVO, grupo_video,  # noqa: E402
                                          iterar_fotos_revisadas, limites_recorte, posicao_anotada, preparar_foto)
from tools.comparar_sugestoes import painel  # noqa: E402
from tools.treinar_fotos_linha import escrever_csv  # noqa: E402
from visao.detector import DetectorLinha  # noqa: E402
from visao.hough import PARAMETROS, detectar_hough  # noqa: E402

METODOS = ('hough', 'contornos', 'cnn')
CORES = {'hough': (140, 130, 0), 'contornos': (255, 105, 30), 'cnn': (40, 30, 245)}


def reescalar(pixel, origem, destino):
    return (pixel + .5) * destino / origem - .5


def analisar(img, modelo, detector):
    h, w = img.shape[:2]
    y0, y1 = limites_recorte(h, w)
    y_ref = Y_RELATIVO * (h - 1)
    cinza = cv2.cvtColor(img[y0:y1], cv2.COLOR_BGR2GRAY)
    roi = cv2.resize(cinza, (320, 160), interpolation=cv2.INTER_AREA)
    hough = detectar_hough(roi, reescalar(y_ref - y0, y1 - y0, 160))
    # A escala de 160 px aproxima a largura do quadro legado, sem deformar a foto.
    pequena = cv2.resize(img, (160, round(h * 160 / w)), interpolation=cv2.INTER_AREA)
    contorno = detector.processar(pequena)
    posicao_cnn = float(modelo.prever(preparar_foto(img))[0][0])
    if not np.isfinite(posicao_cnn):
        raise ValueError('Previsão não finita no checkpoint CNN')
    xs = {
        'hough': reescalar(hough.central.x, 320, w) if hough.central.x is not None else None,
        'contornos': reescalar(contorno.cx, 160, w) if contorno.achou else None,
        'cnn': (posicao_cnn + 1) * (w - 1) / 2,
    }
    return xs, hough, contorno, (y0, y1), pequena.shape[:2]


def diagnostico(img, rev, alvo, xs, hough, contorno, recorte, tamanho_contorno):
    h, w = img.shape[:2]
    y_ref = round(Y_RELATIVO * (h - 1))
    y0, y1 = recorte
    passo = max(2, round(w / 220))
    copia = img.copy()
    cv2.line(copia, (0, y_ref), (w - 1, y_ref), (70, 175, 205), passo)
    if rev['pontos_px']:
        pontos = np.array(rev['pontos_px'], np.int32)
        cv2.polylines(copia, [pontos], False, (30, 180, 20), passo)
    if alvo is not None:
        cv2.circle(copia, (round(alvo), y_ref), 3 * passo, (30, 180, 20), passo)
    if contorno.achou:
        hc, wc = tamanho_contorno
        pontos = contorno.contorno.astype(float)
        pontos[..., 0] = reescalar(pontos[..., 0], wc, w)
        pontos[..., 1] = reescalar(pontos[..., 1] + contorno.y0, hc, h)
        cv2.drawContours(copia, [pontos.round().astype(np.int32)], 0, CORES['contornos'], passo)
    marcadores = (cv2.MARKER_DIAMOND, cv2.MARKER_TILTED_CROSS, cv2.MARKER_CROSS)
    for (metodo, x), marcador in zip(xs.items(), marcadores):
        if x is not None:
            cv2.drawMarker(copia, (round(x), y_ref), CORES[metodo], marcador, 6 * passo, passo)

    segmentos = cv2.resize(img[y0:y1], (320, 160), interpolation=cv2.INTER_AREA)
    for faixa in hough.faixas:
        y = round(faixa.y)
        cv2.line(segmentos, (0, y), (319, y), (80, 150, 175), 1)
        for i, (x1, a, x2, b) in enumerate(faixa.segmentos):
            if i not in faixa.aceitos:
                cv2.line(segmentos, (x1, a), (x2, b), (100, 100, 100), 1, cv2.LINE_AA)
    for faixa in hough.faixas:
        for i in faixa.aceitos:
            x1, a, x2, b = faixa.segmentos[i]
            cv2.line(segmentos, (x1, a), (x2, b), (255, 220, 0), 2, cv2.LINE_AA)
        if faixa.x is not None:
            cv2.drawMarker(segmentos, (round(faixa.x), round(faixa.y)), (255, 220, 0), cv2.MARKER_DIAMOND, 9)
    nomes = {'par_aceito': 'Par aceito', 'sem_par_compativel': 'Sem par compativel',
             'sem_segmentos': 'Sem segmentos', 'pares_ambiguos': 'Pares ambiguos'}
    etapas = np.full((465, 440, 3), 240, np.uint8)
    canny_bgr = cv2.cvtColor(hough.bordas, cv2.COLOR_GRAY2BGR)
    for i, (etapa, titulo) in enumerate([(canny_bgr, 'Bordas Canny'),
                                         (segmentos, 'Hough a 75%: ' + nomes[hough.central.motivo])]):
        y = 231 * i
        cv2.putText(etapas, titulo, (8, y + 20), cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 0, 0), 1, cv2.LINE_AA)
        etapas[y + 26:y + 232, 8:420] = cv2.resize(etapa, (412, 206), interpolation=cv2.INTER_NEAREST)
    corpo = np.hstack([painel(img, 'Quadro original ' + rev['visibilidade']), etapas,
                       painel(copia, 'Estimativas na altura de 75%')])
    imagem = np.vstack([corpo, np.full((30, corpo.shape[1], 3), 240, np.uint8)])
    for i, (legenda, cor) in enumerate([('Cinza: descartado', (100, 100, 100)), ('Ciano: aceito / Hough', CORES['hough']),
                                       ('Azul: contornos', CORES['contornos']), ('Vermelho: CNN', CORES['cnn']),
                                       ('Verde: rotulo', (30, 130, 20))]):
        cv2.putText(imagem, legenda, (12 + i * (corpo.shape[1] // 5), corpo.shape[0] + 19),
                    cv2.FONT_HERSHEY_SIMPLEX, .48, cor, 1, cv2.LINE_AA)
    return imagem


def resumir(grupo):
    com_alvo = [r for r in grupo if r['alvo'] is not None]
    pareados = [r for r in com_alvo if all(r[m] is not None for m in METODOS)]
    ausentes = [r for r in grupo if r['visibilidade'] == 'ausente']
    ambiguos = [r for r in grupo if r['visibilidade'] == 'ambiguo']

    def mae(linhas, metodo):
        erros = [abs(r[metodo] - r['alvo']) * 100 / (r['largura'] - 1) for r in linhas if r[metodo] is not None]
        return sum(erros) / len(erros) if erros else None

    return {'quadros': len(grupo), 'com_alvo': len(com_alvo), 'pareados': len(pareados),
            'ausentes': len(ausentes), 'ambiguos': len(ambiguos), 'metodos': {
                m: {'sem_estimativa': sum(r[m] is None for r in com_alvo), 'mae_pct_largura': mae(com_alvo, m),
                    'mae_pareado_pct_largura': mae(pareados, m),
                    'estimativa_em_ausente': sum(r[m] is not None for r in ausentes),
                    'estimativa_em_ambiguo': sum(r[m] is not None for r in ambiguos)} for m in METODOS}}


def relatorio(saida, grupos):
    linhas = ['# HoughLinesP, contornos e CNN', '',
              'Posição em y=75% da imagem. Hough usa três faixas e mede a posição na faixa central. '
              'Contornos usa o x do centróide do detector atual. A CNN usa o checkpoint do segundo treino. '
              'A avaliação usa as divisões por vídeo já exploradas para a CNN.', '',
              '| Grupo | Método | Sem estimativa com alvo | MAE condicional | MAE nos mesmos quadros |',
              '|---|---|---:|---:|---:|']

    def pct(v):
        return f'{v:.2f}%' if v is not None else '—'

    for nome, grupo in grupos.items():
        if not grupo['com_alvo']:
            continue
        for m, r in grupo['metodos'].items():
            linhas.append(f"| {nome} | {m} | {r['sem_estimativa']}/{grupo['com_alvo']} | "
                          f"{pct(r['mae_pct_largura'])} | {pct(r['mae_pareado_pct_largura'])} (n={grupo['pareados']}) |")
    linhas += ['', 'MAE condicional usa só as estimativas emitidas pelo próprio método. O MAE pareado '
               'usa os quadros em que os três estimaram posição. Ambos usam porcentagem da largura.', '',
               '| Método | Estimou em quadro ausente | Estimou em quadro ambíguo |', '|---|---:|---:|']
    for m in METODOS:
        contagens = [sum(g['metodos'][m][f'estimativa_em_{k}'] for g in grupos.values()) for k in ('ausente', 'ambiguo')]
        n_aus, n_amb = (sum(g[k] for g in grupos.values()) for k in ('ausentes', 'ambiguos'))
        linhas.append(f'| {m} | {contagens[0]}/{n_aus} | {contagens[1]}/{n_amb} |')
    linhas += ['', 'As ausências servem para contar falsas detecções em cenas rotuladas; os ambíguos '
               'medem emissão de posição sem alvo inequívoco. A CNN retorna posição em todos os quadros. '
               'Amostras ausentes e ambíguas do snapshot pertencem aos vídeos usados no treino da CNN. '
               'O dataset tem poucos desses exemplos e carece de rótulos sistemáticos de rejunte.', '',
               'Consulte `comparacao.json` para estratificação por vídeo e `quadros.csv` para erros e motivos '
               'por imagem. `segmentos.jsonl` registra os pares selecionados e todos os segmentos por faixa.', '']
    (saida / 'RELATORIO.md').write_text('\n'.join(linhas), encoding='utf-8')


def comparar(args):
    experimento = json.loads((args.experimento_cnn / 'experimento.json').read_text(encoding='utf-8'))
    modelo = RedeLinha.carregar(args.experimento_cnn / 'pesos_posicao.npz')
    if (experimento['preprocessamento'] != PREPROCESSAMENTO or experimento['y_relativo'] != Y_RELATIVO
            or experimento['tarefa'] != 'localizacao_horizontal_offline' or modelo.hash() != experimento['hash_pesos']):
        raise ValueError('O experimento CNN deve conter pesos verificados para localização em y=75%')
    args.saida.mkdir(parents=True, exist_ok=False)
    paineis = args.saida / 'diagnosticos'
    paineis.mkdir()
    detector = DetectorLinha()
    linhas = []
    with (args.saida / 'segmentos.jsonl').open('w', encoding='utf-8') as arquivo:
        for meta, revisao, img, _ in iterar_fotos_revisadas(args.dataset, args.revisoes):
            grupo = grupo_video(meta['video_origem'])
            posicao = posicao_anotada(revisao)
            if grupo == 'treino' and revisao['visibilidade'] not in {'ausente', 'ambiguo'}:
                continue
            largura = img.shape[1]
            alvo = (posicao + 1) * (largura - 1) / 2 if posicao is not None else None
            xs, hough, contorno, recorte, tamanho = analisar(img, modelo, detector)
            imagem = meta['imagem']
            linha = {'imagem': imagem, 'grupo': grupo, 'video': meta['video_origem'], 'largura': largura,
                     'visibilidade': revisao['visibilidade'], 'alvo': alvo, **xs, 'hough_motivo': hough.central.motivo}
            linha.update({f'{m}_erro_pct': abs(x - alvo) * 100 / (largura - 1) if x is not None and alvo is not None else None
                          for m, x in xs.items()})
            linhas.append(linha)
            arquivo.write(json.dumps({'imagem': imagem, 'recorte_y': recorte, 'faixas': [asdict(f) for f in hough.faixas]}) + '\n')
            if not cv2.imwrite(str(paineis / imagem), diagnostico(img, revisao, alvo, xs, hough, contorno, recorte, tamanho)):
                raise OSError(f'Falha ao salvar painel de {imagem}')
    if not linhas:
        raise ValueError('Nenhum quadro disponível para a comparação')
    escrever_csv(args.saida / 'quadros.csv', linhas)
    grupos = {g: resumir([r for r in linhas if r['grupo'] == g]) for g in ('treino', 'validacao', 'teste')}
    por_video = {v: resumir([r for r in linhas if r['video'] == v]) for v in sorted({r['video'] for r in linhas})}
    resumo = {'opencv': cv2.__version__, 'parametros_hough': PARAMETROS, 'hash_cnn': modelo.hash(),
              'hash_revisoes': hashlib.sha256(args.revisoes.read_bytes()).hexdigest(),
              'config_contornos': {k: getattr(cfg, k) for k in ('ROI_INICIO', 'BLUR_KERNEL', 'LINHA_ESCURA',
                                                              'USAR_OTSU', 'LIMIAR_FIXO', 'CONTRASTE_MIN', 'AREA_MIN')},
              'grupos': grupos, 'por_video': por_video}
    (args.saida / 'comparacao.json').write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding='utf-8')
    relatorio(args.saida, grupos)
    print(f'Diagnósticos para {len(linhas)} quadros em {args.saida.resolve()}')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    dataset = RAIZ / 'dataset_pista'
    ap.add_argument('--dataset', type=Path, default=dataset)
    ap.add_argument('--revisoes', type=Path, default=dataset / 'rotulos/snapshots/treino_posicao_02.jsonl')
    ap.add_argument('--experimento-cnn', type=Path, default=dataset / 'resultados/treino_posicao_02')
    ap.add_argument('--saida', type=Path, required=True)
    comparar(ap.parse_args())


if __name__ == '__main__':
    main()
