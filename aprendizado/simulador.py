"""SIMULADOR SINTÉTICO de pista pontilhada. NÃO É A PISTA REAL.

Serve somente para exercitar e testar o código do aprendizado (gravar -> reparar rótulos -> treinar -> dirigir
com portão -> supervisor -> A/B -> rollback) antes de a pista física existir. Os números produzidos aqui
NÃO dizem nada sobre o desempenho no carrinho real: a geometria, a velocidade, a iluminação e o ruído são
suposições minhas, reproduzindo só as LIMITAÇÕES conhecidas da OV7670 (160x120, 4 bits, ~2,5 quadros/s,
distorção por captura progressiva de 0,4 s, quadros perdidos, atraso comando->efeito).
"""
import cv2
import numpy as np

H, W = 120, 160
PX_POR_M = 160 / 0.24                 # vista de cima: 24 cm de largura
ALCANCE_FRENTE_M = H / PX_POR_M       # 18 cm à frente
DESLOC_CAMERA_M = 0.04                # a vista começa 4 cm à frente do eixo


class PistaSintetica:
    """Curva fechada sinuosa, pontilhada. Aleatória por semente (cada semente = uma 'pista' diferente)."""

    def __init__(self, semente: int = 0, raio_m: float = 0.9, traco_m: float = 0.04, vao_m: float = 0.06,
                 largura_linha_m: float = 0.02):
        rng = np.random.default_rng(semente)
        phi = np.linspace(0, 2 * np.pi, 6000, endpoint=False)
        for _ in range(50):                               # garante curvas suaves o bastante p/ o carrinho
            a1, a2 = rng.uniform(0.12, 0.25), rng.uniform(0.04, 0.10)
            p1, p2 = rng.uniform(0, 2 * np.pi, 2)
            r = raio_m * (1 + a1 * np.sin(3 * phi + p1) + a2 * np.sin(5 * phi + p2))
            x, y = r * np.cos(phi), r * np.sin(phi)
            curv = self._raio_curvatura_min(x, y)
            if curv > 0.30:
                break
        self.pontos = np.stack([x, y], 1)
        seg = np.linalg.norm(np.diff(np.vstack([self.pontos, self.pontos[:1]]), axis=0), axis=1)
        self.s = np.concatenate([[0], np.cumsum(seg)])[:-1]
        self.comprimento = float(seg.sum())
        self.raio_min = curv
        self.largura_linha_m = largura_linha_m
        ciclo = traco_m + vao_m
        self.traco = (self.s % ciclo) < traco_m           # True onde há tinta
        self.vao_m = vao_m

    @staticmethod
    def _raio_curvatura_min(x, y) -> float:
        dx, dy = np.gradient(x), np.gradient(y)
        ddx, ddy = np.gradient(dx), np.gradient(dy)
        k = np.abs(dx * ddy - dy * ddx) / np.maximum((dx ** 2 + dy ** 2) ** 1.5, 1e-12)
        return float(1.0 / max(k.max(), 1e-9))

    def distancia_ao_tracado(self, x: float, y: float) -> float:
        return float(np.min(np.hypot(self.pontos[:, 0] - x, self.pontos[:, 1] - y)))

    def pose_inicial(self, rng: np.random.Generator):
        i = int(rng.integers(len(self.pontos)))
        p, q = self.pontos[i], self.pontos[(i + 8) % len(self.pontos)]
        h = float(np.arctan2(q[1] - p[1], q[0] - p[0]))
        h += rng.uniform(-0.12, 0.12)                     # o operador não coloca perfeitamente
        lat = rng.uniform(-0.02, 0.02)
        return p[0] - np.sin(h) * lat, p[1] + np.cos(h) * lat, h


class AmbienteSimulado:
    """Implementa a interface esperada por executar_tentativa()."""
    DT_QUADRO = 0.4                   # captura progressiva da OV7670 em QQVGA 2,5 fps
    FAIXAS = 6                        # distorção "rolling": a imagem é montada de 6 faixas em instantes distintos
    V_MAX = 0.11                      # m/s com vel_fator = 1 (suposição)
    OMEGA_MAX = 1.6                   # rad/s com |steer| = 1 (suposição)
    TAU = 0.3                         # atraso de 1ª ordem dos motores (s)
    TICK_M = 0.01                     # 1 pulso de encoder a cada 1 cm (suposição)

    def __init__(self, pista: PistaSintetica, rng: np.random.Generator, p_perde_quadro: float = 0.03,
                 ruido: float = 7.0, com_sensor_pista: bool = False, max_fora_m: float = 0.12):
        self.pista, self.rng = pista, rng
        self.p_perde, self.ruido = p_perde_quadro, ruido
        self.com_sensor_pista = com_sensor_pista
        self.max_fora_m = max_fora_m
        self.fora_verdade = False     # só para AVALIAR o simulador; nunca entra no aprendizado
        self.iniciar()

    # -- ciclo de vida
    def iniciar(self) -> None:
        self.x, self.y, self.h = self.pista.pose_inicial(self.rng)
        self.v = self.w = 0.0
        self.cmd_steer, self.cmd_vel = 0.0, 0.0
        self.t = 0.0
        self.ganho = float(self.rng.uniform(0.75, 1.15))          # brilho da "sessão"
        self._ultimo = None
        self._ticks_acum = 0.0
        self.fora_verdade = False
        self.dist_percorrida = 0.0

    def parar(self) -> None:
        self.cmd_steer = self.cmd_vel = 0.0

    def aplicar(self, steer: float, vel_fator: float) -> None:
        self.cmd_steer, self.cmd_vel = float(steer), float(vel_fator)

    # -- física
    def _avancar(self, dt: float) -> None:
        n = max(1, int(round(dt / 0.02)))
        h_ = dt / n
        for _ in range(n):
            v_alvo = self.V_MAX * self.cmd_vel
            w_alvo = -self.OMEGA_MAX * self.cmd_steer             # steer>0 = linha à direita = girar p/ direita
            a = h_ / self.TAU
            self.v += a * (v_alvo - self.v)
            self.w += a * (w_alvo - self.w)
            self.h += self.w * h_
            self.x += self.v * np.cos(self.h) * h_
            self.y += self.v * np.sin(self.h) * h_
            self._ticks_acum += self.v * h_ / self.TICK_M
            self.dist_percorrida += self.v * h_
        self.t += dt
        if self.pista.distancia_ao_tracado(self.x, self.y) > self.max_fora_m:
            self.fora_verdade = True

    # -- imagem
    def _renderizar(self) -> np.ndarray:
        """Vista de cima na pose atual (papel claro, tinta escura)."""
        img = np.full((H, W), 205, np.float32)
        c, s = np.cos(self.h), np.sin(self.h)
        frente = np.array([c, s])
        direita = np.array([s, -c])
        origem = np.array([self.x, self.y]) + frente * DESLOC_CAMERA_M
        rel = self.pista.pontos - origem
        lat = rel @ direita
        fre = rel @ frente
        vis = (np.abs(lat) < 0.16) & (fre > -0.03) & (fre < ALCANCE_FRENTE_M + 0.03)
        idx = np.nonzero(vis & self.pista.traco)[0]
        if len(idx):
            u = (W / 2 + lat[idx] * PX_POR_M).astype(np.float32)
            v = (H - 1 - fre[idx] * PX_POR_M).astype(np.float32)
            esp = max(1, int(round(self.pista.largura_linha_m * PX_POR_M)))
            # une pontos consecutivos do mesmo traço com segmentos; pontos isolados viram círculos
            pts = np.stack([u, v], 1)
            quebra = np.nonzero(np.diff(idx) > 1)[0] + 1
            for grupo in np.split(np.arange(len(idx)), quebra):
                g = pts[grupo].astype(np.int32).reshape(-1, 1, 2)
                if len(g) >= 2:
                    cv2.polylines(img, [g], False, 45.0, esp, cv2.LINE_AA)
                else:
                    cv2.circle(img, tuple(int(a) for a in g[0, 0]), esp // 2, 45.0, -1)
        yy = np.linspace(-1, 1, H)[:, None]
        xx = np.linspace(-1, 1, W)[None, :]
        img *= 1.0 - 0.12 * (xx ** 2 + yy ** 2)                    # vinheta
        return img

    def quadro(self):
        """Captura progressiva: cada faixa vem de um instante diferente, com o robô andando."""
        if self._ultimo is not None and self.rng.random() < self.p_perde:
            self._avancar(self.DT_QUADRO)                          # quadro descartado: o robô seguiu andando
            return self._ultimo[0], self._ultimo[1] + self.DT_QUADRO, self.t
        composto = np.empty((H, W), np.float32)
        altura_faixa = H // self.FAIXAS
        for k in range(self.FAIXAS):
            base = self._renderizar()
            # a faixa de cima é lida primeiro (linha 0 = longe)
            composto[k * altura_faixa:(k + 1) * altura_faixa] = base[k * altura_faixa:(k + 1) * altura_faixa]
            self._avancar(self.DT_QUADRO / self.FAIXAS)
        composto = composto * self.ganho + self.rng.normal(0, self.ruido, composto.shape)
        nivel = np.clip(np.round(composto / 17.0), 0, 14).astype(np.uint8)   # 4 bits, teto em 14
        img = (nivel * 17).astype(np.uint8)
        self._ultimo = (img, 0.0)
        return img, 0.0, self.t

    # -- sensores
    def ticks_delta(self):
        n = int(self._ticks_acum)
        self._ticks_acum -= n
        return n

    def obstaculo(self) -> bool:
        return False

    def sobre_pista(self):
        if not self.com_sensor_pista:
            return None
        return not self.fora_verdade
