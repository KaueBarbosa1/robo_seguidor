"""Treina DQN/PPO e compara com PD discretizado em simulação sintética."""
import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import cv2
import gymnasium
import matplotlib
import numpy as np
import stable_baselines3 as sb3
import torch
from matplotlib.figure import Figure
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.env_checker import check_env
from stable_baselines3.common.monitor import Monitor

matplotlib.use('Agg')
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import config as cfg  # noqa: E402
from aprendizado.ambiente_gym import CONTRATO_GYM, AmbienteLinhaGym  # noqa: E402
from aprendizado.cnn import RedeLinha  # noqa: E402
from aprendizado.dados import preparar_entrada  # noqa: E402
from aprendizado.rl_simulado import ACOES, CONTRATO, acao_pd, treinar_referencia  # noqa: E402
from tools.treinar_fotos_linha import escrever_csv  # noqa: E402

DIVISOES = {'treino': list(range(10)), 'validacao': list(range(10, 13)), 'teste': list(range(20, 25))}
CLASSES = {'DQN': sb3.DQN, 'PPO': sb3.PPO}


def gravar_json(caminho, dados):
    temporario = caminho.with_suffix('.tmp')
    temporario.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding='utf-8')
    temporario.replace(caminho)


def avaliar(referencia, modelo, pistas, passos, seed):
    env = AmbienteLinhaGym(referencia, pistas=pistas, max_passos=passos)
    resultados = []
    try:
        for i, pista in enumerate(pistas):
            observacao, _ = env.reset(seed=seed + i, options={'pista': pista})
            retorno = erro = variacao = bloqueios = parados = n = 0
            terminou = truncado = False
            while not (terminou or truncado):
                acao = acao_pd(env.simulacao) if modelo is None else int(modelo.predict(observacao, deterministic=True)[0])
                observacao, recompensa, terminou, truncado, info = env.step(acao)
                retorno += recompensa
                erro += info['erro_real_m']
                variacao += info['suavidade']
                bloqueios += info['bloqueada']
                parados += info['parado']
                n += 1
            resultados.append({'pista': pista, 'seed_cenario': seed + i, 'retorno': retorno,
                               'progresso_m': info['progresso_m'], 'fora': int(terminou), 'limite_tempo': int(truncado),
                               'passos': n, 'erro_lateral_m': erro / n, 'variacao_direcao': variacao / n,
                               'bloqueios_pct': 100 * bloqueios / n, 'parado_pct': 100 * parados / n})
    finally:
        env.close()
    return resultados


class Validacao(BaseCallback):
    def __init__(self, referencia, pasta, intervalo, passos):
        super().__init__()
        self.referencia, self.pasta = referencia, pasta
        self.intervalo, self.passos = intervalo, passos
        self.melhor = -float('inf')
        self.melhor_passo = None
        self.curvas, self.episodios = [], []

    def medir(self):
        resultados = avaliar(self.referencia, self.model, DIVISOES['validacao'], self.passos, 1000)
        media = float(np.mean([r['retorno'] for r in resultados]))
        self.curvas.append({'interacoes': self.num_timesteps, 'retorno_validacao': media,
                            'progresso_m': float(np.mean([r['progresso_m'] for r in resultados])),
                            'saidas': sum(r['fora'] for r in resultados)})
        if media > self.melhor:
            self.melhor, self.melhor_passo = media, self.num_timesteps
            self.model.save(self.pasta / 'melhor.zip')
        escrever_csv(self.pasta / 'validacao.csv', self.curvas)
        print(f'{self.pasta.name}: {self.num_timesteps} interações | retorno val. {media:.3f}', flush=True)

    def _on_rollout_start(self):
        # Chamado após as atualizações da rodada anterior em ambos os algoritmos.
        if self.num_timesteps and self.num_timesteps % self.intervalo == 0:
            self.medir()

    def _on_step(self):
        for info in self.locals['infos']:
            if 'episode' in info:
                ep = info['episode']
                self.episodios.append({'interacoes': self.num_timesteps, 'retorno': ep['r'], 'passos': ep['l']})
        return True


def criar_modelo(nome, env, seed):
    comuns = dict(policy='MlpPolicy', env=env, seed=seed, device='cpu', gamma=.97, verbose=0,
                  policy_kwargs={'net_arch': [64, 64], 'activation_fn': torch.nn.Tanh})
    if nome == 'DQN':
        return sb3.DQN(**comuns, learning_rate=3e-4, buffer_size=20000, learning_starts=512,
                       batch_size=64, train_freq=4, gradient_steps=1, target_update_interval=512,
                       exploration_fraction=.5, exploration_final_eps=.05)
    return sb3.PPO(**comuns, learning_rate=3e-4, n_steps=128, batch_size=64, n_epochs=10,
                   gae_lambda=.95, clip_range=.2, ent_coef=.01)


def latencia(modelo, observacoes, entradas, referencia):
    for i in range(10):
        referencia.prever(entradas[i % len(entradas)])
        if modelo is not None:
            modelo.predict(observacoes[i % len(observacoes)], deterministic=True)
    linhas = []
    for i in range(100):
        obs = observacoes[i % len(observacoes)]
        entrada = entradas[i % len(entradas)]
        inicio = time.perf_counter_ns()
        referencia.prever(entrada)
        cnn_pronta = time.perf_counter_ns()
        if modelo is None:
            # Mesmo PD do comparador, sobre os valores representados na observação.
            erro, delta = float(obs[0]), float(obs[1]) * 2
            acao_pd(SimpleNamespace(erro=erro, anterior=erro - delta, dt=.1))
        else:
            modelo.predict(obs, deterministic=True)
        fim = time.perf_counter_ns()
        linhas.append({'amostra': i + 1, 'cnn_ms': (cnn_pronta - inicio) / 1e6,
                       'politica_ms': (fim - cnn_pronta) / 1e6, 'total_ms': (fim - inicio) / 1e6})
    return linhas


def amostras_latencia(referencia):
    env = AmbienteLinhaGym(referencia, DIVISOES['teste'])
    observacoes, entradas = [], []
    try:
        for pista in DIVISOES['teste']:
            obs, _ = env.reset(seed=2000 + pista, options={'pista': pista})
            for _ in range(4):
                observacoes.append(obs.copy())
                imagem = np.clip(env.simulacao.fisica._renderizar(), 0, 255).astype(np.uint8)
                entradas.append(preparar_entrada(imagem))
                obs, _, terminou, truncado, _ = env.step(acao_pd(env.simulacao))
                if terminou or truncado:
                    break
    finally:
        env.close()
    return observacoes, entradas


def relatorio(saida, resultados, latencias):
    linhas = ['# DQN, PPO e PD com referência CNN', '',
              '| Controlador | Retorno médio | Progresso médio (m) | Erro lateral (m) | Saídas de pista | Tempo parado |',
              '|---|---:|---:|---:|---:|---:|']
    resumos = {}
    for nome in ('PD', 'DQN', 'PPO'):
        grupo = [r for r in resultados if r['algoritmo'] == nome]
        media = {k: float(np.mean([r[k] for r in grupo])) for k in
                 ('retorno', 'progresso_m', 'erro_lateral_m', 'variacao_direcao', 'parado_pct', 'bloqueios_pct')}
        media.update(saidas=sum(r['fora'] for r in grupo), episodios=len(grupo))
        resumos[nome] = media
        linhas.append(f"| {nome} | {media['retorno']:.3f} | {media['progresso_m']:.3f} | "
                      f"{media['erro_lateral_m']:.4f} | {media['saidas']}/{len(grupo)} | {media['parado_pct']:.1f}% |")
    linhas += ['', 'PD é discretizado nas mesmas onze ações. Sua avaliação determinística é executada uma vez '
               'nas cinco pistas. DQN e PPO são avaliados por semente de treinamento nas mesmas cinco condições.', '',
               '| Agente | Semente de treino | Retorno médio no teste | Progresso médio (m) | Saídas de pista |',
               '|---|---:|---:|---:|---:|']
    for nome in ('DQN', 'PPO'):
        for seed in sorted({r['semente_treino'] for r in resultados if r['algoritmo'] == nome}):
            grupo = [r for r in resultados if r['algoritmo'] == nome and r['semente_treino'] == seed]
            linhas.append(f"| {nome} | {seed} | {np.mean([r['retorno'] for r in grupo]):.3f} | "
                          f"{np.mean([r['progresso_m'] for r in grupo]):.3f} | {sum(r['fora'] for r in grupo)}/{len(grupo)} |")
    linhas += ['',
               '| Controlador | CNN + política P50 (ms) | CNN + política P95 (ms) |', '|---|---:|---:|']
    for nome in ('PD', 'DQN', 'PPO'):
        medidas = [r['total_ms'] for r in latencias if r['algoritmo'] == nome]
        p50, p95 = np.percentile(medidas, [50, 95])
        linhas.append(f'| {nome} | {p50:.3f} | {p95:.3f} |')
    linhas += ['', 'Latência em CPU no computador registrado em experimento.json, com as mesmas entradas '
               'pré-processadas, dez chamadas de aquecimento e cem medições por política. Inclui inferência '
               'da CNN e escolha da ação. Pré-processamento, física, HTTP e serial ficam fora da medição.', '',
               'O horizonte é de 150 passos por padrão. Atingir esse limite é truncamento. '
               'A saída da pista é término. As métricas medem o desempenho no horizonte; sobreviver '
               'inclui casos parados. Os percentuais de tempo parado usam velocidade simulada menor que 0,005 m/s.', '',
               'Os modelos são selecionados pelo retorno de validação. O teste é consultado após selecionar '
               'todos os checkpoints. CNN, dinâmica e rótulos são sintéticos. A velocidade observada é ideal. '
               'A referência ficou congelada. A avaliação física depende de câmera e sensores calibrados.', '']
    (saida / 'RELATORIO.md').write_text('\n'.join(linhas), encoding='utf-8')
    return resumos


def desenhar_curvas(saida, execucoes):
    fig = Figure(figsize=(11, 4.5), layout='constrained')
    axes = fig.subplots(1, 2)
    for nome, cor in [('DQN', '#2761b1'), ('PPO', '#087e66')]:
        runs = [r for r in execucoes if r['algoritmo'] == nome]
        passos = [r['interacoes'] for r in runs[0]['curvas']]
        for ax, campo in zip(axes, ('retorno_validacao', 'progresso_m')):
            valores = np.array([[r[campo] for r in run['curvas']] for run in runs])
            media, desvio = valores.mean(0), valores.std(0)
            ax.plot(passos, media, label=nome, color=cor)
            ax.fill_between(passos, media - desvio, media + desvio, alpha=.18, color=cor)
            ax.set_xlabel('Interações de treino')
            ax.grid(alpha=.2)
    axes[0].set_ylabel('Retorno médio de validação')
    axes[1].set_ylabel('Progresso médio de validação (m)')
    axes[1].legend(frameon=False)
    fig.suptitle('Validação · média e desvio-padrão entre sementes')
    fig.savefig(saida / 'curvas.png', dpi=160)


def executar(args):
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    args.saida.mkdir(parents=True, exist_ok=False)
    if args.referencia is None:
        referencia = treinar_referencia(7)
        origem = 'treinada nesta execução, semente 7, 600 amostras, 250 atualizações'
    else:
        meta = json.loads((args.referencia / 'experimento.json').read_text(encoding='utf-8'))
        referencia = RedeLinha.carregar(args.referencia / 'referencia_sintetica.npz')
        if meta['contrato'] != CONTRATO or meta['hash_referencia_cnn'] != referencia.hash():
            raise ValueError('Referência incompatível com a simulação sintética')
        origem = str(args.referencia)
    referencia.salvar(args.saida / 'referencia_sintetica.npz')
    hash_cnn = referencia.hash()
    env_check = AmbienteLinhaGym(referencia)
    try:
        check_env(env_check, warn=True)
    finally:
        env_check.close()
    execucoes = []
    for seed in args.sementes:
        for nome in CLASSES:
            pasta = args.saida / f'{nome.lower()}_{seed}'
            pasta.mkdir()
            env = Monitor(AmbienteLinhaGym(referencia, max_passos=args.passos))
            callback = Validacao(referencia, pasta, args.avaliar_cada, args.passos)
            modelo = criar_modelo(nome, env, seed)
            inicio = time.monotonic()
            print(f'Treinando {nome}, semente {seed}', flush=True)
            try:
                modelo.learn(total_timesteps=args.interacoes, callback=callback)
                assert modelo.num_timesteps == args.interacoes
                callback.medir()  # último checkpoint após a última atualização
                if callback.episodios:
                    escrever_csv(pasta / 'episodios_treino.csv', callback.episodios)
                else:
                    (pasta / 'episodios_treino.csv').write_text('interacoes,retorno,passos\n', encoding='utf-8')
                execucoes.append({'algoritmo': nome, 'semente': seed, 'interacoes': modelo.num_timesteps,
                                   'checkpoint': callback.melhor_passo, 'retorno_validacao': callback.melhor,
                                   'treino_s': time.monotonic() - inicio, 'curvas': callback.curvas,
                                   'hiperparametros': {k: v for k, v in vars(modelo).items() if isinstance(v, (str, int, float, bool))}})
            finally:
                env.close()
    # Congela todos os checkpoints selecionados antes de consultar o teste.
    observacoes, entradas = amostras_latencia(referencia)
    resultados, latencias = [], []
    for nome, seed in [('PD', -1)] + [(r['algoritmo'], r['semente']) for r in execucoes]:
        modelo = None if nome == 'PD' else CLASSES[nome].load(args.saida / f'{nome.lower()}_{seed}' / 'melhor.zip', device='cpu')
        resultados.extend({'algoritmo': nome, 'semente_treino': seed, **r}
                          for r in avaliar(referencia, modelo, DIVISOES['teste'], args.passos, 2000))
        latencias.extend({'algoritmo': nome, 'semente_treino': seed, **r}
                         for r in latencia(modelo, observacoes, entradas, referencia))
    assert referencia.hash() == hash_cnn
    escrever_csv(args.saida / 'avaliacao.csv', resultados)
    escrever_csv(args.saida / 'latencia.csv', latencias)
    resumos = relatorio(args.saida, resultados, latencias)
    desenhar_curvas(args.saida, execucoes)
    manifesto = {'contrato': CONTRATO_GYM, 'hash_cnn': hash_cnn, 'origem_cnn': origem, 'acoes': ACOES.tolist(),
                 'observacao': ['erro_CNN', 'delta_erro_div_2', 'velocidade_div_0.11_em_menos1_mais1',
                                'idade_div_0.6_em_menos1_mais1_saturada', 'memoria_vigente_menos1_mais1',
                                'direcao_pedida_anterior', 'velocidade_pedida_anterior_em_menos1_mais1'],
                 'divisoes': DIVISOES, 'config_pd': {k: getattr(cfg, k) for k in ('KP', 'KD', 'VEL_BASE', 'VEL_MAX')},
                 'python': platform.python_version(), 'plataforma': platform.platform(), 'torch': torch.__version__,
                 'stable_baselines3': sb3.__version__, 'gymnasium': gymnasium.__version__, 'numpy': np.__version__,
                 'opencv': cv2.__version__, 'parametros': {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
                 'execucoes': execucoes, 'resumos': resumos,
                 'sha256_fontes': {str(p.relative_to(RAIZ)): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in (Path(__file__), RAIZ / 'aprendizado/ambiente_gym.py',
                                             RAIZ / 'aprendizado/rl_simulado.py', RAIZ / 'aprendizado/simulador.py',
                                             RAIZ / 'aprendizado/cnn.py', RAIZ / 'aprendizado/dados.py',
                                             RAIZ / 'visao/detector.py', RAIZ / 'controle.py', RAIZ / 'config.py')},
                 'sha256_checkpoints': {str(p.relative_to(args.saida)): hashlib.sha256(p.read_bytes()).hexdigest()
                                       for p in args.saida.glob('*/melhor.zip')}}
    gravar_json(args.saida / 'experimento.json', manifesto)
    print((args.saida / 'RELATORIO.md').read_text(encoding='utf-8'), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--saida', type=Path, required=True)
    ap.add_argument('--referencia', type=Path, help='pasta do experimento Q-learning com a referência CNN sintética')
    ap.add_argument('--sementes', type=int, nargs='+', default=[7, 17, 27])
    ap.add_argument('--interacoes', type=int, default=8192)
    ap.add_argument('--avaliar-cada', type=int, default=2048)
    ap.add_argument('--passos', type=int, default=150)
    args = ap.parse_args()
    if (args.saida.exists() or args.passos < 1 or args.interacoes < 128 or args.avaliar_cada < 128
            or args.interacoes % 128 or args.avaliar_cada % 128 or min(args.sementes) < 0
            or len(args.sementes) != len(set(args.sementes))):
        ap.error('use pasta nova, sementes distintas, passos positivos e orçamentos múltiplos de 128')
    executar(args)


if __name__ == '__main__':
    main()
