#!/usr/bin/env python3
"""The crank pod, drawn around today's board: 2D (a PDF), 3D (PNG views)
and STL.

The pod is drawn AROUND the board and the cell, never the other way round
(the same rule as the bike computer's case, hardware_gnssbike/caixa): it
reads cad/pmeter.kicad_pcb with every footprint's courtyard, height and
face, plus the GLB the 3D renderer uses, and dry_run_pod.py measures this
file against the board.

What is decided HERE, and is a proposal until the owner says otherwise
(page 3 of the PDF repeats it):
  - a shallow box glued to the inner face of the left crank arm: walls of
    1,2, floor and lid of 1,0, corner radius 3; outside it is the board
    plus 0,5 of play on three sides and a 2,5 mm channel at the left end
    where the cell's leads rise from under the board to the JST on top;
  - the stack, from the arm up: glue 0,5 (not part of the pod), floor 1,0,
    cell 4,0, air 0,5, board 0,8, the module 2,4 plus 0,3 of air under the
    lid, lid 1,0: the height printed by main() and measured by the dry
    run against the 8,5 of docs/02, which this stack does NOT meet (docs/02
    says so too: 8,5 needs the cell beside the board, and 60 x 20 has no
    room for that beside a board this long);
  - the cell LYING UNDER THE BOARD, on the floor between the two ledges
    that carry the board's long edges, held by a rib at its right end and
    by the potting; the envelope reserved for it is 25 x 15 x 4 mm (the
    100 to 150 mAh class; the exact cell is not chosen, and the envelope
    is what the chosen one has to fit);
  - the board on the ledges and on two posts at its left end (the cell
    starts 2,5 mm further right, so the posts stand beside its end);
  - the magnetic connector through a window in the lid, its face in a
    0,7 mm well where the cable's magnetic head lands, with a flat gasket
    ring round the well; a 2,5 mm light hole over the LED, to be filled
    with clear resin; the bridge's wires up from the arm through a slot in
    the floor straight under the board's five plated holes;
  - the cavity potted to the lid's underside, the lid glued on its lip.

Run:  python hardware_powermeter/pod/make_pod.py (after the board's chain:
      it reads cad/pmeter.kicad_pcb and the GLB that dry_run_pcb.py exports)
Out:  here, pmeter-pod.pdf (3 pages) and the STL files pod-concha.stl and
      pod-tampa.stl (triangle soups of overlapping boxes, for a slicer, not
      a CAD solid); in docs/img/hardware/, pod-3d-aberta.png,
      pod-3d-fechada.png and pod-3d-explodida.png.
"""

from __future__ import annotations

import math
import pathlib
import struct
import sys

import fitz
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent          # hardware_powermeter/pod
CAD = HERE.parent / "cad"                                # the board's sources
IMG = HERE.parents[1] / "docs" / "img" / "hardware"      # the rendered views
sys.path.insert(0, str(CAD))

import dry_run_pcb as DR      # noqa: E402
import footprints as FPS      # noqa: E402
import make_3d as M3          # noqa: E402
import make_dxf as MD         # noqa: E402
import make_pcb as MP         # noqa: E402

# ----------------------------------------------------------------- the pod
PAREDE, FUNDO, TAMPA = 1.2, 1.0, 1.0
R_P = 3.0
FOLGA_PLACA = 0.5             # board to wall, right end and both long sides
CANAL_FIO = 2.5               # left end: the cell's leads rise here to the JST
RESSALTO = 0.6                # the ledge under the board's edges
PLACA_W, PLACA_H, PLACA_ESP = MD.W, MD.H, MD.THICKNESS
# the envelope reserved for the cell (docs/02, Pod: 100 to 150 mAh, with
# its own protection): 25 x 15 x 4,0 is what fits between the ledges and
# short of the bridge's holes; the chosen cell has to fit it, not the other
# way round, and 07-pod.md says which classes do
CELULA_W, CELULA_H, CELULA_ESP, CELULA_VAO = 23.0, 15.0, 4.0, 0.5
# From the board's left end, and the number is set by the SLOT: the
# bridge's five holes are at the middle of the board and the floor is cut
# under them (pod x 30,45 to 40,95, measured on 2026-09-27), so the cell
# has to end before that cut with room for the rib that holds it. Left of
# the slot there are 28,65 mm between the ledges; the two posts take the
# first 6,2, which leaves 23 for the cell and 0,6 for the rib. That is why
# the envelope is 23 mm long and not the 25 this started with, and it is
# also why the cell cannot simply be made longer to hold more charge.
CELULA_DESLOC = 2.5
TETO = MD.TETO_TAMPA          # the ceiling over the front parts (2,7)
JANELA_FOLGA = 0.3            # the lid's window round the connector's courtyard
JUNTA_LARG, JUNTA_REBAIXO = 1.5, 0.3
LED_FURO = 2.5
# The floor slot round the bridge's holes. 0,4 and not 0,5: at 0,5 the cut
# ran 0,05 mm under the bottom ledge, which is what the board rests on
# (PD7, measured 2026-09-27). 0,4 still leaves 0,35 mm of clearance round a
# 0,9 mm hole.
RASGO_FOLGA = 0.4
PILAR_D = 2.0
NERVURA = 0.6
COLA = 0.5                    # glue between the arm and the floor (not drawn)
ALVO = (60.0, 20.0, 8.5)      # docs/02, Requisitos: the envelope target
MASSA_ALVO = 20.0             # docs/02: module with cell, in grams
# densities, g/cm3, for the mass ESTIMATE (page 3 says they are estimates):
# printed resin or nylon, silicone potting, FR-4, a LiPo pouch (3,5 g for a
# 401530), and the parts as a solid at the density of a small IC package
DENS_POD, DENS_ENVASE, DENS_FR4, DENS_CELULA, DENS_PECAS = 1.15, 1.0, 1.85, 2.0, 2.5

# ------------------------------------------------ where everything sits
W_P = PAREDE + CANAL_FIO + PLACA_W + FOLGA_PLACA + PAREDE
H_P = PLACA_H + 2.0 * (FOLGA_PLACA + PAREDE)
PLACA_X0 = PAREDE + CANAL_FIO
PLACA_Y0 = PAREDE + FOLGA_PLACA
CELULA_Z0 = FUNDO
CELULA_Z1 = FUNDO + CELULA_ESP
PLACA_Z0 = CELULA_Z1 + CELULA_VAO
PLACA_Z1 = PLACA_Z0 + PLACA_ESP
TAMPA_Z0 = PLACA_Z1 + TETO
T_P = TAMPA_Z0 + TAMPA
CELULA_X0 = PLACA_X0 + CELULA_DESLOC
CELULA_Y0 = (H_P - CELULA_H) / 2.0
# The lid's lip, inside the walls. 0,4 wide and 0,1 of play, not 0,8 and
# 0,15: the lip drops into the same 0,5 mm the board leaves to the wall,
# and at 0,95 it came down on the module's 2,4 mm body (PD12).
ABA_ALT, ABA_LARG, ABA_FOLGA = 1.0, 0.4, 0.1

COR_POD = (0.22, 0.23, 0.26)
COR_TAMPA = (0.27, 0.28, 0.31)
COR_CELULA = (0.30, 0.31, 0.34)
COR_JUNTA = (0.55, 0.30, 0.28)
COR_LED = (0.80, 0.80, 0.55)


# ------------------------------------------------------------ geometry
def contorno_arredondado(x0, y0, x1, y1, r, n=6):
    """A rounded rectangle as a closed polyline (y down), n points per corner."""
    pts = []
    cantos = ((x1 - r, y0 + r, -90.0), (x1 - r, y1 - r, 0.0),
              (x0 + r, y1 - r, 90.0), (x0 + r, y0 + r, 180.0))
    for cx, cy, a0 in cantos:
        for k in range(n + 1):
            a = math.radians(a0 + 90.0 * k / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def poligono_regular(cx, cy, r, n=12):
    return [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n))
            for k in range(n)]


def triangular(pts):
    """Ear clipping of a simple polygon (any winding), as index triples."""
    n = len(pts)
    if n < 3:
        return []
    area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
               for i in range(n))
    idx = list(range(n)) if area > 0 else list(range(n))[::-1]

    def convexo(a, b, c):
        return ((pts[b][0] - pts[a][0]) * (pts[c][1] - pts[a][1])
                - (pts[b][1] - pts[a][1]) * (pts[c][0] - pts[a][0])) > 1e-12

    def dentro(p, a, b, c):
        def s(u, v, w):
            return (v[0] - u[0]) * (w[1] - u[1]) - (v[1] - u[1]) * (w[0] - u[0])
        d1, d2, d3 = s(pts[a], pts[b], p), s(pts[b], pts[c], p), s(pts[c], pts[a], p)
        return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))

    out = []
    guarda = 0
    while len(idx) > 3 and guarda < 10 * n:
        guarda += 1
        for k in range(len(idx)):
            a, b, c = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            if not convexo(a, b, c):
                continue
            if any(dentro(pts[j], a, b, c) for j in idx if j not in (a, b, c)):
                continue
            out.append((a, b, c))
            del idx[k]
            break
    if len(idx) == 3:
        out.append(tuple(idx))
    return out


class Malha:
    """A pile of triangles with a colour each, in mm, y down, z up."""

    def __init__(self):
        self.tris: list = []
        self.cols: list = []

    def tri(self, a, b, c, cor):
        self.tris.append(np.array([a, b, c], dtype=np.float64))
        self.cols.append(np.array(cor))

    def quad(self, a, b, c, d, cor):
        self.tri(a, b, c, cor)
        self.tri(a, c, d, cor)

    def caixa(self, x0, y0, z0, x1, y1, z1, cor):
        b = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)]
        t = [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        self.quad(b[0], b[3], b[2], b[1], cor)
        self.quad(t[0], t[1], t[2], t[3], cor)
        for k in range(4):
            a, c = k, (k + 1) % 4
            self.quad(b[a], b[c], t[c], t[a], cor)

    def extrusao(self, pts, z0, z1, cor):
        """Any simple polygon (plan, y down) extruded between two heights."""
        for a, b, c in triangular(pts):
            self.tri((*pts[a], z0), (*pts[c], z0), (*pts[b], z0), cor)
            self.tri((*pts[a], z1), (*pts[b], z1), (*pts[c], z1), cor)
        n = len(pts)
        for k in range(n):
            a, b = pts[k], pts[(k + 1) % n]
            self.quad((a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1), cor)

    def anel(self, fora, dentro, z0, z1, cor):
        """The wall between two closed polylines of equal length."""
        n = len(fora)
        for k in range(n):
            a, b = fora[k], fora[(k + 1) % n]
            c, d = dentro[k], dentro[(k + 1) % n]
            self.quad((a[0], a[1], z0), (b[0], b[1], z0), (d[0], d[1], z0), (c[0], c[1], z0), cor)
            self.quad((a[0], a[1], z1), (c[0], c[1], z1), (d[0], d[1], z1), (b[0], b[1], z1), cor)
            self.quad((a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1), cor)
            self.quad((c[0], c[1], z0), (c[0], c[1], z1), (d[0], d[1], z1), (d[0], d[1], z0), cor)

    def placa_com_furos(self, x0, y0, x1, y1, z0, z1, furos, cor):
        """A plate minus rectangular holes: the grid of cells between the
        holes' edges, every cell wholly inside a hole left out."""
        xs = sorted({x0, x1} | {f[0] for f in furos if x0 < f[0] < x1} | {f[2] for f in furos if x0 < f[2] < x1})
        ys = sorted({y0, y1} | {f[1] for f in furos if y0 < f[1] < y1} | {f[3] for f in furos if y0 < f[3] < y1})
        for i in range(len(xs) - 1):
            for j in range(len(ys) - 1):
                cx, cy = (xs[i] + xs[i + 1]) / 2.0, (ys[j] + ys[j + 1]) / 2.0
                if any(f[0] <= cx <= f[2] and f[1] <= cy <= f[3] for f in furos):
                    continue
                self.caixa(xs[i], ys[j], z0, xs[i + 1], ys[j + 1], z1, cor)

    def cilindro(self, cx, cy, r, z0, z1, cor, n=12):
        self.extrusao(poligono_regular(cx, cy, r, n), z0, z1, cor)

    def arrays(self):
        if not self.tris:
            return np.zeros((0, 3, 3)), np.zeros((0, 3))
        return np.array(self.tris), np.array(self.cols)

    def stl(self, caminho: pathlib.Path) -> int:
        """Binary STL, in mm, as the slicer wants it."""
        with open(caminho, "wb") as f:
            f.write(b"pmeter pod, generated by make_pod.py".ljust(80, b"\0"))
            f.write(struct.pack("<I", len(self.tris)))
            for t in self.tris:
                n = np.cross(t[1] - t[0], t[2] - t[0])
                ln = np.linalg.norm(n)
                n = n / ln if ln > 0 else n
                f.write(struct.pack("<3f", *n))
                for v in t:
                    f.write(struct.pack("<3f", *v))
                f.write(struct.pack("<H", 0))
        return len(self.tris)


# ------------------------------------------------------------ the board
def ler_placa():
    pecas, _pads, _seg, _vias, _cortes = DR.ler(CAD / "pmeter.kicad_pcb")
    for ref, p in pecas.items():
        nome_fp = FPS.FP.get(ref, ("", 0, 0))[0]
        alt = DR.altura_do_footprint(nome_fp) if nome_fp else None
        p["altura"] = alt[0] if alt else 1.0
    return pecas


def no_pod(caixa):
    """A box in board coordinates to pod coordinates."""
    x0, y0, x1, y1 = caixa
    return (PLACA_X0 + x0, PLACA_Y0 + y0, PLACA_X0 + x1, PLACA_Y0 + y1)


class Pod:
    """Everything the pod has, derived from the placed board."""

    def __init__(self, pecas):
        self.pecas = pecas
        if "J101" not in pecas:
            raise SystemExit("J101 (o conector magnetico) nao esta na placa")
        j = pecas["J101"]
        x0, y0, x1, y1 = no_pod(j["caixa"])
        f = JANELA_FOLGA
        self.janela = (x0 - f, y0 - f, x1 + f, y1 + f)
        self.conector_alt = j["altura"]
        # the well: from the lid's top down to the connector's face
        self.poco = T_P - (PLACA_Z1 + self.conector_alt)
        self.junta = (self.janela[0] - JUNTA_LARG, self.janela[1] - JUNTA_LARG,
                      self.janela[2] + JUNTA_LARG, self.janela[3] + JUNTA_LARG)
        d = pecas.get("D201")
        self.led = None
        if d:
            bx0, by0, bx1, by1 = no_pod(d["caixa"])
            self.led = ((bx0 + bx1) / 2.0, (by0 + by1) / 2.0)
        # the slot in the floor under the bridge's holes
        self.rasgo = None
        j3 = pecas.get("J301")
        if j3 and j3["pads"]:
            xs = [q["x"] for q in j3["pads"]]
            ys = [q["y"] for q in j3["pads"]]
            r = max(q["hw"] for q in j3["pads"])
            self.rasgo = (PLACA_X0 + min(xs) - r - RASGO_FOLGA, PLACA_Y0 + min(ys) - r - RASGO_FOLGA,
                          PLACA_X0 + max(xs) + r + RASGO_FOLGA, PLACA_Y0 + max(ys) + r + RASGO_FOLGA)
        self.pilares = [(PLACA_X0 + 1.2, PLACA_Y0 + 1.5),
                        (PLACA_X0 + 1.2, PLACA_Y0 + PLACA_H - 1.5)]
        # the rib at the cell's right end, short of the slot
        nx0 = CELULA_X0 + CELULA_W + 0.2
        nx1 = nx0 + NERVURA
        if self.rasgo:
            nx1 = min(nx1, self.rasgo[0] - 0.2)
        self.nervura = (nx0, nx1)
        # the module's antenna band, in pod coordinates (the same 4,46 mm
        # the board's dry run measures)
        self.antena = None
        if DR.MODULO in pecas:
            mx0, my0, mx1, my1 = no_pod(pecas[DR.MODULO]["caixa"])
            self.antena = (mx1 - DR.ANT_MOD, my0, mx1, my1)

    # ------------------------------------------------------------- solids
    def contornos(self, folga=0.0):
        fora = contorno_arredondado(0.0, 0.0, W_P, H_P, R_P)
        dentro = contorno_arredondado(PAREDE + folga, PAREDE + folga, W_P - PAREDE - folga,
                                      H_P - PAREDE - folga, max(0.3, R_P - PAREDE - folga))
        return fora, dentro

    def concha(self) -> Malha:
        m = Malha()
        fora, dentro = self.contornos()
        m.anel(fora, dentro, 0.0, TAMPA_Z0, COR_POD)
        furos = [self.rasgo] if self.rasgo else []
        m.placa_com_furos(PAREDE, PAREDE, W_P - PAREDE, H_P - PAREDE, 0.0, FUNDO, furos, COR_POD)
        # the ledges under the board's long edges and its right end
        m.caixa(PAREDE, PAREDE, FUNDO, W_P - PAREDE, PAREDE + RESSALTO, PLACA_Z0, COR_POD)
        m.caixa(PAREDE, H_P - PAREDE - RESSALTO, FUNDO, W_P - PAREDE, H_P - PAREDE, PLACA_Z0, COR_POD)
        m.caixa(W_P - PAREDE - RESSALTO, PAREDE, FUNDO, W_P - PAREDE, H_P - PAREDE, PLACA_Z0, COR_POD)
        for cx, cy in self.pilares:
            m.cilindro(cx, cy, PILAR_D / 2.0, FUNDO, PLACA_Z0, COR_POD)
        nx0, nx1 = self.nervura
        if nx1 > nx0:
            m.caixa(nx0, PAREDE + RESSALTO, FUNDO, nx1, H_P - PAREDE - RESSALTO, CELULA_Z1 - 0.5, COR_POD)
        return m

    def tampa(self, dz: float = 0.0) -> Malha:
        m = Malha()
        fora, dentro = self.contornos()
        z0, z1 = TAMPA_Z0 + dz, T_P + dz
        m.anel(fora, dentro, z0, z1, COR_TAMPA)
        furos = [self.janela]
        if self.led:
            lx, ly = self.led
            furos.append((lx - LED_FURO / 2, ly - LED_FURO / 2, lx + LED_FURO / 2, ly + LED_FURO / 2))
        m.placa_com_furos(PAREDE, PAREDE, W_P - PAREDE, H_P - PAREDE, z0, z1, furos, COR_TAMPA)
        # the lip that drops inside the walls
        aba_fora = contorno_arredondado(PAREDE + ABA_FOLGA, PAREDE + ABA_FOLGA, W_P - PAREDE - ABA_FOLGA,
                                        H_P - PAREDE - ABA_FOLGA, max(0.3, R_P - PAREDE - ABA_FOLGA))
        aba_dentro = contorno_arredondado(PAREDE + ABA_FOLGA + ABA_LARG, PAREDE + ABA_FOLGA + ABA_LARG,
                                          W_P - PAREDE - ABA_FOLGA - ABA_LARG, H_P - PAREDE - ABA_FOLGA - ABA_LARG,
                                          max(0.3, R_P - PAREDE - ABA_FOLGA - ABA_LARG))
        m.anel(aba_fora, aba_dentro, z0 - ABA_ALT, z0, COR_TAMPA)
        return m

    def junta_3d(self, dz: float = 0.0) -> Malha:
        """The flat gasket ring round the well, drawn for the views."""
        m = Malha()
        jx0, jy0, jx1, jy1 = self.junta
        wx0, wy0, wx1, wy1 = self.janela
        z0, z1 = T_P - JUNTA_REBAIXO + dz, T_P + 0.2 + dz
        m.placa_com_furos(jx0, jy0, jx1, jy1, z0, z1, [(wx0, wy0, wx1, wy1)], COR_JUNTA)
        return m

    def celula_3d(self, dz: float = 0.0) -> Malha:
        m = Malha()
        m.caixa(CELULA_X0, CELULA_Y0, CELULA_Z0 + dz, CELULA_X0 + CELULA_W, CELULA_Y0 + CELULA_H,
                CELULA_Z1 + dz, COR_CELULA)
        # the leads, folded up the channel to the JST on the board's top
        m.caixa(PAREDE + 0.3, CELULA_Y0 + CELULA_H / 2 - 1.0, CELULA_Z0 + dz, CELULA_X0,
                CELULA_Y0 + CELULA_H / 2 + 1.0, CELULA_Z0 + 1.0 + dz, COR_CELULA)
        return m

    # -------------------------------------------------------------- mass
    def volumes(self) -> dict:
        """Volumes in mm3, analytic, of what the pod holds and is made of."""
        a_fora = W_P * H_P - (4.0 - math.pi) * R_P ** 2
        ri = R_P - PAREDE
        a_dentro = (W_P - 2 * PAREDE) * (H_P - 2 * PAREDE) - (4.0 - math.pi) * ri ** 2
        v_paredes = (a_fora - a_dentro) * (TAMPA_Z0 - FUNDO)
        v_fundo = a_fora * FUNDO
        if self.rasgo:
            v_fundo -= (self.rasgo[2] - self.rasgo[0]) * (self.rasgo[3] - self.rasgo[1]) * FUNDO
        v_ressaltos = (2 * (W_P - 2 * PAREDE) + (H_P - 2 * PAREDE)) * RESSALTO * (PLACA_Z0 - FUNDO)
        v_pilares = len(self.pilares) * math.pi * (PILAR_D / 2) ** 2 * (PLACA_Z0 - FUNDO)
        nx0, nx1 = self.nervura
        v_nervura = max(0.0, nx1 - nx0) * (H_P - 2 * PAREDE - 2 * RESSALTO) * (CELULA_Z1 - 0.5 - FUNDO)
        v_concha = v_fundo + v_paredes + v_ressaltos + v_pilares + v_nervura
        jx0, jy0, jx1, jy1 = self.janela
        v_tampa = a_fora * TAMPA - (jx1 - jx0) * (jy1 - jy0) * TAMPA
        if self.led:
            v_tampa -= LED_FURO ** 2 * TAMPA
        ra = R_P - PAREDE - ABA_FOLGA
        a_aba_fora = (W_P - 2 * (PAREDE + ABA_FOLGA)) * (H_P - 2 * (PAREDE + ABA_FOLGA)) - (4 - math.pi) * ra ** 2
        rb = max(0.3, ra - ABA_LARG)
        a_aba_dentro = (W_P - 2 * (PAREDE + ABA_FOLGA + ABA_LARG)) * (H_P - 2 * (PAREDE + ABA_FOLGA + ABA_LARG)) - (4 - math.pi) * rb ** 2
        v_tampa += (a_aba_fora - a_aba_dentro) * ABA_ALT
        v_placa = PLACA_W * PLACA_H * PLACA_ESP
        v_celula = CELULA_W * CELULA_H * CELULA_ESP
        # the parts as solids at 70 % of their courtyard box: a courtyard
        # is the body plus 0,25 a side, and most bodies are not full boxes
        v_pecas = 0.0
        for ref, p in self.pecas.items():
            if p["atras"]:
                continue
            x0, y0, x1, y1 = p["caixa"]
            v_pecas += 0.7 * (x1 - x0) * (y1 - y0) * p["altura"]
        v_cavidade = a_dentro * (TAMPA_Z0 - FUNDO) - v_ressaltos - v_pilares - v_nervura
        v_envase = v_cavidade - v_placa - v_celula - v_pecas - (a_aba_fora - a_aba_dentro) * ABA_ALT
        return {"concha": v_concha, "tampa": v_tampa, "placa": v_placa, "celula": v_celula,
                "pecas": v_pecas, "envase": max(0.0, v_envase), "cavidade": v_cavidade}

    def massa(self) -> dict:
        v = self.volumes()
        g = {"concha": v["concha"] / 1000 * DENS_POD, "tampa": v["tampa"] / 1000 * DENS_POD,
             "placa": v["placa"] / 1000 * DENS_FR4, "celula": v["celula"] / 1000 * DENS_CELULA,
             "pecas": v["pecas"] / 1000 * DENS_PECAS, "envase": v["envase"] / 1000 * DENS_ENVASE}
        g["total"] = sum(g.values())
        return g


def placa_3d() -> tuple[np.ndarray, np.ndarray]:
    """The board, from the sources make_3d.py draws it from, moved to where
    the pod holds it (the GLB and the bodies are in the sheet's frame, the
    board's top-left at make_pcb.ORIGEM)."""
    glb = M3._glb_atual()
    if glb is None:
        raise SystemExit("sem GLB da placa: rode dry_run_pcb.py ou make_3d.py")
    j, bina = M3.ler_glb(glb)
    pt, pc = M3.triangulos(j, bina)
    pt = np.stack([pt[..., 0] * 1000.0, -pt[..., 1] * 1000.0, pt[..., 2] * 1000.0], axis=-1)
    extra_t, extra_c = M3.caixas_das_pecas()
    silk_t, silk_c = M3.serigrafia()
    partes_t = [pt] + ([extra_t] if len(extra_t) else []) + ([silk_t] if len(silk_t) else [])
    partes_c = [pc] + ([extra_c] if len(extra_c) else []) + ([silk_c] if len(silk_c) else [])
    t = np.concatenate(partes_t) + np.array([PLACA_X0 - MP.ORIGEM[0], PLACA_Y0 - MP.ORIGEM[1], PLACA_Z0])
    return t, np.concatenate(partes_c)


def juntar(*malhas) -> tuple[np.ndarray, np.ndarray]:
    ts, cs = [], []
    for m in malhas:
        if isinstance(m, tuple):
            t, c = m
        else:
            t, c = m.arrays()
        if len(t):
            ts.append(t)
            cs.append(c)
    return np.concatenate(ts), np.concatenate(cs)


def deslocar(tc, dz: float):
    t, c = tc
    return t + np.array([0.0, 0.0, dz]), c


def renderizar(t, c, nome, w, h, az, el):
    t = np.stack([t[..., 0], -t[..., 1], t[..., 2]], axis=-1) / 1000.0
    img = M3.render(t, c, w, h, az, el)
    IMG.mkdir(parents=True, exist_ok=True)
    img.save(IMG / nome)
    print(f"  {IMG.relative_to(HERE.parents[1]) / nome}: {len(t)} triangulos")


# ------------------------------------------------------------------ 2D
S = 7.0


class Vista:
    def __init__(self, page, x0, y0, s=S):
        self.page, self.x0, self.y0, self.s = page, x0, y0, s

    def P(self, x, y):
        return fitz.Point(self.x0 + x * self.s, self.y0 + y * self.s)

    def rect(self, x0, y0, x1, y1, cor=(0, 0, 0), fill=None, largura=0.5, tracejado=None):
        sh = self.page.new_shape()
        sh.draw_rect(fitz.Rect(self.P(x0, y0), self.P(x1, y1)))
        sh.finish(color=cor, fill=fill, width=largura, dashes=tracejado)
        sh.commit()

    def poli(self, pts, cor=(0, 0, 0), fill=None, largura=0.8, tracejado=None):
        sh = self.page.new_shape()
        sh.draw_polyline([self.P(x, y) for x, y in pts] + [self.P(*pts[0])])
        sh.finish(color=cor, fill=fill, width=largura, dashes=tracejado, closePath=True)
        sh.commit()

    def linha(self, x1, y1, x2, y2, cor=(0.3, 0.3, 0.3), largura=0.5, tracejado=None):
        sh = self.page.new_shape()
        sh.draw_line(self.P(x1, y1), self.P(x2, y2))
        sh.finish(color=cor, width=largura, dashes=tracejado)
        sh.commit()

    def circulo(self, x, y, r, cor=(0, 0, 0), fill=None, largura=0.5):
        sh = self.page.new_shape()
        sh.draw_circle(self.P(x, y), r * self.s)
        sh.finish(color=cor, fill=fill, width=largura)
        sh.commit()

    def texto(self, x, y, s, tam=6.0, cor=(0.1, 0.1, 0.1), rot=0):
        self.page.insert_text(self.P(x, y), s, fontsize=tam, fontname="helv", color=cor, rotate=rot)

    def cota_h(self, y, x1, x2, s, acima=True):
        self.linha(x1, y, x2, y, (0.4, 0.4, 0.4), 0.4)
        for x in (x1, x2):
            self.linha(x, y - 0.6, x, y + 0.6, (0.4, 0.4, 0.4), 0.4)
        self.texto((x1 + x2) / 2 - len(s) * 0.4, y - 0.6 if acima else y + 1.6, s, 5.5, (0.35, 0.35, 0.35))

    def cota_v(self, x, y1, y2, s):
        self.linha(x, y1, x, y2, (0.4, 0.4, 0.4), 0.4)
        for y in (y1, y2):
            self.linha(x - 0.6, y, x + 0.6, y, (0.4, 0.4, 0.4), 0.4)
        self.texto(x + 0.8, (y1 + y2) / 2 + 0.6, s, 5.5, (0.35, 0.35, 0.35))


def _t(page, x, y, s, tam=10.0, negrito=True):
    page.insert_text(fitz.Point(x, y), s, fontsize=tam, fontname="hebo" if negrito else "helv",
                     color=(0.1, 0.1, 0.12))


def _paragrafo(page, x, y, s, tam, largura=780.0):
    linha = ""
    for w in s.split():
        prova = (linha + " " + w).strip()
        if fitz.get_text_length(prova, fontname="helv", fontsize=tam) > largura:
            page.insert_text(fitz.Point(x, y), linha, fontsize=tam, fontname="helv", color=(0.12, 0.12, 0.12))
            y += tam + 3
            linha = w
        else:
            linha = prova
    if linha:
        page.insert_text(fitz.Point(x, y), linha, fontsize=tam, fontname="helv", color=(0.12, 0.12, 0.12))
        y += tam + 3
    return y


def f2(v):
    return f"{v:.1f}".replace(".", ",")


def pagina_1(doc, pod: Pod):
    """Plan view: the pod from above with the lid off, and the lid."""
    page = doc.new_page(width=842, height=595)
    _t(page, 30, 30, f"Pod do medidor de potencia - planta, {f2(W_P)} x {f2(H_P)} x {f2(T_P)} mm por fora. "
                     "PROPOSTA: NADA IMPRESSO NEM MEDIDO.", 11)
    _t(page, 30, 46, "Sem a tampa, vista de cima (o braco fica embaixo da folha). Cinza: a concha; azul: as pecas "
                     "da frente da placa; tracejado: a celula sob a placa; vermelho: a janela do conector e o rasgo dos fios.",
       8, False)
    v = Vista(page, 60, 90)
    fora, dentro = pod.contornos()
    v.poli(fora, (0.2, 0.2, 0.2), (0.86, 0.86, 0.88), 0.8)
    v.poli(dentro, (0.3, 0.3, 0.3), (0.97, 0.97, 0.97), 0.5)
    # ledges, posts, rib
    v.rect(PAREDE, PAREDE, W_P - PAREDE, PAREDE + RESSALTO, (0.5, 0.5, 0.5), (0.8, 0.8, 0.82), 0.3)
    v.rect(PAREDE, H_P - PAREDE - RESSALTO, W_P - PAREDE, H_P - PAREDE, (0.5, 0.5, 0.5), (0.8, 0.8, 0.82), 0.3)
    v.rect(W_P - PAREDE - RESSALTO, PAREDE, W_P - PAREDE, H_P - PAREDE, (0.5, 0.5, 0.5), (0.8, 0.8, 0.82), 0.3)
    for cx, cy in pod.pilares:
        v.circulo(cx, cy, PILAR_D / 2, (0.4, 0.4, 0.4), (0.8, 0.8, 0.82), 0.3)
    nx0, nx1 = pod.nervura
    if nx1 > nx0:
        v.rect(nx0, PAREDE + RESSALTO, nx1, H_P - PAREDE - RESSALTO, (0.4, 0.4, 0.4), (0.8, 0.8, 0.82), 0.3)
    # the cell (under the board) and its leads
    v.rect(CELULA_X0, CELULA_Y0, CELULA_X0 + CELULA_W, CELULA_Y0 + CELULA_H, (0.2, 0.2, 0.5), None, 0.6, [2, 2])
    v.texto(CELULA_X0 + 1.0, CELULA_Y0 + CELULA_H - 1.0, f"celula {f2(CELULA_W)} x {f2(CELULA_H)} x {f2(CELULA_ESP)} (envelope)", 5.0, (0.2, 0.2, 0.5))
    # the board and its front parts
    v.rect(PLACA_X0, PLACA_Y0, PLACA_X0 + PLACA_W, PLACA_Y0 + PLACA_H, (0.1, 0.35, 0.1), None, 0.8)
    for ref, p in sorted(pod.pecas.items()):
        x0, y0, x1, y1 = no_pod(p["caixa"])
        if p["atras"]:
            v.rect(x0, y0, x1, y1, (0.6, 0.4, 0.2), None, 0.3, [1, 1])
        else:
            v.rect(x0, y0, x1, y1, (0.2, 0.3, 0.6), (0.85, 0.88, 0.95), 0.3)
        if (x1 - x0) * (y1 - y0) > 12.0:
            v.texto(x0 + 0.3, y0 + 1.4, ref, 4.0, (0.2, 0.3, 0.6))
    if pod.antena:
        ax0, ay0, ax1, ay1 = pod.antena
        v.rect(ax0, ay0, ax1, ay1, (0.7, 0.2, 0.2), None, 0.4, [1, 1])
        v.texto(ax0 - 6.0, ay0 - 0.6, "antena", 4.0, (0.7, 0.2, 0.2))
    # the window and the slot
    v.rect(*pod.janela, (0.8, 0.1, 0.1), None, 0.7)
    v.rect(*pod.junta, (0.8, 0.1, 0.1), None, 0.4, [1, 1])
    if pod.rasgo:
        v.rect(*pod.rasgo, (0.8, 0.1, 0.1), (1.0, 0.9, 0.9), 0.6)
        v.texto(pod.rasgo[0] - 2.0, pod.rasgo[3] + 2.4, "rasgo dos fios da ponte, no fundo", 4.5, (0.8, 0.1, 0.1))
    if pod.led:
        v.circulo(pod.led[0], pod.led[1], LED_FURO / 2, (0.8, 0.1, 0.1), None, 0.5)
    # the channel for the cell's leads
    v.rect(PAREDE, PAREDE + RESSALTO, PLACA_X0, H_P - PAREDE - RESSALTO, (0.5, 0.5, 0.5), None, 0.3, [1, 1])
    v.texto(PAREDE + 0.2, PAREDE + 4.0, "canal", 3.6, (0.4, 0.4, 0.4), 90)
    # dimensions
    v.cota_h(-3.0, 0.0, W_P, f"{f2(W_P)} (alvo {ALVO[0]:g})")
    v.cota_v(W_P + 3.0, 0.0, H_P, f"{f2(H_P)} (alvo {ALVO[1]:g})")
    v.cota_h(H_P + 3.5, PLACA_X0, PLACA_X0 + PLACA_W, f"placa {f2(PLACA_W)}", False)
    v.cota_h(H_P + 7.0, PAREDE, PLACA_X0, f"canal {f2(CANAL_FIO)}", False)
    v.cota_h(H_P + 7.0, PLACA_X0 + PLACA_W, W_P - PAREDE, f"{f2(FOLGA_PLACA)}", False)
    v.cota_v(-3.0, PLACA_Y0, PLACA_Y0 + PLACA_H, f"placa {f2(PLACA_H)}")
    jx0, jy0, jx1, jy1 = pod.janela
    v.cota_h(-6.5, jx0, jx1, f"janela {f2(jx1 - jx0)} x {f2(jy1 - jy0)}, poco de {f2(pod.poco)}")
    # the lid, drawn below
    y_t = H_P + 16.0
    v.texto(0.0, y_t - 1.0, "A tampa, vista de cima: janela do conector com a junta em volta, furo do LED, aba por dentro das paredes.", 6.0)
    fora_t = [(x, y + y_t) for x, y in fora]
    v.poli(fora_t, (0.2, 0.2, 0.2), (0.90, 0.90, 0.92), 0.8)
    aba = contorno_arredondado(PAREDE + ABA_FOLGA, PAREDE + ABA_FOLGA + y_t, W_P - PAREDE - ABA_FOLGA,
                               H_P - PAREDE - ABA_FOLGA + y_t, max(0.3, R_P - PAREDE - ABA_FOLGA))
    v.poli(aba, (0.4, 0.4, 0.4), None, 0.3, [1, 1])
    v.rect(jx0, jy0 + y_t, jx1, jy1 + y_t, (0.8, 0.1, 0.1), (1.0, 1.0, 1.0), 0.7)
    v.rect(pod.junta[0], pod.junta[1] + y_t, pod.junta[2], pod.junta[3] + y_t, (0.8, 0.3, 0.3), None, 0.5, [1, 1])
    if pod.led:
        v.circulo(pod.led[0], pod.led[1] + y_t, LED_FURO / 2, (0.8, 0.1, 0.1), (1.0, 1.0, 1.0), 0.5)
        v.texto(pod.led[0] + 2.0, pod.led[1] + y_t + 1.0, "LED", 4.0, (0.8, 0.1, 0.1))
    # legend
    y = 90 + (2 * H_P + 30.0) * S + 20
    y = _paragrafo(page, 60, y, "Cores: cinza claro, a concha vista de cima com os ressaltos das bordas, os dois pilares "
                                "da ponta esquerda e a nervura que segura a celula; verde, o contorno da placa; azul, o contorno "
                                "de ocupacao de cada peca da frente (os pontos de teste ficam atras, em laranja tracejado); "
                                "vermelho, a janela do conector na tampa, a junta em volta dela, o furo de luz do LED e o rasgo "
                                "no fundo por onde os cinco fios da ponte sobem do braco ate os furos metalizados da placa.", 8)
    _t(page, 30, 575, "hardware_powermeter/pod/make_pod.py - pagina 1 de 3 - medidas em mm", 7, False)


def pagina_2(doc, pod: Pod):
    """The two sections: across the pod through the cell, and along it."""
    page = doc.new_page(width=842, height=595)
    _t(page, 30, 30, "Cortes: a pilha de alturas. A esquerda o corte transversal pelo meio da celula, "
                     "a direita o longitudinal pelo eixo da placa. PROPOSTA.", 11)
    s = 9.0
    # ---- across (y, z), at x = middle of the cell
    v = Vista(page, 60, 320, s)

    def yz(y0, z0, y1, z1, cor, fill, largura=0.5, tracejado=None):
        v.rect(y0, -z1, y1, -z0, cor, fill, largura, tracejado)

    yz(0.0, 0.0, H_P, FUNDO, (0.2, 0.2, 0.2), (0.86, 0.86, 0.88))
    yz(0.0, 0.0, PAREDE, TAMPA_Z0, (0.2, 0.2, 0.2), (0.86, 0.86, 0.88))
    yz(H_P - PAREDE, 0.0, H_P, TAMPA_Z0, (0.2, 0.2, 0.2), (0.86, 0.86, 0.88))
    yz(PAREDE, FUNDO, PAREDE + RESSALTO, PLACA_Z0, (0.2, 0.2, 0.2), (0.8, 0.8, 0.82))
    yz(H_P - PAREDE - RESSALTO, FUNDO, H_P - PAREDE, PLACA_Z0, (0.2, 0.2, 0.2), (0.8, 0.8, 0.82))
    yz(0.0, TAMPA_Z0, H_P, T_P, (0.2, 0.2, 0.2), (0.90, 0.90, 0.92))
    yz(PAREDE + ABA_FOLGA, TAMPA_Z0 - ABA_ALT, PAREDE + ABA_FOLGA + ABA_LARG, TAMPA_Z0, (0.2, 0.2, 0.2), (0.90, 0.90, 0.92))
    yz(H_P - PAREDE - ABA_FOLGA - ABA_LARG, TAMPA_Z0 - ABA_ALT, H_P - PAREDE - ABA_FOLGA, TAMPA_Z0, (0.2, 0.2, 0.2), (0.90, 0.90, 0.92))
    yz(CELULA_Y0, CELULA_Z0, CELULA_Y0 + CELULA_H, CELULA_Z1, (0.2, 0.2, 0.5), (0.85, 0.85, 0.92))
    yz(PLACA_Y0, PLACA_Z0, PLACA_Y0 + PLACA_H, PLACA_Z1, (0.1, 0.35, 0.1), (0.75, 0.88, 0.75))
    # the tallest front part in this section's neighbourhood: the module
    if DR.MODULO in pod.pecas:
        m = pod.pecas[DR.MODULO]
        mx0, my0, mx1, my1 = no_pod(m["caixa"])
        yz(my0, PLACA_Z1, my1, PLACA_Z1 + m["altura"], (0.2, 0.3, 0.6), (0.85, 0.88, 0.95))
        v.texto(my0 + 0.5, -(PLACA_Z1 + m["altura"]) - 0.4, f"modulo {f2(m['altura'])}", 4.5, (0.2, 0.3, 0.6))
    yz(0.0, -COLA, H_P, 0.0, (0.5, 0.4, 0.2), (0.95, 0.9, 0.8), 0.3, [1, 1])
    v.texto(H_P / 2 - 6.0, COLA + 2.2, f"cola ao braco {f2(COLA)} (fora do pod)", 4.5, (0.5, 0.4, 0.2))
    v.cota_v(H_P + 2.0, -T_P, 0.0, f"{f2(T_P)} (alvo {ALVO[2]:g})")
    v.cota_v(H_P + 6.5, -CELULA_Z1, -CELULA_Z0, f"celula {f2(CELULA_ESP)}")
    v.cota_v(H_P + 6.5, -PLACA_Z1, -PLACA_Z0, f"placa {f2(PLACA_ESP)}")
    v.cota_v(H_P + 6.5, -TAMPA_Z0, -PLACA_Z1, f"teto {f2(TETO)}")
    v.cota_v(H_P + 6.5, -T_P, -TAMPA_Z0, f"tampa {f2(TAMPA)}")
    v.cota_v(H_P + 6.5, -FUNDO, 0.0, f"fundo {f2(FUNDO)}")
    v.cota_h(2.5, 0.0, H_P, f"{f2(H_P)}", False)
    v.texto(0.0, -T_P - 2.0, "corte transversal (y, z), pelo meio da celula", 6.0)
    # ---- along (x, z), at y = middle of the board
    v2 = Vista(page, 60, 520, 8.0)

    def xz(x0, z0, x1, z1, cor, fill, largura=0.5, tracejado=None):
        v2.rect(x0, -z1, x1, -z0, cor, fill, largura, tracejado)

    xz(0.0, 0.0, W_P, FUNDO, (0.2, 0.2, 0.2), (0.86, 0.86, 0.88))
    if pod.rasgo:
        xz(pod.rasgo[0], 0.0, pod.rasgo[2], FUNDO, (0.8, 0.1, 0.1), (1.0, 1.0, 1.0), 0.5)
        v2.texto(pod.rasgo[0], FUNDO + 2.4, "rasgo", 4.5, (0.8, 0.1, 0.1))
    xz(0.0, 0.0, PAREDE, TAMPA_Z0, (0.2, 0.2, 0.2), (0.86, 0.86, 0.88))
    xz(W_P - PAREDE, 0.0, W_P, TAMPA_Z0, (0.2, 0.2, 0.2), (0.86, 0.86, 0.88))
    xz(W_P - PAREDE - RESSALTO, FUNDO, W_P - PAREDE, PLACA_Z0, (0.2, 0.2, 0.2), (0.8, 0.8, 0.82))
    for cx, _cy in pod.pilares[:1]:
        xz(cx - PILAR_D / 2, FUNDO, cx + PILAR_D / 2, PLACA_Z0, (0.2, 0.2, 0.2), (0.8, 0.8, 0.82))
    nx0, nx1 = pod.nervura
    if nx1 > nx0:
        xz(nx0, FUNDO, nx1, CELULA_Z1 - 0.5, (0.2, 0.2, 0.2), (0.8, 0.8, 0.82))
    xz(0.0, TAMPA_Z0, W_P, T_P, (0.2, 0.2, 0.2), (0.90, 0.90, 0.92))
    jx0, _jy0, jx1, _jy1 = pod.janela
    xz(jx0, TAMPA_Z0, jx1, T_P, (0.8, 0.1, 0.1), (1.0, 1.0, 1.0), 0.5)
    xz(CELULA_X0, CELULA_Z0, CELULA_X0 + CELULA_W, CELULA_Z1, (0.2, 0.2, 0.5), (0.85, 0.85, 0.92))
    xz(PLACA_X0, PLACA_Z0, PLACA_X0 + PLACA_W, PLACA_Z1, (0.1, 0.35, 0.1), (0.75, 0.88, 0.75))
    for ref in ("J101", DR.MODULO, "U101", "J102", "U301", "J201"):
        p = pod.pecas.get(ref)
        if not p or p["atras"]:
            continue
        x0, _y0, x1, _y1 = no_pod(p["caixa"])
        xz(x0, PLACA_Z1, x1, PLACA_Z1 + p["altura"], (0.2, 0.3, 0.6), (0.85, 0.88, 0.95), 0.3)
        v2.texto(x0 + 0.2, -(PLACA_Z1 + p["altura"]) - 0.4, ref, 4.0, (0.2, 0.3, 0.6))
    v2.cota_h(-T_P - 3.0, 0.0, W_P, f"{f2(W_P)}")
    v2.cota_h(2.5, PAREDE, PLACA_X0, f"canal {f2(CANAL_FIO)}", False)
    v2.cota_h(2.5, CELULA_X0, CELULA_X0 + CELULA_W, f"celula {f2(CELULA_W)}", False)
    v2.cota_v(W_P + 2.0, -(PLACA_Z1 + pod.conector_alt), -T_P, f"poco {f2(pod.poco)}")
    v2.texto(0.0, -T_P - 5.0, "corte longitudinal (x, z), pelo eixo da placa; as pecas mais altas de cada bloco", 6.0)
    _t(page, 30, 575, "hardware_powermeter/pod/make_pod.py - pagina 2 de 3 - medidas em mm", 7, False)


def conflitos(pod: Pod) -> list[str]:
    """What this drawing knows is unresolved."""
    out = []
    if T_P > ALVO[2]:
        out.append(f"altura de {f2(T_P)} mm contra o alvo de {ALVO[2]:g}: a pilha celula sob a placa nao "
                   "chega a 8,5 (docs/02 ja diz que 8,5 pede a celula ao lado)")
    if W_P > ALVO[0]:
        out.append(f"comprimento de {f2(W_P)} mm contra o alvo de {ALVO[0]:g}: a placa de {f2(PLACA_W)} "
                   f"mais o canal dos fios da celula ({f2(CANAL_FIO)}) e as paredes")
    if H_P > ALVO[1]:
        out.append(f"largura de {f2(H_P)} mm contra o alvo de {ALVO[1]:g}")
    out.append("o conector magnetico e generico: a janela e o poco seguem o contorno de ocupacao de 18 x 5 x 3 "
               "e mudam com a peca escolhida")
    out.append("as medidas do braco (largura da face interna, folga ao quadro, raio da concordancia) sao "
               "LUGARES RESERVADOS ate serem medidas no pedivela do dono")
    return out


def pagina_3(doc, pod: Pod):
    page = doc.new_page(width=842, height=595)
    _t(page, 30, 30, "O que esta decidido aqui, o que e estimativa e o que falta medir", 11)
    y = 52
    g = pod.massa()
    y = _paragrafo(page, 30, y, f"Envelope: {f2(W_P)} x {f2(H_P)} x {f2(T_P)} mm por fora (alvo de docs/02: "
                                f"{ALVO[0]:g} x {ALVO[1]:g} x {ALVO[2]:g}), mais {f2(COLA)} de cola ao braco. Paredes {f2(PAREDE)}, "
                                f"fundo {f2(FUNDO)}, tampa {f2(TAMPA)}, raio dos cantos {f2(R_P)}. A pilha, do braco para cima: "
                                f"fundo {f2(FUNDO)}, celula {f2(CELULA_ESP)}, ar {f2(CELULA_VAO)}, placa {f2(PLACA_ESP)}, "
                                f"teto {f2(TETO)} (modulo de 2,4 mais 0,3), tampa {f2(TAMPA)}.", 9)
    y += 6
    y = _paragrafo(page, 30, y, "Massa ESTIMADA por volume e densidade, nao pesada (densidades: pod impresso 1,15; "
                                "envase de silicone 1,0; FR-4 1,85; celula 2,0; pecas 2,5 g/cm3 sobre 70 % do contorno de "
                                "ocupacao vezes a altura):", 9)
    for k, rot in (("concha", "concha"), ("tampa", "tampa"), ("placa", "placa nua"), ("pecas", "pecas da placa"),
                   ("celula", "celula (envelope cheio)"), ("envase", "envase ate a tampa")):
        _t(page, 50, y, f"{rot:<28} {g[k]:5.1f} g".replace(".", ","), 9, False)
        y += 13
    _t(page, 50, y, f"{'total':<28} {g['total']:5.1f} g  (alvo {MASSA_ALVO:g} g)".replace(".", ","), 9, True)
    y += 20
    y = _paragrafo(page, 30, y, "Decidido aqui (proposta): a celula deitada SOB a placa, entre os ressaltos das bordas, presa "
                                "pela nervura na ponta direita e pelo envase, com as abas na ponta esquerda, onde um canal de "
                                f"{f2(CANAL_FIO)} mm deixa os fios subirem ate o JST SH na frente da placa; a placa apoiada nos "
                                "ressaltos e em dois pilares na ponta esquerda; o conector magnetico atravessa a tampa e a face "
                                f"dele fica num poco de {f2(pod.poco)} mm onde a cabeca magnetica do cabo assenta, com uma junta "
                                f"plana de {f2(JUNTA_LARG)} mm em volta; um furo de {f2(LED_FURO)} mm sobre o LED, a encher com "
                                "resina transparente; os fios da ponte sobem do braco por um rasgo no fundo, direto sob os cinco "
                                "furos metalizados da placa; a cavidade envasada ate a face de baixo da tampa e a tampa colada "
                                "pela aba.", 9)
    y += 6
    y = _paragrafo(page, 30, y, "LUGARES RESERVADOS, a medir no pedivela do dono antes de imprimir: largura da face interna "
                                "do braco esquerdo (____ mm; o pod tem " + f2(H_P) + "); folga entre a face interna do braco e o "
                                "quadro na pedalada (____ mm; o pod tem " + f2(T_P + COLA) + " com a cola); raio da concordancia "
                                "entre a face e o corpo do braco (____ mm; o fundo do pod e plano); posicao da ponte no braco "
                                "(distancia do eixo do pedivela ao centro do pod, ____ mm).", 9)
    y += 6
    for s in conflitos(pod):
        y = _paragrafo(page, 30, y, "- " + s, 9)
    y += 6
    y = _paragrafo(page, 30, y, "O que o dry run do pod mede (pod/dry_run_pod.py): a placa na cavidade com folga; toda peca "
                                "da frente sob o teto, menos o conector, que atravessa a tampa e cuja face tem de ficar dentro "
                                "do poco; a face de tras plana; a celula entre os ressaltos, sob a placa com o vao, longe do "
                                "rasgo, dos pilares e da area da antena; a janela sobre o conector e o furo sobre o LED; o "
                                "rasgo sob os furos da ponte; o envelope e a massa contra o alvo.", 9)
    _t(page, 30, 575, "hardware_powermeter/pod/make_pod.py - pagina 3 de 3", 7, False)


def main() -> int:
    pecas = ler_placa()
    pod = Pod(pecas)
    g = pod.massa()
    print(f"pod {W_P:.1f} x {H_P:.1f} x {T_P:.1f} (alvo {ALVO[0]:g} x {ALVO[1]:g} x {ALVO[2]:g}); "
          f"placa em x {PLACA_X0:.1f}-{PLACA_X0 + PLACA_W:.1f}, y {PLACA_Y0:.1f}-{PLACA_Y0 + PLACA_H:.1f}; "
          f"z: celula {CELULA_Z0:.1f}-{CELULA_Z1:.1f}, placa {PLACA_Z0:.1f}-{PLACA_Z1:.1f}, "
          f"tampa {TAMPA_Z0:.1f}-{T_P:.1f}; poco do conector {pod.poco:.1f}; "
          f"massa estimada {g['total']:.1f} g (alvo {MASSA_ALVO:g})")
    doc = fitz.open()
    pagina_1(doc, pod)
    pagina_2(doc, pod)
    pagina_3(doc, pod)
    doc.save(HERE / "pmeter-pod.pdf", garbage=3, deflate=True)
    print("  pmeter-pod.pdf: 3 paginas")
    for s in conflitos(pod):
        print("  - " + s)

    concha = pod.concha()
    tampa = pod.tampa()
    for nome, malha in (("pod-concha.stl", concha), ("pod-tampa.stl", tampa)):
        n = malha.stl(HERE / nome)
        print(f"  {nome}: {n} triangulos")

    placa = placa_3d()
    celula = pod.celula_3d()
    t, c = juntar(concha, celula, placa)
    renderizar(t, c, "pod-3d-aberta.png", 1800, 900, 200.0, 40.0)
    t, c = juntar(concha, celula, placa, tampa, pod.junta_3d())
    renderizar(t, c, "pod-3d-fechada.png", 1800, 900, 200.0, 62.0)
    dz_t, dz_p, dz_c = 22.0, 11.0, 0.0
    t, c = juntar(concha, pod.celula_3d(dz_c), deslocar(placa, dz_p), pod.tampa(dz_t), pod.junta_3d(dz_t))
    renderizar(t, c, "pod-3d-explodida.png", 1800, 1100, 200.0, 30.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
