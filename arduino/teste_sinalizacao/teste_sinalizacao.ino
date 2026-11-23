// Teste isolado para Arduino UNO: montagem SEM camera.
// LEDs: verde A0 e vermelho A3; antigo amarelo A1 mantido desligado.
const byte LEDS[] = {A0, A3};
const byte N_LEDS = sizeof(LEDS) / sizeof(LEDS[0]);
const byte BUZZER = 10;

void apagar() {
  for (byte i = 0; i < N_LEDS; i++) digitalWrite(LEDS[i], LOW);
  digitalWrite(BUZZER, LOW);
}

void setup() {
  // Mantem a ponte H da montagem sem camera desabilitada.
  const byte motores[] = {5, 6, 7, 8, 13, 12};
  for (byte i = 0; i < 6; i++) {
    digitalWrite(motores[i], LOW);
    pinMode(motores[i], OUTPUT);
  }
  for (byte i = 0; i < N_LEDS; i++) {
    digitalWrite(LEDS[i], LOW);
    pinMode(LEDS[i], OUTPUT);
  }
  digitalWrite(A1, LOW);
  pinMode(A1, OUTPUT);
  digitalWrite(BUZZER, LOW);
  pinMode(BUZZER, OUTPUT);
  Serial.begin(115200);
  apagar();
}

void loop() {
  const char* nomes[] = {"LED verde", "LED vermelho"};
  for (byte i = 0; i < N_LEDS; i++) {
    Serial.println(nomes[i]);
    digitalWrite(LEDS[i], HIGH);
    delay(1000);
    digitalWrite(LEDS[i], LOW);
    delay(300);
  }
  Serial.println("Buzzer: tres bipes");
  for (byte i = 0; i < 3; i++) {
    digitalWrite(BUZZER, HIGH);
    delay(150);
    digitalWrite(BUZZER, LOW);
    delay(350);
  }
  Serial.println("Todos os LEDs com um bipe");
  for (byte i = 0; i < N_LEDS; i++) digitalWrite(LEDS[i], HIGH);
  digitalWrite(BUZZER, HIGH);
  delay(300);
  apagar();
  delay(2000);
}
