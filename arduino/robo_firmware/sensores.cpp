#include "sensores.h"
#include "config.h"
#include "protocolo.h"
#include "servo.h"

#if USAR_SENSORES   // com a câmera OV7670 os pinos do ultrassom e dos encoders são da câmera: este módulo fica desligado


static volatile uint16_t g_encEsq = 0, g_encDir = 0;
static uint16_t g_dist = DIST_SEM_LEITURA;
static uint8_t g_estado = 0;
static uint32_t g_t0 = 0, g_tEco = 0, g_proxMs = 0;
static uint32_t g_ultimaValidaMs = 0;
static uint8_t g_perto = 0, g_longe = 0, g_invalidas = OBSTACULO_LEITURAS;
static bool g_bloqueado = true, g_falha = true;

static void registrarLeitura(uint16_t cm, bool valida) {
  if (servo_em_inspecao()) {
    servo_registrar_leitura(cm, valida);
    return; // leituras direcionais nunca alimentam a protecao frontal
  }
  if (!valida) {
    g_dist = DIST_SEM_LEITURA;
    g_perto = g_longe = 0;
    if (g_invalidas < 255) g_invalidas++;
    if (g_invalidas >= OBSTACULO_LEITURAS) {
      g_falha = true;
      g_bloqueado = true;
    }
    return;
  }
  g_dist = cm;
  g_ultimaValidaMs = millis();
  g_invalidas = 0;
  g_falha = false;
  if (cm < OBSTACULO_DIST_CM) {
    g_longe = 0;
    if (g_perto < OBSTACULO_LEITURAS) g_perto++;
    if (g_perto >= OBSTACULO_LEITURAS) g_bloqueado = true;
  } else if (cm >= OBSTACULO_LIBERACAO_CM) {
    g_perto = 0;
    if (g_longe < OBSTACULO_LEITURAS) g_longe++;
    if (g_longe >= OBSTACULO_LEITURAS) g_bloqueado = false;
  } else {
    g_perto = g_longe = 0;  // zona de histerese: mantém o estado anterior
  }
}

static void isrEsq() { g_encEsq++; }
static void isrDir() { g_encDir++; }

void sensores_iniciar() {
  pinMode(PIN_TRIG, OUTPUT);
  digitalWrite(PIN_TRIG, LOW);
  pinMode(PIN_ECHO, INPUT);
  pinMode(PIN_ENC_ESQ, INPUT_PULLUP);
  pinMode(PIN_ENC_DIR, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_ENC_ESQ), isrEsq, RISING);
  attachInterrupt(digitalPinToInterrupt(PIN_ENC_DIR), isrDir, RISING);
}

// Medição em 4 estados, sem pulseIn (que travaria o loop por até dezenas de ms e faria perder comandos).
//   0: espera a hora da próxima medição e dispara o pulso de 10 us
//   1: espera o eco subir (até 6 ms)     2: mede a duração do eco (até 14 ms ~ 2,4 m)     3: descansa
void sensores_atualizar() {
  if (!servo_frontal_pronto()) {
    // Aborta inclusive um eco iniciado antes de o sensor mudar de direcao.
    // Leitura lateral nunca atualiza a distancia/validade frontal.
    if (!servo_medicao_pronta()) {
      digitalWrite(PIN_TRIG, LOW);
      g_estado = 0;
      g_proxMs = millis();
    }
    g_dist = DIST_SEM_LEITURA;
    g_perto = g_longe = 0;
    g_invalidas = OBSTACULO_LEITURAS;
    g_bloqueado = g_falha = true;
    if (!servo_medicao_pronta()) return;
  }
  switch (g_estado) {
    case 0:
      if ((int32_t)(millis() - g_proxMs) >= 0) {
        digitalWrite(PIN_TRIG, HIGH);
        delayMicroseconds(10);
        digitalWrite(PIN_TRIG, LOW);
        g_t0 = micros();
        g_estado = 1;
      }
      break;
    case 1:
      if (digitalRead(PIN_ECHO)) {
        g_tEco = micros();
        g_estado = 2;
      } else if (micros() - g_t0 > 6000UL) {
        registrarLeitura(0, false);
        g_estado = 3;
      }
      break;
    case 2:
      if (!digitalRead(PIN_ECHO)) {
        const uint32_t us = micros() - g_tEco;
        const uint16_t cm = (uint16_t)(us / 58UL);
        registrarLeitura(cm, cm >= 2 && cm <= 400);
        g_estado = 3;
      } else if (micros() - g_tEco > 14000UL) {
        registrarLeitura(0, false);
        g_estado = 3;
      }
      break;
    default:
      g_proxMs = millis() + 60;                   // pausa entre medições (evita eco de eco)
      g_estado = 0;
      break;
  }
  if (!g_falha && millis() - g_ultimaValidaMs > SENSOR_TIMEOUT_MS) {
    g_falha = true;
    g_bloqueado = true;
  }
}

uint16_t sensores_distancia_cm() { return g_dist; }
bool sensores_avanco_bloqueado() { return g_bloqueado || g_falha; }
bool sensores_falha() { return g_falha; }
bool sensores_obstaculo_confirmado() { return !g_falha && g_perto >= OBSTACULO_LEITURAS; }

uint16_t sensores_encoder_esq() {
  noInterrupts();
  const uint16_t v = g_encEsq;
  interrupts();
  return v & 0x3FFF;
}

uint16_t sensores_encoder_dir() {
  noInterrupts();
  const uint16_t v = g_encDir;
  interrupts();
  return v & 0x3FFF;
}

#else  // sem sensores (modo com câmera): funções vazias, para o resto do código compilar igual

void sensores_iniciar() {}
void sensores_atualizar() {}
uint16_t sensores_distancia_cm() { return DIST_SEM_LEITURA; }
uint16_t sensores_encoder_esq() { return 0; }
uint16_t sensores_encoder_dir() { return 0; }
bool sensores_avanco_bloqueado() { return false; }
bool sensores_falha() { return false; }
bool sensores_obstaculo_confirmado() { return false; }

#endif  // USAR_SENSORES
