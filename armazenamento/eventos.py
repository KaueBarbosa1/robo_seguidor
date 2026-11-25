import json
from armazenamento.normalizacao import inserir, js, valor, utc


def registrar(c, gravacao, categoria, descricao, sessao=None, telemetria=None,
              gravidade='info', origem='computador', instante=None, detalhes=None):
    inserir(c, 'eventos', dict(gravacao_id=gravacao, sessao_id=sessao, telemetria_id=telemetria,
        timestamp_utc=utc(instante), categoria=categoria, gravidade=gravidade,
        origem=origem, descricao=descricao, detalhes_json=js(detalhes or {})))


def transicoes(c, gravacao, msg, ident, opcoes):
    t = msg['dados']['telemetria']
    estado, sensores, visao, motores = (t.get(k) or {} for k in ('operacao','sensores','visao','motores'))
    candidatos = [('modo', estado.get('modo'), 'mudanca_modo'),
                  ('obstaculo', sensores.get('obstaculo_confirmado'), 'obstaculo'),
                  ('bloqueio', sensores.get('avanco_bloqueado'), 'seguranca'),
                  ('sensor_falha', sensores.get('falha_sensor'), 'falha_sensor'),
                  ('encoder_falha', motores.get('falha_encoder'), 'falha_encoder'),
                  ('linha', visao.get('linha_visivel'), 'linha'),
                  ('camera', visao.get('camera_ok'), 'camera')]
    sistema = (msg['dados'].get('sistema') or {}).get('valores') or {}
    for nome, limite, fonte in [('temperatura',opcoes.temperatura_alerta_c,'temperatura_c'),
                               ('cpu',opcoes.cpu_alerta_pct,'cpu_total_pct')]:
        v = sistema.get(fonte)
        if limite is not None and isinstance(v, (float,int)):
            candidatos.append((nome, v >= limite, 'alerta_'+nome))
    gerados = []
    for chave, campo, categoria in candidatos:
        if isinstance(campo, dict) and campo.get('estado') != 'atual':
            continue
        v = valor(campo)
        if v is None:
            continue  # ausência/desatualização nunca rearma contagem de obstáculo
        anterior = c.execute('SELECT valor_json FROM estado_transicoes WHERE sessao_id=? AND chave=?',
                             (msg['sessao'],chave)).fetchone()
        if anterior is None or json.loads(anterior[0]) != v:
            if anterior is not None or v is True:
                if chave == 'obstaculo':
                    categoria = 'obstaculo_detectado' if v else 'obstaculo_liberado'
                registrar(c, gravacao, categoria, f'{chave}: {v}', msg['sessao'], ident,
                          'alerta' if (v is True and chave not in ('linha','camera')) or
                                      (v is False and chave in ('linha','camera')) else 'info',
                          msg['origem'], msg.get('recepcao_utc'), dict(chave=chave, valor=v,
                            timestamp_origem_utc=msg['timestamp'],
                            natureza='observado_na_telemetria', simulado=msg['simulado']))
                gerados.append(categoria)
            c.execute('INSERT INTO estado_transicoes VALUES(?,?,?) ON CONFLICT(sessao_id,chave) '
                      'DO UPDATE SET valor_json=excluded.valor_json', (msg['sessao'],chave,js(v)))
    return gerados
