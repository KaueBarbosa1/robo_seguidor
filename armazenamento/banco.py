from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3

from armazenamento.migracoes import migrar,VERSAO


def caminho_banco(raiz):
    return Path(raiz).resolve()/'banco'/'robo_seguidor.db'


def conectar(raiz, escrita=False):
    p = caminho_banco(raiz)
    if escrita:
        p.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(p, timeout=.25)
    else:
        c = sqlite3.connect(p.as_uri()+'?mode=ro', uri=True, timeout=.25)
    try:
        c.row_factory = sqlite3.Row
        if escrita:
            if c.execute('PRAGMA user_version').fetchone()[0]>VERSAO:
                raise ValueError('Banco mais novo que este software; nenhuma alteracao aplicada')
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('PRAGMA synchronous=FULL')
        c.execute('PRAGMA foreign_keys=ON')
        c.execute('PRAGMA busy_timeout=250')
        if escrita:
            migrar(c)
        return c
    except Exception:
        c.close()
        raise


class Exclusivo:
    """Lock de SO: libera com morte do processo; arquivo remanescente não é uma lease."""
    def __init__(self, raiz):
        self.caminho = Path(raiz).resolve()/'banco'/'writer.lock'
        self.arquivo = None

    def abrir(self):
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.arquivo = self.caminho.open('a+b')
        if self.caminho.stat().st_size == 0:
            self.arquivo.write(b'0')
            self.arquivo.flush()
        self.arquivo.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.arquivo.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.arquivo, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.arquivo.close()
            self.arquivo = None
            raise RuntimeError('Ja existe um gravador neste diretorio') from exc
        return self

    def fechar(self):
        if self.arquivo:
            self.arquivo.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.arquivo.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.arquivo, fcntl.LOCK_UN)
            self.arquivo.close()
            self.arquivo = None

    def __enter__(self):
        return self.abrir()

    def __exit__(self, *_):
        self.fechar()


def tamanho_banco(raiz):
    p = caminho_banco(raiz)
    return sum(q.stat().st_size for q in (p, Path(str(p)+'-wal'), Path(str(p)+'-shm')) if q.exists())
