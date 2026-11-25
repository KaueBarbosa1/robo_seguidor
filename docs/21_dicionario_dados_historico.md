# Dicionario de dados — Etapa 3

Gerado do esquema SQLite v2. Valores indisponiveis sao NULL; nenhuma medicao recebe zero por ausencia. BOOLEAN e representado por INTEGER 0/1. Qualidade e natureza originais ficam nos campos JSON e no envelope fonte.

Colunas normalizadas preservam o valor recebido mesmo desatualizado; consultar qualidade_json. Estatisticas descartam campos explicitamente vencidos nas projecoes que possuem esse indicador. Datas de origem e recepcao nao podem ser subtraidas como latencia entre hosts.

Referencias PPS e PWM solicitados representam o ultimo pedido observado, sem confirmar execucao ou alvo atual. Consultar `motores.qualidade_json.pedidos_observados` para idade/estado; nao interpretar um pedido antigo como ativo apos parada. Versao do software e metadado declarado pelo operador, NULL quando nao fornecida.

## comunicacao

RTT e contadores cumulativos, separados por lado/canal.

| Campo | Tipo SQLite | Nulo | Unidade / significado |
|---|---|---|---|
| `id` (PK) | INTEGER | nao | identificador, texto ou contagem; sem unidade fisica |
| `sessao_id` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `telemetria_id` | INTEGER | sim | identificador, texto ou contagem; sem unidade fisica |
| `gravacao_id` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `timestamp_utc` | TEXT | nao | UTC ISO-8601 com fuso |
| `lado` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `canal` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `rtt_s` | REAL | sim | s; monotonic somente no host/origem indicado |
| `jitter_s` | REAL | sim | s; monotonic somente no host/origem indicado |
| `mensagens_tx` | INTEGER | sim | identificador, texto ou contagem; sem unidade fisica |
| `mensagens_rx` | INTEGER | sim | identificador, texto ou contagem; sem unidade fisica |
| `lacunas` | INTEGER | sim | identificador, texto ou contagem; sem unidade fisica |
| `descartes` | INTEGER | sim | identificador, texto ou contagem; sem unidade fisica |
| `frames_descartados` | INTEGER | sim | identificador, texto ou contagem; sem unidade fisica |
| `fps` | REAL | sim | Hz (quadros/s ou ciclos/s) |
| `kib_s` | REAL | sim | s; monotonic somente no host/origem indicado |
| `reconexoes` | INTEGER | sim | identificador, texto ou contagem; sem unidade fisica |
| `conectado` | INTEGER | sim | 0/1; NULL indisponivel |
| `metricas_json` | TEXT | nao | JSON UTF-8; qualidade/origem/semantica conforme envelope |

Referencias: `gravacao_id` → `gravacoes.id`, `telemetria_id` → `telemetria.id`, `sessao_id` → `sessoes.id`.

## desempenho

Amostras por dispositivo; CPU sintetica e marcada como simulada.

| Campo | Tipo SQLite | Nulo | Unidade / significado |
|---|---|---|---|
| `id` (PK) | INTEGER | nao | identificador, texto ou contagem; sem unidade fisica |
| `sessao_id` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `telemetria_id` | INTEGER | sim | identificador, texto ou contagem; sem unidade fisica |
| `gravacao_id` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `timestamp_utc` | TEXT | nao | UTC ISO-8601 com fuso |
| `dispositivo` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `host` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `plataforma` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `amostra_mono_s` | REAL | sim | s; monotonic somente no host/origem indicado |
| `simulado` | INTEGER | nao | 0/1; NULL indisponivel |
| `natureza` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `cpu_pct` | REAL | sim | % |
| `ram_pct` | REAL | sim | % |
| `rss_bytes` | INTEGER | sim | bytes |
| `temperatura_c` | REAL | sim | graus Celsius |
| `frequencia_mhz` | REAL | sim | MHz |
| `throttling` | INTEGER | sim | 0/1; NULL indisponivel |
| `subtensao` | INTEGER | sim | 0/1; NULL indisponivel |
| `controle_hz` | REAL | sim | Hz (quadros/s ou ciclos/s) |
| `jitter_s` | REAL | sim | s; monotonic somente no host/origem indicado |
| `metricas_json` | TEXT | nao | JSON UTF-8; qualidade/origem/semantica conforme envelope |

Referencias: `gravacao_id` → `gravacoes.id`, `telemetria_id` → `telemetria.id`, `sessao_id` → `sessoes.id`.

## estado_transicoes

Memoria persistente para nao contar o mesmo obstaculo varias vezes.

| Campo | Tipo SQLite | Nulo | Unidade / significado |
|---|---|---|---|
| `sessao_id` (PK) | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `chave` (PK) | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `valor_json` | TEXT | nao | JSON UTF-8; qualidade/origem/semantica conforme envelope |

Referencias: `sessao_id` → `sessoes.id`.

## eventos

Transicoes observadas no PC, nao diagnostico causal do hardware.

| Campo | Tipo SQLite | Nulo | Unidade / significado |
|---|---|---|---|
| `id` (PK) | INTEGER | nao | identificador, texto ou contagem; sem unidade fisica |
| `sessao_id` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `gravacao_id` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `telemetria_id` | INTEGER | sim | identificador, texto ou contagem; sem unidade fisica |
| `timestamp_utc` | TEXT | nao | UTC ISO-8601 com fuso |
| `categoria` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `gravidade` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `origem` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `descricao` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `detalhes_json` | TEXT | nao | JSON UTF-8; qualidade/origem/semantica conforme envelope |

Referencias: `telemetria_id` → `telemetria.id`, `gravacao_id` → `gravacoes.id`, `sessao_id` → `sessoes.id`.

## experimentos

Metadados declarados pelo operador.

| Campo | Tipo SQLite | Nulo | Unidade / significado |
|---|---|---|---|
| `id` (PK) | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `nome` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `objetivo` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `data_utc` | TEXT | nao | UTC ISO-8601 com fuso |
| `modo_processamento` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `algoritmo` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `condicoes_pista` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `repeticao` | INTEGER | sim | identificador, texto ou contagem; sem unidade fisica |
| `configuracoes_json` | TEXT | nao | JSON UTF-8; qualidade/origem/semantica conforme envelope |
| `observacoes` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |

## gravacao_sessoes

Associacao N:N entre gravacao do PC e sessao operacional.

| Campo | Tipo SQLite | Nulo | Unidade / significado |
|---|---|---|---|
| `gravacao_id` (PK) | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `sessao_id` (PK) | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |

Referencias: `sessao_id` → `sessoes.id`, `gravacao_id` → `gravacoes.id`.

## gravacoes

Janela de gravacao do PC; distinta da sessao operacional.

| Campo | Tipo SQLite | Nulo | Unidade / significado |
|---|---|---|---|
| `id` (PK) | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `nome` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `inicio_utc` | TEXT | nao | UTC ISO-8601 com fuso |
| `fim_utc` | TEXT | sim | UTC ISO-8601 com fuso |
| `estado` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `experimento_id` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `descricao` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `observacoes` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `motivo_encerramento` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `versao_software` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `configuracoes_json` | TEXT | nao | JSON UTF-8; qualidade/origem/semantica conforme envelope |
| `estatisticas_json` | TEXT | nao | JSON UTF-8; qualidade/origem/semantica conforme envelope |
| `recuperada_utc` | TEXT | sim | UTC ISO-8601 com fuso |

Referencias: `experimento_id` → `experimentos.id`.

## imagens

Metadados; JPEG original fica em arquivo relativo imutavel.

| Campo | Tipo SQLite | Nulo | Unidade / significado |
|---|---|---|---|
| `id` (PK) | INTEGER | nao | identificador, texto ou contagem; sem unidade fisica |
| `sessao_id` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `canal` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `sequencia` | INTEGER | nao | identificador, texto ou contagem; sem unidade fisica |
| `frame_id` | INTEGER | nao | identificador, texto ou contagem; sem unidade fisica |
| `origem_utc` | TEXT | nao | UTC ISO-8601 com fuso |
| `recebido_utc` | TEXT | nao | UTC ISO-8601 com fuso |
| `origem_mono_s` | REAL | nao | s; monotonic somente no host/origem indicado |
| `caminho` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `largura` | INTEGER | sim | pixels |
| `altura` | INTEGER | sim | pixels |
| `tamanho_bytes` | INTEGER | nao | bytes |
| `formato` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `sha256` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `simulado` | INTEGER | nao | 0/1; NULL indisponivel |
| `estado` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `telemetria_id` | INTEGER | sim | identificador, texto ou contagem; sem unidade fisica |
| `associacao_tipo` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `desvio_temporal_s` | REAL | sim | s; monotonic somente no host/origem indicado |
| `mensagem_json` | TEXT | nao | JSON UTF-8; qualidade/origem/semantica conforme envelope |

Referencias: `telemetria_id` → `telemetria.id`, `sessao_id` → `sessoes.id`.

## imagens_gravacoes

Referencia N:N, evitando duplicar JPEGs ja persistidos.

| Campo | Tipo SQLite | Nulo | Unidade / significado |
|---|---|---|---|
| `imagem_id` (PK) | INTEGER | nao | identificador, texto ou contagem; sem unidade fisica |
| `gravacao_id` (PK) | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |

Referencias: `gravacao_id` → `gravacoes.id`, `imagem_id` → `imagens.id`.

## inteligencia_artificial

Inferencia/politica quando disponiveis; sem treino nesta etapa.

| Campo | Tipo SQLite | Nulo | Unidade / significado |
|---|---|---|---|
| `telemetria_id` (PK) | INTEGER | nao | identificador, texto ou contagem; sem unidade fisica |
| `politica` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `modelo` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `versao_modelo` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `inferencia_s` | REAL | sim | s; monotonic somente no host/origem indicado |
| `previsao` | REAL | sim | identificador, texto ou contagem; sem unidade fisica |
| `acao_json` | TEXT | sim | JSON UTF-8; qualidade/origem/semantica conforme envelope |
| `recompensa` | REAL | sim | identificador, texto ou contagem; sem unidade fisica |
| `aprendizado_ativo` | INTEGER | sim | 0/1; NULL indisponivel |
| `local_processamento` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `qualidade_json` | TEXT | nao | JSON UTF-8; qualidade/origem/semantica conforme envelope |

Referencias: `telemetria_id` → `telemetria.id`.

## intervalos

Pausas/lacunas observadas, sem preencher dados inexistentes.

| Campo | Tipo SQLite | Nulo | Unidade / significado |
|---|---|---|---|
| `id` (PK) | INTEGER | nao | identificador, texto ou contagem; sem unidade fisica |
| `sessao_id` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `gravacao_id` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `canal` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `inicio_utc` | TEXT | nao | UTC ISO-8601 com fuso |
| `fim_utc` | TEXT | sim | UTC ISO-8601 com fuso |
| `motivo` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |

Referencias: `gravacao_id` → `gravacoes.id`, `sessao_id` → `sessoes.id`.

## motores

Projecao 1:1 da telemetria; sentidos sao comandados, pulsos nao medem sentido.

| Campo | Tipo SQLite | Nulo | Unidade / significado |
|---|---|---|---|
| `telemetria_id` (PK) | INTEGER | nao | identificador, texto ou contagem; sem unidade fisica |
| `pwm_solicitado_esq` | REAL | sim | PWM assinado; sinal comandado, nao sentido medido |
| `pwm_solicitado_dir` | REAL | sim | PWM assinado; sinal comandado, nao sentido medido |
| `pwm_informado_esq` | REAL | sim | PWM assinado; sinal comandado, nao sentido medido |
| `pwm_informado_dir` | REAL | sim | PWM assinado; sinal comandado, nao sentido medido |
| `referencia_esq_pps` | REAL | sim | pulsos/s (magnitude) |
| `referencia_dir_pps` | REAL | sim | pulsos/s (magnitude) |
| `pps_esq` | REAL | sim | pulsos/s (magnitude) |
| `pps_dir` | REAL | sim | pulsos/s (magnitude) |
| `ticks_esq` | INTEGER | sim | pulsos acumulados |
| `ticks_dir` | INTEGER | sim | pulsos acumulados |
| `erro_pi` | REAL | sim | identificador, texto ou contagem; sem unidade fisica |
| `velocidade_m_s` | REAL | sim | s; monotonic somente no host/origem indicado |
| `falha_encoder` | INTEGER | sim | 0/1; NULL indisponivel |
| `pi_ativo` | INTEGER | sim | 0/1; NULL indisponivel |
| `qualidade_json` | TEXT | nao | JSON UTF-8; qualidade/origem/semantica conforme envelope |

Referencias: `telemetria_id` → `telemetria.id`.

## odometria

Na Etapa 4, o gêmeo digital passa a gravar estimativas quando `-Gravar` está
ativo e a calibração é válida. Usa a mesma tabela, sem novo banco ou mudança
de esquema. Calibração simulada e estimativa física são identificadas em
`calibracao_json` e `natureza`; registros antigos podem continuar ausentes.

| Campo | Tipo SQLite | Nulo | Unidade / significado |
|---|---|---|---|
| `id` (PK) | INTEGER | nao | identificador, texto ou contagem; sem unidade fisica |
| `sessao_id` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `timestamp_utc` | TEXT | nao | UTC ISO-8601 com fuso |
| `x_m` | REAL | sim | m estimados |
| `y_m` | REAL | sim | m estimados |
| `orientacao_rad` | REAL | sim | rad estimados |
| `distancia_m` | REAL | sim | m estimados |
| `velocidade_linear_m_s` | REAL | sim | m/s estimados |
| `velocidade_angular_rad_s` | REAL | sim | rad/s estimados |
| `calibracao_json` | TEXT | sim | JSON UTF-8; qualidade/origem/semantica conforme envelope |
| `validade` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `natureza` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |

Referencias: `sessao_id` → `sessoes.id`.

## schema_migracoes

Versoes cumulativas aplicadas.

| Campo | Tipo SQLite | Nulo | Unidade / significado |
|---|---|---|---|
| `versao` (PK) | INTEGER | nao | identificador, texto ou contagem; sem unidade fisica |
| `aplicada_utc` | TEXT | nao | UTC ISO-8601 com fuso |

## sensores

Leitura e qualidade originais; servo representa angulo comandado.

| Campo | Tipo SQLite | Nulo | Unidade / significado |
|---|---|---|---|
| `telemetria_id` (PK) | INTEGER | nao | identificador, texto ou contagem; sem unidade fisica |
| `distancia_cm` | REAL | sim | cm |
| `distancia_estado` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `distancia_idade_s` | REAL | sim | s; monotonic somente no host/origem indicado |
| `servo_comandado_graus` | REAL | sim | graus comandados |
| `obstaculo_confirmado` | INTEGER | sim | 0/1; NULL indisponivel |
| `avanco_bloqueado` | INTEGER | sim | 0/1; NULL indisponivel |
| `falha_sensor` | INTEGER | sim | 0/1; NULL indisponivel |
| `qualidade_json` | TEXT | nao | JSON UTF-8; qualidade/origem/semantica conforme envelope |

Referencias: `telemetria_id` → `telemetria.id`.

## sessoes

Sessao operacional UUID do servidor; inicio/fim observados, nao boot fisico.

| Campo | Tipo SQLite | Nulo | Unidade / significado |
|---|---|---|---|
| `id` (PK) | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `inicio_observado_utc` | TEXT | nao | UTC ISO-8601 com fuso |
| `fim_observado_utc` | TEXT | nao | UTC ISO-8601 com fuso |
| `origem` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `simulado` | INTEGER | nao | 0/1; NULL indisponivel |
| `versao_protocolo` | INTEGER | nao | identificador, texto ou contagem; sem unidade fisica |
| `modo_processamento` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `primeiro_mono_s` | REAL | sim | s; monotonic somente no host/origem indicado |
| `ultimo_mono_s` | REAL | sim | s; monotonic somente no host/origem indicado |

## telemetria

Envelope fonte canonico, uma linha por sessao/canal/sequencia.

| Campo | Tipo SQLite | Nulo | Unidade / significado |
|---|---|---|---|
| `id` (PK) | INTEGER | nao | identificador, texto ou contagem; sem unidade fisica |
| `sessao_id` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `canal` | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |
| `sequencia` | INTEGER | nao | identificador, texto ou contagem; sem unidade fisica |
| `origem_utc` | TEXT | nao | UTC ISO-8601 com fuso |
| `recebido_utc` | TEXT | nao | UTC ISO-8601 com fuso |
| `origem_mono_s` | REAL | nao | s; monotonic somente no host/origem indicado |
| `recebido_mono_s` | REAL | nao | s; monotonic somente no host/origem indicado |
| `idade_limite_s` | REAL | sim | s; monotonic somente no host/origem indicado |
| `estado_operacional` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `origem_comandos` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `simulado` | INTEGER | nao | 0/1; NULL indisponivel |
| `qualidade_json` | TEXT | nao | JSON UTF-8; qualidade/origem/semantica conforme envelope |
| `mensagem_json` | TEXT | nao | JSON UTF-8; qualidade/origem/semantica conforme envelope |

Referencias: `sessao_id` → `sessoes.id`.

## telemetria_gravacoes

Referencia N:N, evitando duplicar envelopes ja persistidos.

| Campo | Tipo SQLite | Nulo | Unidade / significado |
|---|---|---|---|
| `telemetria_id` (PK) | INTEGER | nao | identificador, texto ou contagem; sem unidade fisica |
| `gravacao_id` (PK) | TEXT | nao | identificador, texto ou contagem; sem unidade fisica |

Referencias: `gravacao_id` → `gravacoes.id`, `telemetria_id` → `telemetria.id`.

## visao_computacional

Resultado recebido, nao rotulo humano de treino.

| Campo | Tipo SQLite | Nulo | Unidade / significado |
|---|---|---|---|
| `telemetria_id` (PK) | INTEGER | nao | identificador, texto ou contagem; sem unidade fisica |
| `frame_id` | INTEGER | sim | identificador, texto ou contagem; sem unidade fisica |
| `fps` | REAL | sim | Hz (quadros/s ou ciclos/s) |
| `processamento_s` | REAL | sim | s; monotonic somente no host/origem indicado |
| `idade_frame_s` | REAL | sim | s; monotonic somente no host/origem indicado |
| `linha_detectada` | INTEGER | sim | 0/1; NULL indisponivel |
| `erro_normalizado` | REAL | sim | adimensional; [-1,1] quando valido |
| `confianca_heuristica` | REAL | sim | adimensional; nao probabilidade calibrada |
| `algoritmo` | TEXT | sim | identificador, texto ou contagem; sem unidade fisica |
| `camera_ok` | INTEGER | sim | 0/1; NULL indisponivel |
| `qualidade_json` | TEXT | nao | JSON UTF-8; qualidade/origem/semantica conforme envelope |

Referencias: `telemetria_id` → `telemetria.id`.
