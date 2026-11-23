"""Etapa 3: decisões e captura injetada, sem serial, áudio, rede ou motores reais."""
import sys
import time
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock

import cv2
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as cfg
from estado import EstadoRobo, Modo
from controle import ThreadControle, aplicar_comando, aplicar_movimento_manual, calcular_motores
from visao.detector import ThreadVisao, DetectorLinha
from visao.esp32_cam import CameraESP32, receber_quadro
from test_detector_tracejado import imagem
from test_esp32_fonte import HTTPFalso


class CameraFalsa:
    idade_max_s = .3
    def __init__(self):
        self.status, self.geracao = 'ok', 0
    def saude(self): return dict(status=self.status, geracao=self.geracao)
    def proximo_quadro_detalhado(self, *_a, **_k): return None


class MotorFalso:
    def __init__(self):
        self.cmds = []
        self.eventos = []
        self.distancia = 50
        self.falha = False
        self.status = None
    def motores(self, e, d): self.cmds.append((e, d))
    def parar(self, repetir=1):
        self.cmds.append((0, 0)); self.eventos.append('parar')
    def sensores(self):
        return SimpleNamespace(timestamp=time.monotonic(), distancia_cm=self.distancia,
                               falha_sensor=self.falha, avanco_bloqueado=False)
    def status_servo(self): return self.status
    def obstaculo(self, *_): return False
    def conectar(self): self.eventos.append('conectar')
    def fechar(self): self.eventos.append('fechar')


class TestDecisao(unittest.TestCase):
    def setUp(self):
        self.e = EstadoRobo(); self.e.definir_modo(Modo.SEGUINDO)
        self.m = MotorFalso(); self.f = CameraFalsa(); self.stop = threading.Event()
        self.c = ThreadControle(self.e, self.m, self.stop, self.f)
        self.n = 0
    def publicar(self, t, visivel=True, erro=.4, **kw):
        self.n += 1
        dados = dict(timestamp=t, frame_id=self.n, geracao_camera=self.f.geracao,
                     camera_ok=True, confianca=1., motivo='observada' if visivel else 'sem_linha')
        dados.update(kw)
        self.e.publicar_leitura(erro, visivel, **dados)
    def decidir(self, t, bloqueado=False):
        with self.e.lock: return self.c.decidir_linha(t, bloqueado)
    def parado(self, d): self.assertEqual((d.esq, d.dir), (0, 0))
    def test_nunca_avanca_sem_observacao_inicial(self):
        self.parado(self.decidir(10.))
        for t in (10.1, 10.3, 10.7):
            self.publicar(t, False)
            self.parado(self.decidir(t+.01))
        self.publicar(11.)
        self.assertGreater(self.decidir(11.01).esq, 0)
    def test_pd_e_ganhos_preservados_e_direcao_considerada(self):
        self.assertEqual((cfg.KP, cfg.KD, cfg.KD_FILTRO), (90., 25., 1.))
        self.publicar(10.)
        d = self.decidir(10.01)
        self.assertEqual((d.esq, d.dir), calcular_motores(.4, 0.))
        self.publicar(10.1, erro=0., direcao=.3, escala_direcao=.75)
        self.assertGreater(self.decidir(10.11).erro, 0.)
        self.assertEqual(self.m.cmds, [])  # cálculo não aciona saída
    def test_vao_limitado_desacelera_e_nao_renova_observacao(self):
        self.publicar(10.); observado = self.decidir(10.01)
        for t in (10.1, 10.3, 10.55):
            self.publicar(t, False)
            d = self.decidir(t+.01)
            self.assertTrue(d.estimada)
            self.assertGreater(d.esq, 0)
            self.assertLess(d.esq, observado.esq)
            self.assertEqual(self.c._linha_ultima.timestamp, 10.)
        self.publicar(10.61, False)
        d = self.decidir(10.62); self.parado(d)
        self.assertEqual(d.motivo, 'linha_perdida')
        self.publicar(10.7, False); self.parado(self.decidir(10.71))
    def test_frame_antigo_nao_usa_tolerancia_do_tracejado(self):
        self.publicar(10.); self.decidir(10.01)
        d = self.decidir(10.31); self.parado(d)
        self.assertEqual(d.motivo, 'frame_vencido')
        self.publicar(10.4, False); self.parado(self.decidir(10.41))
    def test_idade_total_inclui_esp_e_http(self):
        self.publicar(10., idade_captura_s=.25)
        d = self.decidir(10.1); self.parado(d)
        self.assertEqual(d.motivo, 'frame_vencido')
        self.publicar(11., idade_captura_s=.1); self.decidir(11.01)
        self.publicar(11.51, False); self.parado(self.decidir(11.52))
    def test_camera_falha_independente_da_publicacao_da_visao(self):
        self.publicar(10.); self.decidir(10.01)
        self.f.status = 'erro'
        d = self.decidir(10.02); self.parado(d)
        self.assertEqual(d.motivo, 'camera_indisponivel')
    def test_recuperacao_entre_ciclos_nao_reaproveita_memoria(self):
        self.publicar(10.); self.decidir(10.01)
        self.f.geracao += 1  # falha e recuperação antes do próximo ciclo
        self.publicar(10.1, False)
        self.parado(self.decidir(10.11))
        self.publicar(10.2, erro=-.3)
        d = self.decidir(10.21); self.assertLess(d.esq, d.dir)
    def test_resultado_de_geracao_antiga_e_descartado(self):
        self.publicar(10.); self.f.geracao += 1
        self.parado(self.decidir(10.01))
    def test_modo_pare_siga_e_publicacao_atrasada(self):
        self.publicar(10.); self.decidir(10.01)
        antiga = self.e.sessao_visao
        aplicar_comando(self.e, self.m, 'pare')
        self.e.definir_modo(Modo.SEGUINDO)
        self.assertFalse(self.e.publicar_leitura(.4, True, sessao=antiga))
        self.parado(self.decidir(10.1))
        self.publicar(10.2, False); self.parado(self.decidir(10.21))
    def test_manual_prevalece_e_nao_recebe_resultado_visual_atrasado(self):
        antiga = self.e.sessao_visao
        aplicar_movimento_manual(self.e, self.m, 50, 60)
        self.assertFalse(self.e.publicar_leitura(.4, True, sessao=antiga))
        self.parado(self.decidir(10.))
        self.assertEqual(self.m.cmds[-1], (50, 60))
    def test_bloqueio_exige_nova_observacao_apos_liberar(self):
        self.publicar(10.); self.decidir(10.01)
        self.parado(self.decidir(10.1, True))
        self.parado(self.decidir(10.11))
        self.publicar(10.2, False); self.parado(self.decidir(10.21))
        self.publicar(10.3); self.assertGreater(self.decidir(10.31).esq, 0)
    def test_ambiguidade_baixa_confianca_e_numeros_invalidos_param(self):
        for kw in (dict(confianca=.1), dict(erro=float('nan')),
                   dict(direcao=float('inf')), dict(idade_captura_s=-.1),
                   dict(confianca=float('nan'))):
            self.publicar(10., **kw); self.parado(self.decidir(10.01))
        self.publicar(11.); self.decidir(11.01)
        self.publicar(11.1, False, motivo='trajetorias_ambiguas')
        self.parado(self.decidir(11.11))
    def test_reaparecimento_zera_derivada_apos_vao(self):
        self.publicar(10.); self.decidir(10.01)
        self.publicar(10.1, False); self.decidir(10.11)
        self.publicar(10.2, erro=-.4)
        d = self.decidir(10.21)
        self.assertEqual((d.esq, d.dir), calcular_motores(-.4, 0.))
    def test_sensor_invalido_bloqueia_seguir_e_manual_v4(self):
        self.m.falha = True; self.m.distancia = None
        self.m.status = SimpleNamespace(ativo=True, sonar_movimento=True, timestamp=time.monotonic())
        self.assertTrue(self.c._obstaculo())
        self.e.definir_manual(50, 50)
        self.assertTrue(self.c._obstaculo())
        aplicar_movimento_manual(self.e, self.m, 50, 50)
        self.assertEqual(self.m.cmds[-1], (0, 0))  # nem o callback imediato avanca sem eco
        self.e.definir_modo(Modo.SEGUINDO); self.m.falha = False
        for distancia in (None, float('nan'), -1):
            self.m.distancia = distancia; self.assertTrue(self.c._obstaculo())
    def test_acao_legada_nao_substitui_validacao_esp32(self):
        self.publicar(10.)
        with patch.object(cfg, 'APRENDIZADO_ATIVO', True):
            self.parado(self.decidir(10.01))
    def test_ultrassom_vencido_e_modo4_ainda_ativo_bloqueiam_seguir(self):
        with patch.object(self.m, 'sensores', return_value=None):
            self.assertTrue(self.c._obstaculo())
        antigo = SimpleNamespace(timestamp=time.monotonic()-1, distancia_cm=50,
                                 falha_sensor=False, avanco_bloqueado=False)
        with patch.object(self.m, 'sensores', return_value=antigo):
            self.assertTrue(self.c._obstaculo())
        self.m.status = SimpleNamespace(ativo=True, sonar_movimento=True, timestamp=time.monotonic())
        self.assertTrue(self.c._obstaculo())
    def test_encerramento_recusa_comandos_tardios(self):
        self.e.encerrar()
        aplicar_movimento_manual(self.e, self.m, 100, 100)
        aplicar_comando(self.e, self.m, 'siga')
        aplicar_comando(self.e, self.m, 'voltar')
        self.assertEqual(self.m.cmds, [])
        self.assertEqual(self.e.modo, Modo.PARADO)
        self.assertFalse(self.e.publicar_leitura(.4, True))
        self.assertFalse(self.e.publicar_acao(.4))
    def test_encerramento_e_excecao_sempre_param(self):
        self.publicar(10.); self.stop.set(); self.parado(self.decidir(10.01))
        self.c.run(); self.assertEqual(self.m.cmds[-1], (0, 0))
        self.stop.clear()
        with patch.object(self.c, '_loop', side_effect=RuntimeError('falha simulada')), self.assertLogs('controle', level='ERROR'):
            self.c.run()
        self.assertTrue(self.stop.is_set())
        self.assertEqual(self.m.cmds[-1], (0, 0))


class TestPublicacao(unittest.TestCase):
    def setUp(self):
        self.e = EstadoRobo(); self.e.definir_modo(Modo.SEGUINDO)
        self.f = CameraFalsa(); self.stop = threading.Event()
        self.v = ThreadVisao(self.e, self.stop, self.f)
        self.d = DetectorLinha(True)
        self.meta = dict(recepcao_monotonica=10., idade_captura_s=.02, geracao_camera=0)
    def test_publica_metadados_sem_renovar_recebimento(self):
        with patch('visao.detector.time.monotonic', return_value=10.05):
            r = self.v._processar_detalhado(self.d, (7, imagem(), self.meta), self.e.sessao_visao)
        self.assertTrue(r.achou)
        l = self.e.ler_leitura()
        self.assertEqual((l.timestamp, l.frame_id), (10., 7))
        self.assertAlmostEqual(l.idade(10.1), .12)
        self.assertEqual(l.escala_direcao, .75)
    def test_falha_ou_pare_durante_processamento_descarta_resultado(self):
        original = self.d.processar
        for evento in ('camera', 'modo'):
            def processar(a):
                r = original(a)
                if evento == 'camera': self.f.geracao += 1
                else: self.e.definir_modo(Modo.PARADO)
                return r
            with patch('visao.detector.time.monotonic', return_value=10.05), patch.object(self.d, 'processar', side_effect=processar):
                self.assertIsNone(self.v._processar_detalhado(self.d, (7, imagem(), self.meta), self.e.sessao_visao))
            self.assertFalse(self.e.ler_leitura().linha_visivel)
            self.f.geracao = 0; self.e.definir_modo(Modo.SEGUINDO)
    def test_frame_velho_nem_e_processado(self):
        with patch('visao.detector.time.monotonic', return_value=11.), patch.object(self.d, 'processar') as processar:
            self.assertIsNone(self.v._processar_detalhado(self.d, (7, imagem(), self.meta), self.e.sessao_visao))
            processar.assert_not_called()
        self.assertFalse(self.e.ler_leitura().camera_ok)


class TestIntegracaoSemHardware(unittest.TestCase):
    def esperar(self, cond, prazo=2.):
        limite = time.monotonic()+prazo
        while not cond() and time.monotonic() < limite: time.sleep(.005)
        self.assertTrue(cond())
    def test_http_falso_visao_estado_pd_vãos_falha_e_retomada(self):
        h = HTTPFalso(); h.dados = cv2.imencode('.jpg', imagem())[1].tobytes()
        fonte = CameraESP32(opener=h, reconexao_s=.02)
        e=EstadoRobo();e.definir_modo(Modo.SEGUINDO)
        m=MotorFalso();stop=threading.Event()
        v=ThreadVisao(e, stop, fonte);c=ThreadControle(e,m,stop,fonte)
        fonte.iniciar();v.start();c.start()
        try:
            self.esperar(lambda: c.decisao_linha.motivo == 'observada')
            self.assertTrue(any(a != (0,0) for a in m.cmds))
            h.falhar=True;self.esperar(lambda: fonte.status == 'erro')
            self.esperar(lambda: c.decisao_linha.motivo == 'camera_indisponivel')
            h.dados=cv2.imencode('.jpg', imagem(()))[1].tobytes()
            h.falhar=False
            self.esperar(lambda: fonte.status == 'ok')
            time.sleep(.08);self.assertEqual((c.decisao_linha.esq,c.decisao_linha.dir),(0,0))
            h.dados=cv2.imencode('.jpg', imagem((230,)))[1].tobytes()
            self.esperar(lambda: c.decisao_linha.motivo == 'observada')
            self.assertGreater(c.decisao_linha.esq,c.decisao_linha.dir)
            h.dados=cv2.imencode('.jpg', imagem(()))[1].tobytes()
            self.esperar(lambda: c.decisao_linha.estimada)
            self.esperar(lambda: c.decisao_linha.esq == c.decisao_linha.dir == 0)
        finally:
            stop.set();c.join(2);v.join(2);fonte.parar()
        self.assertFalse(c.is_alive() or v.is_alive())
        self.assertEqual(m.cmds[-1],(0,0))
    def test_main_recusa_cnn_incompativel_antes_de_criar_motor(self):
        import main
        with patch.object(sys, 'argv', ['main.py', '--fonte-imagem', 'esp32']), patch.object(cfg, 'APRENDIZADO_ATIVO', True), patch.object(main, 'ArduinoSerial') as serial, patch.object(main, 'ArduinoNulo') as nulo:
            with self.assertRaises(SystemExit) as erro: main.main()
            self.assertEqual(erro.exception.code, 2)
            serial.assert_not_called(); nulo.assert_not_called()
    def test_snapshot_atomico_e_geracao_da_fonte(self):
        f=CameraESP32();q=receber_quadro(HTTPFalso(),'http://falso/capture',1)
        with f._cond:
            f._status='ok';f._quadro=q;f._id=1
        a=f.proximo_quadro_detalhado(0,0)
        self.assertIs(a[1],q.imagem)
        self.assertEqual(a[2]['recepcao_monotonica'],q.recepcao_monotonica)
        with f._cond: f._invalidar('erro')
        self.assertGreater(f.saude()['geracao'],a[2]['geracao_camera'])
        self.assertIsNone(f.metadados(1))
    def test_main_falha_parcial_para_antes_de_join_e_fecha_recursos(self):
        import main
        m=MotorFalso();fonte=Mock()
        tc=Mock();tv=Mock();voz=Mock()
        tc.join.side_effect=lambda **_: m.eventos.append('join')
        voz.start.side_effect=RuntimeError('falha inicial simulada')
        with patch.object(sys,'argv',['main.py','--sem-arduino','--fonte-imagem','esp32']), patch.object(cfg,'REMOTO_BT_ATIVO',False), patch.object(main,'ArduinoNulo',return_value=m), patch.object(main,'ArduinoSerial',side_effect=AssertionError('serial proibida')), patch.object(main,'abrir_fonte',return_value=fonte), patch.object(main,'ThreadControle',return_value=tc), patch.object(main,'ThreadVisao',return_value=tv), patch.object(main,'ThreadVoz',return_value=voz), patch.object(main.signal,'signal'):
            with self.assertRaisesRegex(RuntimeError,'falha inicial'):main.main()
        self.assertLess(m.eventos.index('parar'),m.eventos.index('join'))
        self.assertIn('fechar',m.eventos);fonte.parar.assert_called_once()

if __name__ == '__main__': unittest.main()
