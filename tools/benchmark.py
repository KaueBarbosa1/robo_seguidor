"""Benchmark de bancada sem Arduino, Bluetooth, microfone ou comando de movimento."""
import argparse
import csv
import json
import math
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg
from monitoramento.benchmark import Benchmark
from monitoramento.telemetria import Telemetria


def achatar(dados, prefixo=''):
    saida = {}
    for k, v in dados.items():
        chave = prefixo+k
        if isinstance(v, dict):
            saida.update(achatar(v, chave+'.'))
        else:
            saida[chave] = json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v
    return saida


def exportar(pasta):
    """Duas passagens sobre arquivo limitado; não carrega toda a sessão na RAM."""
    pasta = Path(pasta)
    origem = pasta/'amostras.jsonl'
    chaves = set()
    with origem.open(encoding='utf-8') as f:
        for linha in f:
            chaves.update(achatar(json.loads(linha)))
    with (pasta/'amostras.csv').open('w', encoding='utf-8-sig', newline='') as out:
        escritor = csv.DictWriter(out, sorted(chaves))
        escritor.writeheader()
        with origem.open(encoding='utf-8') as f:
            for linha in f:
                escritor.writerow(achatar(json.loads(linha)))
    return pasta/'amostras.csv'


def executar(args):
    fonte = controle = None
    parar = threading.Event()
    from estado import EstadoRobo
    from motor.nulo import ArduinoNulo
    estado, motor = EstadoRobo(), ArduinoNulo()
    if args.modo != 'sistema':
        from controle import ThreadControle
        from visao.detector import DetectorLinha
        if args.modo == 'simulado':
            from visao.fontes import FonteSimulada
            fonte = FonteSimulada(args.fps)
        else:
            from visao.esp32_cam import CameraESP32
            fonte = CameraESP32(args.url, cfg.ESP32_TIMEOUT_S, cfg.ESP32_IDADE_MAX_S,
                                cfg.ESP32_RECONEXAO_S)
        detector = DetectorLinha(tracejado=args.modo == 'esp32')
        controle = ThreadControle(estado, motor, parar, fonte)
    telemetria = Telemetria(estado, motor, fonte, controle, simulado=True,
                           fonte_simulada=args.modo == 'simulado')
    benchmark = Benchmark(args.saida, telemetria, intervalo=args.intervalo,
        capacidade=cfg.BENCHMARK_CAPACIDADE, max_bytes=cfg.BENCHMARK_MAX_BYTES,
        condicoes=dict(modo=args.modo, nota=args.nota, duracao_s=args.duracao,
            carga='OpenCV de bancada; controle PARADO com ArduinoNulo',
            camera_real=args.modo == 'esp32', motores_simulados=True,
            controle_hz=cfg.FREQ_CONTROLE_HZ, fps_solicitado=args.fps,
            url=args.url if args.modo == 'esp32' else None))
    pasta = benchmark.iniciar()
    print(f'Sessao: {pasta}', flush=True)
    try:
        if fonte and hasattr(fonte, 'iniciar'):
            fonte.iniciar()
        if controle:
            controle.start()
        ultimo = 0
        fim = time.monotonic()+args.duracao
        while time.monotonic() < fim and not benchmark.erro and not benchmark.fim.is_set():
            if fonte is None:
                parar.wait(min(.1, max(0., fim-time.monotonic())))
                continue
            if args.modo == 'esp32':
                q = fonte.proximo_quadro_detalhado(ultimo, timeout=.1)
            else:
                q = fonte.proximo_quadro(ultimo, timeout=.1)
            if q is None:
                continue
            ultimo, frame = q[:2]
            r = detector.processar(frame)
            meta = q[2] if len(q) > 2 else {}
            estado.publicar_leitura(r.erro, r.achou,
                timestamp=meta.get('recepcao_monotonica'), frame_id=ultimo,
                idade_captura_s=meta.get('idade_captura_s', 0), confianca=r.confianca,
                motivo='benchmark_bancada_'+r.motivo)
            benchmark.registro.contar('benchmark_frames_processados')
    except KeyboardInterrupt:
        pass
    finally:
        parar.set()
        estado.encerrar()
        if controle and controle.ident is not None:
            controle.join(timeout=2)
        if fonte and hasattr(fonte, 'parar'):
            fonte.parar()
        benchmark.parar()
    if benchmark.erro:
        raise RuntimeError(benchmark.erro)
    return pasta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--modo', choices=('sistema', 'simulado', 'esp32'), default='sistema')
    parser.add_argument('--duracao', type=float, default=60.)
    parser.add_argument('--intervalo', type=float, default=cfg.BENCHMARK_INTERVALO_S)
    parser.add_argument('--fps', type=float, default=10.)
    parser.add_argument('--url', default=cfg.ESP32_URL)
    parser.add_argument('--saida', type=Path, default=cfg.BENCHMARK_DIR)
    parser.add_argument('--nota', default='')
    parser.add_argument('--exportar', type=Path, help='somente exporta uma sessao ja encerrada')
    args = parser.parse_args()
    if args.exportar:
        print(exportar(args.exportar))
        return
    if any(not math.isfinite(v) or v <= 0 for v in (args.duracao, args.intervalo, args.fps)) or args.intervalo < 1:
        parser.error('duracao e fps positivos, intervalo >=1 s, todos finitos')
    executar(args)


if __name__ == '__main__':
    main()
