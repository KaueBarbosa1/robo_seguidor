// Leitura em tempo real dos pixels do OV7670 sem FIFO.
//
// A câmera NÃO espera o Arduino: cada byte aparece em D4..D7 durante uma borda de PCLK e some.
// Com COM10[5] = 1 o PCLK só oscila durante os dados, então basta CONTAR bordas (HREF não é usado).
// Padrão de leitura herdado do projeto ComputerNerd/ov7670-no-ram-arduino-uno: espera PCLK ficar
// baixo, lê, espera voltar a alto. Cada byte consome um ciclo de PCLK.
//
// Com CAM_CLKRC = 3: PCLK = 500 kHz (2 us = 32 ciclos de CPU por byte). Uma linha são 320 bytes
// (640 us); as linhas chegam a cada ~3,1 ms. Enviar 82 bytes a 1 Mbaud leva 0,82 ms, então o envio
// cabe com folga entre uma linha e outra, sem buffer de quadro (o UNO só tem 2 KB de RAM).
//
// Chamar SEMPRE com interrupções desligadas (cli) e apenas durante a leitura de uma linha:
// uma única interrupção (millis) de 5 us já perde alguns pixels.
#pragma once
#include <Arduino.h>
#include "config.h"

#define ESPERA_BAIXO() while (PIND & M_PCLK)
#define ESPERA_ALTO() while (!(PIND & M_PCLK))

// Lê uma linha e guarda o nibble alto do Y de 2 pixels por byte: (y_par << 4) | y_impar.
// O nível 15 é limitado a 14 para que 0xFF nunca apareça nos dados (0xFF = marcador de sincronismo).
static inline void lerLinha(uint8_t *dst) {
  for (uint8_t i = 0; i < BYTES_LINHA_ENVIADA; i++) {
    uint8_t y0, y1;
#if CAM_Y_FASE == 0   // Y U Y V
    ESPERA_BAIXO(); y0 = PIND & M_DADOS; ESPERA_ALTO();
    ESPERA_BAIXO(); ESPERA_ALTO();
    ESPERA_BAIXO(); y1 = PIND & M_DADOS; ESPERA_ALTO();
    ESPERA_BAIXO(); ESPERA_ALTO();
#else                 // U Y V Y
    ESPERA_BAIXO(); ESPERA_ALTO();
    ESPERA_BAIXO(); y0 = PIND & M_DADOS; ESPERA_ALTO();
    ESPERA_BAIXO(); ESPERA_ALTO();
    ESPERA_BAIXO(); y1 = PIND & M_DADOS; ESPERA_ALTO();
#endif
    if (y0 == 0xF0) y0 = 0xE0;
    if (y1 == 0xF0) y1 = 0xE0;
    dst[i] = y0 | (y1 >> 4);
  }
}

// Consome uma linha inteira sem guardar (para pular as linhas acima de LINHA_INICIAL).
static inline void pularLinha() {
  for (uint16_t i = 0; i < PCLK_POR_LINHA; i++) {
    ESPERA_BAIXO();
    ESPERA_ALTO();
  }
}

// Lê os 320 bytes crus de uma linha (só o nibble alto de cada byte). Usado no diagnóstico.
static inline void lerLinhaBruta(uint8_t *raw) {
  for (uint16_t i = 0; i < PCLK_POR_LINHA; i++) {
    ESPERA_BAIXO();
    raw[i] = (PIND & M_DADOS) >> 4;
    ESPERA_ALTO();
  }
}
