"""ESP32 -> CNN -> RL em sombra, SEM serial ou motores. Velocidade explicitamente simulada."""
import argparse
import json
import math
from pathlib import Path
import signal
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aprendizado.inferencia_esp32 import Pacote, ThreadInferencia
from estado import EstadoRobo
from visao.esp32_cam import CameraESP32, URL_PADRAO


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--pacote', required=True, type=Path)
    ap.add_argument('--url', default=URL_PADRAO)
    ap.add_argument('--duracao', type=float, default=10.)
    ap.add_argument('--velocidade-simulada', type=float, required=True, help='m/s ficticios, somente diagnostico')
    a = ap.parse_args()
    if not math.isfinite(a.duracao) or a.duracao <= 0 or not math.isfinite(a.velocidade_simulada) or a.velocidade_simulada < 0:
        ap.error('duracao positiva e velocidade nao negativa, ambas finitas')
    try:
        pacote = Pacote(a.pacote)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        ap.error(str(exc))
    estado = EstadoRobo()
    fonte = CameraESP32(a.url)
    fim = threading.Event()
    inferencia = ThreadInferencia(estado, None, fim, fonte, pacote, sombra=True)
    def interromper(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interromper)
    total = ultimo = 0
    inicio = time.monotonic()
    try:
        fonte.iniciar()
        while time.monotonic()-inicio < a.duracao:
            q = fonte.proximo_quadro_detalhado(ultimo, timeout=.1)
            if q is None:
                continue
            ultimo = q[0]
            r = inferencia.processar(q, estado.sessao_visao, a.velocidade_simulada)
            if r is not None:
                total += 1
                print(json.dumps(dict(inferencia.status(), velocidade_simulada=True), ensure_ascii=False), flush=True)
            fim.wait(.1)
    except KeyboardInterrupt:
        pass
    finally:
        fonte.parar()
        estado.encerrar()
    print(json.dumps(dict(quadros_inferidos=total, motores='inexistentes', fonte=fonte.estatisticas)))
    return 0 if total else 2


if __name__ == '__main__':
    raise SystemExit(main())
