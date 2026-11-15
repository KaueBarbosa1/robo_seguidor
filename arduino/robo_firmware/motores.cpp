#include "motores.h"
#include <stdlib.h>
#include "config.h"
#include "sensores.h"
#include "servo.h"

static bool g_velocidade = false, g_interno = false, g_falhaEncoder = false;
static_assert(VELOCIDADE_PWM_PARTIDA > 0 && VELOCIDADE_PWM_PARTIDA <= VELOCIDADE_PWM_MAX,
              "PWM inicial deve respeitar limite do PI");
static int16_t g_alvo[2] = {0, 0};
static float g_integral[2] = {0, 0};
static uint16_t g_ticks[2] = {0, 0};
static uint32_t g_amostra = 0, g_pulso[2] = {0, 0};
static uint32_t g_ultimoComandoMs = 0;
static bool g_parado = true;
static int16_t g_esqAtual = 0, g_dirAtual = 0;
static int16_t g_esqPedido = 0, g_dirPedido = 0;

static_assert(OBSTACULO_REDUZIR_CM > OBSTACULO_LIBERACAO_CM, "Reducao deve anteceder liberacao/parada");
static_assert(OBSTACULO_PWM_PERCENT_MIN > 0 && OBSTACULO_PWM_PERCENT_MIN <= 100, "Percentual invalido");

static void limitarAproximacao(int16_t &esq, int16_t &dir) {
#if USAR_SENSORES
  if (esq <= 0 && dir <= 0) return;
  const uint16_t cm = sensores_distancia_cm();
  if (cm >= OBSTACULO_REDUZIR_CM || sensores_falha()) return;
  const uint16_t faixa = OBSTACULO_REDUZIR_CM - OBSTACULO_DIST_CM;
  const uint16_t delta = cm > OBSTACULO_DIST_CM ? cm - OBSTACULO_DIST_CM : 0;
  const uint16_t percentual = OBSTACULO_PWM_PERCENT_MIN +
      (100 - OBSTACULO_PWM_PERCENT_MIN) * delta / faixa;
  esq = static_cast<int32_t>(esq) * percentual / 100;
  dir = static_cast<int32_t>(dir) * percentual / 100;
#endif
}

static void aplicar(int16_t v, uint8_t pinEn, uint8_t pinA, uint8_t pinB) {
  if (v > 255) v = 255;
  if (v < -255) v = -255;
  // Corrigir apenas a saida eletrica. Seguranca e PI preservam frente positiva.
  if ((pinEn == PIN_ENA && MOTOR_ESQ_INVERTIDO) ||
      (pinEn == PIN_ENB && MOTOR_DIR_INVERTIDO)) v = -v;
  if (v > 0) {
    digitalWrite(pinA, HIGH);
    digitalWrite(pinB, LOW);
  } else if (v < 0) {
    digitalWrite(pinA, LOW);
    digitalWrite(pinB, HIGH);
  } else {
    digitalWrite(pinA, LOW);
    digitalWrite(pinB, LOW);
  }
  analogWrite(pinEn, v < 0 ? -v : v);
}

void motores_iniciar() {
  pinMode(PIN_ENA, OUTPUT);
  pinMode(PIN_ENB, OUTPUT);
  pinMode(PIN_IN1, OUTPUT);
  pinMode(PIN_IN2, OUTPUT);
  pinMode(PIN_IN3, OUTPUT);
  pinMode(PIN_IN4, OUTPUT);
  motores_parar();
}

void motores_set(int16_t esq, int16_t dir) {
  if (!g_interno) g_velocidade = false;
  // Nesta primeira integracao, nao movimentar o carrinho durante varredura ou
  // retorno ao centro. A re continua com sua regra anterior apos estabilizar.
  if (!servo_frontal_pronto()) esq = dir = 0;
  // Proteção local ao ponto que efetivamente aciona a ponte H. Ré segue liberada;
  // qualquer roda positiva é tratada como avanço/manobra com avanço.
  if (sensores_avanco_bloqueado() && (esq > 0 || dir > 0)) esq = dir = 0;
  g_esqPedido = esq;
  g_dirPedido = dir;
  limitarAproximacao(esq, dir);
  aplicar(esq, PIN_ENA, PIN_IN1, PIN_IN2);
  aplicar(dir, PIN_ENB, PIN_IN3, PIN_IN4);
  g_parado = (esq == 0 && dir == 0);
  g_esqAtual = esq;
  g_dirAtual = dir;
}

void motores_parar() {
  g_velocidade = false;
  g_integral[0] = g_integral[1] = 0;
  g_falhaEncoder = false;
  motores_set(0, 0);
  g_parado = true;
}

void motores_marcar_comando() { g_ultimoComandoMs = millis(); }
bool motores_parados() { return g_parado; }

void motores_watchdog() {
  if (!g_parado && (millis() - g_ultimoComandoMs) > MOTORES_WATCHDOG_MS) {
    motores_parar();
  }
}

void motores_aplicar_seguranca() {
  if (sensores_avanco_bloqueado() && (g_esqAtual > 0 || g_dirAtual > 0)) {
    motores_parar();
    return;
  }
  int16_t esq = g_esqPedido, dir = g_dirPedido;
  limitarAproximacao(esq, dir);
  // Pode reduzir sem esperar novo comando; nunca aumenta nem ressuscita movimento.
  if (abs(esq) <= abs(g_esqAtual) && abs(dir) <= abs(g_dirAtual) &&
      (abs(esq) < abs(g_esqAtual) || abs(dir) < abs(g_dirAtual))) {
    aplicar(esq, PIN_ENA, PIN_IN1, PIN_IN2);
    aplicar(dir, PIN_ENB, PIN_IN3, PIN_IN4);
    g_esqAtual = esq;
    g_dirAtual = dir;
    g_parado = (esq == 0 && dir == 0);
  }
}


// Encoders de um canal medem magnitude; o sentido vem do comando.
// Falha fica travada ate S; renovar R nao pode religar uma roda sem pulsos.
bool motores_falha_encoder() { return g_falhaEncoder; }

void motores_velocidade(int16_t esq, int16_t dir) {
#if USAR_SENSORES
  if (g_falhaEncoder) return;
  if (abs(esq) > VELOCIDADE_MAX_PPS || abs(dir) > VELOCIDADE_MAX_PPS) return;
  if (!servo_frontal_pronto() ||
      (sensores_avanco_bloqueado() && (esq > 0 || dir > 0))) {
    motores_parar();
    return;
  }
  const bool inverteEsq = g_velocidade && esq && g_alvo[0] && ((esq > 0) != (g_alvo[0] > 0));
  const bool inverteDir = g_velocidade && dir && g_alvo[1] && ((dir > 0) != (g_alvo[1] > 0));
  const int16_t alvos[2] = {esq, dir};
  const uint16_t ticks[2] = {sensores_encoder_esq(), sensores_encoder_dir()};
  const uint32_t agora = millis();
  for (uint8_t i = 0; i < 2; i++) {
    if (!g_velocidade || (alvos[i] > 0) != (g_alvo[i] > 0) || !alvos[i]) {
      // Comecar perto do PWM de partida medido, em vez de esperar a integral
      // vencer o atrito antes do timeout sem pulsos. Renovacoes nao reiniciam.
      g_integral[i] = alvos[i] ? VELOCIDADE_PWM_PARTIDA : 0;
      g_pulso[i] = agora;
      g_ticks[i] = ticks[i];
    }
    g_alvo[i] = alvos[i];
  }
  if (!g_velocidade) {
    // Ao mudar de PWM para velocidade, nao manter potencia antiga.
    motores_set(0, 0);
    g_amostra = agora;
  }
  g_velocidade = true;
  // Zero deve parar a roda imediatamente, sem esperar a proxima amostra.
  if (!esq || !dir || inverteEsq || inverteDir) {
    g_interno = true;
    motores_set(esq && !inverteEsq ? g_esqAtual : 0, dir && !inverteDir ? g_dirAtual : 0);
    g_interno = false;
  }
#else
  motores_parar(); // sem encoders, nao fingir controle de velocidade
#endif
}

void motores_regular_velocidade() {
#if USAR_SENSORES
  if (!g_velocidade) return;
  const uint32_t agora = millis(), dt = agora - g_amostra;
  if (agora - g_ultimoComandoMs > MOTORES_WATCHDOG_MS ||
      !servo_frontal_pronto() ||
      (sensores_avanco_bloqueado() && (g_alvo[0] > 0 || g_alvo[1] > 0))) {
    motores_parar();
    return;
  }
  if (dt < VELOCIDADE_PERIODO_MS) return;
  const uint16_t ticks[2] = {sensores_encoder_esq(), sensores_encoder_dir()};
  int16_t pwm[2] = {0, 0};
  int16_t alvoEsq = g_alvo[0], alvoDir = g_alvo[1];
  limitarAproximacao(alvoEsq, alvoDir);
  const int16_t alvosSeguros[2] = {alvoEsq, alvoDir};
  for (uint8_t i = 0; i < 2; i++) {
    const uint16_t delta = (ticks[i] - g_ticks[i]) & 0x3FFF;
    g_ticks[i] = ticks[i];
    if (delta || !g_alvo[i]) g_pulso[i] = agora;
    if (g_alvo[i] && agora - g_pulso[i] >= VELOCIDADE_SEM_PULSO_MS) {
      motores_parar();
      g_falhaEncoder = true;
      return;
    }
    if (!g_alvo[i]) continue;
    const float erro = abs(alvosSeguros[i]) - delta * 1000.0f / dt;
    const float candidato = g_integral[i] + VELOCIDADE_KI * erro * dt / 1000.0f;
    const float saida = VELOCIDADE_KP * erro + candidato;
    // Anti-windup: nao acumular erro que empurra alem da saturacao.
    if ((saida >= 0 && saida <= VELOCIDADE_PWM_MAX) ||
        (saida > VELOCIDADE_PWM_MAX && erro < 0) || (saida < 0 && erro > 0))
      g_integral[i] = candidato;
    float limitado = VELOCIDADE_KP * erro + g_integral[i];
    if (limitado < 0) limitado = 0;
    if (limitado > VELOCIDADE_PWM_MAX) limitado = VELOCIDADE_PWM_MAX;
    pwm[i] = (g_alvo[i] < 0 ? -1 : 1) * static_cast<int16_t>(limitado);
  }
  g_amostra = agora;
  g_interno = true;
  motores_set(pwm[0], pwm[1]);
  g_interno = false;
#endif
}
