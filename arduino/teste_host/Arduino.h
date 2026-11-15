#pragma once
#include <stdint.h>
#include <stdio.h>
#include <deque>
#include <vector>
#define _BV(b) (1 << (b))
#define F_CPU 16000000UL
#define COM1A1 7
#define WGM11 1
#define WGM12 3
#define WGM13 4
#define CS11 1
extern volatile uint8_t TCCR1A, TCCR1B, SREG;
extern volatile uint16_t TCNT1, ICR1, OCR1A;
#define RXC0 7
#define UDRE0 5
#define U2X0 1
#define RXEN0 4
#define TXEN0 3
#define UCSZ01 2
#define UCSZ00 1
#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2
#define HIGH 1
#define LOW 0
#define RISING 3
#define A0 14
#define A1 15
#define A2 16
#define A3 17
#define F(x) x
typedef void (*isr_t)();
// relógio falso: cada leitura de tempo avança um pouco, como o tempo real do loop
extern uint32_t g_us;
inline uint32_t micros() { g_us += 4; return g_us; }
inline uint32_t millis() { g_us += 4; return g_us / 1000; }
inline void delayMicroseconds(unsigned n) { g_us += n; }
inline void delay(unsigned ms) { g_us += ms * 1000UL; }
// pinos
extern uint8_t g_pinDig[32]; extern uint8_t g_pwm[32]; extern isr_t g_isr[2];
extern uint32_t g_trigFallUs; extern uint32_t g_echoDistCm; extern bool g_echoAtivo;
void pinMode(uint8_t, uint8_t);
void digitalWrite(uint8_t, uint8_t);
int digitalRead(uint8_t);
void analogWrite(uint8_t, int);
inline int digitalPinToInterrupt(int p) { return p == 2 ? 0 : 1; }
void attachInterrupt(int n, isr_t f, int);
inline void noInterrupts() {}
inline void interrupts() {}
inline void cli() {}
inline void sei() {}
// UART falsa
extern std::deque<uint8_t> g_rx; extern std::vector<uint8_t> g_tx;
extern uint32_t g_uartProntaUs;
struct Reg { uint8_t v = 0; };
struct Udr { uint8_t operator=(uint8_t b) { g_tx.push_back(b); g_uartProntaUs = g_us + 87; return b; }
             operator uint8_t() { uint8_t b = g_rx.front(); g_rx.pop_front(); return b; } };
struct Ucsra { uint8_t v = 0; uint8_t operator=(uint8_t x) { v = x; return x; }
               operator uint8_t() const {
                 g_us += 2;
                 return (g_rx.empty() ? 0 : _BV(RXC0)) |
                        ((int32_t)(g_us - g_uartProntaUs) >= 0 ? _BV(UDRE0) : 0);
               } };
extern Udr UDR0; extern Ucsra UCSR0A; extern volatile uint8_t UCSR0B, UCSR0C, UBRR0H, UBRR0L, MCUSR;
#define WDTO_250MS 5
inline void wdt_enable(int) {} inline void wdt_disable() {} extern int g_wdt; inline void wdt_reset() { g_wdt++; }
