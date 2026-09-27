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

Serviço GATT próprio, com o mesmo canal de comandos em texto que o ciclocomputador usa pelo NUS, para que o mesmo app e a mesma tela sirvam aos dois. Os UUID são de 128 bits, deste projeto, e seguem `7d1f000N-4c8e-4a3b-9e2f-5b6a7c8d9e01`, com `N` de 1 a 5 (`zephyr_app/src/rf/ble_cfg.c`). São estes os números que o app procura:

| Característica | UUID | Propriedades | Conteúdo |
|---|---|---|---|
| (o serviço) | `7d1f0001-4c8e-4a3b-9e2f-5b6a7c8d9e01` | — | o serviço de configuração |
| Comando | `7d1f0002-4c8e-4a3b-9e2f-5b6a7c8d9e01` | write | linha de texto `$CMD,arg,...` |
| Resposta | `7d1f0003-4c8e-4a3b-9e2f-5b6a7c8d9e01` | notify | linha de texto `$ACK[,carga]` ou `$NAK,código,nome` (`pm_cmd`) |
| Configuração | `7d1f0004-4c8e-4a3b-9e2f-5b6a7c8d9e01` | read, write | o bloco de 60 bytes de `pm_settings`: versão (uint16), comprimento do pedivela (0,5 mm), raio do sensor (mm), lado (5 esquerdo, 6 direito), sinal do eixo tangencial, zero, inclinação (µN·m/contagem), `T0` e `k1..k3` (float IEEE 754), taxa de amostragem, auto-zero e o seu passo, número ANT+, data de calibração, nome (12 bytes) e CRC-16/CCITT-FALSE; tudo little-endian, campo a campo, sem CBOR (o mesmo bloco vai ao subsistema settings do Zephyr e os testes de host o fixam byte a byte). Um bloco de outra versão ou com CRC errado é recusado e nada muda |
| Estado | `7d1f0005-4c8e-4a3b-9e2f-5b6a7c8d9e01` | notify, 1 Hz | flags de saúde, temperatura da ponte, código bruto, zero em uso, tensão da bateria |

O aparelho anuncia como `PM-XXXX`, com os dois últimos bytes do endereço BLE, e traz no anúncio o Cycling Power Service e o de bateria; o de configuração é achado depois da conexão, pela descoberta de serviços.

**O que muda o medidor exige vínculo.** As características de comando e de configuração são as duas formas de mudar o aparelho de fora: zerar, reescrever a inclinação, mandar para o modo de guarda, pedir atualização. As duas exigem **ligação cifrada** (`BT_GATT_PERM_*_ENCRYPT`), ou seja, emparelhamento com vínculo antes do primeiro uso; sem isso, qualquer rádio ao alcance reescreve a calibração de um ciclista. O app recebe "insufficient encryption" enquanto não se vincula, que é o fluxo normal. As duas notificações ficam abertas: só informam, e a resposta só existe depois de um comando que já é protegido. O ponto de controle do Cycling Power segue o perfil, sem exigência própria, para não quebrar a compatibilidade com painéis de guidão.

A exigência é **cifra, não autenticação**: o pod não tem tela nem teclado, então a capacidade de entrada e saída é "NoInputNoOutput", o emparelhamento é sempre Just Works e o nível de segurança para no 2. Uma característica pedindo nível 3 nunca seria escrita por um celular: ficaria morta, não segura.

Comandos (`pm_cmd`, nome sem distinção de maiúsculas, linha de até 63 caracteres terminada por CR, LF ou os dois): `$ZERO` (zero com critério de estabilidade), `$SLOPE,m_g,L_mm[,DOWN]` (um ponto de inclinação com a massa em gramas e o braço em mm; `DOWN` marca o ponto na descida da carga, para a histerese; `$SLOPE,END` fecha o ajuste e devolve inclinação, resíduo e histerese), `$TEMP,BEGIN`, `$TEMP,POINT` e `$TEMP,END` (curva de temperatura), `$CFG,GET[,chave]`, `$CFG,SET,chave,valor` e `$CFG,SAVE`, `$DFU`, `$SLEEP` (System OFF; o pedivela acorda o módulo pelo INT1 do BMA400), `$SHIP` (ship mode do nPM1100; só o cabo acorda; recusado com o cabo posto), `$INFO`, `$LOG` (só na serial). As chaves de `$CFG` são `crank` (mm, em passos de 0,5), `radius` (mm), `side` (`L` ou `R`), `sign` (`1` ou `-1`), `zero`, `slope`, `t0`, `k1`, `k2`, `k3`, `tempcal`, `rate` (20, 45, 90, 175, 330, 600 ou 1000 SPS), `autozero`, `azstep`, `ant`, `caldate` (`AAAA-MM-DD` ou `0`) e `name`. Toda escrita de configuração é validada pelo modelo (`pm_settings`: um valor fora da faixa devolve `$NAK,1,EINVAL` e nada muda), gravada pelo subsistema settings do Zephyr com `$CFG,SAVE` e confirmada na resposta. O emparelhamento com o ciclocomputador escreve comprimento do pedivela e lado e dispara `$ZERO`.

## ANT+ Bicycle Power

Transmissor pelo perfil `ant_bpwr` do add-on `sdk-ant` (C:\ncs\sdk-ant), que implementa as páginas 1 (calibração), 16 (potência), 17 (torque na roda), 18 (torque no pedivela), 80 e 81 (fabricante e produto) e o callback de calibração; o exemplo `bpwr_tx` do add-on mostra o uso. O módulo alimenta o perfil com a potência, a cadência, o torque acumulado e o contador de eventos de `chan_power`, e responde ao pedido de calibração manual e ao auto-zero pela mesma rotina do BLE. O material do ANT+ é do add-on e não entra neste repositório; o build com `ANT=1` o encontra em `C:\ncs\sdk-ant`.

## Atualização

mcumgr SMP sobre BLE (grupo de imagem e de sistema), o mesmo transporte do ciclocomputador; e a recuperação serial do MCUboot sobre USB CDC ACM pelo conector magnético, para o cabo. A atualização é recusada pedalando e com bateria abaixo de 30 %.

O serviço SMP também exige ligação cifrada, pelo mesmo motivo do serviço de configuração: `CONFIG_MCUMGR_TRANSPORT_BT_PERM_RW_ENCRYPT` nos dois arquivos de placa. O padrão do Zephyr com o gerenciador de segurança ligado é exigir **autenticação**, e num aparelho sem tela nem teclado isso não é alcançável: a característica ficaria impossível de escrever e a atualização por BLE, impossível de fazer. Medido no `.config` gerado em 2026-09-27.

## Porta serial

Com o cabo no conector, o módulo aparece no PC como porta serial (USB CDC ACM) e aceita os mesmos comandos de texto do serviço de configuração, mais `$LOG` para o log do sistema. Serve à bancada de calibração sem rádio.
