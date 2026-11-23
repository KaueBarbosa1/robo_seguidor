"""Recepcao de bancada independente do controle do robo. q ou Ctrl+C sai."""
import argparse
import csv
import time
from urllib.request import build_opener, ProxyHandler

import cv2
import numpy as np

# Compatibilidade: coletor e testes continuam importando estas funções daqui.
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from visao.esp32_cam import (MAX_JPEG, URL_PADRAO, ERROS_RECEPCAO,
                             QuadroESP32, receber_quadro, receber)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=URL_PADRAO)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--intervalo", type=float, default=0.05)
    parser.add_argument("--csv", default="esp32_cam_bancada.csv")
    parser.add_argument("--tracejado", action="store_true",
                        help="mostra segmentos OpenCV e trajetória, sem comandos de motor")
    args = parser.parse_args()
    detector = None
    if args.tracejado:
        from visao.detector import DetectorLinha, desenhar_debug
        detector = DetectorLinha(tracejado=True)
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
                    if detector is not None:
                        detector.limpar_historico()
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
                    if detector is not None:
                        processamento_inicio = time.monotonic()
                        resultado = detector.processar(imagem)
                        processamento_ms = (time.monotonic() - processamento_inicio) * 1000
                        imagem = desenhar_debug(imagem, resultado)
                        cv2.putText(imagem, f"HTTP OK FPS={fps:.1f} visao={processamento_ms:.1f}ms",
                                    (5, 33), cv2.FONT_HERSHEY_SIMPLEX, .4, (0, 0, 255), 1)
                        print(f"visao={processamento_ms:.2f} ms segmentos={len(resultado.segmentos)} "
                              f"erro={resultado.erro:+.3f} direcao={resultado.direcao:+.3f} "
                              f"confianca={resultado.confianca:.2f} motivo={resultado.motivo}", flush=True)
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
