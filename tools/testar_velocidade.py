"""Teste PI com rodas suspensas: python tools/testar_velocidade.py --pps 20."""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg
from motor.serial_com import ArduinoSerial


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--porta", default=cfg.SERIAL_PORTA)
    ap.add_argument("--pps", type=int, default=20, help="alvo por roda, -120..120 pulsos/s")
    ap.add_argument("--tempo", type=float, default=5)
    a = ap.parse_args()
    if not -120 <= a.pps <= 120 or not 0 < a.tempo <= 30:
        ap.error("Use -120..120 pulsos/s e duracao entre 0 e 30 s")
    if cfg.FIRMWARE_COM_CAMERA:
        ap.error("Exige FIRMWARE_COM_CAMERA=False")
    if input("Rodas suspensas, sensores ligados e frente livre? (s/N) ").strip().lower() != "s":
        return
    ard = ArduinoSerial(porta=a.porta, baud=115200)
    try:
        ard.conectar()
        ard.parar(repetir=3)
        time.sleep(0.3)
        anterior = ard.sensores()
        if anterior is None:
            raise RuntimeError("Sem telemetria do Arduino")
        if anterior.falha_sensor or anterior.avanco_bloqueado:
            raise RuntimeError("Frente bloqueada ou ultrassom sem leitura valida")
        fim = time.monotonic() + a.tempo
        ultimo_print = time.monotonic()
        while time.monotonic() < fim:
            ard.velocidade(a.pps, a.pps)
            time.sleep(0.05)
            agora = time.monotonic()
            atual = ard.sensores()
            if atual is None or agora - atual.timestamp > cfg.SENSOR_TIMEOUT_S:
                raise RuntimeError("Telemetria vencida")
            if agora - ultimo_print >= 0.5 and atual.timestamp > anterior.timestamp:
                dt = atual.timestamp - anterior.timestamp
                de = (atual.ticks_esq - anterior.ticks_esq) % 0x4000
                dd = (atual.ticks_dir - anterior.ticks_dir) % 0x4000
                print(f"Alvo {abs(a.pps)} p/s | "
                      f"E {de/dt:.1f} p/s | D {dd/dt:.1f} p/s")
                if a.pps and (de == 0 or dd == 0):
                    print("Sem pulsos nesta janela: " +
                          ", ".join(nome for nome, delta in (("esquerda (D2)", de),
                                                               ("direita (D3)", dd)) if delta == 0) +
                          ". Se a roda gira, conferir encoder/fios; se nao gira, conferir partida.")
                anterior, ultimo_print = atual, agora
    except KeyboardInterrupt:
        pass
    finally:
        ard.parar(repetir=3)
        ard.fechar()


if __name__ == "__main__":
    main()
