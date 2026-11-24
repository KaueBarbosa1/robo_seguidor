"""Teste isolado de UMA roda, com rodas suspensas; nao executar sem autorizacao.

--pwm: PWM direto (comando M), sem PI.
--pps: alvo em pulsos/s (comando R); o PI pode aplicar impulso de partida.
Exemplo futuro: --roda esquerda --sentido frente --pwm 40 --tempo 0.5
Nao trocar fios sem revisar as inversoes existentes no firmware.
"""
import argparse
import math
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg
from motor.serial_com import ArduinoSerial


def argumentos(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--porta", default=cfg.SERIAL_PORTA)
    ap.add_argument("--baud", type=int, default=cfg.SERIAL_BAUD)
    ap.add_argument("--roda", required=True, choices=("esquerda", "direita"))
    ap.add_argument("--sentido", choices=("frente", "re"), default="frente")
    modo = ap.add_mutually_exclusive_group(required=True)
    modo.add_argument("--pwm", type=int, help="PWM direto: valor par entre 2 e 80")
    modo.add_argument("--pps", type=int, help="velocidade PI: alvo de 1 a 4 pulsos/s; NAO limita PWM")
    ap.add_argument("--tempo", type=float, default=.5, help="pulso maior que zero e de no maximo 1 s")
    a = ap.parse_args(argv)
    if not math.isfinite(a.tempo) or not 0 < a.tempo <= 1:
        ap.error("--tempo deve ser finito, maior que zero e no maximo 1 s")
    if a.pwm is not None and (not 2 <= a.pwm <= 80 or a.pwm % 2):
        ap.error("--pwm exige valor par entre 2 e 80")
    if a.pps is not None and not 1 <= a.pps <= 4:
        ap.error("--pps exige alvo de 1 a 4 pulsos/s")
    if cfg.FIRMWARE_COM_CAMERA:
        ap.error("Exige o perfil existente sem camera no Uno")
    return a


def verificar_exclusividade(porta):
    """Somente consulta; nao para servicos, nao mata processos nem abre serial."""
    for escopo in ([], ["--user"]):
        r = subprocess.run(["systemctl", *escopo, "is-active", "robo.service"],
                           capture_output=True, text=True, timeout=3)
        if r.returncode not in (3, 4) or r.stdout.strip() not in ("inactive", "unknown"):
            raise RuntimeError("robo.service ativo ou estado indisponivel: " +
                               ("usuario" if escopo else "sistema"))
    if not Path(porta).exists():
        raise RuntimeError("Porta serial inexistente: " + porta)
    r = subprocess.run(["fuser", "-v", porta], capture_output=True, text=True, timeout=3)
    if r.returncode != 1 or r.stdout.strip() or r.stderr.strip():
        raise RuntimeError("Serial ocupada ou consulta inconclusiva; confira com sudo fuser -v " + porta)


def _telemetria(ard):
    agora = time.monotonic()
    s, d = ard.sensores(), ard.estado_motores()
    for nome, p in (("sensores", s), ("motores/F8", d)):
        if p is None or not 0 <= agora - p.timestamp <= cfg.SENSOR_TIMEOUT_S:
            raise RuntimeError("Telemetria ausente/vencida: " + nome)
    if (s.falha_sensor or s.avanco_bloqueado or s.distancia_cm is None or
            not math.isfinite(s.distancia_cm) or s.distancia_cm < 0):
        raise RuntimeError("Ultrassom invalido ou frente bloqueada")
    if d.falha_encoder:
        raise RuntimeError("Falha de encoder: ensaio interrompido")
    return s, d


def executar_pulso(ard, a):
    """Reutiliza APIs M/R existentes; chamado com serial falsa nos testes."""
    reconexoes = ard.estatisticas["reconexoes"]
    referencia, _ = _telemetria(ard)
    anteriores = (referencia.ticks_esq, referencia.ticks_dir)
    valor = a.pwm if a.pwm is not None else a.pps
    valor *= 1 if a.sentido == "frente" else -1
    pedido = (valor, 0) if a.roda == "esquerda" else (0, valor)
    enviar = ard.pwm if a.pwm is not None else ard.velocidade
    fim = time.monotonic() + a.tempo
    try:
        while time.monotonic() < fim:
            s, d = _telemetria(ard)
            if ard.estatisticas["reconexoes"] != reconexoes:
                raise RuntimeError("Reconexao serial: nao retomar o pulso")
            ticks = (s.ticks_esq, s.ticks_dir)
            if any(t < ant for t, ant in zip(ticks, anteriores)):
                raise RuntimeError("Contadores regrediram: nao retomar o pulso")
            anteriores = ticks
            enviar(*pedido)
            time.sleep(.02)
        s, d = _telemetria(ard)
        print(f"Encoders: E +{s.ticks_esq - referencia.ticks_esq}, "
              f"D +{s.ticks_dir - referencia.ticks_dir}; "
              f"ultimo PWM informado E={d.pwm_esq} D={d.pwm_dir}")
    finally:
        ard.parar(repetir=3)


def main(argv=None):
    a = argumentos(argv)
    ard = None
    antigo = signal.getsignal(signal.SIGTERM)
    def interromper(*_):
        raise KeyboardInterrupt
    try:
        verificar_exclusividade(a.porta)
        unidade = f"PWM direto {a.pwm}" if a.pwm is not None else f"alvo PI {a.pps} pulsos/s (partida ate PWM80 no perfil atual)"
        print(f"UMA roda: {a.roda}, {a.sentido}, {unidade}, {a.tempo:g} s.")
        if input("Teste fisico autorizado, rodas suspensas e corte de energia acessivel? (s/N) ").strip().lower() != "s":
            return 1
        verificar_exclusividade(a.porta)
        signal.signal(signal.SIGTERM, interromper)
        ard = ArduinoSerial(porta=a.porta, baud=a.baud)
        ard.conectar()
        ard.parar(repetir=3)
        ard.configurar_servo(False)
        # Aguarda sensores/servo estabilizarem sem solicitar movimento.
        limite = time.monotonic() + 2
        while True:
            ard.parar()
            try:
                _telemetria(ard)
                break
            except RuntimeError:
                if time.monotonic() >= limite:
                    raise
                time.sleep(.05)
        executar_pulso(ard, a)
        return 0
    except KeyboardInterrupt:
        print("Interrompido: solicitando parada.")
        return 130
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(f"Teste recusado/interrompido: {exc}", file=sys.stderr)
        return 2
    finally:
        try:
            if ard is not None:
                try:
                    ard.parar(repetir=3)
                finally:
                    ard.fechar()
        finally:
            signal.signal(signal.SIGTERM, antigo)


if __name__ == "__main__":
    raise SystemExit(main())
