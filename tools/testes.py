"""Executa categorias sem hardware, guarda resultados reais e propaga falhas."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

RAIZ=Path(__file__).resolve().parents[1]


def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('categoria',choices=['rapidos','unitarios','integracao','interface','seguranca','carga','todos'],default='rapidos',nargs='?')
    p.add_argument('--saida',type=Path,default=RAIZ/'dados_experimentos/testes');a=p.parse_args();a.saida.mkdir(parents=True,exist_ok=True)
    comandos=[]
    if a.categoria!='interface':
        cmd=[sys.executable,'-m','pytest','tests','-q','--disable-warnings','--tb=short','--junitxml='+str(a.saida/'pytest.xml')]
        marca={'rapidos':'not lento','unitarios':'unitario','integracao':'integracao','seguranca':'seguranca','carga':'carga'}.get(a.categoria)
        if marca:cmd+=['-m',marca]
        comandos.append(('python',cmd,1800))
    if a.categoria in ('interface','todos'):
        arquivos=[str(p.relative_to(RAIZ)) for raiz in ('central_monitoramento/testes','gemeo_digital/testes') for p in (RAIZ/raiz).glob('*.test.js')]
        comandos.append(('javascript',['node','--test',*arquivos],120))
    resultados=[]
    for nome,cmd,prazo in comandos:
        print('Executando',nome,flush=True)
        try:
            r=subprocess.run(cmd,cwd=RAIZ,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',timeout=prazo)
            (a.saida/(nome+'.txt')).write_text(r.stdout,encoding='utf-8');print(r.stdout[-7000:],flush=True)
            resultados.append(dict(nome=nome,comando=cmd,exit_code=r.returncode,estado='aprovado' if r.returncode==0 else 'reprovado'))
        except (OSError,subprocess.TimeoutExpired) as exc:resultados.append(dict(nome=nome,estado='bloqueado',motivo=str(exc),exit_code=None))
    if a.categoria=='todos':
        if os.name=='posix':
            try:
                r=subprocess.run([sys.executable,'tests/test_integracao_robo.py'],cwd=RAIZ,capture_output=True,text=True,timeout=45)
                (a.saida/'integracao_pty.txt').write_text(r.stdout+r.stderr,encoding='utf-8');resultados.append(dict(nome='integracao_PTY_isolada',estado='aprovado' if r.returncode==0 else 'reprovado',exit_code=r.returncode))
            except (OSError,subprocess.TimeoutExpired) as exc:resultados.append(dict(nome='integracao_PTY_isolada',estado='bloqueado',motivo=str(exc)))
        else:resultados.append(dict(nome='integracao_PTY_isolada',estado='bloqueado',motivo='Requer Linux/POSIX termios; nenhum dispositivo real será aberto'))
        compilador=shutil.which('g++')
        if compilador:
            fontes=['harness.cpp',*[f'../robo_firmware/{n}.cpp' for n in ('comandos','motores','sensores','servo','sonar_movimento','sinalizacao')]]
            exe=(a.saida/'firmware_host.exe').resolve()
            r=subprocess.run([compilador,'-std=c++17','-I.','-I../robo_firmware','-o',str(exe),*fontes],cwd=RAIZ/'arduino/teste_host',capture_output=True,text=True,timeout=60)
            texto=r.stdout+r.stderr
            if r.returncode==0:
                r=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30);texto+=r.stdout+r.stderr
            (a.saida/'firmware_host.txt').write_text(texto,encoding='utf-8');resultados.append(dict(nome='firmware_host',estado='aprovado' if r.returncode==0 else 'reprovado',exit_code=r.returncode))
        else:resultados.append(dict(nome='firmware_host',estado='bloqueado',motivo='g++ ausente'))
    (a.saida/'resultado.json').write_text(json.dumps(dict(criado_utc=datetime.now(timezone.utc).isoformat(),categoria=a.categoria,resultados=resultados,origem='software_no_PC'),ensure_ascii=False,indent=2),encoding='utf-8')
    raise SystemExit(1 if any(r['estado']=='reprovado' for r in resultados) else 0)


if __name__=='__main__':main()
