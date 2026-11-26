import { esc } from "./nucleo.js";
import { blocoGrafico } from "./graficos.js";
import { htmlControle } from "./operacao.js";
export const PAGINAS = [
  [
    "geral",
    "Visão geral",
    "◈",
    "O protótipo, os dados atuais e os eventos que precisam de atenção.",
  ],
  [
    "gemeo",
    "Gêmeo digital",
    "⬡",
    "Modelo original do Blender. Inspeção interativa e estimativas sincronizadas.",
  ],
  [
    "motores",
    "Motores e encoders",
    "↔",
    "Magnitude por pulsos; sentido inferido pelo comando. Sem confirmação física de PWM.",
  ],
  [
    "sensores",
    "Sensores",
    "⌁",
    "Leituras válidas e direções comandadas. O ultrassônico não é um LiDAR.",
  ],
  [
    "visao",
    "Visão computacional",
    "▣",
    "Frames do canal existente e resultados efetivamente disponibilizados.",
  ],
  [
    "ia",
    "Inteligência artificial",
    "◇",
    "CNN própria, políticas e estado de inferência; sem treino ou distribuição automática.",
  ],
  [
    "desempenho",
    "Desempenho",
    "⌗",
    "Métricas separadas do host da telemetria e do computador desta central.",
  ],
  [
    "comunicacao",
    "Comunicação",
    "⇄",
    "Conexões observadas, latência e lacunas de sequência; sem inferir perda de pacotes.",
  ],
  [
    "odometria",
    "Odometria e trajetória",
    "⌖",
    "Posição relativa estimada. Não há referência externa de localização.",
  ],
  [
    "historico",
    "Histórico de sessões",
    "◷",
    "Consulta paginada, observações, exportação e reprodução sincronizada.",
  ],
  [
    "experimentos",
    "Experimentos",
    "⚗",
    "Organização acadêmica e comparações exploratórias entre sessões identificadas.",
  ],
  [
    "controle",
    "Controle remoto",
    "⌘",
    "Autorização exclusiva, presença do operador e processamento distribuído.",
  ],
  [
    "simulacao",
    "Simulação",
    "▷",
    "Cenários gerados pela fonte central e transportados pelo protocolo existente.",
  ],
  [
    "diagnostico",
    "Diagnóstico e eventos",
    "⚑",
    "Falhas ativas, resoluções e detalhes técnicos. Dispensar um aviso não altera proteções.",
  ],
  [
    "configuracoes",
    "Configurações",
    "⚙",
    "Preferências do computador, separadas da configuração crítica do carrinho.",
  ],
];
const v = (k, u = "") => `<span data-valor="${k}" data-unidade="${u}">—</span>`;
const kv = (rows) =>
  `<dl class="kv">${rows.map(([n, k, u]) => `<dt>${n}</dt><dd>${k ? v(k, u) : "Indisponível"}</dd>`).join("")}</dl>`;
const metric = (rows) =>
  `<div class="metrics">${rows.map(([n, k, u, t]) => `<div><small>${n}</small><strong>${v(k, u)}</strong><em>${t ?? "Observado na fonte atual"}</em></div>`).join("")}</div>`;
const panel = (t, b) => `<div class="panel"><h2>${t}</h2>${b}</div>`;
export function criarPagina(id) {
  let charts = [];
  const chart = (i, t, u, s) => {
    charts.push({ id: i, unidade: u, series: s });
    return blocoGrafico(i, t, u, s);
  };
  let html = "";
  if (id === "controle") html = htmlControle();
  if (id === "geral")
    html =
      metric([
        ["Roda esquerda", "v_esq", "m/s", "Estimada, exige calibração"],
        ["Roda direita", "v_dir", "m/s", "Estimada, exige calibração"],
        [
          "Distância frontal",
          "distancia",
          "cm",
          "Leitura válida do ultrassônico",
        ],
        [
          "Host da telemetria · CPU",
          "cpu",
          "%",
          "Simulado quando indicado na origem",
        ],
        ["Temperatura do host", "temperatura", "°C"],
        ["Latência RTT", "rtt", "ms"],
      ]) +
      `<div class="overview"><div class="stack"><div><div class="twin-bar"><b>Protótipo digital</b><button data-fullscreen>Expandir 3D</button></div><div id="slot-twin"></div></div>${chart(
        "geral-pps",
        "Dinâmica das rodas",
        "pulsos/s",
        [
          ["pps_esq", "Esquerda"],
          ["pps_dir", "Direita"],
        ],
      )}</div><div class="stack">${panel(
        "Canal de imagem",
        '<div id="slot-camera"></div><div class="kv">' +
          kv([
            ["FPS de captura", "fps", "FPS"],
            ["Estado da linha", "linha"],
            ["RAM do host", "ram", "%"],
            ["Tempo da central", "uptime", "s"],
          ]) +
          "</div>",
      )}${panel("Eventos recentes", '<div id="eventos-rapidos"></div>')}</div></div>`;
  if (id === "gemeo")
    html = `<div class="twin-bar"><b>Inspeção do protótipo</b><span class="tag">GLB original · 313 nós · 37 materiais</span><button data-fullscreen>Tela cheia</button></div><div id="slot-twin"></div><p class="note">Pulsos por revolução, diâmetro e bitola reais aguardam calibração. Parâmetros sintéticos só produzem estimativas simuladas.</p>`;
  if (id === "motores")
    html = `<div class="grid2">${["esq", "dir"]
      .map((l, i) =>
        panel(
          `Motor ${i ? "direito" : "esquerdo"}`,
          kv([
            ["Pulsos por segundo", "pps_" + l, "pulsos/s"],
            ["Pulsos acumulados", "ticks_" + l, "pulsos"],
            ["PWM informado (comandado)", "pwm_" + l],
            ["Sentido comandado", "sentido_" + l],
            ["Velocidade estimada", "v_" + l, "m/s"],
            ["Referência de velocidade", null],
            ["PWM aplicado fisicamente", null],
            ["Erro do PI", null],
          ]) +
            '<p class="note">Encoder de canal único: não mede sentido. Referência e retorno físico só serão exibidos quando disponibilizados pelo contrato.</p>',
        ),
      )
      .join(
        "",
      )}</div><div class="toolbar" style="margin-top:18px"><label>Janela temporal <select data-janela><option value="15">15 s</option><option value="60" selected>60 s</option><option value="300">5 min</option><option value="600">10 min</option></select></label></div><div class="grid2">${chart(
      "motor-pps",
      "Velocidade solicitada e observada",
      "pulsos/s",
      [
        ["pps_esq", "Observada E"],
        ["pps_dir", "Observada D"],
        ["referencia_esq", "Referência E (indisponível)"],
      ],
    )}${chart("motor-pwm", "PWM informado ao longo do tempo", "PWM comandado", [
      ["pwm_esq", "Esquerda"],
      ["pwm_dir", "Direita"],
    ])}${chart("motor-diferenca", "Diferença entre rodas e variação temporal", "pulsos/s", [["diferenca", "Direita − esquerda"]])}${chart(
      "motor-aceleracao",
      "Aceleração estimada por variação de PPS",
      "pulsos/s²",
      [
        ["acel_esq", "Esquerda"],
        ["acel_dir", "Direita"],
      ],
    )}</div><p class="note">Aceleração calculada somente entre amostras válidas próximas. Curvas e desacelerações são observadas nestas séries; erro PI não exportado permanece indisponível.</p>`;
  if (id === "sensores")
    html =
      metric([
        ["Distância", "distancia", "cm"],
        ["Servo comandado", "servo", "°", "Sem sensor de retorno de posição"],
        ["Idade da leitura", "idade_sonar", "s"],
        ["Parada / liberação", "limites_sonar", "", "Configuração existente"],
      ]) +
      `<div class="grid2">${chart("sensor-distancia", "Distância medida", "cm", [["distancia", "Ultrassônico"]])}${panel("Direção estimada das leituras", '<svg id="radar" class="chart" role="img" aria-label="Leituras polares do ultrassônico"></svg><p class="note">Pontos reais ou simulados identificados na origem global. Cinza: leitura antiga. Passe o mouse para ver horário, ângulo e idade. Sem interpolação espacial.</p>')}</div>${panel(
        "Proteções e validade",
        kv([
          ["Obstáculo confirmado", "obstaculo"],
          ["Leitura válida", "sonar_valido"],
          ["Falha informada", "falha_sensor"],
          ["Sonar no Bluetooth", "sonar_bluetooth"],
          ["Segurança global", "seguranca"],
        ]),
      )}`;
  if (id === "visao")
    html =
      `<div class="grid2">${panel("Imagem original recebida", '<div id="slot-camera"></div><p class="note">O mesmo JPEG da etapa 2. Não há outra conexão de captura.</p>')}${panel("Diagnóstico de imagem", '<label><input type="checkbox" id="ativar-cinza"> Mostrar cinza derivado no PC (até 1 Hz)</label><img id="imagem-cinza" alt="Escala de cinza derivada no computador" hidden><p class="note">ROI, segmentação, máscara e coordenadas de linhas não são transmitidas pelo contrato atual. Não são reconstruídas como se fossem resultados do algoritmo embarcado.</p><a id="painel-coleta" target="_blank" rel="noopener" hidden>Abrir painel de coleta existente</a><p class="note" id="painel-sem-url">Configure o endereço do painel de coleta em Configurações. Sua captura existente é preservada.</p>')}</div>` +
      metric([
        ["Captura", "fps", "FPS"],
        ["Idade do frame", "idade_frame", "s"],
        ["Linha detectada", "linha"],
        ["Erro de seguimento", "erro", "", "Estimado, normalizado"],
        ["Confiança heurística", "confianca", "", "Não é confiança da CNN"],
        ["Processamento OpenCV", "opencv_ms", "ms"],
      ]) +
      chart(
        "visao-erro",
        "Erro de seguimento ao longo do tempo",
        "normalizado",
        [["erro", "Erro da linha"]],
      ) +
      panel(
        "Estado da visão",
        kv([
          ["Algoritmo informado", "algoritmo"],
          ["Resolução", "resolucao"],
          ["Frame", "frame"],
          ["Taxa de detecção na janela", "taxa_linha", "%"],
          ["Perdas observadas na janela", "perdas_linha"],
          ["Frames descartados informados", "frames_descartados"],
          ["FPS de processamento", null],
          ["Tempo de transmissão unidirecional", null],
        ]),
      );
  if (id === "ia")
    html = `<div class="grid3">${panel("CNN própria", '<span class="tag purple">Implementada no projeto · não substituída</span><p>Disponibilidade de pesos e inferência ativa são verificadas pela telemetria. Nenhum treinamento é iniciado pela central.</p>')}${panel("Visão tradicional", '<span class="tag">OpenCV</span><p>O algoritmo ativo é informado pela fonte; sua presença no repositório não comprova inferência CNN ativa.</p>')}${panel("Aprendizado por reforço", '<span class="tag purple">Opt-in · validação pendente</span><p>Estado e recompensa aparecem somente quando efetivamente exportados. Não há confiança artificial.</p>')}</div><div class="grid2" style="margin-top:18px">${panel(
      "Inferência e política",
      kv([
        ["Política informada", "politica"],
        ["Local de execução", "local_ia"],
        ["Modo declarado", "processamento"],
        ["Aprendizado ativo", "aprendizado"],
        ["Tempo de inferência", "inferencia_ms", "ms"],
        ["Versão do modelo", "versao_modelo"],
        ["Predição", "predicao"],
        ["Ação selecionada", "acao_ia"],
        ["Recompensa", "recompensa"],
        ["Frequência de inferência", null],
        ["Confiança da CNN", null],
      ]),
    )}${panel("Contrato e diagnósticos", '<pre data-raw="ia"></pre><p class="note">Entrada da CNN própria: cinza 1 × 40 × 80, quando essa rede estiver selecionada. A fonte informa qual política está ativa; não usamos acurácia como métrica de regressão.</p>')}</div>${panel("Históricos de treinamento e distribuição", '<div id="treinos-registrados" class="empty">Carregando evidências locais de treinamento…</div>')}`;
  if (id === "desempenho")
    html = `<div class="grid2">${panel(
      "Host da telemetria / Raspberry",
      kv([
        ["Natureza da fonte", "natureza_host"],
        ["CPU total", "cpu", "%"],
        ["CPU por núcleo", "cpu_nucleos"],
        ["RAM", "ram", "%"],
        ["Temperatura", "temperatura", "°C"],
        ["Frequência", "frequencia", "MHz"],
        ["Subtensão", "subtensao"],
        ["Limitação térmica", "throttling"],
        ["Controle", "controle_hz", "Hz"],
        ["Jitter do controle", "controle_jitter", "ms"],
      ]),
    )}${panel(
      "Computador desta central",
      kv([
        ["CPU", "cpu_pc", "%"],
        ["RAM", "ram_pc", "%"],
        ["Processo Python · RAM", "rss_pc", "MiB"],
        ["GPU / memória gráfica", null],
        ["Temperatura do PC", null],
        ["Renderização 3D", "render_fps"],
        ["CPU/submit 3D · última medição", "render_ms", "ms"],
        ["API de consultas · média", "consulta_ms", "ms"],
        ["Lote de armazenamento", "lote_ms", "ms"],
        ["Registros persistidos", "persistidas"],
        ["Banco local", "banco_mb", "MiB"],
      ]),
    )}</div><div class="grid2" style="margin-top:18px">${chart(
      "perf-cpu",
      "CPU por dispositivo",
      "%",
      [
        ["cpu", "Host da telemetria"],
        ["cpu_pc", "PC da central"],
      ],
    )}${chart("perf-tempo", "Temperatura do host da telemetria", "°C", [["temperatura", "Host informado"]])}</div>${panel("Embarcado × distribuído", '<div class="empty">Comparação preparada na página Experimentos. Não existem resultados de processamento distribuído real registrados nesta entrega. Simulação no PC não mede o desempenho físico da Raspberry.</div>')}`;
  if (id === "comunicacao")
    html = `${panel("Topologia observada", '<div class="topology"><div class="node"><strong>Computador</strong><small>Cliente + central + SQLite</small></div><span class="link-arrow">⇄</span><div class="node"><strong>Raspberry / fonte</strong><small data-valor="rede_estado">Aguardando</small></div><span class="link-arrow">⇄</span><div class="node"><strong>Arduino / ESP32-CAM</strong><small>Indícios por telemetria; sem teste direto</small></div></div><p class="note">Bluetooth não possui estado de conexão exportado. Dados atuais de sensores não comprovam, isoladamente, a conexão serial física. No modo simulado, toda a topologia é virtual.</p>')}<div class="grid2" style="margin-top:18px">${panel(
      "Conexão central",
      kv([
        ["Servidor", "servidor"],
        ["Estado", "rede_estado"],
        ["RTT médio", "rtt", "ms"],
        ["RTT p95", "rtt_p95", "ms"],
        ["Jitter médio (variação absoluta RTT)", "jitter", "ms"],
        ["Mensagens recebidas", "mensagens_rx"],
        ["Lacunas de sequência", "lacunas"],
        ["Descartes na fila opcional do cliente", "descartes"],
        ["Reconexões", "reconexoes"],
        ["Idade da mensagem", "idade_telemetria", "s"],
        ["Recebimento observado", "tele_hz", "Hz"],
        ["Taxa média do canal", "kib_s", "KiB/s"],
        ["Telemetria recebida média", "rede_hz", "Hz"],
        ["Imagens recebidas média", "fps_rede", "FPS"],
        ["Tempo conectado", "tempo_conexao", "s"],
        ["Descartes do assinante central", "fanout_descartes"],
      ]),
    )}${panel("Configurar destino do PC", '<form id="form-conexao"><label>URL do servidor WebSocket<input name="url" placeholder="ws://IP_DA_RASPBERRY:8765" required></label><button>Salvar destino</button></form><p class="note">Não altera a rede da Raspberry ou da ESP32-CAM. Token somente no ambiente do terminal. Troque para simulação antes de alterar o destino.</p><pre data-raw="rede"></pre>')}</div><div class="grid2" style="margin-top:18px">${chart(
      "rede-rtt",
      "Latência e jitter observados",
      "ms",
      [
        ["rtt", "RTT médio"],
        ["jitter", "Variação absoluta RTT"],
      ],
    )}${chart(
      "rede-contadores",
      "Lacunas e fila opcional do cliente",
      "contagem acumulada",
      [
        ["lacunas", "Lacunas"],
        ["descartes", "Fila opcional do cliente (não é perda do gravador)"],
      ],
    )}</div>`;
  if (id === "comunicacao")
    html += `<div class="grid2" style="margin-top:18px">${chart(
      "rede-taxas",
      "Frequências médias recebidas",
      "Hz / FPS",
      [
        ["rede_hz", "Telemetria"],
        ["fps_rede", "Imagens"],
      ],
    )}${chart("rede-bytes", "Transferência média do canal", "KiB/s", [["kib_s", "RX + TX do canal"]])}${chart("rede-reconexoes", "Reconexões informadas", "contagem", [["reconexoes", "Reconexões"]])}</div><p class="note">As taxas do transporte são médias desde o início do cliente. Descartes da fila opcional não consumida não significam perda do assinante central ou do gravador; esses possuem contadores próprios. Lacunas não comprovam perda de pacotes.</p>`;
  if (id === "odometria")
    html =
      metric([
        ["X estimado", "x", "m"],
        ["Y estimado", "y", "m"],
        ["Orientação", "theta", "°"],
        ["Percurso", "distancia_total", "m"],
        ["Velocidade linear", "vel_linear", "m/s"],
        ["Velocidade angular", "vel_angular", "rad/s"],
      ]) +
      panel(
        "Trajetória relativa",
        '<div class="toolbar"><button id="zoom-mais">Aproximar</button><button id="zoom-menos">Afastar</button><button id="centrar-trajeto">Centralizar</button><button id="reset-trajeto">Reiniciar referência virtual</button><select id="comparar-2d" aria-label="Comparar sessão na trajetória"><option value="">Comparar sessão…</option></select><button data-export="trajeto-2d" data-formato="svg">Exportar SVG</button><button id="exportar-odometria">Exportar CSV</button></div><svg id="trajeto-2d" class="chart" role="img" aria-label="Trajetória estimada em duas dimensões"></svg><p class="note">Sem mapa de pista ou erro contra posição real inventados. Eventos só recebem posição se houver associação temporal verificável. Estimativa por pulsos e sentido comandado.</p>',
      );
  if (id === "historico")
    html = `${panel("Pesquisar sessões", '<form id="form-sessoes" class="toolbar"><label class="wide">Nome, identificador ou observação<input name="busca" placeholder="Pesquisar sessões"></label><label>Origem<select name="simulado"><option value="">Todas, identificadas</option><option value="1">Simuladas</option><option value="0">Reais</option></select></label><label>Modo<input name="modo" placeholder="simulacao"></label><label>Início<input type="datetime-local" name="inicio"></label><label>Fim<input type="datetime-local" name="fim"></label><button>Pesquisar</button></form><div id="lista-sessoes" class="table-wrap"></div><div class="toolbar" style="margin-top:15px"><button id="anterior-sessoes">Anterior</button><span id="paginacao-sessoes"></span><button id="proxima-sessoes">Próxima</button><button id="comparar-selecionadas">Comparar selecionadas</button><button id="exportar-selecao">Exportar seleção CSV</button></div>')}<div id="detalhe-sessao" style="margin-top:18px"></div><div id="lista-imagens" class="grid3" style="margin-top:18px"></div>`;
  if (id === "experimentos")
    html = `<div class="grid2">${panel("Registrar experimento", '<form id="form-experimento" class="form-grid"><label>Nome<input name="nome" required maxlength="256"></label><label>Objetivo<input name="objetivo" required></label><label>Hipótese<input name="hipotese"></label><label>Algoritmo<input name="algoritmo" placeholder="OpenCV, CNN própria…"></label><label>Modo de processamento<select name="modo"><option value="simulacao">Simulação</option><option value="embarcado">Embarcado</option><option value="distribuido">Distribuído (metadado planejado)</option></select></label><label>Repetições<input name="repeticao" type="number" min="1" value="1"></label><label>Condições da pista<input name="condicoes"></label><label>Configurações (JSON)<input name="configuracoes" value="{}"></label><label class="full">Descrição e observações<textarea name="observacoes"></textarea></label><button>Registrar experimento</button></form>')}${panel("Experimentos existentes", '<div id="lista-experimentos"></div><div class="divider"></div><h3>Associar sessões selecionadas</h3><p class="note">Selecione sessões em Histórico. A associação não mistura nem converte a origem dos dados.</p><form id="form-associar"><label>Experimento<select id="experimento-associar"></select></label><button>Associar seleção</button></form>')}</div><div class="divider"></div>${panel("Comparação exploratória", '<p class="note">Selecione até seis sessões no Histórico e use Comparar. Tabelas, médias, dispersão e boxplots usam amostras efetivamente registradas. Simulado e real permanecem identificados.</p><button id="comparar-selecionadas">Comparar sessões selecionadas</button><div id="comparacao-experimentos"></div>')}`;
  if (id === "simulacao")
    html = `<div class="grid2">${panel("Cenários de bancada", '<div class="toolbar"><label>Cenário<select id="cenario"><option value="normal">Funcionamento normal</option><option value="seguimento">Seguimento de linha</option><option value="curva">Curva acentuada</option><option value="obstaculo">Obstáculo inesperado</option><option value="linha_perdida">Perda da linha</option><option value="comunicacao">Falha de comunicação</option><option value="sobrecarga">Sobrecarga do sistema</option></select></label></div><div class="toolbar"><button data-cenario="iniciar">Iniciar</button><button data-cenario="pausar">Pausar</button><button data-cenario="retomar">Retomar</button><button data-cenario="reiniciar">Reiniciar</button><button data-cenario="encerrar">Encerrar</button></div><p data-valor="cenario_estado"></p><div id="slot-sim"></div>')}${panel("Controle exclusivamente simulado", '<label>Velocidade virtual · pulsos/s<input id="velocidade-remota" type="range" min="0" max="30" value="8"></label><div class="remote"><span></span><button data-direcao="frente" aria-label="Avançar na simulação">↑</button><span></span><button data-direcao="esquerda" aria-label="Girar à esquerda na simulação">←</button><button data-direcao="parar" aria-label="Parar na simulação">■</button><button data-direcao="direita" aria-label="Girar à direita na simulação">→</button><span></span><button data-direcao="re" aria-label="Recuar na simulação">↓</button></div><button class="danger" data-cenario="emergencia">Parada de emergência SIMULADA</button><p class="note">Controle remoto real e emergência física desabilitados. Não envia PWM ao Arduino nem altera o Bluetooth.</p><label><input id="falha-arduino" type="checkbox"> Falha do Arduino simulada</label><label>Descartar a cada N telemetrias (0 desativa)<input id="descartar" type="number" min="0" max="1000" value="0"></label><label>Modo declarado somente no cenário<select id="processamento-sim"><option value="simulacao">Simulação</option><option value="embarcado">Embarcado (declarado)</option><option value="distribuido">Distribuído (declarado; sem inferência transferida)</option></select></label><button id="gravar-simulacao">Iniciar gravação simulada</button>')}</div>`;
  if (id === "diagnostico")
    html = `${panel("Condições ativas e resolvidas", '<div id="alertas-detalhados"></div><p class="note">Notificações por transição, sem repetição durante a mesma falha. Mudança de origem limpa as condições da fonte anterior.</p>')}${panel("Pesquisar eventos registrados", '<form id="form-eventos" class="toolbar"><label>Gravidade<select name="gravidade"><option value="">Todas</option><option value="info">Informação</option><option value="atencao">Atenção</option><option value="alerta">Alerta legado</option><option value="erro">Erro</option><option value="critico">Crítico</option></select></label><label>Componente / texto<input name="busca" placeholder="Arduino, câmera, sensor…"></label><label>Categoria<input name="categoria"></label><label>Origem<input name="origem"></label><label>Sessão<input name="sessao_id"></label><label>Início<input name="inicio" type="datetime-local"></label><label>Fim<input name="fim" type="datetime-local"></label><button>Consultar eventos</button></form><div id="lista-eventos" class="table-wrap"></div><button id="mais-eventos">Próxima página</button>')}`;
  if (id === "configuracoes")
    html = `<div class="grid2">${panel("Preferências desta central", '<form id="form-preferencias" class="form-grid"><label>Tema<select name="tema"><option value="escuro">Escuro</option><option value="claro">Claro</option></select></label><label>Janela dos gráficos · s<input name="janela_s" type="number" min="5" max="3600" value="60"></label><label>Gráficos · Hz<input name="graficos_hz" type="number" min="0.2" max="10" step="0.1" value="2"></label><label>Atualização visual · Hz<input name="visual_hz" type="number" min="1" max="20" value="10"></label><label>Qualidade gráfica<select name="qualidade"><option value="1">Econômica</option><option value="1.5">Equilibrada</option><option value="2">Alta</option></select></label><label>Unidades<select name="unidades"><option value="SI">SI · m, s, rad</option><option value="centimetros">Centímetros nos indicadores</option></select></label><label>Limiar administrativo CPU · % (opcional)<input name="cpu_alerta_pct" type="number" min="0" max="100"></label><label>Limiar administrativo temperatura · °C (opcional)<input name="temperatura_alerta_c" type="number" min="0" max="150"></label><label class="full">URL do painel de coleta existente<input name="painel_coleta" placeholder="http://IP_DA_PI:8080"></label><label>FOV vertical ilustrativo · °<input name="fov_vertical" type="number" min="20" max="120" value="60"></label><label>Centro visual do servo · °<input name="servo_centro" type="number" min="45" max="135" value="90"></label><button>Salvar preferências</button></form>')}${panel("Armazenamento no PC", '<form id="form-armazenamento" class="form-grid"><label><input name="imagens" type="checkbox"> Gravar imagens continuamente</label><label><input name="imagens_eventos" type="checkbox"> Gravar imagens por eventos</label><label>Limite de imagens · FPS<input name="imagens_fps" type="number" min="0.1" max="30" step="0.1" value="1"></label><label>Limite total · MiB<input name="total_mb" type="number" min="10" value="2048"></label><label>Limite de imagens · MiB<input name="imagens_mb" type="number" min="1" value="500"></label><button>Aplicar com gravação encerrada</button></form><p class="note">Usa as opções e o escritor existentes. Não remove gravações, nem altera a aquisição da câmera.</p><h3>Conexão futura</h3><form id="form-conexao"><label>Servidor do PC<input name="url" placeholder="ws://IP_DA_RASPBERRY:8765"></label><button>Salvar destino</button></form>')}</div>${panel("Registro de calibração local", '<form id="form-calibracao" class="form-grid"><label>Natureza<select name="natureza"><option value="simulada">Simulada</option><option value="estimada">Estimada</option><option value="calibrada">Calibrada (declaração do operador)</option></select></label><label>PPR esquerdo<input name="ppr_esq" type="number" min="0.01" step="0.01" required></label><label>PPR direito<input name="ppr_dir" type="number" min="0.01" step="0.01" required></label><label>Diâmetro esquerdo · m<input name="diametro_esq_m" type="number" min="0.001" step="0.001" required></label><label>Diâmetro direito · m<input name="diametro_dir_m" type="number" min="0.001" step="0.001" required></label><label>Bitola · m<input name="bitola_m" type="number" min="0.001" step="0.001" required></label><label>Relação disco/roda (opcional)<input name="relacao_disco_roda" type="number" min="0.001" step="0.001"></label><button>Registrar parâmetros locais</button></form><p class="note">Registro para consulta, sem alterar firmware/controlador ou ativar automaticamente uma calibração física. Parâmetros de execução real continuam exigindo o JSON confirmado no terminal.</p>')}`;
  return { html, charts };
}
