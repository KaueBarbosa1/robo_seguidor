"""Teste passo a passo dos motores (e dos encoders, se estiverem ligados).

    python tools/testar_motores.py                 # PWM 120, 1 s por passo
    python tools/testar_motores.py --pwm 100 --tempo 1.5 --porta /dev/ttyACM0

ANTES: deixe o carrinho com as RODAS NO AR (sobre uma caixa), bateria dos motores ligada ao L298N,
Arduino na USB da Pi. O script pergunta antes de começar e para tudo com Ctrl+C.

O que conferir em cada passo (descrição vista DE CIMA, com o carrinho apontado para a frente):
  - a roda certa gira, no sentido certo (frente = para a frente do carrinho);
  - se uma roda gira ao contrário, troque os DOIS fios dela no L298N (não mexa no código).
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg  # noqa: E402
from motor.serial_com import ArduinoSerial  # noqa: E402

PASSOS = [
    ("roda ESQUERDA para a FRENTE", +1, 0),
    ("roda ESQUERDA para TRÁS", -1, 0),
    ("roda DIREITA para a FRENTE", 0, +1),
    ("roda DIREITA para TRÁS", 0, -1),
    ("as duas para a FRENTE (carrinho andaria reto para a frente)", +1, +1),
    ("as duas para TRÁS", -1, -1),
    ("GIRO no lugar para a ESQUERDA (esq. trás, dir. frente)", -1, +1),
    ("GIRO no lugar para a DIREITA (esq. frente, dir. trás)", +1, -1),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--porta", default=cfg.SERIAL_PORTA)
    ap.add_argument("--baud", type=int, default=cfg.SERIAL_BAUD)
    ap.add_argument("--pwm", type=int, default=120, help="0-255; comece baixo")
    ap.add_argument("--tempo", type=float, default=1.0, help="segundos por passo")
    a = ap.parse_args()
    pwm = max(0, min(cfg.VEL_MAX, a.pwm))

    print(f"Vou girar cada roda com PWM {pwm} por {a.tempo} s. As rodas estão NO AR? (s/N) ", end="")
    if input().strip().lower() != "s":
        print("Cancelado.")
        return 1

    ard = ArduinoSerial(porta=a.porta, baud=a.baud)
    ard.conectar()
    try:
        for texto, e, d in PASSOS:
            print(f"\n>>> {texto}")
            ant = ard.sensores()
            fim = time.monotonic() + a.tempo
            while time.monotonic() < fim:           # o comando precisa ser reenviado (watchdog de 400 ms)
                ard.motores(e * pwm, d * pwm)
                time.sleep(0.05)
            ard.parar(repetir=3)
            time.sleep(0.3)
            dep = ard.sensores()
            if ant and dep:
                print(f"    encoders: esquerdo +{dep.ticks_esq - ant.ticks_esq}  "
                      f"direito +{dep.ticks_dir - ant.ticks_dir}  (pulsos neste passo)")
            input("    Estava certo? ENTER para o próximo passo (Ctrl+C aborta)... ")
    except KeyboardInterrupt:
        print("\nAbortado.")
    finally:
        ard.parar(repetir=3)
        ard.fechar()
    print("Motores parados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
