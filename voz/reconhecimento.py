"""Módulo de voz: escuta contínua do microfone USB + classificação dos comandos.

Segue o fluxo do projeto original (escuta_continua.py):
  microfone -> VAD por energia (voz/vad.py) -> segmento da palavra
            -> atributos (voz/features.py) -> modelo -> (comando, confiança)
            -> callback `ao_comando` (controle.py)

Modelos (config.MODELO_TIPO):
  "mistura": LSTM + SVM, média das probabilidades (voz/mistura.py, modelo_mistura.pkl). Sem PyTorch.
  "mlp":     MLP + StandardScaler sobre os 244 atributos (modelo.pkl, joblib).

O classificador só roda quando alguém fala, e o callback do microfone não faz nada pesado.
Use o mesmo scikit-learn do treino (1.8.0) na Raspberry Pi.
"""
import logging
import queue
import threading
import time
from typing import Callable

import numpy as np

import config as cfg
from voz.features import extrair_features
from voz.vad import SegmentadorVAD

log = logging.getLogger("voz")


def para_pcm(segmento: np.ndarray) -> np.ndarray:
    """Float [-1, 1] -> int16, como o escuta_continua.py original (gravava um .wav de 16 bits
    antes de classificar). Mantém o resultado idêntico ao do treino."""
    return (np.clip(segmento, -1, 1) * 32767).astype(np.int16)



def achar_dispositivo(sd, escolha):
    """None = padrão; int = índice; str = primeiro dispositivo de ENTRADA cujo nome contém o texto."""
    if escolha is None:
        return None
    if isinstance(escolha, int):
        return escolha
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and str(escolha).lower() in d["name"].lower():
            return i
    raise RuntimeError(f"nenhum microfone com '{escolha}' no nome (headset pareado e conectado?)")


def abrir_taxa(sd, dispositivo) -> int:
    """Primeira taxa de MIC_SR_TENTATIVAS que o dispositivo aceita (headsets costumam dar 8/16 kHz)."""
    tentativas = list(cfg.MIC_SR_TENTATIVAS)
    try:
        padrao = int(sd.query_devices(dispositivo, "input")["default_samplerate"])
        tentativas.append(padrao)
    except Exception:
        pass
    for taxa in tentativas:
        try:
            sd.check_input_settings(device=dispositivo, samplerate=taxa, channels=1, dtype="float32")
            if taxa < cfg.MIC_SR:
                log.warning("Microfone só aceita %d Hz: reconhecimento tende a piorar "
                            "(provável perfil HFP/HSP de banda estreita).", taxa)
            return taxa
        except Exception:
            continue
    raise RuntimeError("o microfone não aceitou nenhuma taxa de amostragem conhecida")


def reamostrar(blk: np.ndarray, de: int, para: int, n_saida: int) -> np.ndarray:
    """Converte um bloco de `de` Hz para `para` Hz e garante exatamente n_saida amostras."""
    if de != para:
        from math import gcd
        from scipy.signal import resample_poly
        g = gcd(de, para)
        blk = resample_poly(blk, para // g, de // g).astype(np.float32)
    if len(blk) < n_saida:
        blk = np.pad(blk, (0, n_saida - len(blk)))
    return blk[:n_saida]

class PreditorMLP:
    """modelo.pkl (joblib): MLP + StandardScaler sobre os 244 atributos."""

    def __init__(self, caminho):
        import joblib                                   # import local: o resto do robô roda sem

        pacote = joblib.load(caminho)
        self._modelo = pacote["modelo"]
        self._scaler = pacote["scaler"]
        self._classes = [str(c) for c in pacote["classes"]]
        log.info("Modelo de voz: %s (%s) | classes: %s",
                 pacote.get("nome", type(self._modelo).__name__), caminho.name, self._classes)

    def prever_pcm(self, pcm: np.ndarray, taxa: int) -> tuple[str, float]:
        x = extrair_features(pcm, taxa).reshape(1, -1)
        probas = self._modelo.predict_proba(self._scaler.transform(x))[0]
        i = int(np.argmax(probas))
        idx_classe = int(self._modelo.classes_[i])
        return self._classes[idx_classe].lower(), float(probas[i])

    def prever(self, segmento: np.ndarray, taxa: int) -> tuple[str, float]:
        """Devolve (comando em minúsculas, confiança 0..1)."""
        return self.prever_pcm(para_pcm(segmento), taxa)


def carregar_preditor():
    if cfg.MODELO_TIPO == "mistura":
        from voz.mistura import PreditorMistura
        return PreditorMistura(cfg.MODELO_MISTURA)
    if cfg.MODELO_TIPO == "mlp":
        return PreditorMLP(cfg.MODELO_MLP)
    raise ValueError(f"MODELO_TIPO inválido: {cfg.MODELO_TIPO!r} (use 'mistura' ou 'mlp')")


class ThreadVoz(threading.Thread):
    def __init__(self, ao_comando: Callable[[str], None], parar: threading.Event):
        super().__init__(name="voz", daemon=True)
        self._ao_comando = ao_comando          # chamado com "siga", "pare", ...
        self._parar = parar
        self._mic_ok = False

    def run(self) -> None:
        try:
            self._loop()
        except Exception:
            log.exception("Thread de voz caiu")
            self._parar.set()                  # main para o robô todo

    def _loop(self) -> None:
        preditor = carregar_preditor()             # se o modelo falhar, é erro fatal (derruba o robô)
        avisou = False
        while not self._parar.is_set():
            try:
                self._escutar(preditor)
            except Exception as e:                 # headset desligou, saiu do alcance, PortAudio falhou...
                log.error("Microfone indisponível (%s). Nova tentativa em %.0f s.", e, cfg.MIC_REABRIR_S)
                if self._mic_ok:                   # o microfone chegou a funcionar e caiu: nova queda
                    avisou, self._mic_ok = False, False
                if cfg.PARAR_SE_SEM_MICROFONE and not avisou:
                    # sem microfone ninguém consegue mandar "pare": por segurança o robô para e só
                    # volta a andar quando o headset voltar e alguém disser "siga"
                    log.error("Sem canal de voz: parando o robô por segurança.")
                    self._ao_comando("pare")
                avisou = True
                self._parar.wait(cfg.MIC_REABRIR_S)

    def _escutar(self, preditor) -> None:
        import sounddevice as sd               # import local: precisa de PortAudio/microfone

        dispositivo = achar_dispositivo(sd, cfg.MIC_DEVICE)
        taxa = abrir_taxa(sd, dispositivo)
        bloco_nat = int(taxa * 0.064)          # ~64 ms na taxa do dispositivo
        bloco = int(cfg.MIC_SR * 0.064)        # 1024 amostras a 16 kHz, como no original
        vad = SegmentadorVAD(taxa=cfg.MIC_SR, bloco=bloco, blocos_fim=cfg.VAD_BLOCOS_FIM)
        fila: queue.Queue[np.ndarray] = queue.Queue()
        erro_stream: list = []

        def callback(indata, frames, tempo, status):
            if status:
                log.debug("audio status: %s", status)
            fila.put(indata[:, 0].copy())      # só repassa o bloco

        def terminou():                        # chamado pelo PortAudio se o dispositivo sumir
            erro_stream.append(True)

        log.info("Calibrando ruído de fundo (fique em silêncio ~1 s)...")
        with sd.InputStream(device=dispositivo, samplerate=taxa, channels=1, blocksize=bloco_nat,
                            dtype="float32", callback=callback, finished_callback=terminou):
            log.info("Escutando microfone (dispositivo %s, %d Hz).", dispositivo, taxa)
            self._mic_ok = True
            ultimo_bloco = time.monotonic()
            while not self._parar.is_set():
                try:
                    blk = fila.get(timeout=0.5)
                except queue.Empty:
                    if erro_stream or time.monotonic() - ultimo_bloco > 3.0:
                        raise RuntimeError("o stream de áudio parou (headset desconectado?)")
                    continue
                ultimo_bloco = time.monotonic()
                blk = reamostrar(blk, taxa, cfg.MIC_SR, bloco)
                segmento = vad.processar_bloco(blk)
                if segmento is not None:
                    self._classificar(preditor, segmento)

    def _classificar(self, preditor, segmento: np.ndarray) -> None:
        try:
            rotulo, conf = preditor.prever(segmento, cfg.MIC_SR)
        except Exception:
            log.exception("Erro ao classificar segmento")
            return
        self.tratar(rotulo, conf)

    def tratar(self, rotulo: str, conf: float) -> None:
        """Aplica o limiar de confiança e repassa o comando ao controle."""
        if rotulo not in cfg.COMANDOS:
            return
        limiar = cfg.LIMIAR_CONFIANCA.get(rotulo, cfg.LIMIAR_PADRAO)
        if conf < limiar:
            log.info("Rejeitado: '%s' com %.0f%% (limiar %.0f%%)", rotulo, conf * 100, limiar * 100)
            return
        log.info("Comando de voz: %s (%.0f%%)", rotulo, conf * 100)
        self._ao_comando(rotulo)
