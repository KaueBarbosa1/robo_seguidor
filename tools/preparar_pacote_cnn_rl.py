"""Empacota CNN+Q/DQN/PPO ja treinados para inferencia sombra na ESP32. Nao treina."""
import argparse
import json
from pathlib import Path
import shutil
import sys

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aprendizado.cnn import RedeLinha
from aprendizado.inferencia_esp32 import CONTRATO, OBS_Q, OBS_GYM, sha256
from aprendizado.rl_simulado import ACOES


def preparar(experimento, algoritmo, checkpoint, saida):
    experimento, saida = Path(experimento), Path(saida)
    meta = json.loads((experimento/'experimento.json').read_text(encoding='utf-8'))
    if meta.get('contrato') not in {OBS_Q, OBS_GYM}:
        raise ValueError('Informe experimento CNN/RL pareado; CNN de posicao offline nao e compativel')
    cnn = experimento/'referencia_sintetica.npz'
    rede = RedeLinha.carregar(cnn)
    if not all(np.isfinite(p).all() for p in rede.parametros()):
        raise ValueError('CNN com parametros invalidos')
    if algoritmo == 'q':
        if (meta['contrato'] != OBS_Q or meta['hash_referencia_cnn'] != rede.hash() or
                meta['referencia']['roi_inicio'] != 40 or
                meta['referencia']['semantica'] != 'lateral_a_10cm_dividida_por_12cm'):
            raise ValueError('Referencia sintetica diferente do contrato Q')
        checkpoint = experimento/'politica_q.npz' if checkpoint is None else Path(checkpoint)
        with np.load(checkpoint, allow_pickle=False) as d:
            if (d['contrato'].item() != OBS_Q or d['hash_cnn'].item() != rede.hash() or
                    not np.array_equal(d['acoes'], ACOES) or
                    d['q'].shape != (7, 5, 3, 3, 11, 11) or not np.isfinite(d['q']).all()):
                raise ValueError('Politica Q nao corresponde a CNN')
        observacao = OBS_Q
    else:
        if checkpoint is None:
            raise ValueError('Informe --checkpoint do agente/seed escolhido na validacao')
        checkpoint = Path(checkpoint)
        relativo = checkpoint.resolve().relative_to(experimento.resolve()).as_posix()
        selecionado = any(e['algoritmo'].lower() == algoritmo and
                          relativo == f"{algoritmo}_{e['semente']}/melhor.zip" for e in meta['execucoes'])
        if (meta['contrato'] != OBS_GYM or meta['hash_cnn'] != rede.hash() or
                not np.array_equal(meta['acoes'], ACOES) or not selecionado or
                meta['sha256_checkpoints'].get(relativo) != sha256(checkpoint)):
            raise ValueError('Checkpoint DQN/PPO ou referencia sem correspondencia no experimento')
        observacao = OBS_GYM
    m = dict(contrato=CONTRATO, dominio='sintetico', hash_cnn=rede.hash(), acoes=ACOES.tolist(),
             escalas=dict(dt_s=.1, memoria_s=.6, velocidade_max_m_s=.11),
             cnn=dict(arquivo='cnn.npz', sha256=sha256(cnn)),
             politica=dict(arquivo='politica'+checkpoint.suffix, sha256=sha256(checkpoint),
                           algoritmo=algoritmo, observacao=observacao),
             percepcao=dict(preprocessamento='simulado_160x120_roi40_v1', visibilidade_treinada=True),
             encoders=dict(mm_por_pulso=[np.pi*65/19.4, np.pi*65/19.2], calibrados=False),
             limitacoes=['Referencia sintetica e adaptacao de resolucao somente para diagnostico',
                         'Geometria de encoder provisoria; nao e velocidade calibrada no piso',
                         'Nao habilita motores; nenhum treino e feito ao empacotar'])
    saida.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(cnn, saida/'cnn.npz')
    shutil.copyfile(checkpoint, saida/m['politica']['arquivo'])
    (saida/'pacote.json').write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding='utf-8')
    return saida/'pacote.json'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--experimento', required=True, type=Path)
    ap.add_argument('--algoritmo', choices=('q', 'dqn', 'ppo'), required=True)
    ap.add_argument('--checkpoint', type=Path, help='caminho completo ou relativo ao diretorio atual')
    ap.add_argument('--saida', required=True, type=Path, help='pasta nova')
    a = ap.parse_args()
    try:
        print(preparar(a.experimento, a.algoritmo, a.checkpoint, a.saida))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        ap.error(str(exc))


if __name__ == '__main__':
    main()
