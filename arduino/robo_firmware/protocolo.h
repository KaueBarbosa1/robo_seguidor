// Protocolo serial Arduino <-> Raspberry Pi (8N1; 1 Mbaud com câmera, 115200 sem). PROVISÓRIO: a ligação definitiva
// entre as placas ainda será decidida.
// Espelho em motor/protocolo.py.
//
// Arduino -> Pi.  (imagem e status só são enviados com USAR_CAMERA 1; sensores só com USAR_CAMERA 0)
//   linha : 0xFF, idx (0..119), 80 bytes     cada byte = (pixel_par << 4) | pixel_impar
//   fim   : 0xFF, 0xFE                        fim do quadro
//   status: 0xFF, 0xFD, codigo                aviso (ver StatusCodigo)
//   sensores: 0xFF, 0xFC, dL, dH, eL, eH, rL, rH, flags (só sem câmera; 7 bytes de 7 bits)
//             distância (cm) = dL | dH<<7, valor 0x3FFF = sem leitura;
//             encoder esquerdo/direito = contadores de 14 bits que dão a volta (a Pi calcula a diferença)
//             flags bit 0 = avanço bloqueado; bit 1 = sensor sem leitura válida / falha;
//             bit 2 = obstaculo confirmado por leituras reais consecutivas (nao e bloqueio de boot).
//   servo: 0xFF, 0xFB, angL, angH, centroL, centroH, flags (5 bytes de 7 bits)
//          angulo nominal comandado, centro em us; nao mede posicao fisica.
//          flags bit3=inspecao, bit4=concluida e novamente no centro estabilizado.
//          Enviado em resposta a comandos V aceitos ou retorno por timeout.
//   inspecao: 0xFF, 0xFA, posicao, cmL, cmH, rodadaL, rodadaH.
//          posicao 0/1/2 = angulos nominais 45/90/135; cm=0x3FFF desconhecido.
//          Um resultado por posicao: menor de tres ecos validos; qualquer falha invalida.
//          Leituras direcionais nao atualizam distancia/frente/flags do pacote FC.
// Os bytes de pixel NUNCA valem 0xFF (o nível 15 é limitado a 14), então 0xFF só aparece como
// marcador. Isso permite ao Pi ressincronizar a cada linha e descartar linhas corrompidas.
//
// Pi -> Arduino (5 bytes fixos):
//   0xAA, cmd, a, b, chk       chk = cmd ^ a ^ b ^ 0x5A
//   cmd 'M': a = motor esquerdo, b = motor direito (int8; PWM = valor * 2, ou seja -254..+254)
//   cmd 'S': parada total (a e b ignorados)
//   cmd 'V': a=0 centro / a=1 varrer parado / a=2 inspecionar 45,90,135; b=offset do centro em unidades de 10 us.
//   cmd 'H': a=0 desligar / a=1 buzinar (max 1500 ms); b=0. Nao renova motores.
#pragma once
#include <stdint.h>

#define CMD_VELOCIDADE 'R' // int8 por roda: pulsos/s; S cancela e rearma falha
#define CMD_AVISO 'A' // a: 0 cancelar, 1 partida, 2 linha perdida; b=0
#define SYNC 0xFF
#define IDX_FIM_QUADRO 0xFE
#define IDX_STATUS 0xFD
#define IDX_SENSORES 0xFC
#define IDX_SERVO 0xFB // angulo L/H, centro_us L/H, flags (5 bytes de 7 bits)
#define IDX_INSPECAO 0xFA // posicao 0/1/2=45/90/135, distancia L/H, rodada L/H (5 bytes)
#define DIST_SEM_LEITURA 0x3FFF
#define SERVO_FLAG_VARREDURA 0x01
#define SERVO_FLAG_CENTRO_PRONTO 0x02
#define SERVO_FLAG_ATIVO 0x04
#define SERVO_FLAG_INSPECAO 0x08
#define SERVO_FLAG_CONCLUIDA 0x10

#define CMD_START 0xAA
#define CMD_MOTORES 'M'
#define CMD_PARAR 'S'
#define CMD_SERVO 'V' // a: 0=centro, 1=varrer, 2=inspecionar; b: ajuste do centro em 10 us
#define CMD_BUZINA 'H'
#define CMD_XOR 0x5A

enum StatusCodigo : uint8_t {
  ST_OK = 0,
  ST_SEM_I2C = 1,       // a câmera não respondeu no barramento I2C (SCCB)
  ST_ID_ERRADO = 2,     // respondeu, mas o ID não é de um OV7670
  ST_REG_FALHOU = 3,    // falha ao escrever a configuração
  ST_SEM_VSYNC = 4      // configurou, mas não chega sinal de quadro (VSYNC/PCLK/XCLK)
};
