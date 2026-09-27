# Testes de host

Mesmo esquema do ciclocomputador: `bash tools/fw/host_tests.sh` compila os módulos de `src/model` com o GCC do PC (MinGW-w64) e roda o Unity pelo CTest; `bash tools/fw/host_tests.sh coverage` compila com `--coverage` e chama `tools/fw/coverage.py`, que falha se qualquer módulo do modelo ficar abaixo de 95 % de linhas. Os módulos são C puro, sem shim de kernel: `shim/zephyr/` e `support/` ficam para o dia em que um precisar.

| Conjunto | Módulos | O que garante |
|---|---|---|
| `test_bridge_calc` | `bridge_calc` | código para torque com zero, inclinação e temperatura; saturação; validade |
| `test_crank_angle` | `crank_angle` | ω pelos cruzamentos do eixo tangencial, θ, volta no ponto baixo, repouso, saltos descartados |
| `test_rev_power` | `rev_power` | integração da volta, TE, PS, acumuladores e unidades do rádio |
| `test_calib` | `calib`, `bridge_calc` | zero com estabilidade, inclinação por mínimos quadrados com resíduo, ajuste de temperatura |
| `test_cps_encode` | `cps_encode` | os bytes do Cycling Power Service 1.1 |
| `test_pm_settings` | `pm_settings`, `bridge_calc` | limites, bloco versionado com CRC, chaves de texto |
| `test_health` | `health` | cada regra de saúde de `docs/06-medicao-e-calibracao.md` |
| `test_pm_fsm` | `pm_fsm` | cada transição da máquina do sistema e as recusadas |
| `test_pm_cmd` | `pm_cmd` | cada comando `$...`, cada `$NAK`, estouro de linha |

Um conjunto novo entra por `pm_add_test(...)` no `CMakeLists.txt`; o procedimento, o teste de mutação e o cppcheck estão na skill `fw-testes`.
