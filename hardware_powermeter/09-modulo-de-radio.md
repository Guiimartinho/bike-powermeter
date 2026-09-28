# Módulo de rádio

O **HOLYIOT-26001-A**: o que ele tem, o que ele custa e por que o projeto
troca o ME54BS13 por ele. A pinagem e as cotas foram lidas no desenho
mecânico do fabricante (fotos do anúncio, enviadas pelo dono em 2026-09-28);
tudo o que é sobre o SoC foi conferido no **NCS v3.3.0 instalado**, arquivo
por arquivo, e não de memória.

**Nesta página:** [Por que trocar](#por-que-trocar) · [O que o SoC muda](#o-que-o-soc-muda) · [Pinagem](#pinagem) · [Mecânica](#mecânica) · [A antena manda no layout](#a-antena-manda-no-layout) · [O mapa de pinos do projeto](#o-mapa-de-pinos-do-projeto) · [O que falta confirmar](#o-que-falta-confirmar)

> [!WARNING]
> **Nenhum módulo foi comprado, soldado ou medido.** As cotas vêm do desenho
> mecânico do anúncio, não de uma peça na bancada nem de uma ficha em PDF. O
> footprint gerado a partir delas é provisório até alguém medir uma peça
> real, e a altura do corpo **não consta em lugar nenhum**.

## Por que trocar

O motivo é um só e foi medido: o módulo era **26 % da área da placa numa
peça só**, mais que as 37 peças pequenas somadas. Passivo não move esse
número; o módulo move.

| | ME54BS13 (nRF54LM20A) | HOLYIOT-26001-A (nRF54L15) |
|---|---|---|
| Corpo | 12,0 × 16,5 mm | **10,0 × 12,5 mm** |
| Courtyard | 212,5 mm² (26 % da placa) | ~136 mm² |
| Pinos | 80 (20 castelados + matriz LGA) | **36** (30 GPIO) |
| Antena | traço no módulo, com recorte na placa | **cerâmica integrada** |
| GPIO que o projeto usa | 19 | 20 (um a mais, ver abaixo) |

A largura é o ganho maior: o [04](04-placa.md#o-contorno) registra que *"a
largura de 16 mm é o limite do pod… o módulo tem 12 mm de largura e é ele
que põe o piso"*. Com 10 mm o piso desce e a placa vai a 14, o que leva o
pod de 19,4 para 17,4 mm de largura — **abaixo da faixa inteira da classe de
referência** (18 a 22 mm). E os cerca de 4 mm de comprimento que a peça mais
curta devolve são quase exatamente o que a vedação da case custa
([07](07-pod.md#o-envelope)).

## O que o SoC muda

Medido nos arquivos do NCS v3.3.0, não suposto:

| | nRF54L15 | nRF54LM20A | Onde foi lido |
|---|---|---|---|
| GPIO | **34** (P0 ×7, P1 ×16, P2 ×11) | 66 | `nrf54l_05_10_15.dtsi`, campo `ngpios` |
| Flash (RRAM) | 1.428 KB | — | `nrf54l15.dtsi` |
| RAM do app | **188 KB** | 511 KB | idem |
| **USB** | **não existe** | `usbhs`, 16 endpoints | `usbhs` só aparece em `nrf54lm20_a_b.dtsi` |

### O USB é o único custo, e ele é contornável

O `usbhs` **não existe** no nRF54L15: contar as ocorrências em
`nrf54l_05_10_15.dtsi` dá zero, e em `nrf54lm20_a_b.dtsi` dá seis. O USB
fazia três coisas neste aparelho, e cada uma tem saída:

| O que o USB fazia | Sem ele |
|---|---|
| Porta serial dos comandos, para a bancada de calibração sem rádio ([`docs/06`](../docs/06-medicao-e-calibracao.md)) | **UART** nos contatos `D+` e `D−` do conector magnético, que ficam livres; o cabo passa a ser USB-serial em vez de USB puro |
| Recuperação serial do MCUboot | idem, o MCUboot faz por UART; e o **SWD continua no conector** de qualquer jeito |
| Saber que o cabo entrou (o `usb_svc.c` registra que *"o nPM1100 não tem pino para isso"*) | **1 GPIO com divisor no `VBUS`** — um pino e dois resistores |

Custo total: **um GPIO a mais** (20 em vez de 19, de 30 disponíveis) e dois
resistores.

### A RAM é o que fica apertado

O firmware de hoje usa 124.068 B com o ANT+ ligado. Em 188 KB isso é
**64 %**, contra 24 % no nRF54LM20A. Funciona, mas a folga cai de 387 KB
para 68 KB, e quem acrescentar função depois precisa saber disso.

## Pinagem

36 pinos: uma coluna castelada e uma fileira LGA de cada lado, e uma fileira
castelada embaixo. A numeração corre da ponta superior esquerda, desce pela
coluna externa esquerda, segue da esquerda para a direita pela fileira de
baixo, sobe pela coluna externa direita, e só então percorre as duas
fileiras internas — a esquerda de cima para baixo, a direita de baixo para
cima.

| # | Sinal | # | Sinal | # | Sinal |
|---|---|---|---|---|---|
| 1 | `NRESET` | 13 | `P1.07` | 25 | `P0.00` |
| 2 | `P0.02` | 14 | `P1.06` | 26 | `P0.04` |
| 3 | `P0.01` | 15 | `VDD` | 27 | `P2.06` |
| 4 | `SWDIO` | 16 | `P2.04` | 28 | `P2.07` |
| 5 | `SWDCLK` | 17 | `P1.05` | 29 | `P2.03` |
| 6 | `P2.10` | 18 | `P1.04` | 30 | `P2.02` |
| 7 | `P2.09` | 19 | `P1.15` | 31 | `P1.03` |
| 8 | `P2.05` | 20 | `P1.14` | 32 | `P1.02` |
| 9 | `P2.00` | 21 | `P1.13` | 33 | `P1.12` |
| 10 | `P2.01` | 22 | `P1.09` | 34 | `P1.11` |
| 11 | `P2.08` | 23 | `GND` | 35 | `P1.10` |
| 12 | `P1.08` | 24 | `P0.03` | 36 | `GND` |

Os 30 GPIO expostos: `P0.00` a `P0.04` (5), `P1.02` a `P1.15` (14) e `P2.00`
a `P2.10` (11). O módulo **não** traz `P0.05`, `P0.06`, `P1.00` e `P1.01`,
e as três portas batem exatamente com o `ngpios` do SoC (7, 16 e 11).

A versão **26001-B** tem a mesma pinagem e troca a antena cerâmica por
conector IPX para antena externa.

## Mecânica

Todas as cotas saem do desenho mecânico do anúncio, e o desenho **fecha por
três caminhos independentes**, o que é a única razão para confiar nele sem
uma peça na mão:

- 7 pads de coluna num vão de 7,2 mm dão 6 × **1,2**;
- 8 pads na fileira de baixo num vão de 8,4 mm dão 7 × **1,2**, o mesmo
  passo;
- do último pad de coluna (3,8 + 7,2 = 11,0 da borda de cima) até a fileira
  de baixo (12,25) vão **1,25 mm**, que é o mesmo passo de novo.

| Cota | Valor |
|---|---|
| Corpo | 10,0 × 12,5 mm |
| Do topo ao centro do primeiro pad de coluna | 3,8 mm |
| Vão das colunas laterais, centro a centro | 7,2 mm (7 pads a 1,2) |
| Vão da fileira de baixo, centro a centro | 8,4 mm (8 pads a 1,2) |
| Centro da coluna castelada, das bordas | 0,5 mm |
| Centro da fileira LGA, das bordas | 2,5 mm (2,0 da coluna castelada) |
| Pad castelado lateral | 1,0 × 0,6 mm |
| Pad LGA interno | 1,0 × 0,8 mm |
| Pad castelado de baixo | 0,6 × 0,5 mm |
| Altura do corpo | **não consta no anúncio** |

## A antena manda no layout

O anúncio é explícito, e é regra de posicionamento, não recomendação:

> *"For the best Bluetooth performance, the antenna of the area need to
> extend about several mm without ground under the antenna of the edge of
> the host PCB."*

O desenho do próprio fabricante classifica três posições: **best** é o
módulo com a antena para fora da borda da placa hospedeira; **good** é no
canto, com a antena passando do plano de terra; **bad** é no meio da placa.

Isto substitui, com a mesma força, o que o ME54BS13 pedia (recorte sob a
antena e 4,7 mm de zona livre): o módulo continua **na ponta da placa, com a
antena virada para fora**, e o que muda é que a antena cerâmica pede
**extensão para fora do plano de terra**, não um vazado na placa. A faixa da
antena são os 3,8 mm entre a borda de cima e a primeira fileira de pads.

## O mapa de pinos do projeto

O mapa de hoje **não serve**, e não é detalhe de gosto: ele usa `i2c23` em
`P1.29` e `uart20` em `P1.31`, e no nRF54L15 a porta `P1` tem 16 pinos
(`P1.00` a `P1.15`) e o bloco 23 não existe. Os pinos abaixo seguem as
escolhas da **própria Nordic** nos arquivos do NCS:

| Periférico | Pinos | Onde a Nordic usa esses pinos |
|---|---|---|
| `spi00` | `SCK P2.01`, `MOSI P2.02`, `MISO P2.04` | `zephyr/boards/nordic/nrf54l15dk/nrf54l15dk_nrf54l_05_10_15-pinctrl.dtsi` |
| `i2c22` | `SCL P1.11`, `SDA P1.12` | `nrf/boards/shields/pca63565/boards/nrf54l15dk_nrf54l15_cpuapp.overlay` |
| `uart20` | `TX P1.04`, `RX P1.05` | o mesmo pinctrl do DK |

Isso importa porque o `SCL` de um TWIM e o `SCK` de um SPIM precisam de pino
com capacidade de clock, e escolher por conta é como o outro projeto perdeu
tempo. Os blocos `20`, `21` e `22` são **o mesmo periférico** em três
endereços: cada um serve como `i2c`, `spi` **ou** `uart`, um de cada vez.

| Sinal | Pino | # | Por quê |
|---|---|---|---|
| `SPI_SCK` | `P2.01` | 10 | `spi00`, o rápido, na porta P2 |
| `SPI_MOSI` | `P2.02` | 30 | idem |
| `SPI_MISO` | `P2.04` | 16 | idem |
| `ADC_CS` | `P2.05` | 8 | junto do barramento |
| `ADC_DRDY` | `P2.03` | 29 | idem |
| `IMU_CS` | `P2.07` | 28 | idem |
| `IMU_INT1` | `P2.08` | 11 | idem |
| `I2C_SCL` | `P1.11` | 34 | `i2c22`, pinos da Nordic |
| `I2C_SDA` | `P1.12` | 33 | idem |
| `UART_TX` | `P1.04` | 18 | `uart20`; sai pelo contato `D+` do conector |
| `UART_RX` | `P1.05` | 17 | idem, pelo `D−` |
| `EXC_EN` | `P2.06` | 27 | chave da excitação da ponte |
| `LED_R` | `P1.10` | 35 | |
| `LED_G` | `P1.13` | 21 | |
| `LED_B` | `P1.14` | 20 | |
| `SHPACT` | `P1.15` | 19 | do nPM1100 |
| `CHG_N` | `P1.09` | 22 | do nPM1100 |
| `ERR_N` | `P1.08` | 12 | do nPM1100 |
| `GAUGE_ALRT` | `P1.07` | 13 | do medidor de carga |
| **`VBUS_SENSE`** | `P1.06` | 14 | **novo**: sem USB, é assim que o aparelho sabe que o cabo entrou |
| `SWDIO` | `SWDIO` | 4 | pino dedicado |
| `SWDCLK` | `SWDCLK` | 5 | pino dedicado |
| `NRESET` | `NRESET` | 1 | pino dedicado |
| `VDD` | `VDD` | 15 | |
| `GND` | `GND` | 23, 36 | |

**20 GPIO de 30.** Sobram `P0.00` a `P0.04`, `P1.02`, `P1.03`, `P2.00`,
`P2.09` e `P2.10` — dez.

## O que falta confirmar

1. **A altura do corpo**, que não consta no anúncio e entra no teto da tampa
   do pod (`PD2`, hoje 2,7 mm com o ME54BS13 de 2,4).
2. **Quanto de folga a antena cerâmica pede**: o anúncio diz "several mm"
   sem número. Enquanto não houver número, o projeto mantém a zona livre que
   já usava, que é mais conservadora.
3. **Se o `NRESET` precisa de pull-up externo** no módulo.
4. As cotas, contra uma peça medida. Elas fecham entre si por três caminhos,
   mas um desenho de anúncio não é uma ficha assinada.
