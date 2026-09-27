# Firmware

Zephyr / nRF Connect SDK v3.3.0, mesma base do ciclocomputador: serviços com thread e caixa de entrada, eventos no zbus, máquinas no SMF, watchdog por serviço. Alvo: módulo MinewSemi ME54BS13 (nRF54LM20A); desenvolvimento no nRF54LM20 DK.

| Pasta | Conteúdo |
|---|---|
| `src/app`, `include/app` | inicialização, watchdog, configuração |
| `src/svc` | serviços: amostragem da ponte, cadência (IMU), cálculo por volta, rádio (BLE CPS e ANT+ BPWR), energia, USB |
| `src/model` | torque, potência, calibração e compensação de temperatura (lógica pura, testada no PC) |
| `src/rf` | servidor BLE Cycling Power, serviço de configuração do projeto, perfil ANT+ (fora do repositório) |
| `modules/pm_drivers` | drivers próprios: ADS1220 (o Zephyr não o traz) |
| `tests/host` | Unity + CTest, shims do Zephyr |
| `boards` | overlays do DK e a placa própria |

Ainda não há código: a estrutura foi criada em 2026-09-27.
