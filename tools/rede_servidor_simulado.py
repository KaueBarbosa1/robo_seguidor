"""Servidor Raspberry SIMULADO, sem serial, voz, Bluetooth ou controle físico."""
import argparse
import json
import logging
import math
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg
from comunicacao.amostras import Amostras
from comunicacao.configuracao import Opcoes, url_local
from comunicacao.servidor import Servidor
from comunicacao.simulacao import CameraSimulada, telemetria_simulada


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', default=cfg.REDE_HOST)
    p.add_argument('--porta', type=int, default=cfg.REDE_PORTA)
    p.add_argument('--telemetria-hz', type=float, default=cfg.REDE_TELEMETRIA_HZ)
    p.add_argument('--imagens-fps', type=float, default=cfg.REDE_IMAGENS_FPS)
    p.add_argument('--duracao', type=float, default=0., help='0 = ate Ctrl+C')
    p.add_argument('--atraso', type=float, default=0.)
    p.add_argument('--descartar-cada', type=int, default=0)
    p.add_argument('--invalida-cada', type=int, default=0)
    p.add_argument('--desconectar-apos', type=float, default=0.)
    a = p.parse_args()
    if any(not math.isfinite(v) or v < 0 for v in
           (a.duracao, a.atraso, a.descartar_cada, a.invalida_cada, a.desconectar_apos)):
        p.error('Parametros de simulacao nao negativos')
    try:
        op = Opcoes.central(os.environ.get(cfg.REDE_TOKEN_ENV, ''), host=a.host, porta=a.porta,
                           telemetria_hz=a.telemetria_hz, imagens_fps=a.imagens_fps)
    except ValueError as exc:
        p.error(str(exc))
    camera = CameraSimulada()
    amostras = Amostras(telemetria_simulada(camera), op.telemetria_hz)
    servidor = Servidor(op, amostras, camera, simulado=True,
        falhas=dict(atraso_s=a.atraso, descartar_cada=a.descartar_cada,
                    invalida_cada=a.invalida_cada, desconectar_s=a.desconectar_apos))
    camera.iniciar()
    try:
        servidor.iniciar()
        print(f'SIMULADO {url_local(op.host, servidor.porta)} — comandos de movimento desabilitados', flush=True)
        inicio = time.monotonic()
        while a.duracao == 0 or time.monotonic()-inicio < a.duracao:
            time.sleep(.2)
    except KeyboardInterrupt:
        pass
    finally:
        servidor.parar()
        camera.parar()
    print(json.dumps(servidor.metricas.snapshot(), ensure_ascii=False))


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    main()
