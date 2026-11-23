"""Interpretador dos comandos que chegam do celular (sem Bluetooth aqui: só texto -> intenção -> PWM).

Dois jeitos de mandar, que podem ser misturados:

1) Apps de "carrinho RC" (um caractere por toque, MAIÚSCULO, sem Enter):
     F frente   B trás   L curva à esquerda   R curva à direita
     G frente-esquerda   I frente-direita   H trás-esquerda   J trás-direita
     S ou D parar        0..9 velocidade (10%..90%)    q velocidade máxima (100%)
     W w U u V v X x     (acessorios: ignorados, salvo buzina configurada em config.py)
2) Texto em minúsculas, terminado por Enter (apps de terminal serial, botões/macros):
     frente | tras | esquerda | direita | pare | vel N (0..10) | status | ajuda
   (uma linha com UMA letra também vale, em maiúscula ou minúscula: "f", "S"...)

3) App **Blue Dot** (analógico; é o app Android do projeto Blue Dot, o mesmo usado com a biblioteca `bluedot` do Python).
   O protocolo (lido do código da biblioteca bluedot 2.0.0, protocolo versão 2) são linhas de texto terminadas em \n:
     "0,col,row,x,y"  soltou     "1,col,row,x,y"  apertou     "2,col,row,x,y"  moveu o dedo
     "3,versao,nome"  o app diz a versão do protocolo ao conectar
   x vai de -1 (esquerda) a +1 (direita) e y de -1 (baixo) a +1 (cima). Aqui só vale o botão (0,0). O analógico combina os dois eixos:
   cima/baixo controla o avanço e esquerda/direita faz curvas diferenciais; diagonais combinam os movimentos. A lateral pura curva para frente.

Segurança: o movimento só dura REMOTO_TIMEOUT_S sem novo comando (quem cuida disso é o controle); aqui só se interpreta.
"""
import math
import re
import time
import unicodedata
from dataclasses import dataclass

import config as cfg

DIRECOES = {"F": "frente", "B": "tras", "L": "esq", "R": "dir",
            "G": "frente_esq", "I": "frente_dir", "H": "tras_esq", "J": "tras_dir"}
IGNORADOS = set("WwUuVvXx")
IMEDIATOS = set(DIRECOES) | {"S", "D", "q", "Y"} | set("0123456789") | IGNORADOS
PALAVRAS = {"frente": ("mover", "frente"), "tras": ("mover", "tras"), "atras": ("mover", "tras"), "re": ("mover", "tras"),
            "esquerda": ("mover", "esq"), "direita": ("mover", "dir"),
            "pare": ("parar", None), "parar": ("parar", None), "para": ("parar", None), "stop": ("parar", None),
            "status": ("status", None), "ajuda": ("ajuda", None), "help": ("ajuda", None), "?": ("ajuda", None)}
PENDENTE_MAX_S = 0.3        # resto de texto sem Enter mais velho que isto é lixo e some
LINHA_MAX = 40
LINHA_BLUEDOT = re.compile(r"^[0-4],")
LINHA_ELETROGATE = re.compile(r"^F(\d{1,3})T(\d{1,3})D(\d{1,3})E(\d{1,3})$")
PREFIXO_ELETROGATE = re.compile(r"^[FTDE]\d")
CONFIG_BLUEDOT = "4,#0000ffff,0,0,1,1,1"   # mensagem de configuração do Blue Dot: cor, quadrado, borda, visível, colunas, linhas

AJUDA = ("Comandos: F frente, B tras, L esquerda, R direita, G/I/H/J diagonais, S parar, 0-9 e q velocidade. "
         "Texto (com Enter): frente, tras, esquerda, direita, pare, vel N, status, buzina, buzina off.")


@dataclass(frozen=True)
class Comando:
    tipo: str                 # "mover" | "parar" | "velocidade" | "status" | "ajuda" | "ignorar" | "desconhecido"
                              # | "dot_toque" (valor = (x, y), apertou ou moveu) | "dot_soltar" | "dot_protocolo" (valor = (versao, nome))
    valor: object = None      # direção (str), nível (int) ou texto
    de_linha: bool = False    # veio de uma linha com Enter (aí vale responder ao celular)


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def _char(c: str, de_linha: bool) -> Comando:
    if c == cfg.REMOTO_BUZINA_PULSO and c not in DIRECOES and c not in {"S", "D", "q"} and not c.isdigit():
        return Comando("buzina_pulso", True, de_linha)
    ligar, desligar = cfg.REMOTO_BUZINA_LIGAR, cfg.REMOTO_BUZINA_DESLIGAR
    if c in IGNORADOS and ligar != desligar:
        if c == ligar:
            return Comando("buzina", True, de_linha)
        if c == desligar:
            return Comando("buzina", False, de_linha)
    if c in DIRECOES:
        return Comando("mover", DIRECOES[c], de_linha)
    if c in ("S", "D"):
        return Comando("parar", None, de_linha)
    if c == "q":
        return Comando("velocidade", 10, de_linha)
    if c.isdigit():
        return Comando("velocidade", int(c), de_linha)
    return Comando("ignorar", c, de_linha)


def _bluedot(texto: str) -> Comando:
    """Linha do app Blue Dot. Mensagem corrompida vira "ignorar" (a biblioteca original também só avisa)."""
    p = texto.strip().split(",", 2)
    try:
        op = int(p[0])
        if op == 3:
            return Comando("dot_protocolo", (int(p[1]), p[2] if len(p) > 2 else ""), True)
        if op in (0, 1, 2):
            c = texto.strip().split(",")
            col, lin, x, y = int(c[1]), int(c[2]), float(c[3]), float(c[4])
            if (col, lin) != (0, 0) or not (math.isfinite(x) and math.isfinite(y)):
                return Comando("ignorar", texto.strip()[:LINHA_MAX], True)
            x, y = max(-1.0, min(1.0, x)), max(-1.0, min(1.0, y))
            return Comando("dot_soltar" if op == 0 else "dot_toque", (x, y), True)
    except (ValueError, IndexError):
        pass
    return Comando("ignorar", texto.strip()[:LINHA_MAX], True)


def _linha(texto: str) -> Comando:
    m = LINHA_ELETROGATE.fullmatch(texto.strip())
    if m:
        valores = tuple(int(v) for v in m.groups())
        if all(0 <= v <= 255 for v in valores):
            return Comando("eletrogate", valores, True)
        return Comando("ignorar", texto.strip()[:LINHA_MAX], True)
    if LINHA_BLUEDOT.match(texto.strip()):
        return _bluedot(texto)
    t = _sem_acento(texto.strip()).lower()
    if t in {"buzina", "buzina on", "buzina off"}:
        return Comando("buzina", t != "buzina off", True)
    if len(texto.strip()) == 1:                              # "f", "S"... com Enter: vale em qualquer caixa
        c = texto.strip()
        c = c if c in IMEDIATOS else c.upper()
        if c in IMEDIATOS:
            return _char(c, True)
    partes = t.split()
    if len(partes) == 2 and partes[0] in ("vel", "velocidade") and partes[1].isdigit() and 0 <= int(partes[1]) <= 10:
        return Comando("velocidade", int(partes[1]), True)
    if len(partes) == 1 and partes[0] in PALAVRAS:
        tipo, valor = PALAVRAS[partes[0]]
        return Comando(tipo, valor, True)
    return Comando("desconhecido", texto.strip()[:LINHA_MAX], True)


class InterpretadorRemoto:
    """Transforma o fluxo de bytes do celular em comandos. Guarda só um resto de linha incompleta."""

    def __init__(self, relogio=time.monotonic):
        self._relogio = relogio
        self._resto = ""
        self._t_resto = 0.0
        self.bluedot = False       # vira True ao ver a 1ª linha do Blue Dot: daí em diante dígitos soltos NÃO são velocidade
        self.eletrogate = False    # detectado pelo pacote estruturado F...T...D...E...

    def alimentar(self, dados: bytes) -> list[Comando]:
        agora = self._relogio()
        if self._resto and agora - self._t_resto > PENDENTE_MAX_S:
            self._resto = ""                                  # lixo velho sem Enter nunca trava os próximos comandos
        self._resto += dados.decode("utf-8", errors="ignore")
        saida: list[Comando] = []
        while True:
            i = next((k for k, c in enumerate(self._resto) if c in "\r\n"), -1)
            if i < 0:
                break
            linha, self._resto = self._resto[:i], self._resto[i + 1:]
            if linha.strip():
                limpa = linha.strip()
                if self.eletrogate and limpa in {"F", "T", "D", "E"}:
                    c = Comando("eletrogate_direcao", limpa, True)
                else:
                    c = _linha(linha)
                self.eletrogate = self.eletrogate or c.tipo == "eletrogate"
                self.bluedot = self.bluedot or c.tipo.startswith("dot_")
                saida.append(c)
        if self._resto and (self.bluedot or "," in self._resto or LINHA_BLUEDOT.match(self._resto)
                            or PREFIXO_ELETROGATE.match(self._resto)):
            self._t_resto = agora                              # pedaço de linha do Blue Dot: espera o resto, nunca vira "botão"
            if len(self._resto) > 80:
                self._resto = ""
        elif self._resto:
            j = len(self._resto)                              # maior final composto só de comandos de um caractere
            while j > 0 and self._resto[j - 1] in IMEDIATOS:
                j -= 1
            for c in self._resto[j:]:
                saida.append(_char(c, False))
            self._resto = self._resto[:j]
            if self._resto:
                self._t_resto = agora
                if len(self._resto) > LINHA_MAX:
                    self._resto = ""
                    saida.append(Comando("desconhecido", "linha longa demais", True))
        return saida


def calcular_pwm(direcao: str, nivel: int) -> tuple[int, int]:
    """(PWM esquerdo, PWM direito) para uma direção e um nível de velocidade 0..10."""
    nivel = max(0, min(10, int(nivel)))
    teto = min(cfg.VEL_MAX, cfg.REMOTO_VEL_MAX)
    v = round(teto * nivel / 10)
    c = round(v * cfg.REMOTO_CURVA_FATOR)
    return {"frente": (v, v), "tras": (-v, -v), "esq": (c, v), "dir": (v, c),
            "frente_esq": (c, v), "frente_dir": (v, c), "tras_esq": (-c, -v), "tras_dir": (-v, -c)}[direcao]


def _misturar_joystick(x: float, y: float) -> tuple[int, int]:
    """Eixos x direita+ e y frente+, com curvas diferenciais e suporte a diagonais."""
    x = max(-1.0, min(1.0, float(x)))
    y = max(-1.0, min(1.0, float(y)))
    r = math.hypot(x, y)
    zona = max(0.0, min(0.9, cfg.REMOTO_BLUEDOT_ZONA_MORTA))
    if r <= zona:
        return 0, 0
    escala = min(1.0, (r - zona) / (1.0 - zona)) / r
    lateral, frente = x * escala, y * escala
    # A curva lateral muda a geometria, nao a intensidade radial do operador.
    velocidade = math.hypot(lateral, frente)
    if abs(frente) < 1e-9:                                 # só lateral: avança em curva, sem girar parado
        frente = abs(lateral)
        intensidade_curva = 1.0
    else:
        intensidade_curva = abs(lateral) / (abs(lateral) + abs(frente))
    intensidade_curva = max(0.0, min(1.0, intensidade_curva))
    fator_dentro = max(0.0, min(1.0, cfg.REMOTO_CURVA_FATOR))
    dentro = 1.0 - intensidade_curva * (1.0 - fator_dentro)
    sinal = -1.0 if frente < 0 else 1.0
    if lateral < 0:                                         # curva à esquerda: roda esquerda é a interna
        esq, dir_ = sinal * velocidade * dentro, sinal * velocidade
    elif lateral > 0:                                       # curva à direita: roda direita é a interna
        esq, dir_ = sinal * velocidade, sinal * velocidade * dentro
    else:
        esq = dir_ = sinal * velocidade
    teto = min(cfg.VEL_MAX, cfg.REMOTO_VEL_MAX)
    return round(teto * esq), round(teto * dir_)


def calcular_pwm_analogico(x: float, y: float) -> tuple[int, int]:
    """Analógico (x direita+, y cima+, ambos -1..1) -> PWM diferencial.
    O centro é parado; esquerda/direita fazem curvas para frente e as diagonais combinam avanço e direção."""
    return _misturar_joystick(x, y)


def calcular_pwm_eletrogate(f: int, t: int, d: int, e: int) -> tuple[int, int]:
    """Traduz as quatro intensidades documentadas pelo app (Frente, Trás, Direita, Esquerda).

    Cada par oposto é reduzido a um eixo assinado e os eixos são misturados como no joystick analógico.
    Movimento só lateral vira curva para frente; diagonais combinam avanço e direção.
    """
    vals = tuple(max(0, min(255, int(v))) for v in (f, t, d, e))
    frente, tras, direita, esquerda = vals
    y = (frente - tras) / 255.0
    x = (direita - esquerda) / 255.0
    return _misturar_joystick(x, y)
