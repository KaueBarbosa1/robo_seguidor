"""Treina Q-learning e compara com PD usando uma referência CNN sintética."""
import argparse
import json
import platform
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from aprendizado.cnn import RedeLinha  # noqa: E402
from aprendizado.rl_simulado import ACOES, CONTRATO, AgenteQ, AmbienteRL, acao_pd, treinar_referencia  # noqa: E402
from tools.treinar_fotos_linha import escrever_csv  # noqa: E402
import config as cfg  # noqa: E402


def episodio(rede, agente, pista, semente, passos, epsilon=None):
    ambiente = AmbienteRL(rede, pista, semente, passos)
    retorno = suavidade = erro = bloqueios = 0.
    terminou = False
    while not terminou:
        estado = ambiente.estado()
        acao = acao_pd(ambiente) if agente is None else agente.escolher(estado, epsilon or 0.)
        proximo, recompensa, terminou, info = ambiente.passo(acao)
        if epsilon is not None:
            agente.atualizar(estado, acao, recompensa, proximo, terminou)
        retorno += recompensa
        suavidade += info['suavidade']
        erro += info['erro_real_m']
        bloqueios += info['bloqueada']
    return {'pista': pista, 'semente': semente, 'retorno': retorno, 'progresso_m': info['progresso_m'],
            'fora': info['fora'], 'passos': ambiente.passos, 'erro_medio_m': erro / ambiente.passos,
            'variacao_acao_media': suavidade / ambiente.passos, 'bloqueios': int(bloqueios)}


def avaliar(rede, agente, pistas, passos, semente):
    return [episodio(rede, agente, pista, semente + i, passos) for i, pista in enumerate(pistas)]


def executar(args):
    args.saida.mkdir(parents=True, exist_ok=False)
    print('Treinando referência CNN em imagens sintéticas', flush=True)
    rede = treinar_referencia(args.semente, args.amostras_cnn, args.passos_cnn)
    rede.salvar(args.saida / 'referencia_sintetica.npz')
    rede = RedeLinha.carregar(args.saida / 'referencia_sintetica.npz')
    agente = AgenteQ(args.semente)
    melhor = agente.q.copy()
    melhor_nota = -float('inf')
    historico = []
    for ep in range(args.episodios):
        epsilon = max(.05, 1 - ep / max(1, .8 * args.episodios))
        r = episodio(rede, agente, ep % 10, args.semente + ep, args.passos, epsilon)
        r.update(episodio=ep + 1, epsilon=epsilon)
        historico.append(r)
        if (ep + 1) % 10 == 0 or ep + 1 == args.episodios:
            val = avaliar(rede, agente, range(10, 13), args.passos, 1000)
            nota = float(np.mean([v['retorno'] for v in val]))
            if nota > melhor_nota:
                melhor_nota, melhor = nota, agente.q.copy()
            print(f'Episódio {ep + 1}: retorno validação={nota:.3f}', flush=True)
    agente.q[:] = melhor
    caminho = args.saida / 'politica_q.npz'
    np.savez(caminho, contrato=CONTRATO, acoes=ACOES, q=agente.q, hash_cnn=rede.hash())
    with np.load(caminho, allow_pickle=False) as salvo:
        np.testing.assert_array_equal(salvo['q'], agente.q)
        np.testing.assert_array_equal(salvo['acoes'], ACOES)
        assert salvo['hash_cnn'].item() == rede.hash()
        agente.q[:] = salvo['q']
    resultados = []
    for nome, controlador in [('PD discretizado', None), ('Q-learning', agente)]:
        for r in avaliar(rede, controlador, range(20, 25), args.passos, 2000):
            resultados.append({'politica': nome, **r})
    escrever_csv(args.saida / 'treino.csv', historico)
    escrever_csv(args.saida / 'avaliacao.csv', resultados)
    manifesto = {'contrato': CONTRATO, 'hash_referencia_cnn': rede.hash(), 'python': platform.python_version(),
                 'numpy': np.__version__, 'parametros': vars(args) | {'saida': str(args.saida)},
                 'referencia': {'entrada': [1, 40, 80], 'roi_inicio': cfg.APR_ROI_LINHA_INICIO,
                                'semantica': 'lateral_a_10cm_dividida_por_12cm',
                                'visibilidade': 'OpenCV_sintetico'},
                 'pd': {'kp': cfg.KP, 'kd': cfg.KD, 'vel_base': cfg.VEL_BASE, 'vel_max': cfg.VEL_MAX},
                 'divisao_pistas': {'treino': list(range(10)), 'validacao': list(range(10, 13)), 'teste': list(range(20, 25))},
                 'resultado': resultados, 'melhor_retorno_validacao': melhor_nota,
                 'fisica': {'dt_s': .1, 'memoria_s': .6, 'velocidade_max_m_s': .11,
                            'omega_max_rad_s': 1.6, 'tau_motor_s': .3, 'limite_fora_m': .10},
                 'recompensa': '20*progresso_assinado - 0.1*(distancia/0.10)^2 - 0.01*variacao_direcao - 5*fora',
                 'limites': ['simulação sintética com geometria e dinâmica hipotéticas',
                             'CNN treinada para esta simulação; contrato distinto das fotos e ESP32',
                             'PD convertido ao mesmo conjunto discreto de ações',
                             'sem obstáculos e sem comunicação serial física',
                             'fim de episódio por limite de tempo não demonstra volta completa']}
    (args.saida / 'experimento.json').write_text(json.dumps(manifesto, indent=2, ensure_ascii=False), encoding='utf-8')
    linhas = ['# RL com referência CNN em simulação', '',
              '| Política | Retorno médio | Progresso médio (m) | Saídas de pista | Erro lateral médio (m) |',
              '|---|---:|---:|---:|---:|']
    for nome in ('PD discretizado', 'Q-learning'):
        grupo = [r for r in resultados if r['politica'] == nome]
        linhas.append(f"| {nome} | {np.mean([r['retorno'] for r in grupo]):.3f} | "
                      f"{np.mean([r['progresso_m'] for r in grupo]):.3f} | {sum(r['fora'] for r in grupo)}/5 | "
                      f"{np.mean([r['erro_medio_m'] for r in grupo]):.4f} |")
    linhas += ['', 'A referência CNN fica congelada durante RL. A política observa a previsão, sua variação, '
               'velocidade simulada, idade e ação anterior. A recompensa usa a geometria real do simulador. '
               'Dados de treino, validação e teste vêm de pistas com sementes distintas.', '', *manifesto['limites'], '']
    (args.saida / 'RELATORIO.md').write_text('\n'.join(linhas), encoding='utf-8')
    print('\n'.join(linhas), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--saida', type=Path, required=True)
    parser.add_argument('--episodios', type=int, default=100)
    parser.add_argument('--passos', type=int, default=150)
    parser.add_argument('--amostras-cnn', type=int, default=600)
    parser.add_argument('--passos-cnn', type=int, default=250)
    parser.add_argument('--semente', type=int, default=7)
    args = parser.parse_args()
    if args.saida.exists() or min(args.episodios, args.passos, args.amostras_cnn, args.passos_cnn) < 1 or args.semente < 0:
        parser.error('use uma pasta nova, quantidades positivas e semente não negativa')
    executar(args)


if __name__ == '__main__':
    main()
