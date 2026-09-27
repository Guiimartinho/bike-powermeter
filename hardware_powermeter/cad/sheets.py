#!/usr/bin/env python3
"""Which sheet each part belongs to, and how each net leaves its sheet.

A schematic of this size is not drawn on one page. It is drawn the way a
board is built: one sheet per block, a root sheet that shows the blocks and
the signals between them, supply rails carried by power symbols instead of by
lines, and only the signals that really cross a block boundary leaving the
sheet at all. The same pattern as the bike computer's (hardware_gnssbike/cad/
sheets.py), which is what the owner asked for on 2026-09-27.

Three kinds of net, and each is drawn differently:

  RAIL     a supply or a ground. It gets a power symbol wherever it touches a
           pin. KiCad joins every power symbol of the same name into one net
           across the whole design.
  ENTRE    a signal whose pins sit on more than one sheet. It gets a
           hierarchical label on each sheet and a pin on each block of the
           root, and the root draws the line between the blocks.
  DENTRO   a signal whose pins are all on one sheet. It is only a wire.
"""

from __future__ import annotations

import nets as N
import parts as P

# The four sheets of 02-esquematico.md, in the order they are read.
FOLHAS: list[tuple[str, str, str]] = [
    ("1 Energia", "folha1-energia.kicad_sch", "2"),
    ("2 MCU e depuracao", "folha2-mcu.kicad_sch", "3"),
    ("3 Ponte e conversor", "folha3-ponte.kicad_sch", "4"),
    ("4 Sensores", "folha4-sensores.kicad_sch", "5"),
]

# Reference prefixes to sheet, by the first digit of the number: 1xx is the
# energy sheet, 2xx the MCU, 3xx the bridge, 4xx the sensors, which is how
# 05-materiais.md numbers them. This is the only rule; nothing is placed by
# hand. Nothing overrides it on this board: the SWD series resistors are
# numbered on the energy sheet because they sit beside the connector, and
# they are drawn there too.
SEGUE: dict[str, str] = {}

_FOLHA_DE: dict[str, str] = {}


def sheet_of(ref: str) -> str:
    """The sheet of a part: its chip's sheet when it serves a chip, else the
    sheet its number says.

    A decoupling capacitor is drawn beside the chip it decouples, whatever
    its number. make_pcb.DECOPLA and JUNTO already say whose each of them
    is, for the board; the schematic follows the same tables.
    """
    if ref in _FOLHA_DE:
        return _FOLHA_DE[ref]
    from make_pcb import DECOPLA, JUNTO
    from blocos import BLOCOS
    # A part that heads a block of the schematic is drawn on the sheet its
    # number says, whatever the board does with it: the TMP117 sits beside
    # the bridge pads on the board (make_pcb.JUNTO) and is still the
    # temperature block of the sensors sheet.
    cabecas = {r for blocos in BLOCOS.values() for _t, refs in blocos for r in refs}
    base = ref
    vistos = set()
    while base not in vistos:
        vistos.add(base)
        if base in cabecas:
            break
        anc = SEGUE.get(base) or DECOPLA.get(base) or JUNTO.get(base)
        if anc is None or anc not in P.PARTS:
            break
        base = anc
    digitos = "".join(c for c in base if c.isdigit())
    n = int(digitos[0]) if digitos else 1
    _FOLHA_DE[ref] = FOLHAS[min(max(n, 1), len(FOLHAS)) - 1][0]
    return _FOLHA_DE[ref]


# Supplies and grounds. Everything here is drawn with power symbols.
TRILHOS: dict[str, bool] = {   # name -> is it a ground
    "GND": True,
    "VBUS": False, "VBAT": False, "VSYS": False,
    "3V0": False, "3V0_MOD": False, "3V0_EXC": False,
}


def classificar() -> tuple[dict[str, str], dict[str, set[str]]]:
    """Give each net its kind, and for the ones that leave, which sheets."""
    tipo: dict[str, str] = {}
    folhas_do_no: dict[str, set[str]] = {}
    for nome, pinos in N.NETS.items():
        folhas = {sheet_of(ref) for ref, _pin in pinos}
        folhas_do_no[nome] = folhas
        if nome in TRILHOS:
            tipo[nome] = "RAIL"
        elif len(folhas) > 1:
            tipo[nome] = "ENTRE"
        else:
            tipo[nome] = "DENTRO"
    return tipo, folhas_do_no


def por_folha() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {nome: [] for nome, _f, _p in FOLHAS}
    for ref in P.PARTS:
        out[sheet_of(ref)].append(ref)
    for k in out:
        out[k].sort(key=lambda r: (-len(P.PARTS[r].pins), r))
    return out


if __name__ == "__main__":
    tipo, folhas = classificar()
    dist = por_folha()
    print(f"{len(P.PARTS)} posicoes em {len(FOLHAS)} folhas")
    for nome, _f, _p in FOLHAS:
        print(f"  {nome}: {len(dist[nome])} pecas")
    for t in ("RAIL", "ENTRE", "DENTRO"):
        quais = [n for n, k in tipo.items() if k == t]
        print(f"{t}: {len(quais)}")
        if t == "ENTRE":
            for n in sorted(quais):
                print(f"    {n}: {', '.join(sorted(folhas[n]))}")
