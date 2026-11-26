import { PAGINAS, criarPagina } from "./paginas.js";
import { OperacaoUI } from "./operacao.js";
import {
  BufferTemporal,
  esc,
  num,
  texto,
  campo,
  extrair,
  historicoParaSerie,
  identidade,
} from "./nucleo.js";
import {
  Grafico,
  radar,
  trajeto,
  boxplot,
  barras,
  exportarGrafico,
} from "./graficos.js";
const $ = (id) => document.getElementById(id),
  buffer = new BufferTemporal();
let estado = null,
  modulo = null,
  pagina = "geral",
  graficos = [],
  janela = 60,
  ultimaPintura = 0,
  epoch = -1,
  comparacao = [],
  zoom = 1,
  paginaSessoes = 0,
  paginaEventos = 0,
  filtroSessoes = {},
  filtroEventos = {},
  sessaoDetalhe = null,
  selecionadas = new Set(),
  ultimaConsulta = null,
  quadro,
  infoQuadro,
  casaQuadro,
  sim,
  casaSim,
  cinzaUrl = null,
  ultimoCinza = 0,
  cinzaOcupado = false,
  diag = {},
  dadosTabela = null;
const api = {
  get: async (p) => modulo.dados.get(p),
  post: async (p, d) =>
    (await modulo.dados.post("/api/central/" + p, d)).resultado,
};
function mensagem(t, erro = false) {
  $("mensagem").textContent = t;
  $("mensagem").classList.toggle("erro", erro);
  $("mensagem").hidden = false;
}
const executar = (fn) => async (e) => {
  if (e?.type === "submit") e.preventDefault();
  try {
    await fn(e);
  } catch (err) {
    mensagem(err.message ?? String(err), true);
  }
};
const operacaoUI = new OperacaoUI((p, d) => api.post(p, d), mensagem);
function formDados(form) {
  return Object.fromEntries(new FormData(form));
}
function parametros(d) {
  return new URLSearchParams(
    Object.entries(d).filter(([k, v]) => v != null && v !== ""),
  );
}
function datas(d) {
  for (const k of ["inicio", "fim"])
    if (d[k]) d[k] = new Date(d[k]).toISOString();
  return d;
}
const tabela = (colunas, rows) =>
  `<table><thead><tr>${colunas.map(([titulo]) => `<th>${titulo}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${colunas.map(([_, fn]) => `<td>${fn(r)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
function listaEventos(es) {
  return es.length
    ? es
        .map(
          (e) =>
            `<div class="event-row" data-severidade="${esc(e.gravidade ?? "info")}"><span class="event-dot"></span><div><b>${esc(e.mensagem ?? e.descricao ?? e.categoria ?? "Evento")}</b><small>${esc(e.componente ?? e.origem ?? "Fonte")} · ${esc(e.estado ?? "registrado")} · ${esc(e.timestamp ?? e.timestamp_utc ?? "")}</small></div></div>`,
        )
        .join("")
    : '<div class="empty">Nenhum evento disponível para esta fonte e instante.</div>';
}
function atualizarCabecalho(s) {
  const r = extrair(s),
    t = s.dados.envelope?.dados?.telemetria ?? {},
    c = s.central ?? {},
    g = c.gravacao ?? {},
    ativos = (c.alertas ?? []).filter((a) => a.ativo),
    tag = {
      simulado: "SIMULAÇÃO",
      historico: "HISTÓRICO",
      real: "DADOS REAIS",
    }[s.modo];
  $("fonte").value = s.modo;
  $("status-operacao").textContent =
    `${tag} · ${t.operacao?.modo ?? "Estado operacional indisponível"}`;
  $("estado-rede").textContent =
    `${s.dados.disponivel ? "●" : "○"} ${s.status}`;
  $("modo-processamento").textContent =
    "Processamento: " +
    (t.distribuido?.processamento ??
      t.ia?.modo_declarado ??
      t.ia?.local ??
      "indisponível");
  $("latencia-global").textContent = "RTT: " + num(r.rtt, "ms");
  $("sessao-global").textContent =
    "Sessão: " + (s.dados.envelope?.sessao?.slice(0, 8) ?? "—");
  $("hora-global").textContent =
    "Atualização: " +
    (s.dados.envelope
      ? new Date(
          s.dados.envelope.recepcao_utc ?? s.dados.envelope.timestamp,
        ).toLocaleTimeString("pt-BR")
      : "—");
  $("seguranca-global").textContent = ativos.length
    ? `${ativos.length} condição(ões) ativa(s)`
    : "Sem falha informada · proteção física não confirmada";
  $("gravando").textContent = g.gravacao ? `● ${g.estado}` : "○ Sem gravação";
  $("gravar-global").textContent = g.gravacao
    ? "Encerrar gravação"
    : "Gravar sessão";
  $("gravar-global").disabled = s.modo === "historico";
  $("timeline-global").hidden = s.modo !== "historico";
  $("alerta-global").hidden = !ativos.length;
  $("alerta-global").textContent = ativos
    .slice(0, 2)
    .map((e) => e.mensagem)
    .join(" · ");
  $("estado-central").textContent =
    `${tag} · ${buffer.itens.length}/7200 amostras no buffer · armazenamento ${g.estado ?? "indisponível"}`;
  const p = c.preferencias ?? {};
  const etapa = document.querySelector(".nav-foot");
  if (etapa && c.etapa6)
    etapa.innerHTML =
      "Plataforma local · Etapa 06<br><small>Atuação física bloqueada por padrão</small>";
  document.documentElement.classList.toggle("light", p.tema === "claro");
  if (modulo) {
    modulo.dados.periodo = 1000 / (p.visual_hz ?? 10);
    modulo.config.servo.centro = p.servo_centro ?? 90;
    if (modulo.sensores) modulo.sensores.configurarFov(p.fov_vertical ?? 60);
    if (modulo.cena && modulo.cena.qualidadeCentral !== p.qualidade) {
      modulo.cena.qualidadeCentral = p.qualidade;
      modulo.cena.renderer.setPixelRatio(
        Math.min(devicePixelRatio, p.qualidade ?? 1.5),
      );
      modulo.cena.renderer.shadowMap.enabled = (p.qualidade ?? 1.5) > 1;
    }
  }
  const link = $("painel-coleta");
  if (link) {
    link.hidden = !p.painel_coleta;
    link.href = p.painel_coleta || "#";
    $("painel-sem-url").hidden = !!p.painel_coleta;
  }
}
function valores(s) {
  const r = extrair(s),
    e = s.dados.envelope ?? {},
    p = e.dados ?? {},
    t = p.telemetria ?? {},
    m = t.motores ?? {},
    u = t.sensores ?? {},
    ia = t.ia ?? {},
    pc = s.central?.pc?.valores ?? {},
    g = s.central?.gravacao ?? {},
    rede = s.central?.rede?.canais?.telemetria ?? {},
    ct = rede.contadores ?? {},
    pose = s.dados.pose ?? {},
    sys = p.sistema?.valores ?? {},
    ok = s.dados.disponivel;
  const rows = buffer.janela(r.t, janela),
    validas = rows.filter((r) => typeof r.linha === "boolean");
  let perdas = 0;
  for (let i = 1; i < validas.length; i++)
    if (validas[i - 1].linha && !validas[i].linha) perdas++;
  const t0 = rows[0]?.t,
    t1 = rows.at(-1)?.t;
  return {
    ...r,
    uptime: s.central?.uptime_pc_s,
    idade_sonar: ok ? u.distancia_cm?.idade_s : null,
    limites_sonar: `${modulo.config.limites.parada_cm} / ${modulo.config.limites.liberacao_cm} cm`,
    obstaculo: ok ? campo(u.obstaculo_confirmado) : null,
    sonar_valido: ok && u.distancia_cm?.estado === "atual",
    falha_sensor: ok ? campo(u.falha_sensor) : null,
    sonar_bluetooth:
      t.operacao?.ultrassom_bluetooth_ativo == null
        ? "Não informado"
        : t.operacao.ultrassom_bluetooth_ativo
          ? "Ativo na configuração"
          : "Desativado na configuração atual",
    seguranca: "Supervisão embarcada preservada; estado completo não exportado",
    sentido_esq:
      r.pwm_esq == null
        ? null
        : r.pwm_esq > 0
          ? "Frente"
          : r.pwm_esq < 0
            ? "Ré"
            : "Parado",
    sentido_dir:
      r.pwm_dir == null
        ? null
        : r.pwm_dir > 0
          ? "Frente"
          : r.pwm_dir < 0
            ? "Ré"
            : "Parado",
    idade_frame: s.imagem?.idade_visualizacao_s,
    algoritmo: t.visao?.algoritmo,
    resolucao: $("imagem").naturalWidth
      ? `${$("imagem").naturalWidth} × ${$("imagem").naturalHeight}`
      : null,
    frame: s.imagem?.dados.frame_id ?? t.visao?.frame_id,
    taxa_linha: validas.length
      ? (validas.filter((r) => r.linha).length / validas.length) * 100
      : null,
    perdas_linha: validas.length ? perdas : null,
    opencv_ms:
      p.tempos_s?.opencv_s?.media != null
        ? p.tempos_s.opencv_s.media * 1000
        : null,
    frames_descartados:
      s.central?.rede?.canais?.imagens?.contadores?.descartes_fila_local,
    politica: ia.politica,
    local_ia:
      ia.local === "simulado_no_PC"
        ? "Simulado no computador"
        : ia.local === "raspberry_ou_host_embarcado"
          ? "Host embarcado informado"
          : ia.local,
    processamento: ia.modo_declarado ?? "Não informado",
    aprendizado: ia.aprendizado_ativo,
    inferencia_ms:
      ia.diagnostico?.inferencia_s != null
        ? ia.diagnostico.inferencia_s * 1000
        : p.tempos_s?.cnn_s?.media != null
          ? p.tempos_s.cnn_s.media * 1000
          : null,
    versao_modelo: ia.diagnostico?.versao ?? ia.diagnostico?.modelo,
    predicao: ia.diagnostico?.previsao,
    acao_ia: ia.diagnostico?.acao,
    recompensa: campo(ia.recompensa),
    natureza_host:
      p.sistema_natureza === "observado_no_PC_da_simulacao"
        ? "PC da simulação; Raspberry virtual"
        : p.sistema_natureza === "simulado"
          ? "SIMULADO no computador"
          : s.modo === "historico"
            ? "Registro histórico, ver metadados"
            : "Host da telemetria",
    cpu_nucleos:
      ok && sys.cpu_nucleos_pct
        ? sys.cpu_nucleos_pct.map((v) => num(v, "%")).join(" · ")
        : null,
    frequencia: ok ? sys.frequencia_mhz : null,
    subtensao: ok ? sys.subtensao_atual : null,
    throttling: ok ? sys.throttling_atual : null,
    controle_hz: p.tempos_s?.controle_periodo_s?.media
      ? 1 / p.tempos_s.controle_periodo_s.media
      : null,
    controle_jitter:
      p.tempos_s?.controle_periodo_s?.desvio_padrao != null
        ? p.tempos_s.controle_periodo_s.desvio_padrao * 1000
        : null,
    rss_pc:
      pc.processo_rss_bytes != null ? pc.processo_rss_bytes / 1024 ** 2 : null,
    render_fps: $("cena").clientWidth
      ? $("fps").textContent
      : "Suspensa (3D oculto)",
    consulta_ms: s.central?.consultas?.media_ms,
    fanout_descartes: s.central?.fanout?.descartadas,
    tempo_conexao: rede.tempo_conexao_s,
    render_ms: diag.render?.media_render_cpu_ms,
    lote_ms: g.tempo_medio_lote_s != null ? g.tempo_medio_lote_s * 1000 : null,
    persistidas: g.contadores?.persistidas,
    banco_mb: g.banco_bytes != null ? g.banco_bytes / 1024 ** 2 : null,
    servidor: s.central?.rede?.servidor,
    rede_estado:
      s.modo === "historico"
        ? "Reprodução local, sem conexão com hardware"
        : s.status,
    rtt_p95: rede.rtt_s?.p95 != null ? rede.rtt_s.p95 * 1000 : null,
    mensagens_rx: ct.mensagens_rx,
    reconexoes: ct.reconexoes,
    idade_telemetria: s.dados.idade_s,
    tele_hz: t1 > t0 ? (rows.length - 1) / (t1 - t0) : null,
    theta:
      ok && pose.orientacao_rad != null
        ? (pose.orientacao_rad * 180) / Math.PI
        : null,
    distancia_total: ok ? pose.distancia_m : null,
    vel_linear: ok ? pose.velocidade_linear_m_s : null,
    vel_angular: ok ? pose.velocidade_angular_rad_s : null,
    cenario_estado: `${s.central?.cenario ?? "—"} · ${s.central?.pausado ? "pausado" : "ativo"} · ${s.modo === "simulado" ? "fonte isolada" : "controles bloqueados nesta origem"}`,
  };
}
function pintar() {
  if (!estado || !modulo) return;
  operacaoUI.atualizar(estado);
  const painelAntigo = document
    .querySelector("[data-direcao]")
    ?.closest(".panel");
  if (painelAntigo && estado.central?.etapa6) painelAntigo.hidden = true;
  for (const [k, valor] of Object.entries(estado.simulacao ?? {})) {
    const i = $("sim-" + k);
    if (!i || document.activeElement === i) continue;
    if (i.type === "checkbox") i.checked = valor;
    else {
      i.value = valor;
      const o = i.parentElement.querySelector("output");
      if (o) o.value = valor;
    }
  }
  const s = estado,
    v = valores(s),
    r = extrair(s),
    rows = buffer.janela(r.t, janela);
  document.querySelectorAll("[data-valor]").forEach((el) => {
    let valor = v[el.dataset.valor],
      unidade = el.dataset.unidade;
    if (
      s.central?.preferencias.unidades === "centimetros" &&
      ["m", "m/s"].includes(unidade) &&
      typeof valor === "number"
    ) {
      valor *= 100;
      unidade = unidade.replace("m", "cm");
    }
    el.textContent =
      typeof valor === "number" ? num(valor, unidade) : texto(valor);
  });
  document.querySelectorAll("[data-raw]").forEach((el) => {
    const qual = el.dataset.raw;
    el.textContent =
      JSON.stringify(
        qual === "rede"
          ? s.central?.rede
          : s.dados.envelope?.dados.telemetria[qual],
        null,
        2,
      ) ?? "Indisponível";
  });
  graficos.forEach((g) => g.atualizar(rows));
  if ($("radar")) radar($("radar"), rows, r.t, modulo.config.limites.parada_cm);
  if ($("trajeto-2d"))
    trajeto($("trajeto-2d"), s.dados.trajeto ?? [], comparacao, zoom);
  const es =
    s.modo === "historico"
      ? (s.eventos ?? [])
          .slice(-6)
          .reverse()
          .map((e) => ({
            mensagem: JSON.stringify(e.detalhes),
            timestamp: e.timestamp,
            origem: "Histórico",
          }))
      : (s.central?.ocorrencias ?? []).slice(-6).reverse();
  if ($("eventos-rapidos")) $("eventos-rapidos").innerHTML = listaEventos(es);
  if ($("alertas-detalhados"))
    $("alertas-detalhados").innerHTML = listaEventos(s.central?.alertas ?? []);
  document
    .querySelectorAll(
      "[data-direcao],[data-cenario],#gravar-simulacao,#falha-arduino,#descartar,#processamento-sim",
    )
    .forEach((el) => (el.disabled = s.modo !== "simulado"));
  if ($("marcadores")) {
    const ss = $("sessoes").selectedOptions[0],
      max = +$("tempo").max,
      base = Date.parse(s.replay.posicao_utc ?? "") - +$("tempo").value * 1000;
    $("marcadores").innerHTML = (s.eventos ?? [])
      .map((e) => {
        const p = ((Date.parse(e.timestamp) - base) / 1000 / max) * 100;
        return p >= 0 && p <= 100
          ? `<i style="left:${p}%" title="${esc(e.timestamp)} · ${esc(JSON.stringify(e.detalhes))}"></i>`
          : "";
      })
      .join("");
  }
}
async function receber(s) {
  estado = s;
  buffer.adicionar(s);
  atualizarCabecalho(s);
  if (identidade(s) !== epoch) {
    if (cinzaUrl) {
      URL.revokeObjectURL(cinzaUrl);
      cinzaUrl = null;
    }
    if ($("imagem-cinza")) $("imagem-cinza").hidden = true;
    epoch = identidade(s);
    const local = epoch;
    if (ultimaConsulta) ultimaConsulta.abort();
    if (s.modo === "historico" && s.replay.sessao && s.replay.posicao_utc) {
      ultimaConsulta = new AbortController();
      try {
        const r = await fetch(
          "/api/central/janela?" +
            parametros({
              sessao: s.replay.sessao,
              fim: s.replay.posicao_utc,
              segundos: janela,
              pontos: 240,
            }),
          { signal: ultimaConsulta.signal },
        );
        const q = await r.json();
        if (!r.ok) throw Error(q.erro);
        if (epoch === local) buffer.substituir(q.itens.map(historicoParaSerie));
      } catch (e) {
        if (e.name !== "AbortError")
          mensagem("Não foi possível restaurar o gráfico: " + e.message, true);
      }
    }
  }
  const hz = s.central?.preferencias.graficos_hz ?? 2;
  if (performance.now() - ultimaPintura >= 1000 / hz) {
    ultimaPintura = performance.now();
    pintar();
  }
}
async function navegar(id) {
  document.querySelector(".shell").classList.remove("expanded-mobile");
  if (cinzaUrl) {
    URL.revokeObjectURL(cinzaUrl);
    cinzaUrl = null;
  }
  if (!PAGINAS.some((p) => p[0] === id)) id = "geral";
  pagina = id;
  const def = PAGINAS.find((p) => p[0] === id);
  if (quadro) casaQuadro.append(quadro, infoQuadro);
  if (sim) casaSim.append(sim);
  $("twin-storage").append($("twin-app"));
  const p = criarPagina(id);
  if (["geral", "ia", "desempenho", "comunicacao", "gemeo"].includes(id))
    p.html = '<section id="operacao-resumo"></section>' + p.html;
  $("conteudo").innerHTML = p.html;
  window.scrollTo(0, 0);
  if ($("ativar-cinza"))
    $("ativar-cinza").onchange = () => {
      if (!$("ativar-cinza").checked) {
        $("imagem-cinza").hidden = true;
        if (cinzaUrl) URL.revokeObjectURL(cinzaUrl);
        cinzaUrl = null;
      }
    };
  $("titulo-pagina").textContent = def[1];
  $("heading-pagina").textContent = def[1];
  $("descricao-pagina").textContent = def[3];
  document
    .querySelectorAll("#menu a")
    .forEach((a) =>
      a.setAttribute("aria-current", a.hash === "#" + id ? "page" : "false"),
    );
  $("twin-app").classList.toggle("overview-twin", id === "geral");
  if ($("slot-twin")) $("slot-twin").append($("twin-app"));
  if (id === "gemeo" && estado?.central?.etapa6) {
    const destaque = document.createElement("button");
    destaque.textContent = "Inspecionar Raspberry no modelo";
    destaque.onclick = () => modulo.selecionar("raspberry_pi");
    $("conteudo").prepend(destaque);
  }
  if ($("slot-camera")) $("slot-camera").append(quadro, infoQuadro);
  if ($("slot-sim")) $("slot-sim").append(sim);
  graficos = p.charts.map((g) => new Grafico($(g.id), g.series, g.unidade));
  if (id === "historico") await listarSessoes();
  if (id === "experimentos") await listarExperimentos();
  if (id === "ia") await listarTreinos();
  if (id === "diagnostico") await listarEventos();
  if (id === "odometria") await opcoesSessoes($("comparar-2d"));
  if (id === "configuracoes" && estado) {
    const f = $("form-preferencias"),
      p = estado.central.preferencias;
    for (const [k, v] of Object.entries(p))
      if (f.elements[k] && v != null) f.elements[k].value = v;
    const op = estado.central.opcoes_armazenamento ?? {},
      fo = $("form-armazenamento");
    for (const k of ["imagens", "imagens_eventos"])
      if (fo.elements[k]) fo.elements[k].checked = !!op[k];
    if (op.imagens_fps != null) fo.elements.imagens_fps.value = op.imagens_fps;
    if (op.max_bytes != null)
      fo.elements.total_mb.value = op.max_bytes / 1024 ** 2;
    if (op.max_imagens_bytes != null)
      fo.elements.imagens_mb.value = op.max_imagens_bytes / 1024 ** 2;
  }
  ligarFormularios();
  operacaoUI.montar(id);
  pintar();
}
async function opcoesSessoes(select) {
  const q = await api.get("/api/central/sessoes?limite=100");
  select.innerHTML =
    '<option value="">Selecione uma sessão…</option>' +
    q.itens
      .map(
        (s) =>
          `<option value="${s.id}">${s.simulado ? "SIM" : "REAL"} · ${esc(s.nome || s.id.slice(0, 8))}</option>`,
      )
      .join("");
}
async function listarSessoes() {
  const q = await api.get(
    "/api/central/sessoes?" +
      parametros({ ...filtroSessoes, pagina: paginaSessoes, limite: 20 }),
  );
  if (pagina !== "historico") return;
  dadosTabela = q.itens;
  $("paginacao-sessoes").textContent =
    `Página ${q.pagina + 1} · ${q.total} sessões`;
  $("lista-sessoes").innerHTML = q.itens.length
    ? tabela(
        [
          [
            "Comparar",
            (s) =>
              `<input type="checkbox" data-selecionar="${s.id}" aria-label="Selecionar sessão ${s.id.slice(0, 8)}" ${selecionadas.has(s.id) ? "checked" : ""}>`,
          ],
          [
            "Sessão",
            (s) =>
              `<b>${esc(s.nome || s.id.slice(0, 8))}</b><small>${esc(s.id)}</small>`,
          ],
          [
            "Origem",
            (s) =>
              `<span class="tag ${s.simulado ? "sim" : ""}">${s.simulado ? "SIMULADA" : "REAL"}</span>`,
          ],
          [
            "Início / duração",
            (s) =>
              `${esc(new Date(s.inicio_observado_utc).toLocaleString("pt-BR"))}<small>${num((Date.parse(s.fim_observado_utc) - Date.parse(s.inicio_observado_utc)) / 1000, "s")}</small>`,
          ],
          ["Amostras / imagens", (s) => `${s.amostras} / ${s.imagens}`],
          [
            "Ações",
            (s) =>
              `<button data-resumo="${s.id}">Resumo</button> <button data-reproduzir="${s.id}">Reproduzir</button> <button data-imagens="${s.id}">Imagens</button>`,
          ],
        ],
        q.itens,
      )
    : '<div class="empty">Nenhuma sessão encontrada. Grave um cenário simulado para criar dados nesta mesma base.</div>';
  $("anterior-sessoes").disabled = paginaSessoes === 0;
  $("proxima-sessoes").disabled = (paginaSessoes + 1) * 20 >= q.total;
}
async function mostrarResumo(sid) {
  $("detalhe-sessao").innerHTML =
    '<div class="empty" role="status">Calculando resumo da sessão…</div>';
  const q = await api.get("/api/central/resumo?sessao=" + sid);
  if (pagina !== "historico") return;
  sessaoDetalhe = sid;
  const stats = q.estatisticas;
  $("detalhe-sessao").innerHTML =
    `<div class="panel"><h2>Resumo · ${esc(q.sessao.nome || sid.slice(0, 8))}</h2><p>${q.sessao.simulado ? "SIMULADO" : "REAL"} · ${q.resumo.amostras} amostras · ${q.sessao.imagens} imagens · duração observada ${num(q.resumo.duracao_observada_s, "s")}</p>${tabela(
      [
        ["Métrica", (r) => r[0]],
        ["n", (r) => r[1].n],
        ["Média", (r) => num(r[1].media)],
        ["Mediana", (r) => num(r[1].mediana)],
        ["Mínimo", (r) => num(r[1].minimo)],
        ["Máximo", (r) => num(r[1].maximo)],
        ["DP", (r) => num(r[1].desvio_padrao)],
        ["p95", (r) => num(r[1].p95)],
      ],
      Object.entries(stats).map(([k, v]) => [
        k + (k === "latencia" ? " (s)" : k === "temperatura" ? " (°C)" : ""),
        v,
      ]),
    )}<p class="note">Percurso: ${num(q.sessao.odometria?.distancia_m, "m")} · eventos: ${esc(JSON.stringify(q.resumo.eventos))}</p><form id="form-metadados" class="form-grid"><label>Nome da sessão<input name="nome" maxlength="256" value="${esc(q.sessao.nome)}"></label><label>Observações<textarea name="observacoes">${esc(q.sessao.observacoes)}</textarea></label><button>Salvar observações</button></form><div class="divider"></div><form id="form-exportar" class="form-grid"><label>Categorias CSV<select name="categorias" multiple size="5">${["consolidado", "telemetria", "motores", "sensores", "visao_computacional", "inteligencia_artificial", "desempenho", "comunicacao", "odometria", "eventos", "experimentos", "imagens", "percepcao_remota", "operacao_rede_eventos"].map((k) => `<option ${k === "consolidado" ? "selected" : ""}>${k}</option>`).join("")}</select></label><label>Início (opcional)<input name="inicio" type="datetime-local"></label><label>Fim (opcional)<input name="fim" type="datetime-local"></label><button>Exportar CSV e resumo</button></form><details><summary>Configurações e limitações</summary><pre>${esc(JSON.stringify({ configuracoes: q.sessao.configuracoes, limitacoes: q.limitacoes }, null, 2))}</pre></details></div>`;
  ligarFormularios();
  $("detalhe-sessao").scrollIntoView({ block: "start" });
}
async function listarExperimentos() {
  const rows = await api.get("/api/central/experimentos");
  if (pagina !== "experimentos") return;
  $("lista-experimentos").innerHTML = rows.length
    ? rows
        .map(
          (e) =>
            `<details><summary>${esc(e.nome)} · ${e.sessoes.length} sessões · ${esc(e.modo_processamento)}</summary><p>${esc(e.objetivo)}</p><pre>${esc(JSON.stringify(e, null, 2))}</pre><button data-experimento-export="${e.id}">Exportar experimento CSV</button></details>`,
        )
        .join("")
    : '<div class="empty">Nenhum experimento registrado.</div>';
  $("experimento-associar").innerHTML = rows
    .map((e) => `<option value="${e.id}">${esc(e.nome)}</option>`)
    .join("");
}
async function listarTreinos() {
  const treinos = await api.get("/api/central/treinos");
  if (pagina !== "ia") return;
  $("treinos-registrados").classList.remove("empty");
  $("treinos-registrados").innerHTML = treinos.length
    ? '<p class="note">Ensaios offline anteriores com frames de vídeos. Estes registros não comprovam desempenho em tempo real ou uso físico aprovado. Curvas ausentes não são inventadas.</p>' +
      treinos
        .map(
          (t, i) =>
            `<details ${i === treinos.length - 1 ? "open" : ""}><summary>${esc(t.id)} · checkpoint ${t.melhor_passo} · ${esc(t.hash_pesos)}</summary><p>Dataset: ${esc(JSON.stringify(t.dataset.grupos))} · entrada ${esc(JSON.stringify(t.entrada))} · ${esc(t.criado_utc)}</p>${tabela(
              [
                ["Grupo", (r) => esc(r[0])],
                ["n", (r) => r[1]?.n ?? "—"],
                ["MAE normalizado", (r) => num(r[1]?.mae, "", 6)],
                ["MSE", (r) => num(r[1]?.mse, "", 6)],
                [
                  "MAE na entrada de 80 px",
                  (r) => num(r[1]?.mae_pixels_entrada80),
                ],
              ],
              Object.entries(t.metricas),
            )}${t.curva.length ? blocoTreino(i) : '<div class="empty">CSV de evolução ausente neste checkout. Métricas finais provêm do JSON registrado.</div>'}<p class="note">${esc(t.origem)} · ${esc(t.preprocessamento)} · ${esc(t.criterio)}. Histórico por passos de otimização, não por épocas.</p></details>`,
        )
        .join("")
    : '<div class="empty">Não foram encontrados artefatos locais verificáveis de treino.</div>';
  for (const [t, i] of treinos.map((t, i) => [t, i]))
    if (t.curva.length) {
      const rows = t.curva.map((r) => ({ ...r, t: r.passo }));
      new Grafico(
        $("treino-mse-" + i),
        [
          ["mse_treino", "MSE treino"],
          ["mse_validacao", "MSE validação"],
        ],
        "MSE",
        "passo",
      ).atualizar(rows);
      new Grafico(
        $("treino-perda-" + i),
        [["perda_lote", "Perda do lote"]],
        "perda registrada",
        "passo",
      ).atualizar(rows);
    }
}
function blocoTreino(i) {
  return `<div class="grid2"><div><h3>MSE de treino e validação × passo</h3><svg id="treino-mse-${i}" class="chart" role="img" aria-label="MSE de treinamento e validação por passo"></svg><p class="legend">Verde: treino · azul: validação</p><button data-export="treino-mse-${i}" data-formato="svg">Exportar curva SVG</button></div><div><h3>Perda do lote × passo</h3><svg id="treino-perda-${i}" class="chart" role="img" aria-label="Perda registrada por passo"></svg></div></div>`;
}
async function comparar() {
  const q = await api.post("comparar", { sessoes: [...selecionadas] });
  if (pagina !== "experimentos") {
    history.replaceState(null, "", "#experimentos");
    await navegar("experimentos");
  }
  const rows = q.itens;
  $("comparacao-experimentos").innerHTML =
    `<p class="note">${esc(q.natureza)}</p><div class="table-wrap">${tabela(
      [
        [
          "Sessão / origem",
          (r) =>
            `${esc(r.sessao.nome || r.sessao.id.slice(0, 8))}<small>${r.sessao.simulado ? "SIMULADA" : "REAL"} · ${esc(r.sessao.modo_processamento)}</small>`,
        ],
        ["Amostras", (r) => r.resumo.amostras],
        [
          "Processamentos registrados",
          (r) =>
            esc(
              (r.sessao.processamentos_registrados ?? []).join(" / ") ||
                "Sem dados da etapa 6",
            ),
        ],
        [
          "Ciclo distribuído · média / p95 (s)",
          (r) =>
            num(r.estatisticas.ciclo_distribuido?.media) +
            " / " +
            num(r.estatisticas.ciclo_distribuido?.p95),
        ],
        [
          "Inferência · média / p95 (s)",
          (r) =>
            num(r.estatisticas.inferencia_percepcao?.media) +
            " / " +
            num(r.estatisticas.inferencia_percepcao?.p95),
        ],
        [
          "PPS E · média / DP",
          (r) =>
            num(r.estatisticas.pps_esq.media) +
            " / " +
            num(r.estatisticas.pps_esq.desvio_padrao),
        ],
        [
          "RTT · média / p95 (s)",
          (r) =>
            num(r.estatisticas.latencia.media) +
            " / " +
            num(r.estatisticas.latencia.p95),
        ],
        [
          "Temperatura · média / máx (°C)",
          (r) =>
            num(r.estatisticas.temperatura.media) +
            " / " +
            num(r.estatisticas.temperatura.maximo),
        ],
      ],
      rows,
    )}</div><h3>Distribuição descritiva de RTT por sessão · s</h3><svg class="chart" id="boxplot-latencia" role="img" aria-label="Boxplot de latência por sessão"></svg><p class="note">Caixa: q1–q3; linha: mediana; extremos: mínimo e máximo. Não é teste de hipótese nem equivalência entre condições.</p><button data-export="boxplot-latencia" data-formato="svg">Exportar gráfico SVG</button>`;
  boxplot(
    $("boxplot-latencia"),
    rows.map((r) => ({
      nome:
        (r.sessao.simulado ? "SIM" : "REAL") +
        " " +
        (r.sessao.nome || r.sessao.id.slice(0, 8)),
      stats: r.estatisticas.latencia,
    })),
  );
  const area = $("comparacao-experimentos"),
    extras = document.createElement("div");
  extras.innerHTML =
    '<h3>Média de RTT por sessão · s</h3><svg id="comparacao-barras" class="chart" role="img" aria-label="RTT médio por sessão"></svg>' +
    rows
      .map(
        (r, i) =>
          `<h3>Distribuição de RTT · ${r.sessao.simulado ? "SIM" : "REAL"} ${esc(r.sessao.nome || r.sessao.id.slice(0, 8))}</h3><svg id="distribuicao-${i}" class="chart" role="img" aria-label="Distribuição de latência por intervalo"></svg><p class="note">Intervalos de RTT em segundos no eixo vertical; contagem de amostras no eixo horizontal.</p>`,
      )
      .join("");
  area.append(extras);
  barras(
    $("comparacao-barras"),
    rows.map((r) => ({
      nome:
        (r.sessao.simulado ? "SIM " : "REAL ") +
        (r.sessao.nome || r.sessao.id.slice(0, 8)),
      valor: r.estatisticas.latencia.media,
    })),
  );
  rows.forEach((r, i) =>
    barras(
      $("distribuicao-" + i),
      (r.histograma_rtt ?? []).map((b) => ({
        nome: num(b.inicio_s, "", 6) + "–" + num(b.fim_s, "s", 6),
        valor: b.n,
      })),
      "amostras",
    ),
  );
}
async function listarEventos() {
  const rows = await api.get(
    "/api/central/eventos?" +
      parametros({ ...filtroEventos, pagina: paginaEventos }),
  );
  if (pagina !== "diagnostico") return;
  $("lista-eventos").innerHTML = rows.length
    ? tabela(
        [
          ["Horário", (r) => esc(r.timestamp_utc)],
          ["Gravidade", (r) => esc(r.gravidade)],
          [
            "Categoria / origem",
            (r) => esc(r.categoria) + "<small>" + esc(r.origem) + "</small>",
          ],
          ["Descrição", (r) => esc(r.descricao)],
          [
            "Detalhes",
            (r) =>
              `<details><summary>Abrir</summary><pre>${esc(r.detalhes_json)}</pre></details>`,
          ],
        ],
        rows,
      )
    : '<div class="empty">Nenhum evento neste filtro.</div>';
}
async function download(categorias, f = {}) {
  mensagem("Preparando arquivos CSV…");
  const r = await api.post("exportar", { categorias, filtros: f });
  oferecerDownload(r);
}
function oferecerDownload(r) {
  mensagem("Arquivos preparados. ");
  const a = document.createElement("a");
  a.href = r.url;
  a.download = "analise_robo.zip";
  a.textContent = "Baixar arquivo CSV (ZIP)";
  a.onclick = executar(async (e) => {
    e.preventDefault();
    const resposta = await fetch(r.url);
    if (!resposta.ok) throw Error("Não foi possível baixar a exportação.");
    // ZIP pequeno por blob também funciona em navegadores incorporados.
    // Grandes arquivos usam o download direto, sem cópia integral em memória.
    if (+resposta.headers.get("Content-Length") > 64 * 1024 ** 2) {
      await resposta.body?.cancel();
      const direto = document.createElement("a");
      direto.href = r.url;
      direto.download = a.download;
      direto.click();
      return;
    }
    const url = URL.createObjectURL(await resposta.blob());
    const arquivo = document.createElement("a");
    arquivo.href = url;
    arquivo.download = a.download;
    arquivo.click();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  });
  $("mensagem").append(a);
}
function ligarFormularios() {
  document.querySelectorAll("#conteudo label").forEach((l) => {
    const c = l.querySelector("input,select,textarea");
    if (c && !c.hasAttribute("aria-label")) {
      const nome = [...l.childNodes]
        .filter((n) => n.nodeType === 3)
        .map((n) => n.textContent)
        .join(" ")
        .trim();
      if (nome) c.setAttribute("aria-label", nome);
    }
  });
  const bind = (id, fn) => {
    if ($(id)) $(id).onsubmit = executar(fn);
  };
  bind("form-sessoes", async (e) => {
    filtroSessoes = datas(formDados(e.target));
    paginaSessoes = 0;
    await listarSessoes();
  });
  bind("form-eventos", async (e) => {
    filtroEventos = datas(formDados(e.target));
    paginaEventos = 0;
    await listarEventos();
  });
  bind("form-metadados", async (e) => {
    await api.post("sessao-metadados", {
      sessao: sessaoDetalhe,
      ...formDados(e.target),
    });
    mensagem("Observações salvas na sessão.");
    await listarSessoes();
  });
  bind("form-exportar", async (e) => {
    const d = datas(formDados(e.target));
    await download(
      [...e.target.elements.categorias.selectedOptions].map((o) => o.value),
      {
        sessao: sessaoDetalhe,
        ...(d.inicio ? { inicio: d.inicio } : {}),
        ...(d.fim ? { fim: d.fim } : {}),
      },
    );
  });
  bind("form-experimento", async (e) => {
    const d = formDados(e.target);
    const conf = JSON.parse(d.configuracoes || "{}");
    d.configuracoes = { ...conf, hipotese: d.hipotese };
    delete d.hipotese;
    d.repeticao = +d.repeticao;
    await api.post("experimento", d);
    mensagem("Experimento registrado.");
    await listarExperimentos();
  });
  bind("form-associar", async () => {
    await api.post("associar", {
      experimento: $("experimento-associar").value,
      sessoes: [...selecionadas],
    });
    mensagem("Sessões associadas.");
    await listarExperimentos();
  });
  bind("form-preferencias", async (e) => {
    const d = formDados(e.target);
    for (const k of [
      "janela_s",
      "graficos_hz",
      "visual_hz",
      "qualidade",
      "fov_vertical",
      "servo_centro",
    ])
      d[k] = +d[k];
    for (const k of ["cpu_alerta_pct", "temperatura_alerta_c"])
      d[k] = d[k] === "" ? null : +d[k];
    await api.post("preferencias", d);
    janela = d.janela_s;
    mensagem("Preferências locais salvas.");
    $("qualidade").value = d.qualidade;
    $("qualidade").onchange({ target: $("qualidade") });
  });
  bind("form-conexao", async (e) => {
    await api.post("conexao", formDados(e.target));
    $("fonte").querySelector("[value=real]").disabled = false;
    $("modo").querySelector("[value=real]").disabled = false;
    mensagem(
      "Destino salvo no processo do PC. Token de acesso continua somente no terminal.",
    );
  });
  bind("form-armazenamento", async (e) => {
    const d = formDados(e.target);
    await api.post("armazenamento", {
      imagens: e.target.elements.imagens.checked,
      imagens_eventos: e.target.elements.imagens_eventos.checked,
      imagens_fps: +d.imagens_fps,
      max_bytes: +d.total_mb * 1024 ** 2,
      max_imagens_bytes: +d.imagens_mb * 1024 ** 2,
    });
    mensagem("Opções do gravador aplicadas.");
  });
  bind("form-calibracao", async (e) => {
    const d = formDados(e.target),
      natureza = d.natureza;
    delete d.natureza;
    for (const k of Object.keys(d)) d[k] = d[k] === "" ? null : +d[k];
    d.simulada = natureza === "simulada";
    d.confirmada = natureza === "calibrada";
    await api.post("preferencias", { calibracao: { natureza, parametros: d } });
    mensagem(
      "Parâmetros registrados localmente. Nenhum parâmetro físico do controlador foi alterado.",
    );
  });
}
document.addEventListener(
  "click",
  executar(async (e) => {
    const el = e.target.closest("button");
    if (!el) return;
    if (el.dataset.fullscreen != null) {
      const twin = $("twin-app");
      if (document.fullscreenElement) await document.exitFullscreen();
      else await twin.requestFullscreen();
    }
    if (el.dataset.export)
      await exportarGrafico($(el.dataset.export), el.dataset.formato);
    if (el.dataset.resumo) await mostrarResumo(el.dataset.resumo);
    if (el.dataset.reproduzir) {
      $("modo").value = "historico";
      await $("modo").onchange();
      $("sessoes").value = el.dataset.reproduzir;
      await $("sessoes").onchange();
      mensagem("Sessão carregada e pausada. Use a linha do tempo global.");
    }
    if (el.dataset.imagens) {
      const q = await api.get(
        "/api/central/dados?" +
          parametros({
            categoria: "imagens",
            filtros: JSON.stringify({ sessao: el.dataset.imagens }),
            limite: 12,
          }),
      );
      $("lista-imagens").innerHTML = q.length
        ? q
            .map(
              (i) =>
                `<div class="panel"><img alt="Frame histórico ${i.frame_id}" loading="lazy" style="width:100%" src="/api/central/imagem?id=${i.id}"><p class="note">Frame ${i.frame_id} · ${esc(i.recebido_utc)} · ${i.simulado ? "simulado" : "real"}</p></div>`,
            )
            .join("")
        : '<div class="empty">Sem imagens gravadas nesta sessão. Nenhum frame será inventado.</div>';
    }
    if (el.dataset.experimentoExport)
      await download(["experimentos", "consolidado", "eventos"], {
        experimento: el.dataset.experimentoExport,
      });
    if (el.dataset.cenario)
      await api.post("cenario", {
        acao: el.dataset.cenario,
        cenario: $("cenario").value,
      });
    if (el.dataset.direcao) {
      if (estado.modo !== "simulado") throw Error("Controle físico bloqueado");
      const vel = +$("velocidade-remota").value;
      const par = {
        frente: [vel, vel],
        re: [-vel, -vel],
        esquerda: [-vel, vel],
        direita: [vel, -vel],
        parar: [0, 0],
      }[el.dataset.direcao];
      await modulo.dados.post("/api/simulacao", {
        esq: par[0],
        dir: par[1],
        motores: true,
      });
    }
    if (el.id === "comparar-selecionadas") await comparar();
    if (el.id === "exportar-selecao") {
      mensagem("Preparando arquivos CSV da seleção…");
      const r = await api.post("exportar", {
        categorias: ["consolidado", "eventos", "odometria"],
        sessoes: [...selecionadas],
        filtros: {},
      });
      oferecerDownload(r);
    }
    if (el.id === "anterior-sessoes") {
      paginaSessoes--;
      await listarSessoes();
    }
    if (el.id === "proxima-sessoes") {
      paginaSessoes++;
      await listarSessoes();
    }
    if (el.id === "mais-eventos") {
      paginaEventos++;
      await listarEventos();
    }
    if (el.id === "zoom-mais") {
      zoom *= 1.4;
      pintar();
    }
    if (el.id === "zoom-menos") {
      zoom /= 1.4;
      pintar();
    }
    if (el.id === "centrar-trajeto") {
      zoom = 1;
      pintar();
    }
    if (el.id === "reset-trajeto")
      await modulo.dados.post("/api/referencia", {});
    if (el.id === "exportar-odometria") {
      const sid = estado.dados.envelope?.sessao;
      if (!sid) throw Error("Sem sessão");
      await download(["odometria"], { sessao: sid });
    }
    if (el.id === "gravar-simulacao")
      await api.post("gravacao", {
        acao: "iniciar",
        nome: "Cenário " + $("cenario").value,
      });
  }),
);
document.addEventListener(
  "change",
  executar(async (e) => {
    const el = e.target;
    if (el.dataset.selecionar) {
      if (el.checked) selecionadas.add(el.dataset.selecionar);
      else selecionadas.delete(el.dataset.selecionar);
    }
    if (el.dataset.janela != null) {
      janela = +el.value;
      if (estado.modo === "historico") {
        epoch = -1;
        await receber(estado);
      }
      pintar();
    }
    if (el.id === "falha-arduino")
      await modulo.dados.post("/api/simulacao", { arduino: !el.checked });
    if (el.id === "descartar")
      await modulo.dados.post("/api/simulacao", { descartar_cada: +el.value });
    if (el.id === "processamento-sim")
      await modulo.dados.post("/api/simulacao", { processamento: el.value });
    if (el.id === "comparar-2d") {
      comparacao = el.value
        ? (await api.get("/api/trajeto?sessao=" + el.value)).pontos
        : [];
      pintar();
    }
  }),
);
window.addEventListener("robo:estado", (e) => {
  receber(e.detail).catch((err) => mensagem(err.message, true));
});
window.addEventListener("hashchange", () =>
  navegar(location.hash.slice(1)).catch((err) => mensagem(err.message, true)),
);
try {
  $("menu").innerHTML = PAGINAS.map(
    ([id, n, icone]) =>
      `<a href="#${id}" aria-label="${n}" title="${n}"><span class="nav-icon" aria-hidden="true">${icone}</span><span class="nav-name">${n}</span></a>`,
  ).join("");
  modulo = await import("/src/main.js");
  quadro = document.querySelector(".quadro");
  infoQuadro = $("camera-info");
  casaQuadro = quadro.parentElement;
  sim = $("sim");
  casaSim = sim.parentElement;
  const hist = $("historico");
  $("timeline-global").append(hist);
  const marc = document.createElement("div");
  marc.id = "marcadores";
  hist.append(marc);
  $("velocidade").prepend(new Option("0.25", "0.25"));
  $("fonte").querySelector("[value=real]").disabled =
    !modulo.config.real_configurado;
  $("fonte").onchange = executar(async (e) => {
    e.target.disabled = true;
    try {
      $("modo").value = e.target.value;
      await $("modo").onchange();
    } finally {
      e.target.disabled = false;
    }
  });
  $("gravar-global").onclick = executar(async () => {
    await api.post("gravacao", {
      acao: estado?.central?.gravacao?.gravacao ? "encerrar" : "iniciar",
    });
    mensagem("Estado da gravação atualizado.");
  });
  $("recolher").onclick = () =>
    document
      .querySelector(".shell")
      .classList.toggle(
        matchMedia("(max-width:1000px)").matches
          ? "expanded-mobile"
          : "collapsed",
      );
  $("fechar-menu").onclick = () =>
    document.querySelector(".shell").classList.remove("expanded-mobile");
  new ResizeObserver(() =>
    document
      .querySelector(".workspace")
      .style.setProperty(
        "--altura-topbar",
        document.querySelector(".topbar").offsetHeight + "px",
      ),
  ).observe(document.querySelector(".topbar"));
  if (modulo.dados.estado) await receber(modulo.dados.estado);
  await navegar(location.hash.slice(1) || "geral");
  setInterval(async () => {
    try {
      diag = await api.get("/api/diagnostico");
    } catch {}
  }, 6000);
  setInterval(async () => {
    if (!estado?.imagem && $("imagem-cinza")) $("imagem-cinza").hidden = true;
    if (!$("ativar-cinza")?.checked || !estado?.imagem || cinzaOcupado) return;
    cinzaOcupado = true;
    const ep = estado.epoch,
      origem = identidade(estado);
    try {
      const r = await fetch("/api/central/quadro-cinza?epoch=" + ep);
      if (!r.ok) return;
      const blob = await r.blob();
      if (
        identidade(estado) !== origem ||
        !$("imagem-cinza") ||
        !$("ativar-cinza")?.checked
      )
        return;
      if (cinzaUrl) URL.revokeObjectURL(cinzaUrl);
      cinzaUrl = URL.createObjectURL(blob);
      $("imagem-cinza").src = cinzaUrl;
      $("imagem-cinza").hidden = false;
    } catch (e) {
      if (pagina === "visao")
        mensagem(
          "Diagnóstico de imagem temporariamente indisponível: " + e.message,
          true,
        );
    } finally {
      cinzaOcupado = false;
    }
  }, 1200);
} catch (e) {
  mensagem("Não foi possível iniciar a central: " + e.message, true);
}
