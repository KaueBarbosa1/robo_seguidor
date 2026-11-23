// Ponte H L298N: dois motores DC com PWM em ENA/ENB e direção em IN1..IN4.
#pragma once
#include <Arduino.h>

void motores_velocidade(int16_t esq, int16_t dir);
void motores_regular_velocidade();
bool motores_falha_encoder();
void motores_diagnostico(int16_t &esq, int16_t &dir, uint8_t &flags);
void motores_iniciar();
void motores_set(int16_t esq, int16_t dir);   // -255..255 (negativo = ré)
void motores_parar();
void motores_marcar_comando();                // chamar a cada comando válido (zera o watchdog)
void motores_watchdog();                      // para os motores se a Pi ficou muda
void motores_aplicar_seguranca();              // corta avanço imediatamente quando o sensor bloqueia
bool motores_parados();
