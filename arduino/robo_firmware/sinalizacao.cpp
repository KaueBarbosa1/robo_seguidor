#include "sinalizacao.h"
#include "config.h"
#include "sensores.h"
#include "servo.h"
#include "motores.h"

#if USAR_SINALIZACAO
static_assert(PIN_LED_VERDE != PIN_LED_AMARELO && PIN_LED_VERDE != PIN_LED_VERMELHO &&
              PIN_LED_AMARELO != PIN_LED_VERMELHO, "LEDs precisam de pinos distintos");
static_assert(AVISO_LIGADO_MS < AVISO_PERIODO_MS, "Bipes precisam de intervalo");
// Conferir conflitos de todos os novos sinais com os componentes ativos.
constexpr bool livre(uint8_t p) {
  return p != PIN_ENA && p != PIN_ENB && p != PIN_IN1 && p != PIN_IN2 &&
         p != PIN_IN3 && p != PIN_IN4 && p != PIN_TRIG && p != PIN_ECHO &&
         p != PIN_ENC_ESQ && p != PIN_ENC_DIR && (!USAR_SERVO || p != PIN_SERVO);
}
static_assert(livre(PIN_BUZZER) && livre(PIN_LED_VERDE) && livre(PIN_LED_AMARELO) &&
              livre(PIN_LED_VERMELHO), "Sinalizacao conflita com pino ativo");
static_assert(PIN_BUZZER != PIN_LED_VERDE && PIN_BUZZER != PIN_LED_AMARELO &&
              PIN_BUZZER != PIN_LED_VERMELHO, "Buzzer conflita com LED");

static uint8_t g_tipo = 0;
static uint32_t g_evento = 0, g_renovado = 0;

void sinalizacao_aviso(uint8_t tipo) {
  if (tipo > 2) return;
  if (tipo != g_tipo) g_evento = millis();
  g_tipo = tipo;
  g_renovado = millis();
}

static bool g_obstaculo = false, g_pedido = false, g_buzina = false;
static uint32_t g_inicioAviso = 0, g_inicioBuzina = 0;

void sinalizacao_iniciar() {
  const uint8_t pinos[] = {PIN_LED_VERDE, PIN_LED_AMARELO, PIN_LED_VERMELHO, PIN_BUZZER};
  for (uint8_t p : pinos) { digitalWrite(p, LOW); pinMode(p, OUTPUT); }
  g_tipo = 0;
  g_obstaculo = g_pedido = g_buzina = false;
}

void sinalizacao_buzina(bool ligada) {
  // Repetir "ligar" nao prolonga indefinidamente. E preciso soltar antes de
  // uma nova buzina. Nenhum comando aqui renova o watchdog dos motores.
  if (!ligada) g_buzina = false;
  else if (!g_pedido && !g_obstaculo) {
    g_buzina = true;
    g_inicioBuzina = millis();
  }
  g_pedido = ligada;
}

void sinalizacao_atualizar() {
  const uint32_t agora = millis();
  if (sensores_obstaculo_confirmado() && !g_obstaculo) {
    g_obstaculo = true;
    g_inicioAviso = agora;
  }
  // Preserva o vermelho durante inspecao/falha/histerese. So novas leituras
  // frontais liberadas pelo sensor apagam um obstaculo previamente confirmado.
  if (servo_movimento_permitido() && !sensores_falha() && !sensores_avanco_bloqueado())
    g_obstaculo = false;

  const bool vermelho = g_obstaculo || !servo_movimento_permitido() || sensores_falha() ||
      sensores_avanco_bloqueado() || motores_falha_encoder();
  digitalWrite(PIN_LED_VERMELHO, vermelho ? HIGH : LOW);
  digitalWrite(PIN_LED_VERDE, vermelho ? LOW : HIGH);
  // A1 e inicializado em LOW e permanece assim: o LED amarelo foi desativado.
  // A sinalizacao somente observa a guarda; nao envia comandos aos motores.

  if (g_obstaculo) g_buzina = false; // aviso tem prioridade; nao retoma buzina velha
  if (g_buzina && agora - g_inicioBuzina >= BUZINA_MAX_MS) g_buzina = false;
  const bool aviso = g_obstaculo && (agora - g_inicioAviso) % AVISO_PERIODO_MS < AVISO_LIGADO_MS;
  if (g_tipo && (agora - g_renovado >= 400 ||
      (g_tipo == 1 && agora - g_evento >= 600))) g_tipo = 0;
  const uint32_t fase = agora - g_evento;
  const bool evento = g_tipo == 1 ? fase % 200 < 100 :
      g_tipo == 2 && fase % 1200 < 400 && fase % 200 < 100;
  digitalWrite(PIN_BUZZER, (g_obstaculo ? aviso : g_tipo ? evento : g_buzina) ? HIGH : LOW);
}
#else
void sinalizacao_iniciar() {}
void sinalizacao_atualizar() {}
void sinalizacao_buzina(bool) {}
void sinalizacao_aviso(uint8_t) {}
#endif
