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
//             bit 3 = modo 4 com calibracao ausente/invalida.
//             bit 4 = perfil experimental ativo (pode permitir movimento sem declarar calibracao).
//   servo: 0xFF, 0xFB, angL, angH, centroL, centroH, flags (5 bytes de 7 bits)
//          angulo nominal comandado, centro em us; nao mede posicao fisica.
//          flags bit3=inspecao, bit4=concluida e novamente no centro estabilizado.
//          Enviado em resposta a comandos V aceitos ou retorno por timeout.
//   inspecao: 0xFF, 0xFA, posicao, cmL, cmH, rodadaL, rodadaH.
//          posicao 0/1/2 = angulos nominais 45/90/135; cm=0x3FFF desconhecido.
//          Um resultado por posicao: menor de tres ecos validos; qualquer falha invalida.
//          Leituras direcionais nao atualizam distancia/frente/flags do pacote FC.
//   sonar: 0xFF, 0xF9, angL, angH, cmL, cmH, seqL, seqH (seis bytes de 7 bits).
//          Angulo comandado no disparo, cm=0x3FFF desconhecido, sequencia de 14 bits.
//          Servo em movimento; nao mede angulo fisico nem garante um eco por grau.
//          V modo 3 inicia/renova parado; status FB bit5 indica sonar ativo.
//          V modo 4 prioriza frente e aceita renovacao durante movimento; FB bit6 indica modo 4.
//          FC usa distancia frontal descontada por encoders nesse modo, nunca eco lateral.
// Os bytes de pixel NUNCA valem 0xFF (o nível 15 é limitado a 14), então 0xFF só aparece como
// marcador. Isso permite ao Pi ressincronizar a cada linha e descartar linhas corrompidas.
//
// Pi -> Arduino (5 bytes fixos):
//   0xAA, cmd, a, b, chk       chk = cmd ^ a ^ b ^ 0x5A
//   cmd 'M': a = motor esquerdo, b = motor direito (int8; PWM = valor * 2, ou seja -254..+254)
//   cmd 'S': parada total (a e b ignorados)
//   cmd 'V': a=0 centro / a=1 varrer parado / a=2 inspecionar 45,90,135; b=offset do centro em unidades de 10 us.
//   cmd 'H': legado, sem efeito (buzzer removido). Nao renova motores.
#pragma once
#include <stdint.h>

// U a=1: manual sem ultrassom, renovar em <400ms; a=0: parar e restaurar protecao. b=0.
// Nao renova watchdog dos motores. Confirmacao F8 bit6; boot e timeout restauram protecao.
#define CMD_MANUAL_SEM_ULTRASSOM 'U'
#define CMD_VELOCIDADE 'R' // int8 por roda: pulsos/s; S cancela e rearma falha
#define CMD_AVISO 'A' // a: 0 cancelar, 1 partida, 2 linha perdida; b=0
#define SYNC 0xFF
#define IDX_FIM_QUADRO 0xFE
#define IDX_STATUS 0xFD
#define IDX_SENSORES 0xFC
#define IDX_SERVO 0xFB // angulo L/H, centro_us L/H, flags (5 bytes de 7 bits)
#define IDX_INSPECAO 0xFA // posicao 0/1/2=45/90/135, distancia L/H, rodada L/H (5 bytes)
#define IDX_SONAR 0xF9 // angulo L/H, distancia L/H, sequencia L/H (6 bytes de 7 bits)
#define IDX_MOTORES 0xF8 // magnitudes PWM E L/H, D L/H, flags (5 bytes de 7 bits)
#define IDX_GUARDA_SONAR 0xF7 // um byte: motivos simultaneos da guarda frontal no modo4
#define GUARDA_PERFIL 0x01
#define GUARDA_SEM_FRENTE 0x02
#define GUARDA_VENCIDA 0x04
#define GUARDA_CONFIRMAR 0x08
#define GUARDA_AVANCO 0x10
#define GUARDA_DIVERGENCIA 0x20
#define GUARDA_DISTANCIA 0x40
// F8 flags: bits0/1 sinal negativo E/D; bit2 falha encoder; bit3 PI ativo;
// bit6 manual sem ultrassom; bits4/5 fase de reforco pendente/ativa E/D. Diagnostico, nao comando ou calibracao.
#define DIST_SEM_LEITURA 0x3FFF
#define SERVO_FLAG_VARREDURA 0x01
#define SERVO_FLAG_CENTRO_PRONTO 0x02
#define SERVO_FLAG_ATIVO 0x04
#define SERVO_FLAG_INSPECAO 0x08
#define SERVO_FLAG_CONCLUIDA 0x10
#define SERVO_FLAG_SONAR 0x20
#define SERVO_FLAG_SONAR_MOVIMENTO 0x40 // modo 4, nao significa que foi liberado/calibrado

#define CMD_START 0xAA
#define CMD_MOTORES 'M'
#define CMD_PARAR 'S'
// FC flags bits5/6: lateral esquerda/direita bloqueada; bit0 permanece frontal.
#define CMD_SERVO 'V' // a: 0=centro, 1=varrer, 2=inspecionar, 3=sonar, 4=sonar em movimento
#define CMD_BUZINA 'H'
#define CMD_XOR 0x5A

enum StatusCodigo : uint8_t {
  ST_OK = 0,
  ST_SEM_I2C = 1,       // a câmera não respondeu no barramento I2C (SCCB)
  ST_ID_ERRADO = 2,     // respondeu, mas o ID não é de um OV7670
  ST_REG_FALHOU = 3,    // falha ao escrever a configuração
  ST_SEM_VSYNC = 4      // configurou, mas não chega sinal de quadro (VSYNC/PCLK/XCLK)
};
