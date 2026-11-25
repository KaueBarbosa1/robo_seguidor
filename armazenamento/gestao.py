import uuid
from armazenamento.banco import conectar,Exclusivo
from armazenamento.normalizacao import inserir,js,utc


def experimento(c,nome,objetivo=None,modo=None,algoritmo=None,condicoes=None,repeticao=None,configuracoes=None,observacoes=None):
    if not isinstance(nome,str) or not 1 <= len(nome) <= 256:
        raise ValueError('Nome invalido')
    if repeticao is not None and (type(repeticao) is not int or repeticao < 1):
        raise ValueError('Repeticao invalida')
    ident = str(uuid.uuid4())
    inserir(c,'experimentos',dict(id=ident,nome=nome,objetivo=objetivo,data_utc=utc(),modo_processamento=modo,
        algoritmo=algoritmo,condicoes_pista=condicoes,repeticao=repeticao,
        configuracoes_json=js(configuracoes or {}),observacoes=observacoes))
    return ident


def criar_experimento(raiz,**dados):
    with Exclusivo(raiz):
        c = conectar(raiz,True)
        try:
            ident = experimento(c,**dados)
            c.commit()
            return ident
        finally:
            c.close()


def anotar(raiz,gravacao,nome=None,observacoes=None,experimento_id=None):
    uuid.UUID(gravacao)
    with Exclusivo(raiz):
        c = conectar(raiz,True)
        try:
            if not c.execute('SELECT 1 FROM gravacoes WHERE id=?',(gravacao,)).fetchone():
                raise ValueError('Gravacao nao encontrada')
            for coluna,v in [('nome',nome),('observacoes',observacoes),('experimento_id',experimento_id)]:
                if v is not None:
                    c.execute(f'UPDATE gravacoes SET {coluna}=? WHERE id=?',(v,gravacao))
            c.commit()
        finally:
            c.close()
