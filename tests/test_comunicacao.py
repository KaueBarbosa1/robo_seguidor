"""Rede localhost real com hardware falso. Nenhum ensaio da Raspberry."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed, InvalidStatus
from comunicacao.cliente import Cliente
from comunicacao.configuracao import Opcoes
from comunicacao.metricas import Metricas
from comunicacao.protocolo import (codificar, decodificar, envelope, Sequencia,
                                   empacotar_imagem, desempacotar_imagem)
from comunicacao.servidor import Servidor, oferecer
from comunicacao.amostras import Amostras
from comunicacao.simulacao import CameraSimulada, telemetria_simulada

TOKEN = 'token-de-teste-local-com-32-caracteres'


class AmostrasFalsas:
    def iniciar(self):
        pass
    def parar(self):
        pass
    def snapshot(self):
        return dict(schema='benchmark_robo_v1', telemetria=dict(simulado=True)), time.monotonic()


class CameraFalsa:
    idade_max_s = .5
    def __init__(self):
        self.chamadas = 0
        self.jpeg = b'\xff\xd8JPEG-original\xff\xd9'
    def proximo_jpeg_detalhado(self, ultimo, timeout=0):
        self.chamadas += 1
        return ultimo+1, SimpleNamespace(jpeg=self.jpeg, recepcao_monotonica=time.monotonic(),
                                        idade_recepcao_limite_ms=0.)


class TestProtocolo(unittest.TestCase):
    def test_envelope_json_e_rejeicoes(self):
        msg = envelope(str(uuid.uuid4()), 1, 'telemetria', {})
        self.assertEqual(decodificar(codificar(msg)), msg)
        for invalida in ('[]', '{}', '{"x":NaN}', '{"x":1e400}', '{"x":1,"x":2}', 'x'*70000):
            with self.subTest(invalida=invalida[:20]), self.assertRaises(ValueError):
                decodificar(invalida)
        for campo, valor in [('sequencia', True), ('versao', True), ('simulado', 1),
                             ('idade_envio_s', -1), ('sessao', 'outra'), ('validade_s', 0)]:
            with self.subTest(campo=campo), self.assertRaises(ValueError):
                decodificar(codificar(dict(msg, **{campo: valor})))

    def test_jpeg_original_e_limites(self):
        msg = envelope(str(uuid.uuid4()), 1, 'imagem', {})
        jpeg = b'\xff\xd8original\xff\xd9'
        pacote = empacotar_imagem(msg, jpeg, 4096, 4096)
        self.assertEqual(desempacotar_imagem(pacote, 4096, 4096)[1], jpeg)
        for invalido in (b'', b'\xff'*8, pacote[:-2]):
            with self.assertRaises(ValueError):
                desempacotar_imagem(invalido, 4096, 4096)

    def test_lacunas_duplicatas_e_sessao(self):
        s = Sequencia()
        msg = envelope(str(uuid.uuid4()), 4, 'telemetria', {})
        self.assertTrue(s.aceitar(msg))
        self.assertFalse(s.aceitar(msg))
        self.assertTrue(s.aceitar(dict(msg, sequencia=7)))
        self.assertEqual(s.lacunas, 2)
        self.assertFalse(s.aceitar(dict(msg, sessao=str(uuid.uuid4()), sequencia=8)))

    def test_configuracao_segura(self):
        for kw in (dict(host='0.0.0.0'), dict(host='8.8.8.8'), dict(token='curto'),
                   dict(fila=0), dict(telemetria_hz=float('nan')), dict(imagens_fps=1000)):
            with self.assertRaises(ValueError):
                Opcoes(**dict(dict(host='127.0.0.1', porta=0, token=TOKEN), **kw))


class TestRede(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.op = Opcoes('127.0.0.1', 0, TOKEN, telemetria_hz=30, imagens_fps=15,
                         heartbeat_s=.08, timeout_s=.5, reconexao_s=.05)
        self.servidores = []
        self.clientes = []

    async def asyncTearDown(self):
        for cliente, tarefa in self.clientes:
            cliente.parar()
            await asyncio.wait_for(tarefa, 2)
        for servidor in self.servidores:
            await asyncio.to_thread(servidor.parar)

    def servidor(self, falhas=None, camera=None, amostras=None):
        servidor = Servidor(self.op, amostras or AmostrasFalsas(), camera,
                            simulado=True, falhas=falhas)
        servidor.iniciar()
        self.servidores.append(servidor)
        return servidor

    def cliente(self, servidor, lento=0):
        cliente = Cliente(f'ws://127.0.0.1:{servidor.porta}', self.op, lento)
        tarefa = asyncio.create_task(cliente.executar())
        self.clientes.append((cliente, tarefa))
        return cliente

    async def esperar(self, condicao, prazo=3):
        async with asyncio.timeout(prazo):
            while not condicao():
                await asyncio.sleep(.01)

    async def test_conexao_duas_vias_telemetria_e_imagens_independentes(self):
        camera = CameraFalsa()
        s = self.servidor(camera=camera)
        c = self.cliente(s)
        await self.esperar(lambda: c.metricas['telemetria'].contas['telemetrias'] >= 4 and
                           c.metricas['imagens'].contas['frames'] >= 2)
        meta, jpeg, _ = await c.proxima('imagens')
        self.assertEqual(jpeg, camera.jpeg)
        self.assertTrue(meta['simulado'])
        self.assertTrue(c.metricas['telemetria'].snapshot()['rtt_s']['media'] >= 0)
        self.assertTrue(s.metricas.snapshot()['rtt_s']['media'] >= 0)
        self.assertLessEqual(c.telemetrias.qsize(), self.op.fila)

    async def test_sem_consumidor_nao_consulta_imagem(self):
        camera = CameraFalsa()
        s = self.servidor(camera=camera)
        await asyncio.sleep(.15)
        self.assertEqual(camera.chamadas, 0)
        async with connect(f'ws://127.0.0.1:{s.porta}/ws/telemetria',
                           additional_headers={'Authorization': 'Bearer '+TOKEN}):
            await asyncio.sleep(.15)
            self.assertEqual(camera.chamadas, 0)

    async def test_autenticacao_endpoint_e_comandos_recusados(self):
        s = self.servidor()
        for rota, token in [('/ws/telemetria', 'errado'), ('/serial', TOKEN)]:
            with self.assertRaises(InvalidStatus):
                async with connect(f'ws://127.0.0.1:{s.porta}'+rota,
                                   additional_headers={'Authorization': 'Bearer '+token}):
                    pass
        async with connect(f'ws://127.0.0.1:{s.porta}/ws/telemetria',
                           additional_headers={'Authorization': 'Bearer '+TOKEN}) as ws:
            ola = decodificar(await ws.recv())
            self.assertFalse(ola['dados']['comandos_habilitados'])
            await ws.send(codificar(envelope(s.sessao, 1, 'comando', {'motores': [200, 200]}, origem='computador')))
            with self.assertRaises(ConnectionClosed):
                while True:
                    await ws.recv()

    async def test_reconexao_nao_executa_comandos(self):
        s = self.servidor(falhas={'desconectar_s': .2})
        c = self.cliente(s)
        await self.esperar(lambda: c.metricas['telemetria'].contas['reconexoes'] >= 2)
        self.assertGreater(c.metricas['telemetria'].contas['telemetrias'], 0)
        self.assertFalse(hasattr(s, 'motor'))

    async def test_lacunas_e_json_invalido(self):
        s = self.servidor(falhas={'descartar_cada': 3, 'invalida_cada': 4})
        c = self.cliente(s)
        await self.esperar(lambda: c.metricas['telemetria'].contas['lacunas'] >= 1 and
                           c.metricas['telemetria'].contas['mensagens_invalidas'] >= 1)
        self.assertGreater(s.metricas.contas['descartes_injetados'], 0)

    async def test_congestionamento_fila_limitada(self):
        s = self.servidor(falhas={'atraso_s': .12}, camera=CameraFalsa())
        c = self.cliente(s)
        await self.esperar(lambda: s.metricas.contas['descartes_fila_telemetria'] > 2)
        self.assertTrue(all(x.fila.qsize() <= self.op.fila for x in s.consumidores))
        self.assertLessEqual(c.imagens.qsize(), self.op.fila)

    async def test_antigos_descartados_no_servidor(self):
        s = self.servidor(falhas={'atraso_s': .6})
        c = self.cliente(s)
        await self.esperar(lambda: s.metricas.contas['descartes_antigos_telemetria'] > 0)
        self.assertEqual(c.metricas['telemetria'].contas['telemetrias'], 0)

    async def test_consumidor_lento_nao_trava_outro_canal(self):
        s = self.servidor(camera=CameraFalsa())
        c = self.cliente(s, lento=.15)
        await asyncio.sleep(.7)
        self.assertGreater(s.metricas.contas['telemetrias'], c.metricas['telemetria'].contas['telemetrias'])
        self.assertLessEqual(c.telemetrias.qsize(), self.op.fila)
        self.assertGreater(s.metricas.contas['frames'], 0)

    async def test_timeout_sem_eco(self):
        sessao = str(uuid.uuid4())
        async def silencioso(ws):
            canal = ws.request.path.rsplit('/', 1)[-1]
            await ws.send(codificar(envelope(sessao, 0, 'ola', {'canal': canal}, simulado=True)))
            await ws.wait_closed()
        async with serve(silencioso, self.op.host, 0) as fake:
            p = fake.sockets[0].getsockname()[1]
            c = self.cliente(SimpleNamespace(porta=p))
            await self.esperar(lambda: c.metricas['telemetria'].contas['timeouts'] >= 1)

    async def test_camera_simulada_sem_serial(self):
        with patch('motor.serial_com.ArduinoSerial.conectar', side_effect=AssertionError('Hardware proibido')):
            camera = CameraSimulada()
            camera.iniciar()
            try:
                s = self.servidor(camera=camera,
                    amostras=Amostras(telemetria_simulada(camera), self.op.telemetria_hz))
                c = self.cliente(s)
                await self.esperar(lambda: c.metricas['imagens'].contas['frames'] > 0)
                msg, _, _ = await c.proxima('telemetria')
                self.assertTrue(msg['dados']['telemetria']['simulado'])
                self.assertEqual(msg['dados']['telemetria']['sensores']['angulo_servo_graus']['natureza'], 'simulado')
            finally:
                camera.parar()

    async def test_cliente_rejeita_antigos_duplicados_e_sessao_trocada(self):
        sessao = str(uuid.uuid4())
        async def falso(ws):
            canal = ws.request.path.rsplit('/', 1)[-1]
            await ws.send(codificar(envelope(sessao, 0, 'ola', {'canal': canal}, simulado=True)))
            primeira = True
            async for texto in ws:
                msg = decodificar(texto)
                await ws.send(codificar(envelope(sessao, 0, 'eco', msg['dados'], simulado=True)))
                if primeira and canal == 'telemetria':
                    primeira = False
                    dados = dict(schema='benchmark_robo_v1', telemetria={'simulado': True})
                    boa = envelope(sessao, 1, 'telemetria', dados, simulado=True)
                    velha = envelope(sessao, 4, 'telemetria', dados, simulado=True)
                    velha['monotonic_s'] -= 2
                    for item in (boa, boa, velha, envelope(str(uuid.uuid4()), 8, 'telemetria', dados, simulado=True)):
                        await ws.send(codificar(item))
        async with serve(falso, self.op.host, 0) as fake:
            c = self.cliente(SimpleNamespace(porta=fake.sockets[0].getsockname()[1]))
            await self.esperar(lambda: c.metricas['telemetria'].contas['descartes_antigos'] > 0 and
                               c.metricas['telemetria'].contas['mensagens_invalidas'] > 0)
            self.assertGreater(c.metricas['telemetria'].contas['duplicadas_ou_sessao_antiga'], 0)
            self.assertGreater(c.metricas['telemetria'].contas['lacunas'], 0)

    async def test_limite_de_conexoes_e_tamanho(self):
        s = self.servidor()
        conexoes = []
        try:
            for _ in range(self.op.max_clientes):
                ws = await connect(f'ws://127.0.0.1:{s.porta}/ws/telemetria',
                                   additional_headers={'Authorization': 'Bearer '+TOKEN})
                conexoes.append(ws)
                await ws.recv()
            with self.assertRaises(InvalidStatus):
                await connect(f'ws://127.0.0.1:{s.porta}/ws/imagens',
                              additional_headers={'Authorization': 'Bearer '+TOKEN})
            await conexoes[0].send('x'*(self.op.max_json+1))
            with self.assertRaises(ConnectionClosed):
                while True:
                    await conexoes[0].recv()
        finally:
            await asyncio.gather(*(w.close() for w in conexoes))

    async def test_encerramento_nao_deixa_thread_ou_cache_vivo(self):
        s = self.servidor(camera=CameraFalsa())
        c = self.cliente(s)
        await self.esperar(lambda: c.ultima is not None)
        await asyncio.to_thread(s.parar)
        await self.esperar(lambda: c.snapshot()['ultima_telemetria'] is None)
        self.assertFalse(s.thread.is_alive())

    async def test_consumidor_rejeita_cache_vencido(self):
        c = Cliente('ws://127.0.0.1:1', self.op)
        msg = envelope(str(uuid.uuid4()), 1, 'telemetria', {})
        msg['idade_limite_recepcao_s'] = 1.
        c.telemetrias.put_nowait((msg, None, time.monotonic()))
        with self.assertRaises(TimeoutError):
            await c.proxima('telemetria', timeout=.05)
        self.assertEqual(c.metricas['telemetria'].contas['descartes_antigos_consumidor'], 1)

    async def test_main_compartilha_camera_sem_mudar_motor(self):
        import main
        import config as cfg
        from visao.esp32_cam import CameraESP32
        camera = CameraESP32()
        motor, controle, visao, voz, servidor = [Mock() for _ in range(5)]
        voz.start.side_effect = RuntimeError('fim do teste')
        with (patch.dict('os.environ', {cfg.REDE_TOKEN_ENV: TOKEN}),
              patch.object(sys, 'argv', ['main.py', '--rede']),
              patch.object(cfg, 'REMOTO_BT_ATIVO', False), patch.object(cfg, 'PAINEL_COLETA_ATIVO', False),
              patch.object(main, 'ArduinoSerial', return_value=motor),
              patch.object(main, 'abrir_fonte', return_value=camera),
              patch.object(main, 'ThreadControle', return_value=controle) as criar_controle,
              patch.object(main, 'ThreadVisao', return_value=visao),
              patch.object(main, 'ThreadVoz', return_value=voz), patch.object(main.signal, 'signal'),
              patch('comunicacao.servidor.Servidor', return_value=servidor) as criar_servidor):
            with self.assertRaisesRegex(RuntimeError, 'fim do teste'):
                main.main()
        self.assertIs(criar_servidor.call_args.args[2], camera)
        self.assertEqual(criar_controle.call_args.args[0].modo.name, 'PARADO')
        motor.motores.assert_not_called()
        servidor.parar.assert_called_once()

    async def test_benchmark_reutilizado_sem_segunda_coleta_so(self):
        b = SimpleNamespace(ultima_amostra={'sistema': {'original': True}, 'monotonic_s': time.monotonic(),
                                          'tempos_s': {'opencv_s': {'n': 1}}})
        a = Amostras(SimpleNamespace(coletar=lambda: {'simulado': True}), benchmark=b)
        with patch('comunicacao.amostras.Sistema', side_effect=AssertionError('SO duplicado')):
            a.iniciar()
            await self.esperar(lambda: a.atual is not None)
            self.assertTrue(a.snapshot()[0]['sistema']['original'])
            a.parar()


if __name__ == '__main__':
    unittest.main()
