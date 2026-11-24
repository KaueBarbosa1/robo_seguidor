"""Painel local: previa e gravacao sob comando, compartilhando a fonte da main."""
import argparse
import csv
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import secrets
import signal
import sys
import threading
import time
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.coletar_esp32_cam import CAMPOS, gravar_atomico, utc_agora
from visao.esp32_cam import CameraESP32, URL_PADRAO

HTML = '''<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Pista · Câmera e gravação</title>
<style>body{margin:0;background:#101923;color:#edf4fb;font:18px system-ui}main{max-width:1000px;margin:auto;padding:24px}h1{font-size:2rem}p{line-height:1.6}img{width:100%;max-height:60vh;object-fit:contain;background:#080e15;border-radius:12px}#estado{font-size:1.4rem;color:#ffd36b}section{padding:16px;background:#203044;border-radius:12px;margin:16px 0}small{font-size:1rem;color:#b8cadd}button{font:inherit;padding:14px 22px;margin:8px 8px 8px 0;border:0;border-radius:8px;background:#62dbb2;color:#102020;cursor:pointer}button:disabled{opacity:.4;cursor:default}#parar{background:#ffac9e}</style>
<main><small>CARRINHO / CÂMERA COMPARTILHADA COM A VISÃO</small><h1>Pista ao vivo</h1>
<section><strong id="estado">Conectando…</strong><p id="dados">Aguardando câmera</p>
<button id="iniciar" disabled>Iniciar gravação</button><button id="parar" disabled>Parar gravação</button>
<p id="mensagem" role="status"></p><small id="pasta"></small></section>
<img id="imagem" alt="Prévia atual da câmera do carrinho" hidden>
<p>Abrir esta página não inicia movimento nem gravação. Dirija pelo Bluetooth. Gravar ou parar a gravação não altera o modo do carrinho.</p>
<p>A prévia pode atrasar. Acompanhe também o carrinho diretamente. São salvos JPEGs originais para preparar o treinamento.</p></main>
<script>
let ultimo=-1,ocupado=false;
async function acao(nome){ocupado=true;document.getElementById('iniciar').disabled=true;document.getElementById('parar').disabled=true;
 try{const r=await fetch('/'+nome,{method:'POST',headers:{'X-Painel-Token':'__TOKEN__'}});const s=await r.json();document.getElementById('mensagem').textContent=s.mensagem||s.erro||'';}catch(e){document.getElementById('mensagem').textContent='Sem resposta da Pi. Confira o estado antes de tentar novamente.';}finally{ocupado=false;}}
 document.getElementById('iniciar').onclick=()=>acao('iniciar');document.getElementById('parar').onclick=()=>acao('parar');
async function atualizar(){try{
 const r=await fetch('/status',{cache:'no-store'});if(!r.ok)throw Error();const s=await r.json();
 document.getElementById('estado').textContent=s.gravando?(s.camera_ok?'GRAVANDO':'GRAVAÇÃO ATIVA · CÂMERA INDISPONÍVEL'):(s.camera_ok?'CÂMERA AO VIVO · SEM GRAVAR':'AGUARDANDO CÂMERA');
 document.getElementById('dados').textContent=`${s.quadros} quadros salvos nesta sessão${s.gravando?' · restam '+Math.ceil(s.restante_s)+' s':''} · câmera: ${s.camera_status} · último salvo: ${s.idade_salvo_s===null?'nenhum':s.idade_salvo_s.toFixed(1)+' s atrás'}`;
 document.getElementById('pasta').textContent=s.pasta+(s.erro?' · ERRO: '+s.erro:'');
 document.getElementById('iniciar').disabled=ocupado||s.gravando||!s.camera_ok;
 document.getElementById('parar').disabled=ocupado||!s.gravando;
 const im=document.getElementById('imagem');im.hidden=!s.camera_ok;
 if(s.frame_id!==ultimo){im.src='/quadro?v='+s.frame_id;ultimo=s.frame_id;}
 }catch(e){document.getElementById('estado').textContent='SEM CONEXÃO COM A PI';document.getElementById('imagem').hidden=true;document.getElementById('iniciar').disabled=true;document.getElementById('parar').disabled=true;}
 setTimeout(atualizar,500);
}atualizar();</script></html>'''


class Coleta:
    """Consome snapshots sem ler a ESP32 novamente ou segurar locks do controle."""
    def __init__(self, fonte, raiz, duracao=180., intervalo=.1, nota='Coleta pelo painel'):
        self.fonte, self.raiz = fonte, Path(raiz)
        self.duracao, self.intervalo, self.nota = duracao, intervalo, nota
        self.lock = threading.RLock()
        self.fim = threading.Event()
        self.thread = None
        self.jpeg = None
        self.quadro = None
        self.frame_id = 0
        self.arquivo = None
        self.csv = None
        self.manifesto = None
        self.pasta = None
        self.total = 0
        self.erro = ''
        self.ultimo_salvo = None
        self.inicio = 0.

    def iniciar_worker(self):
        self.thread = threading.Thread(target=self._loop, name='painel-coleta', daemon=True)
        self.thread.start()

    def _camera_ok(self):
        return (self.fonte.saude()['status'] == 'ok' and self.quadro is not None and
                self.quadro.idade_recepcao_limite_ms/1000 +
                max(0., time.monotonic()-self.quadro.recepcao_monotonica) <= self.fonte.idade_max_s)

    def iniciar_gravacao(self):
        with self.lock:
            if self.fim.is_set():
                raise RuntimeError('Painel encerrando')
            if self.arquivo is not None:
                return 'Gravação já está ativa'
            if not self._camera_ok():
                raise RuntimeError('Câmera sem quadro recente; aguarde a conexão')
            pasta = self.raiz / ('sessao_' + time.strftime('%Y%m%d_%H%M%S') + '_' + uuid4().hex[:8])
            pasta.mkdir(parents=True, exist_ok=False)
            (pasta/'quadros').mkdir()
            manifesto = dict(schema='coleta_esp32_v1', sessao_id=uuid4().hex, nome=pasta.name,
                             inicio_utc=utc_agora(), estado='em_andamento', url=self.fonte.url,
                             nota=self.nota, jpeg_largura_altura=[320, 240], csv_capturas='capturas.csv',
                             intervalo_s=self.intervalo, limite_duracao_s=self.duracao,
                             origem='fonte_compartilhada_main_ou_painel')
            gravar_atomico(pasta/'sessao.json', json.dumps(manifesto, ensure_ascii=False, indent=2).encode())
            arquivo = (pasta/'capturas.csv').open('x', encoding='utf-8', newline='', buffering=1)
            try:
                writer = csv.DictWriter(arquivo, fieldnames=CAMPOS)
                writer.writeheader()
            except Exception:
                arquivo.close()
                raise
            self.pasta, self.manifesto = pasta, manifesto
            self.arquivo, self.csv = arquivo, writer
            self.total, self.erro, self.ultimo_salvo = 0, '', None
            self.inicio = time.monotonic()
            return 'Gravação iniciada'

    def parar_gravacao(self, estado='encerrada'):
        with self.lock:
            if self.arquivo is None:
                return 'Gravação já está parada'
            arquivo, self.arquivo = self.arquivo, None
            try:
                arquivo.close()
                self.manifesto.update(estado=estado, fim_utc=utc_agora(), quadros=self.total,
                                      duracao_s=time.monotonic()-self.inicio)
                gravar_atomico(self.pasta/'sessao.json', json.dumps(self.manifesto, ensure_ascii=False, indent=2).encode())
            finally:
                self.csv = None
            return 'Gravação encerrada; arquivos preservados'

    def receber(self, frame_id, q):
        with self.lock:
            self.frame_id, self.quadro, self.jpeg = frame_id, q, q.jpeg
            agora = time.monotonic()
            if self.arquivo is None:
                return
            if agora-self.inicio >= self.duracao:
                self.parar_gravacao()
                return
            if not self._camera_ok() or (self.ultimo_salvo is not None and agora-self.ultimo_salvo < self.intervalo):
                return
            nome = f'quadros/quadro_{self.total+1:06d}.jpg'
            gravar_atomico(self.pasta/nome, q.jpeg)
            self.csv.writerow(dict(tentativa=self.total+1, status='ok', quadro=self.total+1, jpeg=nome,
                                   recepcao_utc=q.recepcao_utc, tempo_s=agora-self.inicio, bytes=len(q.jpeg),
                                   http_ms=q.http_ms, idade_envio_ms=q.idade_envio_ms,
                                   idade_recepcao_limite_ms=q.idade_recepcao_limite_ms, erro=''))
            self.total += 1
            self.ultimo_salvo = agora

    def _loop(self):
        ultimo = 0
        while not self.fim.is_set():
            try:
                resultado = self.fonte.proximo_jpeg_detalhado(ultimo, timeout=.2)
                if resultado is not None:
                    ultimo, q = resultado
                    self.receber(ultimo, q)
                with self.lock:
                    if self.arquivo is not None and time.monotonic()-self.inicio >= self.duracao:
                        self.parar_gravacao()
            except Exception as exc:
                with self.lock:
                    self.erro = str(exc)
                    try:
                        self.parar_gravacao('erro')
                    except Exception as fechar_exc:
                        self.erro += '; ' + str(fechar_exc)
                self.fim.wait(.2)

    def status(self):
        with self.lock:
            return dict(gravando=self.arquivo is not None, camera_ok=self._camera_ok(),
                        camera_status=self.fonte.saude()['status'], frame_id=self.frame_id,
                        quadros=self.total, pasta=str(self.pasta or ''), erro=self.erro,
                        restante_s=max(0., self.duracao-(time.monotonic()-self.inicio)) if self.arquivo else None,
                        idade_salvo_s=None if self.ultimo_salvo is None else time.monotonic()-self.ultimo_salvo)

    def imagem(self):
        with self.lock:
            return self.jpeg if self._camera_ok() else None

    def fechar(self):
        self.fim.set()
        if self.thread:
            self.thread.join(timeout=1.)
        self.parar_gravacao()


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, coleta, token, **kwargs):
        self.coleta, self.token = coleta, token
        super().__init__(*args, **kwargs)

    def responder(self, codigo, dados, tipo='application/json'):
        self.send_response(codigo)
        self.send_header('Content-Type', tipo)
        self.send_header('Content-Length', str(len(dados)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        try:
            self.wfile.write(dados)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        rota = self.path.split('?')[0]
        if rota == '/':
            self.responder(200, HTML.replace('__TOKEN__', self.token).encode(), 'text/html; charset=utf-8')
        elif rota == '/status':
            self.responder(200, json.dumps(self.coleta.status()).encode())
        elif rota == '/quadro':
            jpeg = self.coleta.imagem()
            self.responder(200 if jpeg else 503, jpeg or b'Camera indisponivel', 'image/jpeg' if jpeg else 'text/plain')
        else:
            self.send_error(404)

    def do_POST(self):
        if not secrets.compare_digest(self.headers.get('X-Painel-Token', ''), self.token):
            self.responder(403, b'{"erro":"Reabra o painel para atualizar a sessao"}')
            return
        try:
            if self.path == '/iniciar':
                mensagem = self.coleta.iniciar_gravacao()
            elif self.path == '/parar':
                mensagem = self.coleta.parar_gravacao()
            else:
                self.send_error(404)
                return
            self.responder(200, json.dumps(dict(mensagem=mensagem)).encode())
        except (RuntimeError, OSError) as exc:
            with self.coleta.lock:
                self.coleta.erro = str(exc)
            self.responder(409, json.dumps(dict(erro=str(exc))).encode())

    def log_message(self, *_):
        pass


class Painel:
    def __init__(self, fonte, raiz, host='0.0.0.0', porta=8080, duracao=180., intervalo=.1):
        self.coleta = Coleta(fonte, raiz, duracao, intervalo)
        self.servidor = ThreadingHTTPServer((host, porta), partial(Handler, coleta=self.coleta, token=secrets.token_urlsafe(32)))
        self.servidor.daemon_threads = True
        self.thread = threading.Thread(target=self.servidor.serve_forever, kwargs=dict(poll_interval=.2), daemon=True)

    def iniciar(self):
        self.coleta.iniciar_worker()
        self.thread.start()

    def parar(self):
        try:
            self.servidor.shutdown()
            self.servidor.server_close()
        finally:
            self.coleta.fechar()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--saida', type=Path, default=Path('dados_pista'), help='pasta base; cada clique cria uma sessao')
    ap.add_argument('--url', default=URL_PADRAO)
    ap.add_argument('--host', default='0.0.0.0')
    ap.add_argument('--porta', type=int, default=8080)
    ap.add_argument('--duracao', type=float, default=180)
    ap.add_argument('--intervalo', type=float, default=.1)
    ap.add_argument('--timeout', type=float, default=1)
    a = ap.parse_args()
    if any(not math.isfinite(v) or v <= 0 for v in (a.duracao, a.timeout)) or not math.isfinite(a.intervalo) or a.intervalo < 0:
        ap.error('duracao/timeout positivos e intervalo nao negativo, todos finitos')
    fonte = CameraESP32(a.url, timeout=a.timeout)
    painel = Painel(fonte, a.saida, a.host, a.porta, a.duracao, a.intervalo)
    def interromper(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interromper)
    try:
        fonte.iniciar()
        painel.iniciar()
        print(f'Painel aguardando: http://IP_DA_PI:{a.porta} · inicie a gravacao pelo navegador.', flush=True)
        while True:
            time.sleep(.5)
    except KeyboardInterrupt:
        pass
    finally:
        painel.parar()
        fonte.parar()


if __name__ == '__main__':
    main()
