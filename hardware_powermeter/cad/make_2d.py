#!/usr/bin/env python3
"""Gera o 2D da placa: uma pagina por camada de cobre, mais a de conjunto.

A vista de conjunto - as quatro camadas de cobre numa folha so - era legivel
enquanto as malhas de terra estavam vazias. Cheias, ela deixa de ser: o
despejo e uma area solida e cobre as trilhas que estao debaixo dele, de modo
que a folha passa a mostrar o contorno do cobre e quase mais nada.

Quem le uma placa le uma camada de cada vez, e e isso que este arquivo gera:
quatro paginas, cada uma com uma camada de cobre sobre o contorno e a
serigrafia, mais uma quinta com as quatro juntas para quem quiser a vista de
conjunto. O `kicad-cli pcb export pdf` junta as camadas que se pede numa
pagina so, entao sao cinco chamadas e uma juncao.

    python hardware_powermeter/cad/make_2d.py
"""
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
KICAD = pathlib.Path(r"D:\KiCAD\bin\kicad-cli.exe")
PCB = HERE / "pmeter.kicad_pcb"

# Copper layer -> what the page is called, and which silkscreen goes with it.
# The silkscreen is per FACE: the front one names the parts on the front and
# the back one names the parts on the back, and printing F.SilkS over the
# B.Cu page labels the wrong side of the board. Four of this board's parts
# are on the back - the buzzer, the battery connector, the barometer and the
# thermistor - and on the back page they were unnamed.
COBRE = (
    ("F.Cu", "", "1 - F.Cu: frente"),
    ("In1.Cu", "", "2 - In1.Cu: plano de terra"),
    ("In2.Cu", "", "3 - In2.Cu: roteamento interno"),
    ("B.Cu", "", "4 - B.Cu: verso"),
)
# The silkscreen gets pages of its own, and it has to: KiCad draws it in a
# pale cream that is unreadable over the red of a filled copper pour, which
# is exactly what these pages are. On white, with only the outline under it,
# it is the assembly drawing - the sheet a person uses to find R602 on a
# board - and that is the only thing silkscreen is for.
# Silkscreen ALONE, and in black. F.Fab carries the library footprint's own
# copy of every reference plus the value, so with it the page prints each
# designator twice, once large and once small, over each other. And KiCad's
# silkscreen cream on white paper is barely darker than the paper.
MONTAGEM = (
    ("F.SilkS", "5 - montagem da frente: serigrafia"),
    ("B.SilkS", "6 - montagem do verso: serigrafia"),
)
CONTEXTO = "Edge.Cuts"


def exporta(saida: pathlib.Path, camadas: str, pb: bool = False) -> None:
    """One layer to one PDF, on whatever kicad-cli this machine has.

    `--page-size-mode 2 --exclude-drawing-sheet` crops the page to the board
    and is what one wants here, but it only exists from KiCad 9: the 8.0.6
    on this machine answers "Unknown argument: --page-size-mode" and exports
    nothing at all. So it is tried, and dropped if the binary does not know
    it; the board is then cropped afterwards by bbox_placa.
    """
    base = [str(KICAD), "pcb", "export", "pdf", "--output", str(saida),
            "--layers", camadas] + (["--black-and-white"] if pb else [])
    novo = base + ["--page-size-mode", "2", "--exclude-drawing-sheet", str(PCB)]
    r = subprocess.run(novo, capture_output=True, text=True)
    if r.returncode != 0 and "page-size-mode" in (r.stdout + r.stderr):
        r = subprocess.run(base + [str(PCB)], capture_output=True, text=True)
    if r.returncode != 0 or not saida.exists():
        raise SystemExit(f"kicad-cli falhou em {camadas}: "
                         f"{(r.stderr or r.stdout).strip()[:200]}")


def bbox_placa(pagina):
    """The board's rectangle on a page that still carries the drawing sheet.

    Without the crop above, the page is a whole sheet with the board on it,
    and enlarging the sheet enlarges mostly white paper: at 1:1 a 48 x 16 mm
    board printed in the top left eighth of an A4. Every vector on the page
    is measured and the ones covering more than half of it, which is the
    sheet's frame and title block, are left out; what remains is the board.
    """
    import fitz
    r = fitz.Rect()
    area_pg = abs(pagina.rect.get_area())
    for d in pagina.get_drawings():
        rr = d["rect"]
        if abs(rr.get_area()) > 0.5 * area_pg:
            continue
        r |= rr
    return r if not r.is_empty else pagina.rect


def main() -> int:
    try:
        import fitz
    except ImportError:
        print("PyMuPDF nao esta instalado: sem ele nao da para juntar as "
              "paginas", file=sys.stderr)
        return 2
    if not KICAD.exists():
        print(f"kicad-cli nao esta em {KICAD}", file=sys.stderr)
        return 2

    tmp = HERE / "_2d"
    tmp.mkdir(exist_ok=True)
    junto = fitz.open()
    paginas = []
    for camada, silk, rotulo in COBRE:
        p = tmp / (camada.replace(".", "_") + ".pdf")
        exporta(p, camada + ("," + silk if silk else "") + "," + CONTEXTO)
        paginas.append((p, rotulo))
    for i, (camadas, rotulo) in enumerate(MONTAGEM):
        p = tmp / ("montagem%d.pdf" % i)
        exporta(p, camadas + "," + CONTEXTO, pb=True)
        paginas.append((p, rotulo))
    todas = tmp / "todas.pdf"
    exporta(todas, ",".join(c for c, _s, _r in COBRE) +
            ",F.SilkS,B.SilkS," + CONTEXTO)
    paginas.append((todas, "7 - as quatro camadas juntas"))

    # Each layer goes on its own A4 landscape, ENLARGED and centred, with
    # the scale written down, a scale bar and a title block. At 1:1 a
    # 50 x 16 mm board prints in the top left eighth of the sheet with the
    # rest blank and no scale declared, which is unreadable on screen and
    # on paper - the owner's reviewer said so on 2026-09-27.
    import make_dxf as MD
    import make_sch as MS

    A4 = (841.89, 595.28)          # landscape, in points
    PT = 72.0 / 25.4               # points per millimetre
    MARGEM_PT = 40.0
    CARIMBO_PT = 58.0
    util = (A4[0] - 2 * MARGEM_PT, A4[1] - 2 * MARGEM_PT - CARIMBO_PT)
    # the largest whole-number scale that fits, capped at 6:1 - beyond that
    # the copper is a poster and the eye gains nothing
    escala = max(1, min(6, int(min(util[0] / (MD.W * PT),
                                   util[1] / (MD.H * PT)))))
    larg, alt = MD.W * PT * escala, MD.H * PT * escala
    x0 = (A4[0] - larg) / 2.0
    y0 = MARGEM_PT + (util[1] - alt) / 2.0

    for p, rotulo in paginas:
        d = fitz.open(p)
        origem = d[0]
        # When kicad-cli could not crop (KiCad 8), the page is a whole sheet:
        # crop it to the board here, so what gets enlarged is the copper and
        # not the paper around it. A little air is left so the outline does
        # not touch the frame.
        alvo = bbox_placa(origem)
        if alvo != origem.rect:
            alvo = (alvo + (-2, -2, 2, 2)) & origem.rect
            origem.set_cropbox(alvo)
        pag = junto.new_page(width=A4[0], height=A4[1])
        pag.show_pdf_page(fitz.Rect(x0, y0, x0 + larg, y0 + alt), d, 0)
        d.close()
        pag.draw_rect(fitz.Rect(x0, y0, x0 + larg, y0 + alt),
                      color=(0.75, 0.75, 0.75), width=0.4)
        pag.insert_text((MARGEM_PT, MARGEM_PT - 14), rotulo,
                        fontsize=12, fontname="hebo")
        # the scale bar: ten millimetres of board, drawn at the same scale
        bx, by = MARGEM_PT, A4[1] - MARGEM_PT - CARIMBO_PT + 30
        dez = 10.0 * PT * escala
        pag.draw_line(fitz.Point(bx, by), fitz.Point(bx + dez, by),
                      color=(0, 0, 0), width=1.2)
        for q in (bx, bx + dez):
            pag.draw_line(fitz.Point(q, by - 4), fitz.Point(q, by + 4),
                          color=(0, 0, 0), width=1.2)
        pag.insert_text((bx + dez + 6, by + 3), "10 mm", fontsize=9,
                        fontname="helv")
        # and the title block, bottom right
        cx = A4[0] - MARGEM_PT - 300
        cy = A4[1] - MARGEM_PT - CARIMBO_PT + 14
        pag.draw_rect(fitz.Rect(cx, cy - 12, A4[0] - MARGEM_PT, cy + 40),
                      color=(0.4, 0.4, 0.4), width=0.6)
        pag.insert_text((cx + 8, cy), "Bike Power Meter - placa",
                        fontsize=10, fontname="hebo")
        pag.insert_text((cx + 8, cy + 14),
                        f"{rotulo}   escala {escala}:1   "
                        f"{MD.W:g} x {MD.H:g} x {MD.THICKNESS:g} mm",
                        fontsize=8, fontname="helv")
        pag.insert_text((cx + 8, cy + 26), f"{MS.DATA}   4 camadas   "
                        "hardware_powermeter/cad/make_2d.py",
                        fontsize=8, fontname="helv")
        pag.insert_text((cx + 8, cy + 36),
                        "NADA FOI FABRICADO, MONTADO NEM MEDIDO",
                        fontsize=8, fontname="hebo", color=(0.6, 0.1, 0.1))
    # the deliverable lives in placa/, beside the 2D SVG and the assembly
    # drawing; cad/ keeps the sources (2026-09-26)
    saida = HERE.parent / "placa" / "pmeter-pcb.pdf"
    saida.parent.mkdir(parents=True, exist_ok=True)
    junto.save(saida, garbage=3, deflate=True)
    junto.close()
    for p, _r in paginas:
        p.unlink()
    tmp.rmdir()
    print(f"{saida.name}: {len(paginas)} paginas, uma por camada de cobre "
          "mais a de conjunto")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
