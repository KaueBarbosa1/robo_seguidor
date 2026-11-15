"""Diagnóstico do HC-SR04 e da barreira que roda no Arduino.

    python tools/testar_ultrassom.py
    python tools/testar_ultrassom.py --comando avancar  # roda suspensa: mantém avanço enquanto observa a proteção
    python tools/testar_ultrassom.py --comando re

O firmware deve estar em USAR_CAMERA=0. Para testar com motores, suspenda as rodas; nunca aproxime
objetos de uma roda em movimento. O estado exibido vem do Arduino, que também aplica o corte de PWM.
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
    ap.add_argument("--comando", choices=("nenhum", "avancar", "re"), default="nenhum")
    ap.add_argument("--segundos", type=float, default=0, help="0 = até Ctrl+C")
    a = ap.parse_args()
    ard = ArduinoSerial(a.porta, a.baud)
    ard.conectar()
    t0 = time.monotonic()
    try:
        while not a.segundos or time.monotonic() - t0 < a.segundos:
            if a.comando == "avancar":
                ard.motores(cfg.VEL_BASE, cfg.VEL_BASE)
            elif a.comando == "re":
                ard.motores(-cfg.VEL_RE, -cfg.VEL_RE)
            s = ard.sensores()
            if s is None or time.monotonic() - s.timestamp > cfg.SENSOR_TIMEOUT_S:
                print("SEGURANCA: AVANÇO BLOQUEADO | telemetria ausente/vencida", flush=True)
            else:
                dist = "SEM ECO" if s.distancia_cm is None else f"{s.distancia_cm} cm"
                if s.falha_sensor:
                    estado = "FALHA DO SENSOR | AVANÇO BLOQUEADO"
                elif s.avanco_bloqueado:
                    estado = "OBSTÁCULO/AVANÇO BLOQUEADO"
                else:
                    estado = "MOVIMENTO LIBERADO"
                print(f"DISTANCIA: {dist} | {estado}", flush=True)
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        ard.parar(repetir=3)
        ard.fechar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
