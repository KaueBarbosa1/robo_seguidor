"""JPEGs imutáveis fora do SQLite; caminhos relativos, hash e associação explícita."""
import hashlib
import os
from pathlib import Path
import shutil
import uuid

from armazenamento.normalizacao import inserir, js, original, sessao, utc


def seguro(raiz, relativo):
    raiz = Path(raiz).resolve()
    caminho = (raiz/relativo).resolve()
    if not caminho.is_relative_to(raiz):
        raise ValueError('Caminho fora do diretorio de dados')
    return caminho


def hash_arquivo(caminho):
    h=hashlib.sha256()
    with Path(caminho).open('rb') as f:
        for bloco in iter(lambda:f.read(1024*1024),b''):
            h.update(bloco)
    return h.hexdigest()


def validar_jpeg(jpeg):
    if len(jpeg)>4*1024*1024 or not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):
        raise ValueError('JPEG incompleto')
    # Verificar dimensões antes do decoder, para limitar a alocação descompactada.
    i=2;dimensoes=None
    sof={0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf}
    while i+4<len(jpeg):
        if jpeg[i]!=0xff:break
        while i<len(jpeg) and jpeg[i]==0xff:i+=1
        if i+3>=len(jpeg):break
        marca=jpeg[i];i+=1
        tamanho=int.from_bytes(jpeg[i:i+2],'big')
        if tamanho<2 or i+tamanho>len(jpeg):break
        if marca in sof and tamanho>=8:
            altura=int.from_bytes(jpeg[i+3:i+5],'big')
            largura=int.from_bytes(jpeg[i+5:i+7],'big')
            dimensoes=largura,altura
            break
        i+=tamanho
    if not dimensoes or min(dimensoes)<=0 or max(dimensoes)>4096 or dimensoes[0]*dimensoes[1]>1920*1080:
        raise ValueError('Dimensoes JPEG ausentes ou acima do limite administrativo')
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise ValueError('Validacao JPEG requer dependencias PC de imagens') from exc
    try:
        imagem = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    except cv2.error as exc:
        raise ValueError('JPEG nao decodificavel') from exc
    if imagem is None:
        raise ValueError('JPEG nao decodificavel')
    return int(imagem.shape[1]), int(imagem.shape[0])


class Arquivos:
    def __init__(self, opcoes):
        self.op = opcoes
        self.raiz = Path(opcoes.raiz).resolve()
        self.raiz.mkdir(parents=True, exist_ok=True)
        self.bytes_imagens = sum(p.stat().st_size for p in (self.raiz/'imagens').rglob('*.jpg'))

    def espaco(self, novos_bytes=0, imagens=False):
        livre = shutil.disk_usage(self.raiz).free
        if livre-novos_bytes < self.op.reserva_livre_bytes:
            raise OSError('Reserva de espaco livre atingida')
        if imagens and self.bytes_imagens+novos_bytes > self.op.max_imagens_bytes:
            raise OSError('Limite administrativo de imagens atingido')

    def criar(self, sessao_id, sequencia, jpeg):
        uuid.UUID(sessao_id)
        largura, altura = validar_jpeg(jpeg)
        hash_ = hashlib.sha256(jpeg).hexdigest()
        relativo = f'imagens/{sessao_id}/{sequencia}_{hash_}.jpg'
        destino = seguro(self.raiz, relativo)
        novo = not destino.exists()
        if novo:
            self.espaco(len(jpeg), True)
            destino.parent.mkdir(parents=True, exist_ok=True)
            temporario = destino.with_suffix('.'+uuid.uuid4().hex+'.part')
            try:
                with temporario.open('xb') as f:
                    f.write(jpeg)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temporario, destino)
            finally:
                if temporario.exists():
                    temporario.unlink()
            self.bytes_imagens += len(jpeg)
        elif hash_arquivo(destino) != hash_:
            raise OSError('Arquivo existente diverge; nao sobrescrito')
        return relativo, largura, altura, hash_, novo

    def reverter(self, caminhos):
        # Somente arquivos novos desta transação, jamais histórico já confirmado.
        for relativo in caminhos:
            p = seguro(self.raiz, relativo)
            if p.exists():
                tamanho = p.stat().st_size
                p.unlink()
                self.bytes_imagens -= tamanho


def gravar(c, arquivos, msg, jpeg, gravacao, modo, novos):
    if (msg['tipo'] != 'imagem' or not isinstance(jpeg,bytes) or
            type(msg['dados'].get('frame_id')) is not int or msg['dados']['frame_id'] < 0 or
            msg['dados'].get('jpeg_bytes') != len(jpeg)):
        raise ValueError('Metadados de imagem invalidos')
    recebido = utc(msg.get('recepcao_utc'))
    sessao(c, msg, gravacao, recebido, modo)
    existente = c.execute('SELECT id FROM imagens WHERE sessao_id=? AND canal=? AND sequencia=?',
                         (msg['sessao'],'imagens',msg['sequencia'])).fetchone()
    if existente:
        inserir(c,'imagens_gravacoes',dict(imagem_id=existente[0],gravacao_id=gravacao),True)
        return existente[0], False
    caminho, largura, altura, hash_, novo = arquivos.criar(msg['sessao'], msg['sequencia'], jpeg)
    if novo:
        novos.append(caminho)
    cur = inserir(c,'imagens',dict(sessao_id=msg['sessao'],canal='imagens',sequencia=msg['sequencia'],
        frame_id=msg['dados']['frame_id'],origem_utc=utc(msg['timestamp']),recebido_utc=recebido,
        origem_mono_s=msg['monotonic_s']-msg['idade_envio_s'],caminho=caminho,largura=largura,
        altura=altura,tamanho_bytes=len(jpeg),formato='image/jpeg',sha256=hash_,simulado=int(msg['simulado']),
        estado='verificado',associacao_tipo='nenhuma',mensagem_json=js(original(msg))))
    inserir(c,'imagens_gravacoes',dict(imagem_id=cur.lastrowid,gravacao_id=gravacao),True)
    return cur.lastrowid, True


def associar(c, sessao_id, tolerancia):
    imagens = c.execute("SELECT id,frame_id,origem_mono_s FROM imagens WHERE sessao_id=? AND telemetria_id IS NULL "
                        'ORDER BY id DESC LIMIT 256', (sessao_id,)).fetchall()
    for imagem in imagens:
        exata = c.execute('SELECT t.id,ABS(t.origem_mono_s-?) AS desvio FROM telemetria t '
            'JOIN visao_computacional v ON v.telemetria_id=t.id '
            'WHERE t.sessao_id=? AND v.frame_id=? ORDER BY desvio LIMIT 1',
            (imagem['origem_mono_s'],sessao_id,imagem['frame_id'])).fetchone()
        tipo = 'frame_id'
        if exata is None:
            exata = c.execute('SELECT id,ABS(origem_mono_s-?) AS desvio FROM telemetria '
                'WHERE sessao_id=? AND origem_mono_s BETWEEN ? AND ? ORDER BY desvio LIMIT 1',
                (imagem['origem_mono_s'],sessao_id,imagem['origem_mono_s']-tolerancia,
                 imagem['origem_mono_s']+tolerancia)).fetchone()
            tipo = 'temporal_estimado'
        if exata:
            c.execute('UPDATE imagens SET telemetria_id=?,associacao_tipo=?,desvio_temporal_s=? WHERE id=?',
                      (exata['id'],tipo,exata['desvio'],imagem['id']))
