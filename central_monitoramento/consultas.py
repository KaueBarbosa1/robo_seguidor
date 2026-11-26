"""Consultas parametrizadas, paginação e redução de séries antes de ir ao navegador."""
from datetime import datetime,timedelta,timezone
from collections import defaultdict
from contextlib import closing
import json,math,time,uuid
from armazenamento.banco import conectar

def instante(s):
    d=datetime.fromisoformat(s)
    if d.tzinfo is None:raise ValueError('Instante sem fuso')
    return d.astimezone(timezone.utc)

def filtros(d):
    permitidos={'sessao','experimento','inicio','fim','modo','simulado','dispositivo','lado'}
    if set(d)-permitidos:raise ValueError('Filtro desconhecido')
    return {k:v for k,v in d.items() if v is not None and v!=''}

class Consultas:
    def __init__(self,historico):self.h=historico

    def sessoes(self,d):
        pagina=int(d.get('pagina',0));limite=int(d.get('limite',20))
        if not 0<=pagina<=100000 or not 1<=limite<=100:raise ValueError('Paginação inválida')
        cond=[];p=[]
        for k,op in [('inicio','>='),('fim','<=')]:
            if d.get(k):cond.append('s.inicio_observado_utc'+op+'?');p.append(instante(d[k]).isoformat())
        for k in ['simulado','modo']:
            if d.get(k) not in (None,''):
                cond.append('s.'+('modo_processamento' if k=='modo' else k)+'=?')
                p.append(int(d[k]) if k=='simulado' else d[k])
        if d.get('busca'):
            cond.append('(s.nome LIKE ? OR s.id LIKE ? OR s.observacoes LIKE ?)');p += ['%'+str(d['busca'])[:200]+'%']*3
        if d.get('experimento'):
            uuid.UUID(d['experimento']);cond.append('EXISTS(SELECT 1 FROM experimento_sessoes es WHERE es.sessao_id=s.id AND es.experimento_id=?)');p.append(d['experimento'])
        where=' WHERE '+' AND '.join(cond) if cond else ''
        with closing(conectar(self.h.raiz)) as c:
            total=c.execute('SELECT COUNT(*) FROM sessoes s'+where,p).fetchone()[0]
            rows=c.execute('SELECT s.*,(SELECT COUNT(*) FROM telemetria t WHERE t.sessao_id=s.id) amostras,'
                '(SELECT COUNT(*) FROM imagens i WHERE i.sessao_id=s.id) imagens FROM sessoes s'+where+
                ' ORDER BY s.inicio_observado_utc DESC LIMIT ? OFFSET ?',(*p,limite,pagina*limite)).fetchall()
        return dict(total=total,pagina=pagina,limite=limite,itens=[dict(r) for r in rows])

    def resumo(self,sid):
        uuid.UUID(sid)
        with closing(conectar(self.h.raiz)) as c:
            row=c.execute('SELECT * FROM sessoes WHERE id=?',(sid,)).fetchone()
            if row is None:raise ValueError('Sessão não encontrada')
            info=dict(row)
            info['imagens']=c.execute('SELECT COUNT(*) FROM imagens WHERE sessao_id=?',(sid,)).fetchone()[0]
            p=c.execute('SELECT * FROM odometria WHERE sessao_id=? ORDER BY timestamp_utc DESC,id DESC LIMIT 1',(sid,)).fetchone()
            info['odometria']=dict(p) if p else None
            info['configuracoes']=[dict(r) for r in c.execute('SELECT g.id,g.nome,g.configuracoes_json FROM gravacoes g JOIN gravacao_sessoes gs ON gs.gravacao_id=g.id WHERE gs.sessao_id=? LIMIT 20',(sid,))]
            info['processamentos_registrados']=[r[0] for r in c.execute('SELECT DISTINCT p.processamento FROM percepcao_remota p JOIN telemetria t ON t.id=p.telemetria_id WHERE t.sessao_id=?',(sid,))]
        f=dict(sessao=sid,simulado=bool(info['simulado']))
        stats={}
        for nome,cat,col in [('pps_esq','motores','pps_esq'),('pps_dir','motores','pps_dir'),('latencia','comunicacao','rtt_s'),('temperatura','desempenho','temperatura_c'),('fps','comunicacao','fps'),('cpu','desempenho','cpu_pct')]:
            extra={'dispositivo':'servidor'} if cat=='desempenho' else {'lado':'servidor'} if cat=='comunicacao' else {}
            stats[nome]=self.h.estatistica(cat,col,**f,**extra)
        histograma=[];lat=stats['latencia']
        for nome,col in [('ciclo_distribuido','latencia_total_s'),('inferencia_percepcao','inferencia_s')]:
            stats[nome]=self.h.estatistica('percepcao_remota',col,**f)
        if lat['n']:
            a,z=lat['minimo'],lat['maximo'];amplitude=max(z-a,1e-12)
            with closing(conectar(self.h.raiz)) as c:
                rows=c.execute("SELECT MIN(11,CAST((rtt_s-?)/?*12 AS INTEGER)) balde,COUNT(*) n FROM comunicacao WHERE sessao_id=? AND lado='servidor' AND rtt_s IS NOT NULL GROUP BY balde ORDER BY balde",(a,amplitude,sid)).fetchall()
            histograma=[dict(inicio_s=a+r['balde']/12*(z-a),fim_s=a+(r['balde']+1)/12*(z-a),n=r['n']) for r in rows]
        return dict(sessao=info,resumo=self.h.resumo(**f),estatisticas=stats,
                    histograma_rtt=histograma,
                    limitacoes=['Posição relativa estimada, sem referência externa.',
                    'Comparação exploratória; condições controladas devem ser verificadas pelo pesquisador.',
                    'NULL e campos vencidos não representam zero; não há histórico de treino inventado.'])

    def janela(self,sid,fim,segundos=60,pontos=240):
        uuid.UUID(sid);segundos=float(segundos);pontos=int(pontos)
        if not 1<=segundos<=3600 or not 10<=pontos<=600:raise ValueError('Janela fora do limite')
        final=instante(fim);inicial=final-timedelta(seconds=segundos)
        baldes={};n=0
        campos={'pps_esq':('motores_qualidade_json','pps_esq'),'pps_dir':('motores_qualidade_json','pps_dir'),
                'pwm_informado_esq':('motores_qualidade_json','pwm_esq'),'pwm_informado_dir':('motores_qualidade_json','pwm_dir'),
                'distancia_cm':('sensores_qualidade_json','distancia_cm'),'erro_normalizado':('visao_qualidade_json','erro'),
                'servo_comandado_graus':('sensores_qualidade_json','angulo_servo_graus'),
                'cpu_servidor_pct':(None,None),'temperatura_servidor_c':(None,None),
                'rtt_servidor_s':(None,None),'fps_captura':(None,None)}
        for row in self.h.iterar('consolidado',sessao=sid,inicio=inicial.isoformat(),fim=final.isoformat()):
            n+=1;t=instante(row['recebido_utc']).timestamp();idx=min(pontos-1,max(0,int((t-inicial.timestamp())/segundos*pontos)))
            b=baldes.setdefault(idx,{'t':t,'valores':defaultdict(list),'n':0});b['n']+=1;b['t']=t
            for k,(json_col,chave) in campos.items():
                q=json.loads(row.get(json_col) or '{}').get(chave,{}) if json_col else {'estado':'atual'}
                v=row.get(k)
                if q.get('estado')=='atual' and type(v) in (float,int) and math.isfinite(v):
                    a=b['valores'].setdefault(k,[0.,0,float('inf'),float('-inf')]);a[0]+=v;a[1]+=1;a[2]=min(a[2],v);a[3]=max(a[3],v)
        itens=[]
        for i,b in sorted(baldes.items()):
            itens.append(dict(t=b['t'],n=b['n'],**{k:(a[0]/a[1] if (a:=b['valores'].get(k)) else None) for k in campos},
                extremos={k:dict(minimo=a[2],maximo=a[3]) for k,a in b['valores'].items()}))
        return dict(itens=itens,amostras_origem=n,agregacao='Média de campos válidos por intervalo; extremos preservados separadamente. Lacunas não são preenchidas.',inicio=inicial.isoformat(),fim=final.isoformat())

    def experimentos(self):
        rows=self.h.consultar('experimentos',limite=100)
        with closing(conectar(self.h.raiz)) as c:
            for r in rows:r['sessoes']=[v[0] for v in c.execute('SELECT sessao_id FROM experimento_sessoes WHERE experimento_id=?',(r['id'],))]
        return rows

    def comparar(self,sessoes):
        if not isinstance(sessoes,list) or not 1<=len(sessoes)<=6:raise ValueError('Compare de 1 a 6 sessões')
        return dict(itens=[self.resumo(s) for s in sessoes],natureza='Comparação exploratória; domínios real/simulado permanecem separados.',
                    distribuido_real='Sem resultados registrados nesta etapa')
