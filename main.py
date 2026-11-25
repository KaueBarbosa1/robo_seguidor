"""Ponto de entrada. Cria o estado compartilhado, sobe as 3 threads e supervisiona.

    visão    -> mede o erro da linha e publica no EstadoRobo
    voz      -> classifica comandos e chama aplicar_comando() (prioridade absoluta)
    controle -> único que escreve nos motores (via ArduinoSerial)
    remoto   -> (opcional) celular Android por Bluetooth serial: anda/para pelo modo MANUAL (remoto/)
    Imagem pela fonte selecionada (inclui ESP32 HTTP); motores e sensores continuam no Arduino.
"""
import argparse
import logging
import signal
import threading
import time

from controle import ThreadControle, aplicar_comando
from estado import EstadoRobo
from motor.nulo import ArduinoNulo
from motor.serial_com import ArduinoSerial
from visao.detector import ThreadVisao
from visao.fontes import criar_fonte
from visao.esp32_cam import CameraESP32
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
            fonte.iniciar()                                 # fontes com captura em segundo plano
    except Exception as e:
        log.error("CÂMERA INDISPONÍVEL (%s). Sem imagem o robô NÃO segue linha; comandos de voz continuam. "
                  "Confira docs/02_bringup_camera.md e python tools/verificar_ambiente.py", e)
        return criar_fonte("nenhuma")
    return fonte


def main() -> None:
    ap = argparse.ArgumentParser(description="Robô seguidor de linha com voz")
    ap.add_argument("--sem-arduino", action="store_true",
                    help="não abre a serial: motores/sensores simulados (testa câmera, visão e voz sem o Arduino)")
    ap.add_argument("--fonte-imagem", choices=("arduino", "csi", "nenhuma", "simulada", "esp32"),
                    default=cfg.FONTE_IMAGEM, help="seleciona a fonte sem alterar config.py")
    ap.add_argument("--politica", choices=("opencv", "cnn-rl-sombra", "cnn-rl"), default=cfg.POLITICA_LINHA)
    ap.add_argument("--pacote-cnn-rl", default=cfg.CNN_RL_PACOTE, help="manifesto do par CNN/RL treinado")
    ap.add_argument('--benchmark', action='store_true', help='grava metricas locais; nao inicia movimento')
    ap.add_argument('--benchmark-dir', default=str(cfg.BENCHMARK_DIR))
    ap.add_argument('--benchmark-nota', default='', help='condicoes do ensaio, pista, alimentacao e repeticao')
    args = ap.parse_args()
    pacote = None
    if args.politica != "opencv":
        if args.fonte_imagem != "esp32" or cfg.APRENDIZADO_ATIVO or not args.pacote_cnn_rl:
            ap.error("CNN/RL exige fonte esp32, pacote pareado e aprendizado online desligado")
        from aprendizado.inferencia_esp32 import Pacote
        try:
            pacote = Pacote(args.pacote_cnn_rl)
            if args.politica == "cnn-rl":
                pacote.validar_motores()
        except (ValueError, OSError, KeyError, TypeError) as exc:
            ap.error(str(exc))
    if args.fonte_imagem == "esp32" and cfg.APRENDIZADO_ATIVO:
        ap.error("ESP32 com aprendizado ativo exige contrato CNN compatível; mantenha APRENDIZADO_ATIVO=False")

    parar = threading.Event()
    estado = EstadoRobo()
    motor = ArduinoNulo() if args.sem_arduino else ArduinoSerial()
    fonte = None
    painel = None
    inferencia = None
    benchmark = None
    iniciadas = []
    try:
        try:
            motor.conectar()
        except Exception as e:
            log.error("Não consegui abrir o Arduino em %s (%s). Para testar sem ele: --sem-arduino",
                      cfg.SERIAL_PORTA, e)
            raise SystemExit(1)
        fonte = abrir_fonte(args.fonte_imagem, motor)
        if pacote is not None:
            if not isinstance(fonte, CameraESP32):
                raise RuntimeError("CNN/RL sem fonte ESP32 disponivel")
            from aprendizado.inferencia_esp32 import ThreadInferencia
            inferencia = ThreadInferencia(estado, motor, parar, fonte, pacote,
                                         sombra=args.politica == "cnn-rl-sombra")
        if cfg.PAINEL_COLETA_ATIVO and isinstance(fonte, CameraESP32):
            from tools.painel_coleta import Painel
            try:
                painel = Painel(fonte, cfg.PAINEL_COLETA_DIR, cfg.PAINEL_COLETA_HOST,
                                cfg.PAINEL_COLETA_PORTA, cfg.PAINEL_COLETA_DURACAO_S,
                                cfg.PAINEL_COLETA_INTERVALO_S)
                if inferencia is not None:
                    painel.coleta.diagnostico_rl = inferencia.status
                painel.iniciar()
                log.info("Painel da camera em http://IP_DA_PI:%s — aguardando clique para gravar.",
                         cfg.PAINEL_COLETA_PORTA)
            except OSError as exc:
                log.error("Painel indisponivel (%s); confira se outro painel ocupa a porta. Visao continua.", exc)


        def ao_comando_de_voz(comando: str) -> None:
            aplicar_comando(estado, motor, comando)

        threads = [
            (ThreadControle(estado, motor, parar, fonte, inferencia_rl=inferencia) if inferencia is not None
             else ThreadControle(estado, motor, parar, fonte)),
            ThreadVisao(estado, parar, fonte),
            ThreadVoz(ao_comando_de_voz, parar),
        ]
        if inferencia is not None:
            threads.append(inferencia)
            log.warning("Politica %s: dominio=%s; inferencia congelada, sem treinamento.", args.politica, pacote.dominio)
        if cfg.APRENDIZADO_ATIVO:
            from aprendizado.robo_real import ThreadAprendizado
            threads.append(ThreadAprendizado(estado, motor, parar, fonte))
        opcionais = []
        if cfg.REMOTO_BT_ATIVO:
            from remoto.bluetooth_spp import ThreadBluetooth
            opcionais.append(ThreadBluetooth(estado, motor, parar))
        if args.benchmark:
            from monitoramento.benchmark import Benchmark
            from monitoramento.telemetria import Telemetria
            try:
                benchmark = Benchmark(args.benchmark_dir,
                    Telemetria(estado, motor, fonte, threads[0], inferencia,
                               args.sem_arduino, args.politica,
                               fonte_simulada=args.fonte_imagem == 'simulada'),
                    intervalo=cfg.BENCHMARK_INTERVALO_S, capacidade=cfg.BENCHMARK_CAPACIDADE,
                    max_bytes=cfg.BENCHMARK_MAX_BYTES,
                    condicoes=dict(nota=args.benchmark_nota, fonte=args.fonte_imagem,
                        politica=args.politica, sem_arduino=args.sem_arduino,
                        controle_hz=cfg.FREQ_CONTROLE_HZ, kp=cfg.KP, kd=cfg.KD,
                        esp32_url=cfg.ESP32_URL, pacote=args.pacote_cnn_rl,
                        aprendizado_ativo=cfg.APRENDIZADO_ATIVO))
                log.info('Benchmark local: %s', benchmark.iniciar())
            except (OSError, ValueError) as exc:
                log.error('Benchmark indisponivel; controle preservado: %s', exc)
        def solicitar_parada(*_):
            parar.set()
            estado.encerrar()

        signal.signal(signal.SIGINT, solicitar_parada)
        signal.signal(signal.SIGTERM, solicitar_parada)
        for t in threads + opcionais:
            t.start()
            iniciadas.append(t)
        log.info("Robô pronto. Parado até ouvir 'siga'%s.",
                 " ou receber comando do celular" if opcionais else "")
        while not parar.is_set():
            if not all(t.is_alive() for t in threads):
                log.error("Uma thread morreu; encerrando.")
                break
            time.sleep(0.2)
    finally:
        parar.set()
        estado.encerrar()
        # Parar antes de aguardar threads, inclusive se inicialização falhar.
        try:
            motor.parar(repetir=3)
        finally:
            try:
                for t in iniciadas:
                    t.join(timeout=2.0)
            finally:
                try:
                    motor.parar(repetir=3)
                finally:
                    try:
                        motor.fechar()
                    finally:
                        try:
                            if painel is not None:
                                painel.parar()
                        finally:
                            try:
                                if fonte is not None and hasattr(fonte, "parar"):
                                    fonte.parar()
                            finally:
                                if benchmark is not None:
                                    benchmark.parar()
        log.info("Encerrado.")


if __name__ == "__main__":
    main()
