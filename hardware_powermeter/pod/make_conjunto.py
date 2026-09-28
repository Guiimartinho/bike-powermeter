#!/usr/bin/env python3
"""The whole thing on the crank arm: gauges, wires, pod and board.

Every other view in this project shows one piece at a time, and the
question that keeps coming back is where the sensor actually is. It is not
in the pod: the four strain gauges are bonded to the ARM, which is the
elastic element, and five wires carry the bridge up into the board. This
draws that, from the same geometry the pod is generated from.

    python hardware_powermeter/pod/make_conjunto.py

Two views in docs/img/hardware/: conjunto-3d-montado.png, the pod closed on
the arm, and conjunto-3d-aberto.png, the pod lifted so the gauges and the
wires show.

What is real and what is a placeholder, because the difference matters:

  - the pod, the board, the cell and the parts are the project's own
    geometry, the same one that makes the STL;
  - the ARM is a placeholder. Nobody has measured the owner's crank yet
    (07-pod.md, Lugares reservados), so it is drawn from the class: 170 mm
    between the two axes, a body that tapers from 30 to 20 mm of width and
    is 14 mm thick, a spindle boss of 34 mm and a pedal boss of 22. It is
    there to show WHERE things sit, not to be fabricated from;
  - the gauges are drawn at the size of a transducer-class shear pattern
    (about 6 x 4 mm of carrier), in the 45 degree pair that reads torque
    (01-lista-de-componentes.md, Extensometros). Where exactly along the
    arm they are bonded is still open, and it is what sets the slope.
"""
from __future__ import annotations

import math
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "cad"))

import make_pod as PD                                    # noqa: E402

# ---------------------------------------------------------------- colours
COR_BRACO = (0.34, 0.35, 0.38)      # anodised aluminium, matt
COR_BOSS = (0.30, 0.31, 0.34)
COR_GRADE = (0.72, 0.45, 0.20)      # the gauge's copper grid on its carrier
COR_CARRIER = (0.88, 0.84, 0.72)    # the polyimide carrier under it
COR_COLA = (0.55, 0.52, 0.45)

# the five wires, in the usual load-cell colours (06-conectores, J301)
FIOS = (
    ("E+", (0.70, 0.13, 0.13)),
    ("S+", (0.15, 0.50, 0.22)),
    ("S-", (0.88, 0.88, 0.88)),
    ("E-", (0.10, 0.10, 0.10)),
    ("SH", (0.55, 0.55, 0.58)),
)

# ------------------------------------------------------------------- arm
# Placeholder geometry, from the class and not from a measured crank.
EIXO_X = -46.0          # spindle axis, in the pod's frame (pod x starts at 0)
PEDAL_X = 124.0         # pedal axis: the two are 170 mm apart
BRACO_ESP = 14.0        # body thickness
BOSS_EIXO_R, BOSS_PEDAL_R = 17.0, 11.0
MEIA_LARG_EIXO, MEIA_LARG_PEDAL = 15.0, 10.0

FACE_Z = -PD.COLA       # the arm's inner face, under the pod's glue line
FUNDO_Z = FACE_Z - BRACO_ESP


def braco(m: PD.Malha) -> None:
    """The arm body plus its two bosses, tapered along x, centred on the pod."""
    cy = PD.H_P / 2.0

    def meia(x: float) -> float:
        t = (x - EIXO_X) / (PEDAL_X - EIXO_X)
        t = min(1.0, max(0.0, t))
        return MEIA_LARG_EIXO + t * (MEIA_LARG_PEDAL - MEIA_LARG_EIXO)

    passos = 24
    xs = [EIXO_X + (PEDAL_X - EIXO_X) * k / passos for k in range(passos + 1)]
    cima = [(x, cy - meia(x)) for x in xs]
    baixo = [(x, cy + meia(x)) for x in reversed(xs)]
    m.extrusao(cima + baixo, FUNDO_Z, FACE_Z, COR_BRACO)
    m.cilindro(EIXO_X, cy, BOSS_EIXO_R, FUNDO_Z - 4.0, FACE_Z, COR_BOSS, n=28)
    m.cilindro(PEDAL_X, cy, BOSS_PEDAL_R, FUNDO_Z - 2.0, FACE_Z, COR_BOSS, n=24)
    # the two bores, drawn as a darker recess so the view reads as a crank
    m.cilindro(EIXO_X, cy, 12.0, FACE_Z - 0.4, FACE_Z + 0.01, (0.12, 0.12, 0.13), n=28)
    m.cilindro(PEDAL_X, cy, 7.1, FACE_Z - 0.4, FACE_Z + 0.01, (0.12, 0.12, 0.13), n=24)


# ---------------------------------------------------------------- gauges
GRADE_W, GRADE_H = 6.0, 4.0     # carrier of a transducer-class shear pattern
GRADE_ESP = 0.05                # foil plus carrier: five hundredths of a mm
CENTRO_X = 26.0                 # under the pod, where the bridge's wires land


def _retangulo_girado(cx, cy, w, h, ang):
    ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    pts = []
    for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
        pts.append((cx + dx * ca - dy * sa, cy + dx * sa + dy * ca))
    return pts


def extensometros(m: PD.Malha) -> list:
    """Four gauges at 45 degrees, two stretching and two compressing.

    A torque in the arm shows up as shear, and a grid at 45 degrees to the
    axis is what reads shear while cancelling bending: the pair at +45 goes
    into tension and the pair at -45 into compression, which is exactly what
    the four arms of a full bridge want (docs/06, Da ponte ao torque).
    """
    cy = PD.H_P / 2.0
    postos = [(CENTRO_X - 7.0, cy - 4.5, +45.0), (CENTRO_X - 7.0, cy + 4.5, -45.0),
              (CENTRO_X + 7.0, cy - 4.5, -45.0), (CENTRO_X + 7.0, cy + 4.5, +45.0)]
    centros = []
    for cx, gy, ang in postos:
        base = _retangulo_girado(cx, gy, GRADE_W, GRADE_H, ang)
        m.extrusao(base, FACE_Z, FACE_Z + GRADE_ESP, COR_CARRIER)
        grade = _retangulo_girado(cx, gy, GRADE_W * 0.62, GRADE_H * 0.55, ang)
        m.extrusao(grade, FACE_Z + GRADE_ESP, FACE_Z + GRADE_ESP * 2, COR_GRADE)
        centros.append((cx, gy))
    return centros


def fios(m: PD.Malha, centros: list, z_topo: float) -> None:
    """Five wires from the gauges to the slot in the pod's floor.

    They lie on the arm, gather under the pod and rise through the slot into
    the five plated holes on the board's edge (06-conectores, J301). Drawn as
    thin square wires so the picture reads; a real one is round, 30 AWG.
    """
    cy = PD.H_P / 2.0
    d = 0.32
    alvo_x = CENTRO_X + 11.0
    for k, (nome, cor) in enumerate(FIOS):
        y = cy - 3.0 + k * 1.5
        x0 = centros[min(k, len(centros) - 1)][0]
        # along the arm to the gathering point
        m.caixa(min(x0, alvo_x), y - d / 2, FACE_Z, max(x0, alvo_x), y + d / 2,
                FACE_Z + d, cor)
        # then up into the pod
        m.caixa(alvo_x - d / 2, y - d / 2, FACE_Z, alvo_x + d / 2, y + d / 2,
                z_topo, cor)


def cola(m: PD.Malha) -> None:
    """The adhesive film between the arm's face and the pod's floor."""
    m.caixa(0.6, 0.6, FACE_Z, PD.W_P - 0.6, PD.H_P - 0.6, 0.0, COR_COLA)


def main() -> int:
    pecas = PD.ler_placa()
    pod = PD.Pod(pecas)

    base = PD.Malha()
    braco(base)
    centros = extensometros(base)

    concha, tampa = pod.concha(), pod.tampa()
    placa, celula = PD.placa_3d(), pod.celula_3d()

    # assembled: the pod closed on the arm, the way it is ridden
    m_cola = PD.Malha()
    cola(m_cola)
    m_fios = PD.Malha()
    fios(m_fios, centros, PD.PLACA_Z0)
    t, c = PD.juntar(base, m_cola, m_fios, concha, celula, placa, tampa,
                     pod.junta_3d())
    PD.renderizar(t, c, "conjunto-3d-montado.png", 1900, 1000, 205.0, 34.0)

    # opened: the pod lifted, so the gauges and the wires are visible
    dz = 26.0
    m_fios2 = PD.Malha()
    fios(m_fios2, centros, FACE_Z + 6.0)
    t, c = PD.juntar(base, m_fios2,
                     PD.deslocar(PD.juntar(concha, celula, placa), dz),
                     PD.deslocar(PD.juntar(tampa, pod.junta_3d()), dz + 16.0))
    PD.renderizar(t, c, "conjunto-3d-aberto.png", 1900, 1200, 205.0, 26.0)

    # close up on the gauges alone, which is the part nobody has seen
    t, c = PD.juntar(base, m_fios2)
    PD.renderizar(t, c, "conjunto-3d-extensometros.png", 1700, 900, 210.0, 46.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
