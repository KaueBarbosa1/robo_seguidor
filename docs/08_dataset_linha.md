# Preparação offline da CNN de linha

Esta etapa usa os JPGs existentes. Não precisa da ESP32-CAM, do Arduino ou dos
motores. O estudo inicial foi feito sem rótulos; depois das marcações humanas foi
executado um primeiro treino experimental, descrito ao final deste guia.
Motores, sensores, Bluetooth, firmware e configurações não foram alterados.

## Estudo executado

Ferramenta: `tools/estudar_linha.py`. Saída inicial:
`dataset_pista/resultados/estudo_01/`.

- 45 frames: cinco por vídeo, incluindo início, meio e fim.
- 45 imagens de diagnóstico, dez painéis por imagem.
- 1.215 combinações medidas: três thresholds × três morfologias × três ROIs × 45 frames.
- Redução proporcional para altura 640; imagens verticais não foram deformadas para 80×40.
- Threshold fixo 100, Otsu e adaptativo gaussiano (bloco 31, constante 7).
- Sem morfologia, abertura 3×3 e fechamento 3×3; ROIs candidatas iniciando em 0%, 35% e 50%.
- Threshold calculado na imagem inteira, seguido do recorte da máscara para a comparação de ROI.
- Componentes com área mínima 20 pixels na resolução de análise.
- `manifesto.json` registra parâmetros, configuração do detector existente, versões e hashes.
- `comparacao.csv` contém medições de máscaras, não rótulos nem métricas de acurácia.

As nove imagens correspondentes ao meio dos vídeos foram inspecionadas visualmente
nos diagnósticos. Isso não representa uma revisão de todas as 45 imagens ou dos 1032 frames.

## Achados concretos

1. `video_03_frame_00026.jpg`: os thresholds separam os dois traçados pretos;
   o maior contorno do detector atual inclui parte do cruzamento. Threshold sozinho
   não informa qual trajetória seguir.
2. `video_04_frame_00048.jpg`: Otsu calculado na imagem inteira usa limiar 178 e
   classifica grande região do piso como primeiro plano. A referência do detector
   atual, que recalcula Otsu na ROI, também seleciona uma região incorreta nessa amostra.
3. `video_06_frame_00067.jpg`, `video_07_frame_00042.jpg` e
   `video_08_frame_00048.jpg`: a referência inclui rejuntes e desloca o centro estimado.
4. `video_05_frame_00107.jpg`: fixo 100 e Otsu separam visualmente os segmentos
   nesta amostra; o adaptativo destaca contornos e rejuntes. Não é evidência de desempenho geral.
5. Nas 45 máscaras completas sem morfologia, a fração de primeiro plano varia de
   0,96% a 11,94% com fixo, 3,07% a 84,82% com Otsu e 3,59% a 13,14% com adaptativo.
   Esses números revelam diferenças de segmentação; não medem acerto.

O limiar fixo merece estudo adicional, mas não foi escolhido como vencedor.
Abertura pode reduzir rejuntes e também apagar segmentos distantes; fechamento
pode unir objetos indevidos. ROI e transformação para a CNN continuam em estudo.
O painel do detector atual é uma referência sem recalibrar sua área mínima para
esta resolução, não uma avaliação justa de acurácia entre métodos.

## Revisão assistida por OpenCV

### Trabalho por lote para a apresentação

Não é necessário revisar os 1032 frames antes de apresentar os resultados.
As 45 marcações e o primeiro experimento já podem ser apresentados com suas
limitações. Para ampliar o conjunto com um orçamento de revisão definido, execute
no terminal do desktop/VNC da Raspberry Pi:

```bash
cd /home/carrasco/Downloads/robo_seguidor
.venv/bin/python tools/rotular_linha.py --lote 30
```

Essa opção mostra somente 30 imagens novas, distribuídas entre os sete vídeos
de treino/validação, priorizando timestamps afastados das marcações existentes.
Não seleciona vídeos de teste nem repete imagens já revisadas. Distância temporal
ajuda a reduzir redundância, mas não garante diversidade visual nem melhora do modelo.
O número 30 é um orçamento de trabalho, não uma quantidade comprovadamente suficiente.

O plano fica em `dataset_pista/rotulos/lotes/lote_30.json`, separado dos rótulos.
Fechar e executar o mesmo comando retoma esse lote, sem acrescentar mais 30.
Quando todas forem confirmadas, a ferramenta informa que o lote foi concluído.
Para criar outro lote futuramente, use outro arquivo explicitamente:

```bash
.venv/bin/python tools/rotular_linha.py --lote 30 --plano-lote dataset_pista/rotulos/lotes/lote_30_segundo.json
```

Depois do primeiro lote, conferir os novos rótulos e repetir o treinamento com
a mesma divisão por vídeo. Apresentar a comparação com o primeiro experimento,
incluindo falhas e tamanho de cada conjunto. Novos vídeos podem ser amostrados;
não precisam ter todos os frames revisados. Atribuir os novos vídeos a grupos
antes de usá-los, preservando gravações novas para avaliação independente.

### Seleção completa e edição

`tools/rotular_linha.py` mostra o original proporcional e, nas imagens pendentes,
uma sugestão em ciano. `visao/sugestao.py` usa OpenCV para separar regiões escuras,
filtrar segmentos pela geometria e associá-los por orientação e continuidade.
Não se limita ao maior contorno. Não usa CNN, YOLO ou pesos pré-treinados.
As sugestões são auxiliares e podem confundir rejuntes e cruzamentos.

A versão atual (`segmentos_geometria_v2`) corrige a iluminação local antes de
segmentar e dá peso ao suporte de pixels e à continuidade dos traços, evitando
favorecer só a quantidade de pequenos fragmentos. A correção é feita apenas
para sugerir os rótulos; o pré-processamento da CNN não foi alterado.
**Alternar original/tratada** mostra o tratamento sem mudar coordenadas ou arquivos.
Se a correção prejudicar a sugestão, **Tentar sem correção** gera uma alternativa
com a seleção geométrica nova. **Recalcular sugestão** restaura o tratamento
padrão da sessão. Confira cada alternativa antes de confirmar.

A comparação com a versão anterior e as falhas restantes estão em
`dataset_pista/resultados/preprocessamento_02/RELATORIO.md`. Nos diagnósticos,
verde é marcação humana e vermelho é sugestão OpenCV; na interface de revisão,
a sugestão ainda não confirmada continua em ciano. Quinze testes da assistência
e dez de dataset passaram, incluindo correção de sombra, preservação dos originais,
rejunte fragmentado na borda e visualização tratada com widgets simulados.

**Execute na Raspberry Pi, em um terminal do desktop ou de uma sessão VNC:**

```bash
cd /home/carrasco/Downloads/robo_seguidor
.venv/bin/python tools/rotular_linha.py --todos
```

O comando usa o ambiente virtual explicitamente. Não executar na Arduino IDE.
SSH sem acesso ao display não abre a interface. Tkinter foi localizado neste ambiente;
a abertura da janela e os cliques precisam ser verificados no desktop do usuário.

1. Feche a janela antiga antes de executar a versão atualizada. Por padrão (ou com `--todos`),
   ela abre na primeira das 1032 imagens ainda não revisada; as 45 anteriores são preservadas.
2. Confira a trajetória em ciano. Se estiver correta, basta escolher a visibilidade
   e clicar em **Confirmar e avançar**. A visibilidade não é escolhida pelo OpenCV.
3. Para corrigir, arraste um ponto, clique para adicionar ou use botão direito
   perto de um ponto para removê-lo (longe dos pontos, remove o último da lista).
   Pontos editados ficam vermelhos. Todos devem ter alturas diferentes.
   "Limpar pontos" permite refazer manualmente. Não marque rejuntes nem o traçado concorrente.
4. Marque `visivel` quando a trajetória estiver visível e definida; `parcial` quando
   houver ocultação ou corte que limite sua interpretação. Para ambos, marque pelo
   menos dois pontos em alturas diferentes, somente na extensão que pode ser identificada.
5. Marque `ausente` só quando a trajetória desejada realmente não estiver visível.
   Marque `ambiguo` quando não conseguir decidir a trajetória, inclusive em cruzamentos.
   Ambos exigem a lista de pontos vazia. Falha de algoritmo não significa ausência.
6. Clique em **Confirmar e avançar**. O programa pula as imagens já revisadas ao
   avançar depois de salvar. "Pular sem salvar" mantém a imagem pendente.
   "Próxima pendente" localiza a próxima ainda não confirmada.

Sem sugestão não significa linha ausente: nesse caso marque manualmente ou
escolha o estado correto após examinar a imagem. "Recalcular sugestão" substitui
os pontos na tela somente após confirmação, quando já existem pontos; a revisão
em disco permanece até um novo salvamento explícito.

Quando existe uma revisão anterior com até dois segundos de diferença no mesmo
vídeo e com as mesmas dimensões, a associação geométrica pode usá-la como apoio.
Isso não copia automaticamente o rótulo nem usa imagens futuras/outros vídeos.
Mudanças bruscas entre frames ainda exigem correção humana.

O programa começa no primeiro frame ainda não revisado. Para corrigir, use "Anterior"
e confirme de novo. Cada salvamento acrescenta uma revisão em
`dataset_pista/rotulos/revisoes.jsonl`; a última revisão da imagem é a vigente.
O arquivo só é criado ao salvar uma anotação. São preservados nome, vídeo,
timestamp, dimensões, hash, pontos em pixels originais e estado de visibilidade.
Rótulos assistidos registram `opencv_confirmado` ou `opencv_corrigido`,
`confirmacao_humana`, versão do algoritmo, sugestão inicial e referência temporal,
quando usada. O schema continua compatível com o carregador de treinamento.
Nenhuma sugestão é salva como rótulo sem clicar em **Confirmar e avançar**.
Arquivo de revisões inválido não é ignorado silenciosamente.

Para rever apenas as 45 amostras do estudo, use `--amostras`:

```bash
.venv/bin/python tools/rotular_linha.py --amostras
```

Não existe posição de controle inventada: os pontos descrevem a localização da
trajetória, não comandos de motor. Não extrapole a linha para fora da parte visível.
Confirmar com o usuário qual trajetória deve ser seguida nos cruzamentos antes
de tratá-los como rótulos definitivos.

## Próximos passos após a revisão

1. Conferir as anotações humanas das amostras e definir a referência geométrica
   da posição horizontal. Uma trajetória anotada permite comparar faixas antes
   de fixar ROI e rótulo escalar. `parcial` e `ambiguo` não serão colapsados automaticamente.
2. Concluir a revisão do conjunto, medir equilíbrio e similaridade entre vídeos.
   Se houver pouca variação lateral ou ausência de linha, coletar dados adicionais.
3. Definir transformação compartilhada para treino e inferência, preservando a
   geometria. Reaproveitar a RedeLinha e adaptar a semântica da saída de direção
   derivada do professor para posição, com registro dessa mudança.
4. Separar por vídeo e agrupar gravações quase repetidas. As 45 amostras de todos
   os vídeos já foram usadas na exploração: não apresentar resultados futuros
   nesses vídeos como avaliação completamente intocada. Reservar gravações novas
   para uma avaliação final estritamente independente quando necessário.
5. Treinar offline, comparar com baselines e avaliar erros e visibilidade.
   Não é possível calcular acurácia ou treinar supervisionadamente com qualidade
   apenas a partir do CSV de metadados.

## Reproduzir o estudo e os testes

**Raspberry Pi, terminal na pasta do projeto, usando a .venv:**

```bash
.venv/bin/python tools/estudar_linha.py --saida dataset_pista/resultados/estudo_02
.venv/bin/python tests/test_dataset_linha.py
.venv/bin/python tests/test_sugestao_linha.py
```

A saída do estudo precisa ser uma pasta nova; o programa recusa sobrescrever uma
execução existente. Cinco testes offline passaram: seleção temporal, polaridade
das máscaras, semântica de visibilidade, geometria e leitura do histórico de revisões.
A integridade dos 45 diagnósticos e das 1.215 medições também foi conferida.
Na etapa inicial não foram validados a interação gráfica, o treinamento ou o uso físico.

### Verificação da sugestão automática

Nove testes da sugestão/confirmação passaram: pontilhado com rejunte, coordenadas
originais, apoio temporal, imagem uniforme, proveniência e confirmação obrigatória,
avanço sem alterar rótulos antigos, segmento único sem extrapolação e callbacks com widgets simulados. Os dez
testes de dataset/posição também passaram. O teste com widgets simulados não
valida a aparência e os cliques em uma janela real; este ambiente não conecta ao
display `:0`, então essa verificação continua no desktop/VNC.

Em 45 amostras reais, o algoritmo gerou sugestões em 45. A montagem comparando
todas elas foi inspecionada. Há uma sugestão e uma marcação humana cobrindo
y=75% em 33 imagens; o erro médio condicional nessas 33 é 0,0262, mas isso não
mede acurácia no conjunto inteiro nem qualidade da trajetória completa. Dez
marcações que cobrem a referência não têm cobertura equivalente da sugestão.
O algoritmo foi ajustado nessa exploração, portanto não se trata de teste independente.
Há erros nos extremos das trajetórias e em alguns rejuntes: corrigir antes de confirmar.
Quando só um segmento é aproveitável, a sugestão fica dentro dele, com aviso;
não se completa automaticamente o restante da trajetória.

A montagem e os candidatos não aprovados estão em
`dataset_pista/resultados/sugestoes_opencv_01/`. Eles não são lidos como rótulos
pelo treinamento. Nenhum novo treino foi executado na implementação da assistência.

## Primeiro treino com as marcações humanas

As 45 imagens foram salvas pelo usuário: 37 `visivel`, oito `parcial`, nenhuma
`ausente` ou `ambiguo`. Há 46 registros de revisão; a última revisão de cada
imagem foi usada. Metadados, hashes e geometria foram conferidos. Uma montagem
com todas as 45 marcações foi inspecionada visualmente.

Foi acrescentado `aprendizado/dataset_rotulado.py`, sem alterar os episódios
antigos: ele recorta uma faixa 2:1 usando a largura inteira, centrada em 75% da
altura original, e reduz proporcionalmente para 80×40. `preparar_foto()` é a
transformação compartilhada de inferência para esses pesos; ela difere da entrada
legada da câmera. O alvo é a posição horizontal interpolada nessa altura, somente
dentro da extensão anotada, normalizada entre -1 (esquerda) e +1 (direita).

43 marcações cobrem essa referência. Duas ficaram excluídas por não cobri-la:
`video_02_frame_00000.jpg` e `video_09_frame_00128.jpg`. Não foram alteradas ou
extrapoladas. A faixa é uma definição experimental inicial baseada na cobertura
das marcações e na inspeção visual, não uma ROI calibrada para a futura ESP32-CAM.

`tools/treinar_fotos_linha.py` reutiliza `RedeLinha`, `Adam`, `normalizar()` e
`aumentar()`. Usa Huber apenas para posição, com peso de visibilidade zero.
Não usa os rótulos interpolados de episódios e não infere comandos do celular.
O treino de episódios continua disponível sem mudanças. A saída de visibilidade
destes pesos não é supervisionada e deve ser ignorada.

O experimento `dataset_pista/resultados/treino_posicao_01/` usou 300 passos,
lotes de oito e semente sete. O checkpoint foi selecionado por menor MSE de
validação (passo 170); o teste só foi avaliado depois dessa seleção.

| Conjunto | Imagens | MAE CNN | MAE sempre centro |
|---|---:|---:|---:|
| Treino | 24 | 0,0201 | 0,2369 |
| Validação | 10 | 0,1403 | 0,2474 |
| Teste exploratório | 9 | 0,1373 | 0,2322 |

O MAE do teste equivale a aproximadamente 6,9% da largura. Isso não é acurácia.
O pior erro do teste foi 0,5963, aproximadamente 29,8% da largura, em
`video_06_frame_00134.jpg`, com a linha perto da borda esquerda. A diferença grande
entre treino e validação indica ajuste aos poucos exemplos e limita a confiança
no resultado. Não foram ajustados hiperparâmetros após consultar o teste.

Divisão fixa por vídeo em `dataset_rotulado.DIVISAO`: cinco vídeos para treino,
dois para validação e dois para teste. Nenhum vídeo está em mais de um conjunto.
A divisão preserva independência entre arquivos de vídeo, mas não garante
independência de percurso/ambiente entre gravações.

**Reproduzir na Raspberry Pi, terminal do projeto, com a .venv:**

```bash
OPENBLAS_NUM_THREADS=1 .venv/bin/python tools/treinar_fotos_linha.py --saida dataset_pista/resultados/treino_posicao_02
.venv/bin/python tests/test_dataset_linha.py
```

Executar novamente com `revisoes.jsonl` ampliado produz outro experimento com
mais dados; não é reprodução exata deste primeiro. Os rótulos usados e os índices
estão preservados em `dataset.json` e `dados.npz` do experimento inicial.

Os dez testes offline de dataset/posição passaram. A preparação de inferência
foi comparada exatamente com a entrada de treinamento nas 43 imagens, e o
checkpoint recarregado foi conferido por hash. Foram salvas 43 sobreposições de
previsão, incluindo falhas; algumas foram inspecionadas. O arquivo `historico.csv`
contém a curva numérica de treino/validação. Pesos, relatório e métricas por vídeo
estão na pasta do experimento. Não houve teste físico, ativação de autonomia ou
validação de ausência da linha. Antes de integrar ao robô, são necessários mais
dados e testes independentes com a câmera instalada.

## Comparação offline com BatchNorm

Com o carrinho parado, execute no ambiente Python do projeto. Os gráficos
e painéis usam `matplotlib`.

```bash
.venv/bin/python -m pip install matplotlib
OPENBLAS_NUM_THREADS=1 .venv/bin/python tools/comparar_batchnorm.py --saida dataset_pista/resultados/comparacao_batchnorm
```

A comparação usa o snapshot do segundo treino e, por padrão, as sementes
7, 17 e 27. Para cada semente, treina as duas variantes do zero com 300 passos,
lotes de oito e os mesmos aumentos de dados. O menor MSE de validação escolhe
o checkpoint de cada execução. Os vídeos de teste ficam fora desta análise.

Com 58 imagens de treino e dez de validação, a comparação produziu os
seguintes MAEs médios entre as três sementes, em porcentagem da largura:

| Variante | Treino | Validação | Diferença validação − treino |
|---|---:|---:|---:|
| Sem BatchNorm | 1,65% | 6,73% | 5,08 p.p. |
| Com BatchNorm | 2,16% | 7,01% | 4,85 p.p. |

A diferença entre treino e validação caiu 0,23 p.p. e o MAE de validação
subiu 0,28 p.p. em média. A CNN original teve menor erro em duas das três
sementes. A variante fica disponível para experimentos. A generalização
continua pendente de avaliação com gravações novas da câmera montada.

- `RELATORIO.md` contém o MAE em porcentagem da largura e a diferença entre
  treino e validação. `comparacao.json` contém também o erro por vídeo.
- `curvas.png` mostra a média e o desvio-padrão entre sementes em cada passo.
- `menor_erro.png` e `maior_erro.png` mostram as mesmas imagens para as duas
  redes, escolhidas pelo erro médio do par na primeira semente. Cada bloco
  usa sua própria escala de intensidade. Os canais são escolhidos pela
  ativação média da imagem, e sua intensidade descreve a resposta do filtro.
- As pastas por semente guardam os checkpoints, as curvas em CSV e cada
  previsão de validação. Para treinar só a variante com normalização,
  use `tools/treinar_fotos_linha.py --batchnorm --saida <pasta-nova>`.

## Referência offline com HoughLinesP

```bash
.venv/bin/python tools/comparar_hough.py --saida dataset_pista/resultados/comparacao_hough
```

O ensaio lê o snapshot do segundo treino e os pesos CNN correspondentes.
Aplica Canny e HoughLinesP num recorte proporcional de 320×160, em três
faixas locais. Procura duas bordas próximas, com inclinações semelhantes
e faixa interna mais escura que os lados. O ponto médio do par estima o
centro. Só a faixa central fornece a previsão avaliada em y=75%.
Para contornos, usa o x do centróide do detector atual em imagem reduzida
proporcionalmente para 160 px de largura. A CNN usa sua entrada 80×40 e
o checkpoint de posição selecionado no segundo treino.

Nos mesmos quadros em que os três métodos estimaram posição, o MAE em
porcentagem da largura foi o seguinte.

| Conjunto | Quadros pareados | Hough | Contornos | CNN |
|---|---:|---:|---:|---:|
| Validação | 8 de 10 | 14,43% | 11,10% | 5,36% |
| Teste exploratório | 5 de 9 | 9,90% | 2,11% | 2,34% |

Hough ficou sem estimativa em 5 dos 19 quadros com posição anotada.
Nos diagnósticos de `video_03_frame_00102.jpg`, `video_04_frame_00048.jpg`
e `video_06_frame_00034.jpg`, o par aceito na faixa central cai sobre o
rejunte, com erros de cerca de 46%, 35% e 42% da largura. A inspeção desses
quadros ilustra o erro de seleção. Uma taxa de falsos positivos por cenário
requer rótulos sistemáticos de rejunte.

No único quadro rotulado como ausente, Hough e contornos ficaram sem
estimativa e a CNN emitiu posição. Nos dois ambíguos, Hough ficou sem
estimativa em ambos, contornos emitiu posição em um e a CNN nos dois.
Esses três casos são do grupo de treino da CNN. A saída de visibilidade
dos pesos permanece sem supervisão, e o conjunto segue exploratório.

O ensaio gera `RELATORIO.md`, `quadros.csv`, `comparacao.json` com métrica
por vídeo, `segmentos.jsonl` com as decisões por faixa e 23 imagens em
`diagnosticos/`. Nos painéis, cinza indica segmentos descartados, ciano
indica os pares aceitos e verde marca a referência humana.
