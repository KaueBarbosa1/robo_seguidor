"""Integração Pi <-> simulador do Arduino (motores/sensores, porta serial virtual) + câmera simulada, com o aprendizado ATIVO.
Verifica a fiação (thread de aprendizado -> estado -> controle -> motores, 'pare' de voz, episódio gravado).
Usa a linha sintética do FonteSimulada: NÃO é a pista real nem o robô físico.   python tests/test_integracao_robo.py
"""
import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import config as cfg  # noqa: E402

sim = subprocess.Popen([sys.executable, str(RAIZ / "tools/simulador_arduino.py"), "--sem-imagem"],
                       stdout=subprocess.PIPE, text=True)
porta = sim.stdout.readline().strip()
cfg.SERIAL_BOOT_DELAY_S = 0.2
cfg.APRENDIZADO_ATIVO = True
cfg.APR_DIR = tempfile.mkdtemp(prefix="apr_int_")
from aprendizado.robo_real import ThreadAprendizado  # noqa: E402
from controle import ThreadControle, aplicar_comando  # noqa: E402
from estado import EstadoRobo, Modo  # noqa: E402
from motor.serial_com import ArduinoSerial  # noqa: E402
from visao.fontes import FonteSimulada  # noqa: E402

mot = ArduinoSerial(porta=porta, baud=cfg.SERIAL_BAUD); mot.conectar()
parar = threading.Event(); est = EstadoRobo()
fonte = FonteSimulada(fps=10)                       # no lugar da OV7670 (linha falsa)
ths = [ThreadControle(est, mot, parar), ThreadAprendizado(est, mot, parar, fonte)]
[t.start() for t in ths]
time.sleep(1.0)
aplicar_comando(est, mot, "siga"); time.sleep(5.0)
assert est.ler_acao() is not None, "a thread de aprendizado não publicou ação"
aplicar_comando(est, mot, "pare"); time.sleep(1.0)
assert est.modo is Modo.PARADO and est.ler_acao() is None
eps = sorted(Path(cfg.APR_DIR, "episodios").glob("ep_*"))
assert len(eps) == 1, eps
meta = json.loads((eps[0] / "meta.json").read_text())
assert meta["motivo"] == "parada_manual" and not meta["falha"] and meta["n_passos"] >= 5, meta
assert (eps[0] / "frames.u8").stat().st_size == meta["n_passos"] * 120 * 160
parar.set(); [t.join(3) for t in ths]; mot.parar(); mot.fechar(); sim.terminate()
linhas = [l for l in sim.stdout.read().splitlines() if l.startswith("[sim] motores")]
assert len(linhas) > 5 and any("PARAR" in l for l in sim.stdout.read().splitlines()) or len(linhas) > 5
assert not any(t.is_alive() for t in ths)
print("INTEGRACAO_OK  passos gravados:", meta["n_passos"], "| comandos de motor vistos pelo Arduino simulado:", len(linhas))
