import { esc, num, estatistica } from "./nucleo.js";

export function htmlControle() {
  return `<div id="operacao-resumo"></div>
  <div class="grid2"><section class="panel"><h2>Autoridade de movimento</h2>
  <p class="note">Habilite explicitamente. Mantenha a tecla ou o botão pressionado para mover. Soltar solicita velocidade zero; perder foco libera a autorização.</p>
  <div class="toolbar"><button id="op-habilitar">Habilitar controle</button><button id="op-liberar">Liberar controle</button></div>
  <label>Velocidade solicitada · pulsos/s<input id="op-velocidade" type="range" min="1" max="4" step="1" value="2" aria-label="Velocidade do controle remoto"><output id="op-vel-valor">2</output></label>
  <div class="controle-direcional"><button data-movimento="frente" aria-label="Manter para avançar">↑ W</button><button data-movimento="esquerda" aria-label="Manter para virar à esquerda">← A</button><button id="op-parar">Parar · espaço</button><button data-movimento="direita" aria-label="Manter para virar à direita">D →</button><button data-movimento="re" aria-label="Manter para recuar">S ↓</button></div>
  <button id="op-emergencia" class="danger">Solicitar emergência por software</button><button id="op-rearmar">Solicitar liberação da emergência</button>
  <p id="op-presenca" class="note" role="status">Controle não habilitado.</p><p class="note">Emergência por software: não substitui um dispositivo físico. A confirmação indica os dados recebidos, não uma medição independente de frenagem.</p></section>
  <section class="panel"><h2>Processamento e operação</h2><form id="op-modo-form"><label>Modo de processamento<select id="op-modo"><option value="embarcado">Embarcado</option><option value="distribuido">Distribuído</option></select></label><button>Solicitar mudança com o carrinho parado</button></form>
  <button id="op-siga">Habilitar seguimento autônomo</button><p class="note">Trocar o modo mantém o carrinho parado e invalida pedidos anteriores. O seguimento exige outra habilitação explícita e percepção válida.</p>
  <h3>Algoritmo compartilhado</h3><form id="op-pipeline"><label>Algoritmo<select id="op-algoritmo"><option value="opencv">OpenCV existente</option><option value="cnn-fotos">CNN própria · diagnóstico offline</option><option value="cnn-rl">Pacote CNN/RL existente · diagnóstico</option></select></label><label>Manifesto local (opcional para CNN de fotos)<input id="op-manifesto" placeholder="Caminho do experimento.json ou pacote.json"></label><button>Carregar algoritmo com o carrinho parado</button></form>
  <p class="note">Pesos ausentes ou incompatíveis são recusados. A CNN de fotos não tem visibilidade supervisionada e não é habilitada para navegação.</p></section></div>
  <section class="panel"><h2>Ensaios sem hardware</h2><form id="op-imagem-form"><label>Imagem local de teste<input id="op-imagem" placeholder="Caminho absoluto de uma imagem coletada"></label><button>Usar imagem no simulador parado</button></form><p class="note">Preserva resolução e pré-processamento do modelo. Use um campo vazio para voltar à pista sintética. Disponível somente em simulação.</p>
  <div class="toolbar"><label>Atraso de inferência simulado · s<input id="op-atraso" type="number" min="0" max="2" step="0.05" value="0"></label><label><input id="op-pausar-inferencia" type="checkbox"> Interromper serviço de inferência</label><label><input id="op-falha-inferencia" type="checkbox"> Falha de inferência</label><button id="op-aplicar-falhas">Aplicar falhas simuladas</button></div></section>
  <section class="panel"><h2>Resultados e métricas do ciclo</h2><div id="op-metricas"></div><details><summary>Detalhes do contrato recebido</summary><pre id="op-detalhes"></pre></details></section>`;
}

const $ = (id) => document.getElementById(id);
const legenda = (v) =>
  ({
    embarcado: "Embarcado",
    distribuido: "Distribuído",
    parado: "Parado",
    manual: "Manual",
    autonomo: "Autônomo",
    nenhuma: "Nenhuma",
    pc_manual: "PC · manual",
    autonomo_embarcado: "Autônomo embarcado",
    autonomo_distribuido: "Autônomo distribuído",
    seguranca: "Segurança",
    confirmada_pelos_dados: "Confirmada pelos dados recebidos",
    aceita: "Solicitada e aceita",
    falha_na_confirmacao: "Sem confirmação no prazo",
    mudanca_de_modo: "Modo alterado; aguardando habilitação",
    pedido_operador: "Parada solicitada pelo operador",
    controle_liberado: "Controle liberado",
    deadman_expirado: "Presença do operador expirada",
    resultado_expirado: "Resultado expirado",
    emergencia_liberada: "Emergência liberada; parado",
  })[v] ?? String(v ?? "Indisponível").replaceAll("_", " ");
export const editavel = (alvo) =>
  !!alvo?.closest?.('input,textarea,select,[contenteditable="true"]');
export const direcaoTecla = (tecla) =>
  ({
    w: "frente",
    ArrowUp: "frente",
    s: "re",
    ArrowDown: "re",
    a: "esquerda",
    ArrowLeft: "esquerda",
    d: "direita",
    ArrowRight: "direita",
  })[tecla.length === 1 ? tecla.toLowerCase() : tecla];

export function resumoOperacao(s) {
  const d = s.dados?.envelope?.dados?.telemetria?.distribuido;
  const canal = s.central?.operacao_rede;
  const r = s.modo === "historico" ? d : (canal?.remoto ?? d);
  if (!r)
    return `<p class="note">Canal da etapa 6 indisponível nesta origem. Nenhuma autorização de movimento.</p>`;
  const local =
    r.processamento === "distribuido"
      ? "Computador"
      : "Raspberry / host virtual";
  const fluxo =
    r.processamento === "distribuido"
      ? [
          "ESP32-CAM",
          "Raspberry",
          "Computador",
          "Raspberry",
          "Arduino",
          "Motores",
        ]
      : ["ESP32-CAM", "Raspberry", "Arduino", "Motores"];
  return `<div class="op-status"><b>${s.modo === "historico" ? "HISTÓRICO" : r.simulado ? "SIMULAÇÃO" : "DADOS REAIS"} · ${esc(legenda(r.processamento))} · ${esc(legenda(r.operacao))}</b><span>Autoridade: ${esc(legenda(r.fonte_controle))}</span><span>Algoritmo: ${esc(r.algoritmo)} · inferência: ${esc(local)}</span><span>Canal: ${esc(canal?.status ?? "reprodução local")}</span><span>Resultado: ${num(r.idade_resultado_s, "s")} de idade</span><span>Parada: ${esc(legenda(r.parada))}</span><span>${r.emergencia ? "EMERGÊNCIA RETIDA" : "Sem emergência retida"} · ${esc(legenda(r.motivo ?? r.fase))}</span></div><ol class="fluxo-operacao" aria-label="Fluxo de processamento">${fluxo.map((x) => `<li class="${(x === "Raspberry" && r.processamento === "embarcado") || (x === "Computador" && r.processamento === "distribuido") ? "processador-ativo" : ""}">${esc(x)}</li>`).join("")}</ol><p class="note">${r.simulado ? "Raspberry, Arduino e pista são virtuais; o algoritmo executa de verdade no PC." : "Atuação real exige aprovação explícita nas duas pontas; padrão bloqueado."} O fluxo indica a rota configurada; o estado do canal informa sua disponibilidade.</p>`;
}

export class OperacaoUI {
  constructor(post, mensagem) {
    this.post = post;
    this.mensagem = mensagem;
    this.operador = crypto.randomUUID();
    this.habilitado = false;
    this.direcao = "parar";
    this.ocupado = false;
    this.foco = true;
    this.tecla = null;
    this.timer = setInterval(() => this.renovar(), 100);
    window.addEventListener("blur", () => {
      this.foco = false;
      this.liberar();
    });
    window.addEventListener("focus", () => {
      this.foco = true;
    });
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) this.liberar();
    });
    window.addEventListener("pagehide", () => this.liberar());
    window.addEventListener("keyup", (e) => {
      if (
        direcaoTecla(e.key) &&
        direcaoTecla(this.tecla ?? "") === direcaoTecla(e.key)
      ) {
        this.tecla = null;
        this.direcao = "parar";
        this.renovar();
      }
    });
    window.addEventListener("keydown", (e) => {
      if (!this.habilitado || !this.naPagina || editavel(e.target) || e.repeat)
        return;
      if (e.code === "Space") {
        e.preventDefault();
        this.acao("parar");
        return;
      }
      const d = direcaoTecla(e.key);
      if (d) {
        e.preventDefault();
        this.tecla = e.key;
        this.direcao = d;
        this.renovar();
      }
    });
    window.addEventListener("pointerup", () => {
      if (this.direcao !== "parar") {
        this.direcao = "parar";
        this.renovar();
      }
    });
    window.addEventListener("pointercancel", () => this.liberar());
  }
  async enviar(d) {
    if (!this.estado) throw Error("Aguardando origem válida");
    return this.post("operacao", {
      ...d,
      operador: this.operador,
      instancia: this.estado.instancia,
      epoch: this.estado.epoch,
    });
  }
  async acao(acao, extras = {}) {
    if (["parar", "emergencia", "liberar"].includes(acao)) {
      this.habilitado = false;
      this.direcao = "parar";
    }
    try {
      if (acao === "habilitar") this.ocupado = true;
      const r = await this.enviar({ acao, ...extras });
      if (acao === "habilitar") {
        this.habilitado = true;
        this.armadoEm = performance.now();
        this.direcao = "parar";
      }
      if (["parar", "emergencia", "liberar"].includes(acao)) {
        this.habilitado = false;
        this.direcao = "parar";
      }
      this.mensagem(
        "Solicitação aceita. Estado confirmado conforme os dados recebidos.",
      );
      return r;
    } catch (e) {
      this.habilitado = false;
      this.direcao = "parar";
      this.mensagem(e.message, true);
    } finally {
      this.ocupado = false;
    }
  }
  async renovar() {
    if (
      !this.habilitado ||
      this.ocupado ||
      !this.naPagina ||
      !this.foco ||
      document.hidden
    )
      return;
    this.ocupado = true;
    try {
      await this.enviar({
        acao: "movimento",
        direcao: this.direcao,
        velocidade_pps: Number($("op-velocidade")?.value ?? 2),
      });
    } catch (e) {
      const aindaHabilitado = this.habilitado;
      this.habilitado = false;
      this.direcao = "parar";
      if (aindaHabilitado) this.mensagem(e.message, true);
    } finally {
      this.ocupado = false;
    }
  }
  liberar() {
    if (this.habilitado) {
      this.habilitado = false;
      this.direcao = "parar";
      this.enviar({ acao: "liberar" }).catch(() => {});
    }
  }
  montar(pagina) {
    if (this.naPagina && pagina !== "controle") this.liberar();
    this.naPagina = pagina === "controle";
    if (!this.naPagina) return;
    const atual = this.estado?.central?.operacao_rede?.remoto;
    if (atual) {
      $("op-modo").value = atual.processamento;
      $("op-algoritmo").value = atual.algoritmo;
    }
    for (const [id, acao] of [
      ["op-habilitar", "habilitar"],
      ["op-liberar", "liberar"],
      ["op-parar", "parar"],
      ["op-emergencia", "emergencia"],
      ["op-rearmar", "liberar_emergencia"],
      ["op-siga", "siga"],
    ])
      $(id).onclick = () => this.acao(acao);
    document.querySelectorAll("[data-movimento]").forEach((b) => {
      b.onpointerdown = (e) => {
        if (!this.habilitado) return;
        e.preventDefault();
        b.setPointerCapture(e.pointerId);
        this.direcao = b.dataset.movimento;
        this.renovar();
      };
      b.onlostpointercapture = () => {
        this.direcao = "parar";
        this.renovar();
      };
    });
    $("op-velocidade").oninput = (e) => {
      $("op-vel-valor").value = e.target.value;
    };
    $("op-modo-form").onsubmit = (e) => {
      e.preventDefault();
      this.acao("modo", { modo: $("op-modo").value });
    };
    $("op-pipeline").onsubmit = (e) => {
      e.preventDefault();
      this.acao("configurar_pipeline", {
        algoritmo: $("op-algoritmo").value,
        manifesto: $("op-manifesto").value || null,
      });
    };
    $("op-imagem-form").onsubmit = (e) => {
      e.preventDefault();
      this.acao("imagem_teste", { caminho: $("op-imagem").value });
    };
    $("op-aplicar-falhas").onclick = () =>
      this.acao("falhas_servico", {
        atraso_s: Number($("op-atraso").value),
        pausar: $("op-pausar-inferencia").checked,
        falhar: $("op-falha-inferencia").checked,
      });
  }
  atualizar(s) {
    const identidade = `${s.instancia}:${s.epoch}`;
    if (this.origem && identidade !== this.origem) {
      this.habilitado = false;
      this.direcao = "parar";
    }
    this.origem = identidade;
    this.estado = s;
    const canal = s.central?.operacao_rede,
      r = canal?.remoto ?? s.dados?.envelope?.dados?.telemetria?.distribuido;
    const disponivel =
      !!s.central?.etapa6 &&
      s.modo !== "historico" &&
      canal?.status === "conectado" &&
      !!canal.permissoes?.includes("controle");
    if (
      this.habilitado &&
      (!disponivel ||
        r?.emergencia ||
        (!r?.autorizacao_ativa && performance.now() - this.armadoEm > 500))
    ) {
      this.habilitado = false;
      this.direcao = "parar";
    }
    if ($("operacao-resumo"))
      $("operacao-resumo").innerHTML = resumoOperacao(s);
    if (!this.naPagina) return;
    document
      .querySelectorAll(
        "#op-modo-form button,#op-pipeline button,#op-habilitar,#op-siga,#op-emergencia,#op-rearmar,#op-parar,#op-liberar",
      )
      .forEach((b) => (b.disabled = !disponivel));
    document
      .querySelectorAll("[data-movimento]")
      .forEach(
        (b) =>
          (b.disabled = !disponivel || !this.habilitado || !!r?.emergencia),
      );
    $("op-habilitar").disabled =
      !disponivel || this.habilitado || !!r?.emergencia;
    $("op-presenca").textContent = this.habilitado
      ? `Autorização ativa nesta aba · presença renovada · pedido: ${this.direcao}`
      : "Controle não habilitado nesta aba. Nenhum movimento autorizado.";
    const sim = s.modo === "simulado";
    $("op-aplicar-falhas").disabled = !disponivel || !sim;
    $("op-imagem-form").querySelector("button").disabled = !disponivel || !sim;
    const est = estatistica(r?.latencias_s ?? []),
      p = canal?.ultimo_resultado ?? r?.ultimo_resultado;
    $("op-metricas").innerHTML =
      `<dl class="kv"><dt>Versão do modelo</dt><dd>${esc(r?.versao_modelo ?? "Indisponível")}</dd><dt>Frame</dt><dd>${esc(r?.frame_id ?? "Indisponível")}</dd><dt>Posição / erro lateral</dt><dd>${num(p?.posicao)} / ${num(p?.erro)}</dd><dt>Inferência</dt><dd>${num(p?.inferencia_s != null ? p.inferencia_s * 1000 : null, "ms")}</dd><dt>Ciclo Pi → PC → Pi · média / p95</dt><dd>${num(est.media != null ? est.media * 1000 : null, "ms")} / ${num(est.p95 != null ? est.p95 * 1000 : null, "ms")}</dd><dt>Resultados aceitos / rejeitados</dt><dd>${r?.contadores?.resultados_aceitos ?? 0} / ${r?.contadores?.resultados_rejeitados ?? 0}</dd><dt>Frames processados no PC</dt><dd>${canal?.contadores?.frames_processados ?? 0}</dd><dt>Filas de frames / resultados / comandos</dt><dd>${canal?.fila_frames ?? "—"} / ${canal?.fila_resultados ?? "—"} / ${canal?.fila_comandos ?? "—"}</dd><dt>Diagnóstico do serviço</dt><dd>${esc(canal?.erro ?? "Sem erro informado")}</dd></dl>`;
    $("op-detalhes").textContent = JSON.stringify(
      { canal, estado: r },
      null,
      2,
    );
    const ciclo = canal?.estatisticas_ciclo_s;
    if (ciclo)
      $("op-metricas").insertAdjacentHTML(
        "beforeend",
        `<p class="note">Ciclo completo, últimas ${ciclo.n} amostras: mín ${num(ciclo.minimo, "s")} · mediana ${num(ciclo.mediana, "s")} · máx ${num(ciclo.maximo, "s")} · DP ${num(ciclo.desvio_padrao, "s")} · p99 ${num(ciclo.p99, "s")} · jitter absoluto médio ${num(ciclo.jitter_medio, "s")}. p99 exige 100 amostras. Inferência efetiva média desde o início: ${num(canal.frequencia_efetiva_hz, "Hz")}.</p>`,
      );
  }
}
