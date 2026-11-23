#include "sonar_movimento.h"
#include "config.h"
#include "protocolo.h"
#include "sensores.h"

static bool g_disparoFrontal = false, g_valida = false;
static bool g_lateral[2] = {false, false};
static bool g_manobra = false;
static bool g_bloqueadoContinuo = true;
static uint32_t prazo_frontal() { return SONAR_MOV_TIMEOUT_MS; }
static uint8_t g_livres = 0, g_perto = 0, g_invalidas = 0;
static uint16_t g_cm = DIST_SEM_LEITURA, g_e = 0, g_d = 0, g_disparoE = 0, g_disparoD = 0;
static uint32_t g_t = 0, g_disparoT = 0;

static bool parametros_validos() {
  return SONAR_MOV_MM_PULSO_ESQ > 0 && SONAR_MOV_MM_PULSO_DIR > 0 &&
         SONAR_MOV_MAX_PPS > 0 && SONAR_MOV_MAX_PPS <= VELOCIDADE_MAX_PPS &&
         SONAR_MOV_AVANCO_MAX_MM > 0;
}
bool sonar_movimento_calibrado() {
  return SONAR_MOV_CALIBRADO && parametros_validos() && SONAR_MOV_FRENAGEM_MM > 0;
}
bool sonar_movimento_experimental() {
  return !sonar_movimento_calibrado() && SONAR_MOV_EXPERIMENTAL && parametros_validos() &&
         SONAR_MOV_RESERVA_EXPERIMENTAL_MM > 0;
}
bool sonar_movimento_configurado() {
  return sonar_movimento_calibrado() || sonar_movimento_experimental();
}
void sonar_movimento_reiniciar() {
  g_manobra = false;
  g_valida = g_disparoFrontal = false;
  g_livres = g_perto = g_invalidas = 0;
  g_cm = DIST_SEM_LEITURA;
  g_bloqueadoContinuo = !SONAR_MOV_CONTINUO;
  g_lateral[0] = g_lateral[1] = false;
}
void sonar_movimento_herdar_frente(uint16_t cm, uint32_t instante, bool bloqueada, bool obstaculo) {
#if SONAR_MOV_CONTINUO
  // Copiar apenas a frente centrada valida antes da troca de modo. Nao esperar
  // outra varredura nem inventar uma leitura livre; conservar sua idade.
  g_valida = true; g_cm = cm; g_t = instante;
  g_bloqueadoContinuo = obstaculo && cm < SONAR_MANUAL_DIST_CM;
  g_livres = cm >= SONAR_MANUAL_LIBERACAO_CM ? OBSTACULO_LEITURAS : 0;
  g_perto = g_bloqueadoContinuo ? OBSTACULO_LEITURAS : 0;
#endif
}
bool sonar_movimento_em_manobra() { return g_manobra; }
void sonar_movimento_marcha(bool manobra) {
  g_manobra = manobra;
}
void sonar_movimento_disparar(bool frontal) {
  g_disparoFrontal = frontal;
  if (!frontal) return;
  g_disparoT = millis();
  g_disparoE = sensores_encoder_esq();
  g_disparoD = sensores_encoder_dir();
}
void sonar_movimento_registrar(uint8_t angulo, uint16_t cm, bool valida) {
  if (!g_disparoFrontal) {
    if (valida && angulo != 90) {
      const uint8_t lado = angulo < 90 ? 0 : 1;
      if (cm < (SONAR_MOV_CONTINUO ? SONAR_MANUAL_DIST_CM : OBSTACULO_DIST_CM)) g_lateral[lado] = true;
      else if (cm >= (SONAR_MOV_CONTINUO ? SONAR_MANUAL_LIBERACAO_CM : OBSTACULO_LIBERACAO_CM)) g_lateral[lado] = false;
    }
    return; // lateral bloqueia a curva desse lado, nunca renova a frente
  }
  g_disparoFrontal = false;
  if (!g_valida || millis() - g_t > prazo_frontal()) {
    g_livres = 0;
    // No manual, perder eco nao cria nem apaga obstaculo confirmado.
  }
  if (!valida) {
    g_perto = 0;
    if (g_livres < OBSTACULO_LEITURAS) g_livres = 0;
    if (g_invalidas < OBSTACULO_LEITURAS) g_invalidas++;
    if (g_invalidas >= OBSTACULO_LEITURAS) {
      g_valida = false;
      g_livres = 0;
      g_cm = DIST_SEM_LEITURA;
    }
    // Uma perda isolada nao renova tempo, distancia ou encoders. A ultima
    // leitura so continua utilizavel dentro das guardas ja existentes.
    return;
  }
  g_valida = true;
  g_invalidas = 0;
  g_cm = cm; g_t = g_disparoT; g_e = g_disparoE; g_d = g_disparoD;
#if SONAR_MOV_CONTINUO
  if (cm < SONAR_MANUAL_DIST_CM) {
    g_livres = 0;
    if (g_perto < OBSTACULO_LEITURAS) g_perto++;
    if (g_perto >= OBSTACULO_LEITURAS) g_bloqueadoContinuo = true;
  } else if (cm >= SONAR_MANUAL_LIBERACAO_CM) {
    g_perto = 0;
    if (g_livres < OBSTACULO_LEITURAS) g_livres++;
    if (g_livres >= OBSTACULO_LEITURAS) g_bloqueadoContinuo = false;
  } else { g_perto = g_livres = 0; }
  return;
#endif
  if (cm < OBSTACULO_DIST_CM) {
    g_livres = 0;
    if (g_perto < OBSTACULO_LEITURAS) g_perto++;
  } else if (cm >= OBSTACULO_LIBERACAO_CM) {
    g_perto = 0;
    if (g_livres < OBSTACULO_LEITURAS) g_livres++;
  } else { g_livres = g_perto = 0; }
}
static float deslocamento(float &diferenca) {
  const uint16_t de = (sensores_encoder_esq() - g_e) & 0x3FFF;
  const uint16_t dd = (sensores_encoder_dir() - g_d) & 0x3FFF;
  const float e = de * SONAR_MOV_MM_PULSO_ESQ, d = dd * SONAR_MOV_MM_PULSO_DIR;
  diferenca = e > d ? e - d : d - e;
  return e > d ? e : d;
}
bool sonar_movimento_falha() {
  return !sonar_movimento_configurado() || !g_valida || millis() - g_t > prazo_frontal();
}
bool sonar_movimento_revisitar_frente() {
  if (!sonar_movimento_configurado() || !g_valida) return false;
  float diferenca;
  const float avancado = deslocamento(diferenca);
  // Reservar tempo e deslocamento para retorno, estabilizacao e ecos.
  // Rodas com respostas diferentes podem esgotar a guarda de divergencia
  // antes do orcamento de avanco. Nao esperar esse bloqueio para voltar.
  // Isto nao renova memoria, altera limites nem libera movimento.
  return avancado >= SONAR_MOV_AVANCO_MAX_MM / 3.f ||
         (!g_manobra && diferenca >= SONAR_MOV_DESVIO_MAX_MM / 3.f) ||
         millis() - g_t >= prazo_frontal() / 3;
}
uint16_t sonar_movimento_distancia_cm() {
  if (!g_valida || millis() - g_t > prazo_frontal()) return DIST_SEM_LEITURA;
#if SONAR_MOV_CONTINUO
  return g_cm;
#endif
  float diferenca;
  const float mm = g_cm * 10.f - deslocamento(diferenca);
  return mm > 0 ? static_cast<uint16_t>(mm / 10.f) : 0;
}
uint8_t sonar_movimento_bloqueios() {
  uint8_t motivos = 0;
  if (!sonar_movimento_configurado()) motivos |= GUARDA_PERFIL;
#if !SONAR_MOV_CONTINUO
  if (!g_valida) motivos |= GUARDA_SEM_FRENTE;
  else if (millis() - g_t > prazo_frontal()) motivos |= GUARDA_VENCIDA;
#endif
#if SONAR_MOV_CONTINUO
  if (g_bloqueadoContinuo) motivos |= GUARDA_DISTANCIA;
  return motivos;
#else
  if (g_livres < OBSTACULO_LEITURAS) motivos |= GUARDA_CONFIRMAR;
  if (motivos) return motivos;
  float diferenca;
  const float avancado = deslocamento(diferenca);
  // Um pulso de folga de quantizacao e descontado antes de autorizar movimento.
  const float quantizacao = SONAR_MOV_MM_PULSO_ESQ > SONAR_MOV_MM_PULSO_DIR ?
      SONAR_MOV_MM_PULSO_ESQ : SONAR_MOV_MM_PULSO_DIR;
  const uint16_t frenagem = sonar_movimento_calibrado() ? SONAR_MOV_FRENAGEM_MM : SONAR_MOV_RESERVA_EXPERIMENTAL_MM;
  if (avancado >= SONAR_MOV_AVANCO_MAX_MM) motivos |= GUARDA_AVANCO;
  if (!g_manobra && diferenca > SONAR_MOV_DESVIO_MAX_MM) motivos |= GUARDA_DIVERGENCIA;
  if (g_cm * 10.f - avancado <= OBSTACULO_DIST_CM * 10.f + frenagem +
                              SONAR_MOV_MARGEM_MM + quantizacao) motivos |= GUARDA_DISTANCIA;
  return motivos;
#endif
}
bool sonar_movimento_bloqueado() { return sonar_movimento_bloqueios() != 0; }
bool sonar_movimento_obstaculo() { return g_valida && g_perto >= OBSTACULO_LEITURAS; }
bool sonar_movimento_lateral_esq() { return g_lateral[SONAR_MOV_ESQUERDA_MENOR_90 ? 0 : 1]; }
bool sonar_movimento_lateral_dir() { return g_lateral[SONAR_MOV_ESQUERDA_MENOR_90 ? 1 : 0]; }
bool sonar_movimento_permitido(int16_t esq, int16_t dir) {
  if (!sonar_movimento_configurado()) return false;
  if (esq > dir && sonar_movimento_lateral_dir()) return false;
  if (esq < dir && sonar_movimento_lateral_esq()) return false;
  // Re reta afasta da frente; nao existe cobertura traseira.
  if (esq <= 0 && dir <= 0) return true;
  return !sonar_movimento_bloqueado();
}
