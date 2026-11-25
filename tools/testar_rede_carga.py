"""Carga SIMULADA localhost: protocolo real, imagens sintéticas, sem hardware."""
import argparse
import asyncio
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import secrets
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg
from comunicacao.amostras import Amostras
from comunicacao.cliente import Cliente
from comunicacao.configuracao import Opcoes, url_local
from comunicacao.servidor import Servidor
from comunicacao.simulacao import CameraSimulada, telemetria_simulada


async def ensaio(hz, fps, duracao, lento=0., falhas=None):
    op = Opcoes.central(secrets.token_hex(24), host=cfg.REDE_SIM_HOST, porta=0, telemetria_hz=hz, imagens_fps=fps)
    camera = CameraSimulada()
    amostras = Amostras(telemetria_simulada(camera), hz)
    servidor = Servidor(op, amostras, camera, simulado=True, falhas=falhas)
    camera.iniciar()
    tarefa = None
    consumidores = []
    try:
        servidor.iniciar()
        cliente = Cliente(url_local(op.host, servidor.porta), op, lento)
        tarefa = asyncio.create_task(cliente.executar())
        async def consumir(canal):
            while not cliente.fim.is_set():
                try:
                    await cliente.proxima(canal)
                except TimeoutError:
                    pass
        consumidores = [asyncio.create_task(consumir(c)) for c in cliente.metricas]
        inicio = time.monotonic()
        await asyncio.sleep(duracao)
        resultado = dict(simulado=True, host=platform.platform(), python=platform.python_version(),
            duracao_real_s=time.monotonic()-inicio, telemetria_hz_alvo=hz, imagens_fps_alvo=fps,
            consumidor_lento_s=lento, falhas=falhas, servidor=servidor.metricas.snapshot(),
            cliente=cliente.snapshot(), sistema_medido_no_host=amostras.sistema,
            fila_max_configurada=op.fila,
            filas_observadas={c: (cliente.telemetrias if c == 'telemetria' else cliente.imagens).qsize()
                              for c in cliente.metricas})
    finally:
        if tarefa:
            cliente.parar()
            for consumidor in consumidores:
                consumidor.cancel()
            await asyncio.gather(*consumidores, return_exceptions=True)
            await tarefa
        await asyncio.to_thread(servidor.parar)
        camera.parar()
    resultado['servidor_encerrado'] = not servidor.thread.is_alive()
    return resultado


async def executar(args):
    resultados = []
    for hz, fps, lento, falhas in [(10, 5, 0, None), (50, 15, 0, None),
                                  (100, 30, 0, {'atraso_s': .08}),
                                  (30, 10, .15, {'descartar_cada': 7, 'invalida_cada': 11,
                                               'desconectar_s': max(1., args.duracao/2)})]:
        resultado = await ensaio(hz, fps, args.duracao, lento, falhas)
        resultados.append(resultado)
        print(f'SIMULADO {hz} Hz / {fps} FPS: '+json.dumps(resultado['servidor'], ensure_ascii=False), flush=True)
    pasta = args.saida/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    pasta.mkdir(parents=True)
    (pasta/'carga.json').write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding='utf-8')
    with (pasta/'carga.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['simulado', 'telemetria_hz_alvo', 'imagens_fps_alvo', 'duracao_s',
                    'telemetrias_recebidas', 'frames_recebidos', 'rtt_medio_s', 'rtt_mediana_s', 'rtt_p95_s',
                    'lacunas', 'reconexoes', 'descartes_fila_servidor', 'servidor_encerrado'])
        for r in resultados:
            t, i = r['cliente']['canais']['telemetria'], r['cliente']['canais']['imagens']
            c = t['contadores']
            rtt = t['rtt_s'] or {}
            w.writerow([True, r['telemetria_hz_alvo'], r['imagens_fps_alvo'], r['duracao_real_s'],
                c.get('telemetrias', 0), i['contadores'].get('frames', 0), rtt.get('media'),
                rtt.get('mediana'), rtt.get('p95'), c.get('lacunas', 0), c.get('reconexoes', 0),
                r['servidor']['contadores'].get('descartes_fila_telemetria', 0), r['servidor_encerrado']])
    print(f'Resultados locais: {pasta}', flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--duracao', type=float, default=5., help='segundos por cenario, minimo 3')
    p.add_argument('--saida', type=Path, default=cfg.BASE_DIR/'dados_rede')
    a = p.parse_args()
    if not 3 <= a.duracao <= 120:
        p.error('Duracao deve ficar entre 3 e 120 segundos por cenario')
    asyncio.run(executar(a))


if __name__ == '__main__':
    main()
