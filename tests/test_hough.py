import cv2
import numpy as np

from tools.comparar_hough import resumir
from visao.hough import detectar_hough


def test_hough_estima_centro_entre_bordas_da_fita():
    imagem = np.full((160, 320), 200, np.uint8)
    cv2.rectangle(imagem, (130, 20), (143, 142), 30, -1)
    r = detectar_hough(imagem, 79.5)
    for faixa in r.faixas:
        assert faixa.motivo == 'par_aceito'
        assert len(faixa.aceitos) == 2
        assert abs(faixa.x - 136.5) <= 1


def test_hough_abstem_em_alvo_sem_suporte_e_em_rejunte_fino():
    imagem = np.full((160, 320), 200, np.uint8)
    imagem[:, 100:102] = 50
    imagem[20:55, 150:165] = 30
    imagem[104:140, 150:165] = 30
    r = detectar_hough(imagem, 79.5)
    assert r.central.x is None
    assert r.faixas[0].x is not None and r.faixas[2].x is not None


def test_resumo_separa_abstencao_no_alvo_de_estimativa_em_ausente():
    linhas = [dict(largura=101, alvo=50, visibilidade='visivel', hough=None, contornos=55, cnn=55),
              dict(largura=101, alvo=50, visibilidade='visivel', hough=51, contornos=55, cnn=50),
              dict(largura=101, alvo=None, visibilidade='ausente', hough=None, contornos=55, cnn=50)]
    resumo = resumir(linhas)
    assert resumo['pareados'] == 1
    assert resumo['metodos']['hough'] == dict(sem_estimativa=1, mae_pct_largura=1., mae_pareado_pct_largura=1.,
                                             estimativa_em_ausente=0, estimativa_em_ambiguo=0)
    assert resumo['metodos']['cnn']['mae_pct_largura'] == 2.5
    assert resumo['metodos']['cnn']['mae_pareado_pct_largura'] == 0
    assert resumo['metodos']['cnn']['estimativa_em_ausente'] == 1
