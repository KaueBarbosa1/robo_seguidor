"""Projeções consultáveis; envelope original e qualidade permanecem auditáveis."""
from datetime import datetime, timezone
import json
import math


def utc(valor=None):
    d = datetime.now(timezone.utc) if valor is None else datetime.fromisoformat(valor)
    if d.tzinfo is None:
        raise ValueError('Timestamp deve possuir fuso horario')
    return d.astimezone(timezone.utc).isoformat(timespec='microseconds')


def js(valor):
    return json.dumps(valor, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def valor(campo):
    return campo.get('valor') if isinstance(campo, dict) else campo


def numero(campo):
    v = valor(campo)
    return v if isinstance(v, (float, int)) and math.isfinite(v) else None


def texto(campo):
    v = valor(campo)
    return v if isinstance(v, str) else None


def media(tempos, chave):
    v = (tempos or {}).get(chave)
    return numero(v.get('media')) if isinstance(v, dict) else None


def original(msg):
    return {k: msg[k] for k in ('versao','sessao','sequencia','tipo','origem','simulado',
        'timestamp','monotonic_s','idade_envio_s','validade_s','dados')}


def inserir(c, tabela, dados, ignorar=False):
    # Nomes provêm somente das projeções internas e nunca de parâmetros SQL da CLI.
    campos = ','.join(dados)
    q = ','.join('?' for _ in dados)
    return c.execute(f'INSERT {"OR IGNORE" if ignorar else ""} INTO {tabela} ({campos}) VALUES ({q})', tuple(dados.values()))


def sessao(c, msg, gravacao, recebido, modo=None):
    existente = c.execute('SELECT origem,simulado FROM sessoes WHERE id=?', (msg['sessao'],)).fetchone()
    if existente and (existente['origem'] != msg['origem'] or existente['simulado'] != int(msg['simulado'])):
        raise ValueError('Sessao mudou de dominio/origem')
    mono = numero(msg.get('monotonic_s'))
    inserir(c, 'sessoes', dict(id=msg['sessao'], inicio_observado_utc=recebido,
        fim_observado_utc=recebido, origem=msg['origem'], simulado=int(msg['simulado']),
        versao_protocolo=msg['versao'], modo_processamento=modo,
        primeiro_mono_s=mono, ultimo_mono_s=mono), True)
    c.execute('UPDATE sessoes SET fim_observado_utc=MAX(fim_observado_utc,?) WHERE id=?',(recebido,msg['sessao']))
    if mono is None:
        inserir(c, 'gravacao_sessoes', dict(gravacao_id=gravacao, sessao_id=msg['sessao']), True)
        return
    c.execute('UPDATE sessoes SET '
              'primeiro_mono_s=CASE WHEN primeiro_mono_s IS NULL THEN ? ELSE MIN(primeiro_mono_s,?) END,'
              'ultimo_mono_s=CASE WHEN ultimo_mono_s IS NULL THEN ? ELSE MAX(ultimo_mono_s,?) END WHERE id=?',
              (mono, mono, mono, mono, msg['sessao']))
    inserir(c, 'gravacao_sessoes', dict(gravacao_id=gravacao, sessao_id=msg['sessao']), True)


def telemetria(c, msg, recepcao_mono, gravacao, modo=None):
    recebido = utc(msg.get('recepcao_utc'))
    sessao(c, msg, gravacao, recebido, modo)
    d, t = msg['dados'], msg['dados']['telemetria']
    op = t.get('operacao') or {}
    cursor = inserir(c, 'telemetria', dict(sessao_id=msg['sessao'], canal='telemetria',
        sequencia=msg['sequencia'], origem_utc=utc(msg['timestamp']), recebido_utc=recebido,
        origem_mono_s=msg['monotonic_s'], recebido_mono_s=recepcao_mono,
        idade_limite_s=numero(msg.get('idade_limite_recepcao_s')),
        estado_operacional=texto(op.get('modo')), origem_comandos=texto(op.get('origem_comandos')),
        simulado=int(msg['simulado']), qualidade_json=js(t.get('dominios', {})), mensagem_json=js(original(msg))), True)
    novo = cursor.rowcount == 1
    ident = cursor.lastrowid if novo else c.execute('SELECT id FROM telemetria WHERE sessao_id=? AND canal=? AND sequencia=?',
                                                  (msg['sessao'], 'telemetria', msg['sequencia'])).fetchone()[0]
    inserir(c, 'telemetria_gravacoes', dict(telemetria_id=ident, gravacao_id=gravacao), True)
    if not novo:
        return ident, False
    m, s, v, ia = (t.get(k) or {} for k in ('motores','sensores','visao','ia'))
    pedidos = d.get('pedidos') or {}
    def par(nome, i):
        p = pedidos.get(nome) or {}
        val = p.get('valor')
        return numero(val[i]) if isinstance(val, (list, tuple)) and len(val) == 2 else None
    if m:
        inserir(c, 'motores', dict(telemetria_id=ident,
            pwm_solicitado_esq=par('pwm_direto_esq_dir',0), pwm_solicitado_dir=par('pwm_direto_esq_dir',1),
            pwm_informado_esq=numero(m.get('pwm_esq')), pwm_informado_dir=numero(m.get('pwm_dir')),
            referencia_esq_pps=par('referencia_pps_esq_dir',0), referencia_dir_pps=par('referencia_pps_esq_dir',1),
            pps_esq=numero(m.get('pps_esq')), pps_dir=numero(m.get('pps_dir')),
            ticks_esq=numero(m.get('ticks_esq')), ticks_dir=numero(m.get('ticks_dir')),
            erro_pi=numero(m.get('erro_pi')), velocidade_m_s=numero(m.get('velocidade_m_s')),
            falha_encoder=numero(m.get('falha_encoder')), pi_ativo=numero(m.get('pi_ativo')),
            qualidade_json=js(dict(m,pedidos_observados=pedidos))))
    if s:
        distancia = s.get('distancia_cm') or {}
        inserir(c, 'sensores', dict(telemetria_id=ident, distancia_cm=numero(distancia),
            distancia_estado=texto(distancia.get('estado')) if isinstance(distancia, dict) else None,
            distancia_idade_s=numero(distancia.get('idade_s')) if isinstance(distancia, dict) else None,
            servo_comandado_graus=numero(s.get('angulo_servo_graus')),
            obstaculo_confirmado=numero(s.get('obstaculo_confirmado')),
            avanco_bloqueado=numero(s.get('avanco_bloqueado')), falha_sensor=numero(s.get('falha_sensor')),
            qualidade_json=js(s)))
    if v:
        inserir(c, 'visao_computacional', dict(telemetria_id=ident, frame_id=numero(v.get('frame_id')),
            fps=numero((t.get('camera') or {}).get('fps')), processamento_s=media(d.get('tempos_s'),'opencv_s'),
            idade_frame_s=numero(v.get('idade_ultima_leitura_s')), linha_detectada=numero(v.get('linha_visivel')),
            erro_normalizado=numero(v.get('erro')), confianca_heuristica=numero(v.get('confianca_heuristica')),
            algoritmo=texto(v.get('algoritmo')), camera_ok=numero(v.get('camera_ok')), qualidade_json=js(v)))
    if ia:
        diag = ia.get('diagnostico') or {}
        inserir(c, 'inteligencia_artificial', dict(telemetria_id=ident, politica=texto(ia.get('politica')),
            modelo=texto(ia.get('modelo')), versao_modelo=texto(ia.get('versao_modelo')),
            inferencia_s=media(d.get('tempos_s'),'cnn_s'), previsao=numero(diag.get('erro_cnn')),
            acao_json=js(diag['acao']) if 'acao' in diag else None, recompensa=numero(ia.get('recompensa')),
            aprendizado_ativo=numero(ia.get('aprendizado_ativo')), local_processamento=texto(ia.get('local')),
            qualidade_json=js(ia)))
    sistema = d.get('sistema')
    if isinstance(sistema, dict):
        desempenho(c, msg['sessao'], gravacao, recebido, sistema, 'servidor', msg['simulado'],
                   mono=numero(d.get('sistema_monotonic_s')), telemetria_id=ident,
                   host=d.get('sistema_host'), plataforma=d.get('sistema_plataforma'), tempos=d.get('tempos_s'),
                   natureza=d.get('sistema_natureza','medido_no_host'))
    if isinstance(d.get('comunicacao'), dict):
        comunicacao(c, msg['sessao'], gravacao, recebido, d['comunicacao'], 'servidor', telemetria_id=ident)
    remoto=t.get('distribuido')
    if isinstance(remoto,dict):
        r=remoto.get('ultimo_resultado') or {};ct=remoto.get('contadores') or {}
        inserir(c,'percepcao_remota',dict(telemetria_id=ident,
            **{k:texto(remoto.get(k)) for k in ('processamento','operacao','fonte_controle','algoritmo','versao_modelo','fase','parada')},
            **{k:numero(remoto.get(k)) for k in ('frame_id','geracao','emergencia','idade_resultado_s')},
            latencia_total_s=(remoto.get('latencias_s') or [None])[-1] if r else None,
            **{k:numero(r.get(k)) for k in ('preprocessamento_s','inferencia_s','processamento_s','erro','posicao','confianca')},
            resultados_aceitos=numero(ct.get('resultados_aceitos')),resultados_rejeitados=numero(ct.get('resultados_rejeitados')),
            detalhes_json=js(remoto)))
        for e in remoto.get('eventos',[]):
            if not isinstance(e,dict) or not isinstance(e.get('id'),str) or not e.get('timestamp') or not e.get('tipo'):continue
            inserir(c,'operacao_rede_eventos',dict(id=e['id'],sessao_id=msg['sessao'],timestamp_utc=utc(e['timestamp']),
                tipo=e['tipo'],simulado=int(msg['simulado']),motivo=texto(e.get('motivo')),detalhes_json=js(e)),True)
    return ident, True


def desempenho(c, sessao_id, gravacao, instante, sistema, dispositivo, simulado,
               mono=None, telemetria_id=None, host=None, plataforma=None, tempos=None, natureza='medido_no_host'):
    v = sistema.get('valores') or {}
    periodo = media(tempos, 'controle.periodo_s')
    inserir(c, 'desempenho', dict(sessao_id=sessao_id, gravacao_id=gravacao, telemetria_id=telemetria_id,
        timestamp_utc=instante, dispositivo=dispositivo, host=host, plataforma=plataforma, amostra_mono_s=mono,
        simulado=int(simulado), natureza=natureza, cpu_pct=numero(v.get('cpu_total_pct')),
        ram_pct=numero(v.get('ram_pct')), rss_bytes=numero(v.get('processo_rss_bytes')),
        temperatura_c=numero(v.get('temperatura_c')), frequencia_mhz=numero(v.get('frequencia_mhz')),
        throttling=numero(v.get('throttling_atual')), subtensao=numero(v.get('subtensao_atual')),
        controle_hz=1/periodo if periodo is not None and periodo > 0 else None,
        jitter_s=media(tempos,'controle.jitter_s'), metricas_json=js(sistema)), True)


def comunicacao(c, sessao_id, gravacao, instante, dados, lado, canal=None, telemetria_id=None):
    contas = dados.get('contadores') or {}
    inserir(c, 'comunicacao', dict(sessao_id=sessao_id, gravacao_id=gravacao, telemetria_id=telemetria_id,
        timestamp_utc=instante, lado=lado, canal=canal,
        rtt_s=numero((dados.get('rtt_s') or {}).get('mediana')),
        jitter_s=numero((dados.get('jitter_rtt_s') or {}).get('media')),
        mensagens_tx=numero(contas.get('mensagens_tx')), mensagens_rx=numero(contas.get('mensagens_rx')),
        lacunas=numero(contas.get('lacunas')),
        descartes=sum(v for k,v in contas.items() if k.startswith('descartes') and isinstance(v,int)),
        frames_descartados=numero(contas.get('descartes_fila_imagens')), fps=numero(dados.get('fps_medio')),
        kib_s=numero(dados.get('kb_s_medio')), reconexoes=numero(contas.get('reconexoes')),
        conectado=numero(dados.get('conectado')), metricas_json=js(dados)))
