"""Backup SQLite online, com conjunto imutável de imagens referenciadas no snapshot."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import uuid

from armazenamento.banco import conectar,caminho_banco
from armazenamento.imagens import seguro,hash_arquivo
from armazenamento.normalizacao import utc


def criar(raiz,destino=None,imagens=True):
    raiz = Path(raiz).resolve()
    pasta = Path(destino).resolve() if destino else raiz/'backups'/str(uuid.uuid4())
    pasta.mkdir(parents=True,exist_ok=False)
    saida = pasta/'banco'/'robo_seguidor.db'
    saida.parent.mkdir()
    origem = conectar(raiz)
    alvo = sqlite3.connect(saida)
    try:
        origem.backup(alvo,pages=256,sleep=.01)
        integridade = alvo.execute('PRAGMA integrity_check').fetchone()[0]
        if integridade != 'ok':
            raise RuntimeError('Backup SQLite sem integridade')
        faltantes = []
        copiadas = 0
        for caminho,hash_ in alvo.execute('SELECT caminho,sha256 FROM imagens'):
            if not imagens:
                continue
            fonte = seguro(raiz,caminho)
            if not fonte.is_file() or hash_arquivo(fonte) != hash_:
                if len(faltantes) < 1000:
                    faltantes.append(caminho)
                continue
            destino_img = seguro(pasta,caminho)
            destino_img.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(fonte,destino_img)
            copiadas += 1
    finally:
        origem.close(); alvo.close()
    manifesto = dict(schema='backup_robo_v1',timestamp_utc=utc(),sqlite='banco/robo_seguidor.db',
        sha256=hash_arquivo(saida),integridade=integridade,
        imagens_incluidas=imagens,imagens_copiadas=copiadas,imagens_ausentes_ou_divergentes=faltantes)
    (pasta/'manifesto.json').write_text(json.dumps(manifesto,ensure_ascii=False,indent=2),encoding='utf-8')
    return pasta


def restaurar(backup,destino,confirmar=False):
    if not confirmar:
        raise ValueError('Restauracao exige confirmar=True/--confirmar')
    backup,destino = Path(backup).resolve(),Path(destino).resolve()
    m = json.loads((backup/'manifesto.json').read_text(encoding='utf-8'))
    banco = seguro(backup,m['sqlite'])
    if m.get('schema') != 'backup_robo_v1' or hash_arquivo(banco) != m['sha256']:
        raise ValueError('Backup invalido/divergente')
    if destino.exists():
        raise ValueError('Destino deve ser novo; banco existente nunca e sobrescrito')
    destino.mkdir(parents=True)
    alvo = caminho_banco(destino)
    alvo.parent.mkdir()
    shutil.copy2(banco,alvo)
    c = conectar(destino)
    try:
        if c.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Banco restaurado sem integridade')
        for row in c.execute('SELECT caminho,sha256 FROM imagens'):
            p = seguro(backup,row['caminho'])
            if p.is_file():
                if hash_arquivo(p) != row['sha256']:
                    raise ValueError('Imagem do backup divergente')
                q = seguro(destino,row['caminho'])
                q.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(p,q)
    finally:
        c.close()
    return destino
