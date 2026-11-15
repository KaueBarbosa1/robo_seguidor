#include "diagnostico.h"
#include "config.h"

#if MODO_DIAGNOSTICO && USAR_CAMERA

#include <Wire.h>
#include "captura.h"
#include "motores.h"
#include "ov7670.h"

// Resultados no Monitor Serial a 115200 baud. Siga a ordem: cada passo depende do anterior.

static void imprimeHex(uint8_t v) {
  Serial.print(F("0x"));
  if (v < 16) Serial.print('0');
  Serial.print(v, HEX);
}

static void varreduraI2C() {
  Serial.println(F("[2] Varredura I2C (esperado: um dispositivo em 0x21)"));
  uint8_t achados = 0;
  for (uint8_t a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) {
      Serial.print(F("    achei "));
      imprimeHex(a);
      Serial.println(a == OV_ENDERECO ? F("  <- OV7670") : F(""));
      achados++;
    }
  }
  if (achados == 0) {
    Serial.println(F("    NADA respondeu. Veja: pull-ups de 4,7k para 3,3V em SIOC/SIOD, fios A4/A5,"));
    Serial.println(F("    XCLK chegando na camera (passo 1), alimentacao 3,3V, PWDN no GND, RESET no 3,3V."));
  }
}

static bool identificacao() {
  Serial.println(F("[3] Identificacao da camera"));
  uint8_t pid = 0, ver = 0, mh = 0, ml = 0;
  const bool ok = ov7670_ler(OV_REG_PID, &pid) && ov7670_ler(OV_REG_VER, &ver);
  if (!ok) {
    Serial.println(F("    FALHA: sem resposta nos registradores PID/VER."));
    return false;
  }
  ov7670_ler(OV_REG_MIDH, &mh);
  ov7670_ler(OV_REG_MIDL, &ml);
  Serial.print(F("    PID="));  imprimeHex(pid);  Serial.print(F(" (esperado 0x76)  VER="));
  imprimeHex(ver);            Serial.print(F(" (esperado 0x73)  MID="));
  imprimeHex(mh);             imprimeHex(ml);     Serial.println(F(" (esperado 0x7FA2)"));
  if (pid == 0x76 && ver == 0x73) {
    Serial.println(F("    OK: e um OV7670 e o barramento I2C esta funcionando."));
    return true;
  }
  Serial.println(F("    ID inesperado: leitura corrompida (pull-ups? fios longos?) ou outro sensor."));
  return false;
}

// Espera VSYNC subir e descer (inicio de quadro). Com interrupcoes ligadas.
static bool aguardarInicioQuadro(uint16_t timeoutMs) {
  const uint32_t t0 = millis();
  while (!(PIND & M_VSYNC)) {
    if (millis() - t0 > timeoutMs) return false;
  }
  while (PIND & M_VSYNC) {
    if (millis() - t0 > timeoutMs) return false;
  }
  return true;
}

static float medirQuadrosPorSegundo() {
  const uint32_t t0 = millis();
  uint8_t anterior = PIND & M_VSYNC;
  uint16_t pulsos = 0;
  while (millis() - t0 < 2000) {
    const uint8_t atual = PIND & M_VSYNC;
    if (atual && !anterior) pulsos++;
    anterior = atual;
  }
  return pulsos / 2.0f;
}

// Conta as bordas de PCLK entre o fim de um VSYNC e o inicio do proximo.
// Com QQVGA YUV422 e COM10[5]=1 o esperado e 160*2*120 = 38400.
static uint32_t contarPclkQuadro(bool *estouro) {
  *estouro = false;
  if (!aguardarInicioQuadro(1500)) { *estouro = true; return 0; }
  uint32_t n = 0;
  uint32_t guarda = 4000000UL;
  uint8_t anterior = PIND & M_PCLK;
  cli();
  while (!(PIND & M_VSYNC)) {
    const uint8_t atual = PIND & M_PCLK;
    if (atual && !anterior) n++;
    anterior = atual;
    if (--guarda == 0) { *estouro = true; break; }
  }
  sei();
  return n;
}

static void analisarLinha() {
  static uint8_t raw[PCLK_POR_LINHA];
  if (!aguardarInicioQuadro(1500)) { Serial.println(F("    sem VSYNC para capturar linha")); return; }
  cli();
  for (uint8_t i = 0; i < 60; i++) pularLinha();   // vai ate a linha 60 (meio da imagem)
  lerLinhaBruta(raw);
  sei();

  float media[2] = {0, 0}, var[2] = {0, 0};
  for (uint8_t f = 0; f < 2; f++) {
    for (uint16_t k = f; k < PCLK_POR_LINHA; k += 2) media[f] += raw[k];
    media[f] /= IMG_LARGURA;
    for (uint16_t k = f; k < PCLK_POR_LINHA; k += 2) {
      const float d = raw[k] - media[f];
      var[f] += d * d;
    }
    var[f] /= IMG_LARGURA;
  }
  Serial.print(F("    bytes de indice par:   media=")); Serial.print(media[0], 1);
  Serial.print(F("  variancia=")); Serial.println(var[0], 2);
  Serial.print(F("    bytes de indice impar: media=")); Serial.print(media[1], 1);
  Serial.print(F("  variancia=")); Serial.println(var[1], 2);
  const uint8_t melhor = var[1] > var[0] ? 1 : 0;
  Serial.print(F("    sugestao: CAM_Y_FASE = ")); Serial.print(melhor);
  Serial.print(F("   (atual: ")); Serial.print(CAM_Y_FASE); Serial.println(F(")"));
  Serial.println(F("    (a luminancia Y varia muito pela imagem; U e V ficam quase constantes)"));
  Serial.print(F("    pixels (0..F) da linha 60: "));
  for (uint16_t k = melhor; k < PCLK_POR_LINHA; k += 2) Serial.print(raw[k], HEX);
  Serial.println();
}

void diagnostico_setup() {
  Serial.begin(115200);
  delay(300);
  motores_iniciar();
  Serial.println();
  Serial.println(F("=== DIAGNOSTICO DA CAMERA OV7670 ==="));

  ov7670_clock_iniciar();
  Serial.println(F("[1] XCLK de 8 MHz ligado em D11. Meca com multimetro/osciloscopio se puder:"));
  Serial.println(F("    na camera o XCLK deve ter ~3,3V de pico (use o divisor de tensao!)."));
  delay(CAM_ESPERA_INICIAL_MS);

  ov7670_i2c_iniciar();
  varreduraI2C();
  if (!identificacao()) {
    Serial.println(F("Parando aqui: corrija o passo 2/3 antes de continuar. Reinicie a placa para repetir."));
    while (true) {}
  }

  Serial.println(F("[4] Configurando QQVGA (160x120) YUV422..."));
  const StatusCodigo st = ov7670_iniciar();
  if (st != ST_OK) {
    Serial.print(F("    FALHA na configuracao, codigo ")); Serial.println((uint8_t)st);
    while (true) {}
  }
  Serial.print(F("    OK. CAM_CLKRC=")); Serial.println(CAM_CLKRC);
}

void diagnostico_loop() {
  Serial.println(F("--- medicao ---"));
  const float fps = medirQuadrosPorSegundo();
  Serial.print(F("[5] VSYNC: ")); Serial.print(fps, 2);
  Serial.println(F(" quadros/s (esperado ~2,5 com CLKRC=3)"));
  if (fps < 0.5f) {
    Serial.println(F("    SEM VSYNC. Veja: fio do VSYNC em D3, XCLK chegando, alimentacao, PWDN no GND."));
    delay(2000);
    return;
  }

  bool estouro = false;
  const uint32_t n = contarPclkQuadro(&estouro);
  Serial.print(F("[6] Bordas de PCLK por quadro: ")); Serial.print(n);
  Serial.println(F(" (esperado 38400)"));
  if (estouro || n == 0) {
    Serial.println(F("    SEM PCLK. Veja: fio do PCLK em D2 e se o XCLK realmente chega na camera."));
  } else if (n > 38400UL + 400UL) {
    Serial.println(F("    PCLK oscila fora dos dados (COM10 nao pegou?) ou ha ruido no fio do PCLK."));
  } else if (n + 400UL < 38400UL) {
    Serial.println(F("    Faltam pulsos: PCLK rapido demais para o UNO (aumente CAM_CLKRC) ou fio solto."));
  } else {
    Serial.println(F("    OK: a camera entrega 160x120 YUV nos tempos certos."));
  }

  Serial.println(F("[7] Linha de amostra (aponte a camera para algo com contraste e rode de novo):"));
  analisarLinha();
  Serial.println();
  delay(3000);
}

#else
// Fora do modo diagnostico estas funcoes nao sao usadas.
void diagnostico_setup() {}
void diagnostico_loop() {}
#endif
