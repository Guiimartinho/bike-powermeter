# Changelog

Formato do [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/); versões pelo [SemVer](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Corrigido

- A lista de componentes dizia que o `bosch,bma4xx` da árvore opera o BMA400; ele reconhece o chip ID `0x90` com um aviso e usa o mapa de registradores do BMA422, que é outro. A coluna passa a dizer "Não: driver próprio", como já diziam `docs/04` e o `CLAUDE.md` (2026-09-27).

- **Os eixos do acelerômetro estavam invertidos no firmware, e ninguém tinha como saber.** A orientação era suposição (`PM_IMU_AXIS_RADIAL` em X, `_TANGENTIAL` em Y) e não estava em documento nenhum, então nada podia confirmar e nada falharia se a placa saísse de outro jeito. `docs/02` passou a trazer o requisito eixo a eixo com a convenção da seção 8.2 da ficha; a medida contra o canto do pino 1 do footprint e a rotação do `U401` mostrou o contrário do suposto, e os três símbolos passam a radial = Y, tangencial = X e sinal do radial −1. A regra `IM1` do dry run da placa reprova enquanto os dois lados discordarem. Invertidos, o termo centrípeto entraria na cadência e a potência sairia errada sem nenhum sinal de erro (2026-09-27).
- **A atualização por BLE não funcionaria e a calibração era escrita por qualquer um.** O serviço SMP herdava o padrão do Zephyr, que com o gerenciador de segurança ligado exige emparelhamento **autenticado**: um pod sem tela nem teclado emparelha por Just Works e nunca chega a esse nível, então a característica seria impossível de escrever. E as características de comando e de configuração aceitavam escrita sem cifra nenhuma, de qualquer rádio ao alcance. As três passam a exigir ligação cifrada, que é o nível que o aparelho alcança (2026-09-27).
- `docs/05` descrevia o serviço de configuração sem dar os UUID, que existiam só no código: sem eles ninguém escreve o app. Os cinco estão na tabela, com a regra de formação e como o aparelho é achado (2026-09-27).
- A linha do SWD na tabela de pinos de `docs/02` dizia que o reset vai ao conector magnético junto com `SWDIO` e `SWDCLK`; o conector tem seis contatos e não leva o reset, que existe só no Tag-Connect, como o esquemático sempre mostrou (2026-09-27).
- Os `.bat` da raiz vinham do ciclocomputador com o nRF52840 DK como alvo padrão, que este projeto não tem, e sem o `tools/fw/ncs_env.bat` que eles chamam: passam ao nRF54LM20 DK, como o `fw.sh`, com o ambiente do `cmd` copiado; e as skills de build, testes, threads, documentação e commit descrevem este firmware, os seus três alvos e a regra dos 95 % de cobertura, em vez do port do stravaV10 (2026-09-27).
- O orçamento de consumo de `docs/02` contava a ponte ligada 15 % do tempo; o ADS1220 integra a conversão inteira, e a ponte de 1 kΩ fica ligada enquanto se mede: 3,9 mA pedalando, abaixo das 50 h do requisito, com as três saídas para o dono decidir (2026-09-27).

### Adicionado

- Hardware de ponta a ponta, gerado por script: o esquemático em 4 folhas (57 peças, 45 nós, ERC sem erro, netlist conferido pino a pino), a placa de 60 × 16 mm em 4 camadas (57 peças, 546 segmentos, 179 vias, **DRC com 0 erros**, 77 das 110 ligações fechadas) e o pod de 65,4 × 19,4 × 10,5 mm com 17,0 g estimados. PDF do esquemático, PDF das camadas, desenho de montagem, vistas 3D da placa e do pod, e STL da concha e da tampa (2026-09-27).
- Cadeia de CAD portada do ciclocomputador para `hardware_powermeter/cad/` e `pod/`, com as tabelas desta placa e três correções medidas no roteador (ordem das ligações a partir do pino mais próximo; pescoço dentro do campo de pads; isolação reservada pela trilha mais larga, que trocou 17 ligações por zero erro de DRC) (2026-09-27).
- Regra `ME7`: o land pattern do módulo de rádio comparado pad a pad com um desenho independente do mesmo módulo. **80 pads, desvio máximo 0,000 mm** — a primeira conferência independente de um footprint que a ficha não publica (2026-09-27).
- Regra `IM1`: os eixos do acelerômetro medidos na placa contra a seção 8.2 da ficha. O resultado **reprova**: o `X` do sensor fica tangencial e o `Y` radial, ao contrário do que `PM_IMU_AXIS_RADIAL` e `_TANGENTIAL` supõem ([`hardware_powermeter/04`](hardware_powermeter/04-placa.md#a-orientação-do-acelerômetro)) (2026-09-27).
- Regras `TX1` e `TX2` (`cad/sch_legivel.py`): a legibilidade do esquemático medida no PDF exportado, palavra por palavra. Achou 81 pares de texto sobrepostos; as correções do gerador (altura real do glifo, 2,43 mm e não 1,27; mais espaço entre peças vizinhas) levaram a 38 (2026-09-27).
- Doze regras de dry run do pod (`PD1` a `PD12`), que mudaram quatro medidas do desenho no mesmo dia: o teto subiu para 3,2 mm porque quem o fixa é o conector da célula, a célula encolheu para 23 mm por causa do rasgo dos fios da ponte, a aba da tampa afinou e o rasgo estreitou (2026-09-27).
- Documentos de hardware 02 a 08: esquemático, lista de nós, placa, materiais, conectores e pontos de teste, pod e o relatório de dry run (2026-09-27).

- O `tools/fw/board_check.py` passa a conferir também o **esquemático**: todo pino do módulo na tabela de `docs/02` está numa rede de `hardware_powermeter/cad/nets.py`, e vice-versa, e nenhum pino do módulo aparece em duas redes. É o que impede a placa de ser fabricada com uma pinagem e o firmware compilado com outra, que só a bancada acusaria. Os 19 pinos batem nos três lados: silício, documento e esquemático (2026-09-27).

- Firmware embarcado inteiro: base (`main`, zbus, watchdog, `pm_store`, `app_cmd`), drivers próprios do ADS1220 e do BMA400 em `modules/pm_drivers`, os seis serviços, o CPS e o serviço de configuração por BLE, a atualização por mcumgr, a porta serial USB, o ANT+ BPWR com `ANT=1` e o overlay do nRF54LM20 DK; compila com zero avisos, pilhas medidas com `CONFIG_STACK_USAGE`, nunca executado (2026-09-27).
- A recuperação serial do MCUboot pelo USB CDC ACM do conector magnético, sem botão (espera de 1 s a cada partida), com o MCUboot em 96 KB e os slots em 904 KB; e o `$SLEEP` como evento da máquina do sistema, testado no PC (2026-09-27).
- A placa própria do pod (`pmboard/nrf54lm20a/cpuapp`, `zephyr_app/boards/pm/pmboard`) com os pinos de `docs/02`, e `tools/fw/board_check.py`, que confere o devicetree contra o silício e contra a tabela de `docs/02` (2026-09-27).
- O comando `$SHIP` (ship mode do nPM1100) e a distinção dele do `$SLEEP` (System OFF com despertar pelo acelerômetro) (2026-09-27).
- Modelo de protocolo e de sistema em C puro (`cps_encode`, `pm_settings`, `pm_cmd`, `health`, `pm_fsm`, `pm_wire`) com 67 casos de teste de host, 100 % das linhas e cinco mutações mortas; o bloco de configuração passa a ser binário versionado com CRC-16 em vez de CBOR, e a máquina do sistema mora no modelo em vez do SMF; `docs/07-status.md` vira a matriz de estado do projeto (2026-09-27).
- Modelo de medição em C puro (`bridge_calc`, `crank_angle`, `rev_power`, `calib`) com 66 casos de teste de host, cobertura por linha medida pelo gcov (`tools/fw/coverage.py`, 100 % nos quatro) e sete mutações mortas (2026-09-27).
- Estrutura do repositório, espelhando o ciclocomputador, e a lista fechada de componentes com o número do datasheet de cada peça (2026-09-27).
