from dataclasses import dataclass
import ipaddress
import math


@dataclass(frozen=True)
class Opcoes:
    host: str
    porta: int
    token: str
    telemetria_hz: float = 10.
    imagens_fps: float = 5.
    heartbeat_s: float = 2.
    timeout_s: float = 5.
    reconexao_s: float = 1.
    validade_s: float = .5
    fila: int = 1
    max_json: int = 65536
    max_jpeg: int = 2*1024*1024
    max_clientes: int = 4

    def __post_init__(self):
        ip = ipaddress.ip_address(self.host)
        if ip.is_unspecified or not (ip.is_private or ip.is_loopback) or ip.is_multicast:
            raise ValueError('Use IP local explicito; bind publico/0.0.0.0 recusado')
        if (not 0 <= self.porta <= 65535 or not isinstance(self.token, str) or
                not self.token.isascii() or len(self.token) < 24):
            raise ValueError('Porta invalida ou token sem 24 caracteres ASCII')
        for v in (self.telemetria_hz, self.imagens_fps, self.heartbeat_s,
                  self.timeout_s, self.reconexao_s, self.validade_s):
            if not math.isfinite(v) or v <= 0:
                raise ValueError('Frequencias e prazos devem ser positivos e finitos')
        if self.telemetria_hz > 200 or self.imagens_fps > 60 or self.timeout_s > 60:
            raise ValueError('Limite: telemetria 200 Hz, imagens 60 FPS, timeout 60 s')
        if not 1 <= self.fila <= 8 or not 1 <= self.max_clientes <= 16:
            raise ValueError('Fila 1..8 e clientes 1..16')
        if not 1024 <= self.max_json <= 262144 or not 1024 <= self.max_jpeg <= 4*1024*1024:
            raise ValueError('Limites de mensagem fora da faixa permitida')

    @classmethod
    def central(cls, token, **alteracoes):
        import config as cfg
        campos = dict(host=cfg.REDE_HOST, porta=cfg.REDE_PORTA, token=token,
            telemetria_hz=cfg.REDE_TELEMETRIA_HZ, imagens_fps=cfg.REDE_IMAGENS_FPS,
            heartbeat_s=cfg.REDE_HEARTBEAT_S, timeout_s=cfg.REDE_TIMEOUT_S,
            reconexao_s=cfg.REDE_RECONEXAO_S, validade_s=cfg.REDE_VALIDADE_S,
            fila=cfg.REDE_FILA, max_json=cfg.REDE_MAX_JSON, max_jpeg=cfg.REDE_MAX_JPEG,
            max_clientes=cfg.REDE_MAX_CLIENTES)
        campos.update(alteracoes)
        return cls(**campos)


def url_local(host, porta):
    return f'ws://[{host}]:{porta}' if ':' in host else f'ws://{host}:{porta}'
