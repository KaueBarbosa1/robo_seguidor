"""SQLite temporário e tráfego localhost. Sem hardware nem dados experimentais reais."""
import asyncio
import csv
from dataclasses import replace
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from armazenamento.banco import conectar,caminho_banco,Exclusivo
from armazenamento.configuracao import OpcoesArmazenamento
from armazenamento.gravador import Gravador
from armazenamento.consultas import Historico
from armazenamento.migracoes import migrar
from armazenamento.normalizacao import utc
from armazenamento.exportacao import exportar
from armazenamento.backup import criar,restaurar
from armazenamento.reproducao import Reprodutor
from armazenamento.gestao import criar_experimento,anotar
from comunicacao.distribuidor import Distribuidor
from comunicacao.protocolo import envelope
from comunicacao.simulacao import CameraSimulada,telemetria_simulada


def mensagem(sid,seq,obstaculo=False,simulado=True,frame=None):
    camera = CameraSimulada()
    camera.estado.publicar_leitura(.2,True,frame_id=frame)
    t = telemetria_simulada(camera).coletar()
    for chave,v in [('obstaculo_confirmado',obstaculo),('avanco_bloqueado',obstaculo)]:
        t['sensores'][chave].update(valor=v,estado='atual')
    d = dict(schema='benchmark_robo_v1',telemetria=t,sistema={'valores':{'cpu_total_pct':25.,'ram_pct':30.,
        'temperatura_c':None}},sistema_monotonic_s=1.,sistema_host='fixture',sistema_plataforma='teste',
        sistema_natureza='simulado',pedidos={},tempos_s={})
    msg = envelope(sid,seq,'telemetria',d,simulado,'simulador' if simulado else 'raspberry')
    msg['recepcao_utc']=utc()
    msg['idade_limite_recepcao_s']=.01
    return msg,None,time.monotonic()


def imagem(sid,seq,frame=1):
    import cv2,numpy as np
    ok,jpeg = cv2.imencode('.jpg',np.full((240,320,3),180,np.uint8))
    jpeg=jpeg.tobytes()
    msg = envelope(sid,seq,'imagem',dict(frame_id=frame,jpeg_bytes=len(jpeg)),True,'simulador')
    msg['recepcao_utc']=utc(); msg['idade_limite_recepcao_s']=.01
    return msg,jpeg,time.monotonic()


class TestHistorico(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.raiz=Path(self.tmp.name)/'dados'
        self.op=OpcoesArmazenamento(self.raiz,reserva_livre_bytes=0,intervalo_s=.02)
        self.bus=Distribuidor()
        self.g=Gravador(self.bus,self.op)
        self.g.iniciar()
        self.gid=self.g.nova_gravacao('Teste',modo='simulacao')
        self.sid=str(uuid.uuid4())
        self.h=Historico(self.raiz)

    def tearDown(self):
        self.g.fechar()
        self.tmp.cleanup()

    def enviar(self,seq,**dados):
        self.bus.publicar('telemetria',mensagem(self.sid,seq,**dados))

    def test_criacao_wal_integridade_chaves(self):
        self.assertEqual(self.h.estado()['versao'],6)
        self.assertEqual(self.h.estado()['journal'],'wal')
        self.assertEqual(self.h.integridade()['sqlite'],['ok'])
        self.assertEqual(self.h.consultar('odometria'),[])
        with closing(conectar(self.raiz,True)) as c:
            with self.assertRaises(sqlite3.IntegrityError):
                c.execute('INSERT INTO motores(telemetria_id,qualidade_json) VALUES(999,?)',('{}',))

    def test_lote_deduplicacao_null_e_desempenho_sem_repeticao(self):
        item=mensagem(self.sid,1)
        for v in [item,item,mensagem(self.sid,2)]: self.bus.publicar('telemetria',v)
        self.g.sincronizar()
        self.assertEqual(len(self.h.consultar('telemetria')),2)
        self.assertEqual(self.g.contas['duplicadas'],1)
        self.assertIsNone(self.h.consultar('motores')[0]['erro_pi'])
        self.assertIn('pedidos_observados',json.loads(self.h.consultar('motores')[0]['qualidade_json']))
        self.assertEqual(len(self.h.consultar('desempenho')),1)
        self.assertIsNone(self.h.consultar('desempenho')[0]['temperatura_c'])

    def test_eventos_nao_contam_obstaculo_repetido(self):
        for seq,obst in enumerate([False,True,True,True,False,True],1): self.enviar(seq,obstaculo=obst)
        self.g.sincronizar()
        eventos=self.h.consultar('eventos',sessao=self.sid)
        self.assertEqual(sum(e['categoria']=='obstaculo_detectado' for e in eventos),2)

    def test_pausa_retomada_encerramento(self):
        self.enviar(1); self.g.sincronizar(); self.g.pausar()
        self.enviar(2); self.g.sincronizar()
        self.g.retomar(); self.enviar(3); self.g.sincronizar()
        self.assertEqual([r['sequencia'] for r in self.h.consultar('telemetria')],[1,3])
        self.assertIsNotNone(self.h.consultar('intervalos')[0]['fim_utc'])
        self.g.encerrar()
        self.assertEqual(self.h.consultar('gravacoes')[0]['estado'],'encerrada')

    def test_duas_gravacoes_mesma_operacao_e_nome(self):
        item=mensagem(self.sid,1)
        self.bus.publicar('telemetria',item); self.g.sincronizar(); self.g.encerrar()
        segunda=self.g.nova_gravacao('Outra')
        # mesmo envelope auditável, reenfileirado após iniciar nova gravação
        self.bus.publicar('telemetria',(item[0],None,time.monotonic())); self.g.sincronizar()
        self.assertEqual(len(self.h.consultar('sessoes')),1)
        self.assertEqual(len(self.h.consultar('telemetria',gravacao=segunda)),1)

    def test_imagens_desabilitadas_por_padrao(self):
        self.bus.publicar('imagens',imagem(self.sid,1)); self.g.sincronizar()
        self.assertEqual(self.h.consultar('imagens'),[])

    def _ativar_imagens(self,**kwargs):
        self.g.fechar()
        self.bus=Distribuidor()
        self.g=Gravador(self.bus,replace(self.op,imagens=True,imagens_fps=100,**kwargs))
        self.g.iniciar(); self.gid=self.g.nova_gravacao('Imagens')

    def test_imagem_original_associacao_exata_e_temporal(self):
        self._ativar_imagens()
        self.enviar(1,frame=1)
        item=imagem(self.sid,1,frame=1)
        self.bus.publicar('imagens',item); self.g.sincronizar()
        row=self.h.consultar('imagens')[0]
        self.assertEqual((self.raiz/row['caminho']).read_bytes(),item[1])
        self.assertEqual(row['associacao_tipo'],'frame_id')
        self.assertEqual(row['sha256'],hashlib.sha256(item[1]).hexdigest())
        self.assertEqual(len(self.h.consultar('dataset')),1)
        self.assertEqual(self.h.consultar('dataset')[0]['estado_rotulo_treino'],'nao_validado')

    def test_quota_imagens_preserva_telemetria(self):
        self._ativar_imagens(max_imagens_bytes=1)
        self.enviar(1)
        self.bus.publicar('imagens',imagem(self.sid,1)); self.g.sincronizar()
        self.assertEqual(len(self.h.consultar('telemetria')),1)
        self.assertEqual(self.h.consultar('imagens'),[])
        self.assertEqual(self.g.estado,'gravando')

    def test_jpeg_corrompido_arquivo_ausente_e_hash(self):
        self._ativar_imagens()
        self.enviar(1); self.bus.publicar('imagens',imagem(self.sid,1)); self.g.sincronizar()
        row=self.h.consultar('imagens')[0]; p=self.raiz/row['caminho']
        p.write_bytes(b'corrompida')
        self.assertEqual(self.h.integridade()['problemas_imagens'][0]['erro'],'hash_divergente')
        p.unlink()
        self.assertEqual(self.h.integridade()['problemas_imagens'][0]['erro'],'imagem_ausente')

    def test_consultas_paginacao_estatisticas_e_dominio(self):
        self.enviar(1); self.enviar(2)
        outro=str(uuid.uuid4())
        self.bus.publicar('telemetria',mensagem(outro,1,simulado=False))
        self.g.sincronizar()
        self.assertEqual(len(self.h.consultar('telemetria',simulado=True)),2)
        self.assertEqual(len(self.h.consultar('telemetria',simulado=False)),1)
        self.assertEqual(len(self.h.consultar('telemetria',limite=1,pagina=1)),1)
        stats=self.h.estatistica('desempenho','cpu_pct')
        self.assertEqual(stats['simulado']['media'],25.)
        self.assertEqual(stats['real']['n'],1)
        with self.assertRaises(ValueError): self.h.consultar('telemetria; DROP TABLE sessoes')
        with self.assertRaises(ValueError): self.h.consultar('telemetria',sessao='1 OR 1=1')
        with self.assertRaises(ValueError): self.h.consultar('telemetria',limite=100000)

    def test_exportacao_consolidada_nao_duplica_amostras(self):
        self.enviar(1); self.enviar(2); self.g.sincronizar()
        pasta,n=exportar(self.h,['consolidado','sensores','odometria','experimentos'],sessao=self.sid)
        self.assertEqual(n['consolidado'],2)
        with (pasta/'consolidado.csv').open(encoding='utf-8-sig') as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['temperatura_servidor_c'],'')

    def test_backup_consistente_e_restauracao_nova(self):
        self.enviar(1); self.g.sincronizar()
        pasta=criar(self.raiz)
        nova=Path(self.tmp.name)/'restaurado'
        with self.assertRaises(ValueError): restaurar(pasta,nova)
        restaurar(pasta,nova,True)
        self.assertEqual(len(Historico(nova).consultar('telemetria')),1)
        with self.assertRaises(ValueError): restaurar(pasta,nova,True)

    def test_replay_ordem_busca_pausa_sem_hardware(self):
        self.enviar(1); self.enviar(2); self.g.sincronizar()
        r=Reprodutor(self.h,self.sid,100)
        r.pausar()
        itens=[]
        worker=threading.Thread(target=lambda:itens.extend(r.iniciar()))
        worker.start(); time.sleep(.05); self.assertEqual(itens,[])
        r.retomar(); worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertTrue(all(i['origem']=='reproducao_historica' for i in itens))
        tempos=[i['timestamp_utc'] for i in itens]; self.assertEqual(tempos,sorted(tempos))
        r.reiniciar(); self.assertGreater(len(list(r.iniciar())),0)

    def test_falha_escrita_rollback_nao_afeta_distribuidor(self):
        self.enviar(1)
        with patch.object(self.g.arquivos,'espaco',side_effect=OSError('disco cheio simulado')):
            self.g.sincronizar()
        self.assertEqual(self.g.estado,'falha')
        self.assertEqual(self.h.consultar('telemetria'),[])
        self.g.retomar(); self.enviar(2); self.g.sincronizar()
        self.assertEqual(len(self.h.consultar('telemetria')),1)

    def test_fila_limitada_e_fanout_independente(self):
        lenta=self.bus.assinar({'telemetria'},1)
        rapida=self.bus.assinar({'telemetria'},3)
        for i in range(10): self.enviar(i)
        self.assertEqual(lenta.fila.qsize(),1)
        self.assertEqual(rapida.fila.qsize(),3)
        self.assertEqual(lenta.contas['descartadas'],9)
        self.g.sincronizar()
        self.assertEqual(len(self.h.consultar('telemetria')),10)

    def test_lock_impede_segundo_gravador(self):
        outro=Gravador(Distribuidor(),self.op)
        with self.assertRaises(RuntimeError): outro.iniciar()
        outro.fechar()

    def test_migracao_preserva_dados_e_recusa_versao_futura(self):
        c=sqlite3.connect(':memory:')
        migrar(c,1)
        c.execute('INSERT INTO experimentos(id,nome,data_utc) VALUES(?,?,?)',(str(uuid.uuid4()),'antigo',utc())); c.commit()
        migrar(c)
        self.assertEqual(c.execute('SELECT nome FROM experimentos').fetchone()[0],'antigo')
        self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],6)
        c.execute('PRAGMA user_version=99')
        with self.assertRaises(ValueError): migrar(c)
        c.close()
        futura=Path(self.tmp.name)/'versao_futura'
        p=caminho_banco(futura);p.parent.mkdir(parents=True)
        c=sqlite3.connect(p);c.execute('PRAGMA user_version=99');c.close()
        hash_antes=hashlib.sha256(p.read_bytes()).hexdigest()
        with self.assertRaises(ValueError):conectar(futura,True)
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),hash_antes)

    def test_experimentos_anotacoes_e_filtro(self):
        ex=self.g.comandar('experimento',nome='Experimento',objetivo='teste',repeticao=1)
        self.g.encerrar(); self.g.nova_gravacao('Associada',experimento=ex)
        self.enviar(1); self.g.sincronizar()
        self.assertEqual(len(self.h.consultar('telemetria',experimento=ex)),1)

    def test_recuperacao_de_processo_interrompido(self):
        raiz=Path(self.tmp.name)/'crash'
        script='''import os,sys
from pathlib import Path
from comunicacao.distribuidor import Distribuidor
from armazenamento.gravador import Gravador
from armazenamento.configuracao import OpcoesArmazenamento
g=Gravador(Distribuidor(),OpcoesArmazenamento(Path(sys.argv[1]),reserva_livre_bytes=0))
g.iniciar();g.nova_gravacao('Interrompida');g.sincronizar();os._exit(0)
'''
        r=subprocess.run([sys.executable,'-c',script,str(raiz)],capture_output=True,text=True,timeout=8)
        self.assertEqual(r.returncode,0,r.stderr)
        novo=Gravador(Distribuidor(),replace(self.op,raiz=raiz)); novo.iniciar(); novo.fechar()
        row=Historico(raiz).consultar('gravacoes')[0]
        self.assertEqual(row['estado'],'interrompida')
        self.assertIsNone(row['fim_utc'])
        self.assertIsNotNone(row['recuperada_utc'])

    def test_imagem_invalida_nao_deixa_amostra_parcial(self):
        self._ativar_imagens()
        item=imagem(self.sid,1)
        self.bus.publicar('imagens',(item[0],b'quebrado',item[2]))
        self.enviar(1);self.g.sincronizar()
        self.assertEqual(self.h.consultar('imagens'),[])
        self.assertEqual(len(self.h.consultar('telemetria')),1)

    def test_backup_com_imagens_e_renomear(self):
        self._ativar_imagens()
        self.enviar(1);self.bus.publicar('imagens',imagem(self.sid,1));self.g.sincronizar();self.g.encerrar()
        self.g.fechar()
        anotar(self.raiz,self.gid,nome='Novo nome',observacoes='Anotacao')
        self.assertEqual(self.h.consultar('gravacoes')[-1]['nome'],'Novo nome')
        pasta=criar(self.raiz)
        novo=Path(self.tmp.name)/'restore_img'
        restaurar(pasta,novo,True)
        self.assertEqual(Historico(novo).integridade()['problemas_imagens'],[])

    def test_retentativa_lock_transitorio(self):
        from armazenamento import normalizacao
        original=normalizacao.telemetria
        tentativas=[]
        def uma_vez(*a,**kw):
            tentativas.append(1)
            if len(tentativas)==1:raise sqlite3.OperationalError('database is locked')
            return original(*a,**kw)
        with patch('armazenamento.gravador.norm.telemetria',side_effect=uma_vez):
            self.enviar(1);self.g.sincronizar()
        self.assertEqual(len(self.h.consultar('telemetria')),1)
        self.assertEqual(self.g.contas['retentativas'],1)

    def test_imagem_associada_por_tempo_sem_frame_exato(self):
        self._ativar_imagens()
        self.enviar(1,frame=None)
        self.bus.publicar('imagens',imagem(self.sid,1,frame=999));self.g.sincronizar()
        self.assertEqual(self.h.consultar('imagens')[0]['associacao_tipo'],'temporal_estimado')

    def test_imagens_por_evento_sem_gravacao_continua(self):
        self.g.fechar();self.bus=Distribuidor()
        self.g=Gravador(self.bus,replace(self.op,imagens_eventos=True))
        self.g.iniciar();self.g.nova_gravacao('Somente evento')
        self.bus.publicar('imagens',imagem(self.sid,1));self.g.sincronizar()
        self.enviar(1,obstaculo=True);self.g.sincronizar()
        self.assertEqual(len(self.h.consultar('imagens')),1)

    def test_backup_nao_aceita_hash_alterado(self):
        self.enviar(1);self.g.sincronizar()
        pasta=criar(self.raiz)
        (pasta/'banco/robo_seguidor.db').write_bytes(b'alterado')
        with self.assertRaises(ValueError):restaurar(pasta,Path(self.tmp.name)/'nao_criar',True)

    def test_resumo_estatisticas_descarte_e_alerta(self):
        self.g.fechar();self.bus=Distribuidor()
        self.g=Gravador(self.bus,replace(self.op,cpu_alerta_pct=20))
        self.g.iniciar();self.gid=self.g.nova_gravacao('Alertas')
        self.enviar(1);self.enviar(2);self.g.sincronizar();self.g.encerrar()
        resumo=self.h.resumo(simulado=True)
        self.assertEqual(resumo['eventos']['alerta_cpu'],1)
        self.assertIsNotNone(resumo['taxa_descarte_gravacoes_fechadas'])
        self.assertEqual(self.h.consultar('desempenho')[-1]['natureza'],'simulado')

    def test_crash_apos_jpeg_detecta_orfao_sem_apagar(self):
        raiz=Path(self.tmp.name)/'crash_imagem'
        script='''import os,sys,time,uuid
from pathlib import Path
import cv2,numpy as np
from comunicacao.distribuidor import Distribuidor
from comunicacao.protocolo import envelope
from armazenamento.gravador import Gravador
from armazenamento.configuracao import OpcoesArmazenamento
import armazenamento.imagens as im
original=im.inserir
def interromper(c,t,d,*a,**kw):
 r=original(c,t,d,*a,**kw)
 if t=='imagens':os._exit(0)
 return r
im.inserir=interromper
bus=Distribuidor();g=Gravador(bus,OpcoesArmazenamento(Path(sys.argv[1]),imagens=True,reserva_livre_bytes=0))
g.iniciar();g.nova_gravacao('Crash entre arquivo e commit')
j=cv2.imencode('.jpg',np.zeros((240,320,3),np.uint8))[1].tobytes()
m=envelope(str(uuid.uuid4()),1,'imagem',dict(frame_id=1,jpeg_bytes=len(j)),True,'simulador')
bus.publicar('imagens',(m,j,time.monotonic()));g.sincronizar()
'''
        r=subprocess.run([sys.executable,'-c',script,str(raiz)],capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stderr)
        novo=Gravador(Distribuidor(),replace(self.op,raiz=raiz));novo.iniciar();novo.fechar()
        estado=Historico(raiz).integridade()
        self.assertEqual(estado['sqlite'],['ok'])
        self.assertEqual(estado['total_orfaos'],1)
        self.assertTrue((raiz/estado['arquivos_orfaos'][0]).exists())


class TestIntegracaoHistorico(unittest.IsolatedAsyncioTestCase):
    async def test_mesmo_cliente_grava_reconexoes_sem_hardware(self):
        from comunicacao.amostras import Amostras
        from comunicacao.configuracao import Opcoes
        from comunicacao.servidor import Servidor
        from armazenamento.receptor import ReceptorPC
        op=Opcoes('127.0.0.1',0,'teste-local-com-mais-de-24-caracteres',telemetria_hz=30,
            imagens_fps=10,heartbeat_s=.1,timeout_s=.5,reconexao_s=.05)
        camera=CameraSimulada()
        servidor=Servidor(op,Amostras(telemetria_simulada(camera),30),camera,True,{'desconectar_s':.6})
        with tempfile.TemporaryDirectory() as tmp:
            camera.iniciar();servidor.iniciar()
            r=ReceptorPC(f'ws://127.0.0.1:{servidor.porta}',op,
                OpcoesArmazenamento(Path(tmp)/'dados',imagens=True,reserva_livre_bytes=0,intervalo_s=.02))
            try:
                with patch('motor.serial_com.ArduinoSerial.conectar',side_effect=AssertionError('Sem hardware')):
                    r.iniciar(True,nome='Integracao')
                    async with asyncio.timeout(5):
                        while r.g.contas['persistidas']<15 or servidor.metricas.contas['conexoes']<4:
                            await asyncio.sleep(.05)
                    self.assertLessEqual(len(servidor.consumidores),2)
            finally:
                await asyncio.to_thread(r.fechar)
                await asyncio.to_thread(servidor.parar)
                camera.parar()
            h=Historico(Path(tmp)/'dados')
            self.assertEqual(len(h.consultar('sessoes')),1)
            self.assertGreater(len(h.consultar('telemetria')),0)
            self.assertGreater(len(h.consultar('imagens')),0)
            self.assertTrue(any(e['categoria']=='reconexao' for e in h.consultar('eventos')))
            self.assertEqual(h.integridade()['chaves_estrangeiras'],[])


if __name__=='__main__':unittest.main()
