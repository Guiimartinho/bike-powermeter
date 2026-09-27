# Ambiente e build

O mesmo do ciclocomputador: NCS v3.3.0 em `C:\ncs`, scripts em `tools/fw/` (`fw.sh build`, `flash`, `recover`, `devices`, `size`), `ANT=1` para o add-on `sdk-ant`, testes de host por `tools/fw/host_tests.sh` (GCC do MinGW-w64 em `C:\ProgramData\mingw64`, Unity 2.6.1 por `FetchContent`, um executável por módulo do modelo em `zephyr_app/tests/host/build/host-tests/`). `bash tools/fw/host_tests.sh coverage` recompila em `build/host-cov` com `--coverage`, roda tudo e chama `tools/fw/coverage.py`, que junta os `.gcov` de todos os executáveis e falha se algum módulo de `zephyr_app/src/model/` ficar abaixo de 95 % das linhas. Nunca WSL.

## Build do firmware

| Tarefa | Comando (Git Bash, na raiz) |
|---|---|
| Build incremental / do zero para o nRF54LM20 DK (o alvo de desenvolvimento) | `bash tools/fw/fw.sh build` / `bash tools/fw/fw.sh build pristine` |
| Build com ANT+ (add-on `sdk-ant` em `C:\ncs\sdk-ant`, módulo `zephyr_app/modules/ant_ncs33_compat`) | `ANT=1 BUILD_DIR=zephyr_app/build_ant bash tools/fw/fw.sh build pristine` |
| Gravar no DK (apaga tudo / mantém settings) | `bash tools/fw/fw.sh flash` / `bash tools/fw/fw.sh flash keep` |
| Pilhas (`CONFIG_STACK_USAGE`, skill `fw-threads`) | `west build -d build_su ... -Dzephyr_app_CONFIG_STACK_USAGE=y` de dentro de `zephyr_app`, e somar os `.su` da cadeia mais funda |

Referência de 2026-09-27, nRF54LM20 DK, sysbuild com MCUboot: aplicação com **290.276 B de FLASH** dos 921.456 B do slot e **119.404 B de RAM** dos 511 KB; MCUboot com 45.676 B de FLASH; com `ANT=1`, 325.556 B de FLASH e 124.068 B de RAM. **Zero avisos de compilador** nos dois builds (com `ANT=1`, o único aviso é o do símbolo depreciado `SOC_SERIES_NRF54LX` que o módulo de compatibilidade religa, e um `unused variable` dentro do próprio `ant_bpwr.c` do add-on, que não é do projeto). O CMake dá dois avisos esperados: `No SOURCES given to Zephyr library` para `drivers__adc` e `drivers__sensor`, porque os drivers dessas classes moram em `zephyr_app/modules/pm_drivers`, e a chave de desenvolvimento do MCUboot. Nada disso rodou em placa nem no DK: não há DK com as placas de avaliação ligadas ainda.
