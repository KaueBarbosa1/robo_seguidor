"""Recepcao de bancada independente do controle do robo. q ou Ctrl+C sai."""
import argparse
import csv
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http.client import HTTPException
from urllib.request import build_opener, ProxyHandler, Request
from urllib.error import URLError

import cv2
import numpy as np

MAX_JPEG = 2 * 1024 * 1024
URL_PADRAO = "http://192.168.4.1/capture"
ERROS_RECEPCAO = (URLError, OSError, HTTPException, ValueError, TypeError, cv2.error)


@dataclass(frozen=True)
class QuadroESP32:
    jpeg: bytes
    imagem: np.ndarray
    recepcao_monotonica: float
    recepcao_utc: str
    http_ms: float
    idade_envio_ms: float

    @property
    def idade_recepcao_limite_ms(self):
        return self.idade_envio_ms + self.http_ms


def receber_quadro(opener, url, timeout):
    inicio = time.monotonic()
    req = Request(url, headers={"Cache-Control": "no-cache"})
    with opener.open(req, timeout=timeout) as resposta:
        if resposta.status != 200:
            raise ValueError(f"HTTP {resposta.status}")
        if resposta.headers.get_content_type() != "image/jpeg":
            raise ValueError("Resposta nao e image/jpeg")
        idade_envio = float(resposta.headers["X-Frame-Age-Us"]) / 1000
        dados = resposta.read(MAX_JPEG + 1)
        recepcao = time.monotonic()
        recepcao_utc = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    if not np.isfinite(idade_envio) or idade_envio < 0:
        raise ValueError("Idade do quadro invalida")
    if len(dados) > MAX_JPEG or not dados.startswith(b"\xff\xd8") or not dados.endswith(b"\xff\xd9"):
        raise ValueError("JPEG truncado ou invalido")
    imagem = cv2.imdecode(np.frombuffer(dados, dtype=np.uint8), cv2.IMREAD_COLOR)
    if imagem is None or imagem.shape[:2] != (240, 320):
        raise ValueError("JPEG invalido ou resolucao diferente de 320x240")
    return QuadroESP32(dados, imagem, recepcao, recepcao_utc, (recepcao - inicio) * 1000, idade_envio)


def receber(opener, url, timeout):
    quadro = receber_quadro(opener, url, timeout)
    return quadro.imagem, quadro.http_ms, quadro.idade_envio_ms, quadro.idade_recepcao_limite_ms


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=URL_PADRAO)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--intervalo", type=float, default=0.05)
    parser.add_argument("--csv", default="esp32_cam_bancada.csv")
    args = parser.parse_args()
    if args.timeout <= 0 or args.intervalo < 0:
        parser.error("timeout deve ser positivo e intervalo nao negativo")
    opener = build_opener(ProxyHandler({})) # Rede local, sem proxy do ambiente.
    janela = "Carrinho-CAM - q sai"
    cv2.namedWindow(janela)
    inicio = time.monotonic()
    janela_inicio = inicio
    total = falhas = quadros = 0
    try:
        with open(args.csv, "w", newline="", buffering=1) as arquivo:
            log = csv.writer(arquivo)
            log.writerow(["tempo_s", "status", "http_ms", "idade_envio_ms",
                          "idade_recepcao_limite_ms", "fps", "erro"])
            while True:
                tentativa = time.monotonic()
                try:
                    imagem, http, idade, limite = receber(opener, args.url, args.timeout)
                except ERROS_RECEPCAO as erro:
                    falhas += 1
                    decorrido = (time.monotonic() - tentativa) * 1000
                    print(f"FALHA ({decorrido:.1f} ms): {erro}; tentando novamente", flush=True)
                    log.writerow([time.monotonic()-inicio, "falha", f"{decorrido:.2f}", "", "", "", str(erro)])
                    cv2.imshow(janela, np.zeros((240, 320, 3), dtype=np.uint8))
                    espera = 1.0
                else:
                    total += 1
                    quadros += 1
                    agora = time.monotonic()
                    fps = quadros / max(agora - janela_inicio, 1e-9)
                    print(f"quadro={total} HTTP={http:.1f} ms idade_envio={idade:.1f} ms "
                          f"idade_recepcao<={limite:.1f} ms FPS={fps:.2f} falhas={falhas}", flush=True)
                    log.writerow([agora-inicio, "ok", f"{http:.2f}", f"{idade:.2f}", f"{limite:.2f}", f"{fps:.2f}", ""])
                    cv2.imshow(janela, imagem)
                    if agora - janela_inicio >= 5:
                        janela_inicio, quadros = agora, 0
                    espera = args.intervalo
                # Mantem a janela responsiva durante o intervalo e as retentativas.
                fim = time.monotonic() + espera
                while True:
                    if cv2.waitKey(10) & 0xFF == ord("q") or cv2.getWindowProperty(janela, cv2.WND_PROP_VISIBLE) < 1:
                        return
                    if time.monotonic() >= fim:
                        break
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
        print(f"Fim: {total} quadros validos, {falhas} falhas; CSV: {args.csv}")


if __name__ == "__main__":
    main()
