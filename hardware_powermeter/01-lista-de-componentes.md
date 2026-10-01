# Lista de componentes (fase 1: módulo no braço do pedivela)

Lista fechada em 2026-09-27. Cada peça tem o datasheet baixado do fabricante e conferido (os PDF ficam em [`datasheets/`](datasheets/), fora do git). Os números abaixo são os do datasheet, com o documento indicado. O estudo que levou a esta lista está no doc "Medidores de potência para bicicleta: estudo para o projeto" (Claude Docs, 2026-09-27).

**Nesta página:** [Decisão](#decisão) · [A placa](#a-placa) · [Extensômetros](#extensômetros) · [Fora da placa](#fora-da-placa) · [O que ficou de fora](#o-que-ficou-de-fora) · [Não verificado](#não-verificado)

## Decisão

O sensor é o **TI ADS1220**: 0,26 µV RMS de ruído com ganho 128 a 175 amostras/s, 585 µA medindo, 0,4 µA desligado, referência ratiométrica, 3,5 × 3,5 mm. O conversor não é o limite dos ±1 a 2 %; a colagem, a temperatura e a calibração são. A compensação de temperatura fica no firmware, aberta e testada no PC.

```mermaid
flowchart LR
    G["Ponte completa<br/>1 kΩ, classe transdutor"] --> A["ADS1220<br/>ganho 128, ratiométrico"]
    SW["TPS22916<br/>excitação chaveada"] --> G
    SW --> A
    A --> M["HOLYIOT-26001-A<br/>nRF54L15"]
    I["BMA400<br/>cadência e ângulo"] --> M
    T["TMP117<br/>temperatura da ponte"] --> M
    M --> R["BLE Cycling Power<br/>ANT+ Bicycle Power"]
    P["nPM1100<br/>carga + buck 3,0 V"] --> M
    P --> SW
    F["MAX17048<br/>estado da bateria"] --> M
    C["Conector magnético<br/>5 V, USB, SWD"] --> P
    C --> M
```

## A placa

| Bloco | Peça | Datasheet | Números conferidos | Driver no NCS v3.3.0 |
|---|---|---|---|---|
| Conversor da ponte | **TI ADS1220**, VQFN-16 | SBAS501D (rev. maio 2026) | Ganho 128, modo normal, AVDD 3,3 V: 0,09 µV RMS a 20 SPS, 0,18 a 90, 0,26 a 175. Corrente AVDD com ganho 64 ou 128: 135 µA em duty-cycle, 510 normal, 890 turbo; DVDD 55, 75, 95 µA; power-down 0,1 µA (3 máx.), 400 nA típico. Referência externa de 0,75 V até AVDD. Referência interna 2,048 V, 5 ppm/°C. Sensor de temperatura 0,5 °C. 2,3 a 5,5 V. 3,5 × 3,5 mm. −40 a +125 °C | Não: driver próprio em `zephyr_app/modules/pm_drivers` |
| Alternativa com driver pronto | TI ADS124S06, VQFN-32 | SBAS660C (rev. junho 2017) | 19 nV RMS com ganho 128; 250 µA AVDD + 225 µA DVDD medindo com referência externa; +185 µA se usar a referência interna de 2,5 V; power-down 0,1 µA; 5 × 5 mm; SPI com CRC, calibração de sistema, detecção de falhas | Sim: `ti,ads124s06` |
| Alternativa com compensação no chip | Renesas ZSSC3224, PQFN-24 | Datasheet Renesas | Ganho 6,6 a 216, ADC de 12 a 24 bits, compensação de 1ª e 2ª ordem em memória MTP, erro do CI 0,01 % FSO, 1050 µA ativo, 20 nA sleep, 24 bits a 60 Hz, 1,68 a 3,6 V, 4 × 4 mm | Não |
| Acelerômetro | **Bosch BMA400**, LGA-12 | BST-BMA400-DS000-14 (rev. 2.3, julho 2025) | 14,5 µA normal (OSR 3) ou 3,5 µA (OSR 0), 850 nA em low-power a 25 Hz, 160 nA em sleep; ODR 12,5 a 800 Hz; ±2 a ±16 g; FIFO de 1 kB; VDDIO 1,2 a 3,6 V; 2 × 2 × 0,95 mm | **Não: driver próprio.** O `bosch,bma4xx` da árvore reconhece o chip ID `0x90` com um aviso e **não opera a peça**: ele usa o mapa de registradores do BMA422 (dados em `0x12`, configuração em `0x40`) e o BMA400 tem outro (`0x04`, `0x19`). O driver está em `zephyr_app/modules/pm_drivers/drivers/sensor` ([`docs/04`](../docs/04-arquitetura-firmware.md)) |
| Temperatura da ponte | **TI TMP117**, WSON-6 | Datasheet TI | ±0,1 °C máx. de −20 a 50 °C, 16 bits (0,0078 °C), 3,5 µA a 1 Hz, 150 nA desligado, 1,7 a 5,5 V, 2 × 2 mm, I2C | Sim: `ti,tmp11x` |
| Carga e trilho de 3,0 V | **Nordic nPM1100**, QFN-24 4 × 4 mm | Product Specification v1.5 | Carregador Li-ion de 20 a 400 mA por resistor, JEITA, terminação selecionável; VBUS de 4,1 a 6,7 V (20 V absoluto); buck de 1,8 a 3,0 V e 150 mA; 800 nA quiescente, 460 nA em ship mode; sem interface de controle; LED de carga e erro | Não precisa (pinos) |
| Alternativa | TI BQ25180 (DSBGA-8) + TI TPS62840 (SON-8) | Datasheets TI | BQ25180: 5 mA a 1 A, proteções OVP, UVLO, curto, sobrecorrente, térmica, ship mode 3,2 µA, 15 nA desligado, I2C. TPS62840: buck de 60 nA quiescente, 750 mA, 1,8 a 6,5 V, 16 tensões por pino | BQ25180: `ti,bq25180` |
| Medidor de bateria | **MAX17048**, TDFN-8 2 × 2 mm | 19-6171 (rev. 7, novembro 2016) | ModelGauge sem resistor de sentido, ±7,5 mV, 3 µA em hibernate, I2C, alerta | Sim: `maxim,max17048` |
| Chave da excitação | **TI TPS22916** | Datasheet TI | 1 a 5,5 V, 2 A, 60 a 200 mΩ, 0,5 µA ligado, 10 nA desligado, bloqueio de corrente reversa | GPIO |
| Proteção dos sinais do conector | **TI TPD4E05U06** | Datasheet TI | IEC 61000-4-2 ±12 kV contato e ±15 kV ar, 0,42 a 0,5 pF por canal, 6,5 V de ruptura, 10 nA de fuga; quatro canais: D+, D−, SWDIO, SWCLK | Passivo |
| Diodo ideal no VBUS (opcional) | TI LM66100 | Datasheet TI | 1,5 a 5,5 V, 1,5 A, 79 a 141 mΩ, 150 nA quiescente | Passivo |
| LDO de 3,0 V (só se o buck sair) | TI TPS7A02 | SBVS277C | 25 nA quiescente, 3 nA desligado, 200 mA, 1,5 %, 1,5 a 6 V, X2SON 1 × 1 mm ou SOT23-5 | Regulador |
| MCU e rádio | **HOLYIOT-26001-A** (nRF54L15, antena cerâmica) | não há ficha em PDF: o desenho mecânico do anúncio do fabricante | 10,0 × 12,5 mm, 36 pads, 30 GPIO; BLE, ANT+ (add-on `sdk-ant`); **sem USB** (o SoC não tem `usbhs`), a porta serial passa para a UART do conector magnético ([09](09-modulo-de-radio.md)). A altura do corpo não consta em lugar nenhum: o projeto reserva 2,4 mm, o mesmo do módulo que saiu | Sim, mais o add-on ANT |
| Versão I2C do conversor | TI ADS122C04, WQFN-16 | SBAS751B | Os mesmos 20 bits efetivos, 315 µA, I2C, 3 × 3 mm | Não |
| Bateria | LiPo de bolsa classe **`501415`**: 5,0 × 14 × 15 mm, **≥ 81 mAh**, dois fios já soldados e proteção (PCM) integrada | **nenhuma listagem foi alcançada**: as nove lojas tentadas em 2026-09-28 (DigiKey, Mouser, AliExpress e seis brasileiras) recusaram a conexão desta máquina. O envelope e a capacidade são **requisito de compra**, não uma peça escolhida | A 0,68 mA (ponte de 5 kΩ com o conversor em duty-cycle), 81 mAh valem **119 h** contra as 50 h do requisito. O nome `501415` é o código de tamanho usual do ramo: 5,0 mm de espessura, 14 mm de largura, 15 de comprimento. O envelope mudou em 2026-09-30, quando a célula saiu de baixo da placa e foi para a baía AO LADO dela | |
| Conector | Magnético de 6 contatos em 2 × 3, ímã com polaridade | **não existe**: nenhum fornecedor foi alcançado, o desenho é deste projeto | 5 V, GND, D+, D−, SWDIO, SWCLK; as molas ficam no **cabo** e os alvos chatos no aparelho, que é o que a vedação exige; cabo com USB-serial e saída SWD de 10 vias ([06](06-conectores-e-pontos-de-teste.md#j101--conector-magnético)) | |
| Indicação | LED RGB de baixa corrente | | Pareamento, calibração, carga (o nPM1100 tem saídas de LED) | |

Topologia dos trilhos: o buck do nPM1100 dá 3,0 V para o módulo, o ADS1220 e os sensores; a excitação da ponte sai desse trilho pela TPS22916 e vai também aos pinos REFP0 e REFN0 do ADS1220, então o ruído do buck cancela na medição ratiométrica. A ponte de 1 kΩ a 3,0 V drena 3 mA só enquanto a chave está ligada.

## Extensômetros

Não são circuitos integrados, mas definem a precisão. Referência: Micro-Measurements (Vishay Precision Group), páginas abertas em 2026-09-27.

| O que | Escolha | Fonte |
|---|---|---|
| Padrão | **Ponte completa numa peça só, de flexão**, classe transdutor: um filme, uma colagem, um alinhamento, com as quatro grades já posicionadas e ligadas de fábrica. Era alternativa nesta linha e vira a escolha, por dois motivos medidos: o padrão de cisalhamento a 45° é de torquímetro de eixo e dá 8,9 vezes menos sinal num braço de pedivela ([`docs/06`](../docs/06-medicao-e-calibracao.md#cisalhamento-ou-flexão-o-padrão-especificado-está-errado)), e quatro colagens separadas multiplicam por quatro o erro de alinhamento, que é o gargalo da precisão | [Transducer Class](https://www.micro-measurements.com/transducer-class); `docs/06` |
| Padrões de análise (para a bancada) | CEA 062UV e 187UVA (350 Ω), CEA 125US e 250USA (120, 350 e 1000 Ω), C2A 062LV | [Shear and torque patterns](https://www.micro-measurements.com/shear-pattern-strain-gages) |
| Resistência | **5 kΩ** (decisão do dono). O guia do fabricante nomeia 120, 350, 1 k e 5 kΩ e diz que, havendo escolha, a resistência mais alta é preferível: gera menos calor na grade, sofre menos dessensibilização pelo fio e melhora a relação sinal-ruído, por permitir excitação maior sem auto-aquecimento | Guia de seleção, p. 4, citado |
| Fios já presos | **Opção P2**, que pelo fabricante "praticamente elimina a necessidade de soldar durante a instalação": cabo de 3,1 m, 30 AWG estanhado, grade inteira encapsulada, vida em fadiga inalterada e sem aumento de rigidez. **Dois poréns medidos:** o cabo da P2 tem **três** condutores e uma ponte cheia precisa de quatro, então para o padrão de ponte cheia a fiação tem de ser confirmada peça a peça; e o limite é −50 a +80 °C, pelo vinil, que cobre com folga os −10 a +50 °C do requisito. A alternativa é a **opção W**, terminais de circuito impresso já presos, que aceita fio mais grosso mas encurta a vida em fadiga e engrossa a peça | Guia de seleção, p. 5 e 6, citado |
| Compensação térmica | S-T-C casado com o material: 13 para alumínio (braço), 06 para aço (eixo) | Guia de seleção |
| Cola | M-Bond AE-10 ou AE-15 para o módulo (resistentes à umidade); M-Bond 200 para a bancada | Guia de seleção, p. 8 |
| Proteção | 3145 RTV + M-Coat B para longo prazo | Guia de seleção, p. 9 |

### A peça, achada no databook do fabricante (2026-09-28)

O databook de classe transdutor (2622-EN, rev. 12-ago-2019, 116 páginas, em `datasheets/`) responde a pergunta: **existe ponte completa numa peça só em 5 kΩ.** O próprio documento diz, na página 7, que os padrões de alta resistência são oferecidos "em configurações linear, de cisalhamento, tee e **de ponte completa**, com até 10 kΩ". Estes são os candidatos, todos com as quatro grades num filme e a ponte já balanceada de fábrica:

| Padrão | Designação | Ω | Matriz | Descrição do databook |
|---|---|---|---|---|
| **S5229** | `N2K-13-S5229A-50C/DG/E3` | 5000 ±5 % | **4,0 × 3,7 mm** | ponte completa miniatura de alta resistência, balanceada a ±0,5 mV/V |
| S5020 | `N2K-13-S5020Q-50C/DG/E3` | 5000 ±5 % | 4,3 × 4,7 mm | idem, balanceada a ±0,4 mV/V |
| S5046 | `N2K-13-S5046M-50C/DG/E5` | 5000 | 4,5 × 4,8 mm | ponte completa aberta, para cisalhamento ou torque |
| S5067 | `N2K-13-S5067P-10C/DG/E5` | 1000 ±3 % | 4,3 × 4,3 mm | ponte completa pequena **para vigas em flexão** |
| S5062 | `N2K-13-S5062N-10C/DG/E5` | 1000 ±3 % | 4,2 × 4,8 mm | idem |

**Recomendação: S5229.** É a menor das cinco, cabe folgado no braço, é de 5 kΩ, o que mantém o consumo em 1,5 mA — 0,68 mA com o conversor em duty-cycle — e o pod em 10,0 mm, e vem com a ponte balanceada a ±0,5 mV/V, o que reduz o zero a calibrar. O desenho do padrão mostra quatro grades, **duas longitudinais e duas transversais**: é ponte de Poisson, que num campo de flexão entrega cerca de dois terços da saída de uma ponte de flexão pura, e ainda assim cerca de seis vezes o que o cisalhamento daria.

**Como se lê a designação:** `N2K` é a série, padrões de liga Karma modificada sobre filme de poliimida, com ilhas de solda douradas (`DG`) e encapsulamento epóxi; `13` é o número de autocompensação térmica, que o databook diz ser o de estoque para **ligas de alumínio** (`06` é o de aços), e é ele que casa o extensômetro com o material do braço.

### Os braços do dono, e o que eles fecham (2026-09-28)

O dono começa pelos **Shimano 105 e Ultegra**, os dois de **liga de alumínio**, e quer depois cobrir SRAM e braços de aço e de carbono. O alumínio fecha o código: **S-T-C 13**. A designação de compra fica

> **`N2K-13-S5229A-50C/DG/E3`**

**Duas armadilhas de compra, do próprio databook:** se o código não for escrito no pedido, o fabricante **embarca o 06**, que é o de aço, e num braço de alumínio isso faz a leitura andar com a temperatura. E o fator de grade da liga K, que é a do N2K, é **2,1**, não 2,0: as contas deste projeto usaram 2,0 e ficam conservadoras em 5 %.

**Braço Shimano é oco, e isso melhora o sinal.** Refazendo a conta com parede de 3 mm numa seção externa de 20 × 14 mm, o momento de inércia cai de 9.333 para 7.504 mm⁴ e a deformação sobe de 459 para **571 µε**, 24 % mais. Com a ponte de Poisson do S5229, que entrega cerca de dois terços de uma ponte de flexão pura, a saída fica em **2,28 mV** a 3,0 V, dentro da faixa que [`docs/06`](../docs/06-medicao-e-calibracao.md) sempre assumiu.

**Para os outros materiais da fase seguinte:**

| Material | O que muda |
|---|---|
| Aço (SRAM e outros) | só o código: `N2K-06-S5229A-50C/DG/E3`. Mesma peça, mesma colagem |
| Carbono | não é só o código. O databook diz que resistências altas são usadas justamente em compósitos, mas o S-T-C é o coeficiente de dilatação do material em ppm/°F, e o de carbono-epóxi é perto de zero na direção das fibras: o número sai do sistema de designação por liga, e ainda há a camada rica em resina da superfície e a anisotropia. É estudo à parte, não troca de código |

Cada braço muda a inclinação, porque muda a seção e a distância da colagem ao pedal. Isso **não é problema**: a inclinação é calibrada por unidade, com massa pendurada, e é justamente o que permite cobrir vários pedivelas com a mesma eletrônica. O que muda de verdade por modelo é a **largura da face interna** e o raio de concordância, que decidem se o pod assenta.

**O que ainda falta:** preço e prazo com o distribuidor. Se o S5229 não vier em `13`, a saída é o S5067 em 1000 Ω com o modo duty-cycle do conversor, que dá 1,40 mA e mantém o pod ([`docs/02`](../docs/02-hardware.md#orçamento-de-consumo)).

**Onde estão os catálogos:** biblioteca do fabricante, PDF direto, sem cadastro. Classe transdutor `docs.micro-measurements.com/?id=12970`; extensômetros de precisão `?id=4079`; acessórios `?id=12967`; instrumentação `?id=4078`.

## Fora da placa

- Um braço esquerdo usado, igual ao do ciclista, para a bancada.
- ADS1232 em placa de avaliação como referência de bancada (SBAS350H: 17 nV RMS a 10 SPS com ganho 128, mas 1,35 mA e só 80 SPS).
- Massas de 5 a 20 kg e um medidor comercial de referência para a prova de estrada.

## O que ficou de fora

| Peça | Motivo |
|---|---|
| Avia HX711 | Ruído, consumo e alimentação de 5 V; peça de balança de cozinha |
| TI ADS1235 | 23 mW e alimentação de 5 V ou ±2,5 V |
| TI PGA302 | Saída analógica e alimentação de 4,5 a 20 V |
| Renesas ZSSC3218 | Só existe como die |
| MAX17262 | WLP de 1,5 mm; o MAX17048 tem TDFN e driver pronto |

## Não verificado

A Analog Devices e a ST recusaram a conexão desta máquina em todos os caminhos (site, DigiKey, Arrow, alldatasheet, GitHub): **AD4130-8**, **AD7124-4** e **LIS2DW12** não entraram na lista. O AD4130-8 é o único que poderia bater o ADS1220 em consumo (excitação e chave da ponte com duty-cycle interno, driver `adi,ad4130-adc` no Zephyr). Se o datasheet chegar, a comparação é refeita com os mesmos critérios.
