"""Teste com rodas suspensas: --pps mede PI; --pwm mede resposta direta do motor."""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg
from motor.serial_com import ArduinoSerial


def partir_pwm(ard, partida, sustentacao):
    """Ensaio parado no apoio: retirar a partida por roda no primeiro pulso.

    Prazo de um segundo para ambas, sem rearmar tentativas automaticamente.
    A confirmacao chega pela telemetria; nao e corte fisico no instante do pulso.
    """
    inicio = time.monotonic()
    referencia = None
    anteriores = None
    iniciou = [False, False]
    reconexoes = ard.estatisticas['reconexoes']
    print(f'Partida PWM {partida} ate o primeiro pulso por roda (maximo 1 s); depois PWM {sustentacao}.')
    try:
        while True:
            agora = time.monotonic()
            s = ard.sensores()
            if s is None or not 0 <= agora - s.timestamp <= cfg.SENSOR_TIMEOUT_S:
                raise RuntimeError('Telemetria vencida durante a partida')
            if s.falha_sensor or s.avanco_bloqueado:
                raise RuntimeError('Frente bloqueada durante a partida')
            if ard.estatisticas['reconexoes'] != reconexoes:
                raise RuntimeError('Reconexao serial durante a partida')
            if agora - inicio >= 1.:
                faltam = ', '.join(nome for nome, ok in zip(('E', 'D'), iniciou) if not ok)
                raise RuntimeError(f'Sem primeiro pulso em 1 s: {faltam}; ensaio encerrado')
            ticks = (s.ticks_esq, s.ticks_dir)
            if referencia is None:
                referencia = anteriores = ticks
            if any(t < r for t, r in zip(ticks, anteriores)):
                raise RuntimeError('Contadores regrediram durante a partida')
            anteriores = ticks
            for i, nome in enumerate(('E', 'D')):
                if not iniciou[i] and ticks[i] > referencia[i]:
                    iniciou[i] = True
                    print(f'Primeiro pulso {nome}: reduzindo para PWM {sustentacao}.')
            if all(iniciou):
                ard.pwm(sustentacao, sustentacao)
                return s
            ard.pwm(*(sustentacao if ok else partida for ok in iniciou))
            time.sleep(.02)
    except BaseException:
        ard.parar(repetir=3)
        raise


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--porta", default=cfg.SERIAL_PORTA)
    modo = ap.add_mutually_exclusive_group()
    modo.add_argument("--pps", type=int, default=20, help="alvo por roda, -120..120 pulsos/s")
    modo.add_argument("--pwm", type=int, help="bancada: PWM direto par de 0..120, sem PI e sem alterar config.py")
    ap.add_argument('--pwm-partida', type=int,
                    help='com --pwm: PWM maior ate o primeiro pulso por roda, por no maximo 1 s')
    ap.add_argument("--tempo", type=float, default=5)
    a = ap.parse_args()
    if not -120 <= a.pps <= 120 or not 0 < a.tempo <= 30:
        ap.error("Use -120..120 pulsos/s e duracao entre 0 e 30 s")
    if a.pwm is not None and (not 0 <= a.pwm <= 120 or a.pwm % 2):
        ap.error('Use PWM par entre 0 e 120 (o protocolo tem resolucao de 2)')
    if a.pwm_partida is not None and (a.pwm is None or a.pwm <= 0 or
                                      not a.pwm < a.pwm_partida <= 120 or a.pwm_partida % 2):
        ap.error('--pwm-partida exige --pwm positivo e valor par maior, ate 120')
    if cfg.FIRMWARE_COM_CAMERA:
        ap.error("Exige FIRMWARE_COM_CAMERA=False")
    if input("Rodas suspensas, sensores ligados e frente livre? (s/N) ").strip().lower() != "s":
        return
    ard = ArduinoSerial(porta=a.porta, baud=115200)
    try:
        ard.conectar()
        ard.parar(repetir=3)
        time.sleep(0.3)
        anterior = ard.sensores()
        if anterior is None:
            raise RuntimeError("Sem telemetria do Arduino")
        if anterior.falha_sensor or anterior.avanco_bloqueado:
            raise RuntimeError("Frente bloqueada ou ultrassom sem leitura valida")
        if a.pwm_partida is not None:
            anterior = partir_pwm(ard, a.pwm_partida, a.pwm)
        fim = time.monotonic() + a.tempo
        ultimo_print = time.monotonic()
        while time.monotonic() < fim:
            if a.pwm is not None:
                ard.pwm(a.pwm, a.pwm)
            else:
                ard.velocidade(a.pps, a.pps)
            time.sleep(0.05)
            agora = time.monotonic()
            atual = ard.sensores()
            if atual is None or agora - atual.timestamp > cfg.SENSOR_TIMEOUT_S:
                raise RuntimeError("Telemetria vencida")
            diagnostico = ard.estado_motores()
            diagnostico_recente = diagnostico is not None and 0 <= agora - diagnostico.timestamp <= cfg.SENSOR_TIMEOUT_S
            if a.pwm is None and diagnostico_recente and diagnostico.falha_encoder:
                raise RuntimeError('Firmware confirmou falha de encoder: encerrando ensaio e solicitando parada')
            if agora - ultimo_print >= 0.5 and atual.timestamp > anterior.timestamp:
                dt = atual.timestamp - anterior.timestamp
                de = (atual.ticks_esq - anterior.ticks_esq) % 0x4000
                dd = (atual.ticks_dir - anterior.ticks_dir) % 0x4000
                pedido = f'PWM direto {a.pwm}' if a.pwm is not None else f'Alvo {abs(a.pps)} p/s'
                detalhes = (f' | PWM aplicado E={diagnostico.pwm_esq} D={diagnostico.pwm_dir}'
                            f' | falha encoder={diagnostico.falha_encoder}'
                            f' | PI ativo={diagnostico.pi_ativo}'
                            f' | reforco E={diagnostico.reforco_esq} D={diagnostico.reforco_dir}'
                            if diagnostico_recente else ' | diagnostico de motores indisponivel/vencido')
                print(f"{pedido} | "
                      f"E {de/dt:.1f} p/s | D {dd/dt:.1f} p/s"
                      f" | frente bloqueada={atual.avanco_bloqueado} falha sensor={atual.falha_sensor}{detalhes}")
                solicitado = a.pwm if a.pwm is not None else a.pps
                if solicitado and (de == 0 or dd == 0):
                    print("Sem pulsos nesta janela: " +
                          ", ".join(nome for nome, delta in (("esquerda (D2)", de),
                                                               ("direita (D3)", dd)) if delta == 0) +
                          ". Se a roda gira, conferir encoder/fios; se nao gira, conferir partida.")
                anterior, ultimo_print = atual, agora
    except KeyboardInterrupt:
        pass
    finally:
        ard.parar(repetir=3)
        ard.fechar()


if __name__ == "__main__":
    main()
