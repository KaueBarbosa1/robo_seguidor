# 3. Headset Bluetooth como microfone

O robô não tem microfone: o headset pareado na Raspberry Pi serve de entrada. **Não foi testado com o seu headset**; use `tools/testar_microfone.py`.

## Parear
```bash
bluetoothctl
  power on
  agent on
  scan on                 # coloque o headset em modo de pareamento
  pair XX:XX:XX:XX:XX:XX
  trust XX:XX:XX:XX:XX:XX
  connect XX:XX:XX:XX:XX:XX
```
`trust` faz reconectar sozinho depois.

## O ponto crítico: perfil HFP/HSP
Bluetooth tem dois modos: **A2DP** (música, sem microfone) e **HFP/HSP** (chamada, com microfone). Para o robô **tem que estar em HFP/HSP**.
- HFP com codec **mSBC** = 16 kHz (igual ao do seu treino, ideal). Com **CVSD** = 8 kHz (a voz fica pior e o reconhecimento cai; o programa avisa).

No Raspberry Pi OS (PipeWire):
```bash
pactl list cards short                                   # ache o card bluez_card....
pactl set-card-profile bluez_card.XX_XX_XX_XX_XX_XX headset-head-unit
pactl list sources short                                 # ache bluez_input....
pactl set-default-source bluez_input.XX_XX_XX_XX_XX_XX.0
```
(Nomes variam por versão; se `headset-head-unit` não existir, veja `pactl list cards` para o nome do perfil com microfone.)

## Usar no robô
1. `python tools/testar_microfone.py` lista os dispositivos e mostra o nível do sinal. Fale e veja a barra subir.
2. Em `config.py`: `MIC_DEVICE = None` (usa o padrão do sistema) ou parte do nome, como `"pipewire"`, `"pulse"` ou o nome do headset.
3. O programa testa as taxas de `MIC_SR_TENTATIVAS` e reamostra para 16 kHz sozinho.

## Se o headset cair
A thread de voz tenta reabrir a cada `MIC_REABRIR_S` segundos. Com `PARAR_SE_SEM_MICROFONE = True` (padrão) o robô **para** quando perde o microfone e só volta a andar com um "siga" depois que o headset voltar — sem voz não existe como mandar "pare". Recomendo também um **botão físico de emergência** cortando a alimentação dos motores.

## Latência
Bluetooth de chamada tem 100–300 ms de atraso, somados ao VAD (~0,5 s de silêncio para fechar a palavra). Fale "pare" com antecedência.
