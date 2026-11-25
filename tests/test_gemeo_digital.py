"""Etapa 4: física sintética, HTTP loopback e reuso do histórico; sem hardware."""
from copy import deepcopy
from datetime import datetime,timedelta
import json,math,threading,time,uuid
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from pathlib import Path
import pytest
from gemeo_digital.cinematica import Calibracao,Odometria
from gemeo_digital.estado_visual import EstadoVisual
from gemeo_digital.integracao import Ponte,CAL_SIM
from gemeo_digital.simulacao import Cenario,MotorCenario
from gemeo_digital.servidor import Aplicacao
from gemeo_digital.analise_modelo import analisar,ler
from comunicacao.protocolo import envelope
from comunicacao.simulacao import CameraSimulada
from monitoramento.telemetria import Telemetria

def mensagem(seq=0,t=1.,ticks=(0,0),sinais=(1,1),sessao=None):
    def c(v):return dict(valor=v,estado='atual')
    m={}
    for i,l in enumerate(('esq','dir')):
        m.update({f'ticks_{l}':c(ticks[i]),f'pwm_{l}':c(sinais[i]*100),f'pps_{l}':c(10)})
    q=envelope(sessao or SID,seq,'telemetria',dict(telemetria=dict(motores=m,sensores={})),True,'simulador');q['monotonic_s']=t
    return q
SID=str(uuid.uuid4())

@pytest.mark.parametrize('sinais,ticks,esperado',[
 ((1,1),(10,10),(.1021017612,0)),((-1,-1),(10,10),(-.1021017612,0)),
 ((-1,1),(10,10),(0,0)),((1,1),(5,10),(None,None))])
def test_cinematica_reta_re_curva_giro(sinais,ticks,esperado):
    o=Odometria(CAL_SIM);o.atualizar(0,0,1,sinais);p=o.atualizar(*ticks,1.1,sinais)
    assert p['validade']=='estimativa'
    if esperado[0] is not None:assert p['x_m']==pytest.approx(esperado[0],abs=1e-9);assert p['y_m']==pytest.approx(esperado[1])
    if ticks[0]!=ticks[1] or sinais[0]!=sinais[1]:assert p['orientacao_rad']>0

def test_sem_calibracao_e_sem_integrar_lacuna():
    o=Odometria(Calibracao());assert o.atualizar(10,10,1,(1,1))['validade']=='sem_calibracao'
    o=Odometria(CAL_SIM);o.atualizar(0,0,1,(1,1));assert o.atualizar(100,100,3,(1,1))['x_m']==0
    o.invalidar();assert o.atualizar(200,200,3.1,(1,1))['x_m']==0
    o.resetar();assert o.trajeto==[]

def test_memoria_trajeto_limitada_e_inversao():
    o=Odometria(CAL_SIM)
    for i in range(2500):o.atualizar(i,i,1+i*.1,(1,1))
    assert len(o.trajeto)==2000
    x=o.x;assert o.atualizar(2501,2501,251,(-1,-1))['x_m']==x

def test_mensagens_invalidas_antigas_e_troca_sessao():
    e=EstadoVisual(CAL_SIM)
    for q in [None,{},dict(tipo='telemetria'),mensagem(t=float('nan'))]:assert not e.aceitar(q)
    q=mensagem();q['dados']['telemetria']['motores']['ticks_esq']['valor']='ruim';assert not e.aceitar(q)
    assert e.aceitar(mensagem());assert not e.aceitar(mensagem())
    assert e.aceitar(mensagem(1,1.1,(1,2)));assert e.angulos!=[0,0]
    assert not e.snapshot(1)['disponivel'];assert e.base is None
    assert e.aceitar(mensagem(sessao=str(uuid.uuid4())));assert e.angulos==[0,0]

def test_simulador_timestamp_valido_sem_hardware():
    c=Cenario();camera=CameraSimulada();t=Telemetria(camera.estado,MotorCenario(c),camera,simulado=True).coletar()
    assert t['motores']['ticks_esq']['estado']=='atual';assert t['sensores']['angulo_servo_graus']['estado']=='atual'
    c.atualizar(dict(geometria=True,obstaculo_z=-1.));assert c.distancia()==pytest.approx(94.)
    c.atualizar(dict(obstaculo_x=2));assert c.distancia()==400
    with pytest.raises(ValueError):c.atualizar(dict(esq=float('nan')))

def test_restaurar_odometria_preserva_calibracao_e_reset_de_referencia():
    e=EstadoVisual(CAL_SIM)
    e.aceitar(mensagem());e.aceitar(mensagem(1,1.1,(10,10)))
    assert e.odom.distancia>0
    p=dict(x_m=0.,y_m=0.,orientacao_rad=0.,distancia_m=0.,velocidade_linear_m_s=0.,
           velocidade_angular_rad_s=0.,validade='estimativa',natureza='simulada',calibracao_json=json.dumps(CAL_SIM.__dict__))
    assert e.restaurar_pose(p);assert e.odom.distancia==0;assert e.odom.trajeto==[[0.,0.]]
    p['x_m']=float('nan');assert not e.restaurar_pose(p)

def test_calibracao_recusa_bools_numericos_e_relacao_invalida():
    from dataclasses import replace
    assert not replace(CAL_SIM,ppr_esq=True).valida()
    assert not replace(CAL_SIM,relacao_disco_roda=float('nan')).valida()
    assert not replace(CAL_SIM,simulada=False).valida()

def test_glb_original_componentes_hierarquia_e_hash():
    p=Path(__file__).resolve().parents[1]/'gemeo_digital/modelos/carrinho_configurado.glb'
    if not p.exists():pytest.skip('GLB original é um recurso local, veja README do gêmeo')
    d=analisar(p);assert d['nos']==313;assert d['quantidade_materiais']==37
    assert d['sha256']=='e2713914a205bfa6504aae3830a67766ad5f1592c5a825660b1677184571a52b'
    assert d['componentes']['servo_eixo'];assert d['eixos']['roda_esquerda']['eixo_local_geometrico'][1]>.99

def esperar(fn,prazo=5):
    fim=time.monotonic()+prazo
    while time.monotonic()<fim:
        v=fn()
        if v:return v
        time.sleep(.02)
    raise AssertionError('Condição não observada')

def test_fluxo_existente_http_isolamento_falha_e_replay(tmp_path):
    p=Ponte(tmp_path,gravar=True);app=Aplicacao(p,0);th=threading.Thread(target=app.serve_forever,daemon=True);th.start()
    url=f'http://127.0.0.1:{app.server_port}'
    def post(rota,d,token=True):
        return json.load(urlopen(Request(url+rota,json.dumps(d).encode(),headers={'X-Gemeo-Token':app.token if token else '', 'Content-Type':'application/json'})))
    try:
        p.modo_alterar('simulado');esperar(lambda:p.snapshot()['dados']['disponivel'])
        with pytest.raises(HTTPError) as e:post('/api/simulacao',{'esq':10},False)
        assert e.value.code==403
        post('/api/simulacao',{'esq':10,'dir':5});esperar(lambda:p.snapshot()['dados']['pose']['distancia_m']>.002)
        q=p.snapshot();sessao=q['dados']['envelope']['sessao'];assert p.fluxo.servidor.simulado
        post('/api/simulacao',{'falha':True});esperar(lambda:not p.snapshot()['dados']['disponivel']);assert p.snapshot()['dados']['omega_rad_s']==[0,0]
        post('/api/simulacao',{'falha':False});esperar(lambda:p.snapshot()['dados']['disponivel'])
        p.fluxo.gravador.sincronizar();assert p.historico.consultar('odometria',sessao=sessao)
        p.modo_alterar('historico');assert p.fluxo is None
        with pytest.raises(ValueError):p.simular({'esq':20})
        p.historico_selecionar(sessao);info=next(s for s in p.sessoes() if s['id']==sessao)
        alvo=(datetime.fromisoformat(info['inicio_observado_utc'])+timedelta(seconds=.3)).isoformat()
        p.controle_replay(dict(acao='buscar',instante=alvo));a=deepcopy(p.estado.angulos)
        p.controle_replay(dict(acao='buscar',instante=alvo));assert p.estado.angulos==a
        assert p.snapshot()['replay']['pausado'];assert len(p.trajeto_sessao(sessao)['pontos'])>0
        from armazenamento.reproducao import Reprodutor
        assert any(r['categoria']=='odometria' for r in Reprodutor(p.historico,sessao).registros())
        with pytest.raises(HTTPError):post('/api/mover',{'pwm':100})
        with pytest.raises(ValueError):p.modo_alterar('real')
    finally:app.shutdown();app.server_close();p.fechar();th.join(2)
