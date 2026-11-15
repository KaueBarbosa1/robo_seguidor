#include "config.h"
#if USAR_CAMERA
#include "ov7670.h"
#include <Wire.h>
#include "config.h"
#include "ov7670_tabelas.h"

void ov7670_clock_iniciar() {
  // Timer2 em PWM rápido com TOP = OCR2A = 0 e saída OC2A (D11) em "toggle":
  // f = F_CPU / (2 * (OCR2A + 1)) = 8 MHz.
  pinMode(PIN_XCLK, OUTPUT);
  ASSR &= ~(_BV(EXCLK) | _BV(AS2));
  TCCR2A = _BV(COM2A0) | _BV(WGM21) | _BV(WGM20);
  TCCR2B = _BV(WGM22) | _BV(CS20);
  OCR2A = 0;
}

void ov7670_i2c_iniciar() {
  Wire.begin();
  Wire.setClock(100000);
#ifdef WIRE_HAS_TIMEOUT
  Wire.setWireTimeout(3000, true);   // não trava se a câmera não responder
#endif
  // O Wire liga os pull-ups internos (para 5V). Com os pull-ups externos de 3,3V eles forçariam
  // 5V na câmera através da linha. Desligar:
  PORTC &= ~(_BV(4) | _BV(5));
}

bool ov7670_escrever(uint8_t reg, uint8_t val) {
  for (uint8_t tentativa = 0; tentativa < 3; tentativa++) {
    Wire.beginTransmission(OV_ENDERECO);
    Wire.write(reg);
    Wire.write(val);
    if (Wire.endTransmission() == 0) {
      delay(1);
      return true;
    }
    delay(2);
  }
  return false;
}

bool ov7670_ler(uint8_t reg, uint8_t *val) {
  // SCCB não aceita "repeated start": escreve o endereço do registrador, PARA, e só então lê.
  Wire.beginTransmission(OV_ENDERECO);
  Wire.write(reg);
  if (Wire.endTransmission() != 0) return false;
  if (Wire.requestFrom((uint8_t)OV_ENDERECO, (uint8_t)1) != 1) return false;
  *val = Wire.read();
  return true;
}

static bool escreverTabela(const uint8_t (*tab)[2], uint16_t n) {
  for (uint16_t i = 0; i < n; i++) {
    const uint8_t reg = pgm_read_byte(&tab[i][0]);
    const uint8_t val = pgm_read_byte(&tab[i][1]);
    if (!ov7670_escrever(reg, val)) return false;
    if (reg == 0x12 && (val & 0x80)) delay(100);   // reset por software
  }
  return true;
}

StatusCodigo ov7670_iniciar() {
  uint8_t pid = 0, ver = 0;
  if (!ov7670_ler(OV_REG_PID, &pid) || !ov7670_ler(OV_REG_VER, &ver)) return ST_SEM_I2C;
  if (pid != 0x76 || ver != 0x73) return ST_ID_ERRADO;

  if (!ov7670_escrever(0x12, 0x80)) return ST_REG_FALHOU;   // COM7: reset
  delay(100);
  if (!escreverTabela(OV_TAB_PADRAO, OV_TAB_PADRAO_N)) return ST_REG_FALHOU;
  if (!ov7670_escrever(0x15, 0x20)) return ST_REG_FALHOU;   // COM10: PCLK só oscila durante os dados
  if (!ov7670_escrever(0x0C, 0x04)) return ST_REG_FALHOU;   // COM3: habilita DCW (redução)
  if (!escreverTabela(OV_TAB_QQVGA, OV_TAB_QQVGA_N)) return ST_REG_FALHOU;     // 160x120
  if (!escreverTabela(OV_TAB_YUV422, OV_TAB_YUV422_N)) return ST_REG_FALHOU;   // YUV 4:2:2
  if (!ov7670_escrever(OV_REG_CLKRC, CAM_CLKRC)) return ST_REG_FALHOU;         // velocidade do PCLK
  return ST_OK;
}

#endif  // USAR_CAMERA
