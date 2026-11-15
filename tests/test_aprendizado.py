"""Testes do pacote aprendizado/. Rodar:  python tests/test_aprendizado.py   (ou  pytest tests/)

O que estes testes verificam: que o CÓDIGO faz o que o projeto diz (gradientes, rótulos, regras de segurança,
promoção, rollback, persistência). Eles NÃO provam que o carrinho aprende na pista física, o que só pode ser
medido com a pista real. Os testes de integração usam o simulador SINTÉTICO.
"""
import sys
import tempfile
import traceback
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg  # noqa: E402
from aprendizado import avaliacao as av  # noqa: E402
from aprendizado.ciclo import CicloAprendizado, executar_tentativa  # noqa: E402
from aprendizado.cnn import Adam, RedeLinha  # noqa: E402
from aprendizado.dados import (BufferTreino, Episodio, GravadorEpisodio, aumentar, carregar_episodio,  # noqa: E402
                               rotulos_do_episodio)
from aprendizado.politica import PoliticaAprendiz, direcao_para_pwm  # noqa: E402
from aprendizado.seguranca import Observacao, Supervisor  # noqa: E402
from aprendizado.simulador import AmbienteSimulado, PistaSintetica  # noqa: E402
from aprendizado.versoes import RegistroModelos  # noqa: E402
from visao.detector import DetectorLinha  # noqa: E402


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="apr_"))


# ------------------------------------------------------------------ CNN
def test_cnn_gradiente_confere_com_numerico():
    r = RedeLinha(1, np.float64)
    rng = np.random.default_rng(0)
    x = rng.standard_normal((6, 1, 40, 80)); y = rng.uniform(-1, 1, 6)
    m = np.array([1, 1, 0, 1, 1, 1.]); yv = np.array([1, 0, 1, 1, 0, 1.]); w = rng.uniform(.5, 2, 6)
    r.perda_e_gradiente(x, y, m, yv, w)
    ga = [g.copy() for g in r.gradientes()]
    erros = []
    for p, g in zip(r.parametros(), ga):
        for k in rng.choice(p.size, size=min(40, p.size), replace=False):
            ij = np.unravel_index(k, p.shape); old = p[ij]; h = 1e-6
            p[ij] = old + h; lp = r.perda_e_gradiente(x, y, m, yv, w)[0]
            p[ij] = old - h; lm = r.perda_e_gradiente(x, y, m, yv, w)[0]
            p[ij] = old
            num = (lp - lm) / (2 * h)
            erros.append(abs(num - g[ij]) / max(1e-9, abs(num) + abs(g[ij])))
    erros = np.array(erros)
    assert np.median(erros) < 1e-6 and (erros < 1e-4).mean() > 0.97, (np.median(erros), (erros < 1e-4).mean())


def test_cnn_aprende_e_salva():
    rng = np.random.default_rng(2)
    r = RedeLinha(2, np.float32); opt = Adam(r, 2e-3)

    def lote(n):
        X = np.zeros((n, 1, 40, 80), np.float32); Y = np.zeros(n, np.float32)
        for i in range(n):
            c = rng.integers(10, 70); X[i, 0, :, c - 2:c + 3] = 1; Y[i] = (c - 40) / 40
        return X + rng.normal(0, .05, X.shape).astype(np.float32), Y
    for _ in range(300):
        X, Y = lote(32); r.perda_e_gradiente(X, Y, np.ones(32), np.ones(32), np.ones(32)); opt.passo()
    X, Y = lote(200); d, _ = r.prever(X)
    assert np.abs(d - Y).mean() < 0.5 * np.abs(Y).mean()
    f = _tmp() / "m.npz"; r.salvar(f); r2 = RedeLinha.carregar(f)
    assert r2.hash() == r.hash() and np.allclose(r2.prever(X)[0], d)


# ------------------------------------------------------------------ dados / rótulos
def _ep(visivel, e=None, dt=0.4):
    passos = [{"t": i * dt, "prof_visivel": bool(v), "e_prof": (e[i] if e else 0.1 * i) if v else None}
              for i, v in enumerate(visivel)]
    return Episodio(Path("."), passos, None)


def test_rotulos_reparam_vao_curto_por_interpolacao():
    ep = _ep([1, 1, 0, 0, 0, 1], e=[0.0, 0.2, 0, 0, 0, 1.0])
    r = rotulos_do_episodio(ep, max_buraco=4)
    assert r["mascara_dir"].all() and r["reparado"].tolist() == [0, 0, 1, 1, 1, 0]
    assert r["dir"][2] < r["dir"][3] < r["dir"][4]                       # rampa de 0.2 até 1.0
    assert abs(r["dir"][3] - np.clip(cfg.APR_GANHO_PROF * 0.6, -1, 1)) < 1e-6


def test_rotulos_nao_inventam_em_vao_longo_nem_nas_pontas():
    ep = _ep([0, 1, 0, 0, 0, 0, 0, 0, 1, 0], e=[0, .1, 0, 0, 0, 0, 0, 0, .3, 0])
    r = rotulos_do_episodio(ep, max_buraco=4)
    assert r["mascara_dir"].tolist() == [0, 1, 0, 0, 0, 0, 0, 0, 1, 0]
    assert not r["reparado"].any()


def test_gravador_sobrevive_a_queda_de_energia():
    pasta = _tmp() / "episodios" / "ep_00001"
    g = GravadorEpisodio(pasta, {"episodio": "ep_00001"})
    for i in range(5):
        g.registrar(np.full((120, 160), i * 10, np.uint8), {"t": i * 0.4, "prof_visivel": True, "e_prof": 0.0})
    with open(pasta / "passos.jsonl", "a") as f:                         # linha cortada no meio
        f.write('{"t": 2.0, "prof_vi')
    ep = carregar_episodio(pasta)
    assert ep.n == 5 and ep.meta is None and int(ep.quadros()[3][0, 0]) == 30
    g.fechar({"motivo": "x"})
    assert carregar_episodio(pasta).meta["n_passos"] == 5


def _gerar_episodios(base: Path, n_ep=6, n=30):
    for k in range(n_ep):
        g = GravadorEpisodio(base / "episodios" / f"ep_{k + 1:05d}", {"episodio": f"ep_{k + 1:05d}"})
        for i in range(n):
            q = np.full((120, 160), 200, np.uint8)
            c = 80 + int(30 * np.sin(i / 4 + k)); q[:, c - 6:c + 6] = 40
            g.registrar(q, {"t": i * 0.4, "prof_visivel": True, "e_prof": (c - 80) / 80})
        g.fechar({"motivo": "concluida", "falha": False})


def test_buffer_divide_por_episodio_inteiro():
    base = _tmp(); _gerar_episodios(base)
    b = BufferTreino(base)
    tr, va = set(b.ep_idx[b.indices(False)]), set(b.ep_idx[b.indices(True)])
    assert tr and va and not (tr & va)


def test_aumentar_espelha_direcao():
    rng = np.random.default_rng(0)
    x = np.zeros((64, 1, 40, 80), np.float32); x[:, 0, :, 10:14] = 1.0   # traço à esquerda
    y = np.full(64, -0.6, np.float32)
    xa, ya = aumentar(x, y, rng)
    esp = xa[:, 0, :, 66:70].mean(axis=(1, 2)) > 0.5                      # traço foi para a direita
    assert esp.any() and (~esp).any()
    assert np.allclose(ya[esp], 0.6, atol=1e-6) and np.allclose(ya[~esp], -0.6, atol=1e-6)


# ------------------------------------------------------------------ supervisor
def _o(**k):
    base = dict(t=1.0, quadro_idade_s=0.4, prof_visivel=True, e_prof=0.1, controlador="professor",
                steer_cmd=0.1, movendo=True, ticks_delta=5)
    base.update(k)
    return Observacao(**base)


def _rodar(sup, obs):
    v = None
    for o in obs:
        v = sup.avaliar(o)
        if v.parar:
            return v
    return v


def test_supervisor_tudo_normal_nao_para():
    assert not _rodar(Supervisor(), [_o(t=i * 0.4) for i in range(50)]).parar


def test_supervisor_motivos():
    s = Supervisor
    assert _rodar(s(), [_o(quadro_idade_s=5)]).motivo == "sem_quadros"
    v = _rodar(s(), [_o(obstaculo=True)]); assert v.motivo == "obstaculo" and not v.falha
    v = _rodar(s(), [_o(t=cfg.APR_TEMPO_MAX_S)]); assert v.motivo == "concluida" and not v.falha
    v = _rodar(s(), [_o(sobre_pista=False)] * 2); assert v.motivo == "fora_da_pista" and v.falha
    assert not _rodar(s(), [_o(sobre_pista=False), _o(sobre_pista=True), _o(sobre_pista=False)]).parar
    v = _rodar(s(), [_o(prof_visivel=False, e_prof=None)] * (cfg.APR_MAX_QUADROS_SEM_LINHA + 1))
    assert v.motivo == "linha_perdida" and v.falha
    v = _rodar(s(), [_o(e_prof=0.95)] * cfg.APR_QUADROS_DIVERGENCIA); assert v.motivo == "divergencia" and v.falha
    osc = [_o(steer_cmd=0.8 * (-1) ** i) for i in range(cfg.APR_OSC_JANELA)]
    assert _rodar(s(), osc).motivo == "oscilacao"
    v = _rodar(s(), [_o(ticks_delta=0)] * cfg.APR_PARADO_PASSOS); assert v.motivo == "parado" and not v.falha


def test_supervisor_vao_curto_do_pontilhado_nao_e_falha():
    obs = [_o(prof_visivel=False, e_prof=None)] * cfg.APR_MAX_QUADROS_SEM_LINHA + [_o()]
    assert not _rodar(Supervisor(), obs).parar


def test_supervisor_marca_causa_aluno():
    v = _rodar(Supervisor(), [_o(controlador="aluno", prof_visivel=False, e_prof=None)] * 10)
    assert v.falha and v.causa_aluno
    v = _rodar(Supervisor(), [_o(controlador="professor", prof_visivel=False, e_prof=None)] * 10)
    assert v.falha and not v.causa_aluno


# ------------------------------------------------------------------ política
class _RedeFixa:
    def __init__(self, steer, p): self.s, self.p = steer, p
    def prever(self, x): return np.array([self.s]), np.array([self.p])


def test_politica_nivel0_so_professor():
    p = PoliticaAprendiz(None, 0, np.random.default_rng(0))
    d = p.decidir(None, 0.5, True)
    assert d.origem == "professor" and abs(d.steer - cfg.APR_GANHO_PROF * 0.5) < 1e-9


def test_politica_portao_so_deixa_aluno_dirigir_se_concordar():
    x = np.zeros((1, 40, 80), np.float32)
    p = PoliticaAprendiz(_RedeFixa(0.9, 0.9), 4, np.random.default_rng(0))             # sem portão
    assert p.decidir(x, 0.0, True).origem == "aluno"
    p = PoliticaAprendiz(_RedeFixa(0.9, 0.9), 1, np.random.default_rng(0))             # portão curto
    origens = [p.decidir(x, 0.0, True).origem for _ in range(300)]
    assert set(origens) == {"professor", "professor_portao"}                           # discorda: nunca "aluno"
    p = PoliticaAprendiz(_RedeFixa(0.05, 0.9), 1, np.random.default_rng(0))            # concorda
    assert "aluno" in {p.decidir(x, 0.0, True).origem for _ in range(300)}


def test_politica_no_vao_aluno_so_se_acha_que_ha_linha():
    x = np.zeros((1, 40, 80), np.float32)
    assert PoliticaAprendiz(_RedeFixa(0.4, 0.9), 4, np.random.default_rng(0)).decidir(x, None, False).origem == "aluno_vao"
    d = PoliticaAprendiz(_RedeFixa(0.4, 0.2), 4, np.random.default_rng(0)).decidir(x, None, False)
    assert d.origem == "mantido"


def test_pwm_dentro_dos_limites_e_sentido():
    e, d = direcao_para_pwm(1.0, 1.0)
    assert e > d and -cfg.VEL_MAX <= d and e <= cfg.VEL_MAX            # linha à direita -> gira p/ direita
    e, d = direcao_para_pwm(-1.0, 1.0); assert e < d


# ------------------------------------------------------------------ avaliação
def _res(tipo, pont, nivel=2, modelo="v0001", papel="campeao", causa=False, motivo=None):
    return {"tipo": tipo, "pontuacao": pont, "nivel": nivel, "modelo_id": modelo, "papel": papel,
            "causa_aluno": causa, "motivo": motivo or ("concluida" if tipo == "concluida" else "linha_perdida"),
            "erro_medio": 0.2}


def test_resumo_tipos_de_tentativa():
    p = [{"t": i * .4, "prof_visivel": True, "e_prof": 0.1, "origem": "aluno"} for i in range(10)]
    assert av.resumir_episodio(p, {"motivo": "concluida", "falha": False})["tipo"] == "concluida"
    r = av.resumir_episodio(p, {"motivo": "linha_perdida", "falha": True, "causa_aluno": True})
    assert r["tipo"] == "falha" and r["causa_aluno"] and r["sobrevida"] < 1
    assert av.resumir_episodio(p, {"motivo": "parada_manual", "falha": False})["tipo"] == "interrompida"
    assert av.resumir_episodio(p, {"motivo": "obstaculo", "falha": False})["tipo"] == "interrompida"


def test_promocao_regras():
    rng = np.random.default_rng(0)
    bom, ruim = [0.95, 0.96, 0.94, 0.95, 0.96], [0.4, 0.5, 0.45, 0.5, 0.4]
    assert av.decidir_promocao(ruim, bom, rng)[0] == "promover"
    assert av.decidir_promocao(bom, ruim, rng)[0] == "descartar"
    assert av.decidir_promocao(bom[:2], bom[:2], rng)[0] == "continuar"
    empate = [0.95, 0.96, 0.94, 0.95, 0.96, 0.95, 0.94, 0.96]
    outro = [0.96, 0.95, 0.95, 0.94, 0.96, 0.95, 0.96, 0.94]
    assert av.decidir_promocao(empate, outro, rng, ganho_offline=0.0)[0] == "descartar"       # sem ganho offline
    d, info = av.decidir_promocao(empate, outro, rng, ganho_offline=0.3)
    assert d == "promover" and info["via"] == "nao_inferior+offline"
    # com ganho offline, mas pior de verdade no A/B: nunca promove
    assert av.decidir_promocao(bom * 2, ruim * 2, rng, ganho_offline=0.9)[0] == "descartar"


def test_nivel_sobe_e_desce():
    ok = [_res("concluida", .95)] * 3
    assert av.decidir_nivel(ok, 2) == 3
    assert av.decidir_nivel(ok, len(cfg.APR_NIVEIS) - 1) == len(cfg.APR_NIVEIS) - 1
    assert av.decidir_nivel([_res("concluida", .95), _res("falha", .3, causa=True), _res("falha", .3, causa=True)], 3) == 2
    assert av.decidir_nivel([_res("falha", .3, causa=False)] * 2, 3) == 3                   # falha não foi da CNN
    assert av.decidir_nivel([_res("interrompida", 0)] * 5, 2) == 2                          # interrompidas não contam


def test_regressao():
    assert av.regressao_do_campeao([.95] * 3, [.5] * 5)
    assert not av.regressao_do_campeao([.95] * 3, [.94] * 5)
    assert not av.regressao_do_campeao([.95] * 3, [.5] * 2)                                  # dados insuficientes


# ------------------------------------------------------------------ versões
def test_registro_promover_reverter_e_hash():
    reg = RegistroModelos(_tmp())
    assert reg.carregar_campeao() == (None, None)
    v1 = reg.nova_versao(RedeLinha(1), {}); reg.promover(v1, "teste")
    v2 = reg.nova_versao(RedeLinha(2), {}); reg.promover(v2, "teste")
    assert reg.campeao_id() == v2 and reg.tem_anterior()
    assert reg.reverter("piorou") == v1 and reg.campeao_id() == v1
    assert reg.meta(v2)["status"] == "revertido"
    assert reg.reverter("x") is None and reg.carregar_campeao() == (None, None)


def test_registro_campeao_corrompido_volta_ao_anterior():
    reg = RegistroModelos(_tmp())
    v1 = reg.nova_versao(RedeLinha(1), {}); reg.promover(v1, "a")
    v2 = reg.nova_versao(RedeLinha(2), {}); reg.promover(v2, "b")
    arq = reg.dir / v2 / "pesos.npz"
    arq.write_bytes(arq.read_bytes()[:100])                                                  # arquivo cortado
    vid, rede = reg.carregar_campeao()
    assert vid == v1 and rede is not None and reg.meta(v2)["status"] == "corrompido"


def test_registro_limpar_guarda_campeao_e_cadeia():
    reg = RegistroModelos(_tmp()); ids = []
    for i in range(8):
        ids.append(reg.nova_versao(RedeLinha(i), {}))
    reg.promover(ids[0], "a"); reg.promover(ids[1], "b")
    reg.limpar(2)
    resto = reg.ids()
    assert ids[0] in resto and ids[1] in resto and ids[-1] in resto and ids[2] not in resto


# ------------------------------------------------------------------ ciclo
def _ciclo_com_dois_campeoes():
    c = CicloAprendizado(_tmp(), np.random.default_rng(0))
    v1 = c.reg.nova_versao(RedeLinha(1), {}); c.reg.promover(v1, "a")
    v2 = c.reg.nova_versao(RedeLinha(2), {}); c.reg.promover(v2, "b")
    c.e.update(nivel=3, nivel_desde=0, promovido_em=0)
    return c, v1, v2


def test_ciclo_rollback_por_falhas_logo_apos_promocao():
    c, v1, v2 = _ciclo_com_dois_campeoes()
    c.registrar_resultado(_res("concluida", .95, nivel=3, modelo=v2))
    ev = c.registrar_resultado(_res("falha", .3, nivel=3, modelo=v2, causa=True))
    assert not ev
    ev = c.registrar_resultado(_res("falha", .3, nivel=3, modelo=v2, causa=True))
    assert any("ROLLBACK" in e for e in ev) and c.reg.campeao_id() == v1 and c.e["nivel"] == 3


def test_ciclo_falhas_de_campeao_antigo_so_descem_o_nivel():
    c, v1, v2 = _ciclo_com_dois_campeoes()
    c.e["promovido_em"] = -1000                                                              # promoção antiga
    c.registrar_resultado(_res("falha", .3, nivel=3, modelo=v2, causa=True))
    ev = c.registrar_resultado(_res("falha", .3, nivel=3, modelo=v2, causa=True))
    assert c.reg.campeao_id() == v2 and c.e["nivel"] == 2 and any("nível" in e for e in ev)


def test_ciclo_regressao_lenta_reverte():
    c, v1, v2 = _ciclo_com_dois_campeoes()
    c.e["nivel"] = len(cfg.APR_NIVEIS) - 1                               # no topo o nível não muda e mascara o teste
    nv = c.e["nivel"]
    for _ in range(cfg.APR_AB_MIN):
        c.registrar_resultado(_res("concluida", .95, nivel=nv, modelo=v2))
    eventos = []
    for _ in range(6):
        eventos += c.registrar_resultado(_res("concluida", .55, nivel=nv, modelo=v2))        # concluiu, mas pior
    assert any("ROLLBACK" in e for e in eventos) and c.reg.campeao_id() == v1


def test_ciclo_interrompida_fica_fora_das_contas_e_estado_persiste():
    c, v1, v2 = _ciclo_com_dois_campeoes()
    ev = c.registrar_resultado(_res("interrompida", 0.0, nivel=3, modelo=v2, motivo="parada_manual"))
    assert "interrompida" in ev[0]
    c2 = CicloAprendizado(c.base, np.random.default_rng(1))
    assert c2.e["nivel"] == 3 and len(c2.e["historico"]) == 1


def test_ciclo_estado_corrompido_nao_derruba():
    base = _tmp(); (base / "estado_ciclo.json").write_text("{quebrado")
    c = CicloAprendizado(base, np.random.default_rng(0))
    assert c.e["nivel"] == 0


def test_ciclo_sem_dados_suficientes_nao_treina():
    base = _tmp(); _gerar_episodios(base, n_ep=1, n=20)
    c = CicloAprendizado(base, np.random.default_rng(0))
    assert c.treinar_se_preciso() == [] and c.reg.campeao_id() is None


# ------------------------------------------------------------------ detector (o "professor")
def test_detector_nao_inventa_linha_em_piso_liso_com_ruido_e_vinheta():
    rng = np.random.default_rng(0)
    yy, xx = np.mgrid[-1:1:120j, -1:1:160j]
    for ganho in (0.7, 1.0, 1.15):
        img = 205 * ganho * (1 - 0.12 * (xx ** 2 + yy ** 2)) + rng.normal(0, 7, (120, 160))
        q = (np.clip(np.round(img / 17), 0, 14) * 17).astype(np.uint8)
        assert not DetectorLinha().processar(q).achou


def test_detector_acha_traco_e_mede_o_lado():
    q = np.full((120, 160), 204, np.uint8); q[70:110, 100:112] = 34        # traço à direita do centro
    r = DetectorLinha().processar(q)
    assert r.achou and 0.2 < r.erro < 0.5


# ------------------------------------------------------------------ integração no simulador SINTÉTICO
def test_simulador_professor_completa_e_cnn_aleatoria_nao_engana_o_supervisor():
    cfg.APR_TEMPO_MAX_S = 30
    rng = np.random.default_rng(3)
    pista = PistaSintetica(3); amb = AmbienteSimulado(pista, rng); det = DetectorLinha()
    c = CicloAprendizado(_tmp(), rng)
    r = executar_tentativa(amb, c, det, rng)                              # sem modelo: professor dirige
    assert r["papel"] == "professor" and r["tipo"] == "concluida" and not amb.fora_verdade
    # CNN sem treino, sem portão: dirige mal; o supervisor tem que interromper marcando falha da CNN
    v = c.reg.nova_versao(RedeLinha(7), {}); c.reg.promover(v, "teste"); c.e["nivel"] = len(cfg.APR_NIVEIS) - 1
    falhas = 0
    for _ in range(4):
        r = executar_tentativa(amb, c, det, rng)
        falhas += r["tipo"] == "falha"
        if r["tipo"] == "falha":
            assert r["causa_aluno"] and r["n_passos"] < 100
    assert falhas >= 1


def test_ciclo_completo_sintetico():
    cfg.APR_TEMPO_MAX_S = 30
    rng = np.random.default_rng(5)
    amb = AmbienteSimulado(PistaSintetica(5), rng); det = DetectorLinha()
    c = CicloAprendizado(_tmp(), rng)
    for _ in range(8):
        r = executar_tentativa(amb, c, det, rng)
        c.registrar_resultado(r); c.treinar_se_preciso()
    assert c.reg.campeao_id() is not None and c.e["nivel"] >= 1
    cid, rede = c.reg.carregar_campeao()
    # o campeão aprendeu a imitar o professor melhor que "sempre reto" nos episódios SEPARADOS para validação
    m = c.reg.meta(cid)["metricas"]["validacao"]
    assert m["mae"] < m["mae_zero"]
    # tudo gravado: um episódio por tentativa, com quadros e passos
    assert len(list((c.base / "episodios").glob("ep_*"))) == 8


def main():
    testes = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    falhou = 0
    for nome, f in testes:
        try:
            f(); print(f"ok    {nome}")
        except Exception:
            falhou += 1; print(f"FALHA {nome}"); traceback.print_exc()
    print(f"\n{len(testes) - falhou}/{len(testes)} testes passaram")
    sys.exit(1 if falhou else 0)


if __name__ == "__main__":
    main()
