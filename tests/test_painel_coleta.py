"""Verifica que a previa so publica arquivos salvos e denuncia falhas."""
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import coletar_esp32_cam as coletor
from tools.painel_coleta import Estado, Handler
from visao.recorte_esp32 import RecorteESP32


class TestPainel(unittest.TestCase):
    def test_publica_apos_gravar_e_registra_falha(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp) / 'sessao'
            args = SimpleNamespace(saida=pasta, sem_janela=True, previa=False, duracao=None,
                                   quadros=2, intervalo=0, timeout=1, nota='', url='http://camera/capture')
            estado = Estado(pasta)
            quadro = SimpleNamespace(jpeg=b'jpeg-original', recepcao_utc='agora',
                                     recepcao_monotonica=0, http_ms=1, idade_envio_ms=1,
                                     idade_recepcao_limite_ms=2, imagem=None)
            def observar(linha, jpeg):
                if jpeg:
                    self.assertEqual((pasta / linha['jpeg']).read_bytes(), jpeg)
                estado.observar(linha, jpeg)
            with patch.object(coletor, 'receber_quadro', side_effect=[quadro, ValueError('JPEG invalido'), quadro]), patch.object(coletor, 'esperar', return_value=True):
                coletor.executar(args, RecorteESP32(0, 80, 320, 160), observar)
            self.assertEqual(estado.status()['quadros'], 2)
            self.assertEqual(estado.status()['falhas'], 1)
            self.assertFalse(estado.status()['falha'])
            self.assertEqual(json.loads((pasta/'sessao.json').read_text())['quadros'], 2)

    def test_parada_nao_inicia_captura(self):
        parar = threading.Event()
        parar.set()
        args = SimpleNamespace(sem_janela=True, duracao=None, quadros=None)
        with patch.object(coletor, 'receber_quadro') as receber:
            self.assertEqual(coletor.capturar(args, None, None, 0, parar=parar)[0], 0)
            receber.assert_not_called()

    def test_erro_de_gravacao_nao_publica_quadro(self):
        args = SimpleNamespace(sem_janela=True, duracao=None, quadros=1, timeout=1, url='http://camera/capture', saida=Path('/nao-existe'))
        with patch.object(coletor, 'receber_quadro', return_value=SimpleNamespace(jpeg=b'x')), patch.object(coletor, 'gravar_atomico', side_effect=OSError('disco cheio')):
            from unittest.mock import Mock
            observar = Mock()
            with self.assertRaises(OSError):
                coletor.capturar(args, None, Mock(), 0, observar)
            observar.assert_not_called()

    def test_http_status_e_jpeg_sem_cache(self):
        estado = Estado('sessao')
        for rota, esperado in [('/status', b'quadros'), ('/', b'GRAVANDO'), ('/quadro?v=1', b'original')]:
            estado.observar({'status': 'ok'}, b'original')
            h = object.__new__(Handler)
            h.estado, h.path, h.wfile = estado, rota, io.BytesIO()
            h.send_response = lambda codigo: self.assertEqual(codigo, 200)
            headers = {}
            h.send_header = lambda k, v: headers.update({k:v})
            h.end_headers = lambda: None
            h.do_GET()
            self.assertIn(esperado, h.wfile.getvalue())
            self.assertEqual(headers['Cache-Control'], 'no-store')


if __name__ == '__main__':
    unittest.main()
