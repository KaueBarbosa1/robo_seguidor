# Estudo offline da linha

45 amostras temporais; 1215 combinações medidas.

Comparação de fixo, Otsu e adaptativo, sem morfologia/com abertura/com fechamento, e recortes inferiores a partir de 0%, 35% e 50%. Coordenadas são candidatas de estudo. Limiarização usa a imagem inteira; ROI recorta as máscaras. Redução proporcional, sem distorção. Kernel 3x3 e área mínima são na resolução de análise.

Os dez painéis mostram original, cinza, três thresholds, abertura e fechamento Otsu, componentes sem seleção, ROIs candidatas e detector atual como referência. Componentes/quantidade de pixels pretos não medem acurácia. Não existe vencedor automático sem rótulos revisados. O erro do detector não é rótulo.

Amostras foram usadas para exploração: não tratá-las depois como teste independente intocado. Manifesto registra parâmetros, hashes e origem; comparacao.csv não é dataset supervisionado.
