"""CNN pequena escrita do zero em NumPy (sem PyTorch, sem pesos pré-treinados).

Entrada : imagem 1x40x80 (recorte + redução do quadro cinza 120x160 da câmera, ver dados.preparar_entrada).
Saídas  : [0] direção sugerida em [-1, 1] (tanh; negativo = esquerda)
          [1] "linha visível" (logit)
Camadas : conv 5x5/2 (8) -> ReLU -> conv 3x3/2 (16) -> ReLU -> conv 3x3/2 (16) -> ReLU -> flatten
          -> dense 64 -> ReLU -> dense 2.     ~55 mil parâmetros.

Por que NumPy: o Raspberry Pi 5 treina isto em segundos, não há dependência pesada, e o gradiente pode ser
conferido numericamente (tools/testes). Os pesos começam ALEATÓRIOS (He) e só aprendem com dados do carrinho.
"""
import hashlib
from pathlib import Path

import numpy as np

ENTRADA = (1, 40, 80)


def _janelas(xp: np.ndarray, k: int, passo: int, oh: int, ow: int) -> np.ndarray:
    """(N,C,Hp,Wp) -> (N,oh,ow,C,k,k)."""
    w = np.lib.stride_tricks.sliding_window_view(xp, (k, k), axis=(2, 3))
    w = w[:, :, ::passo, ::passo][:, :, :oh, :ow]
    return w.transpose(0, 2, 3, 1, 4, 5)


class _Conv:
    def __init__(self, c_in: int, c_out: int, k: int, passo: int, pad: int, rng, dtype):
        self.k, self.passo, self.pad, self.c_in, self.c_out = k, passo, pad, c_in, c_out
        fan_in = c_in * k * k
        self.w = (rng.standard_normal((fan_in, c_out)) * np.sqrt(2.0 / fan_in)).astype(dtype)
        self.b = np.zeros(c_out, dtype)

    def forward(self, x):
        n, c, h, w = x.shape
        k, p, s = self.k, self.pad, self.passo
        oh, ow = (h + 2 * p - k) // s + 1, (w + 2 * p - k) // s + 1
        xp = np.pad(x, ((0, 0), (0, 0), (p, p), (p, p)))
        cols = _janelas(xp, k, s, oh, ow).reshape(n * oh * ow, c * k * k)
        out = cols @ self.w + self.b
        self._cache = (cols, x.shape, xp.shape, oh, ow)
        return out.reshape(n, oh, ow, self.c_out).transpose(0, 3, 1, 2)

    def backward(self, dout):
        cols, xs, xps, oh, ow = self._cache
        n, c, h, w = xs
        k, p, s = self.k, self.pad, self.passo
        d2 = dout.transpose(0, 2, 3, 1).reshape(-1, self.c_out)
        self.dw = cols.T @ d2
        self.db = d2.sum(axis=0)
        dcols = (d2 @ self.w.T).reshape(n, oh, ow, c, k, k)
        dxp = np.zeros(xps, dout.dtype)
        for i in range(k):
            for j in range(k):
                dxp[:, :, i:i + s * oh:s, j:j + s * ow:s] += dcols[:, :, :, :, i, j].transpose(0, 3, 1, 2)
        return dxp[:, :, p:p + h, p:p + w]


class RedeLinha:
    def __init__(self, semente: int = 0, dtype=np.float32):
        rng = np.random.default_rng(semente)
        self.dtype = dtype
        self.c1 = _Conv(1, 8, 5, 2, 2, rng, dtype)
        self.c2 = _Conv(8, 16, 3, 2, 1, rng, dtype)
        self.c3 = _Conv(16, 16, 3, 2, 1, rng, dtype)
        self._flat = 16 * 5 * 10
        self.f1w = (rng.standard_normal((self._flat, 64)) * np.sqrt(2.0 / self._flat)).astype(dtype)
        self.f1b = np.zeros(64, dtype)
        self.f2w = (rng.standard_normal((64, 2)) * np.sqrt(1.0 / 64)).astype(dtype)
        self.f2b = np.zeros(2, dtype)

    # ----------------------------------------------------------- parâmetros
    def _lista(self):
        return [(self.c1, "w"), (self.c1, "b"), (self.c2, "w"), (self.c2, "b"), (self.c3, "w"), (self.c3, "b"),
                (self, "f1w"), (self, "f1b"), (self, "f2w"), (self, "f2b")]

    def parametros(self) -> list[np.ndarray]:
        return [getattr(o, n) for o, n in self._lista()]

    def gradientes(self) -> list[np.ndarray]:
        g = [self.c1.dw, self.c1.db, self.c2.dw, self.c2.db, self.c3.dw, self.c3.db,
             self._g["f1w"], self._g["f1b"], self._g["f2w"], self._g["f2b"]]
        return g

    def n_parametros(self) -> int:
        return int(sum(p.size for p in self.parametros()))

    # ----------------------------------------------------------- forward / backward
    def forward(self, x: np.ndarray):
        x = x.astype(self.dtype, copy=False)
        a1 = np.maximum(self.c1.forward(x), 0)
        self._m1 = a1 > 0
        a2 = np.maximum(self.c2.forward(a1), 0)
        self._m2 = a2 > 0
        a3 = np.maximum(self.c3.forward(a2), 0)
        self._m3 = a3 > 0
        self._shape3 = a3.shape
        flat = a3.reshape(len(x), -1)
        h = np.maximum(flat @ self.f1w + self.f1b, 0)
        self._flat_in, self._h = flat, h
        z = h @ self.f2w + self.f2b
        steer = np.tanh(z[:, 0])
        self._steer = steer
        return steer, z[:, 1]

    def _backward(self, dz0, dz1):
        dz = np.stack([dz0, dz1], axis=1).astype(self.dtype)
        self._g = {"f2w": self._h.T @ dz, "f2b": dz.sum(0)}
        dh = (dz @ self.f2w.T) * (self._h > 0)
        self._g["f1w"] = self._flat_in.T @ dh
        self._g["f1b"] = dh.sum(0)
        d3 = (dh @ self.f1w.T).reshape(self._shape3) * self._m3
        d2 = self.c3.backward(d3) * self._m2
        d1 = self.c2.backward(d2) * self._m1
        self.c1.backward(d1)

    def perda_e_gradiente(self, x, y_dir, mascara_dir, y_vis, peso, lambda_vis=0.5, delta=0.3):
        """Huber da direção (só onde a máscara vale) + BCE do 'linha visível', ponderados por `peso`.
        Calcula e guarda os gradientes. Devolve (perda, mae_direcao_mascarada)."""
        steer, zv = self.forward(x)
        w = peso.astype(self.dtype)
        wsum = float(w.sum()) + 1e-8
        r = steer - y_dir
        absr = np.abs(r)
        huber = np.where(absr <= delta, 0.5 * r * r, delta * (absr - 0.5 * delta))
        dhuber = np.where(absr <= delta, r, delta * np.sign(r))
        m = mascara_dir.astype(self.dtype)
        p = 1.0 / (1.0 + np.exp(-zv))
        eps = 1e-7
        bce = -(y_vis * np.log(p + eps) + (1 - y_vis) * np.log(1 - p + eps))
        perda = float((w * m * huber).sum() / wsum + lambda_vis * (w * bce).sum() / wsum)
        dz0 = (w * m * dhuber / wsum) * (1.0 - steer ** 2)
        dz1 = lambda_vis * w * (p - y_vis) / wsum
        self._backward(dz0, dz1)
        mae = float((m * absr).sum() / (m.sum() + 1e-8))
        return perda, mae

    # ----------------------------------------------------------- inferência
    def prever(self, x: np.ndarray, lote: int = 256):
        """x: (N,1,40,80). Devolve (direcao[N], prob_linha_visivel[N])."""
        saidas_d, saidas_v = [], []
        for i in range(0, len(x), lote):
            d, zv = self.forward(x[i:i + lote])
            saidas_d.append(d)
            saidas_v.append(1.0 / (1.0 + np.exp(-zv)))
        return np.concatenate(saidas_d), np.concatenate(saidas_v)

    # ----------------------------------------------------------- persistência
    def copiar(self) -> "RedeLinha":
        n = RedeLinha(0, self.dtype)
        n.carregar_parametros([p.copy() for p in self.parametros()])
        return n

    def carregar_parametros(self, lista):
        for (o, nome), v in zip(self._lista(), lista):
            setattr(o, nome, np.asarray(v, self.dtype).copy())

    def salvar(self, caminho) -> None:
        caminho = Path(caminho)
        tmp = caminho.with_suffix(".tmp.npz")
        np.savez(tmp, **{f"p{i}": p for i, p in enumerate(self.parametros())})
        tmp.replace(caminho)                              # troca atômica: nunca fica arquivo pela metade

    @classmethod
    def carregar(cls, caminho, dtype=np.float32) -> "RedeLinha":
        dados = np.load(caminho)
        r = cls(0, dtype)
        r.carregar_parametros([dados[f"p{i}"] for i in range(len(r.parametros()))])
        return r

    def hash(self) -> str:
        h = hashlib.sha256()
        for p in self.parametros():
            h.update(np.ascontiguousarray(p).tobytes())
        return h.hexdigest()[:16]


class Adam:
    def __init__(self, rede: RedeLinha, lr=1e-3, b1=0.9, b2=0.999, decaimento=1e-4):
        self.rede, self.lr, self.b1, self.b2, self.wd = rede, lr, b1, b2, decaimento
        self.m = [np.zeros_like(p) for p in rede.parametros()]
        self.v = [np.zeros_like(p) for p in rede.parametros()]
        self.t = 0

    def passo(self, lr: float | None = None) -> None:
        self.t += 1
        lr = self.lr if lr is None else lr
        params, grads = self.rede.parametros(), self.rede.gradientes()
        for i, (p, g) in enumerate(zip(params, grads)):
            if p.ndim > 1:
                g = g + self.wd * p                      # decaimento L2 só nos pesos
            self.m[i] = self.b1 * self.m[i] + (1 - self.b1) * g
            self.v[i] = self.b2 * self.v[i] + (1 - self.b2) * g * g
            mh = self.m[i] / (1 - self.b1 ** self.t)
            vh = self.v[i] / (1 - self.b2 ** self.t)
            p -= (lr * mh / (np.sqrt(vh) + 1e-8)).astype(p.dtype)
