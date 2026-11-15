#include "servo.h"
#include "config.h"
#include "protocolo.h"

#if USAR_SERVO

static_assert(PIN_SERVO == 9, "Timer1 OC1A exige D9 no Uno");
static_assert(PIN_SERVO != PIN_ENA && PIN_SERVO != PIN_ENB && PIN_SERVO != PIN_IN1 &&
              PIN_SERVO != PIN_IN2 && PIN_SERVO != PIN_IN3 && PIN_SERVO != PIN_IN4 &&
              PIN_SERVO != PIN_TRIG && PIN_SERVO != PIN_ECHO &&
              PIN_SERVO != PIN_ENC_ESQ && PIN_SERVO != PIN_ENC_DIR, "Servo conflita com outro pino ativo");
static_assert(F_CPU == 16000000UL, "Driver dimensionado para Uno de 16 MHz");
static_assert(SERVO_MIN_US >= 1000 && SERVO_MAX_US <= 2000, "Manter a faixa ja usada no teste");
static_assert(SERVO_CENTRO_US >= 1250 && SERVO_CENTRO_US <= 1750, "Centro fora da faixa de ajuste fino");
static_assert(SERVO_PASSO_MS > 0, "Periodo do passo deve ser positivo");

static bool g_varrendo = false, g_statusPendente = false;
static bool g_inspecao = false, g_concluida = false, g_amostraPendente = false;
static uint8_t g_etapa = 0, g_amostras = 0, g_validas = 0, g_amostraAngulo = 90;
static uint16_t g_menor = DIST_SEM_LEITURA, g_amostraCm = DIST_SEM_LEITURA, g_rodada = 0;
static const uint8_t ALVOS[] = {45, 90, 135};
static uint8_t g_angulo = 90;
static int8_t g_sentido = -1;
static uint16_t g_centro = SERVO_CENTRO_US;
static uint32_t g_ultimoPasso = 0, g_ultimoMovimento = 0, g_ultimoComando = 0;

static uint16_t pulso(uint8_t angulo) {
  int16_t amplitude = SERVO_AMPLITUDE_US;
  if (amplitude > g_centro - SERVO_MIN_US) amplitude = g_centro - SERVO_MIN_US;
  if (amplitude > SERVO_MAX_US - g_centro) amplitude = SERVO_MAX_US - g_centro;
  return g_centro + (static_cast<int32_t>(angulo) - 90) * amplitude / 45;
}

static void posicionar(uint8_t angulo, bool forcar = false) {
  if (angulo != g_angulo || forcar) {
    g_angulo = angulo;
    OCR1A = pulso(angulo) * 2; // prescaler 8: cada tick vale 0,5 us
    g_ultimoMovimento = millis();
  }
}

void servo_iniciar() {
  digitalWrite(PIN_SERVO, LOW);
  pinMode(PIN_SERVO, OUTPUT);
  const uint8_t sreg = SREG;
  cli();
  TCCR1A = 0;
  TCCR1B = 0;
  TCNT1 = 0;
  ICR1 = 39999;                   // 16 MHz / 8 / 40000 = 50 Hz
  OCR1A = SERVO_CENTRO_US * 2;
  TCCR1A = _BV(COM1A1) | _BV(WGM11);
  TCCR1B = _BV(WGM13) | _BV(WGM12) | _BV(CS11); // Fast PWM, TOP=ICR1
  SREG = sreg;
  g_varrendo = g_inspecao = g_concluida = g_amostraPendente = false;
  g_angulo = 90;
  g_sentido = -1;
  g_centro = SERVO_CENTRO_US;
  g_ultimoPasso = g_ultimoMovimento = g_ultimoComando = millis();
  g_statusPendente = false;
}

bool servo_comandar(uint8_t modo, int8_t ajuste) {
  const int16_t centro = SERVO_CENTRO_US + static_cast<int16_t>(ajuste) * 10;
  if (modo > 2 || centro < 1250 || centro > 1750) return false;
  const bool mudouCentro = centro != g_centro;
  g_centro = centro;
  if (modo == 0) {
    g_varrendo = g_inspecao = g_concluida = g_amostraPendente = false;
    posicionar(90, mudouCentro);
  } else if (modo == 2) {
    if (!g_inspecao || mudouCentro) {
      g_inspecao = true;
      g_concluida = g_varrendo = g_amostraPendente = false;
      g_etapa = g_amostras = g_validas = 0;
      g_menor = DIST_SEM_LEITURA;
      g_rodada = (g_rodada + 1) & 0x3FFF;
      g_ultimoPasso = millis();
      // Invalida qualquer eco anterior, mesmo se o servo ja estiver no alvo.
      g_ultimoMovimento = millis();
    }
  } else if (!g_varrendo || g_inspecao || mudouCentro) {
    g_inspecao = g_concluida = g_amostraPendente = false;
    posicionar(90, mudouCentro);
    g_varrendo = true;
    g_sentido = -1;
    g_ultimoPasso = millis();
  }
  g_ultimoComando = millis();
  g_statusPendente = true;
  return true;
}

void servo_atualizar() {
  if (!g_varrendo && !g_inspecao) return;
  const uint32_t agora = millis();
  if (agora - g_ultimoComando > SERVO_COMANDO_TIMEOUT_MS) {
    servo_comandar(0, static_cast<int8_t>((static_cast<int16_t>(g_centro) - SERVO_CENTRO_US) / 10));
    return;
  }
  if (agora - g_ultimoPasso < SERVO_PASSO_MS) return;
  g_ultimoPasso = agora;
  if (g_inspecao) {
    const uint8_t alvo = g_concluida ? 90 : ALVOS[g_etapa];
    if (g_angulo != alvo) posicionar(g_angulo + (g_angulo < alvo ? 1 : -1));
    return;
  }
  if (g_angulo <= 45) g_sentido = 1;
  if (g_angulo >= 135) g_sentido = -1;
  posicionar(static_cast<uint8_t>(g_angulo + g_sentido));
}

bool servo_varrendo() { return g_varrendo; }
bool servo_frontal_pronto() {
  return !g_varrendo && !g_inspecao && g_angulo == 90 && millis() - g_ultimoMovimento >= SERVO_ESTABILIZACAO_MS;
}
uint8_t servo_angulo_nominal() { return g_angulo; }
uint16_t servo_centro_us() { return g_centro; }
uint8_t servo_flags() {
  return SERVO_FLAG_ATIVO | (g_inspecao ? SERVO_FLAG_INSPECAO : 0) |
         (g_concluida && g_angulo == 90 && millis() - g_ultimoMovimento >= SERVO_ESTABILIZACAO_MS
           ? SERVO_FLAG_CONCLUIDA : 0) | (g_varrendo ? SERVO_FLAG_VARREDURA : 0) |
         (servo_frontal_pronto() ? SERVO_FLAG_CENTRO_PRONTO : 0);
}
bool servo_consumir_status() {
  const bool pendente = g_statusPendente;
  g_statusPendente = false;
  return pendente;
}

bool servo_em_inspecao() { return g_inspecao; }
bool servo_medicao_pronta() {
  return g_inspecao && !g_concluida && g_angulo == ALVOS[g_etapa] &&
         millis() - g_ultimoMovimento >= SERVO_ESTABILIZACAO_MS;
}
void servo_registrar_leitura(uint16_t cm, bool valida) {
  if (!servo_medicao_pronta()) return;
  if (valida) { g_validas++; if (cm < g_menor) g_menor = cm; }
  if (++g_amostras < SERVO_INSPECAO_AMOSTRAS) return;
  g_amostraAngulo = ALVOS[g_etapa];
  g_amostraCm = g_validas == SERVO_INSPECAO_AMOSTRAS ? g_menor : DIST_SEM_LEITURA;
  g_amostraPendente = true;
  g_amostras = g_validas = 0;
  g_menor = DIST_SEM_LEITURA;
  if (++g_etapa >= 3) g_concluida = true;
  g_ultimoMovimento = millis();
  g_statusPendente = true;
}
bool servo_consumir_amostra(uint8_t &angulo, uint16_t &cm, uint16_t &id) {
  if (!g_amostraPendente) return false;
  g_amostraPendente = false;
  angulo = g_amostraAngulo; cm = g_amostraCm; id = g_rodada;
  return true;
}

#else
bool servo_em_inspecao() { return false; }
bool servo_medicao_pronta() { return false; }
void servo_registrar_leitura(uint16_t, bool) {}
bool servo_consumir_amostra(uint8_t &, uint16_t &, uint16_t &) { return false; }
void servo_iniciar() {}
void servo_atualizar() {}
bool servo_comandar(uint8_t, int8_t) { return false; }
bool servo_varrendo() { return false; }
bool servo_frontal_pronto() { return true; }
uint8_t servo_angulo_nominal() { return 90; }
uint16_t servo_centro_us() { return SERVO_CENTRO_US; }
uint8_t servo_flags() { return 0; }
bool servo_consumir_status() { return false; }
#endif
