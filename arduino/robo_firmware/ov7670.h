// OV7670 (sem FIFO): clock, barramento SCCB (I2C) e configuração QQVGA YUV 4:2:2.
#pragma once
#include <Arduino.h>
#include "protocolo.h"

#define OV_ENDERECO 0x21   // endereço I2C de 7 bits
#define OV_REG_PID 0x0A    // esperado 0x76
#define OV_REG_VER 0x0B    // esperado 0x73
#define OV_REG_MIDH 0x1C   // esperado 0x7F
#define OV_REG_MIDL 0x1D   // esperado 0xA2
#define OV_REG_CLKRC 0x11

void ov7670_clock_iniciar();                       // 8 MHz em D11 (Timer2)
void ov7670_i2c_iniciar();                         // Wire a 100 kHz, sem pull-ups internos de 5V
bool ov7670_escrever(uint8_t reg, uint8_t val);
bool ov7670_ler(uint8_t reg, uint8_t *val);
StatusCodigo ov7670_iniciar();                     // confere o ID e grava a configuração
