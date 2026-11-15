"""Ponto de entrada. Cria o estado compartilhado, sobe as 3 threads e supervisiona.

    visão    -> mede o erro da linha e publica no EstadoRobo
    voz      -> classifica comandos e chama aplicar_comando() (prioridade absoluta)
    controle -> único que escreve nos motores (via ArduinoSerial)
    remoto   -> (opcional) celular Android por Bluetooth serial: anda/para pelo modo MANUAL (remoto/)
    A imagem vem da OV7670 ligada ao Arduino (pela serial); o mesmo Arduino aciona os motores (L298N).
"""
import argparse
import logging
import signal
import sys
import threading
import time

from controle import ThreadControle, aplicar_comando
from estado import EstadoRobo
from motor.nulo import ArduinoNulo
from motor.serial_com import ArduinoSerial
from visao.detector import ThreadVisao
from visao.fontes import criar_fonte
import config as cfg
from voz.reconhecimento import ThreadVoz

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
log = logging.getLogger("main")


def abrir_fonte(nome: str, motor):
    """Abre a fonte de imagem. Se não der, o robô continua só com a voz (como sem câmera), com aviso claro."""
    if nome == "arduino" and not cfg.FIRMWARE_COM_CAMERA:
        log.warning("FIRMWARE_COM_CAMERA = False: o Arduino não envia imagem; seguindo sem câmera (só voz e controle remoto).")
        return criar_fonte("nenhuma")
    if nome == "arduino" and not hasattr(motor, "proximo_quadro"):
        log.warning("Modo --sem-arduino: não há imagem da OV7670. Use FONTE_IMAGEM = \"simulada\" para uma linha falsa.")
        return criar_fonte("nenhuma")
    try:
        fonte = criar_fonte(nome, motor)
        if hasattr(fonte, "iniciar"):
            fonte.iniciar()                                 # só a câmera CSI (opcional) precisa abrir
    except Exception as e:
        log.error("CÂMERA INDISPONÍVEL (%s). Sem imagem o robô NÃO segue linha; comandos de voz continuam. "
                  "Confira docs/02_bringup_camera.md e python tools/verificar_ambiente.py", e)
        return criar_fonte("nenhuma")
    return fonte


def main() -> None:
    ap = argparse.ArgumentParser(description="Robô seguidor de linha com voz")
    ap.add_argument("--sem-arduino", action="store_true",
                    help="não abre a serial: motores/sensores simulados (testa câmera, visão e voz sem o Arduino)")
    args = ap.parse_args()

    parar = threading.Event()
    estado = EstadoRobo()
    motor = ArduinoNulo() if args.sem_arduino else ArduinoSerial()
    try:
        motor.conectar()
    except Exception as e:
        log.error("Não consegui abrir o Arduino em %s (%s). Confira a porta (ls /dev/ttyACM*) e SERIAL_PORTA em config.py; "
                  "para testar sem ele: python main.py --sem-arduino", cfg.SERIAL_PORTA, e)
        sys.exit(1)
    fonte = abrir_fonte(cfg.FONTE_IMAGEM, motor)

    def ao_comando_de_voz(comando: str) -> None:
        aplicar_comando(estado, motor, comando)

    threads = [
        ThreadControle(estado, motor, parar),
        ThreadVisao(estado, parar, fonte),
        ThreadVoz(ao_comando_de_voz, parar),
    ]

    if cfg.APRENDIZADO_ATIVO:
        from aprendizado.robo_real import ThreadAprendizado
        threads.append(ThreadAprendizado(estado, motor, parar, fonte))

    opcionais = []                                          # falha aqui não derruba o robô (só avisa)
    if cfg.REMOTO_BT_ATIVO:
        from remoto.bluetooth_spp import ThreadBluetooth
        opcionais.append(ThreadBluetooth(estado, motor, parar))

    signal.signal(signal.SIGINT, lambda *_: parar.set())
    signal.signal(signal.SIGTERM, lambda *_: parar.set())

    for t in threads + opcionais:
        t.start()
    log.info("Robô pronto. Parado até ouvir 'siga'%s.", " ou receber comando do celular" if opcionais else "")

    try:
        while not parar.is_set():
            if not all(t.is_alive() for t in threads):      # qualquer thread morta = parada de segurança
                log.error("Uma thread morreu; encerrando.")
                break
            time.sleep(0.2)
    finally:
        parar.set()
        for t in threads + opcionais:
            t.join(timeout=2.0)
        motor.parar(repetir=3)
        motor.fechar()
        if hasattr(fonte, "parar"):
            fonte.parar()
        log.info("Encerrado.")


if __name__ == "__main__":
    main()
