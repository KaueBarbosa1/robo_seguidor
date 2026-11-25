import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { ALIASES, girar, coordenadas } from "./animacao.js";
export class Modelo {
  async carregar(cena, diag) {
    this.diag = diag;
    this.gltf = await new GLTFLoader().loadAsync("/modelo.glb");
    cena.add(this.gltf.scene);
    this.obj = {};
    this.orig = new Map();
    this.gltf.scene.traverse((o) => {
      this.orig.set(o, {
        p: o.position.clone(),
        q: o.quaternion.clone(),
        s: o.scale.clone(),
      });
      if (o.isMesh) {
        o.castShadow = true;
        o.receiveShadow = true;
      }
    });
    for (const nome of Object.keys(diag.componentes)) {
      this.obj[nome] = null;
      const original = ALIASES[nome] ?? nome;
      this.gltf.scene.traverse((o) => {
        if (o.userData.name === original || o.name === original)
          this.obj[nome] = o;
      });
    }
    this.raiz = this.obj.carrinho_raiz;
    if (!this.raiz)
      throw Error("O GLB não contém carrinho_raiz; confira o modelo original.");
    this.explodido = false;
    this.selecionado = "carrinho_raiz";
    this.contorno = new THREE.Box3Helper(new THREE.Box3(), 0xd3ed86);
    this.contorno.visible = false;
    cena.add(this.contorno);
  }
  animar(angulos, servo, cal, pose) {
    ["esquerdo", "direito"].forEach((lado, i) => {
      for (const nome of [
        "roda_" + (i ? "direita" : "esquerda"),
        "disco_encoder_" + lado,
      ]) {
        const o = this.obj[nome];
        if (!o || !this.diag.eixos[nome]) continue;
        const disco = nome.startsWith("disco");
        const eixo = new THREE.Vector3(
          ...this.diag.eixos[nome].eixo_local_geometrico,
        ).normalize();
        girar(
          o,
          this.orig.get(o).q,
          eixo,
          angulos[i] * (disco ? (cal.relacao_disco_roda ?? 0) : 1),
        );
      }
    });
    const o = this.obj.servo_eixo;
    if (o && servo != null) {
      const a =
        (Math.max(servo.min, Math.min(servo.max, servo.valor)) - servo.centro) *
          (servo.inverter ? -1 : 1) +
        servo.offset;
      girar(
        o,
        this.orig.get(o).q,
        new THREE.Vector3(0, 1, 0),
        (-a * Math.PI) / 180,
      );
    }
    const b = this.orig.get(this.raiz);
    this.raiz.position.copy(b.p);
    this.raiz.quaternion.copy(b.q);
    if (pose && pose.validade !== "sem_calibracao") {
      this.raiz.position.add(coordenadas(pose.x_m, pose.y_m));
      this.raiz.quaternion.multiply(
        new THREE.Quaternion().setFromAxisAngle(
          new THREE.Vector3(0, 1, 0),
          pose.orientacao_rad,
        ),
      );
    }
    this.gltf.scene.updateMatrixWorld(true);
    if (this.contorno.visible)
      this.contorno.box.copy(this.caixa(this.obj[this.selecionado]));
  }
  explodir(ativo) {
    this.explodido = ativo;
    for (const o of this.raiz.children) {
      const b = this.orig.get(o);
      if (!b) continue;
      o.position.copy(b.p);
      if (ativo) {
        const dir = b.p.clone();
        dir.y = Math.max(0.05, dir.y);
        o.position.add(dir.multiplyScalar(0.65));
      }
    }
  }
  caixa(obj) {
    obj.updateWorldMatrix(true, true);
    const b = new THREE.Box3();
    obj.traverse((o) => {
      if (this.orig.has(o) && o.isMesh) {
        if (!o.geometry.boundingBox) o.geometry.computeBoundingBox();
        b.union(o.geometry.boundingBox.clone().applyMatrix4(o.matrixWorld));
      }
    });
    return b;
  }
  selecionar(nome) {
    this.selecionado = nome;
    this.contorno.box.copy(this.caixa(this.obj[nome] ?? this.raiz));
    this.contorno.visible = nome !== "carrinho_raiz";
  }
  identificar(o) {
    while (o) {
      const achado = Object.entries(this.obj).find(
        ([n, v]) => v === o && n !== "carrinho_raiz",
      );
      if (achado) return achado[0];
      o = o.parent;
    }
    return "carrinho_raiz";
  }
}
