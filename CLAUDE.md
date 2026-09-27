# CLAUDE.md · Bike Power Meter

Contexto e regras para assistentes de IA neste repositório. Leia inteiro antes de mexer em qualquer coisa. Este projeto é o **par** do [GNSS Bike Computer](https://github.com/Guiimartinho/gnss-bike-computer) (`F:\1.Projects\32.gnss_bike_computer`): mesma base de firmware, mesma cadeia de CAD, mesmas regras. As skills em [`.claude/skills/`](.claude/skills/) trazem os procedimentos; a documentação está em [`docs/`](docs/README.md).

## 1. Missão

Projetar um medidor de potência de bicicleta aberto, em nível de produto: módulo colado no braço esquerdo do pedivela (fase 1), eixo de pedal (fase 2). Ponte de extensômetros de classe transdutor, conversor TI ADS1220, acelerômetro BMA400, TMP117, módulo MinewSemi ME54BS13 (nRF54LM20A), carga por nPM1100, conector magnético de carga, USB e SWD. Firmware em C sobre Zephyr / nRF Connect SDK v3.3.0, BLE Cycling Power e ANT+ Bicycle Power.

| Parte | Pasta | Papel |
|---|---|---|
| Firmware | `zephyr_app/` | Zephyr nativo, serviços com thread e caixa de entrada, zbus, a máquina do sistema em C puro no modelo (`pm_fsm`), watchdog por serviço |
| Hardware | `hardware_powermeter/` | lista fechada de componentes (01), CAD gerado por script (`cad/`), PDF (`esquematico/`, `placa/`), pod (`pod/`), datasheets locais (fora do git) |
| Ferramentas | `tools/` | `fw/` (build, gravação, testes de host) e `docs/` (Mermaid e links), copiadas do ciclocomputador |

O dono é um desenvolvedor brasileiro de eletrônica embarcada que quer investigação completa, componentes de nível produto com datasheet conferido, código nativo e verificação de verdade.

## 2. Regras que não se discutem

### Comunicação

- **Responda sempre em português do Brasil.** Código, identificadores e comentários em inglês.
- Não afirme nada sem verificar. Número de componente vem do datasheet, com o documento citado; o que não foi medido é dito como não medido. "Aproximado" não entra em documento do projeto.
- Em tarefas longas, mande um status curto de vez em quando.

### Firmware

- **Zephyr nativo:** devicetree, Kconfig, drivers e subsistemas do Zephyr/NCS. Driver próprio só quando o Zephyr não tem: ADS1220 e BMA400 (o `bosch,bma4xx` da árvore usa o mapa de registradores do BMA422, não o do BMA400: reconhece o chip ID com aviso e não o opera); TMP117 (`ti,tmp11x`) e MAX17048 (`maxim,max17048`) usam os da árvore.
- **ISR não processa:** copia para um buffer e acorda uma thread. **Sem alocação dinâmica depois do boot.** **Pilha medida** com `CONFIG_STACK_USAGE`, 1 KB de folga.
- **Lógica pura testada no PC** (`zephyr_app/tests/host`, Unity + CTest): cálculo de potência por volta, calibração, compensação de temperatura, codificação das características BLE. Teste que nunca falha não testa nada: mutação antes de dar por pronto.
- **Verificação antes de dizer que terminou:** build sem aviso (com `ANT=1`, só o do símbolo obsoleto), testes de host, cppcheck nos arquivos tocados e, se mexeu em docs, `tools/docs/*.py`.

### Commits

- **Commit de cada item assim que ele estiver pronto e verificado.** Push só com pedido do dono. Mensagens em **inglês**, Conventional Commits com escopo (`feat(svc): ...`, `fix(drivers): ...`, `docs(docs): ...`).
- **Branches:** trabalho na `develop`; a `main` só recebe merge quando o dono pedir.
- **Nunca atribua commit a IA:** sem `Co-Authored-By` de assistente, sem "Generated with", sem menção a Claude. O autor é a identidade git configurada (Luiz Guilherme Ito).
- Nunca faça commit de credenciais, de builds, de `hardware_powermeter/datasheets/` (ignorada) nem de **material do ANT+** (perfis, código sob a ANT+ Shared Source License, chave de rede): o repositório é público e o Adopter Agreement proíbe.

### Documentação

- Português do Brasil, direto, voz ativa; **diagramas sempre em Mermaid**; README no padrão industrial. Skill `docs-pm`.
- Quando o comportamento muda, a documentação e o `CHANGELOG.md` mudam junto.

### Ambiente

- **Nunca use WSL**, máquinas virtuais nem Docker. Um script que chama `bash` no Windows abre o WSL: chame as ferramentas direto ou o Git Bash pelo caminho completo.
- Não instale pacotes na máquina do dono sem perguntar. CI desligado: a verificação é local.

## 3. Comandos essenciais

Os mesmos do ciclocomputador, em Git Bash na raiz: `bash tools/fw/fw.sh build [pristine]`, `ANT=1 bash tools/fw/fw.sh build pristine`, `bash tools/fw/fw.sh flash|recover|devices|size`, `bash tools/fw/host_tests.sh` (e `coverage`), `BOARD=pmboard/nrf54lm20a/cpuapp BUILD_DIR=zephyr_app/build_custom bash tools/fw/fw.sh build` para a placa própria, `python tools/fw/board_check.py` (o mapa de pinos da placa contra o silício e contra a tabela de `docs/02`), `python tools/docs/mermaid_check.py`, `python tools/docs/links_check.py`. Equivalentes no `cmd`: `build.bat`, `flash.bat`, `recover.bat`, `serial.bat COMx`. O build do DK e o com `ANT=1` compilam com zero avisos desde 2026-09-27; os testes de host cobrem o modelo (`bash tools/fw/host_tests.sh coverage`).

## 4. Estado e próximos passos

- **2026-09-27:** estrutura criada; lista de componentes fechada por datasheet ([`hardware_powermeter/01-lista-de-componentes.md`](hardware_powermeter/01-lista-de-componentes.md)); os nove módulos do modelo (`zephyr_app/src/model`) escritos e testados no PC com 134 casos e 100 % das linhas ([`docs/07-status.md`](docs/07-status.md)); o firmware embarcado inteiro escrito e compilando com zero avisos no nRF54LM20 DK e com `ANT=1` (seis serviços, drivers próprios do ADS1220 e do BMA400, CPS, serviço de configuração, DFU por BLE, USB serial, ANT+ BPWR; pilhas medidas com `CONFIG_STACK_USAGE`), **nunca executado em placa nem no DK**; nenhuma placa; nada montado.
- **Decidido em 2026-09-27:** fase 1 no braço esquerdo, sensor ADS1220 (o ZSSC3224 é a alternativa com compensação no chip; o ADS124S06 a alternativa com driver na árvore), nPM1100 para carga e trilho de 3,0 V, excitação da ponte chaveada pela TPS22916 e ligada à referência do conversor (ratiométrico), conector magnético de 6 pinos, mesmo módulo de rádio do ciclocomputador, repositório novo apresentado como par do ciclocomputador.
- **Em aberto:** o pedivela (modelo, seção do braço, folga até o quadro), o medidor de referência para validar, a licença, o fornecedor do conector magnético, o AD4130-8 (datasheet inacessível desta máquina).
- **Roteiro:** bancada com massas → firmware e testes de host → prova de estrada até ±2 % → placa e pod pela cadeia de CAD e dry run → fase 2, eixo de pedal.

## 5. Armadilhas conhecidas

Valem todas as do `CLAUDE.md` do ciclocomputador (west de dentro do `zephyr_app`, `TOOLCHAIN_ROOT`, `sdk-ant` sobre o NCS v3.3.0 com o módulo de compatibilidade, overlay pelo nome da placa, pinos de clock do nRF54LM20A, build pristine para afirmar `.config`, cadeia de CAD na ordem certa com o Python do KiCad no `fill_zones.py`, modelos 3D conferidos por medida, regras de dry run que falham quando não acham o que medir). Específicas daqui:

| Armadilha | Como evitar |
|---|---|
| A ponte fica ligada enquanto o conversor converte: o ADS1220 integra a conversão inteira (SBAS501D 8.3.6) e não existe "janela da amostra" menor que ela; a ponte de 1 kΩ a 3 V drena 3 mA, e a de 350 Ω 8,6 mA | excitação pela TPS22916 ligada só em `Active`, `Calibrating` e nas rajadas de `Idle`, desligada no resto; a autonomia de 50 h não fecha com 1 kΩ, e as saídas (5 kΩ, duty-cycle com excitação chaveada, 200 mAh) estão em `docs/02` para o dono decidir |
| Medição não ratiométrica deriva com a tensão do buck | a excitação da ponte vai aos pinos REFP0/REFN0 do ADS1220; referência interna só para o sensor de temperatura |
| Extensômetro colado errado é o erro que nenhum firmware corrige | seguir o guia da Micro-Measurements (preparação, AE-10, proteção), medir linearidade e histerese na bancada antes de qualquer firmware |
| O driver `bosch,bma4xx` do Zephyr reconhece o chip ID `0x90` do BMA400 com um aviso, mas usa o mapa de registradores do BMA422 (dados em `0x12`, configuração em `0x40`); o BMA400 tem outro (`0x04`, `0x19`) | driver próprio em `zephyr_app/modules/pm_drivers/drivers/sensor` (`bosch,bma400`), da ficha BST-BMA400-DS000-14 |
| Pinos SWD expostos no conector magnético | TVS TPD4E05U06 e 100 Ω em série; nada sai do pod pelos pinos sem cabo |
| Material do ANT+ (`ant_bpwr`, páginas) fica em `C:\ncs\sdk-ant` | referenciar pelo build com `ANT=1`, nunca copiar para o repositório |
| Com os cabeçalhos dos perfis do `sdk-ant` (`ant_profiles/bpwr/ant_bpwr.h`), incluir `ant_init.h` dá tipos conflitantes com `ant_host_init.h`; e um `LOG_MODULE_REGISTER(ant_bpwr)` colide com o módulo de log do próprio perfil | inclua só `ant_key_manager.h`, `ant_parameters.h` e o perfil (o `ant_host_init.h` vem com ele e declara `ant_init()` e `ant_cb_register()`); nome de log próprio (`rf_ant`) |
| `enum pm_state` já existe no Zephyr (`zephyr/pm/state.h`) e quebra qualquer arquivo que inclua os dois | a máquina do sistema é `enum pm_sysstate` |
| A prioridade de `DEVICE_DT_INST_DEFINE` tem de ser um literal: uma expressão (`CONFIG_SPI_INIT_PRIORITY + 1`) vira nome de seção inválido e o link para com `Undefined initialization levels used` | um símbolo Kconfig próprio (`PM_ADC_ADS1220_INIT_PRIORITY`) |
| Um binding YAML com `description:` em texto simples contendo `: ` ou `[` é YAML inválido e o build para em `isn't valid YAML` | descrição entre aspas ou em bloco `\|` |
| Existindo `zephyr_app/sysbuild/mcuboot.overlay`, o sysbuild deixa de aplicar o `app.overlay` do próprio MCUboot, que é quem diz `zephyr,code-partition = &boot_partition`: o bootloader sai linkado no slot 0 (`FLASH_LOAD_OFFSET` 0x18000) e o build passa sem aviso | repita a linha no overlay e confira `CONFIG_FLASH_LOAD_OFFSET=0x0` em `build/mcuboot/zephyr/.config` a cada mudança de partição |
| O MCUboot com a recuperação serial pelo USB CDC ACM não cabe nos 64 KB do layout do fabricante (estourou 23.668 B) | layout do projeto: MCUboot em 96 KB e slots de 904 KB, nos três devicetrees (placa própria, overlay do DK, `sysbuild/mcuboot.overlay`), que têm de concordar |

## 6. Skills do projeto

| Skill | Use para |
|---|---|
| `fw-build` | ambiente, build, gravação (copiada do ciclocomputador; caminhos a adaptar) |
| `fw-testes` | testes de host, mutação, cppcheck |
| `fw-threads` | threads, ISR, pilhas |
| `docs-pm` | escrever e validar documentação |
| `commit-pm` | preparar e fazer commits |

## 7. Onde está cada coisa

| Assunto | Documento |
|---|---|
| Visão geral, decisão, fases | [README.md](README.md), [docs/01-visao-geral.md](docs/01-visao-geral.md) |
| Componentes fechados por datasheet | [hardware_powermeter/01-lista-de-componentes.md](hardware_powermeter/01-lista-de-componentes.md) |
| Hardware, ambiente, firmware, protocolos, medição, status | [docs/README.md](docs/README.md) |
| Histórico | [CHANGELOG.md](CHANGELOG.md) |
