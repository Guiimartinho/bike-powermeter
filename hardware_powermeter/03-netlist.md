# Lista de nós

O esquemático como lista: cada nó, de onde sai e aonde chega. É esta a
forma que a cadeia confere: [`cad/nets.py`](cad/nets.py) é a fonte, o
`check_sch.py` compara o netlist que o KiCad exporta do esquemático gerado
com ela pino a pino, e o `route.py` e o `dry_run_pcb.py` leem os números
das redes do próprio `pmeter.kicad_pcb`.

**Nesta página:** [Como ler](#como-ler) · [Alimentação](#nós-de-alimentação) · [MCU](#nós-do-módulo) · [Ponte e conversor](#nós-da-ponte-e-do-conversor) · [Sem ligação ao MCU](#nós-sem-ligação-ao-módulo) · [Pinos sem nó](#pinos-sem-nó-de-propósito) · [Contagem](#contagem)

> [!WARNING]
> Nenhum destes nós existe em cobre montado. A placa existe como arquivo
> de CAD ([04](04-placa.md)); nada foi fabricado nem medido.

## Como ler

- **Nó**: o nome do sinal como aparece no esquemático e na placa.
- **Pino do módulo**: o pino do nRF54LM20A como o devicetree o declara
  ([`docs/02`](../docs/02-hardware.md#pinos-do-módulo)); o de-para para o
  pad do ME54BS13 sai da ficha V1.0.0 (páginas 6 a 9) e está em
  [`cad/parts.py`](cad/parts.py) (`PADS_ME54BS13`, os 80 pads, a mesma
  tabela do ciclocomputador). **O espelhamento desse mapa ainda precisa ser
  conferido num módulo real.**
- **Tipo**: `alim` (alimentação), `dig` (digital), `ana` (analógico).
- **Folhas**: `1` energia, `2` MCU e depuração, `3` ponte e conversor,
  `4` sensores ([02](02-esquematico.md)). Um nó que aparece em mais de uma
  folha sai por rótulo hierárquico; os trilhos viajam por símbolo de
  alimentação.
- Toda referência de terra é **GND**, plano contínuo na `In1.Cu`
  ([04](04-placa.md#camadas)).

## Nós de alimentação

| Nó | Tensão | Sai de | Chega em | Tipo |
|---|---|---|---|---|
| `VBUS` | 4,1 a 6,7 V de operação, 20 V absoluto (nPM1100 PS v1.5, 6.1) | conector magnético `J101`, contato 2 | nPM1100 `VBUS` (17); C101 2,2 µF/25 V; pad 9 do módulo (o detector de USB do SoC); `TP101` | alim |
| `VBAT` | 3,0 a 4,2 V | positivo da célula, `J102` contato 1 | nPM1100 `VBAT` (15); C104 10 µF; MAX17048 `VDD` (3), que lê a tensão da célula por ele; C105 100 nF; R106 1 MΩ (o pull-up do `SHPHLD`); `TP102` | alim |
| `VSYS` | `VBUS` ou `VBAT` | nPM1100 `VSYS` (16) | C106 100 nF; `VOUTBSET0` (3), `VOUTBSET1` (2) e `VTERMSET` (9) do nPM1100, os três altos: 3,0 V no buck e 4,2 V de terminação; anodo comum do LED `D201` | alim |
| `BUCK_SW` | chaveado | nPM1100 `SW` (22) | `L101` 2,2 µH, pino 1 | alim |
| `DEC` | interno | nPM1100 `DEC` (21) | C103 1 µF | alim |
| `3V0` | 3,0 V, 150 mA no máximo | `L101` pino 2 e `VOUTB` (1) do nPM1100 (o sentido do buck) | C102 22 µF; `TP103`; pull-ups R103, R104, R105, R204, R205; `FB201` pino 1 e C203; `VTref` do Tag-Connect; ADS1220 `AVDD` (10) e `DVDD` (11) com C305 e C306; TPS22916 `VIN` (A2) com C308; BMA400 `VDD` (7) e `VDDIO` (3) com C401 e C402; TMP117 `V+` (5) com C403 | alim |
| `3V0_MOD` | 3,0 V | `FB201` pino 2 (ferrite de 600 Ω a 100 MHz) | pad 19 (`VDD`) do ME54BS13; C201 100 nF a 0,5 mm do pad; C202 4,7 µF | alim |
| `3V0_EXC` | 3,0 V, ligado só enquanto o conversor converte | TPS22916 `VOUT` (A1) | C307 100 nF; `E+` da ponte (furo 1 de `J301`); `REFP0` (7) do ADS1220 com C304 100 nF; `TP301` | alim |
| `GND` | 0 V | — | plano contínuo; `J101` contato 1 e os dois pads dos ímãs; `D101` 3 e 8; nPM1100 `AVSS` (4), `PVSS` (23), pad exposto, `ISET` (5) e `MODE` (7); MAX17048 `GND` (4), pad exposto, `CTG` (1) e `QSTRT` (6); `J102` contato 2; `TP104`; os oito pads de terra do módulo; ADS1220 `AVSS` (3), `DGND` (2), pad exposto, `CLK` (1) e `REFN0` (6); `E−` e a blindagem da ponte (furos 4 e 5 de `J301`); TPS22916 `GND` (B1); BMA400 `GND` (9) e `GNDIO` (8); TMP117 `GND` (2), pad exposto e `ADD0` (4); o segundo pino de todo capacitor de desacoplamento, de R101 e de R102 | alim |

## Nós do módulo

| Nó | Pino do módulo | Sai de | Chega em | Folhas | Tipo |
|---|---|---|---|---|---|
| `USB_DP` | pad 8 | `J101` contato 4 | `D101` 1 (`D1+`) e 10 (`NC`, passagem direta); pad 8 do módulo; nPM1100 `D+` (20), que lê a porta | 1, 2 | dig |
| `USB_DM` | pad 7 | `J101` contato 3 | `D101` 2 e 9; pad 7; nPM1100 `D−` (19) | 1, 2 | dig |
| `SWDIO_J` | — | `J101` contato 5 | `D101` 4 e 7; `R107` 100 Ω | 1 | dig |
| `SWCLK_J` | — | `J101` contato 6 | `D101` 5 e 6; `R108` 100 Ω | 1 | dig |
| `SWDIO` | pad 5 | `R107` | pad 5 do módulo; Tag-Connect `J201` contato 2 | 1, 2 | dig |
| `SWDCLK` | pad 6 | `R108` | pad 6; `J201` contato 4 | 1, 2 | dig |
| `RESET` | pad 4 | pad 4 do módulo | `J201` contato 3 | 2 | dig |
| `SHPACT` | P1.25 (E5) | módulo | nPM1100 `SHPACT` (6): alto por 200 ms sem cabo entra em ship mode | 1, 2 | dig |
| `CHG_N` | P1.11 (F5) | nPM1100 `CHG` (8), dreno aberto | `R103` 100 kΩ ao `3V0`; módulo | 1, 2 | dig |
| `ERR_N` | P1.12 (F4) | nPM1100 `ERR` (10), dreno aberto | `R104` 100 kΩ ao `3V0`; módulo | 1, 2 | dig |
| `GAUGE_ALRT` | P1.22 (E4) | MAX17048 `ALRT` (5), dreno aberto | `R105` 100 kΩ ao `3V0`; módulo | 1, 2 | dig |
| `I2C_SDA` | P1.29 (B9) | módulo (`TWIM23`) | `R204` 4,7 kΩ ao `3V0`; MAX17048 `SDA` (8); TMP117 `SDA` (6) | 1, 2, 4 | dig |
| `I2C_SCL` | P1.03 (B8, pino de clock) | módulo | `R205` 4,7 kΩ; MAX17048 `SCL` (7); TMP117 `SCL` (1) | 1, 2, 4 | dig |
| `SPI_SCK` | P2.01 (E9, pino de clock) | módulo (`SPIM00`) | ADS1220 `SCLK` (15); BMA400 `SCX` (12) | 2, 3, 4 | dig |
| `SPI_MOSI` | P2.02 (D9) | módulo | ADS1220 `DIN` (14); BMA400 `SDX` (2) | 2, 3, 4 | dig |
| `SPI_MISO` | P2.04 (C8) | ADS1220 `DOUT/DRDY` (13) e BMA400 `SDO` (1), os dois em três estados | módulo | 2, 3, 4 | dig |
| `ADC_CS` | P2.05 (D8) | módulo | ADS1220 `CS` (16) | 2, 3 | dig |
| `ADC_DRDY` | P2.03 (C9) | ADS1220 `DRDY` (12) | módulo, borda de descida | 2, 3 | dig |
| `IMU_CS` | P2.07 (E8) | módulo | BMA400 `CSB` (10) | 2, 4 | dig |
| `IMU_INT1` | P2.08 (F8) | BMA400 `INT1` (5) | módulo | 2, 4 | dig |
| `EXC_EN` | P1.10 (E3) | módulo | TPS22916 `ON` (B2): alto liga a excitação | 2, 3 | dig |
| `LED_R`, `LED_G`, `LED_B` | P1.06 (A6), P1.08 (C6), P1.09 (D6) | módulo, ativo baixo | `R201`, `R202`, `R203` 1,5 kΩ | 2 | dig |
| `UART_TX`, `UART_RX` | P1.00 (A7), P1.31 (B7) | módulo (`UARTE20`) | `TP201`, `TP202` (o console, só na bancada) | 2 | dig |

## Nós da ponte e do conversor

| Nó | Sai de | Chega em | Tipo |
|---|---|---|---|
| `BR_SP` | `S+` da ponte, furo 2 de `J301` | `R301` 1 kΩ | ana |
| `BR_SN` | `S−`, furo 3 | `R302` 1 kΩ | ana |
| `AIN_P` | `R301` | ADS1220 `AIN0` (9); `C301` 47 nF C0G (diferencial, o outro lado em `AIN_N`); `C302` 4,7 nF C0G ao terra | ana |
| `AIN_N` | `R302` | ADS1220 `AIN1` (8); `C301`; `C303` 4,7 nF C0G ao terra | ana |
| `3V0_EXC` | (trilho, acima) | é ao mesmo tempo a excitação da ponte e a referência `REFP0`: medição ratiométrica (SBAA532A, 3.1) | alim |

O filtro é o da figura 9-11 do SBAS501D: resistor em série em cada entrada,
capacitor diferencial e um capacitor de modo comum por entrada, dez vezes
menor que o diferencial. O corte diferencial fica em 1,7 kHz, bem acima
dos 175 SPS, e o de modo comum em 34 kHz; os valores são escolha deste
projeto e estão registrados em [`cad/parts.py`](cad/parts.py).

## Nós sem ligação ao módulo

| Nó | Sai de | Chega em | Tipo |
|---|---|---|---|
| `ICHG` | nPM1100 `ICHG` (12) | `R101` 6,8 kΩ ao terra: cerca de 75 mA de carga (6.2.4) | ana |
| `NTC` | nPM1100 `NTC` (14) | `R102` 10 kΩ ao terra: pack sem termistor (6.2.5) | ana |
| `SHPHLD` | nPM1100 `SHPHLD` (11) | `R106` 1 MΩ ao `VBAT`, e mais nada: o pod não tem botão e só sai do ship mode pelo cabo | dig |
| `LED_KR`, `LED_KG`, `LED_KB` | catodos de `D201` | `R201`, `R202`, `R203` | dig |

## Pinos sem nó, de propósito

| Peça | Pino | Por quê |
|---|---|---|
| nPM1100 `U101` | 13, 18, 24 | `NC` na tabela 24 do PS v1.5 |
| MAX17048 `U102` | 2 (`CELL`) | não ligado internamente no MAX17048: o CI lê a célula pelo `VDD` (ficha, página 6) |
| ADS1220 `U301` | 4 (`AIN3`), 5 (`AIN2`) | entradas não usadas ficam abertas; a ficha manda deixar `AIN3` em aberto (9.1.5) |
| BMA400 `U401` | 4, 11 (`NC`), 6 (`INT2`) | `NC` na ficha; a segunda interrupção não é usada |
| TMP117 `U402` | 3 (`ALERT`) | o alerta de temperatura não é usado: o TMP117 é lido a 1 Hz |
| ME54BS13 `U201` | pad 2 (`RF`) e os pads não listados em `docs/02` | a antena é a de PCB do módulo; os pads livres ficam abertos, sem cobre por baixo da área da antena |

## Contagem

| O que | Quantos |
|---|---|
| Nós | 45 (7 trilhos, 18 que atravessam folha, 20 internos a uma folha) |
| Pinos ligados | 213 |
| Pinos sem nó de propósito | 12 |
| Peças | 57 |

Os números saem de `python cad/sheets.py` e de `python cad/check_sch.py`
(que também confere os 12 pinos deixados abertos contra `nets.py`).
