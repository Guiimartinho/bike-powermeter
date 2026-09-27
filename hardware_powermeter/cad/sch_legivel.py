#!/usr/bin/env python3
"""Measure whether the schematic can actually be READ.

The ERC says nothing about legibility, and neither does any geometric check
made on the s-expression: a reference field and a pin name can sit at the
same millimetre, be perfectly valid, and print as a black smudge. On
2026-09-27 the owner's reviewer went through the exported PDF page by page
and found that exact failure in every sheet - a value over a pin name, two
net labels over each other, a block box over the title block - and asked
for it to be fixed in the generator AND turned into an automatic rule,
because "the next generation brings it all back and nobody sees it".

So this measures **the PDF**, which is the thing people read, and not the
generator's intentions:

  TX1  no two pieces of text overlap on the page
  TX2  no reference and no value prints inside the body of a symbol

A word box comes from the PDF itself (PyMuPDF), so what is measured is what
the plotter drew, with its font and its metrics. Nothing here knows about
KiCad's data model, which is the point: a change in the generator that
looks right and prints wrong still fails.

Used by check_sch.py; runnable on its own:
    python hardware_powermeter/cad/sch_legivel.py [arquivo.pdf]
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent

KICAD_CLI = pathlib.Path(r"D:\KiCAD\bin\kicad-cli.exe")
PT = 25.4 / 72.0          # a PDF point in mm

# How much two boxes may share before it is a collision. Not zero: glyph
# boxes of neighbouring words in the same line touch by a rounding error,
# and a stroke's box can graze the next one. 0,10 mm on each axis is under
# half a character's width (the font is 1,27 mm) and over any rounding.
FOLGA_MM = 0.10
# and a pair that only grazes is not worth reporting: this is the smallest
# shared area, in mm2, that a reader would see as two words on top of
# each other
AREA_MIN = 0.04

# The captions KiCad's own worksheet prints in the title block.
CAPTIONS_CARIMBO = {"Sheet:", "File:", "Title:", "Size:", "Date:", "Rev:",
                    "Id:", "KiCad", "E.D.A.", "A4", "A3", "A2"}


def _cruza(a, b, folga=FOLGA_MM) -> float:
    """Shared area of two boxes in mm2, after shrinking both by `folga`."""
    ax0, ay0, ax1, ay1 = a[0] + folga, a[1] + folga, a[2] - folga, a[3] - folga
    bx0, by0, bx1, by1 = b[0] + folga, b[1] + folga, b[2] - folga, b[3] - folga
    w = min(ax1, bx1) - max(ax0, bx0)
    h = min(ay1, by1) - max(ay0, by0)
    return w * h if w > 0 and h > 0 else 0.0


def _dentro(a, b) -> bool:
    """Is box a wholly inside box b?"""
    return a[0] >= b[0] and a[1] >= b[1] and a[2] <= b[2] and a[3] <= b[3]


def exportar(sch: pathlib.Path, pdf: pathlib.Path) -> None:
    pdf.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([str(KICAD_CLI), "sch", "export", "pdf",
                        "--output", str(pdf), str(sch)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not pdf.exists():
        raise SystemExit(f"kicad-cli nao exportou o PDF: {r.stderr.strip()[:200]}")


def palavras(page) -> list[tuple]:
    """(text, box in mm) for every word the page prints, each once.

    KiCad plots a glyph filled AND stroked, so every word comes out of the
    PDF twice at the same place. Measured on 2026-09-27: 1325 words on five
    sheets that hold about 660. Comparing them raw makes every word overlap
    itself, which is noise, so identical text at the same millimetre counts
    as one.
    """
    vistos = {}
    for x0, y0, x1, y1, txt, *_r in page.get_text("words"):
        s = txt.strip()
        if not s:
            continue
        cx = (x0 * PT, y0 * PT, x1 * PT, y1 * PT)
        chave = (s, round(cx[0], 1), round(cx[1], 1))
        vistos.setdefault(chave, (s, cx))
    return list(vistos.values())


def corpos(page, min_mm: float = 2.5) -> list[tuple]:
    """The rectangles the page draws that are big enough to be a symbol body.

    A symbol body is a stroked rectangle; so is the frame, the title block
    and a block's dashed box, and those are filtered out by size at the
    caller (they are much larger than a symbol).
    """
    out = []
    for d in page.get_drawings():
        r = d["rect"]
        w, h = r.width * PT, r.height * PT
        if w < min_mm or h < min_mm:
            continue
        out.append((r.x0 * PT, r.y0 * PT, r.x1 * PT, r.y1 * PT, w, h))
    return out


def medir(pdf: pathlib.Path, refs: set[str], valores: set[str]) -> dict:
    """Run TX1 and TX2 over every page. Returns what was found."""
    import fitz

    doc = fitz.open(pdf)
    achados = {"sobrepostos": [], "no_corpo": [], "paginas": len(doc),
               "palavras": 0}
    for i, page in enumerate(doc):
        ws = palavras(page)
        achados["palavras"] += len(ws)
        # TX1: two pieces of text on the same spot
        # the stock title block is KiCad's own worksheet, drawn by the
        # plotter: its captions sit tight against each other by design and
        # are not this generator's to move. What IS measured there is
        # whether OUR drawing runs into it, which shows up as one of our
        # words overlapping one of its words.
        # the title block's own corner of the page, from the page size:
        # KiCad's worksheet writes its captions and their values tight
        # against each other there by design
        pw, ph = page.rect.width * PT, page.rect.height * PT
        cant = (pw - 118.0, ph - 34.0, pw, ph)
        carimbo = [w for w in ws
                   if w[0] in CAPTIONS_CARIMBO or _dentro(w[1], cant)]
        for a in range(len(ws)):
            for b in range(a + 1, len(ws)):
                if ws[a] in carimbo and ws[b] in carimbo:
                    continue
                area = _cruza(ws[a][1], ws[b][1])
                if area > AREA_MIN:
                    achados["sobrepostos"].append(
                        (i + 1, ws[a][0], ws[b][0], round(area, 2)))
        # TX2: a reference or a value printed inside a symbol's body. The
        # body has to be SMALL enough to be a symbol and not the frame, the
        # title block or a block's dashed box: 60 mm on a side is bigger
        # than any symbol this generator draws and smaller than any of
        # those. A pin name inside a body is correct and is not measured.
        cps = [c for c in corpos(page) if c[4] <= 60.0 and c[5] <= 60.0]
        for texto, cx in ws:
            if texto not in refs and texto not in valores:
                continue
            for c in cps:
                if _dentro(cx, c[:4]):
                    achados["no_corpo"].append((i + 1, texto))
                    break
    return achados


def main(argv: list[str]) -> int:
    import parts as P

    if len(argv) > 1:
        pdf = pathlib.Path(argv[1])
    else:
        pdf = HERE / "_legivel.pdf"
        exportar(HERE / "pmeter.kicad_sch", pdf)
    refs = set(P.PARTS)
    valores = {w for p in P.PARTS.values() for w in str(p.value).split()}
    a = medir(pdf, refs, valores)
    print(f"{a['paginas']} paginas, {a['palavras']} palavras")
    print(f"TX1 textos sobrepostos: {len(a['sobrepostos'])}")
    for pg, x, y, ar in a["sobrepostos"][:20]:
        print(f"    p{pg}: {x!r} sobre {y!r} ({ar} mm2)")
    print(f"TX2 referencia ou valor dentro do corpo: {len(a['no_corpo'])}")
    for pg, x in a["no_corpo"][:20]:
        print(f"    p{pg}: {x!r}")
    return 1 if a["sobrepostos"] or a["no_corpo"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
