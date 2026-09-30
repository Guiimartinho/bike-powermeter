#!/usr/bin/env python3
"""Write pmeter.kicad_pcb: the board, with every part placed and every net.

The outline, the stackup, the single mounting hole and the two antenna
keep-outs come from hardware_gnssbike/04-pcb-e-caixa.md. What is new here is
the placement: each part that the document gives a zone to is put in its zone,
and everything else - the decoupling, the pull-ups, the series resistors -
lands on the nearest free slot to the part it belongs to, outside the
keep-outs and off the board edge. Nothing is routed: the tracks are the
owner's job, and this is the board he starts from.

Run:   python hardware_powermeter/cad/make_pcb.py
Check: python hardware_powermeter/cad/check_pcb.py
"""

from __future__ import annotations

import hashlib
import math
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import footprints as FPS  # noqa: E402
import fp_load  # noqa: E402
import make_dxf as M  # noqa: E402
import nets as N  # noqa: E402
import parts as P  # noqa: E402

ORIGEM = (25.0, 25.0)          # where the board's top left sits on the sheet
CU = 0.035
# The stack-up is ASYMMETRIC, and that is the point. Section 4.4 of the
# MAX-F10S integration manual says to "select the stack-up, copper, and
# dielectric properties of the PCB accordingly to fulfil this condition" -
# the condition being 50 ohm on the RF line. With the dielectric split
# evenly, 0.22 mm each, a 50 ohm microstrip is 0.431 mm wide and does not fit
# between the module's pads: it cannot leave its own pin. A thin prepreg to
# the ground plane and a thick core in the middle brings it to 0.196 mm,
# which routes, and it is the usual four layer stack-up for a board with RF.
DIEL_RF = 0.10                 # F.Cu to the ground plane on In1.Cu
DIEL_NUCLEO = 0.80 - 4 * CU - 2 * DIEL_RF    # In1.Cu to In2.Cu
DIEL = (DIEL_RF, DIEL_NUCLEO, DIEL_RF)
CU_LAYERS = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
KEEPOUTS = {"KEEPOUT_ANTENA_GNSS", "KEEPOUT_ANTENA_MODULO"}
BORDA = 0.8                    # keep parts this far inside the outline
RAIO_COURTYARD_FURO = 2.45     # F.CrtYd of MountingHole_2.2mm_M2.kicad_mod
# 0,05, the bike computer's number, and it is the right one. 0,30 was tried
# on 2026-09-27 to open a routing channel between every pair of neighbours
# and it backfired, measured: the ring a decoupling capacitor searches got
# too tight to land on, `encostar()` fell through to its step-out fallback
# and the analog block scattered - C308 ended 24 mm from the switch it
# decouples and twelve of nineteen capacitors broke rule AL1. A courtyard
# already carries 0,25 mm of the maker's clearance on each side, so 0,05
# between two of them is 0,55 mm of bare board between the bodies.
FOLGA = 0.25                   # between two courtyards: the courtyard
                               # already carries the maker's clearance
PASSO = 0.5                    # placement grid

# The part that anchors each zone of 04-pcb-e-caixa.md.
# Quantas voltas de melhoria da colocacao, e ate onde cada peca procura
# lugar melhor. Ver o passe 5 de colocar().
MELHORA_VOLTAS = 3
MELHORA_RAIO = 6.0


def caixa_em(ref: str, x: float, y: float, ang: int):
    """A caixa que uma peca ocupa, ja posta em (x, y)."""
    b = caixa(ref, ang)
    return (x + b[0], y + b[1], x + b[2], y + b[3])


ANCORAS: dict[str, str] = {
    "U101": "ZONA_ENERGIA",
    "U301": "ZONA_CONVERSOR_ADS1220",
    "U401": "ZONA_SENSORES",
    "D201": "ZONA_TAG_CONNECT",
    "U201": "ZONA_MODULO_HOLYIOT",
}
# Parts that follow an anchor instead of a zone of their own.
JUNTO: dict[str, str] = {
    "U102": "U101", "L101": "U101", "J102": "U102",
    "U302": "U301", "U402": "J301", "D101": "J101",
    "R101": "U101", "R102": "U101", "R106": "U101",
    "R103": "U101", "R104": "U101", "R105": "U102",
    "R204": "U201", "R205": "U201", "C203": "FB201",
    "R109": "J101", "R110": "R109",
    "R107": "J101", "R108": "J101",
    "R201": "D201", "R202": "D201", "R203": "D201",
    "TP201": "U201", "TP202": "U201",
    # Each power test point goes beside what it measures, which is what
    # 06-conectores-e-pontos-de-teste.md asks for point by point: the VBUS one
    # beside the connector, the ground one with a via of its own to the plane.
    "TP101": "J101", "TP102": "J102", "TP103": "U101", "TP104": "U101",
    "TP301": "U302",
}
# The back face. Nothing about the case decides this: these are the parts
# that do not have to be reached from the front and that free the front face
# for the ones that do.
# J102 left this set on 2026-09-26: the cell connector is a JST SH on the
# FRONT now (see BORDA_FIXA)
# On the back face only what has no body: the test points. The pod is
# shallow because the cell lies under the board (docs/02, Pod), so the back
# has to stay flat, and a test point is a pad. They are for the bare board
# on the bench; in the pod the magnetic connector is the only access.
# The back face carries the test points, which are pads, and the passives
# that could not fit beside the module on the front. The module is 12 mm
# wide on a 16 mm board and its power pads sit on the castellated rows
# along the two 1,75 mm strips: no 0402 fits there, so its own decoupling
# had nowhere to stand and the placer was carrying it 11 to 14 mm away.
# They go underneath instead, outside the cell's shadow (make_dxf), where
# the pod's floor is recessed.
ATRAS: set[str] = set()
# A FACE DE TRAS, agora que a celula saiu de baixo da placa (2026-09-30).
#
# Antes ela so' recebia os pontos de teste e um punhado de passivos: a
# celula cobria x 1,5 a 26 do verso, ou seja o bloco de energia inteiro, e
# quem tivesse corpo nao podia ficar la. Com a celula ao lado da placa o
# verso e livre de ponta a ponta, e ele deixa de ser um recurso de ultimo
# caso para virar o lugar natural do passivo.
#
# A medida que manda: a face de CIMA tinha 55,2% de celula livre antes da
# primeira trilha - ilha e folga comiam 45% dela - contra 87,1% da In2.Cu e
# 81,6% da B.Cu, e toda falha de roteamento era "sem caminho ate (x; y) na
# camada 0". Afinar a trilha nao resolve isso, porque a ilha nao afina.
# Tirar ilha de cima, sim.
#
# Entao vai para tras TODO passivo: resistor, capacitor e o ferrite. Um
# capacitor de desacoplamento no verso, com uma via, fica SOB o pino que ele
# serve - mais perto do que qualquer lugar que sobrasse do lado de cima, que
# e o que a `AL1` vinha cobrando (11 de 19 fora do limite, ate 9 mm).
#
# Fica na frente o que precisa ser alcancado ou visto: os CIs, o modulo, os
# conectores, o LED e o indutor do buck (o laco de chaveamento nao atravessa
# a placa). O teto do verso e 1,5 mm: cabe 0402 (0,5), 0603 (0,9) e 0805
# (1,2).
for _r in list(FPS.FP):
    if _r[0] in ("R", "C") and _r[1:].isdigit():
        ATRAS.add(_r)
ATRAS |= {"FB201", "TP101", "TP102", "TP103", "TP104", "TP201", "TP202",
          "TP301"}
# ... menos estes, que tem de ficar em cima:
ATRAS -= {
    # o capacitor de saida do buck fecha o laco de chaveamento com o
    # indutor e o nPM1100, e esse laco nao pode atravessar a placa
    "C104", "C105",
}
# Experimento reproduzivel: `PMETER_TUDO_NA_FRENTE=1` poe TODA peca na face
# de cima, para comparar as duas topologias com o mesmo roteador e a mesma
# colocacao. Nao e opcao de projeto - e o botao do teste A/B.
if os.environ.get("PMETER_TUDO_NA_FRENTE") == "1":
    ATRAS.clear()
# Everything else stays on the front, and the reason is the cell: it lies
# against the back over the first 25 mm, so a part whose chip is at that
# end has nowhere underneath to go. The charger's resistors and the fuel
# gauge were tried on the back and the placer had to carry them 17 to
# 21 mm, which is the same failure in a new place.
# LS601 is on the back because of arithmetic, not taste: it is 10,5 x 9,5 mm,
# the largest part on the board after the two modules, and on the front the
# only band left between the key row and the module is 9,25 mm tall. Pushed
# out of it, the spiral parked it 0,84 mm from the TPS7A02 and took the ring
# that regulator's decoupling needed, which AL1 then reported as two
# capacitors 5,5 and 6,6 mm from a pin that wants 2. The back face was
# carrying three parts.


def passantes() -> set[str]:
    """Refs whose pads pierce the board, so they take room on both faces."""
    saida = set()
    for ref, (nome, _o, _n) in FPS.FP.items():
        try:
            texto = fp_load.carregar(nome)[0]
        except FileNotFoundError:
            continue
        arv = fp_load.parse(texto)
        for pad in fp_load.kids(arv, "pad"):
            camadas = fp_load.kid(pad, "layers")
            if len(pad) > 2 and pad[2] != "smd":
                saida.add(ref)
                break
            if camadas and any(str(c).startswith("*") for c in camadas[1:]):
                saida.add(ref)
                break
    return saida


PASSANTE = passantes()


def LIMITE_DESLOCA(ref: str) -> float:
    """How far por() may carry a part from the point it was asked for.

    A decoupling capacitor answers to its datasheet: the module's own wants
    0,5 mm from the pin and the others 2 mm for the fast ones and 5 for the
    bulk, which is what dry_run_pcb.AL1 measures pad to pad. Centres sit
    further apart than pads, so the cap here is that limit plus the half
    diagonal of a small part, rounded to something a person would accept.
    Everything else gets one number: a part that has to travel more than a
    centimetre from where it belongs is not where it belongs.
    """
    if ref.startswith("TP"):
        # A test point is a place to put a probe on. It has no loop, no
        # signal integrity and no datasheet asking for anything: it goes
        # wherever the parts that matter left room, and JUNTO only says
        # which one it would rather be near. On the back face it often
        # cannot be near at all, because the cell's shadow covers most of
        # that face and its owner sits inside it.
        return float("inf")
    if ref in DECOPLA and ref.startswith("C"):
        dono = DECOPLA[ref]
        if dono == MODULO_DE_RADIO:
            return 4.0
        return 6.0
    if ref == "C203":
        # The reservoir on the RAIL side of the module's pi filter. Its job
        # is to hold charge on 3V0, not to close a fast loop: the loop that
        # has to be short is C201 to the module's pin (0,5 mm, and it gets
        # the 4,0 above), and the ferrite is between the two. Holding a bulk
        # capacitor on the far side of a ferrite to 10 mm is a number with
        # nothing behind it, and on a 47 x 14 board it costs a real place.
        return 14.0
    if ref in DECOPLA or ref in JUNTO:
        # a pull-up, a configuration resistor or an ESD array: near, but
        # nothing in a datasheet holds them to a millimetre
        return 10.0
    return 12.0

# Parts whose position AND rotation the case decides, not the placer: x, y,
# angle. These are not the numbers of 04-pcb-e-caixa.md, and the difference is
# the point. That document's zone table was written before any footprint
# existed, and three of its rectangles do not hold the real part:
#
#   USB-C      the zone is 9 x 3 mm. A USB-C receptacle is about 9 x 10 mm:
#              the body goes INTO the board, it does not sit on its edge. The
#              three keys and the connector cannot share the bottom band, so
#              the keys moved up to y 79 and the connector kept the edge.
#   modulo     the zone is 10 x 16.2 mm, for the Fanstel part. The MinewSemi
#              ME54BS13 is 12 x 16.5, and its datasheet wants 4 mm clear
#              around the antenna side and that side facing off the board. It
#              lies down with the antenna to the right edge, above the keys.
#   GNSS       the zone starts at y 2, inside the antenna keep-out that runs
#              to y 8. 04 already counted that overlap as 90 mm2 and left it
#              open; here the receiver sits below the keep-out, at y 8.5.
# Every one of these is measured from an EDGE of the board, never from the
# absolute coordinate it used to carry: they were written for a 55 x 97
# outline and every one of them was wrong the moment the outline changed.
# W and H come from make_dxf, which derives them from the rules.
_W, _H = M.W, M.H

BORDA_FIXA: dict[str, tuple[float, float, int]] = {
    # The radio module lying along the board at the right end, its antenna
    # band on the +x edge: the footprint's antenna is at -Y, and 270 turns
    # it to +X (dry_run_pcb.rect_antena reads the angle the same way). The
    # origin is the body centre, so x is W minus half the 17,0 courtyard.
    "U201": (_W - M._MOD_COMP / 2.0, _H / 2.0, 270),
    # The magnetic connector along the top edge, plungers up through the
    # pod's lid: 18,5 x 5,5 courtyard from y 0,55 to 6,05, centred between
    # the energy block and the module (make_dxf.XE and XM).
    "J101": (round((M.XE + M.XM) / 2.0 / PASSO) * PASSO, 3.3, 0),
    # The bridge's five solder pads on the bottom edge, under the
    # converter: the wires come up from the crank arm through the pod's
    # floor and reach the board at its edge.
    "J301": (round((M.XE + 4.0 + M.XM - 6.0) / 2.0 / PASSO) * PASSO, _H - 1.3, 0),
    # The cell's two solder holes at the left end: the wires come up from
    # the cell through the recess in the pod's floor, so they enter from
    # below and the holes only have to be clear of the cell's own shadow.
    "J102": (4.0, 2.0, 0),
}



# Which chip each capacitor decouples, from 05-materiais.md. The netlist
# cannot say it: a decoupling capacitor sits between a rail and ground, and
# the rail touches everything. The bill of materials is where it is written -
# "C101 a C109: entradas e saidas do nPM1300", "C113, C114: entrada e saida do
# TPS7A02", "C115, C116: CSRC e CINT do AEM10900" - and without it the placer
# sends the capacitor to the centre of gravity of a rail, which is nowhere.
DECOPLA: dict[str, str] = {
    "C101": "U101", "C102": "U101", "C103": "U101", "C104": "U101", "C106": "U101",
    "C105": "U102",
    "C201": "U201", "C202": "U201", "FB201": "U201",
    # C203 answers to the FERRITE and not to the module: the pi filter of
    # the module's datasheet is C202 - FB201 - C201, and C203 is the
    # capacitor on the RAIL side of the ferrite. Pointing it at the module
    # asked the placer to put a bulk capacitor inside a ring it does not
    # belong in, and on the smaller module that ring ran out (measured
    # 2026-09-28: C203 ended 9,5 mm away against a limit of 4,0).
    "C301": "U301", "C302": "U301", "C303": "U301", "C304": "U301",
    "C305": "U301", "C306": "U301", "R301": "U301", "R302": "U301",
    "C307": "U302", "C308": "U302",
    "C401": "U401", "C402": "U401", "C403": "U402",
}
# Two terminal parts that sit NEAR their chip but do not hug a pin: a
# resistor to a static pin (ICHG, NTC, SHPHLD) or a pull-up has no loop to
# keep short, and on the ring round the nPM1100 they took the room the
# decoupling and the escapes of the power pins needed (the router died
# 0,2 mm out of VSYS, VBUS and VBAT on 2026-09-27). They are placed from
# their chip's position by the spiral, after the decoupling.
NAO_ENCOSTA = {"R101", "R102", "R103", "R104", "R105", "R106", "R204", "R205"}

# A part is allowed inside the keep-out that exists because of it: the
# radio module sits over its own antenna zone, which forbids copper, not it.
#
# The same goes for the GNSS chip antenna and its two tuning capacitors. The
# Unictron layout guide is explicit that the 50 ohm trace AND the matching
# components live INSIDE the cut-out - the cut-out forbids ground plane, not
# the antenna's own network. Putting the tuning capacitors outside it would
# put ground between the antenna and its own tuning, which is the one place
# copper must not be.
DONO_DO_KEEPOUT: dict[str, str] = {
    "U201": "KEEPOUT_ANTENA_MODULO",
}

# What the ME54BS13 datasheet actually asks around its antenna, read in
# V1.0.0 and not in a summary of it:
#
#   7.3  no copper pour, no component and no fully enclosed metal housing
#        over the antenna area, and the RF side never faces inward;
#   7.4  "no signal traces, metal objects, or other interference sources
#        should exist within 3-5 mm around the antenna area", the module at
#        the edge or corner, and the PCB beneath the antenna hollowed out.
#
# There is NO "20 mm from a switching converter" rule; this file carried one
# until 2026-09-24, and while it kept the power supply 20 mm away it let ten
# other parts sit inside 5 mm of the antenna - one of them at 0.8 mm.
# It applies to EVERY part, not to a chosen list.
DIST_ANTENA = 5.0

# ME54BS13 V1.0.0, 7.2, "Interference Isolation Rule": 20 mm between the
# module and a DC-DC switching supply, a power inductor or a transformer.
#
# This constraint was in this file, was taken out on 2026-09-24 on the wrong
# conclusion that the rule did not exist, and is back. It does exist - the
# section is 7.2, not the 7.3 that was looked in - and taking it out let a
# power inductor sit 6.8 mm from the module.
#
# It is measured to the MODULE's courtyard, which is what the datasheet says,
# not to the antenna band: the sentence is "the module must maintain a
# minimum safe distance from strong interference sources".
LONGE_DO_MODULO = 20.0
CHAVEIA = {"L101", "U101"}
MODULO_DE_RADIO = "U201"
ANTENA_DO_RADIO = "KEEPOUT_ANTENA_MODULO"
# The module's OWN decoupling is exempt, and it has to be. Section 7.2 puts
# the capacitor 0.5 mm from the power pin, and the module's power pads sit
# 2.1 mm from its own antenna band - so no point exists that satisfies both
# 0.5 mm from the pin and 5 mm from the antenna. The 3-5 mm of 7.4 is about
# foreign interference sources, not about the module's own support parts,
# which every figure in 7.5 draws right against it.
DO_MODULO = {"C201", "C202"}

# Rotations that are not about the case but about the circuit.

ROTACAO: dict[str, int] = {
    "U101": 0,
    "U301": 0,
}


def uid(*parts: object) -> str:
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-4{h[13:16]}-8{h[17:20]}-{h[20:32]}"


def P_(x: float, yd: float) -> tuple[float, float]:
    return (x + ORIGEM[0], yd + ORIGEM[1])


def redes() -> tuple[dict[str, int], dict[tuple[str, str], str]]:
    """Merge the nets that share a pin, number them, and index by pad."""
    bruto: dict[str, set] = {}
    for nome, pinos in N.NETS.items():
        membros = set()
        for ref, pin_name in pinos:
            part = P.PARTS[ref]
            numero = next(q.number for q in part.pins
                          if q.name == pin_name or q.number == pin_name)
            membros.add((ref, numero))
        bruto[nome] = membros
    pai = {n: n for n in bruto}

    def raiz(n):
        while pai[n] != n:
            pai[n] = pai[pai[n]]
            n = pai[n]
        return n

    de_pino: dict[tuple, str] = {}
    for nome, membros in bruto.items():
        for m in membros:
            if m in de_pino:
                a, b = raiz(de_pino[m]), raiz(nome)
                if a != b:
                    pai[b] = a
            else:
                de_pino[m] = nome
    juntos: dict[str, set] = {}
    nomes_do_grupo: dict[str, list[str]] = {}
    for nome, membros in bruto.items():
        juntos.setdefault(raiz(nome), set()).update(membros)
        nomes_do_grupo.setdefault(raiz(nome), []).append(nome)

    # A merged group keeps the best of its names, not whichever happened to
    # claim a pin first. Without this the ground comes out called FPC_VSS,
    # because the panel's ground is one of the names that merged into it.
    import sheets as S
    melhor: dict[str, str] = {}
    for r, membros_nomes in nomes_do_grupo.items():
        melhor[r] = sorted(
            membros_nomes,
            key=lambda n: (n not in S.TRILHOS, -len(bruto[n]), n))[0]

    numeros = {"": 0}
    por_pad: dict[tuple[str, str], str] = {}
    for i, (r, membros) in enumerate(sorted(juntos.items(),
                                            key=lambda kv: melhor[kv[0]]), start=1):
        numeros[melhor[r]] = i
        for m in membros:
            por_pad[m] = melhor[r]
    return numeros, por_pad


# Os CIs de passo fino que ja foram postos na FRENTE, e a caixa de cada um.
# `colocar()` preenche isto enquanto coloca; `livre()` le. Existe porque
# `livre()` e funcao de modulo e a colocacao e local de `colocar()`.
CIS_DA_FRENTE: dict[str, tuple[float, float, float, float]] = {}
# O que conta como passo fino: encapsulamento sem perna visivel, em que o
# vao entre duas ilhas nao cabe uma via.
_FINO = ("QFN", "DFN", "SON", "LGA", "BGA", "WLCSP")


def e_fino(ref: str) -> bool:
    nome = FPS.FP[ref][0] if ref in FPS.FP else ""
    return any(k in nome.upper() for k in _FINO)


def _registra_ci(ref: str, x: float, y: float, ang: int, atras: bool) -> None:
    """Guarda a caixa de um CI de passo fino posto na frente."""
    if atras or not e_fino(ref):
        return
    b = caixa(ref, ang)
    CIS_DA_FRENTE[ref] = (x + b[0], y + b[1], x + b[2], y + b[3])


# O anel livre em volta de um CI de passo fino, em mm. Nao e folga estetica:
# e a largura de UMA VIA com a folga dela (0,40/2 + 0,0889 + margem). Um
# QFN24 de 4 x 4 tem os 24 pinos no perimetro e todos saem radialmente; se o
# vizinho encosta no courtyard, nao ha onde a via de fuga pousar. Medido em
# 2026-09-30 com o Freerouting: das ligacoes que sobraram abertas, o `U101`
# aparecia em 14 das 40 pontas - mais que todas as outras pecas somadas.
# E ele vale so' para quem tem pino demais para o tamanho que tem. Medido em
# 2026-09-30: com o anel nos sete CIs finos a placa fechou uma ligacao a mais
# (16 contra 17) e a `AL1` foi de 11 para 12 capacitores fora do limite, com
# o `C105` a 15,6 mm do `U102` - a essa distancia ele nao desacopla nada. O
# `U101` sozinho respondia por 14 das 40 pontas em aberto; os outros seis
# nao precisam de anel, so' de nao ter peca por cima.
# ZERO, medido. O anel de 0,45 em volta dos sete CIs finos fechava uma
# ligacao a mais (16 contra 17) e levava a `AL1` de 11 para 12 capacitores
# fora do limite, com o `C105` a 15,6 mm do `U102` - a essa distancia ele
# nao desacopla nada. So' no `U101`, deu 18, pior que sem anel nenhum. As
# tres medidas ficam dentro da variacao do proprio roteador, entao o que
# decide e o que nao varia: a distancia do desacoplamento. Fica so' a regra
# de nao ter peca POR CIMA do CI, que essa tem mecanismo (a via de fuga nao
# cabe sob um passo de 0,5 mm) e nao custa nada.
ANEL_DO_CI = 0.0
COM_ANEL: set[str] = set()


def sob_ci_fino(x0: float, y0: float, x1: float, y1: float) -> bool:
    """A caixa invade o contorno - ou o anel de fuga - de um CI fino?"""
    for r, (kx0, ky0, kx1, ky1) in CIS_DA_FRENTE.items():
        folga = ANEL_DO_CI if r in COM_ANEL else 0.0
        if x1 + folga > kx0 and kx1 + folga > x0 and                 y1 + folga > ky0 and ky1 + folga > y0:
            return True
    return False


def livre(x: float, y: float, bx: tuple[float, float, float, float],
          postos: list[tuple[float, float, float, float]],
          ref: str = "", borda: float | None = None) -> bool:
    """See por(): `postos` is already the list of the face being placed on."""
    """Is the courtyard, placed at (x, y), inside the board and free?

    The box comes relative to the footprint origin, not centred on it: a
    connector's courtyard sits to one side of its pads, and treating it as
    centred is what pushed every decoupling capacitor two millimetres further
    out than it had to be.
    """
    eps = 1e-6
    b = BORDA if borda is None else borda
    x0, y0, x1, y1 = x + bx[0], y + bx[1], x + bx[2], y + bx[3]
    if x0 < b - eps or y0 < b - eps or             x1 > M.W - b + eps or y1 > M.H - b + eps:
        return False
    r = M.RADIUS_DRAWING
    for cx, cy in ((r, r), (M.W - r, r), (r, M.H - r), (M.W - r, M.H - r)):
        qx = min(max(x0, cx - r if cx < M.W / 2 else -1e9),
                 cx + r if cx > M.W / 2 else 1e9)
        del qx
    if ref in CHAVEIA:
        mx, my, mang = BORDA_FIXA[MODULO_DE_RADIO]
        m = caixa(MODULO_DE_RADIO, mang)
        dx = max(mx + m[0] - x1, x0 - (mx + m[2]), 0.0)
        dy = max(my + m[1] - y1, y0 - (my + m[3]), 0.0)
        if math.hypot(dx, dy) < LONGE_DO_MODULO:
            return False
    # NADA DO VERSO DEBAIXO DE UM CI DE PASSO FINO DA FRENTE.
    #
    # Medido em 2026-09-30, com o Freerouting: das 26 ligacoes que sobraram
    # abertas, quase todas tocavam o `U101` - os pinos 1, 2, 3, 6, 9, 14, 17,
    # 21 e 22 do nPM1100. O motivo estava debaixo dele: o `R101` a 0,0 mm do
    # centro, e `R102`, `C103`, `C106`, `C102` e `R106` a menos de 3,5 mm,
    # todos no verso, sob o corpo do QFN. O passe de HPWL os levou para la
    # porque diretamente sob o pino o fio tem comprimento zero.
    #
    # So que fio zero nao existe: a ligacao entre as duas faces e uma VIA, e
    # sob um QFN de 0,5 mm de passo nao ha onde por uma - o vao entre duas
    # ilhas e 0,25 mm e uma via de 0,40 com folga pede mais que isso. O
    # capacitor do verso tem de ficar logo FORA do contorno do CI, com a via
    # ao lado da ilha dele; e mais longe em desenho e mais perto em
    # eletricidade, que e o que conta.
    if ref not in CIS_DA_FRENTE and sob_ci_fino(x0, y0, x1, y1):
        return False
    # The cell lies against the back face: a part with a body may stand on
    # the back anywhere the cell does not reach, and nowhere it does.
    if ref in ATRAS:
        for nome, (kx0, ky0, kx1, ky1), _c, _s in M.ZONES:
            if nome != M.SOMBRA_CELULA:
                continue
            if x1 > kx0 and kx1 > x0 and y1 > ky0 and ky1 > y0:
                return False
    for nome, (kx0, ky0, kx1, ky1), _c, _s in M.ZONES:
        if nome == ANTENA_DO_RADIO and DONO_DO_KEEPOUT.get(ref) != nome                 and ref not in DO_MODULO:
            dx = max(kx0 - x1, x0 - kx1, 0.0)
            dy = max(ky0 - y1, y0 - ky1, 0.0)
            if math.hypot(dx, dy) < DIST_ANTENA:
                return False
        if nome not in KEEPOUTS or DONO_DO_KEEPOUT.get(ref) == nome:
            continue
        if x1 > kx0 and kx1 > x0 and y1 > ky0 and ky1 > y0:
            return False
    for px0, py0, px1, py1 in postos:
        if x1 + FOLGA > px0 and px1 + FOLGA > x0 and \
                y1 + FOLGA > py0 and py1 + FOLGA > y0:
            return False
    return True


def espiral(cx: float, cy: float, bx: tuple[float, float, float, float],
            postos: list, raio_max: float = 60.0, ref: str = ""):
    """The nearest free slot to (cx, cy), searched outwards."""
    if livre(cx, cy, bx, postos, ref):
        return (cx, cy)
    passo = PASSO
    r = passo
    while r <= raio_max:
        n = max(8, int(2 * math.pi * r / passo))
        for i in range(n):
            a = 2 * math.pi * i / n
            x = round((cx + r * math.cos(a)) / PASSO) * PASSO
            y = round((cy + r * math.sin(a)) / PASSO) * PASSO
            if livre(x, y, bx, postos, ref):
                return (x, y)
        r += passo
    return None


def caixa(ref: str, ang: int) -> tuple[float, float, float, float]:
    """The real courtyard, turned: x0, y0, x1, y1 around the origin.

    Module level on purpose. While this lived inside colocar() the checker
    had a copy of its own - the symmetric box, twice the furthest edge, with
    a 1.8 mm floor - and the two disagreed: the checker reported 54
    overlapping courtyards on a board where KiCad reported one. A rule
    measured by two definitions is not a rule.
    """
    fp_load.carregar(FPS.FP[ref][0])
    x0, y0, x1, y1 = fp_load.CAIXA[FPS.FP[ref][0]]
    for _ in range((ang // 90) % 4):
        x0, y0, x1, y1 = y0, -x1, y1, -x0
    # a minimum, because a test point's courtyard is barely bigger than
    # its own pad and two of them then land on top of each other
    if x1 - x0 < 1.2:
        m = (x0 + x1) / 2
        x0, x1 = m - 0.6, m + 0.6
    if y1 - y0 < 1.2:
        m = (y0 + y1) / 2
        y0, y1 = m - 0.6, m + 0.6
    return (x0, y0, x1, y1)


def tam(ref: str, ang: int) -> tuple[float, float]:
    x0, y0, x1, y1 = caixa(ref, ang)
    return (x1 - x0, y1 - y0)


# Silkscreen text. 0.8 mm tall with a 0.15 mm stroke is not a preference:
# it is the floor almost every fab publishes for legible silkscreen, and what
# this file wrote before - 0.7 with a 0.1 stroke - is below it, so it would
# not print reliably whatever the layout did. Raising it makes the collision
# problem worse, which is why the labels are now PLACED instead of all being
# dropped 1.8 mm above their part: at a fixed offset, 37 pairs of reference
# designators sat on top of each other, and a designator you cannot read
# identifies nothing.
# 0.6 mm with a 0.12 mm stroke. 0.8/0.15 is the number a fab publishes as
# its conservative floor, and it is the right floor for a board with room;
# on this one it is a designator taller than half the parts it names, and it
# read as clutter rather than as labelling. 0.6/0.12 is what dense boards
# use and what most houses print without comment - but it IS below the
# conservative figure, and no fab has been consulted for this board at all
# (that is already an open item), so it is one of the things to confirm with
# the one that is chosen.
TEXTO_ALT = 0.6
TEXTO_TRACO = 0.12
# Width of a character as a fraction of the text height. 1.06, measured in
# KiCad's own SVG export and not guessed: "C101" at 0.8 mm comes out with
# textLength 3.38, which is 0.845 per character. At the 0.75 this carried,
# every label was modelled 30% narrower than it prints, this file reported
# zero collisions and the exported silkscreen had 35 pairs on top of each
# other.
TEXTO_LARG = 1.06
TEXTO_FOLGA = 0.12         # between two labels


def _caixa_texto(ref: str, x: float, y: float, ang: int = 0) -> tuple:
    """The rectangle a label occupies, turned if the label is turned."""
    w = len(ref) * TEXTO_ALT * TEXTO_LARG + TEXTO_FOLGA
    h = TEXTO_ALT + TEXTO_FOLGA
    if ang % 180:
        w, h = h, w
    return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)


def _cruza(a: tuple, b: tuple) -> bool:
    return a[2] > b[0] and b[2] > a[0] and a[3] > b[1] and b[3] > a[1]


def rotulos(lugar: dict) -> dict[str, tuple[float, float, int]]:
    """Where each reference designator goes, and at what angle.

    The angle is not free: it follows the PART. A component turned 90 degrees
    gets a label turned 90 degrees, so the text reads along the thing it
    names, and a board where every designator is horizontal over a column of
    vertical resistors reads as noise - which is what this produced, 123
    labels and not one of them turned, over 44 parts that are.

    Two rules, in order. A label may NEVER sit on another label - that is
    what makes the board unreadable. A label SHOULD not sit on another
    part's courtyard, but on a board at 48% occupancy that is not always
    possible, and a designator printed over a chip's body is still legible
    while two designators printed over each other are not.

    Candidates are tried from the part's own courtyard outwards, nearest
    first, so a label stays next to the thing it names.
    """
    # Um rotulo por FACE: F.SilkS e B.SilkS sao duas serigrafias, e um
    # designador da frente sobre um de tras nao esconde nada. Tratar os dois
    # como uma lista so' gastava candidatos a toa e empurrava rotulos para
    # longe da peca que eles nomeiam.
    postas_face: dict[bool, list[tuple]] = {False: [], True: []}
    corpos = []
    ordem_corpos = []
    for ref, (x, y, ang, _a) in lugar.items():
        bx = caixa(ref, ang)
        corpos.append((x + bx[0], y + bx[1], x + bx[2], y + bx[3]))
        ordem_corpos.append(ref)
    saida: dict[str, tuple[float, float, int]] = {}
    # biggest parts first: they have the most room around them and the most
    # to lose from a label landing in the middle of a fine pitch package
    ordem = sorted(lugar, key=lambda r: -(
        (caixa(r, lugar[r][2])[2] - caixa(r, lugar[r][2])[0]) *
        (caixa(r, lugar[r][2])[3] - caixa(r, lugar[r][2])[1])))
    for ref in ordem:
        x, y, ang, _atras = lugar[ref]
        postas = postas_face[bool(_atras)]
        bx = caixa(ref, ang)
        rot = 90 if ang % 180 else 0
        meia_w = len(ref) * TEXTO_ALT * TEXTO_LARG / 2
        meia_h = TEXTO_ALT / 2
        if rot:
            meia_w, meia_h = meia_h, meia_w
        melhor = None
        # PROXIMIDADE primeiro, e so depois qualquer outra coisa.
        #
        # A versao anterior preferia um lugar livre do contorno de QUALQUER
        # peca a um lugar perto da propria. Numa placa a 48% de ocupacao isso
        # empurra o rotulo para milimetros de distancia, e o resultado e uma
        # nuvem de designadores em que nenhum aponta para nada - que e
        # exatamente o que se via no desenho de montagem. Um rotulo sobre o
        # contorno da PROPRIA peca continua dizendo qual peca e; um rotulo a
        # 4 mm dela nao diz.
        #
        # Entao: candidatos do mais perto para o mais longe, e o primeiro que
        # nao cai sobre OUTRO rotulo ganha. Cair sobre contorno so desempata
        # entre candidatos da mesma distancia.
        # ate 4 mm, e nao ate 2,3: tres rotulos caiam no ultimo recurso
        # de ficar no centro da propria peca, e ai se sobrepunham
        # (C307/C308, TP103/TP201, TP102/TP202, medido em 2026-09-29)
        for passo in (0.0, 0.15, 0.25, 0.35, 0.5, 0.65, 0.8, 1.0,
                      1.2, 1.45, 1.7, 2.0, 2.3, 3.0, 4.0):
            anel = []
            for dx, dy in ((0.0, bx[1] - meia_h - 0.2 - passo),
                           (0.0, bx[3] + meia_h + 0.2 + passo),
                           (bx[2] + meia_w + 0.25 + passo, 0.0),
                           (bx[0] - meia_w - 0.25 - passo, 0.0),
                           (bx[2] + meia_w + 0.25 + passo,
                            bx[1] - meia_h - 0.2 - passo),
                           (bx[0] - meia_w - 0.25 - passo,
                            bx[1] - meia_h - 0.2 - passo),
                           (bx[2] + meia_w + 0.25 + passo,
                            bx[3] + meia_h + 0.2 + passo),
                           (bx[0] - meia_w - 0.25 - passo,
                            bx[3] + meia_h + 0.2 + passo)):
                cx_, cy_ = x + dx, y + dy
                t = _caixa_texto(ref, cx_, cy_, rot)
                # the whole box of the text stays 0.3 mm inside the outline,
                # not just its centre: a label turned 90 degrees near the
                # bottom edge kept its centre inside and its far half out,
                # and the DRC reported the silkscreen cut by the edge
                if not (t[0] > 0.3 and t[2] < M.W - 0.3
                        and t[1] > 0.3 and t[3] < M.H - 0.3):
                    continue
                if any(_cruza(t, q) for q in postas):
                    continue
                # quantos contornos ALHEIOS ele pisa: so para desempatar
                alheios = sum(1 for r2, c in zip(ordem_corpos, corpos)
                              if r2 != ref and _cruza(t, c))
                anel.append((alheios, (dx, dy), t))
            if anel:
                anel.sort(key=lambda q: q[0])
                melhor = (anel[0][1], anel[0][2], anel[0][0] == 0)
                break
        if melhor is None:
            # nothing anywhere: leave it on the part and say so by putting it
            # dead centre, which is visibly deliberate rather than a near miss
            saida[ref] = (0.0, 0.0, rot)
            postas.append(_caixa_texto(ref, x, y, rot))
            continue
        saida[ref] = (melhor[0][0], melhor[0][1], rot)
        postas.append(melhor[1])
    return saida


def colocar() -> tuple[dict[str, tuple[float, float, int, bool]], list[str]]:
    """Place every part: x, y, rotation and which face.

    The rules are the ones a person uses, in this order:

      1. a connector faces the edge it comes out of, and its rotation is not
         negotiable: the USB-C opening has to point out of the case, the
         display's flat cable has to leave to the left, the module's antenna
         has to look off the board;
      2. a part with a zone in 04-pcb-e-caixa.md goes to the middle of it;
      3. everything else goes to the centre of gravity of the parts it
         connects to, so a decoupling capacitor lands beside the pin it
         decouples and a series resistor lands between the two ends it joins;
      4. a two terminal part is turned to lie along the line between the two
         parts it connects, which is what makes the track short and straight
         instead of an L around the part.
    """
    zonas = {n: r for n, r, _c, _s in M.ZONES}
    tam_bruto: dict[str, tuple[float, float]] = {}
    for ref, (nome, _o, _n) in FPS.FP.items():
        tam_bruto[ref] = fp_load.carregar(nome)[1]

    lugar: dict[str, tuple[float, float, int, bool]] = {}
    # The hole is KiCad's MountingHole_2.2mm_M2, and THAT footprint's
    # courtyard is a circle of 2,45 mm of radius (fp_circle end 2.45 on
    # F.CrtYd), for the head or washer of the screw. Reserving less than the
    # courtyard is how J201 landed 2,0 mm from the hole and the DRC called it
    # an overlap: the placer and the DRC have to agree on the same circle.
    raio = RAIO_COURTYARD_FURO + FOLGA
    # One list per face, not one for the board. A part on the back does not
    # take room from a part on the front, and pretending it does is how a
    # small board runs out of space that it has: the battery connector, the
    # barometer and the thermistor were blocking the front face where they
    # are not. What IS in both lists is what goes through the board - the
    # mounting hole and its keep-out - because that really does take the room
    # on both faces.
    # ...unless the hole is not for a screw HEAD. This board's one hole
    # passes the NECK of a post that rises from the pod's floor; the screw
    # and its head are up on the lid and never touch the board. Reserving
    # 2,45 mm for a head that is not there took 5 mm of the middle of a 14 mm
    # board and left the magnetic connector without a place (2026-09-28).
    raio_furo = getattr(M, "FURO_RESERVA_R", None)
    if raio_furo is None:
        raio_furo = raio
    furos = [(fx - raio_furo, fy - raio_furo, fx + raio_furo, fy + raio_furo)
             for fx, fy in M.FUROS_DOC]
    # Corredores sem peca, so na frente: faixas que o roteamento precisa e
    # que o colocador enchia de peca miuda. O primeiro fica em cima dos
    # pinos D+ e D- do modulo, em (20,55; 71,5) e (21,65; 71,5) com o
    # modulo onde BORDA_FIXA o poe: o par do USB so entra neles por cima,
    # entre vizinhos a 1,1 mm, e um resistor a 1,5 mm acima do pino fecha
    # a entrada - o R109 fechou, e quando ele saiu o DISP_PWR_EN entrou.
    # ate 70,7 e nao ate os pinos: a caixa de colocacao do modulo comeca
    # em 70,75, e um corredor que entra nela derruba a posicao fixa do modulo.
    # De 68,3 e nao de 68,2: o contorno da tecla da direita acaba em 67,75 e
    # livre() exige FOLGA entre contornos; a 68,2 a tecla nao cabia.
    # The top end follows the module since the board grew to 95
    # (2026-09-26): the module's placement box starts at H - 19,25, and the
    # corridor ends 0,05 above it, as before; the bottom end stays at 68,3,
    # FOLGA under the keys' courtyards, which did not move in y.
    # The second corridor is the USB pair's own path from the ESD diode D102
    # (courtyard to y 79,85, x 2,5-5,5) to the receptacle J101 (from y 85,44,
    # D+ and D- pads at x 6,25 and 6,75): ligar_usb() draws the two diagonals
    # there from the real positions, and the placer knew nothing about them.
    # When the bottom M2 hole moved to (14,4; 91,7) on 2026-09-26 it pushed
    # the test point TP101 to (3; 84), straight onto the pair: a short to a
    # ground stub, a clearance of 0,071 mm and a mask bridge, all three in
    # the DRC. Both ends are fixed parts, so the strip stops FOLGA short of
    # each courtyard; x 3 to 8,5 keeps the cell connector (x >= 10,22) out
    # of it.
    corredores: list[tuple[float, float, float, float]] = []
    postos_face: dict[bool, list[tuple[float, float, float, float]]] = {
        False: list(furos) + corredores, True: list(furos)}
    falhas: list[str] = []

    def por(ref: str, cx: float, cy: float, ang: int = 0,
            preso: bool = False) -> None:
        bx = caixa(ref, ang)
        atras = ref in ATRAS
        # a part whose pads pierce the board has to clear BOTH faces, and it
        # has to do so when IT is placed, not only afterwards: the Tag-Connect
        # is placed late, by connectivity, and landed on top of the buzzer -
        # which had gone to the back precisely because the front had no room.
        postos = postos_face[atras]
        if ref in PASSANTE:
            postos = postos + postos_face[not atras]
        if preso:
            # a fixed position has to be legal on its own: overlapping here
            # silently is how two connectors end up on top of each other.
            # A connector that comes out of the case may touch the edge - that
            # is the point of it - so the edge margin does not apply to it.
            p = (cx, cy) if livre(cx, cy, bx, postos, ref, borda=0.0) else None
            if p is None:
                falhas.append(f"{ref}: a posicao fixa ({cx:.1f}; {cy:.1f}) nao "
                              f"esta livre para o contorno {bx}")
        else:
            p = espiral(cx, cy, bx, postos, ref=ref)
        if p is None:
            falhas.append(f"{ref}: nao coube perto de ({cx:.1f}; {cy:.1f})")
            return
        # How far the spiral was allowed to carry the part from where it was
        # asked to go. Without this the search just widens until something is
        # free, and a part with nowhere to stand lands anywhere on the board
        # without a word: on 2026-09-27 the module's own decoupling ended
        # 11 to 14 mm away, its bus pull-ups 29 mm, and the load switch's
        # capacitors 17 and 19 mm. Ten capacitors broke rule AL1 and nobody
        # was told. It is the same failure the project already knows in
        # another form - a check that cannot measure has to say so - so the
        # placer now says which part did not fit and how far it had to go.
        d = math.hypot(p[0] - cx, p[1] - cy)
        if d > LIMITE_DESLOCA(ref) + 1e-9:
            dono = DECOPLA.get(ref) or JUNTO.get(ref) or "a sua zona"
            falhas.append(
                f"{ref}: nao coube junto de {dono}; o colocador teve de "
                f"leva-la {d:.1f} mm de ({cx:.1f}; {cy:.1f}), e o limite e "
                f"{LIMITE_DESLOCA(ref):.1f} mm")
        lugar[ref] = (p[0], p[1], ang, ref in ATRAS)
        _registra_ci(ref, p[0], p[1], ang, ref in ATRAS)
        caixa_posta = (p[0] + bx[0], p[1] + bx[1], p[0] + bx[2], p[1] + bx[3])
        postos_face[atras].append(caixa_posta)
        if ref in PASSANTE:
            # its pads pierce the board, so it takes the room on both faces
            postos_face[not atras].append(caixa_posta)

    # ---- 1. the parts whose orientation the case decides ----
    for ref, (cx, cy, ang) in BORDA_FIXA.items():
        if ref in tam_bruto:
            por(ref, cx, cy, ang, preso=True)

    # ---- 2. the zones ----
    for ref, zona in ANCORAS.items():
        if ref in lugar:
            continue
        if ref not in tam_bruto:
            falhas.append(f"{ref}: sem footprint, nao colocado")
            continue
        x0, y0, x1, y1 = zonas[zona]
        ang = ROTACAO.get(ref, 0)
        por(ref, round((x0 + x1) / 2 / PASSO) * PASSO,
            round((y0 + y1) / 2 / PASSO) * PASSO, ang)

    # ---- 3. decoupling and inductors, hugging the pin they serve ----
    # The datasheets do not say "near": the ME54BS13 asks for 0.5 mm between a
    # capacitor's pad and the power pin, and both the nPM1300 and the AEM10900
    # ask for the inductor and the reactive parts "as close as possible" to
    # their pins. A capacitor 7 mm away is 15 nH of loop, which at 200 mA and a
    # 2 ns edge is 1.5 V of ringing on a 3.7 V rail - the capacitor stops being
    # a capacitor and becomes part of the problem.
    def pad_global(ref: str, numero: str) -> tuple[float, float] | None:
        if ref not in lugar:
            return None
        nome_fp = FPS.FP[ref][0]
        texto = fp_load.carregar(nome_fp)[0]
        arv = fp_load.parse(texto)
        for p in fp_load.kids(arv, "pad"):
            if p[1] != numero:
                continue
            a = fp_load.kid(p, "at")
            px, py = float(a[1]), float(a[2])
            x, y, ang, atras = lugar[ref]
            if atras:
                px = -px
            r = math.radians(ang)
            return (x + px * math.cos(r) + py * math.sin(r),
                    y - px * math.sin(r) + py * math.cos(r))
        return None

    def pads_locais(ref: str) -> list[tuple[float, float]]:
        """Every pad of a footprint, as an offset from the footprint origin."""
        arv = fp_load.parse(fp_load.carregar(FPS.FP[ref][0])[0])
        saida = []
        for p in fp_load.kids(arv, "pad"):
            a = fp_load.kid(p, "at")
            if a:
                saida.append((float(a[1]), float(a[2])))
        return saida

    def encostar(ref: str) -> bool:
        """Put a two terminal part right beside the pin it serves."""
        if ref in lugar or ref not in tam_bruto or len(P.PARTS[ref].pins) != 2:
            return False
        if ref in NAO_ENCOSTA:
            return False
        melhor = None
        # the bill of materials decides first; the netlist only breaks ties
        dono_bom = DECOPLA.get(ref)
        for _nome, pinos in N.NETS.items():
            refs = {r for r, _p in pinos}
            if ref not in refs:
                continue
            if dono_bom is None and len(refs) > 8:
                continue
            if dono_bom is not None and dono_bom not in refs:
                continue
            for outro, pino in pinos:
                if outro == ref or outro not in lugar:
                    continue
                if dono_bom is not None and outro != dono_bom:
                    continue
                if dono_bom is None and len(P.PARTS[outro].pins) < 4:
                    continue
                numero = next(q.number for q in P.PARTS[outro].pins
                              if q.name == pino or q.number == pino)
                p = pad_global(outro, numero)
                if p and (melhor is None or len(P.PARTS[outro].pins) > melhor[2]):
                    melhor = (p, outro, len(P.PARTS[outro].pins))
        if melhor is None:
            return False
        (px, py), dono, _n = melhor
        dx, dy, _a, _b = lugar[dono]
        v = math.hypot(px - dx, py - dy) or 1.0
        ux, uy = (px - dx) / v, (py - dy) / v

        # What every one of these datasheets constrains is the loop from the
        # supply PIN to the capacitor's own PAD, and that is not the distance
        # between the two parts' centres: a 0402 turned the wrong way puts its
        # near pad half a millimetre further out for nothing, and stepping a
        # fixed 0.6 mm out of the chip ignores which pad ends up facing the
        # pin. So each free candidate is scored pad to pad, both orientations
        # are tried, and the best wins. C111 sat 2.02 mm from U101's 3V3BL pin
        # against a 2.00 limit while a slot 1.90 mm away was free one grid
        # step up - the old rule could not see it, because by centre distance
        # that slot was the worse of the two.
        locais = pads_locais(ref)
        fora = max((math.hypot(a, b) for a, b in locais), default=0.0)
        espelha = -1.0 if ref in ATRAS else 1.0
        melhor_pos, melhor_d = None, float("inf")
        caixas = {a: caixa(ref, a) for a in (0, 90)}
        postos = postos_face[ref in ATRAS]
        if ref in PASSANTE:
            postos = postos + postos_face[ref not in ATRAS]
        raio = PASSO
        while raio <= 12.0:
            # a pad can only be `fora` closer than the part's own centre, so
            # once the ring itself is further than that, nothing on it or
            # beyond it can beat what is already in hand
            if raio - fora > melhor_d:
                break
            n = max(12, int(2 * math.pi * raio / PASSO))
            for i in range(n):
                a = 2 * math.pi * i / n
                cx = round((px + raio * math.cos(a)) / PASSO) * PASSO
                cy = round((py + raio * math.sin(a)) / PASSO) * PASSO
                for ang, bx in caixas.items():
                    if not livre(cx, cy, bx, postos, ref):
                        continue
                    r = math.radians(ang)
                    d = min(math.hypot(cx + espelha * ax * math.cos(r)
                                       + ay * math.sin(r) - px,
                                       cy - espelha * ax * math.sin(r)
                                       + ay * math.cos(r) - py)
                            for ax, ay in locais)
                    if d < melhor_d:
                        melhor_d, melhor_pos = d, (cx, cy, ang)
            raio += PASSO
        if melhor_pos is None:
            # nothing free within 12 mm: fall back to the old step-out so the
            # failure is reported by por() instead of vanishing
            ang = 0 if abs(ux) >= abs(uy) else 90
            w, h = tam(ref, ang)
            d = 0.6 + max(w, h) / 2
            por(ref, round((px + ux * d) / PASSO) * PASSO,
                round((py + uy * d) / PASSO) * PASSO, ang)
            return ref in lugar
        por(ref, melhor_pos[0], melhor_pos[1], melhor_pos[2])
        return ref in lugar

    def ordem_de_encostar(ref: str) -> tuple:
        """Who gets first pick of the ring around a chip.

        The smallest capacitor decouples the highest frequency, and it is the
        one whose loop to the pin has to be shortest: a 100 nF part 4 mm away
        is not decoupling anything above a few tens of megahertz, while a
        10 uF bulk capacitor 4 mm away is doing its job. So the ring is
        handed out by capacitance, smallest first, and only then to
        everything else. Alphabetical order - which is what this did before -
        put C101 ahead of C112 for no reason at all.
        """
        if ref not in DECOPLA or not ref.startswith("C"):
            return (2, 0.0, ref)
        # The radio module's own decoupling picks first, whatever its value:
        # its datasheet asks for 0.5 mm from the pin, which is the tightest
        # number on this board, and the module sits in a corner where the
        # room runs out. Sorting only by capacitance let a 4.7 uF that had to
        # be within 5 mm land 11.2 mm away, behind parts with no such rule.
        if DECOPLA[ref] == "U201":
            return (0, 0.0, ref)
        v = P.PARTS[ref].value.lower().replace(",", ".")
        mult = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6}
        f = 1.0
        for letra, m in mult.items():
            if letra + "f" in v:
                f = m
                break
        try:
            num = float(v.split()[0])
        except (ValueError, IndexError):
            num = 1.0
        return (1, num * f, ref)

    # first pass: the parts that hug an anchor, before the other
    # chips take the ring around it
    for ref in sorted(FPS.FP, key=ordem_de_encostar):
        encostar(ref)

    # A test point takes what is LEFT. It is a pad to touch a probe on, and
    # it must never push a decoupling capacitor off the ring it needs: when
    # the eleven points of the power sheet were placed with the rest of
    # JUNTO, AL1 went from zero capacitors out of limit to three, one of them
    # 4.0 mm from a pin that wants 2.
    for ref, dono in sorted(JUNTO.items(),
                            key=lambda kv: kv[0].startswith("TP")):
        if ref not in tam_bruto or dono not in lugar or ref in lugar:
            continue
        if ref.startswith("TP"):
            continue                     # depois do desacoplamento
        dx, dy = lugar[dono][0], lugar[dono][1]
        por(ref, dx, dy, ROTACAO.get(ref, 0))

    # second pass: now the chips that follow an anchor are placed too
    for ref in sorted(FPS.FP, key=ordem_de_encostar):
        encostar(ref)

    # and only now the test points, on whatever the decoupling left
    for ref, dono in JUNTO.items():
        if not ref.startswith("TP") or ref not in tam_bruto or ref in lugar:
            continue
        if dono not in lugar:
            continue
        dx, dy = lugar[dono][0], lugar[dono][1]
        por(ref, dx, dy, ROTACAO.get(ref, 0))
        if ref in lugar:
            continue
        # Um ponto de teste que nao coube na face dele tenta a OUTRA, em vez
        # de sumir da placa. Ele e um pad para encostar a ponta de prova: nao
        # tem corpo, nao tem altura e nao tem lado preferido - o lado so
        # existe para a face de tras ficar plana sob a celula, e um pad e
        # plano nas duas. Medido em 2026-09-28: `TP104` e `TP301` ficaram de
        # fora quando o desacoplamento do modulo passou a ser colocado de
        # verdade, e o `check_pcb` os contou como ligacao sem pad.
        era_atras = ref in ATRAS
        if era_atras:
            ATRAS.discard(ref)
        else:
            ATRAS.add(ref)
        por(ref, dx, dy, ROTACAO.get(ref, 0))
        if ref in lugar:
            falhas.append(f"{ref}: nao coube na face de "
                          f"{'tras' if era_atras else 'frente'}, foi para a "
                          "outra")
        elif era_atras:
            ATRAS.add(ref)
        else:
            ATRAS.discard(ref)

    # ---- 4. the rest, by connectivity, turned along it ----
    ligados: dict[str, set[str]] = {}
    for _nome, pinos in N.NETS.items():
        refs = {r for r, _p in pinos}
        if len(refs) > 8:          # a rail joins everything: it says nothing
            continue
        for a in refs:
            ligados.setdefault(a, set()).update(refs - {a})

    # which parts each terminal of a two pin part talks to
    por_terminal: dict[str, dict[str, set[str]]] = {}
    for _nome, pinos in N.NETS.items():
        refs = {r for r, _p in pinos}
        if len(refs) > 8:
            continue
        for ref, pino in pinos:
            if len(P.PARTS[ref].pins) != 2:
                continue
            por_terminal.setdefault(ref, {}).setdefault(pino, set()).update(
                refs - {ref})

    def angulo(ref: str) -> int:
        """Lay a two terminal part along the line between its two ends."""
        if ref in ROTACAO:
            return ROTACAO[ref]
        lados = por_terminal.get(ref)
        if not lados or len(lados) < 2:
            return 0
        centros = []
        for _pino, outros in sorted(lados.items()):
            pts = [lugar[o] for o in outros if o in lugar]
            if not pts:
                return 0
            centros.append((sum(p[0] for p in pts) / len(pts),
                            sum(p[1] for p in pts) / len(pts)))
        dx = centros[1][0] - centros[0][0]
        dy = centros[1][1] - centros[0][1]
        return 0 if abs(dx) >= abs(dy) else 90

    resto = [r for r in FPS.FP if r not in lugar]
    # A part the spiral cannot place stays out of `lugar`, and until
    # 2026-09-26 it also stayed in `resto` with the same score: the same wave
    # came round again, ran the whole spiral again, and the placer never
    # ended (a stack dump every two minutes showed it in espiral(), always
    # from this loop). Whoever fails is given up on here and reported by
    # por() in `falhas`; the run ends and says which part did not fit.
    desistidos: set[str] = set()
    while resto:
        pontuacao = {r: len(ligados.get(r, set()) & set(lugar)) for r in resto}
        melhor = max(pontuacao.values())
        if melhor == 0:
            for ref in sorted(resto):
                por(ref, M.W / 2, M.H / 2, ROTACAO.get(ref, 0))
            break
        onda = [r for r in resto if pontuacao[r] == melhor]
        for ref in sorted(onda):
            vizinhos = [lugar[v] for v in ligados.get(ref, ()) if v in lugar]
            cx = sum(v[0] for v in vizinhos) / len(vizinhos)
            cy = sum(v[1] for v in vizinhos) / len(vizinhos)
            por(ref, round(cx / PASSO) * PASSO, round(cy / PASSO) * PASSO,
                angulo(ref))
            if ref not in lugar:
                desistidos.add(ref)
        resto = [r for r in resto if r not in lugar and r not in desistidos]

    # ---- 5. melhoria: encurtar o que o roteador vai ter de ligar ----
    # O custo e o HPWL: por rede, a meia-perimetro da caixa que contem as
    # ilhas dela. E o limite inferior do comprimento de qualquer arvore que
    # as ligue, e cai quando as pecas de uma rede se aproximam.
    redes_de: dict = {}
    for nome_n, pinos in N.NETS.items():
        refs = {r for r, _q in pinos}
        if len(refs) > 8 or len(refs) < 2:
            continue          # um trilho liga tudo: nao diz nada
        for r in refs:
            redes_de.setdefault(r, set()).add(nome_n)

    def _cx_cy(ref: str):
        return (lugar[ref][0], lugar[ref][1]) if ref in lugar else None

    def hpwl(nome_n: str) -> float:
        pts = [_cx_cy(r) for r, _q in N.NETS[nome_n]]
        pts = [q for q in pts if q]
        if len(pts) < 2:
            return 0.0
        xs = [q[0] for q in pts]
        ys = [q[1] for q in pts]
        return (max(xs) - min(xs)) + (max(ys) - min(ys))

    def custo(refs) -> float:
        vistas = set()
        for r in refs:
            vistas |= redes_de.get(r, set())
        return sum(hpwl(n_) for n_ in vistas)

    # quem pode andar: nem ancora, nem posicao fixa, nem furo
    presas = set(BORDA_FIXA) | set(ANCORAS) | {"J301"}
    # O desacoplamento anda junto com o resto. MEDIDO em 2026-09-29, porque
    # a escolha custa alguma coisa dos dois lados: solto, o HPWL encurta
    # 31,8 mm de ligacao, o negociado fecha e a placa sai com 90 ligacoes,
    # 20 em aberto e nenhum erro - mas a `AL1` piora de 7 de 17 capacitores
    # fora do limite (media 3,06 mm) para 11 de 19 (3,85 mm). Preso de vez,
    # o ganho cai para 3,5 mm; com coleira de 2 mm, para 5,8 mm; nos dois
    # casos o negociado NAO fecha e a placa cai para o sequencial, com 85
    # ligacoes e 24 a 26 em aberto. Fica solto, e a `AL1` continua o item
    # grave que ela ja era: ela nao se resolve mexendo peca, e sim com mais
    # area, que o dono nao quer dar.
    moveis = [r for r in lugar if r not in presas and r in tam_bruto]

    def tira(ref: str):
        x, y, ang, atras = lugar[ref]
        postos_face[atras].remove(caixa_em(ref, x, y, ang))
        del lugar[ref]
        return (x, y, ang, atras)

    _registra = _registra_ci

    def poe(ref: str, x: float, y: float, ang: int, atras: bool) -> bool:
        bx = caixa(ref, ang)
        postos = postos_face[atras]
        if ref in PASSANTE:
            postos = postos + postos_face[not atras]
        if not livre(x, y, bx, postos, ref):
            return False
        lugar[ref] = (x, y, ang, atras)
        _registra(ref, x, y, ang, atras)
        postos_face[atras].append(caixa_em(ref, x, y, ang))
        return True

    ganho_total = 0.0
    for _volta in range(MELHORA_VOLTAS):
        mexeu = False
        for ref in sorted(moveis, key=lambda r: -custo([r])):
            if ref not in lugar:
                continue
            antes = custo([ref])
            if antes <= 0.0:
                continue
            x0, y0, ang0, atras0 = tira(ref)
            # o centro das pecas com que ele fala: e para la que ele quer ir
            amigos = set()
            for n_ in redes_de.get(ref, ()):
                amigos |= {r for r, _q in N.NETS[n_] if r != ref}
            alvos = [_cx_cy(r) for r in amigos]
            alvos = [q for q in alvos if q]
            melhor = (antes, x0, y0, ang0)
            if alvos:
                ax = sum(q[0] for q in alvos) / len(alvos)
                ay = sum(q[1] for q in alvos) / len(alvos)
                cands = []
                raio = PASSO
                while raio <= MELHORA_RAIO:
                    n_p = max(8, int(2 * math.pi * raio / PASSO))
                    for i in range(n_p):
                        a = 2 * math.pi * i / n_p
                        cands.append((round((ax + raio * math.cos(a)) / PASSO) * PASSO,
                                      round((ay + raio * math.sin(a)) / PASSO) * PASSO))
                    raio += PASSO
                cands.insert(0, (round(ax / PASSO) * PASSO,
                                 round(ay / PASSO) * PASSO))
                vistos_c = set()
                for cx_, cy_ in cands:
                    if (cx_, cy_) in vistos_c:
                        continue
                    vistos_c.add((cx_, cy_))
                    for ang in (ang0, (ang0 + 90) % 360):
                        if not poe(ref, cx_, cy_, ang, atras0):
                            continue
                        c = custo([ref])
                        if c < melhor[0] - 1e-9:
                            melhor = (c, cx_, cy_, ang)
                        tira(ref)
            # A peca TEM de voltar. `tira()` a arrancou de `lugar` e de
            # `postos_face`, e se o `poe()` final recusasse ela sumia da
            # placa calada: em 2026-09-29 o gerador passou a colocar 58 das
            # 59 pecas por causa disto. O lugar de origem era legal por
            # construcao, entao, se nem ele passar, ela volta a forca.
            if not poe(ref, melhor[1], melhor[2], melhor[3], atras0) and                     not poe(ref, x0, y0, ang0, atras0):
                lugar[ref] = (x0, y0, ang0, atras0)
                _registra(ref, x0, y0, ang0, atras0)
                postos_face[atras0].append(caixa_em(ref, x0, y0, ang0))
            if melhor[0] < antes - 1e-9:
                ganho_total += antes - melhor[0]
                mexeu = True
        if not mexeu:
            break
    if ganho_total > 0.0:
        print(f"  melhoria da colocacao: {ganho_total:.1f} mm de ligacao a "
              f"menos (HPWL)")

    return lugar, falhas


def cabecalho(n_redes: int, nomes: dict[str, int]) -> str:
    lay = [(0, "F.Cu", "signal", "top_cu"), (1, "In1.Cu", "signal", "gnd"),
           (2, "In2.Cu", "signal", "pwr"), (31, "B.Cu", "signal", "bottom_cu"),
           (32, "B.Adhes", "user", "B.Adhesive"), (33, "F.Adhes", "user", "F.Adhesive"),
           (34, "B.Paste", "user", None), (35, "F.Paste", "user", None),
           (36, "B.SilkS", "user", "B.Silkscreen"), (37, "F.SilkS", "user", "F.Silkscreen"),
           (38, "B.Mask", "user", None), (39, "F.Mask", "user", None),
           (40, "Dwgs.User", "user", "User.Drawings"), (41, "Cmts.User", "user", "User.Comments"),
           (42, "Eco1.User", "user", "User.Eco1"), (43, "Eco2.User", "user", "User.Eco2"),
           (44, "Edge.Cuts", "user", None), (45, "Margin", "user", None),
           (46, "B.CrtYd", "user", "B.Courtyard"), (47, "F.CrtYd", "user", "F.Courtyard"),
           (48, "B.Fab", "user", None), (49, "F.Fab", "user", None)]
    rows = "\n".join(f'\t\t({n} "{nm}" {ty}' + (f' "{al}")' if al else ")")
                     for n, nm, ty, al in lay)
    pilha = [('\t\t\t(layer "F.SilkS"\n\t\t\t\t(type "Top Silk Screen")\n\t\t\t)'),
             ('\t\t\t(layer "F.Paste"\n\t\t\t\t(type "Top Solder Paste")\n\t\t\t)'),
             ('\t\t\t(layer "F.Mask"\n\t\t\t\t(type "Top Solder Mask")\n'
              '\t\t\t\t(thickness 0.01)\n\t\t\t)')]
    for i, nm in enumerate(CU_LAYERS):
        pilha.append(f'\t\t\t(layer "{nm}"\n\t\t\t\t(type "copper")\n'
                     f'\t\t\t\t(thickness {CU})\n\t\t\t)')
        if i < 3:
            tipo = "core" if i == 1 else "prepreg"
            pilha.append(f'\t\t\t(layer "dielectric {i + 1}"\n\t\t\t\t(type "{tipo}")\n'
                         f'\t\t\t\t(thickness {DIEL[i]:.4f})\n\t\t\t\t(material "FR4")\n'
                         f'\t\t\t\t(epsilon_r 4.5)\n\t\t\t\t(loss_tangent 0.02)\n\t\t\t)')
    pilha += [('\t\t\t(layer "B.Mask"\n\t\t\t\t(type "Bottom Solder Mask")\n'
               '\t\t\t\t(thickness 0.01)\n\t\t\t)'),
              ('\t\t\t(layer "B.Paste"\n\t\t\t\t(type "Bottom Solder Paste")\n\t\t\t)'),
              ('\t\t\t(layer "B.SilkS"\n\t\t\t\t(type "Bottom Silk Screen")\n\t\t\t)'),
              '\t\t\t(copper_finish "None")\n\t\t\t(dielectric_constraints no)']
    ax = P_(0.0, 0.0)
    redes_txt = "\n".join(f'\t(net {i} "{nome}")'
                          for nome, i in sorted(nomes.items(), key=lambda kv: kv[1]))
    return ("(kicad_pcb\n\t(version 20240108)\n\t(generator \"pcbnew\")\n"
            "\t(generator_version \"8.0\")\n\t(general\n\t\t(thickness 0.8)\n"
            "\t\t(legacy_teardrops no)\n\t)\n\t(paper \"A4\")\n\t(layers\n" + rows + "\n\t)\n"
            "\t(setup\n\t\t(stackup\n" + "\n".join(pilha) + "\n\t\t)\n"
            "\t\t(pad_to_mask_clearance 0)\n"
            f"\t\t(aux_axis_origin {ax[0]:.4f} {ax[1]:.4f})\n"
            f"\t\t(grid_origin {ax[0]:.4f} {ax[1]:.4f})\n\t)\n" + redes_txt)


def contorno(saida: list[str], r: float) -> None:
    w = 0.1

    def linha(a, b):
        saida.append(f'\t(gr_line\n\t\t(start {a[0]:.4f} {a[1]:.4f})\n'
                     f'\t\t(end {b[0]:.4f} {b[1]:.4f})\n'
                     f'\t\t(stroke (width {w}) (type solid))\n\t\t(layer "Edge.Cuts")\n'
                     f'\t\t(uuid "{uid("l", a, b)}")\n\t)')

    def arco(c, a0, a1):
        def pt(d):
            return (c[0] + r * math.cos(math.radians(d)), c[1] + r * math.sin(math.radians(d)))
        s, m, e = pt(a0), pt((a0 + a1) / 2), pt(a1)
        saida.append(f'\t(gr_arc\n\t\t(start {s[0]:.4f} {s[1]:.4f})\n'
                     f'\t\t(mid {m[0]:.4f} {m[1]:.4f})\n\t\t(end {e[0]:.4f} {e[1]:.4f})\n'
                     f'\t\t(stroke (width {w}) (type solid))\n\t\t(layer "Edge.Cuts")\n'
                     f'\t\t(uuid "{uid("a", c, a0)}")\n\t)')

    # The notch under the module's antenna. Section 7.4 of the ME54BS13
    # datasheet asks for the PCB beneath the antenna to be hollowed out so
    # the antenna region is suspended, and figure 1 of 7.5 - the one it calls
    # "Best" - shows exactly this: the module in a corner with its RF end
    # over the void. Taking it out to the board edge makes it a notch rather
    # than a slot, which avoids leaving a 1 mm rib of board on the outside.
    recorte = next((z for n, z, _c, _s in M.ZONES
                    if n == "RECORTE_ANTENA_MODULO"), None)

    linha(P_(r, 0.0), P_(M.W - r, 0.0))
    if recorte:
        rx0, ry0, _rx1, ry1 = recorte
        linha(P_(M.W, r), P_(M.W, ry0))
        linha(P_(M.W, ry0), P_(rx0, ry0))
        linha(P_(rx0, ry0), P_(rx0, ry1))
        linha(P_(rx0, ry1), P_(M.W, ry1))
        linha(P_(M.W, ry1), P_(M.W, M.H - r))
    else:
        linha(P_(M.W, r), P_(M.W, M.H - r))
    linha(P_(M.W - r, M.H), P_(r, M.H))
    linha(P_(0.0, M.H - r), P_(0.0, r))
    arco(P_(M.W - r, r), 270, 360)
    arco(P_(M.W - r, M.H - r), 0, 90)
    arco(P_(r, M.H - r), 90, 180)
    arco(P_(r, r), 180, 270)


def pad_no_lugar(ref: str, numero: str, lugar: dict):
    """Where a pad ends up on the board, given the placement."""
    if ref not in lugar or ref not in FPS.FP:
        return None
    arv = fp_load.parse(fp_load.carregar(FPS.FP[ref][0])[0])
    for q in fp_load.kids(arv, "pad"):
        if q[1] != numero:
            continue
        a = fp_load.kid(q, "at")
        px, py = float(a[1]), float(a[2])
        x, y, ang, atras = lugar[ref]
        if atras:
            px = -px
        r = math.radians(ang)
        return (x + px * math.cos(r) + py * math.sin(r),
                y - px * math.sin(r) + py * math.cos(r))
    return None


def sem_plano_no_chaveamento(lugar: dict, por_pad: dict) -> list[tuple]:
    """Where no copper pour may go: under a switching node.

    Section 13 of DS-AEM1090x-v2.4.0, word for word: "PCB track capacitance
    must be reduced as much as possible on the boost converter switching node
    SWDCDC. This is done as follows: keep the connection between the SWDCDC
    pin and the inductor short; REMOVE THE GROUND AND POWER PLANES UNDER THE
    SWDCDC NODE - the polygon on the opposite external layer may also be
    removed - increase the distance between SWDCDC and the ground polygon on
    the external PCB layer where the AEM1090x is mounted." And the same
    principle for TH_REF.

    A pour under a switching node is capacitance the converter has to charge
    and discharge at its switching frequency, and on a harvester that runs on
    microwatts that is not a detail. So the rectangle that holds the node's
    pads, with margin, is cut out of every plane.
    """
    zonas = []
    for rede, folga in (("BUCK_SW", 0.6),):
        pontos = []
        for (ref, num), nome in por_pad.items():
            if nome != rede or ref not in lugar:
                continue
            q = pad_no_lugar(ref, num, lugar)
            if q:
                pontos.append(q)
        if len(pontos) < 2:
            continue
        x0 = min(q[0] for q in pontos) - folga
        y0 = min(q[1] for q in pontos) - folga
        x1 = max(q[0] for q in pontos) + folga
        y1 = max(q[1] for q in pontos) + folga
        zonas.append((f"SEM_PLANO_{rede}", (x0, y0, x1, y1)))
    return zonas


def keepout(nome: str, x0: float, y0: float, x1: float, y1: float,
            so_plano: bool = False) -> str:
    """A forbidden area. With so_plano, only the pour is forbidden.

    An antenna zone forbids every kind of copper. A switching node is
    different: section 13 of the AEM10900 datasheet asks to "remove the
    ground and power PLANES under the SWDCDC node", and the node's own track
    obviously has to be there - it is the whole point of the rule. Forbidding
    tracks there too put sixteen items_not_allowed in the DRC, every one of
    them the switching node itself.
    """
    pts = [P_(x0, y0), P_(x1, y0), P_(x1, y1), P_(x0, y1)]
    poly = "\n".join(f"\t\t\t\t(xy {px:.4f} {py:.4f})" for px, py in pts)
    camadas = " ".join(f'"{ly}"' for ly in CU_LAYERS)
    return (f'\t(zone\n\t\t(net 0)\n\t\t(net_name "")\n\t\t(layers {camadas})\n'
            f'\t\t(uuid "{uid("z", nome)}")\n\t\t(name "{nome}")\n\t\t(hatch edge 0.5)\n'
            '\t\t(connect_pads\n\t\t\t(clearance 0)\n\t\t)\n\t\t(min_thickness 0.25)\n'
            '\t\t(filled_areas_thickness no)\n\t\t(keepout\n'
            # An antenna zone forbids COPPER, not parts: the radio module's
            # own antenna sits inside its own keep-out, and its pads with it.
            # A switching node's zone forbids only the POUR, because the node
            # itself has to run there.
            f'\t\t\t(tracks {"allowed" if so_plano else "not_allowed"})\n'
            f'\t\t\t(vias {"allowed" if so_plano else "not_allowed"})\n'
            '\t\t\t(pads allowed)\n'
            '\t\t\t(copperpour not_allowed)\n\t\t\t(footprints allowed)\n\t\t)\n'
            '\t\t(fill\n\t\t\t(thermal_gap 0.5)\n\t\t\t(thermal_bridge_width 0.5)\n\t\t)\n'
            f'\t\t(polygon\n\t\t\t(pts\n{poly}\n\t\t\t)\n\t\t)\n\t)')


def virar(corpo: str) -> str:
    """Flip a footprint to the back face.

    KiCad does not flip a footprint when its layer says B.Cu: the file has to
    already hold the mirrored geometry and the back layer names. Leaving the
    pads on F.Cu under a footprint declared on B.Cu is what makes the DRC say
    two pads of the same connector are shorted with zero clearance - which is
    what it said before this existed.
    """
    for f, b in (('"F.Cu"', '"B.Cu"'), ('"F.Paste"', '"B.Paste"'),
                 ('"F.Mask"', '"B.Mask"'), ('"F.SilkS"', '"B.SilkS"'),
                 ('"F.CrtYd"', '"B.CrtYd"'), ('"F.Fab"', '"B.Fab"'),
                 ('"F.Adhes"', '"B.Adhes"')):
        corpo = corpo.replace(f, b)

    # mirror x on every coordinate the footprint carries
    saida: list[str] = []
    i = 0
    chaves = ("(at ", "(start ", "(end ", "(center ", "(mid ", "(xy ")
    while i < len(corpo):
        for k in chaves:
            if corpo.startswith(k, i):
                j = corpo.index(")", i) if ")" in corpo[i:] else len(corpo)
                dentro = corpo[i + len(k):j].split()
                if dentro and _numero(dentro[0]):
                    dentro[0] = f"{-float(dentro[0]):g}"
                    if k == "(at " and len(dentro) == 3 and _numero(dentro[2]):
                        dentro[2] = f"{(180.0 - float(dentro[2])) % 360:g}"
                saida.append(k + " ".join(dentro) + ")")
                i = j + 1
                break
        else:
            saida.append(corpo[i])
            i += 1
    return "".join(saida)


def _numero(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def girar_pads(corpo: str, ang: int) -> str:
    """Turn every pad by the footprint's angle.

    In a .kicad_pcb a pad's own angle is ABSOLUTE, not relative to its
    footprint: KiCad rotates the pad's position with the footprint but not the
    pad's body. Leave it out and a rotated connector's pads keep their
    original orientation while their centres turn, so they overlap and the DRC
    reports zero clearance between neighbours - which is what it reported
    until this existed.
    """
    if ang % 360 == 0:
        return corpo
    saida: list[str] = []
    i = 0
    dentro_pad = False
    while i < len(corpo):
        if corpo.startswith("(pad ", i):
            dentro_pad = True
        elif dentro_pad and corpo.startswith("(at ", i):
            j = corpo.index(")", i)
            v = corpo[i + 4:j].split()
            a = float(v[2]) if len(v) > 2 else 0.0
            saida.append(f"(at {v[0]} {v[1]} {(a + ang) % 360:g})")
            i = j + 1
            dentro_pad = False
            continue
        saida.append(corpo[i])
        i += 1
    return "".join(saida)


def plano_de_terra(numero: int, camadas: tuple[str, ...], recuo: float) -> str:
    """A ground pour, which is what makes the inner layer a reference plane.

    04-pcb-e-caixa.md is explicit that In1.Cu is a solid ground and that the
    plane is what the GNSS antenna radiates against. The zone is drawn here
    and KiCad fills it when the board is opened; the keep-outs already refuse
    a pour, so the two antenna areas stay clear on their own.
    """
    r = M.RADIUS_DRAWING
    pts = []
    for cx, cy, a0, a1 in ((r, r, 180, 270), (M.W - r, r, 270, 360),
                           (M.W - r, M.H - r, 0, 90), (r, M.H - r, 90, 180)):
        for k in range(9):
            a = math.radians(a0 + (a1 - a0) * k / 8.0)
            pts.append(P_(cx + (r - recuo) * math.cos(a) + (recuo if cx < M.W / 2 else -recuo),
                          cy + (r - recuo) * math.sin(a) + (recuo if cy < M.H / 2 else -recuo)))
    poly = "\n".join(f"\t\t\t\t(xy {px:.4f} {py:.4f})" for px, py in pts)
    lay = " ".join(f'"{ly}"' for ly in camadas)
    return (f'\t(zone\n\t\t(net {numero})\n\t\t(net_name "GND")\n\t\t(layers {lay})\n'
            f'\t\t(uuid "{uid("gnd", camadas)}")\n\t\t(name "PLANO_GND")\n'
            '\t\t(hatch edge 0.5)\n\t\t(priority 0)\n'
            # SOLID, not thermal reliefs. Left on the KiCad default, eleven
            # ground pads came out with fewer than two spokes - U101, U102,
            # U104, U503, U504, both shield rows of the USB-C receptacle and
            # three passives - because a track runs past the side the second
            # spoke needed. A one spoke connection is a 0.3 mm neck in series
            # with the return current of the USB shell and of the MCU, on a
            # board that carries a 2.4 GHz radio and two switching
            # converters, and it is the only thing the DRC calls an error
            # here. Thermal relief is a HAND and WAVE soldering aid; nothing
            # on this board can be soldered by hand anyway - 0402s, a WLP-9
            # and a 0.4 mm pitch QFN.
            #
            # What it costs, written down because it is a real cost: reworking
            # a ground pad by hand needs more heat, and a 0402 with one end on
            # the pour and the other not is a little likelier to tombstone at
            # reflow. If the assembly house objects, this is the one line to
            # change - `yes` back to nothing.
            '\t\t(connect_pads yes\n\t\t\t(clearance 0.2)\n\t\t)\n'
            '\t\t(min_thickness 0.2)\n\t\t(filled_areas_thickness no)\n'
            '\t\t(fill yes\n\t\t\t(thermal_gap 0.3)\n\t\t\t(thermal_bridge_width 0.3)\n\t\t)\n'
            f'\t\t(polygon\n\t\t\t(pts\n{poly}\n\t\t\t)\n\t\t)\n\t)')


def uuids_unicos(corpo: str, ref: str) -> str:
    """Um UUID por item da placa, e nao um por desenho de footprint.

    `footprints._pad()` deriva o UUID da ilha do NUMERO do pino e da posicao
    DENTRO do footprint, que sao os mesmos em toda instancia do mesmo
    desenho: os dezessete resistores 0402 saiam todos com a mesma ilha "1".
    O KiCad guarda os itens num mapa por KIID, entao um UUID repetido faz o
    relatorio do DRC descrever o item ERRADO: a lista de desconectados
    trazia pares entre redes diferentes ("Ilha 1 [VBUS] de TP101" contra uma
    ilha de UART_RX), o que nao existe num ratsnest, e por isso nao dava
    para saber o que faltava fechar. Medido em 2026-09-29: 2.791 UUIDs
    escritos, 2.325 distintos, 43 desenhos repetidos ate dezessete vezes.
    Aqui cada UUID passa a levar a referencia da peca junto.
    """
    def troca(m):
        return '(uuid "' + uid("it", ref, m.group(1)) + '")'
    return re.sub(r'\(uuid "([0-9a-f-]{36})"\)', troca, corpo)


def com_redes(corpo: str, ref: str, por_pad: dict, numeros: dict) -> str:
    """Put the net of each pad into the footprint body."""
    saida = []
    for linha in corpo.split("\n"):
        saida.append(linha)
        s = linha.strip()
        if s.startswith('(pad "'):
            num = s.split('"')[1]
            nome = por_pad.get((ref, num))
            if nome:
                ident = linha[:len(linha) - len(linha.lstrip())]
                saida.append(f'{ident}\t(net {numeros[nome]} "{nome}")')
    return "\n".join(saida)


def main() -> int:
    numeros, por_pad = redes()
    lugar, falhas = colocar()

    saida: list[str] = []
    contorno(saida, M.RADIUS_DRAWING)
    for nome, (x0, y0, x1, y1), _c, src in M.ZONES:
        if nome in KEEPOUTS:
            saida.append(keepout(nome, x0, y0, x1, y1))
        else:
            a, b = P_(x0, y0), P_(x1, y1)
            saida.append(
                f'\t(gr_rect\n\t\t(start {a[0]:.4f} {a[1]:.4f})\n'
                f'\t\t(end {b[0]:.4f} {b[1]:.4f})\n'
                f'\t\t(stroke (width 0.1) (type dash))\n\t\t(fill none)\n'
                f'\t\t(layer "Dwgs.User")\n\t\t(uuid "{uid("r", nome)}")\n\t)')

    # The switching nodes get their pour cut away, which is what section 13
    # of the AEM10900 datasheet asks for by name.
    for nome_z, (zx0, zy0, zx1, zy1) in sem_plano_no_chaveamento(lugar, por_pad):
        saida.append(keepout(nome_z, zx0, zy0, zx1, zy1, so_plano=True))

    # The ground planes. In1.Cu is the solid one and the reference the return
    # current follows; F.Cu and B.Cu get the leftover copper.
    #
    # The front pour is not decoration. Without it every ground pad on the
    # front face depended on a via of its own to reach In1.Cu, and in the
    # crowded corner around the power supply eighteen of the ninety-five had
    # nowhere to put one - so eighteen ground pads had no ground. With the
    # pour, KiCad ties them to it when it fills, and the stubs that do fit
    # stay as the low impedance path they were meant to be.
    if "GND" in numeros:
        saida.append(plano_de_terra(numeros["GND"], ("In1.Cu",), 0.3))
        saida.append(plano_de_terra(numeros["GND"], ("F.Cu",), 0.3))
        saida.append(plano_de_terra(numeros["GND"], ("B.Cu",), 0.3))

    # the mounting holes
    furo = pathlib.Path(
        r"D:\KiCAD\share\kicad\footprints\MountingHole.pretty"
        r"\MountingHole_2.2mm_M2.kicad_mod").read_text(encoding="utf-8")
    corpo_furo = furo[furo.index("\n"):].rstrip()[:-1].rstrip()
    # The library footprint carries a visible "REF**" on the silkscreen. It
    # names nothing - the hole is not a part - and on this board it was the
    # one label left sitting on another, over J402's.
    corpo_furo = corpo_furo.replace(
        '(property "Reference" "REF**"',
        '(property "Reference" "REF**" (hide yes)', 1)
    # And its COURTYARD has to be the same number the placer reserved, or the
    # two disagree and the DRC is right to say so. KiCad's footprint draws a
    # circle of 2,45 mm for the head of an M2 screw sitting ON the board;
    # here the head is on the pod's lid and only a 2,00 mm neck passes
    # through, so make_dxf.FURO_RESERVA_R is what the placer keeps clear and
    # it is what the courtyard has to be. Leaving the library's 2,45 gave
    # four courtyard overlaps against parts the placer had legitimately put
    # 2,5 to 3,0 mm away (2026-09-28).
    _r = getattr(M, "FURO_RESERVA_R", None)
    if _r is not None:
        # Per CIRCLE, not by a loose regular expression. The footprint's
        # FIRST fp_circle is the 2,2 mm one on Cmts.User - the hole itself -
        # and the courtyard is the second; a non-greedy match from "fp_circle"
        # to "F.CrtYd" therefore rewrote the WRONG circle and left the
        # courtyard at 2,45 (2026-09-28).
        def _corta(bloco: str) -> str:
            saida, i = [], 0
            while True:
                j = bloco.find("(fp_circle", i)
                if j < 0:
                    saida.append(bloco[i:])
                    break
                k = bloco.find("(fp_circle", j + 1)
                k = len(bloco) if k < 0 else k
                pedaco = bloco[j:k]
                if 'CrtYd"' in pedaco:
                    pedaco = re.sub(r"(\(end )[\d.]+( 0\))",
                                    lambda m: m.group(1) + f"{_r:.4f}" + m.group(2),
                                    pedaco, count=1)
                saida.append(bloco[i:j])
                saida.append(pedaco)
                i = k
            return "".join(saida)

        corpo_furo = _corta(corpo_furo)
    for i_furo, (dx_furo, dy_furo) in enumerate(M.FUROS_DOC):
        fx, fy = P_(dx_furo, dy_furo)
        saida.append('\t(footprint "MountingHole:MountingHole_2.2mm_M2"\n'
                     f'\t\t(at {fx:.4f} {fy:.4f})\n'
                     f'\t\t(uuid "{uid("furo%d" % i_furo)}")'
                     + corpo_furo.replace("\n", "\n\t") + "\n\t)")

    # where each reference designator goes, decided once for the whole board
    desloca = rotulos(lugar)

    # the parts
    for ref, (x, y, ang, atras) in sorted(lugar.items()):
        nome_fp = FPS.FP[ref][0]
        corpo = fp_load.corpo(nome_fp)
        if atras:
            corpo = virar(corpo)
            # a maker's model on the back may need its own offset, measured
            # (footprints.MODELO_GIRADO_VERSO): the flip is KiCad's, and it
            # does not mirror the model offset the way it mirrors the pads
            corpo = FPS.modelo_no_verso(corpo)
        corpo = girar_pads(corpo, ang)
        corpo = com_redes(corpo, ref, por_pad, numeros)
        corpo = uuids_unicos(corpo, ref)
        px, py = P_(x, y)
        camada = "B.Cu" if atras else "F.Cu"
        # rotulos() picks the offset in the BOARD's frame, and KiCad turns a
        # footprint property by the footprint's own angle before drawing it.
        # Written straight through, a label placed "above" a part rotated 90
        # degrees came out beside it: measured in the exported silkscreen,
        # 38 pairs still overlapped while this file believed there were none.
        # So the world offset is turned back into the footprint's frame,
        # with the same transform pad_global() uses, and mirrored on the back
        # face for the same reason the pads are.
        _r = math.radians(ang)
        _dx, _dy, _ang_rot = desloca[ref]
        _rot = (_dx * math.cos(_r) - _dy * math.sin(_r),
                _dx * math.sin(_r) + _dy * math.cos(_r))
        if atras:
            _rot = (-_rot[0], _rot[1])
        cab = (f'\t(footprint "{nome_fp}"\n\t\t(layer "{camada}")\n'
               f'\t\t(at {px:.4f} {py:.4f} {ang})\n'
               f'\t\t(uuid "{uid("fp", ref)}")\n'
               f'\t\t(property "Reference" "{ref}"\n'
               f'\t\t\t(at {_rot[0]:.4f} {_rot[1]:.4f} {_ang_rot})\n'
               f'\t\t\t(layer "{"B" if atras else "F"}.SilkS")\n'
               f'\t\t\t(uuid "{uid("fpref", ref)}")\n'
               f'\t\t\t(effects (font (size {TEXTO_ALT} {TEXTO_ALT}) '
               f'(thickness {TEXTO_TRACO}))'
               + (' (justify mirror)' if atras else '') + ')\n\t\t)\n'
               f'\t\t(property "Value" "{P.PARTS[ref].value}"\n\t\t\t(at 0 1.8 0)\n'
               f'\t\t\t(layer "{"B" if atras else "F"}.Fab")\n'
               f'\t\t\t(uuid "{uid("fpval", ref)}")\n'
               '\t\t\t(effects (font (size 0.6 0.6) (thickness 0.1))'
               + (' (justify mirror)' if atras else '') + ')\n\t\t)')
        saida.append(cab + corpo + "\n\t)")

    notas = [
        f"BIKE POWER METER - placa {M.W:g} x {M.H:g} mm, "
        f"{M.THICKNESS:g} mm, 4 camadas",
        f"{len(lugar)} pecas colocadas; a ponte de extensometros vive no braco "
        "e chega pelos pads J301",
        f"{len(M.FUROS_DOC)} furos; empilhamento assimetrico {DIEL_RF:g} / "
        f"{DIEL_NUCLEO:.2f} / {DIEL_RF:g} mm, o mesmo do ciclocomputador",
        "ROTEAMENTO PARCIAL; NADA FABRICADO, NADA MEDIDO",
    ]
    for i, s in enumerate(notas):
        p = P_(0.0, M.H + 3.0 + i * 2.0)
        saida.append(f'\t(gr_text "{s}"\n\t\t(at {p[0]:.4f} {p[1]:.4f} 0)\n'
                     f'\t\t(layer "Cmts.User")\n\t\t(uuid "{uid("t", i)}")\n'
                     '\t\t(effects (font (size 1.2 1.2) (thickness 0.2)) '
                     '(justify left top))\n\t)')

    out = HERE / "pmeter.kicad_pcb"
    out.write_text(cabecalho(len(numeros), numeros) + "\n" + "\n".join(saida) + "\n)\n",
                   encoding="utf-8", newline="\n")
    print(f"{out.name}: {len(lugar)} pecas, {len(numeros) - 1} redes, "
          f"{len(KEEPOUTS)} areas de regra")
    if falhas:
        print(f"  NAO COLOCADAS: {len(falhas)}")
        for f in falhas:
            print(f"    {f}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
