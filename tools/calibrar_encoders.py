"""Mede encoders manualmente, no piso ou com rodas suspensas; motores desligados."""
import argparse
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg
from motor.serial_com import ArduinoSerial


def calcular(distancia_mm, pulsos_esq, pulsos_dir):
    if not math.isfinite(distancia_mm) or distancia_mm <= 0 or min(pulsos_esq, pulsos_dir) <= 0:
        raise ValueError('Distancia positiva e pulsos nas duas rodas sao obrigatorios')
    return {'distancia_mm': distancia_mm, 'pulsos_esq': pulsos_esq, 'pulsos_dir': pulsos_dir,
            'mm_pulso_esq': distancia_mm / pulsos_esq, 'mm_pulso_dir': distancia_mm / pulsos_dir}


def calcular_por_voltas(voltas, pulsos_esq, pulsos_dir, diametro_esq_mm=None, diametro_dir_mm=None):
    if not isinstance(voltas, int) or isinstance(voltas, bool) or voltas <= 0 or min(pulsos_esq, pulsos_dir) <= 0:
        raise ValueError('Voltas inteiras positivas e pulsos nas duas rodas sao obrigatorios')
    diametros = (diametro_esq_mm, diametro_dir_mm)
    if any(d is not None for d in diametros) and not all(d is not None for d in diametros):
        raise ValueError('Informe os dois diametros ou deixe ambos para depois')
    dados = {'metodo': 'rodas_suspensas', 'voltas_por_roda': voltas,
             'pulsos_esq': pulsos_esq, 'pulsos_dir': pulsos_dir,
             'pulsos_por_volta_esq': pulsos_esq / voltas, 'pulsos_por_volta_dir': pulsos_dir / voltas}
    if all(d is not None for d in diametros):
        if any(not math.isfinite(d) or d <= 0 for d in diametros):
            raise ValueError('Diametros devem ser positivos e finitos')
        dados.update(diametro_esq_mm=diametro_esq_mm, diametro_dir_mm=diametro_dir_mm,
                     mm_pulso_esq=math.pi * diametro_esq_mm * voltas / pulsos_esq,
                     mm_pulso_dir=math.pi * diametro_dir_mm * voltas / pulsos_dir)
    return dados


def nova_leitura(ard):
    inicio = time.monotonic()
    while time.monotonic() - inicio < 2.:
        s = ard.sensores()
        if s is not None and s.timestamp >= inicio:
            return s
        time.sleep(.02)
    raise RuntimeError('Sem nova leitura dos encoders')


def validar_roda(roda, de, dd):
    print(f'Teste da {roda}: canal E (D2) = {de:+d} pulsos; canal D (D3) = {dd:+d} pulsos.', flush=True)
    if min(de, dd) < 0:
        raise RuntimeError('Contadores regrediram; conferir reinicio/conexao e repetir o teste.')
    esperado, outro = (de, dd) if roda == 'esquerda' else (dd, de)
    if outro:
        oposta = 'direita' if roda == 'esquerda' else 'esquerda'
        causa = ('Somente o canal oposto respondeu. Confirme a roda fisica pela vista de tras; '
                 'se ela estiver correta, conferir correspondencia dos encoders D2/D3.' if esperado == 0 else
                 'Os dois canais responderam. Confira se a outra roda tambem girou, maus contatos ou ruido nos sinais/GND.')
        raise RuntimeError(f'A {oposta} contou pulsos no teste da {roda}. {causa}')
    if esperado == 0:
        raise RuntimeError(f'Nenhum pulso ao girar a {roda}. Conferir encoder, alimentacao e sinal.')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--porta', default=cfg.SERIAL_PORTA)
    metodo = ap.add_mutually_exclusive_group(required=True)
    metodo.add_argument('--distancia-mm', type=float, help='distancia marcada no chao')
    metodo.add_argument('--voltas', type=int, help='rodas suspensas: numero de voltas completas por roda')
    ap.add_argument('--diametro-esq-mm', type=float, help='opcional: diametro externo do pneu esquerdo')
    ap.add_argument('--diametro-dir-mm', type=float, help='opcional: diametro externo do pneu direito')
    ap.add_argument('--saida', type=Path)
    a = ap.parse_args()
    if a.distancia_mm is not None and (not math.isfinite(a.distancia_mm) or a.distancia_mm <= 0):
        ap.error('Distancia deve ser positiva e finita')
    if a.voltas is not None:
        try:
            calcular_por_voltas(a.voltas, 1, 1, a.diametro_esq_mm, a.diametro_dir_mm)
        except ValueError as erro:
            ap.error(str(erro))
    elif a.diametro_esq_mm is not None or a.diametro_dir_mm is not None:
        ap.error('Diametros sao usados somente com --voltas')
    if cfg.FIRMWARE_COM_CAMERA:
        ap.error('Exige firmware sem OV7670')
    if a.saida and a.saida.exists():
        ap.error('Escolha uma saida nova para preservar a medicao anterior')
    ard = ArduinoSerial(porta=a.porta)
    try:
        ard.conectar()
        ard.parar(repetir=3)
        local = 'rodas suspensas e marcadas para contar voltas' if a.voltas else 'carrinho no inicio da marca'
        input(f'Potencia dos motores DESLIGADA, {local}. Enter para iniciar: ')
        inicial = nova_leitura(ard)
        reconexoes = ard.estatisticas['reconexoes']
        if a.voltas:
            print('Esquerda/direita: vista de quem esta ATRAS do carrinho, olhando para a frente.', flush=True)
            input(f'Gire so a roda ESQUERDA {a.voltas} voltas completas no sentido de avanco. Pare e pressione Enter: ')
            meio = nova_leitura(ard)
            if ard.estatisticas['reconexoes'] != reconexoes:
                raise RuntimeError('Houve reconexao; repetir a medicao')
            validar_roda('esquerda', meio.ticks_esq - inicial.ticks_esq, meio.ticks_dir - inicial.ticks_dir)
            input(f'Gire so a roda DIREITA {a.voltas} voltas completas no sentido de avanco. Pare e pressione Enter: ')
            final = nova_leitura(ard)
            if ard.estatisticas['reconexoes'] != reconexoes:
                raise RuntimeError('Houve reconexao; repetir a medicao')
            validar_roda('direita', final.ticks_esq - meio.ticks_esq, final.ticks_dir - meio.ticks_dir)
        else:
            input(f'Empurre em linha reta {a.distancia_mm:g} mm, sem voltar nem levantar rodas. Pare e pressione Enter: ')
            final = nova_leitura(ard)
        if ard.estatisticas['reconexoes'] != reconexoes:
            raise RuntimeError('Houve reconexao; repetir a medicao')
        de, dd = final.ticks_esq - inicial.ticks_esq, final.ticks_dir - inicial.ticks_dir
        dados = (calcular_por_voltas(a.voltas, de, dd, a.diametro_esq_mm, a.diametro_dir_mm) if a.voltas else
                 calcular(a.distancia_mm, de, dd))
        print(json.dumps(dados, indent=2, ensure_ascii=False))
        if a.voltas:
            print('Rodas suspensas: sem diametros, somente pulsos/volta; com diametros, estimativa geometrica de mm/pulso.')
            print('Conferir depois por rolagem no piso com carga. Nao e calibracao final nem mede frenagem.')
        print('Repita para conferir consistencia. Isso nao mede frenagem nem autoriza movimento.')
        if a.saida:
            with a.saida.open('x', encoding='utf-8') as f:
                json.dump(dados, f, indent=2, ensure_ascii=False)
                f.write('\n')
    finally:
        try:
            ard.parar(repetir=3)
        finally:
            ard.fechar()


if __name__ == '__main__':
    main()
