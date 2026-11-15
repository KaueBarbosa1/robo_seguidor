#include <Arduino.h>
#include <stdlib.h>
#include "../robo_firmware/config.h"
uint32_t g_us = 1000; uint8_t g_pinDig[32]; uint8_t g_pwm[32]; isr_t g_isr[2];
uint32_t g_uartProntaUs = 0;
uint32_t g_trigFallUs = 0, g_echoDistCm = 80; bool g_echoAtivo = false; int g_wdt = 0;
std::deque<uint8_t> g_rx; std::vector<uint8_t> g_tx; Udr UDR0; Ucsra UCSR0A;
volatile uint8_t UCSR0B, UCSR0C, UBRR0H, UBRR0L, MCUSR;
volatile uint8_t TCCR1A, TCCR1B, SREG;
volatile uint16_t TCNT1, ICR1, OCR1A;
void pinMode(uint8_t, uint8_t) {}
void digitalWrite(uint8_t p, uint8_t v) {
  if (p == PIN_TRIG && g_pinDig[PIN_TRIG] && !v) g_trigFallUs = g_us;
  g_pinDig[p] = v;
}
int digitalRead(uint8_t p) {
  if (p == PIN_ECHO) {  // ECHO: sobe 700 us depois do trigger e dura dist*58 us (0 = sem eco)
    g_us += 2;
    if (g_echoDistCm == 0) return 0;
    uint32_t t = g_us - g_trigFallUs;
    return (t >= 700 && t < 700 + g_echoDistCm * 58) ? 1 : 0;
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
    } else if (g_tx[i] == SYNC && g_tx[i + 1] == IDX_INSPECAO && i + 6 < g_tx.size()) {
      for (int k = 2; k < 7; k++) CHECK(g_tx[i + k] < 128, "inspecao usa 7 bits");
      i += 7;
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
  cmd('V', 3, 0); step(30); CHECK(!servo_varrendo() && !servo_em_inspecao(), "modo invalido ignorado");
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
  printf("  servo: Timer1, limites, intertravamento, eco frontal e timeout conferidos\n");
#endif
#if USAR_SINALIZACAO
  // Estados visuais e prioridade do aviso usam os sensores reais do firmware.
  cmd('V', 0, 0); g_echoDistCm = 80; step(700);
  CHECK(g_pinDig[PIN_LED_VERDE] && !g_pinDig[PIN_LED_AMARELO] &&
        !g_pinDig[PIN_LED_VERMELHO], "verde com frente livre");
  g_echoDistCm = 45; step(250);
  CHECK(g_pinDig[PIN_LED_AMARELO] && !g_pinDig[PIN_LED_VERDE], "amarelo na aproximacao");
  g_echoDistCm = 0; step(300);
  CHECK(g_pinDig[PIN_LED_AMARELO] && !g_pinDig[PIN_LED_VERMELHO], "falha sem obstaculo confirmado fica amarela");
  g_echoDistCm = 80; step(300);
  cmd('H', 1, 0); step(10);
  CHECK(g_pinDig[PIN_BUZZER], "buzina manual liga");
  cmd('H', 0, 0); step(10);
  CHECK(!g_pinDig[PIN_BUZZER], "soltar desliga buzina");
  cmd('H', 1, 0); step(10);
  for (int i = 0; i < 16; i++) { cmd('H', 1, 0); step(100); }
  CHECK(!g_pinDig[PIN_BUZZER], "repeticao nao estende limite da buzina");
  cmd('H', 0, 0); step(10);
  cmd('M', 60, 60); step(20);
  for (int i = 0; i < 5; i++) { cmd('H', i % 2, 0); step(100); }
  CHECK(motores_parados(), "buzina nao renova watchdog dos motores");
  cmd('H', 0, 0); step(10);
  cmd('H', 2, 0); step(10);
  CHECK(!g_pinDig[PIN_BUZZER], "payload invalido nao liga buzina");
  g_echoDistCm = 20;
  for (int i = 0; i < 400 && !sensores_obstaculo_confirmado(); i++) step(1);
  CHECK(g_pinDig[PIN_LED_VERMELHO] && !g_pinDig[PIN_LED_VERDE] &&
        !g_pinDig[PIN_LED_AMARELO], "vermelho exclusivo no obstaculo");
  CHECK(g_pinDig[PIN_BUZZER], "obstaculo inicia bipe");
  step(200); CHECK(!g_pinDig[PIN_BUZZER], "intervalo silencioso do aviso");
  step(600); CHECK(g_pinDig[PIN_BUZZER], "aviso repete sem bloquear loop");
  g_echoDistCm = 0; step(300);
  CHECK(g_pinDig[PIN_LED_VERMELHO], "falha nao apaga obstaculo anterior");
  g_echoDistCm = 80; step(300);
  CHECK(g_pinDig[PIN_LED_VERDE] && !g_pinDig[PIN_BUZZER], "novas leituras livres encerram aviso");
  cmd('A', 1, 0); step(1);
  CHECK(g_pinDig[PIN_BUZZER], "partida primeiro bipe");
  step(110); CHECK(!g_pinDig[PIN_BUZZER], "partida intervalo");
  cmd('A', 1, 0); step(100);
  CHECK(g_pinDig[PIN_BUZZER], "renovacao nao reinicia partida");
  cmd('A', 0, 0); step(1);
  CHECK(!g_pinDig[PIN_BUZZER], "cancelamento imediato");
  cmd('A', 2, 0); step(1);
  CHECK(g_pinDig[PIN_BUZZER], "linha perdida primeiro bipe");
  step(210); CHECK(g_pinDig[PIN_BUZZER], "linha perdida segundo bipe");
  step(210); CHECK(!g_pinDig[PIN_BUZZER], "aviso expira sem renovacao");
  printf("  sinalizacao: LEDs, bipes, buzina e watchdog conferidos\n");
#endif

#if USAR_SENSORES
  g_echoDistCm = 80; cmd('S', 0, 0); step(400);
  cmd('R', 28, 28); step(110);
  CHECK(g_pwm[PIN_ENA] >= VELOCIDADE_PWM_PARTIDA && g_pwm[PIN_ENB] >= VELOCIDADE_PWM_PARTIDA,
        "alvo baixo parte sem esperar pulsos para vencer atrito");
  const uint8_t pwmPartida = g_pwm[PIN_ENA];
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
#endif
  printf("%s (falhas=%d)\n", falhas ? "REPROVADO" : "TUDO_OK", falhas);
  return falhas ? 1 : 0;
}
