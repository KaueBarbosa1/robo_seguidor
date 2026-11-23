// Servo do ultrassom: independente da rotina bloqueante do teste isolado.
#pragma once
#include <Arduino.h>

void servo_iniciar();
void servo_atualizar();
bool servo_comandar(uint8_t modo, int8_t ajuste); // 0=centro, 1=varrer, 2=inspecao, 3=sonar, 4=movimento
bool servo_varrendo();
bool servo_frontal_pronto(); // centro comandado e prazo de estabilizacao cumprido
uint8_t servo_angulo_nominal(); // comando, nao medicao da posicao real
uint16_t servo_centro_us();
uint8_t servo_flags();
bool servo_consumir_status();
bool servo_em_inspecao();
bool servo_em_sonar();
bool servo_em_sonar_movimento();
bool servo_movimento_permitido();
void servo_configurar_marcha(int16_t esq, int16_t dir);
bool servo_medicao_frontal(); // orientacao no ultimo disparo, nao no fim do eco
bool servo_medicao_pronta();
void servo_iniciar_medicao(); // registra o angulo comandado ao disparar o ultrassom
void servo_registrar_leitura(uint16_t cm, bool valida);
bool servo_consumir_amostra(uint8_t &angulo, uint16_t &cm, uint16_t &id);
bool servo_consumir_sonar(uint8_t &angulo, uint16_t &cm, uint16_t &sequencia);
