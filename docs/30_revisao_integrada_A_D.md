# Revisão integrada A–D — código, computador, visual e Raspberry

Esta revisão sucede a entrega da Etapa7. O relatório final distingue execução
de software no Windows, instalação preparada e validações físicas pendentes.
Acesso SSH confirmado em `carrasco@192.168.3.76`, hostname `redecarr0`.
Raspberry Pi5 ModelB, 8GB, Debian13/aarch64, Python3.13.5. O endereço
`192.168.4.1` identifica exclusivamente a ESP32-CAM.

## Instalação mínima e transferência

Preparar o pacote no PC com `.\iniciar_projeto.ps1 -Acao pacote-pi`.
Ele contém os fontes operacionais, os modelos de voz existentes e os pesos
originais CNN02, com manifesto SHA256. Exclui banco/histórico, imagens/vídeos,
GLB/Three.js/dashboard e credenciais SSH/.env. O código opcional de RL permanece
preservado, mas suas dependências de treinamento não são instaladas na Pi.

Transferir o ZIP para uma **pasta nova**,
sem sobrescrever a instalação anterior. Não desabilitar a verificação da chave
SSH. Confirmar fingerprint com o operador em caso de primeiro acesso ou mudança.
Endereço confirmado nesta bancada (pode mudar por DHCP):

```powershell
scp CAMINHO_DO_ZIP carrasco@192.168.3.76:~/robo_pi.zip
```

Na Pi, inspecionar o arquivo e extrair para uma pasta nova. Em seguida:

```bash
# Perfil mínimo: câmera, controle, serial e aplicativo Bluetooth; sem áudio.
bash deploy/preparar_raspberry.sh --perfil bluetooth --rede
# Teste de visão/rede com motores nulos; não conecta ao Arduino.
bash deploy/iniciar_raspberry.sh --sem-arduino --benchmark
```

Perfis: `visao` não instala voz/Bluetooth; `bluetooth` acrescenta dbus-fast;
`completo` acrescenta áudio, SciPy/joblib e scikit-learn1.8.0 dos modelos existentes.
`--rede` instala WebSocket e métricas. Nenhum perfil instala Matplotlib, banco
histórico, renderer3D, Torch ou ferramentas de experimentação do PC.

Para a comunicação real posterior, definir token forte no terminal e iniciar
`deploy/iniciar_raspberry.sh --rede --host IP_LOCAL_DA_PI --benchmark`.
O PC usa `.\iniciar_projeto.ps1 -Perfil monitoramento -Servidor ws://IP_LOCAL_DA_PI:8765`.
Cada equipamento tem seu processo: o comando do PC não inicia magicamente a Pi
sem uma conexão SSH confirmada. Banco, renderer e treinamento permanecem no PC.
Não iniciar duas mains nem competir com `robo.service` pela serial.

O inicializador da Pi limita explicitamente captura a10FPS e OpenCV a1thread.
São limites iniciais de bancada, não desempenho físico medido. A main mantém
compatibilidade: flags `--sem-voz`, `--sem-bluetooth`, `--camera-fps` e
`--opencv-threads` são opt-in. Não há treino automático ou movimento inicial.
Antes de remover `--sem-arduino`, cumprir as fases elétricas e de segurança do
guia27. A CNN02 continua diagnóstica: sua ROI não cabe em320×240 e a visibilidade
não foi supervisionada. Nenhum modelo pronto ou peso novo a substitui.

## Correções sob revisão

- Teste legado usava30s por episódio e coletava304 rótulos de treino, abaixo do
  mínimo600. Agora usa a duração de produção e verifica o pré-requisito antes
  da promoção. Nenhum limite/ganho/peso de produção foi reduzido.
- Checagem comum de dimensões JPEG/PNG antes do decoder limita alocação de RAM,
  compartilhada por recepção ESP32, percepção distribuída, upload local e armazenamento.
- Experimentos restauram as taxas/opções anteriores após coleta, distinguem
  resultados bloqueados e limitam eventos mantidos em RAM. A checagem SQLite é
  interrompível por cancelamento e tem prazo explícito.
- Servidor simulado conectado como real (ou o inverso) não gera telemetria
  exibida como válida no domínio incorreto. Replay mantém sua origem histórica.
- Queda de thread essencial termina a main com erro depois de solicitar parada,
  permitindo diagnóstico pelo supervisor do processo.

## Verificações concluídas em26/11/2026

- Suíte completa no Windows:495 testes Python aprovados,56 subtestes e13
  ignorados por plataforma/dependência;19 testes JavaScript aprovados.
  Harness C++ do firmware: TUDO_OK, zero falhas. PTY/POSIX continua bloqueado
  no Windows; não é resultado de serial/firmware gravado em placa.
- Sintaxe dos187 arquivos Python já versionados conferida. Novos módulos
  foram importados/exercitados nos testes. A auditoria estrutural das sete
  etapas e a matriz de40 requisitos permanecem nos guias25 e28.
- As15 páginas da central carregaram sem erro de inicialização/console após
  reinício pelo comando oficial. Modelo original313 nós/37 materiais carregado.
  Ensaio virtual40,80s:270 amostras de movimento frente/giro, sem erro;
  servo120° e retorno90°, pulsos/rodas/odometria/gráficos e trajetória estimada.
  Final PARADO, sem gravação ativa. Animação/congelamento também cobertos nos
  testes JS. Não confirma escala, sentido, encoder ou frenagem físicos.
- Corrigido indicador de parada: confirmação antiga não aparece como parada
  atual quando o modo permite movimento. Mantida a confirmação por dados,
  sem apresentar PWM informado como medição independente de frenagem.
- O teste sintético legado agora alcança o mínimo real de rótulos; não foram
  reduzidos critérios de promoção. Testes de sonar com prazo10ms passaram
  a usar relógio falso local, evitando depender do escalonamento do Windows.
- Executor de testes retorna2 quando falta uma dependência solicitada,
  em vez de anunciar sucesso. Bloqueios opcionais de plataforma ficam explícitos.

Evidências locais em `dados_experimentos/revisao_abcd/`: `aprovacao_final/`
(resultadoJSON/JUnit/logs), `interface/` (15 páginas, capturas e snapshots de
movimento), `preservacao.json` e `pi/`. Ensaios anteriores falhos foram mantidos;
`aprovacao_final` é a execução posterior às correções, não alteração dos históricos.

## Instalação e ensaios realmente feitos na Pi

Código transferido separadamente para
`/home/carrasco/robo_implantacoes/revisao_bf509b22`, sem substituir
`/home/carrasco/Downloads/robo_seguidor`. Venv novo, perfil `bluetooth --rede`:
NumPy2.5.5, OpenCV headless5.1.0.95, pyserial3.5, dbus-fast5.2.0,
websockets14.2 e psutil7.2.2; `pip check` aprovado. Sem bibliotecas de voz,
Torch/Gym/Matplotlib, banco histórico, dashboard ou GLB na Pi. Importação da
main e sintaxe dos scripts Bash aprovadas nesse ambiente.

O serviço de sistema antigo `robo.service` tentava reiniciar continuamente
porque `/dev/ttyACM0` não existia. Foi solicitada e observada sua parada pelo
operador. Continua habilitado para boot e aponta à instalação antiga; não foi
reconfigurado. Não iniciar duas mains; a migração do autostart exige concluir
bancada/Arduino primeiro. Nenhum firmware foi enviado nem motor físico acionado.

Ensaio40s da main real na Pi, `--sem-arduino --sem-voz --sem-bluetooth`, imagens
sintéticas, benchmark e servidor observacional autenticado. Controle próximo20Hz;
processo0,54%CPU médio, RSS máximo61.603.840bytes e58,95–61,15°C, sem flags de
subtensão/throttling no período. Esse ensaio é PARADO: não representa carga de
captura/inferência contínua nem garante ausência de sobrecarga na pista.

Cliente real no PC recebeu121 telemetrias em12,14s:9,95Hz, sem lacunas de
sequência observadas; RTT médio24,09ms, p95 68,29ms, seis sondas. Fila latest=1
substitui amostras antigas deliberadamente; não afirmar perda zero da rede.
Canal de imagens autenticou, mas não recebeu JPEGs nesse teste de fonte
sintética. O processo encerrou com código0 e fechou as conexões.

Teste adicional ISOLADO na Pi, imagem sintética640x480 compatível com ROI,
50 inferências por algoritmo a5Hz, OpenCV/OpenBLAS1thread: OpenCV3,41ms
médios/1,7%CPU; CNN própria1,04ms/0,5%CPU, RSS máximo64.634.880bytes. São
latências dessa entrada e carga, não qualidade, taxa máxima, câmera ou navegação.
CNN retornou `navegavel=false`, como exigido. Nenhum treino ou peso alterado.

Para iniciar posteriormente a Pi com rede e motores nulos, nessa pasta:

```bash
ROBO_REDE_TOKEN="$(cat .rede_token)" bash deploy/iniciar_raspberry.sh --sem-arduino --rede --host 192.168.3.76 --benchmark
```

O segredo local tem permissão600; não faz parte do ZIP/Git/relatório. No PC,
definir o mesmo `ROBO_REDE_TOKEN` na sessão e usar:

```powershell
.\iniciar_projeto.ps1 -Perfil monitoramento -Servidor ws://192.168.3.76:8765
```

Com `--sem-arduino`, a telemetria é marcada simulada e o painel em origem real
recusa a incompatibilidade, em vez de rotulá-la como física. O cliente de teste
aceitou essa origem explicitamente. A conexão do dashboard a dados físicos
completos aguarda Arduino, câmera e verificações de bancada.

## Pendências e estado das fases

| Fase | Resultado verificável | Limite |
|---|---|---|
| A | Correções e regressões concluídas | Não é prova da ausência de todo defeito |
| B | Sistema integrado simulado e suíte completa aprovados |13 skips e PTY Windows explícitos |
| C |15 páginas/GLB/gráficos/movimento virtual conferidos | Sincronização/calibração físicas pendentes |
| D | Pacote/perfil mínimo instalado; SSH e telemetria Pi–PC testados | Câmera/Arduino, serviço novo e pista pendentes |

A rede `Carrinho-CAM` não apareceu durante as buscas iniciais; operador informou
que a câmera estava desligada. A transmissão real ESP32→Pi→PC não foi validada
nesses ensaios. Arduino permaneceu desconectado. Não remover os bloqueios de
atuação real, habilitar treino ou declarar autonomia física antes do guia27.
PesosCNN02, códigoCNN, firmware, pinagem, ganhos, Bluetooth e GLB preservados.

