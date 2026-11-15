# Primeiro experimento offline de localização
45 imagens revisadas; 43 usadas; 2 excluídas. Divisão: {'treino': 24, 'validacao': 10, 'teste': 9}.
RedeLinha existente, sem mudar sua arquitetura. Cabeça 0 aprende posição em y=75%, não comando de motor. Cabeça de visibilidade não supervisionada (lambda=0); ignorar sua saída.
Recorte 2:1 na largura inteira centrado em y=75%, cinza 40×80, normalização compartilhada com aprendizado/dados.py. Interpolação somente dentro dos pontos humanos, sem extrapolação. Parciais com pontos cobrindo a referência podem treinar posição; isso não cria rótulos de visibilidade.
Melhor checkpoint no passo 170, por MSE de validação. Teste avaliado só após seleção. Augmentation: espelho com troca de sinal e ruído da função existente.
| Conjunto | N | MAE CNN | MAE centro | MAE média treino | MSE CNN |
|---|---:|---:|---:|---:|---:|
| treino | 24 | 0.0201 | 0.2369 | 0.2323 | 0.0006 |
| validacao | 10 | 0.1403 | 0.2474 | 0.2443 | 0.0303 |
| teste | 9 | 0.1373 | 0.2322 | 0.2354 | 0.0489 |

MAE é erro normalizado na largura: erro 0,1 equivale a 5% da largura. Não é porcentagem de acerto. Ver experimento.json para métricas por vídeo.

Verde: marcação humana; cruz vermelha: CNN; azul: centro; amarelo: limites do recorte. Predições em previsoes/; valores por imagem em predicoes.csv; curva numérica em historico.csv.

Os vídeos já foram inspecionados durante a exploração; o teste é separado por vídeo, mas não é uma avaliação final intocada nem prova generalização para outro ambiente. Poucos exemplos e nenhuma ausência anotada: não avaliar precisão/recall de visibilidade. Coletar mais rótulos e gravações independentes antes de concluir confiabilidade.

Pesos em pesos_posicao.npz são apenas deste experimento: não foram registrados como campeão nem carregados no robô. Firmware, sensores, Bluetooth e configuração preservados.
