"""Diagnóstico de rede no PC; cliente leve, sem Arduino, OpenCV, banco ou dashboard."""
import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg
from comunicacao.cliente import Cliente
from comunicacao.configuracao import Opcoes


async def diagnosticar(args, op):
    cliente = Cliente(args.servidor, op, args.consumo_lento)
    tarefa = asyncio.create_task(cliente.executar())
    async def consumir(canal):
        while not cliente.fim.is_set():
            try:
                await cliente.proxima(canal)
            except TimeoutError:
                pass
    consumidores = [asyncio.create_task(consumir(c)) for c in cliente.metricas]
    inicio = time.monotonic()
    try:
        while args.duracao == 0 or time.monotonic()-inicio < args.duracao:
            await asyncio.sleep(1.)
            dados = cliente.snapshot()
            ultima = dados.pop('ultima_telemetria')
            dados['ultima_telemetria'] = (dict(sessao=ultima['sessao'], sequencia=ultima['sequencia'],
                simulado=ultima['simulado'], dados=ultima['dados']) if ultima else None)
            print(json.dumps(dados, ensure_ascii=False, allow_nan=False), flush=True)
    finally:
        cliente.parar()
        for consumidor in consumidores:
            consumidor.cancel()
        await asyncio.gather(*consumidores, return_exceptions=True)
        await tarefa


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--servidor', required=True, help='ws://IP_LOCAL:PORTA')
    p.add_argument('--duracao', type=float, default=0., help='0 = ate Ctrl+C')
    p.add_argument('--consumo-lento', type=float, default=0.)
    a = p.parse_args()
    try:
        op = Opcoes.central(os.environ.get(cfg.REDE_TOKEN_ENV, ''))
        if any(not math.isfinite(v) or v < 0 for v in (a.duracao, a.consumo_lento)):
            p.error('Duracao/consumo nao negativos')
        asyncio.run(diagnosticar(a, op))
    except ValueError as exc:
        p.error(str(exc))
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
