import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
export class Cena {
  constructor(el) {
    this.el = el;
    this.cena = new THREE.Scene();
    this.cena.background = new THREE.Color("#101b23");
    this.camera = new THREE.PerspectiveCamera(42, 1, 0.005, 100);
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFShadowMap;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    el.appendChild(this.renderer.domElement);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.minDistance = 0.12;
    this.controls.maxDistance = 12;
    this.cena.add(new THREE.HemisphereLight(0xe5f3ff, 0x66715e, 2.4));
    const l = new THREE.DirectionalLight(0xfff5e8, 3.2);
    l.position.set(0.5, 1, 0.4);
    l.castShadow = true;
    l.shadow.mapSize.set(1024, 1024);
    Object.assign(l.shadow.camera, {
      left: -2,
      right: 2,
      top: 2,
      bottom: -2,
      near: 0.01,
      far: 5,
    });
    l.shadow.bias = -0.0001;
    this.cena.add(l);
    const fill = new THREE.DirectionalLight(0xb7d8f7, 1.5);
    fill.position.set(-0.5, 0.5, -0.6);
    this.cena.add(fill);
    const piso = new THREE.Mesh(
      new THREE.PlaneGeometry(40, 40),
      new THREE.MeshStandardMaterial({ color: 0x17262f, roughness: 1 }),
    );
    piso.rotation.x = -Math.PI / 2;
    piso.position.y = -0.005;
    piso.receiveShadow = true;
    this.cena.add(piso);
    this.cena.add(new THREE.GridHelper(12, 120, 0x536675, 0x2e424e));
    this.trilha = this.linha(0xd3ed86);
    this.comparacao = this.linha(0x6ea4c9);
    this.resetar();
    new ResizeObserver(() => this.redimensionar()).observe(el);
    this.redimensionar();
  }
  linha(cor) {
    const g = new THREE.BufferGeometry();
    g.setAttribute(
      "position",
      new THREE.BufferAttribute(new Float32Array(6000), 3),
    );
    g.setDrawRange(0, 0);
    const l = new THREE.Line(g, new THREE.LineBasicMaterial({ color: cor }));
    l.frustumCulled = false;
    this.cena.add(l);
    return l;
  }
  trajeto(pontos, l = this.trilha) {
    const p = l.geometry.attributes.position;
    const n = Math.min(2000, pontos.length);
    for (let i = 0; i < n; i++)
      p.setXYZ(i, -pontos[i][1], 0.003, -pontos[i][0]);
    p.needsUpdate = true;
    l.geometry.setDrawRange(0, n);
  }
  redimensionar() {
    const { clientWidth: w, clientHeight: h } = this.el;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / Math.max(h, 1);
    this.camera.fov =
      (2 *
        Math.atan(
          Math.tan((42 * Math.PI) / 360) / Math.min(1, this.camera.aspect),
        ) *
        180) /
      Math.PI;
    this.camera.updateProjectionMatrix();
  }
  resetar(
    v = "Perspectiva",
    centro = new THREE.Vector3(0, 0.1, 0),
    escala = 1,
  ) {
    const pos = {
      Perspectiva: [0.42, 0.3, 0.46],
      Superior: [0, 0.65, 0.001],
      Frontal: [0, 0.16, -0.65],
      Traseira: [0, 0.16, 0.65],
      Esquerda: [-0.65, 0.16, 0],
      Direita: [0.65, 0.16, 0],
      Livre: [0.42, 0.3, 0.46],
    }[v];
    this.controls.target.copy(centro);
    this.camera.position
      .copy(centro)
      .add(new THREE.Vector3(...pos).multiplyScalar(escala));
    this.controls.update();
  }
  focar(o, caixa) {
    const b = caixa ?? new THREE.Box3().setFromObject(o);
    this.resetar(
      "Perspectiva",
      b.getCenter(new THREE.Vector3()),
      Math.max(0.22, b.getSize(new THREE.Vector3()).length() / 0.5),
    );
  }
  render() {
    this.controls.update();
    this.renderer.render(this.cena, this.camera);
  }
}
