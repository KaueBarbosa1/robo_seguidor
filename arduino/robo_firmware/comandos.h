// Interpretador dos comandos binários vindos da Raspberry Pi (ver protocolo.h).
#pragma once
#include <Arduino.h>

void comandos_byte(uint8_t b);   // alimenta o parser, um byte por vez
