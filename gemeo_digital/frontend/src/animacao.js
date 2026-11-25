import * as THREE from "three";
export const ALIASES = {
  chassi_inferior: "acrilico_0.035_674",
  chassi_superior: "acrilico_0.105_673",
};
export function girar(obj, base, eixo, angulo) {
  obj.quaternion
    .copy(base)
    .multiply(new THREE.Quaternion().setFromAxisAngle(eixo, -angulo));
}
export function coordenadas(x, y) {
  return new THREE.Vector3(-y, 0, -x);
}
export function angulosVisuais(estado, agora) {
  const d = estado?.dados;
  if (!d?.disponivel) return d?.angulos_rad ?? [0, 0];
  const fator =
    estado.modo === "historico"
      ? estado.replay.pausado
        ? 0
        : estado.replay.velocidade
      : 1;
  const dt = Math.min(
    Math.max(0, ((agora - estado.recebido) / 1000) * fator),
    Math.max(0, (d.envelope.validade_s ?? 0.5) - d.idade_s),
  );
  return d.angulos_rad.map((a, i) => a + d.omega_rad_s[i] * dt);
}
export function fresco(s, agora) {
  if (!s?.dados.disponivel) return false;
  const k =
    s.modo === "historico" ? (s.replay.pausado ? 0 : s.replay.velocidade) : 1;
  return (
    s.dados.idade_s + ((agora - s.recebido) / 1000) * k <=
    (s.dados.envelope.validade_s ?? 0.5)
  );
}
