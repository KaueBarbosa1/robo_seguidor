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
