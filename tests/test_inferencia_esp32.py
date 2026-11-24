"""Contratos CNN/RL e guardas em software; pesos artificiais, sem treino ou motores reais."""
from dataclasses import replace
import json
import math
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as cfg
from aprendizado.cnn import RedeLinha
from aprendizado.inferencia_esp32 import Pacote, ThreadInferencia, VelocidadeEncoder, OBS_Q, OBS_GYM, sha256
from aprendizado.rl_simulado import ACOES
from controle import ThreadControle
from estado import EstadoRobo, Modo, AcaoRL
from tools.preparar_pacote_cnn_rl import preparar
from visao.esp32_cam import CameraESP32, receber_quadro
from test_esp32_fonte import HTTPFalso
from test_decisao_visao import MotorFalso


class TestInferencia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name)
        self.exp = self.raiz/'exp'
        self.exp.mkdir()
        rede = RedeLinha(1)
        for p in rede.parametros(): p[:] = 0
        rede.f2b[:] = [.2, 20]  # fixture previsivel, nao e modelo treinado
        rede.salvar(self.exp/'referencia_sintetica.npz')
        q = np.zeros((7,5,3,3,11,11), np.float32)
        q[...,8] = 2
        np.savez(self.exp/'politica_q.npz', contrato=OBS_Q, acoes=ACOES, hash_cnn=rede.hash(), q=q)
        (self.exp/'experimento.json').write_text(json.dumps(dict(contrato=OBS_Q,
            hash_referencia_cnn=rede.hash(), referencia=dict(roi_inicio=40, semantica='lateral_a_10cm_dividida_por_12cm'))))
        self.manifesto = preparar(self.exp, 'q', None, self.raiz/'pacote')
        self.pacote = Pacote(self.manifesto)
        self.estado = EstadoRobo()
        self.estado.definir_modo(Modo.SEGUINDO)
        self.fonte = CameraESP32()
        self.q = receber_quadro(HTTPFalso(), 'http://teste/capture', 1)
        self.fonte._quadro, self.fonte._id, self.fonte._status = self.q, 1, 'ok'
        self.fim = threading.Event()
        self.motor = MotorFalso()
        self.motor.estado_motores=lambda: SimpleNamespace(timestamp=time.monotonic(),falha_encoder=False)
        self.runner = ThreadInferencia(self.estado, self.motor, self.fim, self.fonte, self.pacote)

    def tearDown(self):
        self.fim.set()
        self.tmp.cleanup()

    def meta(self):
        return self.fonte.proximo_quadro_detalhado(0, 0)

    def editar(self, **campos):
        m=json.loads(self.manifesto.read_text());m.update(campos)
        self.manifesto.write_text(json.dumps(m))
        return m

    def leitura(self, timestamp=None):
        t=self.q.recepcao_monotonica if timestamp is None else timestamp
        self.estado.publicar_leitura(0., True, timestamp=t, frame_id=1,
                                    sessao=self.estado.sessao_visao, geracao_camera=0,
                                    confianca=1., motivo='observada')

    def acao(self, **kw):
        dados=dict(steer=.35, vel_fator=.8, timestamp=self.q.recepcao_monotonica,
                   idade_captura_s=.001, frame_id=1, geracao_camera=0,
                   sessao=self.estado.sessao_visao, motivo='cnn_rl', erro_cnn=.2,
                   visibilidade=.9, indice=9)
        dados.update(kw)
        a=AcaoRL(**dados)
        self.estado.publicar_acao_rl(a)
        return a

    def test_pacote_q_pareado_deterministico_e_preprocessamento(self):
        self.assertEqual(self.pacote.escolher(.2, 0, .05, 0, 0), 8)
        x=self.pacote.entrada(self.q.imagem)
        self.assertEqual(x.shape, (1,1,40,80))
        self.assertEqual(x.dtype, np.float32)
        self.assertTrue(np.isfinite(x).all())
        self.assertFalse(self.pacote.rede._norms)
        with self.assertRaises(ValueError): self.pacote.entrada(self.q.imagem[:120])
        with self.assertRaises(ValueError): self.pacote.validar_motores()

    def test_hash_corrompido_recusado(self):
        p=self.manifesto.parent/'cnn.npz';p.write_bytes(p.read_bytes()+b'x')
        with self.assertRaisesRegex(ValueError, 'Hash'): Pacote(self.manifesto)

    def test_politica_com_outra_cnn_recusada(self):
        p=self.manifesto.parent/'politica.npz'
        np.savez(p, contrato=OBS_Q, acoes=ACOES, hash_cnn='outra', q=self.pacote.q)
        m=json.loads(self.manifesto.read_text());m['politica']['sha256']=sha256(p)
        self.manifesto.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError, 'incompativel'): Pacote(self.manifesto)

    def test_visibilidade_nao_supervisionada_e_escalas_recusadas(self):
        m=json.loads(self.manifesto.read_text())
        m['percepcao']['visibilidade_treinada']=False
        self.manifesto.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError, 'visibilidade'): Pacote(self.manifesto)
        m['percepcao']['visibilidade_treinada']=True;m['escalas']['dt_s']=.2
        self.manifesto.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError, 'Escalas'): Pacote(self.manifesto)

    def test_recusa_pesos_de_posicao_offline(self):
        (self.exp/'experimento.json').write_text(json.dumps(dict(tarefa='localizacao_horizontal_offline')))
        with self.assertRaises((ValueError, KeyError)):
            preparar(self.exp, 'q', None, self.raiz/'invalido')
        self.assertFalse((self.raiz/'invalido').exists())

    def test_modelo_real_exige_roi_calibracao_e_orientacao(self):
        m=json.loads(self.manifesto.read_text());m['dominio']='esp32'
        m['percepcao'].update(preprocessamento='esp32_roi_normalizada_v1', roi=[0,80,320,160],
                               semantica='lateral_a_10cm_dividida_por_12cm', espelhar_h=False, espelhar_v=False)
        self.manifesto.write_text(json.dumps(m))
        with self.assertRaises(ValueError): Pacote(self.manifesto).validar_motores()
        m['encoders']['calibrados']=True
        self.manifesto.write_text(json.dumps(m))
        p=Pacote(self.manifesto);p.validar_motores()
        self.assertEqual(p.entrada(self.q.imagem).shape, (1,1,40,80))
        with patch.object(cfg, 'IMAGEM_ESPELHAR_H', True):
            with self.assertRaisesRegex(ValueError, 'orientacao'): p.validar_motores()

    def test_adaptadores_dqn_ppo_deterministicos_com_api_injetada(self):
        m=json.loads(self.manifesto.read_text());m['politica']['observacao']=OBS_GYM
        for nome in ('dqn','ppo'):
            m['politica']['algoritmo']=nome
            self.manifesto.write_text(json.dumps(m))
            modelo=Mock(observation_space=SimpleNamespace(shape=(7,)), action_space=SimpleNamespace(n=11))
            modelo.predict.return_value=(np.array(8), None)
            classe=Mock();classe.load.return_value=modelo
            modulo=SimpleNamespace(DQN=classe,PPO=classe)
            with patch.dict(sys.modules, stable_baselines3=modulo):
                pacote=Pacote(self.manifesto)
                self.assertEqual(pacote.escolher(.4,.2,.055,.3,0),8)
            obs=modelo.predict.call_args.args[0]
            np.testing.assert_allclose(obs,[.4,.1,0,0,1,0,-1],atol=1e-6)
            self.assertTrue(modelo.predict.call_args.kwargs['deterministic'])
            self.assertEqual(classe.load.call_args.kwargs['device'],'cpu')
            modelo.predict.return_value=(np.array(99),None)
            with self.assertRaises(ValueError): pacote.escolher(0,0,0,0,0)

    def test_empacota_dqn_somente_checkpoint_registrado(self):
        pasta=self.exp/'dqn_7';pasta.mkdir();cp=pasta/'melhor.zip';cp.write_bytes(b'fixture-nao-executavel')
        meta=dict(contrato=OBS_GYM, hash_cnn=self.pacote.rede.hash(), acoes=ACOES.tolist(),
                  execucoes=[dict(algoritmo='DQN',semente=7)], sha256_checkpoints={'dqn_7/melhor.zip':sha256(cp)})
        (self.exp/'experimento.json').write_text(json.dumps(meta))
        destino=preparar(self.exp,'dqn',cp,self.raiz/'pacote_dqn')
        m=json.loads(destino.read_text())
        self.assertEqual(m['politica']['observacao'],OBS_GYM)
        self.assertEqual(m['dominio'],'sintetico')
        cp.write_bytes(b'alterado')
        with self.assertRaises(ValueError): preparar(self.exp,'dqn',cp,self.raiz/'invalido')

    def test_falha_inferencia_encerra_sem_escrever_motor(self):
        self.motor.sensores=lambda: SimpleNamespace(timestamp=time.monotonic(),ticks_esq=0,ticks_dir=0,
                                                     falha_sensor=False,avanco_bloqueado=False)
        quadro=self.meta()
        with patch.object(self.fonte,'proximo_quadro_detalhado',return_value=quadro), patch.object(self.pacote.rede,'prever',side_effect=RuntimeError('modelo falhou')), self.assertLogs('cnn-rl',level='ERROR'):
            self.runner.start();self.runner.join(1)
        self.assertTrue(self.fim.is_set())
        self.assertIsNone(self.estado.ler_acao_rl())
        self.assertEqual(self.motor.cmds,[])

    def test_estima_velocidade_por_ticks_sem_inventar_zero(self):
        v=VelocidadeEncoder((10.,10.))
        def s(t,e,d): return SimpleNamespace(timestamp=t,ticks_esq=e,ticks_dir=d)
        self.assertIsNone(v.medir(s(1,0,0),1))
        self.assertAlmostEqual(v.medir(s(1.1,1,1),1.1),.1)
        self.assertAlmostEqual(v.medir(s(1.1,1,1),1.15),.1)
        self.assertIsNone(v.medir(s(1.2,0,0),1.2))
        self.assertIsNone(v.medir(s(1.2,0,0),2))

    def test_inferencia_conserva_timestamp_id_e_nao_treina(self):
        antes=self.pacote.rede.hash()
        a=self.runner.processar(self.meta(),self.estado.sessao_visao,.05)
        self.assertEqual(a.indice,8)
        self.assertEqual(a.timestamp,self.q.recepcao_monotonica)
        self.assertEqual(a.frame_id,1)
        self.assertEqual(self.pacote.rede.hash(),antes)
        self.assertIsNone(self.runner.processar(self.meta(),self.estado.sessao_visao,.05))
        self.assertEqual(self.motor.cmds,[])

    def test_sem_velocidade_ou_referencia_nao_pede_movimento(self):
        a=self.runner.processar(self.meta(),self.estado.sessao_visao,None)
        self.assertEqual(a.motivo,'velocidade_indisponivel')
        self.assertEqual((a.steer,a.vel_fator),(0,0))
        self.runner.resetar()
        with patch.object(self.pacote.rede,'prever',return_value=(np.array([0.]),np.array([.1]))):
            a=self.runner.processar(self.meta(),self.estado.sessao_visao,.05)
        self.assertEqual(a.motivo,'sem_referencia_cnn')
        self.assertEqual(a.vel_fator,0)

    def test_falha_durante_cnn_nao_publica_acao(self):
        def prever(_):
            with self.fonte._cond: self.fonte._invalidar('erro')
            return np.array([0.]),np.array([1.])
        with patch.object(self.pacote.rede,'prever',side_effect=prever):
            self.assertIsNone(self.runner.processar(self.meta(),self.estado.sessao_visao,.05))
        self.assertIsNone(self.estado.ler_acao_rl())

    def test_pare_siga_durante_inferencia_descarta_resultado(self):
        sessao=self.estado.sessao_visao
        def prever(_):
            self.estado.definir_modo(Modo.PARADO);self.estado.definir_modo(Modo.SEGUINDO)
            return np.array([0.]),np.array([1.])
        with patch.object(self.pacote.rede,'prever',side_effect=prever):
            self.assertIsNone(self.runner.processar(self.meta(),sessao,.05))
        self.assertIsNone(self.estado.ler_acao_rl())

    def test_processamento_lento_nao_rejuvenesce_frame(self):
        original=self.pacote.rede.prever
        def lento(x):
            time.sleep(.32)
            return original(x)
        with patch.object(self.pacote.rede,'prever',side_effect=lento):
            self.assertIsNone(self.runner.processar(self.meta(),self.estado.sessao_visao,.05))
        self.assertIsNone(self.estado.ler_acao_rl())

    def test_frame_anterior_ao_siga_nao_vira_acao_da_nova_sessao(self):
        self.estado.definir_modo(Modo.PARADO)
        self.estado.definir_modo(Modo.SEGUINDO)
        self.assertIsNone(self.runner.processar(self.meta(),self.estado.sessao_visao,.05))
        self.assertIsNone(self.estado.ler_acao_rl())

    def test_sombra_nao_aceita_construtor_real_com_modelo_sintetico(self):
        with self.assertRaises(ValueError):
            ThreadInferencia(self.estado,self.motor,self.fim,self.fonte,self.pacote,sombra=False)

    def test_cnn_nan_recusada(self):
        with patch.object(self.pacote.rede,'prever',return_value=(np.array([np.nan]),np.array([1.]))):
            with self.assertRaises(ValueError): self.runner.processar(self.meta(),self.estado.sessao_visao,.05)
        self.assertIsNone(self.estado.ler_acao_rl())

    def test_sombra_nunca_substitui_por_pd(self):
        self.leitura();self.acao()
        c=ThreadControle(self.estado,self.motor,self.fim,self.fonte,inferencia_rl=self.runner)
        d=c.decidir_cnn_rl(time.monotonic())
        self.assertEqual((d.esq,d.dir),(0,0));self.assertEqual(d.motivo,'cnn_rl_sombra')

    def test_controle_rl_guardas_obstaculo_sessao_idade(self):
        self.runner.sombra=False
        self.leitura();self.acao()
        c=ThreadControle(self.estado,self.motor,self.fim,self.fonte,inferencia_rl=self.runner)
        d=c.decidir_cnn_rl(time.monotonic());self.assertEqual(d.motivo,'cnn_rl')
        self.assertGreater(d.esq,d.dir)
        d=c.decidir_cnn_rl(time.monotonic(),True);self.assertEqual((d.esq,d.dir),(0,0))
        self.leitura(time.monotonic())
        self.assertEqual(c.decidir_cnn_rl(time.monotonic()).motivo,'aguardando_rl_apos_bloqueio')
        self.acao(timestamp=time.monotonic())
        self.assertEqual(c.decidir_cnn_rl(time.monotonic()).motivo,'cnn_rl')
        self.acao(timestamp=time.monotonic(), idade_captura_s=1.)
        self.assertEqual(c.decidir_cnn_rl(time.monotonic()).motivo,'acao_rl_vencida')
        self.estado.definir_modo(Modo.MANUAL)
        self.assertIsNone(self.estado.ler_acao_rl())
        self.assertEqual(c.decidir_cnn_rl(time.monotonic()).esq,0)

    def test_diagnostico_motor_f8_vencido_veta_acao_rl(self):
        self.runner.sombra=False;self.leitura();self.acao()
        self.motor.estado_motores=lambda: SimpleNamespace(timestamp=time.monotonic()-1,falha_encoder=False)
        c=ThreadControle(self.estado,self.motor,self.fim,self.fonte,inferencia_rl=self.runner)
        d=c.decidir_cnn_rl(time.monotonic())
        self.assertEqual((d.esq,d.dir),(0,0))
        self.assertEqual(d.motivo,'diagnostico_motor_rl_indisponivel')

    def test_sem_acao_nao_usa_pd_e_camera_falha_para(self):
        self.runner.sombra=False;self.leitura()
        c=ThreadControle(self.estado,self.motor,self.fim,self.fonte,inferencia_rl=self.runner)
        self.assertEqual(c.decidir_cnn_rl(time.monotonic()).motivo,'aguardando_cnn_rl')
        self.acao()
        with self.fonte._cond: self.fonte._invalidar('erro')
        d=c.decidir_cnn_rl(time.monotonic());self.assertEqual((d.esq,d.dir),(0,0))

    def test_fluxo_http_cnn_rl_controle_para_por_obstaculo_e_camera(self):
        # Fixture artificial marcada como contrato real apenas para exercitar o caminho;
        # nenhuma validacao fisica ou modelo de producao e produzido por este teste.
        from visao.detector import ThreadVisao
        from test_detector_tracejado import imagem
        from controle import aplicar_comando
        m=json.loads(self.manifesto.read_text());m['dominio']='esp32'
        m['percepcao'].update(preprocessamento='esp32_roi_normalizada_v1', roi=[0,80,320,160],
                               semantica='lateral_a_10cm_dividida_por_12cm', espelhar_h=False, espelhar_v=False)
        m['encoders']['calibrados']=True
        self.manifesto.write_text(json.dumps(m))
        pacote=Pacote(self.manifesto)
        h=HTTPFalso();h.dados=cv2.imencode('.jpg',imagem())[1].tobytes()
        fonte=CameraESP32(opener=h,reconexao_s=.01)
        motor=MotorFalso();motor.bloqueado=False
        motor.estado_motores=lambda: SimpleNamespace(timestamp=time.monotonic(),falha_encoder=False)
        motor.sensores=lambda: SimpleNamespace(timestamp=time.monotonic(), ticks_esq=0,ticks_dir=0,
            distancia_cm=5 if motor.bloqueado else 100,falha_sensor=False,avanco_bloqueado=motor.bloqueado)
        e=EstadoRobo();e.definir_modo(Modo.SEGUINDO);fim=threading.Event()
        r=ThreadInferencia(e,motor,fim,fonte,pacote,sombra=False)
        c=ThreadControle(e,motor,fim,fonte,inferencia_rl=r);v=ThreadVisao(e,fim,fonte)
        def esperar(cond):
            limite=time.monotonic()+3
            while not cond() and time.monotonic()<limite: time.sleep(.005)
            self.assertTrue(cond(),r.status())
        fonte.iniciar();r.start();v.start();c.start()
        try:
            esperar(lambda: c.decisao_linha.motivo=='cnn_rl' and motor.cmds[-1]!=(0,0))
            motor.bloqueado=True
            esperar(lambda: c.decisao_linha.motivo=='obstaculo_ou_sensor')
            self.assertEqual(motor.cmds[-1],(0,0))
            motor.bloqueado=False
            esperar(lambda: c.decisao_linha.motivo=='cnn_rl' and motor.cmds[-1]!=(0,0))
            h.falhar=True
            esperar(lambda: c.decisao_linha.motivo=='camera_indisponivel')
            self.assertEqual(motor.cmds[-1],(0,0))
            h.dados=cv2.imencode('.jpg',imagem(()))[1].tobytes();h.falhar=False
            esperar(lambda: fonte.status=='ok')
            time.sleep(.15)
            self.assertEqual(motor.cmds[-1],(0,0))
            aplicar_comando(e,motor,'pare')
            time.sleep(.06)
            self.assertEqual(e.modo,Modo.PARADO)
            self.assertEqual(motor.cmds[-1],(0,0))
        finally:
            fim.set();c.join(2);v.join(2);r.join(2);fonte.parar()
        self.assertFalse(any(t.is_alive() for t in (r,v,c)))

    def test_main_sombra_conecta_inferencia_controle_e_painel(self):
        import main
        motor, controle, visao, voz, runner, painel=Mock(),Mock(),Mock(),Mock(),Mock(),Mock()
        voz.start.side_effect=RuntimeError('encerramento de teste')
        with patch.object(sys,'argv',['main.py','--politica','cnn-rl-sombra','--pacote-cnn-rl',str(self.manifesto)]), patch.object(cfg,'REMOTO_BT_ATIVO',False), patch.object(main,'ArduinoSerial',return_value=motor), patch.object(main,'abrir_fonte',return_value=self.fonte), patch.object(main,'ThreadControle',return_value=controle) as criar_controle, patch.object(main,'ThreadVisao',return_value=visao), patch.object(main,'ThreadVoz',return_value=voz), patch.object(main.signal,'signal'), patch('aprendizado.inferencia_esp32.ThreadInferencia',return_value=runner) as criar_runner, patch('tools.painel_coleta.Painel',return_value=painel):
            with self.assertRaisesRegex(RuntimeError,'encerramento de teste'): main.main()
            self.assertTrue(criar_runner.call_args.kwargs['sombra'])
            self.assertIs(criar_controle.call_args.kwargs['inferencia_rl'],runner)
            self.assertIs(painel.coleta.diagnostico_rl,runner.status)
            motor.fechar.assert_called_once()
            self.assertFalse(motor.motores.called)

    def test_ferramenta_diagnostica_sem_serial(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from tools import testar_cnn_rl_esp32 as ferramenta
        out=StringIO()
        with patch.object(sys,'argv',['teste','--pacote',str(self.manifesto),'--duracao','.01','--velocidade-simulada','0']), patch.object(ferramenta,'CameraESP32',return_value=self.fonte), patch.object(self.fonte,'iniciar',side_effect=lambda: setattr(self.fonte,'_quadro',replace(self.q,recepcao_monotonica=time.monotonic()))), patch.object(self.fonte,'parar'), patch('motor.serial_com.ArduinoSerial') as serial, redirect_stdout(out):
            self.assertEqual(ferramenta.main(),0)
            serial.assert_not_called()
        self.assertIn('"velocidade_simulada": true',out.getvalue())
        self.assertIn('"motores": "inexistentes"',out.getvalue())

    def test_main_recusa_modelo_sintetico_antes_de_abrir_serial(self):
        import main
        with patch.object(sys,'argv',['main.py','--politica','cnn-rl','--pacote-cnn-rl',str(self.manifesto)]), patch.object(main,'ArduinoSerial') as motor:
            with self.assertRaises(SystemExit) as exc: main.main()
            self.assertEqual(exc.exception.code,2);motor.assert_not_called()


if __name__ == '__main__': unittest.main()
