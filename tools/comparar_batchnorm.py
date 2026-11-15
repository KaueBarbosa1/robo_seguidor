"""Compara as CNNs de posição com e sem BatchNorm, offline e por semente.

Usa treino e validação por vídeo. A avaliação final requer gravações novas.
Requer matplotlib para exportar as curvas e os mapas de ativação.
"""
import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import matplotlib
import numpy as np
from matplotlib.figure import Figure

matplotlib.use('Agg')
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from aprendizado.cnn import RedeLinha  # noqa: E402
from aprendizado.dados import normalizar  # noqa: E402
from aprendizado.dataset_rotulado import PREPROCESSAMENTO  # noqa: E402
from tools.treinar_fotos_linha import (ajustar_posicao, argumentos_treino, escrever_csv, metricas,  # noqa: E402
                                       preparar_dados, sobrepor_previsao, validar_treino)

VARIANTES = ('Sem BatchNorm', 'Com BatchNorm')


@dataclass
class Execucao:
    modelo: RedeLinha
    historico: list[dict]
    previsoes: np.ndarray
    resumo: dict


def comparar(args):
    reduzidos, y, idx, auditoria = preparar_dados(args.dataset, args.revisoes)
    x = normalizar(reduzidos)
    registros = auditoria['incluidos']
    indices_val = idx['validacao']
    videos = np.array([registros[i]['video_origem'] for i in indices_val])
    args.saida.mkdir(parents=True, exist_ok=False)
    execucoes = {variante: [] for variante in VARIANTES}
    for semente in args.sementes:
        for batchnorm, variante in enumerate(VARIANTES):
            print(f'\n{variante} | semente {semente}', flush=True)
            opcoes = argparse.Namespace(**vars(args), semente=semente, batchnorm=bool(batchnorm))
            modelo, passo, historico = ajustar_posicao(x, y, idx, opcoes)
            pasta = args.saida / f'semente_{semente}' / ('com_batchnorm' if batchnorm else 'sem_batchnorm')
            pasta.mkdir(parents=True)
            pesos = pasta / 'pesos_posicao.npz'
            modelo.salvar(pesos)
            recarregado = RedeLinha.carregar(pesos)
            np.testing.assert_array_equal(recarregado.prever(x[indices_val])[0], modelo.prever(x[indices_val])[0])
            pred, _ = recarregado.prever(x[indices_val])
            pred_treino, _ = recarregado.prever(x[idx['treino']])
            erro = pred - y[indices_val]
            resumo = {'semente': semente, 'variante': variante, 'checkpoint': passo, 'hash': recarregado.hash(),
                      'treino': metricas(y[idx['treino']], pred_treino), 'validacao': metricas(y[indices_val], pred),
                      'por_video': {v: metricas(y[indices_val][videos == v], pred[videos == v])
                                    for v in sorted(set(videos))}}
            escrever_csv(pasta / 'historico.csv', historico)
            escrever_csv(pasta / 'validacao.csv', [
                {'imagem': registros[i]['imagem'], 'video': video, 'real': alvo, 'previsto': p, 'erro': e}
                for i, video, alvo, p, e in zip(indices_val, videos, y[indices_val], pred, erro)
            ])
            execucoes[variante].append(Execucao(recarregado, historico, pred, resumo))

    resumo = {'preprocessamento': PREPROCESSAMENTO, 'lambda_vis': 0, 'uso_no_robo_aprovado': False,
              'criterio_checkpoint': 'menor MSE de validação', 'divisao_por_video': auditoria['divisao_por_video'],
              'contagens': auditoria['contagens'], 'seed_paineis': args.sementes[0],
              'parametros': {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
              'sha256_revisoes': hashlib.sha256(args.revisoes.read_bytes()).hexdigest(),
              'execucoes': [e.resumo for grupo in execucoes.values() for e in grupo]}
    (args.saida / 'comparacao.json').write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding='utf-8')
    escrever_relatorio(args.saida, execucoes, auditoria['contagens'])
    desenhar_curvas(args.saida, execucoes)
    escolhidas = [grupo[0] for grupo in execucoes.values()]
    media_erros = np.abs(np.array([e.previsoes for e in escolhidas]) - y[indices_val]).mean(axis=0)
    for nome, pos in [('menor_erro', media_erros.argmin()), ('maior_erro', media_erros.argmax())]:
        i = indices_val[pos]
        registro = registros[i]
        original = cv2.imread(str(args.dataset / registro['arquivo']))
        desenhar_painel(args.saida / f'{nome}.png', original, registro, x[i:i + 1], escolhidas, pos)
    print(f'\nResultados em {args.saida.resolve()}', flush=True)


def escrever_relatorio(saida, execucoes, contagens):
    linhas = ['# Comparação offline de BatchNorm', '',
              f"Treino com {contagens['treino']} imagens e validação com {contagens['validacao']} imagens "
              'separadas por vídeo. A comparação usa a mesma entrada, posição a 75% da altura, '
              'inicialização e sequência de lotes dentro de cada par de sementes.', '',
              '| Semente | Variante | Passo | MAE treino | MAE validação | Diferença val. − treino |',
              '|---:|---|---:|---:|---:|---:|']
    for variante, grupo in execucoes.items():
        for e in grupo:
            treino = e.resumo['treino']['mae'] * 50
            val = e.resumo['validacao']['mae'] * 50
            linhas.append(f"| {e.resumo['semente']} | {variante} | {e.resumo['checkpoint']} | "
                          f'{treino:.2f}% | {val:.2f}% | {val - treino:+.2f} p.p. |')
    linhas += ['', '| Variante | MAE médio de validação | Desvio entre sementes |', '|---|---:|---:|']
    for variante, grupo in execucoes.items():
        valores = np.array([e.resumo['validacao']['mae'] * 50 for e in grupo])
        linhas.append(f'| {variante} | {valores.mean():.2f}% | {valores.std():.2f} p.p. |')
    linhas += ['', 'O MAE usa porcentagem da largura da imagem. As métricas por vídeo estão em `comparacao.json`. '
               'Os painéis comparam as mesmas duas imagens de validação na primeira semente, selecionadas '
               'pelo menor e maior erro absoluto médio do par.', '',
               'Resultados exploratórios com poucos vídeos do mesmo ambiente. A comparação usa treino e '
               'validação. Ainda falta teste independente com a câmera montada. Os pesos estimam posição '
               'offline, com a saída de visibilidade sem supervisão.', '']
    (saida / 'RELATORIO.md').write_text('\n'.join(linhas), encoding='utf-8')


def desenhar_curvas(saida, execucoes):
    fig = Figure(figsize=(10, 5), layout='constrained')
    eixos = fig.subplots(1, 2, sharey=True)
    for eixo, conjunto in zip(eixos, ('treino', 'validacao')):
        for (variante, grupo), cor in zip(execucoes.items(), ('#475569', '#007a69')):
            passos = [r['passo'] for r in grupo[0].historico]
            valores = np.array([[r[f'mae_{conjunto}'] * 50 for r in e.historico] for e in grupo])
            media, desvio = valores.mean(axis=0), valores.std(axis=0)
            eixo.plot(passos, media, color=cor, label=variante)
            eixo.fill_between(passos, np.maximum(0, media - desvio), media + desvio, color=cor, alpha=.15)
        eixo.set(title={'treino': 'Treino', 'validacao': 'Validação'}[conjunto], xlabel='Atualização dos pesos')
        eixo.grid(alpha=.2)
    eixos[0].set_ylabel('Erro absoluto médio (% da largura)')
    eixos[1].legend(frameon=False)
    fig.suptitle('CNN de posição · média e desvio-padrão entre sementes')
    fig.savefig(saida / 'curvas.png', dpi=160)


def desenhar_painel(destino, original, registro, entrada, execucoes, pos):
    fig = Figure(figsize=(14, 7), layout='constrained')
    grade = fig.add_gridspec(3, 1, height_ratios=[2, 1, 1])
    imagens = grade[0].subgridspec(1, 4)
    eixo = fig.add_subplot(imagens[0, 0])
    eixo.imshow(cv2.cvtColor(original, cv2.COLOR_BGR2RGB))
    eixo.set_title('Quadro original')
    eixo.axis('off')
    eixo = fig.add_subplot(imagens[0, 1])
    eixo.imshow(entrada[0, 0], cmap='gray', vmin=-4, vmax=4, interpolation='nearest')
    eixo.set_title('Entrada normalizada · 80 × 40')
    eixo.axis('off')
    for linha, (variante, e) in enumerate(zip(VARIANTES, execucoes)):
        overlay = sobrepor_previsao(original, registro, e.previsoes[pos])
        eixo = fig.add_subplot(imagens[0, linha + 2])
        eixo.imshow(cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB))
        erro = abs(e.previsoes[pos] - registro['posicao']) * 50
        eixo.set_title(f'{variante}\nErro de {erro:.2f}% da largura', fontsize=11)
        eixo.axis('off')
        subfig = fig.add_subfigure(grade[linha + 1])
        subfig.suptitle(f'{variante} · mapas após ReLU', fontsize=12)
        blocos = subfig.add_gridspec(1, 3, wspace=.08)
        for bloco, ativacao in enumerate(e.modelo.mapas_ativacao(entrada)):
            mapas = ativacao[0]
            canais = np.argsort(-mapas.mean(axis=(1, 2)), kind='stable')[:3]
            limite = max(float(mapas[canais].max()), 1e-8)
            subgrade = blocos[0, bloco].subgridspec(1, 3, wspace=.05)
            for coluna, canal in enumerate(canais):
                eixo = subfig.add_subplot(subgrade[0, coluna])
                eixo.imshow(mapas[canal], cmap='magma', vmin=0, vmax=limite, interpolation='nearest')
                eixo.set_title(f'Bloco {bloco + 1} · canal {canal + 1}', fontsize=9)
                eixo.axis('off')
    fig.suptitle(f"{registro['imagem']} · verde = anotação, vermelho = previsão\n"
                 'Cada bloco mostra os três canais de maior ativação média em escala própria')
    fig.savefig(destino, dpi=155)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    argumentos_treino(ap)
    ap.set_defaults(revisoes=RAIZ / 'dataset_pista/rotulos/snapshots/treino_posicao_02.jsonl')
    ap.add_argument('--saida', type=Path, required=True)
    ap.add_argument('--sementes', type=int, nargs='+', default=[7, 17, 27])
    args = ap.parse_args()
    validar_treino(ap, args)
    if min(args.sementes) < 0 or len(args.sementes) != len(set(args.sementes)):
        ap.error('use sementes distintas e não negativas')
    if args.saida.exists():
        ap.error('a pasta de saída já existe')
    comparar(args)


if __name__ == '__main__':
    main()
