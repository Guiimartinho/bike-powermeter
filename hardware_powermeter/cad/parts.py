#!/usr/bin/env python3
"""Every part of the crank pod board, with its pins.

The reference designators follow hardware_powermeter/05-materiais.md (the
first digit is the sheet: 1xx energy, 2xx MCU and debug, 3xx bridge and
converter, 4xx sensors); the pin numbers and names come from the
manufacturers' datasheets, read in the PDF and noted beside each part.

Pin NUMBERS are the dangerous part. A wrong number is a wrong netlist and a
wrong board, so a part whose numbering has not been read off the datasheet
carries `confirmed=False`, and its symbol says so on the drawing. Nothing
here is guessed: where the number is unknown the pin keeps its name as its
number and the part is marked.

Same conventions as the bike computer's parts.py (hardware_gnssbike/cad),
which this file mirrors on purpose: the two boards are read by the same
people with the same chain.
"""

from __future__ import annotations

from sch_lib import Part, Pin

# Sides: L and R for signals, T for supply, B for ground - the usual reading
# order of a schematic, and what keeps the wires off the bodies.
L, R, T, B = "L", "R", "T", "B"

PARTS: dict[str, Part] = {}
UNCONFIRMED: set[str] = set()


def add(ref: str, value: str, pins: list[tuple], *, confirmed: bool,
        note: str = "", footprint: str = "", lcsc: str = "") -> Part:
    """pins: (number, name, etype, side). number None means 'not read yet'."""
    ps = []
    for number, name, etype, side in pins:
        ps.append(Pin(str(number) if number is not None else name, name, etype, side))
    if not confirmed:
        UNCONFIRMED.add(ref)
        note = (note + " | PINAGEM NAO CONFIRMADA NA FICHA").strip(" |")
    p = Part(ref, value, tuple(ps), footprint=footprint, note=note, lcsc=lcsc)
    PARTS[ref] = p
    return p


def passive(ref: str, value: str, note: str = "", vertical: bool = False,
            lcsc: str = "") -> Part:
    """A two-terminal part. Pins 1 and 2 are the two ends, which is universal."""
    sides = (T, B) if vertical else (L, R)
    return add(ref, value, [(1, "1", "passive", sides[0]), (2, "2", "passive", sides[1])],
               confirmed=True, note=note, lcsc=lcsc)


# ================================================================ folha 1
# The magnetic charging and data connector: six pogo contacts in a row on
# the board's top face (the pod's outer face carries the mating plane),
# plus the two pads that hold the magnet frame. 5 V, GND, the USB pair and
# the SWD pair, so one cable charges, talks USB and programs the pod
# (docs/02, Conector magnetico).
#
# NO PART IS CHOSEN YET. Every supplier page tried on 2026-09-27 was
# unreachable from this machine, so this is a GENERIC 6-way magnetic pogo
# receptacle at 2,5 mm of pitch, drawn to be replaced: the numbering below
# is this project's, not a maker's, and 06-conectores-e-pontos-de-teste.md
# says so. Ground on contact 1 and 5 V on 2 so that a reversed plug (the
# magnets should not allow it, but a cable can be forced) puts 5 V on GND
# and GND on 5 V - a short the cable's supply survives - rather than on a
# data line.
add("J101", "conector magnetico 6 vias", [
    (1, "GND", "passive", R), (2, "VBUS", "power_out", R),
    (3, "D-", "passive", R), (4, "D+", "passive", R),
    (5, "SWDIO", "passive", R), (6, "SWCLK", "passive", R),
    ("MP1", "MP1", "passive", B), ("MP2", "MP2", "passive", B),
], confirmed=False,
    note="receptaculo magnetico de 6 pinos pogo, passo 2,5 mm, 1 A por pino, "
         "ouro; GENERICO: nenhuma ficha de fornecedor foi alcancada em "
         "2026-09-27, e o footprint e um lugar reservado a conferir com o "
         "desenho da peca escolhida (06-conectores-e-pontos-de-teste.md)")

# TI TPD4E05U06DQAR, SLVSBO7O, table 4-2 (DQA, USON-10): D1+ 1, D1- 2, GND 3
# and 8, D2+ 4, D2- 5, NC 6, 7, 9, 10. The four NC are on the nets on
# purpose: the table says "Not connected; used for optional straight-through
# routing" - the signal enters one side and leaves by the pin in front, which
# is the only way a pair crosses a 0,5 mm pitch part without going round it.
# 10 faces 1, 9 faces 2, 7 faces 4 and 6 faces 5.
add("D101", "TPD4E05U06DQAR", [
    (1, "D1P", "passive", L), (2, "D1N", "passive", L), (3, "GND1", "passive", B),
    (4, "D2P", "passive", R), (5, "D2N", "passive", R), (6, "NC1", "passive", R),
    (7, "NC2", "passive", R), (8, "GND2", "passive", B),
    (9, "NC3", "passive", R), (10, "NC4", "passive", R),
], confirmed=True, lcsc="C138714",
    note="ESD dos quatro sinais do conector: D+, D-, SWDIO e SWCLK; "
         "IEC 61000-4-2 12 kV contato, 0,5 pF por canal")

# Nordic nPM1100, Product Specification v1.5, table 24 (QFN24 pin
# assignment) and table 26 (QFN 4,0 x 4,0, D2/E2 2,70 nominal). Pins 13, 18
# and 24 are NC. The exposed pad is AVSS.
add("U101", "nPM1100-QDAB", [
    (17, "VBUS", "power_in", L), (20, "D+", "passive", L), (19, "D-", "passive", L),
    (5, "ISET", "input", L), (6, "SHPACT", "input", L), (11, "SHPHLD", "input", L),
    (7, "MODE", "input", L), (9, "VTERMSET", "input", L),
    (3, "VOUTBSET0", "input", L), (2, "VOUTBSET1", "input", L),
    (12, "ICHG", "passive", L), (14, "NTC", "passive", L),
    (16, "VSYS", "power_out", T), (15, "VBAT", "power_in", R), (22, "SW", "passive", R),
    (1, "VOUTB", "power_out", R), (21, "DEC", "passive", R),
    (8, "CHG", "open_collector", R), (10, "ERR", "open_collector", R),
    (4, "AVSS", "power_in", B), (23, "PVSS", "power_in", B), (25, "EP", "power_in", B),
    (13, "NC13", "no_connect", B), (18, "NC18", "no_connect", B), (24, "NC24", "no_connect", B),
], confirmed=True, lcsc="C2903119",
    note="carregador Li-ion de 20 a 400 mA (ICHG por resistor), buck de 3,0 V "
         "e 150 mA (VOUTBSET0 e VOUTBSET1 altos), VTERM 4,2 V (VTERMSET alto), "
         "deteccao de porta USB (ISET no AVSS: 100 mA em SDP, 500 mA em "
         "DCP/CDP), ship mode por SHPACT (PS v1.5, 3.5); QFN24 4 x 4. "
         "LCSC a conferir no pedido")

# Analog Devices MAX17048G+T10, datasheet 19-6171 rev 7, page 6 (pin
# descriptions, TDFN): CTG 1, CELL 2, VDD 3, GND 4, ALRT 5, QSTRT 6, SCL 7,
# SDA 8, EP to GND. CTG and QSTRT go to ground: CTG is "connect to ground"
# and QSTRT "connect to GND if not used".
add("U102", "MAX17048G+T10", [
    (2, "CELL", "no_connect", L), (6, "QSTRT", "input", L), (1, "CTG", "passive", L),
    (8, "SDA", "bidirectional", R), (7, "SCL", "input", R), (5, "ALRT", "open_collector", R),
    (3, "VDD", "power_in", T),
    (4, "GND", "power_in", B), (9, "EP", "power_in", B),
], confirmed=True, lcsc="C2680383",
    note="medidor de carga ModelGauge, 3 uA em hibernate, sem resistor de "
         "sentido: le a tensao da celula no VDD (CELL nao e ligado "
         "internamente no MAX17048); endereco 0x36. LCSC a conferir")

# The cell: a LiPo of 100 to 150 mAh with its own protection, on a JST SH of
# 1,0 mm pitch, side entry, 2,9 mm tall. The pack maker decides which contact
# is which; here 1 is the positive, as the usual red-wire-on-1 convention,
# and 06-conectores-e-pontos-de-teste.md sends that to the maker.
add("J102", "furos da celula", [
    (1, "1", "power_out", R), (2, "2", "passive", R),
], confirmed=True,
    note="dois furos metalizados de 0,9 mm a 2,5 de passo: 1 = VBAT+, 2 = GND. Nao ha conector - num pod envasado e vedado a IPX7 o fio soldado segura melhor que uma trava, e o JST SH de 2,90 mm era a peca mais alta da placa, que sozinha obrigava a tampa a subir"),

# Passives of the energy sheet. Values from the nPM1100 PS v1.5: table 28
# (configuration 1: 2,2 uF/25 V on VBUS, 22 uF on VOUTB, 1,0 uF on DEC),
# table 20 (inductor 2,2 uH, DCR <= 400 mOhm, Isat >= 350 mA), 6.2.4 (ICHG:
# R = 625 / I - 1562,5: 6,8 k gives 74,7 mA, half of a 150 mAh cell's
# capacity per hour), 6.2.5 (no thermistor: 10 kOhm from NTC to AVSS), 3.5
# (SHPHLD held high by a weak pull-up to VBAT). The MAX17048 asks for
# 0,1 uF on VDD (page 6).
passive("C101", "2,2 uF 25 V", "VBUS do nPM1100 (PS v1.5, tabela 28)")
passive("C102", "22 uF", "VOUTB do nPM1100, o trilho 3V0 (tabela 28)")
passive("C103", "1 uF", "DEC do nPM1100 (tabela 28)")
passive("C104", "10 uF", "VBAT junto do nPM1100 (PS v1.2 acrescentou o capacitor no VBAT)")
passive("C105", "100 nF", "VDD do MAX17048 (ficha, pagina 6)")
passive("C106", "100 nF", "VSYS: os pinos estaticos VOUTBSET e VTERMSET penduram nele")
passive("L101", "2,2 uH", "buck do nPM1100: <= 400 mOhm, Isat >= 350 mA (tabela 20); "
                          "Murata DFE201610E-2R2M, 2,0 x 1,6 mm", lcsc="C296426")
passive("R101", "6,8 k", "ICHG: 625/0,0747 - 1562,5; cerca de 75 mA (6.2.4)")
passive("R102", "10 k", "NTC ao AVSS sem termistor no pack (6.2.5)")
passive("R103", "100 k", "pull-up do CHG_N ao 3V0 (dreno aberto)")
passive("R104", "100 k", "pull-up do ERR_N ao 3V0 (dreno aberto)")
passive("R105", "100 k", "pull-up do GAUGE_ALRT ao 3V0 (dreno aberto)")
passive("R106", "1 M", "SHPHLD ao VBAT: o pull-up fraco que segura o ship mode (3.5)")
# The divider that replaces what the USB stack used to report. 1 M / 470 k
# takes the cable's 5,0 V to 1,60, a solid high on a 3,0 V input, and
# leaks 3,4 uA while the cable is in and nothing while it is out - which
# matters, because this hangs on VBUS and not on the cell.
passive("R109", "1 M", "divisor do VBUS, ramo de cima: 5,0 V viram 1,60")
passive("R110", "470 k", "divisor do VBUS, ramo de baixo, ao terra")
passive("R107", "100 R", "serie do SWDIO entre o conector magnetico e o modulo")
passive("R108", "100 R", "serie do SWCLK entre o conector magnetico e o modulo")

TESTE = (
    ("TP101", "VBUS", "o que o cabo entrega, no conector"),
    ("TP102", "VBAT", "a celula, no conector dela"),
    ("TP103", "3V0", "o buck do nPM1100, o trilho do sistema"),
    ("TP104", "GND", "terra, com via propria ao plano"),
    ("TP201", "UART_TX", "console do modulo"),
    ("TP202", "UART_RX", "console do modulo"),
    ("TP301", "3V0_EXC", "a excitacao da ponte, depois da chave"),
)
for _n, _rede, _o in TESTE:
    add(_n, "pad", [(1, "1", "passive", R)], confirmed=True, note="ponto de teste")

# ================================================================ folha 2
# HOLYIOT-26001-A pad map, from the maker's mechanical drawing read on
# 2026-09-28 and written up in 09-modulo-de-radio.md. 36 pads: a castellated
# column and an LGA column on each side, seven each, and eight castellations
# along the bottom. 30 of them are GPIO, and the three ports match the SoC's
# own `ngpios` in the NCS exactly (P0 has 7 and the module brings 5, P1 has
# 16 and it brings 14, P2 has 11 and it brings all 11).
#
# The numbering is NOT a formula and is written out for that reason: it runs
# down the left castellations, left to right along the bottom, UP the right
# castellations, then down the left LGA column and UP the right one.
PADS_HOLYIOT = {
    # 1..7, left castellations, top to bottom
    "NRESET": "1", "P0.02": "2", "P0.01": "3", "SWDIO": "4", "SWDCLK": "5",
    "P2.10": "6", "P2.09": "7",
    # 8..15, bottom row, left to right
    "P2.05": "8", "P2.00": "9", "P2.01": "10", "P2.08": "11", "P1.08": "12",
    "P1.07": "13", "P1.06": "14", "VDD": "15",
    # 16..22, right castellations, bottom to top
    "P2.04": "16", "P1.05": "17", "P1.04": "18", "P1.15": "19", "P1.14": "20",
    "P1.13": "21", "P1.09": "22",
    # 23..29, left LGA column, top to bottom
    "GND1": "23", "P0.03": "24", "P0.00": "25", "P0.04": "26", "P2.06": "27",
    "P2.07": "28", "P2.03": "29",
    # 30..36, right LGA column, bottom to top
    "P2.02": "30", "P1.03": "31", "P1.02": "32", "P1.12": "33", "P1.11": "34",
    "P1.10": "35", "GND2": "36",
}
# The port pins this board wires, docs/02-hardware.md "Pinos do modulo".
# Every bus pin below is the one NORDIC uses in the NCS for that peripheral
# on this SoC, not a choice made here: a TWIM's SCL and a SPIM's SCK need a
# clock-capable pin, and the DK's pinctrl and the pca63565 shield are the
# evidence (09-modulo-de-radio.md, O mapa de pinos do projeto).
_GPIO = [
    # left side: the energy block, the LED and the console
    ("P1.10", L), ("P1.13", L), ("P1.14", L), ("P1.15", L), ("P1.09", L),
    ("P1.08", L), ("P1.07", L), ("P1.06", L), ("P1.04", L), ("P1.05", L),
    # right side: the buses of the bridge and the sensors
    ("P2.01", R), ("P2.02", R), ("P2.04", R), ("P2.05", R), ("P2.03", R),
    ("P2.06", R), ("P2.07", R), ("P2.08", R), ("P1.11", R), ("P1.12", R),
]
# No VBUS pin: the ME54BS13 had one because it had USB, and this SoC has
# none. Pin 9 of this module is P2.00, a plain GPIO, and wiring VBUS to it
# would put 5 V on a 3,0 V input. The board learns that the cable is in from
# a divider on VBUS into VBUS_SENSE instead.
_mod = [("15", "VDD", "power_in", T),
        ("4", "SWDIO", "bidirectional", L), ("5", "SWDCLK", "input", L),
        ("1", "NRESET", "input", L),
        ("23", "GND1", "power_in", B), ("36", "GND2", "power_in", B)]
for _pp, _lado in _GPIO:
    _mod.append((PADS_HOLYIOT[_pp], _pp, "bidirectional", _lado))
add("U201", "HOLYIOT-26001-A", _mod, confirmed=False,
    note="nRF54L15, 10,0 x 12,5 mm, 36 pads (22 castelados + 14 LGA), antena "
         "CERAMICA integrada. Sem USB: o usbhs nao existe neste SoC, entao a "
         "serial dos comandos e a recuperacao do MCUboot vao por UART nos "
         "contatos D+/D- do conector, e um divisor no VBUS num GPIO diz que o "
         "cabo entrou. A ALTURA do corpo nao consta no anuncio e esta com 2,40 "
         "de reserva: ela decide o teto da tampa do pod. Cotas do desenho do "
         "anuncio, nao de peca medida (09-modulo-de-radio.md)")

# The module's own decoupling and the pi filter footprint its datasheet
# asks for on a switched supply (7.2, Power Supply Design): a ferrite in
# series with a capacitor each side, 100 nF at 0,5 mm of the pin.
passive("FB201", "600 R @ 100 MHz", "filtro pi do modulo: Murata BLM15PX601SN1D",
        lcsc="C76909")
passive("C201", "100 nF", "VDD do modulo, a 0,5 mm do pad 19 (ficha 7.2)")
passive("C202", "4,7 uF", "reserva do modulo, lado do modulo do ferrite")
passive("C203", "4,7 uF", "reserva do modulo, lado do trilho do ferrite")


# TUOZHAN S4-3528RGBTA-A, datasheet S35210052: common anode, pins 1 blue,
# 2 anode, 3 green, 4 red, the chamfered corner beside the red. The same
# part and body as the bike computer's D601 (LCSC C2827321). The anode
# hangs on VSYS (3,0 to 4,2 V on the cell, 5 V on the cable) and each
# cathode is sunk by a GPIO through a resistor: with the GPIO high at 3,0 V
# and the anode at 5 V the blue (Vf 2,8 to 3,4) sees 2 V and stays off.
add("D201", "TUOZHAN S4-3528RGBTA-A", [
    ("A", "ANODO", "passive", T), ("KR", "K_R", "passive", B),
    ("KG", "K_G", "passive", B), ("KB", "K_B", "passive", B),
], confirmed=True, lcsc="C2827321",
    note="LED RGB de ANODO COMUM, 3,5 x 2,8 x 1,9 mm; pinos da ficha "
         "S35210052: 1 azul, 2 anodo, 3 verde, 4 vermelho")
passive("R201", "1,5 k", "catodo vermelho: (5 - 2,0) / 1,5 k = 2 mA no cabo, 0,7 mA na celula")
passive("R202", "1,5 k", "catodo verde")
passive("R203", "1,5 k", "catodo azul")
passive("R204", "4,7 k", "pull-up do I2C_SDA, junto do mestre")
passive("R205", "4,7 k", "pull-up do I2C_SCL, junto do mestre")

# ================================================================ folha 3
# The strain gauge bridge reaches the board by five solder pads at the edge
# nearest the converter: excitation +, signal +, signal -, excitation - and
# the cable's shield. Four wires plus a shield, hand soldered; the pads
# carry no paste.
add("J301", "furos da ponte", [
    ("1", "E+", "passive", R), ("2", "S+", "passive", R), ("3", "S-", "passive", R),
    ("4", "E-", "passive", R), ("5", "SH", "passive", R),
], confirmed=True,
    note="cinco furos metalizados de 0,9 mm em ilhas de 1,5 a 2,0 de passo, sem "
         "pasta: ponte completa de 1 kOhm (docs/06); a blindagem do cabo no "
         "quinto furo; os fios sobem do braco pelo rasgo do fundo do pod")

# TI ADS1220IRVAR, SBAS501D, table 5-1 (RVA, VQFN-16): AIN0/REFP1 9, AIN1 8,
# AIN2 5, AIN3/REFN1 4, AVDD 10, AVSS 3, CLK 1 (to DGND: internal
# oscillator), CS 16, DGND 2, DIN 14, DOUT/DRDY 13, DRDY 12, DVDD 11, REFN0
# 6, REFP0 7, SCLK 15; the thermal pad "do not connect or only connect to
# AVSS" - it goes to AVSS, which is GND here.
add("U301", "ADS1220IRVAR", [
    (9, "AIN0", "input", L), (8, "AIN1", "input", L), (5, "AIN2", "no_connect", L),
    (4, "AIN3", "no_connect", L), (7, "REFP0", "input", L), (6, "REFN0", "input", L),
    (1, "CLK", "input", L),
    (16, "CS", "input", R), (15, "SCLK", "input", R), (14, "DIN", "input", R),
    (13, "DOUT", "tri_state", R), (12, "DRDY", "output", R),
    (10, "AVDD", "power_in", T), (11, "DVDD", "power_in", T),
    (3, "AVSS", "power_in", B), (2, "DGND", "power_in", B), (17, "PAD", "power_in", B),
], confirmed=True, lcsc="C123398",
    note="conversor de 24 bits da ponte: ganho 128, 175 SPS, referencia "
         "externa REFP0/REFN0 na excitacao (ratiometrico, 9.2.3 da ficha); "
         "AIN2 e AIN3 ficam abertos e o firmware nunca os seleciona. "
         "LCSC a conferir")

# TI TPS22916BYFPR, SLVSDO5F, table 5-1 (YFP, 4 bumps): A1 VOUT, A2 VIN, B1
# GND, B2 ON. The B version: 140 us of turn-on at 3,6 V (6.6), against the
# 3000 us of the C version at 1,8 V - the excitation has to stand 1,5 ms
# before each conversion (docs/06), so the slow one would never make it.
add("U302", "TPS22916BYFPR", [
    ("A2", "VIN", "power_in", L), ("B2", "ON", "input", L),
    ("A1", "VOUT", "power_out", R), ("B1", "GND", "power_in", B),
], confirmed=True, lcsc="C2917017",
    note="chave da excitacao da ponte, 60 a 200 mOhm, 10 nA desligada, "
         "pull-down inteligente no ON (nao precisa de resistor); versao B, "
         "a rapida. LCSC a conferir")

# The input and reference filters of figure 9-11 of SBAS501D (RF1, RF2,
# CDIF1, CCM1, CCM2 on the inputs, CDIF2 on the reference): first order,
# the differential capacitor ten times the common-mode ones so that a
# mismatch of the two common-mode parts does not turn into a differential
# error, C0G as 9.4.1 asks. 1 k with 47 nF is a differential corner of
# 1,7 kHz and 1 k with 4,7 nF a common-mode corner of 34 kHz: far above the
# 20 Hz of the pedal stroke and below nothing the sinc filter needs. The
# reference gets only the capacitor, as the figure draws it: a series
# resistor there would take the reference off the excitation node and the
# measurement would stop being ratiometric ("care must be taken to
# maintain a limited amount of filtering", 9.2.3.2).
passive("R301", "1 k", "RF1: serie do S+ ate AIN0")
passive("R302", "1 k", "RF2: serie do S- ate AIN1")
passive("C301", "47 nF C0G", "CDIF1: diferencial entre AIN0 e AIN1")
passive("C302", "4,7 nF C0G", "CCM1: AIN0 ao terra")
passive("C303", "4,7 nF C0G", "CCM2: AIN1 ao terra")
passive("C304", "100 nF", "CDIF2: entre REFP0 e REFN0, na referencia")
passive("C305", "100 nF", "AVDD do ADS1220 (9.3.3)")
passive("C306", "100 nF", "DVDD do ADS1220 (9.3.3)")
passive("C307", "100 nF", "VOUT da chave: a excitacao assenta em menos de 1 ms")
passive("C308", "1 uF", "VIN da chave, junto dela")

# ================================================================ folha 4
# Bosch BMA400, BST-BMA400-DS000-14 rev 2.3, section 7.1 (pin-out, LGA-12):
# 1 SDO, 2 SDX (SDI in SPI 4W), 3 VDDIO, 4 NC, 5 INT1, 6 INT2, 7 VDD, 8
# GNDIO, 9 GND, 10 CSB, 11 NC, 12 SCX (SCK). SPI 4-wire: CSB, SCK, SDI, SDO,
# INT1 to the MCU; INT2 unused ("if not used, do not connect").
add("U401", "BMA400", [
    (10, "CSB", "input", L), (12, "SCX", "input", L), (2, "SDX", "input", L),
    (1, "SDO", "tri_state", L),
    (5, "INT1", "output", R), (6, "INT2", "no_connect", R),
    (7, "VDD", "power_in", T), (3, "VDDIO", "power_in", T),
    (9, "GND", "power_in", B), (8, "GNDIO", "power_in", B),
    (4, "NC4", "no_connect", B), (11, "NC11", "no_connect", B),
], confirmed=True, lcsc="C542206",
    note="acelerometro de 3 eixos, 2 x 2 x 0,95 mm, 14,5 uA em modo normal "
         "(OSR 3), 850 nA em low power a 25 Hz; SPI de 4 fios, INT1 para o "
         "modulo. LCSC a conferir")

# TI TMP117AIDRVR, SNOSD82D, table 5-1 (DRV, WSON-6): SCL 1, GND 2, ALERT 3,
# ADD0 4, V+ 5, SDA 6; thermal pad 7 (page 40). ADD0 to GND: address 0x48.
# ALERT is not used: open-drain, left open.
add("U402", "TMP117AIDRVR", [
    (1, "SCL", "input", L), (6, "SDA", "bidirectional", L), (4, "ADD0", "input", L),
    (3, "ALERT", "no_connect", R),
    (5, "V+", "power_in", T),
    (2, "GND", "power_in", B), (7, "EP", "power_in", B),
], confirmed=True, lcsc="C2687591",
    note="temperatura da ponte, +-0,1 C de -20 a 50 C, 3,5 uA a 1 Hz; "
         "ADD0 ao GND = 0x48; colocado ao lado dos furos da ponte. LCSC a conferir")
passive("C401", "100 nF", "VDD do BMA400")
passive("C402", "100 nF", "VDDIO do BMA400")
passive("C403", "100 nF", "V+ do TMP117 (ficha: 0,1 uF junto do pino)")


if __name__ == "__main__":
    print(f"{len(PARTS)} pecas, {sum(len(p.pins) for p in PARTS.values())} pinos")
    if UNCONFIRMED:
        print("pinagem nao confirmada na ficha: " + ", ".join(sorted(UNCONFIRMED)))
