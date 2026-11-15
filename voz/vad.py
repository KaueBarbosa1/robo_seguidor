"""Detector de fala por energia (VAD) com histerese.

Portado de escuta_continua.py do projeto original (SegmentadorVAD), sem alterar a lógica:
SILENCIO -> FALA -> (fecha segmento) -> SILENCIO. O limiar é calibrado sozinho com o
ruído de fundo do início (~1 s). Um pré-roll evita cortar o começo da palavra.
Parâmetros expostos para o robô: `taxa` e `bloco` (para microfones que não gravam em 16 kHz)
e `blocos_fim` (quanto silêncio espera antes de fechar a palavra: afeta a latência do "pare").
"""
import numpy as np

TAXA = 16000
BLOCO = 1024          # amostras por bloco (~64 ms a 16 kHz)


class SegmentadorVAD:
    def __init__(self, taxa=TAXA, bloco=BLOCO,
                 fator_limiar=3.5, limiar_minimo=0.010,
                 blocos_inicio=2, blocos_fim=8, preroll_blocos=3,
                 dur_min_s=0.25, dur_max_s=2.5, calibracao_s=1.0):
        self.taxa = taxa
        self.bloco = bloco
        self.fator_limiar = fator_limiar
        self.limiar_minimo = limiar_minimo
        self.blocos_inicio = blocos_inicio
        self.blocos_fim = blocos_fim
        self.preroll_blocos = preroll_blocos
        self.min_blocos_fala = max(2, round(dur_min_s * taxa / bloco))
        self.max_amostras = int(dur_max_s * taxa)
        self.blocos_calibracao = max(1, int(calibracao_s * taxa / bloco))

        self._rms_fundo = []
        self.limiar = None            # definido após calibração
        self._em_fala = False
        self._acima = 0
        self._abaixo = 0
        self._blocos_fala = 0
        self._preroll = []
        self._segmento = []
        self.nivel = 0                # 0-100

    def _rms(self, bloco):
        return float(np.sqrt(np.mean(bloco.astype(np.float64) ** 2)))

    def processar_bloco(self, bloco):
        """Recebe um bloco float32 [-1, 1]. Devolve um segmento de fala quando um termina, ou None."""
        rms = self._rms(bloco)

        # ---- calibração: aprende o ruído de fundo ----
        if self.limiar is None:
            self._rms_fundo.append(rms)
            if len(self._rms_fundo) >= self.blocos_calibracao:
                fundo = float(np.median(self._rms_fundo))
                self.limiar = max(fundo * self.fator_limiar, self.limiar_minimo)
            self.nivel = 0
            return None

        self.nivel = int(min(100, 100 * rms / (2 * self.limiar)))

        if not self._em_fala:
            self._preroll.append(bloco.copy())
            if len(self._preroll) > self.preroll_blocos:
                self._preroll.pop(0)

            self._acima = self._acima + 1 if rms >= self.limiar else 0
            if self._acima >= self.blocos_inicio:
                self._em_fala = True
                self._segmento = list(self._preroll)
                self._preroll = []
                self._blocos_fala = self._acima
                self._acima = 0
                self._abaixo = 0
            return None

        # ---- em fala: acumula e observa o silêncio ----
        self._segmento.append(bloco.copy())
        if rms >= self.limiar:
            self._blocos_fala += 1
            self._abaixo = 0
        else:
            self._abaixo += 1

        tamanho = sum(len(b) for b in self._segmento)
        if self._abaixo >= self.blocos_fim or tamanho >= self.max_amostras:
            self._em_fala = False
            segmento = np.concatenate(self._segmento)
            self._segmento = []
            if self._blocos_fala >= self.min_blocos_fala:
                return segmento
        return None
