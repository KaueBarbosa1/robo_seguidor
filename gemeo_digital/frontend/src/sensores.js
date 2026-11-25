import * as THREE from "three";
// Helpers novos; materiais e geometria do GLB ficam intactos.
export class Sensores {
  constructor(modelo, cena) {
    this.modelo = modelo;
    this.cena = cena;
    this.fov = this.feixe(modelo.obj.esp32_cam, 0.6, 60, 4 / 3, 0x79bbed);
    this.sonar = this.feixe(modelo.obj.sensor_ultrassonico, 1, 15, 1, 0xbfe77a);
    this.obstaculo = new THREE.Mesh(
      new THREE.BoxGeometry(0.12, 0.2, 0.12),
      new THREE.MeshStandardMaterial({
        color: 0xe3a569,
        transparent: true,
        opacity: 0.6,
      }),
    );
    cena.add(this.obstaculo);
    this.pulsos = ["encoder_esquerdo", "encoder_direito"].map((n) => {
      if (!modelo.obj[n]) return null;
      const o = modelo.obj[n],
        g = new THREE.Mesh(
          new THREE.SphereGeometry(0.003, 8, 6),
          new THREE.MeshBasicMaterial({ color: 0x6c8791 }),
        );
      const centro = new THREE.Box3()
        .setFromObject(o)
        .getCenter(new THREE.Vector3());
      g.position.copy(o.worldToLocal(centro));
      o.add(g);
      return g;
    });
  }
  feixe(pai, comprimento, angulo, aspecto, cor, origemFixa = null) {
    if (!pai) return new THREE.Group();
    pai.updateWorldMatrix(true, true);
    const b = new THREE.Box3().setFromObject(pai),
      p = b.getCenter(new THREE.Vector3());
    p.z = b.min.z;
    const origem = origemFixa ?? pai.worldToLocal(p),
      a = Math.tan((angulo * Math.PI) / 360) * comprimento,
      l = a * aspecto;
    // A câmera e o ultrassônico olham para −Y local neste GLB, após conversão do Blender.
    const pontos = [
      [0, 0, 0],
      [-l, -comprimento, -a],
      [l, -comprimento, -a],
      [l, -comprimento, a],
      [-l, -comprimento, a],
    ];
    const vertices = [];
    for (const [i, j, k] of [
      [0, 1, 2],
      [0, 2, 3],
      [0, 3, 4],
      [0, 4, 1],
      [1, 4, 3],
      [1, 3, 2],
    ])
      for (const n of [i, j, k]) vertices.push(...pontos[n]);
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
    g.computeVertexNormals();
    const mesh = new THREE.Mesh(
      g,
      new THREE.MeshBasicMaterial({
        color: cor,
        transparent: true,
        opacity: 0.09,
        side: THREE.DoubleSide,
        depthWrite: false,
      }),
    );
    mesh.position.copy(origem);
    const borda = new THREE.LineSegments(
      new THREE.EdgesGeometry(g),
      new THREE.LineBasicMaterial({
        color: cor,
        transparent: true,
        opacity: 0.55,
      }),
    );
    mesh.add(borda);
    pai.add(mesh);
    return mesh;
  }
  atualizar(s, distancia, valido, limites) {
    this.sonar.scale.setScalar(
      Math.max(0.02, Math.min(4, (distancia ?? 100) / 100)),
    );
    const cor = !valido
      ? 0x6a7b88
      : distancia == null
        ? 0x8d7bba
        : distancia < limites.parada_cm
          ? 0xf07872
          : distancia < limites.liberacao_cm
            ? 0xeac675
            : 0xbfe77a;
    if (this.sonar.isMesh) {
      this.sonar.material.color.setHex(cor);
      this.sonar.children[0].material.color.setHex(cor);
    }
    this.obstaculo.visible = s.modo === "simulado";
    if (this.obstaculo.visible)
      this.obstaculo.position.set(
        s.simulacao.obstaculo_x,
        0.1,
        s.simulacao.obstaculo_z,
      );
    const m = s.dados.envelope?.dados.telemetria.motores ?? {};
    this.pulsos.forEach((o, i) =>
      o?.material.color.setHex(
        valido && m["pps_" + (i ? "dir" : "esq")]?.valor > 0
          ? 0xd3ed86
          : 0x647581,
      ),
    );
  }
  configurarFov(angulo) {
    if (this.anguloFov === angulo) return;
    this.anguloFov = angulo;
    const antigo = this.fov,
      pai = antigo.parent;
    if (!pai) return;
    const pos = antigo.position.clone(),
      visivel = antigo.visible;
    pai.remove(antigo);
    antigo.traverse((o) => {
      o.geometry?.dispose();
      o.material?.dispose();
    });
    this.fov = this.feixe(pai, 0.6, angulo, 4 / 3, 0x79bbed, pos);
    this.fov.visible = visivel;
  }
}
