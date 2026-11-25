"""Replay somente leitura. Sem import de cliente WebSocket, controle ou serial."""
import json
import math
import threading
import time
from datetime import datetime,timezone

from armazenamento.banco import conectar
from armazenamento.imagens import seguro,hash_arquivo
from armazenamento.normalizacao import utc


class Reprodutor:
    def __init__(self,historico,sessao,velocidade=1.,imagens=True):
        import uuid
        uuid.UUID(sessao)
        self.historico,self.sessao,self.imagens = historico,sessao,imagens
        self.cond = threading.Condition()
        self._vel = 1.
        self._pausado = False
        self._fim = False
        self._geracao = 0
        self._posicao = 0.
        self._real = time.monotonic()
        self._busca = None
        self._inicio = None
        self.velocidade(velocidade)

    def _agora(self):
        return self._posicao+(0 if self._pausado else (time.monotonic()-self._real)*self._vel)

    def pausar(self):
        with self.cond:
            self._posicao,self._real = self._agora(),time.monotonic()
            self._pausado = True
            self.cond.notify_all()

    def retomar(self):
        with self.cond:
            self._real = time.monotonic()
            self._pausado = False
            self.cond.notify_all()

    def velocidade(self,fator):
        if not math.isfinite(fator) or not .1 <= fator <= 100:
            raise ValueError('Velocidade de replay entre 0.1 e 100')
        with self.cond:
            self._posicao,self._real = self._agora(),time.monotonic()
            self._vel = fator
            self.cond.notify_all()

    def buscar(self,instante):
        instante = utc(instante)
        with self.cond:
            self._busca = instante
            self._posicao = datetime.fromisoformat(instante).timestamp()
            self._real = time.monotonic()
            self._geracao += 1
            self.cond.notify_all()

    def reiniciar(self):
        if self._inicio:
            self.buscar(self._inicio)
        self._fim = False

    def parar(self):
        with self.cond:
            self._fim = True
            self.cond.notify_all()

    @property
    def posicao_utc(self):
        with self.cond:
            return datetime.fromtimestamp(self._agora(),timezone.utc).isoformat()

    def registros(self,inicio=None):
        """Leitura paginada sem temporização, para restaurar estado visual ao buscar."""
        return self._linhas(inicio)

    def _linhas(self,inicio=None):
        c = conectar(self.historico.raiz)
        sql = '''SELECT recebido_utc AS instante,'telemetria' AS categoria,id,mensagem_json,NULL AS caminho,NULL AS sha256 FROM telemetria WHERE sessao_id=?
          UNION ALL SELECT recebido_utc,'imagens',id,mensagem_json,caminho,sha256 FROM imagens WHERE sessao_id=?
          UNION ALL SELECT timestamp_utc,'eventos',id,detalhes_json,NULL,NULL FROM eventos WHERE sessao_id=?
          UNION ALL SELECT inicio_utc,'intervalos',id,json_object('motivo',motivo,'fim_utc',fim_utc),NULL,NULL FROM intervalos WHERE sessao_id=?
          UNION ALL SELECT timestamp_utc,'odometria',id,json_object('x_m',x_m,'y_m',y_m,
            'orientacao_rad',orientacao_rad,'distancia_m',distancia_m,'velocidade_linear_m_s',velocidade_linear_m_s,
            'velocidade_angular_rad_s',velocidade_angular_rad_s,'calibracao_json',calibracao_json,
            'validade',validade,'natureza',natureza),NULL,NULL FROM odometria WHERE sessao_id=?'''
        try:
            cursor = c.execute('SELECT * FROM ('+sql+') WHERE (? IS NULL OR instante>=?) ORDER BY instante,CASE WHEN categoria=\'odometria\' THEN 1 ELSE 0 END,categoria,id',
                               (self.sessao,)*5+(inicio,inicio))
            while True:
                rows = cursor.fetchmany(128)
                if not rows:
                    break
                for row in rows:
                    yield dict(row)
        finally:
            c.close()

    def iniciar(self):
        while not self._fim:
            geracao = self._geracao
            for row in self._linhas(self._busca):
                if self._inicio is None:
                    self._inicio = row['instante']
                    with self.cond:
                        if self._busca is None:
                            self._posicao = datetime.fromisoformat(row['instante']).timestamp()
                        self._real = time.monotonic()
                alvo = datetime.fromisoformat(row['instante']).timestamp()
                with self.cond:
                    while not self._fim and geracao == self._geracao and (self._pausado or self._agora() < alvo):
                        self.cond.wait(.05 if self._pausado else min(.05,(alvo-self._agora())/self._vel))
                    if self._fim:
                        return
                    if geracao != self._geracao:
                        break
                jpeg = None
                corrompida = False
                if row['categoria'] == 'imagens' and self.imagens:
                    p = seguro(self.historico.raiz,row['caminho'])
                    if p.is_file():
                        corrompida = p.stat().st_size>4*1024*1024 or hash_arquivo(p)!=row['sha256']
                        jpeg = p.read_bytes() if not corrompida else None
                yield dict(origem='reproducao_historica',somente_leitura=True,categoria=row['categoria'],
                    timestamp_utc=row['instante'],sessao=self.sessao,registro_id=row['id'],
                    envelope_original=json.loads(row['mensagem_json']),jpeg=jpeg,
                    imagem_corrompida=corrompida,
                    imagem_ausente=row['categoria']=='imagens' and self.imagens and jpeg is None)
            if geracao == self._geracao:
                return
