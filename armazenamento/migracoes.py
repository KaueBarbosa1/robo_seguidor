"""Migrações cumulativas, sem apagar/recriar dados existentes."""
VERSAO = 5
BASE = '''
CREATE TABLE schema_migracoes(versao INTEGER PRIMARY KEY, aplicada_utc TEXT NOT NULL);
CREATE TABLE experimentos(
 id TEXT PRIMARY KEY NOT NULL, nome TEXT NOT NULL, objetivo TEXT, data_utc TEXT NOT NULL,
 modo_processamento TEXT, algoritmo TEXT, condicoes_pista TEXT, repeticao INTEGER,
 configuracoes_json TEXT NOT NULL DEFAULT '{}', observacoes TEXT);
CREATE TABLE gravacoes(
 id TEXT PRIMARY KEY NOT NULL, nome TEXT NOT NULL, inicio_utc TEXT NOT NULL, fim_utc TEXT,
 estado TEXT NOT NULL CHECK(estado IN ('gravando','pausada','encerrada','interrompida','falha')),
 experimento_id TEXT REFERENCES experimentos(id), descricao TEXT, observacoes TEXT,
 motivo_encerramento TEXT, versao_software TEXT, configuracoes_json TEXT NOT NULL,
 estatisticas_json TEXT NOT NULL DEFAULT '{}');
CREATE TABLE sessoes(
 id TEXT PRIMARY KEY NOT NULL, inicio_observado_utc TEXT NOT NULL, fim_observado_utc TEXT NOT NULL,
 origem TEXT NOT NULL, simulado INTEGER NOT NULL CHECK(simulado IN (0,1)),
 versao_protocolo INTEGER NOT NULL, modo_processamento TEXT,
 primeiro_mono_s REAL, ultimo_mono_s REAL);
CREATE TABLE gravacao_sessoes(
 gravacao_id TEXT NOT NULL REFERENCES gravacoes(id), sessao_id TEXT NOT NULL REFERENCES sessoes(id),
 PRIMARY KEY(gravacao_id,sessao_id));
CREATE TABLE telemetria(
 id INTEGER PRIMARY KEY, sessao_id TEXT NOT NULL REFERENCES sessoes(id),
 canal TEXT NOT NULL CHECK(canal='telemetria'), sequencia INTEGER NOT NULL CHECK(sequencia>=0),
 origem_utc TEXT NOT NULL, recebido_utc TEXT NOT NULL, origem_mono_s REAL NOT NULL,
 recebido_mono_s REAL NOT NULL, idade_limite_s REAL, estado_operacional TEXT,
 origem_comandos TEXT, simulado INTEGER NOT NULL CHECK(simulado IN (0,1)),
 qualidade_json TEXT NOT NULL, mensagem_json TEXT NOT NULL,
 UNIQUE(sessao_id,canal,sequencia));
CREATE TABLE telemetria_gravacoes(
 telemetria_id INTEGER NOT NULL REFERENCES telemetria(id), gravacao_id TEXT NOT NULL REFERENCES gravacoes(id),
 PRIMARY KEY(telemetria_id,gravacao_id));
CREATE TABLE motores(
 telemetria_id INTEGER PRIMARY KEY REFERENCES telemetria(id), pwm_solicitado_esq REAL,
 pwm_solicitado_dir REAL, pwm_informado_esq REAL, pwm_informado_dir REAL,
 referencia_esq_pps REAL, referencia_dir_pps REAL, pps_esq REAL, pps_dir REAL,
 ticks_esq INTEGER, ticks_dir INTEGER, erro_pi REAL, velocidade_m_s REAL,
 falha_encoder INTEGER, pi_ativo INTEGER, qualidade_json TEXT NOT NULL);
CREATE TABLE sensores(
 telemetria_id INTEGER PRIMARY KEY REFERENCES telemetria(id), distancia_cm REAL,
 distancia_estado TEXT, distancia_idade_s REAL, servo_comandado_graus REAL,
 obstaculo_confirmado INTEGER, avanco_bloqueado INTEGER, falha_sensor INTEGER,
 qualidade_json TEXT NOT NULL);
CREATE TABLE visao_computacional(
 telemetria_id INTEGER PRIMARY KEY REFERENCES telemetria(id), frame_id INTEGER,
 fps REAL, processamento_s REAL, idade_frame_s REAL, linha_detectada INTEGER,
 erro_normalizado REAL, confianca_heuristica REAL, algoritmo TEXT,
 camera_ok INTEGER, qualidade_json TEXT NOT NULL);
CREATE TABLE inteligencia_artificial(
 telemetria_id INTEGER PRIMARY KEY REFERENCES telemetria(id), politica TEXT, modelo TEXT,
 versao_modelo TEXT, inferencia_s REAL, previsao REAL, acao_json TEXT, recompensa REAL,
 aprendizado_ativo INTEGER, local_processamento TEXT, qualidade_json TEXT NOT NULL);
CREATE TABLE desempenho(
 id INTEGER PRIMARY KEY, sessao_id TEXT NOT NULL REFERENCES sessoes(id),
 telemetria_id INTEGER REFERENCES telemetria(id), gravacao_id TEXT NOT NULL REFERENCES gravacoes(id),
 timestamp_utc TEXT NOT NULL, dispositivo TEXT NOT NULL, host TEXT, plataforma TEXT,
 amostra_mono_s REAL, simulado INTEGER NOT NULL CHECK(simulado IN (0,1)), natureza TEXT NOT NULL,
 cpu_pct REAL, ram_pct REAL, rss_bytes INTEGER, temperatura_c REAL, frequencia_mhz REAL,
 throttling INTEGER, subtensao INTEGER, controle_hz REAL, jitter_s REAL,
 metricas_json TEXT NOT NULL, UNIQUE(sessao_id,dispositivo,amostra_mono_s));
CREATE TABLE comunicacao(
 id INTEGER PRIMARY KEY, sessao_id TEXT REFERENCES sessoes(id), telemetria_id INTEGER REFERENCES telemetria(id),
 gravacao_id TEXT NOT NULL REFERENCES gravacoes(id), timestamp_utc TEXT NOT NULL,
 lado TEXT NOT NULL, canal TEXT, rtt_s REAL, jitter_s REAL, mensagens_tx INTEGER,
 mensagens_rx INTEGER, lacunas INTEGER, descartes INTEGER, frames_descartados INTEGER,
 fps REAL, kib_s REAL, reconexoes INTEGER, conectado INTEGER, metricas_json TEXT NOT NULL);
CREATE TABLE eventos(
 id INTEGER PRIMARY KEY, sessao_id TEXT REFERENCES sessoes(id), gravacao_id TEXT NOT NULL REFERENCES gravacoes(id),
 telemetria_id INTEGER REFERENCES telemetria(id), timestamp_utc TEXT NOT NULL,
 categoria TEXT NOT NULL, gravidade TEXT NOT NULL, origem TEXT NOT NULL,
 descricao TEXT NOT NULL, detalhes_json TEXT NOT NULL);
CREATE TABLE intervalos(
 id INTEGER PRIMARY KEY, sessao_id TEXT REFERENCES sessoes(id), gravacao_id TEXT NOT NULL REFERENCES gravacoes(id),
 canal TEXT NOT NULL, inicio_utc TEXT NOT NULL, fim_utc TEXT, motivo TEXT NOT NULL);
CREATE TABLE imagens(
 id INTEGER PRIMARY KEY, sessao_id TEXT NOT NULL REFERENCES sessoes(id),
 canal TEXT NOT NULL CHECK(canal='imagens'), sequencia INTEGER NOT NULL, frame_id INTEGER NOT NULL,
 origem_utc TEXT NOT NULL, recebido_utc TEXT NOT NULL, origem_mono_s REAL NOT NULL,
 caminho TEXT NOT NULL UNIQUE, largura INTEGER, altura INTEGER, tamanho_bytes INTEGER NOT NULL,
 formato TEXT NOT NULL, sha256 TEXT NOT NULL, simulado INTEGER NOT NULL CHECK(simulado IN (0,1)),
 estado TEXT NOT NULL, telemetria_id INTEGER REFERENCES telemetria(id),
 associacao_tipo TEXT NOT NULL, desvio_temporal_s REAL, mensagem_json TEXT NOT NULL,
 UNIQUE(sessao_id,canal,sequencia));
CREATE TABLE imagens_gravacoes(
 imagem_id INTEGER NOT NULL REFERENCES imagens(id), gravacao_id TEXT NOT NULL REFERENCES gravacoes(id),
 PRIMARY KEY(imagem_id,gravacao_id));
CREATE TABLE odometria(
 id INTEGER PRIMARY KEY, sessao_id TEXT NOT NULL REFERENCES sessoes(id), timestamp_utc TEXT NOT NULL,
 x_m REAL, y_m REAL, orientacao_rad REAL, distancia_m REAL, velocidade_linear_m_s REAL,
 velocidade_angular_rad_s REAL, calibracao_json TEXT, validade TEXT, natureza TEXT);
CREATE TABLE estado_transicoes(
 sessao_id TEXT NOT NULL REFERENCES sessoes(id), chave TEXT NOT NULL, valor_json TEXT NOT NULL,
 PRIMARY KEY(sessao_id,chave));
'''
INDICES = '''
CREATE INDEX idx_telemetria_tempo ON telemetria(sessao_id,recebido_utc,id);
CREATE INDEX idx_telemetria_gravacao ON telemetria_gravacoes(gravacao_id,telemetria_id);
CREATE INDEX idx_visao_frame ON visao_computacional(frame_id,telemetria_id);
CREATE INDEX idx_eventos_tempo ON eventos(sessao_id,timestamp_utc,id);
CREATE INDEX idx_imagens_tempo ON imagens(sessao_id,recebido_utc,id);
CREATE INDEX idx_desempenho_tempo ON desempenho(sessao_id,dispositivo,timestamp_utc,id);
CREATE INDEX idx_comunicacao_tempo ON comunicacao(sessao_id,timestamp_utc,id);
CREATE INDEX idx_gravacoes_experimento ON gravacoes(experimento_id,inicio_utc);
CREATE INDEX idx_sessoes_filtro ON sessoes(simulado,modo_processamento,inicio_observado_utc);
ALTER TABLE gravacoes ADD COLUMN recuperada_utc TEXT;
'''


CENTRAL = '''
ALTER TABLE sessoes ADD COLUMN nome TEXT;
ALTER TABLE sessoes ADD COLUMN observacoes TEXT;
CREATE TABLE experimento_sessoes(
 experimento_id TEXT NOT NULL REFERENCES experimentos(id),
 sessao_id TEXT NOT NULL REFERENCES sessoes(id),
 PRIMARY KEY(experimento_id,sessao_id));
CREATE INDEX idx_odometria_tempo ON odometria(sessao_id,timestamp_utc,id);
'''

CONSULTAS_CENTRAL = '''
CREATE INDEX idx_comunicacao_telemetria ON comunicacao(telemetria_id,lado,id);
CREATE INDEX idx_desempenho_ultimo ON desempenho(sessao_id,dispositivo,id DESC,amostra_mono_s,telemetria_id);
'''

DISTRIBUIDO = '''
CREATE TABLE percepcao_remota(
 telemetria_id INTEGER PRIMARY KEY REFERENCES telemetria(id),
 processamento TEXT, operacao TEXT, fonte_controle TEXT, algoritmo TEXT,
 versao_modelo TEXT, frame_id INTEGER, geracao INTEGER, fase TEXT,
 emergencia INTEGER, parada TEXT, idade_resultado_s REAL, latencia_total_s REAL,
 preprocessamento_s REAL, inferencia_s REAL, processamento_s REAL, erro REAL,
 posicao REAL, confianca REAL, resultados_aceitos INTEGER, resultados_rejeitados INTEGER,
 detalhes_json TEXT NOT NULL);
CREATE TABLE operacao_rede_eventos(
 id TEXT PRIMARY KEY, sessao_id TEXT NOT NULL REFERENCES sessoes(id),
 timestamp_utc TEXT NOT NULL, tipo TEXT NOT NULL, simulado INTEGER NOT NULL,
 motivo TEXT, detalhes_json TEXT NOT NULL);
CREATE INDEX idx_operacao_rede_tempo ON operacao_rede_eventos(sessao_id,timestamp_utc,id);
'''

def migrar(conexao, ate=VERSAO):
    from datetime import datetime, timezone
    atual = conexao.execute('PRAGMA user_version').fetchone()[0]
    if atual > VERSAO or ate > VERSAO:
        raise ValueError('Banco mais novo que este software')
    for versao, sql in ((1, BASE), (2, INDICES), (3,CENTRAL), (4,CONSULTAS_CENTRAL), (5,DISTRIBUIDO)):
        if atual < versao <= ate:
            instante = datetime.now(timezone.utc).isoformat()
            try:
                conexao.executescript('BEGIN IMMEDIATE;\n'+sql+
                    f"\nINSERT INTO schema_migracoes VALUES({versao},'{instante}');\nPRAGMA user_version={versao};\nCOMMIT;")
            except Exception:
                if conexao.in_transaction:
                    conexao.rollback()
                raise
