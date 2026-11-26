"""Autoridade embarcada. Rede publica intenções; só ThreadControle atua.

Relógios: frames guardam a recepção ORIGINAL na Pi. O relógio do PC nunca
determina idade. A trava é a mesma do EstadoRobo, inclusive na arbitragem.
"""
from collections import Counter,OrderedDict,deque
from dataclasses import asdict
import math
import time
import uuid
from datetime import datetime,timezone

import config as cfg
from estado import Modo
from distribuido.configuracao import OpcoesDistribuidas,CONTRATO
from distribuido.contratos import versao_opencv


def real(v,a,b):
    if type(v) not in (int,float) or not math.isfinite(v) or not a<=v<=b:raise ValueError('Valor numérico fora do contrato')
    return float(v)


class Autoridade:
    def __init__(self,estado,motor,fonte,opcoes=None,simulado=False,relogio=time.monotonic):
        self.estado,self.motor,self.fonte=estado,motor,fonte
        self.op=opcoes or OpcoesDistribuidas();self.simulado=simulado;self.agora=relogio
        self.lock=estado.lock;self.sessao=None;self.geracao=0;self.processamento='embarcado'
        self.operacao='parado';self.fonte_controle='nenhuma';self.fase='PARADO'
        self.algoritmo='opencv';self.versao_modelo=versao_opencv();self.versao_opencv=self.versao_modelo
        self.emergencia=False;self.lease=None;self.pedido=None;self.resultado=None
        self.frames=OrderedDict();self.ultimo_frame=-1;self.contas=Counter()
        self.tempos=deque(maxlen=512);self.eventos=deque(maxlen=256)
        self.remoto_pronto=None;self.ultimo_heartbeat=None;self.dono_inferencia=None
        self.stop_status='aceita';self.stop_t=self.agora();self.amostra_parada=None
        self.min_frame_t=self.agora();self.ultima_troca=float('-inf');self.ultimo_motivo=None
        self.estado._autoridade_rede=self

    def ligar(self,sessao):
        with self.lock:self.sessao=sessao

    def evento(self,tipo,**dados):
        self.eventos.append(dict(id=str(uuid.uuid4()),tipo=tipo,mono_s=self.agora(),timestamp=datetime.now(timezone.utc).isoformat(),sessao=self.sessao,
                                geracao=self.geracao,simulado=self.simulado,**dados))

    def invalidar(self):
        self.geracao+=1;self.frames.clear();self.resultado=None;self.ultimo_frame=-1
        self.min_frame_t=self.agora()

    def parar(self,motivo,emergencia=False):
        with self.lock:
            self.estado.definir_modo(Modo.PARADO);self.lease=None;self.pedido=None
            self.operacao='parado';self.fonte_controle='seguranca' if emergencia else 'nenhuma'
            self.emergencia=self.emergencia or emergencia
            self.fase='EMERGENCIA' if self.emergencia else 'PARADO'
            self.stop_status='aceita';self.stop_t=self.agora();self.amostra_parada=None
            self.invalidar();self.evento('parada_aceita',motivo=motivo)
            self.ultimo_motivo=motivo

    def motivo_sensor(self):
        s=self.motor.sensores();d=self.motor.estado_motores();a=self.agora()
        if s is None or d is None or not 0<=a-s.timestamp<=cfg.SENSOR_TIMEOUT_S or not 0<=a-d.timestamp<=cfg.SENSOR_TIMEOUT_S:return 'arduino_ou_telemetria_indisponivel'
        if d.falha_encoder:return 'falha_encoder'
        if getattr(d,'manual_sem_ultrassom',False):return 'aguardando_ultrassom_apos_bluetooth'
        if s.falha_sensor:return 'falha_ultrassom'
        v=s.distancia_cm
        if type(v) not in (int,float) or not math.isfinite(v) or v<0:return 'distancia_invalida'
        if s.avanco_bloqueado or v<cfg.OBSTACULO_DIST_CM:return 'obstaculo_ou_guarda_frontal'
        return None

    def parada_confirmada(self):
        s=self.motor.sensores();d=self.motor.estado_motores();a=self.agora()
        if self.estado.modo is not Modo.PARADO or s is None or d is None:return False
        if not 0<=a-s.timestamp<=cfg.SENSOR_TIMEOUT_S or not 0<=a-d.timestamp<=cfg.SENSOR_TIMEOUT_S or d.falha_encoder:return False
        if d.pwm_esq or d.pwm_dir:self.amostra_parada=None;return False
        ticks=(s.ticks_esq,s.ticks_dir)
        if self.amostra_parada is None or ticks!=self.amostra_parada[1]:self.amostra_parada=(a,ticks);return False
        return a-self.amostra_parada[0]>=.1

    def supervisionar(self):
        """Chamado a 20 Hz pelo controlador, sob estado.lock; nunca espera rede."""
        with self.lock:
            a=self.agora()
            if self.emergencia and self.estado.modo is not Modo.PARADO:self.estado.definir_modo(Modo.PARADO)
            dependente=self.fonte_controle in ('pc_manual','autonomo_distribuido')
            if dependente:
                motivo=self.motivo_sensor()
                if self.fonte_controle=='pc_manual':
                    if not self.lease or a>self.lease['ate'] or self.pedido is None or a-self.pedido['t']>self.op.comando_s:motivo=motivo or 'deadman_expirado'
                else:
                    if self.ultimo_heartbeat is None or a-self.ultimo_heartbeat>self.op.autorizacao_s:motivo=motivo or 'heartbeat_inferencia_expirado'
                    if not self.resultado:
                        if a-self.min_frame_t>self.op.resultado_s:motivo=motivo or 'resultado_expirado'
                    elif a-self.resultado['frame_t']+self.resultado['idade_inicial']>self.op.resultado_s:motivo=motivo or 'resultado_expirado'
                    elif self.resultado['dados']['linha_visivel'] is not True:motivo=motivo or 'linha_perdida'
                    if self.fonte.saude()['status']!='ok':motivo=motivo or 'camera_indisponivel'
                if motivo:self.parar(motivo)
            if self.estado.modo is Modo.PARADO:
                if self.parada_confirmada():
                    if self.stop_status!='confirmada_pelos_dados':self.evento('parada_confirmada_pelos_dados',confirmacao='F8/PWM informado zero e ticks estáveis; não mede frenagem independente')
                    self.stop_status='confirmada_pelos_dados'
                elif a-self.stop_t>2:self.stop_status='falha_na_confirmacao'

    def registrar_frame(self,ident,quadro):
        with self.lock:
            t=quadro.recepcao_monotonica;idade=quadro.idade_recepcao_limite_ms/1000
            meta=dict(geracao=self.geracao,sessao_visao=self.estado.sessao_visao,
                      geracao_camera=getattr(quadro,'geracao',self.fonte.saude()['geracao']),frame_t=t,idade_inicial=idade)
            self.frames[ident]=meta
            while len(self.frames)>self.op.frames:self.frames.popitem(last=False)
            return {k:meta[k] for k in ('geracao','sessao_visao','geracao_camera')}

    def receber_resultado(self,d,cliente):
        with self.lock:
            try:
                if d.get('contrato')!=CONTRATO or d.get('geracao')!=self.geracao:raise ValueError('geracao_ou_contrato')
                ident=d['frame_id'];r=d['resultado'];f=self.frames.get(ident)
                permitidos={'linha_visivel','posicao','erro','confianca','direcao','escala_direcao','motivo','roi','entrada','preprocessamento_s',
                    'inferencia_s','acao','semantica','algoritmo','versao_modelo','navegavel','processamento_s','dimensoes','decodificacao_s','tempo_pc_s'}
                if not isinstance(r,dict) or set(r)-permitidos:raise ValueError('campos_de_resultado_nao_permitidos')
                if type(ident)is not int or f is None:raise ValueError('frame_desconhecido')
                if ident<=self.ultimo_frame:raise ValueError('frame_duplicado_ou_fora_de_ordem')
                if f['geracao']!=self.geracao or d.get('sessao_visao')!=f['sessao_visao'] or f['sessao_visao']!=self.estado.sessao_visao:raise ValueError('sessao_visual_antiga')
                if f['frame_t']<self.min_frame_t:raise ValueError('frame_anterior_a_habilitacao')
                if self.fonte.saude()['status']!='ok' or f['geracao_camera']!=self.fonte.saude()['geracao']:raise ValueError('camera_reconectada_ou_indisponivel')
                idade=self.agora()-f['frame_t']+f['idade_inicial']
                if not 0<=idade<=self.op.resultado_s:raise ValueError('resultado_atrasado')
                uuid.UUID(d['inferencia_id'])
                if not self.remoto_pronto or cliente!=self.dono_inferencia:raise ValueError('fonte_nao_autorizada')
                if r['algoritmo']!=self.algoritmo or r['versao_modelo']!=self.versao_modelo:raise ValueError('modelo_incompativel')
                for k in ('processamento_s','inferencia_s'):real(r[k],0,60)
                if r.get('preprocessamento_s') is not None:real(r['preprocessamento_s'],0,60)
                if r.get('posicao') is not None:real(r['posicao'],-1,1)
                if r.get('erro') is not None:real(r['erro'],-1,1)
                if r.get('confianca') is not None:real(r['confianca'],0,1)
                if r.get('direcao') is not None:real(r['direcao'],-10,10)
                if r.get('escala_direcao') is not None:real(r['escala_direcao'],0,100)
                if r.get('linha_visivel') is not None and type(r['linha_visivel'])is not bool:raise ValueError('linha_invalida')
                # O payload não pode promover pesos offline/RL a modelo navegável.
                navegavel=(self.algoritmo=='opencv' and r.get('navegavel')is True)
                if navegavel and r['linha_visivel'] and r.get('erro') is None:raise ValueError('erro_ausente')
                if navegavel and (type(r['linha_visivel'])is not bool or r.get('confianca') is None):raise ValueError('validade_opencv_ausente')
                if navegavel and (r.get('direcao') is None or r.get('escala_direcao') is None):raise ValueError('geometria_opencv_ausente')
                if not isinstance(r.get('motivo'),str) or len(r['motivo'])>300:raise ValueError('motivo_invalido')
                ciclo=self.agora()-f['frame_t']
                self.ultimo_frame=ident;self.contas['resultados_aceitos']+=1;self.tempos.append(ciclo)
                from monitoramento import observar
                observar('distribuido.ciclo_s',idade);observar('distribuido.inferencia_s',r['inferencia_s'])
                self.resultado=dict(dados=dict(r),frame_id=ident,frame_t=f['frame_t'],idade_inicial=f['idade_inicial'],inferencia_id=d['inferencia_id'])
                self.evento('resultado_aceito',frame_id=ident,resultado=r,idade_resultado_s=idade,latencia_total_s=ciclo,inferencia_id=d['inferencia_id'])
                if self.processamento=='distribuido' and self.operacao=='autonomo' and navegavel:
                    self.estado.publicar_leitura(r.get('erro') or 0.,r['linha_visivel'],timestamp=f['frame_t'],
                        idade_captura_s=f['idade_inicial'],frame_id=ident,geracao_camera=f['geracao_camera'],
                        sessao=f['sessao_visao'],camera_ok=True,direcao=r['direcao'],escala_direcao=r['escala_direcao'],confianca=r['confianca'],motivo=r['motivo'])
                return True
            except (ValueError,KeyError,TypeError,AttributeError) as exc:
                self.contas['resultados_rejeitados']+=1;self.evento('resultado_rejeitado',motivo=str(exc),frame_id=d.get('frame_id'))
                # Rejeição não renova a validade. Uma resposta antiga que já
                # estava em trânsito não cancela uma observação nova válida;
                # a supervisão independente para ao esgotar o prazo original.
                raise ValueError('Resultado rejeitado: '+str(exc)) from exc

    def local_publicar(self,ident,quadro,r):
        with self.lock:
            if self.processamento!='embarcado':return
            if quadro.recepcao_monotonica<max(self.min_frame_t,self.estado._sessao_visao_inicio):return
            if self.estado.modo is Modo.SEGUINDO:
                self.estado.publicar_leitura(r.get('erro') or 0.,r['linha_visivel'] is True,
                    timestamp=quadro.recepcao_monotonica,idade_captura_s=quadro.idade_recepcao_limite_ms/1000,
                    frame_id=ident,geracao_camera=getattr(quadro,'geracao',0),camera_ok=True,
                    direcao=r['direcao'],escala_direcao=r['escala_direcao'],confianca=r['confianca'] or 0.,motivo=r['motivo'])
            self.local_resultado=r

    def comando(self,d,cliente,permissoes):
        with self.lock:
            if d.get('contrato')!=CONTRATO:raise ValueError('Contrato de operação inválido')
            if set(d)-{'contrato','geracao','acao','algoritmo','versao_modelo','modo','autorizacao','direcao','velocidade_pps','desafio','motivo'}:raise ValueError('Campo operacional não permitido')
            acao=d.get('acao');a=self.agora()
            if acao=='consulta':return self.snapshot()
            if acao=='falha_percepcao':
                if 'percepcao' not in permissoes:raise ValueError('Sem permissão de percepção')
                if self.fonte_controle=='autonomo_distribuido':self.parar('falha_percepcao_remota')
                self.evento('falha_percepcao_remota',motivo=str(d.get('motivo','falha'))[:500]);return self.snapshot()
            if acao=='pronto':
                if 'percepcao' not in permissoes:raise ValueError('Sem permissão de percepção')
                if self.dono_inferencia not in (None,cliente):raise ValueError('Outro provedor de percepção já conectado')
                if d.get('algoritmo')!=self.algoritmo:raise ValueError('Algoritmo divergente')
                if not isinstance(d.get('versao_modelo'),str) or len(d['versao_modelo'])>128:raise ValueError('Versão inválida')
                if self.algoritmo=='opencv' and d['versao_modelo']!=self.versao_opencv:raise ValueError('Versão/parâmetros OpenCV não correspondem ao pipeline configurado')
                if self.operacao!='parado' and self.versao_modelo!=d['versao_modelo']:raise ValueError('Versão não pode mudar durante movimento')
                self.dono_inferencia=cliente;self.remoto_pronto=a;self.ultimo_heartbeat=a;self.versao_modelo=d['versao_modelo'];return self.snapshot()
            if acao=='heartbeat':
                if cliente!=self.dono_inferencia or 'percepcao' not in permissoes:raise ValueError('Heartbeat sem provedor autorizado')
                self.ultimo_heartbeat=a;return self.snapshot()
            if 'controle' not in permissoes:raise ValueError('Sem permissão de controle')
            if not self.simulado and not self.op.remoto_real:raise ValueError('Controle real bloqueado até validação física explícita')
            if acao in ('parar','emergencia'):
                self.parar('pedido_operador',acao=='emergencia');return self.snapshot()
            if acao=='liberar_emergencia':
                if 'administrar' not in permissoes or not self.parada_confirmada() or self.motivo_sensor():raise ValueError('Liberação exige administrador, parada e sensores válidos')
                self.emergencia=False;self.parar('emergencia_liberada');return self.snapshot()
            if self.emergencia:raise ValueError('Emergência retida nesta sessão')
            if d.get('geracao')!=self.geracao:raise ValueError('Geração de comando antiga')
            if acao in ('modo','algoritmo'):
                if 'administrar' not in permissoes:raise ValueError('Alteração exige administrador')
                if not self.parada_confirmada():
                    self.parar('troca_solicitada');self.fase='AGUARDANDO_PARADA';raise ValueError('Parada solicitada; confirme e solicite novamente')
                if self.motivo_sensor():raise ValueError('Segurança indisponível')
                if a-self.ultima_troca<.5:raise ValueError('Aguarde estabilização da troca')
                novo=d.get('modo',self.processamento)
                if novo not in ('embarcado','distribuido'):raise ValueError('Modo inválido')
                if novo=='distribuido' and (not self.simulado and not self.op.distribuido_real):raise ValueError('Distribuição real bloqueada')
                if novo=='distribuido' and (self.remoto_pronto is None or self.ultimo_heartbeat is None or a-self.ultimo_heartbeat>self.op.autorizacao_s):raise ValueError('Percepção remota não está pronta')
                algoritmo=d.get('algoritmo',self.algoritmo)
                if algoritmo not in ('opencv','cnn-fotos','cnn-rl'):raise ValueError('Algoritmo inválido')
                self.parar('mudanca_de_modo');self.processamento=novo
                self.tempos.clear()
                if algoritmo!=self.algoritmo:self.algoritmo=algoritmo;self.remoto_pronto=None;self.dono_inferencia=None
                self.ultima_troca=a;self.fase='PRONTO_PARADO';self.evento('modo_alterado',processamento=novo,algoritmo=algoritmo)
                return self.snapshot()
            if acao=='habilitar':
                if self.lease or self.estado.modo is not Modo.PARADO:raise ValueError('Autoridade ocupada; pare antes de transferir')
                if not self.parada_confirmada() or self.motivo_sensor():raise ValueError('Parada/sensores ainda não confirmados')
                self.invalidar();self.lease=dict(id=str(uuid.uuid4()),cliente=cliente,ate=a+self.op.autorizacao_s)
                self.fonte_controle='pc_manual';self.operacao='manual';self.fase='HABILITADO'
                self.pedido=dict(direcao='parar',velocidade_pps=0.,t=a);self.evento('controle_habilitado',origem='pc_manual')
            elif acao=='movimento':
                if not self.lease or self.lease['cliente']!=cliente or d.get('autorizacao')!=self.lease['id'] or a>self.lease['ate']:raise ValueError('Autorização exclusiva ausente ou expirada')
                if d.get('direcao') not in ('frente','re','esquerda','direita','parar'):raise ValueError('Direção inválida')
                velocidade=real(d.get('velocidade_pps'),0,self.op.velocidade_max_pps)
                if self.motivo_sensor():self.parar('bloqueio_sensor');raise ValueError('Movimento bloqueado por sensor')
                self.lease['ate']=a+self.op.autorizacao_s;self.pedido=dict(direcao=d['direcao'],velocidade_pps=velocidade,t=a)
                self.estado.definir_modo(Modo.REMOTO_PC);self.evento('comando_aceito',direcao=d['direcao'],velocidade_pps=velocidade)
            elif acao=='siga':
                if not self.parada_confirmada() or self.lease or self.motivo_sensor():raise ValueError('Fonte ocupada ou parada/sensores não confirmados')
                if self.algoritmo!='opencv':raise ValueError('Modelo CNN/RL disponível somente para diagnóstico; navegação não validada')
                if self.fonte.saude()['status']!='ok':raise ValueError('Câmera indisponível')
                if self.processamento=='distribuido' and (self.ultimo_heartbeat is None or a-self.ultimo_heartbeat>self.op.autorizacao_s):raise ValueError('Serviço remoto não está pronto')
                self.invalidar();self.operacao='autonomo';self.fonte_controle='autonomo_'+self.processamento
                self.estado.definir_modo(Modo.SEGUINDO);self.fase='AUTONOMO';self.evento('autonomia_habilitada',processamento=self.processamento)
            elif acao=='liberar':self.parar('controle_liberado')
            else:raise ValueError('Comando não permitido; PWM/serial indisponíveis')
            return self.snapshot()

    def local_assumir(self,origem,parada=False):
        with self.lock:
            if self.emergencia and not parada:return False
            if origem=='voz' and self.processamento=='distribuido' and not parada:return False
            if self.fonte_controle==origem and not parada:return True
            self.parar('prioridade_'+origem)
            if not parada:self.fonte_controle=origem;self.operacao='manual' if origem=='bluetooth' else 'autonomo'
            return True

    def desconectar(self,cliente):
        with self.lock:
            if self.lease and self.lease['cliente']==cliente:self.parar('operador_desconectado')
            if self.dono_inferencia==cliente:
                self.remoto_pronto=self.ultimo_heartbeat=self.dono_inferencia=None
                if self.fonte_controle=='autonomo_distribuido':self.parar('servico_inferencia_desconectado')

    def pedido_pps(self):
        with self.lock:
            self.supervisionar()
            if self.estado.modo is not Modo.REMOTO_PC or not self.pedido:return (0,0)
            v=self.pedido['velocidade_pps']
            return {'frente':(v,v),'re':(-v,-v),'esquerda':(-v,v),'direita':(v,-v),'parar':(0,0)}[self.pedido['direcao']]

    def snapshot(self,privado=False):
        with self.lock:
            a=self.agora();r=self.resultado
            dados=dict(contrato=CONTRATO,processamento=self.processamento,operacao=self.operacao,
                fonte_controle=self.fonte_controle,fase=self.fase,geracao=self.geracao,algoritmo=self.algoritmo,
                versao_modelo=self.versao_modelo,simulado=self.simulado,emergencia=self.emergencia,
                autorizacao_ativa=self.lease is not None and a<=self.lease['ate'],parada=self.stop_status,
                motivo=self.ultimo_motivo,ultimo_resultado=r['dados'] if r else None,
                frame_id=r['frame_id'] if r else None,idade_resultado_s=a-r['frame_t']+r['idade_inicial'] if r else None,
                remoto_pronto=self.ultimo_heartbeat is not None and a-self.ultimo_heartbeat<=self.op.autorizacao_s,
                contadores=dict(self.contas),frames_registrados=len(self.frames),limite_frames=self.op.frames,
                latencias_s=list(self.tempos),limites=asdict(self.op),local_resultado=getattr(self,'local_resultado',None),eventos=list(self.eventos)[-12:])
            if privado and self.lease:dados['autorizacao']=self.lease['id']
            return dados
