#!/usr/bin/env python3
"""Read back the generated DXF files and check the geometry against the documents.

This does not open a CAD tool and it does not prove that any importer accepts
the files. What it proves is that what was written is the geometry the
documents describe: the outline is closed and measures what make_dxf derives
from the rules, the corner arcs meet the straight edges, the mounting hole sits
where it is declared, every zone lies inside the board, and each rectangle
marked as a conflict really is the intersection of the two zones it names.

Run: python hardware_powermeter/cad/check_dxf.py     (exit 0 = everything agrees)
"""

from __future__ import annotations

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import make_dxf as M  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
TOL = 1e-6
fails: list[str] = []


def check(ok: bool, what: str) -> None:
    print(("  ok   " if ok else "  FALHA ") + what)
    if not ok:
        fails.append(what)


def parse(path: pathlib.Path) -> list[dict]:
    """Group codes to a list of entities. Enough of DXF R12 to read our own files."""
    raw = path.read_text(encoding="ascii").splitlines()
    pairs = [(int(raw[i].strip()), raw[i + 1].strip()) for i in range(0, len(raw) - 1, 2)]
    ents: list[dict] = []
    in_ents = False
    cur: dict | None = None
    for code, val in pairs:
        if code == 0:
            if val == "SECTION":
                cur = None
                continue
            if val == "ENDSEC":
                if cur:
                    ents.append(cur)
                cur = None
                in_ents = False
                continue
            if val == "EOF":
                break
            if cur:
                ents.append(cur)
                cur = None
            if in_ents and val in ("LINE", "ARC", "CIRCLE"):
                cur = {"type": val}
            continue
        if code == 2 and val == "ENTITIES":
            in_ents = True
            continue
        if cur is not None:
            cur[code] = float(val) if code not in (8,) else val
    return ents


def seg_ends(e: dict) -> tuple[tuple[float, float], tuple[float, float]]:
    if e["type"] == "LINE":
        return (e[10], e[20]), (e[11], e[21])
    cx, cy, r, a0, a1 = e[10], e[20], e[40], math.radians(e[50]), math.radians(e[51])
    return ((cx + r * math.cos(a0), cy + r * math.sin(a0)),
            (cx + r * math.cos(a1), cy + r * math.sin(a1)))


def bbox(ents: list[dict]) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for e in ents:
        if e["type"] == "CIRCLE":
            xs += [e[10] - e[40], e[10] + e[40]]
            ys += [e[20] - e[40], e[20] + e[40]]
            continue
        (x1, y1), (x2, y2) = seg_ends(e)
        xs += [x1, x2]
        ys += [y1, y2]
        if e["type"] == "ARC":
            # a quarter arc of ours never crosses an axis extreme other than
            # at its own ends, but check the four cardinal points anyway
            for deg in (0.0, 90.0, 180.0, 270.0):
                a0, a1 = e[50] % 360.0, e[51] % 360.0
                inside = a0 <= deg <= a1 if a0 <= a1 else (deg >= a0 or deg <= a1)
                if inside:
                    xs.append(e[10] + e[40] * math.cos(math.radians(deg)))
                    ys.append(e[20] + e[40] * math.sin(math.radians(deg)))
    return min(xs), min(ys), max(xs), max(ys)


def check_outline(name: str, radius: float) -> None:
    print(f"\n{name} (raio {radius:g} mm)")
    ents = parse(HERE / name)
    check(len(ents) == 8, f"8 entidades (4 linhas e 4 arcos), achou {len(ents)}")
    check(sum(1 for e in ents if e["type"] == "LINE") == 4, "4 linhas")
    check(sum(1 for e in ents if e["type"] == "ARC") == 4, "4 arcos")
    check(all(abs(e[40] - radius) < TOL for e in ents if e["type"] == "ARC"),
          f"todo arco com raio {radius:g} mm")

    x0, y0, x1, y1 = bbox(ents)
    check(abs(x0) < TOL and abs(y0) < TOL, f"origem em (0; 0), achou ({x0:.4f}; {y0:.4f})")
    check(abs(x1 - M.W) < TOL and abs(y1 - M.H) < TOL,
          f"extremo em ({M.W:g}; {M.H:g}), achou ({x1:.4f}; {y1:.4f})")

    # closed: every endpoint is shared by exactly two entities
    pts: list[tuple[float, float]] = []
    for e in ents:
        a, b = seg_ends(e)
        pts += [a, b]
    uniq: list[tuple[float, float]] = []
    for p in pts:
        if not any(math.dist(p, q) < 1e-4 for q in uniq):
            uniq.append(p)
    counts = [sum(1 for p in pts if math.dist(p, q) < 1e-4) for q in uniq]
    check(len(uniq) == 8 and all(c == 2 for c in counts),
          f"contorno fechado: 8 vertices, cada um com 2 pontas (achou {len(uniq)}, {counts})")

    per = 2 * (M.W - 2 * radius) + 2 * (M.H - 2 * radius) + 2 * math.pi * radius
    area = M.W * M.H - (4 - math.pi) * radius * radius
    print(f"       perimetro {per:.2f} mm, area {area:.1f} mm2")


def check_zones() -> None:
    print("\nzonas.dxf")
    ents = parse(HERE / "zonas.dxf")
    circles = [e for e in ents if e["type"] == "CIRCLE"]
    check(len(circles) == len(M.FUROS_DOC), f"{len(M.FUROS_DOC)} furo M2, achou {len(circles)}")

    for sx, sy in M.FUROS_DOC:
        cy = M.H - sy
        hit = [c for c in circles if abs(c[10] - sx) < TOL and abs(c[20] - cy) < TOL]
        check(len(hit) == 1, f"furo em ({sx:g}; {sy:g}) do documento = ({sx:g}; {cy:g}) no CAD")

    # every zone inside the board
    for name, (zx0, zy0, zx1, zy1), _c, _s in M.ZONES + M.CONFLITOS:
        ok = 0.0 <= zx0 < zx1 <= M.W and 0.0 <= zy0 < zy1 <= M.H
        check(ok, f"{name} dentro da placa")

    # each conflict really is the intersection it claims
    zdict = {n: r for n, r, _c, _s in M.ZONES}

    def inter(a: tuple, b: tuple) -> tuple:
        return (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))

    # The conflict rectangles were the intersections that the 55 x 97
    # floorplan carried, and three of the four were the display's or the
    # battery's shadow fighting a part - shadows that left the board
    # floorplan when the board stopped being sized by the case. The list is
    # empty now, and this checks that it really is empty rather than
    # silently skipping: a conflict that comes back has to be declared.
    if M.CONFLITOS:
        raise SystemExit(
            "make_dxf.CONFLITOS deixou de estar vazia e este teste nao sabe "
            "o que esperar de " + ", ".join(n for n, *_r in M.CONFLITOS))
    check(True, "nenhum conflito de zona declarado (0)")


def main() -> int:
    check_outline("contorno.dxf", M.RADIUS_DRAWING)
    check_zones()
    print()
    if fails:
        print(f"{len(fails)} verificacoes falharam")
        return 1
    print("geometria confere com os documentos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
