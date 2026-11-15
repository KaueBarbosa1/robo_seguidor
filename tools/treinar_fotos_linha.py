"""Experimento offline de posição com RedeLinha e anotações humanas.

Não treina visibilidade, não ativa modelos no robô e não acessa motores.
Raspberry Pi, .venv: OPENBLAS_NUM_THREADS=1 .venv/bin/python tools/treinar_fotos_linha.py
"""
import argparse
import csv
import hashlib
import json
import platform
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from aprendizado.cnn import Adam, RedeLinha  # noqa: E402
from aprendizado.dados import aumentar, normalizar  # noqa: E402
from aprendizado.dataset_rotulado import (DIVISAO, PREPROCESSAMENTO, Y_RELATIVO,  # noqa: E402
                                          carregar_fotos, preparar_foto)


def metricas(alvo, previsao):
    if not len(alvo):
        raise ValueError('Conjunto vazio na avaliação')
    erro = np.asarray(previsao) - np.asarray(alvo)
    return {'n': len(alvo), 'mae': float(np.abs(erro).mean()), 'mse': float((erro ** 2).mean()),
            'erro_absoluto_max': float(np.abs(erro).max()),
            'erro_absoluto_mediano': float(np.median(np.abs(erro))),
            'mae_pixels_entrada80': float(np.abs(erro).mean() * 79 / 2)}


def escrever_csv(caminho, linhas):
    with caminho.open('w', encoding='utf-8', newline='') as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(linhas[0]))
        escritor.writeheader()
        escritor.writerows(linhas)


def preparar_dados(dataset, revisoes):
    # A divisão é fixada antes de ajustar pesos ou avaliar previsões.
    videos = [v for lista in DIVISAO.values() for v in lista]
    if len(videos) != len(set(videos)):
        raise ValueError('Vazamento de vídeos entre conjuntos')
    reduzidos, y, registros, excluidos = carregar_fotos(dataset, revisoes)
    idx = {grupo: np.array([i for i, r in enumerate(registros) if r['grupo'] == grupo]) for grupo in DIVISAO}
    if any(len(v) == 0 for v in idx.values()):
        raise ValueError('Cada conjunto precisa ter ao menos um exemplo')
    auditoria = {'revisoes_unicas': len(registros) + len(excluidos),
                 'visibilidade_incluidos': dict(Counter(r['visibilidade'] for r in registros)),
                 'incluidos': registros, 'excluidos': excluidos,
                 'divisao_por_video': DIVISAO,
                 'contagens': {g: len(i) for g, i in idx.items()}}
    return reduzidos, y, idx, auditoria


def ajustar_posicao(x, y, idx, args):
    rng = np.random.default_rng(args.semente)
    rede = RedeLinha(args.semente, batchnorm=args.batchnorm)
    opt = Adam(rede, lr=args.lr)
    melhor, melhor_mse, melhor_passo = None, float('inf'), None
    historico = []
    for passo in range(1, args.passos + 1):
        lote = rng.choice(idx['treino'], size=min(args.lote, len(idx['treino'])), replace=False)
        entrada, alvo = aumentar(x[lote], y[lote], rng)
        perda, _ = rede.perda_e_gradiente(entrada, alvo, np.ones(len(lote), bool),
                                         np.zeros(len(lote), np.float32), np.ones(len(lote), np.float32),
                                         # Pendente: supervisionar validade e três alturas com máscaras;
                                         # não usar a visibilidade destes pesos para autorizar movimento.
                                         # Plano: docs/13_contexto_e_plano_cnn.md.
                                         lambda_vis=0.)
        if not np.isfinite(perda):
            raise ValueError('Perda não finita; experimento interrompido')
        opt.passo()
        if passo % args.avaliar_cada == 0 or passo == args.passos:
            pred_tr, _ = rede.prever(x[idx['treino']])
            pred_val, _ = rede.prever(x[idx['validacao']])
            mt = metricas(y[idx['treino']], pred_tr)
            mv = metricas(y[idx['validacao']], pred_val)
            historico.append({'passo': passo, 'perda_lote': perda,
                              'mse_treino': mt['mse'], 'mse_validacao': mv['mse'],
                              'mae_treino': mt['mae'], 'mae_validacao': mv['mae']})
            if mv['mse'] < melhor_mse:
                melhor, melhor_mse, melhor_passo = rede.copiar(), mv['mse'], passo
            print(f'passo {passo}: MAE treino={mt["mae"]:.4f}, validação={mv["mae"]:.4f}', flush=True)
    return melhor, melhor_passo, historico


def executar(args):
    if args.saida.resolve().exists():
        raise ValueError('A pasta de saída já existe; escolha uma nova execução')
    reduzidos, y, idx, auditoria = preparar_dados(args.dataset, args.revisoes)
    registros = auditoria['incluidos']
    x = normalizar(reduzidos)
    saida = args.saida.resolve()
    saida.mkdir(parents=True, exist_ok=False)
    (saida / 'previsoes').mkdir()
    (saida / 'dataset.json').write_text(json.dumps(auditoria, indent=2, ensure_ascii=False), encoding='utf-8')
    np.savez_compressed(saida / 'dados.npz', reduzidos=reduzidos, posicao=y,
                        **{g: i for g, i in idx.items()})
    inicio = time.monotonic()
    print('Divisão:', auditoria['contagens'], '| excluídos:', len(auditoria['excluidos']), flush=True)
    melhor, melhor_passo, historico = ajustar_posicao(x, y, idx, args)
    melhor.salvar(saida / 'pesos_posicao.npz')
    # Recarrega o checkpoint para avaliar o mesmo arquivo que foi persistido.
    modelo = RedeLinha.carregar(saida / 'pesos_posicao.npz')
    assert modelo.hash() == melhor.hash()
    media_treino = float(np.mean(y[idx['treino']]))
    resultados = {}
    linhas = []
    for grupo, indices in idx.items():
        # O teste é avaliado apenas aqui, após selecionar o checkpoint por validação.
        previsao, _ = modelo.prever(x[indices])
        if not np.isfinite(previsao).all():
            raise ValueError('Previsão não finita')
        resultados[grupo] = {'cnn': metricas(y[indices], previsao),
                             'sempre_centro': metricas(y[indices], np.zeros(len(indices))),
                             'media_treino': metricas(y[indices], np.full(len(indices), media_treino)),
                             'por_video': {}}
        for video in sorted({registros[i]['video_origem'] for i in indices}):
            mask = np.array([registros[i]['video_origem'] == video for i in indices])
            resultados[grupo]['por_video'][video] = metricas(y[indices][mask], previsao[mask])
        for i, pred in zip(indices, previsao):
            r = registros[i]
            linhas.append({k: r[k] for k in ['imagem', 'video_origem', 'timestamp', 'grupo']})
            linhas[-1].update(real=float(y[i]), previsto=float(pred), erro=float(pred - y[i]))
            original = cv2.imread(str(args.dataset / r['arquivo']))
            # Verifica o caminho de inferência compartilhado, sem pré-processamento alternativo.
            np.testing.assert_array_equal(preparar_foto(original), x[i:i + 1])
            desenhar_previsao(original, r, float(pred), saida / 'previsoes' / r['imagem'])
    escrever_csv(saida / 'historico.csv', historico)
    escrever_csv(saida / 'predicoes.csv', linhas)
    manifesto = {'tarefa': 'localizacao_horizontal_offline', 'preprocessamento': PREPROCESSAMENTO,
                 'batchnorm': args.batchnorm,
                 'y_relativo': Y_RELATIVO, 'entrada': [1, 40, 80],
                 'alvo': '2*x/(largura_original-1)-1, positivo para direita; sem ganho de controle',
                 'visibilidade_treinada': False, 'lambda_vis': 0., 'uso_no_robo_aprovado': False,
                 'parametros': {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
                 'melhor_passo': melhor_passo, 'criterio_checkpoint': 'menor MSE de validacao',
                 'hash_pesos': modelo.hash(), 'baseline_media_treino': media_treino,
                 'criado_utc': datetime.now(timezone.utc).isoformat(),
                 'tempo_treino_e_avaliacao_s': time.monotonic() - inicio,
                 'python': platform.python_version(), 'numpy': np.__version__, 'opencv': cv2.__version__,
                 'hash_fontes': {str(p.relative_to(RAIZ)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in [Path(__file__), RAIZ / 'aprendizado/dataset_rotulado.py',
                                           RAIZ / 'aprendizado/cnn.py', RAIZ / 'aprendizado/dados.py']},
                 'hash_revisoes': hashlib.sha256(args.revisoes.read_bytes()).hexdigest(),
                 'hash_metadados': hashlib.sha256((args.dataset / 'metadados.csv').read_bytes()).hexdigest(),
                 'metricas': resultados,
                 'limites': [f'{len(registros)} fotos utilizáveis; conjunto pequeno no experimento inicial',
                             'vídeos do mesmo ambiente e amostras já inspecionadas na exploração',
                             'sem validação de visibilidade/ausência ou ESP32-CAM',
                             'pesos não compatíveis semanticamente com controle atual']}
    (saida / 'experimento.json').write_text(json.dumps(manifesto, indent=2, ensure_ascii=False), encoding='utf-8')
    (saida / 'RELATORIO.md').write_text(relatorio(manifesto, auditoria), encoding='utf-8')
    print(json.dumps(resultados, indent=2, ensure_ascii=False))
    print('Artefatos:', saida, flush=True)


def sobrepor_previsao(imagem, registro, previsto):
    h, w = imagem.shape[:2]
    pequena = cv2.resize(imagem, (360, round(360 * h / w)), interpolation=cv2.INTER_AREA)
    sh, sw = pequena.shape[:2]
    pts = np.array([[round(x * sw / w), round(y * sh / h)] for x, y in registro['pontos_px']], np.int32)
    cv2.polylines(pequena, [pts], False, (0, 200, 0), 2)
    for yy in [registro['recorte_y0'], registro['recorte_y1']]:
        cv2.line(pequena, (0, round(yy * sh / h)), (sw - 1, round(yy * sh / h)), (0, 180, 180), 1)
    py = round(Y_RELATIVO * (h - 1) * sh / h)
    rx = round((registro['posicao'] + 1) * (w - 1) / 2 * sw / w)
    px = round((previsto + 1) * (w - 1) / 2 * sw / w)
    cv2.line(pequena, (sw // 2, 0), (sw // 2, sh - 1), (255, 0, 0), 1)
    cv2.circle(pequena, (rx, py), 6, (0, 200, 0), 2)
    cv2.drawMarker(pequena, (px, py), (0, 0, 255), cv2.MARKER_CROSS, 16, 2)
    cv2.putText(pequena, registro['grupo'], (5, 18), cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 0, 255), 1)
    cv2.putText(pequena, f'real={registro["posicao"]:+.2f} CNN={previsto:+.2f}',
                (5, 38), cv2.FONT_HERSHEY_SIMPLEX, .45, (0, 0, 255), 1)
    return pequena


def desenhar_previsao(imagem, registro, previsto, destino):
    if not cv2.imwrite(str(destino), sobrepor_previsao(imagem, registro, previsto)):
        raise OSError(f'Falha ao salvar {destino}')


def relatorio(manifesto, auditoria):
    arquitetura = ('RedeLinha com BatchNorm nas três convoluções' if manifesto['batchnorm']
                   else 'RedeLinha original')
    texto = ['# Experimento offline de localização\n',
             f"{auditoria['revisoes_unicas']} imagens revisadas; {len(auditoria['incluidos'])} usadas; "
             f"{len(auditoria['excluidos'])} excluídas. Divisão: {auditoria['contagens']}.\n",
             f'{arquitetura}. Cabeça 0 aprende posição em y=75%, '
             'não comando de motor. Cabeça de visibilidade não supervisionada (lambda=0); ignorar sua saída.\n',
             'Recorte 2:1 na largura inteira centrado em y=75%, cinza 40×80, normalização compartilhada '
             'com aprendizado/dados.py. Interpolação somente dentro dos pontos humanos, sem extrapolação. '
             'Parciais com pontos cobrindo a referência podem treinar posição; isso não cria rótulos de visibilidade.\n',
             f"Melhor checkpoint no passo {manifesto['melhor_passo']}, por MSE de validação. "
             'Teste avaliado só após seleção. Augmentation: espelho com troca de sinal e ruído da função existente.\n',
             '| Conjunto | N | MAE CNN | MAE centro | MAE média treino | MSE CNN |\n',
             '|---|---:|---:|---:|---:|---:|\n']
    for g, m in manifesto['metricas'].items():
        texto.append(f"| {g} | {m['cnn']['n']} | {m['cnn']['mae']:.4f} | "
                     f"{m['sempre_centro']['mae']:.4f} | {m['media_treino']['mae']:.4f} | {m['cnn']['mse']:.4f} |\n")
    texto.extend(['\nMAE é erro normalizado na largura: erro 0,1 equivale a 5% da largura. '
                  'Não é porcentagem de acerto. Ver experimento.json para métricas por vídeo.\n',
                  '\nVerde: marcação humana; cruz vermelha: CNN; azul: centro; amarelo: limites do recorte. '
                  'Predições em previsoes/; valores por imagem em predicoes.csv; curva numérica em historico.csv.\n',
                  '\nOs vídeos já foram inspecionados durante a exploração; o teste é separado por vídeo, '
                  'mas não é uma avaliação final intocada nem prova generalização para outro ambiente. '
                  'Poucos exemplos e nenhuma ausência anotada: não avaliar precisão/recall de visibilidade. '
                  'Coletar mais rótulos e gravações independentes antes de concluir confiabilidade.\n',
                  '\nPesos em pesos_posicao.npz são apenas deste experimento: não foram registrados como '
                  'campeão nem carregados no robô. Firmware, sensores, Bluetooth e configuração preservados.\n'])
    return ''.join(texto)


def argumentos_treino(ap):
    ap.add_argument('--dataset', type=Path, default=RAIZ / 'dataset_pista')
    ap.add_argument('--revisoes', type=Path, default=RAIZ / 'dataset_pista/rotulos/revisoes.jsonl')
    ap.add_argument('--passos', type=int, default=300)
    ap.add_argument('--lote', type=int, default=8)
    ap.add_argument('--lr', type=float, default=0.001)
    ap.add_argument('--avaliar-cada', type=int, default=10)


def validar_treino(ap, args):
    if min(args.passos, args.lote, args.avaliar_cada) < 1 or not np.isfinite(args.lr) or args.lr <= 0:
        ap.error('passos/lote/avaliar-cada/lr devem ser positivos e finitos')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    argumentos_treino(ap)
    ap.add_argument('--saida', type=Path, default=RAIZ / 'dataset_pista/resultados/treino_posicao_01')
    ap.add_argument('--semente', type=int, default=7)
    ap.add_argument('--batchnorm', action='store_true', help='normaliza as três convoluções')
    a = ap.parse_args()
    validar_treino(ap, a)
    executar(a)


if __name__ == '__main__':
    main()
