from dataclasses import dataclass
import math
from pathlib import Path


@dataclass(frozen=True)
class OpcoesArmazenamento:
    raiz: Path
    fila_telemetria: int = 2048
    fila_eventos: int = 128
    fila_imagens: int = 8
    lote: int = 128
    intervalo_s: float = .2
    imagens: bool = False
    imagens_eventos: bool = False
    imagens_fps: float = 1.
    associacao_s: float = .25
    max_bytes: int = 2*1024**3
    max_imagens_bytes: int = 500*1024**2
    reserva_livre_bytes: int = 100*1024**2
    temperatura_alerta_c: float | None = None
    cpu_alerta_pct: float | None = None

    def __post_init__(self):
        for v in (self.fila_telemetria, self.fila_eventos, self.fila_imagens, self.lote):
            if type(v) is not int or not 1 <= v <= 100000:
                raise ValueError('Limites de fila/lote invalidos')
        for v in (self.intervalo_s, self.imagens_fps, self.associacao_s):
            if not math.isfinite(v) or v <= 0:
                raise ValueError('Prazos/frequencias invalidos')
        if min(self.max_bytes, self.max_imagens_bytes, self.reserva_livre_bytes) < 0:
            raise ValueError('Limites de disco invalidos')

    @classmethod
    def central(cls, **alteracoes):
        import config as cfg
        d = dict(raiz=cfg.ARMAZ_DIR, fila_telemetria=cfg.ARMAZ_FILA_TELEMETRIA,
                 fila_eventos=cfg.ARMAZ_FILA_EVENTOS, fila_imagens=cfg.ARMAZ_FILA_IMAGENS,
                 lote=cfg.ARMAZ_LOTE, intervalo_s=cfg.ARMAZ_INTERVALO_S,
                 imagens_fps=cfg.ARMAZ_IMAGENS_FPS, max_bytes=cfg.ARMAZ_MAX_BYTES,
                 max_imagens_bytes=cfg.ARMAZ_MAX_IMAGENS_BYTES,
                 reserva_livre_bytes=cfg.ARMAZ_RESERVA_LIVRE_BYTES,
                 temperatura_alerta_c=cfg.ARMAZ_ALERTA_TEMPERATURA_C,
                 cpu_alerta_pct=cfg.ARMAZ_ALERTA_CPU_PCT)
        d.update(alteracoes)
        return cls(**d)


def validar_pc():
    try:
        modelo = Path('/proc/device-tree/model').read_text()
    except OSError:
        return
    if 'Raspberry Pi' in modelo:
        raise ValueError('O gravador historico deve executar no computador, nao na Raspberry')
