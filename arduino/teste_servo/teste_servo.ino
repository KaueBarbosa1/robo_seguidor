// Teste ISOLADO do SG90 no Arduino Uno. Nao e o firmware do carrinho.
// Amarelo: D9. Marrom: GND comum. Vermelho: alimentacao externa compativel.
// Antes de energizar, conferir a fonte do servo e desligar a potencia dos motores.
// Inicia no centro para conferir o alinhamento. Envie 'v' para varrer.
// Varredura continua de ida e volta, passando pelas posicoes intermediarias.
// Faixa inicial nominal: 45 a 135 graus (nao garante cobertura de 180 graus).
// A correspondencia entre pulso e angulo precisa de calibracao no servo real.

#include <Arduino.h>

const uint8_t PIN_SERVO = 9;
const uint16_t PERIODO_US = 20000;  // aproximadamente 50 Hz
const uint16_t CENTRO_US = 1500;
const uint16_t PULSO_MIN_US = 1000;
const uint16_t PULSO_MAX_US = 2000;
const int16_t AJUSTE_CENTRO_US = 10;
const uint16_t US_POR_45_GRAUS = 500;  // referencia inicial, ainda nao calibrada
const int16_t ANGULO_MIN = 45;
const int16_t ANGULO_MAX = 135;
const int16_t PASSO_GRAUS = 1;
const uint8_t PULSOS_POR_PASSO = 1;  // aproximadamente 20 ms em cada posicao

int16_t anguloAtual = 90;
int8_t sentido = -1;
int16_t centroAtualUs = CENTRO_US;
bool varreduraAtiva = false;

static_assert(ANGULO_MIN < 90 && ANGULO_MAX > 90, "A faixa deve incluir o centro");
static_assert(PASSO_GRAUS > 0, "O passo deve ser positivo");

uint16_t amplitudeAtualUs() {
  // Mantem simetria de pulsos em torno do centro ajustado sem ultrapassar a
  // faixa ja usada. Ao deslocar o centro, reduz igualmente os dois lados.
  int16_t amplitude = US_POR_45_GRAUS;
  if (amplitude > centroAtualUs - PULSO_MIN_US) amplitude = centroAtualUs - PULSO_MIN_US;
  if (amplitude > PULSO_MAX_US - centroAtualUs) amplitude = PULSO_MAX_US - centroAtualUs;
  return amplitude;
}

uint16_t pulsoParaAngulo(uint8_t angulo) {
  const int32_t deslocamento = static_cast<int32_t>(angulo) - 90;
  return centroAtualUs + deslocamento * amplitudeAtualUs() / 45;
}

void pulsarServo(uint16_t larguraUs) {
  digitalWrite(PIN_SERVO, HIGH);
  delayMicroseconds(larguraUs);
  digitalWrite(PIN_SERVO, LOW);

  const uint16_t restanteUs = PERIODO_US - larguraUs;
  // O intervalo baixo passa de 16383 us: dividir evita ultrapassar o limite
  // de delayMicroseconds() no Uno. As esperas sao apenas para este teste.
  delay(restanteUs / 1000);
  delayMicroseconds(restanteUs % 1000);
}

void mostrarAjuste() {
  Serial.print(F("Centro (us): "));
  Serial.print(centroAtualUs);
  Serial.print(F("; limites (us): "));
  Serial.print(pulsoParaAngulo(ANGULO_MIN));
  Serial.print(F(" a "));
  Serial.println(pulsoParaAngulo(ANGULO_MAX));
}

void lerComando() {
  if (!Serial.available()) return;
  const char comando = Serial.read();
  if (comando == 'c' || comando == 'C') {
    varreduraAtiva = false;
    mostrarAjuste();
    Serial.println(F("Mantendo centro. Confira se aponta para a frente."));
  } else if (comando == '+' || comando == '-') {
    varreduraAtiva = false;
    const int16_t delta = comando == '+' ? AJUSTE_CENTRO_US : -AJUSTE_CENTRO_US;
    centroAtualUs = constrain(centroAtualUs + delta, 1250, 1750);
    mostrarAjuste();
  } else if (comando == 'v' || comando == 'V') {
    anguloAtual = 90;
    sentido = -1;
    varreduraAtiva = true;
    mostrarAjuste();
    Serial.println(F("Varredura iniciada. Envie c para manter o centro."));
  }
}

void setup() {
  // Mantem desabilitadas as saidas da ponte H no mapa ativo USAR_CAMERA=0.
  // A alimentacao de potencia dos motores deve continuar desligada no teste.
  const uint8_t pinosMotores[] = {5, 6, 7, 8, 13, 12};
  for (uint8_t i = 0; i < sizeof(pinosMotores) / sizeof(pinosMotores[0]); ++i) {
    digitalWrite(pinosMotores[i], LOW);
    pinMode(pinosMotores[i], OUTPUT);
  }

  digitalWrite(PIN_SERVO, LOW);
  pinMode(PIN_SERVO, OUTPUT);
  Serial.begin(115200);
  Serial.println(F("Teste SG90 D9: iniciando no centro para alinhamento."));
  Serial.println(F("c = centro; + / - = ajustar centro 10 us; v = varredura."));
  Serial.println(F("Ajustes sao temporarios: anote o centro antes de desligar."));
  mostrarAjuste();
  for (uint8_t i = 0; i < 50; ++i) {
    pulsarServo(CENTRO_US);
  }
}

void loop() {
  lerComando();
  if (!varreduraAtiva) {
    pulsarServo(centroAtualUs);
    return;
  }
  for (uint8_t i = 0; i < PULSOS_POR_PASSO; ++i) {
    pulsarServo(pulsoParaAngulo(anguloAtual));
  }

  if (anguloAtual == ANGULO_MIN || anguloAtual == ANGULO_MAX || anguloAtual == 90) {
    Serial.print(F("Angulo nominal: "));
    Serial.println(anguloAtual);
  }

  if (anguloAtual <= ANGULO_MIN) sentido = 1;
  if (anguloAtual >= ANGULO_MAX) sentido = -1;
  anguloAtual = constrain(anguloAtual + sentido * PASSO_GRAUS, ANGULO_MIN, ANGULO_MAX);
}
