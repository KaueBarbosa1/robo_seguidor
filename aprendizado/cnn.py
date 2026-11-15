"""CNN pequena escrita do zero em NumPy (sem PyTorch, sem pesos pré-treinados).

Entrada : imagem 1x40x80 (recorte + redução do quadro cinza 120x160 da câmera, ver dados.preparar_entrada).
Saídas  : [0] direção sugerida em [-1, 1] (tanh; negativo = esquerda)
          [1] "linha visível" (logit)
Camadas : conv 5x5/2 (8) -> ReLU -> conv 3x3/2 (16) -> ReLU -> conv 3x3/2 (16) -> ReLU -> flatten
          -> dense 64 -> ReLU -> dense 2.     ~55 mil parâmetros.
          A variante offline insere BatchNorm antes de cada ReLU convolucional.

Por que NumPy: o Raspberry Pi 5 treina isto em segundos, não há dependência pesada, e o gradiente pode ser
conferido numericamente (tools/testes). Os pesos começam ALEATÓRIOS (He) e só aprendem com dados do carrinho.

Plano pendente (docs/13_contexto_e_plano_cnn.md): manter inicialmente 80x40,
calibrar a ROI da ESP32-CAM e prever posições perto/meio/longe com validade
supervisionada. Isso exige alterar cabeça, gradientes, perdas, máscaras e
contrato de pesos; a interface abaixo continua sendo a de duas saídas.
No treino com fotos, a primeira saída é posição em y=75%, não ação de motor;
a visibilidade não é supervisionada (lambda_vis=0) e deve ser ignorada.
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


class _BatchNorm:
    eixos = (0, 2, 3)  # estatísticas por canal, sobre o lote e as posições espaciais
    epsilon = 1e-5
    momento = 0.1

    def __init__(self, canais, dtype):
        forma = (1, canais, 1, 1)
        self.escala = np.ones(forma, dtype=dtype)
        self.deslocamento = np.zeros(forma, dtype=dtype)
        self.media = np.zeros(forma, dtype=dtype)
        self.variancia = np.ones(forma, dtype=dtype)

    def forward(self, x, treino):
        if treino:
            media = x.mean(axis=self.eixos, keepdims=True)
            variancia = x.var(axis=self.eixos, keepdims=True)
            self.media += self.momento * (media - self.media)
            self.variancia += self.momento * (variancia - self.variancia)
        else:
            media, variancia = self.media, self.variancia
        inv_desvio = 1.0 / np.sqrt(variancia + self.epsilon)
        normalizado = (x - media) * inv_desvio
        if treino:
            self._cache = normalizado, inv_desvio
        return self.escala * normalizado + self.deslocamento

    def backward(self, gradiente):
        normalizado, inv_desvio = self._cache
        self.descala = (gradiente * normalizado).sum(axis=self.eixos, keepdims=True)
        self.ddeslocamento = gradiente.sum(axis=self.eixos, keepdims=True)
        n = gradiente.size // self.escala.size
        return self.escala * inv_desvio * (
            gradiente - (self.ddeslocamento + normalizado * self.descala) / n
        )


class RedeLinha:
    def __init__(self, semente: int = 0, dtype=np.float32, *, batchnorm: bool = False):
        rng = np.random.default_rng(semente)
        self.dtype = dtype
        self.c1 = _Conv(1, 8, 5, 2, 2, rng, dtype)
        self.c2 = _Conv(8, 16, 3, 2, 1, rng, dtype)
        self.c3 = _Conv(16, 16, 3, 2, 1, rng, dtype)
        self._convs = (self.c1, self.c2, self.c3)
        self._norms = tuple(_BatchNorm(c.c_out, dtype) for c in self._convs) if batchnorm else ()
        self._flat = 16 * 5 * 10
        self.f1w = (rng.standard_normal((self._flat, 64)) * np.sqrt(2.0 / self._flat)).astype(dtype)
        self.f1b = np.zeros(64, dtype)
        self.f2w = (rng.standard_normal((64, 2)) * np.sqrt(1.0 / 64)).astype(dtype)
        self.f2b = np.zeros(2, dtype)

    # ----------------------------------------------------------- parâmetros
    def _lista(self):
        convs = [(c, nome) for c in self._convs for nome in ("w", "b")]
        densas = [(self, nome) for nome in ("f1w", "f1b", "f2w", "f2b")]
        normas = [(bn, nome) for bn in self._norms for nome in ("escala", "deslocamento")]
        return convs + densas + normas

    def parametros(self) -> list[np.ndarray]:
        return [getattr(o, n) for o, n in self._lista()]

    def gradientes(self) -> list[np.ndarray]:
        return [self._g[nome] if camada is self else getattr(camada, "d" + nome)
                for camada, nome in self._lista()]

    def n_parametros(self) -> int:
        return int(sum(p.size for p in self.parametros()))

    # ----------------------------------------------------------- forward / backward
    def _ativacoes(self, x: np.ndarray, treino: bool):
        x = x.astype(self.dtype, copy=False)
        ativacoes = []
        for i, conv in enumerate(self._convs):
            x = conv.forward(x)
            if self._norms:
                x = self._norms[i].forward(x, treino)
            x = np.maximum(x, 0)
            ativacoes.append(x)
        return ativacoes

    def mapas_ativacao(self, x: np.ndarray):
        """Tensores N×C×H×W após cada ReLU, com estatísticas de inferência."""
        return self._ativacoes(x, treino=False)

    def forward(self, x: np.ndarray, *, treino: bool = False):
        ativacoes = self._ativacoes(x, treino)
        if treino:
            self._mascaras = [a > 0 for a in ativacoes]
        flat = ativacoes[-1].reshape(len(x), -1)
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
        gradiente = (dh @ self.f1w.T).reshape(self._mascaras[-1].shape)
        for i in reversed(range(len(self._convs))):
            gradiente *= self._mascaras[i]
            if self._norms:
                gradiente = self._norms[i].backward(gradiente)
            gradiente = self._convs[i].backward(gradiente)

    def perda_e_gradiente(self, x, y_dir, mascara_dir, y_vis, peso, lambda_vis=0.5, delta=0.3):
        """Huber da direção (só onde a máscara vale) + BCE do 'linha visível', ponderados por `peso`.
        Calcula e guarda os gradientes. Devolve (perda, mae_direcao_mascarada)."""
        steer, zv = self.forward(x, treino=True)
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
        n = RedeLinha(0, self.dtype, batchnorm=bool(self._norms))
        n.carregar_parametros(self.parametros())
        for origem, destino in zip(self._norms, n._norms):
            destino.media[:] = origem.media
            destino.variancia[:] = origem.variancia
        return n

    def carregar_parametros(self, lista):
        valores = [np.asarray(v, self.dtype) for v in lista]
        atuais = self.parametros()
        if len(valores) != len(atuais) or any(v.shape != p.shape for v, p in zip(valores, atuais)):
            raise ValueError("Parâmetros incompatíveis com a arquitetura da CNN")
        for destino, origem in zip(atuais, valores):
            destino[:] = origem

    def _estatisticas(self):
        return {f"bn{i}_{nome}": getattr(bn, nome) for i, bn in enumerate(self._norms, 1)
                for nome in ("media", "variancia")}

    def salvar(self, caminho) -> None:
        caminho = Path(caminho)
        tmp = caminho.with_suffix(".tmp.npz")
        dados = {f"p{i}": p for i, p in enumerate(self.parametros())}
        if self._norms:
            dados.update(arquitetura="rede_linha_batchnorm_v1", **self._estatisticas())
        np.savez(tmp, **dados)
        tmp.replace(caminho)                              # troca atômica: nunca fica arquivo pela metade

    @classmethod
    def carregar(cls, caminho, dtype=np.float32) -> "RedeLinha":
        with np.load(caminho, allow_pickle=False) as dados:
            batchnorm = "arquitetura" in dados
            if batchnorm and dados["arquitetura"].item() != "rede_linha_batchnorm_v1":
                raise ValueError("Arquitetura de checkpoint desconhecida")
            r = cls(0, dtype, batchnorm=batchnorm)
            chaves_parametros = [f"p{i}" for i in range(len(r.parametros()))]
            estatisticas = r._estatisticas()
            esperadas = set(chaves_parametros) | set(estatisticas)
            if batchnorm:
                esperadas.add("arquitetura")
            if set(dados.files) != esperadas:
                raise ValueError("Campos incompatíveis com a arquitetura do checkpoint")
            r.carregar_parametros([dados[chave] for chave in chaves_parametros])
            for nome, destino in estatisticas.items():
                valor = np.asarray(dados[nome], dtype=dtype)
                if (valor.shape != destino.shape or not np.isfinite(valor).all()
                        or (nome.endswith("variancia") and (valor < 0).any())):
                    raise ValueError(f"Estatística BatchNorm inválida: {nome}")
                destino[:] = valor
        return r

    def hash(self) -> str:
        h = hashlib.sha256()
        for p in [*self.parametros(), *self._estatisticas().values()]:
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
            if 1 < p.ndim < 4:                              # exclui escala e deslocamento da BatchNorm
                g = g + self.wd * p                      # decaimento L2 só nos pesos
            self.m[i] = self.b1 * self.m[i] + (1 - self.b1) * g
            self.v[i] = self.b2 * self.v[i] + (1 - self.b2) * g * g
            mh = self.m[i] / (1 - self.b1 ** self.t)
            vh = self.v[i] / (1 - self.b2 ** self.t)
            p -= (lr * mh / (np.sqrt(vh) + 1e-8)).astype(p.dtype)
