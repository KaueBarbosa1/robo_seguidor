"""Ensaio do modo 4: por padrao somente varre; --pps solicita avanco reto por PI.

Primeiro usar com potencia dos motores desligada. Teste de rodas somente
suspensas, apos calibracao no firmware. Nao executa desvio nem usa CNN.
"""
import argparse
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg
from motor.serial_com import ArduinoSerial


def falhas_confirmacao(status, sensores, agora):
    """Distingue ausencia, atraso e modo errado sem atribuir causa ao hardware."""
    falhas = []
    for nome, pacote, prazo in [('servo', status, .5),
                                ('sensores', sensores, cfg.SENSOR_TIMEOUT_S)]:
        if pacote is None:
            falhas.append(f'{nome}: nenhum pacote recebido')
        else:
            idade = agora - pacote.timestamp
            if not 0 <= idade <= prazo:
                falhas.append(f'{nome}: idade={idade:.3f}s (limite={prazo:.3f}s)')
    if status is not None:
        if not status.ativo:
            falhas.append('servo: flag ativo=False')
        if not status.sonar_movimento:
            falhas.append('servo: modo 4 nao confirmado')
    return falhas


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--porta', default=cfg.SERIAL_PORTA)
    ap.add_argument('--pps', type=int, default=0, help='0 somente varre; positivo solicita PI reto')
    ap.add_argument('--tempo', type=float, default=15.)
    a = ap.parse_args()
    if not 0 <= a.pps <= 120 or not math.isfinite(a.tempo) or not 0 < a.tempo <= 30:
        ap.error('Use 0..120 pulsos/s e tempo positivo de ate 30 s')
    if cfg.FIRMWARE_COM_CAMERA:
        ap.error('Exige firmware sem OV7670')
    ard = ArduinoSerial(porta=a.porta)
    confirmou = False
    try:
        ard.conectar()
        ard.parar(repetir=3)
        inicio = ultimo_log = time.monotonic()
        ultima_medida = inicio
        print('Modo 4: sonar manual durante marcha (perfil definido no firmware). Primeiro ensaio com motores desligados; depois rodas suspensas.', flush=True)
        if not a.pps:
            print('Somente observacao: nenhum comando de velocidade sera enviado; encoders zerados sao esperados.', flush=True)
        while time.monotonic() - inicio < a.tempo:
            ard.iniciar_sonar_movimento()
            status, s = ard.status_servo(), ard.sensores()
            agora = time.monotonic()
            falhas = falhas_confirmacao(status, s, agora)
            if falhas:
                ard.parar()
                if agora - inicio > 2.:
                    reconexoes = getattr(ard, 'estatisticas', {}).get('reconexoes', 'indisponivel')
                    raise RuntimeError('Confirmacao perdida/ausente: ' + '; '.join(falhas) +
                                       f'. Tentativas de reconexao serial={reconexoes}. '
                                       'Motores parados; esta falha nao identifica sozinha a causa.')
            else:
                confirmou = True
                if a.pps and s.sonar_nao_calibrado and not s.sonar_experimental:
                    raise RuntimeError('Avanco bloqueado: falta calibrar encoders, frenagem e limites SONAR_MOV_* no firmware.')
                if a.pps and not s.falha_sensor and not s.avanco_bloqueado:
                    ard.velocidade(a.pps, a.pps)
                else:
                    ard.parar()
                for m in ard.consumir_leituras_sonar():
                    recebido_em = time.monotonic()
                    if inicio <= m.timestamp <= recebido_em and recebido_em - m.timestamp <= .5:
                        ultima_medida = agora
                        print(f'Sonar {m.angulo_nominal} graus: {m.distancia_cm if m.distancia_cm is not None else "DESCONHECIDA"} cm', flush=True)
                if agora - ultimo_log >= .5:
                    print(f'Frente descontada: {s.distancia_cm} cm | bloqueado={s.avanco_bloqueado} | '
                          f'falha={s.falha_sensor} | sem calibracao={s.sonar_nao_calibrado} | '
                          f'experimental={s.sonar_experimental} | '
                          f'lateral E={getattr(s, "lateral_esq_bloqueada", False)} '
                          f'D={getattr(s, "lateral_dir_bloqueada", False)} | '
                          f'idade servo={agora - status.timestamp:.3f}s '
                          f'sensores={agora - s.timestamp:.3f}s | '
                          f'encoders E={s.ticks_esq} D={s.ticks_dir}', flush=True)
                    ultimo_log = agora
                if agora - ultima_medida > 3.:
                    raise RuntimeError('Modo 4 sem medidas novas; encerrando.')
            time.sleep(.05)
        if not confirmou:
            raise RuntimeError('Ensaio terminou sem confirmacao do modo 4')
    except KeyboardInterrupt:
        print('Interrompido; solicitando parada e centro.', flush=True)
    finally:
        try:
            ard.parar(repetir=3)
            for _ in range(3):
                ard.configurar_servo(False)
                time.sleep(.05)
        finally:
            ard.fechar()


if __name__ == '__main__':
    main()
