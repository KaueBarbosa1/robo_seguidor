"""Simula o Arduino numa porta serial virtual (pty), para testar a Pi sem hardware.

    python tools/simulador_arduino.py          # imprime o caminho da porta, ex.: /dev/pts/3
    SERIAL_PORTA=/dev/pts/3 python main.py     # (ajuste config.SERIAL_PORTA)

Envia quadros 160x120 no mesmo formato do firmware (linha 0xFF idx 80 bytes; fim 0xFF 0xFE) e
interpreta os comandos 0xAA cmd a b chk, mostrando os motores. Perdas de bytes opcionais (--ruido).
"""
import argparse
import os
import pty
import random
import sys
import threading
import time
import tty
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from motor import protocolo as P  # noqa: E402
import config as cfg  # noqa: E402


def quadro(t: float) -> bytes:
    img = np.full((P.IMG_ALTURA, P.IMG_LARGURA), 13, np.int32)      # piso claro (nível 13)
    for y in range(P.IMG_ALTURA):
        x = int(80 + 30 * np.sin(t + y / 30.0))
        img[y, max(0, x - 5):x + 5] = 2                             # linha escura
    img = np.clip(img + np.random.randint(-1, 2, img.shape), 0, 14)
    out = bytearray()
    for y in range(P.IMG_ALTURA):
        out += bytes([P.SYNC, y])
        out += bytes(((img[y, 0::2] << 4) | img[y, 1::2]).astype(np.uint8))
    out += bytes([P.SYNC, P.IDX_FIM_QUADRO])
    return bytes(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", type=float, default=2.5)
    ap.add_argument("--ruido", type=float, default=0.0, help="probabilidade de perder cada byte")
    ap.add_argument("--distancia", type=int, default=100, help="distância do ultrassom simulada (cm; 0 = sem eco)")
    ap.add_argument("--sem-imagem", action="store_true", help="só sensores, como o firmware sem câmera")
    ap.add_argument("--status", type=int, default=P.ST_OK, help="código de status inicial")
    a = ap.parse_args()

    mestre, escravo = pty.openpty()
    tty.setraw(mestre)
    print(os.ttyname(escravo), flush=True)

    def ler_comandos():
        buf = bytearray()
        while True:
            try:
                buf += os.read(mestre, 256)
            except OSError:
                return
            while len(buf) >= 5:
                if buf[0] != P.CMD_START:
                    del buf[0]
                    continue
                cmd, x, y, chk = buf[1], buf[2], buf[3], buf[4]
                if chk != (cmd ^ x ^ y ^ P.CMD_XOR):
                    del buf[0]
                    continue
                del buf[:5]
                s8 = lambda v: v - 256 if v > 127 else v
                if cmd == P.CMD_MOTORES:
                    print(f"[sim] motores esq={s8(x) * 2:+4d} dir={s8(y) * 2:+4d}", flush=True)
                elif cmd == P.CMD_PARAR:
                    print("[sim] PARAR", flush=True)

    threading.Thread(target=ler_comandos, daemon=True).start()
    if not a.sem_imagem:
        os.write(mestre, bytes([P.SYNC, P.IDX_STATUS, a.status]))
    t0 = time.monotonic()
    enc = [0, 0]

    def pacote_sensores() -> bytes:
        enc[0] = (enc[0] + 3) % P.ENC_MODULO
        enc[1] = (enc[1] + 3) % P.ENC_MODULO
        d = a.distancia if a.distancia > 0 else P.DIST_SEM_LEITURA
        if d == P.DIST_SEM_LEITURA:
            flags = P.SENSOR_FLAG_BLOQUEADO | P.SENSOR_FLAG_FALHA
        else:
            flags = P.SENSOR_FLAG_BLOQUEADO if d < cfg.OBSTACULO_DIST_CM else 0
        v = [d & 0x7F, (d >> 7) & 0x7F, enc[0] & 0x7F, (enc[0] >> 7) & 0x7F,
             enc[1] & 0x7F, (enc[1] >> 7) & 0x7F, flags]
        return bytes([P.SYNC, P.IDX_SENSORES] + v)

    while a.sem_imagem:
        os.write(mestre, pacote_sensores())
        time.sleep(0.05)
    while True:
        dados = quadro(time.monotonic() - t0)
        if a.ruido:
            dados = bytes(b for b in dados if random.random() > a.ruido)
        dados += pacote_sensores()
        for i in range(0, len(dados), 256):
            os.write(mestre, dados[i:i + 256])
            time.sleep(0.003)
        time.sleep(max(0.0, 1 / a.fps - 0.4))


if __name__ == "__main__":
    main()
