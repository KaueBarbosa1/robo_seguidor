"""Protocolo do servo integrado e compatibilidade do decoder; sem hardware."""
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from motor import protocolo as P  # noqa: E402
from motor.serial_com import ArduinoSerial, DecodificadorQuadros  # noqa: E402
from tools import testar_servo  # noqa: E402


def pacote_servo(angulo=135, centro=1500, flags=5):
    return bytes([P.SYNC, P.IDX_SERVO, angulo & 127, angulo >> 7, centro & 127, centro >> 7, flags])


def test_comando_servo_checksum_e_offset_assinado():
    for varrer in [False, True]:
        for ajuste in [-250, -50, 0, 50, 250]:
            pkt = P.comando_servo(varrer, ajuste)
            assert pkt[:3] == bytes([0xAA, ord('V'), int(varrer)])
            assert int.from_bytes(pkt[3:4], signed=True) == ajuste // 10
            assert pkt[-1] == pkt[1] ^ pkt[2] ^ pkt[3] ^ 0x5A
    for invalido in [-260, 260, 5, 10.5]:
        try:
            P.comando_servo(True, invalido)
        except ValueError:
            pass
        else:
            raise AssertionError('Offset invalido aceito')


def test_servo_fragmentado_e_pacote_antigo_de_sensores():
    servos, sensores = [], []
    dec = DecodificadorQuadros(lambda q: None, ao_sensores=lambda *a: sensores.append(a),
                               ao_servo=lambda *a: servos.append(a))
    antigo = bytes([P.SYNC, P.IDX_SENSORES, 50, 0, 3, 0, 4, 0, 0])
    for b in pacote_servo() + antigo + pacote_servo(90, 1450, 6):
        dec.alimentar(bytes([b]))
    assert servos == [(135, 1500, 5), (90, 1450, 6)]
    assert sensores == [(50, 3, 4, 0)]


def test_pacote_corrompido_ressincroniza_e_callback_opcional():
    respostas = []
    dec = DecodificadorQuadros(lambda q: None, ao_servo=lambda *a: respostas.append(a))
    dec.alimentar(bytes([255, P.IDX_SERVO, 0, 255]) + pacote_servo(45))
    assert respostas == [(45, 1500, 5)]
    legado = DecodificadorQuadros(lambda q: None)
    legado.alimentar(pacote_servo() + bytes([255, P.IDX_SENSORES, 50, 0, 0, 0, 0, 0, 0]))


def test_arduino_serial_publica_estado_e_envia_comando():
    ard = ArduinoSerial()
    enviados = []
    ard._escrever = enviados.append
    ard.configurar_servo(True, -50)
    assert enviados == [P.comando_servo(True, -50)]
    dec = DecodificadorQuadros(lambda q: None, ao_servo=ard._ao_servo)
    dec.alimentar(pacote_servo(100, 1450, 5))
    s = ard.status_servo()
    assert s.angulo_nominal == 100 and s.centro_us == 1450 and s.varredura
    assert s.ativo and not s.centro_pronto and time.monotonic() - s.timestamp < 1


class ArduinoFalso:
    def __init__(self, **kwargs):
        self.servo = []
        self.paradas = 0
        self.fechou = False
        self.ultimo = None

    def conectar(self):
        pass

    def parar(self, repetir=1):
        self.paradas += repetir

    def configurar_servo(self, varrer=False, ajuste_us=0):
        self.servo.append((varrer, ajuste_us))
        self.ultimo = (varrer, ajuste_us)

    def status_servo(self):
        from types import SimpleNamespace
        return SimpleNamespace(angulo_nominal=90, centro_us=1500, varredura=self.ultimo[0],
                               centro_pronto=not self.ultimo[0], ativo=True, timestamp=time.monotonic())

    def fechar(self):
        self.fechou = True


def test_ferramenta_mantem_motores_parados_e_retorna_centro():
    ard = ArduinoFalso()
    with patch.object(testar_servo, 'ArduinoSerial', return_value=ard), \
         patch.object(sys, 'argv', ['testar_servo.py', '--tempo', '.06']):
        testar_servo.main()
    assert ard.paradas >= len(ard.servo)
    assert any(v for v, _ in ard.servo)
    assert ard.servo[-3:] == [(False, 0)] * 3 and ard.fechou


def test_ferramenta_sem_ack_falha_e_pede_centro():
    ard = ArduinoFalso()
    ard.status_servo = lambda: None
    try:
        with patch.object(testar_servo, 'ArduinoSerial', return_value=ard), \
             patch.object(sys, 'argv', ['testar_servo.py', '--tempo', '.01']):
            testar_servo.main()
    except RuntimeError:
        pass
    else:
        raise AssertionError('Nao deve anunciar sucesso sem resposta do firmware')
    assert ard.servo[-3:] == [(False, 0)] * 3 and ard.fechou


def test_ferramenta_nao_confirma_modo_diferente_do_solicitado():
    ard = ArduinoFalso()
    status = ard.status_servo
    def modo_errado():
        s = status()
        s.varredura = False
        return s
    ard.status_servo = modo_errado
    try:
        with patch.object(testar_servo, 'ArduinoSerial', return_value=ard), \
             patch.object(sys, 'argv', ['testar_servo.py', '--tempo', '.01']):
            testar_servo.main()
    except RuntimeError:
        pass
    else:
        raise AssertionError('Nao deve confirmar varredura quando o estado recebido e centro')
    assert ard.fechou


def test_ctrl_c_recentraliza_com_o_mesmo_ajuste():
    ard = ArduinoFalso()
    configurar = ard.configurar_servo
    def interromper(varrer=False, ajuste_us=0):
        configurar(varrer, ajuste_us)
        if varrer:
            raise KeyboardInterrupt()
    ard.configurar_servo = interromper
    with patch.object(testar_servo, 'ArduinoSerial', return_value=ard), \
         patch.object(sys, 'argv', ['testar_servo.py', '--ajuste-us', '-50']):
        testar_servo.main()
    assert ard.servo[-3:] == [(False, -50)] * 3 and ard.fechou


def test_inspecao_decoder_fragmentado_rodadas_e_desconhecido():
    ard = ArduinoSerial()
    dec = DecodificadorQuadros(lambda q: None, ao_inspecao=ard._ao_inspecao,
                              ao_servo=ard._ao_servo)
    def pacote(ang, cm, rodada):
        return bytes([255, P.IDX_INSPECAO, (ang - 45) // 45, cm & 127, cm >> 7, rodada & 127, rodada >> 7])
    dados = pacote(45, 75, 300) + pacote(90, 20, 300) + pacote(135, P.DIST_SEM_LEITURA, 300)
    for b in dados:
        dec.alimentar(bytes([b]))
    leituras = ard.leituras_inspecao()
    assert [(a.angulo_nominal, a.distancia_cm) for a in leituras] == [(45, 75), (90, 20), (135, None)]
    assert {a.rodada for a in leituras} == {300}
    dec.alimentar(pacote_servo(flags=P.SERVO_FLAG_ATIVO | P.SERVO_FLAG_INSPECAO | P.SERVO_FLAG_CONCLUIDA))
    assert ard.status_servo().inspecao and ard.status_servo().concluida
    # Payload corrompido seguido de pacote valido se ressincroniza; nova rodada limpa dados antigos.
    dec.alimentar(bytes([255, P.IDX_INSPECAO, 128]) + pacote(45, 50, 301))
    assert len(ard.leituras_inspecao()) == 1 and ard.leituras_inspecao()[0].rodada == 301
    assert P.comando_inspecao() == P.montar_comando(P.CMD_SERVO, 2, 0)

def test_ferramenta_inspecao_exige_tres_resultados_e_conclusao():
    from types import SimpleNamespace
    for completa in (True, False):
        ard = ArduinoFalso()
        amostras = []
        def renovar():
            if not amostras:
                amostras.extend(SimpleNamespace(angulo_nominal=a, distancia_cm=None,
                    rodada=1, timestamp=time.monotonic()) for a in (45, 90, 135))
        ard.inspecionar_obstaculo = renovar
        ard.leituras_inspecao = lambda: amostras
        ard.status_servo = lambda: SimpleNamespace(angulo_nominal=90, centro_us=1500,
            varredura=False, centro_pronto=False, ativo=True, inspecao=True,
            concluida=completa, timestamp=time.monotonic())
        falhou = False
        with patch.object(testar_servo, 'ArduinoSerial', return_value=ard), \
             patch.object(sys, 'argv', ['testar_servo.py', '--modo', 'inspecionar', '--tempo', '.01']):
            try:
                testar_servo.main()
            except RuntimeError:
                falhou = True
        assert falhou != completa
        assert ard.paradas >= 4 and ard.servo[-3:] == [(False, 0)] * 3 and ard.fechou


def test_bloqueio_inicial_nao_e_obstaculo_confirmado():
    ard = ArduinoSerial()
    ard._ao_sensores(20, 0, 0, P.SENSOR_FLAG_BLOQUEADO)
    assert not ard.sensores().obstaculo_confirmado
    ard._ao_sensores(20, 0, 0, P.SENSOR_FLAG_BLOQUEADO | P.SENSOR_FLAG_OBSTACULO)
    assert ard.sensores().obstaculo_confirmado

if __name__ == '__main__':
    for nome, funcao in sorted(list(globals().items())):
        if nome.startswith('test_'):
            funcao()
            print('OK', nome)
