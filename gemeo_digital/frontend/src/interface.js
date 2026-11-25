export const $ = (id) => document.getElementById(id);
export const rotulo = (n) =>
  n
    .replaceAll("_", " ")
    .replace("esp32 cam", "ESP32-CAM")
    .replace("raspberry pi", "Raspberry Pi")
    .replace("arduino uno", "Arduino Uno")
    .replace("ultrassonico", "ultrassônico")
    .replace("ponte h", "ponte H")
    .replace("regulador tensao", "regulador de tensão")
    .replace("case baterias", "suporte de baterias")
    .replace("carrinho raiz", "Carrinho completo");
export const valor = (c) =>
  c && typeof c === "object" && "valor" in c ? c.valor : c;
const numero = (v, sufixo = "") =>
  typeof v === "number" ? `${v.toFixed(2)}${sufixo}` : "Indisponível";
const texto = (v) =>
  v == null
    ? "Indisponível"
    : typeof v === "boolean"
      ? v
        ? "Sim"
        : "Não"
      : typeof v === "number"
        ? numero(v)
        : String(v);
export function metricas(nome, s) {
  const t = s.dados.envelope?.dados.telemetria ?? {},
    m = t.motores ?? {},
    u = t.sensores ?? {},
    v = t.visao ?? {},
    cam = t.camera ?? {},
    sys = s.dados.envelope?.dados.sistema?.valores ?? {};
  const fresco = s.dados.disponivel;
  if (!fresco) {
    $("metricas").replaceChildren();
    const p = document.createElement("p");
    p.textContent =
      "Dados indisponíveis ou desatualizados. Último estado visual congelado.";
    $("metricas").append(p);
    return;
  }
  let pares = [["Validade", "Dados atuais"]];
  const campo = (n, c) =>
    pares.push([
      n,
      c?.estado === "atual" && fresco
        ? texto(valor(c))
        : (c?.estado ?? "indisponível"),
    ]);
  if (nome === "raspberry_pi")
    pares.push(
      ["CPU", numero(sys.cpu_total_pct, " %")],
      ["RAM", numero(sys.ram_pct, " %")],
      ["Temperatura", numero(sys.temperatura_c, " °C")],
      ["Frequência", numero(sys.frequencia_mhz, " MHz")],
      ["Processamento", t.ia?.local ?? "Indisponível"],
    );
  if (/roda|motor|encoder|ponte_h/.test(nome)) {
    for (const lado of nome.endsWith("esquerda") || nome.endsWith("esquerdo")
      ? ["esq"]
      : nome.endsWith("direita") || nome.endsWith("direito")
        ? ["dir"]
        : ["esq", "dir"]) {
      campo(`Pulsos/s · ${lado}`, m["pps_" + lado]);
      campo(`PWM informado · ${lado}`, m["pwm_" + lado]);
      const p = valor(m["pwm_" + lado]);
      pares.push([
        `Sentido comandado · ${lado}`,
        p == null ? "Indisponível" : p > 0 ? "Frente" : p < 0 ? "Ré" : "Parado",
      ]);
      const i = lado === "esq" ? 0 : 1,
        cal = s.dados.calibracao,
        diam = cal["diametro_" + lado + "_m"];
      pares.push([
        `Velocidade estimada · ${lado}`,
        diam && s.dados.omega_rad_s && cal.simulada
          ? numero((s.dados.omega_rad_s[i] * diam) / 2, " m/s")
          : "Sem calibração confirmada",
      ]);
    }
    pares.push(
      ["PWM aplicado fisicamente", "Sem retorno de medição"],
      ["Sentido medido", "Não disponível: encoder de canal único"],
    );
  }
  if (/servo|ultrassonico/.test(nome)) {
    campo("Distância · cm", u.distancia_cm);
    campo("Servo · graus comandados", u.angulo_servo_graus);
    campo("Obstáculo confirmado", u.obstaculo_confirmado);
    pares.push(
      ["Idade da leitura", numero(u.distancia_cm?.idade_s, " s")],
      ["Posição física do servo", "Sem retorno de posição"],
    );
  }
  if (nome === "esp32_cam") {
    pares.push(
      ["FPS", numero(cam.fps)],
      [
        "Resolução",
        s.imagem
          ? `${$("imagem").naturalWidth || "—"} × ${$("imagem").naturalHeight || "—"}`
          : "Indisponível",
      ],
      ["Câmera conectada", texto(v.camera_ok)],
      ["Frame", texto(v.frame_id)],
      ["Idade da telemetria", numero(s.dados.idade_s, " s")],
      ["Idade do frame", numero(s.imagem?.idade_visualizacao_s, " s")],
      ["Recebimento do frame", texto(s.imagem?.recepcao_utc)],
      ["Coordenadas de linha", "Não fornecidas; sem sobreposição inventada"],
    );
    campo("Linha detectada", v.linha_visivel);
  }
  if (pares.length === 1)
    pares.push(
      ["Estado específico", "Não instrumentado"],
      ["Corrente / tensão", "Sem sensores disponíveis"],
    );
  $("metricas").replaceChildren(
    ...pares.flatMap(([k, v]) => {
      const a = document.createElement("dt"),
        b = document.createElement("dd");
      a.textContent = k;
      b.textContent = v;
      return [a, b];
    }),
  );
}
export const funcoes = {
  carrinho_raiz:
    "Conjunto do protótipo. A posição é uma estimativa por odometria, sujeita a deslizamento e erros acumulados.",
  raspberry_pi:
    "Processamento e comunicação embarcados. A renderização 3D acontece apenas no computador.",
  esp32_cam:
    "Captura de imagens. O visualizador reutiliza o canal de imagem existente.",
  servo_eixo:
    "Eixo móvel do servo; o ultrassônico acompanha sua hierarquia. Ângulo comandado, sem medição de posição.",
  servo_base: "Corpo fixo do servo.",
  sensor_ultrassonico:
    "Estimativa de distância na direção comandada. O feixe é ilustrativo e não constitui um mapa 3D.",
  ponte_h:
    "Acionamento dos motores. Não existe medição de corrente ou confirmação física do PWM.",
  encoder_esquerdo: "Sensor óptico fixo; conta pulsos, sem medir o sentido.",
  encoder_direito: "Sensor óptico fixo; conta pulsos, sem medir o sentido.",
};
