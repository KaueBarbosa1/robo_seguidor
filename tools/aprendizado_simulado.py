"""Roda o ciclo COMPLETO de aprendizado num simulador SINTÉTICO (não é a pista real).

Serve para verificar que os mecanismos funcionam: gravar -> reparar rótulos -> treinar do zero -> dirigir com
portão -> supervisor -> A/B -> promoção/descarte/rollback. Os números NÃO valem para o carrinho físico.

    python tools/aprendizado_simulado.py --saida /tmp/sim_apr --tentativas 30 --semente 1
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg  # noqa: E402
from aprendizado.ciclo import CicloAprendizado, executar_tentativa  # noqa: E402
from aprendizado.simulador import AmbienteSimulado, PistaSintetica  # noqa: E402
from visao.detector import DetectorLinha  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--saida", required=True, help="pasta onde ficam episódios e modelos (será reaproveitada)")
    ap.add_argument("--tentativas", type=int, default=30)
    ap.add_argument("--semente", type=int, default=1)
    ap.add_argument("--tempo-max-s", type=float, default=60.0, help="duração máxima de cada tentativa (s simulados)")
    ap.add_argument("--sensor-pista", action="store_true", help="simula o sensor IR sob o chassi (opcional)")
    a = ap.parse_args()

    cfg.APR_TEMPO_MAX_S = a.tempo_max_s
    rng = np.random.default_rng(a.semente)
    pista = PistaSintetica(a.semente)
    amb = AmbienteSimulado(pista, rng, com_sensor_pista=a.sensor_pista)
    print(f"[SINTÉTICO] pista sem. {a.semente}: perímetro {pista.comprimento:.2f} m, raio mínimo {pista.raio_min:.2f} m")
    ciclo = CicloAprendizado(Path(a.saida), rng)
    det = DetectorLinha()
    cabecalho = f"{'#':>3} {'papel':<9} {'modelo':<6} {'nív':>3} {'tipo':<10} {'motivo':<14} {'passos':>6} {'erro':>5} {'auton':>5} {'interv':>6} {'pont':>6} {'fora_real':>9}"
    print(cabecalho)
    for i in range(1, a.tentativas + 1):
        t0 = time.time()
        r = executar_tentativa(amb, ciclo, det, rng)
        ev = ciclo.registrar_resultado(r)
        print(f"{i:>3} {str(r['papel']):<9} {str(r['modelo_id']):<6} {r['nivel']:>3} {r['tipo']:<10} {str(r['motivo']):<14} "
              f"{r['n_passos']:>6} {r['erro_medio']:>5.2f} {r['autonomia']:>5.2f} {r['intervencoes']:>6} {r['pontuacao']:>6.3f} "
              f"{str(amb.fora_verdade):>9}  ({time.time() - t0:.0f}s)")
        for e in ev:
            print("     >", e)
        for e in ciclo.treinar_se_preciso():
            print("     *", e)
    print("\nversões:", json.dumps({v: ciclo.reg.meta(v).get("status") for v in ciclo.reg.ids()}))
    print("campeão:", ciclo.reg.campeao_id(), "| nível:", ciclo.e["nivel"])


if __name__ == "__main__":
    main()
