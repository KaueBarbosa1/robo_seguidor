"""Contrato do comando de velocidade, sem hardware."""
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg
from motor import protocolo as P
from motor.serial_com import ArduinoSerial, DecodificadorQuadros
from tools import testar_velocidade as ferramenta


class TestVelocidade(unittest.TestCase):
    def test_pacote_assinado(self):
        self.assertEqual(P.comando_velocidade(-40, 60),
                         P.montar_comando(ord("R"), -40, 60))

    def test_rejeita_fora_da_faixa_e_fracao(self):
        for valor in (-121, 121, 1.5, True):
            with self.assertRaises(ValueError):
                P.comando_velocidade(valor, 0)

    def test_pwm_explicito_preserva_unidade_com_pi_ativo(self):
        ard = ArduinoSerial()
        ard._escrever = Mock()
        with patch.object(cfg, 'CONTROLE_VELOCIDADE_ATIVO', True):
            ard.pwm(30, -30)
        ard._escrever.assert_called_once_with(P.comando_motores(30, -30))
        for valor in (-255, 255, 1.5, True):
            with self.assertRaises(ValueError):
                ard.pwm(valor, 0)

    def test_pwm_explicito_nao_envia_em_contexto_sonar(self):
        ard = ArduinoSerial()
        ard._escrever = Mock()
        ard._sonar_manual = True
        with self.assertRaises(RuntimeError):
            ard.pwm(30, 30)
        ard._sonar_manual = False
        ard._servo = SimpleNamespace(sonar_movimento=True)
        with self.assertRaises(RuntimeError):
            ard.pwm(30, 30)
        ard._escrever.assert_not_called()

    def test_diagnostico_fragmentado_preserva_sensores_e_flags(self):
        ard = ArduinoSerial()
        dec = DecodificadorQuadros(lambda _: None, ao_motores=ard._ao_motores, ao_sensores=ard._ao_sensores)
        dados = bytes([255, P.IDX_MOTORES, 80, 0, 34, 0, P.MOTORES_FLAG_PI | P.MOTORES_FLAG_REFORCO_ESQ,
                       255, P.IDX_SENSORES, 80, 0, 1, 0, 2, 0, 0])
        for b in dados:
            dec.alimentar(bytes([b]))
        d = ard.estado_motores()
        self.assertEqual((d.pwm_esq, d.pwm_dir), (80, 34))
        self.assertTrue(d.pi_ativo and d.reforco_esq)
        self.assertFalse(d.falha_encoder or d.reforco_dir)
        self.assertEqual(ard.sensores().distancia_cm, 80)
        dec.alimentar(bytes([255, P.IDX_MOTORES, 52, 1, 0, 1,
                             P.MOTORES_FLAG_NEG_ESQ | P.MOTORES_FLAG_NEG_DIR | P.MOTORES_FLAG_PI]))
        self.assertEqual((ard.estado_motores().pwm_esq, ard.estado_motores().pwm_dir), (-180, -128))
        dec.alimentar(bytes([255, P.IDX_MOTORES, 0, 0, 0, 0, P.MOTORES_FLAG_FALHA_ENCODER]))
        self.assertTrue(ard.estado_motores().falha_encoder)
        self.assertFalse(ard.estado_motores().pi_ativo)

    def test_diagnostico_corrompido_ressincroniza_e_callback_opcional(self):
        recebidos = []
        dec = DecodificadorQuadros(lambda _: None, ao_motores=lambda *d: recebidos.append(d))
        dec.alimentar(bytes([255, P.IDX_MOTORES, 0, 2, 0, 0, 0,
                             255, P.IDX_MOTORES, 32, 0, 34, 0, P.MOTORES_FLAG_PI]))
        self.assertEqual(recebidos, [(32, 34, P.MOTORES_FLAG_PI)])
        sensores = []
        antigo = DecodificadorQuadros(lambda _: None, ao_sensores=lambda *s: sensores.append(s))
        antigo.alimentar(bytes([255, P.IDX_MOTORES, 32, 0, 34, 0, 8,
                                255, P.IDX_SENSORES, 80, 0, 0, 0, 0, 0, 0]))
        self.assertEqual(sensores, [(80, 0, 0, 0)])


class TestFerramentaVelocidade(unittest.TestCase):
    def executar(self, argumentos, perder_telemetria=False, falha_encoder=False, diagnostico_atrasado=False):
        relogio, ticks, enviados = [0.], [0], []
        def dormir(segundos):
            relogio[0] += segundos
        def sensores():
            if perder_telemetria and any(p[1] == P.CMD_MOTORES for p in enviados):
                return None
            if any(p[1] in (P.CMD_MOTORES, P.CMD_VELOCIDADE) for p in enviados):
                ticks[0] += 1
            return SimpleNamespace(timestamp=relogio[0], ticks_esq=ticks[0], ticks_dir=ticks[0],
                                   falha_sensor=False, avanco_bloqueado=False)
        ard = ArduinoSerial()
        ard.conectar, ard.fechar = Mock(), Mock()
        ard.sensores = sensores
        ard._escrever = lambda p, repetir=1: enviados.extend([p] * repetir)
        if falha_encoder:
            ard.estado_motores = lambda: SimpleNamespace(
                timestamp=relogio[0] - (cfg.SENSOR_TIMEOUT_S + 1 if diagnostico_atrasado else 0),
                pwm_esq=0, pwm_dir=0, falha_encoder=True, pi_ativo=False, reforco_esq=False, reforco_dir=False)
        saida = StringIO()
        with patch.object(ferramenta, 'ArduinoSerial', return_value=ard), \
             patch.object(ferramenta, 'time', SimpleNamespace(monotonic=lambda: relogio[0], sleep=dormir)), \
             patch.object(cfg, 'FIRMWARE_COM_CAMERA', False), \
             patch.object(cfg, 'CONTROLE_VELOCIDADE_ATIVO', True), \
             patch('builtins.input', return_value='s'), \
             patch.object(sys, 'argv', ['teste', *argumentos, '--tempo', '.6']), redirect_stdout(saida):
            if perder_telemetria or (falha_encoder and not diagnostico_atrasado):
                with self.assertRaisesRegex(RuntimeError, 'falha de encoder' if falha_encoder else 'Telemetria vencida'):
                    ferramenta.main()
            else:
                ferramenta.main()
        ard.fechar.assert_called_once()
        self.assertEqual(enviados[-3:], [P.comando_parar()] * 3)
        return enviados, saida.getvalue()

    def test_cli_pwm_envia_m_sem_conversao_e_mostra_unidade(self):
        enviados, saida = self.executar(['--pwm', '30'])
        self.assertIn(P.comando_motores(30, 30), enviados)
        self.assertFalse(any(p[1] == P.CMD_VELOCIDADE for p in enviados))
        self.assertIn('PWM direto 30 | E ', saida)

    def test_cli_pps_preserva_comando_r(self):
        enviados, saida = self.executar(['--pps', '4'])
        self.assertIn(P.comando_velocidade(4, 4), enviados)
        self.assertFalse(any(p[1] == P.CMD_MOTORES for p in enviados))
        self.assertIn('Alvo 4 p/s | E ', saida)

    def test_cli_perda_de_telemetria_para_e_fecha(self):
        self.executar(['--pwm', '30'], perder_telemetria=True)

    def test_cli_falha_encoder_confirmada_para_e_fecha(self):
        self.executar(['--pps', '4'], falha_encoder=True)

    def test_cli_diagnostico_vencido_nao_afirma_causa_da_parada(self):
        _, saida = self.executar(['--pps', '4'], falha_encoder=True, diagnostico_atrasado=True)
        self.assertIn('diagnostico de motores indisponivel/vencido', saida)

    def test_cli_partida_seguida_de_pwm_sustentacao(self):
        enviados, saida = self.executar(['--pwm', '40', '--pwm-partida', '60'])
        self.assertIn(P.comando_motores(60, 60), enviados)
        self.assertIn(P.comando_motores(40, 40), enviados)
        self.assertIn('Primeiro pulso E:', saida)
        self.assertIn('PWM direto 40 | E ', saida)

    def test_cli_perda_na_partida_fecha_serial(self):
        self.executar(['--pwm', '40', '--pwm-partida', '60'], perder_telemetria=True)

    def test_cli_rejeita_partida_sem_pwm_ou_fora_dos_limites(self):
        for args in [['--pwm-partida', '60'], ['--pwm', '40', '--pwm-partida', '30'],
                     ['--pwm', '40', '--pwm-partida', '59'], ['--pwm', '40', '--pwm-partida', '122'],
                     ['--pwm', '0', '--pwm-partida', '60']]:
            with self.subTest(args=args), patch.object(sys, 'argv', ['teste', *args]), \
                 patch.object(ferramenta, 'ArduinoSerial') as fabrica, redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as erro:
                    ferramenta.main()
                self.assertEqual(erro.exception.code, 2)
                fabrica.assert_not_called()


class TestPartidaPwm(unittest.TestCase):
    def simular(self, amostras, erro=None, passo=.02):
        relogio, indice = [0.], [0]
        ard = SimpleNamespace(pwm=Mock(), parar=Mock(), estatisticas={'reconexoes': 0})
        def sensores():
            item = amostras[min(indice[0], len(amostras) - 1)]
            indice[0] += 1
            if item == 'ausente':
                return None
            if item == 'reconexao':
                ard.estatisticas['reconexoes'] += 1
            ticks = item if isinstance(item, tuple) else (0, 0)
            return SimpleNamespace(timestamp=relogio[0] + (.1 if item == 'futuro' else 0),
                                   ticks_esq=ticks[0], ticks_dir=ticks[1], falha_sensor=False,
                                   avanco_bloqueado=item == 'bloqueado')
        def dormir(_):
            relogio[0] += passo
        ard.sensores = sensores
        with patch.object(ferramenta, 'time', SimpleNamespace(monotonic=lambda: relogio[0], sleep=dormir)), \
             redirect_stdout(StringIO()):
            if erro:
                with self.assertRaisesRegex(RuntimeError, erro):
                    ferramenta.partir_pwm(ard, 60, 40)
                ard.parar.assert_called_once_with(repetir=3)
            else:
                ferramenta.partir_pwm(ard, 60, 40)
                ard.parar.assert_not_called()
        return ard

    def test_reduz_cada_roda_no_seu_primeiro_pulso(self):
        ard = self.simular([(0, 0), (1, 0), (2, 1)])
        self.assertEqual([c.args for c in ard.pwm.call_args_list], [(60, 60), (40, 60), (40, 40)])

    def test_sem_pulsos_aborta_apos_um_segundo_sem_repetir_partida(self):
        self.simular([(0, 0)], erro='Sem primeiro pulso em 1 s: E, D')

    def test_roda_que_partiu_nao_recebe_novo_reforco_se_outra_nao_partir(self):
        ard = self.simular([(0, 0), (1, 0)], erro='Sem primeiro pulso em 1 s: D')
        self.assertTrue(all(c.args == (40, 60) for c in ard.pwm.call_args_list[1:]))

    def test_telemetria_bloqueio_e_reconexao_interrompem(self):
        for item, mensagem in [('ausente', 'Telemetria vencida'), ('futuro', 'Telemetria vencida'),
                               ('bloqueado', 'Frente bloqueada'), ('reconexao', 'Reconexao serial')]:
            with self.subTest(item=item):
                self.simular([(0, 0), item], erro=mensagem)

    def test_regressao_de_contador_interrompe(self):
        self.simular([(0, 0), (2, 0), (1, 0)], erro='Contadores regrediram')

    def test_primeiro_pulso_tardio_nao_rearma_movimento(self):
        ard = self.simular([(0, 0), (1, 1)], erro='Sem primeiro pulso em 1 s', passo=1.1)
        self.assertEqual([c.args for c in ard.pwm.call_args_list], [(60, 60)])


if __name__ == "__main__":
    unittest.main()
