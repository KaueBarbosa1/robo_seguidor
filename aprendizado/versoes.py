"""Registro de versões da CNN: nunca se sobrescreve um modelo bom.

    modelos/v0001/pesos.npz + meta.json     cada versão é imutável depois de gravada
    campeao.json                             {"campeao": "v0003", "anteriores": ["v0001", "v0002"]}

Estados de uma versão: candidato -> campeao -> arquivado (substituída) | revertido (piorou e foi desfeita)
                       candidato -> descartado (não passou nas verificações)
Escritas são atômicas (arquivo temporário + troca): uma queda de energia não deixa meia versão.
O hash dos pesos é conferido ao carregar; se o campeão estiver corrompido, volta sozinho ao anterior.
"""
import json
import logging
import shutil
import time
from pathlib import Path

from aprendizado.cnn import RedeLinha

log = logging.getLogger("versoes")


def _escrever_json(caminho: Path, dados: dict) -> None:
    tmp = caminho.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, indent=1, default=float), encoding="utf-8")
    tmp.replace(caminho)


class RegistroModelos:
    def __init__(self, base: Path):
        self.base = Path(base)
        self.dir = self.base / "modelos"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.arq_campeao = self.base / "campeao.json"

    # ---------------------------------------------------------------- estado
    def _estado(self) -> dict:
        if self.arq_campeao.exists():
            try:
                return json.loads(self.arq_campeao.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                log.error("campeao.json corrompido; usando o histórico das versões")
        return {"campeao": None, "anteriores": []}

    def _gravar_estado(self, e: dict) -> None:
        _escrever_json(self.arq_campeao, e)

    def ids(self) -> list[str]:
        return sorted(p.name for p in self.dir.glob("v[0-9][0-9][0-9][0-9]") if p.is_dir())

    def meta(self, vid: str) -> dict:
        return json.loads((self.dir / vid / "meta.json").read_text(encoding="utf-8"))

    def _evento(self, vid: str, status: str | None, texto: str) -> None:
        m = self.meta(vid)
        if status:
            m["status"] = status
        m.setdefault("eventos", []).append({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "evento": texto})
        _escrever_json(self.dir / vid / "meta.json", m)

    # ---------------------------------------------------------------- criar / carregar
    def nova_versao(self, rede: RedeLinha, info: dict) -> str:
        ids = self.ids()
        vid = f"v{(int(ids[-1][1:]) + 1 if ids else 1):04d}"
        pasta = self.dir / vid
        pasta.mkdir()
        rede.salvar(pasta / "pesos.npz")
        _escrever_json(pasta / "meta.json", {"id": vid, "criada": time.strftime("%Y-%m-%d %H:%M:%S"),
                                             "hash": rede.hash(), "status": "candidato", **info,
                                             "eventos": [{"t": time.strftime("%Y-%m-%d %H:%M:%S"),
                                                          "evento": "criada"}]})
        return vid

    def carregar(self, vid: str) -> RedeLinha:
        rede = RedeLinha.carregar(self.dir / vid / "pesos.npz")
        if rede.hash() != self.meta(vid)["hash"]:
            raise ValueError(f"{vid}: pesos não conferem com o hash registrado (arquivo corrompido)")
        return rede

    def campeao_id(self) -> str | None:
        return self._estado()["campeao"]

    def tem_anterior(self) -> bool:
        return bool(self._estado()["anteriores"])

    def carregar_campeao(self) -> tuple[str | None, RedeLinha | None]:
        while True:
            vid = self.campeao_id()
            if vid is None:
                return None, None
            try:
                return vid, self.carregar(vid)
            except Exception as e:                       # arquivo ausente/corrompido
                log.error("Campeão %s inutilizável (%s): revertendo", vid, e)
                self.reverter(f"campeão ilegível: {e}", status="corrompido")

    # ---------------------------------------------------------------- decisões
    def promover(self, vid: str, motivo: str) -> None:
        e = self._estado()
        if e["campeao"]:
            e["anteriores"].append(e["campeao"])
            self._evento(e["campeao"], "arquivado", f"substituído por {vid}")
        e["campeao"] = vid
        self._gravar_estado(e)
        self._evento(vid, "campeao", f"promovido: {motivo}")
        log.info("Promovido %s (%s)", vid, motivo)

    def descartar(self, vid: str, motivo: str) -> None:
        self._evento(vid, "descartado", f"descartado: {motivo}")
        log.info("Descartado %s (%s)", vid, motivo)

    def reverter(self, motivo: str, status: str = "revertido") -> str | None:
        """Desfaz o campeão atual e volta ao anterior (None = não havia; o robô volta a ser só professor)."""
        e = self._estado()
        atual = e["campeao"]
        if atual:
            self._evento(atual, status, f"revertido: {motivo}")
        e["campeao"] = e["anteriores"].pop() if e["anteriores"] else None
        self._gravar_estado(e)
        log.warning("Rollback: %s -> %s (%s)", atual, e["campeao"], motivo)
        return e["campeao"]

    def limpar(self, manter: int) -> None:
        """Apaga versões antigas não-campeãs, guardando as `manter` mais recentes e a cadeia de campeões."""
        e = self._estado()
        proteger = set(e["anteriores"]) | ({e["campeao"]} if e["campeao"] else set())
        ids = self.ids()
        for vid in ids[:-manter] if manter > 0 else ids:
            if vid not in proteger:
                shutil.rmtree(self.dir / vid, ignore_errors=True)
