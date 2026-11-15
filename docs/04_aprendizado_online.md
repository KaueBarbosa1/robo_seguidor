# 04 — Aprendizado do carrinho na própria pista

> **Estado de validação (leia primeiro).** Tudo aqui foi testado apenas com (a) testes unitários, (b) o simulador
> do Arduino e (c) um **simulador sintético** de pista que escrevi, com suposições minhas. **Nada foi treinado
> nem validado no carrinho ou na pista física.** Nenhum número do simulador vale como desempenho real.

## 1. Limites reais do hardware (avaliados antes de projetar)

| Item | Limite | Consequência no projeto |
|---|---|---|
| Câmera: OV7670 sem FIFO no Arduino | 16 tons de cinza (4 bits), ~2,5 quadros/s (QQVGA 160x120), captura lenta de ~0,4 s por quadro (deformação por *rolling shutter*), pixels/linhas perdidos na serial, sem controle de exposição | Imagem fraca e lenta, **ainda sem teste real**: a CNN usa quadros de 1 canal 40x80 e a padronização por imagem compensa brilho; ritmo de decisão limitado pela câmera |
| Ritmo do aprendizado | `APR_PERIODO_MIN_S = 0,4 s` (2,5 passos/s) | É exatamente o ritmo da OV7670: um passo por quadro novo |
| Latência malha fechada | captura + processamento + resposta do motor: ainda centenas de ms | Sem mérito por ação isolada: recompensa por tentativa |
| Arduino UNO | Faz a ponte da OV7670 (imagem pela serial a 1 Mbaud) e aciona o L298N; com a câmera, ultrassom e encoders ficam desligados (sem odometria para o aprendizado); a divisão final ainda será definida | Sem memória para inferência: o aprendizado e a inferência ficam no Pi 5 |
| Pi 5 | Treino de 55 mil parâmetros em NumPy: ~20 ms/passo (lote 32) num sandbox de 2 núcleos; inferência em poucos ms | Dá para treinar **entre** tentativas (segundos), não durante |
| Auto-reposição | O carrinho **não consegue se recolocar** na pista | Humano reposiciona e diz "siga"; poucas tentativas por hora → eficiência de amostra importa |

O simulador sintético (`aprendizado/simulador.py`) imita as limitações da OV7670 (4 bits, 2,5 quadros/s, captura de 0,4 s):
serve para testar os mecanismos, não para prever o desempenho na pista real.

## 2. Por que não aprendizado por reforço puro

RL puro precisaria de milhares de episódios com reinício automático, exploração insegura (o carrinho tem de sair
da pista para aprender) e crédito por ação, com 2,5 quadros/s e meio segundo de atraso. Aqui isso é inviável.

**Escolha: imitação online com correção estilo DAgger.** O detector OpenCV existente (`DetectorLinha`) é o
*professor*; a CNN (*aluno*, pesos aleatórios, sem pré-treino) aprende **só com o que o próprio carrinho
gravou** nas suas tentativas. Em cada tentativa quem dirige é o professor, o aluno com portão, ou o aluno
livre, conforme o **nível de autonomia**; os estados visitados pelo aluno (inclusive os ruins) entram no treino,
o que corrige o desvio de distribuição da imitação pura. A pista tracejada é tratada assim: nos vãos curtos
o erro lateral é **interpolado com o que o carrinho viu depois** (`APR_MAX_BURACO`); vãos longos ficam sem rótulo.

## 3. Como o sistema sabe se uma ação/tentativa foi boa ou ruim

Sinais independentes da CNN (`seguranca.py`): professor (linha perdida, erro grande, oscilação), encoders
(parado), ultrassom (obstáculo), relógio (quadro velho, tempo máximo) e, opcional, sensor IR de piso.
- **Por tentativa:** `pontuacao = sobrevida − 0,2·min(1, erro_médio)`. Sobrevida = fração do tempo máximo vivida sem falha.
- **Por ação:** não há mérito individual. Cada quadro recebe como alvo a direção do professor; os 8 quadros antes
  de uma falha pesam ×2.
- **Limitação importante:** a detecção de "saiu da pista" usa o professor. Se o professor tiver falso positivo
  em piso liso, a falha passa despercebida. Mitiguei exigindo contraste real entre a mancha e o piso
  (`detector.py`), mas **o sensor IR sob o chassi é o único sinal realmente independente e é recomendado**.

## 4. Fluxo de uma tentativa e do ciclo

1. Voz "siga" → `ThreadAprendizado` escolhe o modelo (professor, campeão ou candidato, alternando) e o nível.
2. A cada quadro: detector → CNN → `PoliticaAprendiz` (portão: o aluno só dirige se concordar com o professor
   dentro de `APR_PORTAO[nível]`; nos vãos dirige se `p_visível ≥ 0,5`) → `Supervisor` → grava quadro+ação → publica a ação.
3. `ThreadControle` executa a ação (único que fala com o Arduino; ação velha ou obstáculo = motores parados;
   "pare" de voz tem prioridade absoluta e cancela a ação).
4. Fim: resumo gravado (`episodios/ep_NNNNN/{frames.u8, passos.jsonl, meta.json}`), resultado registrado.
5. Entre tentativas: treino (primeira CNN com ≥600 quadros rotulados de treino e ≥3 episódios; depois candidatos a cada
   ≥300 quadros novos, herdando do campeão, e de vez em quando do zero).
6. Humano reposiciona e diz "siga".

## 5. Medir progresso, interromper, preservar versões

- **Progresso:** `python tools/aprendizado_relatorio.py` mostra tentativas, falhas, pontuação por nível e métricas
  de treino, validação e teste. Treino e validação usam a mesma perda (Huber para direção e BCE para visibilidade).
  O melhor modelo é escolhido pela validação; o treino para depois de quatro avaliações sem melhora, com mínimo
  de 100 passos. O teste só é calculado no fim e não participa da escolha do modelo.
- A divisão é por ID de episódio e não muda quando chegam dados novos: episódios 1, 5, 10... vão para validação;
  2, 6, 11... vão para teste; os demais vão para treino. Com menos de três episódios, não há teste. Essa divisão
  não garante variedade de pista ou iluminação. Para medir generalização, reserve episódios de outra sessão.
  Episódios usados por versões antigas também não servem como teste independente dessas versões.
- Os indicadores de operação são falhas por nível, autonomia (tempo em que a CNN dirigiu) e intervenções do portão.
  Uma pontuação perto de 0,95 indica principalmente que a tentativa terminou sem falha.
- **Interrupção:** `sem_quadros`, `obstaculo`, `fora_da_pista` (IR), `linha_perdida`, `divergencia`,
  `oscilacao`, `parado`, `concluida` (tempo máximo), `parada_manual` (voz). As três últimas
  não contam como falha; `obstaculo`/`parado`/`parada_manual`/`sem_quadros` ficam fora das comparações.
- **Níveis** (`APR_NIVEIS`/`APR_PORTAO`): sobe após 3 tentativas com ≤20% de falhas; desce após 2 falhas seguidas
  causadas pela CNN. O nível só muda fora de um A/B.
- **Promoção:** A/B com tentativas alternadas no mesmo nível, bootstrap. Promove com ≥80% de chance de ser melhor,
  ou, no limite de tentativas, se for **não inferior** (IC95 > −0,05) **e** reduzir ≥15% o erro de validação
  offline (episódios inteiros separados). Caso contrário o campeão fica.
- **Rollback:** (a) falhas seguidas da CNN logo após uma promoção → volta ao campeão anterior; (b) queda da
  pontuação do campeão (mesmo nível) > 0,25 em relação à linha de base; (c) pesos corrompidos (hash) → volta ao anterior.
  Versões são imutáveis em `modelos/vNNNN/`, escritas de forma atômica; `APR_MANTER_VERSOES` limita o espaço
  mas nunca apaga o campeão nem a cadeia de anteriores.
- **Cuidado de leitura:** validação e teste crescem com os episódios e sua composição pode mudar; métricas entre
  versões diferentes não são diretamente comparáveis. O teste é um indicador exploratório até haver episódios
  de sessões independentes reservados para esse fim.

## 6. O que foi e o que NÃO foi validado

Validado (em código, sem hardware): gradientes da CNN contra diferenças finitas; reparo de rótulos; regras do
supervisor; portão da política; promoção/descarte/nível/rollback; persistência e recuperação de arquivos
corrompidos; fiação voz→aprendizado→controle→Arduino simulado (32 testes unitários + 1 de integração).
No simulador sintético: o ciclo completo roda (primeira CNN do zero, subida de nível, A/B, promoção).

**NÃO validado:** qualquer treino na pista real; a OV7670 e o firmware com câmera no UNO real (compilado para AVR, mas nunca executado); a
conexão Pi⇄Arduino definitiva; motores, bateria, encoders e ultrassom reais; o
desempenho do detector sobre o tracejado real; ruído/iluminação reais; tempo de treino no Pi 5 de verdade.

## 7. Checklist quando a pista chegar

1. Ligar a câmera (`docs/01_ligacao_camera.md` e `docs/02_bringup_camera.md`), focar e conferir a imagem com `tools/ver_camera.py` e ajustar `ROI_INICIO`,
   `LINHA_ESCURA`, `CONTRASTE_MIN`, `AREA_MIN`.
2. **Rodar só com o professor** (`APRENDIZADO_ATIVO=True` e nenhum modelo) algumas voltas: medir o histograma do
   comprimento dos vãos do tracejado (em quadros) e ajustar `APR_MAX_BURACO`; verificar a velocidade
   (`APR_VEL`, `APR_GANHO_DIRECAO`) e o ganho (`APR_GANHO_PROF`). Os valores atuais são suposições.
3. Conferir se o professor completa a pista de forma confiável: se ele falha, o aluno herda a falha.
4. Calibrar `APR_TEMPO_MAX_S` (uma volta + folga), `APR_IDADE_MAX_QUADRO_S` e os limiares do supervisor.
5. Considerar o **sensor IR de piso** (retornar `sobre_pista()` em `AmbienteReal`).
6. Só então subir a autonomia, acompanhando `tools/aprendizado_relatorio.py`; começar com `APR_MIN_QUADROS_PRIMEIRO` alto.

## 8. Arquivos

`aprendizado/`: `cnn.py` (rede e Adam em NumPy), `dados.py` (gravação, rótulos, buffer), `seguranca.py`,
`politica.py`, `avaliacao.py`, `versoes.py`, `treino.py`, `ciclo.py`, `robo_real.py` (adaptador e thread),
`simulador.py` (**sintético**). `tools/aprendizado_simulado.py`, `tools/aprendizado_relatorio.py`,
`tests/test_aprendizado.py`, `tests/test_integracao_robo.py`. Ativar: `APRENDIZADO_ATIVO = True` em `config.py`.
