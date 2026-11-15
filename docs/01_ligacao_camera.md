# 1. Ligando a câmera OV7670 (sem FIFO) no Arduino UNO

> **Câmera definitiva do projeto: OV7670 no Arduino (`USAR_CAMERA 1`, o padrão do firmware).** Os pinos dos motores
> abaixo são os do modo com câmera (diferentes do modo de bancada, `docs/00_motores_e_sensores.md`) e ultrassom e
> encoders ficam desligados nesse modo (os pinos deles são da câmera).

Este é o passo que costuma travar. Faça **com tudo desligado** (USB e bateria dos motores fora).

## Alimentação e o esquema que você montou
- A câmera (e o Bluetooth) são alimentados por um **regulador AMS1117 de 3,3 V** ligado à bateria de 8 V; a bateria também
  alimenta o Arduino e a ponte H. Meça a saída do regulador antes de ligar a câmera (tem que dar ~3,3 V).
- Não ligue o 3,3 V da câmera ao pino 3V3 do Arduino **ao mesmo tempo** que ao regulador (duas fontes de 3,3 V juntas).
- GND comum em tudo.
- No diagrama de referência que você seguiu, D0..D3 da câmera vão para A0..A3 e o HREF para D8. **Tire esses 5 fios**: o firmware
  não usa esses sinais e A0/D8 são saídas dos motores no modo câmera. Os demais fios (PCLK D2, VSYNC D3, D4..D7, XCLK D11,
  SIOC A5, SIOD A4) já são os mesmos do firmware.

## O que você precisa
- OV7670 **sem FIFO** (módulo com 18 ou 20 pinos: 3V3, GND, SIOC, SIOD, VSYNC, HREF, PCLK, XCLK, D0–D7, RESET, PWDN).
- 2 resistores de **4,7 kΩ** (pull-ups do I2C) e, para o XCLK, um divisor de tensão (**1 kΩ + 2 kΩ**).
- Jumpers **curtos** (idealmente < 15 cm). Fio longo em PCLK/XCLK é causa nº 1 de imagem ruim.

## Seu módulo (conferido pela foto): 18 pinos em duas colunas

Os nomes na serigrafia são: **SCL = SIOC, SDA = SIOD, VS = VSYNC, PLK = PCLK, HS = HREF, XLK = XCLK, RET = RESET**.
Os pinos alternam entre as duas colunas, então **leia linha por linha**, não coluna por coluna.
Com a placa como na foto (3.3V no canto superior esquerdo):

| Linha | Coluna esquerda → UNO | Coluna direita → UNO |
|---|---|---|
| 1 | 3.3V → 3,3V | GND → GND |
| 2 | SCL → A5 (pull-up 4,7k p/ 3,3V) | SDA → A4 (pull-up 4,7k p/ 3,3V) |
| 3 | VS → D3 | HS → **não liga** |
| 4 | PLK → D2 | XLK → D11 **pelo divisor 1k/2k** |
| 5 | D7 → D7 | D6 → D6 |
| 6 | D5 → D5 | D4 → D4 |
| 7 | D3 → **não liga** | D2 → **não liga** |
| 8 | D1 → **não liga** | D0 → **não liga** |
| 9 | RET → 3,3V | PWDN → GND |

Confira sempre pelos nomes impressos na placa, caso a sua esteja girada.

- Este módulo só tem entrada de **3,3V** (não há regulador): 5V aqui queima a câmera.
- Os pinos têm que estar **soldados** num header. Jumper só encostado nos furos dá mau contato, e isso faz o I2C falhar de forma intermitente. Se o seu módulo não tem pinos, solde antes de testar.
- Com a câmera **desligada**, meça a resistência entre SCL e 3.3V: ~4,7k significa que o módulo já tem pull-up e você não precisa colocar o seu.

## Tabela de ligação (nomes genéricos)

| Pino da câmera | Pino do UNO | Observação |
|---|---|---|
| 3V3 | 3,3V | **Nunca 5V** (queima a câmera). |
| GND | GND | GND comum com tudo. |
| SIOC (SCL) | A5 | Pull-up 4,7k **para 3,3V** (não para 5V). |
| SIOD (SDA) | A4 | Pull-up 4,7k **para 3,3V**. |
| XCLK | D11 | **Pelo divisor**: D11 → 1k → ponto XCLK → 2k → GND. |
| PCLK | D2 | Direto. |
| VSYNC | D3 | Direto. |
| D7, D6, D5, D4 | D7, D6, D5, D4 | Direto. **Só esses 4 bits** são usados (imagem de 16 tons de cinza). |
| D3, D2, D1, D0 | — | **Não liga.** |
| HREF | — | **Não liga** (o firmware conta pulsos de PCLK). |
| RESET | 3,3V | Em nível alto = funcionando. |
| PWDN | GND | Em baixo = ligada. |

### Por que esses cuidados
- A câmera é **3,3V**; o UNO fala 5V. As saídas da câmera (PCLK, VSYNC, D4–D7) chegam a 3,3V, o que o UNO enxerga como nível alto — pode ligar direto. As **entradas** da câmera (XCLK e o I2C) é que não podem receber 5V: por isso o divisor no XCLK e o pull-up do I2C em 3,3V (o firmware desliga os pull-ups internos de 5V do UNO).
- Muitos módulos já trazem pull-ups de 4,7k no próprio módulo. Se SIOC/SIOD já têm resistor na placa, **não precisa** colocar os seus (dois em paralelo ficam fortes demais; ~2,2k ainda funciona, 1k não costuma funcionar).
- O XCLK é um clock de **8 MHz** gerado pelo UNO (Timer2). Sem ele a câmera não faz nada — nem responde no I2C.

## Ponte H L298N e motores

| L298N | UNO |
|---|---|
| ENA | D9 |
| ENB | D10 |
| IN1 | D8 |
| IN2 | D12 |
| IN3 | D13 |
| IN4 | A0 |
| GND | GND (comum com o UNO) |

- **Tire os jumpers de ENA/ENB** do L298N (senão não há controle de velocidade).
- Os motores usam a **bateria própria** no borne 12V do L298N. **Não alimente o UNO nem a câmera por ela sem regulador**, e não alimente motores pelo UNO.
- Recomendado: resistor de **10 kΩ de cada pino IN1–IN4 para o GND**, para os motores não dispararem enquanto o UNO reinicia.
- Motor girando para o lado errado? Troque os dois fios daquele motor no L298N (não mexa no código).

## Alimentação e USB
- UNO ↔ Raspberry Pi: cabo USB (alimenta o UNO e leva imagem + comandos).
- A câmera pega 3,3V do UNO (~30–40 mA, o regulador aguenta).
- Câmera sem ruído de motor: se a imagem tremer quando os motores ligam, ponha um capacitor de 100 µF entre 3V3 e GND perto da câmera.

## Conferência final (antes de ligar)
1. Nenhum fio de 5V encostando em pino da câmera.
2. 3V3 da câmera no 3,3V (não no 5V) e GND comum.
3. XCLK passando pelo divisor.
4. PWDN no GND, RESET no 3,3V.
5. A4/A5 certos (SIOD em A4, SIOC em A5 — fácil de trocar).

Pronto? Vá para `02_bringup_camera.md`.
