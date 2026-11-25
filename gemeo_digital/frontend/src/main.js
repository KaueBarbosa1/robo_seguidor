import * as THREE from "three";
import { Cena } from "./cena.js";
import { Modelo } from "./modelo.js";
import { Sensores } from "./sensores.js";
import { Dados } from "./dados.js";
import { angulosVisuais, fresco } from "./animacao.js";
import { $, rotulo, valor, metricas, funcoes } from "./interface.js";
import { verificar } from "./verificacao.js";
const erros = [];
function erro(e) {
  erros.push(String(e.message ?? e));
  erros.splice(0, Math.max(0, erros.length - 20));
  $("erro").hidden = false;
  $("erro").textContent = String(e.message ?? e);
}
window.addEventListener("error", (e) => erro(e.error ?? e.message));
window.addEventListener("unhandledrejection", (e) => erro(e.reason));
const inicioCarga = performance.now();
const dados = new Dados(erro);
const fonteId = (s) =>
  `${s.instancia ?? ""}:${s.epoch}:${s.dados.envelope?.sessao ?? ""}`;
let cena,
  modelo,
  sensores,
  config,
  selecionado = "carrinho_raiz",
  sessoes = [],
  estado,
  faseVisual = [0, 0],
  poseVisual = null,
  servo = 90,
  last = performance.now(),
  epoch = -1,
  imagemURL = null,
  fotoOcupada = false,
  ultimoFrame = null;
const acao = (fn) => async () => {
  try {
    await fn();
    $("erro").hidden = true;
  } catch (e) {
    erro(e);
  }
};
function selecionar(n) {
  document.querySelector(".right").scrollTop = 0;
  selecionado = n;
  modelo.selecionar(n);
  $("nome").textContent = rotulo(n);
  $("funcao").textContent =
    funcoes[n] ??
    (/roda|disco/.test(n)
      ? "Componente giratório. Pulsos medidos em magnitude; sentido inferido pelo comando."
      : "Componente do protótipo original. Estado específico disponível apenas quando instrumentado.");
  document
    .querySelectorAll("#componentes button")
    .forEach((b) => b.classList.toggle("active", b.dataset.nome === n));
  if (estado) metricas(n, estado);
}
async function carregarSessoes() {
  sessoes = await dados.get("/api/sessoes");
  for (const id of ["sessoes", "comparar"]) {
    const el = $(id);
    el.replaceChildren(
      new Option(
        id === "comparar" ? "Comparar trajetória…" : "Selecione uma sessão",
        "",
      ),
    );
    for (const s of sessoes)
      el.add(
        new Option(
          `${s.simulado ? "SIM" : "REAL"} · ${s.id.slice(0, 8)} · ${s.inicio_observado_utc}`,
          s.id,
        ),
      );
  }
}
function buscar(seg) {
  const s = sessoes.find((q) => q.id === $("sessoes").value);
  if (!s) return;
  return dados.post("/api/replay", {
    acao: "buscar",
    instante: new Date(
      Date.parse(s.inicio_observado_utc) + seg * 1000,
    ).toISOString(),
  });
}
function atualizar(s) {
  window.dispatchEvent(new CustomEvent("robo:estado", { detail: s }));
  if (s.dados.disponivel && $("erro").textContent === "Failed to fetch")
    $("erro").hidden = true;
  estado = s;
  $("conexao").textContent = s.status;
  $("sessao").textContent = s.dados.envelope?.sessao ?? "Sem sessão";
  $("natureza").textContent =
    s.modo === "simulado"
      ? "SIMULAÇÃO · PARÂMETROS SINTÉTICOS"
      : s.modo === "historico"
        ? "REPRODUÇÃO · SEM ATUAÇÃO FÍSICA"
        : "OBSERVAÇÃO · CALIBRAÇÃO PENDENTE";
  metricas(selecionado, s);
  const p = s.dados.pose;
  $("pose").textContent =
    p && p.validade !== "sem_calibracao"
      ? `X ${p.x_m.toFixed(3)} m · Y ${p.y_m.toFixed(3)} m · θ ${((p.orientacao_rad * 180) / Math.PI).toFixed(1)}° · percurso ${p.distancia_m.toFixed(3)} m (${p.natureza})`
      : "Sem calibração ou dados suficientes";
  cena.trajeto(s.dados.trajeto ?? []);
  $("eventos").textContent = s.eventos.length
    ? s.eventos
        .map((e) => `${e.timestamp}: ${JSON.stringify(e.detalhes)}`)
        .join("\n")
    : "Sem eventos registrados";
  if (fonteId(s) !== epoch) {
    if (s.modo === "historico" && !s.replay.posicao_utc) $("tempo").value = 0;
    faseVisual = [...(s.dados.angulos_rad ?? [0, 0])];
    poseVisual = s.dados.pose ? { ...s.dados.pose } : null;
    epoch = fonteId(s);
    ultimoFrame = null;
    if (imagemURL) URL.revokeObjectURL(imagemURL);
    imagemURL = null;
    $("imagem").hidden = true;
    $("sem-imagem").hidden = false;
    const comandoServo =
      s.dados.envelope?.dados.telemetria.sensores?.angulo_servo_graus;
    servo =
      (comandoServo?.estado === "atual" ? valor(comandoServo) : null) ?? 90;
  }
  const ss = sessoes.find((q) => q.id === s.replay.sessao);
  if (ss) {
    const inicio = Date.parse(ss.inicio_observado_utc),
      fim = Date.parse(
        ss.fim_observado_utc ??
          ss.ultimo_recebido_utc ??
          ss.inicio_observado_utc,
      );
    $("tempo").max = Math.max(0.01, (fim - inicio) / 1000);
    if (s.replay.posicao_utc) {
      $("tempo").value = (Date.parse(s.replay.posicao_utc) - inicio) / 1000;
      $("instante").textContent =
        s.replay.posicao_utc +
        (s.replay.pausado ? " · Pausado" : " · Reproduzindo");
    }
  }
  if (!s.dados.disponivel || !s.imagem) {
    $("imagem").hidden = true;
    $("sem-imagem").hidden = false;
    $("sem-imagem").textContent = "Imagem indisponível ou desatualizada";
  }
}
async function quadro() {
  if (fotoOcupada || !estado?.imagem || !estado.dados.disponivel) return;
  fotoOcupada = true;
  const e = estado.epoch;
  const origem = fonteId(estado);
  try {
    const r = await fetch(
      `/api/quadro?epoch=${e}&instancia=${estado.instancia ?? ""}`,
    );
    if (!r.ok) {
      $("imagem").hidden = true;
      $("sem-imagem").hidden = false;
      return;
    }
    const id = r.headers.get("X-Frame-Id");
    if (id === ultimoFrame) return;
    const blob = await r.blob();
    if (fonteId(estado) !== origem) return;
    const nova = URL.createObjectURL(blob);
    if (imagemURL) URL.revokeObjectURL(imagemURL);
    imagemURL = nova;
    ultimoFrame = id;
    $("imagem").src = nova;
    $("imagem").hidden = false;
    $("sem-imagem").hidden = true;
    $("camera-info").textContent =
      `Frame ${id} · ${blob.size} bytes · recebido pelo canal existente. FOV estimado; ROI distinta.`;
  } catch (e) {
    erro(e);
  } finally {
    fotoOcupada = false;
  }
}
try {
  config = await dados.iniciar((s) => {
    if (sensores) atualizar(s);
  });
  cena = new Cena($("cena"));
  modelo = new Modelo();
  await modelo.carregar(cena.cena, config.modelo);
  const testes = verificar(modelo);
  sensores = new Sensores(modelo, cena.cena);
  testes.push({
    nome: "Frustum acompanha câmera e sonar acompanha sensor",
    ok:
      sensores.fov.parent === modelo.obj.esp32_cam &&
      sensores.sonar.parent === modelo.obj.sensor_ultrassonico,
  });
  const cargaMs = performance.now() - inicioCarga;
  const ausentes = Object.entries(modelo.obj)
    .filter(([n, o]) => !o)
    .map(([n]) => n);
  if (ausentes.length) erro("Componentes ausentes: " + ausentes.join(", "));
  for (const n of Object.keys(modelo.obj)) {
    const b = document.createElement("button");
    b.disabled = !modelo.obj[n];
    b.textContent = rotulo(n);
    b.dataset.nome = n;
    b.onclick = () => selecionar(n);
    $("componentes").append(b);
  }
  for (const v of [
    "Perspectiva",
    "Superior",
    "Frontal",
    "Traseira",
    "Esquerda",
    "Direita",
    "Livre",
  ]) {
    const b = document.createElement("button");
    b.textContent = v;
    b.onclick = () =>
      cena.resetar(
        v,
        modelo.raiz
          .getWorldPosition(new THREE.Vector3())
          .add(new THREE.Vector3(0, 0.07, 0)),
      );
    $("vistas").append(b);
  }
  selecionar("carrinho_raiz");
  $("centralizar").onclick = () =>
    cena.focar(modelo.raiz, modelo.caixa(modelo.raiz));
  $("focar").onclick = () =>
    cena.focar(modelo.obj[selecionado], modelo.caixa(modelo.obj[selecionado]));
  const canvas = cena.renderer.domElement;
  let inicio;
  canvas.addEventListener(
    "pointerdown",
    (e) => (inicio = [e.clientX, e.clientY]),
  );
  canvas.addEventListener("pointerup", (e) => {
    if (!inicio || Math.hypot(e.clientX - inicio[0], e.clientY - inicio[1]) > 4)
      return;
    const r = canvas.getBoundingClientRect(),
      ray = new THREE.Raycaster();
    ray.setFromCamera(
      new THREE.Vector2(
        ((e.clientX - r.left) / r.width) * 2 - 1,
        (-(e.clientY - r.top) / r.height) * 2 + 1,
      ),
      cena.camera,
    );
    const hit = ray
      .intersectObject(modelo.gltf.scene, true)
      .find((h) => modelo.orig.has(h.object));
    if (hit) selecionar(modelo.identificar(hit.object));
  });
  $("acrilico").disabled = !modelo.obj.chassi_superior;
  $("acrilico").onchange = (e) => {
    if (modelo.obj.chassi_superior)
      modelo.obj.chassi_superior.visible = e.target.checked;
  };
  $("explodir").onchange = (e) => modelo.explodir(e.target.checked);
  $("fov").onchange = (e) => (sensores.fov.visible = e.target.checked);
  sensores.fov.visible = false;
  $("sonar").onchange = (e) => (sensores.sonar.visible = e.target.checked);
  $("trajeto").onchange = (e) => (cena.trilha.visible = e.target.checked);
  $("qualidade").onchange = (e) => {
    cena.renderer.setPixelRatio(Math.min(devicePixelRatio, +e.target.value));
    cena.renderer.shadowMap.enabled = +e.target.value > 1;
  };
  $("referencia").onclick = acao(() => dados.post("/api/referencia", {}));
  $("modo").onchange = acao(async () => {
    const m = $("modo").value;
    await dados.post("/api/modo", { modo: m });
    for (const [id, modo] of [
      ["sim", "simulado"],
      ["historico", "historico"],
      ["real", "real"],
    ])
      $(id).hidden = m !== modo;
    await carregarSessoes();
  });
  $("modo").querySelector("[value=real]").disabled = !config.real_configurado;
  const campos = [
    ["esq", "Roda esquerda · pulsos/s", -60, 60, 1],
    ["dir", "Roda direita · pulsos/s", -60, 60, 1],
    ["servo", "Servo comandado · °", 45, 135, 1],
    ["distancia", "Distância manual · cm", 2, 400, 1],
    ["cpu", "CPU simulada · %", 0, 100, 1],
    ["temperatura", "Temperatura · °C", 0, 100, 1],
    ["latencia", "Latência simulada · s", 0, 1, 0.05],
    ["obstaculo_x", "Obstáculo virtual · X (m)", -3, 3, 0.05],
    ["obstaculo_z", "Obstáculo virtual · Z (m)", -3, 3, 0.05],
    ["linha", "Linha detectada"],
    ["camera", "Câmera ativa"],
    ["falha", "Interromper telemetria"],
    ["motores", "Motores ativos"],
    ["geometria", "Distância por obstáculo virtual"],
  ];
  const inicial = (await dados.get("/api/estado")).simulacao;
  for (const [k, n, min, max, step] of campos) {
    const l = document.createElement("label"),
      i = document.createElement("input"),
      o = document.createElement("output");
    l.textContent = n;
    i.id = "sim-" + k;
    l.htmlFor = i.id;
    l.append(o, i);
    if (min != null) {
      i.type = "range";
      Object.assign(i, { min, max, step, value: inicial[k] });
      o.value = i.value;
    } else {
      i.type = "checkbox";
      i.checked = !!inicial[k];
    }
    i.onchange = acao(async () => {
      const v = i.type === "checkbox" ? i.checked : +i.value;
      o.value = i.type === "checkbox" ? "" : i.value;
      await dados.post("/api/simulacao", { [k]: v });
    });
    i.oninput = () => (o.value = i.value);
    $("controles").append(l);
  }
  await carregarSessoes();
  const habilitarReplay = (v) =>
    document
      .querySelectorAll("#historico button, #tempo, #velocidade")
      .forEach((el) => (el.disabled = !v));
  habilitarReplay(false);
  $("sessoes").onchange = acao(async () => {
    habilitarReplay(false);
    await dados.post("/api/sessao", { sessao: $("sessoes").value });
    habilitarReplay(true);
  });
  document
    .querySelectorAll("[data-replay]")
    .forEach(
      (b) =>
        (b.onclick = acao(() =>
          dados.post("/api/replay", { acao: b.dataset.replay }),
        )),
    );
  document
    .querySelectorAll("[data-salto]")
    .forEach(
      (b) =>
        (b.onclick = acao(() =>
          buscar(Math.max(0, +$("tempo").value + Number(b.dataset.salto))),
        )),
    );
  $("tempo").onchange = acao(() => buscar(+$("tempo").value));
  $("velocidade").onchange = acao(() =>
    dados.post("/api/replay", {
      acao: "velocidade",
      fator: +$("velocidade").value,
    }),
  );
  $("comparar").onchange = acao(async () => {
    if (!$("comparar").value) {
      cena.trajeto([], cena.comparacao);
      return;
    }
    const q = await dados.get("/api/trajeto?sessao=" + $("comparar").value);
    cena.trajeto(q.pontos, cena.comparacao);
    $("comparacao").textContent = q.natureza;
  });
  let seguir = true,
    ultimaPos = new THREE.Vector3();
  const eixos = new THREE.AxesHelper(0.12);
  eixos.visible = false;
  modelo.raiz.add(eixos);
  for (const [n, acao, checado] of [
    ["Seguir o carrinho", (v) => (seguir = v), true],
    ["Eixos técnicos locais", (v) => (eixos.visible = v), false],
    [
      "Rodas e motores",
      (v) =>
        [
          "roda_esquerda",
          "roda_direita",
          "motor_esquerdo",
          "motor_direito",
        ].forEach((n) => {
          if (modelo.obj[n]) modelo.obj[n].visible = v;
        }),
      true,
    ],
    [
      "Discos e sensores ópticos",
      (v) =>
        [
          "encoder_esquerdo",
          "encoder_direito",
          "disco_encoder_esquerdo",
          "disco_encoder_direito",
        ].forEach((n) => {
          if (modelo.obj[n]) modelo.obj[n].visible = v;
        }),
      true,
    ],
  ]) {
    const l = document.createElement("label"),
      i = document.createElement("input");
    i.type = "checkbox";
    i.checked = checado;
    i.onchange = () => acao(i.checked);
    l.append(i, n);
    $("componentes").before(l);
  }
  const calibrar = document.createElement("details");
  calibrar.innerHTML = "<summary>Calibração visual do servo</summary>";
  for (const [k, n, min, max] of [
    ["min", "Mínimo", 0, 180],
    ["max", "Máximo", 0, 180],
    ["centro", "Centro", 0, 180],
    ["offset", "Deslocamento", -90, 90],
  ]) {
    const l = document.createElement("label"),
      i = document.createElement("input");
    i.type = "number";
    i.min = min;
    i.max = max;
    i.value = config.servo[k];
    i.style.width = "65px";
    i.onchange = () => {
      const v = +i.value;
      if (Number.isFinite(v) && v >= min && v <= max) config.servo[k] = v;
    };
    l.append(n + " ", i);
    calibrar.append(l);
  }
  const li = document.createElement("label"),
    inv = document.createElement("input");
  inv.type = "checkbox";
  inv.onchange = () => (config.servo.inverter = inv.checked);
  li.append(inv, "Inverter sentido");
  calibrar.append(li);
  $("componentes").before(calibrar);
  const frames = [];
  let inicioFPS = performance.now(),
    contagem = 0;
  function render(agora) {
    const dt = Math.min(0.1, (agora - last) / 1000);
    last = agora;
    if (!cena.el.clientWidth || !cena.el.clientHeight || document.hidden) {
      requestAnimationFrame(render);
      return;
    }
    if (estado) {
      const valido = fresco(estado, agora);
      const ang = angulosVisuais(estado, agora),
        u = estado.dados.envelope?.dados.telemetria.sensores ?? {};
      const alvo = valor(u.angulo_servo_graus);
      if (valido) {
        const fator = 1 - Math.exp(-dt * 24);
        faseVisual = faseVisual.map((v, i) => v + (ang[i] - v) * fator);
        const p = estado.dados.pose;
        if (p) {
          if (!poseVisual) poseVisual = { ...p };
          for (const k of ["x_m", "y_m"])
            poseVisual[k] += (p[k] - poseVisual[k]) * fator;
          const delta = Math.atan2(
            Math.sin(p.orientacao_rad - poseVisual.orientacao_rad),
            Math.cos(p.orientacao_rad - poseVisual.orientacao_rad),
          );
          poseVisual.orientacao_rad += delta * fator;
          poseVisual.validade = p.validade;
        }
      }
      if (valido && u.angulo_servo_graus?.estado === "atual" && alvo != null)
        servo += (alvo - servo) * (1 - Math.exp(-dt * 16));
      modelo.animar(
        faseVisual,
        { ...config.servo, valor: servo },
        estado.dados.calibracao,
        poseVisual,
      );
      sensores.atualizar(
        estado,
        valor(u.distancia_cm),
        valido && u.distancia_cm?.estado === "atual",
        config.limites,
      );
      if (!valido)
        $("conexao").textContent = "Dados desatualizados · movimento congelado";
    }
    const atualPos = modelo.raiz.getWorldPosition(new THREE.Vector3());
    if (seguir) {
      const delta = atualPos.clone().sub(ultimaPos);
      if (ultimaPos.lengthSq() > 0) {
        cena.camera.position.add(delta);
        cena.controls.target.add(delta);
      }
    }
    ultimaPos.copy(atualPos);
    const t = performance.now();
    cena.render();
    frames.push(performance.now() - t);
    if (frames.length > 600) frames.shift();
    contagem++;
    if (agora - inicioFPS > 1000) {
      $("fps").textContent =
        `${Math.round((contagem * 1000) / (agora - inicioFPS))} FPS`;
      contagem = 0;
      inicioFPS = agora;
    }
    requestAnimationFrame(render);
  }
  requestAnimationFrame(render);
  setInterval(quadro, 200);
  setInterval(() => {
    const a = [...frames].sort((a, b) => a - b);
    dados
      .post("/api/diagnostico", {
        testes,
        erros,
        render: {
          viewport: {
            largura: cena.el.clientWidth,
            altura: cena.el.clientHeight,
            pixel_ratio: cena.renderer.getPixelRatio(),
          },
          carregamento_ms: cargaMs,
          amostras: a.length,
          media_render_cpu_ms: a.length
            ? a.reduce((x, y) => x + y, 0) / a.length
            : null,
          fps_texto: $("fps").textContent,
          memoria_js_bytes: performance.memory?.usedJSHeapSize ?? null,
          objetos: modelo.orig.size,
          mediana_ms: a[Math.floor(a.length * 0.5)] ?? null,
          p95_ms: a[Math.floor(a.length * 0.95)] ?? null,
          triangulos: cena.renderer.info.render.triangles,
          chamadas: cena.renderer.info.render.calls,
          geometrias: cena.renderer.info.memory.geometries,
          texturas: cena.renderer.info.memory.textures,
        },
        navegador: navigator.userAgent,
      })
      .catch(erro);
  }, 3000);
} catch (e) {
  erro(e);
}
export { dados, cena, modelo, sensores, config };
