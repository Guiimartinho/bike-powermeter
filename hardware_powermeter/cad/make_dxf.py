#!/usr/bin/env python3
"""Generate the DXF files that carry this board's geometry into a CAD tool.

Everything written here comes from a document in this repository; nothing is
invented. Each rectangle carries the document and the section it came from in
ZONES below, and a value that no document gives is written as a layer name
ending in _CONFERIR, so that it cannot be mistaken for a decided number.

Output (hardware_powermeter/cad/):
  contorno.dxf      board outline only
  zonas.dxf         keep-outs, the antenna notch, the lid's shadow and the
                    placement zones

Coordinates: the documents put the origin at the top left of the board seen
from the front, with y growing downward. CAD puts y upward, so this script
writes y_dxf = H - y_doc.

Run:  python hardware_powermeter/cad/make_dxf.py
Check: python hardware_powermeter/cad/check_dxf.py
"""

from __future__ import annotations

import math
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent

# The board outline. What sets it is the circuit, not the pod (the pod is
# drawn around the board, pod/make_pod.py, and never the other way round):
#
#   - the radio module lies along the board with its antenna end on the
#     right edge (ME54BS13 V1.0.0, 7.3: the RF side faces off the board),
#     12,0 across the 16 mm width and 16,5 along it, plus the 4,7 mm band
#     the antenna wants clear beyond the body;
#   - the switching supply (nPM1100 and its inductor) has to stay 20 mm
#     from the module (7.2, Interference Isolation Rule), which puts it at
#     the LEFT end and leaves the middle to the converter, the bridge pads
#     and the sensors;
#   - the magnetic connector, 18 x 5 in plan, lies along the top edge over
#     the middle, its plungers up through the pod's lid.
#
# 48 x 16 is the TARGET of docs/02 (Placa); 60 is what the 57 parts of
# 05-materiais.md actually take on one face, measured by running the
# placer at one length after another (04-placa.md has the table). PMETER_W
# and PMETER_H override both, so the size can be searched again without
# editing the file, and the placer says what does not fit.
W = float(os.environ.get("PMETER_W", 60.0))
H = float(os.environ.get("PMETER_H", 16.0))
THICKNESS = 0.8

# Corner radius: 1,5 mm, the smallest a pod wall of 1,0 mm can follow with
# a printed inner corner. No document gives another number.
RADIUS_DRAWING = 1.5

# No mounting holes: the board sits on posts in the pod and is potted
# (docs/02, Pod). An empty list is what the placer and the checks expect.
FUROS_DOC: list[tuple[float, float]] = []
M2_DRILL_UNVERIFIED = 2.2
SCREWS_CASE_DRAWING: list[tuple[float, float]] = []

# The module lying along x at the right end: 16,5 along x with the antenna
# band at the +x edge, 12,0 across y, centred in the width.
_ANT_FAIXA = 4.7           # board edge kept clear beside the antenna
_MOD_COMP = 17.0           # the module's courtyard along x (16,5 + 0,5)
_MOD_ALT = 12.5            # across y (12,0 + 0,5)
MOD_Y0 = H / 2.0 - _MOD_ALT / 2.0
MOD_Y1 = H / 2.0 + _MOD_ALT / 2.0

# The lid of the pod over the whole board: the ceiling for the parts on the
# front face. 3,2 mm, and the part that sets it is NOT the module: the
# cell's JST SH connector is 2,90 mm tall against the module's 2,40, and
# 2,9 + 0,3 of air is 3,2. Measured by the pod's dry run on 2026-09-27,
# which failed PD2 on J102 while this said 2,7. The magnetic connector
# goes THROUGH the lid's window, so it is exempt here and PD3 measures it
# against the lid instead - and a 3,2 mm ceiling is now a REQUIREMENT on
# the connector that gets chosen (06-conectores-e-pontos-de-teste.md).
TETO_TAMPA = 3.2
ATRAVESSA_TAMPA = {"J101"}
SOMBRA_TAMPA = f"SOMBRA_TAMPA_MAX_{TETO_TAMPA:.1f}MM".replace(".", "-")


def _f(x0: float, y0: float, x1: float, y1: float) -> tuple:
    """A rectangle, clipped to the board."""
    return (max(0.0, x0), max(0.0, y0), min(W, x1), min(H, y1))


# The floorplan, derived from W and H instead of written out (x left to
# right). XM is where the module's courtyard starts and XE where the energy
# block has to end: 7.2 of the module's datasheet asks for 20 mm between
# the module and a switching supply or a power inductor.
#
#   0 .. XE        ENERGY: nPM1100, inductor, gauge, cell connector at the
#                  left end with its mouth on the end of the board (the
#                  cell lies under the board with its tabs at this end)
#   XE .. XM       the magnetic connector along the top edge (18 x 5),
#                  its plungers up through the pod's lid; under it, from
#                  left to right, the Tag-Connect and the LED, the
#                  CONVERTER with its filters and the bridge pads on the
#                  bottom edge, and the accelerometer by the module's
#                  SPI pads
#   XM .. W        the radio module, antenna to the right edge
XM = W - _MOD_COMP
XE = XM - 20.0
ZONES = [
    # name, rect, colour, source
    ("KEEPOUT_ANTENA_MODULO", _f(W - _ANT_FAIXA, 0.0, W, H), 1,
     "ficha ME54BS13 V1.0.0, 7.3 e 7.4: sobre a area da antena nao pode cobre, "
     "componente nem caixa metalica fechada, e 3 a 5 mm em volta dela nao "
     "pode trilha de sinal, metal nem fonte de interferencia"),
    ("RECORTE_ANTENA_MODULO",
     _f(W - _ANT_FAIXA + 0.4, H / 2.0 - 5.1, W, H / 2.0 + 5.1), 2,
     "ficha ME54BS13 V1.0.0, 7.4: a placa sob a area da antena e VAZADA, para "
     "deixar a regiao suspensa. Comeca 0,4 mm dentro da faixa: a ultima coluna "
     "de pads LGA do modulo tem de manter 0,3 mm de cobre a borda do corte"),
    ("ZONA_MODULO_ME54BS13", _f(XM, MOD_Y0, W, MOD_Y1), 3,
     "MinewSemi ME54BS13, 16,5 x 12,0 mm, deitado no extremo direito com a "
     "antena sobre o recorte"),
    ("ZONA_ENERGIA", _f(0.8, 0.8, XE, H - 0.8), 3,
     "nPM1100, indutor, MAX17048 e o conector da celula. O limite direito nao "
     "e estetico: 7.2 pede 20 mm entre o modulo e uma fonte chaveada ou um "
     "indutor de potencia, e o modulo comeca em XM"),
    ("ZONA_CONECTOR_MAGNETICO", _f(XE + 0.5, 0.55, XM - 0.5, 6.05), 3,
     "conector magnetico de 6 pinos, 18 x 5, deitado na borda de cima com os "
     "pinos para a tampa do pod (docs/02, Conector magnetico)"),
    ("ZONA_CONVERSOR_ADS1220", _f(XE + 4.0, 6.05, XM - 6.0, H - 2.8), 3,
     "ADS1220, o filtro RC das entradas e da referencia, a chave da "
     "excitacao: o canto analogico, a 4 mm do bloco do buck e a 6 mm do "
     "modulo (SBAS501D 9.4.1)"),
    ("ZONA_PONTE_PADS", _f(XE + 4.0, H - 2.8, XM - 6.0, H), 3,
     "os cinco pads de solda da ponte na borda de baixo, a mais perto do "
     "conversor, com o TMP117 ao lado (docs/06: a temperatura da ponte)"),
    ("ZONA_SENSORES", _f(XM - 6.0, 6.05, XM - 0.5, H - 0.8), 3,
     "BMA400 junto dos pads de SPI do modulo, fora do buck e a 5 mm da area "
     "da antena"),
    ("ZONA_TAG_CONNECT", _f(XE + 0.5, 6.05, XE + 8.0, H - 0.8), 3,
     "Tag-Connect TC2030-NL e o LED RGB, entre o bloco de energia e o "
     "conversor, sob o conector magnetico"),
    # The lid's shadow, which the ME2 rule of the board's dry run measures:
    # every part of the front face is under it.
    (SOMBRA_TAMPA, _f(0.0, 0.0, W, H), 4,
     "docs/02, Pod: teto para as pecas da frente; a tampa real e a de "
     "pod/make_pod.py, medida pelo dry run do pod"),
]

# Overlaps the documents flag as unresolved: none on this board.
CONFLITOS: list[tuple] = []


def y(v: float) -> float:
    """Document y (downward, origin at the top) to CAD y (upward)."""
    return H - v


class Dxf:
    """The smallest DXF an importer accepts: R12, LINE, ARC and CIRCLE only."""

    def __init__(self) -> None:
        self.layers: dict[str, int] = {}
        self.ents: list[str] = []

    def layer(self, name: str, colour: int = 7) -> str:
        self.layers.setdefault(name, colour)
        return name

    def line(self, lay: str, x1: float, y1: float, x2: float, y2: float) -> None:
        self.ents += ["0", "LINE", "8", lay,
                      "10", f"{x1:.4f}", "20", f"{y1:.4f}", "30", "0.0",
                      "11", f"{x2:.4f}", "21", f"{y2:.4f}", "31", "0.0"]

    def arc(self, lay: str, cx: float, cy: float, r: float, a0: float, a1: float) -> None:
        self.ents += ["0", "ARC", "8", lay,
                      "10", f"{cx:.4f}", "20", f"{cy:.4f}", "30", "0.0",
                      "40", f"{r:.4f}", "50", f"{a0:.4f}", "51", f"{a1:.4f}"]

    def circle(self, lay: str, cx: float, cy: float, r: float) -> None:
        self.ents += ["0", "CIRCLE", "8", lay,
                      "10", f"{cx:.4f}", "20", f"{cy:.4f}", "30", "0.0",
                      "40", f"{r:.4f}"]

    def rect(self, lay: str, x0: float, y0: float, x1: float, y1: float) -> None:
        self.line(lay, x0, y0, x1, y0)
        self.line(lay, x1, y0, x1, y1)
        self.line(lay, x1, y1, x0, y1)
        self.line(lay, x0, y1, x0, y0)

    def cross(self, lay: str, cx: float, cy: float, arm: float) -> None:
        self.line(lay, cx - arm, cy, cx + arm, cy)
        self.line(lay, cx, cy - arm, cx, cy + arm)

    def text(self) -> str:
        head = ["0", "SECTION", "2", "HEADER",
                "9", "$ACADVER", "1", "AC1009",
                "9", "$INSUNITS", "70", "4",            # 4 = millimetres
                "9", "$MEASUREMENT", "70", "1",         # 1 = metric
                "9", "$EXTMIN", "10", "0.0", "20", "0.0", "30", "0.0",
                "9", "$EXTMAX", "10", f"{W:.4f}", "20", f"{H:.4f}", "30", "0.0",
                "0", "ENDSEC"]
        tab = ["0", "SECTION", "2", "TABLES",
               "0", "TABLE", "2", "LAYER", "70", str(len(self.layers))]
        for name, colour in self.layers.items():
            tab += ["0", "LAYER", "2", name, "70", "0", "62", str(colour),
                    "6", "CONTINUOUS"]
        tab += ["0", "ENDTAB", "0", "ENDSEC"]
        body = ["0", "SECTION", "2", "ENTITIES"] + self.ents + ["0", "ENDSEC", "0", "EOF"]
        return "\r\n".join(head + tab + body) + "\r\n"


def outline(d: Dxf, lay: str, r: float) -> None:
    """Rounded rectangle 0,0 to W,H, four lines and four arcs."""
    d.line(lay, r, 0.0, W - r, 0.0)
    d.line(lay, W, r, W, H - r)
    d.line(lay, W - r, H, r, H)
    d.line(lay, 0.0, H - r, 0.0, r)
    d.arc(lay, W - r, r, r, 270.0, 360.0)
    d.arc(lay, W - r, H - r, r, 0.0, 90.0)
    d.arc(lay, r, H - r, r, 90.0, 180.0)
    d.arc(lay, r, r, r, 180.0, 270.0)


def write_outline(path: pathlib.Path, r: float) -> None:
    d = Dxf()
    lay = d.layer("BOARD_OUTLINE", 7)
    outline(d, lay, r)
    path.write_text(d.text(), encoding="ascii", newline="")


def write_zones(path: pathlib.Path) -> None:
    d = Dxf()
    outline(d, d.layer("BOARD_OUTLINE_REFERENCIA", 8), RADIUS_DRAWING)
    for name, (x0, y0, x1, y1), colour, _src in ZONES + CONFLITOS:
        d.rect(d.layer(name, colour), x0, y(y1), x1, y(y0))
    path.write_text(d.text(), encoding="ascii", newline="")


def main() -> int:
    write_outline(HERE / "contorno.dxf", RADIUS_DRAWING)
    write_zones(HERE / "zonas.dxf")
    print(f"placa {W:g} x {H:g} mm, {THICKNESS:g} mm")
    print(f"contorno.dxf     raio {RADIUS_DRAWING:g} mm")
    print(f"zonas.dxf        {len(ZONES)} zonas, {len(CONFLITOS)} conflitos, "
          f"{len(FUROS_DOC)} furos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
