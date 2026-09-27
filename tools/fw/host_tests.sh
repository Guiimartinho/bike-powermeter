#!/usr/bin/env bash
# Testes de host dos módulos do modelo do zephyr_app (Unity + CTest, GCC do PC).
#
#   tools/fw/host_tests.sh               configura, compila e roda todos
#   tools/fw/host_tests.sh -R calib      só os conjuntos cujo nome casa com o filtro
#   tools/fw/host_tests.sh coverage      compila com --coverage, roda tudo e mede a
#                                        cobertura de linhas (falha abaixo de 95 %)
#
# Precisa de gcc, gcov, cmake e ninja no PATH (no Windows: MinGW-w64 em
# C:/ProgramData/mingw64/mingw64/bin, CMake 4.x e Ninja do pip). Não use o
# ambiente do NCS (tools/fw/ncs_env.sh) no mesmo shell: ele troca o cmake.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TESTS_DIR="$(cd "$HERE/../../zephyr_app/tests/host" && pwd)"
cd "$TESTS_DIR"

if [[ "${1:-}" == "coverage" ]]; then
    shift
    # a fresh count every time: stale .gcda files would add executions
    find build/host-cov -name '*.gcda' -delete 2>/dev/null || true
    cmake --preset host-cov > /dev/null
    cmake --build --preset host-cov
    ctest --preset host-cov "$@"
    python "$HERE/coverage.py" --build "$TESTS_DIR/build/host-cov" --min 95
    exit $?
fi

cmake --preset host-tests > /dev/null
cmake --build --preset host-tests
ctest --preset host-tests "$@"
