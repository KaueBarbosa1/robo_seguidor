# Etapa 7 — auditoria e entrega da plataforma experimental

Data: 26/11/2026. Base inicial: `ab01861`. Esta auditoria combina inventário,
leitura dos caminhos de execução, testes automatizados, WebSocket local,
SQLite temporário/existente, avaliação de imagens reais arquivadas e inspeção
da interface. Não houve acesso ao carrinho, medição na Raspberry, alteração
de firmware, pinagem, ganhos, pesos ou treinamento solicitado nesta etapa.
Os testes legados de treinamento sintético continuam executáveis isoladamente.

## Evidência e classificação

Um arquivo existente não equivale a uma funcionalidade validada. As classes são:
**S** implementada e testada em simulação/software; **F** implementada e aguardando
validação física; **P** parcialmente implementada; **N** não implementada;
**E** bloqueada por dependência externa; **R** reprovada em teste.
Uma mesma funcionalidade pode ter S para software e F para comportamento físico.

| Área auditada | Estado | Evidência / limite |
|---|---|---|
| Organização e configuração | S/F | Inventário AST inicial de 160 Python operacionais/testes; 265 fontes/documentos versionados no inventário ampliado, sem erro sintático; `config.py` preservado |
| Serial Uno | S/F | `motor/serial_com.py`, decodificador e testes fragmentação/checksum; PTY integral requer POSIX; nenhuma COM física aberta |
| Firmware/PI/watchdogs | S/F | Fonte e harness host existentes; compilação host é lógica C++, não build AVR/upload nem resposta física |
| Bluetooth | S/F/E | Parser e arbitragem com fakes; BlueZ/D-Bus real é Linux; dependência opcional ausente neste Windows |
| ESP32-CAM AI Thinker / OV2640 | S/F | Fonte HTTP única, JPEG/idade/timeout/geração; ESP cria AP; câmera física pendente |
| OV7670/CSI | P | Caminhos legados/opcionais preservados, não são a montagem atual |
| OpenCV | S/F | ROI, cinza, GaussianBlur, limiar Otsu/fixo, abertura, segmentos/trajetória, memória limitada; testes geométricos e pipeline compartilhado |
| Hough | S/P | Comparação offline/testes próprios existentes; não virou detector principal silenciosamente |
| CNN própria | S/F/P | RedeLinha NumPy, 55.090 parâmetros nos pesos CNN02, hash `c3a865f28c9de7ff`; regressão offline reavaliada; visibilidade sem supervisão |
| CNN no carrinho | P | ROI y075 original incompatível com JPEG 320×240; não há autorização de navegação física |
| MobileNet legada | P | Ferramenta comparativa opcional; não substitui CNN própria; nenhuma dependência nova de modelo pronto |
| RL | S/E/P | Ambientes sintéticos/Q-learning/Gym e loaders existentes; checkpoints locais para integração ausentes; sem avaliação física/treino online |
| Ciclo legado de promoção | R | `test_ciclo_completo_sintetico`: não promove campeão no cenário/configuração atual; não afrouxar critérios para forçar promoção |
| PD local | S/F | `ThreadControle`, único caminho normal de referências, derivada filtrada; seguimento e ganhos físicos pendentes |
| Telemetria/benchmark | S/F | Registro limitado, produtor sem I/O, Sistema no worker; recursos reais do PC separados dos sensores virtuais |
| WebSocket | S/F | Cliente/servidor existentes, auth, canais/fan-out, latest frames, RTT; rede física não testada, TLS nativo ausente |
| SQLite/imagens | S | Mesmo Gravador/WAL/lock; migração cumulativa v6; hashes de JPEG, FK, backup/replay; bancos temporários nos testes destrutivos |
| Sessões/replay | S/F | Sessão operacional distinta da gravação; replay somente leitura, sem canal físico; origem preservada |
| Gêmeo GLB | S/F | Three.js único/modelo original preservado; materiais/hierarquia/animação em software; pivôs/sentido/escala física não calibrados |
| Odometria | S/F | Integração diferencial com calibração explícita; encoders monocanal dão magnitude e sentido comandado; referência externa pendente |
| Dashboard | S | Quinze páginas, mesma captura/ponte/GLB, histórico/eventos/câmera/controle e página científica ampliada |
| Distribuição | S/F | Pipeline idêntico local/remoto, frame/sessão/geração/idade, expiração no relógio Pi, nenhum fallback automático |
| Controle remoto | S/F | Lease exclusiva, presença, desafio de prazo curto, parada prioritária/emergência; não certifica frenagem física |
| Simulador | S/P | Executa controlador real e transporte localhost; motor virtual não é planta PI física identificada; não mede estabilidade de pista |
| Experimentos A–D | S/F/P | A–D virtuais parados; B/D diagnósticos; quatro configurações físicas documentadas, ainda sem resultados |
| Estatística/gráficos/relatórios | S | Médias por execução, regressão, bootstrap condicionado, controles/odom; PNG/SVG/CSV/JSON/MD/HTML; PDF por impressão manual |
| CI | F/E | Workflow sem deploy/push automatizado, Windows/Linux; arquivo preparado, não executado no GitHub nesta entrega |

## Problemas comprovados e correções

1. **Configuração contaminada entre testes**: testes antigos escreviam atributos
   globais de `config`. Fixture restaura esses atributos entre casos. Não muda
   configuração operacional e não mascara a falha de aprendizado.
2. **Teste de aviso com Mock incompleto**: `timestamp` fictício era um Mock,
   causando subtração inválida. O teste declara diagnóstico ausente; mantém
   verificações de partida/cancelamento.
3. **Testes incompatíveis com Windows**: shell Linux/PTY e dependência BlueZ
   recebem motivo explícito de bloqueio/skip. Roteiro PTY que executa ao importar
   roda isolado no Linux pelo executor; não polui a coleta pytest.
4. **Benchmark com formato de rede diferente**: Benchmark esperava `rtt_s` no
   topo, mas o Cliente fornece `canais.telemetria.rtt_s`. Leitura compatível
   corrigida; executor falha se o worker de benchmark falhar.
5. **Rótulos CRLF/LF**: preservados hashes bruto e normalizado. Só conversão
   CRLF→LF pode equivaler ao snapshot original, sem tolerar conteúdo diferente.
6. **Associação de sessão antes do primeiro commit SQLite**: executor espera
   existência da sessão no banco antes de vincular execução/experimento.
7. **Mudança CNN→distribuído prematura**: espera parada confirmada e intervalo
   administrativo de estabilização da autoridade; não desativa a guarda.
8. **Terminal Windows**: ferramentas novas escrevem stdout UTF-8 para evitar
   falhas apenas de impressão de setas/símbolos após gerar arquivos corretamente.
9. **Confirmação de escrita sob carga**: drenagem final pode exceder10s. Prazo
   explícito até60s para confirmar encerramento/sincronização, sem cancelar
   transação em andamento; evidência parcial salva antes da confirmação final.
   O relatório distingue tentativa falha de nova execução concluída.
10. **Interface antes da primeira amostra**: extração/identidade toleram estado
    ainda ausente e os formulários são vinculados antes da consulta assíncrona,
    evitando exception e submissão GET acidental. Campos ausentes não viram zero.
11. **Comparabilidade**: filtros de origem/nível/categoria também chegam à
    comparação; mudança de filtros limpa resultados antigos. Verificam-se
    condições, host/software e consistência de versão por algoritmo.
12. **Fechamento WebSocket**: fechamento pode ocorrer durante o último ACK.
    Agora é registrado sem traceback espúrio, mantendo revogação no finally.

## Divergências e riscos que não foram alterados

- `arduino/robo_firmware/config.h` define `USAR_CAMERA=0`, embora comentários
  antigos e o cabeçalho do `.ino` descrevam OV7670 como definitiva/padrão.
  O padrão atual ESP32 é externo e conserva serial para sensores/motores.
  Conferir documento elétrico atual, defines e fios antes de gravar firmware.
- Nomes ENA/ENB são canais lógicos: comentários do mapa informam bornes físicos
  invertidos. Não inferir ligação a partir do nome; guia físico exige conferência.
- PPR/diâmetros registrados e ganhos não equivalem a calibração de odometria,
  resposta PI/PD ou distância de frenagem no piso.
- Modo Bluetooth manual já permite bypass do ultrassom por decisão anterior.
  Não foi removido nem enfraquecido; rede PC não herda esse bypass. Sem eco
  não é possível garantir detecção de novos obstáculos nesse perfil manual.
- ESP32 tem senha padrão de bancada no firmware; conferir configuração local
  antes de utilização fora da bancada. Não alteramos rede ou credenciais.
- Um RTT não mede latência unilateral; instante da captura ESP não é relógio Pi.
- Escritor único e filas limitadas evitam crescimento sem limite, mas não
  garantem latência sob saturação. Limites produzem descartes identificados.
- `pip check` encontrou conflito global **giddy 2.3.8 / esda 2.9.0** fora das
  dependências do projeto. Não alteramos esse ambiente; usar venv dedicada.
  Evitar instalar simultaneamente múltiplas distribuições OpenCV no mesmo venv.
- Copias congeladas do código em resultados/Relatorio são evidências históricas,
  não devem ser refatoradas junto ao código operacional. Não foi criada uma
  segunda infraestrutura de banco, captura, transporte ou controle.

## Entregáveis e comandos

Metodologia e hipóteses: [26_metodologia_experimental.md](26_metodologia_experimental.md).
Instalação/calibração/bancada/pista: [27_validacao_fisica_e_manutencao.md](27_validacao_fisica_e_manutencao.md).
Rastreabilidade/diagramas: [28_rastreabilidade_e_arquitetura.md](28_rastreabilidade_e_arquitetura.md).
Resultados medidos: [29_resultados_etapa7.md](29_resultados_etapa7.md).
Manual: [../experimentos/README.md](../experimentos/README.md).

Novos módulos: `experimentos/{configuracao,executor,repositorio,analise,visao,relatorios}.py`;
ferramentas `tools/{experimentos,testes,auditar_projeto}.py`; página científica
`central_monitoramento/frontend/src/experimentos.js`; inicializador
`iniciar_projeto.ps1`; preparação Pi `deploy/preparar_raspberry.sh`; workflow
`.github/workflows/testes-software.yml`; testes Python/JS e configurações JSON.
Alterados somente os pontos de integração/benchmark/armazenamento/teste/docs
necessários. Matplotlib/pytest formalizados em requirements exclusivo do PC;
nenhuma nova dependência de inferência no robô.

```powershell
.\iniciar_projeto.ps1 -Acao instalar
.\iniciar_projeto.ps1                     # central completa, simulador parado
.\iniciar_projeto.ps1 -Acao testes -Categoria todos
.\iniciar_projeto.ps1 -Acao experimento    # com a central anterior encerrada
.\iniciar_projeto.ps1 -Acao visao -Saida dados_experimentos/nova_avaliacao
```

Com a central aberta, use **Experimentos**, sem executar outra CLI escritora
na mesma raiz. Ctrl+C no terminal encerra os serviços que esse processo iniciou.
Não existe encerramento global por nome de processo nem kill de aplicações alheias.
Não há deploy/push automático. A falha legada permanece visível e faz `todos`
retornar código diferente de zero.
