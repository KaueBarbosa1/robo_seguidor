import csv
import json
from pathlib import Path
import uuid

from armazenamento.consultas import CATEGORIAS
from armazenamento.imagens import seguro


def exportar(historico,categorias=None,destino=None,**filtros):
    categorias = categorias or ['consolidado','eventos','imagens','sessoes','gravacoes']
    if not categorias or set(categorias)-CATEGORIAS:
        raise ValueError('Categorias de exportacao invalidas')
    pasta = Path(destino) if destino else historico.raiz/'exportacoes'/str(uuid.uuid4())
    pasta.mkdir(parents=True,exist_ok=False)
    contagens = {}
    for categoria in categorias:
        colunas = set(historico.colunas(categoria,**filtros))
        if categoria == 'dataset':
            colunas.add('arquivo_presente')
        # Mesmo vazia, exportação mantém cabeçalhos úteis.
        colunas = sorted(colunas or {'sem_registros'})
        total = 0
        with (pasta/(categoria+'.csv')).open('x',encoding='utf-8-sig',newline='') as f:
            w = csv.DictWriter(f,fieldnames=colunas)
            w.writeheader()
            for row in historico.iterar(categoria,**filtros):
                if categoria == 'dataset':
                    row['arquivo_presente'] = seguro(historico.raiz,row['caminho']).is_file()
                # Protege texto de interpretação como fórmula, preservando números.
                row = {k: "'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for k,v in row.items()}
                w.writerow(row)
                total += 1
        contagens[categoria] = total
    (pasta/'manifesto.json').write_text(json.dumps(dict(filtros=filtros,linhas=contagens,
        codificacao='UTF-8 com BOM',null='celula vazia',tempo='UTC',
        rotulos_treino='nao validados; previsao e comando nao sao rotulos humanos'),ensure_ascii=False,indent=2),encoding='utf-8')
    return pasta,contagens
