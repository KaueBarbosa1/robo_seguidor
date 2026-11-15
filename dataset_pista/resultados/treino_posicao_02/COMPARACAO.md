# Comparação do primeiro e segundo treino

87 imagens únicas revisadas, 42 novas em relação às 45 iniciais. As 42 novas são do primeiro vídeo.

77 imagens utilizáveis: **58 treino, 10 validação e 9 teste**. Dez ficaram fora: sete não cobrem a altura de referência, duas ambíguas e uma ausente. Nenhum rótulo foi extrapolado.

As 19 imagens de validação/teste, suas marcações, os recortes e os alvos são exatamente iguais nos dois experimentos (conferidos por igualdade dos tensores e dos registros). As 24 imagens de treino antigas foram preservadas; entraram 34 novas imagens utilizáveis.

Mesma RedeLinha de 55.090 parâmetros, mesmo recorte a 75% da altura, entrada 1×40×80, Huber só para posição, Adam com LR=0,001, lote oito, 300 atualizações, semente sete, espelho/ruído iguais. Ambos começam com pesos aleatórios. Checkpoint selecionado por MSE de validação; teste avaliado depois.

| Medida | Primeiro treino | Segundo treino |
|---|---:|---:|
| Imagens de treino | 24 | 58 |
| MAE validação (10 imagens) | 0.1403 | 0.1026 |
| MAE teste (9 imagens) | 0.1373 | 0.0725 |
| MSE teste | 0.0489 | 0.0096 |
| Pior erro de teste | 0.5963 | 0.2462 |
| Checkpoint selecionado | Passo 170 | Passo 130 |

O erro médio do teste caiu de **6,9% para 3,6% da largura**, redução relativa de 47.2% no MAE. **Isso não significa 96,4% de acurácia.** O pior erro atual ainda corresponde a 12,3% da largura. Melhorou em 4 das nove imagens de teste; não houve melhora em todas.

A melhora é observada nesta execução e neste conjunto pequeno. O teste já foi consultado durante a exploração; não é teste final intocado. As novas imagens são consecutivas de um só vídeo: 39 das 58 imagens de treino vêm dele. Não afirmar generalização para outros ambientes/ESP32-CAM nem atribuir o ganho só à quantidade de dados: a distribuição de posições e a forma de rotular também mudaram.

O orçamento de treino ficou em 300 atualizações nos dois casos; não foi igualado o número de épocas. O tratamento novo do OpenCV auxilia as marcações e não foi aplicado à entrada da CNN. A visibilidade continua sem supervisão neste experimento, e ausente/ambíguo ficam fora da regressão de posição. Não foi ativado nenhum modelo no carrinho.

## Arquivos para visualizar

- `comparacao_teste.jpg`: todas as nove imagens de teste, antes à esquerda e depois à direita em cada par.
- `previsoes/`: 77 imagens com previsão do novo modelo.
- `novas_marcacoes.jpg`: montagem das 42 novas marcações.
- `comparacao.json`: comparação numérica e erros por imagem.
- `historico.csv`: curva numérica de treino/validação.
- `pesos_posicao.npz`: pesos do segundo experimento, uso offline.
- `revisoes_origem.jsonl` e `fontes/`: dados de origem e fontes preservados para reprodução.

## Reproduzir

Raspberry Pi, terminal na pasta do projeto, usando a .venv e outra pasta de saída:

```bash
OPENBLAS_NUM_THREADS=1 .venv/bin/python tools/treinar_fotos_linha.py --revisoes dataset_pista/resultados/treino_posicao_02/revisoes_origem.jsonl --saida dataset_pista/resultados/treino_posicao_02_reproducao
```
