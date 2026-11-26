"""Regressões da revisão A–D: sem serial, áudio ou rede física."""
import io
import json
import math
from email.message import Message
from pathlib import Path
import struct
import subprocess
import sys
import threading
import time
import zipfile
from unittest.mock import Mock,patch
import cv2
import numpy as np
import pytest


def test_jpeg_hostil_rejeitado_antes_da_alocacao():
    from visao.esp32_cam import receber_quadro
    # SOF declara resolução enorme num corpo de poucos bytes.
    jpeg=b'\xff\xd8\xff\xc0\x00\x11\x08\xff\xff\xff\xff\x03'+b'\x01\x11\x00'*3+b'\xff\xd9'
    resposta=io.BytesIO(jpeg);resposta.status=200;resposta.headers=Message()
    resposta.headers['Content-Type']='image/jpeg';resposta.headers['X-Frame-Age-Us']='0'
    opener=Mock();opener.open.return_value=resposta
    with patch('visao.esp32_cam.cv2.imdecode') as dec:
        with pytest.raises(ValueError,match='antes do decode'):receber_quadro(opener,'http://camera-falsa',1)
        dec.assert_not_called()


def test_png_hostil_e_formato_falso_nao_alocam_pixels(tmp_path):
    from visao.jpeg import ler_imagem_limitada
    p=tmp_path/'grande.png';p.write_bytes(b'\x89PNG\r\n\x1a\n'+b'\x00\x00\x00\rIHDR'+struct.pack('>II',65000,65000)+b'\x08\x02\x00\x00\x00'+b'\x00'*4)
    with patch('cv2.imdecode') as dec:
        with pytest.raises(ValueError,match='antes do decode'):ler_imagem_limitada(p)
        dec.assert_not_called()
    p.write_bytes(b'texto, nao PNG')
    with pytest.raises(ValueError,match='Cabeçalho'):ler_imagem_limitada(p)


def test_imagem_local_valida_preserva_pixels(tmp_path):
    from visao.jpeg import ler_imagem_limitada
    imagem=np.full((40,80,3),123,np.uint8);p=tmp_path/'pequena.png';p.write_bytes(cv2.imencode('.png',imagem)[1].tobytes())
    assert np.array_equal(ler_imagem_limitada(p),imagem)


def test_captura_http_tem_taxa_limitada_sem_fila():
    from visao.esp32_cam import CameraESP32
    jpeg=cv2.imencode('.jpg',np.full((240,320,3),150,np.uint8))[1].tobytes()
    class HTTP:
        n=0
        def open(self,*a,**kw):
            self.n+=1;r=io.BytesIO(jpeg);r.status=200;r.headers=Message();r.headers['Content-Type']='image/jpeg';r.headers['X-Frame-Age-Us']='0';return r
    http=HTTP();c=CameraESP32(opener=http,fps_max=4);inicio=time.monotonic();c.iniciar()
    try:
        assert c.proximo_quadro(0,2) is not None;time.sleep(.8)
        assert 2<=http.n<=math.ceil((time.monotonic()-inicio)*4)+1
        assert c.estatisticas['fps_max_configurado']==4
    finally:c.parar()
    assert not c._thread.is_alive()


def test_telemetria_de_dominio_incompativel_nao_e_exibida(tmp_path):
    from gemeo_digital.integracao import Ponte
    p=Ponte(tmp_path)
    try:
        assert not p.receber({'simulado':False},time.monotonic(),p.epoch)
        assert p.snapshot()['aviso_origem'] and not p.snapshot()['dados']['disponivel']
        p.modo='real'
        assert not p.receber({'simulado':True},time.monotonic(),p.epoch)
        assert not p.snapshot()['dados']['disponivel']
    finally:p.fechar()


def test_experimento_bloqueado_nao_vira_concluido_e_restaura_taxas(tmp_path):
    from central_monitoramento.central import Central
    c=Central(tmp_path,etapa6=True,arquivo_preferencias=tmp_path/'p.json')
    try:
        c.modo_alterar('simulado');op=c.op_distribuida
        c.experimentos.iniciar(dict(configuracoes=['B'],manifesto='inexistente.json',duracao_s=1,repeticoes=1,aquecimento_s=0,inferencia_hz=8,telemetria_hz=25,imagens_fps=12))
        c.experimentos.thread.join(20)
        s=c.experimentos.snapshot();assert s['estado']=='concluido_com_bloqueios' and s['resultados']=={'bloqueada':1}
        assert c.telemetria_hz==10 and c.imagens_fps==5 and c.camera_fps==30 and c.op_distribuida==op
        assert c.fluxo.integrado.motor.pps==(0.,0.) and not c.escritor_externo.op.imagens
    finally:c.fechar()


def test_integridade_cancelada_nao_e_aprovada(tmp_path):
    from experimentos.executor import verificar_integridade,Cancelado
    e=threading.Event();e.set()
    with pytest.raises(Cancelado):verificar_integridade(tmp_path,e)


def test_queda_de_thread_da_main_retorna_erro_e_para(monkeypatch):
    import main
    from motor.nulo import ArduinoNulo
    motor=ArduinoNulo();motor.parar=Mock(wraps=motor.parar)
    class Thread:
        def __init__(self,*a,**kw):pass
        def start(self):pass
        def is_alive(self):return False
        def join(self,**kw):pass
    monkeypatch.setattr(sys,'argv',['main.py','--sem-arduino','--fonte-imagem','nenhuma','--sem-voz','--sem-bluetooth'])
    monkeypatch.setattr(main,'ArduinoNulo',lambda:motor)
    monkeypatch.setattr(main,'ThreadControle',Thread);monkeypatch.setattr(main,'ThreadVisao',Thread)
    monkeypatch.setattr(main.signal,'signal',lambda *a:None)
    with pytest.raises(RuntimeError,match='thread essencial'):main.main()
    assert motor.parar.call_count>=2 and motor.ultimo==(0,0)


def test_pacote_pi_sem_dados_pc_e_importacao_minima(tmp_path):
    from tools.preparar_pacote_pi import preparar
    r=preparar(tmp_path/'pacotes')
    with zipfile.ZipFile(r['pacote']) as z:
        nomes=z.namelist()
        assert not any(n.startswith(('central_monitoramento/','armazenamento/','gemeo_digital/','dados_')) or n.endswith(('.glb','.csv','.db')) for n in nomes)
        manifesto=json.loads(z.read('manifesto_pacote.json'))
        import hashlib
        assert all(hashlib.sha256(z.read(n)).hexdigest()==h for n,h in manifesto['arquivos_sha256'].items())
        assert 'dataset_pista/resultados/treino_posicao_02/pesos_posicao.npz' in nomes
        assert b'\r\n' not in z.read('deploy/iniciar_raspberry.sh')
        pasta=tmp_path/'extraido';z.extractall(pasta)
    codigo="""import sys,runpy,importlib.abc
class Bloquear(importlib.abc.MetaPathFinder):
 def find_spec(self,nome,*args):
  if nome.split('.')[0] in ('sounddevice','sklearn','joblib','scipy','matplotlib','torch','gymnasium'):raise ImportError('Dependência pesada não permitida no perfil mínimo: '+nome)
sys.meta_path.insert(0,Bloquear());sys.argv=['main.py','--help'];runpy.run_path('main.py',run_name='__main__')
"""
    proc=subprocess.run([sys.executable,'-c',codigo],cwd=pasta,capture_output=True,text=True,timeout=15)
    assert proc.returncode==0,proc.stderr


def test_runner_sem_dependencia_solicitada_nao_retorna_sucesso(tmp_path,monkeypatch):
    from tools import testes
    monkeypatch.setattr(sys,'argv',['testes','interface','--saida',str(tmp_path)])
    def indisponivel(*args,**kwargs):raise FileNotFoundError('node ausente no teste')
    monkeypatch.setattr(testes.subprocess,'run',indisponivel)
    with pytest.raises(SystemExit) as exc:testes.main()
    assert exc.value.code==2
    assert json.loads((tmp_path/'resultado.json').read_text())['resultados'][0]['estado']=='bloqueado'
