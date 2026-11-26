"""Limites de imagens antes de alocar pixels no decoder; sem captura ou hardware."""
from pathlib import Path
import struct


def dimensoes_jpeg(dados, *, max_bytes=4*1024**2, max_lado=4096, max_pixels=8*1024**2):
    if not isinstance(dados,bytes) or len(dados)>max_bytes or not dados.startswith(b'\xff\xd8') or not dados.endswith(b'\xff\xd9'):
        raise ValueError('JPEG truncado, inválido ou acima do limite de bytes')
    pos=2
    while pos+4<=len(dados):
        if dados[pos]!=255:raise ValueError('Marcador JPEG inválido')
        while pos<len(dados) and dados[pos]==255:pos+=1
        if pos>=len(dados):break
        marcador=dados[pos];pos+=1
        if marcador in (0xD9,0xDA):break
        if marcador==0x01 or 0xD0<=marcador<=0xD8:continue
        if pos+2>len(dados):break
        tamanho=int.from_bytes(dados[pos:pos+2],'big')
        if tamanho<2 or pos+tamanho>len(dados):raise ValueError('Segmento JPEG inválido')
        if marcador in (0xC0,0xC1,0xC2,0xC3,0xC5,0xC6,0xC7,0xC9,0xCA,0xCB,0xCD,0xCE,0xCF):
            if tamanho<8:raise ValueError('Dimensões JPEG ausentes')
            h=int.from_bytes(dados[pos+3:pos+5],'big');w=int.from_bytes(dados[pos+5:pos+7],'big')
            validar_dimensoes(w,h,max_lado,max_pixels);return w,h
        pos+=tamanho
    raise ValueError('Dimensões JPEG ausentes')


def validar_dimensoes(w,h,max_lado,max_pixels):
    if min(w,h)<1 or max(w,h)>max_lado or w*h>max_pixels:
        raise ValueError('Resolução excessiva ou inválida antes do decode')


def ler_imagem_limitada(caminho, *, max_bytes=8*1024**2, max_lado=4096, max_pixels=8*1024**2):
    import cv2
    import numpy as np
    p=Path(caminho)
    if p.suffix.lower() not in ('.png','.jpg','.jpeg'):raise ValueError('Formato de imagem não permitido')
    with p.open('rb') as f:dados=f.read(max_bytes+1)
    if len(dados)>max_bytes:raise ValueError('Arquivo de imagem acima do limite')
    if dados.startswith(b'\xff\xd8'):
        dimensoes_jpeg(dados,max_bytes=max_bytes,max_lado=max_lado,max_pixels=max_pixels)
    elif len(dados)>=33 and dados[:8]==b'\x89PNG\r\n\x1a\n' and dados[8:16]==b'\x00\x00\x00\rIHDR':
        w,h=struct.unpack('>II',dados[16:24]);validar_dimensoes(w,h,max_lado,max_pixels)
    else:raise ValueError('Cabeçalho de imagem inválido')
    imagem=cv2.imdecode(np.frombuffer(dados,np.uint8),cv2.IMREAD_COLOR)
    if imagem is None:raise ValueError('Imagem não decodificável')
    validar_dimensoes(imagem.shape[1],imagem.shape[0],max_lado,max_pixels)
    return imagem
