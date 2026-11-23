"""Modo 4 e calibracao: sem serial, motores, Bluetooth ou hardware reais."""
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg
from controle import ThreadControle, aplicar_comando, aplicar_movimento_manual
from estado import EstadoRobo
from estado import Modo
from motor import protocolo as P
from motor.serial_com import ArduinoSerial, DecodificadorQuadros
from tools import calibrar_encoders, testar_sonar_movimento as ferramenta


def test_protocolo_modo4_e_calibracao_sem_mudar_pacote_antigo():
    ard = ArduinoSerial()
    dec = DecodificadorQuadros(lambda _: None, ao_sensores=ard._ao_sensores, ao_servo=ard._ao_servo)
    dados = bytes([255, P.IDX_SERVO, 90, 0, 92, 11, 4 | 32 | 64,
                   255, P.IDX_SENSORES, 80, 0, 0, 0, 0, 0, 1 | 2 | 8])
    for b in dados:
        dec.alimentar(bytes([b]))
    assert ard.status_servo().sonar_movimento and ard.status_servo().sonar
    assert ard.sensores().sonar_nao_calibrado and ard.sensores().avanco_bloqueado
    dec.alimentar(bytes([255, P.IDX_SENSORES, 80, 0, 0, 0, 0, 0, 8 | 16]))
    assert ard.sensores().sonar_experimental and ard.sensores().sonar_nao_calibrado
    assert not ard.sensores().avanco_bloqueado
    assert P.comando_sonar_movimento() == P.montar_comando(P.CMD_SERVO, 4, 0)


def test_flags_laterais_independentes_e_bloqueio_direcional_na_pi():
    ard = ArduinoSerial()
    dec = DecodificadorQuadros(lambda _: None, ao_sensores=ard._ao_sensores)
    dec.alimentar(bytes([255, P.IDX_SENSORES, 80, 0, 0, 0, 0, 0, P.SENSOR_FLAG_LATERAL_DIR | 16]))
    s = ard.sensores()
    assert s.lateral_dir_bloqueada and not s.lateral_esq_bloqueada and not s.avanco_bloqueado
    t = ThreadControle(EstadoRobo(), ard, threading.Event())
    assert t._lateral_bloqueada((100, 50))
    assert not t._lateral_bloqueada((50, 100))
    assert not t._lateral_bloqueada((100, 100))
    assert not t._lateral_bloqueada((-100, -100))
    dec.alimentar(bytes([255, P.IDX_SENSORES, 80, 0, 0, 0, 0, 0, P.SENSOR_FLAG_LATERAL_ESQ | 16]))
    assert t._lateral_bloqueada((50, 100)) and not t._lateral_bloqueada((100, 50))


def test_repetir_fc_nao_confirma_obstaculo_durante_varredura():
    ard = ArduinoSerial()
    t = ThreadControle(EstadoRobo(), ard, threading.Event())
    ard._ao_servo(110, 1500, P.SERVO_FLAG_ATIVO | P.SERVO_FLAG_SONAR_MOVIMENTO | P.SERVO_FLAG_SONAR)
    # FC pode repetir um unico eco curto. Quem conta ecos distintos e o Uno.
    ard._ao_sensores(20, 0, 0, P.SENSOR_FLAG_SONAR_EXPERIMENTAL)
    ard._ao_sensores(20, 0, 0, P.SENSOR_FLAG_SONAR_EXPERIMENTAL)
    with patch.object(cfg, 'OBSTACULO_ATIVO', True):
        assert ard.obstaculo(25, 2)
        assert not t._obstaculo()
        ard._ao_sensores(20, 0, 0, P.SENSOR_FLAG_BLOQUEADO | P.SENSOR_FLAG_OBSTACULO)
        assert t._obstaculo()
        ard._ao_sensores(P.DIST_SEM_LEITURA, 0, 0, P.SENSOR_FLAG_FALHA)
        assert t._obstaculo()  # Pi bloqueia eco invalido tambem no manual


def test_interface_motor_renova_modo4_e_rejeita_pwm_sem_pi():
    ard = ArduinoSerial()
    enviados = []
    ard._escrever = enviados.append
    with patch.object(cfg, 'SONAR_MOVIMENTO_ATIVO', True), patch.object(cfg, 'FIRMWARE_COM_CAMERA', False), \
         patch.object(cfg, 'CONTROLE_VELOCIDADE_ATIVO', True):
        ard.usar_sonar_manual(True)
        ard._ao_servo(90, 1500, P.SERVO_FLAG_ATIVO | P.SERVO_FLAG_SONAR | P.SERVO_FLAG_SONAR_MOVIMENTO)
        ard.motores(127, 127)
        assert enviados == [P.comando_sonar_movimento(), P.comando_velocidade(30, 30)]
        enviados.clear()
        with patch.object(cfg, 'CONTROLE_VELOCIDADE_ATIVO', False):
            try:
                ard.motores(127, 127)
            except RuntimeError:
                pass
            else:
                raise AssertionError('Modo 4 nao deve cair no PWM direto')
        assert enviados == []


def test_interface_nao_envia_velocidade_sem_ack_do_modo4_ou_com_ack_vencido():
    ard = ArduinoSerial()
    enviados = []
    ard._escrever = lambda pacote, repetir=1: enviados.extend([pacote] * repetir)
    with patch.object(cfg, 'SONAR_MOVIMENTO_ATIVO', True), patch.object(cfg, 'FIRMWARE_COM_CAMERA', False), \
         patch.object(cfg, 'CONTROLE_VELOCIDADE_ATIVO', True):
        ard.usar_sonar_manual(True)
        for status in (None,
                       SimpleNamespace(ativo=True, sonar_movimento=False, timestamp=time.monotonic()),
                       SimpleNamespace(ativo=True, sonar_movimento=True, timestamp=time.monotonic() - 1.)):
            ard._servo = status
            enviados.clear()
            ard.motores(127, 127)
            assert enviados == [P.comando_sonar_movimento(), P.comando_parar()]


class MotorFalso:
    def __init__(self):
        self.centros, self.renovacoes, self.movimentos = [], 0, []
        self.contextos = []

    def configurar_servo(self, varrer=False): self.centros.append(varrer)
    def iniciar_sonar_movimento(self): self.renovacoes += 1
    def usar_sonar_manual(self, ativo): self.contextos.append(ativo)
    def motores(self, e, d): self.movimentos.append((e, d))
    def parar(self, repetir=1): pass
    def sensores(self):
        return SimpleNamespace(timestamp=time.monotonic(), falha_sensor=True, avanco_bloqueado=True)


def test_manual_nao_cancela_varredura_e_pare_continua_prioritario():
    est, mot = EstadoRobo(), MotorFalso()
    with patch.object(cfg, 'SONAR_MOVIMENTO_ATIVO', True):
        aplicar_movimento_manual(est, mot, 100, 100)
        assert not mot.centros
        stop = threading.Event()
        t = ThreadControle(est, mot, stop)
        t.start()
        try:
            time.sleep(.16)
        finally:
            stop.set(); t.join(2)
        assert not t.is_alive() and mot.renovacoes >= 2
        # O loop renova a varredura enquanto sensor ainda bloqueia; nao manda andar.
        assert mot.movimentos == []  # envio imediato tambem respeita o sensor
        aplicar_comando(est, mot, 'pare')
        assert mot.centros == [False]


def test_modo_seguidor_nao_ativa_sonar_manual():
    est, mot = EstadoRobo(), MotorFalso()
    est.definir_modo(Modo.SEGUINDO)
    with patch.object(cfg, 'SONAR_MOVIMENTO_ATIVO', True), patch.object(cfg, 'APRENDIZADO_ATIVO', False):
        stop = threading.Event()
        t = ThreadControle(est, mot, stop)
        t.start()
        try:
            time.sleep(.16)
        finally:
            stop.set(); t.join(2)
    assert not t.is_alive() and mot.renovacoes == 0 and mot.contextos
    assert not any(mot.contextos) and not mot.movimentos


def test_sair_do_manual_cancela_modo4_e_nao_envia_v4_no_seguidor():
    ard = ArduinoSerial()
    enviados = []
    ard._escrever = lambda pacote, repetir=1: enviados.extend([pacote] * repetir)
    with patch.object(cfg, 'SONAR_MOVIMENTO_ATIVO', True), patch.object(cfg, 'FIRMWARE_COM_CAMERA', False), \
         patch.object(cfg, 'CONTROLE_VELOCIDADE_ATIVO', True):
        ard.usar_sonar_manual(True)
        ard.usar_sonar_manual(False)
        assert enviados == [P.comando_parar(), P.comando_servo(False)]
        enviados.clear()
        ard.motores(127, 127)
        assert enviados == [P.comando_velocidade(30, 30)]


class ArduinoFalso:
    def __init__(self):
        self.velocidades, self.centros = [], []
        self.fechou = False
        self.experimental = False

    def conectar(self): pass
    def parar(self, repetir=1): pass
    def iniciar_sonar_movimento(self): pass
    def configurar_servo(self, varrer=False): self.centros.append(varrer)
    def fechar(self): self.fechou = True
    def velocidade(self, e, d): self.velocidades.append((e, d))
    def status_servo(self):
        return SimpleNamespace(ativo=True, sonar_movimento=True, timestamp=time.monotonic())
    def sensores(self):
        return SimpleNamespace(timestamp=time.monotonic(), sonar_nao_calibrado=True,
                               sonar_experimental=self.experimental,
                               falha_sensor=not self.experimental, avanco_bloqueado=not self.experimental, distancia_cm=80,
                               ticks_esq=0, ticks_dir=0)
    def consumir_leituras_sonar(self):
        return [SimpleNamespace(timestamp=time.monotonic(), angulo_nominal=90, distancia_cm=80)]


def test_ferramenta_sem_calibracao_nao_envia_movimento_e_fecha():
    ard = ArduinoFalso()
    with patch.object(ferramenta, 'ArduinoSerial', return_value=ard), \
         patch.object(sys, 'argv', ['teste', '--pps', '12', '--tempo', '.01']):
        try:
            ferramenta.main()
        except RuntimeError as erro:
            assert 'falta calibrar' in str(erro)
        else:
            raise AssertionError('Nao pode anunciar liberacao sem calibracao')
    assert ard.fechou and not ard.velocidades and ard.centros == [False] * 3


def test_ferramenta_padrao_so_varre_e_nunca_envia_velocidade():
    ard = ArduinoFalso()
    with patch.object(ferramenta, 'ArduinoSerial', return_value=ard), \
         patch.object(sys, 'argv', ['teste', '--tempo', '.01']):
        ferramenta.main()
    assert ard.fechou and not ard.velocidades


def test_ferramenta_aceita_perfil_experimental_identificado():
    ard = ArduinoFalso()
    ard.experimental = True
    with patch.object(ferramenta, 'ArduinoSerial', return_value=ard), \
         patch.object(sys, 'argv', ['teste', '--pps', '4', '--tempo', '.01']):
        ferramenta.main()
    assert ard.velocidades == [(4, 4)] and ard.fechou


def test_confirmacao_distingue_atraso_de_servo_sensor_e_modo_errado():
    status = SimpleNamespace(ativo=True, sonar_movimento=True, timestamp=10.)
    sensores = SimpleNamespace(timestamp=10.)
    assert ferramenta.falhas_confirmacao(status, sensores, 10.1) == []
    status.timestamp = 9.
    falhas = ferramenta.falhas_confirmacao(status, sensores, 10.1)
    assert len(falhas) == 1 and 'servo: idade=1.100s' in falhas[0]
    status.timestamp = 10.
    sensores.timestamp = 0.
    falhas = ferramenta.falhas_confirmacao(status, sensores, 10.1)
    assert len(falhas) == 1 and falhas[0].startswith('sensores: idade=')
    sensores.timestamp = 10.
    status.sonar_movimento = False
    assert ferramenta.falhas_confirmacao(status, sensores, 10.1) == ['servo: modo 4 nao confirmado']
    status.ativo = False
    assert 'servo: flag ativo=False' in ferramenta.falhas_confirmacao(status, sensores, 10.1)
    assert len(ferramenta.falhas_confirmacao(None, None, 10.)) == 2
    assert ferramenta.falhas_confirmacao(None, sensores, 9.9)[1].startswith('sensores: idade=-')


def test_ferramenta_para_sem_velocidade_e_diagnostica_status_vencido():
    ard = ArduinoFalso()
    ard.experimental = True
    relogio = [0.]
    def agora():
        relogio[0] += .1
        return relogio[0]
    ard.status_servo = lambda: SimpleNamespace(ativo=True, sonar_movimento=True, timestamp=-1.)
    ard.sensores = lambda: SimpleNamespace(timestamp=relogio[0])
    ard.estatisticas = {'reconexoes': 2}
    paradas = []
    ard.parar = lambda repetir=1: paradas.append(repetir)
    with patch.object(ferramenta, 'ArduinoSerial', return_value=ard), \
         patch.object(ferramenta, 'time', SimpleNamespace(monotonic=agora, sleep=lambda _: None)), \
         patch.object(sys, 'argv', ['teste', '--pps', '4', '--tempo', '10']):
        try:
            ferramenta.main()
        except RuntimeError as erro:
            assert 'servo: idade=' in str(erro)
            assert 'sensores: idade=' not in str(erro)
            assert 'reconexao serial=2' in str(erro)
        else:
            raise AssertionError('Status vencido deve encerrar o teste sem liberar motores')
    assert paradas and not ard.velocidades and ard.fechou and ard.centros == [False] * 3


def test_calibracao_exige_distancia_valida_e_pulsos_independentes():
    r = calibrar_encoders.calcular(500, 50, 40)
    assert r['mm_pulso_esq'] == 10 and r['mm_pulso_dir'] == 12.5
    for distancia, e, d in [(0, 10, 10), (float('nan'), 10, 10), (float('inf'), 10, 10),
                           (500, 0, 10), (500, 10, 0), (500, -1, 10)]:
        try:
            calibrar_encoders.calcular(distancia, e, d)
        except ValueError:
            pass
        else:
            raise AssertionError('Calibracao invalida aceita')


if __name__ == '__main__':
    for nome, funcao in sorted(list(globals().items())):
        if nome.startswith('test_'):
            funcao()
            print('OK', nome)
