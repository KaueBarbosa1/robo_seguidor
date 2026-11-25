"""Inspeção do GLB original; não escreve no modelo nem aplica correções."""
import hashlib
import json
from pathlib import Path
import struct
import numpy as np

COMPONENTES = ['carrinho_raiz','chassi_inferior','chassi_superior','roda_esquerda','roda_direita',
 'roda_apoio','motor_esquerdo','motor_direito','encoder_esquerdo','encoder_direito',
 'disco_encoder_esquerdo','disco_encoder_direito','servo_base','servo_eixo','sensor_ultrassonico',
 'esp32_cam','raspberry_pi','arduino_uno','ponte_h','regulador_tensao','placa_universal',
 'case_baterias_1','case_baterias_2']


def ler(caminho):
    b=Path(caminho).read_bytes()
    if b[:4]!=b'glTF' or struct.unpack_from('<I',b,4)[0]!=2 or struct.unpack_from('<I',b,8)[0]!=len(b):
        raise ValueError('GLB inválido')
    n,tipo=struct.unpack_from('<II',b,12)
    if tipo!=0x4e4f534a:raise ValueError('JSON GLB ausente')
    g=json.loads(b[20:20+n]);offset=20+n
    tamanho,tipo=struct.unpack_from('<II',b,offset)
    return g,b[offset+8:offset+8+tamanho],hashlib.sha256(b).hexdigest()


def analisar(caminho):
    g,b,hash_=ler(caminho)
    pais={filho:i for i,n in enumerate(g['nodes']) for filho in n.get('children',[])}
    nomes={n.get('name'):i for i,n in enumerate(g['nodes'])}
    eixos={}
    for nome in ['roda_esquerda','roda_direita','disco_encoder_esquerdo','disco_encoder_direito','servo_eixo']:
        if nome not in nomes:continue
        n=g['nodes'][nomes[nome]];pontos=[]
        for p in g['meshes'][n['mesh']]['primitives']:
            a=g['accessors'][p['attributes']['POSITION']];v=g['bufferViews'][a['bufferView']]
            if a['componentType']!=5126:raise ValueError('POSITION não float32')
            pos=np.ndarray((a['count'],3),dtype='<f4',buffer=b,
                offset=v.get('byteOffset',0)+a.get('byteOffset',0),strides=(v.get('byteStride',12),4))
            pontos.append(pos)
        pontos=np.vstack(pontos).astype(float)
        valores,vetores=np.linalg.eigh(np.cov(pontos.T))
        eixo=vetores[:,0]
        if eixo[np.argmax(np.abs(eixo))]<0:eixo=-eixo
        eixos[nome]=dict(eixo_local_geometrico=eixo.tolist(),autovalores=valores.tolist(),
            metodo='PCA eixo de menor espessura, coordenadas glTF',rotacao_inicial=n.get('rotation',[0,0,0,1]),
            translacao_inicial=n.get('translation',[0,0,0]),validacao_fisica=False)
    return dict(sha256=hash_,nos=len(g['nodes']),quantidade_materiais=len(g['materials']),meshes=len(g['meshes']),
        componentes={k:k in nomes for k in COMPONENTES},eixos=eixos,
        hierarquia={n.get('name',str(i)):g['nodes'][pais[i]].get('name') if i in pais else None for i,n in enumerate(g['nodes'])},
        materiais=[dict(nome=m.get('name'),alphaMode=m.get('alphaMode','OPAQUE'),
                        doubleSided=m.get('doubleSided',False)) for m in g['materials']])
