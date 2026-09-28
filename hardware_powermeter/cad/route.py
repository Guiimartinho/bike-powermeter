#!/usr/bin/env python3
"""Route the board: tracks on the two outer layers, vias, and ground by plane.

How a four layer board of this kind is routed, and what this does:

  GND      is not routed as tracks. In1.Cu is a solid ground pour and F.Cu
           and B.Cu carry one too, so a ground pad is connected by the pour
           of its own face; on top of that each one gets a short stub to a
           via down into the inner plane, which is the short return path.
           The edge is stitched with a ground via about every 3 mm, because
           two planes are one plane only if they are tied together often
           enough - a tenth of a wavelength at 2.44 GHz is about 6 mm.
  signals  are maze routed on F.Cu, In2.Cu and B.Cu, with a via to change
           layer. The cost of a via is high enough that a run only changes
           layer when it has to.
  power    uses the wider track of the Alimentacao net class.
  RF       goes FIRST, on the front layer only, at the calculated 50 ohm
           width for this stack-up (0.196 mm), with ground vias down both
           sides. First because its path is the one that is not negotiable
           and it has to leave the receiver's pin before anything else takes
           the room; front only because a via in the middle of an RF run is
           a stub, which 7.2 of the module datasheet forbids by name. The
           width still assumes the dielectric constant of ordinary FR-4 -
           the fabricator's own stack-up is an open item in
           04-pcb-e-caixa.md, and the dry-run prints the assumption.

Order matters: the switching nodes of the two bucks and of the harvester go
first and stay short, because their loop area is what radiates; then the USB
pair, together; then everything else, shortest first.

TWO GRIDS, and why. The first version kept one grid, inflated by half a
track plus the clearance, and used it for tracks and for vias alike. The
board it produced failed 974 design rules. So: one grid for what a track may
occupy, one for where the CENTRE of a via may land. Along the way, each of
these was a defect that the DRC found and the grid had not:

  a via is 0.45 mm wide where a track is 0.15, with a 0.25 mm hole that the
  grid did not model, so every via sat about 0.15 mm too close;
  pads were inflated as circles of half their longest side, which fits a
  round pad and leaves the corners of a square one bare;
  the ground stub left the pad on whatever bearing was free AT THE VIA,
  crossing whatever lay in between without asking;
  the clearance of a pad was remembered with "first come, first served", so
  a cell inside TWO pads' clearance kept only one of them and a track of the
  first ran 0.025 mm from the second;
  the USB class asks for 0.2 mm and was treated as the default 0.127;
  a 0.4 mm power track ran onto a 0.2 mm pad and stuck out on both sides;
  a via was checked at the grid cell and then drilled at the raw coordinate,
  up to half a step - 0.075 mm - away from what had been checked;
  and writing the tracks did not remove the previous run's, so routing twice
  left two sets of copper on top of each other.

What guards against the next one is conferir(): it measures the result
against itself, shape by shape, before the board is written.

Run:   python hardware_powermeter/cad/route.py
Check: python hardware_powermeter/cad/check_pcb.py
"""

from __future__ import annotations

import heapq
import math
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import footprints as FPS  # noqa: E402,F401
import fp_load  # noqa: E402
import make_dxf as M  # noqa: E402
import make_pcb as MP  # noqa: E402

PASSO = 0.15                # routing grid, mm. 0.3 does not fit between
                            # the balls of the module's LGA: the free band
                            # between two columns is 0.45 mm wide
LARGURA = 0.15              # default track width
LARGURA_ALIM = 0.4          # power track width
LARGURA_USB = 0.2
VIA_D, VIA_FURO = 0.45, 0.25

# The grid is marked for the NARROWEST track and the smallest clearance, and
# a wider or better spaced net asks for the extra radius when it looks. The
# first version inflated everything by the widest track and the widest
# clearance, and then nothing could escape a 0.5 mm pitch LGA: every net
# failed, every failure retried over the whole board, and a pass took
# forever. Two nets need centre to centre wA/2 + folga + wB/2, and marking
# wA/2 + FOLGA + LARGURA/2 while B asks for (wB - LARGURA)/2 gives exactly
# that.
# The classes of pmeter.kicad_pro, read and not guessed: Default 0.127,
# Alimentacao 0.127 (it differs by via size, not by clearance) and USB 0.2.
# Treating USB as 0.127 is what put a ground track 0.075 mm from USB_DP.
FOLGA = 0.14                # 0.127 of the class, plus the grid
FOLGA_FURO = 0.21           # 0.2 do min_hole_clearance, mais a grade
FOLGA_USB = FOLGA           # the USB class keeps the fabricator's 0,127 here
                            # (make_pro.py): at full speed on 3 cm of track
                            # the 0,2 of the bike computer bought nothing
                            # and closed every 0,5 mm pitch escape
# A via next to a pad has to leave more than the electrical clearance: the
# two solder mask openings grow about 0.05 mm each and the web of mask left
# between them has to be wide enough to survive, or the DRC reports a mask
# bridge - 41 of them on the last board. 0.35 mm of copper leaves about
# 0.25 mm of mask, which is the usual minimum.
FOLGA_MASCARA = 0.35
# how far past a footprint's pad box the neck of a track lasts: the
# neighbouring pad's clearance ring plus a grid step (see the main loop)
EXTRA_CAMPO = FOLGA + LARGURA / 2 + PASSO
BORDA_COBRE = 0.3           # copper to board edge
# O que um ponto da grade precisa guardar ate a borda: o isolamento de
# cobre MAIS metade da via, porque o roteador poe uma via em qualquer
# ponto onde troca de camada.
MARGEM_BORDA = 0.3 + 0.45 / 2
# Three routing layers, not two. In1.Cu is the ground plane and stays one:
# it is what the return current follows and what the GNSS antenna radiates
# against, and cutting it up to gain routing space would cost more than it
# gains. In2.Cu was EMPTY - a whole copper layer paid for and unused - while
# 77 connections had nowhere to go on the other two. A signal on In2.Cu has
# the ground plane above it and the back pour below, which is a better
# reference than either outer layer gets.
CAMADAS = ("F.Cu", "In2.Cu", "B.Cu")
NC = len(CAMADAS)
I_BCU = NC - 1
# 6 and not the bike computer's 16 (2026-09-27, measured on this board).
# A via costs this many grid steps of path. At 16 (2,4 mm) the maze would
# rather squeeze along F.Cu than drop to B.Cu, and B.Cu here is EMPTY -
# every part is on the front, because the cell lies under the board. At 6
# the back face is used and twelve more connections closed; at 3 the board
# filled with vias and it got worse again.
CUSTO_VIA = 6.0             # in grid steps, about 0,9 mm
CUSTO_CURVA = 0.7             # virar 90 graus
CUSTO_CURVA_45 = 0.2          # virar 45: meia virada, meio custo
# A maze search that cannot get through explores everything it is allowed to
# before saying so, and on a 367 x 647 grid over two layers that is nearly a
# million cells for one net that was never going to route. The budget turns a
# hopeless search into two seconds instead of half a minute; what it costs is
# that a genuinely tortuous path may be given up on, and that shows in the
# report as a net left unrouted rather than as a wrong board.
ORCAMENTO = 300000   # era 90000: o tabuleiro tem ~400 mil celulas

BLOQUEADO = "\x00"          # a net name no net can have: blocked for everyone

# The RF nets. They are routed LAST and at the calculated 50 ohm width, on
# the front layer only, with the ground pour beside them and ground vias
# along both sides: a via in the middle of an RF run is a stub, and a stub is
# what section 7.2 of the module datasheet forbids by name.
# RF_UFL and RF_CHIP are the two branches after the choice jumper: both are
# 50 ohm line and both are routed at the RF width on the front layer, even
# though only one is ever fitted. The unfitted one ends at an open pad.
NAO_ROTEAR: set[str] = set()
# O par do USB tambem fica na frente: os 0,207 mm de 90 ohm foram
# calculados para microstrip em F.Cu sobre o plano de terra a 0,10 mm. Em
# In2.Cu a mesma trilha tem o plano a 0,46 mm de um lado e o despejo de B.Cu
# a 0,10 do outro, e nao e 90 ohm de nada. As amarracoes dos contatos
# repetidos ficam em In2.Cu de proposito, mas sao emendas de 1,7 mm entre
# ilhas do mesmo no, nao a linha.
#
# E uma preferencia, nao uma lei, e a diferenca foi medida em 2026-09-28: com
# ela como lei o USB_DM nao fecha. Ele tem de ir de J101 (23,5; 2,1) a U101
# (7,2; 6,0) e a U201 (35,6; 2,0) - 16,7 e 8,3 mm - por uma face de cima que
# ja esta cheia, e o roteador dava por encerrado deixando o par em tres
# pedacos. Este aparelho fala USB **full speed**, 12 Mbit/s: o proprio
# make_pro.py registra que a essa velocidade, em 3 cm de trilha, nem a folga
# maior do outro projeto comprou nada. Um trecho em In2.Cu fora dos 90 ohm
# nao muda nada a 12 Mbit/s, e uma ligacao que nao existe muda tudo. Entao a
# busca tenta a frente primeiro, nas duas folgas, e so troca de camada se a
# frente nao tiver caminho.
SO_FRENTE = NAO_ROTEAR | {"USB_DP", "USB_DM"}
# The differential pair. They are routed one after the other, and the second
# one is drawn towards the first, so they run together instead of taking two
# unrelated paths across the board.
PAR = ("USB_DP", "USB_DM")
# Nets that go first and have to stay short: the switching loops.
PRIMEIRO = ["BUCK_SW", "USB_DP", "USB_DM"]


ALIMENTACAO = ("GND", "VSYS", "VBAT", "VBUS", "3V0", "3V0_MOD", "3V0_EXC")


def e_alimentacao(rede: str) -> bool:
    return rede in ALIMENTACAO or rede.startswith("3V0_")



# --- impedancia ------------------------------------------------------------
# The RF line has to be 50 ohm and the USB pair 90 ohm differential, and both
# datasheets say so: ME54BS13 7.2 ("strict 50 ohm characteristic impedance,
# tolerance +-10 %") and MAX-F10S integration manual 4.4 ("the impedance of
# the RF signal line must be 50 ohm; select the stack-up, copper, and
# dielectric properties of the PCB accordingly").
#
# The stack-up is in the board file, so the width is a calculation and not an
# open question: four copper layers of 35 um in 0.80 mm, which leaves
# (0.80 - 4 x 0.035) / 3 = 0.22 mm of dielectric between F.Cu and the ground
# plane on In1.Cu. What is NOT known is the dielectric constant - it is the
# fabricator's, and 4.3 is the usual value for FR-4 at these frequencies.
# That assumption is the reason the result is printed with its inputs.
ER_FR4 = 4.3                 # ASSUMIDO: confirmar com o fabricante
H_DIEL = MP.DIEL_RF           # F.Cu ao plano de terra, do empilhamento
T_CU = 0.035


def z0_microstrip(w: float, h: float = H_DIEL, er: float = ER_FR4) -> float:
    """Hammerstad's microstrip impedance, in ohm."""
    u = w / h
    ef = (er + 1) / 2 + (er - 1) / 2 * (1 + 12 / u) ** -0.5
    if u <= 1:
        return 60 / math.sqrt(ef) * math.log(8 / u + u / 4)
    return 120 * math.pi / (math.sqrt(ef) * (u + 1.393 + 0.667 * math.log(u + 1.444)))


def largura_para(z_alvo: float) -> float:
    """The width that gives this impedance, by bisection on the formula."""
    lo, hi = 0.05, 3.0
    for _ in range(60):
        meio = (lo + hi) / 2
        # a narrower track has HIGHER impedance, so overshooting the target
        # means the track has to get wider, not narrower
        if z0_microstrip(meio) > z_alvo:
            lo = meio
        else:
            hi = meio
    return round((lo + hi) / 2, 3)


LARGURA_RF = largura_para(50.0)
# A coplanar waveguide with its ground far enough away behaves as a plain
# microstrip; the datasheets ask for CPWG, so the pour stays beside the line
# with a gap of at least three widths, and the ground vias go along both
# sides. Closer than that and this number would have to be recomputed with
# the coplanar formula.
FOLGA_CPWG = 3.0 * LARGURA_RF
# The USB pair is 90 ohm DIFFERENTIAL, and that is not two 45 ohm lines: a
# 0.2 mm gap over 0.22 mm of dielectric couples them, and coupling lowers the
# differential impedance. The usual closed form for an edge-coupled
# microstrip is used here,
#
#     Zdiff = 2 x Z0 x (1 - 0.48 x exp(-0.96 x S/H))
#
# which is an approximation: the real number comes from the fabricator's
# field solver together with the real dielectric constant. Both assumptions
# are printed by the dry-run so that neither hides.
PASSO_PAR = 0.2              # gap between the two tracks of the pair


def z_diferencial(w: float, s: float = PASSO_PAR) -> float:
    return 2 * z0_microstrip(w) * (1 - 0.48 * math.exp(-0.96 * s / H_DIEL))


def largura_par(z_alvo: float = 90.0) -> float:
    lo, hi = 0.05, 3.0
    for _ in range(60):
        meio = (lo + hi) / 2
        if z_diferencial(meio) > z_alvo:
            lo = meio
        else:
            hi = meio
    return round((lo + hi) / 2, 3)


LARGURA_USB_CALC = largura_par(90.0)


_LARG_CACHE: dict = {}


def largura_de_corrente(rede: str) -> float:
    """The width a rail needs for the current it actually carries.

    One number for every power net wastes copper on a board this tight:
    0,4 mm is right for the 500 mA that come in from the cable and four
    times what the 3,0 V rail needs, and the extra is exactly the channel
    some signal could not find. The current per rail is already written
    down, with its source, in dry_run_pcb.CORRENTE - the table the AL2 rule
    measures the finished board against - so the width comes from the same
    place by the same IPC-2221 curve, and whatever comes out passes AL2 by
    construction. Measured on 2026-09-27: eleven more connections closed,
    and no rail came out under what the standard asks.
    """
    if rede in _LARG_CACHE:
        return _LARG_CACHE[rede]
    larg = LARGURA_ALIM
    try:
        import dry_run_pcb as _DR
        if rede in _DR.CORRENTE:
            i, _fonte = _DR.CORRENTE[rede]
            pedida = max(_DR.largura_ipc(i, interna=False),
                         _DR.largura_ipc(i, interna=True))
            larg = max(LARGURA, min(LARGURA_ALIM, round(pedida + 0.02, 3)))
    except Exception:
        larg = LARGURA_ALIM
    _LARG_CACHE[rede] = larg
    return larg


def largura(rede: str) -> float:
    if rede in NAO_ROTEAR:
        return LARGURA_RF
    if rede.startswith("USB_D"):
        # A largura que da 90 ohm diferenciais NESTA pilha, calculada logo
        # acima: 0,207 mm com 0,2 de afastamento. Ela cabe.
        #
        # Este comentario dizia 0,352 mm, e isso ficou aqui desde
        # 2026-09-24 sem nunca ter sido conta: 0,352 e a largura de 90 ohm
        # na pilha UNIFORME de 0,22 mm por vao, que foi abandonada no mesmo
        # commit que criou este calculo. Com os 0,10 mm de prepreg que a
        # placa tem, a mesma formula da 0,207. O numero errado sustentava um
        # argumento inteiro - "0,352 nao sai do campo de ilhas de 0,5 mm de
        # passo, entao o par e roteado mais fino e a diferenca e reportada" -
        # que simplesmente nao existe: 0,207 sai.
        return LARGURA_USB_CALC
    if e_alimentacao(rede):
        return largura_de_corrente(rede)
    return LARGURA


def folga_de(rede: str) -> float:
    return FOLGA_USB if rede.startswith("USB_D") else FOLGA


def extra_de(rede: str) -> float:
    """How much further than the marked halo this net has to look.

    The grid carries the narrowest track at the smallest clearance. A net
    that is wider, or that belongs to a class with more clearance, makes up
    the difference here, at the moment it looks - which costs a small disc
    per cell instead of shutting every fine-pitch escape route.
    """
    return max(0.0, (folga_de(rede) - FOLGA) + (largura(rede) - LARGURA) / 2)


def _disco_off(raio: float) -> tuple[tuple[int, int], ...]:
    """The cells a net of this net's width has to look at, beyond its own.

    A full grid step of slack, not none. The marked cells are a discrete
    set: the nearest one to a given cell can be up to a step further away
    than the true nearest point of the obstacle, and asking only about cells
    whose CENTRE is within the radius then misses it. That gap is what let a
    0.4 mm power track sit 0.110 mm from a pad that wanted 0.127.
    """
    if raio <= 1e-9:
        # nothing to make up: a cell that is not marked is already far
        # enough, because that is exactly what the marking means
        return ((0, 0),)
    # One and a half grid steps of slack, not one. The marked cells are a
    # discrete set and the disc is round: at one step the DRC still found 13
    # pairs at 0,049 mm, and at one and a half it found none - and unlike
    # widening the mark, this costs nothing at a fine-pitch escape.
    lim = raio + 1.5 * PASSO
    n = int(math.ceil(lim / PASSO))
    return tuple((dx, dy)
                 for dx in range(-n, n + 1) for dy in range(-n, n + 1)
                 if math.hypot(dx * PASSO, dy * PASSO) <= lim + 1e-9)


class Grade:
    """Where a track may run, and where the centre of a via may land.

    Two maps, because the two things have different sizes. `t` answers "may
    a track of this net occupy this cell"; `v` answers "may a via of this
    net be centred on this cell". Both are keyed by (layer, ix, iy); the via
    map is checked on both layers, since a via goes through.
    """

    def __init__(self) -> None:
        self.nx = int(M.W / PASSO) + 1
        self.ny = int(M.H / PASSO) + 1
        self.t: dict[tuple[int, int, int], str] = {}
        self.v: dict[tuple[int, int, int], str] = {}
        self.fixo: set[tuple[int, int, int]] = set()   # a pad's own copper
        self.postas: set[tuple[int, int]] = set()      # via centres already used

    def cel(self, x: float, y: float) -> tuple[int, int]:
        return (int(round(x / PASSO)), int(round(y / PASSO)))

    def pos(self, ix: int, iy: int) -> tuple[float, float]:
        return (ix * PASSO, iy * PASSO)

    def dentro(self, ix: int, iy: int) -> bool:
        """Can a track or a via CENTRE sit here?

        The margin is not BORDA_COBRE. BORDA_COBRE is what the DRC asks
        between COPPER and the board outline, and what sits on a grid point
        is a centre line: a via of 0,45 mm centred 0,3 mm from the edge
        leaves copper at 0,075, and the DRC says so. The router also drops a
        via wherever it changes layer, so every grid point has to hold the
        widest thing that can land on it, which is the via and not the
        track. That costs 0,225 mm of routable area all round, and it is the
        difference between a board that passes the DRC and one that does
        not - two errors of exactly this kind, a GND track at 0,100 mm and a
        stitching via at 0,075 mm, are what put this comment here.
        """
        x, y = self.pos(ix, iy)
        if x < MARGEM_BORDA or y < MARGEM_BORDA or \
                x > M.W - MARGEM_BORDA or y > M.H - MARGEM_BORDA:
            return False
        # the notch under the module's antenna is not board: copper there is
        # copper hanging in the air, and the DRC calls it what it is
        for nome, (rx0, ry0, rx1, ry1), _c, _s in M.ZONES:
            if nome != "RECORTE_ANTENA_MODULO":
                continue
            if rx0 - MARGEM_BORDA < x < rx1 + MARGEM_BORDA and \
                    ry0 - MARGEM_BORDA < y < ry1 + MARGEM_BORDA:
                return False
        r = M.RADIUS_DRAWING
        for cx, cy in ((r, r), (M.W - r, r), (r, M.H - r), (M.W - r, M.H - r)):
            fora_x = x < r if cx < M.W / 2 else x > M.W - r
            fora_y = y < r if cy < M.H / 2 else y > M.H - r
            if fora_x and fora_y and math.hypot(x - cx, y - cy) > r - MARGEM_BORDA:
                return False
        return True

    # -- marking ----------------------------------------------------------
    def _por(self, mapa: dict, k, rede: str,
             respeitar_fixo: bool = True) -> None:
        """Claim one cell for a net's clearance, and refuse to lie about it.

        A cell can fall inside the clearance of TWO different nets. Marking
        it with setdefault - which is what this did - makes it remember only
        the first, and then a track of that first net may legally run through
        it although it is 0.025 mm from the second net's pad. That was 42 of
        the board's clearance errors, and the same mistake in the via map was
        another 47.

        A cell wanted by two nets belongs to neither: nobody may put copper
        there, because whoever does is too close to the other one. Copper
        that is already a pad of some net is the exception, in `fixo`: it is
        real metal, its own net has to be able to reach it, and two pads too
        close together is a placement problem that the DRC reports on its own.
        """
        if respeitar_fixo and k in self.fixo:
            return
        d = mapa.get(k)
        if d is None:
            mapa[k] = rede
        elif d != rede:
            mapa[k] = BLOQUEADO

    def _ret(self, mapa: dict, camada: int, x: float, y: float,
             hw: float, hh: float, rede: str,
             respeitar_fixo: bool = True) -> None:
        """Reserve the cells of an axis-aligned rectangle, inflated already.

        A cell is a place a track CENTRE may sit, and the rectangle is
        already inflated by the clearance plus half a track. So the cells to
        reserve are exactly those whose centre falls inside it: a centre
        0.075 mm outside the boundary is 0.075 mm MORE than the clearance
        away from the copper, and it is legal.

        This used floor and ceil on the corners, reserving every cell the
        rectangle so much as touched - up to a full step, 0.15 mm, beyond
        the boundary on each side. A 0.365 mm ring became a 0.5 mm one, and
        at 0.5 mm of pad pitch the rings of two neighbouring pads met ON TOP
        of every pad, where two nets' rings make a cell blocked for all.
        Nothing could leave a fine-pitch row: not the USB pair from the
        receptacle, not CC1 from the ESD diode, not the module's pins from
        the top. The DRC, which measures real copper, never saw a problem,
        because there was none: the only thing too close was the model.
        """
        eps = 1e-6
        ix0 = int(math.floor((x - hw) / PASSO + eps)) + 1
        iy0 = int(math.floor((y - hh) / PASSO + eps)) + 1
        ix1 = int(math.ceil((x + hw) / PASSO - eps)) - 1
        iy1 = int(math.ceil((y + hh) / PASSO - eps)) - 1
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                self._por(mapa, (camada, ix, iy), rede, respeitar_fixo)

    def _disco(self, mapa: dict, camada: int, x: float, y: float,
               raio: float, rede: str, respeitar_fixo: bool = True) -> None:
        n = int(math.ceil(raio / PASSO))
        cx, cy = self.cel(x, y)
        for dx in range(-n, n + 1):
            for dy in range(-n, n + 1):
                if math.hypot(dx * PASSO, dy * PASSO) > raio + 1e-9:
                    continue
                self._por(mapa, (camada, cx + dx, cy + dy), rede,
                          respeitar_fixo)

    def cobre(self, camadas, x: float, y: float, hw: float, hh: float,
              rede: str) -> None:
        """A pad's own copper: real metal, and its net has to reach it."""
        for c in camadas:
            ix0, iy0 = self.cel(x - hw, y - hh)
            ix1, iy1 = self.cel(x + hw, y + hh)
            for ix in range(ix0, ix1 + 1):
                for iy in range(iy0, iy1 + 1):
                    k = (c, ix, iy)
                    self.t[k] = rede
                    self.fixo.add(k)

    def pad(self, camadas, x: float, y: float, hw: float, hh: float,
            rede: str, folga: float = FOLGA) -> None:
        """A pad, as the rectangle it is, into both maps.

        A track has to keep FOLGA from the copper, so its centre line has to
        keep FOLGA + half a track. A via has to keep FOLGA from the copper
        with its 0.45 mm pad, AND 0.2 mm from the copper with its 0.25 mm
        hole; the first is the larger, so it decides.
        """
        # The ring is the NARROWEST track's, and a wider one makes up the
        # difference when it looks (extra_de / _disco_off). Reserving the
        # widest track here instead was tried on 2026-09-27 and it shuts
        # every escape out of a 0,5 mm pitch package: 88 connections fell
        # to 67. What the DRC needed was margin in the LOOK, not in the
        # mark, and _disco_off carries it.
        for c in camadas:
            self._ret(self.t, c, x, y, hw + folga + LARGURA / 2,
                      hh + folga + LARGURA / 2, rede)
        # a via goes through: a pad on any layer blocks it on all of them
        # respeitar_fixo=False on purpose. In the track map that exemption
        # is what lets a net reach its own pad; in the VIA map there is no
        # such thing to protect, and keeping it there let a ground stub drop
        # a via 0.075 mm from a neighbouring pad - eleven of the board's
        # nineteen clearance errors.
        for c in range(NC):
            self._ret(self.v, c, x, y, hw + FOLGA_MASCARA + VIA_D / 2,
                      hh + FOLGA_MASCARA + VIA_D / 2, rede,
                      respeitar_fixo=False)

    def trilha(self, camada: int, p0, p1, larg: float, rede: str,
               folga: float = FOLGA) -> None:
        """Reserve a run of track on both maps, along its whole length.

        `folga` exists because the clearance is not one number for the whole
        board: the USB class asks 0.2 mm where the default class asks 0.127.
        Reserving the default around a USB track is how the router put a
        sensor line 0.11 mm from a USB via and the DRC found it afterwards.
        """
        n = max(1, int(math.ceil(math.hypot(p1[0] - p0[0], p1[1] - p0[1]) / (PASSO / 2))))
        rt = larg / 2 + folga + LARGURA / 2
        rv = larg / 2 + folga + VIA_D / 2
        for i in range(n + 1):
            f = i / n
            x = p0[0] + (p1[0] - p0[0]) * f
            y = p0[1] + (p1[1] - p0[1]) * f
            self._disco(self.t, camada, x, y, rt, rede)
            for c in range(NC):
                self._disco(self.v, c, x, y, rv, rede, respeitar_fixo=False)

    def via(self, x: float, y: float, rede: str,
            folga: float = FOLGA) -> None:
        """Reserve a via: its pad on both layers, and room for the next one.

        Two vias have to keep their holes 0.2 mm apart and their pads 0.2 mm
        apart; the pads decide, so the next via centre stays VIA_D + FOLGA
        away. `folga` follows the net's class, for the same reason it does
        in trilha().
        """
        self.postas.add(self.cel(x, y))
        for c in range(NC):
            self._disco(self.t, c, x, y, VIA_D / 2 + folga + LARGURA / 2, rede)
            self._disco(self.v, c, x, y, VIA_D + folga, rede,
                        respeitar_fixo=False)

    def bloquear(self, camada: int, x: float, y: float, raio: float) -> None:
        self._disco(self.t, camada, x, y, raio, BLOQUEADO)
        self._disco(self.v, camada, x, y, raio + VIA_D / 2, BLOQUEADO)

    # -- asking -----------------------------------------------------------
    def livre_t(self, k, rede: str, off=((0, 0),)) -> bool:
        c, ix, iy = k
        t = self.t
        for dx, dy in off:
            d = t.get((c, ix + dx, iy + dy))
            if d is not None and d != rede:
                return False
        return True

    def furo(self, x: float, y: float, raio: float) -> None:
        """A plated through hole: no via may land in it, whatever its net.

        `pad()` marks a pad with its NET, and cabe_via() lets a via of that
        same net stand on it - which is right for a surface pad (the via
        ties it to the plane) and wrong for a hole: two holes in the same
        place is one hole, and the DRC calls it `hole_near_hole` at
        0,000 mm. Eight ground stitches landed inside the bridge's five
        plated holes on 2026-09-27.
        """
        for c in range(NC):
            self._disco(self.v, c, x, y, raio, BLOQUEADO, respeitar_fixo=False)

    def cabe_via(self, ix: int, iy: int, rede: str) -> bool:
        # Two vias of the SAME net still may not share a hole. The ground
        # stubs put five pairs of vias exactly on top of each other, at
        # 0.000 mm, because the via map only ever asked about other nets.
        n = int(math.ceil((VIA_D + FOLGA) / PASSO))
        for dx in range(-n, n + 1):
            for dy in range(-n, n + 1):
                if math.hypot(dx * PASSO, dy * PASSO) > VIA_D + FOLGA:
                    continue
                if (ix + dx, iy + dy) in self.postas:
                    return False
        for c in range(NC):
            d = self.v.get((c, ix, iy))
            if d is not None and d != rede:
                return False
        return True

    def corredor_livre(self, camada: int, p0, p1, rede: str) -> bool:
        """Can this net's track run from p0 to p1 without touching anyone
        else? Sampled at half a grid step, which is what the marking uses, so
        what passes here is what gets reserved there."""
        off = _disco_off(extra_de(rede))
        d = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        n = max(1, int(math.ceil(d / (PASSO / 2))))
        for i in range(n + 1):
            f = i / n
            x = p0[0] + (p1[0] - p0[0]) * f
            y = p0[1] + (p1[1] - p0[1]) * f
            cx, cy = self.cel(x, y)
            if not self.dentro(cx, cy):
                return False
            if not self.livre_t((camada, cx, cy), rede, off):
                return False
        return True


def pads_da_placa(arv) -> tuple[list[tuple], dict[str, list[tuple]], dict]:
    """Every pad: (net, layer index or -1 for through, x, y, half w, half h).

    The half sizes are the rotated ones: a 1.5 x 0.7 pad turned 90 degrees is
    0.7 x 1.5, and marking it the other way round is how a track ends up
    running through a pad it should have gone around.
    """
    todos = []
    por_rede: dict[str, list[tuple]] = {}
    # the bounding box of the pads of each footprint, looked up by the
    # position of any one of them: that box is the pad field the neck-down
    # has to cover, and no wider neighbourhood is
    caixa_fp: dict[tuple[float, float], tuple] = {}
    for f in fp_load.kids(arv, "footprint"):
        at = fp_load.kid(f, "at")
        fx, fy = float(at[1]), float(at[2])
        ang = math.radians(float(at[3])) if len(at) > 3 else 0.0
        meus: list[tuple[float, float, float, float]] = []
        for p in fp_load.kids(f, "pad"):
            a = fp_load.kid(p, "at")
            px, py = float(a[1]), float(a[2])
            gx = fx + px * math.cos(ang) + py * math.sin(ang)
            gy = fy - px * math.sin(ang) + py * math.cos(ang)
            s = fp_load.kid(p, "size")
            sw, sh = float(s[1]) / 2.0, float(s[2]) / 2.0
            # A custom pad's (size ...) is only its anchor: the copper lives
            # in (primitives ...) and can be much bigger. On the TPS7A02 in
            # X2SON the anchor is 0.148 mm square and the copper reaches
            # 0.46 x 0.31, so reading the size alone leaves 0.16 mm of real
            # copper unguarded and a track may cross it.
            if len(p) > 3 and p[3] == "custom":
                prim = fp_load.kid(p, "primitives")
                if prim:
                    px_, py_ = [], []
                    for g in prim:
                        if not isinstance(g, list):
                            continue
                        pts = fp_load.kid(g, "pts")
                        if pts:
                            for q in fp_load.kids(pts, "xy"):
                                px_.append(float(q[1]))
                                py_.append(float(q[2]))
                        for tag in ("start", "end", "center", "mid"):
                            q = fp_load.kid(g, tag)
                            if q:
                                px_.append(float(q[1]))
                                py_.append(float(q[2]))
                    if px_:
                        sw = max(sw, abs(min(px_)), abs(max(px_)))
                        sh = max(sh, abs(min(py_)), abs(max(py_)))
            # the pad angle in a board file is already the final one
            pa = math.radians(float(a[3])) if len(a) > 3 else 0.0
            hw = abs(sw * math.cos(pa)) + abs(sh * math.sin(pa))
            hh = abs(sw * math.sin(pa)) + abs(sh * math.cos(pa))
            camadas = list(fp_load.kid(p, "layers")[1:])
            # "connect" is an SMD pad without paste - the Tag-Connect's six -
            # and it lives on ONE face like any SMD pad. Treating everything
            # that is not "smd" as through-hole let the search end a track
            # on In2.Cu or B.Cu at a pad that only exists on F.Cu: three
            # dangling tracks on SWDIO, SWDCLK and MOD_RESET, counted as
            # routed while the pin had no copper reaching it.
            passante = (any(c.startswith("*") for c in camadas)
                        or p[2] in ("thru_hole", "np_thru_hole"))
            if passante:
                idx = -1
            elif any("B.Cu" in c for c in camadas):
                idx = I_BCU
            else:
                idx = 0
            rede = fp_load.kid(p, "net")
            nome = rede[2] if rede else ""
            item = (nome, idx, gx, gy, hw, hh)
            todos.append(item)
            meus.append((gx, gy, hw, hh))
            if nome:
                por_rede.setdefault(nome, []).append(item)
        if meus:
            b = (min(q[0] - q[2] for q in meus), min(q[1] - q[3] for q in meus),
                 max(q[0] + q[2] for q in meus), max(q[1] + q[3] for q in meus))
            for gx, gy, _hw, _hh in meus:
                caixa_fp[(round(gx, 4), round(gy, 4))] = b
    return todos, por_rede, caixa_fp


def a_estrela(g: Grade, rede: str, inicio: tuple[int, int, int],
              alvos: set[tuple[int, int, int]], folga: int = 200,
              orcamento: int = ORCAMENTO, so_camada: int | None = None,
              perto_de: frozenset | None = None,
              campos: list | None = None, larg_estreita: float = LARGURA):
    """Shortest path from one cell to any target, changing layer at a cost.

    `campos` are the pad fields of this net, in CELL coordinates. Inside one
    of them the track is allowed to be as narrow as the pad it is leaving,
    and the search has to know that or it never finds the way out: emitir()
    already cut the neck, but it only ever saw paths the search had already
    found. With one width for the whole search the USB pair at its calculated
    0.352 mm could not leave a 0.5 mm pitch receptacle at all, and came out
    with zero segments.
    """
    if inicio in alvos:
        return [inicio]
    off = _disco_off(extra_de(rede))
    # The neck is as wide as the PAD, not as the narrowest track on the
    # board, and the search has to look for exactly the width that emitir()
    # will draw. Assuming the minimum put USB_DM 0.335 mm from KEY_R where
    # the geometry needs 0.378.
    # Inside a pad field the search looks at the cell ALONE (2026-09-27,
    # the power meter's board). The marking already keeps FOLGA plus half
    # a track from every other net's copper, and _disco_off() rounds any
    # extra up to a whole grid step, so a neck 0,025 mm wider than LARGURA,
    # or a class 0,07 mm stricter, asked the cells 0,15 mm above and below
    # a 0,25 mm QFN pad to be free - and on a 0,5 mm pitch those cells are
    # the neighbour's clearance. No pin of the nPM1100, the ADS1220 or the
    # TVS could START a net, whatever the board's length (VSYS, VBUS, VBAT
    # and USB_DP with veio=1: the search never left the pad). The neck is
    # LARGURA wide on such pads (larg_pad below), and the DRC (RT1) is the
    # judge of what comes out.
    del larg_estreita
    off_estreito = ((0, 0),)

    def _off(ix: int, iy: int):
        if campos:
            for x0, y0, x1, y1 in campos:
                if x0 <= ix <= x1 and y0 <= iy <= y1:
                    return off_estreito
        return off
    tx = sum(t[1] for t in alvos) / len(alvos)
    ty = sum(t[2] for t in alvos) / len(alvos)
    bx0 = min([inicio[1]] + [t[1] for t in alvos]) - folga
    bx1 = max([inicio[1]] + [t[1] for t in alvos]) + folga
    by0 = min([inicio[2]] + [t[2] for t in alvos]) - folga
    by1 = max([inicio[2]] + [t[2] for t in alvos]) + folga

    fila = [(abs(inicio[1] - tx) + abs(inicio[2] - ty), 0.0, inicio, None)]
    veio: dict[tuple, tuple | None] = {}
    melhor = {inicio: 0.0}
    while fila:
        _f, custo, atual, ant = heapq.heappop(fila)
        if atual in veio:
            continue
        veio[atual] = ant
        if len(veio) > orcamento:
            return None
        if atual in alvos:
            caminho = [atual]
            while veio[caminho[-1]] is not None:
                caminho.append(veio[caminho[-1]])
            caminho.reverse()
            return caminho
        c, ix, iy = atual
        # Eight ways, not four. With four the router can only turn 90
        # degrees, so EVERY corner on the board was a right angle - which is
        # not how a board is drawn: the discontinuity is real on a fast edge
        # and on an impedance-controlled line, and it makes a longer track
        # besides. A diagonal step may not cut a corner: both of the
        # orthogonal cells it passes between have to be free too, or the
        # track would squeeze through a gap that does not exist.
        vizinhos = [(c, ix + 1, iy), (c, ix - 1, iy), (c, ix, iy + 1),
                    (c, ix, iy - 1)]
        for dx, dy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            if g.livre_t((c, ix + dx, iy), rede, _off(ix + dx, iy)) and                     g.livre_t((c, ix, iy + dy), rede, _off(ix, iy + dy)):
                vizinhos.append((c, ix + dx, iy + dy))
        if so_camada is None:
            vizinhos += [(k, ix, iy) for k in range(NC) if k != c]
        for v in vizinhos:
            if v in veio:
                continue
            if not (bx0 <= v[1] <= bx1 and by0 <= v[2] <= by1):
                continue
            if not g.dentro(v[1], v[2]) or                     not g.livre_t(v, rede, _off(v[1], v[2])):
                continue
            if v[0] != c:
                # a layer change is a via: every via here goes right through
                # the board, so it needs room for its pad on EVERY layer and
                # for its hole
                if not g.cabe_via(v[1], v[2], rede):
                    continue
                if not g.livre_t((v[0], ix, iy), rede, _off(ix, iy)):
                    continue
            if v[0] != c:
                passo = CUSTO_VIA
            elif v[1] != ix and v[2] != iy:
                # A diagonal step costs more than its length. At the true
                # 1.414 the shortest path IS the diagonal, so the router
                # drew long diagonals straight across the board, cutting
                # through everyone else's channels - which is legal, passes
                # every rule, and is not how a board is drawn. At 1.9 a
                # diagonal only pays for itself where it replaces a corner,
                # which is exactly what a 45 degree chamfer is for.
                # 2.2, and the number is not taste. A diagonal run of n steps
                # costs 2.2n and covers n cells each way; the L that replaces
                # it costs 2n plus 0.7 for its one corner. At 1.9 the diagonal
                # still won for any n - which is why the board came out with
                # 45 degree lines crossing it end to end - and at 2.2 the L
                # wins from about four steps up, while a single diagonal still
                # beats a corner (2.2 against 2.7). That is a chamfer, which
                # is what 45 degrees is for.
                passo = 2.2
            else:
                passo = 1.0
            if ant is not None and v[0] == c and ant[0] == c:
                d1 = (ix - ant[1], iy - ant[2])
                d2 = (v[1] - ix, v[2] - iy)
                if d1 != d2:
                    # Half a turn costs less than a whole one. Charging the
                    # same for both is what killed the chamfer: cutting a
                    # corner is orth -> diag -> orth, which is TWO turns, so
                    # at 0.7 each it cost 3.6 against the square corner's
                    # 2.7 and the router squared every corner on the board.
                    # A 45 degree turn is 0.2, and the chamfer comes to 2.6.
                    reto = (d1[0] == 0) != (d2[0] == 0) or                            (d1[1] == 0) != (d2[1] == 0)
                    passo += CUSTO_CURVA if (d1[0] and d1[1]) ==                         (d2[0] and d2[1]) and reto else CUSTO_CURVA_45
            if perto_de is not None and (v[1], v[2]) in perto_de:
                # the second half of a differential pair: running beside its
                # partner is cheaper than going its own way, so the two stay
                # together instead of crossing the board separately
                passo *= 0.35
            novo = custo + passo
            if novo < melhor.get(v, float("inf")):
                melhor[v] = novo
                h = abs(v[1] - tx) + abs(v[2] - ty)
                heapq.heappush(fila, (novo + h, novo, v, atual))
    return None




def base(arv, todos):
    """The grid with everything that never moves: pads, hole, keep-outs."""
    g = Grade()
    # The pad's own copper FIRST, and all of it, not only its centre cell:
    # that is what a track of its own net may stand on, and it is what makes
    # a 0.5 mm pitch connector escapable along the pad instead of between
    # two of them - which does not fit anyway, 0.15 of track and twice 0.127
    # of clearance needing 0.404 where a 0.5 pitch with 0.3 pads leaves 0.2.
    for nome, idx, x, y, hw, hh in todos:
        g.cobre(range(NC) if idx < 0 else (idx,), x - MP.ORIGEM[0],
                y - MP.ORIGEM[1], hw, hh, nome or BLOQUEADO)
    # and only then the clearance around it
    for nome, idx, x, y, hw, hh in todos:
        # A pad with no net and no copper on either face is a HOLE - the
        # three locating holes of the Tag-Connect - and the rule for
        # copper next to a hole is 0.2 mm, not the 0.127 of copper to
        # copper. Reserving the smaller one put SWDIO 0.175 mm from a
        # Tag-Connect hole, which the DRC reports as a hole clearance
        # error.
        #
        # A SURFACE pad with no net is not a hole, though: it is a
        # no-connect ball, and it is copper like any other pad. Measured
        # on 2026-09-27: giving the BMA400's two no-connects the hole
        # distance walled in the pad between them, which carries INT1, and
        # the router reported that pin as the one connection on the board
        # with no path at all.
        e_furo = idx < 0 and not nome
        g.pad(range(NC) if idx < 0 else (idx,), x - MP.ORIGEM[0],
              y - MP.ORIGEM[1], hw, hh, nome or BLOQUEADO,
              folga=FOLGA_FURO if e_furo else FOLGA)
        if idx < 0:
            # it pierces the board: keep every via out of the hole itself
            # and out of the hole-to-hole distance around it
            g.furo(x - MP.ORIGEM[0], y - MP.ORIGEM[1],
                   max(hw, hh) + VIA_D / 2 + FOLGA_FURO)

    # EVERY mounting hole, not the first: when the second one came in on
    # 2026-09-25 this still read FUROS_DOC[0], and a track or a via was free
    # to run through the hole at (4.0; 75.75)
    for fx, fy in M.FUROS_DOC:
        for c in range(NC):
            g.bloquear(c, fx, fy, M.M2_DRILL_UNVERIFIED / 2 + FOLGA + 0.3)
    # No via inside a switching node's no-plane area: a ground via there
    # brings the plane straight back under the node, which is exactly what
    # section 13 of the AEM10900 datasheet asks to remove. The node's own
    # track is welcome; its ground is not.
    # These zones are not in the zone table: they are computed from where the
    # parts ended up, so they come off the board itself.
    folga_v = int(math.ceil((VIA_D / 2 + FOLGA) / PASSO))
    for z in fp_load.kids(arv, "zone"):
        nm = fp_load.kid(z, "name")
        if not nm or not nm[1].startswith("SEM_PLANO"):
            continue
        pts = fp_load.kid(fp_load.kid(z, "polygon"), "pts")
        xs = [float(q[1]) - MP.ORIGEM[0] for q in fp_load.kids(pts, "xy")]
        ys = [float(q[2]) - MP.ORIGEM[1] for q in fp_load.kids(pts, "xy")]
        ix0, iy0 = g.cel(min(xs), min(ys))
        ix1, iy1 = g.cel(max(xs), max(ys))
        for c in range(NC):
            for ix in range(ix0 - folga_v, ix1 + folga_v + 1):
                for iy in range(iy0 - folga_v, iy1 + folga_v + 1):
                    g.v[(c, ix, iy)] = BLOQUEADO

    for nome, (x0, y0, x1, y1), _c, _s in M.ZONES:
        if nome not in MP.KEEPOUTS:
            continue
        ix0, iy0 = g.cel(x0, y0)
        ix1, iy1 = g.cel(x1, y1)
        for c in range(NC):
            for ix in range(ix0, ix1 + 1):
                for iy in range(iy0, iy1 + 1):
                    g.t[(c, ix, iy)] = BLOQUEADO
        # a via is 0.45 mm wide: its CENTRE has to stay that much further out
        # of a keep-out, or the pad of it reaches inside
        folga_v = int(math.ceil((VIA_D / 2 + FOLGA) / PASSO))
        for c in range(NC):
            for ix in range(ix0 - folga_v, ix1 + folga_v + 1):
                for iy in range(iy0 - folga_v, iy1 + folga_v + 1):
                    g.v[(c, ix, iy)] = BLOQUEADO
    return g


def terra(g: Grade, por_rede, segmentos, vias, falhas, todos=()) -> int:
    # `todos` and not `por_rede`: a pad with NO net is absent from
    # por_rede, and a pad with no net is exactly the one a ground stub
    # touched on 2026-09-28 (U102's pad 2). Copper is copper.
    """A stub from every ground pad to a via down into the plane.

    The stub is axis-aligned and the whole of it is checked before anything
    is drawn: a stub that leaves on a free bearing but crosses a neighbour's
    pad on the way is exactly the sort of short a plane is supposed to save
    you from.
    """
    n_gnd = 0
    for _nome, idx, x, y, hw, hh in por_rede.get("GND", []):
        if idx < 0:
            continue                     # a through pad already meets the plane
        bx, by = x - MP.ORIGEM[0], y - MP.ORIGEM[1]
        posto = None
        # the four sides first, then the corners: a via straight out of the
        # pad gives the shortest loop, and the diagonal is what saves the
        # pads in the crowded corner by the power supply
        dirs = ((0, 1), (0, -1), (1, 0), (-1, 0),
                (0.7071, 0.7071), (0.7071, -0.7071),
                (-0.7071, 0.7071), (-0.7071, -0.7071))
        for extra in (0.0, 0.2, 0.45, 0.8, 1.3, 2.0):
            for dx, dy in dirs:
                meia = math.hypot(hw * dx, hh * dy)
                d = meia + VIA_D / 2 + FOLGA + extra
                vx, vy = bx + dx * d, by + dy * d
                c0, c1 = g.cel(vx, vy)
                if not g.dentro(c0, c1) or not g.cabe_via(c0, c1, "GND"):
                    continue
                # the grid was asked about the CELL, so the via goes on the
                # cell. Checking at (c0, c1) and then drilling at (vx, vy)
                # puts the hole up to half a step off what was checked, and
                # half a step is 0.075 mm - thirteen of the board's fourteen
                # clearance errors were exactly that.
                vx, vy = g.pos(c0, c1)
                if not g.corredor_livre(idx, (bx, by), (vx, vy), "GND"):
                    continue
                posto = (vx, vy)
                break
            if posto:
                break
        if posto is None:
            falhas.append(f"GND: sem lugar para a via ao lado de ({bx:.1f}; {by:.1f})")
            continue
        # the stub necks down to the pad, exactly like a signal track: a
        # 0.4 mm stub leaving a 0.3 mm ground pad sticks out on both sides and
        # lands inside the neighbouring pad's clearance
        larg_g = max(LARGURA, min(LARGURA_ALIM, 2 * hw, 2 * hh))
        # And then MEASURE it, against the pads, before drawing it. The grid
        # said this corridor was free and it was not: on 2026-09-28 three of
        # these stubs came out 0,102, 0,010 and 0,000 mm from a neighbour's
        # pad, the last one touching a pad of U102 that has no net - a short
        # and a solder mask bridge. A stub that fails here is dropped: the
        # pad it serves reaches the plane through the pour of its own face,
        # which is what the 39 pads without a via of their own already do.
        perto = False
        for nome_p, idx_p, px, py, hw_p, hh_p in todos:
            if nome_p == "GND" or (idx_p >= 0 and idx_p != idx):
                continue
            qx, qy = px - MP.ORIGEM[0], py - MP.ORIGEM[1]
            if _dist_seg_ret((bx, by), posto, qx, qy, hw_p, hh_p) <                     larg_g / 2 + max(FOLGA, folga_de(nome_p or "GND")):
                perto = True
                break
        if perto:
            falhas.append(f"GND: a via ao lado de ({bx:.1f}; {by:.1f}) passaria perto "
                          "demais de um pad vizinho; o pad fica pelo plano da face")
            continue
        vias.append((posto[0], posto[1], "GND"))
        segmentos.append(((bx, by), posto, idx, "GND", larg_g))
        g.trilha(idx, (bx, by), posto, larg_g, "GND")
        g.via(posto[0], posto[1], "GND")
        n_gnd += 1
    return n_gnd


def costurar(g: Grade, vias: list) -> int:
    """Stitch the edge of the board with ground vias.

    The two ground planes are only one plane electrically if they are tied
    together often enough. The number is not taste: at 2.44 GHz a tenth of a
    wavelength in FR-4 is about 6.1 mm, and a gap larger than that turns the
    space between the planes into a slot that radiates. So: a via every
    3 mm around the edge, wherever one fits, and the measured worst gap goes
    into the dry-run.

    It runs LAST, on whatever room the signals left, so a stitch never costs
    a connection.
    """
    passo = 2.5                   # 3,0 deixou um vao de 6,1 mm depois que
                                 # a costura do RF tomou lugares de via
    # in from the edge: the via's own copper has to keep BORDA_COBRE too, and
    # dentro() only ever looked at the cell centre
    d = BORDA_COBRE + VIA_D / 2 + 0.45
    pontos: list[tuple[float, float]] = []
    n_x = max(2, int((M.W - 2 * d) / passo) + 1)
    n_y = max(2, int((M.H - 2 * d) / passo) + 1)
    for i in range(n_x):
        x = d + (M.W - 2 * d) * i / (n_x - 1)
        pontos += [(x, d), (x, M.H - d)]
    for i in range(n_y):
        y = d + (M.H - 2 * d) * i / (n_y - 1)
        pontos += [(d, y), (M.W - d, y)]
    postas = 0
    for x, y in pontos:
        achou = None
        for r in (0.0, 0.3, 0.6, 0.9, 1.2):
            for ang in range(0, 360, 45) if r else (0,):
                vx = x + r * math.cos(math.radians(ang))
                vy = y + r * math.sin(math.radians(ang))
                c0, c1 = g.cel(vx, vy)
                if not g.dentro(c0, c1) or not g.cabe_via(c0, c1, "GND"):
                    continue
                # the whole via pad inside the copper edge, not just its centre
                folga_borda = min(vx, vy, M.W - vx, M.H - vy)
                if folga_borda < BORDA_COBRE + VIA_D / 2:
                    continue
                canto = M.RADIUS_DRAWING
                longe = True
                for cx_, cy_ in ((canto, canto), (M.W - canto, canto),
                                 (canto, M.H - canto), (M.W - canto, M.H - canto)):
                    dentro_x = vx < canto if cx_ < M.W / 2 else vx > M.W - canto
                    dentro_y = vy < canto if cy_ < M.H / 2 else vy > M.H - canto
                    if dentro_x and dentro_y and math.hypot(vx - cx_, vy - cy_) >                             canto - BORDA_COBRE - VIA_D / 2:
                        longe = False
                if not longe:
                    continue
                achou = g.pos(c0, c1)
                break
            if achou:
                break
        if achou is None:
            continue
        vias.append((achou[0], achou[1], "GND"))
        g.via(achou[0], achou[1], "GND")
        postas += 1
    return postas


def costurar_area(g: Grade, vias: list) -> int:
    """Ground vias on a grid across the whole board, not only its edge.

    Edge stitching keeps the boundary of the two surface pours from becoming
    a radiating slot. It does nothing for the MIDDLE: a patch of top pour
    that reaches the internal plane only through a via 20 mm away is not
    ground at 2.4 GHz, it is an antenna with a long feed. What ties the three
    layers into one ground is a mesh, and a mesh is what this lays down.

    The pitch is the same number the edge uses and for the same reason: a
    tenth of a wavelength in FR-4 at 2.44 GHz is 6.1 mm, so anything under
    that keeps every point of pour within half a stitch of a via. 4.0 mm
    leaves margin without spending the room the signals need.

    It runs LAST, after the signals and after the edge, on whatever is free,
    so a stitch never costs a connection.
    """
    passo = 4.0
    d = BORDA_COBRE + VIA_D / 2 + 0.45
    postas = 0
    n_x = max(2, int((M.W - 2 * d) / passo) + 1)
    n_y = max(2, int((M.H - 2 * d) / passo) + 1)
    for i in range(n_x):
        for j in range(n_y):
            x = d + (M.W - 2 * d) * i / (n_x - 1)
            y = d + (M.H - 2 * d) * j / (n_y - 1)
            achou = None
            for r in (0.0, 0.4, 0.8, 1.3):
                for ang in range(0, 360, 45) if r else (0,):
                    vx = x + r * math.cos(math.radians(ang))
                    vy = y + r * math.sin(math.radians(ang))
                    c0, c1 = g.cel(vx, vy)
                    if not g.dentro(c0, c1) or not g.cabe_via(c0, c1, "GND"):
                        continue
                    if min(vx, vy, M.W - vx, M.H - vy) < BORDA_COBRE + VIA_D / 2:
                        continue
                    achou = g.pos(c0, c1)
                    break
                if achou:
                    break
            if achou is None:
                continue
            vias.append((achou[0], achou[1], "GND"))
            g.via(achou[0], achou[1], "GND")
            postas += 1
    return postas


def costurar_rf(g: Grade, vias: list, segmentos: list) -> int:
    """Ground vias along both sides of the RF line.

    A coplanar waveguide is only coplanar if the ground beside it is really
    ground: both datasheets ask for the pour around the RF line to be filled
    with ground vias, and 4.4 of the u-blox manual adds that a stub in the
    ground plane has to end in a via or it picks up interference. They go
    every 2 mm, which is well under a twentieth of a wavelength at 1.6 GHz.
    """
    postas = 0
    for (p0, p1, c, rede, _w) in list(segmentos):
        if rede not in NAO_ROTEAR:
            continue
        comp = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        n = max(1, int(comp / 2.0))
        ux, uy = (p1[0] - p0[0]) / (comp or 1), (p1[1] - p0[1]) / (comp or 1)
        nx, ny = -uy, ux                 # perpendicular
        for i in range(n + 1):
            f = i / n
            bx = p0[0] + (p1[0] - p0[0]) * f
            by = p0[1] + (p1[1] - p0[1]) * f
            for lado in (-1, 1):
                for d in (FOLGA_CPWG, FOLGA_CPWG + 0.4, FOLGA_CPWG + 0.8):
                    vx, vy = bx + nx * d * lado, by + ny * d * lado
                    c0, c1 = g.cel(vx, vy)
                    if not g.dentro(c0, c1) or not g.cabe_via(c0, c1, "GND"):
                        continue
                    pos = g.pos(c0, c1)
                    vias.append((pos[0], pos[1], "GND"))
                    g.via(pos[0], pos[1], "GND")
                    postas += 1
                    break
    return postas


def _mao(g: Grade, segmentos: list, camada: int, pts, larg: float,
         rede: str, folga: float, cells: set) -> None:
    """A hand-drawn run: emit it, reserve it, and remember its cells."""
    for p0, p1 in zip(pts, pts[1:]):
        segmentos.append((p0, p1, camada, rede, larg))
        g.trilha(camada, p0, p1, larg, rede, folga)
        n = max(2, int(math.hypot(p1[0] - p0[0], p1[1] - p0[1]) / (PASSO / 2)))
        for k in range(n + 1):
            f = k / n
            cells.add((camada, *g.cel(p0[0] + (p1[0] - p0[0]) * f,
                                      p0[1] + (p1[1] - p0[1]) * f)))






def podar_soltas(segmentos: list, vias: list, todos: list) -> int:
    """Drop every track end that touches nothing, until none is left.

    A hand-drawn stub the search did not use, a run the neck logic cut at a
    field boundary and never continued - each leaves a copper spur with a
    free end, and the DRC lists every one of them as a dangling track. An
    end is anchored when it sits on a pad of its own net (allowing the
    track's own half width, as KiCad does), on a via of its own net, or on
    the end of another segment of the net on the same layer. Anything else
    is pruned, and pruning one can free the next, so it goes round again.
    """
    orx, ory = MP.ORIGEM
    pads_por_rede: dict[str, list] = {}
    for nome, idx, x, y, hw, hh in todos:
        if nome:
            pads_por_rede.setdefault(nome, []).append((idx, x - orx, y - ory, hw, hh))
    removidos = 0
    while True:
        pontas: dict[tuple, int] = {}
        for p0, p1, cam, rede, _w in segmentos:
            for p in (p0, p1):
                k = (cam, rede, round(p[0], 3), round(p[1], 3))
                pontas[k] = pontas.get(k, 0) + 1
        vias_rede: dict[str, set] = {}
        for vx, vy, rede in vias:
            vias_rede.setdefault(rede, set()).add((round(vx, 3), round(vy, 3)))

        por_camada: dict[tuple, list] = {}
        for p0, p1, cam, rede, w in segmentos:
            por_camada.setdefault((cam, rede), []).append((p0, p1, w))

        def sobre_segmento(p, cam, rede, w):
            """The end lies ON another segment of the net, not just at its end.

            The search may finish on any cell the net already owns, and that
            is often the middle of an earlier run - the second pad of a
            three-pad net joins the first run wherever it is nearest. That
            is a T-junction, and KiCad reads it as connected. Counting only
            endpoints pruned whole routes: the USB D- run to the module went
            piece by piece, from the module back to the tie it had joined.
            """
            for q0, q1, w2 in por_camada.get((cam, rede), ()):
                dx, dy = q1[0] - q0[0], q1[1] - q0[1]
                comp2 = dx * dx + dy * dy
                if comp2 < 1e-12:
                    continue
                tt = ((p[0] - q0[0]) * dx + (p[1] - q0[1]) * dy) / comp2
                if tt < -1e-6 or tt > 1 + 1e-6:
                    continue
                px, py = q0[0] + tt * dx, q0[1] + tt * dy
                if math.hypot(p[0] - px, p[1] - py) <= (w + w2) / 2 + 0.02:
                    # the segment's own ends are not "another" segment
                    if (abs(p[0] - q0[0]) < 1e-6 and abs(p[1] - q0[1]) < 1e-6) or                             (abs(p[0] - q1[0]) < 1e-6 and abs(p[1] - q1[1]) < 1e-6):
                        continue
                    return True
            return False

        def ancorada(p, cam, rede, w):
            if pontas.get((cam, rede, round(p[0], 3), round(p[1], 3)), 0) > 1:
                return True
            if (round(p[0], 3), round(p[1], 3)) in vias_rede.get(rede, ()):
                return True
            for idx, x, y, hw, hh in pads_por_rede.get(rede, ()):
                if idx >= 0 and idx != cam:
                    continue
                # the track's end cap only has to overlap the pad, as KiCad
                # judges it, hence the half width and a little slack
                if (abs(p[0] - x) <= hw + w / 2 + 0.02
                        and abs(p[1] - y) <= hh + w / 2 + 0.02):
                    return True
            return sobre_segmento(p, cam, rede, w)

        solto = None
        for i, (p0, p1, cam, rede, w) in enumerate(segmentos):
            if not ancorada(p0, cam, rede, w) or not ancorada(p1, cam, rede, w):
                solto = i
                break
        if solto is None:
            return removidos
        p0, p1, cam, rede, w = segmentos[solto]
        if removidos < 8:
            print(f"    podado {rede} {CAMADAS[cam]} "
                  f"({p0[0]:.2f};{p0[1]:.2f})->({p1[0]:.2f};{p1[1]:.2f})")
        del segmentos[solto]
        removidos += 1


def uma_passagem(arv, numeros, todos, por_rede, caixa_fp, prioridade,
                 mantidos=None, so_estas=None):
    """One routing attempt with a given order. Returns what came out."""
    g = base(arv, todos)
    segmentos: list[tuple] = []
    vias: list[tuple] = []
    falhas: list[str] = []
    falharam: list[str] = []
    # Tracks and vias carried over from an earlier pass: already drawn, so
    # they are marked on the grid and kept in the output, and their nets
    # are not routed again (see main()).
    if mantidos:
        seg_m, via_m = mantidos
        for x_m, y_m, rede_m in via_m:
            vias.append((x_m, y_m, rede_m))
            g.via(x_m, y_m, rede_m, folga_de(rede_m))
        for p0_m, p1_m, cam_m, rede_m, w_m in seg_m:
            segmentos.append((p0_m, p1_m, cam_m, rede_m, w_m))
            g.trilha(cam_m, p0_m, p1_m, w_m, rede_m, folga_de(rede_m))

    def emitir(caminho_cel, rede, larg, larg_pad=None, campo=None):
        i = 0
        while i < len(caminho_cel) - 1:
            a = caminho_cel[i]
            j = i + 1
            if caminho_cel[j][0] != a[0]:
                x, y = g.pos(a[1], a[2])
                vias.append((x, y, rede))
                g.via(x, y, rede, folga_de(rede))
                i = j
                continue
            d = (caminho_cel[j][1] - a[1], caminho_cel[j][2] - a[2])
            while j + 1 < len(caminho_cel) and caminho_cel[j + 1][0] == a[0] and \
                    (caminho_cel[j + 1][1] - caminho_cel[j][1],
                     caminho_cel[j + 1][2] - caminho_cel[j][2]) == d:
                j += 1
            # The neck lasts while the track is still inside the part's
            # pad field, not just for the first run: a 0.4 mm track two
            # segments out of a 0.4 mm pitch QFN is still between its pads.
            # Necking the whole net instead took VBAT, which carries the
            # 800 mA charging current, to 0.2 mm end to end, because the fuel
            # gauge's WLP bump is 0.2 mm wide.
            #
            # And the neck ends where the FIELD ends, not where the straight
            # run ends. Deciding one width for the whole run by its first
            # point is how VBAT left the MAX17262 at 0.2 mm and stayed there
            # for 9.9 mm across the board, 0.02 mm under what IPC-2221 asks
            # for its 800 mA: the run happened to begin inside the field. So
            # the run is cut at the boundary and each piece gets its own
            # width, which is what a person draws by hand.
            def no_campo(k: int) -> bool:
                if larg_pad is None or campo is None:
                    return False
                px, py = g.pos(caminho_cel[k][1], caminho_cel[k][2])
                return (campo[0] <= px <= campo[2] and
                        campo[1] <= py <= campo[3])

            k0 = i
            while k0 < j:
                # a piece is narrow when EITHER of its ends is in the field,
                # so the wide copper never starts inside it
                estreito = no_campo(k0) or no_campo(k0 + 1)
                k1 = k0 + 1
                while k1 < j and (no_campo(k1) or no_campo(k1 + 1)) == estreito:
                    k1 += 1
                p0 = g.pos(caminho_cel[k0][1], caminho_cel[k0][2])
                p1 = g.pos(caminho_cel[k1][1], caminho_cel[k1][2])
                w = larg_pad if estreito else larg
                segmentos.append((p0, p1, a[0], rede, w))
                g.trilha(a[0], p0, p1, w, rede, folga_de(rede))
                k0 = k1
            i = j

    # The hand-drawn USB stretch goes in BEFORE the ground stitching: its
    # vias are placed, not searched, and a stitching via already sitting
    # there is not checked against them. One landed 0.10 mm from a tie via.
    # no hand-drawn stretch on this board: the magnetic connector's pads
    # are 2,5 mm apart and the maze routes the pair from them
    pre_ligados: dict = {}
    n_gnd = (0 if so_estas is not None
             else terra(g, por_rede, segmentos, vias, falhas, todos))

    def alcance(r: str) -> float:
        xs = [q[2] for q in por_rede[r]]
        ys = [q[3] for q in por_rede[r]]
        return (max(xs) - min(xs)) + (max(ys) - min(ys))

    ordem = [r for r in PRIMEIRO if r in por_rede]
    # A pass may be told which nets go first: the ones the previous pass
    # could not draw. They then take the empty board before the nets that
    # boxed them in, which is the cheapest form of rip-up there is, and the
    # power meter's board needed it (2026-09-27: 14 connections short after
    # two orderings, most of them boxed in by tracks drawn earlier).
    if isinstance(prioridade, tuple):
        ordem += [r for r in prioridade[1] if r in por_rede and r not in ordem]
        prioridade = "curtas"
    resto = [r for r in por_rede
             if r not in ordem and r not in NAO_ROTEAR and r != "GND"]
    resto.sort(key=alcance, reverse=(prioridade != "curtas"))

    n_ok = 0
    fechou = [False]
    caminhos: dict[str, frozenset] = {}
    # The RF lines go FIRST, not last: their width and their path are the
    # only ones that are not negotiable, and they have to leave the
    # receiver's pin before anything else takes the room. The area under the
    # receiver is closed to foreign signals right after they are drawn.
    rf = [r for r in NAO_ROTEAR if r in por_rede]
    for rede in rf + ordem + resto:
        if so_estas is not None and rede not in so_estas:
            continue
        pads = por_rede[rede]
        if len(pads) < 2:
            continue
        # A track may not be wider than the pad it lands on. A 0.4 mm
        # power track ending on a 0.25 mm pad sticks out on both sides and
        # lands 0.100 mm from the neighbouring pad - seven of the nineteen
        # clearance errors. This is the neck-down a person draws by hand.
        #
        # Per CONNECTION, not per net. Taking the narrowest pad of the whole
        # net shrank all of VBAT_SYS to 0.2 mm because the TPS7A02's input
        # pad is that wide - and that pad draws microamps while the rest of
        # the rail carries the 800 mA charging current.
        estreitos = [min(2 * q[4], 2 * q[5]) for q in pads]
        if rede in PAR:
            # Numa fileira de 0,5 mm de passo quem decide a largura NAO e a
            # propria ilha, e a vizinha: entre duas ilhas de 0,30 mm a 0,5 de
            # passo sobram 0,20 mm, e a classe USB pede 0,20 de isolamento de
            # cada lado. Com a grade de 0,15 mm a trilha ainda sai ate 0,075
            # fora do centro da ilha. Medindo so a propria ilha, a trilha de
            # 0,207 passou a 0,1965 mm da vizinha e a DRC acusou tres vezes.
            estreitos = [min(e, LARGURA) for e in estreitos]
        # How far the neck has to last: out of the pad field of the package
        # the pad belongs to, and not one millimetre further. Measuring it as
        # a radius over everything within 6 mm - which is what this did - made
        # the field 4.9 mm wide around the fuel gauge, because the parts
        # crowded around it counted as if they were its own pins, and VBAT
        # left it at 0.2 mm and stayed there for 4.35 mm against the 0.22 mm
        # IPC-2221 asks of its 800 mA. The field is the box of the FOOTPRINT's
        # own pads, plus the clearance the neck exists to respect.
        campos = [caixa_fp.get((round(q[2], 4), round(q[3], 4))) for q in pads]
        celulas = []
        for _n, idx, x, y, _hw, _hh in pads:
            c0, c1 = g.cel(x - MP.ORIGEM[0], y - MP.ORIGEM[1])
            celulas.append({(c, c0, c1)
                            for c in (range(NC) if idx < 0 else (idx,))})
        # Quando a rede ja tem uma ligacao feita a mao - o par do USB-C -,
        # a busca tem de PARTIR dela, nao juntar as duas coisas num monte so:
        # semear `feito` com a ligacao feita e com a primeira ilha da lista
        # diz que as duas estao ligadas entre si, e elas nao estao. Foi assim
        # que o par ficou com as amarracoes desenhadas e nenhuma trilha ate o
        # modulo, enquanto o contador dizia que so faltava uma ligacao.
        pre = pre_ligados.get(rede, set())
        if pre:
            for i_pre, cl in enumerate(celulas):
                if cl & pre:
                    if i_pre:
                        celulas.insert(0, celulas.pop(i_pre))
                        estreitos.insert(0, estreitos.pop(i_pre))
                        campos.insert(0, campos.pop(i_pre))
                    break
        feito = set(celulas[0]) | pre
        if rede not in NAO_ROTEAR and not fechou[0]:
            fechou[0] = True
        # Nearest first, not list order (2026-09-27, the power meter's
        # board): a net with a pad at each end of a 60 mm board and a
        # pull-up in the middle was searched from one END to the OTHER
        # first, through the crowded middle, and failed there. What a
        # person draws is a spanning tree that grows from the closest pad
        # every time, and that is what this picks: at each step the pad
        # whose cell is closest to what is already connected.
        restantes = list(range(1, len(celulas)))

        def _dist_ao_feito(k: int) -> int:
            cl = next(iter(celulas[k]))
            return min((abs(cl[1] - c[1]) + abs(cl[2] - c[2]) for c in feito),
                       default=0)

        while restantes:
            restantes.sort(key=_dist_ao_feito)
            k = restantes.pop(0)
            alvo = celulas[k]
            if alvo & feito:
                continue
            larg = largura(rede)
            # Half a grid step under the pad's width, not the pad's width:
            # the pad's centre is not on the grid, so the neck runs up to
            # 0.075 mm off it and a track as wide as the pad pokes out on
            # one side. On the fuel gauge's 0.2 mm WLP bumps a 0.2 mm neck
            # stuck out 0.05 mm and sat 0.125 mm from the next bump's track.
            # a whole step under the pad's width, not half: a 0,25 mm pad
            # gets a 0,15 neck, which is what its 0,5 mm pitch has room for
            larg_pad = max(LARGURA, min(larg, estreitos[k] - PASSO))
            q = pads[k]
            # the pad field in grid coordinates; without one, the pad's own
            # copper, which still has to be escaped
            b = campos[k] or (q[2] - q[4], q[3] - q[5], q[2] + q[4], q[3] + q[5])
            # The neck lasts until the track is clear of the NEIGHBOURS'
            # clearance, not only of its own pad: a neighbour's ring reaches
            # FOLGA plus half a track beyond its copper, and the grid adds a
            # step. With the field ending at FOLGA, the first cell outside
            # it still sat inside the ring of the pad next door, the wide
            # track could not stand there, and every power pin of the
            # nPM1100 died 0,2 mm out of its pad (veio=14, 2026-09-27).
            campo = (b[0] - MP.ORIGEM[0] - EXTRA_CAMPO, b[1] - MP.ORIGEM[1] - EXTRA_CAMPO,
                     b[2] - MP.ORIGEM[0] + EXTRA_CAMPO, b[3] - MP.ORIGEM[1] + EXTRA_CAMPO)
            # the RF line stays on the front layer: a via in the middle of
            # it is a stub, and 7.2 of the module datasheet forbids stubs by
            # name. The second track of a pair is pulled towards the first.
            # every pad field of this net, in cell coordinates: inside one
            # of them the escape may be as narrow as the pad
            campos_cel = []
            for q in pads:
                b = caixa_fp.get((round(q[2], 4), round(q[3], 4)))
                if not b:
                    b = (q[2] - q[4], q[3] - q[5], q[2] + q[4], q[3] + q[5])
                a0 = g.cel(b[0] - MP.ORIGEM[0] - EXTRA_CAMPO, b[1] - MP.ORIGEM[1] - EXTRA_CAMPO)
                a1 = g.cel(b[2] - MP.ORIGEM[0] + EXTRA_CAMPO, b[3] - MP.ORIGEM[1] + EXTRA_CAMPO)
                campos_cel.append((a0[0], a0[1], a1[0], a1[1]))
            so_camada = 0 if rede in SO_FRENTE else None
            perto = None
            if rede == PAR[1] and PAR[0] in caminhos:
                perto = caminhos[PAR[0]]
            p = None
            tentativas = [(so_camada, 100), (so_camada, 350)]
            if so_camada is not None:
                tentativas.append((None, 350))
            for camada_t, folga in tentativas:
                p = a_estrela(g, rede, next(iter(alvo)), feito, folga,
                              so_camada=camada_t, perto_de=perto,
                              campos=campos_cel, larg_estreita=larg_pad)
                if p:
                    if camada_t is None and so_camada is not None:
                        print(f"    {rede} nao coube so na frente: trocou de "
                              "camada (full speed, ver SO_FRENTE)", flush=True)
                    break
            if p is None:
                c0 = next(iter(alvo))
                c1 = next(iter(feito))
                falhas.append(f"{rede}: nao roteou de ({c0[1] * PASSO:.1f}; "
                              f"{c0[2] * PASSO:.1f}) ate o que ja esta ligado "
                              f"(por exemplo ({c1[1] * PASSO:.1f}; {c1[2] * PASSO:.1f}))")
                falharam.append(rede)
                continue
            emitir(p, rede, larg, larg_pad, campo)
            feito |= set(p)
            n_ok += 1
            if rede == PAR[0]:
                # the cells its partner should hug: the path itself and one
                # step around it, which at a 0.15 mm grid is the pair pitch
                viz = set()
                for _c, cx_, cy_ in p:
                    for dx in (-2, -1, 0, 1, 2):
                        for dy in (-2, -1, 0, 1, 2):
                            viz.add((cx_ + dx, cy_ + dy))
                caminhos[rede] = frozenset(viz)

    n_cost = costurar(g, vias)
    n_cost += costurar_rf(g, vias, segmentos)
    n_malha = costurar_area(g, vias)
    # PMETER_SEM_PODA=1 keeps every spur, to tell a pruning bug from a
    # routing one: if the unconnected count falls with the pruning off, the
    # pruning is eating copper that a net still needs. Measured on
    # 2026-09-27, when the router reported success and the DRC listed 16
    # unconnected items across GND, ERR_N, CHG_N, USB_DM, VBAT and 3V0_MOD,
    # at distances of 13 to 36 mm: too far to be a stub that fell short.
    if os.environ.get("PMETER_SEM_PODA") != "1":
        podar_soltas(segmentos, vias, todos)
    return segmentos, vias, falhas, falharam, n_gnd, n_ok, n_cost, n_malha


def encostar_nos_pads(segmentos: list, vias: list, todos: list,
                      limite: float = 1.5) -> int:
    """Join a track that stopped a step short of its own pad.

    Both routing stages work on a grid, and a grid cell centre is not a pad
    centre: a path can finish on the cell beside the pad and leave a gap of
    a tenth of a millimetre that KiCad counts as an open connection, which
    is what the leftover 0,15 and 0,21 mm stubs in the report were. This
    walks every pad that nothing of its net touches, looks for the nearest
    track end of that same net on a layer the pad lives on, and, if it is
    closer than `limite`, draws the piece between them at that track's own
    width. Anything farther is a route that is genuinely missing, and it is
    left alone rather than bridged blind across other copper.
    """
    orx, ory = MP.ORIGEM
    por_camada: dict = {}
    for i, (p0, p1, cam, rede, w) in enumerate(segmentos):
        por_camada.setdefault((cam, rede), []).append((p0, p1, w))
    vias_rede: dict = {}
    for vx, vy, rede in vias:
        vias_rede.setdefault(rede, []).append((vx, vy))

    def tocado(x, y, hw, hh, idx, rede) -> bool:
        for vx, vy in vias_rede.get(rede, ()):
            if abs(vx - x) <= hw + 0.25 and abs(vy - y) <= hh + 0.25:
                return True
        for (cam, r), lista in por_camada.items():
            if r != rede or (idx >= 0 and idx != cam):
                continue
            for q0, q1, w in lista:
                for p in (q0, q1):
                    if abs(p[0] - x) <= hw + w / 2 + 0.02 and \
                            abs(p[1] - y) <= hh + w / 2 + 0.02:
                        return True
                # or the run passes over the pad
                if min(q0[0], q1[0]) - w / 2 <= x <= max(q0[0], q1[0]) + w / 2 and \
                        min(q0[1], q1[1]) - w / 2 <= y <= max(q0[1], q1[1]) + w / 2:
                    return True
        return False

    postos = 0
    for nome, idx, px, py, hw, hh in todos:
        if not nome:
            continue
        x, y = px - orx, py - ory
        if tocado(x, y, hw, hh, idx, nome):
            continue
        # the nearest end of this net, on ANY layer: a pad on the back with
        # its track on the front is the other half of this problem, and it
        # needs a via, not a stub
        melhor = None
        for (cam, r), lista in por_camada.items():
            if r != nome:
                continue
            mesma = (idx < 0 or idx == cam)
            for q0, q1, w in lista:
                for p in (q0, q1):
                    d = math.hypot(p[0] - x, p[1] - y)
                    # a stub on the pad's own layer is always preferred to
                    # one that costs a via
                    custo = d + (0.0 if mesma else 0.6)
                    if d <= limite and (melhor is None or custo < melhor[0]):
                        melhor = (custo, d, p, cam, w, mesma)
        if melhor is None:
            continue
        _c, _d, p, cam, w, mesma = melhor
        # narrow, so the piece added at the end does not eat the clearance
        # the netclass asks for: four clearance errors came from drawing it
        # at the run's own width (2026-09-28)
        wl = max(LARGURA, min(w, 2.0 * min(hw, hh) - 0.05))
        destino = cam if mesma else (idx if idx >= 0 else cam)
        if not mesma:
            # A via is not free: it goes through every layer, so it has to
            # clear every net on all of them. Measured on 2026-09-28: placed
            # blind, one GND via landed on the module's 3V0_MOD pad and cost
            # two shorts, a hole clearance and a mask bridge - four new DRC
            # errors for a connection it did not even close. If there is no
            # room, the pad stays open and says so, which is the truth.
            if not via_cabe_aqui(p[0], p[1], nome, segmentos, vias, todos):
                continue
            vias.append((p[0], p[1], nome))
            vias_rede.setdefault(nome, []).append((p[0], p[1]))
        segmentos.append((p, (x, y), destino, nome, wl))
        por_camada.setdefault((destino, nome), []).append((p, (x, y), wl))
        postos += 1
    return postos


def via_cabe_aqui(vx: float, vy: float, rede: str,
                  segmentos: list, vias: list, todos: list) -> bool:
    """Is there room for a via of `rede` at (vx, vy), in board coordinates?

    Measured against the copper that is already there, not against the grid:
    this runs after both routing stages, when the grid no longer describes
    the board.
    """
    orx, ory = MP.ORIGEM

    def perto(dist: float, minimo: float) -> bool:
        return dist < minimo - 1e-9

    for p0, p1, _cam, r, w in segmentos:
        if r == rede:
            continue
        f = max(folga_de(rede), folga_de(r))
        if perto(_dist_ponto_seg(vx, vy, p0, p1), VIA_D / 2 + f + w / 2):
            return False
    for wx, wy, r in vias:
        if r == rede:
            # its own net still may not have two vias in the same hole:
            # KiCad calls that "holes co-located" and the fabricator drills
            # the same spot twice (seen on 2026-09-28)
            if perto(math.hypot(wx - vx, wy - vy), VIA_D * 0.5):
                return False
            continue
        f = max(folga_de(rede), folga_de(r))
        if perto(math.hypot(wx - vx, wy - vy), VIA_D + f):
            return False
    for nome, _idx, px, py, hw, hh in todos:
        if not nome or nome == rede:
            continue
        f = max(folga_de(rede), folga_de(nome))
        dx = max(0.0, abs(px - orx - vx) - hw)
        dy = max(0.0, abs(py - ory - vy) - hh)
        if perto(math.hypot(dx, dy), VIA_D / 2 + max(f, FOLGA_FURO)):
            return False
    return True


def _dist_ponto_seg(x: float, y: float, p0, p1) -> float:
    ax, ay = p0
    bx, by = p1
    dx, dy = bx - ax, by - ay
    n = dx * dx + dy * dy
    t = 0.0 if n <= 1e-12 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / n))
    return math.hypot(x - (ax + t * dx), y - (ay + t * dy))


def emitir_caminhos(arv, todos, por_rede, caminhos_por_rede):
    """Turn the negotiated stage's paths into segments and vias.

    The same neck rule the sequential emitter uses: a piece of track that
    is inside a footprint's pad field is drawn as narrow as that pad can
    take, and the rest at the net's own width.
    """
    g = base(arv, todos)
    segmentos: list[tuple] = []
    vias: list[tuple] = []
    for rede, caminhos in caminhos_por_rede.items():
        for caminho, larg, larg_pad, campos_cel in caminhos:
            def no_campo(k: int) -> bool:
                c, ix, iy = caminho[k]
                for x0, y0, x1, y1 in campos_cel:
                    if x0 <= ix <= x1 and y0 <= iy <= y1:
                        return True
                return False

            i = 0
            while i < len(caminho) - 1:
                a = caminho[i]
                j = i + 1
                if caminho[j][0] != a[0]:
                    x, y = g.pos(a[1], a[2])
                    vias.append((x, y, rede))
                    g.via(x, y, rede, folga_de(rede))
                    i = j
                    continue
                d = (caminho[j][1] - a[1], caminho[j][2] - a[2])
                while j + 1 < len(caminho) and caminho[j + 1][0] == a[0] and \
                        (caminho[j + 1][1] - caminho[j][1],
                         caminho[j + 1][2] - caminho[j][2]) == d:
                    j += 1
                k0 = i
                while k0 < j:
                    estreito = no_campo(k0) or no_campo(k0 + 1)
                    k1 = k0 + 1
                    while k1 < j and (no_campo(k1) or no_campo(k1 + 1)) == estreito:
                        k1 += 1
                    p0 = g.pos(caminho[k0][1], caminho[k0][2])
                    p1 = g.pos(caminho[k1][1], caminho[k1][2])
                    w = larg_pad if estreito else larg
                    segmentos.append((p0, p1, a[0], rede, w))
                    g.trilha(a[0], p0, p1, w, rede, folga_de(rede))
                    k0 = k1
                i = j
    return g, segmentos, vias


def conferir(segmentos, vias, todos=()) -> list[str]:
    """Does what came out actually keep its distance? Ask the geometry.

    The grid is a model of the board and a model can be wrong. This checks
    the RESULT by distance between real shapes: every pair of segments on the
    same layer, every pair of vias, and - since 2026-09-28 - every segment
    against every PAD of another net.

    That last one was the hole. Without it this printed "0 pairs too close"
    on a board where a ground stub ran 0,0000 mm from a pad of U102 that has
    no net at all: it touched it, and the DRC found the short and a solder
    mask bridge with it. A check that measures tracks against tracks and
    calls the board clean is worse than no check, because it is believed.
    """
    def dist_seg(a0, a1, b0, b1) -> float:
        def pp(p, q0, q1):
            vx, vy = q1[0] - q0[0], q1[1] - q0[1]
            L = vx * vx + vy * vy
            t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - q0[0]) * vx +
                                                      (p[1] - q0[1]) * vy) / L))
            return math.hypot(p[0] - (q0[0] + t * vx), p[1] - (q0[1] + t * vy))
        d1 = (a1[0] - a0[0], a1[1] - a0[1])
        d2 = (b1[0] - b0[0], b1[1] - b0[1])
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) > 1e-12:
            t = ((b0[0] - a0[0]) * d2[1] - (b0[1] - a0[1]) * d2[0]) / den
            u = ((b0[0] - a0[0]) * d1[1] - (b0[1] - a0[1]) * d1[0]) / den
            if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
                return 0.0
        return min(pp(a0, b0, b1), pp(a1, b0, b1), pp(b0, a0, a1), pp(b1, a0, a1))

    problemas: list[str] = []
    for i, (p0, p1, c, r, w) in enumerate(segmentos):
        for (q0, q1, c2, r2, w2) in segmentos[i + 1:]:
            if c != c2 or r == r2:
                continue
            exigido = w / 2 + w2 / 2 + max(folga_de(r), folga_de(r2)) - 0.01
            d = dist_seg(p0, p1, q0, q1)
            if d < exigido:
                problemas.append(
                    f"{r} e {r2} na camada {CAMADAS[c]} a {d:.3f} mm, "
                    f"pedem {exigido:.3f} (em {p0[0]:.1f}; {p0[1]:.1f})")
    for i, (x, y, r) in enumerate(vias):
        for (x2, y2, r2) in vias[i + 1:]:
            d = math.hypot(x - x2, y - y2)
            if d < VIA_D + 0.12:
                problemas.append(f"via {r} e via {r2} a {d:.3f} mm "
                                 f"(em {x:.1f}; {y:.1f})")
    # tracks against PADS. A pad with no net is not exempt: copper is copper,
    # and touching one shorts whatever the part connects internally.
    orx, ory = MP.ORIGEM
    for (p0, p1, c, r, w) in segmentos:
        for nome, idx, px, py, hw, hh in todos:
            if nome == r or (idx >= 0 and idx != c):
                continue
            qx, qy = px - orx, py - ory
            d = _dist_seg_ret(p0, p1, qx, qy, hw, hh)
            exigido = w / 2 + max(folga_de(r), folga_de(nome or r)) - 0.01
            if d < exigido:
                problemas.append(
                    f"{r} na camada {CAMADAS[c]} a {d:.3f} mm do pad "
                    f"{nome or '<sem rede>'} em ({qx:.1f}; {qy:.1f}), "
                    f"pede {exigido:.3f}")
    return problemas


def _dist_seg_ret(p0, p1, cx, cy, hw, hh) -> float:
    """Distance from a segment's centre line to an axis-aligned pad."""
    def dentro(x, y):
        return abs(x - cx) <= hw and abs(y - cy) <= hh

    def pp(px, py, ax, ay, bx, by):
        vx, vy = bx - ax, by - ay
        L = vx * vx + vy * vy
        k = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / L))
        return math.hypot(px - (ax + k * vx), py - (ay + k * vy))

    if dentro(*p0) or dentro(*p1):
        return 0.0
    lados = ((cx - hw, cy - hh, cx + hw, cy - hh), (cx + hw, cy - hh, cx + hw, cy + hh),
             (cx + hw, cy + hh, cx - hw, cy + hh), (cx - hw, cy + hh, cx - hw, cy - hh))
    melhor = float("inf")
    for ax, ay, bx, by in lados:
        melhor = min(melhor, pp(p0[0], p0[1], ax, ay, bx, by),
                     pp(p1[0], p1[1], ax, ay, bx, by),
                     pp(ax, ay, p0[0], p0[1], p1[0], p1[1]),
                     pp(bx, by, p0[0], p0[1], p1[0], p1[1]))
    return melhor


def escrever(caminho, texto, numeros, segmentos, vias) -> None:
    linhas = []
    for (p0, p1, c, rede, larg) in segmentos:
        a = MP.P_(*p0)
        b = MP.P_(*p1)
        if abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9:
            continue
        linhas.append(
            f'\t(segment\n\t\t(start {a[0]:.4f} {a[1]:.4f})\n'
            f'\t\t(end {b[0]:.4f} {b[1]:.4f})\n\t\t(width {larg})\n'
            f'\t\t(layer "{CAMADAS[c]}")\n\t\t(net {numeros.get(rede, 0)})\n'
            f'\t\t(uuid "{MP.uid("seg", a, b, c)}")\n\t)')
    for (x, y, rede) in vias:
        q = MP.P_(x, y)
        linhas.append(
            f'\t(via\n\t\t(at {q[0]:.4f} {q[1]:.4f})\n\t\t(size {VIA_D})\n'
            f'\t\t(drill {VIA_FURO})\n\t\t(layers "F.Cu" "B.Cu")\n'
            f'\t\t(net {numeros.get(rede, 0)})\n'
            f'\t\t(uuid "{MP.uid("via", q)}")\n\t)')
    texto = sem_cobre(texto)
    fim = texto.rstrip()
    assert fim.endswith(")")
    caminho.write_text(fim[:-1].rstrip() + "\n" + "\n".join(linhas) + "\n)\n",
                       encoding="utf-8", newline="\n")


def sem_cobre(texto: str) -> str:
    """Take out the tracks and vias a previous run left behind.

    Without this, routing appends: run it twice and the board carries both
    sets of tracks, every net on top of itself and across its neighbours.
    That is how a board the router believed had 534 segments reached the file
    with 1576, and why the DRC then reported 206 crossings that the router
    had never drawn. Routing has to be something you can run again.
    """
    saida = []
    i = 0
    n = len(texto)
    while i < n:
        if texto.startswith("(segment", i) or texto.startswith("(via", i):
            d, j = 0, i
            while j < n:
                if texto[j] == '"':
                    j += 1
                    while j < n and texto[j] != '"':
                        j += 2 if texto[j] == "\\" else 1
                elif texto[j] == "(":
                    d += 1
                elif texto[j] == ")":
                    d -= 1
                    if d == 0:
                        break
                j += 1
            # and the indentation of the line it started on
            while saida and saida[-1] in " \t":
                saida.pop()
            i = j + 1
            while i < n and texto[i] in " \t\r\n":
                i += 1
            saida.append("\n")
            continue
        saida.append(texto[i])
        i += 1
    return "".join(saida)


def main() -> int:
    caminho = HERE / "pmeter.kicad_pcb"
    texto = caminho.read_text(encoding="utf-8")
    arv = fp_load.parse(texto)
    # the numbers the FILE uses: nets.py may have moved on since make_pcb
    numeros = fp_load.redes_da_placa(arv)
    todos, por_rede, caixa_fp = pads_da_placa(arv)

    # Several passes. Whatever failed goes to the front of the next one,
    # so a run that could not find a way through gets the empty board next
    # time. A pass costs about a minute; the board settles in three or four.
    melhor = None

    def so_ligacoes(fal):
        return [f for f in fal if not f.startswith("GND: sem lugar para a via")]

    for nome in ("compridas", "curtas"):
        r = uma_passagem(arv, numeros, todos, por_rede, caixa_fp, nome)
        segmentos, vias, falhas, falharam, n_gnd, n_ok, n_cost, n_malha = r
        print(f"  ordem {nome} primeiro: {n_ok} ligacoes, {len(falhas)} falhas",
              flush=True)
        if melhor is None or len(so_ligacoes(falhas)) < len(so_ligacoes(melhor[2])):
            melhor = r
        if not so_ligacoes(falhas):
            break
    # Full re-routes with the failed nets in front: one of these can move
    # a channel that a net drawn earlier had taken, which the incremental
    # pass below cannot.
    for k in range(4):
        pendentes = list(dict.fromkeys(melhor[3]))
        if not pendentes:
            break
        r = uma_passagem(arv, numeros, todos, por_rede, caixa_fp,
                         ("falhas", pendentes))
        n_antes = len(so_ligacoes(melhor[2]))
        n_depois = len(so_ligacoes(r[2]))
        print(f"  passagem {k + 3}, {len(pendentes)} redes na frente: "
              f"{r[5]} ligacoes, {n_depois} falhas", flush=True)
        if n_depois < n_antes:
            melhor = r
        else:
            break

    # And then incremental rip-up: freeze every net that closed and hand
    # the ones that did not the whole of the rest of the board. A full
    # re-route throws away ninety good connections to chase twenty, and
    # they take their channels back in a different arrangement; this keeps
    # what worked.
    for k in range(12):
        pendentes = set(melhor[3])
        if not pendentes:
            break
        seg_bons = [s for s in melhor[0] if s[3] not in pendentes]
        via_boas = [v for v in melhor[1] if v[2] not in pendentes]
        r = uma_passagem(arv, numeros, todos, por_rede, caixa_fp,
                         ("falhas", sorted(pendentes)),
                         mantidos=(seg_bons, via_boas), so_estas=pendentes)
        gnd_falhas = [f for f in melhor[2]
                      if f.startswith("GND: sem lugar para a via")]
        combinado = (list(r[0]), list(r[1]), list(r[2]) + gnd_falhas, r[3],
                     melhor[4], r[5], r[6], r[7])
        n_antes = len(so_ligacoes(melhor[2]))
        n_depois = len(so_ligacoes(combinado[2]))
        print(f"  incremental {k + 1}, {len(pendentes)} redes soltas: "
              f"{n_depois} falhas", flush=True)
        if n_depois < n_antes:
            melhor = combinado
        else:
            break
    segmentos, vias, falhas, _f, n_gnd, n_ok, n_cost, n_malha = melhor

    # Everything above draws one net at a time, and on this board that
    # plateaus about twenty connections short whatever the order, the board
    # size or the rip-up strategy (route_neg.py opens with the measurements).
    # So when something is still open, hand the whole board to the
    # negotiated-congestion router and keep its answer if it is better.
    if so_ligacoes(falhas):
        print("  congestao negociada (route_neg):", flush=True)
        import route_neg as RN
        ordem_redes = [r for r in por_rede
                       if r not in NAO_ROTEAR and r != "GND"]
        ordem_redes.sort(key=lambda r: (max(q[2] for q in por_rede[r])
                                        - min(q[2] for q in por_rede[r]))
                                       + (max(q[3] for q in por_rede[r])
                                          - min(q[3] for q in por_rede[r])))
        import sys as _sys
        # what this stage will NOT route has to be an obstacle for it, or the
        # copper carried over below lands on top of its tracks
        fora = set(ordem_redes)
        pre_seg = [s for s in segmentos if s[3] not in fora]
        pre_via = [v for v in vias if v[2] not in fora]
        saida = RN.rodar(_sys.modules[__name__], arv, numeros, todos,
                         por_rede, caixa_fp, ordem_redes, pre_seg, pre_via)
        if saida is not None:
            (n_disputa, n_falhas), caminhos, falhas_n, n_ok_n, rodadas = saida
            if n_disputa == 0 and n_ok_n > n_ok:
                g2, seg2, via2 = emitir_caminhos(arv, todos, por_rede, caminhos)
                # The negotiated stage routes only the nets it was given, and
                # it was given neither GND nor the ones it failed on. Taking
                # its answer WHOLE threw the sequential copper of everything
                # else away: on 2026-09-27 ERR_N ended with no copper at all
                # while the router reported "95 routed, 0 nets left out", and
                # the DRC found 16 connections open. So what it did not route
                # is carried over, and replayed into its grid first, or the
                # ground vias and the stitching would land on top of it.
                redes_neg = set(caminhos)
                herda_seg = [s for s in segmentos if s[3] not in redes_neg]
                herda_via = [v for v in vias if v[2] not in redes_neg]
                for p0, p1, cam, rede, w in herda_seg:
                    g2.trilha(cam, p0, p1, w, rede, folga_de(rede))
                for vx, vy, rede in herda_via:
                    g2.via(vx, vy, rede, folga_de(rede))
                seg2 = herda_seg + seg2
                via2 = herda_via + via2
                print(f"    herdadas do sequencial: {len(herda_seg)} trilhas e "
                      f"{len(herda_via)} vias de {len(set(s[3] for s in herda_seg))} "
                      "redes que o negociado nao roteou", flush=True)
                falhas2: list[str] = []
                n_gnd2 = terra(g2, por_rede, seg2, via2, falhas2, todos)
                n_cost2 = costurar(g2, via2)
                n_malha2 = costurar_area(g2, via2)
                # nao podar: a poda foi escrita para o roteador sequencial,
                # que desenha uma ligacao de cada vez a partir de um pad. O
                # estagio negociado devolve a arvore inteira de uma rede, e
                # a poda cortava ramos legitimos dela (2026-09-27).
                # And MEASURE the merge before accepting it. The negotiated
                # stage plans on a grid that holds only what it was told
                # about, and it is NOT told about the sequential copper of a
                # net it goes on to fail: that copper is inherited afterwards
                # and can land on top of a track it planned. Measured on
                # 2026-09-28 - 3V0 failed in the negotiated stage, its
                # sequential copper came back, and SPI_MOSI's negotiated
                # track ran 0,000 mm from it. The router SAW it, printed
                # "15 pairs too close", and wrote the board anyway.
                #
                # Detection without a consequence is not a check. If the
                # merge is dirty, the sequential answer is what gets written:
                # fewer connections, but no short.
                ruins2 = conferir(seg2, via2, todos)
                if ruins2:
                    print(f"    o resultado negociado foi RECUSADO: a mistura dele "
                          f"com o cobre sequencial tem {len(ruins2)} pares perto "
                          "demais", flush=True)
                    for r in ruins2[:4]:
                        print(f"      {r}", flush=True)
                    print("    fica o resultado sequencial, que tem menos ligacoes "
                          "e nenhum curto", flush=True)
                else:
                    segmentos, vias = seg2, via2
                    falhas, n_gnd, n_ok = falhas2, n_gnd2, n_ok_n
                    n_cost, n_malha = n_cost2, n_malha2
                    print(f"    fechou em {rodadas} rodadas: {n_ok_n} ligacoes, "
                          "0 celulas disputadas", flush=True)
            else:
                print(f"    nao fechou: {n_falhas} sem caminho, {n_disputa} "
                      f"celulas disputadas depois de {rodadas} rodadas; "
                      "fica o resultado sequencial", flush=True)

    n_enc = encostar_nos_pads(segmentos, vias, todos)
    if n_enc:
        print(f"  {n_enc} pads alcançados por encosto final")

    ruins = conferir(segmentos, vias, todos)
    print(f"  conferencia geometrica: {len(ruins)} pares perto demais")
    for r in ruins[:8]:
        print(f"    {r}")

    escrever(caminho, texto, numeros, segmentos, vias)

    print(f"{len(segmentos)} segmentos, {len(vias)} vias")
    print(f"  {n_gnd} pads de terra com via ao plano, "
          f"{n_cost} vias de costura na borda, {n_malha} na malha da area")
    print(f"  {n_ok} ligacoes roteadas, {len(NAO_ROTEAR)} redes deixadas de fora "
          f"({', '.join(sorted(NAO_ROTEAR))})")
    if falhas:
        # Grouped by net, not the first twelve lines. Printed flat, the list
        # was 134 ground via failures with the signal nets buried behind
        # them - USB_DP and USB_DM came out with zero segments and nothing in
        # the report said so.
        import collections as _c
        por_rede_falha = _c.Counter(f.split(":", 1)[0] for f in falhas)
        print(f"  NAO ROTEADO: {len(falhas)} em {len(por_rede_falha)} redes")
        for rede, n in por_rede_falha.most_common():
            exemplo = next(f for f in falhas if f.startswith(rede + ":"))
            print(f"    {rede}: {n}x  ({exemplo.split(': ', 1)[1]})")
    # A ground pad with no room for a via of its own is not an open
    # circuit: both outer faces carry a ground pour (make_pcb.plano_de_terra)
    # and the pad meets it there; the board's dry run counts how many pads
    # reach the inner plane by via (GN1) and the DRC (RT1) says whether
    # anything is really unconnected. So those are warnings here, and only
    # a connection the maze could not draw fails the run.
    fatais = [f for f in falhas if not f.startswith("GND: sem lugar para a via")]
    if falhas and not fatais:
        print("  (so pads de terra sem via propria: ligados pelo plano da face)")
    return 1 if fatais else 0


if __name__ == "__main__":
    sys.exit(main())
