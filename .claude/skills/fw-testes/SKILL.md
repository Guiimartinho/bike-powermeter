---
name: fw-testes
description: Rodar e escrever testes de host (Unity + CTest, GCC do PC) dos módulos de lógica do port Zephyr do GNSS Bike Computer, usando o legacy stravaV10 como oráculo, fazer testes de mutação e rodar o cppcheck. Use ao mudar ou portar código em zephyr_app/src/model, no parser NMEA ou em qualquer cálculo, ao adicionar um conjunto de testes ou ao investigar uma falha de teste.
---

# Testes de host e análise estática

## Rodar

```sh
bash tools/fw/host_tests.sh             # configura, compila e roda todos
bash tools/fw/host_tests.sh -R power    # só os conjuntos que casam com o filtro
```

Por baixo, em `zephyr_app/tests/host/`: `cmake --preset host-tests`, `cmake --build --preset host-tests`, `ctest --preset host-tests`.

- Compilador: GCC do PC (MinGW-w64 15.2 em `C:\ProgramData\mingw64\mingw64\bin`), CMake 4.x e Ninja do pip. **Não** rode no mesmo shell em que fez `source tools/fw/ncs_env.sh`: o ambiente do NCS troca o `cmake` e o `PATH`.
- O Unity v2.6.1 vem por `FetchContent` com SHA-256 fixo (download único para `build/host-tests/_deps`).
- Um conjunto sozinho: `zephyr_app/tests/host/build/host-tests/test_power_zone.exe` mostra arquivo, linha e mensagem de cada falha.
- Reporte o número exato ("3 de 3 conjuntos, 20 casos"), nunca "os testes passam".

## Renderizador de telas

```sh
python tools/ui/render_screens.py      # compila o LVGL do NCS e a src/ui no PC, desenha e confere as telas
```

- Passa com `0 problems`: nenhum pixel colorido no tema preto e branco, nenhum texto fora da caixa, navegação e ações dos menus como o esperado. Reporte o número de quadros e os picos de heap do LVGL e de pilha que ele imprime.
- As imagens em `docs/telas/` não podem mudar sem motivo: depois de mexer no LVGL, no `lv_conf.h` ou no header de quantização (`memlcd_pixel.h`), `git status docs/telas` precisa mostrar só o que você quis mudar.
- Usa o mesmo GCC dos testes de host (shell limpo, sem o `ncs_env.sh`); o build fica em `build/ui`.
- A formatação dos números tem conjunto de host próprio (`test_ui_fmt`), com o oráculo `legacy_fmkstr` e `legacy_secjmkstr` em `support/legacy_ref.h`.

- `test_sys_fsm` compila o `lib/smf/smf.c` do Zephyr (`ZEPHYR_BASE`, padrão `C:/ncs/v3.3.0/zephyr`); sem o NCS, o conjunto é pulado com aviso.

## Como funciona

```mermaid
flowchart LR
    SRC["zephyr_app/src/model/*.c<br/>(código real do firmware)"] --> EXE["test_x.exe"]
    SHIM["tests/host/shim/zephyr/<br/>kernel.h · logging/log.h"] --> EXE
    SUP["tests/host/support/<br/>host_kernel.c · legacy_ref.h"] --> EXE
    TEST["tests/host/test_x.c<br/>(Unity)"] --> EXE
    EXE --> CTEST["ctest"]
```

- Os módulos de lógica dependem quase só de `<zephyr/logging/log.h>` e, alguns, de `k_mutex` e `k_uptime_get*`. Os shims em `tests/host/shim/` transformam o log em nada, fazem o mutex nunca bloquear e dão um relógio controlável (`host_uptime_set()`/`host_uptime_advance()` em `support/host_kernel.h`, ligado com `SUPPORT host_kernel.c`).
- Módulos que usam `fs_*`, BLE, SPI, I2C ou UART ainda não têm shim: para testá-los, crie o shim mínimo em `tests/host/shim/zephyr/...` ou separe a lógica pura do acesso ao hardware.
- As mesmas flags de aviso do firmware (`-Wall -Wextra -Wno-unused-parameter`) mais `-Werror`.

## Oráculo: o legacy

O port precisa reproduzir o comportamento do `legacy/`. Um teste de fidelidade:

1. Lê a função original em `legacy/source/...` e anota regras, limites e constantes no comentário do topo do teste, com `arquivo:linha`.
2. Quando a fórmula é curta, transcreve a função original em `tests/host/support/legacy_ref.h` (prefixo `legacy_`, com a origem no comentário) e compara o port com ela em várias entradas.
3. Usa pontos reais: Nancy (48.6921, 6.1844), onde foram gravados os traços de simulação do legacy (`tools/TDD/GPX_simu*.csv`).
4. Quando o port **diverge de propósito** do legacy, o teste documenta a diferença no nome e no comentário, e a diferença entra em `docs/06-algoritmos.md`.

## Escrever um conjunto

1. Crie `zephyr_app/tests/host/test_<módulo>.c` com `setUp`, `tearDown`, funções `static void test_<comportamento>(void)` e um `main` com `UNITY_BEGIN`, `RUN_TEST` e `UNITY_END`.
2. Registre em `zephyr_app/tests/host/CMakeLists.txt`: `gnss_add_test(test_<módulo> SOURCES model/<módulo>.c [SUPPORT host_kernel.c])`.
3. Nomeie cada teste pelo comportamento garantido, como frase: `test_power_outside_50_to_1950_watts_is_not_binned_but_moves_the_clock`.
4. Teste números concretos e bordas: limites de zona, primeira amostra, relógio parado, virada de `uint32_t`, entradas fora de faixa, divisão por zero.
5. Floats com `TEST_ASSERT_FLOAT_WITHIN(tolerância, esperado, obtido)`; justifique a tolerância no comentário quando não for óbvia.

## Testes de mutação

Um teste só vale se falhar quando o comportamento some:

1. Copie o arquivo original para o scratchpad.
2. Quebre o comportamento (mude um limite, inverta uma condição, apague uma linha).
3. Rode `bash tools/fw/host_tests.sh -R <conjunto>`: precisa falhar. Se passar, o teste está fraco; melhore o teste.
4. Restaure o arquivo e confirme que tudo volta a passar. Nunca deixe uma mutação no código: confira `git status` e `git diff` no fim.
5. **Automatizando por script**: no Windows, um `bash` chamado de Python ou do `cmd` é o `bash.exe` do `System32`, o lançador do WSL, que o projeto não usa (e tudo "morre" porque nada roda). Chame `cmake --build --preset host-tests` e `ctest --preset host-tests -R ...` direto em `zephyr_app/tests/host`, confira que o conjunto passa antes da primeira mutação e que o filtro achou algo, e ponha o horário do arquivo mutado no futuro (`os.utime`), porque o Ninja não recompila um arquivo com o mesmo horário do objeto.

## cppcheck

```sh
cppcheck --enable=warning,style,performance,portability --std=c11 --inline-suppr --quiet \
  --suppress=missingIncludeSystem --suppress=missingInclude --suppress=unusedFunction \
  -I zephyr_app/include zephyr_app/src
```

- Na interface (`src/ui`, `tests/ui`), passe o LVGL para o cppcheck entender `LV_FONT_DECLARE` e ignore os achados dentro dele: `-DLV_CONF_INCLUDE_SIMPLE=1 -I zephyr_app/src/ui -I zephyr_app/tests/ui -I C:/ncs/v3.3.0/modules/lib/gui/lvgl --suppress="*:C:/ncs/v3.3.0/modules/lib/gui/lvgl/*"`.
- `syntaxError` em `ble_*.c` vem das macros do Zephyr (`BT_GATT_*`) sem os headers: falso positivo. Nos serviços, os `#if DT_...` pedem `"-DDT_NODE_HAS_STATUS(n,s)=1" "-DDT_ALIAS(a)=a"` na linha do cppcheck.
- Achados reais conhecidos estão em `docs/11-qualidade-misra.md`. Corrija o que for seu; supressão só inline, `// cppcheck-suppress <id>`, com o motivo na linha de cima.

## Antes de dizer que passou

- Rode de novo depois da última edição; não confie em resultado antigo.
- Firmware também: `bash tools/fw/fw.sh build` sem aviso.
- Diga o que não foi testado: nada disto substitui teste na placa.
