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
    timestamp: float       # time.monotonic() de quando foi medida


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
        self._partida_ate = 0.0
        self._fim_manobra = 0.0
        self._leitura = Leitura(0.0, False, 0.0)
        self._acao: Acao | None = None
        self._manual: tuple[int, int, float, float | None] | None = None   # (PWM esq, PWM dir, instante, validade em s ou None)

    # ------------------------------------------------------------- modo
    @property
    def modo(self) -> Modo:
        with self.lock:
            return self._modo

    def definir_modo(self, modo: Modo, duracao_s: float | None = None) -> None:
        with self.lock:
            self._modo = modo
            if modo is not Modo.SEGUINDO:
                self._acao = None                 # uma ação velha nunca sobrevive a um "pare"
            if modo is not Modo.MANUAL:
                self._manual = None               # nem um comando remoto velho
            self._fim_manobra = time.monotonic() + duracao_s if duracao_s else 0.0

    def atualizar_manobra(self) -> Modo:
        """Encerra manobras temporizadas. Giro volta a seguir a linha; ré termina parado."""
        with self.lock:
            if self._modo in MANOBRAS and time.monotonic() >= self._fim_manobra:
                self._modo = Modo.PARADO if self._modo is Modo.RE else Modo.SEGUINDO
                self._acao = None
            return self._modo

    # ------------------------------------------------------------ remoto
    def definir_manual(self, esq: int, dir_: int, validade_s: float | None = None) -> None:
        """Comando do celular: entra em MANUAL (ou renova o prazo, se já estiver) com estes PWM.
        validade_s: por quanto tempo vale sem novo comando (None = REMOTO_TIMEOUT_S)."""
        with self.lock:
            self._modo = Modo.MANUAL
            self._acao = None
            self._partida_ate = 0.0
            self._fim_manobra = 0.0
            self._manual = (int(esq), int(dir_), time.monotonic(), validade_s)

    def ler_manual(self) -> tuple[int, int, float, float | None] | None:
        with self.lock:
            return self._manual

    # ---------------------------------------------------------- leitura
    def publicar_leitura(self, erro: float, linha_visivel: bool) -> None:
        nova = Leitura(erro, linha_visivel, time.monotonic())
        with self.lock:
            self._leitura = nova

    def ler_leitura(self) -> Leitura:
        with self.lock:
            return self._leitura

    # ----------------------------------------------------------- ação do aprendizado
    def publicar_acao(self, steer: float | None, vel_fator: float = 1.0) -> bool:
        """Só vale enquanto o modo é SEGUINDO (checado sob o lock: um 'pare' de voz não é desfeito)."""
        with self.lock:
            if steer is None or self._modo is not Modo.SEGUINDO:
                self._acao = None
                return False
            self._acao = Acao(float(steer), float(vel_fator), time.monotonic())
            return True

    def ler_acao(self) -> Acao | None:
        with self.lock:
            return self._acao
