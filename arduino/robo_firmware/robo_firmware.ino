// Firmware do robô (Arduino UNO): ponte entre os motores/sensores e a Raspberry Pi.
//
// USAR_CAMERA 0 (bancada): recebe comandos da Pi e aciona a ponte H L298N; envia a distância do HC-SR04
//                        e os contadores dos encoders. A decisão é toda da Pi.
// USAR_CAMERA 1 (padrão): além disso configura a OV7670 por I2C e envia imagem 160x120 (4 bits de cinza)
//                        pela USB a 1 Mbaud, linha a linha.
//
// Protocolo: protocolo.h. Sem camera, a recepcao usa ISR/buffer de HardwareSerial;
// o parser e os comandos continuam no loop. A camera legada usa polling direto.

#include <avr/wdt.h>
#include "comandos.h"
#include "config.h"
#include "diagnostico.h"
#include "motores.h"
#include "protocolo.h"
#include "sensores.h"
#include "servo.h"
#include "sinalizacao.h"
#include "sonar_movimento.h"
#if USAR_CAMERA
#include "captura.h"
#include "ov7670.h"
#endif

#if MODO_DIAGNOSTICO

void setup() { diagnostico_setup(); }
void loop() { diagnostico_loop(); }

#else

static inline void pollRx() {
#if USAR_CAMERA
  while (UCSR0A & _BV(RXC0)) comandos_byte(UDR0);
#else
  // A guarda do sonar usa calculos float no AVR. Receber os bytes por ISR
  // evita depender de retornar ao loop a cada byte (~87 us em 115200 baud).
  while (Serial.available()) comandos_byte(static_cast<uint8_t>(Serial.read()));
#endif
}

static inline void txByte(uint8_t b) {
  while (!(UCSR0A & _BV(UDRE0))) {
    pollRx();                       // enquanto espera a UART, atende comandos
#if USAR_SENSORES
    // A resposta adicional do servo nao pode fazer perder as bordas do ECHO.
    sensores_atualizar();
    motores_aplicar_seguranca();
    sinalizacao_atualizar();
#endif
  }
  UDR0 = b;
}

// Pacote de sensores: SYNC, IDX_SENSORES e 7 bytes de 7 bits (nunca valem 0xFF).
static void enviarSensores() {
  const uint16_t d = sensores_distancia_cm();
  const uint16_t e = sensores_encoder_esq();
  const uint16_t r = sensores_encoder_dir();
  const uint8_t flags = (sensores_avanco_bloqueado() ? 0x01 : 0) | (sensores_falha() ? 0x02 : 0) |
                        (sensores_obstaculo_confirmado() ? 0x04 : 0) |
                        (servo_em_sonar_movimento() && !sonar_movimento_calibrado() ? 0x08 : 0) |
                        (servo_em_sonar_movimento() && sonar_movimento_experimental() ? 0x10 : 0) |
                        (servo_em_sonar_movimento() && sonar_movimento_lateral_esq() ? 0x20 : 0) |
                        (servo_em_sonar_movimento() && sonar_movimento_lateral_dir() ? 0x40 : 0);
  txByte(SYNC);
  txByte(IDX_SENSORES);
  txByte(d & 0x7F);
  txByte((d >> 7) & 0x7F);
  txByte(e & 0x7F);
  txByte((e >> 7) & 0x7F);
  txByte(r & 0x7F);
  txByte((r >> 7) & 0x7F);
  txByte(flags);
}

static void uartIniciar() {
#if USAR_CAMERA
  UCSR0A = _BV(U2X0);                // baud = 16 MHz / (8 * (UBRR + 1))
  UBRR0H = 0;
  UBRR0L = UART_U2X_UBRR;
  UCSR0B = _BV(RXEN0) | _BV(TXEN0); // sem interrupção de recepção
  UCSR0C = _BV(UCSZ01) | _BV(UCSZ00);
#else
  // HardwareSerial captura RX por interrupcao em buffer de 64 bytes no Uno.
  // TX continua direto em txByte(); nao usar Serial.print/write neste caminho.
  Serial.begin(115200);
#endif
}

static void enviarMotores() {
  int16_t e, d; uint8_t flags;
  motores_diagnostico(e, d, flags);
  if (e < 0) e = -e;
  if (d < 0) d = -d;
  txByte(SYNC); txByte(IDX_MOTORES);
  txByte(e & 127); txByte((e >> 7) & 127);
  txByte(d & 127); txByte((d >> 7) & 127); txByte(flags);
  if (servo_em_sonar_movimento()) {
    txByte(SYNC); txByte(IDX_GUARDA_SONAR); txByte(sonar_movimento_bloqueios());
  }
}

static void enviarInspecaoSePendente() {
  uint8_t angulo;
  uint16_t cm, id;
  if (!servo_consumir_amostra(angulo, cm, id)) return;
  txByte(SYNC); txByte(IDX_INSPECAO); txByte((angulo - 45) / 45);
  txByte(cm & 127); txByte((cm >> 7) & 127);
  txByte(id & 127); txByte((id >> 7) & 127);
}

static void enviarServoSePendente() {
  if (!servo_consumir_status()) return;
  const uint16_t angulo = servo_angulo_nominal(), centro = servo_centro_us();
  const uint8_t flags = servo_flags();
  txByte(SYNC);
  txByte(IDX_SERVO);
  txByte(angulo & 0x7F);
  txByte((angulo >> 7) & 0x7F);
  txByte(centro & 0x7F);
  txByte((centro >> 7) & 0x7F);
  txByte(flags);
}

static void enviarSonarSePendente() {
  uint8_t angulo;
  uint16_t cm, sequencia;
  if (!servo_consumir_sonar(angulo, cm, sequencia)) return;
  txByte(SYNC); txByte(IDX_SONAR);
  txByte(angulo & 127); txByte(angulo >> 7);
  txByte(cm & 127); txByte(cm >> 7);
  txByte(sequencia & 127); txByte(sequencia >> 7);
}

#if USAR_CAMERA
// ------------------------------------------------------------------ com câmera
static StatusCodigo g_status = ST_OK;

static void enviarStatus(StatusCodigo codigo) {
  txByte(SYNC);
  txByte(IDX_STATUS);
  txByte((uint8_t)codigo);
}

// Espera o início de um quadro (VSYNC sobe e desce). Aqui as interrupções ficam ligadas.
static bool esperarInicioQuadro() {
  const uint32_t t0 = millis();
  while (!(PIND & M_VSYNC)) {
    pollRx();
    wdt_reset();
    if (millis() - t0 > 500) return false;
  }
  while (PIND & M_VSYNC) {
    pollRx();
    wdt_reset();
    if (millis() - t0 > 500) return false;
  }
  return true;
}

void setup() {
  MCUSR = 0;
  wdt_disable();
  motores_iniciar();                 // motores parados antes de qualquer outra coisa
  uartIniciar();

  ov7670_clock_iniciar();
  delay(CAM_ESPERA_INICIAL_MS);
  ov7670_i2c_iniciar();
  g_status = ov7670_iniciar();
  enviarStatus(g_status);

  // Se o laço de captura travar (câmera sem PCLK), o watchdog reinicia a placa e os motores soltam.
  // Recomendado: resistores de 10k de cada pino IN1..IN4 para o GND.
  wdt_enable(WDTO_250MS);
}

void loop() {
  static uint8_t linha[BYTES_LINHA_ENVIADA];

  wdt_reset();
  pollRx();
  motores_watchdog();

  if (g_status != ST_OK) {           // câmera com problema: os motores continuam obedecendo à Pi
    static uint32_t ultimoAviso = 0;
    if (millis() - ultimoAviso > 1000) {
      ultimoAviso = millis();
      enviarStatus(g_status);
    }
    return;
  }

  if (!esperarInicioQuadro()) {
    enviarStatus(ST_SEM_VSYNC);
    return;
  }

  for (uint8_t y = 0; y < IMG_ALTURA; y++) {
    wdt_reset();
    if (y < LINHA_INICIAL) {
      cli();
      pularLinha();
      sei();
      continue;
    }
    cli();
    lerLinha(linha);                 // tempo real: ~640 us com CLKRC = 3
    sei();

    txByte(SYNC);                    // o envio acontece no intervalo até a próxima linha
    txByte(y);
    for (uint8_t i = 0; i < BYTES_LINHA_ENVIADA; i++) txByte(linha[i]);
  }
  txByte(SYNC);
  txByte(IDX_FIM_QUADRO);
}

#else
// ------------------------------------------------------------------ sem câmera
void setup() {
  MCUSR = 0;
  wdt_disable();
  motores_iniciar();                 // motores parados antes de qualquer outra coisa
  uartIniciar();
  sensores_iniciar();
  servo_iniciar();
  sinalizacao_iniciar();
  wdt_enable(WDTO_250MS);            // se o loop travar, a placa reinicia e os motores soltam
}

void loop() {
  static uint32_t ultimoEnvio = 0;

  wdt_reset();
  pollRx();                          // comandos da Pi (motores)
  motores_watchdog();                // Pi muda por 400 ms -> motores param
  servo_atualizar();                 // Timer1 gera pulsos sem esperas no loop
  sensores_atualizar();              // HC-SR04 sem bloquear
  motores_aplicar_seguranca();       // sensor pode cortar o avanço sem esperar novo pacote da Pi
  motores_regular_velocidade();
  sinalizacao_atualizar();
  enviarInspecaoSePendente();
  enviarSonarSePendente();
  enviarServoSePendente();

  if (millis() - ultimoEnvio >= SENSORES_PERIODO_MS) {
    ultimoEnvio = millis();
    enviarSensores();
    enviarMotores();
  }
}
#endif  // USAR_CAMERA

#endif  // MODO_DIAGNOSTICO
