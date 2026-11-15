# Contexto do projeto e plano para a CNN

Registro de continuidade em 15/11/2026. Consolida o código disponível e as
decisões propostas pelo usuário. Este documento e os comentários associados
não implementam nem ativam o plano. Os valores de calibração e critérios
numéricos ainda precisam ser definidos em experimentos com o carrinho.

## Objetivo e divisão de responsabilidades

O objetivo é um carrinho que siga uma trajetória pontilhada, atravesse seus
vãos, antecipe curvas e reencontre a linha depois de contornar obstáculos.
Voz e controle remoto Bluetooth permitem comandar e interromper o movimento.

| Componente | Papel atual e evolução pretendida |
|---|---|
| Raspberry Pi 5 | Executar visão, inferência, planejamento e controle; treino apenas parado. |
| ESP32-CAM OV2640 | Fonte de imagem em avaliação: JPEG 320×240 por Wi-Fi, receptor de bancada separado. |
| Arduino Uno e L298N | Acionamento das rodas, leitura de sensores e proteções locais. |
| Encoders | Medir pulsos das rodas; validar e calibrar antes de usá-los como odometria. |
| Ultrassom e servo | Medir distâncias frontal/laterais; alimentar um planejador futuro. |
| CNN de linha | Estimar trajetória e sua validade; não escolher sozinha um contorno de obstáculo. |
| Planejador futuro | Escolher e acompanhar o contorno, procurar e recuperar a trajetória. |
| Controle | Converter decisões em comandos de roda e interromper movimentos inseguros. |

O controle continua sendo o único escritor dos comandos de motor. Visão e
aprendizado publicam resultados no estado compartilhado. Parada manual,
watchdogs, validade dos dados e proteção de obstáculo precisam permanecer
prioritários durante qualquer futura integração.

## Estado atual: implementação não equivale a validação física

- `main.py` reúne controle, visão OpenCV, voz e Bluetooth; a thread de
  aprendizado é opcional. `APRENDIZADO_ATIVO = False` na configuração revisada.
- `FONTE_IMAGEM = "arduino"`, mas `FIRMWARE_COM_CAMERA = False` e a serial está
  em 115200 baud. `main.abrir_fonte` troca essa combinação por fonte sem imagem.
  Portanto, essa configuração não fornece imagem à visão pelo Uno.
- A OV7670 via Uno é o caminho legado. Seu modo com câmera usa 1 Mbaud e
  conflita com ultrassom/encoders. A câmera CSI é uma alternativa antiga sem uso.
  Comentários que chamavam a OV7670 de decisão definitiva são históricos;
  a migração proposta agora considera a ESP32-CAM.
- A ESP32-CAM é testada por `arduino/esp32_cam_bancada/` e
  `tools/testar_esp32_cam.py`: não está integrada a `visao/fontes.py`, ao
  `main.py` ou ao ciclo CNN/controle. A recepção não aplica o recorte da CNN.
- O servo já tem varredura e inspeção de três direções implementadas.
  A inspeção automática em SEGUINDO termina em PARADO; ainda não escolhe um
  desvio nem retoma movimento sozinha. A validação física integrada é pendente.
- Existe controle PI por encoders. `CONTROLE_VELOCIDADE_ATIVO = True` está
  marcado como teste com rodas suspensas; isso não comprova calibração ou
  funcionamento na pista. A falha de encoder ainda não é enviada na telemetria.
- `aprendizado/robo_real.py` contém adaptação do ciclo de aprendizado legado;
  sua documentação registra verificação em simuladores, não na pista física.

Guias: [bancada ESP32-CAM](12_esp32_cam_bancada.md),
[servo e inspeção](09_servo_integrado.md),
[velocidade e encoders](11_controle_velocidade.md),
[aprendizado legado](04_aprendizado_online.md),
[dataset e rotulação](08_dataset_linha.md). As notas antigas do README e desses
guias descrevem etapas específicas; não são comprovação do conjunto atual.

## CNN existente e significado dos pesos

`aprendizado/cnn.py` implementa `RedeLinha` em NumPy, com pesos inicialmente
aleatórios: três convoluções, camada densa de 64 e duas saídas. A entrada tem
formato `(N, 1, 40, 80)`, isto é, imagens cinza de largura 80 e altura 40.

O primeiro valor é limitado a [-1, 1]. No ciclo legado representa direção
sugerida; no treino com fotos foi reaproveitado para posição horizontal da
linha em uma única altura, y = 75% da imagem. **Posição não é comando de motor.**
O segundo valor é um logit de visibilidade, convertido em probabilidade em
`prever`. No treino com fotos, `tools/treinar_fotos_linha.py` usa
`lambda_vis=0`: essa saída não foi supervisionada e deve ser ignorada.
O formato da rede permitir calculá-la não a torna uma confiança confiável.

Há dois caminhos de entrada diferentes:

- `aprendizado/dados.py`: quadros legados 160×120, corte a partir de
  `APR_ROI_LINHA_INICIO` e redução por blocos 2×2.
- `aprendizado/dataset_rotulado.py`: recorte proporcional 2:1 na largura
  inteira, centrado em y=75%, seguido de redução para 80×40. O contrato se
  chama `foto_roi_2por1_y075_v1`. Esse recorte não cabe em um quadro 320×240
  com a referência atual; não basta conectar a câmera ao carregador de fotos.

Ambos usam `dados.normalizar`: divide por 255, subtrai a média por imagem,
divide pelo desvio padrão mais 0,08 e limita a [-4, 4]. Treino e inferência
dos mesmos pesos devem usar exatamente o mesmo caminho completo.

Os rótulos humanos contêm pontos e estados `visivel`, `parcial`, `ausente`
e `ambiguo`. O carregador atual só inclui posições cuja extensão anotada
cubra y=75%; ausentes e ambíguos são excluídos do treino de posição.
A divisão já ocorre por vídeo, mas os conjuntos atuais são exploratórios e
do mesmo ambiente. A sugestão de `visao/sugestao.py` é OpenCV para revisão
humana; não é CNN nem gera visibilidade supervisionada automaticamente.

### Experimento offline com BatchNorm

A `RedeLinha` ganhou uma variante opcional com `Convolução → BatchNorm → ReLU`
nos três blocos. O treino calcula médias e variâncias por canal. A inferência
usa as estimativas móveis persistidas no checkpoint, inclusive ao processar
um único quadro. O formato `rede_linha_batchnorm_v1` identifica esses pesos.

`tools/comparar_batchnorm.py` compara a variante e a CNN original para o
mesmo alvo em y=75%. Cada par usa os mesmos dados, inicialização, sequência de
lotes e critério de seleção por validação. O experimento é offline e mede
erro de posição e diferença entre treino e validação. Ainda é preciso avaliar
a generalização em gravações novas da ESP32-CAM montada.

O diagnóstico visual mostra a imagem original, a entrada normalizada, a
previsão de cada variante sobre a anotação e três canais após a ReLU de cada
bloco. Esses mapas exibem ativações intermediárias. Para acompanhar decisões
do carrinho, a integração futura deve registrar a transição de estado, a
validade e a idade da previsão, a leitura dos sensores e o motivo do comando.

Consulte [a reprodução e os artefatos do experimento](08_dataset_linha.md#comparação-offline-com-batchnorm).

### Comparação offline com HoughLinesP

`tools/comparar_hough.py` compara Hough, contornos e CNN nas mesmas fotos
rotuladas. Hough analisa pares de bordas em três faixas locais e estima
a posição em y=75% quando encontra um par na faixa central. O relatório
separa cobertura, erro nos quadros comuns e casos ausentes ou ambíguos.
Nos vídeos exploratórios, houve abstenções e seleção de rejunte como fita.
O experimento roda fora do controle. Consulte
[o método e os resultados](08_dataset_linha.md#referência-offline-com-houghlinesp).

## Quatro mudanças propostas na CNN — todas pendentes

### 1. Adaptar a entrada à ESP32-CAM

Receber JPEGs 320×240 e calibrar orientação e recorte com a câmera montada no
carrinho, preservando área perto e longe da pista. Começar avaliando 80×40;
medir se os pontos distantes continuam distinguíveis antes de aumentar a rede.
Não deformar a geometria para fazer caber um recorte antigo.

Criar um pré-processamento compartilhado entre coleta, treino e inferência.
Versionar resolução, ROI, orientação, conversão para cinza e normalização junto
dos pesos. Não substituir silenciosamente o tratamento de pesos antigos.
Rever `dataset_rotulado.py`, `dados.py`, `visao/fontes.py` e o receptor de bancada.

### 2. Prever trajetória em três alturas

Prever posições horizontais perto, no meio e longe, em alturas calibradas
dentro da ROI; elas ainda não têm valores definidos. Usar perto para corrigir
alinhamento e as demais para antecipar curvatura e continuidade do pontilhado.
Altura da imagem só vira distância física após calibração geométrica.

Modificar saída, forward/backward, perdas, aumento de dados, métricas,
carregamento de pesos e consumidores das previsões. Os pesos antigos de duas
saídas não são diretamente compatíveis com a nova cabeça. Registrar versão
e validar formato e semântica ao carregar, evitando erro silencioso.

Gerar alvos pela interpolação dos pontos humanos apenas dentro da extensão
anotada. Usar uma máscara por altura para pontos não identificáveis, sem
extrapolar atrás de um obstáculo ou marcar ausência como posição central.
No espelho horizontal, inverter todos os alvos horizontais e preservar máscaras.

### 3. Supervisionar linha ausente ou ambígua

Incluir exemplos positivos e negativos, oclusões por obstáculos e situações
nas quais não existe trajetória identificável. Definir explicitamente o que
significam parcial, ausente e ambíguo para a nova saída de validade; não
transformar os quatro estados em uma probabilidade binária sem essa decisão.
Avaliar também validade por altura, pois pode haver trecho próximo oculto e
trecho distante visível. A escolha final da cabeça ainda está pendente.

Treinar a validade com rótulos humanos e aplicar perda de posição somente nas
alturas válidas. Medir principalmente falsas aceitações de trajetórias
inválidas, além de falsas rejeições; escolher limiares na validação. Não usar
a saída de visibilidade dos pesos atuais como autorização para movimento.

### 4. Treinar novamente com imagens da câmera real

Coletar com a ESP32-CAM instalada: retas, curvas para ambos os lados, vãos do
pontilhado, sombras, mudanças de luz, linha nas bordas, linha ausente,
cruzamentos ambíguos, obstáculos e retorno após desvio. Preservar originais,
metadados da montagem/câmera e revisões humanas.

Separar gravações/sessões para treino, validação e teste antes de treinar.
Não distribuir quadros vizinhos da mesma gravação entre conjuntos. Reservar
gravações novas para avaliação independente e não ajustar o modelo pelo teste.
Registrar erro por altura, desempenho por cenário e casos de falha, comparando
com referências simples e com o modelo de uma posição quando comparável.

## Vãos do pontilhado: começar com memória no controle

Combinar previsões recentes válidas com os encoders durante um intervalo
limitado. Calibrar pulsos por distância, geometria das rodas e sinais; pulsos
sem direção e derrapagem não fornecem odometria precisa automaticamente.
Definir limites de tempo, distância e incerteza para manter uma estimativa.
Reduzir velocidade conforme a incerteza e parar ao exceder os limites, perder
telemetria ou detectar obstáculo. Invalidar memória em parada, troca de modo
e recuperação da câmera, para não aplicar uma trajetória antiga.

Essa memória ainda precisa ser implementada e validada na pista. A política
legada de `aprendizado/politica.py` não comprova esse comportamento. Uma CNN
com sequência de quadros fica para uma etapa posterior, se os testes mostrarem
necessidade; não é a primeira ampliação proposta.

## Obstáculos: colaboração entre sensores, planejador, CNN e controle

1. Ultrassom e servo avaliam distâncias e registram direção, validade e tempo.
2. O planejador futuro escolhe e acompanha o contorno, com critérios de aborto.
3. A CNN auxilia a reencontrar a trajetória e voltar ao seguimento.
4. O controle ajusta as rodas e interrompe movimentos inseguros.

A inspeção atual é parada. Autorizar contorno exige implementar estados,
transições, tratamento de leituras desconhecidas, acompanhamento do progresso
e recuperação da linha. Eco lateral isolado não autoriza avançar; ausência de
eco não significa passagem livre. Definir como obter medições frontais recentes
durante o contorno respeitando o bloqueio atual de movimento durante a inspeção.

Detectar obstáculos pela imagem é uma ampliação separada: adicionar saída
específica e novos rótulos de obstáculos ou espaço livre, com treinamento e
avaliação próprios. A cabeça de linha não tem essa capacidade por inferência.

## Inferência contínua, desempenho e treino parado

Carregar pesos aprovados na Raspberry e processar continuamente o quadro mais
recente, descartando intermediários para não acumular atraso. Publicar junto
da previsão identificador, idade do quadro, validade e versão do modelo.
Ausência de câmera, pesos incompatíveis ou previsão vencida devem invalidar
a ação; não reaproveitar indefinidamente a última previsão.

Os aproximadamente 12 FPS relatados e os CSVs de bancada se referem à
recepção da câmera, não à execução integrada de CNN e controle. Registrar
captura/recepção, decodificação, pré-processamento, inferência, planejamento e
envio ao motor, além da idade da imagem quando a ação é usada. Medir sob carga
real com sensores, voz e Bluetooth, incluindo falhas e recuperação do Wi-Fi.
Os relógios da ESP e da Pi não devem ser subtraídos como se sincronizados.

Treinar somente com o carrinho parado. Separar treino e inferência, promover
pesos após avaliação e manter possibilidade de voltar à versão anterior.
A infraestrutura legada de versões/ciclo é referência, mas não comprova uma
integração da ESP32-CAM nem compatibilidade com a nova cabeça.

## Ordem de trabalho e evidências necessárias

- [ ] Consolidar montagem e ensaios da ESP32-CAM; documentar orientação, foco,
  alimentação, estabilidade e recuperação das desconexões nos CSVs.
- [ ] Calibrar ROI e alturas; confirmar que 80×40 preserva a trajetória distante.
- [ ] Coletar e revisar dados reais com as situações acima e divisão por sessão.
- [ ] Versionar pré-processamento e contrato de pesos; implementar três posições,
  máscaras e validade supervisionada; verificar perdas/gradientes e persistência.
- [ ] Avaliar offline por gravação e cenário, incluindo ausências e oclusões.
- [ ] Integrar inferência sem comandar rodas e medir latência e descarte de dados.
- [ ] Validar encoders e implementar memória limitada, com aborto e parada.
- [ ] Validar seguimento físico progressivamente; depois implementar e avaliar
  planejamento de contorno e recuperação, preservando as proteções existentes.
- [ ] Decidir, a partir das falhas medidas, sobre sequência temporal ou cabeça
  visual de obstáculos. Não são pré-requisitos da primeira versão.

Atualizar este registro a cada mudança e fazer commit das alterações verificadas,
conforme solicitado pelo usuário. Não marcar itens concluídos só porque foram
documentados, simulados ou tiveram recepção de câmera bem-sucedida.
