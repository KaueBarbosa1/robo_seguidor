"""Modo manual sem HC-SR04, com telemetria e serial simuladas."""
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import config as cfg
from controle import ThreadControle, aplicar_movimento_manual, aplicar_comando
from estado import EstadoRobo, Modo
from motor import protocolo as P
from motor.serial_com import ArduinoSerial, DecodificadorQuadros


class TestBluetoothSemUltrassom(unittest.TestCase):
    def setUp(self):
        self.tempo=100.
        p=patch('time.monotonic',side_effect=lambda:self.tempo);p.start();self.addCleanup(p.stop)
        for nome,valor in [('ULTRASSOM_BLUETOOTH_ATIVO',False),('CONTROLE_VELOCIDADE_ATIVO',True),
                           ('FIRMWARE_COM_CAMERA',False),('REMOTO_DIAGNOSTICO_MOVIMENTO',False)]:
            p=patch.object(cfg,nome,valor);p.start();self.addCleanup(p.stop)
        self.ard=ArduinoSerial();self.tx=[]
        self.ard._escrever=lambda pacote,repetir=1:self.tx.extend([pacote]*repetir)
        self.e=EstadoRobo();self.fim=threading.Event();self.t=ThreadControle(self.e,self.ard,self.fim)
        self.telemetria()

    def telemetria(self,manual=True,falha_encoder=False):
        self.ard._ao_sensores(P.DIST_SEM_LEITURA,0,0,127)
        self.ard._ao_motores(32,34,(64 if manual else 0)|(4 if falha_encoder else 0))

    def rodar(self,ciclos=1,renovar=True):
        n=0
        def dormir(_):
            nonlocal n
            n+=1;self.tempo+=.05
            if renovar:self.telemetria()
            if n>=ciclos:self.fim.set()
        with patch('controle.time.sleep',side_effect=dormir):self.t._loop()
        self.fim.clear()

    def test_callback_ignora_distancia_frente_laterais_e_nao_recuar(self):
        aplicar_movimento_manual(self.e,self.ard,120,70,validade_s=float('inf'))
        self.assertIn(P.comando_manual_sem_ultrassom(True),self.tx)
        self.assertEqual(self.tx[-1],P.comando_velocidade(4,2))
        self.assertFalse(self.t._recuar_manual(self.tempo,self.e.ler_manual()))
        self.assertFalse(self.t._lateral_bloqueada((120,70)))
        self.assertIsNone(self.t._recuo)

    def test_um_comando_bluetooth_mantem_marcha_por_dois_segundos_sem_eco(self):
        aplicar_movimento_manual(self.e,self.ard,120,120,validade_s=float('inf'))
        self.tx.clear()
        self.rodar(40)
        velocidades=[p for p in self.tx if p[1]==P.CMD_VELOCIDADE]
        self.assertEqual(len(velocidades),40)
        self.assertTrue(all(p==P.comando_velocidade(4,4) for p in velocidades))
        self.assertFalse(any(p[1]==P.CMD_PARAR for p in self.tx))
        self.assertFalse(any(p==P.comando_sonar_movimento() for p in self.tx))

    def test_espera_ack_sem_exigir_outro_comando_do_app(self):
        self.telemetria(manual=False)
        aplicar_movimento_manual(self.e,self.ard,120,120,validade_s=float('inf'))
        self.assertFalse(any(p[1]==P.CMD_VELOCIDADE for p in self.tx))
        self.telemetria(manual=True);self.tx.clear()
        self.rodar()
        self.assertIn(P.comando_velocidade(4,4),self.tx)

    def test_firmware_antigo_ou_ack_vencido_nao_recebe_velocidade(self):
        for manual,t in ((False,100.),(True,99.)):
            self.ard._manual_sem_ultrassom=True
            self.ard._motores=SimpleNamespace(timestamp=t,manual_sem_ultrassom=manual)
            self.tx.clear();self.ard.motores(120,120)
            self.assertFalse(any(p[1]==P.CMD_VELOCIDADE for p in self.tx))
            self.assertIn(P.comando_parar(),self.tx)

    def test_retorno_autonomo_exige_ack_desativado_e_frente_nova(self):
        aplicar_movimento_manual(self.e,self.ard,120,120)
        aplicar_comando(self.e,self.ard,'siga')
        self.assertIn(P.comando_manual_sem_ultrassom(False),self.tx)
        self.tx.clear();self.ard.motores(120,120)
        self.assertFalse(any(p[1]==P.CMD_VELOCIDADE for p in self.tx))
        self.assertTrue(self.t._obstaculo())
        self.tempo+=.01
        self.telemetria(manual=False)
        self.assertTrue(self.t._obstaculo())  # HC-SR04 ainda desconhecido
        self.ard._ao_sensores(80,0,0,0)
        self.assertFalse(self.t._obstaculo())
        self.tx.clear();self.ard.motores(120,120)
        self.assertEqual(self.tx[-1],P.comando_velocidade(28,28))

    def test_ack_inativo_anterior_a_saida_nao_libera_autonomo(self):
        self.ard.usar_manual_sem_ultrassom(True)
        self.ard._ao_motores(0,0,0)  # nao e confirmacao posterior ao comando de saida
        self.tempo+=.01
        self.ard.usar_manual_sem_ultrassom(False)
        self.tx.clear();self.ard.motores(120,120)
        self.assertFalse(any(p[1]==P.CMD_VELOCIDADE for p in self.tx))
        self.tempo+=.01;self.telemetria(manual=False)
        self.tx.clear();self.ard.motores(120,120)
        self.assertIn(P.comando_velocidade(28,28),self.tx)

    def test_telemetria_vencida_continua_parando(self):
        aplicar_movimento_manual(self.e,self.ard,120,120,validade_s=float('inf'))
        self.tempo+=1;self.tx.clear();self.rodar(renovar=False)
        self.assertEqual(self.t.motivo_parada,'telemetria_vencida')
        self.assertFalse(any(p[1]==P.CMD_VELOCIDADE for p in self.tx))

    def test_falha_encoder_continua_parando(self):
        aplicar_movimento_manual(self.e,self.ard,120,120,validade_s=float('inf'))
        self.telemetria(falha_encoder=True);self.tx.clear();self.rodar()
        self.assertEqual(self.t.motivo_parada,'falha_encoder')
        self.assertIn(P.comando_parar(),self.tx)
        self.assertFalse(any(p[1]==P.CMD_VELOCIDADE for p in self.tx))

    def test_timeout_bluetooth_e_pare_preservados(self):
        aplicar_movimento_manual(self.e,self.ard,120,120,validade_s=.1)
        self.tempo+=.2;self.telemetria();self.tx.clear();self.rodar()
        self.assertEqual(self.e.modo,Modo.PARADO)
        self.assertIn(P.comando_parar(),self.tx)
        aplicar_movimento_manual(self.e,self.ard,120,120)
        aplicar_comando(self.e,self.ard,'pare')
        self.assertEqual(self.e.modo,Modo.PARADO)
        self.assertEqual(self.tx[-1],P.comando_parar())
        self.assertIn(P.comando_manual_sem_ultrassom(False),self.tx)

    def test_f8_novo_preserva_flags_e_enquadramento(self):
        dec=DecodificadorQuadros(lambda _:None,ao_motores=self.ard._ao_motores)
        dec.alimentar(bytes([255,P.IDX_MOTORES,32,0,34,0,64|8|1]))
        d=self.ard.estado_motores()
        self.assertTrue(d.manual_sem_ultrassom and d.pi_ativo)
        self.assertEqual((d.pwm_esq,d.pwm_dir),(-32,34))

    def test_pwm_bancada_nao_aproveita_modo_manual(self):
        with self.assertRaises(RuntimeError):self.ard.pwm(40,40)


if __name__=='__main__':unittest.main()
