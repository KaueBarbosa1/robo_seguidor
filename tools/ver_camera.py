"""Mostra o que a câmera está enviando: use para apontar, FOCAR e ajustar a luz. Usa a fonte de config.FONTE_IMAGEM
(a OV7670 pelo Arduino, por padrão).

    python tools/ver_camera.py                     # abre janela (precisa de monitor ou VNC)
    python tools/ver_camera.py --salvar foto.png   # salva um quadro e sai (funciona via SSH)

A imagem é a que o robô realmente usa: cinza 120x160 (16 tons na OV7670; ampliada 4x aqui), com a região analisada e a
linha detectada. Antes disto, o firmware (USAR_CAMERA 1, MODO_DIAGNOSTICO 0) tem de estar gravado e o diagnóstico da câmera
(docs/02_bringup_camera.md, passo A) deve ter dado OK.
"""
import argparse
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg  # noqa: E402
from visao.detector import DetectorLinha, desenhar_debug  # noqa: E402
from visao.fontes import criar_fonte  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salvar")
    ap.add_argument("--porta", default=cfg.SERIAL_PORTA)
    ap.add_argument("--baud", type=int, default=cfg.SERIAL_BAUD)
    a = ap.parse_args()
    motor = None
    if cfg.FONTE_IMAGEM == "arduino":
        from motor.serial_com import ArduinoSerial
        motor = ArduinoSerial(porta=a.porta, baud=a.baud)
        motor.conectar()
    cam = criar_fonte(cfg.FONTE_IMAGEM, motor)
    if hasattr(cam, "iniciar"):
        cam.iniciar()
    det = DetectorLinha()
    ultimo = cam.id_atual()
    t0 = time.monotonic()
    try:
        while True:
            q = cam.proximo_quadro(ultimo, 3.0)
            if q is None:
                print(f"sem quadros (status={getattr(cam, 'status', '?')}). Estatísticas: {getattr(cam, 'estatisticas', '-')}")
                continue
            ultimo, img = q
            if a.salvar:
                time.sleep(1.0)
                q = cam.proximo_quadro(ultimo, 3.0)
                img = q[1] if q else img
            vis = cv2.resize(desenhar_debug(img, det.processar(img)), None, fx=4, fy=4,
                             interpolation=cv2.INTER_NEAREST)
            if a.salvar:
                cv2.imwrite(a.salvar, vis)
                print("salvo em", a.salvar, getattr(cam, "estatisticas", ""))
                return
            cv2.imshow("Camera (q sai)", vis)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                return
            if time.monotonic() - t0 > 5:
                print(getattr(cam, "estatisticas", ""))
                t0 = time.monotonic()
    finally:
        if hasattr(cam, "parar"):
            cam.parar()
        if motor is not None:
            motor.parar()
            motor.fechar()


if __name__ == "__main__":
    main()
