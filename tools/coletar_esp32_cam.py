"""Coleta JPEGs originais da ESP32-CAM e exibe uma prévia de recorte 80x40."""
import argparse
import csv
import json
import math
import sys
import time
from contextlib import nullcontext
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import ProxyHandler, build_opener
from uuid import uuid4

import cv2
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
if __package__ in (None, ""):
    sys.path.insert(0, str(RAIZ))
from tools.testar_esp32_cam import ERROS_RECEPCAO, URL_PADRAO, receber_quadro
from visao.recorte_esp32 import ENTRADA, RESOLUCAO, VERSAO_PREVIA, RecorteESP32

JANELA = "Coleta ESP32-CAM"
CAMPOS = ("tentativa", "status", "quadro", "jpeg", "recepcao_utc", "tempo_s", "bytes",
          "http_ms", "idade_envio_ms", "idade_recepcao_limite_ms", "erro")


def utc_agora():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def gravar_atomico(destino, dados):
    temporario = destino.with_suffix(destino.suffix + ".part")
    try:
        temporario.write_bytes(dados)
        temporario.replace(destino)
    finally:
        temporario.unlink(missing_ok=True)


def montar_previa(imagem, recorte, status):
    orientada = recorte.orientar(imagem)
    pequena = recorte.reduzir(orientada)
    largura, altura = RESOLUCAO
    tela = np.full((altura + 56, 2 * largura + 12, 3), 28, dtype=np.uint8)
    esquerda = tela[28:28 + altura, :largura]
    esquerda[:] = orientada
    cv2.rectangle(esquerda, (recorte.x, recorte.y),
                  (recorte.x + recorte.largura - 1, recorte.y + recorte.altura - 1), (0, 215, 255), 1)
    ampliada = cv2.resize(pequena, (largura, 160), interpolation=cv2.INTER_NEAREST)
    tela[28:188, -largura:] = cv2.cvtColor(ampliada, cv2.COLOR_GRAY2BGR)
    legendas = [((7, 19), "Quadro orientado 320x240"), ((largura + 17, 19), "Recorte cinza 80x40 (ampliado)"),
                ((largura + 17, 211), f"ROI x={recorte.x} y={recorte.y} {recorte.largura}x{recorte.altura}"),
                ((7, altura + 46), status + "  |  q: sair")]
    for xy, texto in legendas:
        cv2.putText(tela, texto, xy, cv2.FONT_HERSHEY_SIMPLEX, .49, (235, 235, 235), 1, cv2.LINE_AA)
    return tela


def esperar(intervalo, com_janela):
    if not com_janela:
        time.sleep(intervalo)
        return True
    fim = time.monotonic() + intervalo
    while True:
        if cv2.waitKey(10) & 0xFF == ord("q"):
            return False
        try:
            if cv2.getWindowProperty(JANELA, cv2.WND_PROP_VISIBLE) < 1:
                return False
        except cv2.error:
            # Algumas versões retornam erro depois que a janela é fechada.
            return False
        if time.monotonic() >= fim:
            return True


def capturar(args, recorte, csv_sessao, inicio, observar=None, parar=None):
    opener = build_opener(ProxyHandler({}))
    com_janela = not args.sem_janela
    total = falhas = tentativa = 0
    limite = inicio + args.duracao if args.duracao is not None else math.inf
    estado = "encerrada"
    try:
        while (parar is None or not parar.is_set()) and time.monotonic() < limite and (args.quadros is None or total < args.quadros):
            tentativa += 1
            inicio_get = time.monotonic()
            linha = {"tentativa": tentativa}
            try:
                quadro = receber_quadro(opener, args.url, min(args.timeout, max(limite - inicio_get, .01)))
            except ERROS_RECEPCAO as erro:
                agora = time.monotonic()
                falhas += 1
                linha.update(status="falha", tempo_s=f"{agora - inicio:.6f}",
                             http_ms=f"{(agora - inicio_get) * 1000:.2f}", erro=str(erro))
                imagem = np.zeros((RESOLUCAO[1], RESOLUCAO[0], 3), np.uint8)
                status = f"Falha de recepcao ({falhas})"
                print(f"{status}: {erro}", flush=True)
                intervalo = max(1., args.intervalo)
            else:
                total += 1
                nome = f"quadros/quadro_{total:06d}.jpg"
                if csv_sessao is not None:
                    gravar_atomico(args.saida / nome, quadro.jpeg)
                linha.update(status="ok", quadro=total, jpeg=nome, recepcao_utc=quadro.recepcao_utc,
                             tempo_s=f"{quadro.recepcao_monotonica - inicio:.6f}", bytes=len(quadro.jpeg),
                             http_ms=f"{quadro.http_ms:.2f}", idade_envio_ms=f"{quadro.idade_envio_ms:.2f}",
                             idade_recepcao_limite_ms=f"{quadro.idade_recepcao_limite_ms:.2f}")
                imagem = quadro.imagem
                status = f"Quadros: {total}  |  falhas: {falhas}" + ("  |  previa" if args.previa else "  |  gravando")
                if total == 1 or total % 20 == 0:
                    print(status, flush=True)
                intervalo = args.intervalo
            if csv_sessao is not None:
                csv_sessao.writerow(linha)
            if observar is not None:
                observar(linha, quadro.jpeg if linha["status"] == "ok" else None)
            if com_janela:
                cv2.imshow(JANELA, montar_previa(imagem, recorte, status))
            if args.quadros is not None and total >= args.quadros:
                break
            if not esperar(max(0., min(intervalo, limite - time.monotonic())), com_janela):
                break
    except KeyboardInterrupt:
        estado = "interrompida"
    return total, falhas, estado


def executar(args, recorte, observar=None, parar=None):
    com_janela = not args.sem_janela
    if com_janela:
        try:
            cv2.namedWindow(JANELA)
        except cv2.error as erro:
            raise RuntimeError("Use OpenCV com interface gráfica ou rode com --sem-janela.") from erro
    try:
        inicio = time.monotonic()
        manifesto = None
        if not args.previa:
            args.saida.mkdir(parents=True, exist_ok=False)
            (args.saida / "quadros").mkdir()
            destino = args.saida / "sessao.json"
            manifesto = {"schema": "coleta_esp32_v1", "sessao_id": uuid4().hex, "nome": args.saida.name,
                         "inicio_utc": utc_agora(), "estado": "em_andamento", "url": args.url,
                         "nota": args.nota, "jpeg_largura_altura": RESOLUCAO,
                         "csv_capturas": "capturas.csv", "intervalo_s": args.intervalo, "timeout_s": args.timeout,
                         "limite_quadros": args.quadros, "limite_duracao_s": args.duracao,
                         "previa": {"versao": VERSAO_PREVIA, "recorte": asdict(recorte),
                                    "largura_altura": ENTRADA, "cor": "cinza", "redimensionamento": "INTER_AREA"}}
            gravar_atomico(destino, json.dumps(manifesto, indent=2, ensure_ascii=False).encode("utf-8"))
        try:
            contexto = nullcontext() if manifesto is None else (args.saida / "capturas.csv").open(
                "x", encoding="utf-8", newline="", buffering=1)
            with contexto as arquivo:
                csv_sessao = csv.DictWriter(arquivo, fieldnames=CAMPOS) if arquivo is not None else None
                if csv_sessao is not None:
                    csv_sessao.writeheader()
                total, falhas, estado = capturar(args, recorte, csv_sessao, inicio, observar, parar)
        except Exception:
            if manifesto is not None:
                manifesto.update(estado="erro", fim_utc=utc_agora())
                gravar_atomico(destino, json.dumps(manifesto, indent=2, ensure_ascii=False).encode("utf-8"))
            raise
        if manifesto is not None:
            manifesto.update(estado=estado, fim_utc=utc_agora(), duracao_s=round(time.monotonic() - inicio, 3),
                             quadros=total, falhas=falhas)
            gravar_atomico(destino, json.dumps(manifesto, indent=2, ensure_ascii=False).encode("utf-8"))
        print(f"Fim: {total} quadros válidos, {falhas} falhas" + (f" | {args.saida}" if manifesto else ""), flush=True)
    finally:
        if com_janela:
            cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    destino = parser.add_mutually_exclusive_group(required=True)
    destino.add_argument("--saida", type=Path, help="pasta nova para uma sessão")
    destino.add_argument("--previa", action="store_true", help="mostra a câmera e o recorte sem gravar")
    parser.add_argument("--url", default=URL_PADRAO)
    parser.add_argument("--roi", type=int, nargs=4, metavar=("X", "Y", "L", "A"), default=(0, 80, 320, 160),
                        help="posição e tamanho em pixels sobre o quadro orientado (padrão: 0 80 320 160)")
    parser.add_argument("--espelhar-h", action="store_true", help="inverte esquerda e direita na prévia")
    parser.add_argument("--espelhar-v", action="store_true", help="inverte cima e baixo na prévia")
    parser.add_argument("--sem-janela", action="store_true", help="coleta por SSH sem abrir a prévia")
    parser.add_argument("--nota", default="", help="descrição da montagem, iluminação e trecho da pista")
    parser.add_argument("--quadros", type=int, help="encerra ao atingir este total de quadros válidos")
    parser.add_argument("--duracao", type=float, help="segundos máximos para iniciar novas capturas")
    parser.add_argument("--intervalo", type=float, default=.2, help="segundos de pausa entre capturas válidas")
    parser.add_argument("--timeout", type=float, default=3., help="timeout de operações HTTP em segundos")
    args = parser.parse_args()
    if args.previa and args.sem_janela:
        parser.error("--previa precisa de janela")
    for nome, valor in (("--timeout", args.timeout), ("--duracao", args.duracao), ("--quadros", args.quadros)):
        if valor is not None and (not math.isfinite(valor) or valor <= 0):
            parser.error(f"{nome} deve ser positivo e finito")
    if not math.isfinite(args.intervalo) or args.intervalo < 0:
        parser.error("--intervalo deve ser não negativo e finito")
    if args.saida is not None and args.saida.exists():
        parser.error("--saida deve apontar para uma pasta nova")
    try:
        recorte = RecorteESP32(*args.roi, espelhar_h=args.espelhar_h, espelhar_v=args.espelhar_v)
    except ValueError as erro:
        parser.error(str(erro))
    executar(args, recorte)


if __name__ == "__main__":
    main()
