# Etapa 6 — execução no Windows

Na raiz do projeto, com as dependências anteriores instaladas:

```powershell
.\iniciar_distribuido.ps1
```

Abre a central em <http://127.0.0.1:8780>, com execução virtual e percepção
embarcada como padrão. Não abre ArduinoSerial, Bluetooth ou câmera física.
Para iniciar já com percepção distribuída **e motores virtuais parados**:

```powershell
.\iniciar_distribuido.ps1 -Perfil simulacao-distribuida
```

Não execute outro gravador/central sobre a mesma base. Encerre a instância
anterior com `Ctrl+C`. Se necessário, instale com `instalar_central.ps1`.
Nenhuma dependência de execução nova foi adicionada nesta etapa.

## Utilizar o controle

1. Abra **Controle remoto**. Verifique a origem SIMULAÇÃO e a parada confirmada
   pelos dados virtuais.
2. Clique em **Habilitar controle**. Use W/A/S/D, setas ou mantenha um botão
   direcional pressionado. Espaço solicita parada. A velocidade é pedida em
   pulsos/s, limitada inicialmente a4 no controle pelo computador.
3. Soltar solicita referência zero. Sair da página, perder foco ou ocultar a
   janela libera a autorização. Se a página/processo deixar de responder,
   a supervisão embarcada para sem depender desses eventos do navegador.
4. **Solicitar emergência por software** retém o bloqueio durante a sessão.
   A liberação exige pedido explícito, privilégio administrativo, sensores
   válidos e evidências de parada. Não substitui emergência física.
5. Para autonomia, pare/libere o controle manual, selecione o processamento,
   solicite a mudança e depois **Habilitar seguimento autônomo**. A troca de
   modo não inicia movimento. Se a primeira solicitação precisar parar o
   carrinho, aguarde a confirmação e solicite novamente.

Os comandos não funcionam durante digitação em campos. Duas abas não recebem
a mesma autorização. A conexão de percepção e a de aquisição são independentes
do ciclo do navegador; fechar a aba não interrompe autonomia embarcada.

## CNN própria e imagens de teste

O OpenCV atual é o padrão. A CNN de fotos existente é carregada por seu
`experimento.json` e pelos pesos pareados `pesos_posicao.npz`; o seletor usa
o treino02 local quando o caminho fica vazio. Nenhuma rede é treinada.

Esses pesos usam a ROI original y075. Ela **não cabe** no JPEG320×240;
a tentativa é recusada, sem redimensionamento silencioso. Para testar a CNN,
pare o simulador, carregue uma imagem de teste compatível no formulário,
selecione **CNN própria · diagnóstico offline** e processamento distribuído.
A previsão entre−1 e1 é real, mas não autoriza navegação. Confiança/visibilidade
não supervisionadas permanecem indisponíveis. O erro lateral de controle não
é inventado a partir da posição offline.

O pacote CNN/RL utiliza o carregador existente e inferência determinística.
Não há checkpoint RL local nesta cópia; sem pacote compatível, a seleção é
recusada. Não inicia treinamento e não substitui por modelo pré-treinado.

## Ensaios reproduzíveis

Com a central anterior encerrada:

```powershell
python tools/validar_distribuido.py --duracao 6
```

Usa a mesma base histórica, quatro cenários de carga, JPEGs sintéticos fixos,
OpenCV e pesos CNN existentes. Salva JSON/imagens em `dados_distribuido/` e
exporta as novas categorias CSV pela infraestrutura anterior. Não é teste
físico nem comparação científica de superioridade entre modos.

Inferência isolada em JPEGs já gravados, sem abrir qualquer rede/serial:

```powershell
python tools/inferir_historico_distribuido.py --historico 'C:\pasta\historico' --sessao UUID --algoritmo opencv --saida dados_distribuido\historico.csv
```

Para CNN, acrescente `--algoritmo cnn-fotos --manifesto CAMINHO\experimento.json`.
Imagens ausentes, incompatíveis ou com hash incorreto são registradas como falha;
não são substituídas. Reprodução histórica não é ambiente RL responsivo.

## Parâmetros

O inicializador aceita `-Historico`, `-Porta`, `-Servidor`, `-InferenciaHz`,
`-ImagensFPS`, `-CameraFPS`, `-TelemetriaHz`, `-TimeoutResultado`,
`-TimeoutComando`, `-Heartbeat`, `-VelocidadeMaxPPS` e `-SemAbrir`.
As frequências de inferência e visualização são independentes.
Os limites conservadores são para ensaios, não calibração física definitiva.

Monitoramento físico futuro usa `-Perfil monitoramento -Servidor ws://IP:8765`.
As credenciais ficam em variáveis de ambiente nas duas pontas. O padrão é
observacional. `distribuido-real` exige ainda um registro manual explícito de
validação física; o exemplo incluído está **sem aprovação** e não habilita nada.
Não altere o exemplo para simular ensaios que não ocorreram.

Arquitetura, protocolo, arbitragem, resultados, limitações e roteiro físico:
[guia24](../docs/24_processamento_distribuido.md).
