"""Métricas das tentativas e regras de decisão (promover, descartar, subir/descer de nível, reverter).

Como o sistema sabe se uma tentativa foi boa: SOBREVIDA (quanto tempo andou sem sair da pista ou ficar inseguro,
medido por sensores independentes da CNN) menos uma penalidade pelo erro lateral médio. É uma recompensa
"esparsa" por tentativa; não há atribuição de mérito a cada ação isolada (com ~2,5 quadros/s e ~0,5 s de
atraso entre ver e agir isso seria ruído, veja docs/04).
"""
import numpy as np

import config as cfg


def resumir_episodio(passos: list, meta: dict | None) -> dict:
    meta = meta or {}
    erros = [abs(p["e_prof"]) for p in passos if p.get("prof_visivel") and p.get("e_prof") is not None]
    origens = [p.get("origem", "") for p in passos]
    n = max(1, len(passos))
    motivo = meta.get("motivo")
    falha = bool(meta.get("falha"))
    duracao = float(passos[-1]["t"]) if passos else 0.0
    if motivo in ("parada_manual", "sem_quadros", "obstaculo", "parado", None) and not falha:
        tipo = "interrompida"             # não diz nada sobre a CNN: fica fora das comparações
    elif falha:
        tipo = "falha"
    else:
        tipo = "concluida"
    sobrevida = 1.0 if tipo == "concluida" else min(1.0, duracao / cfg.APR_TEMPO_MAX_S)
    erro_medio = float(np.mean(erros)) if erros else 1.0
    return {
        "episodio": meta.get("episodio"), "modelo_id": meta.get("modelo_id"), "papel": meta.get("papel"),
        "nivel": meta.get("nivel", 0), "tipo": tipo, "motivo": motivo, "causa_aluno": bool(meta.get("causa_aluno")),
        "n_passos": len(passos), "duracao_s": duracao,
        "erro_medio": erro_medio,
        "frac_dentro": float(np.mean([e < 0.3 for e in erros])) if erros else 0.0,
        "autonomia": sum(o.startswith("aluno") for o in origens) / n,
        "intervencoes": sum(o == "professor_portao" for o in origens),
        "sobrevida": sobrevida,
        "pontuacao": sobrevida - 0.2 * min(1.0, erro_medio),
    }


def comparar(base: list[float], novo: list[float], rng: np.random.Generator, n_boot: int = 4000) -> dict:
    """Bootstrap da diferença de médias (novo - base). prob_melhor = chance de o novo ser realmente melhor."""
    a, b = np.asarray(base, float), np.asarray(novo, float)
    ia = rng.integers(0, len(a), (n_boot, len(a)))
    ib = rng.integers(0, len(b), (n_boot, len(b)))
    d = b[ib].mean(axis=1) - a[ia].mean(axis=1)
    return {"diferenca": float(b.mean() - a.mean()), "prob_melhor": float((d > 0).mean()),
            "prob_pior": float((d < 0).mean()), "ic95": (float(np.quantile(d, .025)), float(np.quantile(d, .975)))}


def decidir_promocao(pont_campeao: list[float], pont_candidato: list[float], rng,
                     ganho_offline: float = 0.0) -> tuple[str, dict]:
    """'promover' | 'descartar' | 'continuar' (A/B com tentativas alternadas no mesmo nível).

    O A/B serve principalmente como TRAVA DE SEGURANÇA. Regras:
      - evidência clara de que é melhor (prob_melhor >= APR_AB_PROB)        -> promover
      - evidência clara de que é pior   (prob_pior   >= APR_AB_PROB)        -> descartar
      - no limite de tentativas sem evidência: promove só se for NÃO-INFERIOR (limite inferior do IC95 da
        diferença acima de -APR_NAO_INFERIOR_MARGEM) E tiver melhorado a validação offline (em episódios
        inteiros separados) em pelo menos APR_GANHO_OFFLINE_MIN. Caso contrário o campeão fica.
    `ganho_offline` = (erro_campeão - erro_candidato) / erro_campeão na validação offline."""
    if min(len(pont_campeao), len(pont_candidato)) < cfg.APR_AB_MIN:
        return "continuar", {}
    c = comparar(pont_campeao, pont_candidato, rng)
    if c["prob_melhor"] >= cfg.APR_AB_PROB:
        return "promover", c
    if c["prob_pior"] >= cfg.APR_AB_PROB:
        return "descartar", c
    if min(len(pont_campeao), len(pont_candidato)) >= cfg.APR_AB_MAX:
        if c["ic95"][0] > -cfg.APR_NAO_INFERIOR_MARGEM and ganho_offline >= cfg.APR_GANHO_OFFLINE_MIN:
            c["via"] = "nao_inferior+offline"
            return "promover", c
        return "descartar", c
    return "continuar", c


def decidir_nivel(resumos_campeao_no_nivel: list[dict], nivel: int) -> int:
    """Nível de autonomia novo, olhando as tentativas do campeão no nível atual (só falha/concluída)."""
    r = [x for x in resumos_campeao_no_nivel if x["tipo"] in ("falha", "concluida")]
    # desce: falhas seguidas causadas pela CNN
    recentes = r[-cfg.APR_NIVEL_DESCER_FALHAS:]
    if (nivel > 1 and len(recentes) == cfg.APR_NIVEL_DESCER_FALHAS
            and all(x["tipo"] == "falha" and x["causa_aluno"] for x in recentes)):
        return nivel - 1
    # sobe: tentativas suficientes e poucas falhas
    ultimas = r[-cfg.APR_NIVEL_SUBIR_TENT:]
    if (nivel < len(cfg.APR_NIVEIS) - 1 and len(ultimas) == cfg.APR_NIVEL_SUBIR_TENT
            and np.mean([x["tipo"] == "falha" for x in ultimas]) <= cfg.APR_NIVEL_SUBIR_FALHAS):
        return nivel + 1
    return nivel


def regressao_do_campeao(pont_baseline: list[float], pont_recentes: list[float], janela: int = 5,
                         margem: float = 0.25) -> bool:
    """True se o campeão, já promovido, piorou: média das últimas `janela` tentativas (mesmo nível) abaixo da
    média de quando foi promovido por mais que `margem`."""
    if len(pont_baseline) < cfg.APR_AB_MIN or len(pont_recentes) < janela:
        return False
    return float(np.mean(pont_recentes[-janela:])) < float(np.mean(pont_baseline)) - margem
