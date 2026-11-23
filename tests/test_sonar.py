"""Sonar continuo: protocolo, compatibilidade e encerramento, sem hardware."""
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from motor import protocolo as P
from motor.serial_com import ArduinoSerial, DecodificadorQuadros
from tools import testar_servo


def pacote(angulo, cm, sequencia):
    valores = (angulo, cm, sequencia)
    return bytes([P.SYNC, P.IDX_SONAR] + [b for v in valores for b in (v & 127, v >> 7)])


def test_sonar_fragmentado_ressincroniza_sem_alterar_sensores_ou_inspecao():
    ard = ArduinoSerial()
    enviados = []
    ard._escrever = enviados.append
    ard.iniciar_sonar()
    assert enviados == [P.montar_comando(P.CMD_SERVO, 3, 0)]
    dec = DecodificadorQuadros(lambda q: None, ao_sonar=ard._ao_sonar,
                              ao_sensores=ard._ao_sensores, ao_servo=ard._ao_servo)
    dados = bytes([255, P.IDX_SONAR, 200]) + pacote(135, 80, 16383) + pacote(134, P.DIST_SEM_LEITURA, 0)
    dados += bytes([255, P.IDX_SENSORES, 60, 0, 0, 0, 0, 0, 0])
    dados += bytes([255, P.IDX_SERVO, 6, 1, 92, 11, P.SERVO_FLAG_ATIVO | P.SERVO_FLAG_SONAR])
    for b in dados:
        dec.alimentar(bytes([b]))
    medidas = ard.consumir_leituras_sonar()
    assert [(m.angulo_nominal, m.distancia_cm, m.sequencia) for m in medidas] == [(135, 80, 16383), (134, None, 0)]
    assert ard.consumir_leituras_sonar() == []
    assert ard.sensores().distancia_cm == 60 and ard.leituras_inspecao() == []
    assert ard.status_servo().sonar
    assert not ard.status_servo().inspecao
    # Decoder antigo sem callback opcional continua a separar os outros pacotes.
    DecodificadorQuadros(lambda q: None).alimentar(pacote(90, 50, 1))


class ArduinoSonarFalso:
    def __init__(self):
        self.paradas = 0
        self.centros = []
        self.fechou = False
        self.comandos = 0
        self.timestamp = time.monotonic()

    def conectar(self):
        pass

    def parar(self, repetir=1):
        self.paradas += repetir

    def iniciar_sonar(self):
        self.comandos += 1

    def status_servo(self):
        return SimpleNamespace(ativo=True, sonar=True, timestamp=time.monotonic(), angulo_nominal=90,
                               centro_us=1500, varredura=False, centro_pronto=False)

    def consumir_leituras_sonar(self):
        return [SimpleNamespace(angulo_nominal=90, distancia_cm=None, sequencia=1, timestamp=time.monotonic())]

    def configurar_servo(self, varrer, ajuste):
        self.centros.append((varrer, ajuste))

    def fechar(self):
        self.fechou = True


def test_sonar_sem_prazo_termina_com_ctrl_c_e_pede_centro():
    ard = ArduinoSonarFalso()
    def esperar(_):
        if ard.comandos == 2 and not ard.centros:
            raise KeyboardInterrupt()
    with patch.object(testar_servo, 'ArduinoSerial', return_value=ard), \
         patch.object(sys, 'argv', ['testar_servo.py', '--modo', 'sonar']), \
         patch.object(testar_servo.time, 'sleep', side_effect=esperar):
        testar_servo.main()
    assert ard.comandos == 2 and ard.paradas >= 5
    assert ard.centros == [(False, 0)] * 3 and ard.fechou


def test_sonar_nao_anuncia_sucesso_sem_medidas():
    ard = ArduinoSonarFalso()
    ard.consumir_leituras_sonar = lambda: []
    try:
        with patch.object(testar_servo, 'ArduinoSerial', return_value=ard), \
             patch.object(sys, 'argv', ['testar_servo.py', '--modo', 'sonar', '--tempo', '.01']):
            testar_servo.main()
    except RuntimeError as erro:
        assert 'sem medidas' in str(erro)
    else:
        raise AssertionError('Nao deve confirmar sonar sem medidas')
    assert ard.fechou and ard.centros == [(False, 0)] * 3


def test_sonar_nao_aceita_medidas_antigas():
    ard = ArduinoSonarFalso()
    ard.consumir_leituras_sonar = lambda: [SimpleNamespace(timestamp=0)]
    try:
        with patch.object(testar_servo, 'ArduinoSerial', return_value=ard), \
             patch.object(sys, 'argv', ['testar_servo.py', '--modo', 'sonar', '--tempo', '.01']):
            testar_servo.main()
    except RuntimeError:
        pass
    else:
        raise AssertionError('Medida antiga nao confirma o sonar')
    assert ard.fechou


def test_sonar_para_se_medidas_cessarem_mesmo_com_status_recente():
    ard = ArduinoSonarFalso()
    relogio = [100.]
    consumos = [0]
    def medidas():
        consumos[0] += 1
        if consumos[0] != 1:
            return []
        return [SimpleNamespace(angulo_nominal=45, distancia_cm=50, sequencia=1, timestamp=relogio[0])]
    ard.consumir_leituras_sonar = medidas
    with patch.object(testar_servo, 'ArduinoSerial', return_value=ard), \
         patch.object(sys, 'argv', ['testar_servo.py', '--modo', 'sonar']), \
         patch.object(testar_servo.time, 'monotonic', side_effect=lambda: relogio[0]), \
         patch.object(testar_servo.time, 'sleep', side_effect=lambda s: relogio.__setitem__(0, relogio[0] + s)):
        try:
            testar_servo.main()
        except RuntimeError as erro:
            assert 'sem novas medidas' in str(erro)
        else:
            raise AssertionError('Status recente nao substitui medidas novas')
    assert ard.fechou and ard.centros == [(False, 0)] * 3


if __name__ == '__main__':
    for nome, funcao in sorted(list(globals().items())):
        if nome.startswith('test_'):
            funcao()
            print('OK', nome)
