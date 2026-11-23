"""Estado compartilhado entre as threads.

Regra de ouro: nenhuma thread mexe em variável global solta. Tudo passa por EstadoRobo,
que protege os dados com um RLock. Quem precisa de uma decisão atômica
("ler o modo E enviar ao motor") segura `estado.lock` durante toda a operação.
"""
import threading
import time
from dataclasses import dataclass
from enum import Enum, auto


class Modo(Enum):
    PARADO = auto()
    SEGUINDO = auto()
    GIRO_ESQ = auto()
    GIRO_DIR = auto()
    RE = auto()
    MANUAL = auto()          # controle remoto (celular por Bluetooth): anda enquanto chegarem comandos


MANOBRAS = {Modo.GIRO_ESQ, Modo.GIRO_DIR, Modo.RE}


@dataclass(frozen=True)
class Leitura:
    """Última medição da visão (imutável, então pode ser lida fora do lock)."""
    erro: float            # -1.0 (linha à esquerda) .. +1.0 (linha à direita)
    linha_visivel: bool
    timestamp: float       # recepção na Pi (ou medição para fontes legadas)
    idade_captura_s: float = 0.0     # limite estimado na recepção; nunca renovado no controle
    frame_id: int | None = None
    camera_ok: bool = True
    geracao_camera: int = 0
    sessao: int = 0
    direcao: float = 0.0             # dx/dy em direção ao alto da imagem
    escala_direcao: float = 0.0      # altura ROI / meia largura do frame
    confianca: float = 1.0
    motivo: str = "legado"

    def idade(self, agora: float) -> float:
        return agora - self.timestamp + self.idade_captura_s


@dataclass(frozen=True)
class Acao:
    """Ação do aprendizado (direção -1..1 e fator de velocidade), executada pelo controle."""
    steer: float
    vel_fator: float
    timestamp: float


class EstadoRobo:
    def __init__(self):
        self.lock = threading.RLock()
        self._modo = Modo.PARADO            # começa parado: só anda depois de ouvir "siga"
        self._encerrando = False
        self._sessao_visao = 0
        self._partida_ate = 0.0
        self._fim_manobra = 0.0
        self._leitura = Leitura(0.0, False, 0.0)
        self._acao: Acao | None = None
        self._manual: tuple[int, int, float, float | None] | None = None   # (PWM esq, PWM dir, instante, validade em s ou None)
        self._recuo_bloqueia_avanco = False
        self._parada_manual_id = 0

    # ------------------------------------------------------------- modo
    @property
    def modo(self) -> Modo:
        with self.lock:
            return self._modo

    def definir_modo(self, modo: Modo, duracao_s: float | None = None) -> None:
        with self.lock:
            if self._encerrando and modo is not Modo.PARADO:
                return
            self._trocar_modo(modo)
            if modo is not Modo.SEGUINDO:
                self._acao = None                 # uma ação velha nunca sobrevive a um "pare"
            if modo is not Modo.MANUAL:
                self._manual = None               # nem um comando remoto velho
            self._fim_manobra = time.monotonic() + duracao_s if duracao_s else 0.0

    @property
    def encerrando(self) -> bool:
        with self.lock:
            return self._encerrando

    def encerrar(self) -> None:
        with self.lock:
            self._encerrando = True
            self.definir_modo(Modo.PARADO)
            self._partida_ate = 0.0

    @property
    def sessao_visao(self) -> int:
        with self.lock:
            return self._sessao_visao

    def _trocar_modo(self, modo: Modo) -> None:
        # Chamado sob lock: até um pare/siga entre dois ciclos invalida a visão.
        if self._modo is not modo:
            self._sessao_visao += 1
            self._leitura = Leitura(0.0, False, 0.0, camera_ok=False,
                                    sessao=self._sessao_visao)
        self._modo = modo

    def atualizar_manobra(self) -> Modo:
        """Encerra manobras temporizadas. Giro volta a seguir a linha; ré termina parado."""
        with self.lock:
            if self._modo in MANOBRAS and time.monotonic() >= self._fim_manobra:
                self._trocar_modo(Modo.PARADO if self._modo is Modo.RE else Modo.SEGUINDO)
                self._acao = None
            return self._modo

    # ------------------------------------------------------------ remoto
    def definir_manual(self, esq: int, dir_: int, validade_s: float | None = None) -> None:
        """Comando do celular: entra em MANUAL (ou renova o prazo, se já estiver) com estes PWM.
        validade_s: por quanto tempo vale sem novo comando (None = REMOTO_TIMEOUT_S)."""
        with self.lock:
            if self._encerrando:
                return
            if esq == 0 and dir_ == 0:
                self._recuo_bloqueia_avanco = False
                self._parada_manual_id += 1
            self._trocar_modo(Modo.MANUAL)
            self._acao = None
            self._partida_ate = 0.0
            self._fim_manobra = 0.0
            self._manual = (int(esq), int(dir_), time.monotonic(), validade_s)

    def ler_manual(self) -> tuple[int, int, float, float | None] | None:
        with self.lock:
            return self._manual

    # ---------------------------------------------------------- leitura
    def publicar_leitura(self, erro: float, linha_visivel: bool, *,
                         timestamp: float | None = None, sessao: int | None = None,
                         **metadados) -> bool:
        with self.lock:
            if self._encerrando:
                return False
            if sessao is not None and (sessao != self._sessao_visao or self._modo is not Modo.SEGUINDO):
                return False
            self._leitura = Leitura(erro, linha_visivel,
                                    time.monotonic() if timestamp is None else timestamp,
                                    sessao=self._sessao_visao, **metadados)
            return True

    def ler_leitura(self) -> Leitura:
        with self.lock:
            return self._leitura

    # ----------------------------------------------------------- ação do aprendizado
    def publicar_acao(self, steer: float | None, vel_fator: float = 1.0) -> bool:
        """Só vale enquanto o modo é SEGUINDO (checado sob o lock: um 'pare' de voz não é desfeito)."""
        with self.lock:
            if self._encerrando or steer is None or self._modo is not Modo.SEGUINDO:
                self._acao = None
                return False
            self._acao = Acao(float(steer), float(vel_fator), time.monotonic())
            return True

    def ler_acao(self) -> Acao | None:
        with self.lock:
            return self._acao
