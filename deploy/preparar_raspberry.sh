#!/usr/bin/env bash
# Somente instalação opt-in. Não habilita serviço, rede ou movimentação.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt -r requirements-rede-pi.txt
echo 'Dependências preparadas. Valide alimentação/comunicação antes de executar main.py.'
echo 'Nenhum serviço foi habilitado e nenhum firmware foi gravado.'
