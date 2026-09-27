---
name: fw-threads
description: Trabalhar com threads, interrupções, pilhas, prioridades e concorrência no port Zephyr do GNSS Bike Computer - criar ou mudar threads, mover trabalho para fora de ISR, dimensionar e medir pilhas com CONFIG_STACK_USAGE, proteger estado compartilhado, callbacks do BT. Use em qualquer mudança em zephyr_app/src/app/main.c ou nas threads de zephyr_app/src/svc/, em callbacks de ISR ou do Bluetooth, ou quando algo roda em mais de uma thread.
---

# Threads, ISR e pilhas

## Mapa de execução

Desde 2026-09-19 (`docs/05-arquitetura-zephyr.md`): um serviço por assunto, cada um com a sua thread, que dorme na sua caixa de entrada (uma `k_msgq` enchida por listeners do zbus) com espera máxima de 1 s. São **oito** serviços, iniciados nesta ordem por `zephyr_app/src/app/main.c:48-57`: `storage`, `usb`, `power`, `sensors`, `gnss`, `radio`, `model` e `ui`. O `usb` só entra com `CONFIG_USB_DEVICE_STACK_NEXT` (ligado nos dois alvos nRF54LM20A).

| Contexto | Prioridade | Pilha | Acorda com | Pode |
|---|---|---|---|---|
| `sensors` | 4 | 2048 B | a cada 20 ms | ler sensores pela API do Zephyr, publicar `baro`, `imu`, `mag`, `ambient` |
| `model` | 5 | 4096 B | caixa de entrada, 1 s | escrever o modelo (é o único), Kalman, segmentos, zonas, máquina de modos, publicar `model_state` e `log_point` |
| `gnss` | 6 | 2048 B | caixa de entrada | seguir o modo e o desligamento |
| `radio` | 6 | 3072 B | caixa de entrada | subir ANT e BLE, atualizar o BAS |
| `ui` | 7 | 6144 B | caixa de entrada, timer do LVGL, 1 s | a única que chama o LVGL e as funções `ui_*`; luz e COM |
| `storage` | 8 | 3584 B | caixa de entrada | FatFs, log, segmentos, percursos |
| `usb` | 8 | 2048 B | caixa de entrada, 1 s | pilha USB, serial dos comandos (`cmd_parser`) e disco do ciclista no modo MSC |
| `power` | 9 | 3072 B | caixa de entrada, 1 s | máquina de sistema, desligamento |
| workqueue do modem | do sistema | 2048 B | bytes do receptor | driver GNSS; os callbacks do serviço só convertem e publicam |
| RX do BT | cooperativa | 3072 B | rádio | clientes BLE; os callbacks só publicam |
| entrada | 0 | 2048 B | teclas | o callback de `ui_input.c` só publica `input` |
| workqueue do sistema | do sistema | 2048 B | trabalhos | debounce das teclas; na V3, o VCOM serial da tela (tenta de novo em 5 ms se um quadro está saindo) |
| timer do EXTCOMIN | ISR | pilha de ISR | meio período do COM | só troca o pino |
| ISRs | IRQ | pilha de ISR | — | ficam nos drivers do Zephyr; só sinalizam |

O legacy era cooperativo (nada preemptava uma task no meio de uma estrutura); aqui tudo é preemptivo, e o estado compartilhado virou cópia.

## Regras

1. **ISR não processa.** Copie e acorde uma thread. Proibido em ISR: `k_mutex_lock`, `fs_*`, `snprintf` com float, trigonometria, log com float, chamadas ao modelo.
2. **Um dono por dado.** O modelo é escrito só pela thread `model`. Outro serviço que precise mudá-lo publica um comando (`app_command()`) ou um dado num canal; nada de chamar funções do modelo de outra thread.
3. **Listener do zbus** roda na thread de quem publica, com o canal travado: só copia para a caixa de entrada (`app_inbox_put()`, que nunca espera) e retorna. Mensagem maior que a união da caixa não entra: lê-se o canal na thread (`zbus_chan_read`).
4. **Callbacks** (BT RX, workqueue do modem, entrada) só convertem e publicam; não dormem nem seguram mutex.
5. **Espera única por thread**: `app_inbox_get()`, que alimenta o watchdog antes de esperar. Trabalho periódico sai do tempo máximo da espera, não de um `k_msleep` solto.
6. **Prioridade**: dados que chegam de fora acima da interface; o timeslicing só age entre iguais (`gnss` e `radio` dividem a 6).
7. **Nada alocado depois do boot**: caixas, pilhas e buffers estáticos; o retrato da tela (2,4 KB) fica em variável estática, nunca na pilha.

## Nova thread ou cadeia pesada

1. Defina pilha e prioridade como constantes no arquivo do serviço (`src/svc/<serviço>/`), com a medição no comentário, e a prioridade em `include/app/app_svc.h`.
2. Meça a pilha: build com `CONFIG_STACK_USAGE=y` numa pasta separada e some a cadeia mais funda.

   ```sh
   source tools/fw/ncs_env.sh
   cd zephyr_app
   python -m west build -p always -b nrf54lm20dk/nrf54lm20a/cpuapp -d build_su --no-sysbuild . -- -DCONFIG_STACK_USAGE=y
   find build_su -name "*.su" -exec cat {} + | sort -t$'\t' -k2 -rn | head -40
   ```

   Some os quadros da cadeia (o `.su` dá o quadro de cada função, inclusive das bibliotecas do Zephyr), acrescente ~100 B para o quadro de exceção com FPU e ~250 B por chamada de log. Deixe pelo menos 1 KB de folga.
3. Referência medida em 2026-09-19 (tabela em `docs/05-arquitetura-zephyr.md#pilhas`): Kalman na `model` ~2,8 KB (`measurement_update` sozinho tem 1.672 B), carga de segmentos na `storage` ~2,2 KB, `bt_enable` na `radio` ~1,5 KB, publicação no zbus ~0,4 KB.
4. Apague a pasta `build_su` no fim.
5. Na placa, confirme com `CONFIG_THREAD_ANALYZER=y` (imprime o uso real das pilhas).

## Falhas

- `CONFIG_MPU_STACK_GUARD=y`: estouro de pilha vira falha fatal na hora.
- `CONFIG_RESET_ON_FATAL_ERROR=y` (lib `fatal_error` do NCS): a falha é logada e o aparelho reinicia, em vez de travar.
- **Watchdog** (`task_wdt`, [docs/05](../../../docs/05-arquitetura-zephyr.md#watchdog)): cada thread de serviço tem um canal de 4 s (`app_wdt_add()` em `src/app/app_svc.c`), alimentado pelo `app_inbox_get()` antes de cada espera. Thread nova ganha o seu canal e sobe `CONFIG_TASK_WDT_CHANNELS`. Operação que pode passar de 4 s (carga de segmentos, formatação do SD) fica antes do canal ou é quebrada em partes.
- O `task_wdt` reinicia a placa depois de um breakpoint longo (o timer do kernel não pausa com a CPU parada). Para depurar passo a passo: `-DCONFIG_TASK_WDT=n`.

## Antes de terminar

- Build sem aviso novo e testes de host verdes (skills `fw-build` e `fw-testes`).
- Se mudou quem chama o quê, atualize as tabelas de threads, canais e pilhas e o fluxo de dados em `docs/05-arquitetura-zephyr.md`.
