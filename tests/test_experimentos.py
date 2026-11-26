"""Métricas científicas e executor integrado sobre dispositivos virtuais."""
import json
import math
from pathlib import Path
import tempfile
import threading
import time
import uuid
import pytest
from experimentos.analise import resumo,regressao,diferenca,pareado,resposta_degrau,odometria,criterios
from experimentos.configuracao import validar
from experimentos.repositorio import comparar,listar,obter


def test_nulos_e_percentis_nao_inventam_zeros():
    assert resumo([None,float('nan'),True])['media'] is None
    r=resumo([1,2,3]);assert r['media']==2 and r['desvio_padrao']==1 and r['p99'] is None
    assert resumo(list(range(100)))['p99']==pytest.approx(98.01)
    assert resumo([0,0])['cv'] is None


def test_regressao_continua_e_r2_constante():
    r=regressao([1,2,3],[2,2,2]);assert r['mae']==pytest.approx(2/3) and r['rmse']==pytest.approx(math.sqrt(2/3)) and r['r2']==0
    assert regressao([1,1],[1,1])['r2'] is None
    assert regressao([None],[1])['n']==0
    with pytest.raises(ValueError):regressao([1],[])


def test_denominadores_e_bootstrap_repeticoes():
    assert diferenca(0,1)['reducao_pct'] is None
    assert diferenca(1,0)['speedup'] is None
    assert diferenca(4,2)['speedup']==2
    with pytest.raises(ValueError):pareado([1]*4,[2]*4)
    r=pareado([1,2,3,4,5],[2,3,4,5,6]);assert r['ic95_bootstrap']==[1,1] and r['efeito_dz'] is None


def test_degrau_subida_acomodacao_e_horizonte():
    r=resposta_degrau([0,1,2,3,4,5],[0,.1,.9,1,1,1],0,1)
    assert r['subida_10_90_s']==1 and r['acomodacao_s']==3 and r['sobressinal_pct']==0
    assert resposta_degrau([0,1,2],[0,.3,1],0,1)['acomodacao_s'] is None
    with pytest.raises(ValueError):resposta_degrau([0,0],[0,1],0,1)


def test_odometria_referencia_e_angulo_circular():
    r=odometria([[0,0,math.pi-.01],[1,0,-math.pi+.01]],[[0,0,-math.pi+.01],[1.1,0,math.pi-.01]])
    assert r['erro_final_m']==pytest.approx(.1) and abs(r['erro_orientacao_rad']['media'])<1e-8
    with pytest.raises(ValueError):odometria([],[])


def test_configuracao_rejeita_real_nan_e_movimento():
    assert validar({})['repeticoes']==5
    for d in ({'origem':'real'},{'duracao_s':float('nan')},{'nivel':5},{'configuracoes':['A','A']},{'condicoes':{'velocidade_referencia_pps':4}},{'resolucao':[320,240]}):
        with pytest.raises(ValueError):validar(d)
    assert criterios({'x':None},{'x':{'maximo':1}})['x']['resultado']=='não avaliado'


def linha(k,media,**extra):
    return dict(configuracao=k,estado='concluida',origem='simulada',nivel=3,categoria='benchmark_integrado',
                configuracoes=validar({}),resultado={'metricas':{'inferencia_s':{'media':media}}},**extra)


def test_comparacao_por_execucao_e_dominios():
    rows=[linha('A',1),linha('A',3),linha('C',1)]
    r=comparar(rows,'inferencia_s');assert r['itens'][0]['n']==2 and r['itens'][0]['media']==2
    rows[0]['nivel']=5;assert not comparar(rows,'inferencia_s')['comparavel']
    rows[0]['nivel']=3;rows[0]['configuracoes']={**rows[0]['configuracoes'],'resolucao':[320,240]}
    assert not comparar(rows,'inferencia_s')['comparavel']
    rows=[linha('A',1),linha('C',2)];rows[0]['ambiente']={'cpu':'outro host'}
    assert not comparar(rows,'inferencia_s')['comparavel']


@pytest.mark.integracao
def test_executor_grava_sessao_csv_relatorio_e_mantem_parado(tmp_path):
    from central_monitoramento.central import Central
    from experimentos.relatorios import gerar
    c=Central(tmp_path,etapa6=True,arquivo_preferencias=tmp_path/'prefs.json')
    try:
        c.modo_alterar('simulado');time.sleep(.2)
        c.experimentos.iniciar(dict(nome='Teste integrado',configuracoes=['A','C'],duracao_s=2,repeticoes=1,aquecimento_s=.1))
        with pytest.raises(ValueError):c.modo_alterar('real')
        with pytest.raises(ValueError):c.experimentos.iniciar({})
        c.experimentos.thread.join(30);assert not c.experimentos.snapshot()['ativo']
        assert c.experimentos.snapshot()['estado']=='concluido',c.experimentos.snapshot()
        rows=listar(tmp_path);assert len(rows)==2 and all(r['estado']=='concluida' for r in rows),rows
        assert len({r['sessao_id'] for r in rows})==2
        assert all(r['resultado']['metricas']['inferencia_s']['n']>0 for r in rows)
        assert all(r['resultado']['metricas']['controle_hz']['n']>0 for r in rows)
        assert all(r['resultado']['integridade']['integrity_check']=='ok' for r in rows)
        assert c.fluxo.integrado.motor.pps==(0.,0.) and c.fluxo.integrado.autoridade.lease is None
        e=obter(tmp_path,rows[0]['id']);assert (tmp_path/e['artefato_relativo']/'amostras.csv').exists()
        r=gerar(tmp_path,e['id'],'Interpretação de teste <script>');assert 'relatorio.zip' in r['arquivos']
        html=(tmp_path/e['artefato_relativo']/'relatorio.html').read_text(encoding='utf-8');assert '&lt;script&gt;' in html
    finally:c.fechar()


@pytest.mark.seguranca
def test_cancelamento_encerra_sem_autorizar_e_rejeita_real(tmp_path):
    from central_monitoramento.central import Central
    c=Central(tmp_path,etapa6=True,arquivo_preferencias=tmp_path/'prefs.json')
    try:
        c.modo_alterar('simulado');c.experimentos.iniciar(dict(configuracoes=['A'],duracao_s=20,repeticoes=1,aquecimento_s=5))
        time.sleep(.1);c.experimentos.parar();c.experimentos.thread.join(15)
        assert c.experimentos.snapshot()['estado']=='cancelado'
        assert c.fluxo.integrado.autoridade.lease is None and c.fluxo.integrado.estado.modo.name=='PARADO'
        with pytest.raises(ValueError):c.experimentos.iniciar({'origem':'real'})
    finally:c.fechar()


def test_timeout_do_escritor_preserva_pedido_pendente(tmp_path):
    from types import SimpleNamespace
    from armazenamento.gravador import Gravador
    from armazenamento.configuracao import OpcoesArmazenamento
    from comunicacao.distribuidor import Distribuidor
    g=Gravador(Distribuidor(),OpcoesArmazenamento(tmp_path))
    g.thread=SimpleNamespace(is_alive=lambda:True)
    with pytest.raises(TimeoutError,match='pode continuar em execução'):
        g.comandar('sincronizar',prazo_s=.001)
    tipo,dados,futuro=g.pedidos.get_nowait()
    assert tipo=='sincronizar' and not futuro.done() and not futuro.cancelled()


def test_execucao_orfa_recuperada_sem_inventar_fim(tmp_path):
    from central_monitoramento.central import Central
    from datetime import datetime,timezone
    c=Central(tmp_path,arquivo_preferencias=tmp_path/'prefs.json')
    eid=c.escritor_externo.comandar('experimento',nome='Órfão simulado')
    ident=str(uuid.uuid4())
    c.escritor_externo.comandar('execucao_experimental',id=ident,experimento_id=eid,sessao_id=None,
        configuracao='A',repeticao=1,origem='simulada',nivel=3,categoria='benchmark_integrado',inicio_utc=datetime.now(timezone.utc).isoformat(),
        fim_utc=None,estado='executando',configuracoes_json='{}',ambiente_json='{}',resultado_json='{}',artefato_relativo='experimentos/'+ident)
    c.fechar()
    outra=Central(tmp_path,arquivo_preferencias=tmp_path/'prefs.json')
    try:
        r=obter(tmp_path,ident);assert r['estado']=='falha' and r['fim_utc'] is None
        assert 'desconhecidos' in r['resultado']['erro']
    finally:outra.fechar()


def test_csv_cientifico_exige_referencia_e_identifica_dados_sinteticos(tmp_path):
    from experimentos.graficos import analisar
    arquivo=tmp_path/'pares.csv';arquivo.write_text('real,previsto\n0,0.1\n0.5,0.4\n',encoding='utf-8')
    with pytest.raises(ValueError,match='referência independente'):
        analisar(arquivo,tmp_path/'sem_ref','regressao','simulada',1)
    r=analisar(arquivo,tmp_path/'saida','regressao','simulada',1,'Alvos sintéticos definidos no teste')
    assert r['metricas']['mae']==pytest.approx(.1) and r['origem']=='simulada'
    assert (tmp_path/'saida/analise.svg').is_file()
