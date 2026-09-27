---
name: fw-threads
description: Trabalhar com threads, interrupções, pilhas, prioridades e concorrência no firmware Zephyr do Bike Power Meter - criar ou mudar serviços, mover trabalho para fora de ISR, dimensionar e medir pilhas com CONFIG_STACK_USAGE, proteger estado compartilhado, callbacks do BT e dos drivers. Use em qualquer mudança em zephyr_app/src/app/main.c, nos serviços de zephyr_app/src/svc/, nos drivers de zephyr_app/modules/pm_drivers, em callbacks de ISR ou do Bluetooth, ou quando algo roda em mais de uma thread.
---

# Threads, ISR e pilhas

## Mapa de execução

A mesma base do ciclocomputador (`docs/04-arquitetura-firmware.md`): um serviço por assunto, cada um com a sua thread, que dorme na sua caixa de entrada (uma `k_msgq` enchida por listeners do zbus) com espera máxima abaixo do watchdog. São **seis** serviços, iniciados por `zephyr_app/src/app/main.c`: `power`, `usb`, `sample`, `motion`, `compute` e `radio`. O `usb` só entra com `CONFIG_USB_DEVICE_STACK_NEXT` (ligado nos dois alvos).

| Contexto | Prioridade | Pilha | Acorda com | Pode |
|---|---|---|---|---|
| `sample` | 4 | 2048 B | caixa de entrada, 50 ms em contínuo; a mensagem do DRDY | excitação, ADS1220 pelo SPI, TMP117 e o monitor da referência; publica `chan_torque`, `chan_temp`, `chan_excitation` |
| `motion` | 5 | 2560 B | semáforo do trigger do BMA400, 20 ms | ler os eixos pela API de sensor, `crank_update()`, publicar `chan_crank` e `chan_motion_state`; em `Sleep`, armar o despertar |
| `compute` | 5 | 3072 B | caixa de entrada, 1 s | `rev_power`, `calib`, `health`, auto-zero; publica `chan_power`, `chan_vector`, `chan_health`, `chan_cmd_result` |
| `radio` | 6 | 3072 B | caixa de entrada, 1 s | subir ANT e BLE, CPS, BAS, o serviço de configuração, DFU |
| `usb` | 8 | 3072 B | caixa de entrada, 100 ms | pilha USB, a serial dos comandos (`pm_cmd` + `app_cmd`), `chan_vbus` |
| `power` | 9 | 3072 B | caixa de entrada, 1 s | `pm_fsm`, MAX17048 e os pinos do nPM1100 a cada 10 s, `chan_battery`, `chan_system_state`, System OFF e ship mode |
| thread do driver BMA400 | 4 | 1536 B | semáforo da ISR do INT1 | lê o estado da interrupção pelo SPI e chama o handler do trigger, que só dá o semáforo do `motion` |
| RX do BT | cooperativa | 4096 B (`CONFIG_BT_RX_STACK_SIZE`) | rádio | o control point do CPS e as escritas do serviço de configuração (`app_cmd_handle` e `pm_cmd_parse`): decidem, publicam e respondem |
| workqueue do mcumgr | do sistema | 4608 B | SMP | DFU; os hooks do projeto só consultam o estado e recusam |
| workqueue do sistema | do sistema | 2048 B | trabalhos | eventos do stack USB e do settings |
| ISR do DRDY (`drdy_isr`) | IRQ | pilha de ISR | borda do ADS1220 | só `app_inbox_put()` de uma mensagem `MSG_DRDY` |
| ISR do INT1 | IRQ | pilha de ISR | borda do BMA400 | só dá o semáforo da thread do driver |
| ISR da CDC ACM | IRQ | pilha de ISR | bytes do USB | só move bytes para o ring do `usb` |

Tudo é preemptivo, e o estado compartilhado é cópia: cada serviço lê os canais na sua thread e nunca chama outro serviço.

## Regras

1. **ISR não processa.** Copie e acorde uma thread. Proibido em ISR: `k_mutex_lock`, `snprintf` com float, trigonometria, log com float, chamadas ao modelo, SPI ou I2C.
2. **Um dono por dado.** Cada módulo do modelo tem uma thread dona: `crank_angle` é do `motion`; `rev_power`, `calib` e `health` são do `compute`; `pm_fsm` é do `power`; a configuração em vigor (`pm_settings`) é do `app` (`pm_store`) e chega aos outros como cópia por `chan_settings`. Outro serviço que precise mudar algo publica um comando (`chan_cmd`) ou um dado num canal.
3. **Listener do zbus** roda na thread de quem publica, com o canal travado: só copia para a caixa de entrada (`app_inbox_put()`, que nunca espera) e retorna. Mensagem maior que a união da caixa não entra: lê-se o canal na thread (`zbus_chan_read`).
4. **Callbacks** (BT RX, trigger do sensor, stack USB, hooks do mcumgr) só convertem e publicam; não dormem nem seguram mutex. O control point do CPS responde da thread RX do BT porque a especificação pede a indicação na mesma conexão, mas só depois de decidir com o estado que já tem em cópia.
5. **Espera única por thread**: `app_inbox_get()`, que alimenta o watchdog antes de esperar. Trabalho periódico sai do tempo máximo da espera, não de um `k_msleep` solto. O `motion` é a exceção: espera no semáforo do trigger, com tempo máximo de 20 ms, e alimenta o seu canal a cada volta.
6. **Prioridade**: `sample` acima de tudo, porque perder uma amostra desloca a integral da volta; o timeslicing só age entre iguais (`motion` e `compute` dividem a 5).
7. **Nada alocado depois do boot**: caixas, pilhas e buffers estáticos. As amostras da calibração (`collect` do `compute`) ficam num vetor estático dimensionado no Kconfig.
8. **Barramento SPI dividido**: o ADS1220 e o BMA400 dividem o `spi00` (`spi22` no DK) com chip selects próprios; o driver de SPI do Zephyr serializa as transações, e cada driver faz a sua com `spi_transceive_dt` de uma vez, sem segurar o barramento entre chamadas.

## Nova thread ou cadeia pesada

1. Defina pilha e prioridade como constantes no arquivo do serviço (`src/svc/<serviço>/`), com a medição no comentário, e a prioridade em `include/app/app_svc.h`.
2. Meça a pilha: build com `CONFIG_STACK_USAGE=y` numa pasta separada e some a cadeia mais funda.

   ```sh
   source tools/fw/ncs_env.sh
   cd zephyr_app
   python -m west build -p always -b nrf54lm20dk/nrf54lm20a/cpuapp -d build_su --no-sysbuild . -- -DCONFIG_STACK_USAGE=y
   find build_su -name "*.su" -exec cat {} + | sort -t$'\t' -k2 -rn | head -40
   ```

   Some os quadros da cadeia (o `.su` dá o quadro de cada função, inclusive das bibliotecas do Zephyr), acrescente cerca de 500 B para o `snprintf` com float do picolibc, 200 B para o empilhamento de exceção com FPU e cerca de 250 B por chamada de log. Deixe pelo menos 1 KB de folga.
3. Referência medida em 2026-09-27 (tabela em `docs/04-arquitetura-firmware.md#pilhas-e-prioridades`): `compute_thread` 336 B com as calibrações, `pm_cmd_parse` 360 B, `motion_thread` 248 B, `radio_thread` 264 B; `bt_enable` e a carga dos bonds cerca de 2 KB na `radio`; o fuel gauge e o `LOG_PANIC` do desligamento cerca de 1,5 KB na `power`.
4. Apague a pasta `build_su` no fim.
5. Na placa, confirme com `CONFIG_THREAD_ANALYZER=y` (imprime o uso real das pilhas).

## Falhas

- `CONFIG_MPU_STACK_GUARD=y`: estouro de pilha vira falha fatal na hora.
- `CONFIG_RESET_ON_FATAL_ERROR=y` (lib `fatal_error` do NCS): a falha é logada e o aparelho reinicia, em vez de travar.
- **Watchdog** (`task_wdt`, `docs/04-arquitetura-firmware.md`): cada thread de serviço tem um canal de 4 s (`app_wdt_add()` em `src/app/app_svc.c`), alimentado pelo `app_inbox_get()` antes de cada espera. Thread nova ganha o seu canal e sobe `CONFIG_TASK_WDT_CHANNELS`. Operação que pode passar de 4 s (a coleta de uma calibração, o `bt_enable` com bonds) fica quebrada em partes ou antes do canal.
- O `task_wdt` reinicia a placa depois de um breakpoint longo (o timer do kernel não pausa com a CPU parada). Para depurar passo a passo: `-DCONFIG_TASK_WDT=n`.
- O System OFF (`sys_poweroff()` no `$SLEEP`) só acontece depois de publicar `Sleep` e de o `motion` armar o despertar do BMA400; quem mexer na ordem tem de manter o despertar antes do desligamento, senão o pod só volta com o cabo.

## Antes de terminar

- Os três builds sem aviso e testes de host verdes (skills `fw-build` e `fw-testes`).
- Se mudou quem chama o quê, atualize as tabelas de serviços, canais e pilhas em `docs/04-arquitetura-firmware.md`.
