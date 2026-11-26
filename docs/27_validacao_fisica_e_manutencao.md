# Instalação, calibração, validação física e manutenção

**Documento de preparação, não registro de ensaio executado.** Todos os campos
de aprovação física estão pendentes. Raspberry Pi5, UnoR3, ESP32-CAM AI Thinker
OV2640, L298N, DC/encoders monocanal, servo e HC-SR04 seguem a montagem do usuário.
Nenhuma conexão foi modificada. Conferir `docs/00`, `07`, `09`, `11`, `12`, `14`
e os defines ativos antes de registrar pinagem. Fotos e continuidade informadas
pelo usuário não substituem uma inspeção atual com fontes desligadas.

## Instalação e comandos

Windows, em venv exclusiva, na raiz do repositório:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
.\iniciar_projeto.ps1 -Acao instalar
.\iniciar_projeto.ps1 -Perfil simulacao-embarcada
# Outros perfis virtuais: -Perfil simulacao-distribuida
python tools/testes.py todos
python tools/auditar_projeto.py
```

GLB original deve estar em `gemeo_digital/modelos/carrinho_configurado.glb`, com
o JSON de componentes/eixos já existente. Não substituir modelo. Three.js usa
lockfile e módulos estáticos; não há bundler/build separado do frontend.
Não há necessidade de iniciar um servidor de banco ou outro processo de gêmeo:
a mesma central gerencia ponte, escritor, dashboard e renderização.

Raspberry, executar posteriormente pelo operador, em Raspberry Pi OS compatível:

```bash
cd /caminho/real/robo_seguidor
python3 -m venv venv
bash deploy/preparar_raspberry.sh
venv/bin/python tools/verificar_ambiente.py
venv/bin/python main.py --help
```

Se dependências nativas de áudio/OpenCV não instalarem, verificar versão do OS,
Python e bibliotecas de sistema conforme o guia específico; não substituir
automaticamente pesos/versão scikit-learn dos modelos de voz. O instalador novo
não usa sudo, não grava firmware, não muda Wi-Fi e não ativa systemd. O serviço
existente pode iniciar a main; parar o serviço **antes** de iniciar outra main:

```bash
systemctl --user status robo.service
systemctl --user stop robo.service
journalctl --user -u robo.service -n 100 --no-pager
```

Modo embarcado sem rede deve permanecer operável sem dashboard. Para bancada de
visão sem serial, `main.py --sem-arduino --fonte-imagem esp32` usa motor nulo,
mas requer endereço/rede da câmera e dependências locais já conferidos. Para
modo observacional real, configurar token existente no terminal e usar `main.py
--rede --benchmark` somente após inspeção. `--operacao-rede` prepara um canal
protegido; **não** criar aprovação física fictícia para liberar atuação.
Não usar comandos de movimento durante instalação ou testes de câmera.

## Registro de inspeção elétrica e mecânica

Preencher responsável/data, instrumento/faixa, medida, origem documental,
resultado e evidência em cada linha. Todos **não executados** nesta entrega.

| Verificação | Procedimento | Aprovação / interrupção |
|---|---|---|
| Fontes/baterias/regulador | Identificar modelo, tensão e corrente nominais; medir saída sem carga e com carga progressiva | Compatível com especificações dos módulos; interrupção por queda/aquecimento/cheiro |
| Polaridade e curtos | Desenergizar, conferir continuidade e isolamento, bornes/jumpers/placa universal | Sem curto, sem fio solto/exposto; não energizar se houver dúvida |
| GND e alimentação | Conferir mapa real de massas e circuitos que exigem referência comum; evitar dupla alimentação não prevista | Ligação confirmada documentalmente e por medida; não inferir pelos nomes ENA/ENB |
| Raspberry e ESP32 | Conferir fonte adequada, estabilidade/subtensão e fixação da placa/câmera | Sem reset/subtensão sob carga prevista; falha interrompe avanço |
| L298N e DC | Conferir borne lógico/físico, jumpers ENA/ENB, isolamento e aquecimento | Primeiro rodas suspensas; se inverter sentido, registrar e interromper, sem trocar pinagem automaticamente |
| Encoder por roda | Conferir posição/fixação, um canal por roda, pulsos cruzados e liberdade do disco | Cada roda informa somente seu canal; erro implica recalibração |
| Servo/HC-SR04 | Conferir fixação, alcance mecânico, cabos livres e níveis no componente correto | Sem colisão do suporte/cabo; ECHO não pode ser inferido como compatível com GPIO da Pi |
| Serial/USB | Identificar dispositivo/porta/baud e fonte única de comunicação | Um processo proprietário da serial; reset ou leitura inválida bloqueia movimento |
| Ruído/aquecimento | Comparar câmera/serial/CPU com motores desligados e depois carga controlada | Sem resets/erros; aquecimento excessivo interrompe teste |

Não medir continuidade em circuito energizado. Não registrar tensões/correntes
nominais inventadas: copiar da documentação/etiqueta do módulo e confirmar com
instrumento. Não alimentar motores a partir de uma porta USB sem fonte adequada.

## Fases de validação A–M

Ficha por fase: UUID do ensaio; operador/data; equipamento; versão/hash Git e
firmware gravado; condição inicial; procedimento; dados; falha; resposta esperada;
resposta observada; tempos disponíveis; evidência; aprovação/reprovação/bloqueado.
É obrigatório parar na fase anterior se os critérios de segurança não passarem.

### A — Alimentação e inspeção

Pré-requisito: fontes desligadas, diagrama atual e multímetro. Equipamentos:
fontes/baterias identificadas, multímetro, suporte para rodas. Executar checklist
acima; sem comando de movimento. Esperado: ligações fixas e alimentação estável.
Aprovar só com polaridade/continuidade/tensões documentadas. Interromper por curto,
instabilidade ou aquecimento. Registrar medidas/fotos; falha exige revisão manual.

### B — Comunicação básica

Pré-requisito: A aprovada; rodas suspensas e motores sem habilitação. Equipamentos:
Pi/Uno/ESP/celular/PC e rede identificada. Comandos: `verificar_ambiente.py`, logs
systemd, `main.py --help`; listar portas por ferramenta do sistema. Confirmar um
serial owner, endereço ESP e Bluetooth do celular na Pi. Esperado: conexões sem
movimento. Falha de porta/baud/rede → parar serviços e diagnosticar, não abrir
segundo serial. Registrar dispositivos/endereço/versões, sem publicar tokens.

### C — Telemetria

Pré-requisito: B e serial única. Equipamentos: Uno, sensores, referência de
distância e roda livre. Usar painel/coletor existente e `--benchmark`; conferir
F8, idade dos sensores, flags de encoder, servo e zero comandado/informado.
Esperado: atualizações coerentes e ausência de movimento. Aprovar atualidade e
identidade por canal; valores vencidos/sem confirmação interrompem. Registrar
CSV/eventos e medida externa. Não confundir PWM informado pelo firmware com
velocidade física comprovada.

### D — Câmera

Pré-requisito: C, fixação/energia da ESP estáveis. Equipamentos: ESP/PC/Pi,
referência visual. Usar fonte/painel de coleta existente, compartilhado; teste
de bancada pode usar `main.py --sem-arduino --fonte-imagem esp32`. Verificar JPEG,
320×240 atual, FPS, geracao, idade e desconectar/reconectar. Esperado: perda
sinalizada e frame antigo rejeitado. Aprovar captura estável com registro;
reset/idade excessiva interrompe. Salvar imagens reais identificadas, não iniciar
outra captura concorrente nem reprogramar ESP sem necessidade/autorização.

### E — Processamento de imagens

Pré-requisito: D, zero motor. Equipamentos: imagens/rotulador, pesos próprios.
Comparar imagens idênticas com `tools/experimentos.py visao --saida <nova_pasta>`
no PC; na Pi testar inferência isolada com seu mesmo contrato. Conferir hash,
orientação, ROI e normalização. Esperado: previsões finitas, erro reportado quando
ROI não cabe. CNN02 320×240 permanece bloqueada, sem redimensionamento oculto.
Aprovar somente diagnóstico compatível; erro/hash/semântica bloqueia avanço.
Registrar tempos/hashes/outputs, sem promover ou treinar modelo.

### F — Comunicação distribuída

Pré-requisito: E e rede/topologia confirmadas. Equipamentos: PC/Pi, tokens por
papel e bancada sem movimento. `main --rede --benchmark` prepara observação;
canal operacional opt-in conforme guia24, com atuação bloqueada. Verificar
frame/sessão/geração/inferência, heartbeat, prazos e filas. Esperado: rejeição de
antigo/duplicado e ausência de fallback/retomada. Aprovar logs correlacionados;
incompatibilidade ou reconexão invalida intenções. Registrar RTT e idade no
relógio Pi; não calcular latência unilateral entre relógios independentes.

### G — Segurança

Pré-requisito: F; primeiro simulação, depois rodas suspensas com interrupção
física da alimentação dos motores acessível. Equipamentos: suporte estável,
barreira inanimada adequada, operador. Usar testes de segurança virtuais e roteiro
do guia24; introduzir câmera/Arduino/sensor/heartbeat/rede ausentes, comando
inválido/conflito e emergência. Esperado: solicitação de parada e ausência de
retomada automática. Confirmar física e independentemente que rodas cessam.
Registrar detecção/pedido/dados F8 e cessação física separadamente. Qualquer
movimento não autorizado/reinício obriga interrupção. Pessoas/animais não são
obstáculos. Bypass manual Bluetooth requer avaliação própria, não herdar para PC.

### H — Calibração

Pré-requisito: G e autorização de bancada; fita métrica/paquímetro/marcações.
Medir diâmetro efetivo **por roda**, PPR no eixo efetivo, transmissão, bitola entre
centros de contato, sentido do comando, câmera e centro/limites servo. Usar
`tools/calibrar_encoders.py --help` antes de qualquer ensaio: a execução com motor
é um procedimento físico a habilitar manualmente. Primeiro girar roda manualmente,
contar várias voltas e repetir; registrar assimetria/incerteza. Nunca multiplicar
duas vezes a relação de transmissão se PPR já estiver referido à roda.
Sem medição de bitola não há orientação calibrada. JSON deve declarar confirmado
só após medida e evidência; não alterar automaticamente PI/PD/firmware. Divergência
de pulsos/sentido → interromper e revisar.

### I — Movimentação controlada

Pré-requisito: A–H aprovadas, habilitação explícita do operador. Equipamentos:
espaço livre, baixa referência definida para a bancada/piso, corte físico.
Executar ferramenta existente somente após ler `--help`; uma roda de cada vez,
depois frente/ré/giro. Esperado: sentido correto e parada; registrar referência,
pps/PWM/ticks/tempo externo. Aprovar limites/direções e parada; travamento,
deriva inesperada, falta de encoder ou reset interrompe. Não autoajustar ganhos.

### J — Seguimento de linha

Pré-requisito: I e limites provisórios aprovados pelo pesquisador. Equipamentos:
pista marcada, iluminação registrada e referência externa calibrada. Cenários:
reto, curva suave, curva acentuada, curvas consecutivas, completo, iluminação,
interrupção da linha, obstáculo estático, diferentes velocidades e rede degradada.
Primeiro OpenCV embarcado com baixa velocidade; cada início é uma habilitação
explícita. Registrar erro em imagem separado de erro físico, conclusão/tempo,
distância/velocidade, perdas/duração, intervenções e segurança. Falha de referência
ou parada insegura interrompe o percurso. CNN/RL só após contrato/validade próprios
e aprovação separada; esta entrega não libera esses modos na pista.

### K — Comparação experimental

Pré-requisito: J, hipóteses/plano registrado e configurações compatíveis. Executar
A/C e, futuramente B/D, com mesma pista/frames/velocidade/ganhos, aquecimento,
5/10 ou mais repetições, ordem alternada/aleatória. Registrar temperatura/bateria
inicial e carga observacional. Esperado: sessões independentes reproduzíveis;
condição diferente identifica comparação não homogênea. Interromper por segurança
ou aquecimento; execução interrompida permanece no banco, não descartar silenciosamente.

### L — Gêmeo digital

Pré-requisito: telemetria/calibração e roteiro seguro. Equipamentos: PC/GLB original,
vídeo físico de referência. Conferir materiais/hierarquia, eixos/pivôs, sentido
rodas/discos, servo/sonar/FOV, trajetória, seleção, replay/pausa/seek. Registrar
FPS/tempo de carga/CPU-render e diferença temporal observável; câmera física
separada pode comparar eventos sem inferir sincronização perfeita. Aprovar
coerência observada; congelamento/deslocamento errado → parar/registrar, não
compensar alterando geometria original sem diagnóstico.

### M — Análise final

Pré-requisito: sessões finalizadas, integridade/FK verificadas e backup. Equipamentos:
PC e registros externos. Exportar CSV/JSON, gerar gráficos/relatório e anexar
interpretação manual. Separar N1–N5, dados faltantes, interrompidos e limitações.
Esperado: tabelas por repetição e fontes rastreáveis; critérios preenchidos pelo
pesquisador. Não declarar superioridade, significância, energia ou autonomia
sem desenho/medição adequados. Dados incoerentes bloqueiam conclusão, não são zero.

## Recuperação e manutenção

- **Banco**: usar backup online do módulo existente `armazenamento.backup.criar`;
  verificar integridade e hashes. Restauração é para **pasta nova**, preserva
  original e arquivos JPEG. Consultar `python tools/historico.py --help` para
  subcomandos. Nunca copiar apenas `.db` aberto ignorando WAL nem apagar base real.
- **Sessão interrompida**: escritor detecta gravações órfãs no boot e registra
  interrupção; a execução experimental em andamento recupera estado equivalente.
  Exportar evidência parcial, criar nova repetição, sem inventar instante final.
- **Câmera**: revisar energia/flex/endereço/rede/Content-Type/JPEG/idade/geração;
  testar fonte existente isolada; não abrir segunda captura na mesma main.
- **Serial**: parar serviço anterior; conferir porta/baud/define USAR_CAMERA e
  log de protocolo; sem motor até sensores e F8 coerentes. Não mudar pinos às cegas.
- **Pesos**: conferir manifesto/hash/entrada/ROI/normalização; pesos incompatíveis
  falham explicitamente. Não usar modelo aleatório/pré-treinado como fallback.
- **Rede**: conferir papéis/tokens localmente, RTT/canais/heartbeat/geração/filas;
  não imprimir credenciais. Desconexão exige nova habilitação, nunca replay de comandos.
- **Retorno embarcado**: parar e liberar autoridade, confirmar repouso, selecionar
  embarcado ou encerrar canal/central; main padrão não depende do PC. Reiniciar
  serviço só com autorização e condições seguras. Não fazer rollback em movimento.
- **Versão**: preservar Git; criar branch/checkout isolado para diagnóstico e
  conferir migração suportada antes de abrir banco. Software antigo pode recusar
  v6: usar backup pré-migração em pasta nova, sem downgrade destrutivo da base.
- **Encerramento**: cancelar coleta, encerrar gravação, Ctrl+C no terminal dono;
  verificar liberação do writer/porta e estado físico parado. Não matar processos
  arbitrários nem reiniciar firmware/carrinho automaticamente.
