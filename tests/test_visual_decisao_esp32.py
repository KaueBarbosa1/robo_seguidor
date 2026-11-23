"""Prévia integrada: câmera/GUI injetadas; nenhuma serial ou atuação física."""
import csv
import io
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tools import testar_decisao_esp32 as ferramenta
from visao.esp32_cam import CameraESP32, QuadroESP32
from test_detector_tracejado import imagem
from test_esp32_fonte import HTTPFalso


class TestSimulador(unittest.TestCase):
    def setUp(self):
        self.tempo = 10.
        self.relogio = patch('time.monotonic', side_effect=lambda: self.tempo)
        self.relogio.start()
        self.fonte = CameraESP32()
        self.fonte._inicio = 9.5
        self.sim = ferramenta.SimuladorVisao(self.fonte)
    def tearDown(self):
        self.sim.encerrar()
        self.relogio.stop()
    def publicar(self, t, xs=(160,), idade_ms=1.):
        self.tempo = t
        with self.fonte._cond:
            self.fonte._id += 1
            self.fonte._validos += 1
            self.fonte._status = 'ok'
            self.fonte._quadro = QuadroESP32(b'', imagem(xs), t, '', 2., idade_ms)
        return self.sim.atualizar()
    def test_centro_esquerda_direita_e_motores_nulos(self):
        for i, (xs, nome) in enumerate([((80,), 'ESQUERDA'), ((160,), 'RETO'), ((240,), 'DIREITA')]):
            self.sim.tecla(ord('p'));self.sim.tecla(ord('p'))
            dados = self.publicar(10.1+i*.1, xs)
            self.assertEqual(dados['decisao'], nome)
            self.assertEqual(dados['motivo'], 'observada')
            self.assertTrue(dados['novo_frame'])
            self.assertEqual(self.sim.motor.ultimo, (0, 0))
            self.assertEqual(self.sim.motor.estatisticas['comandos'], 0)
    def test_sem_linha_inicial_fica_parado(self):
        dados = self.publicar(10.1, ())
        self.assertEqual(dados['decisao'], 'PARAR')
        self.assertFalse(dados['linha_visivel'])
    def test_vao_limitado_e_reaparecimento(self):
        self.publicar(10.1, (240,))
        dados = self.publicar(10.2, ())
        self.assertTrue(dados['estimada'])
        self.assertEqual(dados['decisao'], 'DIREITA')
        self.assertIsNone(dados['erro_horizontal'])
        dados = self.publicar(10.75, ())
        self.assertEqual(dados['decisao'], 'PARAR')
        self.assertEqual(dados['motivo'], 'linha_perdida')
        dados = self.publicar(10.85, (80,))
        self.assertEqual(dados['decisao'], 'ESQUERDA')
    def test_frames_repetidos_nao_inflam_fps_ou_renovam_idade(self):
        self.publicar(10.1)
        for t in (10.12, 10.16, 10.2):
            self.tempo=t;dados=self.sim.atualizar()
            self.assertFalse(dados['novo_frame'])
            self.assertEqual(self.sim.processados, 1)
            self.assertAlmostEqual(dados['fps_visao'], 1/(t-10.))
        self.assertGreater(dados['idade_frame_ms'], 90.)
    def test_expiracao_ou_desconexao_apaga_imagem_e_para(self):
        self.publicar(10.1)
        self.tempo=10.5;dados=self.sim.atualizar()
        self.assertEqual(dados['decisao'], 'PARAR')
        self.assertIsNone(self.sim.frame)
        self.assertIsNone(dados['idade_frame_ms'])
        self.assertIsNone(dados['frame_id'])
        self.assertEqual(dados['direcao'], 0.)
        self.publicar(10.6)
        with self.fonte._cond:self.fonte._invalidar('erro')
        self.tempo=10.61;dados=self.sim.atualizar()
        self.assertEqual(dados['camera'], 'erro')
        self.assertEqual(dados['decisao'], 'PARAR')
        self.assertIsNone(self.sim.frame)
        dados=self.publicar(10.7, ())
        self.assertEqual(dados['decisao'], 'PARAR')
    def test_ultrassom_simulado_bloqueia_e_exige_nova_observacao(self):
        self.publicar(10.1)
        for tecla in (ord('2'), ord('3')):
            self.sim.tecla(tecla);self.tempo+=.01
            dados=self.sim.atualizar()
            self.assertEqual(dados['decisao'], 'PARAR')
            self.assertEqual(dados['motivo'], 'obstaculo_ou_sensor')
        self.sim.tecla(ord('1'));self.tempo+=.01
        self.assertEqual(self.sim.atualizar()['decisao'], 'PARAR')
        self.assertEqual(self.publicar(10.2)['decisao'], 'RETO')
    def test_pausa_e_retomada_nao_usam_frame_anterior(self):
        self.publicar(10.1)
        self.sim.tecla(ord('p'));self.tempo=10.11
        self.assertEqual(self.sim.atualizar()['decisao'], 'PARAR')
        self.sim.tecla(ord('p'));self.tempo=10.12
        self.assertEqual(self.sim.atualizar()['decisao'], 'PARAR')
        self.assertEqual(self.publicar(10.2)['decisao'], 'RETO')
    def test_painel_mostra_dados_sem_alterar_frame(self):
        dados=self.publicar(10.1)
        original=self.sim.frame.copy()
        with patch.object(cv2,'putText',wraps=cv2.putText) as texto:
            painel=ferramenta.montar_painel(self.sim,dados)
        frases=' '.join(c.args[1] for c in texto.call_args_list)
        self.assertIn('NENHUM MOTOR REAL',frases)
        self.assertIn('ULTRASSOM SIMULADO',frases)
        self.assertIn('Decisao simulada: RETO',frases)
        self.assertIn('FPS captura/visao',frases)
        self.assertEqual(painel.shape,(390,750,3))
        np.testing.assert_array_equal(original,self.sim.frame)
    def test_painel_estimada_e_marcada_separadamente(self):
        self.publicar(10.1,(240,));dados=self.publicar(10.2,())
        with patch.object(cv2,'putText',wraps=cv2.putText) as texto:
            ferramenta.montar_painel(self.sim,dados)
        self.assertIn('ESTIMADA',[c.args[1] for c in texto.call_args_list])
    def test_estatisticas_tem_historico_numerico_limitado(self):
        medida=ferramenta.Medidas()
        for i in range(1000):medida.adicionar(float(i))
        medida.adicionar(None)
        self.assertEqual(len(medida.ultimas),600)
        self.assertEqual(medida.resumo()['amostras'],1000)
        self.assertEqual(medida.resumo()['media_ms'],499.5)


class TestExecucao(unittest.TestCase):
    def fonte(self):
        http=HTTPFalso()
        http.dados=cv2.imencode('.jpg',imagem())[1].tobytes()
        return CameraESP32(opener=http,reconexao_s=.01)
    def test_sem_janela_csv_e_encerramento_sem_serial(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho=Path(pasta)/'medicoes.csv'
            args=ferramenta.argumentos(['--sem-janela','--duracao','.2','--csv',str(caminho)])
            fonte=self.fonte()
            with patch.object(ferramenta,'montar_painel',side_effect=AssertionError('GUI proibida')), patch.object(cv2,'namedWindow',side_effect=AssertionError('GUI proibida')), patch('serial.Serial',side_effect=AssertionError('serial proibida')), redirect_stdout(io.StringIO()):
                resumo=ferramenta.executar(args,fonte)
            self.assertGreater(resumo['frames_processados'],0)
            self.assertIsNotNone(resumo['medidas']['http']['media_ms'])
            self.assertEqual(resumo['motores'],'NULOS')
            self.assertFalse(fonte._thread.is_alive())
            with caminho.open() as arq:linhas=list(csv.DictReader(arq))
            self.assertEqual(set(linhas[0]),set(ferramenta.CAMPOS))
            self.assertTrue(all(l['ultrassom_simulado']=='livre' for l in linhas))
    def test_nao_sobrescreve_csv_existente(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho=Path(pasta)/'preservar.csv';caminho.write_text('original')
            args=ferramenta.argumentos(['--sem-janela','--csv',str(caminho)])
            fonte=self.fonte()
            with patch.object(fonte,'iniciar') as iniciar, redirect_stdout(io.StringIO()):
                with self.assertRaises(FileExistsError):ferramenta.executar(args,fonte)
            iniciar.assert_not_called()
            self.assertEqual(caminho.read_text(),'original')
    def test_q_fecha_janela_e_fonte_com_gui_simulada(self):
        args=ferramenta.argumentos([]);fonte=self.fonte()
        with patch.object(cv2,'namedWindow'),patch.object(cv2,'imshow') as mostrar,patch.object(cv2,'waitKey',return_value=ord('q')),patch.object(cv2,'destroyAllWindows') as fechar,redirect_stdout(io.StringIO()):
            ferramenta.executar(args,fonte)
        mostrar.assert_called_once();fechar.assert_called_once()
        self.assertFalse(fonte._thread.is_alive())
    def test_excecao_gui_tambem_encerra(self):
        args=ferramenta.argumentos([]);fonte=self.fonte()
        with patch.object(cv2,'namedWindow'),patch.object(cv2,'imshow',side_effect=RuntimeError('GUI simulada')),patch.object(cv2,'destroyAllWindows') as fechar,redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError,'GUI simulada'):ferramenta.executar(args,fonte)
        fechar.assert_called_once();self.assertFalse(fonte._thread.is_alive())
    def test_argumentos_invalidos(self):
        for arg in (['--timeout','nan'],['--duracao','0'],['--duracao','inf']):
            with redirect_stdout(io.StringIO()),patch('sys.stderr',new=io.StringIO()):
                with self.assertRaises(SystemExit):ferramenta.argumentos(arg)

if __name__=='__main__':unittest.main()
