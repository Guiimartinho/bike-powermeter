#!/usr/bin/env python3
"""A footprint for every part, and the ones KiCad does not have, generated.

Each entry says where the land pattern comes from, because that is what
decides whether the board can be assembled:

  EXATO      the KiCad library footprint is for this very part number.
  ENCAPSULAMENTO  the library footprint is for the same package - same pad
             count, same pitch, same body - but drawn for another part. It
             fits, and it still has to be checked against the datasheet
             before fabrication.
  GERADO     no library footprint exists, so it is generated here from the
             package dimensions. Where the datasheet's recommended land
             pattern was not in hand, the pads follow the package outline
             with the usual allowances, and the entry says so.

The machinery (pad writer, box bodies, moulded-package bodies, the module
generator, the real-model lookup and the 2D/3D check) is the bike
computer's (hardware_powermeter/cad/footprints.py), function by function; the
tables are this board's. Nothing here has been fabricated or measured.
"""

from __future__ import annotations

import math

# ref -> (footprint, origin, note)
# origin is EXATO, ENCAPSULAMENTO or GERADO
FP: dict[str, tuple[str, str, str]] = {}

# Parts that are not on the board. The bridge itself lives on the crank arm
# and reaches the board by wires to J301's pads, which ARE on the board; so
# nothing is off it.
FORA_DA_PLACA: set[str] = set()


def _fp(refs, name, origem, nota=""):
    for r in (refs if isinstance(refs, (list, tuple)) else [refs]):
        FP[r] = (name, origem, nota)


# ---------------------------------------------------------------- passivos
R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"

_fp(["R101", "R102", "R103", "R104", "R105", "R106", "R107", "R108",
     "R201", "R202", "R203", "R204", "R205", "R301", "R302",
     "R109", "R110"], R0402,
    "ENCAPSULAMENTO", "0402")
_fp(["C103", "C105", "C106", "C201", "C301", "C302", "C303", "C304", "C305",
     "C306", "C307", "C308", "C401", "C402", "C403"], C0402, "ENCAPSULAMENTO",
    "0402; C0G nos tres do filtro da ponte")
_fp(["C101", "C102", "C104", "C202", "C203"], C0603, "ENCAPSULAMENTO",
    "0603: 2,2 uF/25 V, 22 uF e 10 uF de 6,3 V, 4,7 uF")
_fp("L101", "Inductor_SMD:L_0805_2012Metric", "ENCAPSULAMENTO",
    "Murata DFE201610E-2R2M e 2,0 x 1,6 mm; o 0805 da KiCad e 2,0 x 1,2 mm")
_fp("FB201", "Inductor_SMD:L_0603_1608Metric", "ENCAPSULAMENTO",
    "ferrite Murata BLM15PX601SN1D em 0603")

# ---------------------------------------------------------------- CIs
_fp("U101", "Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.7x2.7mm", "ENCAPSULAMENTO",
    "nPM1100 QFN24 4x4 P0,5, pad exposto D2/E2 2,70 nominal (PS v1.5, "
    "tabela 26); o pad termico e o pino 25")
_fp("U102", "Package_DFN_QFN:TDFN-8-1EP_2x2mm_P0.5mm_EP0.8x1.2mm", "ENCAPSULAMENTO",
    "MAX17048 em TDFN-8 2x2 (T822+3); o footprint do KiCad cita o desenho "
    "21-0168 da Maxim, o da propria peca; o pad exposto e o pino 9")
_fp("U301", "Package_DFN_QFN:Texas_RVA_VQFN-16-1EP_3.5x3.5mm_P0.5mm_EP2.14x2.14mm",
    "EXATO", "ADS1220IRVAR: o RVA da TI, pino por pino; o pad termico e o 17")
_fp("U401", "Package_LGA:LGA-12_2x2mm_P0.5mm", "ENCAPSULAMENTO",
    "BMA400 LGA-12 2x2 P0,5; a ficha (8.3) recomenda pads de 0,30 x 0,35 e "
    "0,45 x 0,30 e nenhuma via sob a peca - conferir contra o generico")
_fp("U402", "Package_SON:WSON-6-1EP_2x2mm_P0.65mm_EP1x1.6mm", "ENCAPSULAMENTO",
    "TMP117 em DRV (WSON-6 2x2 P0,65, pad exposto 1,0 x 1,6 do desenho "
    "DRV0006B); o pad termico e o pino 7")

# ---------------------------------------------------------------- conectores
_fp("J102", "pmeter:Furos_Celula_2x1.5mm_P2.5mm", "GERADO",
    "dois furos metalizados para os fios da celula, soldados a mao")
import parts as _P  # noqa: E402

_fp([t[0] for t in _P.TESTE], "TestPoint:TestPoint_Pad_D1.0mm", "EXATO", "")

# ------------------------------------------------------- footprints gerados
def _pad(num, x, y, w, h, tipo="smd", forma="roundrect", drill=0.0,
         camadas='"F.Cu" "F.Paste" "F.Mask"'):
    extra = f'\n\t\t(drill {drill})' if drill else ""
    rr = '\n\t\t(roundrect_rratio 0.25)' if forma == "roundrect" else ""
    return (f'\t(pad "{num}" {tipo} {forma}\n\t\t(at {x:.4f} {y:.4f})\n'
            f'\t\t(size {w:.4f} {h:.4f}){extra}\n\t\t(layers {camadas}){rr}\n'
            f'\t\t(uuid "{_uid(num, x, y)}")\n\t)')


def _uid(*p):
    import hashlib
    h = hashlib.sha256("|".join(str(x) for x in p).encode()).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-4{h[13:16]}-8{h[17:20]}-{h[20:32]}"


# Body height of each generated footprint, in mm, from its datasheet. It is
# what turns the board's 3D view from a bare set of pads into something you
# can look at, and it is also the number the case has to clear.
# Every body drawn by this file, generated footprint or library one, so the
# project's own renderer can draw the same box the KiCad viewer shows. KiCad
# exports GLB from STEP only, so a model written as VRML never reaches the
# GLB and has to be drawn again on this side.
CORPO_TODOS: dict[str, tuple[float, float, float]] = {}


CORPO: dict[str, tuple[float, float, float]] = {
    # nome do footprint -> largura, altura em planta, altura do corpo (mm)
    "pmeter:MinewSemi_ME54BS13_16.5x12mm": (12.00, 16.50, 2.40),
    # HOLYIOT-26001-A: 10,0 x 12,5 do desenho mecanico. A ALTURA nao consta
    # no anuncio e 2,40 e a do ME54BS13, posta aqui como reserva ate alguem
    # medir uma peca - ela decide o teto da tampa do pod (PD2), entao um
    # numero errado aqui vira uma tampa que nao fecha
    # (09-modulo-de-radio.md, O que falta confirmar).
    "pmeter:HOLYIOT_26001A_10x12.5mm": (10.00, 12.50, 2.40),
    "pmeter:TPD4E05U06_USON-10_1x2.5mm_P0.5mm": (1.00, 2.50, 0.55),
    # TUOZHAN S4-3528RGBTA-A: 3,5 x 2,8 x 1,9
    "pmeter:LED_RGB_3528_3.5x2.8mm": (3.50, 2.80, 1.90),
    # TI TPS22916 YFP: D e E de 0,75 a 0,81, 0,5 de altura maxima
    "pmeter:TPS22916_DSBGA-4_0.78x0.78mm_P0.4mm": (0.78, 0.78, 0.50),
    # o conector magnetico GENERICO: 6 contatos a 2,5 mais os dois imas,
    # 18 x 5 em planta e 3,0 de altura - lugar reservado, nao peca
    # 3,20 of height is not a maker's number, it is the pod's REQUIREMENT:
    # the lid sits 3,2 mm over the board (make_dxf.TETO_TAMPA, set by the
    # cell connector's 2,9) and this one has to reach it to be met by the
    # cable's magnetic head. The part chosen has to be at least this tall
    # (06-conectores-e-pontos-de-teste.md).
    "pmeter:Pogo_Magnetico_6P_2x3_P2.5mm": (9.00, 5.00, 3.20),
}


# KiCad reads a VRML model in units of a tenth of an inch, not in
# millimetres, and multiplies by this to place it. Checked, not assumed:
# R_0402_1005Metric.wrl, a part 1.0 x 0.5 mm, has its corners at +-0.197 and
# +-0.098, which is 1.0/2.54 and 0.5/2.54. Written in millimetres with a
# scale of 1, every one of these boxes came out 2.54 times too big in the 3D
# viewer - a 16.5 mm module drawn 41.9 mm long, over most of the board.
VRML_POR_MM = 1.0 / 25.4 * 10.0


def wrl_caixa(caminho, w: float, h: float, alt: float, cor=(0.13, 0.13, 0.14)):
    """A plain box in VRML, so KiCad's 3D viewer has a body to show.

    KiCad's GLB and STEP exports read only STEP models, so this box shows in
    the 3D viewer and not in an exported GLB; the project's own renderer draws
    the same box from the footprint, which is why both exist.
    """
    e = VRML_POR_MM
    hw, hh, alt = w / 2.0 * e, h / 2.0 * e, alt * e
    pts = [(-hw, -hh, 0), (hw, -hh, 0), (hw, hh, 0), (-hw, hh, 0),
           (-hw, -hh, alt), (hw, -hh, alt), (hw, hh, alt), (-hw, hh, alt)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    caminho.write_text(
        "#VRML V2.0 utf8\n# caixa do encapsulamento, nao o modelo do fabricante\n"
        "Shape {\n  appearance Appearance { material Material { diffuseColor "
        f"{cor[0]} {cor[1]} {cor[2]} }} }}\n"
        "  geometry IndexedFaceSet {\n    coord Coordinate { point [\n"
        + ",\n".join(f"      {x:.4f} {y:.4f} {z:.4f}" for x, y, z in pts)
        + " ] }\n    coordIndex [\n"
        + ",\n".join("      " + " ".join(str(i) for i in f) + " -1" for f in faces)
        + " ]\n  }\n}\n", encoding="utf-8", newline="\n")


def _corpo(nome, w, h, pads, descr, crtyd=None):
    """Wrap pads in a footprint with a courtyard and a fab outline.

    `crtyd` is (largura, altura) para o contorno de ocupacao quando ele NAO e
    o corpo mais a folga. Num conector de FPC os pes de fixacao ficam atras
    do corpo, e um contorno tirado so do corpo deixaria o vizinho encostar
    neles - o colocador acredita no contorno, nao no que esta desenhado.
    O F.Fab continua sendo o corpo, porque e ele que o ME3 compara com a
    ficha.
    """
    hw, hh = w / 2.0, h / 2.0
    cw, ch = (crtyd if crtyd else (w, h))
    linhas = []
    for lay, larg, folga in (("F.CrtYd", 0.05, 0.25), ("F.Fab", 0.1, 0.0)):
        if lay == "F.CrtYd":
            a, b = cw / 2.0 + folga, ch / 2.0 + folga
            linhas.append(
                f'\t(fp_rect\n\t\t(start {-a:.4f} {-b:.4f})\n\t\t(end {a:.4f} {b:.4f})\n'
                f'\t\t(stroke (width {larg}) (type solid))\n\t\t(fill none)\n'
                f'\t\t(layer "{lay}")\n\t\t(uuid "{_uid(nome, lay)}")\n\t)')
            continue
        a, b = hw + folga, hh + folga
        linhas.append(
            f'\t(fp_rect\n\t\t(start {-a:.4f} {-b:.4f})\n\t\t(end {a:.4f} {b:.4f})\n'
            f'\t\t(stroke (width {larg}) (type solid))\n\t\t(fill none)\n'
            f'\t\t(layer "{lay}")\n\t\t(uuid "{_uid(nome, lay)}")\n\t)')
    return ('(footprint "' + nome + '"\n\t(version 20240108)\n\t(generator "pmeter")\n'
            '\t(generator_version "8.0")\n\t(layer "F.Cu")\n'
            f'\t(descr "{descr}")\n\t(attr smd)\n'
            f'\t(property "Reference" "REF**"\n\t\t(at 0 {-hh - 1.2:.3f} 0)\n'
            '\t\t(layer "F.SilkS")\n\t\t(uuid "' + _uid(nome, "ref") + '")\n'
            '\t\t(effects (font (size 0.8 0.8) (thickness 0.12)))\n\t)\n'
            f'\t(property "Value" "{nome}"\n\t\t(at 0 {hh + 1.2:.3f} 0)\n'
            '\t\t(layer "F.Fab")\n\t\t(uuid "' + _uid(nome, "val") + '")\n'
            '\t\t(effects (font (size 0.8 0.8) (thickness 0.12)))\n\t)\n'
            + "\n".join(linhas) + "\n" + "\n".join(pads) + "\n)\n")


def son(nome, n, pitch, pad_w, pad_h, span, corpo_w, corpo_h, descr,
        nomes=None, ep=None):
    """Two rows of pads, numbered counter-clockwise from the top left."""
    pads = []
    por_lado = n // 2
    y0 = -(por_lado - 1) * pitch / 2.0
    for i in range(por_lado):
        num = nomes[i] if nomes else str(i + 1)
        pads.append(_pad(num, -span / 2.0, y0 + i * pitch, pad_w, pad_h))
    for i in range(por_lado):
        num = nomes[por_lado + i] if nomes else str(n - i)
        pads.append(_pad(num, span / 2.0, y0 + i * pitch, pad_w, pad_h))
    if ep:
        pads.append(_pad(ep[0], 0, 0, ep[1], ep[2], forma="rect"))
    return _corpo(nome, corpo_w, corpo_h, pads, descr)


def wlp(nome, linhas, colunas, pitch, bola, corpo_w, corpo_h, descr):
    """A ball grid, named A1..: letter is the row, number the column."""
    pads = []
    for r in range(linhas):
        for c in range(colunas):
            x = (c - (colunas - 1) / 2.0) * pitch
            y = (r - (linhas - 1) / 2.0) * pitch
            pads.append(_pad(f"{chr(ord('A') + r)}{c + 1}", x, y, bola, bola,
                             forma="circle"))
    return _corpo(nome, corpo_w, corpo_h, pads, descr)


def led_rgb_3528(nome):
    """TUOZHAN S4-3528RGBTA-A, ficha S35210052 de 2021-02-21.

    3,5 x 2,8 x 1,9, anodo comum. A pinagem sai do esquema interno impresso
    no mesmo desenho, e o anodo fica na DIAGONAL do vermelho:

      1  B   catodo azul      superior esquerdo
      2  +   anodo comum      inferior esquerdo
      3  G   catodo verde     superior direito
      4  R   catodo vermelho  inferior direito, no canto chanfrado

    Muito mais brilhante que o APTF1616 que substitui - 460 a 1000 mcd no
    vermelho contra 15, 1300 a 2900 no verde contra 50 - entao os resistores
    de serie precisam ser RECALCULADOS para nao ofuscar a noite.

      pad 1,8 x 0,8, centros em (+-1,70; +-0,75); o pad avanca 0,85 para
      fora do corpo de cada lado, como e proprio de LED
    """
    # Os nomes sao os do esquematico, nao os numeros da ficha: o pino 1 da
    # ficha e o catodo azul, o 2 o anodo comum, o 3 o verde e o 4 o vermelho.
    pads = [_pad("KB", -1.70, 0.75, 1.8, 0.8),
            _pad("A", -1.70, -0.75, 1.8, 0.8),
            _pad("KG", 1.70, 0.75, 1.8, 0.8),
            _pad("KR", 1.70, -0.75, 1.8, 0.8)]
    return _corpo(nome, 3.5, 2.8, pads,
                  "TUOZHAN S4-3528RGBTA-A, anodo comum no pino 2; canto "
                  "chanfrado junto ao pino 4 (vermelho). MSL4")


GERADOS: dict[str, str] = {}


def pogo_magnetico() -> str:
    """The 6-way magnetic pogo receptacle, GENERIC: six 1,5 mm round pads
    at 2,5 mm of pitch in TWO ROWS OF THREE, and two pads at the ends for
    the magnet frame's tabs.

    Two rows and not one line (2026-09-27): six contacts at 2,5 mm in a
    row are 12,5 mm of contacts alone, and on a board whose whole length
    is about 33 mm that is a third of it. In two rows the same six
    contacts take 5,0 x 2,5 mm, and the part about 7,5 x 5,0 - some 7 mm
    of length given back, with the six ways kept.

    Nothing here comes from a maker's drawing: no supplier page could be
    reached, so the arrangement, like the numbering, is this project's and
    becomes a purchase requirement alongside the minimum height of 3,2 mm
    (06-conectores-e-pontos-de-teste.md)."""
    pads = []
    for i in range(6):
        col, lin = i % 3, i // 3
        pads.append(_pad(str(i + 1), -2.5 + col * 2.5, -1.25 + lin * 2.5,
                         1.5, 1.5, forma="circle"))
    # The magnet frame's tabs, clear of the contacts: a 1,5 mm contact at
    # 2,5 reaches 3,25, so the tab starts at 3,25 + 0,127 of clearance.
    # At 3,5 the two coppers overlapped and the DRC called it a short.
    pads.append(_pad("MP1", -3.9, 0.0, 0.8, 4.4, forma="rect"))
    pads.append(_pad("MP2", 3.9, 0.0, 0.8, 4.4, forma="rect"))
    return _corpo("pmeter:Pogo_Magnetico_6P_2x3_P2.5mm", 9.0, 5.0, pads,
                  "conector magnetico de 6 pinos pogo em duas fileiras de "
                  "tres, GENERICO, a trocar pelo desenho do fornecedor")


def furos_celula() -> str:
    """Two plated holes for the cell's wires, soldered by hand.

    There is no connector: the pod is potted and sealed to IPX7, and in
    that a soldered wire holds better than a latch. It also takes the
    tallest part off the board - the JST SH was 2,90 mm and set the lid's
    height all by itself - so the ceiling goes back to the module's 2,4
    plus air (make_dxf.TETO_TAMPA). The wires come up from the cell, which
    lies under the board, through the recess in the pod's floor.
    """
    pads = [_pad(str(i + 1), -1.25 + i * 2.5, 0.0, 1.5, 1.5, tipo="thru_hole",
                 forma="circle", drill=0.9, camadas='"*.Cu" "*.Mask"')
            for i in range(2)]
    return _corpo("pmeter:Furos_Celula_2x1.5mm_P2.5mm", 5.0, 1.6, pads,
                  "VBAT+ e GND da celula, furos metalizados; o fio sobe pelo "
                  "rebaixo do fundo do pod")


def furos_ponte() -> str:
    """Five plated holes for the bridge's wires and the shield: 0,9 mm
    drill in a 1,5 mm ring at 2,0 mm of pitch, soldered by hand when the
    gauges are wired to the pod. Holes and not pads (2026-09-27): the wires
    come up from the crank arm through a slot in the pod's floor, so they
    reach the board from BELOW, and a hole holds a wire where a pad on the
    top face would need it bent over the edge. The cell under the board
    stops short of these holes (pod/make_pod.py)."""
    pads = [_pad(str(i + 1), -4.0 + i * 2.0, 0.0, 1.5, 1.5, tipo="thru_hole",
                 forma="circle", drill=0.9, camadas='"*.Cu" "*.Mask"')
            for i in range(5)]
    return _corpo("pmeter:Furos_Ponte_5x1.5mm_P2mm", 10.0, 1.6, pads,
                  "E+, S+, S-, E- e blindagem da ponte, furos metalizados para "
                  "os fios que sobem do braco pelo rasgo do fundo do pod")


def _gerar():
    # TPD4E05U06 USON-10, 1.0 x 2.5 mm, 0.5 mm pitch.
    GERADOS["pmeter:TPD4E05U06_USON-10_1x2.5mm_P0.5mm"] = son(
        "pmeter:TPD4E05U06_USON-10_1x2.5mm_P0.5mm", 10, 0.5, 0.3, 0.24, 0.8,
        1.0, 2.5, "TI TPD4E05U06 em DQA, USON-10; land pattern aproximado")
    # TPS22916 in YFP: 2 x 2 bumps at 0,4 mm, land 0,23 mm (SLVSDO5F, land
    # pattern example, page 25), body 0,78 x 0,78 (D and E 0,75 to 0,81).
    GERADOS["pmeter:TPS22916_DSBGA-4_0.78x0.78mm_P0.4mm"] = wlp(
        "pmeter:TPS22916_DSBGA-4_0.78x0.78mm_P0.4mm", 2, 2, 0.4, 0.23, 0.78, 0.78,
        "TI TPS22916 em YFP, 4 bolas; land pattern da ficha SLVSDO5F, pagina 25")
    GERADOS["pmeter:LED_RGB_3528_3.5x2.8mm"] = led_rgb_3528(
        "pmeter:LED_RGB_3528_3.5x2.8mm")
    GERADOS["pmeter:Pogo_Magnetico_6P_2x3_P2.5mm"] = pogo_magnetico()
    GERADOS["pmeter:Furos_Ponte_5x1.5mm_P2mm"] = furos_ponte()
    GERADOS["pmeter:Furos_Celula_2x1.5mm_P2.5mm"] = furos_celula()


_gerar()


# Body height of the library footprints the board file does not carry.
# Where the number is from the part's datasheet it says so; where it is the
# usual value for the package it says THAT. PACOTE wins over this table.
ALTURA: dict[str, tuple[float, str]] = {
    "Connector_JST:JST_SH_SM02B-SRSS-TB_1x02-1MP_P1.00mm_Horizontal": (2.90,
        "JST SH de entrada lateral: 2,9 mm de altura sobre a placa (catalogo "
        "da serie SH) - CONFERIR no desenho da peca"),
    "Package_DFN_QFN:Texas_RVA_VQFN-16-1EP_3.5x3.5mm_P0.5mm_EP2.14x2.14mm": (1.00,
        "altura maxima corrente de um VQFN de 3,5 mm - o desenho RVA0016 da "
        "TI nao foi lido: CONFERIR"),
    "Package_DFN_QFN:TDFN-8-1EP_2x2mm_P0.5mm_EP0.8x1.2mm": (0.80,
        "altura maxima corrente de um TDFN 2x2 - o desenho 21-0168 da Maxim "
        "nao foi lido: CONFERIR"),
    "Package_LGA:LGA-12_2x2mm_P0.5mm": (1.00,
        "BMA400: 1,00 MAX no desenho 8.1 da ficha (0,95 tipico)"),
}


def altura_de(nome: str) -> tuple[float, str] | None:
    """The height of a package: the datasheet's if there is one.

    PACOTE holds what a mechanical drawing says and ALTURA what is merely
    usual for the family. When both have an entry the drawing wins, and it
    has to: those two disagreed by 0.10 mm on the harvester's QFN and by
    0.15 on the ESD array, and the number that was being used was the guess.
    """
    if nome in PACOTE:
        return (PACOTE[nome][2], PACOTE[nome][8])
    return ALTURA.get(nome)


# No body at all, and that is correct: a test point is a pad and the
# Tag-Connect is only pads and holes; the bridge pads are pads.
SEM_CORPO = {"TestPoint:TestPoint_Pad_D1.0mm",
             "Connector:Tag-Connect_TC2030-IDC-NL_2x03_P1.27mm_Vertical",
             "pmeter:Furos_Ponte_5x1.5mm_P2mm",
             "pmeter:Furos_Celula_2x1.5mm_P2.5mm"}


def fab_do_footprint(nome: str) -> tuple[float, float] | None:
    """The package outline of a footprint, from its own F.Fab drawing."""
    import fp_load as _fl

    arv = _fl.parse(_fl.carregar(nome)[0])
    xs: list[float] = []
    ys: list[float] = []
    for chave in ("fp_line", "fp_rect", "fp_poly", "fp_circle"):
        for g in _fl.kids(arv, chave):
            lay = _fl.kid(g, "layer")
            if not lay or lay[1] not in ("F.Fab", "B.Fab"):
                continue
            for tag in ("start", "end", "center", "mid"):
                q = _fl.kid(g, tag)
                if q:
                    xs.append(float(q[1]))
                    ys.append(float(q[2]))
            pts = _fl.kid(g, "pts")
            if pts:
                for q in _fl.kids(pts, "xy"):
                    xs.append(float(q[1]))
                    ys.append(float(q[2]))
    if not xs:
        return None
    return (max(xs) - min(xs), max(ys) - min(ys))


# Where KiCad keeps its own 3D models.
LIB3D = __import__("pathlib").Path(r"D:\KiCAD\share\kicad\3dmodels")

NL = chr(10)

TAB = chr(9)


# A part the maker does publish a model for goes in cad/3d/real/, and it
# wins over the box drawn here. Put the file there under the footprint's own
# name - SW_SPST_B3S-1000.step for the key, USB_C_Receptacle_Palconn_UTC16-G
# .step for the receptacle - and the next run picks it up with nothing else
# to change. STEP is preferred because it is the only format KiCad's GLB and
# STEP exports read; a .wrl works in the 3D viewer alone.
#
# The model files themselves are NOT committed: this repository is public and
# a manufacturer's 3D model carries the manufacturer's terms, the same reason
# the datasheets stay out. cad/3d/real/ is in the .gitignore, and 3d/LEIAME.md
# lists which parts are worth fetching and under what name.
def modelo_de_verdade(base: str) -> str | None:
    """A manufacturer model dropped into cad/3d/real/, if there is one."""
    import pathlib as _pl

    pasta = _pl.Path(__file__).resolve().parent / "3d" / "real"
    for ext in (".step", ".stp", ".STEP", ".wrl"):
        p = pasta / (base + ext)
        if p.exists():
            return "3d/real/" + p.name
    return None


# Maker models that come turned against the footprint's frame, in degrees
# about Z, then the (x, y) offset in the MODEL's frame after the turn. None
# yet on this board: every body is drawn here or is KiCad's own. Whoever
# adds a STEP to cad/3d/real/ measures it with the ME4, ME5 and ME6 rules
# of dry_run_pcb.py, as the bike computer did (its footprints.py tells the
# story of the USB-C that came 180 degrees off).
MODELO_GIRADO: dict[str, tuple[int, float, float]] = {}

# The same model on the BACK face needs another turn AND another offset,
# both measured, never deduced (the bike computer's JST ZH of J103).
MODELO_GIRADO_VERSO: dict[str, tuple[int, float, float]] = {}


def modelo_no_verso(corpo: str) -> str:
    """The footprint's text for a BACK face instance: the model offset of
    MODELO_GIRADO_VERSO in place of the front one, when the table has it."""
    import re as _re

    m = _re.search(r'\(model "([^"]+)"', corpo)
    if not m:
        return corpo
    base = m.group(1).rsplit("/", 1)[-1].rsplit(".", 1)[0]
    if base not in MODELO_GIRADO_VERSO:
        return corpo
    giro, ox, oy = MODELO_GIRADO_VERSO[base]
    inicio = m.start()
    trecho = corpo[inicio:]
    trecho = _re.sub(r"\(offset\s*\(xyz [^)]*\)\s*\)", "(offset (xyz %g %g 0))" % (ox, oy), trecho, count=1)
    trecho = _re.sub(r"\(rotate\s*\(xyz [^)]*\)\s*\)", "(rotate (xyz 0 0 %d))" % giro, trecho, count=1)
    return corpo[:inicio] + trecho


def linha_de_modelo(rel: str) -> str:
    base = rel.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    giro, ox, oy = MODELO_GIRADO.get(base, (0, 0.0, 0.0))
    return (TAB + '(model "${KIPRJMOD}/' + rel + '"' + NL +
            TAB * 2 + "(offset (xyz %g %g 0))" % (ox, oy) + NL +
            TAB * 2 + "(scale (xyz 1 1 1))" + NL +
            TAB * 2 + "(rotate (xyz 0 0 %d))" % giro + NL +
            TAB + ")" + NL)


def trocar_modelo(nome: str, corpo: str) -> str:
    """Give a library footprint a body when KiCad has no model for it.

    Leaves the model alone when the file is really there - 85 of this board's
    footprints are in that case and use KiCad's own STEP. When it is not,
    draws the box and points the footprint at it. When the part has no body
    to speak of - a test point, a mounting hole, a Tag-Connect that is only
    pads - takes the model line out, so nothing pretends otherwise.
    """
    import pathlib as _pl
    import re as _re

    m = _re.search(r'\(model "([^"]+)"', corpo)
    if not m:
        return corpo
    caminho = m.group(1)
    if caminho.startswith("${KIPRJMOD}"):
        return corpo                      # already one of ours
    rel = caminho.replace("${KICAD8_3DMODEL_DIR}/", "")
    if (LIB3D / rel).exists() or (LIB3D / rel.replace(".wrl", ".step")).exists():
        return corpo                      # KiCad has it: use KiCad's

    def sem_bloco(texto: str) -> str:
        i = texto.index("(model ")
        d, j = 0, i
        while j < len(texto):
            c = texto[j]
            if c == '"':
                j += 1
                while j < len(texto) and texto[j] != '"':
                    j += 2 if texto[j] == "\\" else 1
            elif c == "(":
                d += 1
            elif c == ")":
                d -= 1
                if d == 0:
                    break
            j += 1
        inicio = texto.rfind(NL, 0, i) + 1
        return texto[:inicio] + texto[j + 1:].lstrip(NL)

    base_real = nome.split(":", 1)[1]
    real = modelo_de_verdade(base_real)
    if real:
        return sem_bloco(corpo).rstrip(NL) + NL + linha_de_modelo(real)
    if nome in SEM_CORPO:
        return sem_bloco(corpo)
    tam = fab_do_footprint(nome)
    medida = altura_de(nome)
    if tam is None or medida is None:
        return sem_bloco(corpo)
    alt, _fonte = medida
    # The BODY is the datasheet's, whenever the datasheet has been read. The
    # F.Fab outline is what someone drew for the land pattern, and where the
    # two disagree it is the drawing that is right - the Molex receptacle is
    # 9.99 x 8.58 and the footprint in use draws 8.94 x 7.32, so taking the
    # footprint's size would have drawn the part a millimetre small in both
    # directions and hidden, in the 3D view, exactly the mismatch that ME3
    # reports in the 2D one.
    if nome in PACOTE:
        tam = (PACOTE[nome][0], PACOTE[nome][1])
    base = nome.split(":", 1)[1]
    pasta = _pl.Path(__file__).resolve().parent / "3d"
    pasta.mkdir(exist_ok=True)
    est = estilo_de(nome)
    if nome in DESENHADOS:
        DESENHADOS[nome](pasta / (base + ".wrl"), tam[0], tam[1], alt)
    elif est:
        wrl_ci(pasta / (base + ".wrl"), tam[0], tam[1], alt, est, nome)
    else:
        wrl_caixa(pasta / (base + ".wrl"), tam[0], tam[1], alt, cor=cor_de(nome))
    CORPO_TODOS[nome] = (tam[0], tam[1], alt)
    return sem_bloco(corpo).rstrip(NL) + NL + linha_de_modelo("3d/" + base + ".wrl")


def _caixa_vrml(pts, faces, cor) -> str:
    return ("Shape {\n  appearance Appearance { material Material { "
            f"diffuseColor {cor[0]} {cor[1]} {cor[2]} }} }}\n"
            "  geometry IndexedFaceSet {\n    coord Coordinate { point [\n"
            + ",\n".join(f"      {x:.4f} {y:.4f} {z:.4f}" for x, y, z in pts)
            + " ] }\n    coordIndex [\n"
            + ",\n".join("      " + " ".join(str(i) for i in f) + " -1"
                         for f in faces)
            + " ]\n  }\n}\n")


def _bloco(x0, y0, z0, x1, y1, z1, cor) -> str:
    e = VRML_POR_MM
    pts = [(x0 * e, y0 * e, z0 * e), (x1 * e, y0 * e, z0 * e),
           (x1 * e, y1 * e, z0 * e), (x0 * e, y1 * e, z0 * e),
           (x0 * e, y0 * e, z1 * e), (x1 * e, y0 * e, z1 * e),
           (x1 * e, y1 * e, z1 * e), (x0 * e, y1 * e, z1 * e)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return _caixa_vrml(pts, faces, cor)


def wrl_me54bs13(caminho) -> None:
    """The radio module as the mechanical drawing of V1.0.0 draws it.

    Not one box but two, because the part is not one box: a 12.00 x 16.50 mm
    printed circuit 0.80 mm thick, and a metal shield can 1.60 mm high over
    everything except the last 4.46 mm, which is the antenna and has to stay
    open. Seeing that in the 3D view is the difference between believing the
    antenna faces the board edge and knowing it.
    """
    W, H, ANT, ESP, ALT = 12.00, 16.50, 4.46, 0.80, 2.40
    # footprint coordinates: the antenna is at -Y, which is up on the screen
    pcb = _bloco(-W / 2, -H / 2, 0.0, W / 2, H / 2, ESP, (0.05, 0.28, 0.12))
    lata = _bloco(-W / 2 + 0.1, -H / 2 + ANT, ESP, W / 2 - 0.1, H / 2 - 0.1,
                  ALT, (0.62, 0.63, 0.66))
    # the meander, drawn flat on the antenna end so it is visible
    trilha = _bloco(-W / 2 + 0.6, -H / 2 + 0.6, ESP, W / 2 - 0.6,
                    -H / 2 + 1.2, ESP + 0.05, (0.78, 0.66, 0.30))
    trilha += _bloco(-W / 2 + 0.6, -H / 2 + 2.4, ESP, W / 2 - 0.6,
                     -H / 2 + 3.0, ESP + 0.05, (0.78, 0.66, 0.30))
    caminho.write_text(
        "#VRML V2.0 utf8\n"
        "# MinewSemi ME54BS13, do desenho mecanico da ficha V1.0.0:\n"
        "# 12,00 x 16,50 x 2,40 mm, com a antena nos 4,46 mm de uma ponta,\n"
        "# fora da blindagem. Corpo desenhado aqui: a Minew nao publica STEP.\n"
        + pcb + lata + trilha, encoding="utf-8", newline="\n")


def wrl_holyiot_26001a(caminho) -> None:
    """The HOLYIOT-26001-A as its mechanical drawing and its photo give it.

    Every DIMENSION here is off the maker's drawing, the same one the
    footprint is generated from (09-modulo-de-radio.md). Every COLOUR is
    read off the product photo of the advert, and that difference is
    recorded rather than smoothed over: a dimension that closes three ways
    is evidence, a colour from a photograph is a reading.

    The part is not one box, and drawing it as one hides the thing that
    decides the layout:

      - the printed circuit, 10,00 x 12,50 x 0,80, with BLACK solder mask.
        Holyiot's photo shows a black board, not the green of the ME54BS13;
      - a shield can over the components, from the antenna band down to the
        bottom edge, 1,00 mm proud of the board. In the photo it reads dark,
        not as bright tin, so it is drawn as a dark grey coated can and NOT
        as the bright plate the ME54BS13 has;
      - the CERAMIC ANTENNA at the top, in the 3,80 mm band the drawing
        keeps clear of pads: a small ivory block, metallised on the ends,
        sitting on the board outside the can. It is the reason the module
        has to hang off the host board's edge, and seeing it is the point of
        drawing the part at all;
      - the gold pads: seven per side on each of the two columns, eight
        along the bottom, on the underside where they are soldered.

    Total height 2,40 mm, and that is a RESERVATION, not a measurement: the
    advert gives no height. A module of this class - a shield can over a
    0,80 mm board - runs 1,8 to 2,2, so 2,40 has margin. It is drawn at the
    reservation so that the body, the lid's ceiling (make_dxf.TETO_TAMPA)
    and the rule (PD18, make_pod.MODULO_ALT_MAX) all carry the same number,
    and a part that arrives taller is caught by the rule and not by a lid
    that will not close.
    """
    W, H = HOLY_W, HOLY_H
    # 0,80 of board and 1,60 of can: 2,40 in all, which is the RESERVED
    # height and not a measured one. The advert gives no height at all, and a
    # module of this class - a can over a 0,80 mm board - runs 1,8 to 2,2. It
    # is drawn at the reservation on purpose: the body, the lid's ceiling and
    # PD18 then all carry the same number, and a part that arrives taller
    # than what is drawn is caught by the rule instead of by the lid.
    ESP, LATA = 0.80, 1.60
    PRETO_PCB = (0.07, 0.07, 0.08)        # black solder mask, from the photo
    LATA_COR = (0.30, 0.31, 0.33)         # the can reads dark in the photo
    CERAMICA = (0.90, 0.88, 0.82)         # ivory ceramic
    METAL = (0.72, 0.73, 0.75)            # the antenna's metallised ends
    OURO = (0.80, 0.68, 0.32)

    def fy(y):
        return y - H / 2.0

    def fx(x):
        return x - W / 2.0

    partes = [_bloco(-W / 2, -H / 2, 0.0, W / 2, H / 2, ESP, PRETO_PCB)]
    # the can: from the antenna band down, inside the pad columns
    partes.append(_bloco(fx(HOLY_X_LGA - 1.2), fy(HOLY_ANT + 0.2), ESP,
                         fx(W - HOLY_X_LGA + 1.2), fy(H - 0.6), ESP + LATA,
                         LATA_COR))
    # the ceramic antenna, centred in the band the drawing keeps clear
    ax0, ax1 = fx(1.7), fx(8.3)
    ay0, ay1 = fy(0.7), fy(2.0)
    partes.append(_bloco(ax0, ay0, ESP, ax1, ay1, ESP + 0.60, CERAMICA))
    for sx in (0, 1):
        x = ax0 if sx == 0 else ax1 - 0.5
        partes.append(_bloco(x, ay0, ESP, x + 0.5, ay1, ESP + 0.62, METAL))
    # the pads, on the underside
    ys = [HOLY_Y0 + i * HOLY_PASSO for i in range(7)]
    xs_baixo = [(W - 8.40) / 2.0 + i * HOLY_PASSO for i in range(8)]
    cw, ch = HOLY_PAD_CAST
    lw, lh = HOLY_PAD_LGA
    bw, bh = HOLY_PAD_BAIXO
    for y in ys:
        for x in (HOLY_X_CAST, W - HOLY_X_CAST):
            partes.append(_bloco(fx(x) - cw / 2, fy(y) - ch / 2, -0.03,
                                 fx(x) + cw / 2, fy(y) + ch / 2, 0.0, OURO))
        for x in (HOLY_X_LGA, W - HOLY_X_LGA):
            partes.append(_bloco(fx(x) - lw / 2, fy(y) - lh / 2, -0.03,
                                 fx(x) + lw / 2, fy(y) + lh / 2, 0.0, OURO))
    for x in xs_baixo:
        partes.append(_bloco(fx(x) - bw / 2, fy(H - bh / 2) - bh / 2, -0.03,
                             fx(x) + bw / 2, fy(H - bh / 2) + bh / 2, 0.0, OURO))
    caminho.write_text(
        "#VRML V2.0 utf8" + NL +
        "# HOLYIOT-26001-A, nRF54L15: 10,00 x 12,50 x 1,80 mm." + NL +
        "# Cotas do desenho mecanico do anuncio; CORES lidas da foto do" + NL +
        "# produto (placa preta, blindagem escura, antena ceramica no topo)." + NL +
        "# Corpo desenhado aqui: a Holyiot nao publica STEP." + NL +
        "".join(partes), encoding="utf-8", newline=NL)


# What each package actually looks like. A board where every drawn part is
# the same grey box tells you nothing; these are the colours of the real
# materials, so a moulded plastic IC reads as black epoxy, a shield can as
# tin plate and a ceramic capacitor as the pale tan it is. The key is matched
# against the footprint name, first hit wins.
COR_PACOTE = (
    ("HOLYIOT", (0.07, 0.07, 0.08)),       # black board, dark can
    ("MinewSemi", (0.62, 0.63, 0.66)),     # shield can
    ("u-blox", (0.62, 0.63, 0.66)),        # shield can
    ("USB_C", (0.78, 0.79, 0.80)),         # stainless shell
    ("FFC-FPC", (0.90, 0.88, 0.82)),       # ivory housing with a dark latch
    ("SW_SPST", (0.10, 0.10, 0.11)),       # black body
    ("Buzzer", (0.09, 0.09, 0.10)),        # black can
    ("LED_RGB", (0.92, 0.92, 0.90)),       # clear lens
    ("TestPoint", (0.80, 0.70, 0.35)),
    ("QFN", (0.09, 0.09, 0.10)),
    ("SOIC", (0.09, 0.09, 0.10)),
    ("SON", (0.09, 0.09, 0.10)),
    ("SOT", (0.09, 0.09, 0.10)),
    ("WLP", (0.22, 0.20, 0.24)),           # bare silicon, purple-grey
    ("LGA", (0.12, 0.12, 0.13)),
)

COR_PADRAO = (0.11, 0.11, 0.12)


def cor_de(nome: str) -> tuple[float, float, float]:
    for chave, c in COR_PACOTE:
        if chave.lower() in nome.lower():
            return c
    return COR_PADRAO


def _cilindro(x, y, z0, z1, raio, cor, lados: int = 20) -> str:
    """A can: the buzzer, and the plunger of a tactile switch."""
    e = VRML_POR_MM
    pts = []
    for z in (z0, z1):
        for i in range(lados):
            a = 2 * math.pi * i / lados
            pts.append(((x + raio * math.cos(a)) * e,
                        (y + raio * math.sin(a)) * e, z * e))
    faces = []
    for i in range(lados):
        j = (i + 1) % lados
        faces.append((i, j, lados + j, lados + i))
    faces.append(tuple(range(lados - 1, -1, -1)))
    faces.append(tuple(range(lados, 2 * lados)))
    return _caixa_vrml(pts, faces, cor)


def wrl_led_3528(caminho, w: float, h: float, alt: float) -> None:
    """TUOZHAN S4-3528RGBTA-A: corpo branco, lente transparente incolor.

    A ficha declara o encapsulante como 透明 "water clear" - transparente
    INCOLOR, nao leitoso. A cor do corpo a ficha nao declara; a foto do
    produto mostra resina BRANCA (parede RGB 217,212,227, fundo da cavidade
    245,239,245), que e o PPA/PCT de praxe. Registrado como inferido da
    foto, e nao da ficha.

    A secao de baixo tem 1,05 mm de altura reta; os 0,85 de cima afunilam de
    3,5 para 3,2 mm. A cavidade refletora mede 2,64 x 2,14, e o canto
    chanfrado fica junto ao pino 4, o vermelho.
    """
    BRANCO = (0.86, 0.85, 0.88)
    CAVIDADE = (0.96, 0.94, 0.96)
    LENTE = (0.92, 0.94, 0.96)
    ESTANHO = (0.74, 0.75, 0.77)
    partes = [
        _bloco(-w / 2, -h / 2, 0.0, w / 2, h / 2, 1.05, BRANCO),
        _bloco(-1.6, -h / 2 + 0.15, 1.05, 1.6, h / 2 - 0.15, alt, BRANCO),
        # a cavidade refletora, 2,64 x 2,14, cheia de resina transparente
        _bloco(-1.32, -1.07, 0.9, 1.32, 1.07, alt, CAVIDADE),
        _bloco(-1.30, -1.05, 1.0, 1.30, 1.05, alt - 0.02, LENTE),
    ]
    # os quatro terminais na face de baixo, 0,80 x 0,785
    for sx in (-1, 1):
        for sy in (-1, 1):
            partes.append(_bloco(sx * 1.35 - 0.40, sy * 0.7075 - 0.3925, 0.0,
                                 sx * 1.35 + 0.40, sy * 0.7075 + 0.3925,
                                 0.06, ESTANHO))
    caminho.write_text(
        "#VRML V2.0 utf8" + NL +
        "# TUOZHAN S4-3528RGBTA-A: 3,5 x 2,8 x 1,9, corpo branco, lente "
        "transparente incolor, anodo comum no pino 2" + NL +
        "".join(partes), encoding="utf-8", newline=NL)


def wrl_pogo_magnetico(caminho, w: float, h: float, alt: float) -> None:
    """The 6-way magnetic connector, drawn part by part.

    NOTHING here is a maker's drawing: no supplier page for a 6-way magnetic
    receptacle could be reached, so this body is DESIGNED by this project
    from the footprint outwards, and every number below is a purchase
    requirement, not a measurement. It replaces the plain box the generator
    used to write, which said nothing about how the thing works and hid the
    one decision that matters for sealing.

    That decision: **the flat contacts are on the DEVICE and the spring pins
    are in the CABLE.** A magnetic connector can be built either way round.
    Putting the springs on the pod would put six moving parts, six barrels
    and six gaps into a part that has to survive IPX7, road grit and a
    pressure wash, and each barrel is a path for water into a housing that
    is potted shut. Flat gold targets have nothing to jam and nothing to
    let water past; the wear and the mechanism go in the cable, which is
    cheap to replace and lives indoors. It is also what a sealed device
    does - a smartwatch charger has the pins in the puck, not in the watch.

    The geometry, from the footprint (pogo_magnetico) outwards:

      - housing 8,6 x 4,6, black LCP, 0,2 mm inside the 9,0 x 5,0 courtyard;
      - a 0,35 mm chamfer round the top, so the cable's head self-centres
        instead of stopping on a square edge;
      - six gold targets of 1,3 mm over the six 1,5 mm pads, standing
        0,05 mm proud of the housing so the spring lands on gold and not on
        plastic;
      - two nickel-plated magnets of 1,1 x 4,2 x 2,6 at the ends, over the
        MP1 and MP2 tabs, exposed on the top face: they are the magnetic
        circuit AND the mechanical anchor, which is why those two pads are
        4,4 mm long;
      - the solder side: six tinned pads and the two tabs, 0,08 mm thick.

    The total height of 3,20 mm is not a maker's number either: it is the
    pod's requirement, because the lid sits that far over the board and the
    face has to reach it (06-conectores-e-pontos-de-teste.md).
    """
    CORPO_PLAST = (0.10, 0.10, 0.11)     # black LCP, the usual for this
    OURO = (0.83, 0.69, 0.22)
    NIQUEL = (0.78, 0.79, 0.81)
    ESTANHO = (0.74, 0.75, 0.77)
    cw, ch = w - 0.4, h - 0.4            # housing, inside the courtyard
    chanfro = 0.35
    partes = [
        # the housing, in two steps so the top reads as chamfered
        _bloco(-cw / 2, -ch / 2, 0.0, cw / 2, ch / 2, alt - chanfro, CORPO_PLAST),
        _bloco(-cw / 2 + chanfro, -ch / 2 + chanfro, alt - chanfro,
               cw / 2 - chanfro, ch / 2 - chanfro, alt, CORPO_PLAST),
    ]
    # the two magnets at the ends, through the housing and exposed on top
    for sx in (-1, 1):
        partes.append(_bloco(sx * 3.9 - 0.55, -2.1, 0.0,
                             sx * 3.9 + 0.55, 2.1, alt, NIQUEL))
        # and their solder tabs under the board side
        partes.append(_bloco(sx * 3.9 - 0.4, -2.2, 0.0,
                             sx * 3.9 + 0.4, 2.2, 0.08, ESTANHO))
    # the six gold targets, over the six pads, proud of the housing
    for i in range(6):
        col, lin = i % 3, i // 3
        x, y = -2.5 + col * 2.5, -1.25 + lin * 2.5
        partes.append(_cilindro(x, y, alt - 0.10, alt + 0.05, 0.65, OURO, 16))
        partes.append(_cilindro(x, y, 0.0, 0.08, 0.75, ESTANHO, 16))
    caminho.write_text(
        "#VRML V2.0 utf8" + NL +
        "# conector magnetico de 6 vias, 9,0 x 5,0 x 3,2: DESENHADO POR ESTE"
        " PROJETO, nao por um fabricante." + NL +
        "# Contatos chatos de ouro no APARELHO e molas no CABO, para o pod"
        " poder ser vedado." + NL +
        "".join(partes), encoding="utf-8", newline=NL)


DESENHADOS = {
    "pmeter:MinewSemi_ME54BS13_16.5x12mm":
        lambda c, w, h, a: wrl_me54bs13(c),
    "pmeter:LED_RGB_3528_3.5x2.8mm": wrl_led_3528,
    "pmeter:Pogo_Magnetico_6P_2x3_P2.5mm": wrl_pogo_magnetico,
    "pmeter:HOLYIOT_26001A_10x12.5mm": lambda c, w, h, a: wrl_holyiot_26001a(c),
}


# The mechanical drawing of each package, read in the part's own datasheet.
# Not the footprint outline, which is a land pattern and is deliberately
# bigger than the body; not "the usual value for the package" either. Each
# entry is: body w x h x A, standoff A1, exposed pad (or None), terminal
# width b, terminal length L, pitch e, and where the numbers come from.
#
# w and h follow the FOOTPRINT's orientation, which is not always the
# datasheet's: the TPD4E05U06 drawing gives 2.50 x 1.00 and the footprint
# stands it on end. conferir_2d_3d() compares the two ignoring orientation.
PACOTE: dict[str, tuple] = {
    "pmeter:TPD4E05U06_USON-10_1x2.5mm_P0.5mm":
        (1.00, 2.50, 0.40, 0.03, None, 0.20, 0.36, 0.50,
         "TI, desenho do DQA0010A: 2,6/2,4 x 1,1/0,9, altura 0,45/0,35"),
    "pmeter:LED_RGB_3528_3.5x2.8mm":
        (3.50, 2.80, 1.90, 0.00, None, 0.80, 0.785, 1.50,
         "TUOZHAN S4-3528RGBTA-A, ficha S35210052 (2021-02-21): 3,5 +-0,2 "
         "por 2,8 +-0,2 por 1,9 de altura, terminais de 0,80 x 0,785. Lente "
         "water clear; canto chanfrado junto ao pino 4, o vermelho"),
    "pmeter:TPS22916_DSBGA-4_0.78x0.78mm_P0.4mm":
        (0.78, 0.78, 0.50, 0.13, None, 0.23, 0.23, 0.40,
         "TI SLVSDO5F, desenho YFP0004 (4223507/A): D e E 0,75 a 0,81, "
         "altura 0,5 MAX, bola 0,21 a 0,25 (a 0,13 e a folga da bola), "
         "passo 0,4 nos dois eixos"),
    "Package_DFN_QFN:QFN-24-1EP_4x4mm_P0.5mm_EP2.7x2.7mm":
        (4.00, 4.00, 0.85, 0.035, (2.70, 2.70), 0.25, 0.40, 0.50,
         "Nordic nPM1100 PS v1.5, tabela 26: D e E 4,0, A 0,80/0,85/0,90, "
         "A1 0/0,035/0,05, D2 e E2 2,60/2,70/2,80, b 0,20/0,25/0,30, "
         "L 0,35/0,40/0,45, e 0,50"),
    "Package_SON:WSON-6-1EP_2x2mm_P0.65mm_EP1x1.6mm":
        (2.00, 2.00, 0.80, 0.00, (1.00, 1.60), 0.30, 0.30, 0.65,
         "TI SNOSD82D, desenho DRV0006B (4223922/A): 2,1/1,9 quadrado, "
         "0,8 MAX de altura, standoff 0,05/0,00, pad exposto 1,6 x 1,0, "
         "terminais 0,35/0,25 por 0,3/0,2, passo 0,65"),
    "Package_LGA:LGA-12_2x2mm_P0.5mm":
        (2.00, 2.00, 0.95, 0.00, None, 0.28, 0.29, 0.50,
         "Bosch BST-BMA400-DS000-14 rev 2.3, desenho 8.1: 2,00 x 2,00, "
         "1,00 MAX (0,95 na lista de caracteristicas), pads 0,280 x 0,290 "
         "(4 de canto) e 0,290 x 0,280 (8), passo 0,50"),
}


def conferir_2d_3d() -> list[str]:
    """Does the body the datasheet gives fit the footprint that was drawn?

    A land pattern is bigger than the body, on purpose, so the two are never
    equal - but they cannot disagree by much either, and a footprint chosen
    for the wrong package shows up here as a body that does not fit inside
    its own outline or that rattles around in it. Orientation is ignored,
    because a footprint may stand the package on end.
    """
    import fp_load as _fl

    achados = []
    for nome, dados in PACOTE.items():
        w, h, alt = dados[0], dados[1], dados[2]
        fab = fab_do_footprint(nome)
        if fab is None:
            achados.append(f"{nome}: o footprint nao tem contorno em F.Fab")
            continue
        corpo = tuple(sorted((w, h)))
        desenho = tuple(sorted(fab))
        for i, (c, d) in enumerate(zip(corpo, desenho)):
            if abs(c - d) > 0.15:
                achados.append(
                    f"{nome}: a ficha da {'menor' if i == 0 else 'maior'} "
                    f"medida do corpo como {c:.2f} mm e o footprint desenha "
                    f"{d:.2f} mm ({abs(c - d):.2f} de diferenca)")
        cy = _fl.CAIXA.get(nome)
        if cy and (w > cy[2] - cy[0] + 0.01 or h > cy[3] - cy[1] + 0.01):
            achados.append(f"{nome}: o corpo de {w:.2f} x {h:.2f} nao cabe no "
                           f"contorno de {cy[2]-cy[0]:.2f} x {cy[3]-cy[1]:.2f}")
    return achados


def wrl_ci(caminho, w: float, h: float, alt: float, estilo: str,
           nome: str = "") -> None:
    """A moulded package with the shape its family actually has.

    A board where every part is the same black cuboid tells you nothing. What
    distinguishes these packages at a glance is where the metal is: a QFN
    shows its exposed pad and a ring of lead flags underneath, a SOIC has
    gull-wing leads standing out on two sides, a SOT has three of them, and a
    wafer-level package is bare silicon with a grid of solder balls. All of
    it is drawn from the same outline the footprint already carries, so
    nothing here is invented dimension - only which part of it is metal.
    """
    METAL = (0.72, 0.73, 0.75)
    EPOXI = (0.09, 0.09, 0.10)
    SILICIO = (0.24, 0.21, 0.28)
    partes = []
    # the datasheet's own numbers when there are any: body, standoff,
    # exposed pad, terminal width and length, pitch
    dados = PACOTE.get(nome)
    a1, ep, bw, bl, passo_t = 0.03, None, 0.25, 0.35, 0.5
    if dados:
        w, h, alt, a1, ep, bw, bl, passo_t = dados[:8]

    if estilo == "wlp":
        # bare die, with the ball grid under it
        partes.append(_bloco(-w / 2, -h / 2, 0.12, w / 2, h / 2, alt, SILICIO))
        passo = 0.4
        nx = max(1, int(w / passo))
        ny = max(1, int(h / passo))
        for i in range(nx):
            for j in range(ny):
                bx = -w / 2 + passo / 2 + i * passo
                by = -h / 2 + passo / 2 + j * passo
                partes.append(_cilindro(bx, by, 0.0, 0.14, 0.11, METAL, 8))
    elif estilo == "soic":
        # body raised on its leads, with the gull wings on two sides
        corpo_alt = alt - 0.15
        partes.append(_bloco(-w / 2 + 0.9, -h / 2, 0.15, w / 2 - 0.9, h / 2,
                             corpo_alt, EPOXI))
        n = max(2, int(h / 1.27))
        for i in range(n):
            by = -h / 2 + h * (i + 0.5) / n
            for lado in (-1, 1):
                x0 = lado * (w / 2 - 0.9)
                x1 = lado * (w / 2)
                partes.append(_bloco(min(x0, x1), by - 0.2, 0.0,
                                     max(x0, x1), by + 0.2, 0.15, METAL))
    elif estilo == "sot":
        corpo_alt = alt - 0.1
        partes.append(_bloco(-w / 2, -h / 2 + 0.25, 0.10, w / 2, h / 2 - 0.25,
                             corpo_alt, EPOXI))
        for bx, by in ((-w / 4, -h / 2 + 0.12), (w / 4, -h / 2 + 0.12),
                       (0.0, h / 2 - 0.12)):
            partes.append(_bloco(bx - 0.18, by - 0.15, 0.0,
                                 bx + 0.18, by + 0.15, 0.10, METAL))
    else:
        # qfn, dfn, son, lga: a moulded body with metal underneath
        partes.append(_bloco(-w / 2, -h / 2, a1, w / 2, h / 2, a1 + alt, EPOXI))
        if ep:
            partes.append(_bloco(-ep[0] / 2, -ep[1] / 2, 0.0,
                                 ep[0] / 2, ep[1] / 2, a1 + 0.02, METAL))
        # the terminals, at the pitch and the size the drawing gives
        for eixo, comp in ((0, w), (1, h)):
            n = max(1, int(round((comp - bw) / passo_t)))
            for i in range(n + 1):
                d = -comp / 2 + bw / 2 + i * passo_t
                if d > comp / 2 - bw / 2 + 1e-6:
                    break
                for lado in (-1, 1):
                    if eixo == 0:
                        bx0, bx1 = d - bw / 2, d + bw / 2
                        by = lado * (h / 2 - bl / 2)
                        by0, by1 = by - bl / 2, by + bl / 2
                    else:
                        by0, by1 = d - bw / 2, d + bw / 2
                        bx = lado * (w / 2 - bl / 2)
                        bx0, bx1 = bx - bl / 2, bx + bl / 2
                    partes.append(_bloco(bx0, by0, 0.0, bx1, by1,
                                         a1 + 0.02, METAL))

    # pin 1, as the dot the real package carries
    partes.append(_cilindro(-w / 2 + 0.35, -h / 2 + 0.35, alt, alt + 0.02,
                            min(0.22, w / 8), (0.45, 0.45, 0.47), 10))
    caminho.write_text(
        "#VRML V2.0 utf8" + NL +
        f"# encapsulamento {estilo}, {w:.2f} x {h:.2f} x {alt:.2f} mm" + NL +
        "".join(partes), encoding="utf-8", newline=NL)


ESTILO = (
    ("QFN", "qfn"), ("DFN", "qfn"), ("SON", "qfn"), ("LGA", "qfn"),
    ("SOIC", "soic"), ("SO-", "soic"),
    ("SOT", "sot"),
    ("WLP", "wlp"), ("WLCSP", "wlp"), ("DSBGA", "wlp"),
)


def estilo_de(nome: str) -> str | None:
    for chave, est in ESTILO:
        if chave.lower() in nome.lower():
            return est
    return None


def _com_modelo() -> None:
    """Give every generated footprint a body, and reference it.

    The box is the package outline of CORPO, raised to the height of the part.
    It goes into 3d/ as VRML, which is what KiCad's 3D viewer reads; the
    project's own renderer draws the same box from the same table, because
    KiCad's GLB and STEP exports read only STEP models.
    """
    import pathlib as _pl

    pasta = _pl.Path(__file__).resolve().parent / "3d"
    pasta.mkdir(exist_ok=True)
    for nome, (w, h, alt) in CORPO.items():
        if nome not in GERADOS:
            continue
        # PACOTE wins here too: CORPO is the outline this file drew the
        # footprint from, PACOTE is what the mechanical drawing cotes.
        if nome in PACOTE:
            w, h, alt = PACOTE[nome][0], PACOTE[nome][1], PACOTE[nome][2]
        CORPO_TODOS[nome] = (w, h, alt)
        base = nome.split(":", 1)[1]
        est = estilo_de(nome)
        if nome in DESENHADOS:
            DESENHADOS[nome](pasta / (base + ".wrl"), w, h, alt)
        elif est:
            wrl_ci(pasta / (base + ".wrl"), w, h, alt, est, nome)
        else:
            wrl_caixa(pasta / (base + ".wrl"), w, h, alt, cor=cor_de(nome))
        # O modelo do FABRICANTE ganha do desenhado aqui, sempre. A caixa
        # que este arquivo desenha existe porque quase nenhuma destas pecas
        # tem modelo publico; quando tem, ele e melhor em tudo - traz o
        # chanfro, a marcacao, a lingueta, e foi feito por quem fabrica.
        # E, ao contrario do .wrl, o STEP chega ao GLB e ao STEP exportados,
        # que e o que o mecanico abre.
        real = modelo_de_verdade(base)
        # through linha_de_modelo(), so that MODELO_GIRADO applies to the
        # generated footprints too: this block wrote its own model line with
        # a fixed rotate of 0, and the HCTL FPC's 180 degrees (J402) were
        # written in the table and never reached the board (2026-09-26)
        modelo = linha_de_modelo(real if real else "3d/" + base + ".wrl")
        texto = GERADOS[nome]
        GERADOS[nome] = texto[:texto.rindex(")")] + modelo + ")\n"


def me54bs13() -> str:
    """MinewSemi ME54BS13, from the mechanical drawing of datasheet V1.0.0.

    Body 12.00 x 16.50 mm, antenna on one 12 mm end. Twenty castellated pads
    on the long sides at 1.1 mm pitch and a 60 pad LGA matrix of 0.6 mm pads
    at 1.5 x 1.2 mm pitch. The datasheet's origin is the bottom left corner
    with the antenna at +Y; the footprint's is the body centre with the
    antenna at -Y, which is up on the screen.

    Minew does not publish a land pattern - the datasheet says to ask for it -
    so the pads here are the module's own pads with the usual allowance:
    1.50 mm across the edge by 0.70 mm along it for the castellated ones,
    half inside the body and half outside, and 0.65 mm circles for the matrix.
    The 0.70 is what has to run along the edge: the pitch there is 1.10 mm,
    so a 1.50 mm pad along it would overlap its neighbour.
    """
    W, H = 12.00, 16.50
    ANT = 4.46                      # antenna band, measured from the +Y end
    ys_cast = [1.10 + i * 1.10 for i in range(10)]
    xs_lga = [2.25 + i * 1.50 for i in range(6)]
    ys_lga = [0.90 + i * 1.20 for i in range(10)]

    def fy(y_ds: float) -> float:
        return H / 2.0 - y_ds       # datasheet Y up, footprint Y down

    pads = []
    # 1..10 down the left side, 11..20 up the right side
    for i in range(10):
        pads.append(_pad(str(i + 1), -W / 2.0, fy(ys_cast[9 - i]), 1.50, 0.70,
                         forma="rect"))
    for i in range(10):
        pads.append(_pad(str(11 + i), W / 2.0, fy(ys_cast[i]), 1.50, 0.70,
                         forma="rect"))
    for c, letra in enumerate("ABCDEF"):
        for linha in range(10):
            pads.append(_pad(f"{letra}{linha}", xs_lga[c] - W / 2.0,
                             fy(ys_lga[9 - linha]), 0.65, 0.65, forma="circle"))

    corpo = _corpo("pmeter:MinewSemi_ME54BS13_16.5x12mm", W, H, pads,
                   "MinewSemi ME54BS13, nRF54LM20A; 20 pads castelados e 60 LGA. "
                   "Land pattern NAO oficial: a Minew fornece o dela sob pedido")
    # the antenna band, and the 4 mm the datasheet asks for around the RF side
    faixa = (f'\t(fp_rect\n\t\t(start {-W / 2.0:.3f} {-H / 2.0:.3f})\n'
             f'\t\t(end {W / 2.0:.3f} {-H / 2.0 + ANT:.3f})\n'
             '\t\t(stroke (width 0.12) (type dash))\n\t\t(fill none)\n'
             '\t\t(layer "Dwgs.User")\n'
             f'\t\t(uuid "{_uid("me54", "ant")}")\n\t)\n'
             f'\t(fp_text user "antena: sem cobre, 4 mm livres, virada para a borda"\n'
             f'\t\t(at 0 {-H / 2.0 - 1.0:.3f} 0)\n\t\t(layer "Dwgs.User")\n'
             f'\t\t(uuid "{_uid("me54", "txt")}")\n'
             '\t\t(effects (font (size 0.6 0.6) (thickness 0.1)))\n\t)\n')
    return corpo[:-2] + faixa + ")\n"


# ---------------------------------------------------------- HOLYIOT-26001-A
# Every number below is off the maker's mechanical drawing, read on
# 2026-09-28 and written up in 09-modulo-de-radio.md. The drawing closes on
# itself by three independent routes, which is the only reason to trust it
# without a part on the bench: 7 column pads over 7,2 mm give 6 x 1,2; 8
# bottom pads over 8,4 give 7 x 1,2, the same pitch; and from the last
# column pad (3,8 + 7,2 = 11,0 from the top edge) to the bottom row (12,25)
# there are 1,25 mm, the same pitch once more.
HOLY_W, HOLY_H = 10.00, 12.50
HOLY_PASSO = 1.20
HOLY_Y0 = 3.80                  # top edge to the first column pad's centre
HOLY_X_CAST = 0.50              # castellated column centre, from each edge
HOLY_X_LGA = 2.50               # LGA column centre, from each edge
HOLY_ANT = 3.80                 # the antenna band: top edge to the first pad
# The pads the MODULE has. The land pattern is this project's, like the
# ME54BS13's: Holyiot publishes no land pattern either.
HOLY_PAD_CAST = (1.00, 0.60)    # side castellation: into the board x along it
HOLY_PAD_LGA = (1.00, 0.80)
HOLY_PAD_BAIXO = (0.60, 0.50)
# A castellated land has to run PAST the body, or the solder fillet forms
# inside the module's shadow where nobody can see it and no optical
# inspection can judge it. IPC-7351's practice for castellations is the
# module's own pad plus a toe, and 0,50 mm is what the ME54BS13's footprint
# uses here (half in, half out). The LGA pads stay as they are: they are
# under the body by definition and there is no fillet to look at.
HOLY_TOE = 0.50

# The pin names, in the drawing's own order. Written out instead of
# generated, because the order is NOT a formula: it runs down the left
# castellations, left to right along the bottom, UP the right castellations,
# then down the left LGA column and UP the right one.
HOLY_PINOS = [
    # 1..7, left castellations, top to bottom
    "NRESET", "P0.02", "P0.01", "SWDIO", "SWDCLK", "P2.10", "P2.09",
    # 8..15, bottom row, left to right
    "P2.05", "P2.00", "P2.01", "P2.08", "P1.08", "P1.07", "P1.06", "VDD",
    # 16..22, right castellations, bottom to top
    "P2.04", "P1.05", "P1.04", "P1.15", "P1.14", "P1.13", "P1.09",
    # 23..29, left LGA column, top to bottom
    "GND", "P0.03", "P0.00", "P0.04", "P2.06", "P2.07", "P2.03",
    # 30..36, right LGA column, bottom to top
    "P2.02", "P1.03", "P1.02", "P1.12", "P1.11", "P1.10", "GND",
]


def holyiot_26001a() -> str:
    """HOLYIOT-26001-A, nRF54L15 with a ceramic antenna, 10,0 x 12,5 mm.

    36 pads: a castellated column and an LGA column on each side, seven each,
    and eight castellations along the bottom edge. The pad NAMES carry the
    port pin (`P1.11`), not the pin number, because that is what the
    netlist and `board_check.py` compare against the silicon - the two `GND`
    pads are told apart by a suffix.

    The origin is the body centre and the antenna is at -Y, which is up on
    the screen, the same convention the ME54BS13's footprint uses.
    """
    W, H = HOLY_W, HOLY_H
    ys = [HOLY_Y0 + i * HOLY_PASSO for i in range(7)]      # from the TOP edge
    xs_baixo = [(W - 8.40) / 2.0 + i * HOLY_PASSO for i in range(8)]
    y_baixo = H - HOLY_PAD_BAIXO[1] / 2.0

    def fx(x):
        return x - W / 2.0

    def fy(y):
        return y - H / 2.0          # drawing Y down, footprint Y down too

    nomes = list(HOLY_PINOS)
    vistos: dict[str, int] = {}
    for i, n in enumerate(nomes):
        if nomes.count(n) > 1:
            vistos[n] = vistos.get(n, 0) + 1
            nomes[i] = f"{n}{vistos[n]}"

    pads = []
    cw, ch = HOLY_PAD_CAST
    lw, lh = HOLY_PAD_LGA
    bw, bh = HOLY_PAD_BAIXO
    # the castellated lands run HOLY_TOE past the body: the module's pad is
    # cw deep from the edge, the land is cw + toe, so its centre moves out
    cw_l = cw + HOLY_TOE
    x_cast_l = HOLY_X_CAST - HOLY_TOE / 2.0
    bh_l = bh + HOLY_TOE
    y_baixo_l = y_baixo + HOLY_TOE / 2.0
    for i in range(7):                                     # 1..7
        pads.append(_pad(nomes[i], fx(x_cast_l), fy(ys[i]), cw_l, ch, forma="rect"))
    for i in range(8):                                     # 8..15
        pads.append(_pad(nomes[7 + i], fx(xs_baixo[i]), fy(y_baixo_l), bw, bh_l,
                         forma="rect"))
    for i in range(7):                                     # 16..22, bottom up
        pads.append(_pad(nomes[15 + i], fx(W - x_cast_l), fy(ys[6 - i]), cw_l, ch,
                         forma="rect"))
    for i in range(7):                                     # 23..29, top down
        pads.append(_pad(nomes[22 + i], fx(HOLY_X_LGA), fy(ys[i]), lw, lh, forma="rect"))
    for i in range(7):                                     # 30..36, bottom up
        pads.append(_pad(nomes[29 + i], fx(W - HOLY_X_LGA), fy(ys[6 - i]), lw, lh,
                         forma="rect"))

    corpo = _corpo("pmeter:HOLYIOT_26001A_10x12.5mm", W, H, pads,
                   "HOLYIOT-26001-A, nRF54L15 com antena ceramica; 22 pads "
                   "castelados e 14 LGA. Land pattern NAO oficial: cotas lidas "
                   "do desenho mecanico do anuncio (09-modulo-de-radio.md)")
    faixa = (f'\t(fp_rect\n\t\t(start {-W / 2.0:.3f} {-H / 2.0:.3f})\n'
             f'\t\t(end {W / 2.0:.3f} {-H / 2.0 + HOLY_ANT:.3f})\n'
             '\t\t(stroke (width 0.12) (type dash))\n\t\t(fill none)\n'
             '\t\t(layer "Dwgs.User")\n'
             f'\t\t(uuid "{_uid("holy", "ant")}")\n\t)\n'
             f'\t(fp_text user "antena ceramica: para FORA da borda, sem terra embaixo"\n'
             f'\t\t(at 0 {-H / 2.0 - 1.0:.3f} 0)\n\t\t(layer "Dwgs.User")\n'
             f'\t\t(uuid "{_uid("holy", "txt")}")\n'
             '\t\t(effects (font (size 0.6 0.6) (thickness 0.1)))\n\t)\n')
    return corpo[:-2] + faixa + ")\n"


# the generated ones, assigned
_fp("D101", "pmeter:TPD4E05U06_USON-10_1x2.5mm_P0.5mm", "GERADO", "")
_fp("D201", "pmeter:LED_RGB_3528_3.5x2.8mm", "GERADO",
    "TUOZHAN S4-3528RGBTA-A, anodo comum, a mesma peca do ciclocomputador")
_fp("U302", "pmeter:TPS22916_DSBGA-4_0.78x0.78mm_P0.4mm", "GERADO",
    "TPS22916B em YFP; land pattern da propria ficha")
_fp("J101", "pmeter:Pogo_Magnetico_6P_2x3_P2.5mm", "GERADO",
    "GENERICO: nenhuma peca escolhida; a trocar pelo desenho do fornecedor")
_fp("J301", "pmeter:Furos_Ponte_5x1.5mm_P2mm", "GERADO",
    "cinco pads de solda a mao, sem pasta")
_fp("U201", "pmeter:HOLYIOT_26001A_10x12.5mm", "GERADO",
    "modulo de radio; a Holyiot nao publica land pattern")
GERADOS["pmeter:MinewSemi_ME54BS13_16.5x12mm"] = me54bs13()
GERADOS["pmeter:HOLYIOT_26001A_10x12.5mm"] = holyiot_26001a()

# every generated footprint gets its body last, once they all exist
_com_modelo()


def resumo() -> str:
    from collections import Counter
    c = Counter(v[1] for v in FP.values())
    return (f"{len(FP)} pecas com footprint: "
            + ", ".join(f"{k} {v}" for k, v in sorted(c.items()))
            + f"; {len(GERADOS)} footprints gerados aqui; "
            + f"{len(FORA_DA_PLACA)} pecas fora da placa")


if __name__ == "__main__":
    import parts as P
    print(resumo())
    faltam = [r for r in P.PARTS if r not in FP and r not in FORA_DA_PLACA]
    print(f"sem footprint: {len(faltam)}")
    if faltam:
        print("  " + ", ".join(sorted(faltam)))
