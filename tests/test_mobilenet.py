import numpy as np

from aprendizado.dataset_rotulado import limites_recorte
from aprendizado.mobilenet import ajustar_regressao, preparar_foto_mobilenet


def test_preparacao_mobilenet_preserva_recorte_e_converte_bgr_para_rgb():
    imagem = np.full((240, 128, 3), 255, dtype=np.uint8)
    y0, y1 = limites_recorte(*imagem.shape[:2])
    imagem[y0:y1, :64] = (0, 128, 255)
    imagem[y0:y1, 64:] = (255, 0, 0)
    entrada = preparar_foto_mobilenet(imagem)
    assert entrada.shape == (1, 64, 128, 3) and entrada.dtype == np.float32
    np.testing.assert_allclose(entrada[0, :, :64], np.broadcast_to([1, 128 / 127.5 - 1, -1], (64, 64, 3)), atol=1e-7)
    np.testing.assert_array_equal(entrada[0, :, 64:], np.broadcast_to([-1, -1, 1], (64, 64, 3)))


def test_ridge_usa_validacao_para_selecionar_regularizacao():
    x = np.array([[-1., -1.], [-.5, -.5], [.5, .5], [1., 1.]])
    y = x[:, 0] * .6 + .15
    xv = np.array([[-.8, -.8], [0., 0.], [.8, .8]])
    yv = xv[:, 0] * .6 + .15
    coef, vies, fator, auditoria = ajustar_regressao(x, y, xv, yv)
    np.testing.assert_allclose(xv @ coef + vies, yv, atol=2e-5)
    assert fator == min(auditoria, key=lambda r: r['mse_validacao'])['fator']
