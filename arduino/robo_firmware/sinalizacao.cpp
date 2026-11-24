#include "sinalizacao.h"
#include "config.h"
#include "sensores.h"
#include "servo.h"
#include "motores.h"

#if USAR_SINALIZACAO
static_assert(PIN_LED_VERDE != PIN_LED_AMARELO && PIN_LED_VERDE != PIN_LED_VERMELHO &&
              PIN_LED_AMARELO != PIN_LED_VERMELHO, "LEDs precisam de pinos distintos");
// Conferir conflitos de todos os novos sinais com os componentes ativos.
constexpr bool livre(uint8_t p) {
  return p != PIN_ENA && p != PIN_ENB && p != PIN_IN1 && p != PIN_IN2 &&
         p != PIN_IN3 && p != PIN_IN4 && p != PIN_TRIG && p != PIN_ECHO &&
         p != PIN_ENC_ESQ && p != PIN_ENC_DIR && (!USAR_SERVO || p != PIN_SERVO);
}
static_assert(livre(PIN_LED_VERDE) && livre(PIN_LED_AMARELO) &&
              livre(PIN_LED_VERMELHO), "Sinalizacao conflita com pino ativo");

static bool g_obstaculo = false;

// Comandos legados aceitos sem efeito; nenhum pino de som e configurado.
void sinalizacao_aviso(uint8_t) {}
void sinalizacao_buzina(bool) {}

void sinalizacao_iniciar() {
  const uint8_t pinos[] = {PIN_LED_VERDE, PIN_LED_AMARELO, PIN_LED_VERMELHO};
  for (uint8_t p : pinos) { digitalWrite(p, LOW); pinMode(p, OUTPUT); }
  g_obstaculo = false;
}

void sinalizacao_atualizar() {
  if (sensores_obstaculo_confirmado()) g_obstaculo = true;
  // Preserva o vermelho durante inspecao/falha/histerese. So novas leituras
  // frontais liberadas pelo sensor apagam um obstaculo previamente confirmado.
  if (servo_movimento_permitido() && !sensores_falha() && !sensores_avanco_bloqueado())
    g_obstaculo = false;

  const bool manual = motores_manual_sem_ultrassom();
  if (manual) g_obstaculo = false;
  const bool vermelho = motores_falha_encoder() || (!manual &&
      (g_obstaculo || !servo_movimento_permitido() || sensores_falha() || sensores_avanco_bloqueado()));
  digitalWrite(PIN_LED_VERMELHO, vermelho ? HIGH : LOW);
  digitalWrite(PIN_LED_VERDE, vermelho ? LOW : HIGH);
  // A1 e inicializado em LOW e permanece assim: o LED amarelo foi desativado.
  // A sinalizacao somente observa a guarda; nao envia comandos aos motores.


}
#else
void sinalizacao_iniciar() {}
void sinalizacao_atualizar() {}
void sinalizacao_buzina(bool) {}
void sinalizacao_aviso(uint8_t) {}
#endif
