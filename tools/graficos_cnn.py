"""Exporta gráficos dos experimentos existentes, sem treinar ou alterar dados.

Raspberry Pi, .venv: python tools/graficos_cnn.py
Usa SVG e os renderizadores Cairo/librsvg do sistema, sem dependências pip novas.
"""
import argparse
import csv
import ctypes as C
import ctypes.util
import hashlib
from html import escape
import json
import math
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
LARGURA, ALTURA = 1280, 800
ANTERIOR, NOVO = '#64748b', '#0f766e'
TREINO, VALIDACAO = '#2563eb', '#c2410c'
TEXTO, GRADE = '#172033', '#e2e8f0'


def numero(v, casas=1):
    return f'{v:.{casas}f}'.replace('.', ',')


class Grafico:
    def __init__(self, titulo, subtitulo, n_teste):
        self.itens = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{LARGURA}" height="{ALTURA}" '
                      f'viewBox="0 0 {LARGURA} {ALTURA}">',
                      '<style>text{font-family:DejaVu Sans,sans-serif;fill:#172033}</style>',
                      f'<rect width="{LARGURA}" height="{ALTURA}" fill="white"/>']
        self.texto(50, 52, titulo, 29, peso='bold')
        self.texto(50, 86, subtitulo, 17, cor=ANTERIOR)
        self.linha(50, 740, 1230, 740, GRADE)
        self.texto(50, 769, f'Resultados exploratórios • teste com {n_teste} imagens • CNN treinada do zero • sem validação física', 14, cor=ANTERIOR)

    def texto(self, x, y, valor, tamanho=18, cor=TEXTO, ancora='start', peso='normal', rotacao=None):
        transform = f' transform="rotate({rotacao} {x} {y})"' if rotacao is not None else ''
        self.itens.append(f'<text x="{x}" y="{y}" font-size="{tamanho}" style="fill:{cor}" '
                          f'text-anchor="{ancora}" font-weight="{peso}"{transform}>{escape(str(valor))}</text>')

    def linha(self, x1, y1, x2, y2, cor=GRADE, largura=1, tracejada=False):
        dash = ' stroke-dasharray="7 5"' if tracejada else ''
        self.itens.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{cor}" stroke-width="{largura}"{dash}/>')

    def retangulo(self, x, y, w, h, cor):
        self.itens.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{cor}" rx="3"/>')

    def caminho(self, pontos, cor, largura=3):
        if pontos:
            valores = ' '.join(f'{x:.3f},{y:.3f}' for x, y in pontos)
            self.itens.append(f'<polyline points="{valores}" fill="none" stroke="{cor}" stroke-width="{largura}"/>')

    def ponto(self, x, y, cor, triangulo=False):
        if triangulo:
            self.itens.append(f'<polygon points="{x},{y-7} {x-6},{y+5} {x+6},{y+5}" fill="{cor}"/>')
        else:
            self.itens.append(f'<circle cx="{x}" cy="{y}" r="6" fill="white" stroke="{cor}" stroke-width="2.5"/>')

    def legenda(self, x, y, itens):
        for cor, texto in itens:
            self.retangulo(x, y - 14, 18, 18, cor)
            self.texto(x + 28, y, texto, 17)
            x += 35 + len(texto) * 10

    def eixos(self, x, y, w, h, xmin, xmax, ymin, ymax, xticks, yticks, xlabel='', ylabel=''):
        tx = lambda v: x + (v - xmin) * w / (xmax - xmin)
        ty = lambda v: y + h - (v - ymin) * h / (ymax - ymin)
        for v in yticks:
            self.linha(x, ty(v), x + w, ty(v))
            self.texto(x - 12, ty(v) + 6, numero(v, 0 if v == int(v) else 1), 16, ancora='end')
        for v in xticks:
            self.linha(tx(v), y, tx(v), y + h)
            self.texto(tx(v), y + h + 25, numero(v, 0 if v == int(v) else 1), 16, ancora='middle')
        self.linha(x, y, x, y + h, TEXTO)
        self.linha(x, y + h, x + w, y + h, TEXTO)
        if xlabel:
            self.texto(x + w / 2, y + h + 62, xlabel, 18, ancora='middle')
        if ylabel:
            self.texto(x - 59, y + h / 2, ylabel, 17, ancora='middle', rotacao=-90)
        return tx, ty

    def svg(self):
        return '\n'.join(self.itens + ['</svg>'])


def carregar(pasta):
    pasta = Path(pasta)
    experimento = json.loads((pasta / 'experimento.json').read_text())
    dataset = json.loads((pasta / 'dataset.json').read_text())
    with (pasta / 'predicoes.csv').open(newline='') as arquivo:
        predicoes = list(csv.DictReader(arquivo))
    with (pasta / 'historico.csv').open(newline='') as arquivo:
        historico = [{k: float(v) for k, v in r.items()} for r in csv.DictReader(arquivo)]
    if not historico or any(not math.isfinite(v) for r in historico for v in r.values()):
        raise ValueError('Histórico vazio ou não finito')
    if any(b['passo'] <= a['passo'] for a, b in zip(historico, historico[1:])):
        raise ValueError('Passos do histórico fora de ordem')
    for grupo in ['treino', 'validacao', 'teste']:
        linhas = [r for r in predicoes if r['grupo'] == grupo]
        e = np.array([float(r['previsto']) - float(r['real']) for r in linhas])
        m = experimento['metricas'][grupo]['cnn']
        if not len(e) or len(e) != m['n'] or not np.isfinite(e).all():
            raise ValueError(f'Quantidade/previsões inválidas: {grupo}')
        np.testing.assert_allclose(np.abs(e).mean(), m['mae'], atol=1e-6)
        np.testing.assert_allclose((e ** 2).mean(), m['mse'], atol=1e-6)
    return {'pasta': pasta, 'exp': experimento, 'dataset': dataset,
            'pred': predicoes, 'hist': historico}


def validar_comparacao(a, b):
    for chave in ['preprocessamento', 'entrada', 'y_relativo', 'lambda_vis']:
        if a['exp'][chave] != b['exp'][chave]:
            raise ValueError(f'Experimentos têm {chave} diferentes')
    for chave in ['passos', 'lote', 'lr', 'avaliar_cada', 'semente']:
        if a['exp']['parametros'][chave] != b['exp']['parametros'][chave]:
            raise ValueError(f'Comparação controlada exige o mesmo parâmetro: {chave}')
    for grupo in ['validacao', 'teste']:
        orig = {r['imagem']: r for r in a['pred'] if r['grupo'] == grupo}
        novo = {r['imagem']: r for r in b['pred'] if r['grupo'] == grupo}
        if set(orig) != set(novo):
            raise ValueError('As imagens de avaliação não são iguais')
        for nome, r in orig.items():
            if any(r[k] != novo[nome][k] for k in ['real', 'video_origem', 'timestamp']):
                raise ValueError(f'Alvo/origem de avaliação mudou: {nome}')


def n(dados, grupo):
    return dados['exp']['metricas'][grupo]['cnn']['n']


def melhorias(a, b):
    antes = {r['imagem']: abs(float(r['erro'])) for r in a['pred'] if r['grupo'] == 'teste'}
    return sum(abs(float(r['erro'])) < antes[r['imagem']] for r in b['pred'] if r['grupo'] == 'teste')


def grafico_resumo(a, b):
    g = Grafico('Erro médio de localização: comparação dos treinos',
                'Mesmas imagens de validação e teste. Menor erro é melhor; o valor não é uma taxa de acerto.', n(a, 'teste'))
    g.legenda(150, 135, [(ANTERIOR, f"Primeiro: {n(a, 'treino')} imagens de treino"), (NOVO, f"Segundo: {n(b, 'treino')} imagens de treino")])
    ymax = max(2, math.ceil(max(d['exp']['metricas'][grupo]['cnn']['mae'] * 50 for d in [a, b] for grupo in ['validacao', 'teste']) / 2) * 2)
    tx, ty = g.eixos(130, 190, 1020, 390, 0, 2, 0, ymax, [], range(0, ymax + 1, 2), ylabel='Erro médio (% da largura)')
    for i, (grupo, nome) in enumerate([('validacao', f"Validação ({n(a, 'validacao')} imagens)"), ('teste', f"Teste ({n(a, 'teste')} imagens)")]):
        centro = tx(i + .5)
        for offset, dados, cor in [(-100, a, ANTERIOR), (15, b, NOVO)]:
            valor = dados['exp']['metricas'][grupo]['cnn']['mae'] * 50
            g.retangulo(centro + offset, ty(valor), 85, ty(0) - ty(valor), cor)
            g.texto(centro + offset + 42, ty(valor) - 13, numero(valor) + '%', 23, cor, 'middle', 'bold')
        g.texto(centro, 620, nome, 21, ancora='middle')
    g.texto(130, 685, f"No teste: menor erro em {melhorias(a, b)} de {n(a, 'teste')} imagens. A média não descreve todos os casos.", 18)
    return g


def grafico_curvas(a, b):
    g = Grafico('Evolução do erro durante o treinamento',
                f"Mesmos parâmetros e {a['exp']['parametros']['passos']} atualizações. Linhas verticais: checkpoints selecionados.", n(a, 'teste'))
    g.legenda(150, 130, [(TREINO, 'Treinamento'), (VALIDACAO, 'Validação')])
    ymax = max(2, math.ceil(max(r[k] * 50 for d in [a, b] for r in d['hist'] for k in ['mae_treino', 'mae_validacao']) / 2) * 2)
    xmax = a['exp']['parametros']['passos']
    xticks = sorted(set([round(xmax * i / 6) for i in range(7)]))
    for i, dados in enumerate([a, b]):
        x = 105 + i * 620
        g.texto(x + 225, 170, f"{['Primeiro', 'Segundo'][i]} treino: {n(dados, 'treino')} imagens", 22, ancora='middle')
        tx, ty = g.eixos(x, 200, 465, 400, 0, xmax, 0, ymax, xticks, range(0, ymax + 1, 2),
                        xlabel='Atualização dos pesos', ylabel='Erro médio (% da largura)')
        for chave, cor in [('mae_treino', TREINO), ('mae_validacao', VALIDACAO)]:
            g.caminho([(tx(r['passo']), ty(r[chave] * 50)) for r in dados['hist']], cor)
        passo = dados['exp']['melhor_passo']
        g.linha(tx(passo), ty(0), tx(passo), ty(ymax), TEXTO, 1.5, True)
        g.texto(tx(passo) + 7, 219, str(passo), 17)
    g.texto(100, 704, 'O checkpoint é escolhido pelo MSE de validação. Este gráfico exibe MAE; são métricas diferentes.', 17)
    return g


def grafico_dispersao(a, b):
    g = Grafico('Posição prevista versus posição marcada',
                f"{n(a, 'teste')} imagens de teste. Quanto mais próximo da diagonal, menor o erro de localização.", n(a, 'teste'))
    tx, ty = g.eixos(160, 150, 510, 510, -1, 1, -1, 1, [-1, -.5, 0, .5, 1], [-1, -.5, 0, .5, 1],
                    xlabel='Posição marcada por você', ylabel='Posição prevista pela CNN')
    g.linha(tx(-1), ty(-1), tx(1), ty(1), TEXTO, 1.5, True)
    g.linha(tx(0), ty(-1), tx(0), ty(1), GRADE, 1, True)
    for dados, cor, triangulo in [(a, ANTERIOR, False), (b, NOVO, True)]:
        for r in dados['pred']:
            if r['grupo'] == 'teste':
                g.ponto(tx(float(r['real'])), ty(float(r['previsto'])), cor, triangulo)
    g.ponto(770, 230, ANTERIOR)
    g.texto(790, 237, 'Primeiro treino', 22)
    g.ponto(770, 285, NOVO, True)
    g.texto(790, 292, 'Segundo treino', 22)
    for y, texto in [(380, '−1: lado esquerdo'), (420, '0: centro da imagem'), (460, '+1: lado direito'),
                     (540, 'A diagonal representa previsão perfeita.'), (580, 'Não representa precisão de direção'),
                     (610, 'dos motores nem visibilidade da linha.')]:
        g.texto(750, y, texto, 19)
    return g


def grafico_individual(a, b):
    g = Grafico('Erro em cada imagem de teste',
                f"O segundo treino teve menor erro em {melhorias(a, b)} das {n(a, 'teste')} imagens. Confira também as pioras.", n(a, 'teste'))
    g.legenda(300, 135, [(ANTERIOR, 'Primeiro treino'), (NOVO, 'Segundo treino')])
    orig = {r['imagem']: r for r in a['pred'] if r['grupo'] == 'teste'}
    novo = {r['imagem']: r for r in b['pred'] if r['grupo'] == 'teste'}
    maximo = max(5, math.ceil(max(abs(float(r['erro'])) * 50 for r in list(orig.values()) + list(novo.values())) / 5) * 5)
    x, y, w, h = 330, 175, 830, 465
    tx = lambda v: x + v * w / maximo
    for v in range(0, maximo + 1, 5):
        g.linha(tx(v), y, tx(v), y + h)
        g.texto(tx(v), y + h + 30, str(v), 17, ancora='middle')
    passo = h / len(orig)
    for i, nome in enumerate(sorted(orig)):
        cy = y + i * passo + 8
        g.texto(x - 15, cy + 21, nome.replace('video_', '').replace('_frame_', ' / ').replace('.jpg', ''), 18, ancora='end')
        for offset, r, cor in [(0, orig[nome], ANTERIOR), (20, novo[nome], NOVO)]:
            valor = abs(float(r['erro'])) * 50
            g.retangulo(x, cy + offset, tx(valor) - x, 15, cor)
            g.texto(tx(valor) + 7, cy + offset + 13, numero(valor) + '%', 14, cor)
    g.texto(x + w / 2, 709, 'Erro absoluto (% da largura da imagem)', 20, ancora='middle')
    return g


def grafico_videos(a, b):
    g = Grafico('Erro médio por vídeo de teste',
                'Poucas amostras por vídeo. Não interpretar os valores como desempenho em todo o vídeo.', n(a, 'teste'))
    g.legenda(150, 135, [(ANTERIOR, 'Primeiro treino'), (NOVO, 'Segundo treino')])
    videos = sorted(a['exp']['metricas']['teste']['por_video'])
    ymax = max(2, math.ceil(max(d['exp']['metricas']['teste']['por_video'][v]['mae'] * 50 for d in [a, b] for v in videos) / 2) * 2)
    tx, ty = g.eixos(130, 190, 1020, 390, 0, len(videos), 0, ymax, [], range(0, ymax + 1, 2), ylabel='Erro médio (% da largura)')
    for i, video in enumerate(videos):
        centro = tx(i + .5)
        for offset, dados, cor in [(-100, a, ANTERIOR), (15, b, NOVO)]:
            valor = dados['exp']['metricas']['teste']['por_video'][video]['mae'] * 50
            g.retangulo(centro + offset, ty(valor), 85, ty(0) - ty(valor), cor)
            g.texto(centro + offset + 42, ty(valor) - 13, numero(valor) + '%', 23, cor, 'middle', 'bold')
        quantidade = a['exp']['metricas']['teste']['por_video'][video]['n']
        g.texto(centro, 620, video, 21, ancora='middle')
        g.texto(centro, 652, f'{quantidade} imagens avaliadas', 17, ANTERIOR, 'middle')
    return g


def grafico_distribuicao(a, b):
    g = Grafico('Quantidade de imagens de treino por vídeo',
                'Compare a quantidade de dados e sua distribuição entre as gravações.', n(a, 'teste'))
    g.legenda(400, 135, [(ANTERIOR, f"Primeiro: total {n(a, 'treino')}"), (NOVO, f"Segundo: total {n(b, 'treino')}")])
    contagens = []
    for dados in [a, b]:
        c = {}
        for r in dados['dataset']['incluidos']:
            if r['grupo'] == 'treino':
                c[r['video_origem']] = c.get(r['video_origem'], 0) + 1
        contagens.append(c)
    videos = sorted(set(contagens[0]) | set(contagens[1]))
    x, y, w, h = 400, 190, 720, 420
    maximo = max(10, math.ceil(max(v for c in contagens for v in c.values()) / 10) * 10)
    tx = lambda v: x + v * w / maximo
    for v in range(0, maximo + 1, 10):
        g.linha(tx(v), y, tx(v), y + h)
        g.texto(tx(v), y + h + 30, str(v), 17, ancora='middle')
    for i, video in enumerate(videos):
        cy = y + i * h / len(videos) + 14
        g.texto(x - 20, cy + 23, video, 18, ancora='end')
        for offset, contagem, cor in [(0, contagens[0], ANTERIOR), (23, contagens[1], NOVO)]:
            quantidade = contagem.get(video, 0)
            g.retangulo(x, cy + offset, tx(quantidade) - x, 18, cor)
            g.texto(tx(quantidade) + 8, cy + offset + 15, str(quantidade), 16, cor)
    g.texto(x + w / 2, 680, 'Imagens utilizadas no treinamento', 20, ancora='middle')
    return g


class Exportador:
    """Renderização vetorial com as bibliotecas já disponíveis no Linux."""
    def __init__(self):
        nomes = [ctypes.util.find_library(n) for n in ['rsvg-2', 'cairo', 'gobject-2.0']]
        if not all(nomes):
            raise RuntimeError('Para exportar PNG/PDF, o sistema precisa de librsvg e Cairo.')
        self.rsvg, self.cairo, self.gobject = [C.CDLL(n) for n in nomes]
        funcoes = [(self.rsvg, 'rsvg_handle_new_from_data', [C.c_void_p, C.c_size_t, C.POINTER(C.c_void_p)], C.c_void_p),
                   (self.rsvg, 'rsvg_handle_render_cairo', [C.c_void_p, C.c_void_p], C.c_int),
                   (self.cairo, 'cairo_image_surface_create', [C.c_int, C.c_int, C.c_int], C.c_void_p),
                   (self.cairo, 'cairo_pdf_surface_create', [C.c_char_p, C.c_double, C.c_double], C.c_void_p),
                   (self.cairo, 'cairo_create', [C.c_void_p], C.c_void_p),
                   (self.cairo, 'cairo_surface_write_to_png', [C.c_void_p, C.c_char_p], C.c_int),
                   (self.cairo, 'cairo_status', [C.c_void_p], C.c_int),
                   (self.cairo, 'cairo_surface_status', [C.c_void_p], C.c_int)]
        for lib, nome, args, result in funcoes:
            f = getattr(lib, nome)
            f.argtypes, f.restype = args, result
        for lib, nome in [(self.cairo, 'cairo_destroy'), (self.cairo, 'cairo_surface_destroy'),
                          (self.cairo, 'cairo_show_page'), (self.cairo, 'cairo_surface_finish'),
                          (self.gobject, 'g_object_unref')]:
            f = getattr(lib, nome)
            f.argtypes, f.restype = [C.c_void_p], None

    def desenhar(self, svg, contexto):
        dados = svg.encode('utf-8')
        buffer = C.create_string_buffer(dados)
        erro = C.c_void_p()
        handle = self.rsvg.rsvg_handle_new_from_data(buffer, len(dados), C.byref(erro))
        if not handle:
            raise RuntimeError('SVG inválido no renderizador')
        try:
            if not self.rsvg.rsvg_handle_render_cairo(handle, contexto) or self.cairo.cairo_status(contexto):
                raise RuntimeError('Falha ao renderizar o gráfico')
        finally:
            self.gobject.g_object_unref(handle)

    def png(self, svg, caminho):
        surface = self.cairo.cairo_image_surface_create(0, LARGURA, ALTURA)
        contexto = self.cairo.cairo_create(surface)
        try:
            self.desenhar(svg, contexto)
            if self.cairo.cairo_surface_write_to_png(surface, str(caminho).encode()):
                raise OSError(f'Falha ao gravar {caminho}')
        finally:
            self.cairo.cairo_destroy(contexto)
            self.cairo.cairo_surface_destroy(surface)

    def pdf(self, graficos, caminho):
        surface = self.cairo.cairo_pdf_surface_create(str(caminho).encode(), LARGURA, ALTURA)
        contexto = self.cairo.cairo_create(surface)
        try:
            for g in graficos:
                self.desenhar(g.svg(), contexto)
                self.cairo.cairo_show_page(contexto)
            self.cairo.cairo_surface_finish(surface)
            if self.cairo.cairo_surface_status(surface):
                raise OSError('Falha ao gravar PDF')
        finally:
            self.cairo.cairo_destroy(contexto)
            self.cairo.cairo_surface_destroy(surface)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--primeiro', type=Path, default=RAIZ / 'dataset_pista/resultados/treino_posicao_01')
    ap.add_argument('--segundo', type=Path, default=RAIZ / 'dataset_pista/resultados/treino_posicao_02')
    ap.add_argument('--saida', type=Path, default=RAIZ / 'dataset_pista/resultados/graficos_comparacao_01_02')
    args = ap.parse_args()
    a, b = carregar(args.primeiro), carregar(args.segundo)
    validar_comparacao(a, b)
    exportador = Exportador()
    args.saida.mkdir(parents=True, exist_ok=False)
    figuras = [('01_resumo', grafico_resumo(a, b)), ('02_curvas_treinamento', grafico_curvas(a, b)),
               ('03_previsto_real', grafico_dispersao(a, b)), ('04_erros_por_imagem', grafico_individual(a, b)),
               ('05_erros_por_video', grafico_videos(a, b)), ('06_dados_por_video', grafico_distribuicao(a, b))]
    for nome, g in figuras:
        svg = g.svg()
        (args.saida / f'{nome}.svg').write_text(svg, encoding='utf-8')
        exportador.png(svg, args.saida / f'{nome}.png')
        print(nome, flush=True)
    exportador.pdf([g for _, g in figuras], args.saida / 'graficos_cnn.pdf')
    manifesto = {'experimentos': [str(args.primeiro.resolve()), str(args.segundo.resolve())],
                 'arquivos': [n for n, _ in figuras], 'unidade_erro': 'porcentagem_da_largura = MAE_normalizado * 50',
                 'avaliacao_identica_verificada': True, 'treino_executado': False,
                 'hashes_origem': {str(d['pasta'] / nome): hashlib.sha256((d['pasta'] / nome).read_bytes()).hexdigest()
                                   for d in [a, b] for nome in ['experimento.json', 'dataset.json', 'predicoes.csv', 'historico.csv']},
                 'hash_script': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (args.saida / 'manifesto.json').write_text(json.dumps(manifesto, indent=2, ensure_ascii=False), encoding='utf-8')
    (args.saida / 'LEIA-ME.md').write_text(
        '# Gráficos para a apresentação\n\n'
        'Abra graficos_cnn.pdf para ver os seis gráficos. PNGs servem para slides; SVGs preservam qualidade vetorial.\n\n'
        'Sugestão: apresentar 01_resumo, 04_erros_por_imagem e 06_dados_por_video; '
        'usar 02_curvas_treinamento para explicar a diferença entre erro de treino e validação.\n\n'
        'A mesma CNN foi treinada do zero com 24 e 58 imagens. A avaliação usa os mesmos 10 frames de validação '
        'e 9 de teste. MAE não é acurácia: 3,6% da largura de erro médio não significa 96,4% de acerto. '
        'O erro médio de teste diminuiu, mas só quatro dos nove frames melhoraram. '
        'As novas imagens são de um vídeo; o teste já foi consultado na exploração, '
        'sem validação física nem avaliação da saída de visibilidade.\n\n'
        'Os gráficos leem os arquivos existentes e não treinam ou alteram o modelo. '
        'Os valores agregados foram conferidos contra predicoes.csv, e os alvos/IDs de avaliação foram comparados. '
        'Não apresentam intervalos de confiança nem prova de generalização.\n\n'
        'Na Raspberry Pi, terminal na pasta do projeto com a .venv, para reproduzir em outra pasta:\n\n'
        '```bash\n.venv/bin/python tools/graficos_cnn.py --saida dataset_pista/resultados/graficos_reproducao\n```\n',
        encoding='utf-8')
    print('Gráficos salvos em', args.saida, flush=True)


if __name__ == '__main__':
    main()
