#include "comandos.h"
#include "motores.h"
#include "protocolo.h"
#include "servo.h"
#include "sinalizacao.h"

// Máquina de estados: espera 0xAA, depois lê cmd, a, b, chk. Pacote com checksum errado é descartado
// (a Pi reenvia o comando 20 vezes por segundo, então um pacote perdido não importa).
static uint8_t g_estado = 0;
static uint8_t g_pkt[4];

void comandos_byte(uint8_t b) {
  if (g_estado == 0) {
    if (b == CMD_START) g_estado = 1;
    return;
  }
  g_pkt[g_estado - 1] = b;
  if (g_estado < 4) {
    g_estado++;
    return;
  }
  g_estado = 0;

  const uint8_t cmd = g_pkt[0], a = g_pkt[1], bb = g_pkt[2], chk = g_pkt[3];
  if (chk != (uint8_t)(cmd ^ a ^ bb ^ CMD_XOR)) return;

  if (cmd == CMD_AVISO && a <= 2 && bb == 0) {
    sinalizacao_aviso(a);
  } else if (cmd == CMD_VELOCIDADE) {
    motores_velocidade((int8_t)a, (int8_t)bb);
    motores_marcar_comando();
  } else if (cmd == CMD_MOTORES) {
    motores_set((int16_t)(int8_t)a * 2, (int16_t)(int8_t)bb * 2);
    motores_marcar_comando();
  } else if (cmd == CMD_PARAR) {
    motores_parar();
    motores_marcar_comando();
  } else if (cmd == CMD_SERVO && motores_parados()) {
    servo_comandar(a, static_cast<int8_t>(bb));
  } else if (cmd == CMD_BUZINA && a <= 1 && bb == 0) {
    sinalizacao_buzina(a == 1);
  }
}
