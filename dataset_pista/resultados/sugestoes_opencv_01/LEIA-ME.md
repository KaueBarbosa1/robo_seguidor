# Sugestões de trajetória por OpenCV

Comparação exploratória em 45 imagens já rotuladas: verde = marcação humana;
vermelho = sugestão automática. Não são novas marcações aprovadas.

Foram geradas sugestões em 45 imagens. Em 33, a sugestão e a marcação humana
cobrem a referência y=75%, permitindo comparação: MAE normalizado 0,0262
nessas 33, com erro máximo 0,3355. O número não mede acurácia nos 45 frames
nem garante que a trajetória completa esteja correta. Dez marcações humanas
cobrem y=75% sem cobertura equivalente da sugestão; duas humanas não cobrem.
Essa exclusão limita o resultado e não pode ser interpretada como sucesso.

O algoritmo foi ajustado durante a inspeção destas amostras: resultado
exploratório, não teste independente. Nenhuma referência temporal foi usada
nessa comparação. A interface pode usar como apoio a última revisão confirmada
até dois segundos antes no mesmo vídeo, registrando sua origem.

Falhas observadas: rejuntes espessos, continuação incorreta nos extremos e
cruzamentos. Quando só um segmento é aproveitável, o algoritmo sugere somente
seu trecho interno e informa a limitação; isso não completa toda a trajetória.
Não há probabilidades calibradas nem classificação automática de visibilidade.
Cada sugestão precisa de confirmação explícita na interface antes de virar rótulo.

avaliacao.json contém candidatos, medições e hashes. Não é dataset supervisionado.
Nenhum modelo pré-treinado, CNN ou pesos externos foi usado.
