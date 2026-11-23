"""Detecção sintética em ROI, sem câmera, serial, modelos ou motores."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg
from visao.detector import DetectorLinha, desenhar_debug


def imagem(xs=(160,), direcao=0., clara=False, altura=240, largura=320):
    fundo, tinta = (20, 220) if clara else (220, 20)
    a = np.full((altura, largura), fundo, np.uint8)
    escala = altura / 240.
    for x in xs:
        for y in (130, 172, 214):
            y = round(y * escala)
            cx = round(x + direcao * (altura * .75 - y))
            cv2.line(a, (cx, y), (round(cx - 20 * escala * direcao), round(y + 20 * escala)),
                     tinta, max(3, round(9 * escala)))
    return a


class TestTracejado(unittest.TestCase):
    def test_centro_deslocamento_e_multiplos_segmentos(self):
        for x in (40, 90, 160, 230, 280):
            with self.subTest(x=x):
                r = DetectorLinha(True).processar(imagem((x,)))
                self.assertTrue(r.achou)
                self.assertEqual(len(r.segmentos), 3)
                self.assertAlmostEqual(r.erro, (x-160)/160, places=2)
                self.assertGreater(r.confianca, 0)
                self.assertTrue(all(y >= 120 for _, y in r.trajetoria))
    def test_direcao_geométrica(self):
        for direcao in (-.3, .3):
            r = DetectorLinha(True).processar(imagem(direcao=direcao))
            self.assertTrue(r.achou)
            self.assertAlmostEqual(r.direcao, direcao, delta=.05)
    def test_linha_clara_e_limiar_fixo(self):
        with patch.object(cfg, 'LINHA_ESCURA', False), patch.object(cfg, 'USAR_OTSU', False):
            r = DetectorLinha(True).processar(imagem((230,), clara=True))
        self.assertTrue(r.achou)
        self.assertGreater(r.erro, .3)
    def test_ausencia_nunca_e_observacao_historica(self):
        d = DetectorLinha(True)
        with patch('visao.detector.time.monotonic', return_value=10.):
            self.assertTrue(d.processar(imagem()).achou)
        with patch('visao.detector.time.monotonic', return_value=10.1):
            r = d.processar(imagem(()))
        self.assertFalse(r.achou)
        self.assertEqual(r.segmentos, ())
        self.assertEqual(d._referencia_t, 10.)
        self.assertEqual(d._referencia.shape, (2, 2))
    def test_memoria_associa_e_expira_sem_guardar_frames(self):
        d = DetectorLinha(True)
        with patch('visao.detector.time.monotonic', return_value=10.):
            d.processar(imagem((240,)))
        with patch('visao.detector.time.monotonic', return_value=10.1):
            r = d.processar(imagem((80, 240)))
        self.assertTrue(r.achou)
        self.assertGreater(r.erro, .4)
        with patch('visao.detector.time.monotonic', return_value=11.):
            r = d.processar(imagem((80, 240)))
        self.assertFalse(r.achou)
        self.assertEqual(r.motivo, 'trajetorias_ambiguas')
        self.assertIsNone(d._referencia)
    def test_formato_tempo_regressivo_e_reset_invalidam_memoria(self):
        for reset in ('forma', 'tempo', 'explicito'):
            d = DetectorLinha(True)
            with patch('visao.detector.time.monotonic', return_value=10.):
                d.processar(imagem((240,)))
            if reset == 'explicito':
                d.limpar_historico()
            quadro = cv2.cvtColor(imagem((80, 240)), cv2.COLOR_GRAY2BGR) if reset == 'forma' else imagem((80, 240))
            with patch('visao.detector.time.monotonic', return_value=9. if reset == 'tempo' else 10.1):
                r = d.processar(quadro)
            self.assertFalse(r.achou)
    def test_ruido_fino_piso_uniforme_e_baixo_contraste(self):
        for brilho in (0, 128, 255):
            self.assertFalse(DetectorLinha(True).processar(np.full((240, 320), brilho, np.uint8)).achou)
        ruido = np.full((240, 320), 220, np.uint8)
        cv2.line(ruido, (80, 120), (100, 239), 20, 1)
        self.assertFalse(DetectorLinha(True).processar(ruido).achou)
        baixo = imagem(); baixo[baixo < 200] = 200
        self.assertFalse(DetectorLinha(True).processar(baixo).achou)
    def test_ambiguidade_sem_historico_abstem(self):
        r = DetectorLinha(True).processar(imagem((80, 240)))
        self.assertFalse(r.achou)
        self.assertEqual(r.motivo, 'trajetorias_ambiguas')
    def test_roi_ignora_linha_acima_do_recorte(self):
        a = imagem(())
        a[10:100, 155:166] = 20
        r = DetectorLinha(True).processar(a)
        self.assertFalse(r.achou)
        self.assertEqual(r.binaria.shape, (120, 320))
    def test_continua_e_quadro_menor_sem_resize(self):
        for altura, largura in ((240, 320), (120, 160)):
            a = np.full((altura, largura), 220, np.uint8)
            a[:, largura//2-4:largura//2+5] = 20
            r = DetectorLinha(True).processar(a)
            self.assertTrue(r.achou)
            self.assertAlmostEqual(r.erro, 0, places=2)
            self.assertEqual(r.binaria.shape, (altura//2, largura))
    def test_limite_de_candidatos_abstem(self):
        a = imagem(())
        for y in (130, 160, 190, 220):
            for x in range(15, 310, 30):
                cv2.rectangle(a, (x, y), (x+5, y+13), 20, -1)
        r = DetectorLinha(True).processar(a)
        self.assertFalse(r.achou)
        self.assertEqual(r.motivo, 'sem_segmentos_compativeis_ou_excesso')
    def test_blur_desativavel_e_debug_nao_alteram_frame(self):
        a = imagem(); antes = a.copy()
        with patch.object(cfg, 'BLUR_KERNEL', 1), patch('visao.detector.cv2.GaussianBlur', side_effect=AssertionError):
            r = DetectorLinha(True).processar(a)
        self.assertTrue(r.achou)
        vis = desenhar_debug(a, r)
        self.assertEqual(vis.shape, (240, 320, 3))
        np.testing.assert_array_equal(a, antes)
        desenhar_debug(a, DetectorLinha(True).processar(imagem(())))
    def test_tracos_colineares_muito_separados_nao_viram_ambiguidade(self):
        a = imagem(())
        cv2.rectangle(a, (155, 122), (165, 152), 20, -1)
        cv2.rectangle(a, (155, 207), (165, 237), 20, -1)
        r = DetectorLinha(True).processar(a)
        self.assertTrue(r.achou)
        self.assertAlmostEqual(r.erro, 0., places=2)
    def test_reaparecimento_corrige_posicao_e_qualidade_baixa_abstem(self):
        d = DetectorLinha(True)
        with patch('visao.detector.time.monotonic', return_value=10.):
            self.assertTrue(d.processar(imagem((160,))).achou)
        with patch('visao.detector.time.monotonic', return_value=10.1):
            self.assertFalse(d.processar(imagem(())).achou)
        with patch('visao.detector.time.monotonic', return_value=10.2):
            r = d.processar(imagem((190,)))
        self.assertTrue(r.achou)
        self.assertGreater(r.erro, .1)
        with patch.object(cfg, 'TRACEJADO_CONFIANCA_MIN', 1.1):
            r = DetectorLinha(True).processar(imagem())
        self.assertFalse(r.achou)
        self.assertEqual(r.motivo, 'suporte_insuficiente')
    def test_padrao_permanece_legado(self):
        r = DetectorLinha().processar(imagem())
        self.assertTrue(r.achou)
        self.assertIsNotNone(r.contorno)
        self.assertEqual(r.segmentos, ())
        self.assertEqual(r.motivo, 'legado')

if __name__ == '__main__':
    unittest.main()
