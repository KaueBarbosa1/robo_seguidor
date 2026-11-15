import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
import threading

from voz.reconhecimento import ThreadVoz

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

parar = threading.Event()


def mostrar_comando(comando):
    print(f"\n>>> COMANDO RECONHECIDO: {comando.upper()}", flush=True)


voz = ThreadVoz(
    ao_comando=mostrar_comando,
    parar=parar
)

print("Teste de reconhecimento de voz iniciado.")
print("Fale: siga, pare, esquerda, direita ou voltar.")
print("Pressione Ctrl+C para encerrar.")
print("Nenhum motor será acionado.\n")

voz.start()

try:
    while voz.is_alive():
        voz.join(timeout=0.5)
except KeyboardInterrupt:
    print("\nEncerrando teste...")
    parar.set()
    voz.join(timeout=3)
