#!/usr/bin/env bash
# Único ponto de entrada do pacote Pi; main preserva captura/serial/controle únicos.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x venv/bin/python ] || [ ! -f venv/perfil_robo.txt ]; then
 echo 'Prepare o perfil com deploy/preparar_raspberry.sh antes de iniciar.' >&2; exit 2
fi
perfil="$(cat venv/perfil_robo.txt)"
args=(main.py --fonte-imagem esp32 --camera-fps 10 --opencv-threads 1)
case "$perfil" in
 visao) args+=(--sem-voz --sem-bluetooth) ;;
 bluetooth) args+=(--sem-voz) ;;
 completo) ;;
 *) echo 'Registro de perfil inválido' >&2; exit 2 ;;
esac
while [ "$#" -gt 0 ]; do
 case "$1" in
  --rede) args+=(--rede); shift ;;
  --host) args+=(--rede-host "${2:?Informe o IP local da Raspberry}"); shift 2 ;;
  --benchmark) args+=(--benchmark); shift ;;
  --sem-arduino) args+=(--sem-arduino); shift ;;
  --help|-h) echo 'Uso: bash deploy/iniciar_raspberry.sh [--sem-arduino] [--rede --host IP_DA_RASPBERRY] [--benchmark]'; exit 0 ;;
  *) echo "Opção desconhecida: $1" >&2; exit 2 ;;
 esac
done
echo "Perfil $perfil; Pi sem banco/renderer/treino automático; controle parado no início."
exec venv/bin/python "${args[@]}"
