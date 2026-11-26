"""Canal opcional no MESMO servidor WebSocket, com privilégios separados."""
import asyncio
from http import HTTPStatus
import secrets
import time
import uuid
from websockets.exceptions import ConnectionClosed

from comunicacao.protocolo import decodificar,codificar,Sequencia
from distribuido.configuracao import CONTRATO


class CanalOperacao:
    def __init__(self,autoridade,tokens):
        self.autoridade=autoridade
        self.tokens=dict(tokens)
        if set(self.tokens)-{'percepcao','controle','administrar'}:raise ValueError('Permissão desconhecida')
        if any(not isinstance(t,str) or not t.isascii() or len(t)<24 for t in self.tokens.values()):raise ValueError('Tokens operacionais exigem 24 caracteres ASCII')
        if len(set(self.tokens.values()))!=len(self.tokens):raise ValueError('Use credenciais distintas por permissão')

    def permissoes(self,pedido):
        aceitas=set()
        for p,t in self.tokens.items():
            v=pedido.headers.get_all('X-Robo-'+p)
            if len(v)>1:raise ValueError('Cabeçalho duplicado')
            if len(v)==1 and secrets.compare_digest(v[0],t):aceitas.add(p)
        return aceitas

    def autorizar(self,conexao,pedido):
        try:
            if self.permissoes(pedido):return None
        except ValueError:pass
        return conexao.respond(HTTPStatus.FORBIDDEN,'Privilégio operacional necessário\n')

    async def conectar(self,servidor,ws):
        self.autoridade.ligar(servidor.sessao)
        cliente=str(uuid.uuid4());permissoes=self.permissoes(ws.request)
        from comunicacao.servidor import Consumidor
        consumidor=Consumidor('operacao',asyncio.Queue(1));servidor.consumidores.add(consumidor)
        seq=Sequencia();janela=time.monotonic();quantidade=0
        desafio=secrets.token_hex(16);desafio_t=time.monotonic()
        try:
            await ws.send(codificar(servidor.mensagem(0,'ola',dict(canal='operacao',contrato=CONTRATO,
                permissoes=sorted(permissoes),desafio=desafio,estado=self.autoridade.snapshot()))))
            async for texto in ws:
                try:
                    agora=time.monotonic()
                    if agora-janela>=1:janela=agora;quantidade=0
                    quantidade+=1
                    if quantidade>80:
                        await ws.close(1008,'Limite operacional excedido');return
                    msg=decodificar(texto,servidor.op.max_json)
                    if (msg['sessao']!=servidor.sessao or msg['origem']!='computador' or
                        msg['simulado']!=servidor.simulado or not seq.aceitar(msg) or
                        msg['idade_envio_s']>min(msg['validade_s'],.5)):
                        raise ValueError('Sessão/domínio/sequência/prazo inválido')
                    if msg['tipo']=='inferencia':
                        if 'percepcao' not in permissoes:raise ValueError('Percepção não autorizada')
                        resultado=self.autoridade.receber_resultado(msg['dados'],cliente)
                    elif msg['tipo']=='comando':
                        if msg['dados'].get('acao') not in ('parar','emergencia','pronto','heartbeat','falha_percepcao','consulta'):
                            if msg['dados'].get('desafio')!=desafio or agora-desafio_t>self.autoridade.op.comando_s:raise ValueError('Desafio expirado: comando em trânsito antigo')
                        resultado=self.autoridade.comando(msg['dados'],cliente,permissoes)
                    else:raise ValueError('Tipo operacional não permitido')
                    dono=self.autoridade.lease and self.autoridade.lease['cliente']==cliente
                    resposta=dict(ok=True,sequencia=msg['sequencia'],resultado=resultado,estado=self.autoridade.snapshot(privado=dono))
                except (ValueError,KeyError,TypeError) as exc:
                    servidor.metricas.contar('operacao_rejeitadas')
                    resposta=dict(ok=False,erro=str(exc),sequencia=msg['sequencia'] if 'msg' in locals() else None,estado=self.autoridade.snapshot())
                    self.autoridade.evento('mensagem_rejeitada',motivo=str(exc))
                desafio=secrets.token_hex(16);desafio_t=time.monotonic();resposta['desafio']=desafio
                await asyncio.wait_for(ws.send(codificar(servidor.mensagem(0,'referencia',resposta))),servidor.op.timeout_s)
        except (ConnectionClosed,asyncio.TimeoutError) as exc:
            # Encerramento pode coincidir com o envio do último ACK. Preserva
            # o evento e o finally de revogação sem traceback de fechamento normal.
            self.autoridade.evento('canal_operacional_encerrado',motivo=type(exc).__name__)
        finally:
            self.autoridade.desconectar(cliente);servidor.consumidores.discard(consumidor)
