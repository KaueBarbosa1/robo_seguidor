"""Log da main sem Bluetooth, serial ou qualquer alteracao de movimento."""
from pathlib import Path
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg
from controle import ThreadControle
from estado import EstadoRobo
from motor import protocolo as P
from motor.serial_com import ArduinoSerial, DecodificadorQuadros


class TestDiagnosticoManual(unittest.TestCase):
    def setUp(self):
        self.s = SimpleNamespace(timestamp=100., avanco_bloqueado=False, falha_sensor=False,
                                 ticks_esq=12, ticks_dir=13, distancia_cm=144)
        self.d = SimpleNamespace(timestamp=100., pwm_esq=32, pwm_dir=34, falha_encoder=False)
        self.v = SimpleNamespace(timestamp=100., ativo=True, sonar_movimento=True, angulo_nominal=102)
        self.motor = SimpleNamespace(sensores=Mock(return_value=self.s),
                                     estado_motores=Mock(return_value=self.d),
                                     status_servo=Mock(return_value=self.v), motores=Mock(), parar=Mock())
        self.estado = EstadoRobo()
        self.controle = ThreadControle(self.estado, self.motor, threading.Event())
        self.manual = (120, 120, 100., None)

    def registrar(self, agora=100., motivo='pedido_movimento'):
        with patch.object(cfg, 'REMOTO_DIAGNOSTICO_MOVIMENTO', True), \
             patch.object(cfg, 'SONAR_MOVIMENTO_ATIVO', True), patch('controle.time.monotonic', return_value=agora):
            self.controle._diagnosticar_manual(self.manual, motivo)

    def test_log_mostra_pwm_e_guarda_sem_enviar_comandos(self):
        with self.assertLogs('controle', level='INFO') as logs:
            self.registrar()
        texto = '\n'.join(logs.output)
        self.assertIn('PWM E=32 D=34 falha_encoder=False', texto)
        self.assertIn('frente_bloqueada=False falha_sensor=False', texto)
        self.assertIn('encoders E=12 D=13', texto)
        self.assertIn('frente_cm=144 angulo_nominal=102', texto)
        self.motor.motores.assert_not_called()
        self.motor.parar.assert_not_called()
        self.assertIsNone(self.estado.ler_manual())

    def test_limita_log_repetido_e_registra_transicao_de_falha_imediatamente(self):
        with self.assertLogs('controle', level='INFO'):
            self.registrar()
        with self.assertNoLogs('controle', level='INFO'):
            self.registrar(100.01)
        self.d.falha_encoder = True
        with self.assertLogs('controle', level='INFO') as logs:
            self.registrar(100.02)
        self.assertIn('motivo=falha_encoder_no_arduino', logs.output[0])

    def test_publica_resumo_periodico_sem_mudar_motivo(self):
        with self.assertLogs('controle', level='INFO'):
            self.registrar()
        self.s.timestamp = self.d.timestamp = self.v.timestamp = 101.1
        with self.assertLogs('controle', level='INFO'):
            self.registrar(101.1)

    def test_dados_vencidos_ou_futuros_nao_sao_usados_como_confirmacao(self):
        for timestamp in (90., 101.):
            with self.subTest(timestamp=timestamp):
                self.controle._diagnostico_manual_chave = None
                self.s.timestamp = self.d.timestamp = self.v.timestamp = timestamp
                self.d.falha_encoder = True
                with self.assertLogs('controle', level='INFO') as logs:
                    self.registrar()
                self.assertIn('motivo=aguardando_manual_sem_ultrassom', logs.output[0])
                self.assertIn('falha_encoder=indisponivel', logs.output[0])
                self.assertIn('frente_bloqueada=indisponivel', logs.output[0])
                self.assertIn('frente_cm=indisponivel angulo_nominal=indisponivel', logs.output[0])

    def test_flag_desativa_diagnostico_e_nao_exige_novos_getters_no_motor(self):
        with patch.object(cfg, 'REMOTO_DIAGNOSTICO_MOVIMENTO', False), \
             self.assertNoLogs('controle', level='INFO'):
            self.controle._diagnosticar_manual(self.manual, 'pedido_movimento')
        self.motor.sensores.assert_not_called()
        self.controle._motor = SimpleNamespace()
        with self.assertLogs('controle', level='INFO') as logs:
            self.registrar()
        self.assertIn('indisponivel', logs.output[0])

    def test_motivos_simultaneos_e_validade_do_diagnostico(self):
        self.motor.guarda_sonar = Mock(return_value=(0x30, 100.))
        with self.assertLogs('controle', level='INFO') as logs:
            self.registrar()
        self.assertIn('guarda=limite_avanco+divergencia_rodas', logs.output[0])
        for timestamp in (90., 101.):
            self.motor.guarda_sonar.return_value = (0x30, timestamp)
            self.controle._diagnostico_manual_chave = None
            with self.assertLogs('controle', level='INFO') as logs:
                self.registrar()
            self.assertIn('guarda=indisponivel', logs.output[0])
        self.motor.guarda_sonar.return_value = (0, 100.)
        self.v.sonar_movimento = False
        with self.assertLogs('controle', level='INFO') as logs:
            self.registrar()
        self.assertIn('guarda=indisponivel', logs.output[0])

    def test_decoder_guarda_fragmentada_corrompida_e_opcional(self):
        ard = ArduinoSerial()
        self.assertIsNone(ard.guarda_sonar())
        dec = DecodificadorQuadros(lambda img: None, ao_guarda_sonar=ard._ao_guarda_sonar)
        with patch('motor.serial_com.time.monotonic', return_value=100.):
            dec.alimentar(bytes([P.SYNC, P.IDX_GUARDA_SONAR]))
            self.assertIsNone(ard.guarda_sonar())
            dec.alimentar(bytes([0x30]))
            self.assertEqual(ard.guarda_sonar(), (0x30, 100.))
            dec.alimentar(bytes([P.SYNC, P.IDX_GUARDA_SONAR, 0x80]))
            self.assertEqual(ard.guarda_sonar(), (0x30, 100.))
            dec.alimentar(bytes([P.SYNC, P.IDX_GUARDA_SONAR, 0]))
            self.assertEqual(ard.guarda_sonar(), (0, 100.))
        DecodificadorQuadros(lambda img: None).alimentar(bytes([P.SYNC, P.IDX_GUARDA_SONAR, 0]))


if __name__ == '__main__':
    unittest.main()
