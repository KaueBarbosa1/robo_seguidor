"""Imagem da OV7670 pela serial: decodificador (linhas, perdas, status, sensores) e a cadeia completa
simulador de Arduino (porta virtual, 1 Mbaud nominal) -> ArduinoSerial -> criar_fonte("arduino") -> DetectorLinha.
SIMULADO: prova a lógica da Pi; NÃO prova o firmware nem a câmera reais.   python tests/test_serial_imagem.py
"""
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import config as cfg  # noqa: E402
from motor import protocolo as P  # noqa: E402
from motor.serial_com import ArduinoSerial, DecodificadorQuadros  # noqa: E402
from visao.detector import DetectorLinha  # noqa: E402
from visao.fontes import criar_fonte  # noqa: E402


def _quadro_bytes(img4, pular_linhas=()):
    out = bytearray()
    for y in range(P.IMG_ALTURA):
        if y in pular_linhas:
            continue
        out += bytes([P.SYNC, y]) + bytes(((img4[y, 0::2] << 4) | img4[y, 1::2]).astype(np.uint8))
    out += bytes([P.SYNC, P.IDX_FIM_QUADRO])
    return bytes(out)


def _img4(seed=0):
    return np.random.default_rng(seed).integers(0, 15, (P.IMG_ALTURA, P.IMG_LARGURA))     # 0..14: nunca 0xFF


def _dec():
    quadros, status, sens = [], [], []
    d = DecodificadorQuadros(quadros.append, status.append, None, lambda *a: sens.append(a))
    return d, quadros, status, sens


def test_quadro_completo_e_quantizacao():
    d, quadros, _, _ = _dec(); img = _img4()
    d.alimentar(_quadro_bytes(img))
    assert len(quadros) == 1 and quadros[0].shape == (120, 160) and quadros[0].dtype == np.uint8
    assert np.array_equal(quadros[0], (img * 17).astype(np.uint8))


def test_fluxo_em_pedacos_pequenos():
    d, quadros, _, _ = _dec(); b = _quadro_bytes(_img4(1))
    for i in range(0, len(b), 7):
        d.alimentar(b[i:i + 7])
    assert len(quadros) == 1


def test_byte_perdido_descarta_so_aquela_linha_e_preenche():
    d, quadros, _, _ = _dec(); img = _img4(2); b = bytearray(_quadro_bytes(img))
    ini = 2 + 50 * (2 + P.BYTES_LINHA)                       # início da linha 50
    del b[ini + 10]                                          # perde um byte no meio da linha 50
    d.alimentar(bytes(b))
    assert len(quadros) == 1
    assert np.array_equal(quadros[0][49], quadros[0][50])    # linha 50 refeita com a anterior
    assert np.array_equal(quadros[0][51], (img[51] * 17).astype(np.uint8))   # as outras seguem intactas


def test_quadro_muito_incompleto_e_descartado():
    d, quadros, _, _ = _dec()
    d.alimentar(_quadro_bytes(_img4(3), pular_linhas=set(range(0, 60))))
    assert quadros == [] and d._est["quadros_incompletos"] == 1


def test_status_e_sensores():
    d, _, status, sens = _dec()
    d.alimentar(bytes([P.SYNC, P.IDX_STATUS, P.ST_SEM_I2C]))
    assert status == [P.ST_SEM_I2C]
    d.alimentar(bytes([P.SYNC, P.IDX_SENSORES, 20, 0, 5, 0, 6, 0, P.SENSOR_FLAG_BLOQUEADO]))
    assert sens == [(20, 5, 6, P.SENSOR_FLAG_BLOQUEADO)]


def test_flags_estado_de_segurança():
    d, _, _, sens = _dec()
    d.alimentar(bytes([P.SYNC, P.IDX_SENSORES, 40, 0, 0, 0, 0, 0,
                       P.SENSOR_FLAG_FALHA | P.SENSOR_FLAG_BLOQUEADO]))
    assert sens == [(40, 0, 0, P.SENSOR_FLAG_FALHA | P.SENSOR_FLAG_BLOQUEADO)]


def test_cadeia_completa_com_simulador():
    sim = subprocess.Popen([sys.executable, str(RAIZ / "tools/simulador_arduino.py"), "--fps", "8"],
                           stdout=subprocess.PIPE, text=True)
    cfg.SERIAL_BOOT_DELAY_S = 0.2
    try:
        porta = sim.stdout.readline().strip()
        mot = ArduinoSerial(porta=porta, baud=cfg.SERIAL_BAUD); mot.conectar()
        fonte = criar_fonte("arduino", mot)
        assert fonte is mot
        det = DetectorLinha(); ultimo = fonte.id_atual(); achou = 0; n = 0
        for _ in range(6):
            q = fonte.proximo_quadro(ultimo, 3.0)
            assert q is not None, f"nenhum quadro; estatísticas={mot.estatisticas}"
            ultimo, img = q; n += 1
            assert img.shape == (120, 160)
            achou += det.processar(img).achou
        assert achou >= 5, f"o detector achou a linha em só {achou}/{n} quadros"
        mot.motores(60, 60); time.sleep(0.2); mot.parar(3); mot.fechar()
    finally:
        sim.terminate()


def test_fonte_arduino_exige_motor_com_imagem():
    for ruim in (None, object()):
        try:
            criar_fonte("arduino", ruim)
        except ValueError:
            continue
        raise AssertionError("deveria recusar")


if __name__ == "__main__":
    falhou = 0
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f(); print("ok   ", n)
            except Exception:
                import traceback; falhou += 1; print("FALHA", n); traceback.print_exc()
    print("tudo ok" if not falhou else f"{falhou} falhas"); sys.exit(1 if falhou else 0)
