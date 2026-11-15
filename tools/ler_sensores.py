"""Mostra o que o Arduino está enviando: distância do HC-SR04 e pulsos dos encoders.

    python tools/ler_sensores.py                   # roda até Ctrl+C
    python tools/ler_sensores.py --porta /dev/ttyACM0 --segundos 20

ATENÇÃO: o Arduino só envia sensores com o firmware em USAR_CAMERA 0 (modo bancada, 115200 baud): use  --baud 115200 .
Com a câmera OV7670 (USAR_CAMERA 1) ultrassom e encoders ficam desligados (pinos em conflito).
Teste: aproxime a mão do sensor (a distância tem que cair) e gire cada roda à mão (os pulsos sobem).
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg  # noqa: E402
from motor.serial_com import ArduinoSerial  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--porta", default=cfg.SERIAL_PORTA)
    ap.add_argument("--baud", type=int, default=cfg.SERIAL_BAUD)
    ap.add_argument("--segundos", type=float, default=0, help="0 = até Ctrl+C")
    a = ap.parse_args()

    ard = ArduinoSerial(porta=a.porta, baud=a.baud)
    ard.conectar()
    t0 = time.monotonic()
    try:
        while not a.segundos or time.monotonic() - t0 < a.segundos:
            s = ard.sensores()
            if s is None:
                print("aguardando dados do Arduino... (porta/baud certos? firmware gravado?)")
            else:
                dist = "sem eco (>2,4 m)" if s.distancia_cm is None else f"{s.distancia_cm:4d} cm"
                estado = "AVANÇO BLOQUEADO" if s.avanco_bloqueado else "MOVIMENTO LIBERADO"
                if s.falha_sensor:
                    estado = "FALHA DO SENSOR | AVANÇO BLOQUEADO"
                elif s.distancia_cm is not None and s.distancia_cm < cfg.OBSTACULO_DIST_CM:
                    estado = "OBSTÁCULO DETECTADO"
                print(f"DISTANCIA: {dist} | {estado} | encoders E:{s.ticks_esq} D:{s.ticks_dir}")
            time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        ard.fechar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
