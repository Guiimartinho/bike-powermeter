# Materiais por folha

O que cada folha do esquemático consome, com o designador de referência,
o footprint que a placa usa e o código de distribuidor quando ele já foi
anotado. Esta página **não substitui** a [lista de componentes](01-lista-de-componentes.md),
que traz o número do datasheet de cada peça e as razões da escolha; ela
diz **quantas peças cada folha pede** e o que cada uma faz no circuito.
A fonte é [`cad/parts.py`](cad/parts.py) e [`cad/footprints.py`](cad/footprints.py).

**Nesta página:** [Como ler](#como-ler) · [Folha 1 · Energia](#folha-1--energia) · [Folha 2 · MCU e depuração](#folha-2--mcu-e-depuração) · [Folha 3 · Ponte e conversor](#folha-3--ponte-e-conversor) · [Folha 4 · Sensores](#folha-4--sensores) · [Contagem](#contagem) · [O que ainda não tem código](#o-que-ainda-não-tem-código-de-compra)

> [!WARNING]
> **Nada foi comprado, nada foi montado.** Os códigos LCSC anotados vêm
> da [lista de componentes](01-lista-de-componentes.md) e estão marcados
> "a conferir" onde não foram batidos contra a página do distribuidor no
> dia do pedido.

## Como ler

- **Referência**: o designador do esquemático. O **primeiro dígito é a
  folha**: `1xx` energia, `2xx` MCU e depuração, `3xx` ponte e conversor,
  `4xx` sensores. `U` integrado, `R` resistor, `C` capacitor, `L` indutor,
  `FB` ferrite, `D` diodo e LED, `J` conector, `TP` ponto de teste.
- **Footprint**: o nome no `pmeter.kicad_pcb`. Os da biblioteca do KiCad 8
  aparecem com o prefixo da biblioteca; os desenhados aqui, com o prefixo
  `pmeter:` e a cota da ficha em `footprints.PACOTE`.
- **Quantidade**: por placa.
- Os passivos são **0402** salvo onde a ficha pede mais capacitância do
  que um 0402 aguenta (2,2 µF/25 V, 10 µF, 22 µF e 4,7 µF em **0603**).

## Folha 1 · Energia

| Referência | Componente | Valor ou código | Footprint | Qtd | Código |
|---|---|---|---|---|---|
| J101 | Conector magnético de 6 contatos, 2 fileiras de 3 | **genérico**, passo 2,5 mm, 1 A por contato, ouro | `pmeter:Pogo_Magnetico_6P_2x3_P2.5mm` (corpo 8,6 × 4,6 × 3,2 no courtyard de 9,0 × 5,0; footprint e corpo 3D **deste projeto**, a trocar pelo desenho do fornecedor) | 1 | **sem fornecedor** ([06](06-conectores-e-pontos-de-teste.md#j101--conector-magnético)) |
| D101 | ESD dos quatro sinais do conector | TI TPD4E05U06DQAR, USON-10 | `pmeter:TPD4E05U06_USON-10_1x2.5mm_P0.5mm` | 1 | C138714 |
| U101 | Carregador Li-ion e buck de 3,0 V | Nordic nPM1100-QDAB, QFN-24 4 × 4 | `Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.7x2.7mm` | 1 | C2903119, a conferir |
| U102 | Medidor de carga ModelGauge, 0x36 | Analog Devices MAX17048G+T10, TDFN-8 | `Package_DFN_QFN:TDFN-8-1EP_2x2mm_P0.5mm_EP0.8x1.2mm` | 1 | C2680383, a conferir |
| J102 | Conector da célula | **JST `SM02B-SRSS-TB`** — série SH, 1,0 mm, 2 vias, **entrada lateral**, 2,90 mm. A célula entra pelo plugue `SHR-02V-S` do próprio pack, que é **requisito de compra** dela | `Connector_JST:JST_SH_SM02B-SRSS-TB_1x02-1MP_P1.00mm_Horizontal` | — | a série é o que fixa o teto da tampa do pod ([06](06-conectores-e-pontos-de-teste.md#j102--célula)) |
| L101 | Indutor do buck | 2,2 µH, ≤ 400 mΩ, Isat ≥ 350 mA (Murata DFE201610E-2R2M) | `Inductor_SMD:L_0805_2012Metric` | 1 | C296426 |
| C101 | `VBUS` do nPM1100 | 2,2 µF, 25 V | 0603 | 1 | — |
| C102 | `VOUTB`, o trilho `3V0` | 22 µF | 0603 | 1 | — |
| C103 | `DEC` | 1 µF | 0402 | 1 | — |
| C104 | `VBAT` junto do nPM1100 | 10 µF | 0603 | 1 | — |
| C105 | `VDD` do MAX17048 | 100 nF | 0402 | 1 | — |
| C106 | `VSYS` | 100 nF | 0402 | 1 | — |
| R101 | `ICHG`: 625 / 0,0747 − 1562,5 | 6,8 kΩ | 0402 | 1 | — |
| R102 | `NTC` ao `AVSS`, pack sem termistor | 10 kΩ | 0402 | 1 | — |
| R103, R104 | Pull-ups de `CHG_N` e `ERR_N` | 100 kΩ | 0402 | 2 | — |
| R105 | Pull-up de `GAUGE_ALRT` | 100 kΩ | 0402 | 1 | — |
| R106 | `SHPHLD` ao `VBAT` | 1 MΩ | 0402 | 1 | — |
| R107, R108 | Série do SWD entre o conector e o módulo | 100 Ω | 0402 | 2 | — |
| TP101 a TP104 | `VBUS`, `VBAT`, `3V0`, `GND` | pad de 1,0 mm, **na face de trás** | `TestPoint:TestPoint_Pad_D1.0mm` | 4 | — |

## Folha 2 · MCU e depuração

| Referência | Componente | Valor ou código | Footprint | Qtd | Código |
|---|---|---|---|---|---|
| U201 | Módulo de rádio com o nRF54L15 | HOLYIOT-26001-A, 10,0 × 12,5 × 2,4 (a altura é reserva: não consta do desenho), antena cerâmica | `pmeter:HOLYIOT_26001A_10x12.5mm` (36 pads meio-furo, gerado das cotas do desenho mecânico) | 1 | a comprar do fabricante (AliExpress) |
| FB201 | Ferrite do filtro pi do módulo | 600 Ω a 100 MHz (Murata BLM15PX601SN1D) | `Inductor_SMD:L_0603_1608Metric` | 1 | C76909 |
| C201 | `VDD` do módulo, a 0,5 mm do pad 19 | 100 nF | 0402 | 1 | — |
| C202, C203 | Reserva dos dois lados do ferrite | 4,7 µF | 0603 | 2 | — |
| J201 | Gravação de fábrica e bancada | Tag-Connect TC2030-IDC-NL (só pads e furos de alinhamento) | `Connector:Tag-Connect_TC2030-IDC-NL_2x03_P1.27mm_Vertical` | 1 | cabo, não peça |
| D201 | LED RGB de anodo comum | TUOZHAN S4-3528RGBTA-A, 3,5 × 2,8 × 1,9 | `pmeter:LED_RGB_3528_3.5x2.8mm` | 1 | C2827321 |
| R201, R202, R203 | Série dos três catodos | 1,5 kΩ | 0402 | 3 | — |
| R204, R205 | Pull-ups do I2C, junto do mestre | 4,7 kΩ | 0402 | 2 | — |
| TP201, TP202 | Console `UART_TX` e `UART_RX` | pad de 1,0 mm, na face de trás | `TestPoint:TestPoint_Pad_D1.0mm` | 2 | — |

## Folha 3 · Ponte e conversor

| Referência | Componente | Valor ou código | Footprint | Qtd | Código |
|---|---|---|---|---|---|
| J301 | Furos dos fios da ponte e da blindagem | cinco furos metalizados de 0,9 mm em ilhas de 1,5, passo 2,0 | `pmeter:Furos_Ponte_5x1.5mm_P2mm` | 1 | — (é cobre) |
| U301 | Conversor de 24 bits da ponte | TI ADS1220IRVAR, VQFN-16 3,5 × 3,5 | `Package_DFN_QFN:Texas_RVA_VQFN-16-1EP_3.5x3.5mm_P0.5mm_EP2.14x2.14mm` | 1 | C123398, a conferir |
| U302 | Chave da excitação | TI TPS22916BYFPR, DSBGA-4 | `pmeter:TPS22916_DSBGA-4_0.78x0.78mm_P0.4mm` | 1 | C2917017, a conferir |
| R301, R302 | Série das entradas (filtro da figura 9-11) | 1 kΩ | 0402 | 2 | — |
| C301 | Capacitor diferencial das entradas | 47 nF, C0G | 0402 | 1 | — |
| C302, C303 | Modo comum de cada entrada | 4,7 nF, C0G | 0402 | 2 | — |
| C304 | Referência `REFP0`–`REFN0` | 100 nF | 0402 | 1 | — |
| C305, C306 | `AVDD` e `DVDD` do ADS1220 | 100 nF | 0402 | 2 | — |
| C307 | `VOUT` da chave | 100 nF | 0402 | 1 | — |
| C308 | `VIN` da chave | 1 µF | 0402 | 1 | — |
| TP301 | `3V0_EXC` | pad de 1,0 mm, na face de trás | `TestPoint:TestPoint_Pad_D1.0mm` | 1 | — |

## Folha 4 · Sensores

| Referência | Componente | Valor ou código | Footprint | Qtd | Código |
|---|---|---|---|---|---|
| U401 | Acelerômetro de 3 eixos | Bosch BMA400, LGA-12 2 × 2 | `Package_LGA:LGA-12_2x2mm_P0.5mm` | 1 | C542206, a conferir |
| U402 | Temperatura da ponte, ±0,1 °C | TI TMP117AIDRVR, WSON-6 2 × 2 | `Package_SON:WSON-6-1EP_2x2mm_P0.65mm_EP1x1.6mm` | 1 | C2687591, a conferir |
| C401, C402 | `VDD` e `VDDIO` do BMA400 | 100 nF | 0402 | 2 | — |
| C403 | `V+` do TMP117 | 100 nF | 0402 | 1 | — |

## Contagem

| Folha | Posições | Integrados | Passivos | Conectores e pontos de teste |
|---|---|---|---|---|
| 1 · Energia | 24 | 3 (U101, U102, D101) | 15 (6 C, 8 R, 1 L) | J101, J102, TP101 a TP104 |
| 2 · MCU e depuração | 14 | 2 (U201, D201) | 9 (3 C, 5 R, 1 FB) | J201, TP201, TP202 |
| 3 · Ponte e conversor | 14 | 2 (U301, U302) | 10 (8 C, 2 R) | J301, TP301 |
| 4 · Sensores | 5 | 2 (U401, U402) | 3 C | — |
| **Total** | **57** | **9** | **37** | **11** |

Os totais saem de `python cad/sheets.py`.

## O que ainda não tem código de compra

| Peça | Situação |
|---|---|
| J101, o conector magnético | nenhuma página de fornecedor pôde ser alcançada em 2026-09-27; o footprint é um lugar reservado e a numeração dos contatos é deste projeto ([06](06-conectores-e-pontos-de-teste.md#j101--conector-magnético)) |
| U201, o módulo | compra direta do fabricante, como no ciclocomputador |
| os passivos | genéricos; os C0G do filtro da ponte (C301 a C303) são a única exigência de dielétrico |
| a célula | envelope de 25 × 15 × 4 mm reservado no pod ([07](07-pod.md)); a célula não foi escolhida |
