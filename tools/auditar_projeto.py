"""Inventário reproduzível dos fontes versionados; não executa hardware."""
import argparse
import ast
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experimentos.configuracao import RAIZ,ambiente


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--saida',type=Path,default=RAIZ/'dados_experimentos/auditoria');a=p.parse_args();a.saida.mkdir(parents=True,exist_ok=True)
    nomes=subprocess.check_output(['git','ls-files','-z'],cwd=RAIZ).decode('utf-8').split('\0')
    fontes=[];duplicatas=defaultdict(list);erros=[];contas=Counter()
    for nome in nomes:
        caminho=RAIZ/nome
        if not nome or caminho.suffix not in ('.py','.js','.cpp','.h','.ino','.md','.txt','.ps1','.sh','.json','.yml'):continue
        if 'dataset_pista/resultados' in nome or 'Relatorio/' in nome:continue
        bruto=caminho.read_bytes();sha=hashlib.sha256(bruto.replace(b'\r\n',b'\n')).hexdigest();duplicatas[sha].append(nome);contas[nome.split('/')[0]]+=1
        item=dict(arquivo=nome,bytes=len(bruto),sha256_lf=sha)
        if caminho.suffix=='.py':
            try:
                arvore=ast.parse(bruto.decode('utf-8-sig'));item['classes']=[n.name for n in ast.walk(arvore) if isinstance(n,ast.ClassDef)]
                item['funcoes']=sum(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) for n in ast.walk(arvore))
            except (SyntaxError,UnicodeError) as exc:erros.append(dict(arquivo=nome,erro=str(exc)))
        fontes.append(item)
    r=dict(ambiente=ambiente(),contagem=dict(contas),fontes=fontes,erros=erros,
        duplicatas_bytes=[v for v in duplicatas.values() if len(v)>1],
        limitacao='Inventário estático não comprova integração; consultar auditoria técnica e resultados de execução. Snapshot de treino e documentos LaTeX fora do inventário de código operacional.')
    (a.saida/'inventario.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8');print(len(fontes),'fontes/documentos inventariados;',len(erros),'erros sintáticos')


if __name__=='__main__':main()
