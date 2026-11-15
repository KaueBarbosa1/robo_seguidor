"""Compara regressão MobileNetV2 e RedeLinha em fotos rotuladas, sem hardware."""
import argparse
import hashlib
import json
import os
import platform
import sys
from pathlib import Path
from time import perf_counter_ns

import cv2
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from aprendizado.cnn import RedeLinha  # noqa: E402
from aprendizado.dataset_rotulado import (DIVISAO, PREPROCESSAMENTO as PREP_CNN, Y_RELATIVO,  # noqa: E402
                                          grupo_video, iterar_fotos_revisadas, limites_recorte,
                                          posicao_anotada, preparar_foto)
from aprendizado.mobilenet import (ALPHA, CAMADA_ESPACIAL, ENTRADA, PREPROCESSAMENTO, SHA256_PESOS_IMAGENET,  # noqa: E402
                                    ajustar_regressao, criar_extrator, montar_regressor, preparar_foto_mobilenet)
from tools.comparar_sugestoes import painel  # noqa: E402
from tools.treinar_fotos_linha import escrever_csv, sobrepor_previsao  # noqa: E402

MODELOS = ('cnn', 'mobilenet')


def fotos_posicao(dataset, revisoes):
    for meta, revisao, imagem, arquivo in iterar_fotos_revisadas(dataset, revisoes):
        alvo = posicao_anotada(revisao)
        if alvo is None:
            continue
        y0, y1 = limites_recorte(*imagem.shape[:2])
        yield imagem, {**meta, 'arquivo': arquivo, 'grupo': grupo_video(meta['video_origem']),
                       'pontos_px': revisao['pontos_px'], 'posicao': alvo, 'recorte_y0': y0, 'recorte_y1': y1}


def digest(arquivo):
    return hashlib.sha256(arquivo.read_bytes()).hexdigest()


def carregar_referencia(args):
    pasta = args.experimento_cnn
    manifesto = json.loads((pasta / 'experimento.json').read_text(encoding='utf-8'))
    revisoes = hashlib.sha256(args.revisoes.read_text(encoding='utf-8').encode('utf-8')).hexdigest()
    dados = json.loads((pasta / 'dataset.json').read_text(encoding='utf-8'))
    cnn = RedeLinha.carregar(pasta / 'pesos_posicao.npz')
    if (manifesto['tarefa'] != 'localizacao_horizontal_offline' or manifesto['preprocessamento'] != PREP_CNN
            or manifesto['y_relativo'] != Y_RELATIVO or manifesto['hash_pesos'] != cnn.hash()
            or manifesto['hash_revisoes'] not in (revisoes, digest(args.revisoes))
            or dados['divisao_por_video'] != DIVISAO):
        raise ValueError('A referência deve usar os mesmos rótulos, divisões e alvo em y=75%')
    return cnn, revisoes


def metricas(linhas):
    erros = {m: np.abs([r[f'erro_{m}_pct'] for r in linhas]) for m in MODELOS}
    if not linhas:
        raise ValueError('Conjunto de avaliação vazio')
    return {'n': len(linhas), **{m: {'mae_pct_largura': float(v.mean()), 'pior_pct_largura': float(v.max())}
                               for m, v in erros.items()}}


def renderizar_paineis(args, registros, linhas):
    pasta = args.saida / 'diagnosticos'
    pasta.mkdir()
    for registro, linha in zip(registros, linhas):
        if linha['grupo'] == 'treino':
            continue
        imagem = cv2.imread(str(args.dataset / registro['arquivo']))
        paineis = [painel(sobrepor_previsao(imagem, registro, linha[m]),
                         f'{titulo} | erro {abs(linha[f"erro_{m}_pct"]):.2f}%')
                   for m, titulo in [('cnn', 'CNN NumPy'), ('mobilenet', 'MobileNetV2')]]
        if not cv2.imwrite(str(pasta / linha['imagem']), np.hstack(paineis)):
            raise OSError(f"Falha ao salvar diagnóstico de {linha['imagem']}")


def comparar(args, tf):
    hash_base = digest(args.pesos_base)
    if hash_base != SHA256_PESOS_IMAGENET:
        raise ValueError('O arquivo deve conter os pesos oficiais ImageNet 0.5/128 sem topo')
    cnn, revisoes = carregar_referencia(args)
    entradas_cnn, entradas_mobile, registros = [], [], []
    for imagem, registro in fotos_posicao(args.dataset, args.revisoes):
        entradas_cnn.append(preparar_foto(imagem)[0])
        entradas_mobile.append(preparar_foto_mobilenet(imagem)[0])
        registros.append(registro)
    idx = {g: [i for i, r in enumerate(registros) if r['grupo'] == g] for g in DIVISAO}
    if any(not indices for indices in idx.values()):
        raise ValueError('Cada divisão por vídeo precisa de pelo menos um quadro com posição')
    args.saida.mkdir(parents=True, exist_ok=False)
    alvo = np.array([r['posicao'] for r in registros])
    x_mobile = np.stack(entradas_mobile)
    extrator = criar_extrator(tf.keras, args.pesos_base)
    treino, validacao = idx['treino'], idx['validacao']
    feats_treino = extrator(x_mobile[treino], training=False).numpy()
    feats_val = extrator(x_mobile[validacao], training=False).numpy()
    coef, vies, fator, selecao = ajustar_regressao(feats_treino, alvo[treino], feats_val, alvo[validacao])
    modelo = montar_regressor(tf.keras, extrator, coef, vies)
    caminho = args.saida / 'mobilenet.keras'
    modelo.save(caminho)
    recarregado = tf.keras.models.load_model(caminho, compile=False)
    # Avalia o checkpoint persistido, com um quadro por chamada.
    inferir = inferencia_mobile(tf, recarregado)
    amostra = x_mobile[validacao[:1]]
    np.testing.assert_allclose(inferir(amostra), modelo(amostra, training=False).numpy(), atol=1e-6, rtol=0)
    previsoes = {'cnn': cnn.prever(np.stack(entradas_cnn))[0],
                 'mobilenet': np.array([inferir(x[None])[0, 0] for x in x_mobile])}
    if not all(np.isfinite(p).all() for p in previsoes.values()):
        raise ValueError('Previsão não finita')
    linhas = []
    for i, r in enumerate(registros):
        p = {m: float(v[i]) for m, v in previsoes.items()}
        linhas.append({'imagem': r['imagem'], 'video': r['video_origem'], 'grupo': r['grupo'], 'real': r['posicao'], **p,
                       **{f'erro_{m}_pct': (v - r['posicao']) * 50 for m, v in p.items()}})
    resumo = {g: metricas([linhas[i] for i in indices]) for g, indices in idx.items()}
    por_video = {v: metricas([r for r in linhas if r['video'] == v]) for v in sorted({r['video'] for r in linhas})}
    manifesto = {'preprocessamento': PREPROCESSAMENTO, 'entrada': ENTRADA, 'alpha': ALPHA, 'camada': CAMADA_ESPACIAL,
                 'pre_treino': 'ImageNet', 'sha256_pesos_base': hash_base,
                 'sha256_modelo': digest(caminho), 'hash_cnn': cnn.hash(), 'hash_revisoes_lf': revisoes,
                 'divisao_por_video': DIVISAO, 'parametros_base': extrator.count_params(), 'parametros_saida': int(coef.size + 1),
                 'fator_ridge': fator, 'selecao_por_mse_validacao': selecao, 'tensorflow': tf.__version__,
                 'opencv': cv2.__version__, 'numpy': np.__version__, 'resumo': resumo, 'por_video': por_video}
    (args.saida / 'comparacao.json').write_text(json.dumps(manifesto, indent=2, ensure_ascii=False), encoding='utf-8')
    escrever_csv(args.saida / 'quadros.csv', linhas)
    renderizar_paineis(args, registros, linhas)
    relatorio(args.saida, resumo)
    print(f'Comparação em {args.saida.resolve()}', flush=True)


def relatorio(saida, resumo):
    linhas = ['# MobileNetV2 e CNN NumPy', '',
              'Regressão de posição em y=75% nos mesmos quadros. Os erros absolutos médios são '
              'expressos em porcentagem da largura.', '',
              '| Conjunto | Quadros | CNN NumPy | MobileNetV2 |', '|---|---:|---:|---:|']
    for grupo, r in resumo.items():
        linhas.append(f"| {grupo} | {r['n']} | {r['cnn']['mae_pct_largura']:.2f}% | {r['mobilenet']['mae_pct_largura']:.2f}% |")
    linhas += ['', 'O treinamento ajusta somente a saída linear da MobileNetV2 com ridge. '
               'A regularização foi escolhida pelo menor MSE de validação. A CNN NumPy usa o '
               'checkpoint do segundo treino. Cada rede usa seu próprio tamanho, canais e normalização.', '',
               'Em cada painel, a linha verde é a anotação humana e a cruz vermelha é a previsão. '
               'As imagens de validação e teste foram exploradas anteriormente. Ambas as redes são avaliadas '
               'como regressores de posição. Ainda falta avaliar validade e generalização com sessões novas.', '']
    (saida / 'RELATORIO.md').write_text('\n'.join(linhas), encoding='utf-8')


def inferencia_mobile(tf, modelo):
    assinatura = [tf.TensorSpec((1, *ENTRADA), dtype=tf.float32)]
    funcao = tf.function(lambda x: modelo(x, training=False), input_signature=assinatura)
    return lambda x: funcao(x).numpy()


def medir_latencia(args, tf):
    cnn, revisoes = carregar_referencia(args)
    pasta = args.experimento_mobilenet
    manifesto = json.loads((pasta / 'comparacao.json').read_text(encoding='utf-8'))
    caminho = pasta / 'mobilenet.keras'
    if (manifesto['preprocessamento'] != PREPROCESSAMENTO or manifesto['sha256_modelo'] != digest(caminho)
            or manifesto['hash_cnn'] != cnn.hash() or manifesto['hash_revisoes_lf'] != revisoes):
        raise ValueError('Modelo MobileNetV2 ou pré-processamento incompatível com o manifesto')
    mobile = tf.keras.models.load_model(caminho, compile=False)
    imagens = [img for img, r in fotos_posicao(args.dataset, args.revisoes) if r['grupo'] != 'treino']
    if not imagens:
        raise ValueError('Nenhum quadro de validação ou teste para medir')
    pipelines = {'cnn': (preparar_foto, cnn.prever), 'mobilenet': (preparar_foto_mobilenet, inferencia_mobile(tf, mobile))}
    linhas = []
    for nome, (preparar, inferir) in pipelines.items():
        for i in range(5):
            inferir(preparar(imagens[i % len(imagens)]))
        for repeticao in range(args.repeticoes):
            for i, imagem in enumerate(imagens):
                inicio = perf_counter_ns()
                entrada = preparar(imagem)
                pronto = perf_counter_ns()
                inferir(entrada)
                fim = perf_counter_ns()
                linhas.append({'modelo': nome, 'repeticao': repeticao + 1, 'quadro': i + 1,
                               'pre_ms': (pronto - inicio) / 1e6, 'inferencia_ms': (fim - pronto) / 1e6,
                               'total_ms': (fim - inicio) / 1e6})
    resumo = {}
    for nome in MODELOS:
        medidas = [r for r in linhas if r['modelo'] == nome]
        resumo[nome] = {k: dict(zip(('p50', 'p95'), np.percentile([r[k] for r in medidas], [50, 95]).tolist()))
                        for k in ('pre_ms', 'inferencia_ms', 'total_ms')}
    args.saida.mkdir(parents=True, exist_ok=False)
    escrever_csv(args.saida / 'latencia.csv', linhas)
    dados = {'host': platform.platform(), 'arquitetura': platform.machine(), 'tensorflow': tf.__version__,
             'threads_tensorflow': args.threads, 'OPENBLAS_NUM_THREADS': os.environ.get('OPENBLAS_NUM_THREADS'),
             'quadros': len(imagens), 'repeticoes': args.repeticoes,
             'aquecimento': 5, 'lote': 1, 'inclui_decodificacao': False, 'ms': resumo}
    (args.saida / 'latencia.json').write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(dados, indent=2, ensure_ascii=False), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    comandos = ap.add_subparsers(dest='comando', required=True)
    treino = comandos.add_parser('comparar', help='ajusta a regressão e compara previsões')
    treino.add_argument('--pesos-base', type=Path, required=True, help='pesos oficiais ImageNet alpha 0.5, 128, sem topo')
    medir = comandos.add_parser('latencia', help='mede o caminho de cada quadro em CPU')
    medir.add_argument('--experimento-mobilenet', type=Path, required=True)
    medir.add_argument('--repeticoes', type=int, default=5)
    dataset = RAIZ / 'dataset_pista'
    for comando in (treino, medir):
        comando.add_argument('--dataset', type=Path, default=dataset)
        comando.add_argument('--revisoes', type=Path, default=dataset / 'rotulos/snapshots/treino_posicao_02.jsonl')
        comando.add_argument('--experimento-cnn', type=Path, default=dataset / 'resultados/treino_posicao_02')
        comando.add_argument('--saida', type=Path, required=True)
        comando.add_argument('--threads', type=int, default=1, help='threads intra-op do TensorFlow')
    args = ap.parse_args()
    if args.threads < 1 or getattr(args, 'repeticoes', 1) < 1 or args.saida.exists():
        ap.error('use números positivos e uma pasta de saída nova')
    try:
        import tensorflow as tf
    except ImportError:
        ap.error('este ensaio offline requer TensorFlow com Keras 3')
    tf.config.set_visible_devices([], 'GPU')
    tf.config.threading.set_inter_op_parallelism_threads(1)
    tf.config.threading.set_intra_op_parallelism_threads(args.threads)
    if args.comando == 'comparar':
        comparar(args, tf)
    else:
        medir_latencia(args, tf)


if __name__ == '__main__':
    main()
