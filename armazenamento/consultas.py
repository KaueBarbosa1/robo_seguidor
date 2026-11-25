"""Fachada local de leitura, filtros parametrizados e paginação. Sem SQL arbitrário."""
import json
import math
import statistics
from pathlib import Path
import uuid

from armazenamento.banco import conectar, tamanho_banco
from armazenamento.normalizacao import utc

CATEGORIAS = {'sessoes','gravacoes','telemetria','motores','sensores','visao_computacional',
              'inteligencia_artificial','desempenho','comunicacao','eventos','imagens',
              'experimentos','odometria','intervalos','consolidado','dataset'}
FILHAS = {'motores','sensores','visao_computacional','inteligencia_artificial'}
CONSOLIDADO = '''SELECT t.id,t.sessao_id,t.sequencia,t.recebido_utc,t.origem_utc,t.simulado,
 t.estado_operacional,m.pwm_informado_esq,m.pwm_informado_dir,m.pps_esq,m.pps_dir,
 m.ticks_esq,m.ticks_dir,s.distancia_cm,s.distancia_estado,s.servo_comandado_graus,
 s.obstaculo_confirmado,v.frame_id,v.erro_normalizado,v.linha_detectada,v.confianca_heuristica,
 ia.politica,ia.inferencia_s,ia.previsao,t.qualidade_json AS dominios_json,
 m.qualidade_json AS motores_qualidade_json,s.qualidade_json AS sensores_qualidade_json,
 v.qualidade_json AS visao_qualidade_json,ia.qualidade_json AS ia_qualidade_json,
 (SELECT p.cpu_pct FROM desempenho p WHERE p.sessao_id=t.sessao_id AND p.dispositivo='servidor'
  AND (p.amostra_mono_s<=t.origem_mono_s OR p.telemetria_id=t.id) ORDER BY p.id DESC LIMIT 1) AS cpu_servidor_pct,
 (SELECT p.temperatura_c FROM desempenho p WHERE p.sessao_id=t.sessao_id AND p.dispositivo='servidor'
  AND (p.amostra_mono_s<=t.origem_mono_s OR p.telemetria_id=t.id) ORDER BY p.id DESC LIMIT 1) AS temperatura_servidor_c,
 (SELECT cm.rtt_s FROM comunicacao cm WHERE cm.telemetria_id=t.id AND cm.lado='servidor' LIMIT 1) AS rtt_servidor_s
 FROM telemetria t LEFT JOIN motores m ON m.telemetria_id=t.id
 LEFT JOIN sensores s ON s.telemetria_id=t.id LEFT JOIN visao_computacional v ON v.telemetria_id=t.id
 LEFT JOIN inteligencia_artificial ia ON ia.telemetria_id=t.id'''


class Historico:
    def __init__(self,raiz):
        self.raiz = Path(raiz).resolve()

    def _query(self,categoria,filtros):
        if categoria not in CATEGORIAS:
            raise ValueError('Categoria nao permitida')
        permitidos = {'sessao','gravacao','experimento','inicio','fim','modo','simulado','dispositivo','lado'}
        if set(filtros)-permitidos:
            raise ValueError('Filtro desconhecido')
        for k in ('sessao','gravacao','experimento'):
            if filtros.get(k) is not None:
                uuid.UUID(filtros[k])
        cond,params = [],[]
        sid,gid,instante = 'x.sessao_id','x.gravacao_id','x.timestamp_utc'
        if categoria == 'sessoes':
            base = 'SELECT x.* FROM sessoes x'
            sid,instante = 'x.id','x.inicio_observado_utc'
            gid = None
        elif categoria == 'gravacoes':
            base = 'SELECT x.* FROM gravacoes x'
            sid,gid,instante = None,'x.id','x.inicio_utc'
        elif categoria == 'experimentos':
            base = 'SELECT x.* FROM experimentos x'
            sid,gid,instante = None,None,'x.data_utc'
        elif categoria in FILHAS:
            base = f'SELECT x.*,t.sessao_id,t.sequencia,t.recebido_utc,t.simulado FROM {categoria} x JOIN telemetria t ON t.id=x.telemetria_id'
            sid,gid,instante = 't.sessao_id',None,'t.recebido_utc'
        elif categoria == 'telemetria':
            base = 'SELECT x.* FROM telemetria x'
            gid,instante = None,'x.recebido_utc'
        elif categoria == 'consolidado':
            base = CONSOLIDADO
            sid,gid,instante = 't.sessao_id',None,'t.recebido_utc'
        elif categoria == 'dataset':
            base = '''SELECT x.*,v.erro_normalizado,v.linha_detectada,m.pwm_informado_esq,m.pwm_informado_dir,
             m.pps_esq,m.pps_dir,v.qualidade_json AS visao_qualidade_json,
             m.qualidade_json AS motores_qualidade_json,'nao_validado' AS estado_rotulo_treino FROM imagens x
             LEFT JOIN visao_computacional v ON v.telemetria_id=x.telemetria_id
             LEFT JOIN motores m ON m.telemetria_id=x.telemetria_id'''
            gid,instante = None,'x.recebido_utc'
        else:
            base = f'SELECT x.* FROM {categoria} x'
            if categoria == 'imagens':
                gid,instante = None,'x.recebido_utc'
            elif categoria == 'intervalos':
                instante = 'x.inicio_utc'
            elif categoria == 'odometria':
                gid = None
        if filtros.get('sessao') is not None:
            if sid is None:
                if categoria == 'gravacoes':
                    cond.append('EXISTS(SELECT 1 FROM gravacao_sessoes gs WHERE gs.gravacao_id=x.id AND gs.sessao_id=?)')
                elif categoria == 'experimentos':
                    cond.append('EXISTS(SELECT 1 FROM gravacoes g JOIN gravacao_sessoes gs ON gs.gravacao_id=g.id WHERE g.experimento_id=x.id AND gs.sessao_id=?)')
                else:
                    raise ValueError('Filtro sessao nao se aplica a categoria')
            else:
                cond.append(sid+'=?')
            params.append(filtros['sessao'])
        if filtros.get('gravacao') is not None:
            if gid:
                cond.append(gid+'=?')
            elif categoria in FILHAS or categoria in {'consolidado','telemetria'}:
                tid = 'x.id' if categoria == 'telemetria' else 't.id'
                cond.append(f'EXISTS(SELECT 1 FROM telemetria_gravacoes tg WHERE tg.telemetria_id={tid} AND tg.gravacao_id=?)')
            elif categoria in {'imagens','dataset'}:
                cond.append('EXISTS(SELECT 1 FROM imagens_gravacoes ig WHERE ig.imagem_id=x.id AND ig.gravacao_id=?)')
            elif sid:
                cond.append(f'EXISTS(SELECT 1 FROM gravacao_sessoes gs WHERE gs.sessao_id={sid} AND gs.gravacao_id=?)')
            elif categoria == 'experimentos':
                cond.append('EXISTS(SELECT 1 FROM gravacoes g WHERE g.experimento_id=x.id AND g.id=?)')
            else:
                raise ValueError('Filtro gravacao nao se aplica')
            params.append(filtros['gravacao'])
        if filtros.get('experimento') is not None:
            if categoria == 'experimentos':
                cond.append('x.id=?')
            elif categoria == 'gravacoes':
                cond.append('x.experimento_id=?')
            elif sid:
                cond.append(f'EXISTS(SELECT 1 FROM gravacao_sessoes gs JOIN gravacoes g ON g.id=gs.gravacao_id '
                            f'WHERE gs.sessao_id={sid} AND g.experimento_id=?)')
            else:
                raise ValueError('Filtro experimento nao se aplica')
            params.append(filtros['experimento'])
        for k,operador in [('inicio','>='),('fim','<=')]:
            if filtros.get(k):
                cond.append(instante+operador+'?'); params.append(utc(filtros[k]))
        if filtros.get('inicio') and filtros.get('fim') and utc(filtros['inicio']) > utc(filtros['fim']):
            raise ValueError('Intervalo invertido')
        for k,coluna in [('modo','modo_processamento'),('simulado','simulado')]:
            if filtros.get(k) is not None:
                if sid:
                    cond.append(f'EXISTS(SELECT 1 FROM sessoes filtro WHERE filtro.id={sid} AND filtro.{coluna}=?)')
                elif categoria == 'gravacoes':
                    cond.append(f'EXISTS(SELECT 1 FROM gravacao_sessoes gs JOIN sessoes filtro ON filtro.id=gs.sessao_id '
                                f'WHERE gs.gravacao_id=x.id AND filtro.{coluna}=?)')
                elif categoria == 'experimentos':
                    cond.append(f'EXISTS(SELECT 1 FROM gravacoes g JOIN gravacao_sessoes gs ON gs.gravacao_id=g.id '
                                f'JOIN sessoes filtro ON filtro.id=gs.sessao_id WHERE g.experimento_id=x.id AND filtro.{coluna}=?)')
                else:
                    raise ValueError('Filtro de dominio/modo nao aplicavel')
                if k == 'simulado' and type(filtros[k]) is not bool:
                    raise ValueError('Simulado deve ser bool')
                params.append(filtros[k])
        for k in ('dispositivo','lado'):
            if filtros.get(k) is not None:
                if (k == 'dispositivo' and categoria != 'desempenho') or (k == 'lado' and categoria != 'comunicacao'):
                    raise ValueError('Filtro de origem nao aplicavel')
                cond.append('x.'+k+'=?'); params.append(filtros[k])
        sql = base+(' WHERE '+' AND '.join(cond) if cond else '')
        return sql,params,instante

    def consultar(self,categoria,limite=100,pagina=0,**filtros):
        if type(limite) is not int or not 1 <= limite <= 1000 or type(pagina) is not int or not 0 <= pagina <= 100000:
            raise ValueError('Paginacao invalida')
        sql,p,ordem = self._query(categoria,filtros)
        c = conectar(self.raiz)
        try:
            return [dict(r) for r in c.execute(sql+' ORDER BY '+ordem+' LIMIT ? OFFSET ?',(*p,limite,pagina*limite))]
        finally:
            c.close()

    def iterar(self,categoria,**filtros):
        sql,p,ordem = self._query(categoria,filtros)
        c = conectar(self.raiz)
        try:
            cursor = c.execute(sql+' ORDER BY '+ordem,p)
            while True:
                lote = cursor.fetchmany(256)
                if not lote:
                    break
                for row in lote:
                    yield dict(row)
        finally:
            c.close()

    def colunas(self,categoria,**filtros):
        sql,p,_=self._query(categoria,filtros)
        c=conectar(self.raiz)
        try:
            return [col[0] for col in c.execute(sql+' LIMIT 0',p).description]
        finally:
            c.close()

    def estatistica(self,categoria,coluna,**filtros):
        if filtros.get('simulado') is None:
            return {k:self.estatistica(categoria,coluna,**dict(filtros,simulado=v))
                    for k,v in [('real',False),('simulado',True)]}
        colunas = dict(motores={'pps_esq','pps_dir','pwm_informado_esq','pwm_informado_dir'},
            sensores={'distancia_cm','servo_comandado_graus'},visao_computacional={'erro_normalizado'},
            desempenho={'cpu_pct','ram_pct','temperatura_c','rss_bytes','controle_hz','jitter_s'},
            comunicacao={'rtt_s','jitter_s','fps'},inteligencia_artificial={'inferencia_s','previsao'})
        if coluna not in colunas.get(categoria,set()):
            raise ValueError('Metrica estatistica nao permitida')
        sql,p,_ = self._query(categoria,filtros)
        c = conectar(self.raiz)
        try:
            where = f' FROM ({sql}) q WHERE q.{coluna} IS NOT NULL'
            # Qualidade original é preservada; excluir explicitamente campos vencidos.
            chave = {'servo_comandado_graus':'angulo_servo_graus','pwm_informado_esq':'pwm_esq',
                     'pwm_informado_dir':'pwm_dir','erro_normalizado':'erro'}.get(coluna,coluna)
            if categoria in FILHAS or categoria == 'sensores':
                where += f" AND COALESCE(json_extract(q.qualidade_json,'$.{chave}.estado'),'atual')='atual'"
            valores = c.execute(f'SELECT COUNT({coluna}),AVG({coluna}),MIN({coluna}),MAX({coluna})'+where,p).fetchone()
            n = valores[0]
            def percentil(fracao):
                if not n:
                    return None
                pos = (n-1)*fracao
                v = [r[0] for r in c.execute(f'SELECT {coluna}'+where+f' ORDER BY {coluna} LIMIT 2 OFFSET ?',(*p,int(pos)))]
                return v[0]+(v[-1]-v[0])*(pos-int(pos))
            media = 0.; m2 = 0.; total = 0
            for row in c.execute(f'SELECT {coluna}'+where,p):
                total += 1; delta = row[0]-media; media += delta/total; m2 += delta*(row[0]-media)
            return dict(n=n,media=valores[1],minimo=valores[2],maximo=valores[3],mediana=percentil(.5),
                        p95=percentil(.95),desvio_padrao=math.sqrt(max(0,m2/total)) if total else None,
                        filtros=filtros,escopo='desvio populacional; exclui NULL e campos marcados vencidos')
        finally:
            c.close()

    def resumo(self,**filtros):
        if filtros.get('simulado') is None:
            return {k:self.resumo(**dict(filtros,simulado=v)) for k,v in [('real',False),('simulado',True)]}
        sql,p,_ = self._query('telemetria',filtros)
        c = conectar(self.raiz)
        try:
            row = c.execute('SELECT COUNT(*),MIN(origem_mono_s),MAX(origem_mono_s),COUNT(DISTINCT sessao_id) FROM ('+sql+')',p).fetchone()
            from collections import Counter
            contagens=Counter();falhas=0
            for e in self.iterar('eventos',**filtros):
                contagens[e['categoria']]+=1
                if e['categoria']=='desconexao' or (e['gravidade']=='alerta' and e['categoria'].startswith('falha')):
                    falhas+=1
            recebidas=descartadas=0;gravacoes_contabilizadas=0
            # Contadores de uma gravação com domínios mistos não são atribuídos artificialmente a um domínio.
            gf={k:v for k,v in filtros.items() if k not in ('dispositivo','lado')}
            for g in ([] if filtros.get('inicio') or filtros.get('fim') else self.iterar('gravacoes',**gf)):
                dominios,n_sessoes=c.execute('SELECT COUNT(DISTINCT s.simulado),COUNT(DISTINCT s.id) FROM sessoes s JOIN gravacao_sessoes gs '
                                   'ON gs.sessao_id=s.id WHERE gs.gravacao_id=?',(g['id'],)).fetchone()
                if dominios==1 and g['fim_utc'] and (not filtros.get('sessao') or n_sessoes==1):
                    st=json.loads(g['estatisticas_json'])
                    ct=st.get('contadores_gravacao') or {}
                    filas=sum((st.get('descartes_filas_gravacao') or {}).values())
                    recebidas+=ct.get('recebidas',0)+filas
                    descartadas+=ct.get('descartadas',0)+filas
                    gravacoes_contabilizadas+=1
            duracao=row[2]-row[1] if row[3]==1 and row[1] is not None else None
            return dict(amostras=row[0],duracao_observada_s=row[2]-row[1] if row[3] == 1 and row[1] is not None else None,
                sessoes=row[3],eventos=dict(contagens),obstaculos=contagens['obstaculo_detectado'],
                falhas_observadas=falhas,frequencia_falhas_h=falhas*3600/duracao if duracao and duracao>0 else None,
                taxa_descarte_gravacoes_fechadas=descartadas/recebidas if recebidas else None,
                gravacoes_contabilizadas=gravacoes_contabilizadas,
                nota='Obstaculos contados por transicoes, nao leituras; duracao inclui lacunas observadas da mesma sessao')
        finally:
            c.close()

    def estado(self):
        c = conectar(self.raiz)
        try:
            return dict(versao=c.execute('PRAGMA user_version').fetchone()[0],
                journal=c.execute('PRAGMA journal_mode').fetchone()[0],banco_bytes=tamanho_banco(self.raiz),
                gravacoes=[dict(r) for r in c.execute("SELECT id,estado,nome FROM gravacoes ORDER BY inicio_utc DESC LIMIT 100")])
        finally:
            c.close()

    def integridade(self):
        from armazenamento.imagens import seguro,hash_arquivo
        import hashlib
        c = conectar(self.raiz)
        try:
            problemas = []
            total = total_problemas = 0
            for row in c.execute('SELECT id,caminho,sha256 FROM imagens'):
                total += 1
                p = seguro(self.raiz,row['caminho'])
                if not p.is_file():
                    total_problemas+=1
                    if len(problemas)<1000:problemas.append(dict(id=row['id'],erro='imagem_ausente'))
                elif hash_arquivo(p) != row['sha256']:
                    total_problemas+=1
                    if len(problemas)<1000:problemas.append(dict(id=row['id'],erro='hash_divergente'))
            from itertools import islice
            orfas=[]; n_orfas=0
            for p in (self.raiz/'imagens').rglob('*.jpg'):
                if not c.execute('SELECT 1 FROM imagens WHERE caminho=?',(p.relative_to(self.raiz).as_posix(),)).fetchone():
                    n_orfas+=1
                    if len(orfas)<1000:orfas.append(p.relative_to(self.raiz).as_posix())
            return dict(sqlite=[r[0] for r in c.execute('PRAGMA integrity_check')],
                chaves_estrangeiras=[tuple(r) for r in c.execute('PRAGMA foreign_key_check')],
                imagens_verificadas=total,problemas_imagens=problemas[:1000],
                total_problemas_imagens=total_problemas,arquivos_orfaos=orfas,total_orfaos=n_orfas,
                temporarios=[str(p.relative_to(self.raiz)) for p in islice(self.raiz.rglob('*.part'),1000)])
        finally:
            c.close()
