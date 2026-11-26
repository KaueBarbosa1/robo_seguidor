"""Estado da central: mesmo cliente, simulador, gravador e banco do gêmeo."""
from collections import deque
from dataclasses import asdict,replace
from datetime import datetime,timezone
from pathlib import Path
import json,math,threading,time
from urllib.parse import urlsplit
from gemeo_digital.integracao import Ponte
from gemeo_digital.estado_visual import valor,atual
from gemeo_digital.cinematica import Calibracao
from armazenamento.gravador import Gravador
from armazenamento.configuracao import OpcoesArmazenamento
from monitoramento.sistema import Sistema
from central_monitoramento.consultas import Consultas

PRESETS={
 'normal':dict(esq=0.,dir=0.,distancia=100.,linha=True,camera=True,falha=False,cpu=32.,temperatura=48.,latencia=0.,motores=True,arduino=True,emergencia=False,descartar_cada=0),
 'seguimento':dict(esq=8.,dir=8.,linha=True,camera=True,falha=False,motores=True,arduino=True,emergencia=False),
 'curva':dict(esq=3.,dir=12.,motores=True,emergencia=False),
 'obstaculo':dict(distancia=12.,geometria=False,esq=0.,dir=0.),
 'linha_perdida':dict(linha=False),
 'comunicacao':dict(falha=True),
 'sobrecarga':dict(cpu=98.,temperatura=85.,latencia=.35,descartar_cada=3),
}

class SistemaEmCache:
    def __init__(self,central):self.central=central
    def coletar(self):return self.central.pc

class Central(Ponte):
    def __init__(self,*a,arquivo_preferencias=None,etapa6=False,op_distribuida=None,tokens_operacao=None,
                 telemetria_hz=10.,imagens_fps=5.,camera_fps=30.,**kw):
        from distribuido.configuracao import OpcoesDistribuidas
        self.etapa6=etapa6;self.op_distribuida=op_distribuida or OpcoesDistribuidas()
        self.tokens_operacao=tokens_operacao or {};self.telemetria_hz=telemetria_hz;self.imagens_fps=imagens_fps;self.camera_fps=camera_fps
        for nome,v,maximo in [('telemetria_hz',telemetria_hz,200),('imagens_fps',imagens_fps,60),('camera_fps',camera_fps,60)]:
            if type(v) not in (int,float) or not math.isfinite(v) or not .2<=v<=maximo:raise ValueError('Frequência inválida: '+nome)
        super().__init__(*a,**kw)
        self.consultas=Consultas(self.historico);self.inicio=time.monotonic();self.alarmes={};self.ocorrencias=deque(maxlen=300)
        self.consultas_metricas={}
        self.ultima_chave=None;self.cenario_nome='normal';self.pausado=False;self.antes_pausa=None
        self.preferencias=dict(tema='escuro',janela_s=60,graficos_hz=2,visual_hz=10,qualidade=1.5,
            unidades='SI',painel_coleta='',cpu_alerta_pct=None,temperatura_alerta_c=None,
            fov_vertical=60.,servo_centro=90.,calibracao=None)
        self.pre_path=Path(arquivo_preferencias) if arquivo_preferencias else Path(__file__).resolve().parents[1]/'dados_gemeo/dashboard_config.json'
        if self.pre_path.exists():
            try:self.configurar(json.loads(self.pre_path.read_text(encoding='utf-8')),salvar=False)
            except (ValueError,OSError):pass
        self.pc={};self.pc_t=0.;self.parada=threading.Event();self.sistema=Sistema()
        self.escritor_externo=Gravador(self.bus,OpcoesArmazenamento.central(raiz=self.historico.raiz),
            diagnostico=self._diagnostico_rede,sistema_pc=SistemaEmCache(self))
        self.escritor_externo.iniciar()
        self.worker=threading.Thread(target=self._monitorar,daemon=True,name='central-pc');self.worker.start()
        from experimentos.executor import Executor
        self.experimentos=Executor(self)

    def proteger_experimento(self):
        e=getattr(self,'experimentos',None)
        if e and e.snapshot()['ativo'] and threading.current_thread() is not e.thread:
            raise ValueError('Experimento em andamento: cancele antes de alterar a fonte ou configuração')

    def _monitorar(self):
        while not self.parada.is_set():
            try:
                amostra=self.sistema.coletar()
                with self.lock:self.pc=amostra;self.pc_t=time.monotonic()
                self._avaliar(super().snapshot())
            except Exception as exc:self.alerta('monitor_pc',True,'erro','Computador',str(exc))
            self.parada.wait(1.)

    def _diagnostico_rede(self):
        fluxo=self.fluxo
        return fluxo.cliente.snapshot() if fluxo and fluxo.cliente else {'canais':{}}

    def alerta(self,chave,ativo,gravidade,componente,mensagem):
        with self.lock:
            anterior=self.alarmes.get(chave)
            if anterior is None and not ativo:return
            if anterior and anterior['ativo']==bool(ativo):return
            timestamp=self.replay.posicao_utc if self.modo=='historico' and self.replay else datetime.now(timezone.utc).isoformat()
            e=dict(chave=chave,ativo=bool(ativo),gravidade=gravidade,componente=componente,
                mensagem=mensagem,timestamp=timestamp,
                sessao=self.estado.sessao,origem=self.modo,estado='ativa' if ativo else 'resolvida')
            self.alarmes[chave]=e;self.ocorrencias.append(e)
            self.bus.publicar('alertas',e)

    def _avaliar(self,s):
        d=s['dados'];t=d.get('envelope',{}).get('dados',{}).get('telemetria',{});u=t.get('sensores',{});v=t.get('visao',{})
        self.alerta('telemetria',not d['disponivel'],'atencao','Comunicação','Telemetria indisponível ou vencida; estado visual congelado')
        for chave,campo,gravidade,componente,mensagem,inverter in [
            ('obstaculo',u.get('obstaculo_confirmado'),'atencao','Ultrassônico','Obstáculo informado pelo sensor',False),
            ('linha',v.get('linha_visivel'),'atencao','Visão','Linha não detectada',True),
            ('encoder',t.get('motores',{}).get('falha_encoder'),'erro','Encoders','Falha de encoder informada',False),
            ('sensor',u.get('falha_sensor'),'erro','Ultrassônico','Falha de sensor informada',False)]:
            if d['disponivel'] and atual(campo):self.alerta(chave,not valor(campo) if inverter else valor(campo),gravidade,componente,mensagem)
        if d['disponivel'] and type(v.get('camera_ok'))is bool:self.alerta('camera',not v['camera_ok'],'erro','ESP32-CAM','Câmera informada como indisponível')
        distribuido=t.get('distribuido')
        if isinstance(distribuido,dict):
            self.alerta('emergencia_rede',distribuido.get('emergencia',False),'critico','Controle','Emergência por software retida; exige liberação explícita')
            self.alerta('confirmacao_parada',distribuido.get('parada')=='falha_na_confirmacao','erro','Controle','Parada solicitada sem confirmação pelos dados disponíveis')
        if s['modo']=='simulado':
            c=s['simulacao'];self.alerta('arduino',not c.get('arduino',True),'erro','Arduino','Falha do Arduino simulada')
            self.alerta('emergencia',c.get('emergencia',False),'critico','Simulador','Parada de emergência exclusivamente simulada')
        sys=d.get('envelope',{}).get('dados',{}).get('sistema',{}).get('valores',{})
        for k,limite in [('cpu_total_pct','cpu_alerta_pct'),('temperatura_c','temperatura_alerta_c')]:
            lim=self.preferencias[limite];v=sys.get(k)
            if d['disponivel'] and lim is not None and isinstance(v,(int,float)):self.alerta(k,v>=lim,'atencao','Host da telemetria','Limiar administrativo de '+k+' atingido')

    def receber(self,*a,**kw):
        ok=super().receber(*a,**kw)
        self.alerta('dominio_origem',bool(self.aviso_origem),'erro','Comunicação',self.aviso_origem or 'Origem compatível com a fonte selecionada')
        if ok:self._avaliar(super().snapshot())
        return ok

    def snapshot(self):
        s=super().snapshot()
        with self.lock:
            rede=self.fluxo.cliente.snapshot() if self.fluxo and self.fluxo.cliente else None
            if rede:
                rede.pop('ultima_telemetria',None);rede.pop('ultimo_frame',None)
            s['central']=dict(pc=self.pc,pc_idade_s=max(0,time.monotonic()-self.pc_t),rede=rede,
                gravacao=self.escritor_externo.snapshot(),preferencias=self.preferencias.copy(),
                opcoes_armazenamento={k:getattr(self.escritor_externo.op,k) for k in ('imagens','imagens_eventos','imagens_fps','max_bytes','max_imagens_bytes')},
                consultas=self.consultas_metricas,fanout=dict(self.fluxo.ass.contas) if self.fluxo else None,
                alertas=list(self.alarmes.values()),ocorrencias=list(self.ocorrencias)[-40:],
                uptime_pc_s=time.monotonic()-self.inicio,cenario=self.cenario_nome,pausado=self.pausado,
                remoto_real=False,distribuido_real=False)
            s['central']['etapa6']=self.etapa6
            s['central']['experimento']=self.experimentos.snapshot() if hasattr(self,'experimentos') else None
            s['central']['operacao_rede']=self.fluxo.operacao.snapshot() if self.fluxo and self.fluxo.operacao else None
        return s

    def operacao_comando(self,d):
        if d.get('acao') in ('parar','emergencia'):
            if hasattr(self,'experimentos'):self.experimentos.parar()
        else:self.proteger_experimento()
        if not self.etapa6 or self.modo=='historico' or not self.fluxo or not self.fluxo.operacao:raise ValueError('Canal operacional indisponível nesta origem')
        if d.get('instancia')!=self.instancia or d.get('epoch')!=self.epoch:raise ValueError('Fonte da interface mudou; pedido descartado')
        op=self.fluxo.operacao
        import uuid
        try:uuid.UUID(d.get('operador',''))
        except (ValueError,TypeError,AttributeError):raise ValueError('Identificação da aba de operação inválida')
        if self.modo=='real' and not self.op_distribuida.remoto_real:
            raise ValueError('Controle/configuração real bloqueados no PC até validação física explícita')
        if d.get('acao')=='imagem_teste':
            if self.modo!='simulado' or not self.fluxo.integrado:raise ValueError('Imagem local exclusiva do simulador')
            rt=self.fluxo.integrado
            if rt.estado.modo.name!='PARADO':raise ValueError('Pare antes de trocar a imagem')
            caminho=d.get('caminho','');imagem=None
            if caminho:
                from visao.jpeg import ler_imagem_limitada
                imagem=ler_imagem_limitada(caminho)
            with rt.estado.lock:rt.autoridade.invalidar();rt.camera.imagem_teste=imagem
            return dict(imagem_teste=bool(caminho),dimensoes=list(imagem.shape[:2]) if imagem is not None else [240,320])
        if d.get('acao')=='configurar_pipeline':
            manifesto=d.get('manifesto')
            if d.get('algoritmo')=='cnn-fotos' and not manifesto:manifesto=Path(__file__).resolve().parents[1]/'dataset_pista/resultados/treino_posicao_02/experimento.json'
            op.configurar(d.get('algoritmo'),manifesto);return op.snapshot()
        if d.get('acao')=='falhas_servico':
            if self.modo!='simulado':raise ValueError('Injeção de falhas exclusiva da simulação')
            atraso=d.get('atraso_s',0.)
            if type(atraso)not in (int,float) or not math.isfinite(atraso) or not 0<=atraso<=2:raise ValueError('Atraso inválido')
            op.atraso_s=atraso;op.pausa_inferencia=d.get('pausar') is True;op.falha_inferencia=d.get('falhar') is True
            return op.snapshot()
        dados={k:v for k,v in d.items() if k in ('acao','modo','algoritmo','direcao','velocidade_pps')}
        return op.comandar(dados,operador=d.get('operador'))

    def modo_alterar(self,modo):
        self.proteger_experimento()
        if self.escritor_externo and self.escritor_externo.gravacao:self.escritor_externo.encerrar('troca de fonte; sem retomada automática')
        super().modo_alterar(modo)
        with self.lock:self.alarmes={};self.ocorrencias.clear()

    def simular(self,dados):
        self.proteger_experimento()
        super().simular(dados)
        if self.fluxo and self.fluxo.servidor:
            c=self.cenario.ler();self.fluxo.servidor.falhas['descartar_cada']=c.get('descartar_cada',0)

    def historico_selecionar(self,*a,**kw):
        super().historico_selecionar(*a,**kw)
        with self.lock:self.alarmes={};self.ocorrencias.clear()
        self._avaliar(super().snapshot())

    def cenario_comando(self,d):
        if self.modo!='simulado':raise ValueError('Controle permitido somente em simulação; hardware real bloqueado')
        acao=d['acao']
        if acao in ('iniciar','reiniciar'):
            nome=d.get('cenario',self.cenario_nome)
            if nome not in PRESETS:raise ValueError('Cenário desconhecido')
            self.simular(dict(PRESETS['normal'],**PRESETS[nome]));self.cenario_nome=nome;self.pausado=False
            if acao=='reiniciar':
                with self.lock:self.estado.odom.resetar();self.estado.base=None
        elif acao=='pausar':
            self.antes_pausa=self.cenario.ler();self.simular(dict(motores=False));self.pausado=True
        elif acao=='retomar':
            if self.antes_pausa:self.simular({'motores':self.antes_pausa['motores']})
            self.pausado=False
        elif acao=='encerrar':self.simular(dict(esq=0.,dir=0.,motores=False,falha=False,emergencia=False));self.pausado=True
        elif acao=='emergencia':self.simular(dict(esq=0.,dir=0.,emergencia=True,motores=False))
        else:raise ValueError('Ação inválida')
        return True

    def gravacao_comando(self,d):
        self.proteger_experimento()
        if self.modo=='historico':raise ValueError('Reprodução é somente leitura')
        g=self.escritor_externo;acao=d['acao']
        if acao=='iniciar':return g.nova_gravacao(d.get('nome','Central de monitoramento'),modo='simulacao' if self.modo=='simulado' else 'observacao_embarcada')
        if acao not in ('pausar','retomar','encerrar'):raise ValueError('Ação de gravação inválida')
        return getattr(g,acao)()

    def configurar(self,d,salvar=True):
        self.proteger_experimento()
        if not isinstance(d,dict) or set(d)-set(self.preferencias):raise ValueError('Preferência não permitida')
        p=dict(self.preferencias,**d)
        for k,a,b in [('janela_s',5,3600),('graficos_hz',.2,10),('visual_hz',1,20),('qualidade',1,2),('fov_vertical',20,120),('servo_centro',45,135)]:
            if type(p[k]) not in (int,float) or not math.isfinite(p[k]) or not a<=p[k]<=b:raise ValueError('Valor inválido: '+k)
        for k in ['cpu_alerta_pct','temperatura_alerta_c']:
            if p[k] is not None and (type(p[k]) not in (int,float) or not math.isfinite(p[k]) or not 0<=p[k]<=150):raise ValueError('Limiar inválido')
        if p['tema'] not in ('escuro','claro') or p['unidades'] not in ('SI','centimetros'):raise ValueError('Preferência inválida')
        if p['painel_coleta']:
            u=urlsplit(p['painel_coleta'])
            if u.scheme not in ('http','https') or not u.hostname or u.username or u.password:raise ValueError('URL do painel inválida')
        if p['calibracao']:
            c=p['calibracao'];cal=Calibracao(**c['parametros'])
            if c['natureza'] not in ('simulada','estimada','calibrada') or not replace(cal,simulada=True).valida():raise ValueError('Calibração inválida')
            if cal.simulada!=(c['natureza']=='simulada') or cal.confirmada!=(c['natureza']=='calibrada'):raise ValueError('Natureza e flags de calibração inconsistentes')
        self.preferencias=p
        if salvar:
            self.pre_path.parent.mkdir(parents=True,exist_ok=True);tmp=self.pre_path.with_suffix('.tmp');tmp.write_text(json.dumps(p,ensure_ascii=False,allow_nan=False),encoding='utf-8');tmp.replace(self.pre_path)
        return p

    def conexao_configurar(self,url):
        u=urlsplit(url)
        if u.scheme not in ('ws','wss') or not u.hostname or u.username or u.password or u.query or u.fragment:raise ValueError('URL WebSocket inválida; token fica somente no terminal')
        if self.modo=='real':raise ValueError('Troque para simulação antes de alterar a conexão')
        self.url_real=url;return True

    def fechar(self):
        if hasattr(self,'experimentos'):self.experimentos.fechar()
        self.parada.set();super().fechar();self.worker.join(timeout=3);self.escritor_externo.fechar()
