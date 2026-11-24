#include <Arduino.h>
#include <stdlib.h>
#include "../robo_firmware/config.h"
#include "../robo_firmware/servo.h"
#include "../robo_firmware/sonar_movimento.h"
static bool g_echoPorAngulo = false;
static bool g_falhasFrontaisIsoladas = false;
static uint16_t g_frentesIntermitentes = 0, g_distIntermitente = 80;
struct DisparoSonar { uint8_t angulo; uint16_t cm; uint32_t us; };
static std::vector<DisparoSonar> g_disparosSonar;
static uint16_t g_echoSonarCm = 0;
static int g_sonarMudouDuranteEco = 0;
static std::vector<uint32_t> g_disparosFrenteMovimento;
uint32_t g_us = 1000; uint8_t g_pinDig[32]; uint8_t g_pwm[32]; isr_t g_isr[2];
uint32_t g_uartProntaUs = 0;
uint32_t g_trigFallUs = 0, g_echoDistCm = 80; bool g_echoAtivo = false; int g_wdt = 0;
std::deque<uint8_t> g_rx; std::vector<uint8_t> g_tx; Udr UDR0; Ucsra UCSR0A;
volatile uint8_t UCSR0B, UCSR0C, UBRR0H, UBRR0L, MCUSR;
volatile uint8_t TCCR1A, TCCR1B, SREG;
volatile uint16_t TCNT1, ICR1, OCR1A;
HardwareSerialFalso Serial;
void pinMode(uint8_t, uint8_t) {}
void digitalWrite(uint8_t p, uint8_t v) {
  if (p == PIN_TRIG && g_pinDig[PIN_TRIG] && !v) {
    g_trigFallUs = g_us;
    g_distIntermitente = g_echoDistCm;
    if (g_falhasFrontaisIsoladas && servo_em_sonar_movimento() && servo_medicao_frontal() &&
        ++g_frentesIntermitentes % 3 == 1) g_distIntermitente = 0;
    if (servo_em_sonar_movimento() && servo_medicao_frontal()) g_disparosFrenteMovimento.push_back(g_us);
    if (g_echoPorAngulo && servo_em_sonar()) {
      const uint8_t ang = servo_angulo_nominal();
      g_echoSonarCm = ang >= 70 && ang <= 80 ? 0 : ang + 90;
      g_disparosSonar.push_back({ang, g_echoSonarCm, g_us});
    }
  }
  g_pinDig[p] = v;
}
int digitalRead(uint8_t p) {
  if (p == PIN_ECHO) {  // ECHO: sobe 700 us depois do trigger e dura dist*58 us (0 = sem eco)
    g_us += 2;
    const uint32_t distancia = g_echoPorAngulo ? g_echoSonarCm :
        (g_falhasFrontaisIsoladas ? g_distIntermitente : g_echoDistCm);
    if (distancia == 0) return 0;
    uint32_t t = g_us - g_trigFallUs;
    if (g_echoPorAngulo && t >= 700 + distancia * 58 && !g_disparosSonar.empty() &&
        servo_angulo_nominal() != g_disparosSonar.back().angulo) g_sonarMudouDuranteEco++;
    return (t >= 700 && t < 700 + distancia * 58) ? 1 : 0;
  }
  return g_pinDig[p];
}
void analogWrite(uint8_t p, int v) { g_pwm[p] = v; }
void attachInterrupt(int n, isr_t f, int) { g_isr[n] = f; }
#include "../robo_firmware/robo_firmware.ino"

// ---------------- teste
static int falhas = 0;
#define CHECK(c, msg) do { if (!(c)) { printf("FALHA: %s\n", msg); falhas++; } } while (0)
static void step(int ms) { uint32_t fim = g_us + ms * 1000UL; while (g_us < fim) loop(); }
static void cmd(uint8_t c, int8_t a, int8_t b) {
  uint8_t A = (uint8_t)a, B = (uint8_t)b;
  uint8_t p[5] = {0xAA, c, A, B, (uint8_t)(c ^ A ^ B ^ 0x5A)};
  for (int i = 0; i < 5; i++) g_rx.push_back(p[i]);
}
struct Sens { int dist, el, er, flags; };
static bool ultimoPacote(Sens *s) {
  // procura o último pacote FF FC + 7 bytes; também valida o enquadramento de todo o fluxo
  bool achou = false; int ok = 0;
  for (size_t i = 0; i + 8 < g_tx.size();) {
    if (g_tx[i] == 0xFF && g_tx[i + 1] == 0xFC) {
      for (int k = 2; k < 9; k++) if (g_tx[i + k] > 0x7F) { printf("byte invalido no pacote\n"); falhas++; }
      s->dist = g_tx[i + 2] | (g_tx[i + 3] << 7);
      s->el = g_tx[i + 4] | (g_tx[i + 5] << 7);
      s->er = g_tx[i + 6] | (g_tx[i + 7] << 7);
      s->flags = g_tx[i + 8];
      achou = true; ok++; i += 9;
    } else if (g_tx[i] == SYNC && g_tx[i + 1] == IDX_GUARDA_SONAR && i + 2 < g_tx.size()) {
      CHECK(g_tx[i + 2] < 128, "diagnostico guarda usa 7 bits");
      i += 3;
    } else if (g_tx[i] == SYNC && g_tx[i + 1] == IDX_MOTORES && i + 6 < g_tx.size()) {
      for (int k = 2; k < 7; k++) CHECK(g_tx[i + k] < 128, "diagnostico motores usa 7 bits");
      i += 7;
    } else if (g_tx[i] == SYNC && g_tx[i + 1] == IDX_INSPECAO && i + 6 < g_tx.size()) {
      for (int k = 2; k < 7; k++) CHECK(g_tx[i + k] < 128, "inspecao usa 7 bits");
      i += 7;
    } else if (g_tx[i] == SYNC && g_tx[i + 1] == IDX_SONAR && i + 7 < g_tx.size()) {
      for (int k = 2; k < 8; k++) CHECK(g_tx[i + k] < 128, "sonar usa payload de 7 bits");
      i += 8;
    } else if (g_tx[i] == SYNC && g_tx[i + 1] == IDX_SERVO && i + 6 < g_tx.size()) {
      for (int k = 2; k < 7; k++) CHECK(g_tx[i + k] < 128, "servo usa payload de 7 bits");
      i += 7;
    } else { printf("lixo no fluxo em %zu\n", i); falhas++; i++; }
  }
  printf("  pacotes de sensores: %d\n", ok);
  return achou;
}
int main() {
  setup();
  CHECK(UBRR0L == 16, "UBRR para 115200");
  CHECK(g_pwm[5] == 0 && g_pwm[6] == 0, "motores parados no boot");
  Sens s;
  g_echoDistCm = 80; step(400);
  CHECK(ultimoPacote(&s), "pacote de sensores");
  printf("  distancia lida: %d cm (esperado 80)\n", s.dist);
  CHECK(s.dist >= 79 && s.dist <= 81, "distancia 80 cm");
  for (uint16_t cm : {240, 300, 400}) {
    g_echoDistCm = cm; step(400);
    CHECK(!sensores_falha() && sensores_distancia_cm() >= cm - 1 && sensores_distancia_cm() <= cm + 1,
          "ecos a 2,4/3/4 metros dentro da faixa configurada sao aceitos");
  }
  g_echoDistCm = 410; step(400);
  CHECK(sensores_falha() && sensores_avanco_bloqueado(), "eco acima da faixa continua invalido e bloqueado");
  g_echoDistCm = 80; step(240);
  g_tx.clear();
  g_echoDistCm = 0; step(300); ultimoPacote(&s);
  CHECK(s.dist == 0x3FFF, "sem eco -> 0x3FFF");
  g_tx.clear();
  g_echoDistCm = 15; step(300); ultimoPacote(&s); CHECK(s.dist >= 14 && s.dist <= 16, "15 cm");
  // limpa a falha do período sem eco; são necessárias duas leituras a >= 30 cm
  g_echoDistCm = 80; step(180);
  // comandos de motor
  cmd('M', 60, 0); step(60);
  CHECK(g_pwm[6] == 120 && g_pwm[5] == 0,
        "roda esquerda usa canal fisico B, encoder D2");
  cmd('M', 0, 60); step(60);
  CHECK(g_pwm[5] == 120 && g_pwm[6] == 0,
        "roda direita usa canal fisico A, encoder D3");
  g_tx.clear(); cmd('M', 70, 70); step(60);
  CHECK(g_pwm[5] == 140 && g_pwm[6] == 140, "PWM 140/140");
  CHECK(g_pinDig[PIN_IN1] == !MOTOR_ESQ_INVERTIDO && g_pinDig[PIN_IN2] == MOTOR_ESQ_INVERTIDO &&
        g_pinDig[PIN_IN3] == !MOTOR_DIR_INVERTIDO && g_pinDig[PIN_IN4] == MOTOR_DIR_INVERTIDO, "frente com polaridade da montagem");
  step(500);
  CHECK(g_pwm[5] == 0 && g_pwm[6] == 0 && !g_pinDig[7] && !g_pinDig[8], "watchdog parou os motores");
  // obstáculo interrompe movimento ativo e comandos repetidos não liberam o avanço
  cmd('M', 70, 70); step(60); CHECK(g_pwm[5] == 140, "avanco liberado com caminho livre");
  g_echoDistCm = 20; step(240);
  CHECK(sensores_obstaculo_confirmado(), "obstaculo confirmado por ecos consecutivos");
  CHECK(g_pwm[5] == 0 && g_pwm[6] == 0, "obstaculo para motores em movimento");
  cmd('M', 70, 70); step(60); CHECK(g_pwm[5] == 0 && g_pwm[6] == 0, "avanco bloqueado com comandos repetidos");
  cmd('M', -65, -65); step(60); CHECK(g_pwm[5] == 130 && g_pwm[6] == 130, "re permitida com obstaculo frontal");
  cmd('S', 0, 0); step(20);
  g_echoDistCm = 32; step(240);
  cmd('M', 70, 70); step(60); CHECK(g_pwm[5] > 0 && g_pwm[5] < 140, "liberacao reduzida apos afastar para 32 cm");
  // leituras ausentes persistentes entram em estado seguro e bloqueiam avanço
  g_echoDistCm = 0; step(240);
  cmd('M', 70, 70); step(60); CHECK(g_pwm[5] == 0 && g_pwm[6] == 0, "falha persistente bloqueia avanco");
  g_echoDistCm = 80; step(180); cmd('S', 0, 0); step(20);
  cmd('M', -65, 65); step(60);
  CHECK(g_pwm[5] == 130 && g_pwm[6] == 130, "PWM 130/130");
  CHECK(g_pinDig[PIN_IN1] == MOTOR_ESQ_INVERTIDO && g_pinDig[PIN_IN2] == !MOTOR_ESQ_INVERTIDO &&
        g_pinDig[PIN_IN3] == !MOTOR_DIR_INVERTIDO && g_pinDig[PIN_IN4] == MOTOR_DIR_INVERTIDO, "giro: esq re, dir frente");
  cmd('S', 0, 0); step(20);
  CHECK(g_pwm[5] == 0 && g_pwm[6] == 0, "comando S");
  // checksum errado
  uint8_t ruim[5] = {0xAA, 'M', 50, 50, 0x00}; for (int i = 0; i < 5; i++) g_rx.push_back(ruim[i]); step(20);
  CHECK(g_pwm[5] == 0, "checksum errado ignorado");
  // encoders (14 bits, com volta)
  g_tx.clear();
  for (int i = 0; i < 100; i++) g_isr[0]();
  for (int i = 0; i < 30; i++) g_isr[1]();
  step(120); ultimoPacote(&s);
  CHECK(s.el == 100 && s.er == 30, "encoders 100/30");
  for (int i = 0; i < 16300; i++) g_isr[0]();   // passa de 16384
  g_tx.clear(); step(120); ultimoPacote(&s);
  printf("  encoder esq apos volta: %d (esperado %d)\n", s.el, (100 + 16300) & 0x3FFF);
  CHECK(s.el == ((100 + 16300) & 0x3FFF), "encoder da a volta em 14 bits");
#if USAR_SERVO
  CHECK(ICR1 == 39999 && OCR1A == SERVO_CENTRO_US * 2, "Timer1 configurado em 50 Hz, centro");
  CHECK(!servo_varrendo() && servo_frontal_pronto(), "boot sem varredura");
  g_echoDistCm = 80; step(200);
  cmd('M', 60, 60); step(30);
  CHECK(!motores_parados(), "motor em movimento antes de recusar varredura");
  cmd('V', 1, 0); step(20);
  CHECK(!servo_varrendo(), "nao inicia varredura com motores ativos");
  cmd('S', 0, 0); step(10);
  cmd('V', 1, 0); step(100);
  CHECK(servo_varrendo() && !servo_frontal_pronto(), "varredura habilitada com motores parados");
  CHECK(sensores_distancia_cm() == DIST_SEM_LEITURA, "distancia frontal invalida enquanto varre");
  CHECK(sensores_falha() && sensores_avanco_bloqueado(), "scan nao renova protecao frontal");
  for (int i = 0; i < 40; i++) {
    cmd('V', 1, 0);
    cmd('M', 60, 60); step(50);
    CHECK(motores_parados(), "avanco bloqueado em varredura");
    cmd('M', -60, -60); step(50);
    CHECK(motores_parados(), "re bloqueada durante varredura de bancada");
    CHECK(servo_angulo_nominal() >= 45 && servo_angulo_nominal() <= 135, "limites angulares");
    CHECK(OCR1A >= SERVO_MIN_US * 2 && OCR1A <= SERVO_MAX_US * 2, "pulsos dentro dos limites");
  }
  // Verifica que medidas laterais nao liberam o caminho e que a telemetria nova
  // nao altera o enquadramento dos sensores/encoders antigos.
  CHECK(ultimoPacote(&s), "telemetria continua durante varredura");
  CHECK(s.dist == DIST_SEM_LEITURA && (s.flags & 3) == 3, "frente indisponivel na telemetria");
  g_tx.clear();
  cmd('V', 0, 0); step(20);
  CHECK(!servo_varrendo() && !servo_frontal_pronto(), "retorno aguarda estabilizacao");
  cmd('M', 60, 60); step(20); CHECK(motores_parados(), "nao move antes de estabilizar");
  step(400); cmd('M', 60, 60); step(20);
  CHECK(g_pwm[PIN_ENA] == 120, "frente liberada somente apos novas leituras frontais");
  step(450); CHECK(motores_parados(), "watchdog dos motores preservado apos scan");
  // Ajuste negativo exercita tambem a recentralizacao pelo timeout.
  cmd('V', 1, -5); step(100);
  CHECK(servo_centro_us() == SERVO_CENTRO_US - 50, "offset negativo");
  step(450);
  CHECK(!servo_varrendo() && servo_angulo_nominal() == 90, "sem renovacao retorna ao centro");
  CHECK(servo_centro_us() == SERVO_CENTRO_US - 50, "timeout preserva ajuste negativo");
  CHECK(!servo_frontal_pronto(), "timeout nao reaproveita leitura anterior");
  step(400);
  CHECK(servo_frontal_pronto() && !sensores_avanco_bloqueado(), "sensor retoma apos timeout");
  cmd('V', 5, 0); step(30); CHECK(!servo_varrendo() && !servo_em_inspecao() && !servo_em_sonar(), "modo invalido ignorado");
  cmd('V', 1, 100); step(30); CHECK(!servo_varrendo(), "offset fora da faixa ignorado");
  CHECK(servo_centro_us() == SERVO_CENTRO_US - 50, "comando invalido nao muda centro");
  const uint8_t ruimServo[5] = {CMD_START, CMD_SERVO, 1, 0, 0};
  for (uint8_t b : ruimServo) g_rx.push_back(b);
  step(30); CHECK(!servo_varrendo(), "checksum invalido nao inicia servo");
  cmd('V', 0, 0); step(400);
  CHECK(servo_centro_us() == SERVO_CENTRO_US, "restaura centro configurado");
  // Reducao proporcional preserva a curva; nao limita re nem autoriza avanco bloqueado.
  g_echoDistCm = 80; step(250); cmd('M', 100, 50); step(20);
  CHECK(g_pwm[PIN_ENA] == 200 && g_pwm[PIN_ENB] == 100, "velocidade livre a 80 cm");
  g_echoDistCm = 45; step(180); cmd('M', 100, 50); step(20);
  const int pwm45 = g_pwm[PIN_ENA];
  CHECK(pwm45 > 80 && pwm45 < 200, "reduz ao entrar na faixa de aproximacao");
  CHECK(abs(g_pwm[PIN_ENA] - 2 * g_pwm[PIN_ENB]) <= 1, "preserva proporcao das rodas");
  g_echoDistCm = 32; step(180); cmd('M', 100, 50); step(20);
  CHECK(g_pwm[PIN_ENA] > 0 && g_pwm[PIN_ENA] < pwm45, "reduz mais ao aproximar");
  g_echoDistCm = 20; step(180);
  CHECK(motores_parados(), "barreira local para abaixo do limite");
  cmd('M', -100, -100); step(20);
  CHECK(g_pwm[PIN_ENA] == 200, "re nao recebe reducao frontal");
  cmd('S', 0, 0); step(20);

  // Inspecao parada: cada posicao recebe um eco diferente; sem eco lateral e desconhecido.
  g_tx.clear(); cmd('V', 2, 0); step(20);
  CHECK(servo_em_inspecao(), "inicia inspecao por comando explicito");
  int rodadas = 0;
  for (int i = 0; i < 160; i++) {
    const int ang = servo_angulo_nominal();
    g_echoDistCm = ang == 45 ? 75 : (ang == 90 ? 20 : 0);
    cmd('V', 2, 0);
    cmd('M', i % 2 ? 70 : -70, i % 2 ? 70 : -70);
    step(50);
    CHECK(motores_parados(), "nenhuma roda move durante inspecao");
    CHECK(sensores_distancia_cm() == DIST_SEM_LEITURA && sensores_avanco_bloqueado(),
          "leituras direcionais nunca liberam frente");
    if (servo_flags() & SERVO_FLAG_CONCLUIDA) { rodadas++; break; }
  }
  CHECK(rodadas == 1 && servo_angulo_nominal() == 90, "conclui e retorna ao centro");
  int nAmostras = 0, rodada = -1;
  for (size_t i = 0; i + 6 < g_tx.size(); i++) {
    if (g_tx[i] != SYNC || g_tx[i + 1] != IDX_INSPECAO) continue;
    const int ang = 45 + 45 * g_tx[i + 2], cm = g_tx[i + 3] | (g_tx[i + 4] << 7);
    const int id = g_tx[i + 5] | (g_tx[i + 6] << 7);
    if (rodada < 0) rodada = id;
    CHECK(id == rodada, "mesma rodada nos tres resultados");
    CHECK(ang == (nAmostras == 0 ? 45 : (nAmostras == 1 ? 90 : 135)), "ordem dos alvos");
    CHECK(ang == 45 ? cm >= 74 && cm <= 76 :
          (ang == 90 ? cm >= 19 && cm <= 21 : cm == DIST_SEM_LEITURA),
          "resultado corresponde ao angulo; sem eco nao significa caminho livre");
    nAmostras++;
  }
  CHECK(nAmostras == 3, "tres resultados direcionais, sem repeticao por keep-alive");
  cmd('V', 2, 0); step(100);
  CHECK(servo_flags() & SERVO_FLAG_CONCLUIDA, "renovar nao reinicia inspecao concluida");
  step(450);
  CHECK(!servo_em_inspecao() && servo_angulo_nominal() == 90, "timeout abandona inspecao");
  CHECK(motores_parados(), "timeout nao retoma movimento");
  g_echoDistCm = 80; step(400);
  CHECK(!sensores_avanco_bloqueado(), "so novas leituras frontais liberam protecao");
  cmd('V', 2, 0); step(150); cmd('V', 0, 0); step(20);
  CHECK(!servo_em_inspecao() && !servo_frontal_pronto(), "cancelamento recentraliza e aguarda");
  step(400); cmd('M', 60, 60); step(20); cmd('V', 3, 0); step(20);
  CHECK(!servo_em_sonar(), "sonar recusado com motores ativos");
  cmd('S', 0, 0); step(20); cmd('V', 3, 1); step(20);
  CHECK(!servo_em_sonar(), "sonar recusa offset sem calibracao");
  g_tx.clear(); g_echoPorAngulo = true; g_disparosSonar.clear();
  bool visitado[181] = {};
  int angAnterior = servo_angulo_nominal(), sentidoMovimento = -1, inversoes = 0;
  uint32_t ultimoMovimento = g_us;
  for (int i = 0; i < 400; i++) {
    cmd('V', 3, 0); // renovar nao pode reiniciar a sequencia
    cmd('M', i % 2 ? 60 : -60, i % 2 ? 60 : -60);
    for (int j = 0; j < 50; j++) {
      step(1);
      const int ang = servo_angulo_nominal();
      if (ang >= 0 && ang <= 180) visitado[ang] = true;
      if (ang != angAnterior) {
        if (angAnterior == SONAR_ANGULO_MIN) { sentidoMovimento = 1; inversoes++; }
        if (angAnterior == SONAR_ANGULO_MAX) { sentidoMovimento = -1; inversoes++; }
        CHECK(ang == angAnterior + sentidoMovimento, "movimento avanca um grau sem saltos");
        CHECK(g_us - ultimoMovimento <= (SERVO_PASSO_MS + 4) * 1000UL,
              "sonar nao pausa por eco, ausencia de eco ou envio UART");
        ultimoMovimento = g_us;
      }
      CHECK(g_us - ultimoMovimento <= (SERVO_PASSO_MS + 4) * 1000UL, "sem pausa de 200 ms por grau");
      angAnterior = ang;
    }
    CHECK(servo_em_sonar() && (servo_flags() & SERVO_FLAG_SONAR), "sonar permanece ativo");
    CHECK(motores_parados() && !servo_frontal_pronto() && sensores_avanco_bloqueado(),
          "sonar bloqueia movimento inclusive ao medir 90 graus");
    CHECK(sensores_distancia_cm() == DIST_SEM_LEITURA, "sonar nunca publica eco como frontal");
    CHECK(OCR1A >= SERVO_MIN_US * 2 && OCR1A <= SERVO_MAX_US * 2, "sonar respeita pulsos");
  }
  int nSonar = 0, seqAnterior = -1, desconhecidas = 0;
  for (size_t i = 0; i + 7 < g_tx.size(); i++) {
    if (g_tx[i] != SYNC || g_tx[i + 1] != IDX_SONAR) continue;
    const int ang = g_tx[i + 2] | (g_tx[i + 3] << 7);
    const int cm = g_tx[i + 4] | (g_tx[i + 5] << 7);
    const int seq = g_tx[i + 6] | (g_tx[i + 7] << 7);
    CHECK(ang >= SONAR_ANGULO_MIN && ang <= SONAR_ANGULO_MAX, "sonar dentro da faixa");
    CHECK(nSonar < static_cast<int>(g_disparosSonar.size()), "todo resultado tem disparo");
    if (nSonar < static_cast<int>(g_disparosSonar.size())) {
      const auto &disparo = g_disparosSonar[nSonar];
      CHECK(ang == disparo.angulo, "publica angulo do disparo, nao da recepcao");
      CHECK(disparo.cm == 0 ? cm == DIST_SEM_LEITURA : abs(cm - disparo.cm) <= 1,
            "distancia corresponde ao eco iniciado nesse angulo");
      if (cm == DIST_SEM_LEITURA) desconhecidas++;
      if (nSonar > 0)
        CHECK(disparo.us - g_disparosSonar[nSonar - 1].us >= 60000UL, "intervalo minimo entre disparos");
    }
    if (seqAnterior >= 0) {
      CHECK(seq == ((seqAnterior + 1) & 0x3FFF), "sequencia nao reinicia por keep-alive");
    }
    seqAnterior = seq; nSonar++;
  }
  for (int ang = SONAR_ANGULO_MIN; ang <= SONAR_ANGULO_MAX; ang++)
    CHECK(visitado[ang], "servo percorre todos os graus");
  CHECK(nSonar > 2 * (SONAR_ANGULO_MAX - SONAR_ANGULO_MIN) && inversoes >= 2,
        "sonar continua apos ida e volta completas");
  CHECK(desconhecidas > 0 && g_sonarMudouDuranteEco > 0,
        "teste exercita eco ausente e movimento enquanto aguarda eco");
  CHECK(ultimoPacote(&s), "enquadramento da telemetria com sonar");
  step(450);
  CHECK(!servo_em_sonar() && servo_angulo_nominal() == 90 && motores_parados(),
        "timeout do sonar recentraliza sem retomar rodas");
  g_echoPorAngulo = false; g_echoDistCm = 80; step(400);
  CHECK(!sensores_avanco_bloqueado(), "novas leituras frontais apos sonar");
  cmd('V', 3, 0); step(100); cmd('V', 0, 0); step(20);
  CHECK(!servo_em_sonar() && !servo_frontal_pronto(), "cancelamento do sonar aguarda centro");
  printf("  servo: Timer1, limites, intertravamento, eco frontal e timeout conferidos\n");
#endif
#if USAR_SINALIZACAO
  // Estados visuais e prioridade do aviso usam os sensores reais do firmware.
  cmd('V', 0, 0); g_echoDistCm = 80; step(700);
  CHECK(g_pinDig[PIN_LED_VERDE] && !g_pinDig[PIN_LED_AMARELO] &&
        !g_pinDig[PIN_LED_VERMELHO], "verde com frente livre");
  g_echoDistCm = 45; step(250);
  CHECK(g_pinDig[PIN_LED_VERDE] && !g_pinDig[PIN_LED_VERMELHO] && !g_pinDig[PIN_LED_AMARELO],
        "frente liberada em aproximacao fica verde sem amarelo");
  g_echoDistCm = 0; step(300);
  CHECK(g_pinDig[PIN_LED_VERMELHO] && !g_pinDig[PIN_LED_VERDE] && !g_pinDig[PIN_LED_AMARELO],
        "falha sem obstaculo confirmado fica vermelha sem amarelo");
  g_echoDistCm = 80; step(300);
  // D10 deve permanecer intocado, mesmo com comandos legados e obstaculos.
  for (uint8_t nivel : {uint8_t(LOW), uint8_t(HIGH)}) {
    g_pinDig[10] = nivel;
    sinalizacao_iniciar();
    cmd('H', 1, 0); cmd('A', 1, 0); step(200);
    cmd('A', 2, 0); step(500);
    g_echoDistCm = 20; step(400);
    CHECK(g_pinDig[PIN_LED_VERMELHO] && !g_pinDig[PIN_LED_VERDE],
          "obstaculo continua vermelho sem buzzer");
    cmd('H', 0, 0); cmd('A', 0, 0);
    g_echoDistCm = 80; step(400);
    CHECK(g_pinDig[PIN_LED_VERDE], "frente livre continua verde");
    CHECK(g_pinDig[10] == nivel, "sinalizacao nao escreve no antigo pino D10");
  }
  cmd('M', 60, 60); step(20);
  for (int i = 0; i < 5; i++) { cmd('H', i % 2, 0); step(100); }
  CHECK(motores_parados(), "comando legado de buzina nao renova watchdog");
  printf("  sinalizacao: LEDs, D10 livre e watchdog conferidos\n");
#endif

#if USAR_SENSORES
  g_echoDistCm = 80; cmd('S', 0, 0); step(400);
  cmd('R', 28, 28); step(110);
  CHECK(g_pwm[PIN_ENA] >= VELOCIDADE_PWM_PARTIDA && g_pwm[PIN_ENB] >= VELOCIDADE_PWM_PARTIDA,
        "alvo baixo parte sem esperar pulsos para vencer atrito");
  const uint8_t pwmPartida = g_pwm[PIN_ENA];
  cmd('V', 0, 0); step(10);
  CHECK(!motores_parados() && g_pwm[PIN_ENA] == pwmPartida,
        "pedido de centro legado nao interrompe PI normal ja em movimento");
  cmd('R', 28, 28); step(110);
  CHECK(g_pwm[PIN_ENA] > pwmPartida, "renovar alvo nao reinicia integral");
  cmd('S', 0, 0); step(1);
  cmd('R', 40, 40); step(110);
  CHECK(g_pwm[PIN_ENA] > 0 && g_pwm[PIN_ENA] <= VELOCIDADE_PWM_MAX, "PI inicia com PWM limitado");
  for (int k = 0; k < 8; k++) g_isr[0]();
  cmd('R', 40, 40); step(110);
  CHECK(g_pwm[PIN_ENA] < g_pwm[PIN_ENB], "PI independente reduz roda mais rapida");
  cmd('R', 0, 40); step(1);
  CHECK(g_pwm[PIN_ENA] == 0, "alvo zero corta roda imediatamente");
  for (int k = 0; k < 15; k++) { cmd('R', 0, 40); step(100); }
  CHECK(motores_falha_encoder() && g_pwm[PIN_ENA] == 0 && g_pwm[PIN_ENB] == 0,
        "sem pulsos para ambas e trava falha");
  cmd('R', 40, 40); step(110);
  CHECK(g_pwm[PIN_ENA] == 0 && g_pwm[PIN_ENB] == 0, "R nao rearma falha");
  cmd('S', 0, 0); step(1);
  CHECK(!motores_falha_encoder(), "S rearma falha");
  cmd('R', -40, -40); step(110);
  CHECK(g_pwm[PIN_ENA] > 0 && g_pinDig[PIN_IN1] == MOTOR_ESQ_INVERTIDO &&
        g_pinDig[PIN_IN2] == !MOTOR_ESQ_INVERTIDO, "PI aceita re");
  step(450);
  CHECK(motores_parados(), "watchdog encerra PI");
  cmd('R', 40, 40); step(110);
  g_echoDistCm = 20;
  for (int k = 0; k < 5; k++) { cmd('R', 40, 40); step(80); }
  CHECK(g_pwm[PIN_ENA] == 0 && g_pwm[PIN_ENB] == 0, "obstaculo corta PI");
  cmd('S', 0, 0); step(1);

  // Regressao da aproximacao, com sensor valido e servo centralizado.
  // Planta sintetica: PWM >= partida produz 14 pulsos/s; abaixo nao vence atrito.
  // Isso verifica o algoritmo, nao calibra o motor fisico.
  g_echoDistCm = 80; step(300); cmd('R', 28, 28); step(110);
  const uint8_t pwmPILivre = g_pwm[PIN_ENA];
  cmd('S', 0, 0); step(1);
  g_echoDistCm = 32; step(300);
  CHECK(!sensores_avanco_bloqueado() && !sensores_falha(), "32 cm libera protecao frontal");
  cmd('R', 28, 28); step(110);
  printf("  PI a 32 cm: PWM inicial %u/%u, partida=%u\n",
         g_pwm[PIN_ENA], g_pwm[PIN_ENB], VELOCIDADE_PWM_PARTIDA);
  CHECK(g_pwm[PIN_ENA] >= VELOCIDADE_PWM_PARTIDA && g_pwm[PIN_ENB] >= VELOCIDADE_PWM_PARTIDA,
        "aproximacao reduz alvo de velocidade sem cortar PWM de partida novamente");
  CHECK(g_pwm[PIN_ENA] < pwmPILivre, "PI recebe alvo reduzido em relacao ao caminho livre");
#if USAR_SINALIZACAO
  CHECK(g_pinDig[PIN_LED_VERDE] && !g_pinDig[PIN_LED_VERMELHO] && !g_pinDig[PIN_LED_AMARELO],
        "PI com frente liberada a32 cm fica verde sem amarelo");
#endif
  float pulsosPlanta[2] = {0, 0};
  for (int k = 0; k < 150; k++) {
    if (k % 5 == 0) cmd('R', 28, 28);
    const uint32_t antes = g_us;
    step(10);
    for (int roda = 0; roda < 2; roda++) {
      if (g_pwm[roda == 0 ? PIN_ENA : PIN_ENB] >= VELOCIDADE_PWM_PARTIDA)
        pulsosPlanta[roda] += 14.f * (g_us - antes) / 1000000.f;
      while (pulsosPlanta[roda] >= 1.f) { g_isr[roda](); pulsosPlanta[roda] -= 1.f; }
    }
  }
  CHECK(!motores_falha_encoder() && !motores_parados(), "PI continua reduzido sem falsa roda travada");
  g_echoDistCm = 20;
  for (int k = 0; k < 4; k++) { cmd('R', 28, 28); step(50); }
  CHECK(motores_parados(), "aproximacao preserva parada por obstaculo no PI");
  cmd('S', 0, 0); step(1);
#endif
// Modo 4 em compilacoes separadas com/sem calibracao SINTETICA.
#if USAR_SERVO && USAR_SENSORES
#if !SONAR_MOV_CONTINUO
  g_echoDistCm = 80; cmd('S', 0, 0); cmd('V', 0, 0); step(400);
  cmd('V', 4, 0); step(20);
  g_disparosFrenteMovimento.clear();
  CHECK(servo_em_sonar_movimento(), "modo 4 explicito inicia parado");
  CHECK(!servo_movimento_permitido(), "modo 4 nao reutiliza leitura frontal antiga");
  int visitou60 = 0, visitou120 = 0, moveuLateral = 0;
  int livresScan = 0, verdesScan = 0, bloqueiosScan = 0;
  int pwmMinScan = 255, pwmMaxScan = 0;
  float pulsosMov = 0;
  for (int k = 0; k < 600; k++) {
    if (k % 5 == 0) { cmd('V', 4, 0); cmd('R', 12, 12); }
    step(10);
    if (g_pwm[PIN_ENA] && g_pwm[PIN_ENB]) {
      pulsosMov += (SONAR_MOV_MAX_PPS < 12 ? SONAR_MOV_MAX_PPS : 12) * .01f;
      if (servo_angulo_nominal() != 90) moveuLateral++;
    }
    while (pulsosMov >= 1.f) { g_isr[0](); g_isr[1](); pulsosMov -= 1.f; }
    if (servo_angulo_nominal() == 60) visitou60++;
    if (servo_angulo_nominal() == 120) visitou120++;
    if (k > 200 && sonar_movimento_configurado()) {
      if (sensores_avanco_bloqueado()) bloqueiosScan++;
      else {
        livresScan++;
        if (g_pwm[PIN_ENA] < pwmMinScan) pwmMinScan = g_pwm[PIN_ENA];
        if (g_pwm[PIN_ENA] > pwmMaxScan) pwmMaxScan = g_pwm[PIN_ENA];
#if USAR_SINALIZACAO
        if (g_pinDig[PIN_LED_VERDE]) verdesScan++;
#endif
      }
    }
    if (!sonar_movimento_configurado()) CHECK(motores_parados(), "sem perfil valido nunca move no modo 4");
  }
  CHECK(visitou60 && visitou120, "modo 4 visita ambos os lados retornando a frente");
  CHECK(servo_flags() & SERVO_FLAG_SONAR_MOVIMENTO, "status diferencia modo 4");
  CHECK(g_disparosFrenteMovimento.size() > 4, "frente recebe medicoes repetidas");
  for (size_t i = 1; i < g_disparosFrenteMovimento.size(); i++)
    CHECK(g_disparosFrenteMovimento[i] - g_disparosFrenteMovimento[i - 1] < SONAR_MOV_TIMEOUT_MS * 1000UL,
          "revisita frontal cabe na janela configurada nesta simulacao");
  if (sonar_movimento_configurado()) {
    printf("  varredura livre: bloqueios=%d; verde=%d/%d; PWM=%d..%d\n", bloqueiosScan, verdesScan, livresScan, pwmMinScan, pwmMaxScan);
    CHECK(bloqueiosScan == 0, "frente constante livre nao alterna bloqueio durante varredura");
#if USAR_SINALIZACAO
    CHECK(verdesScan == livresScan, "sonar com frente livre mostra verde mesmo fora do centro");
#endif
    if (SONAR_MOV_MAX_PPS == 4)
      CHECK(pwmMaxScan - pwmMinScan <= 6, "PI de 4 pulsos/s evita salto de PWM por quantizacao de um pulso");
    CHECK(moveuLateral > 0, "rodas continuam em movimento durante a observacao lateral");
    g_falhasFrontaisIsoladas = true;
    int cortesPorFalhaIsolada = 0;
    for (int k = 0; k < 600; k++) {
      if (k % 5 == 0) { cmd('V', 4, 0); cmd('R', 4, 4); }
      step(10);
      pulsosMov += .04f;
      while (pulsosMov >= 1.f) { g_isr[0](); g_isr[1](); pulsosMov -= 1.f; }
      if (k > 200 && sensores_avanco_bloqueado()) cortesPorFalhaIsolada++;
    }
    CHECK(g_frentesIntermitentes >= 6 && cortesPorFalhaIsolada == 0,
          "falha frontal isolada permite retry sem apagar memoria ainda valida");
    g_falhasFrontaisIsoladas = false;
    cmd('S', 0, 0); g_echoDistCm = 300;
    for (int k = 0; k < 60; k++) { cmd('V', 4, 0); step(50); }
    CHECK(!sensores_falha() && !sensores_avanco_bloqueado() && sensores_distancia_cm() >= 299,
          "sonar mantem frente valida com parede distante a 3 metros");
    g_echoDistCm = 80;
    cmd('V', 4, 0); cmd('M', 60, 60); step(10);
    CHECK(motores_parados(), "PWM direto recusado no modo 4");
    float encCurva[2] = {0, 0};
    int curvaLateral = 0;
    for (int k = 0; k < 60; k++) {
      cmd('V', 4, 0); cmd('R', 12, 6); step(50);
      const float e = SONAR_MOV_MAX_PPS < 12 ? SONAR_MOV_MAX_PPS : 12;
      encCurva[0] += e * .05f; encCurva[1] += e * .025f;
      for (int roda = 0; roda < 2; roda++)
        while (encCurva[roda] >= 1) { g_isr[roda](); encCurva[roda] -= 1; }
      if (!motores_parados() && servo_angulo_nominal() != 90) curvaLateral++;
    }
    CHECK(curvaLateral > 0 && sonar_movimento_em_manobra(),
          "curva manual e varredura lateral simultaneas");
    g_us += (SONAR_MOV_TIMEOUT_MS + 1) * 1000UL;
    motores_aplicar_seguranca();
    CHECK(motores_parados(), "curva corta movimento ao vencer memoria frontal");
    g_echoDistCm = 0;
    cmd('V', 4, 0); cmd('R', -12, -12); step(110);
    CHECK(!motores_parados() && sensores_falha(), "re manual permitida sem eco frontal; nao tem protecao traseira");
    CHECK(g_pinDig[PIN_IN1] == MOTOR_ESQ_INVERTIDO && g_pinDig[PIN_IN2] == !MOTOR_ESQ_INVERTIDO,
          "re manual preserva sentido fisico");
    int reLateral = 0, re60 = 0, re120 = 0;
    float pulsosRe = 0;
    for (int k = 0; k < 400; k++) {
      if (k % 5 == 0) { cmd('V', 4, 0); cmd('R', -4, -4); }
      step(10);
      pulsosRe += .04f;
      while (pulsosRe >= 1) { g_isr[0](); g_isr[1](); pulsosRe -= 1; }
      if (!motores_parados() && servo_angulo_nominal() != 90) reLateral++;
      if (servo_angulo_nominal() == 60) re60++;
      if (servo_angulo_nominal() == 120) re120++;
    }
    CHECK(reLateral && re60 && re120, "re e frente sem eco nao interrompem varredura lateral");
    cmd('S', 0, 0); step(1); g_echoDistCm = 80;
    for (int k = 0; k < 50; k++) { cmd('V', 4, 0); step(50); }
    for (int k = 0; k < 10; k++) { cmd('V', 4, 0); cmd('R', 12, 12); step(50); }
    cmd('S', 0, 0); step(1);
    cmd('V', 4, 0); cmd('R', SONAR_MOV_MAX_PPS, SONAR_MOV_MAX_PPS); step(110);
    const uint8_t pwmNoTeto = g_pwm[PIN_ENA];
    cmd('S', 0, 0); step(1);
    cmd('V', 4, 0); cmd('R', SONAR_MOV_MAX_PPS + 1, SONAR_MOV_MAX_PPS + 1); step(110);
    CHECK(pwmNoTeto > 0 && g_pwm[PIN_ENA] == pwmNoTeto, "pedido acima do teto e limitado ao mesmo alvo PI");
    cmd('S', 0, 0); step(1);
    for (int k = 0; k < 12; k++) { cmd('V', 4, 0); cmd('R', -4, -4); step(100); }
    CHECK(motores_falha_encoder() && motores_parados(), "filtro a 4 pulsos/s nao mascara encoder sem pulsos");
    cmd('S', 0, 0); step(1);
    sonar_movimento_reiniciar();
    for (int k = 0; k < 2; k++) { sonar_movimento_disparar(true); sonar_movimento_registrar(90, 80, true); }
    sonar_movimento_disparar(false); sonar_movimento_registrar(120, 10, true);
    CHECK(!sonar_movimento_bloqueado() && sonar_movimento_permitido(4, 4), "objeto a direita nao bloqueia reta com frente livre");
#if USAR_SINALIZACAO
    sinalizacao_atualizar();
    CHECK(g_pinDig[PIN_LED_VERDE] && !g_pinDig[PIN_LED_VERMELHO] && !g_pinDig[PIN_LED_AMARELO],
          "lateral ocupada preserva verde para reta liberada sem amarelo");
#endif
    CHECK(!sonar_movimento_permitido(4, 2) && sonar_movimento_permitido(2, 4), "direita bloqueada permite curva a esquerda");
    cmd('R', 4, 2); step(1);
    CHECK(motores_parados(), "guarda autoritativa recusa curva para objeto lateral");
    cmd('R', 4, 4); step(110);
    CHECK(!motores_parados(), "PI avanca reto apesar do obstaculo lateral");
    cmd('S', 0, 0);
    sonar_movimento_disparar(false); sonar_movimento_registrar(120, 10, true);
    sonar_movimento_disparar(false); sonar_movimento_registrar(120, 0, false);
    CHECK(!sonar_movimento_permitido(4, 2), "sem eco nao libera lado bloqueado");
    sonar_movimento_disparar(false); sonar_movimento_registrar(60, 200, true);
    CHECK(!sonar_movimento_permitido(4, 2), "lado oposto livre nao limpa direita bloqueada");
    sonar_movimento_disparar(false); sonar_movimento_registrar(120, 40, true);
    sonar_movimento_disparar(false); sonar_movimento_registrar(60, 10, true);
    CHECK(sonar_movimento_permitido(4, 2) && !sonar_movimento_permitido(2, 4), "esquerda bloqueada permite curva a direita");
    sonar_movimento_disparar(true); sonar_movimento_registrar(90, 10, true);
    sonar_movimento_disparar(true); sonar_movimento_registrar(90, 10, true);
    CHECK(sonar_movimento_obstaculo() && !sonar_movimento_permitido(4, 4), "frente confirmada proxima bloqueia avanco");
    CHECK(sonar_movimento_permitido(-4, -4), "re reta continua disponivel para recuo frontal");
    CHECK(sonar_movimento_lateral_esq() && !sonar_movimento_lateral_dir(), "lados possuem estados independentes");
    cmd('S', 0, 0);
  }
  if (sonar_movimento_calibrado()) {
    sonar_movimento_reiniciar();
    sonar_movimento_disparar(true); sonar_movimento_registrar(90, 80, true);
    CHECK(sonar_movimento_bloqueado(), "uma leitura frontal nao libera");
    sonar_movimento_disparar(true); sonar_movimento_registrar(90, 80, true);
    CHECK(!sonar_movimento_bloqueado(), "duas leituras frontais com margem liberam");
    sonar_movimento_disparar(true); sonar_movimento_registrar(90, 37, true);
    CHECK(sonar_movimento_bloqueado(), "reserva inclui frenagem, margem e quantizacao");
    const uint16_t ateVoltaE = (16380 - sensores_encoder_esq()) & 0x3FFF;
    const uint16_t ateVoltaD = (16380 - sensores_encoder_dir()) & 0x3FFF;
    for (uint16_t i = 0; i < ateVoltaE; i++) g_isr[0]();
    for (uint16_t i = 0; i < ateVoltaD; i++) g_isr[1]();
    sonar_movimento_disparar(true); sonar_movimento_registrar(90, 80, true);
    for (int i = 0; i < 10; i++) { g_isr[0](); g_isr[1](); }
    CHECK(sonar_movimento_distancia_cm() == 79 && !sonar_movimento_bloqueado(),
          "distancia descontada trata volta do contador de 14 bits");
    sonar_movimento_disparar(true); sonar_movimento_registrar(90, 80, true);
    for (int i = 0; i <= SONAR_MOV_AVANCO_MAX_MM; i++) { g_isr[0](); g_isr[1](); }
    CHECK(sonar_movimento_bloqueado(), "orcamento de avanco encerra validade");
    sonar_movimento_disparar(false); sonar_movimento_registrar(120, 200, true);
    CHECK(sonar_movimento_bloqueado(), "lateral longe nao renova orcamento frontal");
    sonar_movimento_disparar(true); sonar_movimento_registrar(90, 80, true);
    for (int i = 0; i <= SONAR_MOV_DESVIO_MAX_MM; i++) g_isr[0]();
    CHECK(sonar_movimento_bloqueado(), "divergencia das rodas bloqueia marcha reta");
    sonar_movimento_disparar(true); sonar_movimento_registrar(90, 80, true);
    cmd('V', 4, 0); cmd('R', 12, 12); step(110);
    CHECK(!motores_parados(), "PI ativo antes de vencer a frente");
    g_us += (SONAR_MOV_TIMEOUT_MS + 1) * 1000UL;
    motores_aplicar_seguranca();
    CHECK(motores_parados(), "guarda local corta PWM quando a leitura vence sem depender da Pi");
    sonar_movimento_disparar(false); sonar_movimento_registrar(60, 200, true);
    CHECK(sonar_movimento_falha() && sonar_movimento_bloqueado(), "eco lateral nao mascara frente vencida");
    sonar_movimento_disparar(true); sonar_movimento_registrar(90, 80, true);
    CHECK(sonar_movimento_bloqueado(), "retorno apos vencimento exige duas leituras");
    sonar_movimento_disparar(true); sonar_movimento_registrar(90, 80, true);
    sonar_movimento_disparar(false); sonar_movimento_registrar(120, 10, true);
    CHECK(!sonar_movimento_permitido(4, 2), "obstaculo lateral proximo bloqueia sua direcao");
    sonar_movimento_disparar(false); sonar_movimento_registrar(60, 200, true);
    CHECK(!sonar_movimento_permitido(4, 2), "lado oposto nao libera obstaculo lateral");
    sonar_movimento_disparar(false); sonar_movimento_registrar(120, 40, true);
    CHECK(!sonar_movimento_bloqueado(), "nova leitura do mesmo lado libera lateral");
    sonar_movimento_disparar(true); sonar_movimento_registrar(90, 0, false);
    CHECK(!sonar_movimento_falha(), "perda isolada conserva somente memoria valida anterior");
    sonar_movimento_disparar(true); sonar_movimento_registrar(90, 0, false);
    CHECK(sonar_movimento_falha() && sonar_movimento_bloqueado(), "duas falhas frontais consecutivas bloqueiam");
  } else if (!sonar_movimento_configurado())
    CHECK(moveuLateral == 0, "perfil ausente e bloqueio efetivo, nao apenas aviso");
  if (sonar_movimento_configurado()) {
    auto frente = [](uint16_t cm, bool valida) {
      sonar_movimento_disparar(true); sonar_movimento_registrar(90, cm, valida);
    };
    sonar_movimento_reiniciar();
    frente(0, false);
    CHECK(sonar_movimento_falha() && sonar_movimento_bloqueado(), "sem memoria previa, sem eco nunca libera avanco");
    frente(80, true); frente(0, false); frente(80, true);
    CHECK(sonar_movimento_bloqueado(), "partida exige duas frentes livres consecutivas apos perda");
    frente(80, true);
    CHECK(!sonar_movimento_bloqueado(), "duas frentes livres reconstroem memoria");
    frente(0, false);
    CHECK(!sonar_movimento_bloqueado() && sonar_movimento_distancia_cm() == 80, "perda unica reutiliza leitura frontal anterior");
    g_us += (SONAR_MOV_TIMEOUT_MS + 1) * 1000UL;
    CHECK(sonar_movimento_falha() && sonar_movimento_bloqueado(), "perda isolada nao prolonga prazo da memoria");
    frente(80, true); frente(80, true);
    const int limiteE = SONAR_MOV_AVANCO_MAX_MM / SONAR_MOV_MM_PULSO_ESQ + 1;
    const int limiteD = SONAR_MOV_AVANCO_MAX_MM / SONAR_MOV_MM_PULSO_DIR + 1;
    for (int k = 0; k < limiteE; k++) g_isr[0]();
    for (int k = 0; k < limiteD; k++) g_isr[1]();
    frente(0, false);
    CHECK(sonar_movimento_bloqueado(), "perda isolada nao renova orcamento de deslocamento");
    sonar_movimento_reiniciar(); frente(80, true); frente(80, true);
    frente(0, false); frente(0, false);
    CHECK(sonar_movimento_falha() && sonar_movimento_bloqueado(), "falhas consecutivas descartam memoria e param");
    frente(80, true); frente(80, true); frente(0, false); frente(10, true);
    CHECK(sonar_movimento_bloqueado(), "eco proximo valido bloqueia mesmo apos perda isolada");
    sonar_movimento_reiniciar(); frente(80, true); frente(80, true);
    CHECK(!sonar_movimento_revisitar_frente(), "frente nova sem deslocamento permite observar lateral");
    for (int n = 0; n < 1000 && !sonar_movimento_revisitar_frente(); n++) { g_isr[0](); g_isr[1](); }
    CHECK(sonar_movimento_revisitar_frente() && !sonar_movimento_bloqueado(),
          "pedido de revisita frontal antecipa limite sem bloquear rodas");
    sonar_movimento_reiniciar(); frente(80, true); frente(80, true);
    const int pulsosDesvio = SONAR_MOV_DESVIO_MAX_MM / 3.f / SONAR_MOV_MM_PULSO_DIR + 1;
    for (int n = 0; n < pulsosDesvio; n++) g_isr[1]();
    CHECK(sonar_movimento_revisitar_frente() && !sonar_movimento_bloqueado(),
          "assimetria das rodas pede retorno antes de bloquear por divergencia");
    CHECK(sonar_movimento_bloqueios() == 0, "retorno antecipado nao cria bloqueio");
    for (int n = 0; n <= SONAR_MOV_DESVIO_MAX_MM / SONAR_MOV_MM_PULSO_DIR; n++) g_isr[1]();
    CHECK(sonar_movimento_bloqueios() & GUARDA_DIVERGENCIA,
          "diagnostico distingue divergencia mesmo com frente longe");
    sonar_movimento_reiniciar(); frente(80, true); frente(80, true);
    for (int n = 0; n < pulsosDesvio; n++) g_isr[1]();
    sonar_movimento_marcha(true);
    CHECK(!sonar_movimento_revisitar_frente(),
          "curva nao usa divergencia de reta para antecipar retorno");
    sonar_movimento_reiniciar(); frente(80, true); frente(80, true);
    g_us += (SONAR_MOV_TIMEOUT_MS / 3 + 1) * 1000UL;
    CHECK(sonar_movimento_revisitar_frente() && !sonar_movimento_bloqueado(),
          "idade da frente pede retorno com tempo restante para observar");
    g_us += (SONAR_MOV_TIMEOUT_MS + 1) * 1000UL;
    CHECK(sonar_movimento_falha() && sonar_movimento_bloqueado(),
          "pedido de revisita sozinho nao renova validade frontal");
    CHECK(sonar_movimento_bloqueios() & GUARDA_VENCIDA, "diagnostico identifica frente vencida");
    sonar_movimento_reiniciar();
    CHECK(!sonar_movimento_revisitar_frente() && sonar_movimento_bloqueado(),
          "sem memoria mantem varredura e rodas bloqueadas");
  }
  cmd('V', 4, 0); step(450);
  CHECK(!servo_em_sonar_movimento() && motores_parados(), "watchdogs encerram movimento e modo 4");
  cmd('V', 4, 0); step(100); cmd('V', 0, 0); step(10);
  CHECK(!servo_em_sonar_movimento() && motores_parados(), "centro cancela modo 4 e para rodas");
#else
  g_echoDistCm = 147; cmd('S', 0, 0); cmd('V', 0, 0); step(400);
  cmd('V', 4, 0); step(10);
  CHECK(servo_em_sonar_movimento(), "manual continuo inicia modo4");
  if (sonar_movimento_configurado()) {
    CHECK(!sensores_avanco_bloqueado(), "manual herda frente valida sem esperar varredura");
    int v60 = 0, v120 = 0, cortes = 0, paradasCentro = 0;
    float fases[2] = {0, 0};
    for (int k = 0; k < 2000; k++) {
      if (k % 10 == 0) { cmd('V', 4, 0); cmd('R', 4, 4); }
      step(5);
      // E4 e D6 p/s: acumula diferenca e ultrapassa os antigos100 mm.
      for (int r = 0; r < 2; r++) {
        fases[r] += r == 0 ? .02f : .03f;
        while (fases[r] >= 1) { g_isr[r](); fases[r] -= 1; }
      }
      if (servo_angulo_nominal() == 60) v60++;
      if (servo_angulo_nominal() == 120) v120++;
      if (sensores_avanco_bloqueado()) cortes++;
      if (servo_angulo_nominal() == 90) paradasCentro++;
    }
    CHECK(v60 && v120 && paradasCentro < 100, "sonda completa varredura sem permanecer presa na frente");
    CHECK(cortes == 0 && !motores_parados(), "rodas mantem marcha apesar da varredura e assimetria");
    CHECK(sonar_movimento_distancia_cm() >= 146, "manual usa eco frontal sem desconto de odometria");
    // Objeto realimentado pelo ECHO simulado, com o servo ainda varrendo.
    g_echoDistCm = 8;
    for (int k = 0; k < 400; k++) {
      if (k % 10 == 0) { cmd('V', 4, 0); cmd('R', 4, 4); }
      step(5);
      if (k % 50 == 0 && !motores_parados()) { g_isr[0](); g_isr[1](); }
    }
    CHECK(motores_parados() && sensores_obstaculo_confirmado(),
          "eco frontal durante varredura confirma obstaculo e para ponte H");
    g_echoDistCm = 147;
    sonar_movimento_disparar(true); sonar_movimento_registrar(90, 147, true);
    sonar_movimento_disparar(true); sonar_movimento_registrar(90, 147, true);
    // A guarda usa ecos reais, com histerese; lados nao renovam a frente.
    g_echoDistCm = 8; // ecos do loop durante o ensaio de re continuam ocupados
    sonar_movimento_disparar(true); sonar_movimento_registrar(90, 8, true);
    CHECK(!sonar_movimento_bloqueado(), "um eco curto isolado nao inventa obstaculo confirmado");
    sonar_movimento_disparar(true); sonar_movimento_registrar(90, 8, true);
    motores_aplicar_seguranca();
    CHECK(motores_parados() && sensores_obstaculo_confirmado(), "obstaculo confirmado corta PWM localmente");
    CHECK(sonar_movimento_bloqueios() & GUARDA_DISTANCIA, "vermelho identifica obstaculo frontal");
    cmd('R', -4, -4); step(110);
    CHECK(!motores_parados(), "re curta continua permitida com obstaculo frontal");
    cmd('S', 0, 0); step(1);
    sonar_movimento_disparar(false); sonar_movimento_registrar(60, 147, true);
    CHECK(sonar_movimento_bloqueado(), "eco lateral nao libera frente ocupada");
    g_echoDistCm = 147;
    sonar_movimento_disparar(true); sonar_movimento_registrar(90, 147, true);
    CHECK(sonar_movimento_bloqueado(), "liberacao exige dois ecos frontais reais");
    sonar_movimento_disparar(true); sonar_movimento_registrar(90, 147, true);
    CHECK(!sonar_movimento_bloqueado(), "dois ecos livres liberam novamente");
    // Sem eco: parar por falha, mantendo a sonda em movimento.
    g_echoDistCm = 0;
    int semEco60 = 0, semEco120 = 0;
    for (int k = 0; k < 400; k++) {
      if (k % 5 == 0) { cmd('V', 4, 0); cmd('S', 0, 0); }
      step(10);
      if (servo_angulo_nominal() == 60) semEco60++;
      if (servo_angulo_nominal() == 120) semEco120++;
    }
    CHECK(sensores_falha() && !sensores_avanco_bloqueado(), "sem eco informa falha sem cancelar comando manual");
    CHECK(semEco60 && semEco120, "falha nao prende varredura no centro");
  } else CHECK(!servo_movimento_permitido(), "perfil ausente permanece bloqueado");
  step(450);
  CHECK(!servo_em_sonar_movimento() && motores_parados(), "watchdog cancela modo continuo");
#endif
#endif
#if USAR_SENSORES
  g_echoDistCm = 147; cmd('S', 0, 0); cmd('V', 0, 0); step(400);
  cmd('R', 4, 4); step(110);
  CHECK(g_pwm[PIN_ENA] == VELOCIDADE_PWM_PARTIDA_BAIXA &&
        g_pwm[PIN_ENB] == VELOCIDADE_PWM_PARTIDA_BAIXA, "baixa velocidade parte com reforco limitado a80");
  g_isr[0](); step(1);
  CHECK(g_pwm[PIN_ENA] == VELOCIDADE_PWM_BASE_BAIXA_ESQ &&
        g_pwm[PIN_ENB] == VELOCIDADE_PWM_PARTIDA_BAIXA,
        "primeiro pulso E retira somente seu reforco antes de100 ms");
  cmd('R', 4, 4); step(10);
  CHECK(g_pwm[PIN_ENA] == VELOCIDADE_PWM_BASE_BAIXA_ESQ &&
        g_pwm[PIN_ENB] == VELOCIDADE_PWM_PARTIDA_BAIXA, "renovar R nao reinicia reforco E");
  g_isr[1](); step(1);
  CHECK(g_pwm[PIN_ENA] == VELOCIDADE_PWM_BASE_BAIXA_ESQ &&
        g_pwm[PIN_ENB] == VELOCIDADE_PWM_BASE_BAIXA_DIR, "primeiro pulso D usa sua propria base");
  for (int k = 0; k < 2; k++) { g_isr[0](); g_isr[1](); }
  step(90);
  CHECK(g_pwm[PIN_ENA] >= VELOCIDADE_PWM_BASE_BAIXA_ESQ &&
        g_pwm[PIN_ENB] >= VELOCIDADE_PWM_BASE_BAIXA_DIR,
        "piso condicional evita perder torque com medicao proxima do alvo");
  for (int k = 0; k < 2; k++) {
    cmd('R', 4, 4);
    for (int j = 0; j < 3; j++) { g_isr[0](); g_isr[1](); }
    step(100);
  }
  CHECK(g_pwm[PIN_ENA] < VELOCIDADE_PWM_BASE_BAIXA_ESQ &&
        g_pwm[PIN_ENB] < VELOCIDADE_PWM_BASE_BAIXA_DIR,
        "excesso de velocidade permite reduzir PWM abaixo do piso");
  cmd('R', 0, 4); step(1);
  CHECK(g_pwm[PIN_ENA] == 0, "zero corta roda em baixa velocidade");
  cmd('R', -4, 4); step(110);
  CHECK(g_pwm[PIN_ENA] == VELOCIDADE_PWM_PARTIDA_BAIXA &&
        g_pinDig[PIN_IN1] == MOTOR_ESQ_INVERTIDO, "zero para re inicia reforco com sentido correto");
  cmd('S', 0, 0); step(1);
  CHECK(motores_parados(), "S cancela ambos os reforcos");
  cmd('R', 2, 2); step(110);
  g_isr[0](); g_isr[0](); g_isr[1](); g_isr[1](); step(100);
  CHECK(g_pwm[PIN_ENA] < VELOCIDADE_PWM_BASE_BAIXA_ESQ &&
        g_pwm[PIN_ENB] < VELOCIDADE_PWM_BASE_BAIXA_DIR,
        "pedido abaixo da faixa ensaiada nao recebe piso de torque");
  cmd('S', 0, 0); cmd('R', -4, -4); step(110);
  for (int k = 0; k < 3; k++) { g_isr[0](); g_isr[1](); }
  step(100);
  CHECK(g_pwm[PIN_ENA] < VELOCIDADE_PWM_BASE_BAIXA_ESQ &&
        g_pwm[PIN_ENB] < VELOCIDADE_PWM_BASE_BAIXA_DIR,
        "re continua sem piso obtido em ensaio de avanco");
  cmd('S', 0, 0); step(1);

  // Planta sintetica com atrito de partida, sustentacao menor e inercia.
  // Pulsos dependem do PWM aplicado, nao do alvo enviado ao PI.
  auto testarPlantaPI = [&](bool comSonar, float atritoExtra, float assimetria = 0.f) {
    cmd('S', 0, 0); cmd('V', 0, 0); step(400);
    if (comSonar) { cmd('V', 4, 0); step(1); }
    bool liberouPlanta = false;
    int cortesPlanta = 0;
    uint8_t motivosCortes = 0;
    float taxaSintetica[2] = {0, 0}, fracaoSintetica[2] = {0, 0};
    bool girandoSintetico[2] = {false, false};
    const uint16_t inicioSintetico[2] = {sensores_encoder_esq(), sensores_encoder_dir()};
    uint16_t primeiroSegundo[2] = {0, 0}, inicioCauda[2] = {0, 0};
    for (int k = 0; k < 2000; k++) {
      if (k % 10 == 0) {
        if (comSonar) cmd('V', 4, 0);
        cmd('R', 4, 4);
      }
      const uint32_t antes = g_us;
      step(5);
      const float dtS = (g_us - antes) / 1000000.f;
      for (uint8_t i = 0; i < 2; i++) {
        const int pwm = g_pwm[i == 0 ? PIN_ENA : PIN_ENB];
        if (pwm >= 60) girandoSintetico[i] = true;
        const float limiar = (i == 0 ? 30.f : 32.f) + atritoExtra;
        const float ganho = i == 1 ? 2.f + assimetria : 2.f;
        const float desejada = girandoSintetico[i] && pwm > limiar ? (pwm - limiar) * ganho : 0;
        taxaSintetica[i] += (desejada - taxaSintetica[i]) * dtS / (.35f + dtS);
        if (taxaSintetica[i] < .5f && desejada == 0) girandoSintetico[i] = false;
        fracaoSintetica[i] += taxaSintetica[i] * dtS;
        while (fracaoSintetica[i] >= 1.f) { g_isr[i](); fracaoSintetica[i] -= 1.f; }
      }
      if (comSonar) {
        if (!sensores_avanco_bloqueado()) liberouPlanta = true;
        else if (liberouPlanta) { cortesPlanta++; motivosCortes |= sonar_movimento_bloqueios(); }
      }
      if (k == 199) {
        primeiroSegundo[0] = (sensores_encoder_esq() - inicioSintetico[0]) & 0x3FFF;
        primeiroSegundo[1] = (sensores_encoder_dir() - inicioSintetico[1]) & 0x3FFF;
      }
      if (k == 1599) { inicioCauda[0] = sensores_encoder_esq(); inicioCauda[1] = sensores_encoder_dir(); }
    }
    const uint16_t caudaE = (sensores_encoder_esq() - inicioCauda[0]) & 0x3FFF;
    const uint16_t caudaD = (sensores_encoder_dir() - inicioCauda[1]) & 0x3FFF;
    int16_t pwmDiagnosticoE, pwmDiagnosticoD; uint8_t flagsDiagnostico;
    motores_diagnostico(pwmDiagnosticoE, pwmDiagnosticoD, flagsDiagnostico);
    printf("  planta PI4 sonar=%d atritoExtra=%.1f assimetria=%.1f: primeiro segundo=%u/%u; cauda2s=%u/%u; cortes=%d\n",
           comSonar, atritoExtra, assimetria, primeiroSegundo[0], primeiroSegundo[1], caudaE, caudaD, cortesPlanta);
    CHECK(primeiroSegundo[0] <= 12 && primeiroSegundo[1] <= 12,
          "PI baixo evita arrancada prolongada na planta com inercia");
    CHECK((assimetria > 0 || (caudaE >= 6 && caudaE <= 10 && caudaD >= 6 && caudaD <= 10)) && !motores_falha_encoder(),
          "PI baixo sustenta pulsos proximos ao alvo inclusive com atrito extra");
    CHECK((flagsDiagnostico & 0x0C) == 0x08 && pwmDiagnosticoE > 0 && pwmDiagnosticoD > 0,
          "diagnostico informa PI ativo sem falha na sustentacao");
    if (assimetria == 0)
      CHECK(cortesPlanta == 0, "planta simetrica respeita orcamento frontal sem cortes apos liberacao");
    else if (sonar_movimento_experimental() && !SONAR_MOV_CONTINUO)
      CHECK(cortesPlanta > 0 && (motivosCortes & GUARDA_DIVERGENCIA),
            "assimetria forte reproduz divergencia; nao declarar giro continuo validado");
    else CHECK(cortesPlanta == 0, "manual continuo nao corta planta assimetrica pela odometria");
  };
  testarPlantaPI(false, 0);
  testarPlantaPI(false, 1);
#if USAR_SERVO
  if (sonar_movimento_configurado()) {
    testarPlantaPI(true, 0);
    testarPlantaPI(true, 1);
    testarPlantaPI(true, 0, 1.f);
  }
#endif
  cmd('S', 0, 0); cmd('V', 0, 0); step(400);
  for (int k = 0; k < 24; k++) {
    cmd('R', 4, 4);
    if (k % 5 == 0) g_isr[0]();
    step(50);
  }
  CHECK(motores_parados() && motores_falha_encoder(), "roda D sem primeiro pulso trava ambas mesmo com R renovado");
#if USAR_SINALIZACAO
  sinalizacao_atualizar();
  CHECK(g_pinDig[PIN_LED_VERMELHO] && !g_pinDig[PIN_LED_VERDE] && !g_pinDig[PIN_LED_AMARELO],
        "falha de encoder fica vermelha com amarelo desligado");
#endif
  cmd('R', 4, 4); step(110);
  CHECK(motores_parados(), "R nao rearma partida apos falha de encoder");
  cmd('S', 0, 0); cmd('R', 4, 4); step(110);
  CHECK(!motores_parados(), "S rearma partida baixa explicitamente");
  step(420);
  CHECK(motores_parados(), "watchdog corta reforco sem renovacao R");
  cmd('S', 0, 0); step(1);
#endif
#if USAR_SERVO && USAR_SENSORES
  // Rajadas chegam enquanto o loop esta ocupado (p.ex. calculos da guarda).
  // A ISR apenas recebe; nao pode executar motores/parser durante a pausa.
  g_echoDistCm = 147; cmd('S', 0, 0); cmd('V', 0, 0); step(400);
  cmd('R', 4, 4); step(110);
  CHECK(!motores_parados(), "precondicao de motor ativo no ensaio de RX");
  CHECK(UCSR0B & _BV(RXCIE0), "RX sem camera usa interrupcao para preservar rajadas");
  auto rajada = []() {
    const uint8_t bytes[] = {0xAA, 'S', 0, 0, 'S' ^ CMD_XOR,
                             0xAA, 'V', 4, 0, 'V' ^ 4 ^ CMD_XOR};
    for (uint8_t b : bytes)
      Serial.injetarDurantePausa(b);
  };
  rajada();
  CHECK(!motores_parados() && !servo_em_sonar_movimento(), "ISR nao executa comandos de movimento");
  step(2);
  CHECK(motores_parados() && servo_em_sonar_movimento(), "loop recebe S e V4 completos apos pausa de 870 us");
  int perdasRx = 0, visitou60Rx = 0, visitou120Rx = 0;
  for (int k = 0; k < 200; k++) {
    rajada(); step(49);
    if (!servo_em_sonar_movimento()) perdasRx++;
    // Amostrar a cada49 ms pode saltar o extremo continuo (dura20 ms).
    if (servo_angulo_nominal() <= (SONAR_MOV_CONTINUO ? 62 : 60)) visitou60Rx++;
    if (servo_angulo_nominal() >= (SONAR_MOV_CONTINUO ? 118 : 120)) visitou120Rx++;
  }
  CHECK(perdasRx == 0 && visitou60Rx && visitou120Rx, "rajadas renovam modo 4 e completam ambos os lados");
  step(420);
  CHECK(!servo_em_sonar_movimento() && motores_parados(), "buffer RX nao prolonga watchdog sem novos comandos");
  printf("  RX em rajadas: perdas de modo=%d, visitas 60/120=%d/%d\n", perdasRx, visitou60Rx, visitou120Rx);
#endif
  // Bluetooth manual sem HC-SR04: lease separado do watchdog dos motores.
  cmd('S', 0, 0); cmd('V', 0, 0); step(300);
  g_echoDistCm = 0; step(300);
  cmd('U', 1, 0); step(20);
  CHECK(motores_manual_sem_ultrassom(), "U1 confirma modo manual sem ultrassom");
  const uint32_t ultimoTriggerManual = g_trigFallUs;
  for (int k = 0; k < 40; k++) {
    cmd('U', 1, 0); cmd('M', 60, 60); step(50);
    CHECK(g_pwm[PIN_ENA] == 120 && g_pwm[PIN_ENB] == 120,
          "manual sustentado nao corta por eco ausente nem pede novo comando Bluetooth");
  }
  CHECK(g_trigFallUs == ultimoTriggerManual && !g_pinDig[PIN_TRIG], "manual pausa disparos HC-SR04");
  int16_t manualE, manualD; uint8_t manualFlags;
  motores_diagnostico(manualE, manualD, manualFlags);
  CHECK(manualFlags & 0x40, "F8 confirma manual sem ultrassom");
  for (int k = 0; k < 10; k++) { cmd('U', 1, 0); step(50); }
  CHECK(motores_parados() && motores_manual_sem_ultrassom(), "U nao alimenta watchdog de movimento");
  cmd('R', 60, 60); step(20);
  motores_diagnostico(manualE, manualD, manualFlags);
  CHECK((manualFlags & 0x08) && !(manualFlags & 0x30), "manual ampliado usa PI sem reforco exclusivo da faixa ate8 PPS");
  cmd('S', 0, 0); step(20);
  CHECK(motores_parados(), "S interrompe manual sem ultrassom");
  cmd('U', 0, 0); cmd('M', 60, 60); step(60);
  CHECK(!motores_manual_sem_ultrassom() && sensores_avanco_bloqueado() && motores_parados(),
        "U0 restaura protecao sem reutilizar eco antigo");
  g_echoDistCm = 15; step(300); cmd('M', 60, 60); step(20);
  CHECK(motores_parados(), "autonomo continua bloqueado por obstaculo depois de U0");
  g_echoDistCm = 80; step(300); cmd('M', 60, 60); step(20);
  CHECK(g_pwm[PIN_ENA] == 120 && g_pwm[PIN_ENB] == 120, "dois ecos livres novos liberam autonomo");
  cmd('S', 0, 0); cmd('U', 1, 0); step(20); g_echoDistCm = 0;
  for (int k = 0; k < 10; k++) { cmd('R', 4, 4); step(50); }
  CHECK(!motores_manual_sem_ultrassom() && motores_parados(), "R nao renova lease manual; timeout para e restaura ultrassom");
  cmd('U', 2, 0); step(10);
  CHECK(!motores_manual_sem_ultrassom(), "U com argumento invalido ignorado");
  printf("%s (falhas=%d)\n", falhas ? "REPROVADO" : "TUDO_OK", falhas);
  return falhas ? 1 : 0;
}
