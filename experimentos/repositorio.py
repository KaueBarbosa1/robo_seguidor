"""Consulta das execuções na mesma base SQLite; escrita pelo Gravador."""
from contextlib import closing
import json
import uuid
from armazenamento.banco import conectar


def listar(raiz, experimento=None, origem=None, nivel=None, categoria=None):
    where=[];args=[]
    for k,v in [('experimento_id',experimento),('origem',origem),('nivel',nivel),('categoria',categoria)]:
        if v is not None and v!='':where.append(k+'=?');args.append(v)
    with closing(conectar(raiz)) as c:
        rows=c.execute('SELECT * FROM execucoes_experimentais'+(' WHERE '+' AND '.join(where) if where else '')+' ORDER BY inicio_utc DESC LIMIT 400',args).fetchall()
    saida=[]
    for row in rows:
        d=dict(row)
        for k in ('configuracoes_json','ambiente_json','resultado_json'):d[k.removesuffix('_json')]=json.loads(d.pop(k))
        saida.append(d)
    return saida


def obter(raiz,ident):
    uuid.UUID(ident)
    with closing(conectar(raiz)) as c:row=c.execute('SELECT * FROM execucoes_experimentais WHERE id=?',(ident,)).fetchone()
    if not row:raise ValueError('Execução não encontrada')
    d=dict(row)
    for k in ('configuracoes_json','ambiente_json','resultado_json'):d[k.removesuffix('_json')]=json.loads(d.pop(k))
    return d


def comparar(rows,metrica):
    """Uma média por execução; nunca mensagens como repetições independentes."""
    from experimentos.analise import resumo,diferenca
    campos={'inferencia_s','processamento_s','ciclo_s','cpu_pc_pct','rss_bytes','controle_hz','rtt_s','consulta_s'}
    if metrica not in campos:raise ValueError('Métrica não comparável')
    dominios={(r['origem'],r['nivel'],r['categoria']) for r in rows}
    if len(dominios)>1:return dict(comparavel=False,motivo='Origem, nível ou categoria incompatíveis',itens=[])
    controles=('resolucao','camera_fps','imagens_fps','telemetria_hz','inferencia_hz','duracao_s','aquecimento_s','cenario','atraso_s','condicoes')
    grupos={};assinaturas=set();ambientes=set();modelos={}
    for r in rows:
        if r['estado']!='concluida':continue
        conf=r['configuracoes'];assinaturas.add(json.dumps({k:conf.get(k) for k in controles},sort_keys=True))
        ambiente=r.get('ambiente',{})
        ambientes.add(json.dumps({k:ambiente.get(k) for k in ('cpu','nucleos','sistema','commit','python','dependencias','hashes')},sort_keys=True))
        algoritmo=conf.get('configuracao_efetiva',{}).get('algoritmo',r['configuracao'])
        versao=r['resultado'].get('versao_modelo')
        if versao:modelos.setdefault(algoritmo,set()).add(versao)
        v=r['resultado'].get('metricas',{}).get(metrica,{}).get('media')
        if v is not None:grupos.setdefault(r['configuracao'],[]).append(v)
    if len(assinaturas)>1:return dict(comparavel=False,motivo='Condições controladas diferentes; selecione um experimento homogêneo',itens=[])
    if len(ambientes)>1 or any(len(v)>1 for v in modelos.values()):
        return dict(comparavel=False,motivo='Hardware/software ou versão do mesmo algoritmo diferem; registre um desenho específico para essa comparação',itens=[])
    itens=[dict(configuracao=k,**resumo(v)) for k,v in sorted(grupos.items())]
    dominio=next(iter(dominios),('indisponível',None,None))
    return dict(comparavel=len(itens)>1,itens=itens,metrica=metrica,origem=dominio[0],nivel=dominio[1],categoria=dominio[2],
                unidade_experimental='Uma média por execução independente; amostras internas não são repetições',
                motivo=None if len(itens)>1 else 'Dados insuficientes para comparar duas configurações',
                diferenca_extremos=diferenca(itens[0]['media'],itens[-1]['media']) if len(itens)>1 else None,
                conclusao='Descritivo do PC/simulador. Sem conclusão sobre superioridade física ou significância.')
