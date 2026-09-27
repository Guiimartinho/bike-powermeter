#!/usr/bin/env python3
"""Every net of the crank pod board, as (reference, pin name).

This is hardware_powermeter/03-netlist.md turned into data. The pin NAME is
used, not the number, because that is what the documents state; parts.py
turns the name into the number the symbol carries.

The pin map of the module is the one of docs/02-hardware.md ("Pinos do
modulo"), which the firmware's board devicetree follows too; the two are
compared by check_sch.py against what KiCad extracts, pin by pin.

Two rules were kept while writing this, as on the bike computer:

  - nothing that the documents do not state is wired here. Where a document
    leaves a connection open, the net is listed in ABERTO instead;
  - where a datasheet forces a tie (ISET to AVSS, CTG and QSTRT to ground,
    CLK to DGND), the tie is a plain wire to the rail, not a resistor.
"""

from __future__ import annotations

# The only parts whose pin may appear in two nets: a connector and the part
# behind it are one electrical node, and the schematic draws them as two.
# ANY OTHER pin in two nets is a short, and check_sch.py fails on it.
PASSA_DIRETO: set[str] = set()

# name -> [(ref, pin name), ...]
NETS: dict[str, list[tuple[str, str]]] = {}

# things a document explicitly leaves open: name -> why
ABERTO: dict[str, str] = {}


def net(name: str, *pins: tuple[str, str]) -> None:
    NETS[name] = list(pins)


# ------------------------------------------------------------ alimentacao
# 5 V of the cable, through the magnetic connector, into the PMIC's SYSREG
# and the module's USB detector (pad 9 is the VBUS pin of the SoC's PHY).
net("VBUS", ("J101", "VBUS"), ("U101", "VBUS"), ("C101", "1"), ("U201", "VBUS"),
    ("TP101", "1"))
# The cell, with the gauge reading it at VDD and the PMIC charging it; the
# weak pull-up of SHPHLD hangs on it (PS v1.5, 3.5).
net("VBAT", ("J102", "1"), ("U101", "VBAT"), ("C104", "1"), ("U102", "VDD"),
    ("C105", "1"), ("R106", "1"), ("TP102", "1"))
# VSYS: the PMIC's power path output (cell or cable). It feeds the buck
# internally; outside it only holds the static pins high and the LED's
# anode (docs/02).
net("VSYS", ("U101", "VSYS"), ("C106", "1"), ("U101", "VOUTBSET0"),
    ("U101", "VOUTBSET1"), ("U101", "VTERMSET"), ("D201", "ANODO"))
net("BUCK_SW", ("U101", "SW"), ("L101", "1"))
net("DEC", ("U101", "DEC"), ("C103", "1"))
# 3V0: the buck output, the rail of everything (docs/02, Blocos e trilhos)
net("3V0", ("L101", "2"), ("U101", "VOUTB"), ("C102", "1"), ("TP103", "1"),
    ("R103", "1"), ("R104", "1"), ("R105", "1"), ("R204", "1"), ("R205", "1"),
    ("FB201", "1"), ("C203", "1"), ("J201", "VTref"),
    ("U301", "AVDD"), ("U301", "DVDD"), ("C305", "1"), ("C306", "1"),
    ("U302", "VIN"), ("C308", "1"),
    ("U401", "VDD"), ("U401", "VDDIO"), ("C401", "1"), ("C402", "1"),
    ("U402", "V+"), ("C403", "1"))
# the module's supply, behind the ferrite of its pi filter
net("3V0_MOD", ("FB201", "2"), ("U201", "VDD"), ("C201", "1"), ("C202", "1"))
# the bridge excitation, switched: the load switch's output, the bridge's
# E+ pad and the converter's positive reference (ratiometric)
net("3V0_EXC", ("U302", "VOUT"), ("C307", "1"), ("J301", "E+"), ("U301", "REFP0"),
    ("C304", "1"), ("TP301", "1"))
net("GND",
    ("J101", "GND"), ("J101", "MP1"), ("J101", "MP2"),
    ("D101", "GND1"), ("D101", "GND2"),
    ("U101", "AVSS"), ("U101", "PVSS"), ("U101", "EP"), ("U101", "ISET"), ("U101", "MODE"),
    ("C101", "2"), ("C102", "2"), ("C103", "2"), ("C104", "2"), ("C105", "2"), ("C106", "2"),
    ("R101", "2"), ("R102", "2"),
    ("U102", "GND"), ("U102", "EP"), ("U102", "CTG"), ("U102", "QSTRT"),
    ("J102", "2"), ("TP104", "1"),
    ("U201", "GND"), ("U201", "GND3"), ("U201", "GND10"), ("U201", "GND11"),
    ("U201", "GND20"), ("U201", "GND_D0"), ("U201", "GND_E0"), ("U201", "GND_F0"),
    ("C201", "2"), ("C202", "2"), ("C203", "2"), ("J201", "GND"),
    ("U301", "AVSS"), ("U301", "DGND"), ("U301", "PAD"), ("U301", "CLK"), ("U301", "REFN0"),
    ("C302", "2"), ("C303", "2"), ("C304", "2"), ("C305", "2"), ("C306", "2"),
    ("C307", "2"), ("C308", "2"), ("J301", "E-"), ("J301", "SH"), ("U302", "GND"),
    ("U401", "GND"), ("U401", "GNDIO"), ("C401", "2"), ("C402", "2"),
    ("U402", "GND"), ("U402", "EP"), ("U402", "ADD0"), ("C403", "2"))

# ------------------------------------------------------ conector e USB
# The USB pair: connector, ESD array (in one pin, out by the pin in front),
# the module's PHY and the PMIC's port detector, which the PS v1.5 (7.3)
# connects to the same lines as the SoC on purpose.
net("USB_DP", ("J101", "D+"), ("D101", "D1P"), ("D101", "NC4"), ("U201", "USB_DP"),
    ("U101", "D+"))
net("USB_DM", ("J101", "D-"), ("D101", "D1N"), ("D101", "NC3"), ("U201", "USB_DM"),
    ("U101", "D-"))
# SWD from the cable: through the ESD array and 100 R in series into the
# module's SWD pads, which the Tag-Connect reaches directly.
net("SWDIO_J", ("J101", "SWDIO"), ("D101", "D2P"), ("D101", "NC2"), ("R107", "1"))
net("SWCLK_J", ("J101", "SWCLK"), ("D101", "D2N"), ("D101", "NC1"), ("R108", "1"))
net("SWDIO", ("R107", "2"), ("U201", "SWDIO"), ("J201", "SWDIO"))
net("SWDCLK", ("R108", "2"), ("U201", "SWDCLK"), ("J201", "SWDCLK"))
net("RESET", ("U201", "RESET"), ("J201", "RESET"))

# --------------------------------------------------------------- energia
net("ICHG", ("U101", "ICHG"), ("R101", "1"))
net("NTC", ("U101", "NTC"), ("R102", "1"))
net("SHPHLD", ("U101", "SHPHLD"), ("R106", "2"))
net("SHPACT", ("U101", "SHPACT"), ("U201", "P1.25"))
net("CHG_N", ("U101", "CHG"), ("R103", "2"), ("U201", "P1.11"))
net("ERR_N", ("U101", "ERR"), ("R104", "2"), ("U201", "P1.12"))
net("GAUGE_ALRT", ("U102", "ALRT"), ("R105", "2"), ("U201", "P1.22"))

# ------------------------------------------------------------ MCU e LED
net("I2C_SDA", ("U201", "P1.29"), ("R204", "2"), ("U102", "SDA"), ("U402", "SDA"))
net("I2C_SCL", ("U201", "P1.03"), ("R205", "2"), ("U102", "SCL"), ("U402", "SCL"))
net("LED_R", ("U201", "P1.06"), ("R201", "2"))
net("LED_G", ("U201", "P1.08"), ("R202", "2"))
net("LED_B", ("U201", "P1.09"), ("R203", "2"))
net("LED_KR", ("R201", "1"), ("D201", "K_R"))
net("LED_KG", ("R202", "1"), ("D201", "K_G"))
net("LED_KB", ("R203", "1"), ("D201", "K_B"))
net("UART_TX", ("U201", "P1.00"), ("TP201", "1"))
net("UART_RX", ("U201", "P1.31"), ("TP202", "1"))

# ------------------------------------------------- ponte e conversor
net("EXC_EN", ("U201", "P1.10"), ("U302", "ON"))
net("BR_SP", ("J301", "S+"), ("R301", "1"))
net("BR_SN", ("J301", "S-"), ("R302", "1"))
net("AIN_P", ("R301", "2"), ("U301", "AIN0"), ("C301", "1"), ("C302", "1"))
net("AIN_N", ("R302", "2"), ("U301", "AIN1"), ("C301", "2"), ("C303", "1"))
# the SPI of the bridge and the accelerometer, spi00 of port P2
net("SPI_SCK", ("U201", "P2.01"), ("U301", "SCLK"), ("U401", "SCX"))
net("SPI_MOSI", ("U201", "P2.02"), ("U301", "DIN"), ("U401", "SDX"))
net("SPI_MISO", ("U201", "P2.04"), ("U301", "DOUT"), ("U401", "SDO"))
net("ADC_CS", ("U201", "P2.05"), ("U301", "CS"))
net("ADC_DRDY", ("U201", "P2.03"), ("U301", "DRDY"))
net("IMU_CS", ("U201", "P2.07"), ("U401", "CSB"))
net("IMU_INT1", ("U201", "P2.08"), ("U401", "INT1"))

ABERTO["J101"] = ("o conector magnetico nao tem peca escolhida: a numeracao dos "
                  "contatos e deste projeto e o footprint e generico, a trocar "
                  "pelo desenho do fornecedor (06-conectores-e-pontos-de-teste.md)")
ABERTO["J102"] = ("qual contato do JST SH e o positivo e decisao do fabricante do "
                  "pack: aqui 1 = VBAT+, 2 = GND, a mandar por escrito com o pedido")


if __name__ == "__main__":
    import parts as P

    pinos = {(r, n) for pins in NETS.values() for r, n in pins}
    todos = {(ref, q.name) for ref, p in P.PARTS.items() for q in p.pins
             if q.etype != "no_connect"}
    print(f"{len(NETS)} nos, {len(pinos)} pinos ligados de {len(todos)} ligaveis")
    soltos = sorted(todos - pinos)
    if soltos:
        print("sem no: " + ", ".join(f"{r}.{n}" for r, n in soltos))
    ruins = sorted(pinos - {(ref, q.name) for ref, p in P.PARTS.items() for q in p.pins})
    if ruins:
        print("pino que nao existe: " + ", ".join(f"{r}.{n}" for r, n in ruins))
