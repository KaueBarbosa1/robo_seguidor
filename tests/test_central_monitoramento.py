"""Central no PC, SQLite temporário e tráfego loopback; nenhum hardware."""
from contextlib import closing
from datetime import datetime,timezone,timedelta
from io import BytesIO
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import json,threading,time,zipfile
import pytest
from central_monitoramento.central import Central
from central_monitoramento.servidor import AplicacaoCentral
from armazenamento.banco import conectar

def esperar(fn,prazo=6):
    fim=time.monotonic()+prazo
    while time.monotonic()<fim:
        v=fn()
        if v:return v
        time.sleep(.03)
    raise AssertionError('Condição não observada')

@pytest.fixture
def ambiente(tmp_path):
    b=Central(tmp_path/'historico',arquivo_preferencias=tmp_path/'preferencias.json')
    app=AplicacaoCentral(b,0);t=threading.Thread(target=app.serve_forever,daemon=True);t.start()
    base=f'http://127.0.0.1:{app.server_port}'
    def get(p):return json.load(urlopen(base+p,timeout=10))
    def post(p,d,token=True,origem=None):
        headers={'Content-Type':'application/json','X-Gemeo-Token':app.token if token else ''}
        if origem:headers['Origin']=origem
        return json.load(urlopen(Request(base+p,json.dumps(d).encode(),headers=headers),timeout=15))
    yield b,app,base,get,post
    app.shutdown();app.server_close();b.fechar();t.join(2)

def iniciar_gravado(b):
    b.modo_alterar('simulado');esperar(lambda:b.snapshot()['dados']['disponivel'])
    b.gravacao_comando({'acao':'iniciar','nome':'Ensaio sintético'})
    b.cenario_comando({'acao':'iniciar','cenario':'seguimento'})
    esperar(lambda:b.escritor_externo.contas['persistidas']>=3)
    b.escritor_externo.sincronizar();return b.estado.sessao

def test_inicializacao_reutiliza_html_modelo_e_migracao(ambiente):
    b,app,url,get,post=ambiente
    html=urlopen(url).read().decode()
    assert 'RS · Central de operações' in html and html.count('id="cena"')==1
    assert html.count('importmap')==1
    assert b.historico.estado()['versao']==5
    with closing(conectar(b.historico.raiz)) as c:
        plano=' '.join(str(tuple(r)) for r in c.execute("EXPLAIN QUERY PLAN SELECT rtt_s FROM comunicacao WHERE telemetria_id=1 AND lado='servidor' LIMIT 1"))
        assert 'idx_comunicacao_telemetria' in plano
        plano=' '.join(str(tuple(r)) for r in c.execute("EXPLAIN QUERY PLAN SELECT cpu_pct FROM desempenho WHERE sessao_id='x' AND dispositivo='servidor' ORDER BY id DESC LIMIT 1"))
        assert 'idx_desempenho_ultimo' in plano and 'TEMP B-TREE' not in plano
    assert urlopen(url+'/gemeo').status==200
    assert urlopen(url+'/central/src/nucleo.js').status==200

def test_quadro_rejeita_instancia_de_servidor_anterior(ambiente):
    b,app,url,get,post=ambiente
    with pytest.raises(HTTPError) as exc:urlopen(url+'/api/quadro?epoch=0&instancia=servidor-antigo')
    assert exc.value.code==409
    assert get('/api/estado')['instancia']==b.instancia

def test_gravacao_metadados_experimento_associacao_e_filtros(ambiente):
    b,app,url,get,post=ambiente;sid=iniciar_gravado(b)
    post('/api/central/sessao-metadados',{'sessao':sid,'nome':'Curva no PC','observacoes':'Sem teste físico'})
    eid=post('/api/central/experimento',{'nome':'Experimento CNN/OpenCV','objetivo':'Comparar',
        'modo':'simulacao','configuracoes':{'hipotese':'Exploratória'},'repeticao':2})['resultado']
    post('/api/central/associar',{'experimento':eid,'sessoes':[sid]})
    assert get('/api/central/sessoes?busca=Curva')['itens'][0]['nome']=='Curva no PC'
    assert b.historico.consultar('consolidado',experimento=eid)
    assert get('/api/central/experimentos')[0]['sessoes']==[sid]
    resumo=get('/api/central/resumo?sessao='+sid)
    assert resumo['resumo']['amostras']>=3 and resumo['estatisticas']['pps_esq']['n']>0
    assert 'q1' in resumo['estatisticas']['pps_esq']

def test_exportacao_csv_resumo_zip_e_protecao_caminhos(ambiente):
    b,app,url,get,post=ambiente;sid=iniciar_gravado(b)
    r=post('/api/central/exportar',{'categorias':['consolidado','motores','odometria','eventos'],'filtros':{'sessao':sid}})['resultado']
    pacote=urlopen(url+r['url']).read()
    with zipfile.ZipFile(BytesIO(pacote)) as z:
        assert 'consolidado.csv' in z.namelist() and 'resumo_limitacoes.json' in z.namelist()
        assert z.read('motores.csv').startswith(b'\xef\xbb\xbf')
        assert json.loads(z.read('manifesto.json'))['linhas']['consolidado']>=3
    with pytest.raises(HTTPError):get('/api/central/download?id=../../config.py')
    with pytest.raises(HTTPError):post('/api/central/exportar',{'categorias':['sqlite_master'],'filtros':{}})

def test_exportacao_multiplas_sessoes_separa_arquivos(ambiente):
    b,app,url,get,post=ambiente;sid=iniciar_gravado(b)
    r=post('/api/central/exportar',{'categorias':['consolidado'],'sessoes':[sid]})['resultado']
    with zipfile.ZipFile(BytesIO(urlopen(url+r['url']).read())) as z:assert sid+'/consolidado.csv' in z.namelist()

def test_evidencias_cnn_somente_leitura_sem_treino(ambiente):
    b,app,url,get,post=ambiente
    r=get('/api/central/treinos')
    assert any(t['id']=='treino_posicao_02' for t in r)
    for t in r:
        assert t['entrada']==[1,40,80]
        assert t['uso_no_robo_aprovado'] is False
        assert len(t['curva'])<=5000 and t['metricas']['teste']['n']>0
    assert b.escritor_externo.gravacao is None

def test_buffers_replay_busca_gravacao_nao_retorna_automaticamente(ambiente):
    b,app,url,get,post=ambiente;sid=iniciar_gravado(b)
    b.modo_alterar('historico');assert b.escritor_externo.gravacao is None
    b.historico_selecionar(sid);row=b.consultas.sessoes({})['itens'][0]
    b.historico_selecionar(sid,row['fim_observado_utc'])
    s=b.snapshot();assert s['replay']['pausado'] and s['status']=='histórico'
    janela=b.consultas.janela(sid,row['fim_observado_utc'],60,10)
    assert janela['amostras_origem']>=3 and len(janela['itens'])<=10
    assert all(isinstance(r['t'],(int,float)) for r in janela['itens'])
    with pytest.raises(HTTPError):post('/api/central/cenario',{'acao':'emergencia'})
    with pytest.raises(HTTPError):post('/api/central/gravacao',{'acao':'iniciar'})
    b.modo_alterar('simulado');assert b.escritor_externo.gravacao is None

def test_alertas_por_transicao_e_resolucao_persistidas(ambiente):
    b,app,url,get,post=ambiente;iniciar_gravado(b)
    b.cenario_comando({'acao':'iniciar','cenario':'obstaculo'})
    esperar(lambda:b.alarmes.get('obstaculo',{}).get('ativo'))
    n=sum(e['chave']=='obstaculo' for e in b.ocorrencias)
    for i in range(5):b._avaliar(b.snapshot())
    assert sum(e['chave']=='obstaculo' for e in b.ocorrencias)==n
    b.simular({'distancia':100.});esperar(lambda:not b.alarmes['obstaculo']['ativo'])
    b.escritor_externo.sincronizar()
    assert any(r['categoria']=='central_obstaculo' for r in b.historico.consultar('eventos'))

def test_falhas_sinteticas_camera_arduino_emergencia(ambiente):
    b,app,url,get,post=ambiente;b.modo_alterar('simulado');esperar(lambda:b.estado.msg)
    b.simular({'arduino':False,'camera':False});esperar(lambda:b.alarmes.get('arduino',{}).get('ativo'))
    esperar(lambda:b.alarmes.get('camera',{}).get('ativo'))
    b.cenario_comando({'acao':'emergencia'});esperar(lambda:b.alarmes.get('emergencia',{}).get('ativo'))
    b.simular({'esq':20.,'dir':20.,'arduino':True})
    esperar(lambda:b.estado.msg['dados']['telemetria']['motores']['pwm_esq']['valor']==0)
    b.cenario_comando({'acao':'iniciar','cenario':'normal'});assert not b.cenario.ler()['emergencia']

def test_seguranca_tokens_origem_e_sem_controles_reais(ambiente):
    b,app,url,get,post=ambiente
    for token,origem in [(False,None),(True,'https://site-externo.example')]:
        with pytest.raises(HTTPError) as e:post('/api/central/cenario',{'acao':'emergencia'},token,origem)
        assert e.value.code==403
    with pytest.raises(HTTPError):post('/api/central/pwm',{'pwm':255})
    with pytest.raises(ValueError):b.modo_alterar('real')
    assert not b.snapshot()['central']['remoto_real'] and not b.snapshot()['central']['distribuido_real']
    with pytest.raises(ValueError):b.conexao_configurar('ws://usuario:segredo@host:1234')

def test_preferencias_opcoes_e_validacao_atomica(ambiente):
    b,app,url,get,post=ambiente
    post('/api/central/preferencias',{'tema':'claro','janela_s':30,'graficos_hz':1})
    assert b.pre_path.exists() and b.preferencias['tema']=='claro'
    with pytest.raises(HTTPError):post('/api/central/preferencias',{'tema':'escuro','janela_s':-1})
    assert b.preferencias['tema']=='claro'
    post('/api/central/armazenamento',{'imagens':True,'imagens_fps':1.,'max_bytes':104857600})
    assert b.escritor_externo.op.imagens
    with pytest.raises(HTTPError):post('/api/central/armazenamento',{'imagens':True,'imagens_fps':-1})
    assert b.escritor_externo.op.imagens_fps==1

def test_cenario_valida_tudo_antes_de_alterar_e_nao_aceita_distribuido_real(ambiente):
    b,app,url,get,post=ambiente;b.modo_alterar('simulado')
    antes=b.cenario.ler()
    with pytest.raises(ValueError):b.simular({'esq':20.,'processamento':'hack'})
    assert b.cenario.ler()==antes
    b.simular({'processamento':'distribuido','descartar_cada':2})
    assert not b.snapshot()['central']['distribuido_real']
    assert b.fluxo.servidor.falhas['descartar_cada']==2

def test_comparacao_separa_dominios_e_nao_inventa_metricas(ambiente):
    b,app,url,get,post=ambiente;sid=iniciar_gravado(b)
    q=post('/api/central/comparar',{'sessoes':[sid]})['resultado']
    assert q['itens'][0]['sessao']['simulado']==1
    assert q['itens'][0]['estatisticas']['temperatura']['media']==48.
    assert q['itens'][0]['estatisticas']['cpu']['media']==32.
    assert 'exploratória' in q['natureza']
    with pytest.raises(HTTPError):post('/api/central/comparar',{'sessoes':[sid]*7})
