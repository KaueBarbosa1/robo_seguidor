"""Um ensaio por vez, na Central existente; somente percepção virtual parada."""
from collections import deque,OrderedDict,Counter
from dataclasses import asdict,replace
from datetime import datetime,timezone
import csv
import json
import random
import threading
import time
import uuid

from experimentos.configuracao import validar,CONFIGURACOES,RAIZ,ambiente
from experimentos.analise import resumo,criterios


def utc():return datetime.now(timezone.utc).isoformat()


class Cancelado(Exception):pass


def verificar_integridade(raiz,cancelar,prazo_s=60.):
    from contextlib import closing
    import sqlite3
    from armazenamento.banco import conectar
    if cancelar.is_set():raise Cancelado('Cancelado antes da verificação de integridade')
    limite=time.monotonic()+prazo_s
    with closing(conectar(raiz)) as banco:
        banco.set_progress_handler(lambda:int(cancelar.is_set() or time.monotonic()>limite),5000)
        try:
            resultado=dict(integrity_check=banco.execute('PRAGMA integrity_check').fetchone()[0],
                foreign_key_check=[list(r) for r in banco.execute('PRAGMA foreign_key_check')])
            if cancelar.is_set():raise Cancelado('Cancelado durante verificação de integridade')
            return resultado
        except sqlite3.OperationalError as exc:
            if cancelar.is_set():raise Cancelado('Cancelado durante verificação de integridade') from exc
            if time.monotonic()>limite:raise RuntimeError('Verificação de integridade excedeu o prazo; não foi aprovada') from exc
            raise


class Executor:
    def __init__(self,central):
        self.central=central;self.lock=threading.RLock();self.cancelar=threading.Event();self.thread=None
        self.estado=dict(ativo=False,estado='ocioso',execucao=None,erro=None,concluidas=0,total=0)

    def snapshot(self):
        with self.lock:return dict(self.estado)

    def iniciar(self,config):
        c=validar(config)
        with self.lock:
            if self.thread and self.thread.is_alive():raise ValueError('Já existe um experimento em andamento')
            b=self.central
            if not b.etapa6 or b.modo!='simulado':raise ValueError('Selecione a simulação integrada; nenhum ensaio é executado no hardware')
            if b.escritor_externo.gravacao:raise ValueError('Encerre a gravação manual antes do experimento')
            rt=b.fluxo.integrado if b.fluxo else None
            if not rt or rt.estado.modo.name!='PARADO' or rt.autoridade.lease:raise ValueError('Pare e libere o controle antes do experimento')
            self.cancelar.clear();self.estado=dict(ativo=True,estado='preparando',execucao=None,erro=None,concluidas=0,total=c['repeticoes']*len(c['configuracoes']))
            self.thread=threading.Thread(target=self._executar,args=(c,),name='experimento-PC',daemon=True);self.thread.start()
            return self.snapshot()

    def parar(self):self.cancelar.set();return self.snapshot()

    def fechar(self):
        self.cancelar.set()
        if self.thread:self.thread.join(20)
        if self.thread and self.thread.is_alive():raise RuntimeError('Executor ainda encerrando; não liberar banco antes dele')

    def _esperar(self,fn,prazo=8):
        fim=time.monotonic()+prazo
        while time.monotonic()<fim:
            if self.cancelar.wait(.025):raise Cancelado('Cancelado pelo operador')
            v=fn()
            if v:return v
        raise RuntimeError('Pré-condição não observada no prazo')

    def _executar(self,c):
        b=self.central
        original=(b.op_distribuida,b.telemetria_hz,b.imagens_fps,b.camera_fps,b.escritor_externo.op)
        contagens=Counter()
        try:
            env=ambiente()
            eid=b.escritor_externo.comandar('experimento',nome=c['nome'],objetivo=c['objetivo'],modo='simulacao',
                algoritmo='A–D',repeticao=c['repeticoes'],configuracoes=c,observacoes=c['hipotese'])
            with self.lock:self.estado['experimento']=eid
            ordem=[];rng=random.Random(c['semente'])
            for repeticao in range(1,c['repeticoes']+1):
                ids=list(c['configuracoes']);rng.shuffle(ids)
                ordem.extend((k,repeticao) for k in ids)
            for k,rep in ordem:
                if self.cancelar.is_set():raise Cancelado('Cancelado pelo operador')
                estado=self._ensaio(c,k,rep,eid,env);contagens[estado]+=1
                with self.lock:
                    self.estado['concluidas']+=1;self.estado['resultados']=dict(contagens)
            with self.lock:self.estado['estado']='falha' if contagens['falha'] else 'concluido_com_bloqueios' if contagens['bloqueada'] else 'concluido'
        except Cancelado as exc:
            with self.lock:self.estado.update(estado='cancelado',erro=str(exc))
        except Exception as exc:
            with self.lock:self.estado.update(estado='falha',erro=f'{type(exc).__name__}: {exc}')
        finally:
            # Volta somente ao simulador parado, nunca retoma comandos anteriores.
            try:
                b.op_distribuida,b.telemetria_hz,b.imagens_fps,b.camera_fps,armazenamento=original
                if not b.escritor_externo.gravacao:
                    b.escritor_externo.comandar('opcoes_locais',imagens=armazenamento.imagens,imagens_fps=armazenamento.imagens_fps)
                if b.modo=='simulado':b.modo_alterar('simulado')
            except Exception as exc:
                with self.lock:self.estado.update(estado='falha',erro=(self.estado.get('erro') or '')+f' | Encerramento: {type(exc).__name__}: {exc}')
            with self.lock:self.estado['ativo']=False

    def _ensaio(self,c,k,rep,eid,env):
        from tools.validar_distribuido import imagens_fixas
        from distribuido.percepcao import Pipeline
        from monitoramento.benchmark import Benchmark
        from armazenamento.imagens import hash_arquivo
        b=self.central;ident=str(uuid.uuid4());pasta=b.historico.raiz/'experimentos'/ident;pasta.mkdir(parents=True)
        config={**c,'configuracao_efetiva':CONFIGURACOES[k]}
        row=dict(id=ident,experimento_id=eid,sessao_id=None,configuracao=k,repeticao=rep,origem='simulada',nivel=3,
                 categoria=c['categoria'],inicio_utc=utc(),fim_utc=None,estado='executando',configuracoes_json=json.dumps(config,ensure_ascii=False),
                 ambiente_json=json.dumps(env,ensure_ascii=False),resultado_json='{}',artefato_relativo=pasta.relative_to(b.historico.raiz).as_posix())
        b.escritor_externo.comandar('execucao_experimental',**row)
        with self.lock:self.estado.update(execucao=ident,configuracao=k,repeticao=rep,estado='inicializando')
        bench=None;rt=None;resultado={};amostras=0;limitadas={m:deque(maxlen=25000) for m in ('inferencia_s','processamento_s','ciclo_s','cpu_pc_pct','rss_bytes','controle_hz','rtt_s','consulta_s')}
        try:
            inicio=time.perf_counter()
            # Nova sessão por repetição; usa os mesmos Fluxo/Servidor/Cliente/Gravador.
            b.op_distribuida=replace(b.op_distribuida,inferencia_hz=c['inferencia_hz'])
            b.telemetria_hz=c['telemetria_hz'];b.imagens_fps=c['imagens_fps'];b.camera_fps=c['camera_fps']
            b.modo_alterar('simulado');b.simular(dict(camera=True,linha=True,arduino=True,motores=True,emergencia=False,falha=False,falha_sensor=False,latencia=0.,descartar_cada=0,idade_frame_s=0.))
            rt=b.fluxo.integrado;op=b.fluxo.operacao
            jpeg,imagem=imagens_fixas()[1];rt.camera.imagem_teste=imagem
            (pasta/'imagem_entrada.jpg').write_bytes(jpeg)
            self._esperar(lambda:op.snapshot()['remoto'].get('remoto_pronto') and op.snapshot()['remoto'].get('parada')=='confirmada_pelos_dados')
            modelo=CONFIGURACOES[k];t0=time.perf_counter()
            if modelo['algoritmo']=='cnn-fotos':
                manifesto=(RAIZ/c['manifesto']).resolve()
                # Local diagnóstico usa a mesma câmera e o mesmo pipeline; não publica comandos.
                if modelo['processamento']=='embarcado':
                    pipeline=Pipeline('cnn-fotos',manifesto)
                    with rt.estado.lock:
                        rt.autoridade.algoritmo='cnn-fotos';rt.autoridade.versao_modelo=pipeline.versao
                    rt.pipeline=pipeline
                else:op.configurar('cnn-fotos',manifesto)
            carga_modelo=time.perf_counter()-t0 if modelo['algoritmo']=='cnn-fotos' else None
            if modelo['processamento']=='distribuido':
                self._esperar(lambda:op.snapshot()['remoto'].get('remoto_pronto') and
                    op.snapshot()['remoto'].get('algoritmo')==modelo['algoritmo'] and
                    op.snapshot()['remoto'].get('parada')=='confirmada_pelos_dados')
                # A autoridade exige 500 ms entre duas alterações administrativas.
                if self.cancelar.wait(.55):raise Cancelado('Cancelado durante estabilização')
                op.comandar({'acao':'modo','modo':'distribuido'});op.atraso_s=c['atraso_s']
            inicializacao=time.perf_counter()-inicio
            if self.cancelar.wait(c['aquecimento_s']):raise Cancelado('Cancelado durante aquecimento')
            b.escritor_externo.comandar('opcoes_locais',imagens=c['gravar_imagens'],imagens_fps=c['imagens_fps'])
            gid=b.gravacao_comando(dict(acao='iniciar',nome=f'{c["nome"]} · {k} · repetição {rep}'))
            sid=self._esperar(lambda:b.estado.sessao)
            def registrada():
                from contextlib import closing
                from armazenamento.banco import conectar
                with closing(conectar(b.historico.raiz)) as banco:
                    return banco.execute('SELECT 1 FROM sessoes WHERE id=?',(sid,)).fetchone() is not None
            self._esperar(registrada)
            row['sessao_id']=sid
            b.escritor_externo.comandar('associar_sessoes',experimento=eid,sessoes=[row['sessao_id']])
            bench=Benchmark(pasta/'benchmark',intervalo=1.,condicoes=config);bench.diagnostico_rede=b._diagnostico_rede;bench.iniciar()
            inicio=time.monotonic();ultimo_frame=None;ultimo_sys=0.;ultima_consulta=0.;bytes_csv=0;eventos=OrderedDict();eventos_observados=0
            with self.lock:self.estado['estado']='coletando'
            with (pasta/'amostras.csv').open('w',encoding='utf-8',newline='') as f:
                campos=['t_s','frame_id','inferencia_id','geracao','inferencia_s','processamento_s','ciclo_s','cpu_pc_pct','rss_bytes','controle_hz','rtt_s','consulta_s']
                writer=csv.DictWriter(f,fieldnames=campos);writer.writeheader()
                while time.monotonic()-inicio<c['duracao_s']:
                    if self.cancelar.wait(.1):raise Cancelado('Cancelado durante coleta')
                    a=rt.autoridade.snapshot();r=a.get('ultimo_resultado') or {};frame=a.get('frame_id')
                    # Execução local diagnóstica guardada pelo runtime, independente de navegação.
                    if modelo['processamento']=='embarcado':
                        r=dict(rt.ultimo_diagnostico or {});frame=r.get('frame_id')
                    t=time.monotonic();sample=dict(t_s=t-inicio,frame_id=frame,inferencia_id=None,geracao=a.get('geracao'))
                    novo=frame is not None and frame!=ultimo_frame
                    if novo:
                        ultimo_frame=frame
                        for m in ('inferencia_s','processamento_s'):sample[m]=r.get(m)
                        if modelo['processamento']=='distribuido':
                            ev=next((e for e in reversed(a['eventos']) if e.get('tipo')=='resultado_aceito' and e.get('frame_id')==frame),None)
                            if ev:sample['ciclo_s']=ev.get('latencia_total_s');sample['inferencia_id']=ev.get('inferencia_id')
                    sistema=b.pc.get('valores',{})
                    if b.pc_t!=ultimo_sys:
                        ultimo_sys=b.pc_t;sample['cpu_pc_pct']=sistema.get('processo_cpu_pct');sample['rss_bytes']=sistema.get('processo_rss_bytes')
                    if bench.ultima_amostra:sample['controle_hz']=bench.ultima_amostra.get('controle_hz')
                    rede=b._diagnostico_rede();sample['rtt_s']=(rede.get('canais',{}).get('telemetria',{}).get('rtt_s') or {}).get('mediana')
                    if t-ultima_consulta>=1:
                        t0=time.perf_counter();b.consultas.sessoes({'limite':10});sample['consulta_s']=time.perf_counter()-t0;ultima_consulta=t
                    for m in limitadas:
                        v=sample.get(m)
                        if v is not None:limitadas[m].append(v)
                    writer.writerow(sample);amostras+=1;bytes_csv=f.tell()
                    if bytes_csv>50_000_000:raise RuntimeError('Limite de 50 MB de amostras por execução atingido')
                    for e in a.get('eventos',[]):
                        if e['id'] not in eventos:eventos_observados+=1
                        eventos[e['id']]=e
                        if len(eventos)>1024:eventos.popitem(last=False)
            dt=time.monotonic()-inicio
            inicio_finalizacao=time.perf_counter()
            with self.lock:self.estado['estado']='finalizando_gravacao_e_integridade'
            bench.parar()
            if bench.erro:raise RuntimeError('Benchmark não coletou corretamente: '+bench.erro)
            bench=None
            b.gravacao_comando({'acao':'encerrar'});b.escritor_externo.sincronizar()
            servico_final=op.snapshot();autoridade_final=rt.autoridade.snapshot();gravador_final=b.escritor_externo.snapshot()
            saude=verificar_integridade(b.historico.raiz,self.cancelar)
            if saude['integrity_check']!='ok' or saude['foreign_key_check']:raise RuntimeError('Integridade/FK reprovadas; consulte o banco antes de continuar')
            resultado=dict(metricas={m:resumo(list(v)) for m,v in limitadas.items()},duracao_coleta_s=dt,
                amostras=amostras,inicializacao_s=inicializacao,carga_modelo_s=carga_modelo,aquecimento_s=c['aquecimento_s'],
                hash_imagem=hash_arquivo(pasta/'imagem_entrada.jpg'),versao_modelo=rt.pipeline.versao if modelo['processamento']=='embarcado' else op.pipeline.versao,
                opcoes_autoridade=asdict(rt.autoridade.op),seguranca=autoridade_final,servico=servico_final,
                gravacao=gid,gravador=gravador_final,integridade=saude,eventos=list(eventos.values()),eventos_observados=eventos_observados,eventos_limite_memoria=1024,finalizacao_s=time.perf_counter()-inicio_finalizacao,
                limitacoes=['Percepção parada em JPEG sintético fixo; não mede seguimento de linha ou frenagem.',
                    'Todas as CPUs/memórias são do PC; Raspberry virtual compartilha o processo.',
                    'A–D referem-se à arquitetura virtual, não a quatro configurações físicas validadas.',
                    'OpenCV e CNN têm semânticas/ROI distintas; comparação de velocidade não é comparação de qualidade.',
                    'Estatísticas de amostras limitadas às últimas 25000 por métrica; CSV completo limitado a 50 MB.',
                    'RTT/controle amostrados podem repetir estimativas; não são repetições independentes.'])
            resultado['criterios']=criterios({m:s['media'] for m,s in resultado['metricas'].items()},c['criterios'])
            row['estado']='concluida'
        except Cancelado as exc:row['estado']='cancelada';resultado['erro']=str(exc);raise
        except (ValueError,FileNotFoundError) as exc:
            row['estado']='bloqueada';resultado['erro']=str(exc)
        except Exception as exc:
            row['estado']='falha';resultado['erro']=f'{type(exc).__name__}: {exc}';raise
        finally:
            if bench:bench.parar()
            if rt:rt.autoridade.parar('fim_experimento')
            if b.escritor_externo.gravacao:
                try:b.gravacao_comando({'acao':'encerrar'})
                except Exception as exc:
                    resultado['erro_encerramento']=f'{type(exc).__name__}: {exc}';row['estado']='falha'
            row['fim_utc']=utc();row['resultado_json']=json.dumps(resultado,ensure_ascii=False,allow_nan=False)
            # Evidência parcial existe mesmo se não houver confirmação da escrita final.
            (pasta/'execucao.json').write_text(json.dumps({**row,'resultado':resultado},ensure_ascii=False,indent=2),encoding='utf-8')
            try:b.escritor_externo.comandar('execucao_experimental',prazo_s=60,**row)
            except Exception as exc:
                resultado['erro_persistencia_final']=f'{type(exc).__name__}: {exc}'
                (pasta/'execucao.json').write_text(json.dumps({**row,'resultado':resultado},ensure_ascii=False,indent=2),encoding='utf-8')
                raise
        return row['estado']
