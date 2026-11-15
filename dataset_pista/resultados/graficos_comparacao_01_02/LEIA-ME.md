# Gráficos para a apresentação

Abra graficos_cnn.pdf para ver os seis gráficos. PNGs servem para slides; SVGs preservam qualidade vetorial.

Sugestão: apresentar 01_resumo, 04_erros_por_imagem e 06_dados_por_video; usar 02_curvas_treinamento para explicar a diferença entre erro de treino e validação.

A mesma CNN foi treinada do zero com 24 e 58 imagens. A avaliação usa os mesmos 10 frames de validação e 9 de teste. MAE não é acurácia: 3,6% da largura de erro médio não significa 96,4% de acerto. O erro médio de teste diminuiu, mas só quatro dos nove frames melhoraram. As novas imagens são de um vídeo; o teste já foi consultado na exploração, sem validação física nem avaliação da saída de visibilidade.

Os gráficos leem os arquivos existentes e não treinam ou alteram o modelo. Os valores agregados foram conferidos contra predicoes.csv, e os alvos/IDs de avaliação foram comparados. Não apresentam intervalos de confiança nem prova de generalização.

Na Raspberry Pi, terminal na pasta do projeto com a .venv, para reproduzir em outra pasta:

```bash
.venv/bin/python tools/graficos_cnn.py --saida dataset_pista/resultados/graficos_reproducao
```
