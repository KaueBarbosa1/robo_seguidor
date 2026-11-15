"""Dados do aprendizado: pré-processamento, gravação de episódios, reparo de rótulos e buffer de treino.

Um EPISÓDIO é uma tentativa do carrinho na pista. Pasta:
    frames.u8      quadros 120x160 (uint8) um atrás do outro (gravação incremental: sobrevive a queda de energia)
    passos.jsonl   uma linha por quadro: ação tomada, leitura do professor, previsão da CNN, encoders...
    meta.json      resultado da tentativa (só existe se a tentativa foi encerrada normalmente)
"""
import json
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

import config as cfg

ALTURA, LARGURA = 120, 160
BYTES_QUADRO = ALTURA * LARGURA


# ------------------------------------------------------------------ pré-processamento
def reduzir(quadro: np.ndarray) -> np.ndarray:
    """Quadro 120x160 uint8 -> recorte da parte de baixo reduzido 2x2 -> (40,80) uint8."""
    roi = quadro[cfg.APR_ROI_LINHA_INICIO:, :]
    h = roi.shape[0] // 2
    return roi[:h * 2].reshape(h, 2, LARGURA // 2, 2).mean(axis=(1, 3)).round().astype(np.uint8)


def normalizar(reduzidos: np.ndarray) -> np.ndarray:
    """(N,40,80) uint8 -> (N,1,40,80) float32, com contraste normalizado por imagem
    (a câmera muda a exposição sozinha; sem isso a CNN aprenderia o brilho, não a pista)."""
    x = reduzidos.astype(np.float32) / 255.0
    mu = x.mean(axis=(1, 2), keepdims=True)
    sd = x.std(axis=(1, 2), keepdims=True)
    return np.clip((x - mu) / (sd + 0.08), -4, 4)[:, None]


def preparar_entrada(quadro: np.ndarray) -> np.ndarray:
    """Um quadro -> (1,1,40,80) pronto para a CNN."""
    return normalizar(reduzir(quadro)[None])


def aumentar(x: np.ndarray, y_dir: np.ndarray, rng: np.random.Generator):
    """Espelho horizontal (a direção troca de sinal) + ruído. O espelho é válido porque a tarefa é simétrica
    e equilibra curvas à esquerda e à direita."""
    x = x.copy()
    y = y_dir.copy()
    flip = rng.random(len(x)) < 0.5
    x[flip] = x[flip][..., ::-1]
    y[flip] = -y[flip]
    x += rng.normal(0, 0.05, x.shape).astype(np.float32)
    return x, y


# ------------------------------------------------------------------ gravação
class GravadorEpisodio:
    def __init__(self, pasta: Path, meta_inicio: dict):
        self.pasta = Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)
        self._frames = open(self.pasta / "frames.u8", "ab")
        self._passos = open(self.pasta / "passos.jsonl", "a", encoding="utf-8")
        self.meta_inicio = meta_inicio
        self.n = 0

    def registrar(self, quadro: np.ndarray, passo: dict) -> None:
        self._frames.write(np.ascontiguousarray(quadro, np.uint8).tobytes())
        passo = dict(passo, i=self.n)
        self._passos.write(json.dumps(passo, default=float) + "\n")
        self._frames.flush()
        self._passos.flush()
        self.n += 1

    def fechar(self, resumo: dict) -> None:
        self._frames.close()
        self._passos.close()
        tmp = self.pasta / "meta.tmp"
        tmp.write_text(json.dumps({**self.meta_inicio, **resumo, "n_passos": self.n}, indent=1, default=float),
                       encoding="utf-8")
        tmp.replace(self.pasta / "meta.json")


@dataclass
class Episodio:
    pasta: Path
    passos: list
    meta: dict | None
    _frames: np.ndarray | None = field(default=None, repr=False)

    @property
    def id(self) -> str:
        return self.pasta.name

    @property
    def n(self) -> int:
        return len(self.passos)

    def quadros(self) -> np.ndarray:
        if self._frames is None:
            bruto = np.memmap(self.pasta / "frames.u8", dtype=np.uint8, mode="r")
            n = min(len(bruto) // BYTES_QUADRO, len(self.passos))
            self._frames = bruto[:n * BYTES_QUADRO].reshape(n, ALTURA, LARGURA)
        return self._frames


def carregar_episodio(pasta: Path) -> Episodio:
    pasta = Path(pasta)
    passos = []
    arq = pasta / "passos.jsonl"
    if arq.exists():
        for linha in arq.read_text(encoding="utf-8").splitlines():
            try:
                passos.append(json.loads(linha))
            except json.JSONDecodeError:
                break                                  # última linha cortada por queda de energia
    meta = None
    if (pasta / "meta.json").exists():
        meta = json.loads((pasta / "meta.json").read_text(encoding="utf-8"))
    nq = (pasta / "frames.u8").stat().st_size // BYTES_QUADRO if (pasta / "frames.u8").exists() else 0
    return Episodio(pasta, passos[:nq], meta)


def listar_episodios(base: Path) -> list[Path]:
    d = Path(base) / "episodios"
    return sorted(p for p in d.glob("ep_*") if p.is_dir()) if d.exists() else []


# ------------------------------------------------------------------ rótulos
def rotulos_do_episodio(ep: Episodio, max_buraco: int | None = None):
    """Rótulos de treino de um episódio.

    O professor (OpenCV) só enxerga um traço do pontilhado de cada vez. Nos vãos curtos (<= max_buraco quadros)
    o erro lateral é interpolado entre o último e o próximo quadro em que a linha foi vista: é o carrinho usando
    o que viu DEPOIS para rotular o que não conseguiu ver antes. Vãos longos ficam sem rótulo de direção.

    Devolve dict com: dir (direção alvo), mascara_dir (bool), visivel (alvo da cabeça 'linha visível'),
    reparado (bool: rótulo veio de interpolação).
    """
    max_buraco = cfg.APR_MAX_BURACO if max_buraco is None else max_buraco
    n = ep.n
    e = np.array([p.get("e_prof") if p.get("prof_visivel") else np.nan for p in ep.passos], dtype=np.float64)
    t = np.array([p["t"] for p in ep.passos], dtype=np.float64)
    visto = ~np.isnan(e)
    reparado = np.zeros(n, bool)
    i = 0
    while i < n:
        if visto[i]:
            i += 1
            continue
        j = i
        while j < n and not visto[j]:
            j += 1
        tem_antes, tem_depois = i > 0, j < n
        if tem_antes and tem_depois and (j - i) <= max_buraco:
            e[i:j] = np.interp(t[i:j], [t[i - 1], t[j]], [e[i - 1], e[j]])
            reparado[i:j] = True
        i = j
    mascara = ~np.isnan(e)
    direcao = np.clip(cfg.APR_GANHO_PROF * np.nan_to_num(e), -1, 1)
    return {"dir": direcao, "mascara_dir": mascara, "visivel": mascara.astype(np.float32), "reparado": reparado}


# ------------------------------------------------------------------ buffer de treino
class BufferTreino:
    """Todos os quadros dos episódios gravados, já reduzidos (uint8 40x80), com rótulos e pesos.
    A divisão treino/validação/teste é por EPISÓDIO inteiro (quadros vizinhos são quase iguais: dividir quadro
    a quadro faria as métricas parecerem melhores do que são). O teste fica fora do treino e da seleção de pesos."""

    def __init__(self, base: Path, max_quadros: int | None = None):
        max_quadros = max_quadros or cfg.APR_BUFFER_MAX
        eps = [carregar_episodio(p) for p in listar_episodios(base)]
        eps = [e for e in eps if e.n > 0]
        usados, total = [], 0
        for e in reversed(eps):                       # mantém os mais recentes até o limite de memória
            if total + e.n > max_quadros and usados:
                break
            usados.append(e)
            total += e.n
        usados.reverse()
        self.episodios = usados
        X, D, M, V, W, R, E = [], [], [], [], [], [], []
        for k, e in enumerate(usados):
            rot = rotulos_do_episodio(e)
            q = e.quadros()
            X.append(np.stack([reduzir(f) for f in q]))
            D.append(rot["dir"]); M.append(rot["mascara_dir"]); V.append(rot["visivel"]); R.append(rot["reparado"])
            w = np.ones(e.n, np.float32)
            w[rot["reparado"]] *= 1.5                 # os vãos são justamente onde o professor falha
            if e.meta and e.meta.get("falha"):
                w[-cfg.APR_JANELA_FALHA:] *= 2.0      # quadros logo antes de sair da pista
            W.append(w)
            E.append(np.full(e.n, k))
        z = lambda lst, dt: np.concatenate(lst) if lst else np.zeros(0, dt)
        self.X = z(X, np.uint8) if X else np.zeros((0, 40, 80), np.uint8)
        self.dir, self.mascara = z(D, np.float64).astype(np.float32), z(M, bool)
        self.visivel, self.peso = z(V, np.float32), z(W, np.float32)
        self.reparado, self.ep_idx = z(R, bool), z(E, int)
        self._dividir()

    def _dividir(self) -> None:
        n_ep = len(self.episodios)
        val_eps = set()
        teste_eps = set()
        if n_ep >= 3:
            for k, ep in enumerate(self.episodios):
                sufixo = ep.id.rsplit("_", 1)[-1]
                numero = int(sufixo) if sufixo.isdigit() else zlib.crc32(ep.id.encode())
                # IDs estáveis: o papel do episódio não muda quando novas tentativas são gravadas.
                if numero == 1 or (numero >= 3 and numero % 5 == 0):
                    val_eps.add(k)
                elif numero == 2 or (numero >= 3 and numero % 5 == 1):
                    teste_eps.add(k)
        elif n_ep == 2:
            val_eps = {1}
        self.val_mask = np.isin(self.ep_idx, list(val_eps)) if len(self.ep_idx) else np.zeros(0, bool)
        self.teste_mask = np.isin(self.ep_idx, list(teste_eps)) if len(self.ep_idx) else np.zeros(0, bool)

    def __len__(self) -> int:
        return len(self.X)

    @property
    def n_rotulados(self) -> int:
        return int(self.mascara.sum())

    def indices(self, validacao: bool) -> np.ndarray:
        m = self.val_mask if validacao else ~(self.val_mask | self.teste_mask)
        return np.flatnonzero(m)

    def indices_teste(self) -> np.ndarray:
        return np.flatnonzero(self.teste_mask)

    def lote(self, idx: np.ndarray, rng: np.random.Generator | None = None):
        x = normalizar(self.X[idx])
        y = self.dir[idx].copy()
        if rng is not None:
            x, y = aumentar(x, y, rng)
        return x, y, self.mascara[idx], self.visivel[idx], self.peso[idx]
