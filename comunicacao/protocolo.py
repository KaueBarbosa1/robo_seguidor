"""JSON estrito; JPEG binário = uint32 tamanho JSON + cabeçalho UTF-8 + JPEG original."""
from datetime import datetime, timezone
import json
import math
import struct
import time
import uuid

VERSAO = 1
TIPOS = {'ola', 'telemetria', 'imagem', 'sonda', 'eco', 'erro', 'inferencia', 'referencia', 'comando'}


def envelope(sessao, sequencia, tipo, dados, simulado=False, origem='raspberry',
             idade=0., validade=.5):
    return dict(versao=VERSAO, sessao=sessao, sequencia=sequencia, tipo=tipo,
                origem=origem, simulado=simulado,
                timestamp=datetime.now(timezone.utc).isoformat(), monotonic_s=time.monotonic(),
                idade_envio_s=idade, validade_s=validade, dados=dados)


def codificar(msg):
    return json.dumps(msg, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def _objeto(pares):
    d = {}
    for k, v in pares:
        if k in d:
            raise ValueError('Campo JSON duplicado')
        d[k] = v
    return d


def _real(texto):
    valor = float(texto)
    if not math.isfinite(valor):
        raise ValueError('Numero fora da faixa finita')
    return valor


def decodificar(texto, limite=65536):
    if not isinstance(texto, str) or len(texto.encode('utf-8')) > limite:
        raise ValueError('JSON invalido ou grande demais')
    try:
        d = json.loads(texto, object_pairs_hook=_objeto, parse_float=_real,
                       parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Numero nao finito')))
        if not isinstance(d, dict) or d['versao'] != VERSAO or type(d['versao']) is not int:
            raise ValueError('Versao invalida')
        uuid.UUID(d['sessao'])
        if type(d['sequencia']) is not int or not 0 <= d['sequencia'] <= 2**63-1:
            raise ValueError('Sequencia invalida')
        if d['tipo'] not in TIPOS or type(d['simulado']) is not bool:
            raise ValueError('Tipo/dominio invalido')
        if d['origem'] not in {'raspberry', 'simulador', 'computador'} or not isinstance(d['dados'], dict):
            raise ValueError('Origem/payload invalidos')
        if datetime.fromisoformat(d['timestamp']).tzinfo is None:
            raise ValueError('Timestamp sem fuso')
        for k in ('monotonic_s', 'idade_envio_s', 'validade_s'):
            v = d[k]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
                raise ValueError('Prazo invalido')
        if not 0 < d['validade_s'] <= 60:
            raise ValueError('Validade invalida')
        return d
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError, json.JSONDecodeError) as exc:
        raise ValueError('Formato de mensagem invalido') from exc


def empacotar_imagem(meta, jpeg, max_json, max_jpeg):
    cab = codificar(meta).encode('utf-8')
    if len(cab) > max_json or len(jpeg) > max_jpeg or not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):
        raise ValueError('Imagem/cabecalho invalido')
    return struct.pack('!I', len(cab))+cab+jpeg


def desempacotar_imagem(pacote, max_json, max_jpeg):
    if not isinstance(pacote, bytes) or len(pacote) < 8 or len(pacote) > max_json+max_jpeg+4:
        raise ValueError('Pacote binario invalido')
    n = struct.unpack('!I', pacote[:4])[0]
    if not 0 < n <= max_json or n+4 >= len(pacote):
        raise ValueError('Comprimento invalido')
    try:
        cab = decodificar(pacote[4:4+n].decode('utf-8'), max_json)
    except UnicodeError as exc:
        raise ValueError('Cabecalho nao UTF-8') from exc
    jpeg = pacote[4+n:]
    if cab['tipo'] != 'imagem' or len(jpeg) > max_jpeg or not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):
        raise ValueError('JPEG invalido')
    return cab, jpeg


class Sequencia:
    """Uma instância por conexão/canal. Gaps não são chamados de perda de pacotes TCP."""
    def __init__(self):
        self.sessao = None
        self.ultimo = None
        self.lacunas = self.duplicadas = self.antigas = 0

    def aceitar(self, msg):
        if self.sessao is None:
            self.sessao = msg['sessao']
        if self.sessao != msg['sessao']:
            self.antigas += 1
            return False
        n = msg['sequencia']
        if self.ultimo is not None and n <= self.ultimo:
            self.duplicadas += 1
            return False
        if self.ultimo is not None:
            self.lacunas += n-self.ultimo-1
        self.ultimo = n
        return True
