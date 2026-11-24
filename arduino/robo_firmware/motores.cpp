#include "motores.h"
#include <stdlib.h>
#include "config.h"
#include "sensores.h"
#include "servo.h"
#include "sonar_movimento.h"

static bool g_manualSemUltrassom = false;
static uint32_t g_manualRenovacao = 0;

static bool movimento_permitido(int16_t esq, int16_t dir) {
  if (g_manualSemUltrassom) return true;
  if (servo_em_sonar_movimento()) return sonar_movimento_permitido(esq, dir);
  return servo_movimento_permitido();
}

static bool g_velocidade = false, g_interno = false, g_falhaEncoder = false;
static_assert(VELOCIDADE_PWM_PARTIDA > 0 && VELOCIDADE_PWM_PARTIDA <= VELOCIDADE_PWM_MAX,
              "PWM inicial deve respeitar limite do PI");
static int16_t g_alvo[2] = {0, 0};
static float g_integral[2] = {0, 0};
static float g_taxaFiltrada[2] = {0, 0};
static bool g_partidaBaixa[2] = {false, false};
static int16_t g_pwmRegulado[2] = {0, 0};
static_assert(VELOCIDADE_PWM_PARTIDA_BAIXA > 0 && VELOCIDADE_PWM_PARTIDA_BAIXA <= VELOCIDADE_PWM_MAX &&
              VELOCIDADE_PWM_BASE_BAIXA_ESQ > 0 && VELOCIDADE_PWM_BASE_BAIXA_DIR > 0 &&
              VELOCIDADE_PWM_BASE_BAIXA_ESQ < VELOCIDADE_PWM_PARTIDA_BAIXA &&
              VELOCIDADE_PWM_BASE_BAIXA_DIR < VELOCIDADE_PWM_PARTIDA_BAIXA,
              "PWM de baixa velocidade deve respeitar limites");
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
  if (g_manualSemUltrassom) return;
  // Manual continuo usa alvo baixo fixo ate o obstaculo confirmado. A antiga
  // rampa levava alvo4 abaixo do torque de sustentacao antes da parada.
  if (SONAR_MOV_CONTINUO && servo_em_sonar_movimento()) return;
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
  // Modos anteriores exigem centro; modo 4 consulta a guarda de deslocamento.
  if (!movimento_permitido(g_velocidade ? g_alvo[0] : esq, g_velocidade ? g_alvo[1] : dir)) esq = dir = 0;
  // Modo 4 aceita somente PI; nao existe conversao calibrada de PWM em distancia.
  if (servo_em_sonar_movimento() && !g_interno) esq = dir = 0;
  // Proteção local ao ponto que efetivamente aciona a ponte H. Ré segue liberada;
  // qualquer roda positiva é tratada como avanço/manobra com avanço.
  if (!g_manualSemUltrassom && sensores_avanco_bloqueado() && (esq > 0 || dir > 0)) esq = dir = 0;
  g_esqPedido = esq;
  g_dirPedido = dir;
  // No PI a aproximacao ja reduz o alvo em pulsos/s. Atenuar tambem o PWM
  // impede a partida e limita a capacidade do PI de vencer atrito/carga.
  if (!g_velocidade) limitarAproximacao(esq, dir);
  aplicar(esq, PIN_ENA, PIN_IN1, PIN_IN2);
  aplicar(dir, PIN_ENB, PIN_IN3, PIN_IN4);
  g_parado = (esq == 0 && dir == 0);
  g_esqAtual = esq;
  g_dirAtual = dir;
}

void motores_parar() {
  g_velocidade = false;
  g_integral[0] = g_integral[1] = 0;
  g_taxaFiltrada[0] = g_taxaFiltrada[1] = 0;
  g_partidaBaixa[0] = g_partidaBaixa[1] = false;
  g_pwmRegulado[0] = g_pwmRegulado[1] = 0;
  g_falhaEncoder = false;
  motores_set(0, 0);
  g_parado = true;
}

bool motores_manual_sem_ultrassom() { return g_manualSemUltrassom; }

void motores_usar_manual_sem_ultrassom(bool ativo) {
#if USAR_SENSORES
  if (ativo != g_manualSemUltrassom) {
    motores_parar();
    servo_comandar(0, 0);
    sensores_invalidar_frente();
    g_manualSemUltrassom = ativo;
  }
  if (ativo) g_manualRenovacao = millis();
#else
  (void)ativo; // legado com camera nao oferece esse modo nem confirmacao F8
#endif
}

void motores_marcar_comando() { g_ultimoComandoMs = millis(); }
bool motores_parados() { return g_parado; }

void motores_watchdog() {
  if (g_manualSemUltrassom && millis() - g_manualRenovacao > MOTORES_WATCHDOG_MS) {
    motores_usar_manual_sem_ultrassom(false);
  }
  if (!g_parado && (millis() - g_ultimoComandoMs) > MOTORES_WATCHDOG_MS) {
    motores_parar();
  }
}

void motores_aplicar_seguranca() {
  if (!movimento_permitido(g_velocidade ? g_alvo[0] : g_esqAtual,
                          g_velocidade ? g_alvo[1] : g_dirAtual) && !g_parado) {
    motores_parar();
    return;
  }
  if (!g_manualSemUltrassom && sensores_avanco_bloqueado() && (g_esqAtual > 0 || g_dirAtual > 0)) {
    motores_parar();
    return;
  }
  // O PI atualiza o alvo reduzido a cada VELOCIDADE_PERIODO_MS. A barreira
  // acima continua imediata; nao aplicar uma segunda reducao na saida do PI.
  if (g_velocidade) return;
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
void motores_diagnostico(int16_t &esq, int16_t &dir, uint8_t &flags) {
  esq = g_esqAtual; dir = g_dirAtual;
  flags = (esq < 0 ? 0x01 : 0) | (dir < 0 ? 0x02 : 0) |
          (g_falhaEncoder ? 0x04 : 0) | (g_velocidade ? 0x08 : 0) |
          (g_partidaBaixa[0] ? 0x10 : 0) | (g_partidaBaixa[1] ? 0x20 : 0) |
          (g_manualSemUltrassom ? 0x40 : 0);
}

void motores_velocidade(int16_t esq, int16_t dir) {
#if USAR_SENSORES
  if (g_falhaEncoder) return;
  if (abs(esq) > VELOCIDADE_MAX_PPS || abs(dir) > VELOCIDADE_MAX_PPS) return;
  if (g_manualSemUltrassom || servo_em_sonar_movimento()) {
    const int16_t maior = abs(esq) > abs(dir) ? abs(esq) : abs(dir);
    const int16_t teto = g_manualSemUltrassom ? MANUAL_SEM_ULTRASSOM_MAX_PPS : SONAR_MOV_MAX_PPS;
    if (maior > teto) {
      esq = static_cast<int32_t>(esq) * teto / maior;
      dir = static_cast<int32_t>(dir) * teto / maior;
    }
    if (esq || dir) servo_configurar_marcha(esq, dir);
  }
  if (!movimento_permitido(esq, dir) ||
      (!g_manualSemUltrassom && sensores_avanco_bloqueado() && (esq > 0 || dir > 0))) {
    motores_parar();
    return;
  }
  const bool inverteEsq = g_velocidade && esq && g_alvo[0] && ((esq > 0) != (g_alvo[0] > 0));
  const bool inverteDir = g_velocidade && dir && g_alvo[1] && ((dir > 0) != (g_alvo[1] > 0));
  const int16_t alvos[2] = {esq, dir};
  const uint16_t ticks[2] = {sensores_encoder_esq(), sensores_encoder_dir()};
  const uint32_t agora = millis();
  for (uint8_t i = 0; i < 2; i++) {
    const bool baixa = alvos[i] && abs(alvos[i]) <= VELOCIDADE_FILTRO_BAIXA_PPS;
    const bool eraBaixa = g_alvo[i] && abs(g_alvo[i]) <= VELOCIDADE_FILTRO_BAIXA_PPS;
    if (!g_velocidade || !g_alvo[i] || (alvos[i] > 0) != (g_alvo[i] > 0) || !alvos[i] || baixa != eraBaixa) {
      // Em baixa velocidade, separar reforco e integral de sustentacao.
      // Pedidos maiores conservam a inicializacao anterior. Renovar nao reinicia.
      const int16_t base = i == 0 ? VELOCIDADE_PWM_BASE_BAIXA_ESQ : VELOCIDADE_PWM_BASE_BAIXA_DIR;
      g_partidaBaixa[i] = baixa;
      g_integral[i] = alvos[i] ? (baixa ? base : VELOCIDADE_PWM_PARTIDA) : 0;
      g_pwmRegulado[i] = baixa ? (alvos[i] < 0 ? -base : base) : 0;
      g_taxaFiltrada[i] = 0;
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

static void aplicarSaidaPI() {
  int16_t saida[2];
  for (uint8_t i = 0; i < 2; i++)
    saida[i] = g_partidaBaixa[i] ? (g_alvo[i] < 0 ? -VELOCIDADE_PWM_PARTIDA_BAIXA : VELOCIDADE_PWM_PARTIDA_BAIXA)
                               : g_pwmRegulado[i];
  g_interno = true;
  motores_set(saida[0], saida[1]);
  g_interno = false;
}

void motores_regular_velocidade() {
#if USAR_SENSORES
  if (!g_velocidade) return;
  const uint32_t agora = millis(), dt = agora - g_amostra;
  if (agora - g_ultimoComandoMs > MOTORES_WATCHDOG_MS ||
      !movimento_permitido(g_alvo[0], g_alvo[1]) ||
      (!g_manualSemUltrassom && sensores_avanco_bloqueado() && (g_alvo[0] > 0 || g_alvo[1] > 0))) {
    motores_parar();
    return;
  }
  const uint16_t ticks[2] = {sensores_encoder_esq(), sensores_encoder_dir()};
  bool terminouPartida = false;
  for (uint8_t i = 0; i < 2; i++) {
    if (!g_partidaBaixa[i]) continue;
    if (((ticks[i] - g_ticks[i]) & 0x3FFF) != 0) {
      g_partidaBaixa[i] = false;
      g_pulso[i] = agora;
      terminouPartida = true;
    } else if (agora - g_pulso[i] >= VELOCIDADE_SEM_PULSO_MS) {
      motores_parar();
      g_falhaEncoder = true;
      return;
    }
  }
  // Retirar o reforco no primeiro pulso sem esperar a janela PI de100 ms.
  // Renovacoes R nao rearmam a partida; qualquer guarda acima continua prioritaria.
  if (dt < VELOCIDADE_PERIODO_MS) {
    if (terminouPartida) aplicarSaidaPI();
    return;
  }
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
    if (!g_alvo[i] || !alvosSeguros[i]) {
      g_partidaBaixa[i] = false;
      g_pwmRegulado[i] = 0;
      continue;
    }
    // O reforco nao carrega a integral; ela recebe apenas a base de sustentacao.
    if (g_partidaBaixa[i]) continue;
    const float medida = delta * 1000.0f / dt;
    if (abs(alvosSeguros[i]) <= VELOCIDADE_FILTRO_BAIXA_PPS) {
      // A 4 pulsos/s, janelas de 100 ms alternam entre 0 e 10 pulsos/s.
      // Filtrar somente a medicao; parada, deslocamento e timeout continuam
      // usando os contadores brutos, sem impor um PWM minimo permanente.
      const float alfa = dt / (VELOCIDADE_FILTRO_TAU_MS + dt);
      g_taxaFiltrada[i] += alfa * (medida - g_taxaFiltrada[i]);
    } else g_taxaFiltrada[i] = medida;
    const float erro = abs(alvosSeguros[i]) - g_taxaFiltrada[i];
    const bool baixa = abs(g_alvo[i]) <= VELOCIDADE_FILTRO_BAIXA_PPS;
    const float kp = baixa ? VELOCIDADE_KP_BAIXA : VELOCIDADE_KP;
    const float ki = baixa ? VELOCIDADE_KI_BAIXA : VELOCIDADE_KI;
    const float integralAnterior = g_integral[i];
    const float candidato = g_integral[i] + ki * erro * dt / 1000.0f;
    const float saida = kp * erro + candidato;
    // Anti-windup: nao acumular erro que empurra alem da saturacao.
    if ((saida >= 0 && saida <= VELOCIDADE_PWM_MAX) ||
        (saida > VELOCIDADE_PWM_MAX && erro < 0) || (saida < 0 && erro > 0))
      g_integral[i] = candidato;
    float limitado = kp * erro + g_integral[i];
    if (limitado < 0) limitado = 0;
    if (limitado > VELOCIDADE_PWM_MAX) limitado = VELOCIDADE_PWM_MAX;
    // A bancada mostrou perda de giro em PWM30/32. Compensar a zona morta
    // somente em avanco na faixa ensaiada e perto do alvo. Com excesso de
    // velocidade o PI volta a poder reduzir abaixo dessa referencia.
    if (baixa && alvosSeguros[i] >= VELOCIDADE_PISO_MIN_PPS &&
        g_taxaFiltrada[i] <= alvosSeguros[i] * VELOCIDADE_PISO_MAX_RAZAO) {
      const float piso = i == 0 ? VELOCIDADE_PWM_BASE_BAIXA_ESQ : VELOCIDADE_PWM_BASE_BAIXA_DIR;
      if (limitado < piso) {
        limitado = piso;
        // Anti-windup na saturacao inferior: congelar apenas a integracao
        // que empurraria mais contra o piso. Nao elevar a integral para
        // compensar o transitorio de partida.
        if (erro < 0) g_integral[i] = integralAnterior;
      }
    }
    g_pwmRegulado[i] = (g_alvo[i] < 0 ? -1 : 1) * static_cast<int16_t>(limitado);
  }
  g_amostra = agora;
  aplicarSaidaPI();
#endif
}
