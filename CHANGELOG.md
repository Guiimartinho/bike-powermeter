# Changelog

Formato do [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/); versões pelo [SemVer](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Corrigido

- A orientação do acelerômetro na placa era suposição do firmware e não estava em documento nenhum. `docs/02` passa a trazer o requisito eixo a eixo, com a convenção de sinais medida na seção 8.2 da ficha do BMA400, e diz qual é o elo que ainda falta medir: se o `+X` do footprint é o `+X` do encapsulamento. Um palpite errado aqui troca radial por tangencial e a potência sai errada sem sinal de erro (2026-09-27).
- **A atualização por BLE não funcionaria e a calibração era escrita por qualquer um.** O serviço SMP herdava o padrão do Zephyr, que com o gerenciador de segurança ligado exige emparelhamento **autenticado**: um pod sem tela nem teclado emparelha por Just Works e nunca chega a esse nível, então a característica seria impossível de escrever. E as características de comando e de configuração aceitavam escrita sem cifra nenhuma, de qualquer rádio ao alcance. As três passam a exigir ligação cifrada, que é o nível que o aparelho alcança (2026-09-27).
- `docs/05` descrevia o serviço de configuração sem dar os UUID, que existiam só no código: sem eles ninguém escreve o app. Os cinco estão na tabela, com a regra de formação e como o aparelho é achado (2026-09-27).
- A linha do SWD na tabela de pinos de `docs/02` dizia que o reset vai ao conector magnético junto com `SWDIO` e `SWDCLK`; o conector tem seis contatos e não leva o reset, que existe só no Tag-Connect, como o esquemático sempre mostrou (2026-09-27).
- Os `.bat` da raiz vinham do ciclocomputador com o nRF52840 DK como alvo padrão, que este projeto não tem, e sem o `tools/fw/ncs_env.bat` que eles chamam: passam ao nRF54LM20 DK, como o `fw.sh`, com o ambiente do `cmd` copiado; e as skills de build, testes, threads, documentação e commit descrevem este firmware, os seus três alvos e a regra dos 95 % de cobertura, em vez do port do stravaV10 (2026-09-27).
- O orçamento de consumo de `docs/02` contava a ponte ligada 15 % do tempo; o ADS1220 integra a conversão inteira, e a ponte de 1 kΩ fica ligada enquanto se mede: 3,9 mA pedalando, abaixo das 50 h do requisito, com as três saídas para o dono decidir (2026-09-27).

### Adicionado

- O `tools/fw/board_check.py` passa a conferir também o **esquemático**: todo pino do módulo na tabela de `docs/02` está numa rede de `hardware_powermeter/cad/nets.py`, e vice-versa, e nenhum pino do módulo aparece em duas redes. É o que impede a placa de ser fabricada com uma pinagem e o firmware compilado com outra, que só a bancada acusaria. Os 19 pinos batem nos três lados: silício, documento e esquemático (2026-09-27).

- Firmware embarcado inteiro: base (`main`, zbus, watchdog, `pm_store`, `app_cmd`), drivers próprios do ADS1220 e do BMA400 em `modules/pm_drivers`, os seis serviços, o CPS e o serviço de configuração por BLE, a atualização por mcumgr, a porta serial USB, o ANT+ BPWR com `ANT=1` e o overlay do nRF54LM20 DK; compila com zero avisos, pilhas medidas com `CONFIG_STACK_USAGE`, nunca executado (2026-09-27).
- A recuperação serial do MCUboot pelo USB CDC ACM do conector magnético, sem botão (espera de 1 s a cada partida), com o MCUboot em 96 KB e os slots em 904 KB; e o `$SLEEP` como evento da máquina do sistema, testado no PC (2026-09-27).
- A placa própria do pod (`pmboard/nrf54lm20a/cpuapp`, `zephyr_app/boards/pm/pmboard`) com os pinos de `docs/02`, e `tools/fw/board_check.py`, que confere o devicetree contra o silício e contra a tabela de `docs/02` (2026-09-27).
- O comando `$SHIP` (ship mode do nPM1100) e a distinção dele do `$SLEEP` (System OFF com despertar pelo acelerômetro) (2026-09-27).
- Modelo de protocolo e de sistema em C puro (`cps_encode`, `pm_settings`, `pm_cmd`, `health`, `pm_fsm`, `pm_wire`) com 67 casos de teste de host, 100 % das linhas e cinco mutações mortas; o bloco de configuração passa a ser binário versionado com CRC-16 em vez de CBOR, e a máquina do sistema mora no modelo em vez do SMF; `docs/07-status.md` vira a matriz de estado do projeto (2026-09-27).
- Modelo de medição em C puro (`bridge_calc`, `crank_angle`, `rev_power`, `calib`) com 66 casos de teste de host, cobertura por linha medida pelo gcov (`tools/fw/coverage.py`, 100 % nos quatro) e sete mutações mortas (2026-09-27).
- Estrutura do repositório, espelhando o ciclocomputador, e a lista fechada de componentes com o número do datasheet de cada peça (2026-09-27).
