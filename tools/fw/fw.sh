#!/usr/bin/env bash
# Comandos do firmware Zephyr no Git Bash, com o mesmo fluxo dos .bat da raiz.
#
#   tools/fw/fw.sh build [pristine]   compila zephyr_app (sysbuild)
#   tools/fw/fw.sh flash [keep]       grava no DK pelo J-Link
#   tools/fw/fw.sh recover            desbloqueia um chip protegido (apaga tudo)
#   tools/fw/fw.sh devices            lista as placas conectadas
#   tools/fw/fw.sh size               memória por região e maiores símbolos de RAM/flash
#
# Variáveis: BUILD_DIR (padrão: zephyr_app/build), BOARD (padrão:
# nrf54lm20dk/nrf54lm20a/cpuapp, que é o alvo do projeto; o nRF52840 DK,
# que não é mais usado, ainda compila com BOARD=nrf52840dk/nrf52840),
# FAMILY (família do nrfutil, deduzida da BOARD: nrf52 ou nrf54l),
# NRF_SERIAL (número de série do J-Link) e as de tools/fw/ncs_env.sh
# (NCS_ROOT, NCS_VERSION, NCS_TOOLCHAIN).
# ANT=1 compila com o ANT: o add-on sdk-ant em SDK_ANT_DIR (padrão
# $NCS_ROOT/sdk-ant), zephyr_app/modules/ant_ncs33_compat e zephyr_app/ant.conf;
# ao trocar ANT, use pristine ou outra BUILD_DIR.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=tools/fw/ncs_env.sh
source "$ROOT/tools/fw/ncs_env.sh"

APP_DIR="$ROOT/zephyr_app"
BUILD_DIR="${BUILD_DIR:-$APP_DIR/build}"
# Um BUILD_DIR relativo vale a partir da pasta de quem chamou: o build roda
# dentro do zephyr_app e o west o resolveria a partir de lá.
case "$BUILD_DIR" in
    /*|[A-Za-z]:*) ;;
    *) BUILD_DIR="$PWD/$BUILD_DIR" ;;
esac
BOARD="${BOARD:-nrf54lm20dk/nrf54lm20a/cpuapp}"
case "$BOARD" in
    *nrf54l*) DEFAULT_FAMILY=nrf54l ;;
    *) DEFAULT_FAMILY=nrf52 ;;
esac
FAMILY="${FAMILY:-$DEFAULT_FAMILY}"
SDK_ANT_DIR="${SDK_ANT_DIR:-$NCS_ROOT/sdk-ant}"

select_probe() {
    if [ -n "${NRF_SERIAL:-}" ]; then
        echo "--serial-number $NRF_SERIAL"
    else
        echo "--traits jlink"
    fi
}

firmware_hex() {
    local hex
    for hex in "$BUILD_DIR/merged.hex" "$BUILD_DIR/zephyr_app/zephyr/zephyr.hex" "$BUILD_DIR/zephyr/zephyr.hex"; do
        if [ -f "$hex" ]; then
            echo "$hex"
            return 0
        fi
    done
    echo "fw.sh: firmware não encontrado em $BUILD_DIR; rode tools/fw/fw.sh build" >&2
    return 1
}

firmware_elf() {
    local elf
    for elf in "$BUILD_DIR/zephyr_app/zephyr/zephyr.elf" "$BUILD_DIR/zephyr/zephyr.elf"; do
        if [ -f "$elf" ]; then
            echo "$elf"
            return 0
        fi
    done
    echo "fw.sh: zephyr.elf não encontrado em $BUILD_DIR" >&2
    return 1
}

cmd="${1:-build}"
shift || true

case "$cmd" in
    build)
        pristine=auto
        if [ "${1:-}" = "pristine" ]; then
            pristine=always
        fi
        extra=()
        if [ "${ANT:-0}" = "1" ]; then
            if [ ! -f "$SDK_ANT_DIR/zephyr/module.yml" ]; then
                echo "fw.sh: sdk-ant não encontrado em $SDK_ANT_DIR (defina SDK_ANT_DIR)" >&2
                exit 1
            fi
            # O add-on e o módulo de compatibilidade com o NCS v3.3.0 entram como
            # módulos extras; ant.conf liga o ANT só na imagem do app.
            ZEPHYR_EXTRA_MODULES="$(cygpath -m "$SDK_ANT_DIR");$(cygpath -m "$APP_DIR/modules/ant_ncs33_compat")"
            export ZEPHYR_EXTRA_MODULES
            extra=(-Dzephyr_app_EXTRA_CONF_FILE=ant.conf)
        fi
        # A placa própria (gnssbike) mora em zephyr_app/boards/gnss/gnssbike;
        # o BOARD_ROOT é a pasta que contém "boards", e precisa chegar também
        # à imagem do MCUboot, que o sysbuild constrói à parte.
        board_root="$(cygpath -m "$APP_DIR")"
        # O west precisa rodar no drive do projeto (F:), não no do NCS (C:).
        cd "$APP_DIR"
        python -m west build -p "$pristine" -b "$BOARD" -d "$BUILD_DIR" --sysbuild "$APP_DIR"             -- "-DBOARD_ROOT=$board_root" "-Dmcuboot_BOARD_ROOT=$board_root" "${extra[@]}"
        ;;
    flash)
        erase=ERASE_ALL
        if [ "${1:-}" = "keep" ]; then
            erase=ERASE_RANGES_TOUCHED_BY_FIRMWARE
        fi
        hex="$(firmware_hex)"
        echo "Gravando $hex (apagamento: $erase)"
        # shellcheck disable=SC2046
        nrfutil device program $(select_probe) --family "$FAMILY" --firmware "$hex" \
            --options "chip_erase_mode=$erase,verify=VERIFY_READ,reset=RESET_SYSTEM"
        ;;
    recover)
        # shellcheck disable=SC2046
        nrfutil device recover $(select_probe) --family "$FAMILY"
        ;;
    devices)
        nrfutil device list
        ;;
    size)
        elf="$(firmware_elf)"
        # head fecha o pipe cedo; sem isto o SIGPIPE do sort aborta o script.
        set +o pipefail
        arm-zephyr-eabi-size -A "$elf" | grep -E "^(section|text|rodata|datas|bss|noinit)"
        echo "--- maiores símbolos de RAM (bytes) ---"
        arm-zephyr-eabi-nm --size-sort -S -t d "$elf" | awk '$3 ~ /[bBdD]/ {print $2+0, $4}' | sort -rn | head -20
        echo "--- maiores símbolos de flash (bytes) ---"
        arm-zephyr-eabi-nm --size-sort -S -t d "$elf" | awk '$3 ~ /[tTrR]/ {print $2+0, $4}' | sort -rn | head -20
        ;;
    *)
        sed -n '2,17p' "$0"
        exit 2
        ;;
esac
