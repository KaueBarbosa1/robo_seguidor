#!/usr/bin/env bash
# Instalação manual por perfil. Não altera rede/serviço/firmware nem move motores.
set -euo pipefail
cd "$(dirname "$0")/.."
perfil=completo
rede=0
while [ "$#" -gt 0 ]; do
 case "$1" in
  --perfil) perfil="${2:?Informe visao, bluetooth ou completo}"; shift 2 ;;
  --rede) rede=1; shift ;;
  --help|-h) echo 'Uso: bash deploy/preparar_raspberry.sh [--perfil visao|bluetooth|completo] [--rede]'; exit 0 ;;
  *) echo "Opção desconhecida: $1" >&2; exit 2 ;;
 esac
done
case "$perfil" in visao|bluetooth|completo) ;; *) echo 'Perfil inválido' >&2; exit 2 ;; esac
if [ "$(uname -s)" != Linux ] || ! grep -aq 'Raspberry Pi' /proc/device-tree/model 2>/dev/null; then
 echo 'Execute o instalador somente na Raspberry, após conferir sistema/alimentação.' >&2; exit 2
fi
python3 -m venv venv
venv/bin/python -m pip install -r requirements-pi-base.txt
if [ "$perfil" != visao ]; then venv/bin/python -m pip install -r requirements-pi-bluetooth.txt; fi
if [ "$perfil" = completo ]; then venv/bin/python -m pip install -r requirements-pi-voz.txt; fi
if [ "$rede" = 1 ]; then venv/bin/python -m pip install -r requirements-rede-pi.txt; fi
printf '%s\n' "$perfil" > venv/perfil_robo.txt
echo "Dependências do perfil $perfil preparadas. Valide a bancada antes de iniciar."
echo 'Nenhum serviço foi habilitado e nenhum firmware foi gravado.'
