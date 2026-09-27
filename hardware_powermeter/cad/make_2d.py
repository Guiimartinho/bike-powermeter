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
    r = subprocess.run(
        [str(KICAD), "pcb", "export", "pdf", "--output", str(saida),
         "--layers", camadas]
        + (["--black-and-white"] if pb else []) + [str(PCB)],
        capture_output=True, text=True)
    if r.returncode != 0 or not saida.exists():
        raise SystemExit(f"kicad-cli falhou em {camadas}: {r.stderr.strip()}")


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

    for p, rotulo in paginas:
        d = fitz.open(p)
        junto.insert_pdf(d)
        pag = junto[-1]
        pag.insert_text((36, 28), rotulo, fontsize=11, fontname="helv")
        d.close()
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
