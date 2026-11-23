# RL com referência CNN

A orientação recebida em 23/11/2026 coloca a política de Reinforcement
Learning na escolha das ações. A CNN fornece percepção. A camada de controle
aplica os limites e as paradas antes de enviar os comandos ao Arduino.

## Protótipo em simulação

`tools/treinar_rl_simulado.py` exercita essa divisão com Q-learning tabular
em NumPy. A primeira versão usa ações discretas para tornar inspecionáveis
os valores aprendidos. São onze ações, incluindo parar e combinações de cinco
direções com dois fatores de velocidade. O algoritmo e as discretizações são
escolhas iniciais para experimentar o ciclo de recompensa.

O protótipo reutiliza `PistaSintetica`, a dinâmica de `AmbienteSimulado`,
`RedeLinha`, seu pré-processamento legado e o otimizador Adam. A câmera
simulada usa a renderização 160×120 do simulador antigo, com ruído e perdas
de quadros. O passo de decisão é 0,1 s. A dinâmica usa velocidade máxima
de 0,11 m/s, rotação de 1,6 rad/s e atraso dos motores de 0,3 s, todos
hipotéticos. A velocidade observada é a velocidade ideal do simulador.

Antes do RL, uma CNN de referência é treinada em poses sintéticas de dez
pistas. A saída de direção recebe um alvo geométrico a 10 cm à frente,
normalizado pela meia largura de 12 cm da vista. A visibilidade recebe o
resultado do OpenCV nas imagens sintéticas. A CNN fica congelada no treino
de Q-learning. Os pesos gerados têm semântica própria dessa simulação.

O agente recebe cinco observações discretizadas.

- Previsão da CNN.
- Variação da previsão desde a observação anterior.
- Velocidade simulada.
- Tempo desde a última previsão aceita pela saída sintética de visibilidade.
- Índice da ação anterior.

A posição real na pista participa apenas da recompensa e da avaliação.
A recompensa por passo soma 20 vezes o progresso assinado em metros,
desconta 0,1 vezes o erro lateral relativo ao limite de 10 cm ao quadrado,
desconta 0,01 vezes a variação de direção e desconta cinco ao sair da pista.
Usar progresso assinado penaliza retrocesso. O controle simulado reduz
a velocidade durante perda breve da referência e para após 0,6 s.

Os episódios terminam ao sair mais de 10 cm da trajetória ou atingir o
limite de passos. O objetivo desse ensaio é o retorno no horizonte finito.
As contagens de episódios sem saída de pista incluem casos parados. Por isso
o relatório também mede progresso, erro lateral e suavidade, em vez de
considerar sobrevivência uma conclusão de percurso.

## Executar e conferir

Treinamento somente com o carrinho parado. Em terminal do projeto com
NumPy e OpenCV disponíveis, rode o comando abaixo com uma pasta nova.

```bash
OPENBLAS_NUM_THREADS=1 .venv/bin/python tools/treinar_rl_simulado.py \
  --saida dataset_pista/resultados/rl_cnn_simulado_01
```

O padrão treina a referência em 600 amostras e 250 atualizações. Em seguida,
treina Q-learning por 100 episódios com até 150 passos cada. As pistas
0 a 9 são de treino, 10 a 12 são de validação e 20 a 24 são de teste.
O retorno médio na validação seleciona o checkpoint a cada dez episódios.
O teste é executado depois dessa seleção. O comparador PD usa os ganhos
do projeto e tem sua saída aproximada para as mesmas onze ações discretas.
O comparador exercita direção e velocidade sobre a mesma referência CNN.

Os arquivos são `referencia_sintetica.npz`, `politica_q.npz`, `treino.csv`,
`avaliacao.csv`, `experimento.json` e `RELATORIO.md`. O checkpoint da política
guarda o identificador de contrato, as ações e o hash da referência CNN.
As métricas incluem retorno, progresso, erro lateral, saídas de pista,
variação de direção e bloqueios por previsão vencida.

## Primeiro ensaio de software em 23/11/2026

Com os parâmetros padrão e semente 7, a política selecionada na validação
produziu os seguintes valores nas cinco pistas reservadas ao teste.

| Política | Retorno médio | Progresso médio | Saídas de pista | Erro lateral médio |
|---|---:|---:|---:|---:|
| PD discretizado | 13,848 | 0,707 m | 0/5 | 0,0072 m |
| Q-learning | 0,321 | 0,361 m | 1/5 | 0,0537 m |

O PD teve melhor desempenho nesse ensaio. O retorno de validação do agente
oscilou e caiu nas últimas rodadas. A seleção pela validação preservou um
checkpoint anterior. Esse comportamento pede investigar discretização,
exploração e representação temporal antes de promover uma política. A
avaliação usa uma única semente de treino e cinco pistas sintéticas. Ela
exercita o pipeline e orienta experimentos posteriores em simulação.

## Comparação entre DQN, PPO e PD

`aprendizado/ambiente_gym.py` disponibiliza a mesma dinâmica, recompensa,
referência CNN e onze ações discretas pela interface Gymnasium. O vetor
de observação contém sete valores limitados a `[-1, 1]`, incluindo previsão,
variação da previsão, velocidade simulada, idade, memória vigente e direção
e velocidade pedidas no passo anterior. A geometria real da pista aparece
na recompensa e nas métricas. A referência CNN fica congelada.

Saída de pista encerra o episódio com `terminated=True`. Atingir o limite
de passos gera `truncated=True`. O Stable-Baselines3 pode assim usar o valor
da observação final para bootstrap nos cortes por tempo. O protótipo tabular
anterior conserva sua interface e seus registros históricos. O comparador
Gymnasium recebe observações contínuas normalizadas.

O ensaio usa Stable-Baselines3 para DQN e PPO, com redes de duas camadas de
64 unidades, ativação tanh, desconto 0,97 e taxa de aprendizado 0,0003.
As particularidades de cada algoritmo são as seguintes.

| Parâmetro | DQN | PPO |
|---|---|---|
| Memória de transições | 20.000 | 128 passos por rodada |
| Início das atualizações | após 512 interações | após 128 interações |
| Lote | 64 | 64 |
| Atualizações | uma a cada quatro interações | dez épocas por rodada |
| Rede alvo | atualização a cada 512 interações | estimador de valor da própria política |
| Exploração | epsilon decresce até 0,05 na primeira metade | bônus de entropia 0,01 |

Por padrão são três sementes de treino, 7, 17 e 27, e exatamente 8.192
interações por algoritmo e semente. A avaliação de validação ocorre após
as atualizações, a cada 2.048 interações e ao final. Cada checkpoint é
selecionado pelo retorno médio nas mesmas três pistas de validação. Todos
os checkpoints são selecionados antes de executar o teste nas cinco pistas
reservadas. O PD discretizado é avaliado uma vez nessas mesmas condições.

Treinamento somente com o carrinho parado. Instale as dependências opcionais
no ambiente de experimentos e use uma pasta nova para a saída.

```bash
.venv/bin/python -m pip install -r requirements-rl.txt
OPENBLAS_NUM_THREADS=1 .venv/bin/python tools/comparar_agentes_rl.py \
  --saida dataset_pista/resultados/comparacao_dqn_ppo_01
```

O comando treina uma única CNN sintética de referência com os parâmetros
do primeiro ensaio e a reutiliza em todos os agentes. Para usar a referência
de um ensaio tabular já existente, acrescente
`--referencia dataset_pista/resultados/rl_cnn_simulado_01`. O contrato e
o hash são conferidos ao carregar. `--interacoes` e `--avaliar-cada`
aceitam múltiplos de 128, permitindo orçamento igual para DQN e PPO.

Cada pasta de agente e semente contém `melhor.zip`, `validacao.csv` e
`episodios_treino.csv`. A pasta principal guarda a CNN, `avaliacao.csv`,
`latencia.csv`, `curvas.png`, `RELATORIO.md` e `experimento.json` com versões,
hiperparâmetros, configuração do PD e hashes de fontes e checkpoints.
As curvas mostram média e desvio-padrão da validação entre sementes.

O relatório mede retorno, progresso, erro lateral, saídas da pista,
tempo parado, bloqueios e variação de direção. O tempo parado usa
velocidade simulada abaixo de 0,005 m/s. A latência usa as mesmas entradas
pré-processadas para todos os agentes, com dez chamadas de aquecimento e
cem medições por política salva. Ela inclui a inferência da CNN e a escolha
da ação, em CPU com uma thread do PyTorch. A plataforma do ensaio aparece
no manifesto. A medição na Raspberry com câmera e sensores segue pendente.

Esses hiperparâmetros e o orçamento inicial permitem uma comparação
exploratória. A dinâmica continua hipotética, as pistas vêm do gerador
sintético existente e a velocidade observada é ideal. O teste não deve
ser reutilizado para escolher hiperparâmetros. Novas rodadas de ajuste
precisam de validação e reserva de novos cenários para avaliação final.

Referências de implementação no [Gymnasium](https://gymnasium.farama.org/api/env/),
[DQN](https://stable-baselines3.readthedocs.io/en/master/modules/dqn.html) e
[PPO](https://stable-baselines3.readthedocs.io/en/master/modules/ppo.html).

### Ensaio de 23/11/2026

Executados seis treinos, três sementes por algoritmo, cada um com 8.192
interações. A referência do ensaio tabular foi reutilizada e seu hash
permaneceu igual ao final. O teste usou as mesmas cinco pistas e os mesmos
estados iniciais por política. Os agregados DQN/PPO têm quinze episódios
por agente, correspondentes às três políticas treinadas sobre cinco pistas.

| Controlador | Retorno médio | Progresso médio | Erro lateral médio | Saídas | Tempo parado |
|---|---:|---:|---:|---:|---:|
| PD discretizado | 13,740 | 0,704 m | 0,0092 m | 0/5 | 0,0% |
| DQN | 21,378 | 1,189 m | 0,0323 m | 0/15 | 0,0% |
| PPO | 13,350 | 0,926 m | 0,0472 m | 2/15 | 16,1% |

O DQN apresentou maior retorno e progresso médio neste orçamento, junto
com maior erro lateral que o PD. As três sementes de DQN ficaram entre
1,154 e 1,224 m de progresso médio. PPO teve 1,363 m na semente 7,
1,242 m na 17 e 0,172 m na 27. A semente 27 concentrou as duas saídas
de pista do PPO. Os retornos de validação oscilaram em ambos os algoritmos.
A seleção pela validação preservou checkpoints anteriores ao fim do treino
em parte das execuções.

A mediana de CNN mais escolha da ação na CPU Windows foi 0,456 ms para
PD, 0,710 ms para DQN e 0,882 ms para PPO, sobre entradas previamente
processadas. São medidas do computador deste ensaio. A captura e o
desempenho integrado na Raspberry permanecem pendentes.

O teste de ponta a ponta exerceu treino e recarga dos modelos, além da
avaliação pelo checkpoint persistido. Treze testes direcionados de ambiente,
CNN, persistência e Q-learning passaram. Verificador Stable-Baselines3,
contagem de interações e hashes dos checkpoints/fontes também conferidos.

## Etapas físicas e evolução

O fechamento de 22/11 registra zero bytes recebidos do Uno na Raspberry.
A enumeração de portas COM neste Windows não identifica o Uno nem esclarece
essa falha. É preciso verificar alimentação, RESET e fios D0/D1 no conjunto,
e obter telemetria recente antes de avaliar rodas e sensores.

A próxima integração depende da coleta da ESP32-CAM montada, definição do
contrato de percepção e validação da CNN nas imagens reais. A referência de
três alturas e validade supervisionada continua proposta. O estado real do
RL deverá incorporar velocidades medidas, idade e validade dos sensores e
distâncias do ultrassom. Recompensa e término no hardware precisam de critérios
observáveis, independentes o suficiente para reconhecer falhas da própria CNN.

Após avaliar a política em pistas simuladas novas e diferentes sementes de
treino, executar inferência sem rodas para medir idade das observações e
latência. A integração com o escritor único dos motores deve conservar voz,
parada manual, watchdogs e guardas de câmera, encoder e ultrassom. O contorno
de obstáculos requer ambiente, ações, recompensa e avaliação adicionais.
