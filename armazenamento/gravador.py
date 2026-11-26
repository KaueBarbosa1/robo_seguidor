"""Um escritor SQLite no PC; filas limitadas, prioridade a eventos e lotes transacionais."""
from collections import Counter, deque
from concurrent.futures import Future
from dataclasses import asdict
import json
import logging
from pathlib import Path
import platform
import queue
import sqlite3
import threading
import time
import uuid

from armazenamento.banco import conectar, Exclusivo, tamanho_banco
from armazenamento.configuracao import validar_pc
from armazenamento import normalizacao as norm
from armazenamento import eventos
from armazenamento.imagens import Arquivos, gravar, associar
from comunicacao.protocolo import codificar, decodificar

log = logging.getLogger('armazenamento')


class Gravador:
    def __init__(self, distribuidor, opcoes, diagnostico=None, sistema_pc=None):
        self.bus, self.op = distribuidor, opcoes
        self.tele = distribuidor.assinar({'telemetria','odometria'}, opcoes.fila_telemetria)
        self.evt = distribuidor.assinar({'eventos','alertas'}, opcoes.fila_eventos)
        self.img = distribuidor.assinar({'imagens'}, opcoes.fila_imagens)
        self.pedidos = queue.Queue(32)
        self.fim, self.pronto = threading.Event(), threading.Event()
        self.thread = None
        self.erro = None
        self.gravacao = None
        self.estado = 'inativo'
        self.contas = Counter(dict(recebidas=0,persistidas=0,duplicadas=0,descartadas=0,
                                   imagens_persistidas=0,falhas=0,lotes=0))
        self.tempos = deque(maxlen=512)
        self.ultimo_jpeg = None
        self._ultima_imagem = {}
        self._inicio = time.monotonic()
        self._limiar = 0.
        self._modo = None
        self.diagnostico, self.sistema_pc = diagnostico, sistema_pc
        self._ultimo_pc = 0.
        self._base_contas = Counter()
        self._base_filas = {'telemetria':0,'eventos':0,'imagens':0}
        self._perdas_registradas = dict(self._base_filas)

    def iniciar(self):
        validar_pc()
        if self.thread:
            raise RuntimeError('Gravador ja iniciado')
        self.thread = threading.Thread(target=self._loop,name='sqlite-gravador',daemon=True)
        self.thread.start()
        if not self.pronto.wait(5) or self.erro:
            raise RuntimeError(self.erro or 'Banco nao iniciou')

    def comandar(self, tipo, *, prazo_s=None, **dados):
        if not self.thread or not self.thread.is_alive():
            raise RuntimeError('Gravador indisponivel')
        futuro = Future()
        self.pedidos.put_nowait((tipo,dados,futuro))
        # Drenagem final inclui fsync de JPEG e lotes já recebidos. Um timeout
        # não confirma cancelamento da transação no escritor.
        prazo_s=prazo_s if prazo_s is not None else (60 if tipo in ('encerrar','sincronizar') else 10)
        try:return futuro.result(timeout=prazo_s)
        except TimeoutError as exc:
            raise TimeoutError(f'Escritor sem confirmação de {tipo} em {prazo_s:g}s; pedido pode continuar em execução') from exc

    def nova_gravacao(self, nome='Sessao', **dados):
        return self.comandar('iniciar',nome=nome,**dados)

    def pausar(self):
        return self.comandar('pausar')

    def retomar(self):
        return self.comandar('retomar')

    def encerrar(self, motivo='operador'):
        return self.comandar('encerrar',motivo=motivo)

    def sincronizar(self):
        return self.comandar('sincronizar')

    def snapshot(self):
        tempos = list(self.tempos)
        return dict(gravacao=self.gravacao,estado=self.estado,erro=self.erro,contadores=dict(self.contas),
            contadores_gravacao={k:v-self._base_contas.get(k,0) for k,v in self.contas.items()},
            filas=dict(telemetria=self.tele.fila.qsize(),eventos=self.evt.fila.qsize(),imagens=self.img.fila.qsize()),
            descartes_distribuidor={k: a.contas['descartadas'] for k,a in
                                    [('telemetria',self.tele),('eventos',self.evt),('imagens',self.img)]},
            descartes_filas_gravacao={k:a.contas['descartadas']-self._base_filas[k]
                for k,a in [('telemetria',self.tele),('eventos',self.evt),('imagens',self.img)]},
            recebidas_distribuidor={k:a.contas['recebidas'] for k,a in
                [('telemetria',self.tele),('eventos',self.evt),('imagens',self.img)]},
            tempo_medio_lote_s=sum(tempos)/len(tempos) if tempos else None,
            registros_s=self.contas['persistidas']/max(.001,time.monotonic()-self._inicio),
            banco_bytes=tamanho_banco(self.op.raiz),
            imagens_bytes=self.arquivos.bytes_imagens if hasattr(self,'arquivos') else 0)

    def fechar(self):
        self.fim.set()
        if self.thread:
            self.thread.join(timeout=10)
            if self.thread.is_alive():
                raise RuntimeError('Escritor ainda ativo; nao afirmar encerramento seguro')
        for a in (self.tele,self.evt,self.img):
            self.bus.remover(a)
        if self.erro and self.gravacao is not None and self.estado=='falha':
            raise RuntimeError('Gravacao sem encerramento confirmado: '+self.erro)

    def _recuperar(self):
        self.c.execute("UPDATE execucoes_experimentais SET estado='falha',resultado_json=? WHERE estado='executando' AND fim_utc IS NULL",
            (json.dumps({'erro':'Processo anterior interrompido; fim e resultado desconhecidos','recuperacao_observada_utc':norm.utc()},ensure_ascii=False),))
        for row in self.c.execute("SELECT id FROM gravacoes WHERE estado IN ('gravando','pausada','falha') AND fim_utc IS NULL").fetchall():
            self.c.execute("UPDATE gravacoes SET estado='interrompida',recuperada_utc=?,"
                           "motivo_encerramento='fim do processo anterior desconhecido' WHERE id=?", (norm.utc(),row[0]))
            eventos.registrar(self.c,row[0],'recuperacao','Gravacao anterior interrompida; instante final desconhecido')
        self.c.commit()

    def _loop(self):
        bloqueio = Exclusivo(self.op.raiz)
        try:
            bloqueio.abrir()
            self.c = conectar(self.op.raiz,True)
            self.arquivos = Arquivos(self.op)
            self._recuperar()
            self.pronto.set()
            while not self.fim.is_set():
                try:
                    tipo,dados,futuro = self.pedidos.get_nowait()
                except queue.Empty:
                    self._drenar(self.op.lote)
                    self._pc()
                    self.fim.wait(self.op.intervalo_s)
                    continue
                try:
                    futuro.set_result(self._comando(tipo,dados))
                except Exception as exc:
                    self.c.rollback()
                    futuro.set_exception(exc)
            self._drenar(self.op.fila_telemetria+self.op.fila_eventos+self.op.fila_imagens)
            if self.gravacao:
                self._finalizar('encerramento do gravador')
        except Exception as exc:
            self.erro = f'{type(exc).__name__}: {exc}'
            log.error('Armazenamento indisponivel: %s',self.erro)
        finally:
            self.pronto.set()
            if hasattr(self,'c'):
                self.c.close()
            bloqueio.fechar()

    def _comando(self,tipo,dados):
        if tipo == 'execucao_experimental':
            # Passa pelo único escritor existente; sem conexão de escrita paralela.
            permitidos={'id','experimento_id','sessao_id','configuracao','repeticao','origem','nivel','categoria',
                        'inicio_utc','fim_utc','estado','configuracoes_json','ambiente_json','resultado_json','artefato_relativo'}
            if set(dados)!=permitidos:raise ValueError('Registro experimental incompleto')
            uuid.UUID(dados['id']);uuid.UUID(dados['experimento_id'])
            if dados['sessao_id']:uuid.UUID(dados['sessao_id'])
            if dados['estado'] not in ('executando','concluida','falha','cancelada','bloqueada'):raise ValueError('Estado experimental inválido')
            anterior=self.c.execute('SELECT experimento_id,estado FROM execucoes_experimentais WHERE id=?',(dados['id'],)).fetchone()
            if anterior and (anterior['experimento_id']!=dados['experimento_id'] or anterior['estado']!='executando'):raise ValueError('Execução final não pode ser sobrescrita')
            if anterior:
                self.c.execute('UPDATE execucoes_experimentais SET sessao_id=?,fim_utc=?,estado=?,resultado_json=? WHERE id=?',
                    (dados['sessao_id'],dados['fim_utc'],dados['estado'],dados['resultado_json'],dados['id']))
            else:norm.inserir(self.c,'execucoes_experimentais',dados)
            self.c.commit();return dados['id']
        if tipo == 'metadados_sessao':
            uuid.UUID(dados['sessao'])
            if not self.c.execute('SELECT 1 FROM sessoes WHERE id=?',(dados['sessao'],)).fetchone():raise ValueError('Sessão não encontrada')
            for k,limite in [('nome',256),('observacoes',10000)]:
                v=dados.get(k)
                if v is not None:
                    if not isinstance(v,str) or len(v)>limite:raise ValueError('Texto inválido: '+k)
                    self.c.execute(f'UPDATE sessoes SET {k}=? WHERE id=?',(v,dados['sessao']))
            self.c.commit();return dados['sessao']
        if tipo == 'associar_sessoes':
            uuid.UUID(dados['experimento'])
            if not self.c.execute('SELECT 1 FROM experimentos WHERE id=?',(dados['experimento'],)).fetchone():raise ValueError('Experimento não encontrado')
            if not isinstance(dados['sessoes'],list) or not 1<=len(dados['sessoes'])<=100:raise ValueError('Seleção inválida')
            for sid in dados['sessoes']:
                uuid.UUID(sid)
                self.c.execute('INSERT OR IGNORE INTO experimento_sessoes VALUES(?,?)',(dados['experimento'],sid))
            self.c.commit();return True
        if tipo == 'opcoes_locais':
            from dataclasses import replace
            if self.gravacao:raise ValueError('Encerre a gravação antes de mudar os limites')
            if set(dados)-{'imagens','imagens_eventos','imagens_fps','max_bytes','max_imagens_bytes'}:raise ValueError('Opção não permitida')
            self.op=replace(self.op,**dados);self.arquivos=Arquivos(self.op);return True
        if tipo == 'experimento':
            from armazenamento.gestao import experimento
            ident = experimento(self.c,**dados)
            self.c.commit()
            return ident
        if tipo in ('sincronizar','pausar','encerrar'):
            self._drenar(self.op.fila_telemetria+self.op.fila_eventos+self.op.fila_imagens)
        if tipo == 'sincronizar':
            return self.snapshot()
        if tipo == 'iniciar':
            if self.gravacao:
                raise ValueError('Ja existe gravacao; encerre-a primeiro')
            nome = dados.get('nome','Sessao')
            if not isinstance(nome,str) or not 1 <= len(nome) <= 256:
                raise ValueError('Nome invalido')
            ident = str(uuid.uuid4())
            cfg = asdict(self.op)
            cfg['raiz'] = str(cfg['raiz'])
            cfg['modo_processamento_declarado'] = dados.get('modo')
            norm.inserir(self.c,'gravacoes',dict(id=ident,nome=nome,inicio_utc=norm.utc(),estado='gravando',
                experimento_id=dados.get('experimento'),descricao=dados.get('descricao'),
                observacoes=dados.get('observacoes'),versao_software=dados.get('versao_software'),
                configuracoes_json=norm.js(cfg)))
            eventos.registrar(self.c,ident,'gravacao_iniciada','Gravacao iniciada no computador')
            self.c.commit()
            self.gravacao,self.estado,self._modo = ident,'gravando',dados.get('modo')
            self._base_contas = Counter(self.contas)
            self._base_filas = {k:a.contas['descartadas'] for k,a in
                [('telemetria',self.tele),('eventos',self.evt),('imagens',self.img)]}
            self._perdas_registradas = dict(self._base_filas)
            self._limiar = time.monotonic()
            self.erro = None
            return ident
        if not self.gravacao:
            raise ValueError('Nenhuma gravacao ativa')
        if tipo == 'pausar':
            if self.estado != 'gravando':
                raise ValueError('Gravacao nao esta ativa')
            norm.inserir(self.c,'intervalos',dict(gravacao_id=self.gravacao,canal='gravacao',
                inicio_utc=norm.utc(),motivo='pausada_pelo_operador'))
            self.estado = 'pausada'
            eventos.registrar(self.c,self.gravacao,'gravacao_pausada','Pausa manual')
        elif tipo == 'retomar':
            if self.estado not in ('pausada','falha'):
                raise ValueError('Gravacao nao esta pausada')
            self.arquivos.espaco()
            self.c.execute("UPDATE intervalos SET fim_utc=? WHERE gravacao_id=? AND canal='gravacao' AND fim_utc IS NULL",
                           (norm.utc(),self.gravacao))
            self._limiar = time.monotonic()
            erro_anterior=self.erro
            self.estado,self.erro = 'gravando',None
            if erro_anterior:
                eventos.registrar(self.c,self.gravacao,'recuperacao_armazenamento',erro_anterior,
                                  detalhes={'dados_perdidos_nao_recuperados':True})
            eventos.registrar(self.c,self.gravacao,'gravacao_retomada','Retomada manual; nao preenche lacunas')
        elif tipo == 'encerrar':
            return self._finalizar(dados.get('motivo','operador'))
        else:
            raise ValueError('Comando de gravacao desconhecido')
        self.c.execute('UPDATE gravacoes SET estado=? WHERE id=?',(self.estado,self.gravacao))
        self.c.commit()
        return self.gravacao

    def _finalizar(self,motivo):
        ident = self.gravacao
        fim=norm.utc()
        if self.estado=='falha':motivo+='; '+str(self.erro)
        eventos.registrar(self.c,ident,'gravacao_encerrada',motivo)
        self.c.execute("UPDATE intervalos SET fim_utc=?,motivo=motivo||'_ate_encerramento' "
                       'WHERE gravacao_id=? AND fim_utc IS NULL',(fim,ident))
        self.c.execute('UPDATE gravacoes SET estado=?,fim_utc=?,motivo_encerramento=?,estatisticas_json=? WHERE id=?',
            ('falha' if self.estado=='falha' else 'encerrada',fim,motivo,norm.js(self.snapshot()),ident))
        self.c.commit()
        self.gravacao,self.estado = None,'inativo'
        self._ultima_imagem.clear()
        self.ultimo_jpeg = None
        return ident

    def _drenar(self,limite):
        itens = []
        for assinatura in (self.evt,self.tele,self.img):
            for _ in range(min(assinatura.fila.qsize(),limite)):
                try:
                    itens.append(assinatura.fila.get_nowait())
                except queue.Empty:
                    break
            # limite por fila; imagem permanece fila pequena e vem por último
        if not itens:
            return
        self.contas['recebidas']+=len(itens)
        if self.estado != 'gravando':
            self.contas['descartadas'] += len(itens)
            self.contas['fora_gravacao']+=len(itens)
            return
        for inicio in range(0,len(itens),self.op.lote):
            self._lote(itens[inicio:inicio+self.op.lote])

    def _lote(self,itens,tentativa=0):
        inicio = time.perf_counter()
        novos = []
        delta = Counter()
        ultima_img = dict(self._ultima_imagem)
        try:
            self.arquivos.espaco()
            if tamanho_banco(self.op.raiz)+self.arquivos.bytes_imagens >= self.op.max_bytes:
                raise OSError('Limite administrativo total atingido')
            self.c.execute('BEGIN IMMEDIATE')
            sessoes = set()
            for canal,item in itens:
                if canal=='alertas':
                    sid=item.get('sessao')
                    if sid and not self.c.execute('SELECT 1 FROM sessoes WHERE id=?',(sid,)).fetchone():sid=None
                    eventos.registrar(self.c,self.gravacao,'central_'+item['chave'],item['mensagem'],sid,
                        gravidade=item['gravidade'],origem='central_pc',instante=item['timestamp'],detalhes=item)
                    delta['alertas_persistidos']+=1;continue
                if canal=='odometria':
                    p=item.get('pose',{})
                    if p.get('validade')=='estimativa' and self.c.execute('SELECT 1 FROM sessoes WHERE id=?',(item.get('sessao'),)).fetchone():
                        norm.inserir(self.c,'odometria',dict(sessao_id=item['sessao'],timestamp_utc=norm.utc(item['timestamp']),
                            x_m=norm.numero(p.get('x_m')),y_m=norm.numero(p.get('y_m')),
                            orientacao_rad=norm.numero(p.get('orientacao_rad')),distancia_m=norm.numero(p.get('distancia_m')),
                            velocidade_linear_m_s=norm.numero(p.get('velocidade_linear_m_s')),
                            velocidade_angular_rad_s=norm.numero(p.get('velocidade_angular_rad_s')),
                            calibracao_json=norm.js(p.get('calibracao')),validade=p['validade'],natureza=p['natureza']))
                        delta['odometria_persistida']+=1
                    continue
                if canal == 'eventos':
                    if item.get('recepcao_mono_s',self._limiar) >= self._limiar:
                        self._evento_rede(item)
                        delta['eventos_rede_persistidos']+=1
                    else:
                        delta['descartadas']+=1
                        delta['anteriores_inicio']+=1
                    continue
                msg,jpeg,recepcao = item
                if recepcao < self._limiar:
                    delta['descartadas'] += 1
                    delta['anteriores_inicio'] += 1
                    continue
                self.c.execute('SAVEPOINT amostra')
                antes = Counter(delta)
                arquivos_antes = len(novos)
                try:
                    decodificar(codificar(norm.original(msg)))
                    if canal == 'telemetria':
                        if msg['tipo'] != 'telemetria' or not isinstance(msg['dados'].get('telemetria'),dict):
                            raise ValueError('Telemetria invalida')
                        ident,novo = norm.telemetria(self.c,msg,recepcao,self.gravacao,self._modo)
                        delta['persistidas' if novo else 'duplicadas'] += 1
                        if novo:
                            gerados = eventos.transicoes(self.c,self.gravacao,msg,ident,self.op)
                            if gerados and self.op.imagens_eventos and self.ultimo_jpeg:
                                jm,jb,jt = self.ultimo_jpeg
                                if (jm['sessao'] == msg['sessao'] and jt >= self._limiar and
                                        abs(jt-recepcao) <= self.op.associacao_s):
                                    self.c.execute('SAVEPOINT imagem_evento')
                                    n_antes = len(novos)
                                    try:
                                        _,criada = gravar(self.c,self.arquivos,jm,jb,self.gravacao,self._modo,novos)
                                        delta['imagens_persistidas'] += int(criada)
                                        self.c.execute('RELEASE imagem_evento')
                                    except (OSError,ValueError) as exc:
                                        self.c.execute('ROLLBACK TO imagem_evento')
                                        self.c.execute('RELEASE imagem_evento')
                                        self.arquivos.reverter(novos[n_antes:]); del novos[n_antes:]
                                        delta['imagens_rejeitadas'] += 1
                                        eventos.registrar(self.c,self.gravacao,'falha_imagem',str(exc),gravidade='alerta')
                    else:
                        self.ultimo_jpeg = item
                        ultimo = self._ultima_imagem.get(msg['sessao'])
                        if not self.op.imagens or (ultimo is not None and recepcao-ultimo < 1/self.op.imagens_fps):
                            delta['descartadas'] += 1
                            delta['imagens_politica'] += 1
                            self.c.execute('RELEASE amostra')
                            continue
                        _,novo = gravar(self.c,self.arquivos,msg,jpeg,self.gravacao,self._modo,novos)
                        delta['imagens_persistidas' if novo else 'duplicadas'] += 1
                        self._ultima_imagem[msg['sessao']] = recepcao
                    sessoes.add(msg['sessao'])
                    self.c.execute('RELEASE amostra')
                except (ValueError,TypeError,KeyError) as exc:
                    self.c.execute('ROLLBACK TO amostra')
                    self.c.execute('RELEASE amostra')
                    self.arquivos.reverter(novos[arquivos_antes:])
                    del novos[arquivos_antes:]
                    delta = antes
                    delta['descartadas'] += 1
                    delta['invalidas'] += 1
                    eventos.registrar(self.c,self.gravacao,'amostra_invalida',str(exc),gravidade='alerta')
                except OSError as exc:
                    self.c.execute('ROLLBACK TO amostra')
                    self.c.execute('RELEASE amostra')
                    self.arquivos.reverter(novos[arquivos_antes:])
                    del novos[arquivos_antes:]
                    delta = antes
                    delta['descartadas'] += 1
                    delta['imagens_rejeitadas'] += 1
                    # Falha de arquivo/quota de imagens não invalida telemetria já preparada.
                    eventos.registrar(self.c,self.gravacao,'falha_imagem',str(exc),gravidade='alerta')
            for sid in sessoes:
                associar(self.c,sid,self.op.associacao_s)
            perdas={k:a.contas['descartadas'] for k,a in
                    [('telemetria',self.tele),('eventos',self.evt),('imagens',self.img)]}
            if perdas!=self._perdas_registradas:
                eventos.registrar(self.c,self.gravacao,'descarte_armazenamento','Fila limitada rejeitou mensagens novas',
                                  gravidade='alerta',detalhes={'cumulativo_por_canal':perdas})
            self.c.commit()
            self._perdas_registradas=perdas
            self.contas.update(delta)
            self.contas['lotes'] += 1
        except (OSError,sqlite3.Error) as exc:
            self.c.rollback()
            self.arquivos.reverter(novos)
            self._ultima_imagem = ultima_img
            if isinstance(exc,sqlite3.OperationalError) and ('locked' in str(exc) or 'busy' in str(exc)) and tentativa < 2:
                self.contas['retentativas'] += 1
                time.sleep(.05*(tentativa+1))
                return self._lote(itens,tentativa+1)
            self.contas['falhas'] += 1
            self.contas['descartadas'] += len(itens)
            self.contas['por_falha'] += len(itens)
            self.erro = f'{type(exc).__name__}: {exc}'
            self.estado = 'falha'
            log.error('Falha no PC; transporte e robo independentes: %s',self.erro)
        finally:
            self.tempos.append(time.perf_counter()-inicio)

    def _evento_rede(self,item):
        falso = dict(sessao=item['sessao'],origem=item['origem'],simulado=item['simulado'],
                     versao=item['versao'],monotonic_s=None)
        norm.sessao(self.c,falso,self.gravacao,norm.utc(item['timestamp']),self._modo)
        eventos.registrar(self.c,self.gravacao,item['tipo'],item['tipo'],item['sessao'],
                          instante=item['timestamp'],detalhes={'canal':item['canal']})
        if item['tipo'] == 'desconexao':
            norm.inserir(self.c,'intervalos',dict(sessao_id=item['sessao'],gravacao_id=self.gravacao,
                canal=item['canal'],inicio_utc=norm.utc(item['timestamp']),motivo='desconexao'))
        elif item['tipo'] in ('reconexao','conexao_estabelecida'):
            self.c.execute('UPDATE intervalos SET fim_utc=? WHERE sessao_id=? AND gravacao_id=? AND canal=? '
                           'AND fim_utc IS NULL AND motivo=?',
                           (norm.utc(item['timestamp']),item['sessao'],self.gravacao,item['canal'],'desconexao'))

    def _pc(self):
        agora = time.monotonic()
        if not self.gravacao or self.estado != 'gravando' or agora-self._ultimo_pc < 1 or not self.diagnostico:
            return
        self._ultimo_pc = agora
        try:
            dados = self.diagnostico()
            for canal,metricas in dados.get('canais',{}).items():
                sid = metricas.get('sessao')
                row = self.c.execute('SELECT simulado FROM sessoes WHERE id=?',(sid,)).fetchone()
                if row:
                    norm.comunicacao(self.c,sid,self.gravacao,norm.utc(),metricas,'computador',canal)
                    if canal == 'telemetria' and self.sistema_pc:
                        norm.desempenho(self.c,sid,self.gravacao,norm.utc(),self.sistema_pc.coletar(),
                            'computador',row[0],mono=agora,host=platform.node(),plataforma=platform.system())
            self.c.commit()
        except (OSError,sqlite3.Error,ValueError) as exc:
            self.c.rollback()
            self.contas['falhas'] += 1
            self.erro = str(exc)
