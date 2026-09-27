# shellcheck shell=bash
# Ambiente do nRF Connect SDK para o Git Bash.
#
#   source tools/fw/ncs_env.sh
#
# Variáveis opcionais (defina antes do source):
#   NCS_ROOT       pasta de instalação do NCS           (padrão: C:/ncs)
#   NCS_VERSION    versão do SDK                          (padrão: v3.3.0)
#   NCS_TOOLCHAIN  id do toolchain em NCS_ROOT/toolchains (padrão: lido do toolchains.json)
#
# Reproduz o environment.json do toolchain: PATH, PYTHONPATH, NRFUTIL_HOME,
# ZEPHYR_TOOLCHAIN_VARIANT e ZEPHYR_SDK_INSTALL_DIR, mais ZEPHYR_BASE.
#
# Não exporte TOOLCHAIN_ROOT: o Zephyr lê essa variável como raiz das
# definições de toolchain (cmake/toolchain/...) e o build quebra.

NCS_ROOT="${NCS_ROOT:-C:/ncs}"
NCS_VERSION="${NCS_VERSION:-v3.3.0}"

if [ -z "${NCS_TOOLCHAIN:-}" ] && [ -f "$NCS_ROOT/toolchains/toolchains.json" ]; then
    NCS_TOOLCHAIN="$(python -c '
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
for entry in data if isinstance(data, list) else [data]:
    for toolchain in entry.get("toolchains", []):
        if sys.argv[2] in toolchain.get("ncs_versions", []):
            print(toolchain["identifier"]["bundle_id"])
            sys.exit(0)
' "$NCS_ROOT/toolchains/toolchains.json" "$NCS_VERSION" 2>/dev/null)"
fi

if [ -z "${NCS_TOOLCHAIN:-}" ]; then
    echo "ncs_env: toolchain do NCS $NCS_VERSION não encontrado em $NCS_ROOT/toolchains (defina NCS_TOOLCHAIN)" >&2
    return 1 2>/dev/null || exit 1
fi

_ncs_tc="$(cygpath -m "$NCS_ROOT/toolchains/$NCS_TOOLCHAIN")"
_ncs_tc_unix="$(cygpath -u "$_ncs_tc")"

if [ ! -x "$_ncs_tc_unix/opt/bin/python.exe" ]; then
    echo "ncs_env: $_ncs_tc não parece um toolchain do NCS (falta opt/bin/python.exe)" >&2
    return 1 2>/dev/null || exit 1
fi
if [ ! -f "$NCS_ROOT/$NCS_VERSION/zephyr/VERSION" ]; then
    echo "ncs_env: SDK não encontrado em $NCS_ROOT/$NCS_VERSION" >&2
    return 1 2>/dev/null || exit 1
fi

export NCS_ROOT NCS_VERSION NCS_TOOLCHAIN
export NCS_TOOLCHAIN_DIR="$_ncs_tc"
export PATH="$_ncs_tc_unix:$_ncs_tc_unix/mingw64/bin:$_ncs_tc_unix/bin:$_ncs_tc_unix/opt/bin:$_ncs_tc_unix/opt/bin/Scripts:$_ncs_tc_unix/opt/nanopb/generator-bin:$_ncs_tc_unix/nrfutil/bin:$_ncs_tc_unix/opt/zephyr-sdk/arm-zephyr-eabi/bin:$PATH"
export PYTHONPATH="$_ncs_tc/opt/bin;$_ncs_tc/opt/bin/Lib;$_ncs_tc/opt/bin/Lib/site-packages"
export NRFUTIL_HOME="$_ncs_tc/nrfutil/home"
export ZEPHYR_TOOLCHAIN_VARIANT=zephyr
export ZEPHYR_SDK_INSTALL_DIR="$_ncs_tc/opt/zephyr-sdk"
ZEPHYR_BASE="$(cygpath -m "$NCS_ROOT/$NCS_VERSION/zephyr")"
export ZEPHYR_BASE

unset _ncs_tc _ncs_tc_unix
