#!/usr/bin/env python3
"""The whole thing on the crank arm: gauges, wires, pod and board.

Every other view in this project shows one piece at a time, and the
question that keeps coming back is where the sensor actually is. It is not
in the pod: the bridge is bonded to the ARM, which is the elastic element,
and five wires carry it up into the board. This draws that, from the same
geometry the pod is generated from.

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
  - the bridge is ONE piece and its size is real: the S5229 pattern of the
    transducer-class databook, 4,0 x 3,7 mm of carrier with four grids on
    it, two along the arm and two across (the Poisson bridge). It is drawn
    off the middle line of the face on purpose, because the middle line is
    the neutral axis and bending strain there is zero. WHERE along the arm
    it is bonded, and how far off the middle, are still open, and they are
    what set the slope: nothing here has been bonded to a crank.
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

# The wires, in the usual load-cell colours (06-conectores, J301). The
# bridge itself has FOUR: the S5229 is a complete bridge on one carrier, so
# only its two corners of excitation and two of signal come out. The fifth
# hole of J301 is the cable's shield, which is not a gauge terminal, and it
# is drawn from the same place because that is where the cable is.
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
BRACO_ESP = PD.BRACO_ESP   # do make_pod: a `PD6` mede a antena contra ela
BOSS_EIXO_R, BOSS_PEDAL_R = 17.0, 11.0
MEIA_LARG_EIXO, MEIA_LARG_PEDAL = 15.0, 10.0

FACE_Z = -PD.COLA       # the arm's inner face, under the pod's glue line
FUNDO_Z = FACE_Z - BRACO_ESP


def meia_largura(x: float) -> float:
    """Metade da largura da face interna do braco em x, no cone do pedivela.

    Fica fora do `braco()` para a `PD17` poder MEDIR a face ao longo da faixa
    x do pod em vez de comparar com um escalar: a face vai de 27,29 mm em x = 0
    a 22,93 em x = 74,2, e o 20,0 que a regra cobrava so ocorre no eixo do
    pedal, quase 40 mm depois do fim do pod (revisao de 2026-10-01).
    """
    t = (x - EIXO_X) / (PEDAL_X - EIXO_X)
    t = min(1.0, max(0.0, t))
    return MEIA_LARG_EIXO + t * (MEIA_LARG_PEDAL - MEIA_LARG_EIXO)


def braco(m: PD.Malha) -> None:
    """The arm body plus its two bosses, tapered along x, centred on the pod."""
    cy = PD.H_P / 2.0
    meia = meia_largura

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


# ---------------------------------------------------------------- gauge
# ONE piece, not four: the S5229 full bridge, N2K-13-S5229A-50C/DG/E3.
# Every number below is off its page in the transducer-class databook
# (2622-EN, rev. 12-Aug-2019, p. 58), in millimetres.
# As cotas da matriz e o lugar dela vem do `make_pod`, nao daqui: e o POD que
# reserva esse lugar - um bolso na face de baixo sobre a matriz e uma canaleta
# sobre o feixe de fios -, e as duas coisas tem de usar o mesmo numero. Ate
# 2026-10-01 o lugar estava escrito aqui e o pod nao sabia dele: os cinco fios
# corriam ate 44,83 mm dentro da linha de cola de 0,50 mm.
MATRIZ_W, MATRIZ_H = PD.GAUGE_W, PD.GAUGE_H
GRADE_L, GRADE_W = 0.71, 1.13    # one grid: length along its own axis, width
GRADE_ESP = 0.05                 # foil plus carrier
ILHA = 0.55                      # the four gold solder tabs (DG)
CENTRO_X = PD.GAUGE_X
# Across the arm the bridge sits OFF the middle: the middle line of the face
# is the neutral axis, where bending strain is zero. How far off is still
# open and it is what sets the slope (docs/06).
DESLOC_Y = PD.GAUGE_DESLOC_Y


def _ret(cx, cy, w, h):
    return [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2),
            (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)]


def extensometros(m: PD.Malha) -> list:
    """The S5229: four grids on one carrier, bonded once.

    Two grids run along the arm and two across it, which is the Poisson
    bridge the databook's drawing shows: under bending the longitudinal pair
    reads +e and the transverse pair -v.e, so the four arms of the bridge
    add up. It gives about two thirds of a pure bending bridge and still
    some six times what a 45 degree shear pattern would (docs/06).

    Returns the four solder tabs, which is where the wires start.
    """
    cy = PD.H_P / 2.0 - DESLOC_Y
    cx = CENTRO_X
    m.extrusao(_ret(cx, cy, MATRIZ_W, MATRIZ_H), FACE_Z, FACE_Z + GRADE_ESP,
               COR_CARRIER)
    z0, z1 = FACE_Z + GRADE_ESP, FACE_Z + GRADE_ESP * 2
    # the two longitudinal grids, above the centre line of the carrier
    for dx in (-0.85, 0.85):
        m.extrusao(_ret(cx + dx, cy - 0.85, GRADE_W, GRADE_L), z0, z1, COR_GRADE)
    # and the two transverse ones, below it, turned a quarter
    for dx in (-0.85, 0.85):
        m.extrusao(_ret(cx + dx, cy + 0.85, GRADE_L, GRADE_W), z0, z1, COR_GRADE)
    # the four gold tabs along the lower edge, where the cable is soldered
    ilhas = []
    for k in range(4):
        tx = cx - 1.35 + k * 0.9
        ty = cy + MATRIZ_H / 2.0 - ILHA / 2.0
        m.extrusao(_ret(tx, ty, ILHA, ILHA), z0, z1 + 0.01, (0.85, 0.72, 0.35))
        ilhas.append((tx, ty))
    centros = ilhas
    return centros


def ilhas_da_ponte(pecas) -> list:
    """The five bridge pads, where they really are, not where they look nice.

    J301 is read from the placed board and its box turned into five centres
    at the footprint's 2,0 mm pitch, so the wires in the picture land on the
    pads the board actually has (06-conectores-e-pontos-de-teste.md, J301).
    """
    x0, y0, x1, y1 = PD.no_pod(pecas["J301"]["caixa"])
    cy = (y0 + y1) / 2.0
    meia = (x1 - x0) / 2.0 - 1.25            # half a pad in from each end
    cx = (x0 + x1) / 2.0
    return [(cx - meia + 2.0 * k * meia / 4.0, cy) for k in range(5)]


def fios(m: PD.Malha, pod: PD.Pod, centros: list, ilhas: list, z_topo: float) -> None:
    """Five wires from the gauge to the five plated holes of the board.

    They leave the tabs as a BUNDLE, run along the arm inside the pod's wire
    channel, turn up its leg to the slot and only there fan out to the five
    holes, where the solder is the strain relief. Routed through the channel
    and not straight to each pad because the straight route crossed up to
    44,83 mm of glued floor (revision of 2026-10-01); the channel's two legs
    come from `Pod.canaleta_fios()`, so the groove and the wires cannot drift
    apart. Drawn with the real OUTSIDE diameter, insulation included.
    """
    d = PD.FIO_PONTE_D
    trechos = pod.canaleta_fios()
    if not trechos:
        return
    (_a0, cy0, xa1, cy1), (xb0, _b1, xb2, yb3) = trechos
    cy = (cy0 + cy1) / 2.0
    xf = (xb0 + xb2) / 2.0
    for k, (nome, cor) in enumerate(FIOS):
        ax, ay = centros[min(k, len(centros) - 1)]
        px, py = ilhas[k]
        o = (k - (len(FIOS) - 1) / 2.0) * PD.FIO_PONTE_PASSO
        # 1. da ilha da matriz ate a linha do feixe, em DOIS trechos retos e nao
        #    numa caixa unica: a caixa unica cobria o retangulo inteiro entre os
        #    dois pontos e saia da canaleta por 0,075 mm ao longo de 35 mm, o que
        #    a `PD25` mediu como 14,9 mm2 de fio sem cola por cima.
        m.caixa(ax - d / 2, min(ay, cy + o) - d / 2, FACE_Z,
                ax + d / 2, max(ay, cy + o) + d / 2, FACE_Z + d, cor)
        m.caixa(min(ax, xf + o) - d / 2, cy + o - d / 2, FACE_Z,
                max(ax, xf + o) + d / 2, cy + o + d / 2, FACE_Z + d, cor)
        # 2. pela perna da canaleta, ate dentro do rasgo
        m.caixa(xf + o - d / 2, cy + o - d / 2, FACE_Z,
                xf + o + d / 2, max(py, yb3) + d / 2, FACE_Z + d, cor)
        # 3. dentro do rasgo, abrindo para o furo de cada um
        m.caixa(min(xf + o, px) - d / 2, py - d / 2, FACE_Z,
                max(xf + o, px) + d / 2, py + d / 2, FACE_Z + d, cor)
        # 4. e para cima, pelo furo metalizado
        m.caixa(px - d / 2, py - d / 2, FACE_Z, px + d / 2, py + d / 2,
                z_topo, cor)


def cola(m: PD.Malha, pod: PD.Pod) -> None:
    """The adhesive film: the bonding land, minus everything carved out of it.

    It was the whole footprint until 2026-10-01, which said the pod was glued
    over 21,0 mm of a face only 15,0 mm wide and glued over the slot, the
    gauge and the wires as well.
    """
    vazios = [pod.rasgo, pod.bolso_gauge()] + pod.canaleta_fios()
    for a, b, c, d in PD.menos_retangulos(pod.base_cola(), vazios, minimo=0.0):
        m.caixa(a, b, FACE_Z, c, d, 0.0, COR_COLA)


def main() -> int:
    pecas = PD.ler_placa()
    pod = PD.Pod(pecas)

    ilhas = ilhas_da_ponte(pecas)
    base = PD.Malha()
    braco(base)
    centros = extensometros(base)

    concha, tampa = pod.concha(), pod.tampa()
    placa, celula = PD.placa_3d(), pod.celula_3d()

    # assembled: the pod closed on the arm, the way it is ridden. The wires
    # end at the board's underside, which is where the holes are.
    m_cola = PD.Malha()
    cola(m_cola, pod)
    m_fios = PD.Malha()
    fios(m_fios, pod, centros, ilhas, PD.PLACA_Z0)
    t, c = PD.juntar(base, m_cola, m_fios, concha, celula, placa, tampa,
                     pod.junta_3d())
    PD.renderizar(t, c, "conjunto-3d-montado.png", 1900, 1000, 205.0, 34.0)

    # opened: the pod lifted, the wires stretched to the board they solder
    # into, so the path gauge -> slot -> hole is one continuous thing
    dz = 26.0
    m_fios2 = PD.Malha()
    fios(m_fios2, pod, centros, ilhas, PD.PLACA_Z0 + dz)
    t, c = PD.juntar(base, m_fios2,
                     PD.deslocar(PD.juntar(concha, celula, placa), dz),
                     PD.deslocar(PD.juntar(tampa, pod.junta_3d()), dz + 16.0))
    PD.renderizar(t, c, "conjunto-3d-aberto.png", 1900, 1200, 205.0, 26.0)

    # close up on the arm alone: the bridge and the five wires standing where
    # they enter the pod, which is the part nobody had seen
    m_fios3 = PD.Malha()
    fios(m_fios3, pod, centros, ilhas, FACE_Z + 5.0)
    t, c = PD.juntar(base, m_fios3)
    PD.renderizar(t, c, "conjunto-3d-extensometros.png", 1700, 900, 210.0, 46.0)

    # The whole product, one layer at a time, from the arm up: the bridge
    # bonded to it, the wires, the shell with the cell in its cradle, the
    # board, the O-ring and the lid. Every piece someone has to hold during
    # assembly is in this one picture, in the order they are held.
    m_fios4 = PD.Malha()
    fios(m_fios4, pod, centros, ilhas, PD.PLACA_Z0 + 30.0)
    t, c = PD.juntar(
        base, m_fios4,
        PD.deslocar(PD.juntar(concha, celula), 22.0),
        PD.deslocar(placa, 40.0),
        pod.anel_oring(52.0),
        PD.deslocar(PD.juntar(tampa, pod.junta_3d()), 60.0))
    PD.renderizar(t, c, "conjunto-3d-produto.png", 1900, 1500, 205.0, 22.0)

    # And the same stack from almost straight on, which is the view that
    # reads as a drawing rather than as a photograph.
    PD.renderizar(t, c, "conjunto-3d-produto-lateral.png", 1500, 1600, 200.0, 8.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
