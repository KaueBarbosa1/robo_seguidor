import { esc, num, estatistica } from "./nucleo.js";
const CORES = ["#c9e88b", "#78b7df", "#b4a0de", "#efd086"];
const ns = "http://www.w3.org/2000/svg";
export function blocoGrafico(id, titulo, unidade, series) {
  return `<div class="panel"><h2>${esc(titulo)}</h2><svg class="chart" id="${id}" role="img" aria-label="${esc(titulo)}" viewBox="0 0 700 230"></svg><div class="legend">${series.map((s, i) => `<span style="--c:${CORES[i % 4]}">${esc(s[1])}</span>`).join("")}</div><div class="chart-stats" id="${id}-stats">Aguardando amostras válidas · ${esc(unidade)}</div><div class="chart-tools"><small>${esc(unidade)} · horário local no eixo X</small><div><button data-export="${id}" data-formato="svg">SVG</button> <button data-export="${id}" data-formato="png">PNG</button></div></div></div>`;
}
export class Grafico {
  constructor(svg, series, unidade, eixoX = "tempo") {
    this.svg = svg;
    this.series = series;
    this.unidade = unidade;
    this.eixoX = eixoX;
    this.svg.innerHTML =
      '<g class="eixos"/><g class="curvas"/><text class="sem-dados" x="350" y="115" text-anchor="middle" fill="#9ab0be" font-size="12"/>';
    this.paths = series.map((s, i) => {
      const p = document.createElementNS(ns, "path");
      p.setAttribute("fill", "none");
      p.setAttribute("stroke", CORES[i % 4]);
      p.setAttribute("stroke-width", "1.8");
      svg.querySelector(".curvas").append(p);
      return p;
    });
  }
  atualizar(rows) {
    const vals = rows
      .flatMap((r) => this.series.map(([k]) => r[k]))
      .filter((v) => typeof v === "number" && Number.isFinite(v));
    this.svg.querySelector(".sem-dados").textContent = vals.length
      ? ""
      : "Sem valores válidos disponíveis";
    if (!rows.length || !vals.length) {
      this.paths.forEach((p) => p.setAttribute("d", ""));
      return;
    }
    const min = Math.min(...vals),
      max = Math.max(...vals),
      margem = Math.max(
        (max - min) * 0.15,
        Math.abs(max) * 0.03,
        max === 0 && min === 0 ? 0.5 : 0.000001,
      ),
      a = min >= 0 ? Math.max(0, min - margem) : min - margem,
      b = max + margem;
    const casas = Math.min(6, Math.max(1, 1 - Math.floor(Math.log10(b - a))));
    const t0 = rows[0].t,
      t1 = Math.max(t0 + 1, rows.at(-1).t),
      X = (t) => 55 + ((t - t0) / (t1 - t0)) * 625,
      Y = (v) => 195 - ((v - a) / (b - a)) * 175;
    let axes = "";
    for (let i = 0; i < 5; i++) {
      const y = 20 + i * 43.75;
      axes += `<line x1="55" x2="680" y1="${y}" y2="${y}" stroke="#526a7730"/><text x="48" y="${y + 4}" text-anchor="end" fill="#93a9b7" font-size="10">${esc(num(b - ((b - a) * i) / 4, "", casas))}</text>`;
    }
    for (let i = 0; i < 4; i++) {
      const t = t0 + ((t1 - t0) * i) / 3;
      axes += `<text x="${X(t)}" y="218" text-anchor="middle" fill="#93a9b7" font-size="10">${esc(this.eixoX === "passo" ? String(Math.round(t)) : new Date(t * 1000).toLocaleTimeString("pt-BR"))}</text>`;
    }
    this.svg.querySelector(".eixos").innerHTML = axes;
    this.series.forEach(([k], i) => {
      let path = "",
        ativo = false,
        ant = null;
      const salto = Math.max(1.2, ((t1 - t0) / Math.max(rows.length, 1)) * 3);
      for (const r of rows) {
        const v = r[k];
        if (typeof v !== "number" || !Number.isFinite(v)) {
          ativo = false;
          continue;
        }
        if (ant != null && r.t - ant > salto) ativo = false;
        path += (ativo ? "L" : "M") + X(r.t).toFixed(2) + "," + Y(v).toFixed(2);
        ativo = true;
        ant = r.t;
      }
      this.paths[i].setAttribute("d", path);
    });
    const stats = this.series.map(([k, n]) => {
      const s = estatistica(rows.map((r) => r[k]));
      return `${n}: n=${s.n} · média ${num(s.media, this.unidade)} · mediana ${num(s.mediana)} · mín ${num(s.minimo)} · máx ${num(s.maximo)} · DP ${num(s.desvio_padrao)} · p95 ${num(s.p95)}`;
    });
    const out = document.getElementById(this.svg.id + "-stats");
    if (out) out.textContent = stats.join(" | ");
  }
}
export function radar(svg, rows, agora, limite) {
  const max = 400,
    centro = [200, 220],
    r = 185;
  let g = `<rect width="400" height="250" fill="#101f29"/><path d="M15 220 A185 185 0 0 1 385 220" fill="none" stroke="#385466"/>`;
  for (const cm of [100, 200, 300, 400])
    g += `<path d="M${200 - (r * cm) / max} 220 A${(r * cm) / max} ${(r * cm) / max} 0 0 1 ${200 + (r * cm) / max} 220" fill="none" stroke="#385466"/><text x="${202 + (r * cm) / max}" y="232" fill="#93a9b7" font-size="10">${cm} cm</text>`;
  g += `<path d="M${200 - (r * limite) / max} 220 A${(r * limite) / max} ${(r * limite) / max} 0 0 1 ${200 + (r * limite) / max} 220" fill="none" stroke="#ef9c77" stroke-width="2"/>`;
  for (const p of rows
    .filter((r) => r.distancia != null && r.servo != null)
    .slice(-80)) {
    const a = ((p.servo - 90) * Math.PI) / 180,
      dist = (Math.min(max, p.distancia) / max) * r,
      idade = Math.max(0, agora - p.t);
    g += `<circle cx="${200 - Math.sin(a) * dist}" cy="${220 - Math.cos(a) * dist}" r="3" fill="${idade > 0.5 ? "#71818d" : "#c9e88b"}" opacity="${idade > 10 ? 0.25 : idade > 0.5 ? 0.5 : 1}"><title>${esc(p.natureza)} · ${num(p.distancia, "cm")} · ${num(p.servo, "°")} comandados · ${new Date(p.t * 1000).toISOString()} · idade ${num(idade, "s")}</title></circle>`;
  }
  svg.setAttribute("viewBox", "0 0 400 250");
  svg.innerHTML = g;
}
export function trajeto(svg, pontos, comparacao = [], zoom = 1, eventos = []) {
  const all = [...pontos, ...comparacao].filter((p) =>
    p.every(Number.isFinite),
  );
  if (!all.length) {
    svg.innerHTML =
      '<text x="20" y="35" fill="#93a9b7">Trajetória indisponível sem calibração/dados válidos.</text>';
    return;
  }
  const xs = all.map((p) => p[0]),
    ys = all.map((p) => p[1]),
    x0 = Math.min(...xs),
    x1 = Math.max(...xs),
    y0 = Math.min(...ys),
    y1 = Math.max(...ys),
    span = Math.max(0.2, x1 - x0, y1 - y0) / zoom;
  const X = (x) => 350 + ((x - (x0 + x1) / 2) / span) * 350,
    Y = (y) => 130 - ((y - (y0 + y1) / 2) / span) * 180;
  const path = (ps) =>
    ps.map((p, i) => (i ? "L" : "M") + X(p[0]) + "," + Y(p[1])).join("");
  svg.setAttribute("viewBox", "0 0 700 260");
  svg.innerHTML = `<text x="15" y="25" fill="#93a9b7" font-size="11">X à frente · Y à esquerda · m estimados</text><path d="${path(comparacao)}" stroke="#78b7df" fill="none" stroke-width="2"/><path d="${path(pontos)}" stroke="#c9e88b" fill="none" stroke-width="2"/><circle cx="${X(pontos[0][0])}" cy="${Y(pontos[0][1])}" r="4" fill="#78b7df"/><circle cx="${X(pontos.at(-1)[0])}" cy="${Y(pontos.at(-1)[1])}" r="5" fill="#c9e88b"/><text x="15" y="248" fill="#93a9b7" font-size="10">Estimativa relativa; azul: sessão comparada. Eventos sem posição sincronizada não são projetados no mapa.</text>`;
}
export function boxplot(svg, itens) {
  const rows = itens.filter((i) => i.stats.n);
  if (!rows.length) {
    svg.innerHTML =
      '<text x="20" y="40" fill="#93a9b7">Sem amostras válidas para distribuição.</text>';
    return;
  }
  const min = Math.min(...rows.map((i) => i.stats.minimo)),
    max = Math.max(...rows.map((i) => i.stats.maximo)),
    X = (v) => 150 + ((v - min) / Math.max(0.001, max - min)) * 500;
  svg.setAttribute(
    "viewBox",
    `0 0 700 ${Math.max(140, rows.length * 55 + 35)}`,
  );
  svg.innerHTML = rows
    .map((r, i) => {
      const s = r.stats,
        y = 35 + i * 55;
      return `<text x="10" y="${y + 5}" fill="#b8cbd8" font-size="10">${esc(r.nome.length > 21 ? r.nome.slice(0, 20) + "…" : r.nome)}<title>${esc(r.nome)}</title></text><line x1="${X(s.minimo)}" x2="${X(s.maximo)}" y1="${y}" y2="${y}" stroke="#78b7df"/><rect x="${X(s.q1)}" y="${y - 12}" width="${Math.max(1, X(s.q3) - X(s.q1))}" height="24" fill="#78b7df40" stroke="#78b7df"/><line x1="${X(s.mediana)}" x2="${X(s.mediana)}" y1="${y - 13}" y2="${y + 13}" stroke="#c9e88b"/><text x="${X(s.mediana)}" y="${y + 27}" text-anchor="middle" fill="#93a9b7" font-size="10">mediana ${num(s.mediana, "s")} · n=${s.n}</text>`;
    })
    .join("");
}
export async function exportarGrafico(svg, formato) {
  const clone = svg.cloneNode(true);
  clone.setAttribute("xmlns", ns);
  const xml = new XMLSerializer().serializeToString(clone);
  let blob = new Blob([xml], { type: "image/svg+xml" });
  if (formato === "png") {
    const url = URL.createObjectURL(blob),
      img = new Image();
    await new Promise((ok, err) => {
      img.onload = ok;
      img.onerror = err;
      img.src = url;
    });
    const c = document.createElement("canvas");
    c.width = 1400;
    c.height = 520;
    const ctx = c.getContext("2d");
    ctx.fillStyle = "#101f29";
    ctx.fillRect(0, 0, c.width, c.height);
    ctx.drawImage(img, 0, 0, c.width, c.height);
    URL.revokeObjectURL(url);
    blob = await new Promise((ok) => c.toBlob(ok, "image/png"));
  }
  const url = URL.createObjectURL(blob),
    a = document.createElement("a");
  a.href = url;
  a.download = `robo_${svg.id}.${formato}`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function barras(svg, itens, unidade = "s") {
  const rows = itens.filter(
    (r) => typeof r.valor === "number" && Number.isFinite(r.valor),
  );
  if (!rows.length) {
    svg.innerHTML =
      '<text x="20" y="40" fill="#93a9b7">Sem valores válidos para esta comparação.</text>';
    return;
  }
  const max = Math.max(...rows.map((r) => r.valor), 0.000001);
  svg.setAttribute(
    "viewBox",
    `0 0 700 ${Math.max(150, rows.length * 48 + 30)}`,
  );
  svg.innerHTML = rows
    .map(
      (r, i) =>
        `<text x="10" y="${35 + i * 48}" fill="#b9cbd6" font-size="10">${esc(r.nome.length > 21 ? r.nome.slice(0, 20) + "…" : r.nome)}<title>${esc(r.nome)}</title></text><rect x="150" y="${18 + i * 48}" width="${(r.valor / max) * 420}" height="24" fill="#78b7df80"/><text x="${160 + (r.valor / max) * 420}" y="${35 + i * 48}" fill="#c9e88b" font-size="10">${esc(num(r.valor, unidade, unidade === "amostras" ? 0 : 6))}</text>`,
    )
    .join("");
}
