"""Teste do servo JA INTEGRADO no robo_firmware, pela USB da Raspberry Pi.

Na Raspberry Pi, parar robo.service antes; usar .venv/bin/python tools/testar_servo.py
Mantem motores parados. Ctrl+C pede retorno ao centro. Sem Monitor Serial ASCII.
"""
import argparse
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg  # noqa: E402
from motor.serial_com import ArduinoSerial  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--porta', default=cfg.SERIAL_PORTA)
    ap.add_argument('--modo', choices=['varrer', 'centro', 'inspecionar'], default='varrer')
    ap.add_argument('--tempo', type=float, default=10., help='duracao do teste em segundos')
    ap.add_argument('--ajuste-us', type=int, default=0, help='offset do centro do firmware; passo de 10 us')
    a = ap.parse_args()
    if not math.isfinite(a.tempo) or a.tempo <= 0:
        ap.error('--tempo deve ser positivo e finito')
    if a.ajuste_us % 10 or not -250 <= a.ajuste_us <= 250:
        ap.error('--ajuste-us deve ser multiplo de 10 entre -250 e 250')
    if cfg.FIRMWARE_COM_CAMERA:
        ap.error('O servo integrado exige firmware USAR_CAMERA=0 e FIRMWARE_COM_CAMERA=False')
    if a.modo == 'inspecionar' and a.ajuste_us:
        ap.error('Inspecao usa o centro configurado no firmware; deixe --ajuste-us 0')
    ard = ArduinoSerial(porta=a.porta)
    confirmou = False
    concluiu = False
    impressas = set()
    try:
        ard.conectar()
        inicio = time.monotonic()
        ultimo_log = 0.
        print('Teste do servo: mantenha a potencia dos motores desligada. Modo:', a.modo, flush=True)
        while time.monotonic() - inicio < a.tempo:
            ard.parar()
            if a.modo == 'inspecionar':
                ard.inspecionar_obstaculo()
            else:
                ard.configurar_servo(a.modo == 'varrer', a.ajuste_us)
            agora = time.monotonic()
            status = ard.status_servo()
            recente = status is not None and agora - status.timestamp <= .5
            modo_correto = status is not None and (
                getattr(status, 'inspecao', False) if a.modo == 'inspecionar' else
                not getattr(status, 'inspecao', False) and status.varredura == (a.modo == 'varrer'))
            if recente and status.ativo and modo_correto:
                confirmou = True
                if a.modo == 'inspecionar':
                    amostras = ard.leituras_inspecao()
                    for amostra in amostras:
                        chave = (amostra.rodada, amostra.angulo_nominal)
                        if amostra.timestamp >= inicio and chave not in impressas:
                            print(f'Posicao nominal {amostra.angulo_nominal}: '
                                  f'{amostra.distancia_cm if amostra.distancia_cm is not None else "DESCONHECIDA"} cm', flush=True)
                            impressas.add(chave)
                    if (status.concluida and len(amostras) == 3 and
                            all(amostra.timestamp >= inicio for amostra in amostras)):
                        concluiu = True
                        break
                if agora - ultimo_log >= .5:
                    print(f'Comando angular: {status.angulo_nominal} graus nominais; '
                          f'centro={status.centro_us} us; varrendo={status.varredura}; '
                          f'centro estavel={status.centro_pronto}', flush=True)
                    ultimo_log = agora
            elif agora - inicio > 2.:
                raise RuntimeError('Sem resposta recente do servo. Confira firmware integrado, USAR_SERVO e porta.')
            time.sleep(.05)  # renova servo antes do timeout de 400 ms
        if a.modo == 'inspecionar' and not concluiu:
            raise RuntimeError('Inspecao nao concluiu tres posicoes no prazo; nenhuma passagem foi liberada.')
        if not confirmou:
            raise RuntimeError('Teste terminou sem confirmacao do firmware; aumente --tempo se necessario.')
    except KeyboardInterrupt:
        print('\nInterrompido: solicitando centro.', flush=True)
    finally:
        try:
            ard.parar(repetir=3)
            for _ in range(3):
                ard.configurar_servo(False, a.ajuste_us)
                time.sleep(.05)
        finally:
            ard.fechar()
    print('Motores parados; centro solicitado. Isso nao comprova o angulo fisico do servo.', flush=True)


if __name__ == '__main__':
    main()
