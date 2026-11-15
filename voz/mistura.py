"""Modelo de mistura LSTM + SVM (média das probabilidades), SEM PyTorch.

O `modelo_mistura.pkl` é um arquivo do torch.save (zip com data.pkl + tensores). Para não
instalar o PyTorch na Raspberry Pi:
  - o arquivo é lido com um desserializador com LISTA DE PERMISSÕES: só reconstrói os objetos
    esperados (numpy, SVC, StandardScaler, OrderedDict e tensores), qualquer outra coisa é recusada;
  - os tensores viram arrays NumPy;
  - o BiLSTM (1 camada, bidirecional, média no tempo + camada linear) roda em NumPy, seguindo as
    equações do torch.nn.LSTM (ordem das portas i, f, g, o).

Fluxo igual ao prever_comando.py original:
    pl = softmax(LSTM(sequência normalizada))      sequência: 60 colunas, agrupadas de 4 em 4
    ps = SVM.predict_proba(scaler(244 atributos))
    probabilidades = (pl + ps) / 2
"""
import importlib
import io
import logging
import pickle
import zipfile

import numpy as np

from voz import features as F

log = logging.getLogger("voz")

_PERMITIDOS = {
    ("collections", "OrderedDict"),
    ("_codecs", "encode"),
    ("numpy", "ndarray"),
    ("numpy", "dtype"),
    ("numpy._core.multiarray", "_reconstruct"),
    ("numpy._core.multiarray", "scalar"),
    ("numpy.core.multiarray", "_reconstruct"),     # numpy 1.x
    ("numpy.core.multiarray", "scalar"),
    ("sklearn.svm._classes", "SVC"),
    ("sklearn.preprocessing._data", "StandardScaler"),
}
_TIPOS_STORAGE = {"FloatStorage": np.float32, "DoubleStorage": np.float64,
                  "LongStorage": np.int64, "IntStorage": np.int32}


class _TipoStorage:
    def __init__(self, dtype):
        self.dtype = np.dtype(dtype)


def _reconstruir_tensor(storage, offset, size, stride, requires_grad=False,
                        hooks=None, metadata=None):
    """Equivalente numpy de torch._utils._rebuild_tensor_v2."""
    if len(size) == 0:
        return np.array(storage[offset])
    passos = tuple(s * storage.itemsize for s in stride)
    vista = np.lib.stride_tricks.as_strided(storage[offset:], shape=tuple(size), strides=passos)
    return np.array(vista, copy=True)


class _Descompactador(pickle.Unpickler):
    def __init__(self, arquivo, zf: zipfile.ZipFile, prefixo: str):
        super().__init__(arquivo)
        self._zf = zf
        self._prefixo = prefixo

    def find_class(self, modulo, nome):
        if (modulo, nome) == ("torch._utils", "_rebuild_tensor_v2"):
            return _reconstruir_tensor
        if modulo == "torch" and nome in _TIPOS_STORAGE:
            return _TipoStorage(_TIPOS_STORAGE[nome])
        if (modulo, nome) in _PERMITIDOS:
            try:
                return getattr(importlib.import_module(modulo), nome)
            except (ImportError, AttributeError):
                if modulo.startswith("numpy._core"):
                    return getattr(importlib.import_module(modulo.replace("_core", "core")), nome)
                raise
        raise pickle.UnpicklingError(f"Objeto não permitido no modelo: {modulo}.{nome}")

    def persistent_load(self, pid):
        if pid[0] != "storage":
            raise pickle.UnpicklingError(f"id persistente desconhecido: {pid[0]}")
        tipo, chave, numel = pid[1], pid[2], pid[4]
        bruto = self._zf.read(f"{self._prefixo}/data/{chave}")
        return np.frombuffer(bruto, dtype=tipo.dtype, count=int(numel))


def carregar_pacote(caminho) -> dict:
    with zipfile.ZipFile(caminho) as zf:
        nome_pkl = next(n for n in zf.namelist() if n.endswith("/data.pkl"))
        prefixo = nome_pkl.rsplit("/", 1)[0]
        return _Descompactador(io.BytesIO(zf.read(nome_pkl)), zf, prefixo).load()


# ---------------------------------------------------------------- BiLSTM em NumPy
def _sigmoide(x):
    return 1.0 / (1.0 + np.exp(-x))


def _lstm_direcao(x, w_ih, w_hh, b_ih, b_hh, reverso):
    """Uma direção do LSTM. x: (T, F) -> saídas (T, H). Portas na ordem do PyTorch: i, f, g, o."""
    T = x.shape[0]
    H = w_hh.shape[1]
    entrada = x @ w_ih.T + (b_ih + b_hh)               # (T, 4H)
    h = np.zeros(H)
    c = np.zeros(H)
    saida = np.zeros((T, H))
    for t in (range(T - 1, -1, -1) if reverso else range(T)):
        g = entrada[t] + w_hh @ h
        i = _sigmoide(g[:H])
        f = _sigmoide(g[H:2 * H])
        cand = np.tanh(g[2 * H:3 * H])
        o = _sigmoide(g[3 * H:])
        c = f * c + i * cand
        h = o * np.tanh(c)
        saida[t] = h                                    # a saída fica no índice de tempo original
    return saida


class LSTMNumpy:
    def __init__(self, estado: dict, arq: dict):
        if arq["n_camadas"] != 1:
            raise ValueError("Só LSTM de 1 camada é suportado")
        self._w = {k: np.asarray(v, dtype=np.float64) for k, v in estado.items()}
        self._n_classes = arq["n_classes"]

    def probas(self, seq: np.ndarray) -> np.ndarray:
        w = self._w
        frente = _lstm_direcao(seq, w["lstm.weight_ih_l0"], w["lstm.weight_hh_l0"],
                               w["lstm.bias_ih_l0"], w["lstm.bias_hh_l0"], reverso=False)
        tras = _lstm_direcao(seq, w["lstm.weight_ih_l0_reverse"], w["lstm.weight_hh_l0_reverse"],
                             w["lstm.bias_ih_l0_reverse"], w["lstm.bias_hh_l0_reverse"], reverso=True)
        media = np.concatenate([frente, tras], axis=1).mean(axis=0)     # (2H,)
        logits = w["fc.weight"] @ media + w["fc.bias"]                  # dropout é identidade no eval
        e = np.exp(logits - logits.max())
        return e / e.sum()


# ------------------------------------------------------------------- preditor
class PreditorMistura:
    def __init__(self, caminho):
        p = carregar_pacote(caminho)
        if p.get("tipo") != "mistura_lstm_svm" or p.get("metodo") != "media":
            raise ValueError(f"Pacote inesperado: tipo={p.get('tipo')} metodo={p.get('metodo')}")
        ext = p["extracao"]
        esperado = {"taxa_alvo": F.TAXA_ALVO, "duracao_s": F.DURACAO_S, "num_ceps": F.NUM_CEPS,
                    "num_filtros": F.NUM_FILTROS, "n_fft": F.N_FFT}
        if ext != esperado:
            raise ValueError(f"Parâmetros de extração do modelo {ext} != voz/features.py {esperado}")

        self._classes = [str(c) for c in p["classes"]]
        self._svm = p["svm"]
        self._scaler = p["scaler_svm"]
        self._lstm = LSTMNumpy(p["lstm_state"], p["lstm_arq"])
        self._mu = np.asarray(p["seq_mu"], dtype=np.float64)
        self._sd = np.asarray(p["seq_sd"], dtype=np.float64)
        self._agrupar = int(p["agrupar"])
        log.info("Modelo de voz: mistura LSTM+SVM (%s) | classes: %s", caminho.name, self._classes)

    def probas_pcm(self, pcm: np.ndarray, taxa: int):
        """(probabilidades LSTM, probabilidades SVM) para um áudio em int16."""
        seq = F.extrair_sequencia(pcm, taxa, self._agrupar)
        seq = (seq - self._mu) / self._sd
        pl = self._lstm.probas(seq)

        vetor = F.extrair_features(pcm, taxa).reshape(1, -1)
        ps = self._svm.predict_proba(self._scaler.transform(vetor))[0]
        return pl, ps

    def prever_pcm(self, pcm: np.ndarray, taxa: int) -> tuple[str, float]:
        pl, ps = self.probas_pcm(pcm, taxa)
        probas = (pl + ps) / 2                          # mistura por média simples
        i = int(np.argmax(probas))
        return self._classes[i].lower(), float(probas[i])

    def prever(self, segmento: np.ndarray, taxa: int) -> tuple[str, float]:
        """Segmento float [-1, 1] do microfone; passa por int16 como no original."""
        return self.prever_pcm((np.clip(segmento, -1, 1) * 32767).astype(np.int16), taxa)
