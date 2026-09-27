#!/usr/bin/env python3
"""Functional blocks of the schematic: who goes with whom, and where.

A readable schematic is drawn the way the circuit works, not the way the
netlist lists it. This module turns each sheet of sheets.FOLHAS into a row
of functional blocks - "USB-C and its protection", "nPM1300: input, charge
and the two bucks", "solar harvesting" - and lays each block out around its
own anchor: the chip or connector in the middle, every passive next to the
pin it serves, on the side that pin faces, and the decoupling in a shelf
underneath. The blocks then go on the page left to right in the order the
signal flows, each inside a dashed rectangle with its title.

What decides membership, in this order:

  1. the BLOCOS table below: the anchors of each block, by hand, because
     "what is a functional block" is a design statement, not a graph
     property;
  2. make_pcb.JUNTO, the table that already says which chip each passive
     belongs to on the board - a decoupling capacitor touches only rails,
     so no netlist walk could ever tell whose it is;
  3. the netlist, rails excluded: a part joins the block of the nearest
     anchor it reaches through signal nets (the divider of the thermal
     cut-off reaches the comparator in one hop, the NTC in two).

Conventions applied, and where they come from: signal flow left to right
and blocks in that order; supplies drawn as power symbols above the pin and
grounds below (KiCad Eeschema manual, "power symbols make global
connections"); a net that leaves its block is a local label, never a wire
across the page (same manual: "local labels connect items located in the
same sheet"; SparkFun, "give a net a name and label it, rather than
routing a wire all over the schematic"); a net that leaves the sheet is a
hierarchical label at the pin; every symbol and wire on the 50 mil grid
(manual: "wires connect ... only if their ends coincide exactly").
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import nets as N
import parts as P
import sheets as S
from sch_lib import GRID, snap

# sheet -> list of (title, anchors). The order is the order on the page.
BLOCOS: dict[str, list[tuple[str, list[str]]]] = {
    "1 Energia": [
        ("Conector magnetico e protecao", ["J101", "D101"]),
        ("nPM1100: carga da celula e buck de 3,0 V", ["U101"]),
        ("Medidor de carga e celula", ["U102", "J102"]),
    ],
    "2 MCU e depuracao": [
        ("Modulo ME54BS13 (nRF54LM20A)", ["U201"]),
        ("Depuracao SWD, console e LED", ["J201", "D201"]),
    ],
    "3 Ponte e conversor": [
        ("Ponte de extensometros", ["J301"]),
        ("Excitacao chaveada TPS22916", ["U302"]),
        ("Conversor ADS1220", ["U301"]),
    ],
    "4 Sensores": [
        ("Acelerometro BMA400", ["U401"]),
        ("Temperatura da ponte TMP117", ["U402"]),
    ],
}

# 5 and not the bike computer's 3 grid steps (2026-09-27, measured on the
# exported PDF by sch_legivel.py): at 3 the tip-to-tip gap is 3,81 mm and a
# reference or a value, 1,27 mm tall and up to 13 characters long, has
# nowhere to go that is not over the neighbour. 81 pairs of text printed on
# top of each other on five sheets.
GAP = 5 * GRID            # pin tip to neighbour's pin tip
# pin tip to the tip of a part standing past the pin's label: the stub of
# two steps plus an eight-character name ("DISP_EXTCOMIN" is longer and
# pushes the part further out by cabe())
GAP_ROTULO = 10 * GRID
FOLGA = 2 * GRID          # between two bodies of the same block (blocks)
# Between two members of one block: two steps between bodies, so that two
# parts on neighbouring lines are staggered along them rather than stacked
# (stacked, the far tip of one landed on the wire of the other); a
# reference or a value keeps clear of everything by a little more than the
# stroke width.
FOLGA_CORPO = FOLGA
FOLGA_TEXTO = 0.4
MARGEM_BLOCO = 6 * GRID   # inside the dashed box, room for power symbols
ENTRE_BLOCOS = 8 * GRID   # between two dashed boxes
# The shelf of stood-up capacitors under the anchors. The pitch holds the
# body (2,54), the reference and a six-character value to its right
# ("100 nF": 6,6 mm) and a step of air before the next plate; between two
# rows there is the rail symbol with its name over the top tips and the
# ground with its name under the bottom ones. The row is up to 110 mm wide
# (eight parts) even under a narrow chip, so that twenty-one parts make
# three rows and the block still fits an A3 next to its neighbours.
PASSO_PRATELEIRA = 10 * GRID
ENTRE_LINHAS_PRATELEIRA = 13 * GRID
LARGURA_PRATELEIRA = 110.0


def _trilho_de_cima(ref: str) -> str:
    """The rail a shelf part hangs from: what its top pin is on, so that
    the parts of one rail stand side by side. Ground is never it."""
    p = P.PARTS[ref]
    redes = []
    for q in p.pins:
        for nome, pinos in N.NETS.items():
            if any(r == ref and (pi == q.name or pi == q.number) for r, pi in pinos):
                redes.append(nome)
    outras = [n for n in redes if n != "GND"]
    return (outras or redes or [""])[0]


@dataclass
class Bloco:
    titulo: str
    ancoras: list[str]
    membros: list[str] = field(default_factory=list)   # anchors first
    # bounding box on the sheet, set by posicionar()
    caixa: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


def _vizinhos_por_sinal(refs: list[str]) -> dict[str, set[str]]:
    """Who touches whom through a net that is not a rail, on this sheet."""
    conjunto = set(refs)
    viz: dict[str, set[str]] = {r: set() for r in refs}
    for nome, pinos in N.NETS.items():
        if nome in S.TRILHOS:
            continue
        na_folha = {r for r, _p in pinos} & conjunto
        for a in na_folha:
            viz[a] |= na_folha - {a}
    return viz


def blocos_da_folha(nome: str, refs: list[str]) -> list[Bloco]:
    """Split the sheet's parts into its functional blocks."""
    from make_pcb import JUNTO
    blocos = [Bloco(t, [a for a in ancs if a in refs])
              for t, ancs in BLOCOS.get(nome, [])]
    blocos = [b for b in blocos if b.ancoras]
    dono: dict[str, Bloco] = {}
    for b in blocos:
        for a in b.ancoras:
            dono[a] = b
    viz = _vizinhos_por_sinal(refs)

    # 1. make_pcb.JUNTO and DECOPLA: the board already knows whose each
    #    passive is - the decoupling table by capacitor, JUNTO by anchor
    from make_pcb import DECOPLA
    for r in refs:
        if r in dono:
            continue
        anc = S.SEGUE.get(r) or DECOPLA.get(r) or JUNTO.get(r)
        # follow the chain (C132 -> U106 -> U301) until an anchor of a block
        vistos = set()
        while anc and anc not in dono and anc not in vistos:
            vistos.add(anc)
            anc = S.SEGUE.get(anc) or DECOPLA.get(anc) or JUNTO.get(anc)
        if anc in dono:
            dono[r] = dono[anc]

    # 2. the netlist: nearest anchor by hops through signal nets
    fila = [(a, 0) for b in blocos for a in b.ancoras]
    dist: dict[str, int] = {a: 0 for a, _d in fila}
    origem: dict[str, Bloco] = {a: dono[a] for a, _d in fila}
    while fila:
        atual, d = fila.pop(0)
        for v in sorted(viz[atual]):
            if v not in dist:
                dist[v] = d + 1
                origem[v] = origem[atual]
                fila.append((v, d + 1))
    for r in refs:
        if r not in dono and r in origem:
            dono[r] = origem[r]

    # 2b. a part that touches only rails, but one of them is a rail of ONE
    #     block - 3V0_GNSS, 3V0_MOD, SD3V0_FLASH, VBCKP - joins the block of
    #     the anchor on that rail. GND and the rails that feed everything say
    #     nothing about membership and are skipped.
    GLOBAIS = {"GND", "3V0", "VSYS", "VBUS", "VBAT"}
    for r in refs:
        if r in dono:
            continue
        contagem: dict[int, int] = {}
        por_id: dict[int, Bloco] = {}
        for nome_n, pinos in N.NETS.items():
            if nome_n not in S.TRILHOS or nome_n in GLOBAIS:
                continue
            if not any(rr == r for rr, _p in pinos):
                continue
            for rr, _p in pinos:
                if rr in dono and rr != r:
                    b = dono[rr]
                    contagem[id(b)] = contagem.get(id(b), 0) + 1
                    por_id[id(b)] = b
        if contagem:
            dono[r] = por_id[max(contagem, key=lambda k: contagem[k])]

    # 3. whatever is left: a block of its own, so nothing disappears
    sobras = [r for r in refs if r not in dono]
    if sobras:
        b = Bloco("Outros", [])
        blocos.append(b)
        for r in sobras:
            dono[r] = b

    for b in blocos:
        b.membros = list(b.ancoras) + sorted(
            (r for r in refs if dono[r] is b and r not in b.ancoras),
            key=lambda r: (dist.get(r, 9), -len(P.PARTS[r].pins), r))
    return blocos


# ------------------------------------------------------------------ layout
def _caixa(ref: str, x: float, y: float) -> tuple[float, float, float, float]:
    """Body box of a part placed at (x, y), pins included."""
    p = P.PARTS[ref]
    old = (p.x, p.y)
    p.x, p.y = x, y
    bx0, by0, bx1, by1 = p.box()
    esq, dire = p.avanco_dos_pinos()
    if p.kicad or not __import__("sch_lib").classe_do_simbolo(p):
        # pins stick out of the body on every side that has them
        pl = p.pin_local()
        for _n, (px, py, _a) in pl.items():
            bx0 = min(bx0, x + px)
            bx1 = max(bx1, x + px)
            by0 = min(by0, y - py)
            by1 = max(by1, y - py)
    else:
        if p.eixo() == "v":
            by0 -= PIN_LEN_V
            by1 += PIN_LEN_V
        else:
            bx0 -= esq
            bx1 += dire
    # ...and the room the reference and the value take, wherever the part
    # writes them (sch_lib.Part.textos): to the right of a stood-up part,
    # above and below a lying one, at the corners of a block. Two parts on
    # neighbouring pins used to print their values on top of each other.
    for tx0, ty0, tx1, ty1 in p.caixas_de_texto():
        bx0, by0 = min(bx0, tx0), min(by0, ty0)
        bx1, by1 = max(bx1, tx1), max(by1, ty1)
    p.x, p.y = old
    return (bx0, by0, bx1, by1)


def _retangulos(ref: str, x: float, y: float) -> list[tuple[float, float, float, float]]:
    """What the part occupies at (x, y), as separate rectangles: the body
    with its pins, then each text. For the overlap test between parts;
    _caixa() is the bounding box of these, for the block's extents."""
    p = P.PARTS[ref]
    old = (p.x, p.y)
    p.x, p.y = x, y
    bx0, by0, bx1, by1 = p.box()
    esq, dire = p.avanco_dos_pinos()
    if p.kicad or not __import__("sch_lib").classe_do_simbolo(p):
        for _n, (px, py, _a) in p.pin_local().items():
            bx0, bx1 = min(bx0, x + px), max(bx1, x + px)
            by0, by1 = min(by0, y - py), max(by1, y - py)
    elif p.eixo() == "v":
        by0 -= PIN_LEN_V
        by1 += PIN_LEN_V
    else:
        bx0 -= esq
        bx1 += dire
    out = [(bx0, by0, bx1, by1)] + list(p.caixas_de_texto())
    p.x, p.y = old
    return out


PIN_LEN_V = 2.54


def _sobrepoe(a, b, folga: float) -> bool:
    return (a[2] + folga > b[0] and b[2] + folga > a[0]
            and a[3] + folga > b[1] and b[3] + folga > a[1])


def _lado_e_ponta(ref: str, pin_name: str) -> tuple[str, tuple[float, float]]:
    """Side a pin faces and its tip, for the part where it currently is."""
    p = P.PARTS[ref]
    num = next(q.number for q in p.pins if q.name == pin_name or q.number == pin_name)
    px, py, ang = p.pin_local()[num]
    lado = {0: "L", 180: "R", 90: "B", 270: "T"}[ang] if p.kicad else \
        next(q.side for q in p.pins if q.number == num)
    if not p.kicad and __import__("sch_lib").classe_do_simbolo(p):
        # the two-terminal symbols: left/right or top/bottom by position
        if p.eixo() == "v":
            lado = "T" if py > 0 else "B"
        else:
            lado = "L" if px < 0 else "R"
    return lado, (p.x + px, p.y - py)


def _pino_compartilhado(ref: str, colocado: str) -> tuple[str, str] | None:
    """(pin of `colocado`, pin of `ref`) on a common signal net, if any."""
    melhor = None
    for nome, pinos in N.NETS.items():
        if nome in S.TRILHOS:
            continue
        de_col = [p for r, p in pinos if r == colocado]
        de_ref = [p for r, p in pinos if r == ref]
        if de_col and de_ref:
            cand = (de_col[0], de_ref[0], len(pinos))
            if melhor is None or cand[2] < melhor[2]:
                melhor = cand
    return None if melhor is None else (melhor[0], melhor[1])


def _colocar_bloco(bloco: Bloco) -> tuple[float, float]:
    """Lay the block out around its anchors, at origin (0, 0). Returns (w, h).

    Coordinates are relative; posicionar() shifts the whole block later.
    """
    caixas: dict[str, tuple[float, float, float, float]] = {}
    # every placed pin tip with its net: a candidate whose tip lands within
    # two grid steps of another net's tip is refused, because the power
    # symbol or the label stub that pin will need has nowhere else to go
    pontas: dict[tuple[float, float], str] = {}

    def rede_do_pino(ref: str, numero: str) -> str:
        p = P.PARTS[ref]
        nome_p = next(q.name for q in p.pins if q.number == numero)
        for nome_n, pinos in N.NETS.items():
            if any(r == ref and (pi == nome_p or pi == numero) for r, pi in pinos):
                return nome_n
        return ""

    def pontas_de(ref: str, x: float, y: float):
        p = P.PARTS[ref]
        old = (p.x, p.y)
        p.x, p.y = x, y
        saida = [((snap(tx), snap(ty)), rede_do_pino(ref, n))
                 for n, (tx, ty) in p.pin_sheet().items()]
        p.x, p.y = old
        return saida

    # what each placed part occupies, as SEPARATE rectangles: the body with
    # its pins, and each text. One bounding box around a connector and its
    # 26 mm value ("Hirose FH12-10S-0.5SH(55)") walled off every row to the
    # right of the connector, and the pull-ups on its lines were pushed past
    # the display.
    retangulos: dict[str, list[tuple[float, float, float, float]]] = {}

    def cabe(ref: str, x: float, y: float) -> bool:
        meus = _retangulos(ref, x, y)
        for r, outros in retangulos.items():
            if r == ref:
                continue
            # bodies may touch (two lying parts on neighbouring pin lines
            # are 2,54 mm apart, like the lines); a text touches nothing -
            # a value under one part printed over the reference of the
            # part on the next line, and FOLGA between the bodies pushed
            # the second part a whole body length down its line instead
            for i, c in enumerate(meus):
                for j, o in enumerate(outros):
                    folga = FOLGA_CORPO if (i == 0 and j == 0) else FOLGA_TEXTO
                    if _sobrepoe(c, o, folga):
                        return False
        for (tx, ty), rede in pontas_de(ref, x, y):
            for (ox, oy), outra in pontas.items():
                if outra != rede and math.hypot(tx - ox, ty - oy) < 2.5 * GRID:
                    return False
        return True

    def por(ref: str, x: float, y: float) -> None:
        p = P.PARTS[ref]
        p.x, p.y = snap(x), snap(y)
        caixas[ref] = _caixa(ref, p.x, p.y)
        retangulos[ref] = _retangulos(ref, p.x, p.y)
        for ponta, rede in pontas_de(ref, p.x, p.y):
            pontas[ponta] = rede

    # the anchors, in a row. Two anchors that talk to each other (the FPC
    # connector and the display it feeds) are set 20 steps apart, room for
    # the series parts on the lines between them and for the wires; the
    # others sit 8 steps apart. At 8 the display's ten lines and their
    # resistors were crammed into 10 mm and three of them did not route.
    def _conversam(a: str, b: str) -> bool:
        for nome_n, pinos in N.NETS.items():
            if nome_n in S.TRILHOS:
                continue
            refs_n = {r for r, _p in pinos}
            if a in refs_n and b in refs_n:
                return True
        return False

    # A KiCad-library connector has all its pins on one side. Placed left
    # of the chip it talks to with the pins facing left, every line had to
    # loop over the top to reach the chip (the display's FPC did): it is
    # mirrored so that the pins face the partner.
    ancoras = list(bloco.ancoras)
    for i, a in enumerate(ancoras):
        p = P.PARTS[a]
        p.espelho = False
        p.rotacao = 0
        if not p.kicad:
            continue
        lados = {{0: "L", 180: "R", 90: "B", 270: "T"}.get(ang, "L")
                 for _x, _y, ang in p.pin_base().values()}
        if i + 1 < len(ancoras) and _conversam(a, ancoras[i + 1]) and lados == {"L"}:
            p.espelho = True
        if i > 0 and _conversam(ancoras[i - 1], a) and lados == {"R"}:
            p.espelho = True

    x = 0.0
    for i, a in enumerate(ancoras):
        w, h = P.PARTS[a].size()
        esq, dire = P.PARTS[a].avanco_dos_pinos()
        dx, dy = P.PARTS[a].desloca_centro()
        por(a, x + esq + w / 2.0 - dx, h / 2.0 - dy)
        if i > 0 and _conversam(ancoras[i - 1], a):
            # on the rows of the pins it talks to: the anchor slides up or
            # down by the median offset of the connected pairs, so that
            # the lines between the two run straight (J401's contacts 6
            # to 10 reached DS401's rows 1 to 5 by five diagonals)
            difs = []
            for nome_n, pinos_n in N.NETS.items():
                if nome_n in S.TRILHOS:
                    continue
                de_a = [p_ for r_, p_ in pinos_n if r_ == a]
                de_b = [p_ for r_, p_ in pinos_n if r_ == ancoras[i - 1]]
                for pa in de_a:
                    for pb in de_b:
                        difs.append(_lado_e_ponta(ancoras[i - 1], pb)[1][1]
                                    - _lado_e_ponta(a, pa)[1][1])
            if difs:
                difs.sort()
                por(a, P.PARTS[a].x, P.PARTS[a].y + snap(difs[len(difs) // 2]))
        passo = 8 * GRID
        if i + 1 < len(ancoras) and _conversam(a, ancoras[i + 1]):
            passo = 20 * GRID
        # from the right edge of what the anchor occupies, its value
        # included: "JST S4B-ZR-SM4A-TF" ran under the harvester's pins
        x = max(x + esq + w + dire, caixas[a][2]) + passo

    # The labels come first, like a person draws: every anchor pin whose
    # net leaves the block gets its label's room reserved - a stub of two
    # steps and the text along the pin's line, the pentagon's height - as a
    # rectangle no member's body or text may take. Without it a series part
    # on the next line put its value under the label, and the label was
    # then placed wherever the maze found room, on top of something else.
    def _rotulada_(rede: str) -> bool:
        return any(r not in bloco.membros for r, _p in N.NETS.get(rede, []))

    for a in ancoras:
        pa = P.PARTS[a]
        for n_, (tx_, ty_) in pa.pin_sheet().items():
            rede_ = rede_do_pino(a, n_)
            if not rede_ or rede_ in S.TRILHOS or not _rotulada_(rede_):
                continue
            lado_, _pt = _lado_e_ponta(a, n_)
            comp = 2 * GRID + len(rede_) * 1.05 + 2.5
            if lado_ == "L":
                r_ = (tx_ - comp, ty_ - 1.0, tx_, ty_ + 1.0)
            elif lado_ == "R":
                r_ = (tx_, ty_ - 1.0, tx_ + comp, ty_ + 1.0)
            elif lado_ == "T":
                r_ = (tx_ - 1.0, ty_ - comp, tx_ + 1.0 + len(rede_) * 1.05, ty_)
            else:
                r_ = (tx_ - 1.0, ty_, tx_ + 1.0 + len(rede_) * 1.05, ty_ + comp)
            retangulos[f"rotulo:{a}.{n_}"] = [r_]

    # the members, each beside the pin it serves
    prateleira: list[str] = []
    for ref in bloco.membros:
        if ref in caixas:
            continue
        alvo = None
        for colocado in list(bloco.ancoras) + [r for r in caixas if r not in bloco.ancoras]:
            par = _pino_compartilhado(ref, colocado)
            if par:
                alvo = (colocado, par)
                break
        if alvo is None:
            prateleira.append(ref)
            continue
        colocado, (pin_col, pin_ref) = alvo
        lado, (tx, ty) = _lado_e_ponta(colocado, pin_col)
        dvec = {"L": (-1, 0), "R": (1, 0), "T": (0, -1), "B": (0, 1)}[lado]
        # where this part's own pin tip is, relative to its origin. For a
        # two-terminal part the pin that serves the chip has to be the one
        # FACING it: a part to the left of the chip presents its right pin.
        # The symbol cannot be rotated here, but it can be flipped.
        p = P.PARTS[ref]
        num = next(q.number for q in p.pins if q.name == pin_ref or q.number == pin_ref)
        p.espelho = False
        p.rotacao = 0
        cl = __import__("sch_lib").classe_do_simbolo(p)
        rx, ry, _a = p.pin_local()[num]
        # A part between a pin that ALSO leaves the block (it gets a label
        # on its stub) and a rail - a pull-up, a pull-down, a LED to VSYS -
        # stands up past the label, its serving tip on the pin's line: the
        # line runs from the pin, under the label, to the standing part,
        # and the rail's symbol goes up (or the ground down) from its other
        # end. Lying on the line at GAP, it sat under the label's text.
        em_pe = False
        dist = GAP

        def _rotulada(rede: str) -> bool:
            return any(r not in bloco.membros for r, _p in N.NETS.get(rede, []))

        if cl and len(p.pins) == 2 and lado in ("L", "R") and p.eixo_base() == "h":
            outro = next(q.number for q in p.pins if q.number != num)
            rede_serv = rede_do_pino(ref, num)
            rede_outro = rede_do_pino(ref, outro)
            if rede_outro in S.TRILHOS and _rotulada(rede_serv):
                # A shunt on a line that also leaves the block - a pull-up
                # or pull-down under a label - stands beside the line past
                # the label. (Standing EVERY shunt was tried on 2026-09-26:
                # the far tip of a standing part lands three lines away, on
                # another pin's wire, and two nets became one.)
                em_pe = True
                # the serving tip at the bottom when the other end goes to
                # a rail (its symbol stands above), at the top when it goes
                # to ground (the bars hang below); 270 puts pin 1 on top
                # and 90 puts it at the bottom (measured)
                serve_pino1 = (num == p.pins[0].number)
                if S.TRILHOS[rede_outro]:        # ground: serving tip on top
                    p.rotacao = 270 if serve_pino1 else 90
                else:
                    p.rotacao = 90 if serve_pino1 else 270
                # past the labels when this line or a line within three
                # pitches on the same side carries one (the standing body
                # spans three lines); else two steps of air past the pin
                perto = [n_ for n_, (tx2, ty2) in P.PARTS[colocado].pin_sheet().items()
                         if abs(tx2 - tx) < 1e-6 and abs(ty2 - ty) <= 3 * 2 * GRID + 1e-6]
                rotulos = [rede_serv] + [rede_do_pino(colocado, n_) for n_ in perto]
                rotulos = [r_ for r_ in rotulos if r_ and _rotulada(r_)]
                if rotulos:
                    # past the longest of those labels: its stub of two
                    # steps, the text, the pentagon, and a step of air -
                    # "GNSS_TIMEPULSE" reaches 20 mm, and a fixed ten steps
                    # put the pull-ups of the MCU under their labels
                    maior = max(len(r_) for r_ in rotulos)
                    dist = max(GAP_ROTULO,
                               snap(2 * GRID + maior * 1.05 + 3.0 + 1.5 * GRID))
                else:
                    dist = GAP + 2 * GRID
        if cl and len(p.pins) == 2 and not em_pe:
            if p.eixo() == "h" and lado in ("L", "R"):
                # left of the chip (dvec -1): the serving pin must be at +x
                if (dvec[0] < 0 and rx < 0) or (dvec[0] > 0 and rx > 0):
                    p.espelho = True
            elif p.eixo() == "v" and lado in ("T", "B"):
                # above the chip (dvec y -1 on the sheet): the serving pin is
                # the lower one, py < 0 in symbol space (y up)
                if (dvec[1] < 0 and ry > 0) or (dvec[1] > 0 and ry < 0):
                    p.espelho = True
        rx, ry, _a = p.pin_local()[num]
        # first try: the part's pin tip `dist` away from the placed pin tip
        ty_alvo = ty
        if em_pe:
            # When the line goes on to another anchor on that side (the
            # FPC's contacts to the panel), a body standing on the line
            # would wall the lines next to it, and they looped around it.
            # The part then stands clear of the corridor - above the top
            # line when its other end is a rail, below the bottom one when
            # it is ground - and the router drops a wire to its line,
            # crossing the others square, as a person draws a pull-up row.
            pa = P.PARTS[colocado]
            segue = any(_conversam(colocado, a2) for a2 in ancoras
                        if a2 != colocado
                        and ((P.PARTS[a2].x > pa.x) == (dvec[0] > 0)))
            if segue and dvec[0] != 0:
                linhas = [ty2 for _n2, (tx2, ty2) in pa.pin_sheet().items()
                          if abs(tx2 - tx) < 1e-6]
                if S.TRILHOS.get(rede_outro, False):     # ground: hangs below
                    ty_alvo = max(linhas) + 2 * GRID
                else:                                    # rail: stands above
                    ty_alvo = min(linhas) - 2 * GRID
        base = (tx + dvec[0] * dist - rx, ty_alvo + dvec[1] * dist + ry)
        achou = False
        # Outward along the pin's own line first, up to twelve steps, and
        # only then sideways onto the neighbouring lines: a series part
        # that slid one line up sat under that line's label, and two parts
        # on neighbouring pins are staggered along their lines, the way a
        # person draws them, not side by side.
        # Five steps outward is what staggering two parts on neighbouring
        # lines takes (their texts clear at about 6 mm); further than that
        # a part was pushed past the next anchor and its wire never came
        # back, so from there the search goes sideways as before.
        tentativas = [(passo, 0) for passo in range(0, 6)]
        tentativas += [(passo, lateral) for passo in range(0, 60)
                       for lateral in (0, 1, -1, 2, -2, 3, -3, 4, -4)
                       if not (lateral == 0 and passo < 6)]
        for passo, lateral in tentativas:
            ox = base[0] + dvec[0] * passo * GRID + (dvec[1] * lateral * 2 * GRID)
            oy = base[1] + dvec[1] * passo * GRID + (dvec[0] * lateral * 2 * GRID)
            if cabe(ref, snap(ox), snap(oy)):
                por(ref, ox, oy)
                achou = True
                break
        if not achou:
            prateleira.append(ref)

    # the shelf: parts that touch only rails, under the anchors
    if prateleira:
        # a block with no anchor ("Outros") starts its shelf at the origin.
        # The shelf wraps: a row is never wider than the anchors above it
        # (or 70 mm), so forty decoupling capacitors do not become a
        # single 400 mm line.
        y_base = (max(c[3] for c in caixas.values()) + 8 * GRID) if caixas else 0.0
        x_ini = min(c[0] for c in caixas.values()) if caixas else 0.0
        largura = max(LARGURA_PRATELEIRA,
                      (max(c[2] for c in caixas.values()) - x_ini) if caixas else 0.0)
        x = x_ini
        alt = 0.0
        # Same rail side by side: the tops of the 3V0 capacitors are then
        # one line of tips, and make_sch draws one wire along them with one
        # symbol at the end, instead of a symbol and a name over every one.
        # The parts that hang from two rails (the 0 R links) and the test
        # points come after the capacitors, in the same rows.
        prateleira.sort(key=lambda r: (_trilho_de_cima(r), r))
        for ref in prateleira:
            p = P.PARTS[ref]
            # A two-terminal part in the shelf stands up, the way a row of
            # decoupling is drawn: rail pin on top, ground pin at the bottom,
            # so the rail wire runs along the tops and the ground along the
            # bottoms with one symbol each (make_sch joins the runs). Which
            # way up: 270 puts pin 1 on top (measured), 90 puts pin 2 there.
            if __import__("sch_lib").classe_do_simbolo(p) and len(p.pins) == 2 \
                    and {q.side for q in p.pins} != {"T", "B"}:
                p.espelho = False
                rede1 = rede_do_pino(ref, p.pins[0].number)
                p.rotacao = 90 if rede1 == "GND" else 270
            elif __import__("sch_lib").classe_do_simbolo(p) == "tp":
                # a test point stands too, its pad hanging from the rail
                # line: the pin is on the symbol's right, and 90 takes the
                # right pin to the top (measured). Lying, its symbol went
                # 2 steps to the right, onto the next capacitor's name.
                p.espelho = False
                p.rotacao = 90
            w, h = p.size()
            esq, dire = p.avanco_dos_pinos()
            if x > x_ini and x + PASSO_PRATELEIRA > x_ini + largura:
                x = x_ini
                # a row holds the symbol over the top tips and the ground
                # under the bottom ones, each with its name: 24 mm
                y_base += alt + ENTRE_LINHAS_PRATELEIRA
                alt = 0.0
            cx, cy = x + esq + w / 2.0, y_base + h / 2.0
            if p.eixo() == "v":
                cy = y_base + PIN_LEN_V + h / 2.0
            k = 0
            while not cabe(ref, snap(cx), snap(cy)) and k < 60:
                cx += GRID
                k += 1
            por(ref, cx, cy)
            # the next part: at the shelf pitch from this one's centre when
            # both stand up (cx = x + esq + w/2), else clear of its box
            if p.eixo() == "v":
                x = snap(p.x) + PASSO_PRATELEIRA - esq - w / 2.0
            else:
                x = caixas[ref][2] + 2 * GRID
            alt = max(alt, caixas[ref][3] - caixas[ref][1])

    # the block's extents: the parts and the room kept for the labels
    tudo = list(caixas.values()) + [r for k, rs in retangulos.items()
                                    if k.startswith("rotulo:") for r in rs]
    x0 = min(c[0] for c in tudo)
    y0 = min(c[1] for c in tudo)
    x1 = max(c[2] for c in tudo)
    y1 = max(c[3] for c in tudo)
    # normalise to the origin
    for ref in caixas:
        P.PARTS[ref].x = snap(P.PARTS[ref].x - x0 + MARGEM_BLOCO)
        P.PARTS[ref].y = snap(P.PARTS[ref].y - y0 + MARGEM_BLOCO)
    return (snap(x1 - x0 + 2 * MARGEM_BLOCO), snap(y1 - y0 + 2 * MARGEM_BLOCO))


def posicionar(blocos: list[Bloco], papel: tuple[float, float],
               margem: float, topo: float) -> float:
    """Blocks on the page, left to right, shelf by shelf. Returns the y the
    last shelf ends at (what escolher_papel() asks)."""
    w_pag, _h_pag = papel
    x_lim = w_pag - margem
    x, y = margem, topo
    alt_linha = 0.0
    # Rows are packed tallest block first (the order among blocks of one
    # row is the reading order of BLOCOS): the two tall blocks of the power
    # sheet - the nPM1300 and the solar harvester - then share one row and
    # the four short ones the next, and the sheet is an A3. In the reading
    # order the tall ones fell in different rows, each row grew to the
    # taller of them, and only an A2 held it.
    tamanhos = {id(b): _colocar_bloco(b) for b in blocos}
    ordem = sorted(range(len(blocos)),
                   key=lambda i: (-tamanhos[id(blocos[i])][1], i))
    for i in ordem:
        b = blocos[i]
        bw, bh = tamanhos[id(b)]
        if x + bw > x_lim and alt_linha > 0.0:
            x = margem
            y += alt_linha + ENTRE_BLOCOS
            alt_linha = 0.0
        for ref in b.membros:
            P.PARTS[ref].x = snap(P.PARTS[ref].x + x)
            P.PARTS[ref].y = snap(P.PARTS[ref].y + y)
        b.caixa = (snap(x), snap(y), snap(x + bw), snap(y + bh))
        x += bw + ENTRE_BLOCOS
        alt_linha = max(alt_linha, bh)
    return y + alt_linha


def bloco_de(blocos: list[Bloco]) -> dict[str, Bloco]:
    return {r: b for b in blocos for r in b.membros}
