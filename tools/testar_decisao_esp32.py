"""Teste da ESP32 + visão + PD com ultrassom simulado; nunca abre serial física."""
import argparse
import csv
import json
import math
import sys
import threading
import time
from collections import deque
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg
from controle import ThreadControle
from estado import EstadoRobo, Modo
from motor.nulo import ArduinoNulo
from visao.detector import DetectorLinha, ThreadVisao, desenhar_debug
from visao.esp32_cam import CameraESP32
from visao.recorte_esp32 import RecorteESP32

JANELA = 'ESP32 - decisao SIMULADA - q sai'
CAMPOS = ('tempo_s', 'frame_id', 'novo_frame', 'camera', 'geracao', 'ultrassom_simulado',
          'linha_visivel', 'erro_horizontal', 'erro_controle', 'direcao', 'confianca',
          'estimada', 'decisao', 'motivo', 'esq_simulado', 'dir_simulado',
          'idade_frame_ms', 'idade_observacao_ms', 'http_ms', 'visao_ms', 'decisao_ms',
          'fps_captura', 'fps_visao')


class MotorTeste(ArduinoNulo):
    """Somente nesta ferramenta: leituras fictícias, guardas reais preservadas."""
    def __init__(self, ultrassom):
        super().__init__()
        self.ultrassom = ultrassom

    def sensores(self):
        distancia = {'livre': 100, 'obstaculo': 0, 'invalido': None}[self.ultrassom]
        return SimpleNamespace(timestamp=time.monotonic(), distancia_cm=distancia,
                               falha_sensor=distancia is None,
                               avanco_bloqueado=self.ultrassom == 'obstaculo')

    def obstaculo(self, *_):
        return self.ultrassom == 'obstaculo'


class Medidas:
    """Estatísticas numéricas limitadas; não armazena imagens."""
    def __init__(self):
        self.n = 0
        self.soma = 0.
        self.ultimas = deque(maxlen=600)

    def adicionar(self, valor):
        if valor is not None and math.isfinite(valor):
            self.n += 1
            self.soma += valor
            self.ultimas.append(valor)

    def resumo(self):
        return dict(amostras=self.n, media_ms=self.soma / self.n if self.n else None,
                    p95_ultimas_600_ms=float(np.percentile(self.ultimas, 95)) if self.n else None)


def nome_decisao(decisao):
    if decisao.esq == decisao.dir == 0:
        return 'PARAR'
    if decisao.esq > decisao.dir:
        return 'DIREITA'
    if decisao.esq < decisao.dir:
        return 'ESQUERDA'
    return 'RETO'


class SimuladorVisao:
    def __init__(self, fonte, ultrassom='livre'):
        self.fonte = fonte
        self.estado = EstadoRobo()
        self.estado.definir_modo(Modo.SEGUINDO)
        self.parar = threading.Event()
        self.motor = MotorTeste(ultrassom)  # não há opção de Arduino real
        self.controle = ThreadControle(self.estado, self.motor, self.parar, fonte)
        self.visao = ThreadVisao(self.estado, self.parar, fonte)
        self.detector = DetectorLinha(tracejado=True)
        self.orientacao = RecorteESP32(espelhar_h=cfg.IMAGEM_ESPELHAR_H,
                                      espelhar_v=cfg.IMAGEM_ESPELHAR_V)
        self.ultimo_id = fonte.id_atual()
        self.frame = self.resultado = self.meta = None
        self.processados = 0
        self.inicio = time.monotonic()
        self.medidas = {n: Medidas() for n in ('http', 'visao', 'decisao', 'idade_no_uso')}

    def atualizar(self):
        quadro = self.fonte.proximo_quadro_detalhado(self.ultimo_id, timeout=0.)
        novo, visao_ms = False, None
        if quadro is not None:
            self.ultimo_id, frame, meta = quadro
            if self.estado.modo is Modo.SEGUINDO:
                inicio = time.perf_counter()
                frame = self.orientacao.orientar(frame)
                r = self.visao._processar_detalhado(
                    self.detector, (self.ultimo_id, frame, meta), self.estado.sessao_visao)
                visao_ms = (time.perf_counter() - inicio) * 1000
                if r is not None:
                    self.frame, self.resultado, self.meta = frame, r, meta
                    self.processados += 1
                    novo = True
                    self.medidas['visao'].adicionar(visao_ms)
                    self.medidas['http'].adicionar(meta['http_ms'])
        if self.meta is not None and not self.visao._camera_valida(self.meta):
            self.frame = self.resultado = self.meta = None
        saude = self.fonte.saude()
        if saude['status'] != 'ok':
            self.detector.limpar_historico()
            self.estado.publicar_leitura(0., False, camera_ok=False,
                                         motivo='sem_quadros', sessao=self.estado.sessao_visao)
        inicio = time.perf_counter()
        with self.estado.lock:
            bloqueado = self.controle._inspecionar_obstaculo(time.monotonic()) or self.controle._obstaculo()
            decisao = self.controle.decidir_linha(time.monotonic(), bloqueado)
            leitura = self.estado.ler_leitura()
        decisao_ms = (time.perf_counter() - inicio) * 1000
        self.medidas['decisao'].adicionar(decisao_ms)
        agora = time.monotonic()
        idade = leitura.idade(agora) * 1000 if self.meta is not None else None
        self.medidas['idade_no_uso'].adicionar(idade)
        captura = self.fonte.estatisticas
        return dict(tempo_s=agora-self.inicio, frame_id=leitura.frame_id if self.meta is not None else None, novo_frame=novo,
                    camera=saude['status'], geracao=saude['geracao'],
                    ultrassom_simulado=self.motor.ultrassom,
                    linha_visivel=bool(self.meta is not None and leitura.linha_visivel),
                    erro_horizontal=leitura.erro if leitura.linha_visivel and self.meta is not None else None,
                    erro_controle=decisao.erro, direcao=leitura.direcao if self.meta is not None else 0.,
                    confianca=leitura.confianca if self.meta is not None else 0.,
                    estimada=decisao.estimada, decisao=nome_decisao(decisao), motivo=decisao.motivo,
                    esq_simulado=decisao.esq, dir_simulado=decisao.dir,
                    idade_frame_ms=idade,
                    idade_observacao_ms=decisao.idade_observacao_s*1000 if decisao.idade_observacao_s is not None else None,
                    http_ms=self.meta['http_ms'] if self.meta is not None else None,
                    visao_ms=visao_ms if novo else None, decisao_ms=decisao_ms,
                    fps_captura=captura['fps'], fps_visao=self.processados/max(agora-self.inicio, 1e-9))

    def tecla(self, tecla):
        if tecla == ord('q'):
            return False
        if tecla in (ord('1'), ord('2'), ord('3')):
            self.motor.ultrassom = {ord('1'): 'livre', ord('2'): 'obstaculo', ord('3'): 'invalido'}[tecla]
        if tecla in (ord('p'), ord(' ')):
            self.estado.definir_modo(Modo.PARADO if self.estado.modo is Modo.SEGUINDO else Modo.SEGUINDO)
            self.detector.limpar_historico()
            self.ultimo_id = self.fonte.id_atual()
            self.frame = self.resultado = self.meta = None
        return True

    def resumo(self):
        tempo = time.monotonic()-self.inicio
        captura = self.fonte.estatisticas
        return dict(motores='NULOS', ultrassom='SIMULADO', tempo_s=tempo,
                    frames_processados=self.processados, fps_visao=self.processados/max(tempo, 1e-9),
                    captura=captura, medidas={n: m.resumo() for n, m in self.medidas.items()})

    def encerrar(self):
        self.parar.set()
        self.estado.encerrar()
        try:
            self.motor.parar(repetir=3)
        finally:
            self.fonte.parar()


def formatar(valor, casas=1):
    return '--' if valor is None else f'{valor:.{casas}f}'


def montar_painel(simulador, dados):
    painel = np.zeros((390, 750, 3), np.uint8)
    cv2.putText(painel, 'SIMULACAO - NENHUM MOTOR REAL - ULTRASSOM FICTICIO',
                (10, 22), cv2.FONT_HERSHEY_SIMPLEX, .49, (0, 220, 255), 1)
    if simulador.frame is not None and simulador.resultado is not None:
        imagem = desenhar_debug(simulador.frame, simulador.resultado)
        if dados['estimada']:
            h, w = imagem.shape[:2]
            x = int(np.clip((1+dados['erro_controle'])*w/2, 0, w-1))
            cv2.line(imagem, (x, simulador.resultado.y0), (x, h-1), (255, 0, 255), 2)
            cv2.putText(imagem, 'ESTIMADA', (5, 50), cv2.FONT_HERSHEY_SIMPLEX, .45, (255, 0, 255), 1)
        painel[38:278, 10:330] = imagem
    else:
        cv2.putText(painel, 'SEM FRAME ATUAL', (35, 150), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 0, 255), 1)
    linhas = [
        'Decisao simulada: '+dados['decisao'],
        'Motivo: '+dados['motivo'],
        'Camera: '+dados['camera']+' | geracao='+str(dados['geracao']),
        'ULTRASSOM SIMULADO: '+dados['ultrassom_simulado'],
        f"Saidas E/D (sim): {dados['esq_simulado']}/{dados['dir_simulado']}",
        'Erro horizontal: '+formatar(dados['erro_horizontal'], 3),
        'Erro controle: '+formatar(dados['erro_controle'], 3),
        'Direcao: '+formatar(dados['direcao'], 3)+' | qualidade: '+formatar(dados['confianca'], 2),
        'Idade frame <= '+formatar(dados['idade_frame_ms'])+' ms',
        'Ultima observacao <= '+formatar(dados['idade_observacao_ms'])+' ms',
        'HTTP: '+formatar(dados['http_ms'])+' ms',
        'Visao/decisao: '+formatar(dados['visao_ms'])+'/'+formatar(dados['decisao_ms'])+' ms',
        'FPS captura/visao: '+formatar(dados['fps_captura'])+'/'+formatar(dados['fps_visao']),
    ]
    for i, linha in enumerate(linhas):
        cv2.putText(painel, linha, (345, 50+i*22), cv2.FONT_HERSHEY_SIMPLEX, .42, (220, 220, 220), 1)
    for i, linha in enumerate(('Verde: tracos | amarelo: trajetoria',
                               'Magenta: estimativa limitada no vao',
                               '1 livre | 2 obstaculo | 3 invalido', 'p/espaco: pausar | q: sair')):
        cv2.putText(painel, linha, (10, 302+i*22), cv2.FONT_HERSHEY_SIMPLEX, .42, (200, 200, 200), 1)
    return painel


def argumentos(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default=cfg.ESP32_URL)
    parser.add_argument('--timeout', type=float, default=cfg.ESP32_TIMEOUT_S)
    parser.add_argument('--ultrassom', choices=('livre', 'obstaculo', 'invalido'), default='livre',
                        help='cenário fictício; não lê o Arduino')
    parser.add_argument('--sem-janela', action='store_true')
    parser.add_argument('--duracao', type=float, help='limite em segundos; Ctrl+C também encerra')
    parser.add_argument('--csv', type=Path, help='arquivo novo; recusa sobrescrever')
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error('timeout deve ser positivo e finito')
    if args.duracao is not None and (not math.isfinite(args.duracao) or args.duracao <= 0):
        parser.error('duracao deve ser positiva e finita')
    return args


def executar(args, fonte=None):
    fonte = fonte if fonte is not None else CameraESP32(
        args.url, args.timeout, cfg.ESP32_IDADE_MAX_S, cfg.ESP32_RECONEXAO_S)
    simulador = SimuladorVisao(fonte, args.ultrassom)
    print('SIMULACAO: motor nulo, sem serial, voz ou Bluetooth; ultrassom SIMULADO='+args.ultrassom, flush=True)
    resumo = None
    with ExitStack() as recursos:
        recursos.callback(simulador.encerrar)
        escritor = None
        if args.csv is not None:
            arquivo = recursos.enter_context(args.csv.open('x', newline='', encoding='utf-8', buffering=1))
            escritor = csv.DictWriter(arquivo, fieldnames=CAMPOS)
            escritor.writeheader()
        if not args.sem_janela:
            cv2.namedWindow(JANELA, cv2.WINDOW_NORMAL)
            recursos.callback(cv2.destroyAllWindows)
        fonte.iniciar()
        proximo_log = simulador.inicio
        try:
            while args.duracao is None or time.monotonic()-simulador.inicio < args.duracao:
                inicio = time.monotonic()
                dados = simulador.atualizar()
                if escritor is not None:
                    escritor.writerow(dados)
                if not args.sem_janela:
                    cv2.imshow(JANELA, montar_painel(simulador, dados))
                    if not simulador.tecla(cv2.waitKey(1) & 0xFF) or cv2.getWindowProperty(JANELA, cv2.WND_PROP_VISIBLE) < 1:
                        break
                if time.monotonic() >= proximo_log:
                    print(f"{dados['decisao']} ({dados['motivo']}) camera={dados['camera']} "
                          f"FPS captura/visao={dados['fps_captura']:.2f}/{dados['fps_visao']:.2f} "
                          f"idade<={formatar(dados['idade_frame_ms'])} ms", flush=True)
                    proximo_log = time.monotonic()+1
                simulador.parar.wait(max(0., 1/cfg.FREQ_CONTROLE_HZ-(time.monotonic()-inicio)))
        except KeyboardInterrupt:
            pass
        resumo = simulador.resumo()
    return resumo


def main():
    args = argumentos()
    try:
        resumo = executar(args)
    except (OSError, ValueError, cv2.error) as erro:
        print(f'Erro no teste: {erro}', file=sys.stderr)
        return 1
    print(json.dumps(resumo, ensure_ascii=False, sort_keys=True))
    return 0 if resumo['frames_processados'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
