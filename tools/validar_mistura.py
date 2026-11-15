"""Compara a mistura do robô (NumPy, sem PyTorch) com o prever_comando.py ORIGINAL (PyTorch).

Rode no SEU COMPUTADOR (o que tem torch instalado), uma vez, antes de levar para a Raspberry Pi:

    python tools/validar_mistura.py PASTA_DO_PROJETO_ORIGINAL audio1.wav audio2.wav ...
    python tools/validar_mistura.py PASTA_DO_PROJETO_ORIGINAL PASTA_COM_OS_AUDIOS   # usa TODOS os .wav (inclui subpastas; se cada comando tem a sua pasta, mostra também o acerto por pasta)

PASTA_DO_PROJETO_ORIGINAL é onde estão prever_comando.py, 2_extract_mfccs.py e modelo_mistura.pkl.
Use áudios reais do seu dataset (alguns de cada comando). Para cada um o script mostra a maior
diferença entre as probabilidades do LSTM e do SVM nos dois caminhos. Esperado: diferença
< 1e-4 (só ruído numérico de float32 contra float64) e a mesma classe final.
"""
import os
import sys
from pathlib import Path

import numpy as np
from scipy.io import wavfile

RAIZ_ROBO = Path(__file__).resolve().parent.parent


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1

    pasta = Path(sys.argv[1]).resolve()
    wavs = []
    for a in sys.argv[2:]:
        caminho = Path(a).resolve()
        if caminho.is_dir():                          # pasta: pega todos os .wav, inclusive nas subpastas
            wavs += sorted(caminho.rglob("*.wav")) + sorted(caminho.rglob("*.WAV"))
        else:
            wavs.append(caminho)
    wavs = list(dict.fromkeys(wavs))                  # sem repetidos, mantém a ordem
    if not wavs:
        print("Nenhum .wav encontrado.")
        return 1
    print(f"{len(wavs)} áudios para validar...")
    detalhar = len(wavs) <= 30                        # com muitos áudios, só mostra os problemas

    sys.path.insert(0, str(RAIZ_ROBO))
    os.chdir(pasta)                                   # o original procura 2_extract_mfccs.py aqui
    sys.path.insert(0, str(pasta))

    from prever_comando import Preditor as Original
    from voz.mistura import PreditorMistura

    original = Original(str(pasta / "modelo_mistura.pkl"))
    robo = PreditorMistura(Path(pasta / "modelo_mistura.pkl"))

    pior = 0.0
    divergencias = 0
    por_pasta = {}      # nome da pasta (= comando real) -> [total, acertos do original, acertos do robô]
    por_pasta = {}                                    # nome da pasta (= comando) -> [total, acertos robô, acertos original]
    for n, w in enumerate(wavs, 1):
        pl_o = original._probas_lstm(str(w))[0]
        ps_o = original._probas_svm(str(w))[0]
        r_o = original.prever(str(w))

        taxa, pcm = wavfile.read(str(w))
        pl_n, ps_n = robo.probas_pcm(pcm, taxa)
        classe_n, conf_n = robo.prever_pcm(pcm, taxa)

        d_lstm = float(np.max(np.abs(pl_o - pl_n)))
        d_svm = float(np.max(np.abs(ps_o - ps_n)))
        pior = max(pior, d_lstm, d_svm)
        igual = classe_n.lower() == r_o["classe"].lower()
        divergencias += 0 if igual else 1
        est = por_pasta.setdefault(w.parent.name.lower(), [0, 0, 0])
        est[0] += 1
        est[1] += r_o["classe"].lower() == w.parent.name.lower()
        est[2] += classe_n.lower() == w.parent.name.lower()
        verdade = w.parent.name.lower()               # se as pastas têm o nome do comando, serve de gabarito
        if verdade in ("siga", "pare", "esquerda", "direita", "voltar"):
            c = por_pasta.setdefault(verdade, [0, 0, 0])
            c[0] += 1
            c[1] += classe_n.lower() == verdade
            c[2] += r_o["classe"].lower() == verdade
        if detalhar or not igual or max(d_lstm, d_svm) >= 1e-4:
            print(f"{w.name:<32} LSTM diff={d_lstm:.2e}  SVM diff={d_svm:.2e}  "
                  f"original={r_o['classe']}({r_o['confianca']:.2f})  robo={classe_n}({conf_n:.2f})  "
                  f"{'OK' if igual else 'CLASSE DIFERENTE'}")
        elif n % 50 == 0:
            print(f"  {n}/{len(wavs)} ok até agora")

    print("\nAcertos por pasta (a pasta é o comando real):")
    for nome, (tot, ac_o, ac_r) in sorted(por_pasta.items()):
        print(f"  {nome:<10} {tot:>5} áudios | original acerta {ac_o / tot:6.1%} | robô acerta {ac_r / tot:6.1%}")
    print(f"\nÁudios: {len(wavs)} | classe diferente da original: {divergencias}")
    print(f"Maior diferença de probabilidade: {pior:.2e}")
    if por_pasta:
        print("\nAcerto por pasta (nome da pasta = comando esperado):")
        print(f"  {'pasta':<10} {'áudios':>7} {'robô':>8} {'original':>9}")
        for nome, (t, a_r, a_o) in sorted(por_pasta.items()):
            print(f"  {nome:<10} {t:>7} {100 * a_r / t:>7.1f}% {100 * a_o / t:>8.1f}%")
    if pior < 1e-4 and divergencias == 0:
        print("APROVADO: o robô reproduz o prever_comando.py original.")
        return 0
    print("REPROVADO: me envie esta saída que eu corrijo o LSTM em NumPy.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
