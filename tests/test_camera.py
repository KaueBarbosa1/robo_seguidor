"""Testes da fonte de imagem CSI com uma câmera FALSA (imita a interface do Picamera2). Não prova nada sobre a câmera real."""
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg  # noqa: E402
from visao.camera_csi import CameraCSI, para_quadro_cinza, y_do_yuv420  # noqa: E402
from visao.detector import DetectorLinha  # noqa: E402


class PicamFalsa:
    def __init__(self, falhas_iniciais=0):
        lw, lh = cfg.CAMERA_LORES
        self.lw, self.lh = lw, lh
        self.cfg = None
        self.rodando = False
        self.n = 0
        self.falhas = falhas_iniciais

    def create_video_configuration(self, **k):
        self.pedido = k
        return k

    def configure(self, c): self.cfg = c
    def start(self): self.rodando = True
    def stop(self): self.rodando = False
    def close(self): pass

    def capture_array(self, nome):
        assert nome == "lores" and self.rodando
        if self.falhas > 0:
            self.falhas -= 1
            raise RuntimeError("câmera caiu")
        time.sleep(0.01)
        self.n += 1
        y = np.full((self.lh, self.lw), 205, np.uint8)
        y[:, 200:220] = 40                                        # linha escura à direita do centro
        uv = np.full((self.lh // 2, self.lw), 128, np.uint8)
        return np.vstack([y, uv])                                 # YUV420: Y + metade de altura de croma


def test_conversao_yuv420_para_quadro_cinza():
    cam = PicamFalsa(); cam.rodando = True
    arr = cam.capture_array("lores")
    y = y_do_yuv420(arr, 240, 320)
    assert y.shape == (240, 320)
    q = para_quadro_cinza(y)
    assert q.shape == (120, 160) and q.dtype == np.uint8
    assert q[:, 100:110].mean() < 80 and q[:, :50].mean() > 190
    r = DetectorLinha().processar(q)
    assert r.achou and r.erro > 0.2                               # a linha está à direita


def test_espelhar_inverte_o_lado():
    cfg.IMAGEM_ESPELHAR_H = True
    try:
        cam = PicamFalsa(); cam.rodando = True
        q = para_quadro_cinza(y_do_yuv420(cam.capture_array("lores"), 240, 320))
        assert DetectorLinha().processar(q).erro < -0.2
    finally:
        cfg.IMAGEM_ESPELHAR_H = False


def test_camera_publica_quadros_e_id_cresce():
    fake = PicamFalsa()
    c = CameraCSI(fabrica=lambda: fake); c.iniciar()
    try:
        q1 = c.proximo_quadro(c.id_atual(), 2.0)
        q2 = c.proximo_quadro(q1[0], 2.0)
        assert q1 is not None and q2 is not None and q2[0] > q1[0] and q2[1].shape == (120, 160)
        assert fake.pedido["lores"]["format"] == "YUV420" and fake.pedido["controls"]["FrameRate"] == cfg.CAMERA_FPS
    finally:
        c.parar()
    assert not c._thread.is_alive()


def test_camera_reabre_depois_de_falhas():
    criadas = []

    def fabrica():
        f = PicamFalsa(falhas_iniciais=3 if not criadas else 0)
        criadas.append(f)
        return f
    c = CameraCSI(fabrica=fabrica); c.iniciar()
    try:
        t0 = time.time(); q = None
        while time.time() - t0 < 8 and q is None:
            q = c.proximo_quadro(c.id_atual(), 1.0)
        assert q is not None and c.estatisticas["reaberturas"] >= 1 and len(criadas) >= 2
    finally:
        c.parar()


def test_sem_quadros_devolve_none_no_timeout():
    c = CameraCSI(fabrica=lambda: PicamFalsa(falhas_iniciais=10 ** 6)); c.iniciar()
    try:
        assert c.proximo_quadro(0, 0.3) is None
    finally:
        c.parar()


def test_picamera2_ausente_da_erro_claro():
    c = CameraCSI()
    try:
        c.iniciar()
    except RuntimeError as e:
        assert "python3-picamera2" in str(e)
    else:                                                          # (numa Pi de verdade a câmera pode abrir)
        c.parar()


if __name__ == "__main__":
    falhou = 0
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            try:
                f(); print("ok   ", n)
            except Exception:
                import traceback; falhou += 1; print("FALHA", n); traceback.print_exc()
    print("tudo ok" if not falhou else f"{falhou} falhas"); sys.exit(1 if falhou else 0)
