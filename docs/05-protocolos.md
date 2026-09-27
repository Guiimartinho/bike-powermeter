# Protocolos

O módulo fala dois protocolos padrão e um serviço próprio. O ciclocomputador do projeto par implementa o lado cliente dos dois padrões e é o primeiro banco de teste.

**Nesta página:** [BLE Cycling Power](#ble-cycling-power) · [Serviço de configuração](#serviço-de-configuração) · [ANT+ Bicycle Power](#ant-bicycle-power) · [Atualização](#atualização) · [Porta serial](#porta-serial)

## BLE Cycling Power

Cycling Power Service 1.1 (UUID 0x1818), servidor escrito no projeto sobre o GATT do Zephyr, que traz só os UUIDs. Anúncio com o UUID do serviço, aparência de sensor de potência, nome `PM-xxxx` (os quatro últimos dígitos do endereço).

| Característica | UUID | Propriedades | Conteúdo |
|---|---|---|---|
| Cycling Power Measurement | 0x2A63 | notify, 1 Hz e a cada volta | flags; potência instantânea (int16, W); balanço (uint8, 1/2 %, "referência desconhecida" com um lado só); torque acumulado (uint16, 1/32 N·m, na fonte do pedivela); voltas do pedivela (uint16) e tempo do último evento (uint16, 1/1024 s); energia acumulada (uint16, kJ) |
| Cycling Power Feature | 0x2A65 | read | balanço, torque acumulado, voltas do pedivela, energia, compensação de offset, medição de um lado com estimativa do outro (bit de "sensor measurement context"), efetividade e suavidade pelo Vector, calibração por temperatura quando calibrada |
| Sensor Location | 0x2A5D | read | pedivela esquerdo (fase 1) |
| Cycling Power Control Point | 0x2A66 | write, indicate | comandos padrão: definir e ler o comprimento do pedivela, iniciar compensação de offset (o zero), pedir a localização, definir a localização, pedir a data de calibração de fábrica, mascarar o conteúdo da medição; resposta com código de resultado |
| Cycling Power Vector | 0x2A64 | notify, por volta, quando inscrito | voltas e tempo do último evento, ângulo do primeiro ponto, ângulos dos pontos mortos, e o vetor de torques instantâneos da volta (int16, 1/32 N·m), até 16 pontos por notificação |

Mais Device Information (0x180A: fabricante, modelo, série, versões de hardware e firmware) e Battery Service (0x180F). A lista de opcodes e o formato exato das respostas seguem o HTML da especificação ([bluetooth.com](https://www.bluetooth.com/specifications/specs/cycling-power-service-1-1/)), incluída a errata 23224.

## Serviço de configuração

Serviço GATT próprio (UUID de 128 bits do projeto), com o mesmo canal de comandos em texto que o ciclocomputador usa pelo NUS, para que o mesmo app e a mesma tela sirvam aos dois:

| Característica | Propriedades | Conteúdo |
|---|---|---|
| Comando | write | linha de texto `$CMD,arg,...` |
| Resposta | notify | linha de texto `$ACK,...` ou `$NAK,código` |
| Configuração | read, write | a estrutura de `pm_settings` em CBOR: comprimento do pedivela (mm), raio do sensor (mm), lado, zero, inclinação (µN·m/contagem), `T0` e `k1..k3`, taxa de amostragem, limites do auto-zero, nome, número ANT+ |
| Estado | notify, 1 Hz | flags de saúde, temperatura da ponte, código bruto, zero em uso, tensão da bateria |

Comandos: `$ZERO` (zero com critério de estabilidade), `$SLOPE,m_g,L_mm` (um ponto de inclinação; `$SLOPE,END` fecha o ajuste e devolve inclinação, resíduo e histerese), `$TEMP,BEGIN` e `$TEMP,POINT` (curva de temperatura), `$CFG,GET` e `$CFG,SET,...`, `$DFU`, `$SLEEP`, `$INFO`. Toda escrita de configuração é validada pelo modelo (`pm_settings`), gravada pelo subsistema settings do Zephyr e confirmada na resposta. O emparelhamento com o ciclocomputador escreve comprimento do pedivela e lado e dispara `$ZERO`.

## ANT+ Bicycle Power

Transmissor pelo perfil `ant_bpwr` do add-on `sdk-ant` (C:\ncs\sdk-ant), que implementa as páginas 1 (calibração), 16 (potência), 17 (torque na roda), 18 (torque no pedivela), 80 e 81 (fabricante e produto) e o callback de calibração; o exemplo `bpwr_tx` do add-on mostra o uso. O módulo alimenta o perfil com a potência, a cadência, o torque acumulado e o contador de eventos de `chan_power`, e responde ao pedido de calibração manual e ao auto-zero pela mesma rotina do BLE. O material do ANT+ é do add-on e não entra neste repositório; o build com `ANT=1` o encontra em `C:\ncs\sdk-ant`.

## Atualização

mcumgr SMP sobre BLE (grupo de imagem e de sistema), o mesmo transporte do ciclocomputador; e a recuperação serial do MCUboot sobre USB CDC ACM pelo conector magnético, para o cabo. A atualização é recusada pedalando e com bateria abaixo de 30 %.

## Porta serial

Com o cabo no conector, o módulo aparece no PC como porta serial (USB CDC ACM) e aceita os mesmos comandos de texto do serviço de configuração, mais `$LOG` para o log do sistema. Serve à bancada de calibração sem rádio.
