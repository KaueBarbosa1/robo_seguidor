"""Ciclo de aprendizado: escolhe quem dirige, roda a tentativa, avalia, treina candidatos e decide versões.

    tentativa -> episódio gravado -> métricas -> (a cada N quadros novos) treina candidato
             -> verificação offline contra o campeão -> A/B em tentativas alternadas -> promover | descartar
    campeão piorou -> rollback para o anterior;  falhas seguidas da CNN -> desce um nível de autonomia
Tudo fica em disco (config.APR_DIR): o ciclo continua de onde parou depois de desligar o robô.
"""
import json
import logging
import shutil
import time
from pathlib import Path

import numpy as np

import config as cfg
from aprendizado import avaliacao as av
from aprendizado.dados import (BufferTreino, GravadorEpisodio, carregar_episodio, listar_episodios,
                               preparar_entrada)
from aprendizado.politica import PoliticaAprendiz
from aprendizado.seguranca import Observacao, Supervisor
from aprendizado.treino import avaliar_offline, treinar
from aprendizado.versoes import RegistroModelos, _escrever_json

log = logging.getLogger("ciclo")


class TentativaAbortada(Exception):
    """O ambiente avisa que a tentativa acabou por fora (ex.: o operador disse 'pare')."""


class CicloAprendizado:
    def __init__(self, base: Path, rng: np.random.Generator | None = None):
        self.base = Path(base)
        self.base.mkdir(parents=True, exist_ok=True)
        self.reg = RegistroModelos(self.base)
        self.rng = rng or np.random.default_rng()
        self.arq = self.base / "estado_ciclo.json"
        padrao = {"nivel": 0, "nivel_desde": 0, "candidato": None, "candidato_desde": 0, "historico": [],
                  "quadros_no_ultimo_treino": 0, "n_treinos": 0, "baseline": None}
        self.e = padrao
        if self.arq.exists():
            try:
                self.e = {**padrao, **json.loads(self.arq.read_text(encoding="utf-8"))}
            except json.JSONDecodeError:
                log.error("estado_ciclo.json corrompido; recomeçando o estado (dados e modelos ficam)")

    def _salvar(self) -> None:
        _escrever_json(self.arq, self.e)

    # ------------------------------------------------------------------ quem dirige nesta tentativa
    def escolher_modelo(self) -> dict:
        cid, rede_c = self.reg.carregar_campeao()
        if cid is None:
            if self.e["nivel"] != 0:
                self.e["nivel"], self.e["nivel_desde"] = 0, len(self.e["historico"])
                self._salvar()
            return {"papel": "professor", "modelo_id": None, "rede": None, "nivel": 0}
        if self.e["nivel"] == 0:
            self.e["nivel"], self.e["nivel_desde"] = 1, len(self.e["historico"])
            self._salvar()
        nivel = self.e["nivel"]
        kid = self.e["candidato"]
        if kid:
            n_c = len(self._pontuacoes(kid, nivel, self.e["candidato_desde"]))
            n_k = len(self._pontuacoes(cid, nivel, self.e["candidato_desde"]))
            if n_c <= n_k:                                  # alterna: candidato, campeão, candidato...
                try:
                    return {"papel": "candidato", "modelo_id": kid, "rede": self.reg.carregar(kid), "nivel": nivel}
                except Exception as err:
                    self.reg.descartar(kid, f"ilegível: {err}")
                    self.e["candidato"] = None
                    self._salvar()
        return {"papel": "campeao", "modelo_id": cid, "rede": rede_c, "nivel": nivel}

    def _pontuacoes(self, modelo_id: str, nivel: int, desde: int) -> list[float]:
        return [h["pontuacao"] for h in self.e["historico"][desde:]
                if h["modelo_id"] == modelo_id and h["nivel"] == nivel and h["tipo"] in ("falha", "concluida")]

    # ------------------------------------------------------------------ depois de cada tentativa
    def registrar_resultado(self, resumo: dict) -> list[str]:
        eventos = []
        self.e["historico"].append(resumo)
        cid = self.reg.campeao_id()
        nivel = self.e["nivel"]
        if resumo["tipo"] == "interrompida":
            self._salvar()
            return [f"tentativa interrompida ({resumo['motivo']}): fora das comparações"]

        kid = self.e["candidato"]
        if kid:                                            # A/B em andamento: nível congelado
            desde = self.e["candidato_desde"]
            pk, pc = self._pontuacoes(cid, nivel, desde), self._pontuacoes(kid, nivel, desde)
            dec, info = av.decidir_promocao(pk, pc, self.rng, self.e.get("candidato_ganho", 0.0))
            if dec == "promover":
                self.reg.promover(kid, f"A/B: prob. de ser melhor {info['prob_melhor']:.2f}, dif {info['diferenca']:+.3f}, via {info.get('via', 'evidência direta')}")
                self.e.update(candidato=None, promovido_em=len(self.e["historico"]), baseline={"modelo": kid, "nivel": nivel, "pont": list(pc),
                                                         "desde": len(self.e["historico"])})
                eventos.append(f"{kid} promovido a campeão (A/B)")
            elif dec == "descartar":
                self.reg.descartar(kid, f"A/B: não superou o campeão ({info})")
                self.e["candidato"] = None
                eventos.append(f"{kid} descartado (A/B)")
        elif cid and resumo["papel"] == "campeao":
            bl = self.e["baseline"]
            if bl is None or bl["modelo"] != cid or bl["nivel"] != nivel:
                bl = self.e["baseline"] = {"modelo": cid, "nivel": nivel, "pont": [], "desde": len(self.e["historico"]) - 1}
            if not bl["pont"]:                                   # as primeiras tentativas viram a linha de base
                serie = self._pontuacoes(cid, nivel, bl["desde"])
                if len(serie) >= cfg.APR_AB_MIN:
                    bl["pont"], bl["desde"] = serie[:cfg.APR_AB_MIN], len(self.e["historico"])
            else:
                recentes = self._pontuacoes(cid, nivel, bl["desde"])
                if av.regressao_do_campeao(bl["pont"], recentes):
                    antigo = self.reg.reverter("desempenho do campeão caiu em relação à linha de base")
                    eventos.append(f"ROLLBACK: {cid} -> {antigo}")
                    self.e["baseline"] = None
                    self.e["promovido_em"] = len(self.e["historico"])
                    self.e["nivel"], self.e["nivel_desde"] = (max(1, nivel - 1) if antigo else 0), len(self.e["historico"])
                    self._salvar()
                    return eventos
        if self.e["candidato"] is None:                      # nível só muda fora de um A/B em andamento
            cid = self.reg.campeao_id()
            nivel = self.e["nivel"]
            if cid and nivel > 0:
                novo = av.decidir_nivel([h for h in self.e["historico"][self.e["nivel_desde"]:]
                                         if h["modelo_id"] == cid and h["nivel"] == nivel and h["papel"] != "professor"],
                                        nivel)
                recente = len(self.e["historico"]) - self.e.get("promovido_em", -10 ** 6) <= 3 * cfg.APR_AB_MAX
                if novo < nivel and recente and self.reg.tem_anterior():
                    # falhas seguidas causadas pela CNN logo depois de uma promoção: a atualização piorou -> rollback
                    antigo = self.reg.reverter("falhas seguidas da CNN logo após a promoção")
                    eventos.append(f"ROLLBACK: {cid} -> {antigo}")
                    self.e.update(baseline=None, nivel_desde=len(self.e["historico"]),
                                  promovido_em=len(self.e["historico"]))
                elif novo != nivel:
                    self.e["nivel"], self.e["nivel_desde"] = novo, len(self.e["historico"])
                    self.e["baseline"] = None
                    eventos.append(f"nível de autonomia {nivel} -> {novo}")
        self._salvar()
        return eventos

    # ------------------------------------------------------------------ treino entre tentativas
    def treinar_se_preciso(self) -> list[str]:
        if self.e["candidato"]:
            return []
        buf = BufferTreino(self.base)
        idx_treino = buf.indices(False)
        n_rot, n_eps = int(buf.mascara[idx_treino].sum()), len(buf.episodios)
        cid, rede_c = self.reg.carregar_campeao()
        eventos = []
        if cid is None:
            if n_rot < cfg.APR_MIN_QUADROS_PRIMEIRO or n_eps < 3:
                return []
            rede, m = treinar(buf, None, semente=self.e["n_treinos"])
            vm = m["validacao"]
            vid = self.reg.nova_versao(rede, self._info(buf, m, "do zero"))
            if not m["sem_validacao"] and vm["mae"] <= 0.8 * vm["mae_zero"]:
                self.reg.promover(vid, f"primeira CNN: erro {vm['mae']:.3f} vs {vm['mae_zero']:.3f} do chute 'sempre reto'")
                self.e.update(nivel=1, nivel_desde=len(self.e["historico"]), baseline=None,
                              promovido_em=len(self.e["historico"]))
                eventos.append(f"{vid}: primeira CNN promovida (nível 1)")
            else:
                self.reg.descartar(vid, f"não superou o chute 'sempre reto' (validação {vm})")
                eventos.append(f"{vid}: primeira CNN descartada")
        else:
            if n_rot - self.e["quadros_no_ultimo_treino"] < cfg.APR_NOVOS_PARA_TREINAR:
                return []
            do_zero = self.e["n_treinos"] % 3 == 2          # de vez em quando reconstrói sem herdar vícios
            rede, m = treinar(buf, None if do_zero else rede_c, semente=self.e["n_treinos"] + 1)
            vid = self.reg.nova_versao(rede, self._info(buf, m, "do zero" if do_zero else f"a partir de {cid}"))
            ref = avaliar_offline(rede_c, buf, buf.indices(True))
            vm = m["validacao"]
            if m["sem_validacao"] or not vm.get("n") or vm["mae"] > ref["mae"] * (1 + cfg.APR_TOL_OFFLINE):
                self.reg.descartar(vid, f"validação offline pior que o campeão ({vm.get('mae')} vs {ref.get('mae')})")
                eventos.append(f"{vid}: descartado na verificação offline")
            else:
                self.e.update(candidato=vid, candidato_desde=len(self.e["historico"]),
                              candidato_ganho=float((ref["mae"] - vm["mae"]) / max(ref["mae"], 1e-9)))
                eventos.append(f"{vid}: candidato em teste A/B (validação {vm['mae']:.3f} vs campeão {ref['mae']:.3f})")
        self.e["quadros_no_ultimo_treino"] = n_rot
        self.e["n_treinos"] += 1
        self.reg.limpar(cfg.APR_MANTER_VERSOES)
        self._salvar()
        return eventos

    @staticmethod
    def _info(buf, m, origem) -> dict:
        return {"origem": origem, "n_quadros": len(buf), "n_episodios": len(buf.episodios),
                "metricas": {k: v for k, v in m.items() if k != "historico"}}


# ====================================================================== uma tentativa
def executar_tentativa(amb, ciclo: CicloAprendizado, detector, rng: np.random.Generator,
                       max_passos: int | None = None) -> dict:
    """Roda UMA tentativa no ambiente `amb` (robô real ou simulado) e devolve o resumo.

    Interface do ambiente:  iniciar() | quadro() -> (quadro120x160, idade_s, t_s) | aplicar(steer, vel_fator)
                            ticks_delta() -> int|None | obstaculo() -> bool | sobre_pista() -> bool|None | parar()
    """
    sel = ciclo.escolher_modelo()
    pasta_eps = ciclo.base / "episodios"
    n = len(listar_episodios(ciclo.base)) + 1
    ep_id = f"ep_{n:05d}"
    meta0 = {"episodio": ep_id, "papel": sel["papel"], "modelo_id": sel["modelo_id"], "nivel": sel["nivel"],
             "inicio": time.strftime("%Y-%m-%d %H:%M:%S")}
    grav = GravadorEpisodio(pasta_eps / ep_id, meta0)
    pol = PoliticaAprendiz(sel["rede"], sel["nivel"], rng)
    sup = Supervisor()
    amb.iniciar()
    veredito = None
    abortada = False
    try:
        while max_passos is None or grav.n < max_passos:
            try:
                frame, idade, t = amb.quadro()
            except TentativaAbortada:
                abortada = True
                break
            r = detector.processar(frame)
            entrada = preparar_entrada(frame) if sel["rede"] is not None else None
            dec = pol.decidir(entrada, r.erro if r.achou else None, r.achou)
            obs = Observacao(t=t, quadro_idade_s=idade, prof_visivel=r.achou, e_prof=r.erro if r.achou else None,
                             controlador=dec.origem, steer_cmd=dec.steer, movendo=True,
                             ticks_delta=amb.ticks_delta(), obstaculo=amb.obstaculo(), sobre_pista=amb.sobre_pista())
            veredito = sup.avaliar(obs)
            grav.registrar(frame, {"t": t, "idade": idade, "prof_visivel": bool(r.achou),
                                   "e_prof": float(r.erro) if r.achou else None, "steer": dec.steer,
                                   "origem": dec.origem, "steer_prof": dec.steer_prof,
                                   "steer_aluno": dec.steer_aluno, "p_visivel": dec.p_visivel,
                                   "ticks": obs.ticks_delta, "sobre_pista": obs.sobre_pista})
            if veredito.parar:
                break
            amb.aplicar(dec.steer, dec.vel_fator)
    finally:
        amb.parar()
    if abortada:
        motivo, falha, causa = "parada_manual", False, False
    else:
        motivo = veredito.motivo if veredito and veredito.parar else "limite_de_passos"
        falha, causa = bool(veredito and veredito.falha), bool(veredito and veredito.causa_aluno)
    grav.fechar({"motivo": motivo, "falha": falha, "causa_aluno": causa})
    if grav.n == 0:                                   # nada gravado: não deixa episódio vazio
        shutil.rmtree(pasta_eps / ep_id, ignore_errors=True)
        return {"episodio": None, "modelo_id": sel["modelo_id"], "papel": sel["papel"], "nivel": sel["nivel"],
                "tipo": "interrompida", "motivo": motivo, "causa_aluno": False, "n_passos": 0, "duracao_s": 0.0,
                "erro_medio": 1.0, "frac_dentro": 0.0, "autonomia": 0.0, "intervencoes": 0, "sobrevida": 0.0,
                "pontuacao": 0.0}
    ep = carregar_episodio(pasta_eps / ep_id)
    resumo = av.resumir_episodio(ep.passos, ep.meta)
    resumo["episodio"] = ep_id
    return resumo
