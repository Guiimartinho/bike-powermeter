#!/usr/bin/env bash
# Testes de host dos módulos de lógica do zephyr_app (Unity + CTest, GCC do PC).
#
#   tools/fw/host_tests.sh              configura, compila e roda todos
#   tools/fw/host_tests.sh -R segment   só os conjuntos cujo nome casa com o filtro
#
# Precisa de gcc, cmake e ninja no PATH (no Windows: MinGW-w64 em
# C:/ProgramData/mingw64/mingw64/bin, CMake 4.x e Ninja do pip). Não use o
# ambiente do NCS (tools/fw/ncs_env.sh) no mesmo shell: ele troca o cmake.
set -euo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../zephyr_app/tests/host" && pwd)"
cd "$TESTS_DIR"

cmake --preset host-tests > /dev/null
cmake --build --preset host-tests
ctest --preset host-tests "$@"
