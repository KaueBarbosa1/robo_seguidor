import test from "node:test";
import assert from "node:assert/strict";
import {
  BufferTemporal,
  estatistica,
  enriquecer,
  extrair,
  esc,
} from "../frontend/src/nucleo.js";
function s(seq, epoch = 1, disponivel = true) {
  const motores = {
    pps_esq: { valor: 4, estado: "atual" },
    pps_dir: { valor: 6, estado: "atual" },
  };
  return {
    epoch,
    modo: "simulado",
    dados: {
      disponivel,
      calibracao: {},
      envelope: {
        sessao: "teste",
        sequencia: seq,
        timestamp: new Date(seq * 100).toISOString(),
        dados: { telemetria: { motores } },
      },
    },
  };
}
test("buffer limitado, deduplicação e troca de fonte", () => {
  const b = new BufferTemporal(20);
  for (let i = 0; i < 50; i++) b.adicionar(s(i));
  assert.equal(b.itens.length, 20);
  assert.equal(b.adicionar(s(49)), false);
  b.adicionar(s(0, 2));
  assert.equal(b.itens.length, 1);
});
test("reinício e nova sessão não reutilizam o buffer da origem anterior", () => {
  const b = new BufferTemporal();
  b.adicionar(s(1));
  const novo = s(2);
  novo.dados.envelope.sessao = "nova-sessao";
  b.adicionar(novo);
  assert.equal(b.itens.length, 1);
  const reiniciado = s(3);
  reiniciado.instancia = "novo-processo";
  b.adicionar(reiniciado);
  assert.equal(b.itens.length, 1);
});
test("valores vencidos não viram zero ou velocidade calibrada", () => {
  const r = extrair(s(1, 1, false));
  assert.equal(r.pps_esq, null);
  assert.equal(r.v_esq, null);
});
test("estatística mantém NULL ausente e calcula quantis", () => {
  const r = estatistica([null, 1, 2, 3, 4, NaN]);
  assert.equal(r.n, 4);
  assert.equal(r.media, 2.5);
  assert.equal(r.q1, 1.75);
  assert.equal(r.q3, 3.25);
  assert.equal(estatistica([null]).n, 0);
});
test("aceleração somente entre amostras válidas próximas", () => {
  assert.equal(
    enriquecer(
      { t: 1.1, pps_esq: 5, pps_dir: 8 },
      { t: 1, pps_esq: 4, pps_dir: 6 },
    ).acel_esq.toFixed(1),
    "10.0",
  );
  assert.equal(
    enriquecer(
      { t: 3, pps_esq: 5, pps_dir: 8 },
      { t: 1, pps_esq: 4, pps_dir: 6 },
    ).acel_esq,
    null,
  );
});
test("metadados escapados antes de inserir em HTML", () => {
  assert.equal(
    esc('<img src=x onerror="alert(1)">'),
    "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;",
  );
});

import { Dados } from "../../gemeo_digital/frontend/src/dados.js";
test("reinício do backend renova a credencial local sem outra fonte de telemetria", async () => {
  const erros = [];
  const d = new Dados((e) => erros.push(e));
  let configuracoes = 0,
    consultas = 0;
  d.periodo = 1;
  d.get = async (url) =>
    url === "/api/config"
      ? { token: "token-" + ++configuracoes }
      : {
          instancia: ++consultas === 1 ? "A" : "B",
          dados: { disponivel: true },
        };
  let concluir;
  const recebido = new Promise((ok) => (concluir = ok));
  await d.iniciar((s) => {
    if (s.instancia === "B") concluir();
  });
  try {
    await Promise.race([
      recebido,
      new Promise((_, err) =>
        setTimeout(() => err(Error("Prazo do teste")), 700),
      ),
    ]);
    assert.equal(d.token, "token-2");
    assert.equal(configuracoes, 2);
    assert.equal(erros.length, 0);
  } finally {
    clearInterval(d.timer);
  }
});
