"""Painel com fonte injetada: nenhum motor, serial ou camera fisica."""
import csv
from dataclasses import replace
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tools.painel_coleta import Coleta, Handler
from visao.esp32_cam import CameraESP32, receber_quadro
from test_esp32_fonte import HTTPFalso


class TestPainel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)/'dados'
        self.fonte = CameraESP32()
        self.q = receber_quadro(HTTPFalso(), 'http://falso/capture', 1)
        self.fonte._status, self.fonte._quadro, self.fonte._id = 'ok', self.q, 1
        self.coleta = Coleta(self.fonte, self.raiz, intervalo=0)
        self.coleta.receber(1, self.q)

    def tearDown(self):
        self.coleta.fechar()
        self.tmp.cleanup()

    def publicar(self, i=2):
        self.q = replace(self.q, recepcao_monotonica=time.monotonic())
        self.fonte._quadro, self.fonte._id, self.fonte._status = self.q, i, 'ok'
        self.coleta.receber(i, self.q)

    def test_inicia_sem_gravar_e_abrir_status_nao_cria_pasta(self):
        self.assertTrue(self.coleta.status()['camera_ok'])
        self.assertFalse(self.coleta.status()['gravando'])
        self.assertEqual(self.coleta.imagem(), self.q.jpeg)
        self.assertFalse(self.raiz.exists())

    def test_cliques_start_stop_e_nova_sessao(self):
        self.coleta.iniciar_gravacao()
        pasta = self.coleta.pasta
        self.coleta.iniciar_gravacao()  # clique duplicado nao cria duas sessoes
        self.assertEqual(self.coleta.pasta, pasta)
        self.publicar()
        self.assertEqual(self.coleta.status()['quadros'], 1)
        self.assertEqual((pasta/'quadros/quadro_000001.jpg').read_bytes(), self.q.jpeg)
        self.coleta.parar_gravacao()
        self.publicar(3)
        self.assertEqual(self.coleta.total, 1)
        self.assertTrue(self.coleta.status()['camera_ok'])
        self.assertEqual(json.loads((pasta/'sessao.json').read_text())['estado'], 'encerrada')
        with (pasta/'capturas.csv').open() as f:
            self.assertEqual(len(list(csv.DictReader(f))), 1)
        self.coleta.iniciar_gravacao()
        self.assertNotEqual(self.coleta.pasta, pasta)
        self.assertEqual(self.coleta.total, 0)

    def test_camera_desconectada_e_recuperacao(self):
        self.coleta.iniciar_gravacao()
        with self.fonte._cond:
            self.fonte._invalidar('erro')
        self.assertIsNone(self.coleta.imagem())
        self.assertFalse(self.coleta.status()['camera_ok'])
        self.coleta.parar_gravacao()
        with self.assertRaisesRegex(RuntimeError, 'Câmera'):
            self.coleta.iniciar_gravacao()
        self.publicar()
        self.coleta.iniciar_gravacao()
        self.publicar(3)
        self.assertEqual(self.coleta.total, 1)

    def test_vencido_nao_aparece_nem_e_gravado(self):
        self.coleta.iniciar_gravacao()
        velho = replace(self.q, recepcao_monotonica=time.monotonic()-1)
        self.coleta.receber(2, velho)
        self.assertFalse(self.coleta.status()['camera_ok'])
        self.assertIsNone(self.coleta.imagem())
        self.assertEqual(self.coleta.total, 0)

    def test_limite_duracao_fecha_arquivo_mas_mantem_previa(self):
        self.coleta.iniciar_gravacao()
        self.coleta.inicio -= 181
        self.publicar()
        self.assertFalse(self.coleta.status()['gravando'])
        self.assertTrue(self.coleta.status()['camera_ok'])

    def test_disco_cheio_nao_conta_como_salvo(self):
        self.coleta.iniciar_gravacao()
        with patch('tools.painel_coleta.gravar_atomico', side_effect=OSError('disco cheio')):
            with self.assertRaises(OSError):
                self.publicar()
        self.assertEqual(self.coleta.total, 0)

    def test_worker_encerra_sessao_em_erro_de_disco(self):
        self.coleta.iniciar_gravacao()
        with patch.object(self.fonte, 'proximo_jpeg_detalhado', return_value=(2, self.q)), patch('tools.painel_coleta.gravar_atomico', side_effect=OSError('disco cheio')):
            self.coleta.iniciar_worker()
            fim = time.monotonic()+1
            while not self.coleta.status()['erro'] and time.monotonic()<fim:
                time.sleep(.005)
            self.coleta.fim.set()
            self.coleta.thread.join(1)
        self.assertFalse(self.coleta.status()['gravando'])
        self.assertIn('disco cheio', self.coleta.status()['erro'])

    def requisicao(self, rota, metodo='GET', token='segredo'):
        h = object.__new__(Handler)
        h.coleta, h.token, h.path, h.wfile = self.coleta, 'segredo', rota, io.BytesIO()
        h.headers = {'X-Painel-Token': token}
        codigos, headers = [], {}
        h.send_response = codigos.append
        h.send_header = lambda k,v: headers.update({k:v})
        h.end_headers = lambda: None
        h.send_error = codigos.append
        getattr(h, 'do_'+metodo)()
        return codigos[0], h.wfile.getvalue(), headers

    def test_http_get_nao_grava_e_post_exige_token(self):
        codigo, html, headers = self.requisicao('/')
        self.assertEqual(codigo, 200)
        self.assertIn(b'Iniciar grava', html)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertFalse(self.coleta.status()['gravando'])
        self.assertEqual(self.requisicao('/iniciar', 'POST', 'errado')[0], 403)
        self.assertFalse(self.coleta.status()['gravando'])
        self.assertEqual(self.requisicao('/iniciar', 'POST')[0], 200)
        self.assertTrue(self.coleta.status()['gravando'])
        self.assertEqual(self.requisicao('/parar', 'POST')[0], 200)
        self.assertFalse(self.coleta.status()['gravando'])

    def test_http_quadro_indisponivel_nao_entrega_imagem_velha(self):
        self.assertEqual(self.requisicao('/quadro')[1], self.q.jpeg)
        with self.fonte._cond:
            self.fonte._invalidar('erro')
        self.assertEqual(self.requisicao('/quadro')[0], 503)

    def test_snapshot_jpeg_e_visao_mesmo_id_sem_novo_http(self):
        with patch('visao.esp32_cam.receber_quadro', side_effect=AssertionError('captura duplicada')):
            imagem = self.fonte.proximo_quadro_detalhado(0, 0)
            ident, q = self.fonte.proximo_jpeg_detalhado(0, 0)
        self.assertEqual(ident, imagem[0])
        self.assertIs(q.imagem, imagem[1])
        self.assertEqual(q.recepcao_monotonica, imagem[2]['recepcao_monotonica'])
        self.assertIsNone(self.fonte.proximo_jpeg_detalhado(ident, 0))
        with self.fonte._cond:
            self.fonte._invalidar('erro')
        self.assertIsNone(self.fonte.proximo_jpeg_detalhado(0, 0))

    def test_visao_e_gravacao_concorrentes_com_captura_unica(self):
        h = HTTPFalso()
        fonte = CameraESP32(opener=h, reconexao_s=.01)
        coleta = Coleta(fonte, self.raiz, intervalo=.01)
        fonte.iniciar()
        coleta.iniciar_worker()
        try:
            fim = time.monotonic()+2
            while not coleta.status()['camera_ok'] and time.monotonic()<fim:
                time.sleep(.005)
            coleta.iniciar_gravacao()
            fim = time.monotonic()+2
            ids=[]
            while coleta.total<3 and time.monotonic()<fim:
                a=fonte.proximo_quadro_detalhado(ids[-1] if ids else 0, .1)
                if a: ids.append(a[0])
            self.assertGreaterEqual(coleta.total, 3)
            self.assertGreater(len(set(ids)), 1)
            self.assertIsNotNone(coleta.imagem())
            coleta.parar_gravacao()
            self.assertIsNotNone(fonte.proximo_quadro_detalhado(0, .1))
        finally:
            coleta.fechar()
            fonte.parar()

    def test_painel_http_completo_com_botoes_e_reconexao(self):
        from urllib.request import urlopen, Request
        from urllib.error import HTTPError
        import re
        from tools.painel_coleta import Painel
        h = HTTPFalso()
        fonte = CameraESP32(opener=h, reconexao_s=.01)
        painel = Painel(fonte, self.raiz, host='127.0.0.1', porta=0)
        fonte.iniciar()
        painel.iniciar()
        url = 'http://127.0.0.1:' + str(painel.servidor.server_port)
        def get(rota):
            with urlopen(url+rota, timeout=2) as r:
                return r.read()
        def esperar(cond):
            fim=time.monotonic()+2
            while not cond() and time.monotonic()<fim:
                time.sleep(.01)
            self.assertTrue(cond())
        try:
            html = get('/').decode()
            token = re.search("'X-Painel-Token':'([^']+)'", html).group(1)
            esperar(lambda: json.loads(get('/status'))['camera_ok'])
            self.assertFalse(self.raiz.exists())
            def post(rota):
                with urlopen(Request(url+rota, method='POST', headers={'X-Painel-Token':token}), timeout=2) as r:
                    self.assertEqual(r.status, 200)
            post('/iniciar')
            esperar(lambda: painel.coleta.total > 0)
            self.assertEqual(get('/quadro'), h.dados)
            post('/parar')
            pasta = painel.coleta.pasta
            self.assertEqual(json.loads((pasta/'sessao.json').read_text())['estado'], 'encerrada')
            h.falhar = True
            esperar(lambda: not json.loads(get('/status'))['camera_ok'])
            with self.assertRaises(HTTPError) as erro:
                get('/quadro')
            self.assertEqual(erro.exception.code, 503)
            h.falhar = False
            esperar(lambda: json.loads(get('/status'))['camera_ok'])
            post('/iniciar')
            self.assertNotEqual(painel.coleta.pasta, pasta)
        finally:
            painel.parar()
            fonte.parar()

    def test_main_compartilha_fonte_e_para_motor_antes_do_painel(self):
        import main
        import config as cfg
        from estado import Modo
        for porta_ocupada in (False, True):
            eventos = []
            motor, tc, tv, voz, painel = Mock(), Mock(), Mock(), Mock(), Mock()
            motor.parar.side_effect = lambda **_: eventos.append('motor_parado')
            painel.parar.side_effect = lambda: eventos.append('painel_parado')
            voz.start.side_effect = RuntimeError('fim simulado')
            with patch.object(sys, 'argv', ['main.py', '--sem-arduino']), patch.object(cfg, 'REMOTO_BT_ATIVO', False), patch.object(main, 'ArduinoNulo', return_value=motor), patch.object(main, 'abrir_fonte', return_value=self.fonte), patch.object(main, 'ThreadControle', return_value=tc) as controle, patch.object(main, 'ThreadVisao', return_value=tv), patch.object(main, 'ThreadVoz', return_value=voz), patch.object(main.signal, 'signal'), patch('tools.painel_coleta.Painel', return_value=painel) as criar_painel:
                if porta_ocupada:
                    criar_painel.side_effect = OSError('porta ocupada')
                with self.assertRaisesRegex(RuntimeError, 'fim simulado'):
                    main.main()
                self.assertIs(controle.call_args.args[3], self.fonte)
                self.assertIs(criar_painel.call_args.args[0], self.fonte)
                self.assertEqual(controle.call_args.args[0].modo, Modo.PARADO)
                tc.start.assert_called_once()
                motor.fechar.assert_called_once()
                if not porta_ocupada:
                    painel.iniciar.assert_called_once()
                    self.assertLess(eventos.index('motor_parado'), eventos.index('painel_parado'))



if __name__ == '__main__':
    unittest.main()
