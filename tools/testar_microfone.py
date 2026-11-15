"""Lista os microfones, mostra qual taxa o headset aceita e o nível do sinal por 5 s."""
import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg  # noqa: E402
from voz.reconhecimento import abrir_taxa, achar_dispositivo  # noqa: E402

print("Dispositivos de entrada:")
for i, d in enumerate(sd.query_devices()):
    if d["max_input_channels"] > 0:
        print(f"  [{i}] {d['name']}  (padrão {int(d['default_samplerate'])} Hz)")
disp = achar_dispositivo(sd, cfg.MIC_DEVICE)
taxa = abrir_taxa(sd, disp)
print(f"\nUsando dispositivo {disp}, {taxa} Hz. Fale por 5 s...")
with sd.InputStream(device=disp, samplerate=taxa, channels=1, dtype="float32") as s:
    t0 = time.time()
    while time.time() - t0 < 5:
        x, _ = s.read(int(taxa * 0.25))
        rms = float(np.sqrt(np.mean(x ** 2)))
        print(f"  {'#' * min(60, int(rms * 600)):<60} {rms:.4f}")
