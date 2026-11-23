#!/usr/bin/env bash
# Só usa perfis existentes; não lê nem grava senhas.
set -Eeuo pipefail
export LC_ALL=C
SCRIPT=$(readlink -f -- "${BASH_SOURCE[0]}")
RAIZ=$(dirname -- "$(dirname -- "$SCRIPT")")
PYTHON=/usr/bin/python3

falhar() { printf 'ERRO: %s\n' "$*" >&2; exit 1; }
uuid_valido() { [[ $1 =~ ^[[:xdigit:]]{8}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{12}$ ]]; }
ativa() {
    [[ $(nmcli -g GENERAL.STATE device show "$1") == 100* ]] || return 1
    nmcli -g GENERAL.CON-UUID device show "$1"
}

restaurar() {
    local anterior=$1 interface=$2 tentativa
    for tentativa in 1 2 3; do
        if [[ $(ativa "$interface" 2>/dev/null || true) == "$anterior" ]]; then
            printf 'RESTAURACAO_OK uuid=%s interface=%s\n' "$anterior" "$interface" || true
            return 0
        fi
        printf 'RESTAURACAO_TENTATIVA=%s uuid=%s\n' "$tentativa" "$anterior" || true
        if nmcli --wait 15 connection up uuid "$anterior" ifname "$interface"; then
            if [[ $(ativa "$interface") == "$anterior" ]]; then
                printf 'RESTAURACAO_OK uuid=%s interface=%s\n' "$anterior" "$interface" || true
                return 0
            fi
        fi
        sleep 2
    done
    printf 'RESTAURACAO_FALHOU uuid=%s\n' "$anterior" >&2 || true
    return 1
}

# Retaguarda do systemd: executada mesmo se o worker não conseguir rodar o trap.
if [[ ${1:-} == --restaurar ]]; then
    [[ $# == 4 ]] || falhar 'Argumentos internos de restauracao invalidos.'
    if { : >>"$4"; } 2>/dev/null; then
        restaurar "$2" "$3" >>"$4" 2>&1
    else
        restaurar "$2" "$3"  # journal continua disponivel se o log falhar
    fi
    exit $?
fi

if [[ ${1:-} == --worker ]]; then
    [[ $# == 7 ]] || falhar 'Argumentos internos do worker invalidos.'
    anterior=$2 camera=$3 interface=$4 usuario=$5 saida=$6 unidade=$7
    exec >>"$saida/execucao.log" 2>&1
    filho=''
    limpar() {
        local resultado=$?
        trap - EXIT INT TERM
        if [[ -n $filho ]]; then
            kill -TERM "$filho" 2>/dev/null || true
            wait "$filho" 2>/dev/null || true
        fi
        printf 'WORKER_RC=%s\n' "$resultado" || true
        if ! restaurar "$anterior" "$interface"; then resultado=90; fi
        printf 'FIM=%s RC_FINAL=%s\n' "$(date -Is)" "$resultado"
        exit "$resultado"
    }
    trap limpar EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    printf 'INICIO=%s UNIDADE=%s\n' "$(date -Is)" "$unidade"
    printf 'Rede sera trocada em 8 segundos; somente motores nulos.\n'
    sleep 8
    [[ $(ativa "$interface") == "$anterior" ]] || falhar 'A rede ativa mudou antes do teste; abortando.'
    nmcli --wait 25 connection up uuid "$camera" ifname "$interface"
    [[ $(ativa "$interface") == "$camera" ]] || falhar 'Perfil da camera nao ficou ativo.'
    printf 'CAMERA_CONECTADA=%s\n' "$(date -Is)"
    # 30 s de ensaio; 40 s de limite externo + 5 s para encerramento forcado.
    timeout --signal=INT --kill-after=5s 40s \
        runuser -u "$usuario" -- env PYTHONDONTWRITEBYTECODE=1 \
        "$PYTHON" "$RAIZ/tools/testar_decisao_esp32.py" \
        --sem-janela --duracao 30 --ultrassom livre --csv "$saida/capturas.csv" &
    filho=$!
    resultado=0
    wait "$filho" || resultado=$?
    filho=''
    printf 'TESTE_RC=%s\n' "$resultado"
    exit "$resultado"
fi

modo=${1:---ajuda}
if [[ $modo == --ajuda || $modo == --help ]]; then
    printf 'Uso: bash %s --verificar|--iniciar UUID_CAMERA [INTERFACE]\n' "$SCRIPT"
    exit 0
fi
[[ $modo == --verificar || $modo == --iniciar ]] || falhar 'Use --verificar ou --iniciar.'
[[ $# == 2 || $# == 3 ]] || falhar 'Informe UUID_CAMERA e, opcionalmente, interface.'
camera=$2 interface=${3:-wlan0}
uuid_valido "$camera" || falhar 'Use o UUID do perfil, nao o nome da rede.'
[[ $interface =~ ^[[:alnum:]_.:-]+$ ]] || falhar 'Interface invalida.'
for comando in nmcli systemd-run timeout runuser readlink mktemp; do
    command -v "$comando" >/dev/null || falhar "Comando ausente: $comando"
done
[[ -x $PYTHON ]] || falhar 'Python do sistema indisponivel.'
"$PYTHON" -c 'import cv2, numpy' || falhar 'OpenCV/NumPy indisponiveis.'
[[ $(nmcli -g GENERAL.TYPE device show "$interface") == wifi ]] || falhar 'Interface nao e Wi-Fi.'
anterior=$(ativa "$interface" || true)
uuid_valido "$anterior" || falhar 'Nao existe perfil ativo para restaurar.'
[[ $(nmcli -g 802-11-wireless.ssid connection show uuid "$camera") == Carrinho-CAM ]] || falhar 'Perfil informado nao pertence a Carrinho-CAM.'
[[ $(nmcli -g 802-11-wireless.ssid connection show uuid "$anterior") != Carrinho-CAM ]] || falhar 'Comece conectado a rede domestica.'
printf 'INTERFACE=%s\nREDE_ANTERIOR_UUID=%s\nPERFIL_CAMERA_UUID=%s\n' "$interface" "$anterior" "$camera"
if [[ $modo == --verificar ]]; then
    printf 'VERIFICACAO_OK: nenhuma rede foi trocada.\n'
    exit 0
fi
usuario=$(id -un)
mkdir -p -- "$RAIZ/resultados_esp32_wifi"
saida=$(mktemp -d "$RAIZ/resultados_esp32_wifi/$(date +%Y%m%d_%H%M%S)_XXXXXX")
unidade=robo-esp32-cam-teste  # nome fixo impede dois ensaios simultaneos
log="$saida/execucao.log"
printf 'UNIDADE=%s\nREDE_ANTERIOR_UUID=%s\nPERFIL_CAMERA_UUID=%s\nINTERFACE=%s\n' \
    "$unidade" "$anterior" "$camera" "$interface" >"$log"
printf 'CSV=%s/capturas.csv\nLOG=%s\n' "$saida" "$log"
elevacao=()
if (( EUID != 0 )); then elevacao=(sudo); fi
"${elevacao[@]}" systemd-run --unit="$unidade" --collect --service-type=exec \
    --property=RuntimeMaxSec=150s --property=TimeoutStopSec=55s \
    --property=KillMode=control-group \
    --property="ExecStopPost=/usr/bin/bash \"$SCRIPT\" --restaurar $anterior $interface \"$log\"" \
    /usr/bin/bash "$SCRIPT" --worker "$anterior" "$camera" "$interface" "$usuario" "$saida" "$unidade"
printf 'AGENDADO=%s; o trabalho independe desta sessao.\n' "$unidade"
