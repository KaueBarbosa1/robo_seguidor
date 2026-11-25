export const MAX_PONTOS = 7200;
export const identidade = (s) =>
  `${s.instancia ?? ""}:${s.epoch}:${s.dados.envelope?.sessao ?? ""}`;
export const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
export const num = (v, unidade = "", casas = null) =>
  typeof v === "number" && Number.isFinite(v)
    ? `${v.toLocaleString("pt-BR", { maximumFractionDigits: casas ?? (v !== 0 && Math.abs(v) < 0.01 ? 6 : 2), minimumFractionDigits: casas ?? (v !== 0 && Math.abs(v) < 0.01 ? 6 : 2) })}${unidade ? " " + unidade : ""}`
    : "Indisponível";
export const texto = (v) =>
  v == null
    ? "Indisponível"
    : typeof v === "boolean"
      ? v
        ? "Sim"
        : "Não"
      : String(v);
export const campo = (c) =>
  c && typeof c === "object" && c.estado === "atual" ? c.valor : null;
export function extrair(s) {
  const d = s.dados,
    e = d.envelope ?? {},
    p = e.dados ?? {},
    t = p.telemetria ?? {},
    m = t.motores ?? {},
    u = t.sensores ?? {},
    v = t.visao ?? {},
    cal = d.calibracao ?? {},
    ok = d.disponivel;
  const val = (c) => (ok ? campo(c) : null);
  const lado = (l, i) => {
    const omega =
      ok && (cal.simulada || cal.confirmada) ? d.omega_rad_s?.[i] : null;
    return omega == null
      ? null
      : (omega * (cal["diametro_" + l + "_m"] ?? NaN)) / 2;
  };
  const rede = s.central?.rede?.canais?.telemetria ?? {},
    sr = p.comunicacao ?? {},
    rtt = rede.rtt_s?.media ?? sr.rtt_s?.media;
  return {
    t:
      Date.parse(
        s.modo === "historico"
          ? (s.replay.posicao_utc ?? e.timestamp)
          : (e.recepcao_utc ?? e.timestamp),
      ) / 1000,
    seq: e.sequencia,
    pps_esq: val(m.pps_esq),
    pps_dir: val(m.pps_dir),
    pwm_esq: val(m.pwm_esq),
    pwm_dir: val(m.pwm_dir),
    ticks_esq: val(m.ticks_esq),
    ticks_dir: val(m.ticks_dir),
    distancia: val(u.distancia_cm),
    servo: val(u.angulo_servo_graus),
    erro: val(v.erro),
    confianca: val(v.confianca_heuristica),
    linha: val(v.linha_visivel),
    camera: ok ? v.camera_ok : null,
    cpu: ok ? p.sistema?.valores?.cpu_total_pct : null,
    ram: ok ? p.sistema?.valores?.ram_pct : null,
    temperatura: ok ? p.sistema?.valores?.temperatura_c : null,
    cpu_pc: s.central?.pc?.valores?.cpu_total_pct,
    ram_pc: s.central?.pc?.valores?.ram_pct,
    fps: ok ? t.camera?.fps : null,
    rtt: ok && rtt != null ? rtt * 1000 : null,
    jitter:
      ok && rede.jitter_rtt_s?.media != null
        ? rede.jitter_rtt_s.media * 1000
        : null,
    lacunas: rede.contadores?.lacunas ?? null,
    descartes: rede.contadores?.descartes_fila_local ?? null,
    kib_s: ok ? rede.kb_s_medio : null,
    rede_hz: ok ? rede.telemetria_hz_medio : null,
    fps_rede: ok ? s.central?.rede?.canais?.imagens?.fps_medio : null,
    reconexoes: rede.contadores?.reconexoes ?? null,
    v_esq: lado("esq", 0),
    v_dir: lado("dir", 1),
    x: ok ? d.pose?.x_m : null,
    y: ok ? d.pose?.y_m : null,
    referencia_esq: null,
    referencia_dir: null,
    erro_pi: null,
    natureza:
      s.modo === "simulado"
        ? "Simulado"
        : s.modo === "historico"
          ? "Histórico"
          : "Observado",
  };
}
export class BufferTemporal {
  constructor(limite = MAX_PONTOS) {
    this.limite = limite;
    this.itens = [];
    this.chave = null;
    this.epoch = null;
  }
  adicionar(s) {
    if (identidade(s) !== this.epoch) {
      this.epoch = identidade(s);
      this.itens = [];
      this.chave = null;
    }
    const e = s.dados.envelope;
    if (!e) return false;
    const chave = e.sessao + ":" + e.sequencia;
    if (chave === this.chave) return false;
    this.chave = chave;
    const r = extrair(s);
    if (!Number.isFinite(r.t)) return false;
    enriquecer(r, this.itens.at(-1));
    this.itens.push(r);
    if (this.itens.length > this.limite)
      this.itens.splice(0, this.itens.length - this.limite);
    return true;
  }
  substituir(rows) {
    this.itens = rows.slice(-this.limite);
  }
  janela(t, segundos) {
    return this.itens.filter((r) => r.t >= t - segundos && r.t <= t + 0.05);
  }
}
export function enriquecer(r, anterior) {
  r.diferenca =
    r.pps_esq != null && r.pps_dir != null ? r.pps_dir - r.pps_esq : null;
  const dt = anterior ? r.t - anterior.t : 0;
  for (const l of ["esq", "dir"])
    r["acel_" + l] =
      dt > 0 &&
      dt <= 0.5 &&
      r["pps_" + l] != null &&
      anterior["pps_" + l] != null
        ? (r["pps_" + l] - anterior["pps_" + l]) / dt
        : null;
  return r;
}
export function estatistica(valores) {
  const a = valores
    .filter((v) => typeof v === "number" && Number.isFinite(v))
    .sort((a, b) => a - b);
  if (!a.length) return { n: 0 };
  const media = a.reduce((a, b) => a + b, 0) / a.length;
  const p = (q) => {
    const i = (a.length - 1) * q,
      l = Math.floor(i);
    return a[l] + (a[Math.ceil(i)] - a[l]) * (i - l);
  };
  return {
    n: a.length,
    media,
    minimo: a[0],
    maximo: a.at(-1),
    mediana: p(0.5),
    q1: p(0.25),
    q3: p(0.75),
    p95: p(0.95),
    desvio_padrao: Math.sqrt(
      a.reduce((s, x) => s + (x - media) ** 2, 0) / a.length,
    ),
  };
}
export function historicoParaSerie(r) {
  return {
    t: r.t,
    pps_esq: r.pps_esq,
    pps_dir: r.pps_dir,
    pwm_esq: r.pwm_informado_esq,
    pwm_dir: r.pwm_informado_dir,
    distancia: r.distancia_cm,
    erro: r.erro_normalizado,
    servo: r.servo_comandado_graus,
    cpu: r.cpu_servidor_pct,
    temperatura: r.temperatura_servidor_c,
    rtt: r.rtt_servidor_s != null ? r.rtt_servidor_s * 1000 : null,
    fps: r.fps_captura,
  };
}
