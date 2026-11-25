import * as THREE from "three";
import { coordenadas } from "./animacao.js";
export function verificar(modelo) {
  const testes = [];
  const ok = (nome, v) => testes.push({ nome, ok: !!v });
  const obj = modelo.obj;
  if (Object.values(obj).some((o) => !o))
    return [
      {
        nome: "Componentes ausentes; funcionalidades correspondentes desabilitadas",
        ok: false,
      },
    ];
  ok(
    "Todos os componentes identificados por nome ou alias",
    Object.values(obj).every(Boolean),
  );
  ok(
    "Ultrassônico é filho do eixo do servo",
    obj.sensor_ultrassonico.parent === obj.servo_eixo,
  );
  const materiais = new Map();
  modelo.gltf.scene.traverse((o) => {
    for (const m of o.material
      ? Array.isArray(o.material)
        ? o.material
        : [o.material]
      : [])
      materiais.set(m, JSON.stringify(m.toJSON()));
  });
  const cal = { relacao_disco_roda: 1 };
  const qd = obj.roda_direita.quaternion.clone(),
    qe = obj.roda_esquerda.quaternion.clone(),
    qs = obj.encoder_esquerdo.quaternion.clone(),
    qb = obj.servo_base.quaternion.clone();
  modelo.animar([1, 0], null, cal, null);
  ok(
    "Roda esquerda gira independentemente",
    qe.angleTo(obj.roda_esquerda.quaternion) > 0.9 &&
      qd.angleTo(obj.roda_direita.quaternion) < 1e-7,
  );
  ok(
    "Disco gira e sensor óptico fica fixo",
    obj.disco_encoder_esquerdo.quaternion.angleTo(
      modelo.orig.get(obj.disco_encoder_esquerdo).q,
    ) > 0.9 && qs.angleTo(obj.encoder_esquerdo.quaternion) < 1e-7,
  );
  modelo.animar([0, 1], null, cal, null);
  ok(
    "Roda direita gira independentemente",
    qe.angleTo(obj.roda_esquerda.quaternion) < 1e-7 &&
      qd.angleTo(obj.roda_direita.quaternion) > 0.9,
  );
  modelo.animar(
    [0, 0],
    { min: 45, max: 135, centro: 90, inverter: false, offset: 0, valor: 90 },
    cal,
    null,
  );
  const antes = obj.sensor_ultrassonico.getWorldQuaternion(
    new THREE.Quaternion(),
  );
  modelo.animar(
    [0, 0],
    { min: 45, max: 135, centro: 90, inverter: false, offset: 0, valor: 120 },
    cal,
    null,
  );
  ok(
    "Servo move o sensor sem girar a base",
    antes.angleTo(
      obj.sensor_ultrassonico.getWorldQuaternion(new THREE.Quaternion()),
    ) > 0.5 && qb.angleTo(obj.servo_base.quaternion) < 1e-7,
  );
  modelo.explodir(true);
  modelo.explodir(false);
  ok(
    "Vista explodida restaura posições",
    modelo.raiz.children.every(
      (o) => o.position.distanceTo(modelo.orig.get(o).p) < 1e-10,
    ),
  );
  ok(
    "Materiais originais preservados",
    [...materiais].every(([m, v]) => JSON.stringify(m.toJSON()) === v),
  );
  ok(
    "Conversão de coordenadas",
    coordenadas(1, 2).distanceTo(new THREE.Vector3(-2, 0, -1)) < 1e-10,
  );
  const caixa = new THREE.Box3().setFromObject(modelo.raiz);
  ok(
    "Escala métrica finita",
    caixa.getSize(new THREE.Vector3()).length() < 2 &&
      caixa.getSize(new THREE.Vector3()).length() > 0.1,
  );
  modelo.animar(
    [0, 0],
    { min: 45, max: 135, centro: 90, inverter: false, offset: 0, valor: 90 },
    cal,
    null,
  );
  const roda = modelo.obj.roda_esquerda;
  const centro = modelo.caixa(roda).getCenter(new THREE.Vector3());
  const ray = new THREE.Raycaster(
    centro.clone().add(new THREE.Vector3(-0.2, 0, 0)),
    new THREE.Vector3(1, 0, 0),
  );
  ok(
    "Raycaster seleciona a roda por ancestral nomeado",
    ray
      .intersectObject(roda, true)
      .some((h) => modelo.identificar(h.object) === "roda_esquerda"),
  );
  ok(
    "Transformações iniciais restauradas",
    [...modelo.orig].every(
      ([o, b]) =>
        o.position.distanceTo(b.p) < 1e-8 &&
        o.quaternion
          .toArray()
          .every((v, i) => Math.abs(v - b.q.toArray()[i]) < 1e-8) &&
        o.scale.distanceTo(b.s) < 1e-8,
    ),
  );
  return testes;
}
