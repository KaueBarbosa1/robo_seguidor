"""Testes da fonte com HTTP injetado: não abrem serial nem motores."""
import sys
import time
import threading
import unittest
from pathlib import Path
from email.message import Message
from io import BytesIO
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cv2
import numpy as np
from visao.esp32_cam import CameraESP32, receber_quadro
from visao.fontes import criar_fonte
from tools.testar_esp32_cam import receber_quadro as receptor_legado

class Resposta(BytesIO):
    status = 200
    def __init__(self, dados, idade):
        super().__init__(dados)
        self.headers = Message()
        self.headers['Content-Type'] = 'image/jpeg'
        self.headers['X-Frame-Age-Us'] = str(idade)

class HTTPFalso:
    def __init__(self):
        self.falhar = False
        self.idade = 1000
        self.dados = cv2.imencode('.jpg', np.full((240,320,3), 150, np.uint8))[1].tobytes()
        self.pedidos = 0
    def open(self, req, timeout):
        time.sleep(.005)
        self.pedidos += 1
        if self.falhar:
            raise OSError('desconectada')
        return Resposta(self.dados, self.idade)

class TestFonte(unittest.TestCase):
    def esperar(self, cond):
        fim = time.monotonic() + 2
        while not cond() and time.monotonic() < fim:
            time.sleep(.005)
        self.assertTrue(cond())
    def test_reuso_e_resolucao_sem_resize(self):
        self.assertIs(receptor_legado, receber_quadro)
        self.assertIsInstance(criar_fonte('esp32'), CameraESP32)
        h = HTTPFalso()
        q = receber_quadro(h, 'http://teste/capture', 1)
        self.assertEqual(q.imagem.shape, (240,320,3))
        self.assertEqual(q.jpeg, h.dados)
        h.dados = cv2.imencode('.jpg', np.zeros((120,160,3), np.uint8))[1].tobytes()
        with self.assertRaisesRegex(ValueError, '320x240'):
            receber_quadro(h, 'http://teste/capture', 1)
    def test_ultimo_frame_metadados_e_encerramento(self):
        h = HTTPFalso(); c = CameraESP32(opener=h)
        c.iniciar()
        try:
            primeiro = c.proximo_quadro(0, 1)
            self.assertIsNotNone(primeiro)
            self.esperar(lambda: c.id_atual() > primeiro[0] + 3)
            with c._cond:
                atual = c.proximo_quadro(primeiro[0], 0)
                self.assertEqual(atual[0], c.id_atual())
                self.assertIs(atual[1], c._quadro.imagem)
                self.assertIsNone(c.metadados(primeiro[0]))
                self.assertGreaterEqual(c.metadados(atual[0])['idade_limite_ms'], 1)
            self.assertGreater(c.estatisticas['fps'], 0)
        finally:
            c.parar()
        self.assertFalse(c._thread.is_alive())
        self.assertIsNone(c.proximo_quadro(0, 0))
    def test_falha_invalida_e_recupera(self):
        h = HTTPFalso(); c = CameraESP32(opener=h, reconexao_s=.01)
        c.iniciar()
        try:
            self.assertIsNotNone(c.proximo_quadro(0, 1))
            h.falhar = True
            self.esperar(lambda: c.status == 'erro')
            self.assertIsNone(c.proximo_quadro(0, .01))
            h.falhar = False
            self.esperar(lambda: c.status == 'ok')
            self.assertGreater(c.estatisticas['erros'], 0)
        finally:
            c.parar()
    def test_idade_esp_http_e_tempo_local(self):
        h = HTTPFalso(); h.idade = 500000
        c = CameraESP32(opener=h, idade_max_s=.1)
        c.iniciar()
        try:
            self.esperar(lambda: c.estatisticas['vencidos'] > 0)
            self.assertIsNone(c.proximo_quadro(0, .02))
            h.idade = 1000
            self.assertIsNotNone(c.proximo_quadro(0, 1))
            with c._cond:
                c._quadro = type(c._quadro)(c._quadro.jpeg, c._quadro.imagem,
                    time.monotonic()-1, c._quadro.recepcao_utc, 5, 1)
                self.assertIsNone(c.proximo_quadro(0, 0))
                self.assertEqual(c.status, 'vencida')
            h.idade = 0
            c.idade_max_s = .001  # HTTP falso leva >=5 ms, mesmo sem idade na ESP.
            self.esperar(lambda: c.status == 'vencida')
        finally:
            c.parar()
    def test_jpeg_truncado_e_cabecalho_invalido(self):
        h = HTTPFalso(); h.dados = h.dados[:-2]
        with self.assertRaisesRegex(ValueError, 'truncado'):
            receber_quadro(h, 'http://teste/capture', 1)
        h = HTTPFalso(); h.idade = 'nan'
        with self.assertRaisesRegex(ValueError, 'Idade'):
            receber_quadro(h, 'http://teste/capture', 1)

if __name__ == '__main__':
    unittest.main()
