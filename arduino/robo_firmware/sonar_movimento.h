#pragma once
#include <Arduino.h>

void sonar_movimento_reiniciar();
void sonar_movimento_herdar_frente(uint16_t cm, uint32_t instante, bool bloqueada, bool obstaculo);
bool sonar_movimento_calibrado();
bool sonar_movimento_configurado();
bool sonar_movimento_experimental();
bool sonar_movimento_em_manobra();
void sonar_movimento_marcha(bool manobra);
void sonar_movimento_disparar(bool frontal);
void sonar_movimento_registrar(uint8_t angulo, uint16_t cm, bool valida);
bool sonar_movimento_falha();
bool sonar_movimento_bloqueado();
uint8_t sonar_movimento_bloqueios();
bool sonar_movimento_revisitar_frente();
bool sonar_movimento_lateral_esq();
bool sonar_movimento_lateral_dir();
bool sonar_movimento_permitido(int16_t esq, int16_t dir);
bool sonar_movimento_obstaculo();
uint16_t sonar_movimento_distancia_cm();
