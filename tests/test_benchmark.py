"""Benchmark com clocks/interfaces injetados; nenhuma serial física."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from monitoramento import Registro, ativar, medir
from monitoramento.benchmark import Benchmark
from monitoramento.sistema import Sistema
from monitoramento.telemetria import Telemetria
from estado import EstadoRobo, Modo
from motor.nulo import ArduinoNulo
from motor.serial_com import ArduinoSerial, Sensores, StatusServo
from tools.benchmark import exportar, executar


class TestRegistro(unittest.TestCase):
    def tearDown(self):
        ativar(None)

    def test_desabilitado_preserva_resultado_e_excecao(self):
        @medir('teste')
        def f(x):
            if x < 0:
                raise ValueError('original')
            return x*2
        self.assertEqual(f(3), 6)
        with self.assertRaisesRegex(ValueError, 'original'):
            f(-1)

    def test_memoria_limitada_e_percentis(self):
        r = Registro(3)
        for i in range(5):
            r.observar('t', i)
        tempos, _, descartes = r.drenar()
        self.assertEqual(tempos['t']['n'], 3)
        self.assertEqual(tempos['t']['mediana'], 3)
        self.assertAlmostEqual(tempos['t']['p95'], 3.9)
        self.assertEqual(descartes, 2)
        self.assertEqual(r.drenar()[0], {})

    def test_produtor_nao_aguarda_lock(self):
        r = Registro()
        with r.lock:
            r.observar('t', 1)
            r.contar('x')
            r.ciclo('controle', .05)
        self.assertEqual(r.descartados, 3)

    def test_jitter_e_periodo_por_clock(self):
        r = Registro()
        with patch('monitoramento.time.perf_counter', side_effect=[10., 10.06]):
            r.ciclo('controle', .05)
            r.ciclo('controle', .05)
        tempos, contadores, _ = r.drenar()
        self.assertAlmostEqual(tempos['controle.jitter_s']['media'], .01)
        self.assertEqual(contadores['controle.ciclos'], 2)

    def test_decorador_mede_excecao_sem_ocultar(self):
        r = Registro()
        ativar(r)
        @medir('teste_s')
        def f():
            raise RuntimeError('erro')
        with self.assertRaises(RuntimeError):
            f()
        self.assertEqual(r.drenar()[0]['teste_s']['n'], 1)

    def test_serial_registra_pedido_sem_confundir_com_aplicacao(self):
        r = Registro()
        ativar(r)
        serial = ArduinoSerial()
        # Sem conectar: registra intenção, mas não finge bytes transmitidos.
        serial.velocidade(4, -5)
        self.assertEqual(r.ler_pedidos()['referencia_pps_esq_dir']['valor'], (4, -5))
        self.assertNotIn('serial_tx_bytes', r.drenar()[1])

    def test_camera_instrumentada_sem_segunda_captura(self):
        from test_esp32_fonte import HTTPFalso
        from visao.esp32_cam import receber_quadro
        r = Registro()
        ativar(r)
        quadro = receber_quadro(HTTPFalso(), 'http://falso/capture', 1)
        tempos, contadores, _ = r.drenar()
        self.assertEqual(tempos['camera_decode_s']['n'], 1)
        self.assertEqual(contadores['camera_jpeg_rx_bytes'], len(quadro.jpeg))


class TestSistema(unittest.TestCase):
    def test_sem_psutil_e_sem_interfaces_produz_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            dados = Sistema(Path(tmp), ps=None).coletar()
        self.assertTrue(all(v is None for v in dados['valores'].values()))
        self.assertIn('psutil', dados['indisponiveis'])

    def test_flags_pi_temperatura_e_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz/'proc/device-tree').mkdir(parents=True)
            (raiz/'proc/device-tree/model').write_text('Raspberry Pi 5')
            zona = raiz/'sys/class/thermal/thermal_zone0'
            zona.mkdir(parents=True)
            (zona/'type').write_text('cpu-thermal')
            (zona/'temp').write_text('61000')
            with patch('monitoramento.sistema.subprocess.run',
                       return_value=Mock(stdout='throttled=0x50005')) as comando:
                dados = Sistema(raiz, ps=None).coletar()['valores']
            self.assertEqual(dados['temperatura_c'], 61.)
            self.assertTrue(dados['subtensao_atual'])
            self.assertTrue(dados['throttling_atual'])
            self.assertTrue(dados['subtensao_desde_boot'])
            self.assertEqual(comando.call_args.kwargs['timeout'], .2)
            with patch('monitoramento.sistema.subprocess.run', side_effect=FileNotFoundError):
                self.assertIsNone(Sistema(raiz, ps=None).coletar()['valores']['subtensao_atual'])


class TestTelemetria(unittest.TestCase):
    def test_snapshot_nao_escreve_motor_e_marca_ausencia(self):
        motor = Mock(spec=ArduinoNulo)
        motor.sensores.return_value = None
        motor.estatisticas = {}
        estado = EstadoRobo()
        dados = Telemetria(estado, motor).coletar()
        self.assertEqual(estado.modo, Modo.PARADO)
        self.assertEqual(dados['sensores']['distancia_cm']['estado'], 'indisponivel')
        motor.motores.assert_not_called()
        motor.parar.assert_not_called()

    def test_sensor_vencido_e_servo_comandado(self):
        motor = Mock()
        motor.estatisticas = {}
        motor.sensores.return_value = Sensores(10, 1, 2, 1.)
        motor.estado_motores.return_value = None
        motor.status_servo.return_value = StatusServo(90, 1500, False, True, True, 1.)
        with patch('monitoramento.telemetria.time.monotonic', return_value=2.):
            dados = Telemetria(motor=motor).coletar()
        self.assertEqual(dados['sensores']['distancia_cm']['estado'], 'desatualizado')
        self.assertEqual(dados['sensores']['angulo_servo_graus']['natureza'], 'comandado')
        self.assertIsNone(dados['motores']['sentido_medido']['valor'])

    def test_pps_nao_inventa_velocidade_em_dado_repetido(self):
        motor = Mock()
        motor.estatisticas = {}
        motor.estado_motores.return_value = motor.status_servo.return_value = None
        t = Telemetria(motor=motor)
        with patch('monitoramento.telemetria.time.monotonic', return_value=10.):
            motor.sensores.return_value = Sensores(100, 10, 20, 10.)
            self.assertIsNone(t.coletar()['motores']['pps_esq']['valor'])
            self.assertIsNone(t.coletar()['motores']['pps_esq']['valor'])
        with patch('monitoramento.telemetria.time.monotonic', return_value=10.1):
            motor.sensores.return_value = Sensores(100, 11, 22, 10.1)
            self.assertAlmostEqual(t.coletar()['motores']['pps_esq']['valor'], 10.)

    def test_motores_simulados_nao_rotulam_imagem_real_como_simulada(self):
        e = EstadoRobo()
        e.publicar_leitura(.1, True)
        dados = Telemetria(e, ArduinoNulo(), simulado=True).coletar()
        self.assertEqual(dados['visao']['erro']['natureza'], 'estimado')
        self.assertTrue(dados['simulado'])
        e.publicar_leitura(0., False, camera_ok=False)
        invalida = Telemetria(e, ArduinoNulo()).coletar()
        self.assertIsNone(invalida['visao']['erro']['valor'])
        self.assertIsNone(invalida['visao']['idade_ultima_leitura_s']['valor'])


class TestBenchmark(unittest.TestCase):
    def tearDown(self):
        ativar(None)

    def test_sessao_exportacao_e_metricas_ausentes(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = Benchmark(tmp, Telemetria(EstadoRobo(), ArduinoNulo(), simulado=True),
                          sistema=Mock(coletar=lambda: {}))
            pasta = b.iniciar()
            limite = time.monotonic()+3
            while b.amostras == 0 and time.monotonic() < limite:
                time.sleep(.01)
            b.parar()
            self.assertIsNone(b.erro)
            dados = json.loads((pasta/'amostras.jsonl').read_text().splitlines()[0])
            self.assertIsNone(dados['tempos_s']['cnn_s'])
            self.assertIsNone(dados['serial_rtt_s'])
            self.assertEqual(dados['sequencia'], 0)
            self.assertEqual(json.loads((pasta/'manifesto.json').read_text())['estado'], 'encerrado')
            self.assertIn('serial_rtt_s', exportar(pasta).read_text(encoding='utf-8-sig'))

    def test_falha_de_disco_isola_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = Benchmark(tmp, sistema=Mock(coletar=lambda: {}))
            abrir = Path.open
            def disco(path, *args, **kwargs):
                if path.name == 'amostras.jsonl':
                    raise OSError('disco cheio')
                return abrir(path, *args, **kwargs)
            with patch.object(Path, 'open', disco):
                b.iniciar()
                b.thread.join(2)
                b.parar()
            self.assertIn('disco cheio', b.erro)

    def test_limite_de_arquivo_para_apenas_benchmark(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = EstadoRobo()
            b = Benchmark(tmp, Telemetria(e, ArduinoNulo()), max_bytes=1024,
                          sistema=Mock(coletar=lambda: {}))
            pasta = b.iniciar()
            b.thread.join(2)
            b.parar()
            self.assertEqual(b.manifesto['estado'], 'limite_arquivo')
            self.assertEqual(e.modo, Modo.PARADO)
            self.assertLessEqual((pasta/'amostras.jsonl').stat().st_size, 1024)

    def test_cli_simulada_sem_abrir_serial_ou_movimentar(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(modo='simulado', saida=tmp, intervalo=1.,
                duracao=.15, fps=30., url='http://nao-usar', nota='teste')
            with (patch('motor.serial_com.ArduinoSerial.conectar', side_effect=AssertionError('serial proibida')),
                  patch.object(ArduinoNulo, 'motores', side_effect=AssertionError('movimento proibido'))):
                pasta = executar(args)
            self.assertTrue((pasta/'manifesto.json').exists())

    def test_main_com_benchmark_fecha_worker_apos_falha_de_inicio(self):
        import main
        import config as cfg
        motor, controle, visao, voz, benchmark = [Mock() for _ in range(5)]
        voz.start.side_effect = RuntimeError('fim de teste')
        with (patch.object(sys, 'argv', ['main.py', '--sem-arduino', '--fonte-imagem', 'nenhuma', '--benchmark']),
              patch.object(cfg, 'REMOTO_BT_ATIVO', False),
              patch.object(main, 'ArduinoNulo', return_value=motor),
              patch.object(main, 'ThreadControle', return_value=controle),
              patch.object(main, 'ThreadVisao', return_value=visao),
              patch.object(main, 'criar_thread_voz', return_value=voz),
              patch.object(main.signal, 'signal'),
              patch('monitoramento.benchmark.Benchmark', return_value=benchmark)):
            with self.assertRaisesRegex(RuntimeError, 'fim de teste'):
                main.main()
        benchmark.iniciar.assert_called_once()
        benchmark.parar.assert_called_once()
        self.assertEqual(controle.method_calls[0][0], 'start')
        motor.motores.assert_not_called()


if __name__ == '__main__':
    unittest.main()
