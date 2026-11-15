"""Relatório de progresso do aprendizado a partir do que está gravado em disco.

    python tools/aprendizado_relatorio.py [pasta]  [--csv saida.csv]      (padrão: config.APR_DIR)

Mostra: tentativas (papel, nível, resultado, pontuação), mediana móvel, taxa de falhas por nível, linha do tempo
das versões da CNN. Só lê; não altera nada. Os números valem para o que o carrinho realmente fez (ou para o
simulador sintético, se a pasta veio dele): o relatório não distingue, quem distingue é você.
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta", nargs="?", default=cfg.APR_DIR)
    ap.add_argument("--csv")
    a = ap.parse_args()
    base = Path(a.pasta)
    arq = base / "estado_ciclo.json"
    if not arq.exists():
        sys.exit(f"Sem estado_ciclo.json em {base}: ainda não houve tentativas.")
    e = json.loads(arq.read_text(encoding="utf-8"))
    h = e["historico"]
    print(f"{len(h)} tentativas | nível atual {e['nivel']} | campeão: ", end="")
    try:
        print(json.loads((base / "campeao.json").read_text())["campeao"])
    except Exception:
        print("nenhum")
    print(f"\n{'#':>3} {'papel':<9} {'modelo':<6} {'nív':>3} {'tipo':<10} {'motivo':<15} {'passos':>6} {'erro':>5} {'auton':>5} {'interv':>6} {'pont':>6} {'med5':>6}")
    pont_validas = []
    for i, r in enumerate(h, 1):
        if r["tipo"] in ("falha", "concluida"):
            pont_validas.append(r["pontuacao"])
        med = f"{np.median(pont_validas[-5:]):.3f}" if pont_validas else "-"
        print(f"{i:>3} {str(r['papel']):<9} {str(r['modelo_id']):<6} {r['nivel']:>3} {r['tipo']:<10} {str(r['motivo']):<15} "
              f"{r['n_passos']:>6} {r['erro_medio']:>5.2f} {r['autonomia']:>5.2f} {r['intervencoes']:>6} {r['pontuacao']:>6.3f} {med:>6}")
    por_nivel = defaultdict(list)
    for r in h:
        if r["tipo"] in ("falha", "concluida"):
            por_nivel[r["nivel"]].append(r)
    print("\nPor nível de autonomia (só tentativas válidas):")
    for n in sorted(por_nivel):
        rs = por_nivel[n]
        print(f"  nível {n}: {len(rs):>3} tentativas | falhas {sum(x['tipo'] == 'falha' for x in rs):>2} "
              f"| pontuação média {np.mean([x['pontuacao'] for x in rs]):.3f} | autonomia média {np.mean([x['autonomia'] for x in rs]):.2f}")
    print("\nVersões da CNN:")
    for d in sorted((base / "modelos").glob("v[0-9]*")):
        try:
            m = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        except Exception:
            print(f"  {d.name}: meta ilegível"); continue
        metr = m.get("metricas", {})
        v = metr.get("validacao", {})
        t = metr.get("teste", {})
        mae_val = v.get("mae")
        mae_zero = v.get("mae_zero")
        mae_teste = t.get("mae")
        if mae_val is None:
            mae_val = float("nan")
        if mae_zero is None:
            mae_zero = float("nan")
        if mae_teste is None:
            mae_teste = float("nan")
        print(f"  {m['id']} [{m.get('status')}] {m.get('origem')} | quadros {m.get('n_quadros')} | "
              f"MAE val {mae_val:.3f} (chute 'reto' {mae_zero:.3f}) | "
              f"MAE teste {mae_teste:.3f} | "
              f"perda treino/val {metr.get('treino', {}).get('perda')} / {v.get('perda')} | "
              f"passos {metr.get('passos_executados', '?')}/{metr.get('passos', '?')} "
              f"{'(parada antecipada)' if metr.get('parada_antecipada') else ''}")
        for ev in m.get("eventos", [])[1:]:
            print(f"        {ev['t']}  {ev['evento']}")
    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(h[0].keys())); w.writeheader(); w.writerows(h)
        print("\nCSV:", a.csv)


if __name__ == "__main__":
    main()
