# Segundo experimento offline de localização
87 imagens revisadas; 77 usadas; 10 excluídas. Divisão: {'treino': 58, 'validacao': 10, 'teste': 9}.
RedeLinha existente, sem mudar sua arquitetura. Cabeça 0 aprende posição em y=75%, não comando de motor. Cabeça de visibilidade não supervisionada (lambda=0); ignorar sua saída.
Recorte 2:1 na largura inteira centrado em y=75%, cinza 40×80, normalização compartilhada com aprendizado/dados.py. Interpolação somente dentro dos pontos humanos, sem extrapolação. Parciais com pontos cobrindo a referência podem treinar posição; isso não cria rótulos de visibilidade.
Melhor checkpoint no passo 130, por MSE de validação. Teste avaliado só após seleção. Augmentation: espelho com troca de sinal e ruído da função existente.
| Conjunto | N | MAE CNN | MAE centro | MAE média treino | MSE CNN |
|---|---:|---:|---:|---:|---:|
| treino | 58 | 0.0349 | 0.2972 | 0.2862 | 0.0020 |
| validacao | 10 | 0.1026 | 0.2474 | 0.2669 | 0.0146 |
| teste | 9 | 0.0725 | 0.2322 | 0.2358 | 0.0096 |

MAE é erro normalizado na largura: erro 0,1 equivale a 5% da largura. Não é porcentagem de acerto. Ver experimento.json para métricas por vídeo.

Verde: marcação humana; cruz vermelha: CNN; azul: centro; amarelo: limites do recorte. Predições em previsoes/; valores por imagem em predicoes.csv; curva numérica em historico.csv.

Os vídeos já foram inspecionados durante a exploração; o teste é separado por vídeo, mas não é uma avaliação final intocada nem prova generalização para outro ambiente. A cabeça de visibilidade não foi supervisionada: não avaliar precisão/recall dessa saída. As marcações ausentes e ambíguas ficam fora da regressão de posição. Coletar mais rótulos e gravações independentes antes de concluir confiabilidade.

Pesos em pesos_posicao.npz são apenas deste experimento: não foram registrados como campeão nem carregados no robô. Firmware, sensores, Bluetooth e configuração preservados.
