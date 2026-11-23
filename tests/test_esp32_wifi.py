"""Orquestração Wi-Fi: TODOS os nmcli/systemd/sudo/timeout são falsos."""
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ANTERIOR = '11111111-1111-1111-1111-111111111111'
CAMERA = '22222222-2222-2222-2222-222222222222'
FALSO = r'''#!/usr/bin/python3
import json,os,sys,time,signal
from pathlib import Path
base=Path(os.environ['WIFI_TEST_DIR'])
args=sys.argv[1:]; nome=Path(sys.argv[0]).name
with (base/'chamadas.jsonl').open('a') as f:f.write(json.dumps([nome]+args)+'\n')
if nome=='nmcli':
 if args[:2]==['-g','GENERAL.TYPE']:print('wifi')
 elif args[:2]==['-g','GENERAL.STATE']:print('100 (connected)')
 elif args[:2]==['-g','GENERAL.CON-UUID']:print((base/'ativa').read_text())
 elif args[:2]==['-g','802-11-wireless.ssid']:
  print('Carrinho-CAM' if args[-1]==os.environ['WIFI_TEST_CAM'] else 'Domestica')
 elif 'up' in args:
  alvo=args[args.index('uuid')+1]
  if alvo==os.environ['WIFI_TEST_CAM'] and os.environ.get('WIFI_TEST_CAM_FAIL'):sys.exit(10)
  if alvo==os.environ['WIFI_TEST_HOME'] and os.environ.get('WIFI_TEST_HOME_FAIL'):sys.exit(11)
  (base/'ativa').write_text(alvo)
 else:sys.exit(50)
elif nome=='timeout':
 (base/'teste_iniciado').touch()
 if os.environ.get('WIFI_TEST_ESPERAR'):
  def terminar(*_):sys.exit(143)
  signal.signal(signal.SIGTERM,terminar)
  while True:time.sleep(.02)
 if '--csv' in args:
  Path(args[args.index('--csv')+1]).write_text('tempo_s,decisao\n0,PARAR\n')
 print('FERRAMENTA_SIMULADA')
 sys.exit(int(os.environ.get('WIFI_TEST_RC','0')))
elif nome=='sudo':os.execvp(args[0],args)
elif nome in ('systemd-run','sleep','runuser'):pass
else:sys.exit(51)
'''

class TestWifi(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
  (self.base/'ativa').write_text(ANTERIOR)
  self.repo=self.base/'projeto';(self.repo/'tools').mkdir(parents=True)
  self.script=self.repo/'tools/testar_esp32_wifi.sh'
  shutil.copy2(RAIZ/'tools/testar_esp32_wifi.sh',self.script)
  self.bin=self.base/'bin';self.bin.mkdir()
  for nome in ('nmcli','systemd-run','timeout','sleep','sudo','runuser'):
   p=self.bin/nome;p.write_text(FALSO);p.chmod(0o755)
  self.env=dict(os.environ,PATH=str(self.bin)+os.pathsep+os.environ['PATH'],
                WIFI_TEST_DIR=str(self.base),WIFI_TEST_HOME=ANTERIOR,WIFI_TEST_CAM=CAMERA)
  self.saida=self.base/'saida';self.saida.mkdir()
 def tearDown(self):self.temp.cleanup()
 def rodar(self,*args):
  return subprocess.run(['bash',str(self.script),*args],env=self.env,text=True,capture_output=True,timeout=8)
 def worker(self):
  return self.rodar('--worker',ANTERIOR,CAMERA,'wlan0','usuario_falso',str(self.saida),'unidade_falsa')
 def chamadas(self):
  p=self.base/'chamadas.jsonl'
  return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []
 def ativacoes(self):return [c for c in self.chamadas() if c[0]=='nmcli' and 'up' in c]
 def test_verificar_nao_troca_rede_nem_agenda(self):
  r=self.rodar('--verificar',CAMERA)
  self.assertEqual(r.returncode,0,r.stderr)
  self.assertIn('VERIFICACAO_OK',r.stdout)
  self.assertFalse(self.ativacoes())
  self.assertFalse(any(c[0]=='systemd-run' for c in self.chamadas()))
 def test_iniciar_agenda_servico_independente_com_retaguarda(self):
  r=self.rodar('--iniciar',CAMERA)
  self.assertEqual(r.returncode,0,r.stderr)
  chamadas=[c for c in self.chamadas() if c[0]=='systemd-run']
  self.assertEqual(len(chamadas),1)
  self.assertIn('--unit=robo-esp32-cam-teste',chamadas[0])
  self.assertTrue(any('ExecStopPost=' in a and ANTERIOR in a for a in chamadas[0]))
  self.assertIn('--property=RuntimeMaxSec=150s',chamadas[0])
  self.assertFalse(self.ativacoes())  # serviço falso nunca ativa rede
 def test_sucesso_executa_30s_sem_janela_e_restaura(self):
  r=self.worker();self.assertEqual(r.returncode,0,r.stderr)
  self.assertEqual((self.base/'ativa').read_text(),ANTERIOR)
  teste=next(c for c in self.chamadas() if c[0]=='timeout')
  self.assertIn('--sem-janela',teste)
  self.assertEqual(teste[teste.index('--duracao')+1],'30')
  self.assertIn('40s',teste)
  self.assertTrue((self.saida/'capturas.csv').exists())
  self.assertIn('RESTAURACAO_OK',(self.saida/'execucao.log').read_text())
 def test_falha_da_camera_tambem_restaura(self):
  self.env['WIFI_TEST_CAM_FAIL']='1'
  r=self.worker();self.assertEqual(r.returncode,10)
  self.assertEqual((self.base/'ativa').read_text(),ANTERIOR)
  self.assertFalse((self.base/'teste_iniciado').exists())
  self.assertIn('RESTAURACAO_OK',(self.saida/'execucao.log').read_text())
 def test_timeout_do_teste_restaura_e_preserva_status(self):
  self.env['WIFI_TEST_RC']='124'
  r=self.worker();self.assertEqual(r.returncode,124,r.stderr)
  self.assertEqual((self.base/'ativa').read_text(),ANTERIOR)
  self.assertIn('TESTE_RC=124',(self.saida/'execucao.log').read_text())
 def test_restauracao_tem_tres_tentativas_limitadas(self):
  self.env['WIFI_TEST_HOME_FAIL']='1'
  r=self.worker();self.assertEqual(r.returncode,90,r.stderr)
  tentativas=[c for c in self.ativacoes() if ANTERIOR in c]
  self.assertEqual(len(tentativas),3)
  self.assertTrue(all(c[1:3]==['--wait','15'] for c in tentativas))
  self.assertIn('RESTAURACAO_FALHOU',(self.saida/'execucao.log').read_text())
 def test_retaguarda_idempotente_e_recuperacao_pos_worker(self):
  log=self.saida/'execucao.log'
  r=self.rodar('--restaurar',ANTERIOR,'wlan0',str(log))
  self.assertEqual(r.returncode,0);self.assertFalse(self.ativacoes())
  (self.base/'ativa').write_text(CAMERA)
  r=self.rodar('--restaurar',ANTERIOR,'wlan0',str(log))
  self.assertEqual(r.returncode,0)
  self.assertEqual((self.base/'ativa').read_text(),ANTERIOR)
 def test_retaguarda_funciona_sem_arquivo_de_log(self):
  (self.base/'ativa').write_text(CAMERA)
  r=self.rodar('--restaurar',ANTERIOR,'wlan0',str(self.base/'inexistente'/'log'))
  self.assertEqual(r.returncode,0,r.stderr)
  self.assertEqual((self.base/'ativa').read_text(),ANTERIOR)
 def test_interrupcao_termina_filho_e_tenta_restaurar(self):
  self.env['WIFI_TEST_ESPERAR']='1'
  args=['bash',str(self.script),'--worker',ANTERIOR,CAMERA,'wlan0','usuario_falso',str(self.saida),'unidade_falsa']
  p=subprocess.Popen(args,env=self.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  try:
   fim=time.monotonic()+4
   while not (self.base/'teste_iniciado').exists() and time.monotonic()<fim:time.sleep(.01)
   self.assertTrue((self.base/'teste_iniciado').exists())
   p.send_signal(signal.SIGTERM);p.communicate(timeout=4)
   self.assertEqual(p.returncode,143)
   self.assertEqual((self.base/'ativa').read_text(),ANTERIOR)
  finally:
   if p.poll() is None:p.kill();p.communicate()
 def test_argumento_sem_uuid_rejeitado_sem_ativacao(self):
  r=self.rodar('--iniciar','Carrinho-CAM')
  self.assertNotEqual(r.returncode,0);self.assertFalse(self.ativacoes())

if __name__=='__main__':unittest.main()
