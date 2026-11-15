# Correção de iluminação e seleção dos segmentos para rotulagem

O usuário relatou sugestões nos cantos, longe da fita. Foram examinados o lote
atual e as revisões disponíveis, sem alterar imagens ou rótulos. A comparação
usa 44 frames marcados como visíveis/parciais de vídeos de treino e validação;
os vídeos reservados ao teste da CNN ficaram fora. As revisões foram congeladas
em revisoes_snapshot.jsonl, incluindo as anteriores com auxílio OpenCV.

## Alterações

- Redução proporcional até 640 pixels no lado maior, preservando coordenadas.
- Estimativa do fundo com fechamento morfológico elíptico 51×51 e divisão do cinza
  pelo fundo estimado. Isso reduz variações de iluminação antes do limiar.
- Suavização 3×3, limiares escuros e Otsu limitado; abertura para ruído fino.
- A seleção anterior favorecia quantidade de fragmentos: muitos pequenos pedaços
  de rejunte podiam vencer a fita. A nova seleção pondera suporte de pixels,
  verifica espessura entre segmentos e admite vãos maiores do tracejado.
- Um segmento bem definido pode vencer uma sequência de ruído. A localização
  perto da borda, sozinha, não é motivo para descartar a linha.
- A imagem tratada pode ser vista na interface; a original e suas coordenadas
  continuam preservadas. O rótulo só é salvo após confirmação humana.

## Comparação exploratória

Em cada frame foram amostradas 25 alturas dentro da trajetória humana; o erro é
calculado somente nas alturas cobertas também pela sugestão. Por isso a cobertura
deve ser lida junto com o erro. MAE 0,1 equivale a 5% da largura; não é acurácia.

| Estratégia | Frames com sobreposição | MAE médio por frame | Cobertura média das alturas humanas |
|---|---:|---:|---:|
| Algoritmo anterior | 43 | 0,1187 | 77,8% |
| Seleção nova, sem correção de iluminação | 44 | 0,0142 | 86,6% |
| Seleção nova e iluminação corrigida | 44 | 0,0200 | 92,7% |
| Seleção nova e CLAHE | 44 | 0,0583 | 93,6% |

Comparando estritamente as mesmas alturas em 40 imagens, o MAE do algoritmo
anterior foi 0,0712 e o da versão com iluminação corrigida foi 0,0197.

Grande parte da melhora veio da seleção geométrica, não apenas do tratamento.
A correção de iluminação estendeu a cobertura, mas também prejudicou algumas
imagens: em video_04_frame_00073.jpg, associou parte do fundo à fita. Portanto
ela não é universalmente melhor. O botão **Tentar sem correção** mantém a seleção
geométrica nova e gera uma alternativa para a imagem atual. **Recalcular sugestão**
volta ao tratamento padrão da sessão. Nenhuma alternativa é salva automaticamente.

Em video_07_frame_00084.jpg, a versão anterior seguia o rejunte direito. A nova
sugestão acompanha os segmentos principais. Os diagnósticos têm cinco painéis:
marcação humana, sugestão anterior, sugestão nova, cinza tratado e máscara usada.
Verde = humano; vermelho = OpenCV. Erros restantes precisam de correção humana.

O algoritmo foi ajustado durante esta análise. Não é um teste independente;
as revisões assistidas não são anotações cegas ao algoritmo. Não extrapolar
esses números para os 1032 frames ou para a câmera real. Não foi treinada outra CNN.

## Execução

Raspberry Pi, terminal no desktop/VNC, ambiente virtual do projeto:

```bash
cd /home/carrasco/Downloads/robo_seguidor
.venv/bin/python tools/rotular_linha.py --lote 30
```

Fechar a janela anterior antes de executar. Usar **Alternar original/tratada**
para examinar o tratamento. O lote e as marcações já salvas são preservados.

Para reproduzir a comparação em uma pasta nova com a cópia histórica do algoritmo:

```bash
OPENBLAS_NUM_THREADS=1 .venv/bin/python tools/comparar_sugestoes.py --revisoes dataset_pista/resultados/preprocessamento_02/revisoes_snapshot.jsonl --anterior dataset_pista/resultados/preprocessamento_02/fonte_sugestao_v1.py --saida dataset_pista/resultados/preprocessamento_03
```

comparacao.json contém métricas por imagem e cobertura; fontes do algoritmo e do
script foram copiadas para rastreabilidade. Quinze testes da assistência e dez
testes de dataset passaram. O teste da interface usa widgets simulados: aparência
e cliques na janela real ainda precisam ser conferidos no desktop/VNC.
