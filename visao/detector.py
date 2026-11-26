"""Módulo de visão: acha a linha no frame e mede o erro de direção.

Esta thread NÃO fala com o Arduino. Ela só publica no EstadoRobo o erro medido;
quem converte erro em comando e escreve na serial é o controle (controle.py).
Assim existe um único ponto de decisão e a hierarquia "voz > visão" fica garantida.

ESP32 usa snapshots com idade e geração de conexão; o OpenCV tracejado publica
posição/direção/qualidade para o PD e sua memória limitada em controle.py.
A integração de pesos CNN compatíveis e o planejamento de desvio permanecem
pendentes; ver docs/13_contexto_e_plano_cnn.md.
"""
import logging
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np

import config as cfg
from estado import EstadoRobo, Modo
from monitoramento import medir

log = logging.getLogger("visao")


@dataclass
class ResultadoLinha:
    achou: bool
    erro: float = 0.0                 # normalizado -1..+1 (positivo = linha à direita)
    cx: float = 0.0
    cy: float = 0.0                   # em coordenadas do frame inteiro
    binaria: np.ndarray | None = None
    contorno: np.ndarray | None = None
    y0: int = 0
    segmentos: tuple[tuple[float, float, float, float], ...] = ()             # extremos (x1,y1,x2,y2) no frame inteiro
    trajetoria: tuple[tuple[float, float], ...] = ()            # pontos (x,y) medidos/associados, sem frames
    direcao: float = 0.0              # dx/dy para frente (alto da imagem); + = direita
    confianca: float = 0.0            # qualidade geométrica heurística, não probabilidade
    motivo: str = "legado"


class DetectorLinha:
    def __init__(self, tracejado: bool = False):
        # Opt-in até a integração de segurança da Etapa 3. Caminho legado intacto.
        self._tracejado = tracejado
        self.limpar_historico()
        k = cfg.BLUR_KERNEL | 1       # garante ímpar
        self._k = (k, k)
        self._kernel = np.ones((3, 3), np.uint8)
        self._tipo = cv2.THRESH_BINARY_INV if cfg.LINHA_ESCURA else cv2.THRESH_BINARY

    @medir('opencv_s')
    def processar(self, frame: np.ndarray) -> ResultadoLinha:
        h, w = frame.shape[:2]
        y0 = int(h * cfg.ROI_INICIO)
        roi = frame[y0:, :]

        cinza = roi if roi.ndim == 2 else cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        suave = cinza if self._k == (1, 1) else cv2.GaussianBlur(cinza, self._k, 0)
        if self._tracejado:
            agora = time.monotonic()
            if (self._forma != frame.shape or agora < self._referencia_t or
                    agora - self._referencia_t > cfg.TRACEJADO_MEMORIA_S):
                self.limpar_historico()
            self._forma = frame.shape
        if int(suave.max()) - int(suave.min()) < cfg.CONTRASTE_MIN:   # piso liso: não há linha
            return ResultadoLinha(False, binaria=np.zeros_like(suave), y0=y0,
                                  motivo="contraste_insuficiente" if self._tracejado else "legado")
        if cfg.USAR_OTSU:
            _, binaria = cv2.threshold(suave, 0, 255, self._tipo + cv2.THRESH_OTSU)
        else:
            _, binaria = cv2.threshold(suave, cfg.LIMIAR_FIXO, 255, self._tipo)
        binaria = cv2.morphologyEx(binaria, cv2.MORPH_OPEN, self._kernel)   # tira ruído fino

        if self._tracejado:
            return self._processar_segmentos(suave, binaria, y0, agora)

        contornos, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contornos:
            return ResultadoLinha(False, binaria=binaria, y0=y0)

        maior = max(contornos, key=cv2.contourArea)
        if cv2.contourArea(maior) < cfg.AREA_MIN:
            return ResultadoLinha(False, binaria=binaria, y0=y0)

        m = cv2.moments(maior)
        if m["m00"] == 0:
            return ResultadoLinha(False, binaria=binaria, y0=y0)

        # a mancha precisa ser de fato diferente do piso: sem isto, ruído + vinheta da lente viram "linha" falsa
        mascara = np.zeros(suave.shape, np.uint8)
        cv2.drawContours(mascara, [maior], -1, 255, -1)
        dentro, fora = suave[mascara > 0], suave[mascara == 0]
        if fora.size and abs(float(fora.mean()) - float(dentro.mean())) < cfg.CONTRASTE_MIN:
            return ResultadoLinha(False, binaria=binaria, y0=y0)

        cx = m["m10"] / m["m00"]
        cy = m["m01"] / m["m00"] + y0
        centro = w / 2.0
        erro = (cx - centro) / centro
        return ResultadoLinha(True, erro, cx, cy, binaria, maior, y0)


    def limpar_historico(self):
        """Descarta só referência geométrica: nunca guarda frames/máscaras."""
        self._referencia = None
        self._referencia_t = 0.0
        self._forma = None

    def _processar_segmentos(self, cinza, binaria, y0, agora):
        from visao.sugestao import _segmentos, _trajetoria

        h, w = binaria.shape
        def ausente(motivo):
            return ResultadoLinha(False, binaria=binaria, y0=y0, motivo=motivo)

        # Mesmo limiar/ROI do detector original; contraste com sinal de polaridade.
        primeiro = binaria != 0
        if not primeiro.any() or primeiro.all():
            return ausente("sem_contraste_com_piso")
        contraste = float(cinza[~primeiro].mean()) - float(cinza[primeiro].mean())
        if not cfg.LINHA_ESCURA:
            contraste = -contraste
        if contraste < cfg.CONTRASTE_MIN:
            return ausente("contraste_insuficiente")
        candidatos = _segmentos(binaria, area_min=cfg.AREA_MIN,
                                fracao_area_max=.35, fracao_altura_max=1.,
                                alongamento_max=10000,
                                max_candidatos=cfg.TRACEJADO_MAX_SEGMENTOS)
        if not candidatos:
            return ausente("sem_segmentos_compativeis_ou_excesso")
        caminho, score = _trajetoria(candidatos, h, w, self._referencia)
        if not caminho:
            return ausente("sem_trajetoria")
        # Uma alternativa independente de qualidade próxima é ambígua.
        usados = {id(s) for s in caminho}
        outro, nota = _trajetoria([s for s in candidatos if id(s) not in usados],
                                  h, w, self._referencia)
        if outro and nota >= cfg.TRACEJADO_AMBIGUIDADE * score:
            separacao = abs(np.mean([s['x'] for s in outro]) -
                            np.mean([s['x'] for s in caminho]))
            if separacao > max(4., w * .02):
                return ausente("trajetorias_ambiguas")
        pontos = np.array([caminho[0]['extremos'][0]] +
                          [[s['x'], s['y']] for s in caminho] +
                          [caminho[-1]['extremos'][1]], dtype=float)
        pontos = pontos[np.argsort(pontos[:, 1])]
        extensao = pontos[-1, 1] - pontos[0, 1]
        if extensao <= 0:
            return ausente("extensao_insuficiente")
        # Referência no meio da ROI, limitada à extensão realmente sustentada.
        y = float(np.clip(h / 2., pontos[0, 1], pontos[-1, 1]))
        x = float(np.interp(y, pontos[:, 1], pontos[:, 0]))
        direcao = float((pontos[0, 0] - pontos[-1, 0]) / extensao)
        confianca = float(min(1., contraste / max(2 * cfg.CONTRASTE_MIN, 1)) *
                          min(1., extensao / max(.5 * h, 1)) *
                          min(1., sum(s['area'] for s in caminho) / max(3 * cfg.AREA_MIN, 1)))
        if confianca < cfg.TRACEJADO_CONFIANCA_MIN:
            return ausente("suporte_insuficiente")
        # Memória fixa: só dois pontos da última observação válida. Não renova
        # na ausência e nunca converte referência histórica em detecção nova.
        self._referencia = pontos[[0, -1]].copy()
        self._referencia_t = agora
        extremos = tuple((float(a[0]), float(a[1] + y0),
                          float(b[0]), float(b[1] + y0))
                         for s in caminho for a, b in [s['extremos']])
        trajetoria = tuple((float(px), float(py + y0)) for px, py in pontos)
        return ResultadoLinha(True, (x - w / 2.) / (w / 2.), x, y + y0,
                              binaria=binaria, y0=y0, segmentos=extremos,
                              trajetoria=trajetoria, direcao=direcao,
                              confianca=confianca, motivo="observada")


def desenhar_debug(frame: np.ndarray, r: ResultadoLinha) -> np.ndarray:
    saida = frame.copy() if frame.ndim == 3 else cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    h, w = saida.shape[:2]
    cv2.line(saida, (w // 2, 0), (w // 2, h), (255, 0, 0), 1)           # centro da tela
    cv2.line(saida, (0, r.y0), (w, r.y0), (0, 255, 255), 1)             # início da ROI
    if r.achou:
        if r.contorno is not None:
            cv2.drawContours(saida[r.y0:, :], [r.contorno], -1, (0, 255, 0), 2)
        for x1, y1, x2, y2 in r.segmentos:
            cv2.line(saida, (round(x1), round(y1)), (round(x2), round(y2)), (0, 255, 0), 3)
        if r.trajetoria:
            cv2.polylines(saida, [np.rint(r.trajetoria).astype(np.int32)], False, (0, 180, 255), 1)
        cv2.circle(saida, (int(r.cx), int(r.cy)), 5, (0, 0, 255), -1)
        cv2.putText(saida, f"erro={r.erro:+.2f}", (5, 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    if r.motivo != "legado":
        texto = f"{r.motivo} conf={r.confianca:.2f} dir={r.direcao:+.2f}"
        cv2.putText(saida, texto, (5, h - 8), cv2.FONT_HERSHEY_SIMPLEX, .34, (0, 0, 255), 1)
    return saida


class ThreadVisao(threading.Thread):
    """Fontes legadas ou ESP32 com metadados; processa apenas em SEGUINDO."""

    def __init__(self, estado: EstadoRobo, parar: threading.Event, fonte):
        super().__init__(name="visao", daemon=True)
        self._estado = estado
        self._parar = parar
        self._fonte = fonte
        self._detalhada = callable(getattr(fonte, 'proximo_quadro_detalhado', None))
        self._geracao_processada = None

    def run(self) -> None:
        try:
            self._loop()
        except Exception:
            log.exception("Thread de visão caiu")
            self._estado.publicar_leitura(0.0, False, camera_ok=False, motivo="excecao_visao")
            self._parar.set()                      # main para o robô todo

    def _camera_valida(self, meta):
        camera = self._fonte.saude()
        agora = time.monotonic()
        recebida = meta['recepcao_monotonica']
        idade = meta['idade_captura_s']
        limite = min(cfg.LEITURA_VALIDADE_S, self._fonte.idade_max_s)
        return (camera['status'] == 'ok' and camera['geracao'] == meta['geracao_camera']
                and np.isfinite(recebida) and np.isfinite(idade) and idade >= 0
                and agora >= recebida and agora - recebida + idade <= limite)

    def _processar_detalhado(self, detector, quadro, sessao):
        quadro_id, frame, meta = quadro
        if not self._camera_valida(meta):
            detector.limpar_historico()
            self._estado.publicar_leitura(0.0, False, camera_ok=False,
                                         motivo="camera_indisponivel", sessao=sessao)
            return None
        if self._geracao_processada != meta['geracao_camera']:
            detector.limpar_historico()
            self._geracao_processada = meta['geracao_camera']
        resultado = detector.processar(frame)
        # A captura pode falhar/recuperar ou envelhecer durante o processamento.
        if not self._camera_valida(meta):
            detector.limpar_historico()
            self._estado.publicar_leitura(0.0, False, camera_ok=False,
                                         motivo="camera_indisponivel", sessao=sessao)
            return None
        publicada = self._estado.publicar_leitura(
            resultado.erro, resultado.achou, sessao=sessao,
            timestamp=meta['recepcao_monotonica'], idade_captura_s=meta['idade_captura_s'],
            frame_id=quadro_id, geracao_camera=meta['geracao_camera'], camera_ok=True,
            direcao=resultado.direcao, escala_direcao=(frame.shape[0] - resultado.y0) / (frame.shape[1] / 2.),
            confianca=resultado.confianca, motivo=resultado.motivo)
        if not publicada:
            detector.limpar_historico()
            return None
        return resultado

    def _loop(self) -> None:
        detector = DetectorLinha(tracejado=self._detalhada)
        ultimo_id = self._fonte.id_atual()
        sessao_anterior = None
        sem_quadro = 0
        while not self._parar.is_set():
            autoridade=getattr(self._estado,'_autoridade_rede',None)
            if autoridade is not None and autoridade.processamento=='distribuido':
                detector.limpar_historico();sessao_anterior=None
                self._parar.wait(.02)
                continue
            with self._estado.lock:
                modo, sessao = self._estado.modo, self._estado.sessao_visao
            if modo is not Modo.SEGUINDO:
                sessao_anterior = None
                detector.limpar_historico()
                self._parar.wait(.05)
                continue
            if sessao != sessao_anterior:
                ultimo_id = self._fonte.id_atual() + (0 if self._detalhada else 1)
                detector.limpar_historico()
                sessao_anterior = sessao
            if self._detalhada:
                q = self._fonte.proximo_quadro_detalhado(ultimo_id, timeout=.1)
            else:
                q = self._fonte.proximo_quadro(ultimo_id, timeout=.5)
            if q is None:
                # Esperar o próximo id não é um vão. Não renova a leitura anterior.
                saudavel = self._detalhada and self._fonte.saude()['status'] == 'ok'
                if not saudavel:
                    sem_quadro += 1
                    detector.limpar_historico()
                    if sem_quadro == 1 or sem_quadro % 10 == 0:
                        log.warning("Sem quadros da câmera (status=%s)", getattr(self._fonte, 'status', None))
                    self._estado.publicar_leitura(0.0, False, camera_ok=False,
                                                 motivo="sem_quadros", sessao=sessao)
                continue
            sem_quadro = 0
            ultimo_id, frame = q[:2]
            if self._detalhada:
                if cfg.IMAGEM_ESPELHAR_H or cfg.IMAGEM_ESPELHAR_V:
                    eixo = -1 if cfg.IMAGEM_ESPELHAR_H and cfg.IMAGEM_ESPELHAR_V else 1 if cfg.IMAGEM_ESPELHAR_H else 0
                    frame = cv2.flip(frame, eixo)
                    q = (ultimo_id, frame, q[2])
                r = self._processar_detalhado(detector, q, sessao)
            else:
                r = detector.processar(frame)
                if not self._estado.publicar_leitura(r.erro, r.achou, sessao=sessao):
                    r = None
            if cfg.MOSTRAR_DEBUG and r is not None:
                cv2.imshow("visao", cv2.resize(desenhar_debug(frame, r), None, fx=3, fy=3,
                                               interpolation=cv2.INTER_NEAREST))
                cv2.waitKey(1)
