"""Calibracao manual no piso/suspensa, sem motores ou serial reais."""
from contextlib import redirect_stdout
from io import StringIO
import math
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import calibrar_encoders as ferramenta


def test_sem_diametros_nao_inventa_distancia():
    d = ferramenta.calcular_por_voltas(5, 100, 150)
    assert d['pulsos_por_volta_esq'] == 20 and d['pulsos_por_volta_dir'] == 30
    assert 'mm_pulso_esq' not in d and 'mm_pulso_dir' not in d


def test_diametros_independentes_usam_circunferencia_do_pneu():
    d = ferramenta.calcular_por_voltas(5, 100, 150, 50, 60)
    assert math.isclose(d['mm_pulso_esq'], math.pi * 50 / 20)
    assert math.isclose(d['mm_pulso_dir'], math.pi * 60 / 30)


def test_rejeita_calibracao_incompleta_ou_invalida():
    for args in [(0, 100, 100), (2.5, 100, 100), (True, 100, 100), (5, 0, 100),
                 (5, 100, 100, 50, None), (5, 100, 100, 0, 50),
                 (5, 100, 100, float('nan'), 50), (5, 100, 100, 50, float('inf'))]:
        try:
            ferramenta.calcular_por_voltas(*args)
        except ValueError:
            pass
        else:
            raise AssertionError(args)


class ArduinoFalso:
    def __init__(self):
        self.estatisticas = {'reconexoes': 0}
        self.paradas = 0
        self.fechou = False
    def conectar(self): pass
    def parar(self, repetir=1): self.paradas += repetir
    def fechar(self): self.fechou = True
    def velocidade(self, *_): raise AssertionError('Nao pode acionar motores')
    def motores(self, *_): raise AssertionError('Nao pode acionar motores')


def executar(args, leituras):
    ard, saida = ArduinoFalso(), StringIO()
    with patch.object(ferramenta, 'ArduinoSerial', return_value=ard), \
         patch.object(ferramenta, 'nova_leitura', side_effect=[
             SimpleNamespace(ticks_esq=e, ticks_dir=d) for e, d in leituras]), \
         patch('builtins.input', return_value=''), patch.object(sys, 'argv', ['teste'] + args), \
         redirect_stdout(saida):
        ferramenta.main()
    assert ard.fechou and ard.paradas == 6
    return saida.getvalue()


def test_cli_suspenso_mede_uma_roda_de_cada_vez():
    saida = executar(['--voltas', '5'], [(12, 8), (112, 8), (112, 158)])
    assert '"pulsos_por_volta_esq": 20.0' in saida and '"pulsos_por_volta_dir": 30.0' in saida
    assert '"mm_pulso_esq"' not in saida


def test_cli_piso_continua_compativel():
    saida = executar(['--distancia-mm', '500'], [(12, 8), (112, 133)])
    assert '"mm_pulso_esq": 5.0' in saida and '"mm_pulso_dir": 4.0' in saida


def test_contagem_cruzada_aborta_e_fecha():
    ard = ArduinoFalso()
    with patch.object(ferramenta, 'ArduinoSerial', return_value=ard), \
         patch.object(ferramenta, 'nova_leitura', side_effect=[
             SimpleNamespace(ticks_esq=0, ticks_dir=0), SimpleNamespace(ticks_esq=100, ticks_dir=3)]), \
         patch('builtins.input', return_value=''), patch.object(sys, 'argv', ['teste', '--voltas', '5']):
        try:
            ferramenta.main()
        except RuntimeError as erro:
            assert 'direita contou pulsos' in str(erro)
        else:
            raise AssertionError('Contagem cruzada aceita')
    assert ard.fechou and ard.paradas == 6


def test_diagnostico_diferencia_canal_oposto_de_dois_canais():
    for de, dd, esperado in [(0, 20, 'Somente o canal oposto'), (20, 3, 'Os dois canais')]:
        saida = StringIO()
        with redirect_stdout(saida):
            try:
                ferramenta.validar_roda('esquerda', de, dd)
            except RuntimeError as erro:
                assert esperado in str(erro)
            else:
                raise AssertionError('Contagem oposta nao deve virar calibracao')
        assert f'E (D2) = {de:+d}' in saida.getvalue() and f'D (D3) = {dd:+d}' in saida.getvalue()


def test_diagnostico_aceita_roda_correta_e_recusa_zero_ou_regressao():
    with redirect_stdout(StringIO()):
        ferramenta.validar_roda('direita', 0, 20)
        for de, dd in [(0, 0), (-1, 20)]:
            try:
                ferramenta.validar_roda('direita', de, dd)
            except RuntimeError:
                pass
            else:
                raise AssertionError('Sem pulsos validos nao pode calibrar')


if __name__ == '__main__':
    for nome, funcao in sorted(list(globals().items())):
        if nome.startswith('test_'):
            funcao()
            print('OK', nome)
