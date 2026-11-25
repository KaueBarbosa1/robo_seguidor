"""Extensão do HTTP local da etapa 4; sem segunda captura, rede ou banco."""
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from contextlib import closing
import json,mimetypes,secrets,sqlite3,time,uuid,zipfile
from gemeo_digital.servidor import Aplicacao,Handler
from armazenamento.exportacao import exportar
from armazenamento.banco import conectar
from armazenamento.imagens import seguro,hash_arquivo
from central_monitoramento.consultas import filtros

RAIZ=Path(__file__).resolve().parent

class AplicacaoCentral(Aplicacao):
    def __init__(self,ponte,porta=8780):
        super().__init__(ponte,porta);self.RequestHandlerClass=HandlerCentral;self.cinza=None;self.consultas_ms=[]

class HandlerCentral(Handler):
    def pagina(self):
        original=(self.server.raiz/'frontend/index.html').read_text(encoding='utf-8')
        corpo=original.split('<body>',1)[1].split('</body>',1)[0]
        corpo=corpo[:corpo.rfind('<script type="module"')]
        html=(RAIZ/'frontend/index.html').read_text(encoding='utf-8').replace('<!-- GEMEO -->',corpo)
        self.resposta(200,html.encode(),'text/html; charset=utf-8')

    def do_GET(self):
        if not self.host_valido():self.resposta(403,{'erro':'Host inválido'});return
        u=urlsplit(self.path);p=u.path;q={k:v[-1] for k,v in parse_qs(u.query).items()};b=self.server.ponte;inicio=time.perf_counter()
        try:
            if p=='/':self.pagina();return
            if p=='/gemeo':
                self.resposta(200,(self.server.raiz/'frontend/index.html').read_bytes(),'text/html; charset=utf-8');return
            if p.startswith('/central/'):
                raiz=RAIZ/'frontend';arquivo=(raiz/p.removeprefix('/central/')).resolve()
                if not arquivo.is_relative_to(raiz.resolve()) or not arquivo.is_file():raise ValueError('Recurso não encontrado')
                self.resposta(200,arquivo.read_bytes(),'application/javascript' if arquivo.suffix=='.js' else mimetypes.guess_type(arquivo)[0]);return
            if not p.startswith('/api/central/'):super().do_GET();return
            rota=p.removeprefix('/api/central/')
            if rota=='sessoes':d=b.consultas.sessoes(q)
            elif rota=='resumo':d=b.consultas.resumo(q['sessao'])
            elif rota=='janela':d=b.consultas.janela(q['sessao'],q['fim'],q.get('segundos',60),q.get('pontos',240))
            elif rota=='experimentos':d=b.consultas.experimentos()
            elif rota=='treinos':
                from central_monitoramento.treinamentos import listar
                d=listar()
            elif rota=='dados':
                f=json.loads(q.get('filtros','{}'));d=b.historico.consultar(q['categoria'],limite=int(q.get('limite',50)),pagina=int(q.get('pagina',0)),**filtros(f))
            elif rota=='eventos':
                pagina=int(q.get('pagina',0));limite=50
                if not 0<=pagina<=100000:raise ValueError('Página inválida')
                cond=[];args=[]
                for campo in ['sessao_id','gravidade','categoria','origem']:
                    if q.get(campo):cond.append(campo+'=?');args.append(q[campo])
                if q.get('busca'):cond.append('(descricao LIKE ? OR detalhes_json LIKE ?)');args += ['%'+q['busca'][:200]+'%']*2
                for campo,op in [('inicio','>='),('fim','<=')]:
                    if q.get(campo):cond.append('timestamp_utc'+op+'?');args.append(q[campo])
                with closing(conectar(b.historico.raiz)) as c:
                    d=[dict(r) for r in c.execute('SELECT * FROM eventos'+(' WHERE '+' AND '.join(cond) if cond else '')+' ORDER BY timestamp_utc DESC LIMIT ? OFFSET ?',(*args,limite,pagina*limite))]
            elif rota=='quadro-cinza':
                if q.get('epoch')!=str(b.epoch):raise ValueError('Fonte trocada')
                frame=b.imagem()
                if frame is None:self.resposta(503,{'erro':'Sem frame válido'});return
                chave=(b.epoch,frame[1]);cache=self.server.cinza
                if not cache or cache[0][0]!=b.epoch or (cache[0]!=chave and time.monotonic()-cache[1]>=1.):
                    import cv2,numpy as np
                    img=cv2.imdecode(np.frombuffer(frame[0],np.uint8),cv2.IMREAD_GRAYSCALE)
                    if img is None:raise ValueError('JPEG inválido')
                    _,jpeg=cv2.imencode('.jpg',img);cache=(chave,time.monotonic(),jpeg.tobytes());self.server.cinza=cache
                self.resposta(200,cache[2],'image/jpeg');return
            elif rota=='imagem':
                with closing(conectar(b.historico.raiz)) as c:r=c.execute('SELECT * FROM imagens WHERE id=?',(int(q['id']),)).fetchone()
                if r is None:raise ValueError('Imagem não encontrada')
                arquivo=seguro(b.historico.raiz,r['caminho'])
                if not arquivo.is_file() or arquivo.stat().st_size>4*1024**2 or hash_arquivo(arquivo)!=r['sha256']:raise ValueError('Imagem ausente ou hash inválido')
                self.resposta(200,arquivo.read_bytes(),'image/jpeg');return
            elif rota=='download':
                ident=str(uuid.UUID(q['id']));arquivo=b.historico.raiz/'exportacoes'/ident/'analise.zip'
                if not arquivo.is_file():raise ValueError('Exportação não encontrada')
                self.send_response(200);self.send_header('Content-Type','application/zip');self.send_header('Content-Disposition',f'attachment; filename="analise_{ident}.zip"');self.send_header('Content-Length',str(arquivo.stat().st_size));self.end_headers()
                with arquivo.open('rb') as f:
                    while trecho:=f.read(65536):self.wfile.write(trecho)
                return
            else:raise ValueError('Consulta não disponível')
            self.resposta(200,d)
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error) as exc:self.resposta(400,{'erro':str(exc)})
        finally:
            if p.startswith('/api/central/') and not p.endswith(('download','imagem','quadro-cinza')):
                self.server.consultas_ms=(self.server.consultas_ms+[1000*(time.perf_counter()-inicio)])[-256:]
                a=sorted(self.server.consultas_ms);b.consultas_metricas=dict(n=len(a),media_ms=sum(a)/len(a),p95_ms=a[int((len(a)-1)*.95)],escopo='API de consultas: execução e serialização local')

    def do_POST(self):
        rota=urlsplit(self.path).path
        if not rota.startswith('/api/central/'):super().do_POST();return
        # Consumir o corpo limitado antes de responder evita reset de conexão
        # no Windows ao fechar um POST rejeitado com bytes ainda por ler.
        try:
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=65536:raise ValueError('Corpo inválido')
            self.connection.settimeout(5.)
            corpo=self.rfile.read(n)
        except (ValueError,OSError) as exc:
            self.resposta(400,{'erro':str(exc)});return
        if not self.host_valido() or not secrets.compare_digest(self.headers.get('X-Gemeo-Token',''),self.server.token):self.resposta(403,{'erro':'Requisição local não autorizada'});return
        origem=self.headers.get('Origin')
        if origem and origem not in (f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'):self.resposta(403,{'erro':'Origem inválida'});return
        try:
            d=json.loads(corpo)
            if not isinstance(d,dict):raise ValueError('Objeto JSON esperado')
            b=self.server.ponte;r=rota.removeprefix('/api/central/')
            if r=='gravacao':resultado=b.gravacao_comando(d)
            elif r=='cenario':resultado=b.cenario_comando(d)
            elif r=='preferencias':resultado=b.configurar(d)
            elif r=='conexao':resultado=b.conexao_configurar(d['url'])
            elif r=='armazenamento':
                permitidos={'imagens','imagens_eventos','imagens_fps','max_bytes','max_imagens_bytes'}
                if set(d)-permitidos:raise ValueError('Opção inválida')
                for k,v in d.items():
                    if k in ('imagens','imagens_eventos'):
                        if type(v)is not bool:raise ValueError('Booleano esperado')
                    elif type(v) not in (int,float) or not math_finito(v) or v<=0:raise ValueError('Limite inválido')
                resultado=b.escritor_externo.comandar('opcoes_locais',**d)
            elif r=='sessao-metadados':resultado=b.escritor_externo.comandar('metadados_sessao',**d)
            elif r=='experimento':
                permitidos={'nome','objetivo','modo','algoritmo','condicoes','repeticao','configuracoes','observacoes'}
                if set(d)-permitidos:raise ValueError('Campo de experimento inválido')
                if any(isinstance(v,str) and len(v)>10000 for v in d.values()):raise ValueError('Texto extenso demais')
                resultado=b.escritor_externo.comandar('experimento',**d)
            elif r=='associar':resultado=b.escritor_externo.comandar('associar_sessoes',**d)
            elif r=='comparar':resultado=b.consultas.comparar(d['sessoes'])
            elif r=='exportar':
                f=filtros(d.get('filtros',{}));categorias=d.get('categorias')
                if not isinstance(categorias,list) or not 1<=len(categorias)<=15:raise ValueError('Categorias inválidas')
                selecionadas=d.get('sessoes')
                if selecionadas is not None:
                    if not isinstance(selecionadas,list) or not 1<=len(selecionadas)<=6 or 'sessao' in f:raise ValueError('Selecione de 1 a 6 sessões')
                    for sid in selecionadas:uuid.UUID(sid)
                    pasta=b.historico.raiz/'exportacoes'/str(uuid.uuid4());pasta.mkdir(parents=True,exist_ok=False);contagens={}
                    for sid in selecionadas:
                        _,ct=exportar(b.historico,categorias,destino=pasta/sid,**dict(f,sessao=sid));contagens[sid]=ct
                else:pasta,contagens=exportar(b.historico,categorias,**f)
                (pasta/'resumo_limitacoes.json').write_text(json.dumps(b.consultas.resumo(f['sessao']) if f.get('sessao') else {'filtros':f,'nota':'Resumo por sessão disponível na central; resultados exploratórios, sem conclusão científica automática.'},ensure_ascii=False,allow_nan=False),encoding='utf-8')
                with zipfile.ZipFile(pasta/'analise.zip','w',zipfile.ZIP_DEFLATED) as z:
                    for a in pasta.rglob('*'):
                        if a.is_file() and a.suffix in ('.csv','.json'):z.write(a,a.relative_to(pasta).as_posix())
                resultado=dict(id=pasta.name,contagens=contagens,url='/api/central/download?id='+pasta.name)
            else:raise ValueError('Operação não disponível; atuação real bloqueada')
            self.resposta(200,{'ok':True,'resultado':resultado})
        except (ValueError,KeyError,TypeError,RuntimeError,OSError,sqlite3.Error) as exc:self.resposta(400,{'erro':str(exc)})

def math_finito(v):
    import math
    return math.isfinite(v)
