"""Etapa6: algoritmos reais, rede loopback e motores virtuais. Sem serial física."""
from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import time
from types import SimpleNamespace
import uuid

import cv2
import numpy as np
import pytest
from estado import EstadoRobo,Modo
from distribuido.autoridade import Autoridade
from distribuido.configuracao import CONTRATO,OpcoesDistribuidas,opcoes_aprovadas
from distribuido.percepcao import Pipeline,PercepcaoLocal,PercepcaoRemota,decodificar_jpeg
from central_monitoramento.central import Central
from armazenamento.banco import conectar
from controle import aplicar_movimento_manual,aplicar_comando

RAIZ=Path(__file__).resolve().parents[1]
PAPEIS={'percepcao','controle','administrar'}

class Relogio:
    def __init__(self):self.t=100.
    def __call__(self):return self.t
    def avancar(self,v):self.t+=v

class Motor:
    def __init__(self,r):self.r=r;self.distancia=100.;self.falha=False;self.encoder=False;self.arduino=True;self.ticks=0;self.ultimo=(0,0)
    def sensores(self):return SimpleNamespace(timestamp=self.r(),distancia_cm=self.distancia,falha_sensor=self.falha,avanco_bloqueado=self.distancia<25,ticks_esq=self.ticks,ticks_dir=self.ticks) if self.arduino else None
    def estado_motores(self):return SimpleNamespace(timestamp=self.r(),falha_encoder=self.encoder,pwm_esq=self.ultimo[0],pwm_dir=self.ultimo[1]) if self.arduino else None
    def motores(self,e,d):self.ultimo=(e,d)
    def parar(self,**kw):self.ultimo=(0,0)

@pytest.fixture
def autoridade():
    r=Relogio();estado=EstadoRobo();motor=Motor(r);camera=SimpleNamespace(saude=lambda:dict(status='ok',geracao=0))
    a=Autoridade(estado,motor,camera,simulado=True,relogio=r);a.ligar(str(uuid.uuid4()))
    a.comando(dict(contrato=CONTRATO,acao='pronto',algoritmo='opencv',versao_modelo=a.versao_modelo),'pc',PAPEIS)
    return a,r,motor

def cmd(a,acao,**dados):return a.comando(dict(contrato=CONTRATO,geracao=a.geracao,acao=acao,**dados),'pc',PAPEIS)

def repousar(a,r):
    a.parada_confirmada();r.avancar(.11);assert a.parada_confirmada()

def resultado(a,r,ident=1):
    a.registrar_frame(ident,SimpleNamespace(recepcao_monotonica=r(),idade_recepcao_limite_ms=0.,geracao=0))
    return dict(contrato=CONTRATO,geracao=a.geracao,sessao_visao=a.estado.sessao_visao,
        frame_id=ident,inferencia_id=str(uuid.uuid4()),resultado=dict(algoritmo='opencv',versao_modelo=a.versao_modelo,
        navegavel=True,linha_visivel=True,posicao=.2,erro=.2,confianca=.8,direcao=0.,escala_direcao=.75,
        motivo='teste_contrato',processamento_s=.001,inferencia_s=.001,preprocessamento_s=None))

def test_inicio_parado_e_zero_credenciais_no_snapshot(autoridade):
    a,r,m=autoridade
    assert a.estado.modo is Modo.PARADO and not a.snapshot()['autorizacao_ativa']
    assert not any(k in json.dumps(a.snapshot()) for k in ('Bearer','token','autorizacao"'))

@pytest.mark.parametrize('campo,valor',[
    ('frame_id',999),('frame_id',True),('geracao',-1),('sessao_visao',999),('contrato','outro'),('inferencia_id','x')])
def test_resultados_incompativeis_recusados(autoridade,campo,valor):
    a,r,m=autoridade;d=resultado(a,r);d[campo]=valor
    with pytest.raises(ValueError):a.receber_resultado(d,'pc')
    assert a.snapshot()['contadores']['resultados_rejeitados']==1

@pytest.mark.parametrize('campo,valor',[
    ('navegavel',False),('erro',float('nan')),('posicao',float('inf')),('posicao',1.1),('confianca',-1),
    ('algoritmo','cnn-fotos'),('versao_modelo','outros-pesos'),('linha_visivel',1),('inferencia_s',-1),('direcao',99),('confianca',None),('linha_visivel',None)])
def test_saida_invalida_recusada(autoridade,campo,valor):
    a,r,m=autoridade;d=resultado(a,r);d['resultado'][campo]=valor
    with pytest.raises(ValueError):a.receber_resultado(d,'pc')

def test_temporalidade_usa_relogio_original_e_nao_o_pc(autoridade):
    a,r,m=autoridade;d=resultado(a,r);d['timestamp_pc']=1e12
    r.avancar(.1);a.receber_resultado(d,'pc')
    assert a.snapshot()['idade_resultado_s']==pytest.approx(.1)
    with pytest.raises(ValueError):a.receber_resultado(d,'pc')
    d=resultado(a,r,2);r.avancar(.31)
    with pytest.raises(ValueError,match='atrasado'):a.receber_resultado(d,'pc')

def test_frame_da_geracao_anterior_e_ordem(autoridade):
    a,r,m=autoridade;d=resultado(a,r);a.invalidar()
    with pytest.raises(ValueError):a.receber_resultado(d,'pc')
    d1=resultado(a,r,4);d2=resultado(a,r,5);a.receber_resultado(d2,'pc')
    with pytest.raises(ValueError):a.receber_resultado(d1,'pc')

def test_mudanca_de_modo_exige_parada_sem_retomada(autoridade):
    a,r,m=autoridade;a.estado.definir_modo(Modo.SEGUINDO);m.ultimo=(20,20)
    with pytest.raises(ValueError,match='Parada solicitada'):cmd(a,'modo',modo='distribuido')
    assert a.estado.modo is Modo.PARADO and a.processamento=='embarcado'
    m.ultimo=(0,0);repousar(a,r);cmd(a,'modo',modo='distribuido')
    assert a.estado.modo is Modo.PARADO and a.fonte_controle=='nenhuma'
    with pytest.raises(ValueError):cmd(a,'modo',modo='embarcado')

def test_exclusividade_deadman_e_sem_retomada(autoridade):
    a,r,m=autoridade;repousar(a,r);cmd(a,'habilitar');lease=a.lease['id']
    with pytest.raises(ValueError):cmd(a,'habilitar')
    with pytest.raises(ValueError):cmd(a,'movimento',autorizacao='errada',direcao='frente',velocidade_pps=2)
    cmd(a,'movimento',autorizacao=lease,direcao='frente',velocidade_pps=2)
    assert a.pedido_pps()==(2,2)
    r.avancar(.31);a.supervisionar()
    assert a.estado.modo is Modo.PARADO and a.lease is None
    with pytest.raises(ValueError):cmd(a,'movimento',autorizacao=lease,direcao='frente',velocidade_pps=2)

@pytest.mark.parametrize('falha',['obstaculo','sensor','arduino','encoder'])
def test_falhas_interrompem_movimento_da_rede(autoridade,falha):
    a,r,m=autoridade;repousar(a,r);cmd(a,'habilitar');lease=a.lease['id']
    cmd(a,'movimento',autorizacao=lease,direcao='frente',velocidade_pps=2)
    if falha=='obstaculo':m.distancia=12
    elif falha=='sensor':m.falha=True
    elif falha=='arduino':m.arduino=False
    else:m.encoder=True
    a.supervisionar();assert a.estado.modo is Modo.PARADO and a.lease is None

def test_emergencia_retida_bloqueia_bt_voz_e_exige_liberacao_validada(autoridade):
    a,r,m=autoridade;cmd(a,'emergencia')
    aplicar_movimento_manual(a.estado,m,20,20);aplicar_comando(a.estado,m,'siga')
    assert a.estado.modo is Modo.PARADO and m.ultimo==(0,0)
    with pytest.raises(ValueError):cmd(a,'habilitar')
    with pytest.raises(ValueError):cmd(a,'liberar_emergencia')
    repousar(a,r);cmd(a,'liberar_emergencia')
    assert not a.emergencia and a.estado.modo is Modo.PARADO

def test_bluetooth_preempta_pc_preserva_renovacao_e_nao_ignora_emergencia(autoridade):
    a,r,m=autoridade;repousar(a,r);cmd(a,'habilitar')
    assert a.local_assumir('bluetooth') and a.lease is None
    geracao=a.geracao;assert a.local_assumir('bluetooth');assert a.geracao==geracao

def test_sem_monitor_nao_para_autonomia_embarcada(autoridade):
    a,r,m=autoridade;repousar(a,r);cmd(a,'siga');a.desconectar('pc');a.supervisionar()
    assert a.estado.modo is Modo.SEGUINDO and a.processamento=='embarcado'

def test_distribuido_para_por_resultado_ou_heartbeat_vencido(autoridade):
    a,r,m=autoridade;repousar(a,r);cmd(a,'modo',modo='distribuido');repousar(a,r);cmd(a,'siga')
    d=resultado(a,r);a.receber_resultado(d,'pc');r.avancar(.31);a.supervisionar()
    assert a.estado.modo is Modo.PARADO and a.ultimo_motivo=='resultado_expirado'

def test_reconexao_nao_rearma(autoridade):
    a,r,m=autoridade;repousar(a,r);cmd(a,'modo',modo='distribuido');repousar(a,r);cmd(a,'siga');a.desconectar('pc')
    assert a.estado.modo is Modo.PARADO
    a.comando(dict(contrato=CONTRATO,acao='pronto',algoritmo='opencv',versao_modelo=a.versao_modelo),'novo',PAPEIS)
    assert a.estado.modo is Modo.PARADO and a.lease is None

def test_modo_real_bloqueado_por_padrao_e_papeis(autoridade):
    a,r,m=autoridade;a.simulado=False
    with pytest.raises(ValueError,match='bloqueado'):cmd(a,'habilitar')
    with pytest.raises(ValueError):a.comando(dict(contrato=CONTRATO,acao='emergencia'),'monitor',{'monitorar'})
    assert not opcoes_aprovadas().remoto_real
    with pytest.raises(ValueError,match='parâmetros'):
        a.comando(dict(contrato=CONTRATO,acao='pronto',algoritmo='opencv',versao_modelo='opencv_com_configuracao_diferente'),'pc',PAPEIS)

def imagens_fixas():
    imagens=[]
    for x in (140,220,330):
        img=np.full((640,480,3),220,np.uint8)
        cv2.line(img,(x,639),(x+12,0),(20,20,20),12)
        for y in range(50,640,80):img[y:y+18]=220
        ok,jpeg=cv2.imencode('.jpg',img);assert ok
        imagens.append(decodificar_jpeg(jpeg.tobytes())[0])
    return imagens

def test_equivalencia_opencv_matriz_identica_sem_alterar_parametros(monkeypatch):
    local=PercepcaoLocal(Pipeline());remoto=PercepcaoRemota(Pipeline())
    for img in imagens_fixas():
        a,b=local.processar(img),remoto.processar(img)
        for k in ('linha_visivel','posicao','erro','roi','entrada','direcao','confianca','semantica'):assert a[k]==b[k]
    import config as configuracao
    original=local.pipeline.versao
    monkeypatch.setattr(configuracao,'ROI_INICIO',configuracao.ROI_INICIO+.01)
    assert Pipeline().versao!=original

def test_cnn_existente_equivalente_sem_confianca_nem_navegacao():
    manifesto=RAIZ/'dataset_pista/resultados/treino_posicao_02/experimento.json'
    if not (manifesto.parent/'pesos_posicao.npz').exists():pytest.skip('Pesos próprios locais ausentes')
    a=Pipeline('cnn-fotos',manifesto);b=Pipeline('cnn-fotos',manifesto)
    for img in imagens_fixas():
        p,q=a.processar(img),b.processar(img)
        assert abs(p['posicao']-q['posicao'])<=1e-6
        assert p['confianca'] is None and p['linha_visivel'] is None and not p['navegavel']
    with pytest.raises(ValueError,match='recorte'):a.processar(np.zeros((240,320,3),np.uint8))

def test_pesos_ausentes_e_rl_ausente_nao_geram_pesos_aleatorios(tmp_path):
    with pytest.raises((ValueError,OSError)):Pipeline('cnn-fotos',tmp_path/'ausente.json')
    with pytest.raises(ValueError):Pipeline('cnn-rl')

def test_jpeg_com_dimensao_excessiva_recusado_antes_de_alocar_pixels():
    jpeg=b'\xff\xd8\xff\xc0\x00\x0b\x08'+(60000).to_bytes(2,'big')+(60000).to_bytes(2,'big')+b'\x01\x01\x11\x00\xff\xd9'
    with pytest.raises(ValueError,match='antes do decode'):decodificar_jpeg(jpeg)

def esperar(fn,prazo=5):
    fim=time.monotonic()+prazo
    while time.monotonic()<fim:
        v=fn()
        if v:return v
        time.sleep(.02)
    raise AssertionError('Condição não observada no prazo')

@pytest.fixture
def integrado(tmp_path):
    c=Central(tmp_path/'historico',etapa6=True,arquivo_preferencias=tmp_path/'pref.json')
    c.modo_alterar('simulado');op=c.fluxo.operacao
    esperar(lambda:op.snapshot()['remoto'].get('parada')=='confirmada_pelos_dados' and op.snapshot()['remoto'].get('remoto_pronto'))
    yield c,op
    c.fechar()

def test_ciclo_real_de_software_por_websocket_e_gravacao_na_mesma_base(integrado):
    c,op=integrado;c.gravacao_comando({'acao':'iniciar'})
    op.comandar({'acao':'modo','modo':'distribuido'})
    esperar(lambda:op.snapshot()['contadores'].get('frames_processados',0)>=2)
    op.comandar({'acao':'siga'})
    esperar(lambda:c.fluxo.integrado.motor.ultimo!=(0,0))
    assert c.fluxo.integrado.motor.autor_escrita=={'controle'}
    op.pausa_inferencia=True
    esperar(lambda:c.fluxo.integrado.estado.modo is Modo.PARADO)
    assert c.fluxo.integrado.autoridade.ultimo_motivo=='resultado_expirado'
    esperar(lambda:c.historico.consultar('percepcao_remota'))
    resumo=c.consultas.resumo(c.estado.sessao)
    assert resumo['estatisticas']['ciclo_distribuido']['n']>0
    assert resumo['estatisticas']['inferencia_percepcao']['media']>0
    assert c.historico.consultar('operacao_rede_eventos')
    c.escritor_externo.sincronizar()
    with closing(conectar(c.historico.raiz)) as banco:assert banco.execute('PRAGMA integrity_check').fetchone()[0]=='ok'

def test_aba_exclusiva_e_deadman_pela_rede(integrado):
    c,op=integrado;aba=str(uuid.uuid4());op.comandar({'acao':'habilitar'},operador=aba)
    op.comandar({'acao':'movimento','direcao':'frente','velocidade_pps':2},operador=aba)
    with pytest.raises(ValueError):op.comandar({'acao':'movimento','direcao':'frente','velocidade_pps':2},operador=str(uuid.uuid4()))
    esperar(lambda:c.fluxo.integrado.estado.modo is Modo.PARADO)
    assert c.fluxo.integrado.motor.ultimo==(0,0)

def test_emergencia_na_rede_rejeita_rearme_automatico(integrado):
    c,op=integrado;op.comandar({'acao':'emergencia'})
    with pytest.raises(ValueError):op.comandar({'acao':'habilitar'})
    assert c.fluxo.integrado.autoridade.emergencia

def test_filas_limitadas_sob_inferencia_lenta(integrado):
    c,op=integrado;op.comandar({'acao':'modo','modo':'distribuido'});op.atraso_s=.6
    time.sleep(1.4);s=op.snapshot()
    assert s['fila_frames']<=1 and s['fila_resultados']<=1 and s['fila_comandos']<=16
    assert s['descartes_frames']>0

def test_equivalencia_do_jpeg_que_atravessou_a_rede(integrado):
    c,op=integrado;rt=c.fluxo.integrado
    rt.camera.imagem_teste=imagens_fixas()[1]
    op.comandar({'acao':'modo','modo':'distribuido'})
    esperar(lambda:rt.autoridade.resultado and rt.autoridade.resultado['dados']['dimensoes']==[640,480])
    remoto=rt.autoridade.resultado['dados'];frame=rt.camera.quadro.imagem
    local=Pipeline().processar(frame)
    assert remoto['roi']==local['roi'] and remoto['entrada']==local['entrada']
    assert remoto['linha_visivel']==local['linha_visivel']
    assert remoto['erro']==pytest.approx(local['erro'],abs=1e-6)

def test_canal_operacional_exige_privilegios_separados(integrado):
    import asyncio
    from websockets.asyncio.client import connect
    from websockets.exceptions import InvalidStatus
    c,op=integrado;f=c.fluxo
    async def verificar():
        for token in ('errado',f.op.token):
            with pytest.raises(InvalidStatus):
                async with connect(f.url+'/ws/operacao',additional_headers={'Authorization':'Bearer '+token}):pass
    asyncio.run(verificar())

def test_permissao_de_percepcao_nao_concede_controle_e_desafio_expira(integrado):
    import asyncio
    from websockets.asyncio.client import connect
    from comunicacao.protocolo import decodificar,codificar,envelope
    c,op=integrado;f=c.fluxo
    async def verificar():
        for papel in ('percepcao','controle'):
            headers={'Authorization':'Bearer '+f.op.token,'X-Robo-'+papel:f.servidor.operacao.tokens[papel]}
            async with connect(f.url+'/ws/operacao',additional_headers=headers) as ws:
                ola=decodificar(await ws.recv())
                if papel=='controle':await asyncio.sleep(.35)
                dados=dict(contrato=CONTRATO,acao='habilitar',geracao=ola['dados']['estado']['geracao'],desafio=ola['dados']['desafio'])
                msg=envelope(ola['sessao'],1,'comando',dados,True,'computador')
                await ws.send(codificar(msg));res=decodificar(await ws.recv())['dados']
                assert not res['ok']
                if papel=='controle':assert 'Desafio expirado' in res['erro']
                else:assert 'permissão' in res['erro']
                await ws.send(codificar(msg));repetido=decodificar(await ws.recv())['dados'];assert not repetido['ok']
        assert c.fluxo.integrado.estado.modo is Modo.PARADO
    asyncio.run(verificar())

def test_frames_mais_antigos_que_habilitacao_nao_rejuvenescem(autoridade):
    a,r,m=autoridade;d=resultado(a,r);a.min_frame_t=r()+.01
    with pytest.raises(ValueError,match='anterior'):a.receber_resultado(d,'pc')

def test_fila_de_frames_tem_limite_rigido(autoridade):
    a,r,m=autoridade
    for i in range(200):resultado(a,r,i)
    assert len(a.frames)==a.op.frames

def test_heartbeat_ausente_para_mesmo_com_resultado_recente(autoridade):
    a,r,m=autoridade;repousar(a,r);cmd(a,'modo',modo='distribuido');repousar(a,r);cmd(a,'siga')
    r.avancar(.7);a.receber_resultado(resultado(a,r),'pc');a.supervisionar()
    assert a.estado.modo is Modo.PARADO and a.ultimo_motivo=='heartbeat_inferencia_expirado'


def test_confirmacao_da_parada_anterior_nao_aparece_durante_movimento(autoridade):
    a,r,m=autoridade;repousar(a,r);a.supervisionar()
    assert a.snapshot()['parada']=='confirmada_pelos_dados'
    cmd(a,'habilitar');cmd(a,'movimento',autorizacao=a.lease['id'],direcao='frente',velocidade_pps=2)
    assert a.snapshot()['parada']=='nao_solicitada'
    cmd(a,'parar');assert a.snapshot()['parada']=='aceita'
