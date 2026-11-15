#!/bin/bash
# Instala/remove o serviço que sobe o robô quando a Pi liga.
#   bash deploy/instalar_servico.sh            instala e ativa
#   bash deploy/instalar_servico.sh remover    desativa e apaga
# Rode como o SEU usuário (não com sudo): é um serviço de usuário; só o "linger" pede sudo.
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
ALVO="$HOME/.config/systemd/user"
if [ "$1" = "remover" ]; then
  systemctl --user disable --now robo.service 2>/dev/null || true
  rm -f "$ALVO/robo.service"
  systemctl --user daemon-reload
  echo "Serviço removido."
  exit 0
fi
if [ -x "$DIR/venv/bin/python" ]; then PY="$DIR/venv/bin/python"; else PY="$(command -v python3)"; echo "AVISO: venv não encontrado em $DIR/venv; usando $PY"; fi
mkdir -p "$ALVO"
sed -e "s#@DIR@#$DIR#g" -e "s#@PYTHON@#$PY#g" "$DIR/deploy/robo.service" > "$ALVO/robo.service"
systemctl --user daemon-reload
systemctl --user enable robo.service
sudo loginctl enable-linger "$USER"      # roda no boot mesmo sem ninguém logado
echo
echo "Instalado. Comandos úteis:"
echo "  systemctl --user start robo.service     # liga agora"
echo "  systemctl --user status robo.service    # estado"
echo "  journalctl --user -u robo.service -f    # log ao vivo"
echo "  systemctl --user stop robo.service      # desliga (use antes de rodar python main.py na mão)"
echo "  bash deploy/instalar_servico.sh remover"
