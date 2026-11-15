"""Extração de atributos de áudio (244 features por comando).

Cópia fiel das funções de 2_extract_mfccs.py do projeto original, para que a
inferência no robô use EXATAMENTE o mesmo cálculo do treino. As únicas mudanças:
  - recebe o sinal já em memória (em vez de ler um .wav);
  - o banco de filtros mel e a matriz da DCT são calculados uma vez só (o resultado
    numérico é idêntico, só evita refazer a cada comando na Raspberry Pi).

Vetor final = 244 valores:
  (média, desvio, máx, mín) × 60 colunas [20 MFCC + 20 delta + 20 delta-delta]
  + [energia, taxa de cruzamento de zero, centróide espectral, largura espectral]
"""
import numpy as np

TAXA_ALVO = 16000
DURACAO_S = 2.5
NUM_CEPS = 20
NUM_FILTROS = 26
N_FFT = 512
JANELA_MS = 25.0
PASSO_MS = 10.0
COEF_PRE_ENFASE = 0.97


# ------------------------------------------------------------ preparação do sinal
def reamostrar(sinal: np.ndarray, taxa_orig: int, taxa_destino: int) -> np.ndarray:
    if taxa_orig == taxa_destino:
        return sinal

    n_orig = len(sinal)
    n_destino = int(round(n_orig * taxa_destino / taxa_orig))

    espectro = np.fft.rfft(sinal)
    n_bins_destino = n_destino // 2 + 1
    novo_espectro = np.zeros(n_bins_destino, dtype=complex)
    n = min(len(espectro), n_bins_destino)
    novo_espectro[:n] = espectro[:n]

    return np.fft.irfft(novo_espectro, n=n_destino) * (n_destino / n_orig)


def ajustar_duracao(sinal: np.ndarray, taxa: int, duracao_s: float) -> np.ndarray:
    tamanho_alvo = int(round(taxa * duracao_s))
    if len(sinal) >= tamanho_alvo:
        return sinal[:tamanho_alvo]
    return np.pad(sinal, (0, tamanho_alvo - len(sinal)))


def pre_enfase(sinal: np.ndarray, coef: float = 0.9) -> np.ndarray:
    return np.append(sinal[0], sinal[1:] - coef * sinal[:-1])


def janelamento(sinal: np.ndarray, taxa: int, dur_janela_ms: float = 25.0,
                passo_ms: float = 10.0) -> np.ndarray:
    tamanho_quadro = int(round(dur_janela_ms * taxa / 1000))
    passo = int(round(passo_ms * taxa / 1000))
    num_quadros = 1 + (len(sinal) - tamanho_quadro) // passo

    indices = (np.arange(tamanho_quadro)[np.newaxis, :]
               + np.arange(num_quadros)[:, np.newaxis] * passo)
    quadros = sinal[indices]

    hamming = 0.54 - 0.46 * np.cos(2 * np.pi * np.arange(tamanho_quadro) / (tamanho_quadro - 1))
    return quadros * hamming


def espectro_potencia(quadros: np.ndarray, N_fft: int = 512) -> np.ndarray:
    espectro = np.fft.rfft(quadros, n=N_fft)
    return (np.abs(espectro) ** 2) / N_fft


# ----------------------------------------------------------------- mel e DCT
def hz_para_mel(hz: float) -> float:
    return 2595.0 * np.log10(1.0 + hz / 700.0)


def mel_para_hz(mel: float) -> float:
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def banco_filtros_mel(num_filtros: int, N_fft: int, taxa: int,
                      freq_min: float = 0.0, freq_max: float = None) -> np.ndarray:
    if freq_max is None:
        freq_max = taxa / 2.0

    pontos_mel = np.linspace(hz_para_mel(freq_min), hz_para_mel(freq_max), num_filtros + 2)
    pontos_hz = mel_para_hz(pontos_mel)
    bins = np.floor((N_fft + 1) * pontos_hz / taxa).astype(int)

    num_bins = N_fft // 2 + 1
    filtros = np.zeros((num_filtros, num_bins))
    for m in range(1, num_filtros + 1):
        f_esq, f_centro, f_dir = bins[m - 1], bins[m], bins[m + 1]
        for k in range(f_esq, f_centro):
            filtros[m - 1, k] = (k - f_esq) / (f_centro - f_esq)
        for k in range(f_centro, f_dir):
            filtros[m - 1, k] = (f_dir - k) / (f_dir - f_centro)
    return filtros


def log_energias_mel(espectro: np.ndarray, filtros: np.ndarray) -> np.ndarray:
    energias = espectro @ filtros.T
    return np.log(np.maximum(energias, 1e-10))


def _matriz_dct(N: int) -> np.ndarray:
    n = np.arange(N)
    k = np.arange(N)[:, np.newaxis]
    return np.cos(np.pi / N * (n + 0.5) * k)


_FILTROS = banco_filtros_mel(NUM_FILTROS, N_FFT, TAXA_ALVO)   # calculados uma vez
_DCT = _matriz_dct(NUM_FILTROS)


# -------------------------------------------------------------------- deltas
def delta(feat: np.ndarray, N: int = 2) -> np.ndarray:
    Q, _ = feat.shape
    denominador = 2.0 * np.sum(np.arange(1, N + 1) ** 2)
    feat_pad = np.pad(feat, ((N, N), (0, 0)), mode="edge")

    d = np.zeros_like(feat)
    for n in range(1, N + 1):
        d += n * (feat_pad[N + n: N + n + Q] - feat_pad[N - n: N - n + Q])
    return d / denominador


def agregar_mfcc(feat: np.ndarray) -> np.ndarray:
    return np.concatenate([
        np.mean(feat, axis=0),
        np.std(feat, axis=0),
        np.max(feat, axis=0),
        np.min(feat, axis=0),
    ])


# ------------------------------------------------------ descritores adicionais
def taxa_cruzamento_zero(sinal: np.ndarray) -> float:
    sinais = np.sign(sinal)
    sinais[sinais == 0] = 1.0
    return np.mean(np.abs(np.diff(sinais)) / 2.0)


def descritores_espectrais(espectro_pot: np.ndarray, taxa: int) -> tuple[float, float]:
    mag = np.sqrt(espectro_pot)
    freqs = np.linspace(0, taxa / 2.0, mag.shape[1])
    soma = np.sum(mag, axis=1) + 1e-10

    centroide = np.sum(freqs[np.newaxis, :] * mag, axis=1) / soma
    desvio_freq = freqs[np.newaxis, :] - centroide[:, np.newaxis]
    largura = np.sqrt(np.sum((desvio_freq ** 2) * mag, axis=1) / soma)
    return float(np.mean(centroide)), float(np.mean(largura))


# ------------------------------------------------------------- função pública
def preparar(sinal: np.ndarray, taxa: int, coef_pre_enfase: float = COEF_PRE_ENFASE):
    """Sinal bruto -> (matriz 60 colunas por quadro, espectro de potência, sinal padronizado).

    Mesmos passos de extrair_mfcc(): normalização de pico, reamostragem para 16 kHz,
    duração fixa de 2,5 s (zeros no fim), pré-ênfase 0.97, quadros de 25 ms / passo 10 ms,
    mel (26 filtros), DCT descartando o coeficiente 0, deltas.
    """
    sinal = np.asarray(sinal, dtype=np.float64)
    if sinal.ndim == 2:
        sinal = sinal[:, 0]
    pico = np.max(np.abs(sinal))
    if pico > 0:
        sinal = sinal / pico

    sinal = reamostrar(sinal, taxa, TAXA_ALVO)
    sinal = ajustar_duracao(sinal, TAXA_ALVO, DURACAO_S)
    sinal_base = sinal.copy()

    sinal = pre_enfase(sinal, coef_pre_enfase)
    quadros = janelamento(sinal, TAXA_ALVO, JANELA_MS, PASSO_MS)
    espectro = espectro_potencia(quadros, N_FFT)

    log_mel = log_energias_mel(espectro, _FILTROS)
    coef = (log_mel @ _DCT.T)[:, 1: NUM_CEPS + 1]
    d1 = delta(coef)
    d2 = delta(d1)
    matriz = np.concatenate([coef, d1, d2], axis=1)
    return matriz, espectro, sinal_base


def extrair_features(sinal: np.ndarray, taxa: int) -> np.ndarray:
    """Vetor de 244 atributos usado pelo MLP e pelo SVM."""
    matriz, espectro, sinal_base = preparar(sinal, taxa)
    energia = np.mean(sinal_base ** 2)
    zcr = taxa_cruzamento_zero(sinal_base)
    centroide, largura = descritores_espectrais(espectro, TAXA_ALVO)
    return np.concatenate([agregar_mfcc(matriz), [energia, zcr, centroide, largura]])


# ------------------------------------------------- sequência para o LSTM
# ATENÇÃO: 5_extract_sequences.py e prever_comando.py chamam pre_enfase(sinal) SEM coeficiente,
# ou seja, usam o padrão 0.9, enquanto os 244 atributos (extrair_mfcc) usam 0.97.
# É assim que o LSTM foi treinado, então é assim que fica aqui.
COEF_PRE_ENFASE_SEQ = 0.9
AGRUPAR_PADRAO = 4


def agrupar_quadros(matriz: np.ndarray, n: int) -> np.ndarray:
    """Média a cada n quadros: (T, F) -> (T//n, F). Descarta a sobra final."""
    if n <= 1:
        return matriz
    T, F = matriz.shape
    T2 = (T // n) * n
    if T2 == 0:
        return matriz
    return matriz[:T2].reshape(T2 // n, n, F).mean(axis=1)


def extrair_sequencia(sinal: np.ndarray, taxa: int, agrupar: int = AGRUPAR_PADRAO) -> np.ndarray:
    """Sequência (T', 60) que entra no LSTM (antes da normalização seq_mu/seq_sd)."""
    matriz, _, _ = preparar(sinal, taxa, COEF_PRE_ENFASE_SEQ)
    return agrupar_quadros(matriz, agrupar)
