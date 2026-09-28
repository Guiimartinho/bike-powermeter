# Ambiente e build

O mesmo do ciclocomputador: NCS v3.3.0 em `C:\ncs`, scripts em `tools/fw/` (`fw.sh build`, `flash`, `recover`, `devices`, `size`), `ANT=1` para o add-on `sdk-ant`, testes de host por `tools/fw/host_tests.sh` (GCC do MinGW-w64 em `C:\ProgramData\mingw64`, Unity 2.6.1 por `FetchContent`, um executável por módulo do modelo em `zephyr_app/tests/host/build/host-tests/`). `bash tools/fw/host_tests.sh coverage` recompila em `build/host-cov` com `--coverage`, roda tudo e chama `tools/fw/coverage.py`, que junta os `.gcov` de todos os executáveis e falha se algum módulo de `zephyr_app/src/model/` ficar abaixo de 95 % das linhas. Nunca WSL.

## Build do firmware

| Tarefa | Comando (Git Bash, na raiz) |
|---|---|
| Build incremental / do zero para o nRF54LM20 DK (o alvo de desenvolvimento) | `bash tools/fw/fw.sh build` / `bash tools/fw/fw.sh build pristine` |
| Build com ANT+ (add-on `sdk-ant` em `C:\ncs\sdk-ant`, módulo `zephyr_app/modules/ant_ncs33_compat`) | `ANT=1 BUILD_DIR=zephyr_app/build_ant bash tools/fw/fw.sh build pristine` |
| Build para a placa própria do pod (`zephyr_app/boards/pm/pmboard`) | `BOARD=pmboard/nrf54l15/cpuapp BUILD_DIR=zephyr_app/build_custom bash tools/fw/fw.sh build` |
| Conferir o mapa de pinos contra o silício, contra a tabela de [02](02-hardware.md#pinos-do-módulo) e contra a lista de nós do esquemático | `python tools/fw/board_check.py` |
| Gravar no DK (apaga tudo / mantém settings) | `bash tools/fw/fw.sh flash` / `bash tools/fw/fw.sh flash keep` |
| Pilhas (`CONFIG_STACK_USAGE`, skill `fw-threads`) | `west build -d build_su ... -Dzephyr_app_CONFIG_STACK_USAGE=y` de dentro de `zephyr_app`, e somar os `.su` da cadeia mais funda |

**Referência de 2026-09-28**, medida em build do zero nos três alvos, com sysbuild e MCUboot, e com a mesma tabela de partições nos três devicetrees (slot de 659.312 B, bootloader de 60 KB):

| Alvo | FLASH da aplicação | RAM | MCUboot |
|---|---|---|---|
| `pmboard/nrf54l15/cpuapp` (o pod) | 256.872 B (38,96 %) | 108.548 B de **188 KB** (56,39 %) | 46.996 B de 60 KB (76,49 %) |
| `nrf54lm20dk/nrf54lm20a/cpuapp` | 290.312 B (44,03 %) | 119.404 B de 511 KB (22,82 %) | 53.324 B de 60 KB (86,79 %) |
| o mesmo, `ANT=1` | 325.592 B (49,38 %) | 124.068 B (23,71 %) | idem |

A RAM do pod é o número a vigiar: 188 KB contra os 511 do nRF54LM20A. **Zero avisos de compilador** nos três builds. Os que aparecem não são de código do projeto: com `ANT=1`, o símbolo depreciado `SOC_SERIES_NRF54LX` que o módulo de compatibilidade religa, e um `unused variable` dentro do próprio `ant_bpwr.c` do add-on; e na imagem do MCUboot do pod, `lto-wrapper.exe: warning: using serial compilation of 2 LTRANS jobs`, que é o compilador dizendo que não paralelizou a otimização de ligação. O CMake dá dois avisos esperados: `No SOURCES given to Zephyr library` para `drivers__adc` e `drivers__sensor`, porque os drivers dessas classes moram em `zephyr_app/modules/pm_drivers`, e a chave de desenvolvimento do MCUboot. Nada disso rodou em placa nem no DK: não há DK com as placas de avaliação ligadas ainda.
