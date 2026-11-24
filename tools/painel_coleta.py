"""Painel local de coleta ESP32: exibe somente JPEGs ja gravados. Sem motores."""
import argparse
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import signal
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.coletar_esp32_cam import executar, URL_PADRAO
from visao.recorte_esp32 import RecorteESP32

HTML = '''<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Pista · Coleta</title>
<style>body{margin:0;background:#101923;color:#edf4fb;font:18px system-ui}main{max-width:1000px;margin:auto;padding:24px}h1{font-size:2rem}p{line-height:1.6}img{width:100%;max-height:65vh;object-fit:contain;background:#080e15;border-radius:12px}#estado{font-size:1.4rem;color:#ffd36b}section{padding:16px;background:#203044;border-radius:12px;margin:16px 0}small{font-size:1rem;color:#b8cadd}</style>
<main><small>CÂMERA DO CARRINHO / COLETA LOCAL</small><h1>Gravação da pista</h1>
<section><strong id="estado">Conectando…</strong><p id="dados">Aguardando quadros</p><small id="pasta"></small></section>
<img id="imagem" alt="Último quadro salvo da câmera" hidden>
<p>Prévia dos JPEGs salvos na Raspberry Pi. Controle pelo Bluetooth. Para encerrar a coleta, pressione Ctrl+C no terminal da Pi.</p></main>
<script>
let ultimo=0;
async function atualizar(){try{
 const r=await fetch('/status',{cache:'no-store'});if(!r.ok)throw Error();const s=await r.json();
 const recente=s.idade_s!==null&&s.idade_s<2;
 document.getElementById('estado').textContent=s.erro?'ERRO NA COLETA':s.encerrado?'COLETA ENCERRADA':s.falha?'FALHA DE CAPTURA':recente?'GRAVANDO · quadro salvo recentemente':'AGUARDANDO / CAPTURA ATRASADA';
 document.getElementById('dados').textContent=`${s.quadros} quadros salvos · ${s.falhas} falhas · último quadro: ${s.idade_s===null?'nenhum':s.idade_s.toFixed(1)+' s atrás'}`;
 document.getElementById('pasta').textContent=s.pasta+(s.erro?' · '+s.erro:'');
 const im=document.getElementById('imagem');im.hidden=!recente||s.falha||!!s.erro||s.encerrado;
 if(s.quadros!==ultimo){im.src='/quadro?v='+s.quadros;ultimo=s.quadros;}
 }catch(e){document.getElementById('estado').textContent='SEM CONEXÃO COM A PI';document.getElementById('imagem').hidden=true;}
 setTimeout(atualizar,500);
}atualizar();</script></html>'''


class Estado:
    def __init__(self, pasta):
        self.lock = threading.Lock()
        self.jpeg = None
        self.instante = None
        self.dados = dict(quadros=0, falhas=0, falha=False, encerrado=False, erro='', pasta=str(pasta))

    def observar(self, linha, jpeg):
        with self.lock:
            self.dados['falha'] = linha['status'] != 'ok'
            if jpeg is not None:
                self.jpeg = jpeg
                self.instante = time.monotonic()
                self.dados['quadros'] += 1
            else:
                self.dados['falhas'] += 1

    def status(self):
        with self.lock:
            return dict(self.dados, idade_s=None if self.instante is None else time.monotonic()-self.instante)


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, estado, **kwargs):
        self.estado = estado
        super().__init__(*args, **kwargs)

    def do_GET(self):
        rota = self.path.split('?')[0]
        if rota == '/':
            dados, tipo = HTML.encode(), 'text/html; charset=utf-8'
        elif rota == '/status':
            dados, tipo = json.dumps(self.estado.status()).encode(), 'application/json'
        elif rota == '/quadro':
            with self.estado.lock:
                dados = self.estado.jpeg
            if dados is None:
                self.send_error(404)
                return
            tipo = 'image/jpeg'
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', tipo)
        self.send_header('Content-Length', str(len(dados)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        try:
            self.wfile.write(dados)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *_):
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--saida', required=True, type=Path)
    ap.add_argument('--url', default=URL_PADRAO)
    ap.add_argument('--host', default='0.0.0.0')
    ap.add_argument('--porta', type=int, default=8080)
    ap.add_argument('--duracao', type=float, default=180)
    ap.add_argument('--intervalo', type=float, default=.1)
    ap.add_argument('--timeout', type=float, default=3)
    ap.add_argument('--nota', default='Coleta pelo painel local')
    a = ap.parse_args()
    if a.saida.exists():
        ap.error('--saida precisa ser uma pasta nova')
    if any(not math.isfinite(v) or v <= 0 for v in (a.duracao, a.timeout)) or not math.isfinite(a.intervalo) or a.intervalo < 0:
        ap.error('duracao/timeout positivos e intervalo nao negativo, todos finitos')
    a.sem_janela, a.previa, a.quadros = True, False, None
    estado, parar = Estado(a.saida.resolve()), threading.Event()
    servidor = ThreadingHTTPServer((a.host, a.porta), partial(Handler, estado=estado))
    servidor.daemon_threads = True

    def coletar():
        try:
            executar(a, RecorteESP32(0, 80, 320, 160), estado.observar, parar)
        except Exception as exc:
            with estado.lock:
                estado.dados['erro'] = str(exc)
        finally:
            with estado.lock:
                estado.dados['encerrado'] = True

    def interromper(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interromper)
    worker = threading.Thread(target=coletar)
    worker.start()
    print(f'No PC: http://IP_DA_PI:{a.porta} · Ctrl+C encerra. Use somente na rede local confiavel.', flush=True)
    try:
        servidor.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:
        pass
    finally:
        parar.set()
        servidor.server_close()
        worker.join()


if __name__ == '__main__':
    main()
