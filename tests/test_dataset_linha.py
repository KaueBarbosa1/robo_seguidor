"""Testes offline de amostragem e revisão, sem interface gráfica ou hardware."""
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.estudar_linha import mascaras, selecionar  # noqa: E402
from tools.rotular_linha import carregar_revisoes, validar_anotacao  # noqa: E402
from aprendizado.dataset_rotulado import (DIVISAO, grupo_video, limites_recorte,  # noqa: E402
                                          posicao_anotada, preparar_foto, reduzir_foto)
from aprendizado.dados import normalizar  # noqa: E402
from aprendizado.cnn import RedeLinha  # noqa: E402


def rejeita(funcao, *args):
    try:
        funcao(*args)
    except ValueError:
        return
    raise AssertionError('Entrada inválida foi aceita')


def test_amostragem_inclui_extremos_por_video_e_ordena_timestamp():
    registros = [{'video_origem': v, 'timestamp': str(i)}
                 for v in ['a', 'b'] for i in [4, 0, 3, 1, 2]]
    amostra = selecionar(registros, 3)
    assert [(r['video_origem'], r['timestamp']) for r in amostra] == [
        ('a', '0'), ('a', '2'), ('a', '4'), ('b', '0'), ('b', '2'), ('b', '4')]
    assert len(selecionar(registros, 100)) == 10


def test_mascaras_preservam_forma_e_polaridade():
    imagem = np.full((100, 80), 230, np.uint8)
    imagem[20:80, 30:50] = 20
    masks, limiar = mascaras(imagem, 100, 31, 7)
    assert 20 < limiar < 230
    for mascara in masks.values():
        assert mascara.shape == imagem.shape and mascara.dtype == np.uint8
        assert set(np.unique(mascara)) <= {0, 255}
    assert masks['fixo'][50, 40] == masks['otsu'][50, 40] == 255
    assert masks['fixo'][0, 0] == masks['otsu'][0, 0] == 0


def test_visibilidade_nao_e_inferida_por_falta_de_pontos():
    for status in ['', 'visivel', 'parcial']:
        rejeita(validar_anotacao, status, [], 100, 100)
    for status in ['ausente', 'ambiguo']:
        assert validar_anotacao(status, [], 100, 100) == []
        rejeita(validar_anotacao, status, [[10, 20]], 100, 100)


def test_trajetoria_limites_e_ordem():
    assert validar_anotacao('visivel', [[99, 99], [0, 0]], 100, 100) == [[0, 0], [99, 99]]
    rejeita(validar_anotacao, 'visivel', [[0, 0], [100, 99]], 100, 100)
    rejeita(validar_anotacao, 'parcial', [[0, 4], [10, 4]], 100, 100)


def test_revisoes_preservam_historico_e_rejeitam_json_incompleto():
    with tempfile.TemporaryDirectory() as pasta:
        caminho = Path(pasta) / 'rotulos.jsonl'
        assert carregar_revisoes(caminho) == {}
        itens = [{'schema': 'trajetoria_humana_v1', 'imagem': 'a.jpg', 'revisao': i} for i in [1, 2]]
        caminho.write_text(''.join(json.dumps(i) + '\n' for i in itens))
        assert carregar_revisoes(caminho)['a.jpg']['revisao'] == 2
        with caminho.open('a') as arquivo:
            arquivo.write('{')
        rejeita(carregar_revisoes, caminho)


def test_posicao_interpola_sem_extrapolar_nem_confundir_visibilidade():
    r = {'largura': '101', 'altura': '101', 'visibilidade': 'visivel',
         'pontos_px': [[10, 50], [90, 100]]}
    assert abs(posicao_anotada(r)) < 1e-8  # y=75 -> x=50 -> centro
    r['visibilidade'] = 'parcial'
    assert abs(posicao_anotada(r)) < 1e-8
    r['pontos_px'] = [[10, 10], [90, 70]]
    assert posicao_anotada(r) is None
    r.update(visibilidade='ausente', pontos_px=[])
    assert posicao_anotada(r) is None


def test_posicao_respeita_convencao_esquerda_direita():
    r = {'largura': '101', 'altura': '101', 'visibilidade': 'visivel'}
    for x, esperado in [(0, -1.), (50, 0.), (100, 1.)]:
        r['pontos_px'] = [[x, 0], [x, 100]]
        assert posicao_anotada(r) == esperado


def test_recorte_preserva_proporcao_e_inferencia_usa_mesma_transformacao():
    img = np.full((1920, 1080, 3), 230, np.uint8)
    y0, y1 = limites_recorte(*img.shape[:2])
    assert y1 - y0 == img.shape[1] // 2
    assert y0 <= .75 * 1919 < y1
    img[y0:y1, 100:200] = 20
    reduzido = reduzir_foto(img)
    assert reduzido.shape == (40, 80) and reduzido.dtype == np.uint8
    np.testing.assert_array_equal(preparar_foto(img), normalizar(reduzido[None]))
    rejeita(limites_recorte, 100, 201)  # largura ímpar
    rejeita(limites_recorte, 40, 200)   # ROI não cabe


def test_divisao_nao_compartilha_videos():
    todos = [v for videos in DIVISAO.values() for v in videos]
    assert len(todos) == len(set(todos)) == 9
    for grupo, videos in DIVISAO.items():
        for video in videos:
            assert grupo_video(video) == grupo
    rejeita(grupo_video, 'novo_video.mp4')
    rejeita(grupo_video, 'a', {'treino': ['a'], 'teste': ['a']})


def test_perda_somente_posicao_nao_supervisiona_cabeca_visibilidade():
    rng = np.random.default_rng(1)
    rede = RedeLinha(1)
    entrada = rng.normal(0, 1, (2, 1, 40, 80)).astype(np.float32)
    alvo = np.array([-.2, .3], np.float32)
    comuns = (entrada, alvo, np.ones(2, bool))
    perda_a, _ = rede.perda_e_gradiente(*comuns, np.zeros(2), np.ones(2), lambda_vis=0.)
    gradientes_a = [g.copy() for g in rede.gradientes()]
    perda_b, _ = rede.perda_e_gradiente(*comuns, np.ones(2), np.ones(2), lambda_vis=0.)
    assert perda_a == perda_b
    for antes, depois in zip(gradientes_a, rede.gradientes()):
        np.testing.assert_array_equal(antes, depois)
    assert np.count_nonzero(rede.gradientes()[-2][:, 1]) == 0
    assert rede.gradientes()[-1][1] == 0


if __name__ == '__main__':
    for nome, funcao in sorted(list(globals().items())):
        if nome.startswith('test_'):
            funcao()
            print('OK', nome)
