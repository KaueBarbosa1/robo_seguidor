# Plataforma experimental no PC

Reutiliza Central/Fluxo/Servidor/Cliente/fan-out/Gravador/SQLite da Etapa6.
Não há segundo banco ou aquisição concorrente. A execução é virtual e parada;
CNN02 é diagnóstico, não navegação. O roteiro físico está em docs/27.

## Fluxo principal

```powershell
.\iniciar_projeto.ps1 -Acao instalar
.\iniciar_projeto.ps1
```

Abrir **Experimentos**: editar JSON, iniciar, consultar progresso, cancelar,
filtrar por origem/nível/categoria, escolher experimento, comparar médias por
execução. Gerar relatório abre links CSV/JSON/MD/HTML/ZIP e gráficos PNG/SVG.
**Reproduzir** usa a sessão existente no gêmeo, somente leitura.
As opções reais não têm dados nesta entrega e não são preenchidas artificialmente.

## CLI e reprodução

Com a central anterior encerrada, pois a mesma base aceita só um Gravador:

```powershell
python tools/experimentos.py executar experimentos/configuracoes/comparacao_pc.json
python tools/experimentos.py executar experimentos/configuracoes/carga_5min.json
python tools/experimentos.py listar
python tools/experimentos.py relatorio UUID_DA_EXECUCAO --interpretacao "Análise manual do pesquisador"
python tools/experimentos.py visao --saida dados_experimentos/visao_nova
python tools/experimentos.py analisar resposta.csv --tipo degrau --origem real --nivel 4 --inicial 0 --alvo 4 --unidade pps --saida dados_experimentos/resposta_nova
python tools/auditar_projeto.py
python tools/testes.py rapidos
python tools/testes.py unitarios
python tools/testes.py integracao
python tools/testes.py interface
python tools/testes.py seguranca
python tools/testes.py carga
python tools/testes.py todos
```

`--historico <raiz>` seleciona uma base existente explicitamente; o padrão
reutiliza a raiz da central. Saídas integradas ficam em
`<raiz_historico>/experimentos/<UUID>/`, com amostras CSV, imagem/hash, manifesto,
Benchmark original e relatórios. Não escrever resultados grandes no Git.
`dados_experimentos/` contém auditoria/testes/avaliação offline locais ignorados.

Os comandos de testes propagam falhas. O ciclo legado de promoção sintética
está reprovado no estado atual e não foi removido/xfail para deixar CI verde.
PTY/Wi-Fi/BlueZ exigem plataforma/dependências específicas e têm motivo explícito.
O simulador integral da porta serial roda separado no Linux, para não executar
código ao importar no processo pytest. Não há testes com dispositivo físico.

Análise de CSV externo também aceita `--tipo regressao` (colunas real/previsto),
`odometria` (x_m/y_m/theta_rad e ref_x_m/ref_y_m/ref_theta_rad) e `serie`
(tempo_s/valor). Regressão/odometria exigem `--referencia` descrevendo a referência
independente. Degrau usa tempo_s/medido, inicial/alvo e unidade. A ferramenta
registra hash/origem/nível declarados e gera JSON/PNG/SVG; não comprova que o
operador calibrara a referência. Não há CSV físico de resposta nesta entrega.

## Configuração e limites

Planos versionados aceitam A/B/C/D, duração1–86400s, aquecimento,1–100 repetições,
seed/taxas/atraso e registro opcional de JPEG. Hoje o cenário integrado é um
JPEG sintético fixo compartilhado480×640, para isolar software. Usar outro cenário
exige implementação e identificação novas; não fingir um percurso em movimento.
Para15/30/60min alterar duração para900/1800/3600s no plano de carga.
Comparação só entre mesma origem/nível/categoria e condições controladas iguais.
Cada execução é um voto; as telemetrias internas não inflam n de repetições.

Estatísticas limitadas às últimas25000 amostras por métrica e CSV limitado50MB;
Benchmark também tem limite de arquivo. Frequências são alvos, registrar as
efetivas. Dados não disponíveis são NULL. Falha de worker, cancelamento e
bloqueio de peso/contrato ficam no banco, sem conclusão automática.

Dependências de análise são do PC. Não instalar Three.js/SQLite/reporting na Pi
para fazer renderização/banco no carrinho. Gráficos e relatório por HTML/PNG/SVG;
PDF pode ser obtido por impressão do HTML. Nenhum serviço é publicado.

Metodologia: docs/26. Auditoria/pendências: docs/25. Matriz: docs/28.
Resultados observados e limitações: docs/29.
