"""Regressão offline de posição com uma base MobileNetV2 congelada."""
import cv2
import numpy as np

from aprendizado.dataset_rotulado import limites_recorte

ENTRADA = (64, 128, 3)
ALPHA = 0.5
CAMADA_ESPACIAL = 'block_16_project_BN'
PREPROCESSAMENTO = 'mobilenet_rgb_128x64_roi_y075_v1'
SHA256_PESOS_IMAGENET = '5c9415fd2486b2d10cd66a8406449fe72163597c085fba245d6e3107be0a564b'


def preparar_foto_mobilenet(imagem):
    """Mesmo recorte geométrico da CNN original, RGB em [-1, 1]."""
    y0, y1 = limites_recorte(*imagem.shape[:2])
    pequena = cv2.resize(imagem[y0:y1], (ENTRADA[1], ENTRADA[0]), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(pequena, cv2.COLOR_BGR2RGB)
    return rgb[None].astype(np.float32) / 127.5 - 1.0


def criar_extrator(keras, pesos):
    base = keras.applications.MobileNetV2(input_shape=ENTRADA, alpha=ALPHA, include_top=False, weights=None)
    base.load_weights(str(pesos))
    espacial = base.get_layer(CAMADA_ESPACIAL).output
    extrator = keras.Model(base.input, keras.layers.Flatten()(espacial), name='mobilenet_v2_congelada')
    extrator.trainable = False
    return extrator


def ajustar_regressao(treino, alvo_treino, validacao, alvo_validacao):
    """Ajusta só a saída linear via ridge, com regularização escolhida por validação."""
    centro = treino.mean(axis=0, dtype=np.float64)
    x = treino - centro
    media_alvo = alvo_treino.mean(dtype=np.float64)
    gram = x @ x.T
    escala = max(float(np.trace(gram) / len(x)), 1e-8)
    identidade = np.eye(len(x))
    opcoes = []
    for fator in (0.0001, 0.001, 0.01, 0.1, 1., 10.):
        regularizacao = fator * escala
        duais = np.linalg.solve(gram + regularizacao * identidade, alvo_treino - media_alvo)
        coeficientes = x.T @ duais
        vies = media_alvo - centro @ coeficientes
        previsao = np.clip(validacao @ coeficientes + vies, -1., 1.)
        opcoes.append((float(np.mean((previsao - alvo_validacao) ** 2)), fator, coeficientes, vies))
    _, fator, coeficientes, vies = min(opcoes, key=lambda opcao: opcao[0])
    auditoria = [{'fator': f, 'lambda': f * escala, 'mse_validacao': mse} for mse, f, _, _ in opcoes]
    return coeficientes, vies, fator, auditoria


def montar_regressor(keras, extrator, coeficientes, vies):
    saida = keras.layers.Dense(1, name='posicao_horizontal')
    predicao = keras.ops.clip(saida(extrator.output), -1., 1.)
    modelo = keras.Model(extrator.input, predicao, name='mobilenet_v2_posicao')
    saida.set_weights([coeficientes[:, None].astype(np.float32), np.array([vies], dtype=np.float32)])
    return modelo
