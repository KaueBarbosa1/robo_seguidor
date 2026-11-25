# Gêmeo digital 3D — Etapa 4

Visualizador local no computador, com Three.js e o GLB original do carrinho.
Simulação e histórico funcionam sem a Raspberry Pi ou o Arduino. A integração
física continua pendente. Não existe comando de atuação no visualizador.

## Abrir no Windows

Na raiz do projeto:

```powershell
python -m pip install -r requirements-gemeo-pc.txt
.\iniciar_gemeo.ps1
```

O script instala o Three.js pelo lockfile se necessário e abre
`http://127.0.0.1:8780`. Requer Python 3.10+ e Node.js/npm; foram utilizados
Python 3.13 e Node.js 24.16 nesta validação. Ctrl+C encerra os serviços locais.
Se preferir execução direta:

```powershell
npm.cmd ci --prefix gemeo_digital/frontend
python tools/gemeo_digital.py
```

Não é necessário instalar Node.js ou Three.js na Raspberry. Depois da instalação
das dependências, o visualizador não depende de CDN ou acesso à internet.

## Modelo original

Já foi copiado, sem alteração, de
`C:\Users\kaueb\OneDrive\Documentos\modelo_carrinho\carrinho_configurado.glb`
para `gemeo_digital/modelos/carrinho_configurado.glb` neste checkout.
O original não foi sobrescrito. Os dois arquivos têm os mesmos 3.583.476 bytes
e SHA-256 `e2713914a205bfa6504aae3830a67766ad5f1592c5a825660b1677184571a52b`.

O GLB e `node_modules` são recursos locais ignorados pelo Git. Em outro checkout,
coloque esse mesmo GLB em `gemeo_digital/modelos/carrinho_configurado.glb`.
O JSON original de eixos e o diagnóstico de nomes/hierarquia estão versionados
em `modelos/`. Nenhuma versão modificada do GLB foi criada.

## Usar os três modos

- **Simulação:** altere os pulsos/s de cada roda, com sinal positivo para frente
  e negativo para ré; ajuste servo, distância, câmera, linha, CPU, temperatura
  e latência. “Motores ativos” para a bancada virtual; “Interromper telemetria”
  testa dados vencidos. Começa com as rodas paradas. Os valores são sintéticos.
- **Histórico:** selecione uma sessão existente, depois reproduza, pause ou use
  a linha do tempo e os botões de ±1 segundo. A busca restaura o prefixo temporal
  da sessão, com memória limitada; sessões longas podem demorar para buscar.
  Imagens aparecem apenas se foram gravadas e estão próximas do instante atual.
- **Tempo real:** fica desabilitado até configurar a URL e o token no terminal.
  É observação do cliente WebSocket existente. Sem calibração física confirmada,
  a odometria e a velocidade angular real permanecem indisponíveis.

O botão de referência reinicia a estimativa e o trajeto locais. A lista de
comparação sobrepõe outra trajetória em azul. Nas sessões novas com odometria
gravada, ela prevalece sobre a recomputação e preserva os resets registrados.
Sessões antigas sem odometria usam recomputação com calibração explicitamente
simulada ou fornecida; sem calibração válida, não há trajetória real confiável.

Para consultar uma base específica, reutilize a raiz da etapa 3:

```powershell
.\iniciar_gemeo.ps1 -Historico 'C:\caminho\dados_historico'
```

Sem argumento, usa `ARMAZ_DIR`; se não houver banco nessa raiz, procura a última
base de validação `validacao_*/cenario_10hz` já existente. Não cria outro histórico
para a visualização. A leitura usa a mesma fachada `Historico` da etapa 3.

Para gravar a nova sessão e sua odometria na base escolhida:

```powershell
.\iniciar_gemeo.ps1 -Historico 'C:\caminho\dados_historico' -Gravar
```

Gravar é opcional e usa o `Gravador` existente. As imagens obedecem à política de
armazenamento já existente; `-Gravar` não habilita gravação indiscriminada de JPEG.

## Telemetria real futuramente

Com o servidor da etapa 2 já validado e acessível, forneça o token existente por
`ROBO_REDE_TOKEN` no ambiente do terminal e execute:

```powershell
.\iniciar_gemeo.ps1 -Servidor 'ws://IP_DA_RASPBERRY:PORTA'
```

Selecione “Tempo real” no navegador. O token da Raspberry não é enviado ao
frontend. O servidor HTTP permanece restrito a `127.0.0.1`; a porta 8780 é do
visualizador, não necessariamente a porta WebSocket do robô.

`-Calibracao 'C:\caminho\calibracao_confirmada.json'` aceita parâmetros físicos
confirmados. O JSON deve conter `ppr_esq`, `ppr_dir`, `diametro_esq_m`,
`diametro_dir_m`, `bitola_m`, `confirmada: true`, `simulada: false` e, opcionalmente,
`relacao_disco_roda`. Não preencha com valores do cenário simulado. Não há
calibração real confirmada fornecida por este módulo.

## Interação e limites

Clique nas peças ou na lista para inspecionar; arraste para orbitar e use a roda
do mouse para ampliar. Há vistas superior, frontal, traseira, laterais e livre,
foco, acompanhamento do carrinho, chassi superior ocultável e vista explodida.
As opções técnicas controlam eixos, rodas/motores, discos/sensores, feixe do sonar,
FOV estimado e trajetória. A calibração visual do servo permite mínimo, máximo,
centro, inversão e deslocamento; não programa o servo físico.

PPR=20/20, diâmetros=0,065 m, bitola=0,18 m e relação disco/roda=1 são parâmetros
**somente do cenário sintético**, não resultados de calibração. As referências
de bancada de 19,4/19,2 PPR e 65 mm existentes no projeto não validam o piso e
não fornecem a bitola. Por isso não foram ativadas como calibração real.

O sonar usa os limiares existentes de `config.py`. Seu feixe de 15° é ilustrativo;
a caixa virtual tem seção simplificada e a opção de distância por obstáculo usa
interseção de raio com círculo de 6 cm. Não é uma simulação física de ecos.
O FOV ilustrativo usa 60° verticais e aspecto 4:3, sem calibração óptica; não é
a ROI do algoritmo de visão. Não existem coordenadas de linha fornecidas pelo
contrato atual; a interface informa isso e não desenha uma linha inventada.

O ângulo do servo é comandado; o sentido das rodas vem do comando e não do
encoder de canal único. A odometria é relativa, sujeita a deslizamento e erro
acumulado. Dados vencidos congelam a animação; não são usados para integrar
deslocamentos através de lacunas. Corrente, tensão e PWM físico aplicado não
são apresentados como medidos sem sensores/retorno correspondente.

## Arquitetura e validação

Leia [o guia técnico da etapa 4](../docs/22_gemeo_digital_3d.md) para o diagrama,
componentes, eixos, fórmulas, arquivos modificados, testes, desempenho e
validações físicas pendentes.

```powershell
python -m pytest tests/test_gemeo_digital.py tests/test_armazenamento.py -q
npm.cmd test --prefix gemeo_digital/frontend
```

O navegador executa verificações no modelo carregado; o resultado e métricas
de renderização podem ser consultados em `http://127.0.0.1:8780/api/diagnostico`.
Esse diagnóstico não substitui a inspeção mecânica do protótipo.
