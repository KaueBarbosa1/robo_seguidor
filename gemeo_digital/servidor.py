"""HTTP apenas loopback do PC. Nenhum endpoint de movimento real ou SQL arbitrário."""
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import json
import mimetypes
from pathlib import Path
import secrets
from urllib.parse import urlsplit,parse_qs


class Aplicacao(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,ponte,porta=8780):
        super().__init__(('127.0.0.1',porta),Handler)
        self.ponte=ponte;self.token=secrets.token_urlsafe(24)
        self.raiz=Path(__file__).resolve().parent
        self.diagnostico={}


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*_):pass
    def host_valido(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
    def resposta(self,codigo,dados,tipo='application/json; charset=utf-8',headers=None):
        if not isinstance(dados,bytes):dados=json.dumps(dados,ensure_ascii=False,allow_nan=False).encode()
        try:
            self.send_response(codigo);self.send_header('Content-Type',tipo);self.send_header('Content-Length',str(len(dados)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; img-src 'self' blob:; style-src 'self' 'unsafe-inline'; connect-src 'self'")
            for k,v in (headers or {}).items():self.send_header(k,str(v))
            self.end_headers();self.wfile.write(dados)
        except ConnectionError:pass
    def do_GET(self):
        if not self.host_valido():self.resposta(403,{'erro':'Host inválido'});return
        rota=urlsplit(self.path);p=rota.path;raiz=self.server.raiz
        try:
            if p=='/api/config':
                import config as cfg
                diag=json.loads((raiz/'modelos/diagnostico.json').read_text(encoding='utf-8'))
                self.resposta(200,dict(token=self.server.token,modelo=diag,real_configurado=bool(self.server.ponte.url_real),
                    limites=dict(parada_cm=cfg.OBSTACULO_DIST_CM,liberacao_cm=cfg.OBSTACULO_LIBERACAO_CM,
                                 validade_s=cfg.LEITURA_VALIDADE_S),servo=dict(min=45,max=135,centro=90,inverter=False,offset=0)))
            elif p=='/api/estado':self.resposta(200,self.server.ponte.snapshot())
            elif p=='/api/sessoes':self.resposta(200,self.server.ponte.sessoes())
            elif p=='/api/diagnostico':self.resposta(200,self.server.diagnostico)
            elif p=='/api/trajeto':self.resposta(200,self.server.ponte.trajeto_sessao(parse_qs(rota.query).get('sessao',[''])[0]))
            elif p=='/api/quadro':
                epoch=parse_qs(rota.query).get('epoch',[''])[0]
                instancia=parse_qs(rota.query).get('instancia',[''])[0]
                if instancia and instancia!=self.server.ponte.instancia:self.resposta(409,{'erro':'Servidor reiniciado'});return
                if epoch!=str(self.server.ponte.epoch):self.resposta(409,{'erro':'Fonte trocada'});return
                q=self.server.ponte.imagem()
                if q:self.resposta(200,q[0],'image/jpeg',{'X-Frame-Id':q[1]})
                else:self.resposta(503,{'erro':'Imagem indisponível ou vencida'})
            else:
                if p=='/modelo.glb':arquivo=raiz/'modelos/carrinho_configurado.glb'
                elif p=='/':arquivo=raiz/'frontend/index.html'
                elif p.startswith('/vendor/'):
                    rel=p.removeprefix('/vendor/')
                    base=raiz/'frontend/node_modules/three'
                    arquivo=base/('examples/jsm/'+rel.removeprefix('addons/') if rel.startswith('addons/') else 'build/'+rel)
                    if not arquivo.resolve().is_relative_to(base.resolve()):raise ValueError('Caminho inválido')
                else:
                    base=raiz/'frontend';arquivo=base/p.lstrip('/')
                    if not arquivo.resolve().is_relative_to(base.resolve()):raise ValueError('Caminho inválido')
                if not arquivo.is_file():self.resposta(404,{'erro':'Arquivo não encontrado'});return
                tipo='application/javascript' if arquivo.suffix=='.js' else 'model/gltf-binary' if arquivo.suffix=='.glb' else mimetypes.guess_type(arquivo)[0] or 'application/octet-stream'
                self.resposta(200,arquivo.read_bytes(),tipo)
        except (ValueError,OSError) as exc:self.resposta(400,{'erro':str(exc)})
    def do_POST(self):
        if not self.host_valido() or not secrets.compare_digest(self.headers.get('X-Gemeo-Token',''),self.server.token):
            self.resposta(403,{'erro':'Requisição local não autorizada'});return
        origem=self.headers.get('Origin')
        if origem and origem not in (f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'):
            self.resposta(403,{'erro':'Origem inválida'});return
        try:
            tamanho=int(self.headers.get('Content-Length','0'))
            if not 0<tamanho<=65536:raise ValueError('Tamanho inválido')
            d=json.loads(self.rfile.read(tamanho))
            p=urlsplit(self.path).path;b=self.server.ponte
            if p=='/api/modo':b.modo_alterar(d['modo'])
            elif p=='/api/simulacao':b.simular(d)
            elif p=='/api/sessao':b.historico_selecionar(d['sessao'])
            elif p=='/api/replay':b.controle_replay(d)
            elif p=='/api/referencia':
                with b.lock:b.estado.odom.resetar()
            elif p=='/api/diagnostico':self.server.diagnostico=d
            else:raise ValueError('Endpoint indisponível; sem comandos físicos')
            self.resposta(200,{'ok':True})
        except (ValueError,KeyError,TypeError,RuntimeError) as exc:self.resposta(400,{'erro':str(exc)})
