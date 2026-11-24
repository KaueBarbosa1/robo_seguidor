"""Seguranca e ferramenta isolada com relogio, serial e motores falsos."""
import contextlib
import io
from pathlib import Path
import sys
import threading
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg
from controle import ThreadControle, aplicar_movimento_manual, aplicar_comando
from estado import EstadoRobo, Modo
from tools import testar_motores as ferramenta


class Motor:
    def __init__(self):
        self.cmds = []
        self.s = NS(timestamp=100., distancia_cm=80, falha_sensor=False,
                    avanco_bloqueado=False, obstaculo_confirmado=False,
                    ticks_esq=10, ticks_dir=20)
        self.d = NS(timestamp=100., falha_encoder=False, pwm_esq=0, pwm_dir=0)
        self.v = NS(timestamp=100., ativo=True, sonar_movimento=True)
        self.estatisticas = {"reconexoes": 0}
    def sensores(self): return self.s
    def estado_motores(self): return self.d
    def status_servo(self): return self.v
    def motores(self, e, d): self.cmds.append(("manual", e, d))
    def pwm(self, e, d): self.cmds.append(("pwm", e, d))
    def velocidade(self, e, d): self.cmds.append(("pps", e, d))
    def parar(self, repetir=1): self.cmds.append(("stop", 0, 0))
    def usar_sonar_manual(self, ativo): pass
    def iniciar_sonar_movimento(self): pass
    def configurar_servo(self, *a): pass
    def obstaculo(self, *a): return False


# Perfil legado explicitamente habilitado para verificar sua compatibilidade.
@patch.object(cfg, "ULTRASSOM_BLUETOOTH_ATIVO", True)
class Seguranca(unittest.TestCase):
    def setUp(self):
        self.agora = 100.
        self.relogio = patch("controle.time.monotonic", side_effect=lambda: self.agora)
        self.relogio.start(); self.addCleanup(self.relogio.stop)
        self.proibido = patch("motor.serial_com.serial.Serial",
                              side_effect=AssertionError("Serial fisica proibida"))
        self.proibido.start(); self.addCleanup(self.proibido.stop)
        self.est, self.m = EstadoRobo(), Motor()
        self.t = ThreadControle(self.est, self.m, threading.Event())
    def passo(self):
        self.t._parar.clear()
        with patch.object(cfg, "RECUO_MANUAL_ATIVO", False), \
             patch.object(cfg, "INSPECAO_OBSTACULO_ATIVA", False), \
             patch("controle.time.sleep", side_effect=lambda _: self.t._parar.set()):
            self.t._loop()
    def livre(self):
        self.agora += .05
        self.m.s.timestamp = self.m.d.timestamp = self.m.v.timestamp = self.agora
        self.m.s.avanco_bloqueado = self.m.s.falha_sensor = False
        self.m.s.obstaculo_confirmado = False
        self.m.s.distancia_cm = 80
    def comando(self): aplicar_movimento_manual(self.est, self.m, 40, 40, validade_s=float("inf"))
    def test_bloqueio_libera_sensor_sem_repetir_pedido(self):
        self.comando()
        self.m.s.avanco_bloqueado = self.m.s.obstaculo_confirmado = True
        self.passo()
        self.assertEqual(self.t.motivo_parada, "obstaculo")
        self.livre(); self.passo()
        self.assertEqual(self.t.motivo_parada, "aguardando_novo_comando")
        self.assertEqual(self.m.cmds[-1][0], "stop")
        self.comando()
        self.assertEqual(self.m.cmds[-1], ("manual", 40, 40))
    def test_comando_durante_bloqueio_nao_fica_para_depois(self):
        self.m.s.avanco_bloqueado = True
        self.comando()
        self.livre(); self.passo()
        self.assertFalse(any(c[0] == "manual" for c in self.m.cmds))
    def test_novo_comando_apos_liberacao_nao_precisa_de_ciclo(self):
        self.m.s.avanco_bloqueado = True; self.comando()
        self.livre(); self.comando()
        self.assertEqual(self.m.cmds[-1], ("manual", 40, 40))
    def test_eco_invalido_bloqueia_tambem_envio_imediato_v4(self):
        for distancia, falha in ((None, True), (None, False), (float("nan"), False)):
            self.m.s.distancia_cm, self.m.s.falha_sensor = distancia, falha
            self.comando(); self.passo()
            self.assertEqual(self.t.motivo_parada, "eco_invalido")
        self.assertFalse(any(c[0] == "manual" for c in self.m.cmds))
    def test_telemetria_ausente_vencida_futura(self):
        for timestamp in (99., 101.):
            self.m.s.timestamp = timestamp
            self.comando(); self.passo()
            self.assertEqual(self.t.motivo_parada, "telemetria_vencida")
    def test_encoder_nao_rearma_sozinho_apos_S(self):
        self.comando(); self.m.d.falha_encoder = True; self.passo()
        self.assertEqual(self.t.motivo_parada, "falha_encoder")
        self.m.d.falha_encoder = False
        self.livre(); self.passo()
        self.assertEqual(self.t.motivo_parada, "falha_encoder")
        self.comando()
        self.assertEqual(self.m.cmds[-1], ("manual", 40, 40))
    def test_encoder_sem_confirmacao_recente_nao_rearma(self):
        self.m.d.falha_encoder = True; self.comando()
        self.m.d.falha_encoder = False; self.m.d.timestamp = 99.
        self.comando()
        self.assertEqual(self.m.cmds[-1][0], "stop")
    def test_recuo_concluido_libera_flag_mas_descarta_comando(self):
        self.est.definir_manual(40, 40, float("inf"))
        self.est._recuo_bloqueia_avanco = True
        self.passo()
        self.assertFalse(self.est._recuo_bloqueia_avanco)
        self.assertEqual(self.t.motivo_parada, "aguardando_novo_comando")
        self.comando()
        self.assertEqual(self.m.cmds[-1], ("manual", 40, 40))
    def test_parada_manual_prioritaria(self):
        self.comando(); aplicar_comando(self.est, self.m, "pare"); self.passo()
        self.assertEqual(self.est.modo, Modo.PARADO)
        self.assertEqual(self.t.motivo_parada, "modo_PARADO")
        self.assertEqual(self.m.cmds[-1][0], "stop")
    def test_lateral_bloqueada_requer_novo_comando(self):
        self.m.s.lateral_dir_bloqueada = True
        aplicar_movimento_manual(self.est, self.m, 50, 30)
        self.assertEqual(self.m.cmds[-1][0], "stop")
        self.m.s.lateral_dir_bloqueada = False
        self.passo()
        self.assertEqual(self.t.motivo_parada, "aguardando_novo_comando")
    def test_re_manual_nao_e_bloqueada_por_obstaculo_frontal(self):
        self.m.s.avanco_bloqueado = True
        aplicar_movimento_manual(self.est, self.m, -30, -30)
        self.assertEqual(self.m.cmds[-1], ("manual", -30, -30))
    def test_retomada_autonoma_exige_observacao_posterior_a_liberacao(self):
        self.est.definir_modo(Modo.SEGUINDO); self.m.v = None
        self.est.publicar_leitura(0., True, timestamp=self.agora)
        self.m.s.avanco_bloqueado = True
        self.passo()
        self.agora += .05; self.m.s.timestamp = self.agora
        self.m.s.avanco_bloqueado = False
        self.passo()
        self.assertEqual(self.m.cmds[-1][0], "stop")
        self.agora += .02; self.m.s.timestamp = self.agora
        self.est.publicar_leitura(0., False, timestamp=self.agora)
        self.passo()
        self.assertEqual(self.m.cmds[-1][0], "stop")
        self.agora += .02; self.m.s.timestamp = self.agora
        self.est.publicar_leitura(0., True, timestamp=self.agora)
        self.passo()
        self.assertEqual(self.m.cmds[-1][0], "manual")
    def test_sem_camera_ou_linha_inicial_nao_avanca(self):
        self.est.definir_modo(Modo.SEGUINDO); self.m.v = None
        self.passo()
        self.assertEqual(self.m.cmds[-1][0], "stop")


    def test_retomada_com_acao_legada_tambem_exige_linha(self):
        self.est.definir_modo(Modo.SEGUINDO); self.m.v = None
        with patch.object(cfg, "APRENDIZADO_ATIVO", True):
            self.m.s.avanco_bloqueado = True
            self.passo()
            self.agora += .05; self.m.s.timestamp = self.agora
            self.m.s.avanco_bloqueado = False
            self.est.publicar_acao(.5, 1.)
            self.passo()
            self.assertEqual(self.m.cmds[-1][0], "stop")
            self.agora += .02; self.m.s.timestamp = self.agora
            self.est.publicar_leitura(0., True, timestamp=self.agora)
            self.est.publicar_acao(.5, 1.)
            self.passo()
            self.assertEqual(self.m.cmds[-1][0], "manual")


class Ferramenta(unittest.TestCase):
    def args(self, *extra):
        return ferramenta.argumentos(["--roda", "esquerda", *extra])
    def test_limites_rejeitados_antes_de_abrir_serial(self):
        for extra in (["--pwm","61"], ["--pwm","41"], ["--pps","5"],
                      ["--pwm","40","--tempo","inf"], ["--pwm","40","--tempo","nan"],
                      ["--pwm","40","--tempo","0"], ["--pwm","40","--tempo","1.1"],
                      ["--pwm","40","--pps","2"]):
            with self.subTest(extra=extra), contextlib.redirect_stderr(io.StringIO()), \
                 self.assertRaises(SystemExit):
                self.args(*extra)
    def test_servico_ativo_ou_consulta_inconclusiva_recusa(self):
        for r in (NS(returncode=0, stdout="active", stderr=""),
                  NS(returncode=1, stdout="", stderr="D-Bus indisponivel")):
            with patch.object(ferramenta.subprocess, "run", return_value=r), self.assertRaises(RuntimeError):
                ferramenta.verificar_exclusividade("/dev/falsa")
    def test_checa_dois_escopos_e_serial(self):
        rs = [NS(returncode=3, stdout="inactive", stderr="") for _ in range(2)]
        with patch.object(ferramenta.Path, "exists", return_value=True), \
             patch.object(ferramenta.subprocess, "run", side_effect=rs+[NS(returncode=1, stdout="", stderr="")]) as run:
            ferramenta.verificar_exclusividade("/dev/falsa")
            self.assertIn("--user", run.call_args_list[1].args[0])
        with patch.object(ferramenta.Path, "exists", return_value=True), \
             patch.object(ferramenta.subprocess, "run", side_effect=rs+[NS(returncode=0, stdout="123", stderr="")]), \
             self.assertRaises(RuntimeError):
            ferramenta.verificar_exclusividade("/dev/falsa")
    def test_pwm_e_pps_uma_roda_ambos_sentidos(self):
        for roda in ("esquerda", "direita"):
            for sentido in ("frente", "re"):
                for unidade, valor in (("pwm", 40), ("pps", 4)):
                    with self.subTest(roda=roda, sentido=sentido, unidade=unidade):
                        m = Motor(); agora = [100.]
                        a = ferramenta.argumentos(["--roda",roda,"--sentido",sentido,
                                                  "--"+unidade,str(valor),"--tempo",".06"])
                        def dormir(_):
                            agora[0] += .02; m.s.timestamp = m.d.timestamp = agora[0]
                        with patch.object(ferramenta.time,"monotonic",side_effect=lambda:agora[0]), \
                             patch.object(ferramenta.time,"sleep",side_effect=dormir), \
                             contextlib.redirect_stdout(io.StringIO()):
                            ferramenta.executar_pulso(m,a)
                        v=valor if sentido=="frente" else -valor
                        esperado=(v,0) if roda=="esquerda" else (0,v)
                        self.assertTrue(any(c == (unidade,*esperado) for c in m.cmds))
                        self.assertTrue(all(c[0] in (unidade,"stop") for c in m.cmds))
                        self.assertEqual(m.cmds[-1][0],"stop")
    def test_excecao_durante_pulso_envia_parada(self):
        m=Motor();m.pwm=Mock(side_effect=RuntimeError("envio falhou"))
        with patch.object(ferramenta.time,"monotonic",return_value=100.), self.assertRaises(RuntimeError):
            ferramenta.executar_pulso(m,self.args("--pwm","40"))
        self.assertEqual(m.cmds[-1][0],"stop")
    def test_falha_conectar_e_interrupcao_fecham_serial_falsa(self):
        for erro in (RuntimeError("conexao"),KeyboardInterrupt()):
            m=Mock();m.conectar.side_effect=erro
            with patch.object(ferramenta,"verificar_exclusividade"), \
                 patch.object(ferramenta,"ArduinoSerial",return_value=m), \
                 patch("builtins.input",return_value="s"), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertIn(ferramenta.main(["--roda","esquerda","--pwm","40"]), (2,130))
            m.parar.assert_called();m.fechar.assert_called_once()


    def test_reconexao_ou_sensor_invalido_durante_pulso_para(self):
        for falha in ("reconexao", "sensor", "encoder"):
            m=Motor();agora=[100.]
            def dormir(_):
                agora[0] += .02;m.s.timestamp=m.d.timestamp=agora[0]
                if falha=="reconexao": m.estatisticas["reconexoes"] += 1
                elif falha=="sensor": m.s.falha_sensor=True
                else: m.d.falha_encoder=True
            with patch.object(ferramenta.time,"monotonic",side_effect=lambda:agora[0]), \
                 patch.object(ferramenta.time,"sleep",side_effect=dormir), self.assertRaises(RuntimeError):
                ferramenta.executar_pulso(m,self.args("--pwm","40"))
            self.assertEqual(m.cmds[-1][0],"stop")

    def test_falha_ao_parar_ainda_fecha_recurso(self):
        m=Mock();m.conectar.side_effect=RuntimeError("conexao")
        m.parar.side_effect=OSError("serial indisponivel")
        with patch.object(ferramenta,"verificar_exclusividade"), \
             patch.object(ferramenta,"ArduinoSerial",return_value=m), \
             patch("builtins.input",return_value="s"), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
             self.assertRaises(OSError):
            ferramenta.main(["--roda","esquerda","--pwm","40"])
        m.fechar.assert_called_once()


if __name__ == "__main__":
    unittest.main()
