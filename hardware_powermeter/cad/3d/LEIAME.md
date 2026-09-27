# Corpos 3D das peças

Das 113 peças da placa, **85 usam o modelo STEP da própria biblioteca do
KiCad** e aparecem sem que ninguém faça nada. As **18** desta página o KiCad
não tem, e para elas este projeto **desenha uma caixa** com a medida do
encapsulamento. As outras 5 (o furo M2, os três pontos de teste e os pads do
Tag-Connect) não têm corpo, e isso está certo: um ponto de teste é um pad.

> [!NOTE]
> Os `.wrl` desta pasta são **gerados** por
> [`../footprints.py`](../footprints.py) a cada `make_pcb.py`. Não os edite:
> a próxima execução os reescreve.

## Como pôr um modelo de verdade

Baixe o STEP do fabricante (ou do SnapEDA, Ultra Librarian, Mouser, DigiKey)
e salve em **`3d/real/`** com o **nome do footprint**. O gerador prefere o que
estiver lá e nem escreve a caixa:

```text
cad/3d/real/SW_SPST_B3S-1000.step
cad/3d/real/USB_C_Receptacle_Palconn_UTC16-G.step
```

Aceita `.step`, `.stp` e `.wrl`, nessa ordem. **STEP é melhor**: é o único
formato que a exportação GLB e STEP do KiCad lê, então só ele aparece na
imagem gerada por `make_3d.py`. Um `.wrl` aparece apenas no visualizador 3D
do KiCad.

> [!WARNING]
> **`3d/real/` não vai para o repositório.** Este repositório é público e um
> modelo 3D de fabricante vem com os termos do fabricante — a mesma razão que
> mantém as fichas fora de [`../../datasheets/`](../../datasheets/). O
> `.gitignore` da pasta cuida disso. Os `.wrl` gerados também ficam de fora,
> como todo arquivo gerado neste repositório: quem os reconstrói é o
> `make_pcb.py`. O que é versionado é o **gerador**, em
> [`../footprints.py`](../footprints.py).

## As 18 peças, e o que procurar

Nome do footprint é o nome do arquivo a salvar em `3d/real/`.

| Footprint | Peça a procurar | Medida usada (mm) | Altura: de onde veio |
|---|---|---|---|
| `SW_SPST_B3S-1000` | Omron **B3S-1002P** | 6,00 × 6,60 × **5,00** | corpo de 3,5 mais o botão — **conferir na ficha da Omron** |
| `USB_C_Receptacle_Palconn_UTC16-G` | Molex **2036150003** | 8,94 × 7,32 × **3,26** | altura corrente de receptáculo USB-C — **conferir na ficha do Molex** |
| `Buzzer_CUI_CPT-9019S-SMT` | CUI **CPT-1117-83-SMT** | 9,00 × 9,00 × **3,00** | **conferir**: a lista de compras traz o CPT-1117, não o CPT-9019S |
| `TE_0-1734839-5_1x05-1MP_P0.5mm_Horizontal` | Molex **503480-0500** | 7,93 × 4,40 × **1,20** | **conferir**: a peça ainda não está escolhida ([06](../../06-conectores-e-pontos-de-teste.md)) |
| `SOIC-8_5.23x5.23mm_P1.27mm` | Macronix **MX25R6435F** | 5,23 × 5,23 × 2,00 | altura normal do SOIC-8 |
| `QFN-28-1EP_4x4mm_P0.4mm_EP2.3x2.3mm` | e-peas **AEM10900** | 4,00 × 4,00 × 0,90 | altura normal de um QFN |
| `Texas_X2SON-4_1x1mm_P0.65mm` | TI **TPS7A0218PDQN** | 1,00 × 1,00 × 0,40 | altura normal do X2SON |
| `SOT-523` | Diodes **DMG1012T-7** | 0,80 × 1,60 × 0,60 | altura normal do SOT-523 |
| `MinewSemi_ME54BS13_16.5x12mm` | MinewSemi **ME54BS13** | 12,00 × 16,50 × 2,40 | **ficha V1.0.0, desenho mecânico** |
| `u-blox_MAX-F10S_9.7x10.1mm` | u-blox **MAX-F10S** | 9,70 × 10,10 × 2,40 | medida do encapsulamento MAX |
| `MAX17262_WLP-9_1.4x1.4mm_P0.4mm` | Analog **MAX17262REWL** | 1,40 × 1,40 × 0,50 | ficha |
| `BMP585_LGA-8_3.25x3.25mm` | Bosch **BMP585** | 3,25 × 3,25 × 1,96 | ficha |
| `MMC5633_WLP-4_0.85x0.85mm` | MEMSIC **MMC5633NJL** | 0,85 × 0,85 × 0,40 | ficha |
| `OPT3001_USON-6_2x2mm_P0.65mm` | TI **OPT3001DNPR** | 2,00 × 2,00 × 0,65 | ficha |
| `TXU0204_WQFN-14_3x2.5mm_P0.5mm` | TI **TXU0204BQAR** | 3,00 × 2,50 × 0,80 | ficha |
| `TPD4E05U06_USON-10_1x2.5mm_P0.5mm` | TI **TPD4E05U06DQAR** | 1,00 × 2,50 × 0,55 | ficha |
| `ESD761_X1SON-2_1x0.6mm` | **ESD761DPYR** | 1,00 × 0,60 × 0,45 | ficha |
| `LED_RGB_APTF1616_1.6x1.6mm` | Kingbright **APTF1616SEEZGKQBKC** | 1,60 × 1,60 × 0,70 | ficha |

### As duas que valem mais a pena

Os dois módulos são os únicos desenhados com mais de um bloco, porque neles a
forma diz alguma coisa:

- **ME54BS13** — substrato de 12,00 × 16,50 × 0,80 mm, blindagem metálica de
  1,60 mm sobre tudo **menos os 4,46 mm da ponta**, que é a antena e fica
  aberta. É o que o desenho mecânico da ficha V1.0.0 mostra, e é o que
  permite ver na imagem que a antena olha para a borda.
- **MAX-F10S** — substrato mais blindagem sobre a peça inteira, que é por que
  o manual de integração pode pedir terra por baixo dela ([§4.4](../../08-dry-run-2026-09-27.md)).

**Nenhum dos dois fabricantes publica STEP.** A página do ME54BS13 na
MinewSemi e a loja deles listam só a ficha; a da u-blox não responde a
requisição automática. Por isso esses dois foram **desenhados a partir das
cotas**, não baixados.

## Prioridade, se for baixar

Só quatro alturas mudam alguma coisa, e são as das peças altas, que decidem se
a tampa fecha: a **tecla** (5,0 mm), o **USB-C** (3,26), o **buzzer** (3,0) e
o **conector da luz** (1,2). As outras catorze ficam abaixo de 2,4 mm, bem
dentro dos 2,6 mm que a sombra do display deixa
([04](../../04-placa.md#zonas-proibidas)).
