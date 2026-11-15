// Servo do ultrassom: independente da rotina bloqueante do teste isolado.
#pragma once
#include <Arduino.h>

void servo_iniciar();
void servo_atualizar();
bool servo_comandar(uint8_t modo, int8_t ajuste); // 0=centro, 1=varrer, 2=inspecao parada; ajuste em 10 us
bool servo_varrendo();
bool servo_frontal_pronto(); // centro comandado e prazo de estabilizacao cumprido
uint8_t servo_angulo_nominal(); // comando, nao medicao da posicao real
uint16_t servo_centro_us();
uint8_t servo_flags();
bool servo_consumir_status();
bool servo_em_inspecao();
bool servo_medicao_pronta();
void servo_registrar_leitura(uint16_t cm, bool valida);
bool servo_consumir_amostra(uint8_t &angulo, uint16_t &cm, uint16_t &id);
