"""Pacote mínimo versionado para a Pi, sem dados operacionais ou credenciais."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid
import zipfile

RAIZ=Path(__file__).resolve().parents[1]
PASTAS=('motor','remoto','visao','voz','aprendizado','monitoramento','comunicacao','distribuido')
FIXOS=('main.py','config.py','controle.py','estado.py','requirements.txt','requirements-pi-base.txt',
 'requirements-pi-bluetooth.txt','requirements-pi-voz.txt','requirements-rede-pi.txt',
 'deploy/preparar_raspberry.sh','deploy/iniciar_raspberry.sh','docs/30_revisao_integrada_A_D.md',
 'tools/painel_coleta.py','tools/coletar_esp32_cam.py','tools/rotular_linha.py','tools/testar_esp32_cam.py',
 'tools/verificar_ambiente.py','docs/07_controle_bluetooth.md','docs/12_esp32_cam_bancada.md',
 'docs/17_integracao_cnn_rl_esp32.md','docs/19_comunicacao_websocket.md')


def preparar(saida,raiz=RAIZ):
    raiz=Path(raiz);nomes=set(FIXOS)
    for pasta in PASTAS:nomes.update(p.relative_to(raiz).as_posix() for p in (raiz/pasta).glob('*.py'))
    nomes.update(p.relative_to(raiz).as_posix() for p in (raiz/'voz/modelo').glob('*.pkl'))
    modelos='dataset_pista/resultados/treino_posicao_02/'
    for nome in ('experimento.json','pesos_posicao.npz'):
        if (raiz/modelos/nome).is_file():nomes.add(modelos+nome)
    for nome in nomes:
        if not (raiz/nome).is_file():raise ValueError('Arquivo obrigatório ausente: '+nome)
    try:
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=raiz,text=True,stderr=subprocess.DEVNULL).strip()
        alterado=bool(subprocess.check_output(['git','status','--porcelain'],cwd=raiz,text=True))
    except (OSError,subprocess.SubprocessError):commit=None;alterado=None
    destino=Path(saida)/str(uuid.uuid4());destino.mkdir(parents=True,exist_ok=False)
    pacote=destino/'robo_pi.zip';hashes={}
    with zipfile.ZipFile(pacote,'w',zipfile.ZIP_DEFLATED) as z:
        for nome in sorted(nomes):
            dados=(raiz/nome).read_bytes()
            if (raiz/nome).suffix in ('.py','.sh','.txt','.md','.json'):dados=dados.replace(b'\r\n',b'\n')
            hashes[nome]=hashlib.sha256(dados).hexdigest();z.writestr(nome,dados)
        manifesto=dict(criado_utc=datetime.now(timezone.utc).isoformat(),commit=commit,arvore_modificada=alterado,
            arquivos_sha256=hashes,perfil_padrao='completo',cnn='própria preservada; CNN02 diagnóstica, sem navegação autorizada',
            excluidos=['SQLite/JPEG/CSV/histórico','GLB/Three.js/dashboard','datasets e vídeos','credenciais .env/SSH','treino de RL e suas dependências opcionais'],
            limite='Pacote preparado; transferência/instalação/bancada só após confirmar o endereço da Raspberry.')
        z.writestr('manifesto_pacote.json',json.dumps(manifesto,ensure_ascii=False,indent=2))
    (destino/'manifesto.json').write_text(json.dumps(manifesto,ensure_ascii=False,indent=2),encoding='utf-8')
    return dict(pacote=str(pacote.resolve()),bytes=pacote.stat().st_size,arquivos=len(nomes),sha256=hashlib.sha256(pacote.read_bytes()).hexdigest())


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--saida',type=Path,default=RAIZ/'dados_implantacao');a=p.parse_args()
    print(json.dumps(preparar(a.saida),ensure_ascii=True,indent=2))


if __name__=='__main__':main()
