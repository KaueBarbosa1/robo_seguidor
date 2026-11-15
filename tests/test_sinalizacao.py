"""Protocolo e encaminhamento da buzina, sem sockets ou hardware."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, call

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from estado import EstadoRobo
from motor import protocolo as P
from remoto.bluetooth_spp import SessaoRemota
from remoto.comandos import InterpretadorRemoto


class TestBuzina(unittest.TestCase):
    def test_botao_y_rearma_cada_toque_sem_mover(self):
        estado, motor = EstadoRobo(), Mock()
        modo = estado.modo
        sessao = SessaoRemota(Mock(), 'teste', estado, motor)
        interp = InterpretadorRemoto()
        for dados in (b'Y', b'Y'):
            comandos = interp.alimentar(dados)
            self.assertEqual(len(comandos), 1)
            sessao._tratar(comandos[0])
        self.assertEqual(motor.buzinar.call_args_list,
                         [call(False), call(True), call(False), call(True)])
        motor.motores.assert_not_called()
        motor.parar.assert_not_called()
        self.assertIs(estado.modo, modo)

    def test_protocolo_espelha_firmware(self):
        self.assertEqual(P.comando_buzina(True), bytes([0xAA, ord('H'), 1, 0, ord('H') ^ 1 ^ 0x5A]))
        self.assertEqual(P.comando_buzina(False), P.montar_comando(ord('H'), 0, 0))

    def test_texto_encaminha_sem_mover_ou_trocar_modo(self):
        estado, motor, sock = EstadoRobo(), Mock(), Mock()
        modo = estado.modo
        sessao = SessaoRemota(sock, 'teste', estado, motor)
        interp = InterpretadorRemoto()
        for dados, ligada in [(b'buzina\n', True), (b'buzina off\n', False)]:
            comandos = interp.alimentar(dados)
            self.assertEqual(len(comandos), 1)
            sessao._tratar(comandos[0])
            motor.buzinar.assert_called_with(ligada)
        motor.motores.assert_not_called()
        motor.parar.assert_not_called()
        self.assertIs(estado.modo, modo)


if __name__ == '__main__':
    unittest.main()

class TestAvisos(unittest.TestCase):
    def test_pacote_aviso(self):
        for tipo in (0, 1, 2):
            self.assertEqual(P.comando_aviso(tipo), P.montar_comando(ord('A'), tipo, 0))
        with self.assertRaises(ValueError):
            P.comando_aviso(3)

    def test_partida_e_cancelamento(self):
        from controle import aplicar_comando
        from estado import Modo
        import time
        estado, motor = EstadoRobo(), Mock()
        aplicar_comando(estado, motor, 'siga')
        self.assertGreater(estado._partida_ate, time.monotonic())
        motor.parar.assert_called()
        motor.avisar.assert_called_with(1)
        prazo = estado._partida_ate
        aplicar_comando(estado, motor, 'siga')
        self.assertEqual(estado._partida_ate, prazo)
        aplicar_comando(estado, motor, 'pare')
        motor.avisar.assert_called_with(0)
        self.assertEqual(estado._partida_ate, 0)
        self.assertIs(estado.modo, Modo.PARADO)
