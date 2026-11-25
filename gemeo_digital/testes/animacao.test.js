import test from "node:test";
import assert from "node:assert/strict";
import * as THREE from "../frontend/node_modules/three/build/three.module.js";
import {
  girar,
  coordenadas,
  angulosVisuais,
  fresco,
} from "../frontend/src/animacao.js";
test("quaternion preserva orientação e permite ida e volta sem acumular erro", () => {
  const o = new THREE.Object3D(),
    base = new THREE.Quaternion(0.5, 0.5, -0.5, 0.5);
  o.quaternion.copy(base);
  girar(o, base, new THREE.Vector3(0, 1, 0), 1);
  assert.ok(o.quaternion.angleTo(base) > 0.99);
  girar(o, base, new THREE.Vector3(0, 1, 0), 0);
  assert.ok(o.quaternion.angleTo(base) < 1e-7);
});
test("odometria para Three: frente −Z e esquerda −X", () => {
  assert.deepEqual(coordenadas(1, 2).toArray(), [-2, 0, -1]);
});
const estado = () => ({
  recebido: 1000,
  modo: "simulado",
  dados: {
    disponivel: true,
    idade_s: 0.1,
    envelope: { validade_s: 0.5 },
    angulos_rad: [0, 1],
    omega_rad_s: [2, -2],
  },
});
test("extrapolação limitada pela validade, independente do FPS", () => {
  const s = estado();
  assert.deepEqual(angulosVisuais(s, 1100), [0.2, 0.8]);
  assert.deepEqual(angulosVisuais(s, 3000), [0.8, 0.19999999999999996]);
  assert.equal(fresco(s, 1600), false);
});
test("replay pausado não gira e velocidade respeita relógio virtual", () => {
  const s = estado();
  s.modo = "historico";
  s.replay = { pausado: true, velocidade: 2 };
  assert.deepEqual(angulosVisuais(s, 3000), [0, 1]);
  assert.equal(fresco(s, 3000), true);
  s.replay.pausado = false;
  assert.deepEqual(angulosVisuais(s, 1100), [0.4, 0.6]);
});
test("desconexão congela fase recebida", () => {
  const s = estado();
  s.dados.disponivel = false;
  assert.deepEqual(angulosVisuais(s, 4000), [0, 1]);
  assert.equal(fresco(s, 1001), false);
});
