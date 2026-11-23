"""Recuo manual com relogio/telemetria simulados; nao aciona hardware."""
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg
from controle import ThreadControle, aplicar_comando, aplicar_movimento_manual
from estado import EstadoRobo, Modo


class Motor:
    def __init__(self):
        self.cmds = []
        self.s = SimpleNamespace(timestamp=100., distancia_cm=9, ticks_esq=20,
                                 ticks_dir=30, falha_sensor=False,
                                 avanco_bloqueado=True, obstaculo_confirmado=True)
        self.status = SimpleNamespace(timestamp=100., ativo=True, sonar_movimento=True)

    def sensores(self): return self.s
    def status_servo(self): return self.status
    def motores(self, e, d): self.cmds.append(('manual', e, d))
    def velocidade(self, e, d): self.cmds.append(('pps', e, d))
    def parar(self, repetir=1): self.cmds.append(('stop', 0, 0))


class RecuoManual(unittest.TestCase):
    def setUp(self):
        self.est, self.motor = EstadoRobo(), Motor()
        self.est.definir_manual(80, 80)
        self.t = ThreadControle(self.est, self.motor, threading.Event())

    def passo(self, agora):
        self.motor.s.timestamp = self.motor.status.timestamp = agora
        with self.est.lock:
            return self.t._recuar_manual(agora, self.est.ler_manual())

    def iniciar(self):
        self.assertTrue(self.passo(100.))
        self.assertEqual(self.motor.cmds[-1][0], 'stop')
        self.assertTrue(self.passo(100.16))
        self.assertEqual(self.motor.cmds[-1], ('pps', -4, -4))

    def test_parada_re_curta_e_sem_repeticao_ou_retomada(self):
        self.iniciar()
        self.passo(100.51)
        self.assertEqual(self.motor.cmds[-1][0], 'stop')
        self.motor.s.distancia_cm = 200
        for agora in (101., 102.):
            aplicar_movimento_manual(self.est, self.motor, 80, 80)
            self.assertEqual(self.motor.cmds[-1][0], 'stop')
            self.assertTrue(self.passo(agora))
        self.assertEqual(sum(c[0] == 'pps' for c in self.motor.cmds), 1)

    def test_pacote_repetido_nao_sobrescreve_re(self):
        self.iniciar()
        cmds = list(self.motor.cmds)
        aplicar_movimento_manual(self.est, self.motor, 80, 80)
        self.assertEqual(cmds, self.motor.cmds)
        self.passo(100.2)
        self.assertEqual(self.motor.cmds[-1][0], 'pps')

    def test_limite_de_pulsos_em_qualquer_roda(self):
        for lado in ('ticks_esq', 'ticks_dir'):
            with self.subTest(lado=lado):
                self.setUp()
                self.iniciar()
                setattr(self.motor.s, lado, getattr(self.motor.s, lado) + 2)
                self.passo(100.2)
                self.assertEqual(self.motor.cmds[-1][0], 'stop')
                self.assertIsNone(self.t._recuo)

    def test_reconexao_contadores_e_link_vencido_abortam(self):
        for falha in ('ticks_esq', 'sensor', 'status'):
            with self.subTest(falha=falha):
                self.setUp()
                self.iniciar()
                if falha == 'ticks_esq': self.motor.s.ticks_esq = 0
                if falha == 'sensor': self.motor.s.timestamp = 99.
                if falha == 'status': self.motor.status.timestamp = 99.
                self.t._recuar_manual(100.2, self.est.ler_manual())
                self.assertIsNone(self.t._recuo)
                self.assertEqual(self.motor.cmds[-1][0], 'stop')
                self.passo(100.21)
                self.assertIsNone(self.t._recuo)

    def test_frente_invalidada_pela_re_nao_exige_caminho_livre(self):
        self.iniciar()
        self.motor.s.falha_sensor = True
        self.motor.s.distancia_cm = None
        self.passo(100.2)
        self.assertEqual(self.motor.cmds[-1][0], 'pps')

    def test_neutro_ou_pare_cancela_e_rearma(self):
        for parar in ('neutro', 'voz'):
            with self.subTest(parar=parar):
                self.setUp()
                self.iniciar()
                if parar == 'neutro': aplicar_movimento_manual(self.est, self.motor, 0, 0)
                else: aplicar_comando(self.est, self.motor, 'pare')
                self.assertEqual(self.motor.cmds[-1][0], 'stop')
                self.passo(100.2)
                self.assertIsNone(self.t._recuo)
                aplicar_movimento_manual(self.est, self.motor, 80, 80)
                self.passo(101.)
                self.assertIsNotNone(self.t._recuo)

    def test_troca_para_re_manual_interrompe_automatico(self):
        self.iniciar()
        aplicar_movimento_manual(self.est, self.motor, -80, -80)
        self.assertFalse(self.passo(100.2))
        self.assertIsNone(self.t._recuo)

    def test_timeout_nao_rearma_e_nao_executa_no_seguidor(self):
        self.iniciar()
        self.est.definir_modo(Modo.PARADO)
        self.assertFalse(self.passo(100.2))
        self.est.definir_manual(80, 80)
        self.assertTrue(self.passo(101.))
        self.assertIsNone(self.t._recuo)
        self.est.definir_modo(Modo.SEGUINDO)
        self.assertFalse(self.passo(102.))

    def test_sem_confirmacao_ou_dado_valido_nao_recua(self):
        for campo, valor in (('obstaculo_confirmado', False), ('falha_sensor', True),
                             ('distancia_cm', None), ('distancia_cm', 25),
                             ('avanco_bloqueado', False)):
            with self.subTest(campo=campo, valor=valor):
                self.setUp()
                setattr(self.motor.s, campo, valor)
                self.assertFalse(self.passo(100.))
                self.assertFalse(self.motor.cmds)
        self.setUp()
        self.motor.status.sonar_movimento = False
        self.assertFalse(self.passo(100.))
        with patch.object(cfg, 'RECUO_MANUAL_ATIVO', False):
            self.motor.status.sonar_movimento = True
            self.assertFalse(self.passo(100.))

    def test_loop_corta_por_timeout_do_bluetooth(self):
        self.iniciar()
        self.est._manual = (80, 80, 90., .4)
        with patch('controle.time.monotonic', return_value=100.2), \
                patch('controle.time.sleep', side_effect=lambda _: self.t._parar.set()):
            self.t._loop()
        self.assertIs(self.est.modo, Modo.PARADO)
        self.assertIsNone(self.t._recuo)
        self.assertEqual(self.motor.cmds[-1][0], 'stop')

    def test_loop_manual_dispara_re_sem_ativar_seguidor(self):
        self.est._manual = (80, 80, 100., .4)
        with patch('controle.time.monotonic', return_value=100.), \
                patch('controle.time.sleep', side_effect=lambda _: self.t._parar.set()):
            self.t._loop()
        self.assertIsNotNone(self.t._recuo)
        self.assertIs(self.est.modo, Modo.MANUAL)
        self.assertEqual(self.motor.cmds[-1][0], 'stop')

    def test_saida_da_thread_interrompe_re(self):
        self.iniciar()
        with patch.object(self.t, '_loop'):
            self.t.run()
        self.assertEqual(self.motor.cmds[-1][0], 'stop')
        self.assertIsNone(self.t._recuo)


if __name__ == '__main__':
    unittest.main()
