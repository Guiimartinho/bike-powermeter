# Changelog

Formato do [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/); versões pelo [SemVer](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Corrigido

- O orçamento de consumo de `docs/02` contava a ponte ligada 15 % do tempo; o ADS1220 integra a conversão inteira, e a ponte de 1 kΩ fica ligada enquanto se mede: 3,9 mA pedalando, abaixo das 50 h do requisito, com as três saídas para o dono decidir (2026-09-27).

### Adicionado

- Firmware embarcado inteiro: base (`main`, zbus, watchdog, `pm_store`, `app_cmd`), drivers próprios do ADS1220 e do BMA400 em `modules/pm_drivers`, os seis serviços, o CPS e o serviço de configuração por BLE, a atualização por mcumgr, a porta serial USB, o ANT+ BPWR com `ANT=1` e o overlay do nRF54LM20 DK; compila com zero avisos, pilhas medidas com `CONFIG_STACK_USAGE`, nunca executado (2026-09-27).
- A recuperação serial do MCUboot pelo USB CDC ACM do conector magnético, sem botão (espera de 1 s a cada partida), com o MCUboot em 96 KB e os slots em 904 KB; e o `$SLEEP` como evento da máquina do sistema, testado no PC (2026-09-27).
- A placa própria do pod (`pmboard/nrf54lm20a/cpuapp`, `zephyr_app/boards/pm/pmboard`) com os pinos de `docs/02`, e `tools/fw/board_check.py`, que confere o devicetree contra o silício e contra a tabela de `docs/02` (2026-09-27).
- O comando `$SHIP` (ship mode do nPM1100) e a distinção dele do `$SLEEP` (System OFF com despertar pelo acelerômetro) (2026-09-27).
- Modelo de protocolo e de sistema em C puro (`cps_encode`, `pm_settings`, `pm_cmd`, `health`, `pm_fsm`, `pm_wire`) com 67 casos de teste de host, 100 % das linhas e cinco mutações mortas; o bloco de configuração passa a ser binário versionado com CRC-16 em vez de CBOR, e a máquina do sistema mora no modelo em vez do SMF; `docs/07-status.md` vira a matriz de estado do projeto (2026-09-27).
- Modelo de medição em C puro (`bridge_calc`, `crank_angle`, `rev_power`, `calib`) com 66 casos de teste de host, cobertura por linha medida pelo gcov (`tools/fw/coverage.py`, 100 % nos quatro) e sete mutações mortas (2026-09-27).
- Estrutura do repositório, espelhando o ciclocomputador, e a lista fechada de componentes com o número do datasheet de cada peça (2026-09-27).
