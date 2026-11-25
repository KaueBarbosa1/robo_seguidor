# Central de monitoramento — Etapa 5

Aplicação local para Windows que integra o gêmeo digital original, gráficos,
câmera, simulação, histórico SQLite e experimentos. O modo inicial é simulado;
movimentação remota e inferência distribuída reais permanecem bloqueadas.

Na raiz do projeto, com Python e Node/npm instalados:

```powershell
.\instalar_central.ps1
.\iniciar_central.ps1
```

Abra <http://127.0.0.1:8780/>. Se a porta já estiver ocupada, use `-Porta 8781`
ou encerre a instância anterior. `Ctrl+C` no terminal encerra o servidor,
cliente, simulador e gravador. Não inicie outro gravador na mesma base.
Após instalar as dependências, a aplicação funciona sem internet.

O GLB local é o mesmo da etapa 4, em
`gemeo_digital/modelos/carrinho_configurado.glb`; siga o README do gêmeo em
outro checkout. Nenhum modelo substituto é criado se esse arquivo estiver ausente.

## Primeiro uso

1. Em **Simulação**, escolha um cenário e clique em **Iniciar**.
2. Navegue pelas páginas: os indicadores, gráficos e modelo usam a mesma fonte.
3. Use **Gravar sessão** na barra superior e depois **Encerrar gravação**.
   A gravação de imagens é opcional e configurada antes de iniciar a gravação.
4. Em **Histórico de sessões**, pesquise e abra **Resumo** para nomear,
   adicionar observações ou exportar categorias/intervalos. Após preparar a
   exportação, use o link **Baixar arquivo CSV (ZIP)**.
5. Selecione sessões para comparar ou associar a um experimento.
6. Clique em **Reproduzir** na sessão. A linha do tempo global controla o
   modelo, câmera, gráficos e indicadores, inclusive ao avançar/retroceder.
   Trechos sem dados ficam indisponíveis; não são preenchidos artificialmente.

**Visão computacional** reaproveita o JPEG recebido. O cinza opcional é derivado
no PC, em frequência reduzida; não representa uma etapa intermediária enviada
pela Raspberry. O painel de coleta existente continua na main; informe seu
endereço em **Configurações** para disponibilizar o atalho.

**Inteligência artificial** mostra os registros locais dos dois treinos próprios
da CNN. A curva só aparece quando o CSV original está presente. Não executa treino,
não carrega outra CNN e não aprova uso no robô.

## Histórico e futura observação real

O caminho padrão é o da configuração existente. Havendo a base de validação da
etapa 3, o inicializador a reutiliza. Para escolher explicitamente outra base
existente:

```powershell
.\iniciar_central.ps1 -Historico 'C:\caminho\historico'
```

Observação real futura, com o servidor da etapa 2 já configurado e validado:

```powershell
$env:ROBO_REDE_TOKEN = 'token definido no ambiente da Raspberry'
.\iniciar_central.ps1 -Servidor 'ws://IP_DA_RASPBERRY:8765'
```

A aplicação ainda abre em simulação. Selecione **Dados reais** apenas quando o
servidor estiver acessível. Isso recebe telemetria; não habilita controle físico.
Nenhuma rede, firmware, pinagem ou configuração da ESP32-CAM é alterada.

Consulte o [guia técnico e relatório de validação](../docs/23_central_monitoramento.md)
para arquitetura, páginas, endpoints, resultados e classificação das pendências.
