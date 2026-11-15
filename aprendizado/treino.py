"""Treino e avaliação offline da CNN com os dados gravados pelo próprio carrinho."""
import logging

import numpy as np

import config as cfg
from aprendizado.cnn import Adam, RedeLinha
from aprendizado.dados import BufferTreino, normalizar

log = logging.getLogger("treino")


def avaliar_offline(rede: RedeLinha, buf: BufferTreino, idx: np.ndarray) -> dict:
    """Perda do treino (Huber + BCE) e métricas nos episódios inteiros fora do treino."""
    if len(idx) == 0:
        return {"n": 0, "perda": None, "mae": None, "mae_zero": None, "mae_vao": None, "acc_visivel": None}
    d, p = rede.prever(normalizar(buf.X[idx]))
    m = buf.mascara[idx]
    y = buf.dir[idx]
    vao = m & buf.reparado[idx]
    w = buf.peso[idx].astype(np.float64)
    soma_pesos = float(w.sum()) + 1e-8
    erro = d - y
    abs_erro = np.abs(erro)
    huber = np.where(abs_erro <= 0.3, 0.5 * erro * erro, 0.3 * (abs_erro - 0.15))
    p_seguro = np.clip(p, 1e-7, 1 - 1e-7)
    bce = -(buf.visivel[idx] * np.log(p_seguro) + (1 - buf.visivel[idx]) * np.log(1 - p_seguro))
    perda = float(((w * m * huber).sum() + 0.5 * (w * bce).sum()) / soma_pesos)
    return {
        "n": int(m.sum()),
        "perda": perda,
        "mae": float(np.abs(d - y)[m].mean()) if m.any() else float("nan"),
        "mae_zero": float(np.abs(y)[m].mean()) if m.any() else float("nan"),   # chute "sempre reto"
        "mae_vao": float(np.abs(d - y)[vao].mean()) if vao.any() else None,     # quadros em vãos do pontilhado
        "acc_visivel": float(((p > 0.5) == (buf.visivel[idx] > 0.5)).mean()),
    }


def treinar(buf: BufferTreino, rede: RedeLinha | None = None, semente: int = 0,
            passos: int | None = None) -> tuple[RedeLinha, dict]:
    """Treina e seleciona pesos pela perda de validação; o teste é avaliado só ao final."""
    passos = passos or cfg.APR_PASSOS_TREINO
    rng = np.random.default_rng(semente)
    rede = rede.copiar() if rede is not None else RedeLinha(semente)
    idx_tr, idx_val, idx_teste = buf.indices(False), buf.indices(True), buf.indices_teste()
    idx_tr = idx_tr[buf.mascara[idx_tr] | (rng.random(len(idx_tr)) < 0.3)]   # mantém alguns "sem linha"
    if len(idx_tr) < cfg.APR_LOTE:
        raise ValueError("poucos quadros para treinar")
    p = buf.peso[idx_tr] / buf.peso[idx_tr].sum()
    opt = Adam(rede, lr=cfg.APR_LR)
    melhor, melhor_val = rede.copiar(), float("inf")
    hist = []
    sem_melhora = 0
    executados = 0
    parada_antecipada = False
    for k in range(passos):
        lote = rng.choice(idx_tr, size=cfg.APR_LOTE, p=p)
        x, y, m, v, w = buf.lote(lote, rng)
        lr = cfg.APR_LR * (0.1 + 0.9 * 0.5 * (1 + np.cos(np.pi * k / passos)))   # decaimento cosseno
        perda, _ = rede.perda_e_gradiente(x, y, m, v, np.ones_like(w))           # peso já está na amostragem
        opt.passo(lr)
        executados = k + 1
        avaliar_agora = (k + 1) % cfg.APR_AVALIAR_A_CADA_PASSOS == 0 or k + 1 == passos
        if len(idx_val) and avaliar_agora:
            mt = avaliar_offline(rede, buf, idx_tr)
            mv = avaliar_offline(rede, buf, idx_val)
            hist.append({
                "passo": k + 1,
                "perda_lote": float(perda),
                "perda_treino": mt["perda"],
                "perda_validacao": mv["perda"],
                "mae_validacao": mv["mae"],
            })
            if mv["perda"] < melhor_val:
                melhor_val, melhor = mv["perda"], rede.copiar()
                sem_melhora = 0
            else:
                sem_melhora += 1
            if k + 1 >= cfg.APR_MIN_PASSOS_TREINO and sem_melhora >= cfg.APR_PACIENCIA_TREINO:
                parada_antecipada = k + 1 < passos
                break
    final = melhor if len(idx_val) else rede
    metr = {"passos": passos, "n_treino": int(len(idx_tr)), "n_validacao": int(len(idx_val)),
            "passos_executados": executados, "parada_antecipada": parada_antecipada,
            "treino": avaliar_offline(final, buf, idx_tr),
            "validacao": avaliar_offline(final, buf, idx_val),
            "teste": avaliar_offline(final, buf, idx_teste),
            "sem_validacao": len(idx_val) == 0, "sem_teste": len(idx_teste) == 0,
            "historico": hist}
    return final, metr
