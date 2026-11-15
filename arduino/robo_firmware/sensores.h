// Ultrassom HC-SR04 (sem bloquear o loop) e encoders das rodas.
#pragma once
#include <Arduino.h>

void sensores_iniciar();
void sensores_atualizar();        // chamar a cada volta do loop (máquina de estados, não espera)
uint16_t sensores_distancia_cm(); // DIST_SEM_LEITURA (0x3FFF) se não houve eco
uint16_t sensores_encoder_esq();  // contador de 14 bits (dá a volta em 16384)
uint16_t sensores_encoder_dir();
bool sensores_avanco_bloqueado();
bool sensores_falha();
bool sensores_obstaculo_confirmado();
