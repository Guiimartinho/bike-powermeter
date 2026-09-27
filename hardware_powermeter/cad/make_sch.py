#!/usr/bin/env python3
"""Write the hierarchical schematic: a root sheet and four block sheets.

The root is a block diagram: one box per sheet of 02-esquematico.md, the
signals that cross between them drawn as lines from box to box. Inside each
sheet the parts are placed on a grid with routing channels between the rows,
supplies and grounds are carried by power symbols next to the pin they feed,
and a signal that leaves the sheet ends at a hierarchical label on the
margin. That is the shape a schematic of this size has when a person draws
it, and it is what makes it readable: no page is wider than a sheet of paper,
and nothing is connected by a name that appears nowhere else.

Run:   python hardware_powermeter/cad/make_sch.py
Check: python hardware_powermeter/cad/check_sch.py
"""

from __future__ import annotations

import math
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import nets as N  # noqa: E402
import parts as P  # noqa: E402
import footprints as FPS  # noqa: E402
import sheets as S  # noqa: E402
import blocos as B  # noqa: E402
from sch_lib import (GRID, HierLabel, LocalLabel, PowerPort, Router,  # noqa: E402
                     Schematic, SheetSymbol, snap)

PROJETO = "pmeter"
DATA = "2026-09-27"

# Standard paper, chosen per sheet by how much it has to hold.
PAPEIS = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0),
          "A1": (841.0, 594.0), "A0": (1189.0, 841.0)}
ORDEM = ["A4", "A3", "A2", "A1", "A0"]

MARGEM = 20.0
# Routing channels between parts. They were 24 and 30, which is a corridor
# wider than most of the symbols it separates: with 69 parts on the power
# sheet that alone forced A1 - 841 x 594 mm of paper for a block that fits
# on a third of it. A schematic sheet bigger than A4 is almost always a
# layout that was spread to fill the paper rather than paper chosen to hold
# the layout. 14 and 18 still leave more than a wire's width between any two
# symbols, and check_sch.py is what proves it: it fails if a wire crosses a
# component on any sheet.
COL_GAP = 16.0
ROW_GAP = 22.0
LABEL_X = 12.0     # how far inside the left and right margins a label sits

# folha -> redes que recebem PWR_FLAG nela. Preenchido em main().
FLAGS_AQUI: dict[str, set[str]] = {}


def escolher_papel(refs: list[str], n_labels: int) -> str:
    """The smallest standard sheet the drawing actually fits on.

    Measured, not estimated. The old version budgeted a fixed 30 x 18 mm cell
    plus the channels for EVERY part - 54 x 48 mm each, whether it was a
    0402 or an eighty pad module - and started from A3, so A4 was never even
    considered. Sixty-nine parts then "needed" 178.848 mm2 and landed on A1,
    where the real drawing occupies about a third of the sheet.

    This lays the parts out on the candidate sheet and asks whether the last
    row ended above the bottom margin. That is the same code that draws them,
    so the answer cannot drift from the drawing.
    """
    # `refs` is the list of functional blocks since 2026-09-26: the blocks are
    # laid out on the candidate sheet and the sheet is accepted when the last
    # shelf ends above the bottom margin and no block is wider than the page.
    for nome in ORDEM:
        w, h = PAPEIS[nome]
        fim = B.posicionar(refs, (w, h), MARGEM, MARGEM + 14.0)
        if fim <= h - MARGEM and all(b.caixa[2] <= w - MARGEM + 1e-6 for b in refs):
            return nome
    return "A0"


def ordenar_por_ligacao(refs: list[str]) -> list[str]:
    """Walk the sheet's parts by what connects to what, biggest part first.

    Filling the grid in this order puts the decoupling next to its chip and
    the divider next to the pin it divides, instead of sorting the page by
    pin count and scattering a circuit across it.
    """
    conjunto = set(refs)
    ligados: dict[str, set[str]] = {r: set() for r in refs}
    for nome, pinos in N.NETS.items():
        if nome in S.TRILHOS:          # a rail touches everything: it says nothing
            continue
        na_folha = {r for r, _p in pinos} & conjunto
        for a in na_folha:
            ligados[a] |= na_folha - {a}
    restantes = sorted(refs, key=lambda r: (-len(P.PARTS[r].pins), r))
    saida: list[str] = []
    vistos: set[str] = set()
    while restantes:
        raiz = next(r for r in restantes if r not in vistos)
        fila = [raiz]
        vistos.add(raiz)
        while fila:
            atual = fila.pop(0)
            saida.append(atual)
            for v in sorted(ligados[atual],
                            key=lambda r: (-len(P.PARTS[r].pins), r)):
                if v not in vistos:
                    vistos.add(v)
                    fila.append(v)
        restantes = [r for r in restantes if r not in vistos]
    return saida


def posicionar(refs: list[str], papel: str) -> float:
    """Grid placement with channels, biggest part first.

    Returns the y the last row ends at, which is what escolher_papel() asks
    to know whether the block fits on this sheet.
    """
    w_pag, h_pag = PAPEIS[papel]
    x_lim = w_pag - MARGEM - LABEL_X
    x = MARGEM + LABEL_X
    y = MARGEM + 14.0
    alt_linha = 0.0
    for ref in refs:
        part = P.PARTS[ref]
        w, h = part.size()
        # Quanto os pinos avancam para fora da caixa de cada lado.
        #
        # Nos simbolos deste projeto isso e sempre PIN_LEN e da na mesma. Nos
        # da biblioteca do KiCad nao: um `Conn_01x10_Socket` tem o desenho com
        # 1,27 mm de largura e os DEZ pinos 3,81 mm a esquerda dele. Sem
        # reservar esse avanco, o vizinho da esquerda encosta nos dez pinos e
        # os dez fios tem de se espremer no que sobra - dois deles nao
        # roteavam.
        esq, dire = part.avanco_dos_pinos()
        if x + esq + w + dire > x_lim and alt_linha > 0.0:
            x = MARGEM + LABEL_X
            y += alt_linha + ROW_GAP
            alt_linha = 0.0
        x += esq
        # `desloca_centro` e zero para os simbolos deste projeto e diferente
        # de zero para os da biblioteca do KiCad, que nao sao centrados na
        # origem. Sem descontar aqui, a peca sai da celula que a fila lhe deu.
        dx, dy = part.desloca_centro()
        part.x = snap(x + w / 2.0 - dx)
        part.y = snap(y + h / 2.0 - dy)
        x += w + dire + COL_GAP
        alt_linha = max(alt_linha, h)
    return y + alt_linha


def pinos_do_no(nome: str, folha: str) -> list[tuple[str, str]]:
    return [(r, p) for r, p in N.NETS[nome] if S.sheet_of(r) == folha]


def ponto(ref: str, pin_name: str) -> tuple[float, float]:
    part = P.PARTS[ref]
    numero = next(q.number for q in part.pins
                  if q.name == pin_name or q.number == pin_name)
    return part.pin_sheet()[numero]


def _dentro_do_corpo(part, x: float, y: float) -> bool:
    """Is the point on the part's body, a hair of margin included?"""
    bx0, by0, bx1, by1 = part.box()
    return bx0 - 0.3 <= x <= bx1 + 0.3 and by0 - 0.3 <= y <= by1 + 0.3


def lado_do_pino(ref: str, pin_name: str) -> str:
    part = P.PARTS[ref]
    numero = next(q.number for q in part.pins
                  if q.name == pin_name or q.number == pin_name)
    if part.kicad:
        # Num simbolo da biblioteca do KiCad quem manda e o angulo do pino,
        # nao o lado que este projeto declarou em parts.py: o desenho ja
        # existe e o fio tem de sair na direcao em que o pino aponta. Angulo
        # 0 e um pino que aponta para a direita, ou seja, esta na ESQUERDA.
        ang = part.pin_local()[numero][2]
        return {0: "L", 180: "R", 90: "B", 270: "T"}.get(ang, "L")
    # Um simbolo de dois terminais deste projeto e desenhado pela GEOMETRIA
    # de pin_local(), nao pelos lados que parts.py declarou: o modulo solar
    # PV101 declara os pinos como R e B e o desenho os poe a esquerda e a
    # direita. Quem usava o lado declarado punha o simbolo de terra dois
    # passos ABAIXO da ponta direita, em cima do vizinho - foi assim que o
    # GND engoliu PV_A, PV_B, SRC e MPPT em 2026-09-26.
    from sch_lib import classe_do_simbolo
    if classe_do_simbolo(part):
        px, py, _a = part.pin_local()[numero]
        if part.eixo() == "v":
            return "T" if py > 0 else "B"
        return "L" if px < 0 else "R"
    return next(q.side for q in part.pins
                if q.name == pin_name or q.number == pin_name)


def montar_folha(nome: str, arquivo: str, pagina: str, root_uuid: str,
                 sheet_uuid: str, tipo: dict[str, str],
                 papel_forcado: str = "") -> tuple[Schematic, list[str], int]:
    refs = S.por_folha()[nome]
    entre = sorted(n for n, k in tipo.items()
                   if k == "ENTRE" and any(S.sheet_of(r) == nome for r, _p in N.NETS[n]))
    # The sheet is drawn by functional block since 2026-09-26 (blocos.py):
    # each block around its anchor, the blocks left to right in the order
    # the signal flows, a dashed box and a title on each.
    blocos = B.blocos_da_folha(nome, refs)
    papel = papel_forcado or escolher_papel(blocos, len(entre))
    B.posicionar(blocos, PAPEIS[papel], MARGEM, MARGEM + 14.0)
    w_pag, h_pag = PAPEIS[papel]

    sch = Schematic(PROJETO, papel, name=nome, root_uuid=root_uuid,
                    title=f"Bike Power Meter - {nome}", rev="A", date=DATA)
    sch.sheet_symbol_uuid = sheet_uuid
    sch.parts = [P.PARTS[r] for r in refs]
    for b in blocos:
        sch.rects.append(b.caixa)
        # the title sits just above its box, where no power symbol can be
        sch.text(b.caixa[0], b.caixa[1] - 0.8, b.titulo, 1.8)
    dono_bloco = B.bloco_de(blocos)

    router = Router(sch.parts)
    router.build_obstacles()
    # A wire never leaves its block: the gaps between the boxes and the page
    # margins are closed to the router, so what crosses a box boundary is a
    # label, by construction.
    x_cells = range(0, int(w_pag / GRID) + 2)
    y_cells = range(0, int(h_pag / GRID) + 2)
    dentro_de_bloco: set[tuple[int, int]] = set()
    for b in blocos:
        x0, y0, x1, y1 = b.caixa
        for kx in range(router.key(x0, y0)[0], router.key(x1, y1)[0] + 1):
            for ky in range(router.key(x0, y0)[1], router.key(x1, y1)[1] + 1):
                dentro_de_bloco.add((kx, ky))
    for kx in x_cells:
        for ky in y_cells:
            if (kx, ky) not in dentro_de_bloco:
                router.blocked.add((kx, ky))

    # De quem e cada celula de pino desta folha.
    #
    # O roteador sabe QUE uma celula e de pino, mas nao DE QUEM - e o
    # colocador de simbolos de alimentacao, que roda antes de qualquer fio,
    # so olhava `router.blocked`. Uma celula de pino nao esta em `blocked`,
    # esta em `pin_cells`: nada impedia um simbolo de GND de pousar em cima
    # do pino do vizinho, ou o talo dele de atravessar o pino alheio. Dois
    # fios que se encostam sao um no so para o KiCad, e nada no desenho diz
    # isso - foi assim que o MPPT do ADP5091, que fica na borda de baixo
    # junto dos tres pinos de terra, virou terra.
    dono_da_celula: dict[tuple[int, int], set[str]] = {}
    for rede_n, pinos_n in N.NETS.items():
        for ref_n, pin_n in pinos_n:
            if S.sheet_of(ref_n) != nome:
                continue
            peca = P.PARTS[ref_n]
            num = next(q.number for q in peca.pins
                       if q.name == pin_n or q.number == pin_n)
            px_n, py_n = peca.pin_sheet()[num]
            ang_n = peca.pin_local()[num][2]
            dx_n, dy_n = {0: (1, 0), 90: (0, -1),
                          180: (-1, 0), 270: (0, 1)}.get(ang_n, (0, 0))
            bx0, by0, bx1, by1 = peca.box()
            cx_n, cy_n = px_n, py_n
            for _ in range(9):
                dono_da_celula.setdefault(router.key(cx_n, cy_n),
                                          set()).add(rede_n)
                if bx0 <= cx_n <= bx1 and by0 <= cy_n <= by1:
                    break
                cx_n += dx_n * GRID
                cy_n += dy_n * GRID
            # ...and two cells OUTWARD of the tip, kept for the stub the
            # pin will need - its label, its symbol, its own wire. Nothing
            # reserved them, FPC_DISP ran along the line in front of
            # J401.VDDA, and that pin had nowhere to go (2026-09-26).
            for k in (1, 2):
                cel = router.key(px_n - dx_n * k * GRID, py_n - dy_n * k * GRID)
                cx_k, cy_k = router.pos(cel)
                # a cell inside another part's body stays an obstacle (the
                # pad of a test point faced the edge of a standing resistor,
                # and a wire ran along that edge)
                if any(r_o != ref_n and _dentro_do_corpo(P.PARTS[r_o], cx_k, cy_k)
                       for r_o in refs):
                    continue
                dono_da_celula.setdefault(cel, set()).add(rede_n)
                router.pin_cells.add(cel)
                router.used.setdefault(cel, set()).add(rede_n)
                # and never an obstacle: the coil on SW2 sat one line under
                # the coil on SW1, whose margin covered the two cells in
                # front of its pin, and its own net could not reach it
                router.blocked.discard(cel)

    # A pass-through connector's pin is in two nets that are one node (the
    # board's DISP_SCK and the panel's FPC_SCLK on J401.SCLK): for the
    # keep-outs of that pin the two are not "another net" to each other.
    irmas: dict[str, set[str]] = {}
    for ref_p in N.PASSA_DIRETO:
        por_pino: dict[str, set[str]] = {}
        for rede_n, pinos_n in N.NETS.items():
            for r_n, p_n in pinos_n:
                if r_n == ref_p:
                    por_pino.setdefault(p_n, set()).add(rede_n)
        for redes_p in por_pino.values():
            for r1 in redes_p:
                irmas.setdefault(r1, set()).update(redes_p - {r1})

    router.irmas = irmas

    def _de_outro(cel, rede: str) -> bool:
        return bool(dono_da_celula.get(cel, set()) - {rede} - irmas.get(rede, set()))

    # ---- supplies and grounds, one power symbol per pin ----
    # A power symbol is a symbol AND a label, and only the symbol was being
    # given room: two ground pins two grid steps apart each got their own
    # symbol, the symbols did not collide, and the words printed straight
    # over each other - "GNDGNDGND" across the bottom of every chip. What is
    # reserved now is the whole thing, the name included.
    ocupados: set[tuple[float, float]] = set()
    # what a symbol's name must not sit on: the other symbols (added as
    # they are placed) and the parts, with the room their reference and
    # value take - the same boxes the block placer keeps apart
    # as SEPARATE rectangles per part (body with pins, each text), never
    # one bounding box: the 26 mm value of the FPC connector, in one box
    # with the connector, walled off the two steps in front of every one
    # of its pins, and its ten labels were placed by the maze in a heap
    caixas: list[tuple[float, float, float, float]] = [
        rect for r in refs
        for rect in B._retangulos(r, P.PARTS[r].x, P.PARTS[r].y)]
    # and the blocks' titles, which a symbol's name printed over
    for b in blocos:
        caixas.append((b.caixa[0], b.caixa[1] - 0.8 - 1.8,
                       b.caixa[0] + len(b.titulo) * 1.5, b.caixa[1] - 0.8))

    flags_desta = FLAGS_AQUI.get(nome, set())
    # the point and direction of the first symbol placed for each rail on
    # this sheet: a PWR_FLAG the rail needs goes there, pointing the other
    # way
    simbolo_da_rede: dict[str, tuple[float, float, str]] = {}
    SENTIDO_DO_LADO = {"L": "L", "R": "R", "T": "U", "B": "D"}
    # where the PWR_FLAG points when it shares the point of the rail's
    # symbol: sideways off a standing symbol (pointing back down went over
    # the stub that feeds the point), down off a lying one
    CONTRARIO = {"U": "R", "D": "R", "L": "D", "R": "D"}

    def _caixa_simbolo(qx: float, qy: float, rede: str, sentido: str
                       ) -> tuple[float, float, float, float]:
        """What a power symbol occupies: the art (2,54 from the point) and
        its name beyond it, in the direction it points - plus the PWR_FLAG
        and its name on the other side, when the rail carries one here."""
        terra = S.TRILHOS.get(rede, False)
        a = PowerPort(rede, qx, qy, ground=terra, sentido=sentido).caixa()
        if rede in flags_desta:
            f = PowerPort("PWR_FLAG", qx, qy, sentido=CONTRARIO[sentido]).caixa()
            a = (min(a[0], f[0]), min(a[1], f[1]), max(a[2], f[2]), max(a[3], f[3]))
        return a

    def _cabe(qx: float, qy: float, rede: str, sentido: str) -> bool:
        a = _caixa_simbolo(qx, qy, rede, sentido)
        return not any(a[2] > b[0] and b[2] > a[0] and a[3] > b[1] and b[3] > a[1]
                       for b in caixas)

    def _reservar_simbolo(qx: float, qy: float, rede: str, sentido: str) -> None:
        """The symbol is placed: keep the next symbols and the labels off
        it, and keep the wires routed later out of it.

        A symbol lying along a side pin's line (L, R) is closed whole: art
        and name are on that line and on nothing else. A standing one (U, D)
        has only its art closed: its name is 3,3 mm past the point, between
        two pin lines, and the neighbouring pins' wires run under it the
        way they do on any dense chip - closing the name too shut the
        neighbours in, and CC1, CC2 and TERM lost their labels.
        """
        a = _caixa_simbolo(qx, qy, rede, sentido)
        caixas.append(a)
        simbolo_da_rede.setdefault(rede, (qx, qy, sentido))
        kx0, ky0 = router.key(qx, qy)
        sentidos = [sentido] + ([CONTRARIO[sentido]] if rede in flags_desta else [])
        for s in sentidos:
            dx, dy = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}[s]
            fim = 2 if s in ("U", "D") else int(math.ceil(
                (2.54 + 0.76 + len(rede) * 1.05 + 0.5) / GRID))
            for k in range(1, fim + 1):
                cel = (kx0 + dx * k, ky0 + dy * k)
                if cel not in router.pin_cells:
                    router.blocked.add(cel)

    # A rail pin that gets no room for its symbol is closed by a LABEL with
    # the rail's name instead (same net for KiCad: a local label named GND
    # joins the GND power net of the sheet). Until 2026-09-26 the fallback
    # was "put the symbol two steps away anyway", and two steps away was the
    # neighbour's pin: that is how GND swallowed PV_A, SRC and MPPT.
    sem_simbolo: list[tuple[str, str, str]] = []
    # every pin tip of the sheet with its net: what a rail run must not
    # cross, and what a stub must not land on
    todas_pontas: dict[tuple[float, float], str] = {}
    for rede_t, pinos_t in N.NETS.items():
        for ref_t, pin_t in pinos_t:
            if S.sheet_of(ref_t) == nome:
                todas_pontas[ponto(ref_t, pin_t)] = rede_t
    for rede, terra in S.TRILHOS.items():
        if rede not in N.NETS:
            continue
        # Neighbouring pins of the same rail on the same side of a part -
        # the four VDD pins across the top of the IMU - are joined by one
        # wire along their tips and get ONE symbol, at the end of the run.
        # One symbol per pin printed four names on top of each other.
        # A run may cross parts: the tops of a row of stood-up decoupling
        # capacitors are one line of tips of the same rail, and get one
        # wire along them and one symbol. Grouped by side and by the line
        # the tips are on; two tips are neighbours when they are at most
        # eight steps apart and no tip of ANOTHER net lies between them.
        grupos: dict[tuple[str, float], list[tuple[float, tuple[float, float], str, str]]] = {}
        pontos_vistos: set[tuple[float, float]] = set()
        for ref, pin_name in pinos_do_no(rede, nome):
            px, py = ponto(ref, pin_name)
            # pins a KiCad symbol stacks on one point (the USB-C's GND
            # A1/B1/A12/B12) are one tip and get one symbol, not a column
            if (px, py) in pontos_vistos:
                continue
            pontos_vistos.add((px, py))
            lado = lado_do_pino(ref, pin_name)
            chave, linha = (py, px) if lado in ("L", "R") else (px, py)
            grupos.setdefault((lado, round(linha, 3)), []).append(
                (chave, (px, py), pin_name, ref))

        def _alheia_entre(a: tuple[float, float], b: tuple[float, float]) -> bool:
            for (tx, ty), outra in todas_pontas.items():
                if outra == rede:
                    continue
                if abs(a[0] - b[0]) < 1e-6 and abs(tx - a[0]) < 1e-6 \
                        and min(a[1], b[1]) + 1e-6 < ty < max(a[1], b[1]) - 1e-6:
                    return True
                if abs(a[1] - b[1]) < 1e-6 and abs(ty - a[1]) < 1e-6 \
                        and min(a[0], b[0]) + 1e-6 < tx < max(a[0], b[0]) - 1e-6:
                    return True
            return False

        def _caminho_livre(a: tuple[float, float], b: tuple[float, float]) -> bool:
            """No body, no text and no other net's pin between two tips."""
            ka, kb = router.key(*a), router.key(*b)
            n = max(abs(kb[0] - ka[0]), abs(kb[1] - ka[1]))
            for k in range(1, n):
                cel = (ka[0] + (kb[0] - ka[0]) * k // n, ka[1] + (kb[1] - ka[1]) * k // n)
                if cel in router.blocked or _de_outro(cel, rede):
                    return False
            return True

        primeiros: list[tuple[str, str]] = []
        for (lado, _linha), lista in grupos.items():
            lista.sort()
            i = 0
            while i < len(lista):
                j = i
                # up to the shelf pitch apart (blocos.PASSO_PRATELEIRA), so
                # that the stood-up capacitors of one rail share the wire
                while (j + 1 < len(lista)
                       and 1e-6 < lista[j + 1][0] - lista[j][0] <= B.PASSO_PRATELEIRA + 1e-6
                       and not _alheia_entre(lista[j][1], lista[j + 1][1])
                       and _caminho_livre(lista[j][1], lista[j + 1][1])):
                    j += 1
                if j > i:
                    # one wire per pair of neighbours, not one wire over the
                    # whole run: "wires connect with other wires or pins
                    # only if their ends coincide exactly" (KiCad manual),
                    # so a pin in the middle of a long wire is NOT on it
                    for k in range(i, j):
                        a, b = lista[k][1], lista[k + 1][1]
                        sch.wires.append((a, b))
                        # EVERY cell of the wire is the net's: marking only
                        # the two ends and the middle left the cells between
                        # free, a label of another net was placed on one of
                        # them, and FPC_VSSA became the ground (2026-09-26)
                        ka, kb = router.key(*a), router.key(*b)
                        n = max(abs(kb[0] - ka[0]), abs(kb[1] - ka[1]), 1)
                        for t in range(n + 1):
                            cel = (ka[0] + (kb[0] - ka[0]) * t // n,
                                   ka[1] + (kb[1] - ka[1]) * t // n)
                            router.used.setdefault(cel, set()).add(rede)
                            router.dirs.setdefault(cel, {}).setdefault(rede, set()).add(
                                "V" if lado in ("L", "R") else "H")
                primeiros.append((lista[i][3], lista[i][2]))
                i = j + 1
        for ref, pin_name in primeiros:
            px, py = ponto(ref, pin_name)
            lado = lado_do_pino(ref, pin_name)
            dx, dy = {"L": (-1, 0), "R": (1, 0), "T": (0, -1), "B": (0, 1)}[lado]
            sentido = SENTIDO_DO_LADO[lado]
            # First pass: a spot where the NAME also fits. Second: any free
            # spot at all. A long stub to save a label is worse than the
            # label - at fourteen grid steps one of them ran across a
            # component and split a net.
            passo = None
            # only a spot where the NAME also fits; a second pass that took
            # any free spot printed the name on the neighbour's value
            motivos: list[str] = []
            for tentativa in range(2, 13):
                qx, qy = (px + dx * tentativa * GRID,
                          py + dy * tentativa * GRID)
                if (qx, qy) in ocupados:
                    motivos.append(f"{tentativa}:ocupado")
                    continue
                if router.key(qx, qy) in router.blocked:
                    motivos.append(f"{tentativa}:bloqueado")
                    continue
                # nor may the stub run through a body or a text on its way
                # there: the shield of the U.FL took its ground straight
                # through the antenna jumper's box (2026-09-26)
                if any(router.key(px + dx * k * GRID, py + dy * k * GRID) in router.blocked
                       for k in range(1, tentativa)):
                    motivos.append(f"{tentativa}:talo bloqueado")
                    continue
                # nem o simbolo nem o talo dele podem encostar num pino
                # de OUTRA rede: seria um curto que o desenho nao mostra
                if any(_de_outro(router.key(px + dx * k * GRID,
                                            py + dy * k * GRID), rede)
                       for k in range(1, tentativa + 1)):
                    motivos.append(f"{tentativa}:pino alheio")
                    continue
                if not _cabe(qx, qy, rede, sentido):
                    motivos.append(f"{tentativa}:nome nao cabe")
                    continue
                passo = tentativa
                break
            # No straight spot where the name fits: the maze takes the
            # symbol to one (below). A third pass that took any free cell
            # up to twenty steps out printed the name on the neighbour.
            if passo is None:
                if os.environ.get("SCH_DEBUG"):
                    print(f"  [debug] {nome}: {rede} em {ref}.{pin_name}: "
                          + " ".join(motivos))
                sem_simbolo.append((rede, ref, pin_name))
                continue
            qx, qy = px + dx * passo * GRID, py + dy * passo * GRID
            ocupados.add((qx, qy))
            router.pin_cells.add(router.key(qx, qy))
            _reservar_simbolo(qx, qy, rede, sentido)
            sch.powers.append(PowerPort(rede, qx, qy, ground=terra,
                                        ref=f"#PWR{len(sch.powers) + 1:03d}",
                                        sentido=sentido))
            sch.wires.append(((px, py), (qx, qy)))
            for k in range(min(passo, 14) + 1):
                cel = router.key(px + dx * k * GRID, py + dy * k * GRID)
                router.used.setdefault(cel, set()).add(rede)
                d = router.dirs.setdefault(cel, {}).setdefault(rede, set())
                d.add("H" if dy == 0 else "V")

    # ---- nets: a wire inside a block, a label across blocks and sheets ----
    #
    # A net whose pins all sit in one block is drawn as a wire, by the maze
    # router, inside the box. A net that touches two blocks of this sheet
    # gets a local label on a short stub at every pin; one that leaves the
    # sheet gets a hierarchical label the same way (the root sheet draws the
    # line between the blocks). Nothing crosses the page as a wire.
    falhas: list[str] = []
    n_rotulos_por_falha = 0
    dentro = [n for n, k in tipo.items()
              if k == "DENTRO" and any(S.sheet_of(r) == nome for r, _p in N.NETS[n])]
    nomes_entre = set(entre)

    # where each labelled pin's label ended up, by (ref, pin number): a
    # pass-through connector's other net continues from there
    ponta_do_rotulo: dict[tuple[str, str], tuple[float, float]] = {}

    def _livre(c: tuple[int, int], rede: str) -> bool:
        if c in router.blocked or _de_outro(c, rede):
            return False
        # a pin cell is free for the net that owns it (the two cells in
        # front of its own pin), never for another
        if c in router.pin_cells and rede not in router.used.get(c, set()):
            return False
        return not (router.used.get(c, set()) - {rede} - irmas.get(rede, set()))

    def _rotulo(rede: str, ref: str, pin: str, hier: bool) -> bool:
        """A stub out of the pin, in the direction it faces, and the label.

        A straight stub of two to eight steps when the way is clear; when it
        is not, the maze router takes the stub to the nearest free cell
        instead. What is never done is drawing the stub over something
        else: a label on another net's wire joins the two, silently.
        """
        lado, (px, py) = B._lado_e_ponta(ref, pin)
        dx, dy = {"L": (-1, 0), "R": (1, 0), "T": (0, -1), "B": (0, 1)}[lado]
        fim = None

        def _texto_cabe(qx: float, qy: float) -> bool:
            # the label's text runs outward from its point along the stub's
            # direction, and must not sit on a part, its value or a power
            # symbol's name (the same boxes the symbols are kept off)
            w = len(rede) * 1.05 + 2.5
            if dx:
                a = (qx if dx > 0 else qx - w, qy - 1.0, qx + w if dx > 0 else qx, qy + 1.0)
            else:               # on a vertical stub the text still runs to the right
                a = (qx, qy - 1.0, qx + w, qy + 1.0)
            return not any(a[2] > b[0] and b[2] > a[0] and a[3] > b[1] and b[3] > a[1]
                           for b in caixas)

        for tent in range(2, 13):
            cels = [router.key(px + dx * k * GRID, py + dy * k * GRID)
                    for k in range(1, tent + 1)]
            if all(_livre(c, rede) for c in cels) and \
                    _texto_cabe(snap(px + dx * tent * GRID), snap(py + dy * tent * GRID)):
                fim = (snap(px + dx * tent * GRID), snap(py + dy * tent * GRID))
                sch.wires.append(((px, py), fim))
                for k in range(tent + 1):
                    cel = router.key(px + dx * k * GRID, py + dy * k * GRID)
                    router.used.setdefault(cel, set()).add(rede)
                    router.dirs.setdefault(cel, {}).setdefault(rede, set()).add(
                        "H" if dy == 0 else "V")
                break
        if fim is None:
            k0 = router.key(px, py)
            # a free cell where the label's text also lands on nothing;
            # failing that, any free cell, so that the pin is never open
            livres = {(k0[0] + ax, k0[1] + ay)
                      for ax in range(-10, 11) for ay in range(-10, 11)
                      if 2 <= abs(ax) + abs(ay) <= 10
                      and _livre((k0[0] + ax, k0[1] + ay), rede)}
            alvos = {c for c in livres if _texto_cabe(*router.pos(c))}
            router.used.setdefault(k0, set()).add(rede)
            caminho = router.route(rede, (px, py), alvos, 12) if alvos else None
            if caminho is None and livres - alvos:
                caminho = router.route(rede, (px, py), livres - alvos, 12)
            if caminho is None:
                if os.environ.get("SCH_DEBUG"):
                    def _estado(c):
                        if c in router.blocked:
                            return "bloqueada"
                        if c in router.pin_cells:
                            return "pino"
                        if _de_outro(c, rede):
                            return "talo de " + ",".join(sorted(dono_da_celula.get(c, set()) - {rede}))
                        outras = router.used.get(c, set()) - {rede}
                        return "fio de " + ",".join(sorted(outras)) if outras else "livre"
                    vizinhas = [(k, _estado((k0[0] + dx * k, k0[1] + dy * k))) for k in range(1, 7)]
                    print(f"  [debug] {nome}: rotulo {rede} em {ref}.{pin} ({lado}): "
                          f"{len(alvos)} alvos; a frente: {vizinhas}")
                falhas.append(f"{nome}: {rede} sem lugar para o rotulo em {ref}.{pin}")
                return False
            router.add_path(rede, caminho)
            fim = router.pos(caminho[-1])
            fim = (snap(fim[0]), snap(fim[1]))
        qx, qy = fim
        # a label is a connection point: a wire of another net that runs
        # over it joins that signal, silently
        router.pin_cells.add(router.key(qx, qy))
        numero_r = next(q.number for q in P.PARTS[ref].pins
                        if q.name == pin or q.number == pin)
        ponta_do_rotulo[(ref, numero_r)] = (qx, qy)
        ang = 180 if lado == "L" else 0
        if hier:
            sch.labels.append(HierLabel(rede, qx, qy, angle=ang))
        else:
            sch.local_labels.append(LocalLabel(rede, qx, qy, angle=ang))
        return True

    # The rail pins that got no room for a power symbol next to them: the
    # maze router takes a stub to the nearest free cell and the symbol goes
    # there. NOT a local label named after the rail - measured in KiCad's
    # netlist on 2026-09-26, a local label "3V0" is a net of its own,
    # "/folha/3V0", and never joins the power net 3V0.
    for rede_s, ref_s, pin_s in sem_simbolo:
        terra_s = S.TRILHOS.get(rede_s, False)
        _lado_s, (px_s, py_s) = B._lado_e_ponta(ref_s, pin_s)
        k0 = router.key(px_s, py_s)
        # a cell where the symbol AND its name fit, pointing some way;
        # the way it ends up pointing is the path's last leg (below)
        alvos = {(k0[0] + ax, k0[1] + ay)
                 for ax in range(-12, 13) for ay in range(-12, 13)
                 if 2 <= abs(ax) + abs(ay) <= 12
                 and _livre((k0[0] + ax, k0[1] + ay), rede_s)
                 and any(_cabe(*router.pos((k0[0] + ax, k0[1] + ay)), rede_s, s)
                         for s in ("L", "R", "U", "D"))}
        router.used.setdefault(k0, set()).add(rede_s)
        caminho = router.route(rede_s, (px_s, py_s), alvos, 14) if alvos else None
        if caminho is None:
            # last resort, so that no pin is ever left open: any free cell
            # the maze reaches, the name landing where it lands (and the
            # run says so, to be looked at)
            alvos = {(k0[0] + ax, k0[1] + ay)
                     for ax in range(-14, 15) for ay in range(-14, 15)
                     if 2 <= abs(ax) + abs(ay) <= 14
                     and _livre((k0[0] + ax, k0[1] + ay), rede_s)}
            caminho = router.route(rede_s, (px_s, py_s), alvos, 18) if alvos else None
            if caminho is not None:
                print(f"  aviso: {nome}: o simbolo de {rede_s} em {ref_s}.{pin_s} "
                      "ficou onde coube, sem lugar para o nome")
        if caminho is None:
            falhas.append(f"{nome}: {rede_s} sem lugar para o simbolo em {ref_s}.{pin_s}")
            continue
        router.add_path(rede_s, caminho)
        qx_s, qy_s = router.pos(caminho[-1])
        qx_s, qy_s = snap(qx_s), snap(qy_s)
        router.pin_cells.add(router.key(qx_s, qy_s))
        # it points on along the last leg of the path that brought it here
        ax_s, ay_s = router.pos(caminho[-2]) if len(caminho) > 1 else (px_s, py_s)
        if abs(qx_s - ax_s) > abs(qy_s - ay_s):
            sentido_s = "R" if qx_s > ax_s else "L"
        else:
            sentido_s = "D" if qy_s > ay_s else "U"
        _reservar_simbolo(qx_s, qy_s, rede_s, sentido_s)
        sch.powers.append(PowerPort(rede_s, qx_s, qy_s, ground=terra_s,
                                    ref=f"#PWR{len(sch.powers) + 1:03d}",
                                    sentido=sentido_s))

    # A ORDEM importa: roteando primeiro quem tem menos espaco em volta, o
    # apertado passa e o folgado da a volta, que e o que uma pessoa faz.
    def _aperto(rede: str) -> int:
        livre = 0
        for r, p in pinos_do_no(rede, nome):
            kx, ky = router.key(*ponto(r, p))
            for ax in range(-3, 4):
                for ay in range(-3, 4):
                    c = (kx + ax, ky + ay)
                    if c not in router.blocked and c not in router.pin_cells:
                        livre += 1
        return livre

    # Labels first, wires after: a label is a fixed point and a wire is not,
    # so the wires are what bends around them, not the other way round.
    com_fio: list[str] = []
    for rede in sorted(dentro, key=lambda n: (_aperto(n), n)) + sorted(entre):
        pinos = pinos_do_no(rede, nome)
        hier = rede in nomes_entre
        blocos_da_rede = {id(dono_bloco[r]) for r, _p in pinos}
        if hier or len(blocos_da_rede) > 1:
            for r, p in pinos:
                _rotulo(rede, r, p, hier)
        else:
            com_fio.append(rede)
    for rede in com_fio:
        pinos = pinos_do_no(rede, nome)
        # On a pass-through connector the pin already has the board net's
        # label on a stub: the panel's wire continues from the label's
        # point (a wire end on a wire end: connected), instead of fighting
        # the label for the two cells in front of the pin.
        pts = []
        for r, p in pinos:
            xy = ponto(r, p)
            if r in N.PASSA_DIRETO:
                numero_p = next(q.number for q in P.PARTS[r].pins
                                if q.name == p or q.number == p)
                xy = ponta_do_rotulo.get((r, numero_p), xy)
            pts.append(xy)
        if len(pts) < 2:
            continue
        feito = {router.key(*pts[0])}
        router.used.setdefault(router.key(*pts[0]), set()).add(rede)
        roteou = True
        for pt in pts[1:]:
            if router.key(*pt) in feito:
                continue
            caminho = None
            for folga in (40, 120, 400):
                caminho = router.route(rede, pt, feito, folga)
                if caminho is not None:
                    break
            if caminho is None:
                if os.environ.get("SCH_DEBUG"):
                    quem = [f"{r}.{p}" for r, p in pinos if ponto(r, p) == pt]
                    ka = router.key(*pt)
                    kb = min(feito, key=lambda c: abs(c[0] - ka[0]) + abs(c[1] - ka[1]))

                    def _estado_r(c):
                        if c in router.blocked:
                            return "B"
                        if c in router.pin_cells and rede not in router.used.get(c, set()):
                            return "P(" + ",".join(sorted(router.used.get(c, set())))[:14] + ")"
                        outras = router.used.get(c, set()) - {rede}
                        if outras:
                            return "u(" + ",".join(sorted(outras))[:14] + ")"
                        return "."
                    n = max(abs(kb[0] - ka[0]), abs(kb[1] - ka[1]), 1)
                    linha = [(ka[0] + (kb[0] - ka[0]) * t // n, ka[1] + (kb[1] - ka[1]) * t // n)
                             for t in range(n + 1)]
                    print(f"  [debug] {nome}: {rede}: sem caminho de {quem} {pt} ate {kb}; "
                          f"reta: " + " ".join(_estado_r(c) for c in linha))
                roteou = False
                break
            router.add_path(rede, caminho)
            feito |= set(caminho)
        if not roteou:
            # the wire did not find its way inside the block: the net is
            # closed by labels instead, which is electrically the same and
            # leaves nothing open. Counted, and printed, so it is known.
            n_rotulos_por_falha += 1
            falhas.append(f"{nome}: {rede} fechada por rotulo")
            for r, p in pinos:
                _rotulo(rede, r, p, False)

    _fechar(sch, router)

    # ---- as duas bandeiras que o ERC do KiCad cobra ----
    #
    # Sem elas o ERC acusa 52 erros que nao sao erros, e um relatorio com 52
    # falsos positivos e um relatorio que ninguem le - foi por isso que este
    # projeto passou meses sem nunca ter rodado o ERC.
    #
    # 1. Pino aberto DE PROPOSITO leva bandeira de "sem conexao". Sao os
    #    NC do supressor, os GPIO que ninguem usa, o SDA e o SCL do receptor
    #    (que fala por UART), o SWO do gravador. `nets.py` ja e a fonte da
    #    verdade sobre o que esta aberto: um pino que nao aparece em rede
    #    nenhuma esta aberto, e ponto.
    # Uma rede de UM pino so nao liga nada: e um pino aberto com nome. O
    # R111, que era o pull-up do IRQ do colhedor antigo, virou isso quando a
    # peca mudou - e o ERC, com razao, chamou de pino sem ligacao. Em
    # 2026-09-26 o R111 saiu da lista; a regra fica, para o proximo.
    com_no = {(r, q.number) for rede, pinos_r in N.NETS.items()
              if len(pinos_r) > 1
              for r, p in pinos_r if S.sheet_of(r) == nome
              for q in P.PARTS[r].pins if q.name == p or q.number == p}
    for ref in refs:
        peca = P.PARTS[ref]
        folha_pinos = peca.pin_sheet()
        # Pontos onde JA existe um pino ligado. Simbolo da biblioteca do
        # KiCad empilha pinos - os quatro VBUS do USB-C num ponto so, o pad
        # exposto do colhedor sobre o AGND -, e por um desses pontos a rede
        # ja passa. Uma bandeira de "sem conexao" ali seria mentira, e o ERC
        # a chama de `no_connect_connected`.
        ligados = {folha_pinos[n] for n in folha_pinos if (ref, n) in com_no}
        for num, xy in folha_pinos.items():
            if (ref, num) not in com_no and xy not in ligados:
                sch.no_connects.append(xy)
                ligados.add(xy)      # um so por ponto, nunca dois empilhados

    # 2. Trilho alimentado atraves de peca passiva nao tem fonte que o ERC
    #    enxergue: o 3V0_GNSS vem do 3V0 por um ferrite, o SD3V0_FLASH vem
    #    do SD3V0 por um jumper, o VIN do colhedor vem do painel. O PWR_FLAG
    #    e o simbolo que existe para dizer "esta alimentado, eu respondo por
    #    isso".
    #
    #    UMA por rede NO PROJETO INTEIRO. Duas bandeiras na mesma rede sao
    #    duas saidas de alimentacao ligadas entre si, que e outro erro de
    #    ERC - e uma rede que atravessa folhas ganharia uma em cada. Por isso
    #    `precisa_de_flag` e calculado uma vez, fora daqui, e cada folha so
    #    coloca as que lhe couberem.
    #    The flag shares the point of the rail's first power symbol on the
    #    sheet and hangs under it, the rail's arrow and name going up and
    #    the flag's going down: on the pin tip itself it printed over the
    #    pin's neighbours and over the rail symbol's stub.
    for rede in sorted(FLAGS_AQUI.get(nome, ())):
        if rede in simbolo_da_rede:
            px, py, sentido_f = simbolo_da_rede[rede]
            sentido_f = CONTRARIO[sentido_f]
        else:
            px, py = ponto(*pinos_do_no(rede, nome)[0])
            sentido_f = "U"
        sch.powers.append(PowerPort("PWR_FLAG", px, py, ground=False,
                                    ref=f"#FLG{len(sch.powers) + 1:03d}",
                                    sentido=sentido_f))

    # inside the frame, above the first row of blocks (which start at
    # MARGEM + 14); at MARGEM - 8 it printed over the sheet's border
    sch.text(MARGEM, MARGEM + 4.0,
             f"{nome} - {len(refs)} posicoes. NADA MONTADO NEM MEDIDO.", 2.5)
    return sch, falhas, len(refs)


def _mais_a_esquerda(rede: str, folha: str, w_pag: float) -> bool:
    pts = [ponto(r, p) for r, p in pinos_do_no(rede, folha)]
    if not pts:
        return True
    return sum(p[0] for p in pts) / len(pts) < w_pag / 2.0


def _fechar(sch: Schematic, router: Router) -> None:
    """Cut every run at the points its own net touches, then dot the branches.

    KiCad joins two wires only where they share an END: a run that stops in
    the middle of another one does not connect, junction dot or not.
    """
    segs = list(router.segs)
    nos: dict[str, set[tuple[float, float]]] = {}
    for a, b, n in segs:
        nos.setdefault(n, set()).update({(round(a[0], 3), round(a[1], 3)),
                                         (round(b[0], 3), round(b[1], 3))})
    partidos = []
    for a, b, n in segs:
        pontos = [a, b]
        for k in nos.get(n, ()):
            if abs(a[1] - b[1]) < 1e-6 and abs(k[1] - a[1]) < 1e-6 \
                    and min(a[0], b[0]) < k[0] < max(a[0], b[0]):
                pontos.append(k)
            elif abs(a[0] - b[0]) < 1e-6 and abs(k[0] - a[0]) < 1e-6 \
                    and min(a[1], b[1]) < k[1] < max(a[1], b[1]):
                pontos.append(k)
        pontos.sort(key=lambda p: (p[0], p[1]))
        for i in range(len(pontos) - 1):
            if pontos[i] != pontos[i + 1]:
                partidos.append((pontos[i], pontos[i + 1], n))
    sch.wires += [(a, b) for a, b, _n in partidos]

    contagem: dict[tuple[float, float], dict[str, int]] = {}
    for a, b, n in partidos:
        for p in (a, b):
            k = (round(p[0], 3), round(p[1], 3))
            contagem.setdefault(k, {}).setdefault(n, 0)
            contagem[k][n] += 1
    for k, donos in contagem.items():
        if any(c >= 3 for c in donos.values()) and \
                len(router.used.get(router.key(*k), set())) == 1:
            sch.junctions.append(k)


def main() -> int:
    # The footprint field is what ties the schematic to the board: without it
    # KiCad cannot update the layout from the schematic at all.
    for ref, (nome, _origem, _nota) in FPS.FP.items():
        P.PARTS[ref].footprint = nome
    for ref in FPS.FORA_DA_PLACA:
        P.PARTS[ref].note = (P.PARTS[ref].note + " | FORA DA PLACA: "
                             "vive na caixa e chega por contato ou cabo").strip(" |")

    tipo, _folhas = S.classificar()

    # How big each block has to be, and therefore how big the sheet is. The
    # blocks were a fixed 190 x 240 mm on a 370 x 350 mm pitch, which spans
    # 990 x 680 and forces A0 - for a diagram of six rectangles and the lines
    # between them. A block only has to hold its title and its pins: the pins
    # go two per row at 4 grid steps, and the widest pin NAME decides the
    # width. Measured, the diagram fits on A2.
    entre_raiz = sorted(n for n, k in tipo.items() if k == "ENTRE")
    pinos_por_folha: dict[str, list[str]] = {n: [] for n, _f, _p in S.FOLHAS}
    for rede in entre_raiz:
        for folha in sorted({S.sheet_of(r) for r, _p in N.NETS[rede]}):
            pinos_por_folha[folha].append(rede)
    n_max = max(len(v) for v in pinos_por_folha.values())
    letra = max((len(r) for v in pinos_por_folha.values() for r in v),
                default=8)
    # Two grid steps between pins, not four. Four is a 5,08 mm slot for a
    # 1,27 mm label, and on the MCU block - 33 crossing signals - it alone
    # made the block 116 mm tall and pushed the diagram off A3 onto A2.
    PASSO_PINO = 2 * GRID
    bloco_h = snap(20.0 + ((n_max + 1) // 2) * PASSO_PINO + 10.0)
    # the pin name is drawn inside the block, from each side
    bloco_w = snap(max(70.0, 2 * (letra * 2.1) + 24.0))
    passo_x = bloco_w + 34.0
    passo_y = bloco_h + 30.0
    largura = 30.0 + 1 * passo_x + bloco_w + 30.0
    altura = 40.0 + passo_y + bloco_h + 20.0
    papel_raiz = "A0"
    for nome_p in ORDEM:
        w, h = PAPEIS[nome_p]
        if largura <= w and altura <= h:
            papel_raiz = nome_p
            break

    raiz = Schematic(PROJETO, papel_raiz,
                     title="Bike Power Meter - diagrama de blocos",
                     rev="A", date=DATA)

    # the four blocks, two rows of two
    blocos: list[SheetSymbol] = []
    for i, (nome, arquivo, pagina) in enumerate(S.FOLHAS):
        col, lin = i % 2, i // 2
        blocos.append(SheetSymbol(nome, arquivo,
                                  x=snap(30.0 + col * passo_x),
                                  y=snap(40.0 + lin * passo_y),
                                  w=bloco_w, h=bloco_h, page=pagina))
    raiz.sheets = blocos
    por_nome = {b.name: b for b in blocos}

    # one pin per crossing signal on each block it touches
    entre = sorted(n for n, k in tipo.items() if k == "ENTRE")
    contador: dict[str, int] = {b.name: 0 for b in blocos}
    for rede in entre:
        for folha in sorted({S.sheet_of(r) for r, _p in N.NETS[rede]}):
            b = por_nome[folha]
            i = contador[folha]
            contador[folha] += 1
            lado = 180 if (i % 2 == 0) else 0
            py = snap(b.y + 10.0 + (i // 2) * PASSO_PINO)
            b.pins.append((rede, py, lado, "bidirectional"))

    # Quais redes precisam de PWR_FLAG, e em que folha cada uma recebe a sua.
    #
    # Precisa quem tem pino de ENTRADA de alimentacao e nenhum de saida em
    # lugar nenhum do projeto: um trilho que chega por ferrite, por jumper ou
    # de fora da placa. A folha escolhida e a primeira, em ordem, que tenha
    # um pino daquela rede - assim a bandeira fica perto de onde a rede vive.
    FLAGS_AQUI.clear()
    # Duas redes que compartilham um PINO sao uma so para o KiCad. Acontece
    # de proposito nos conectores que atravessam sinal - o do display leva o
    # FPC_VSS de um lado e o GND do outro pelo mesmo contato -, e sem juntar
    # antes de contar, cada lado ganharia a sua bandeira e as duas brigariam
    # como duas saidas de alimentacao ligadas entre si.
    grupo: dict[str, str] = {}

    def _raiz(n: str) -> str:
        while grupo.get(n, n) != n:
            n = grupo[n]
        return n

    por_pino: dict[tuple[str, str], str] = {}
    for rede, pinos_r in N.NETS.items():
        grupo.setdefault(rede, rede)
        for r, pi in pinos_r:
            num = next(q.number for q in P.PARTS[r].pins
                       if q.name == pi or q.number == pi)
            outro = por_pino.setdefault((r, num), rede)
            if _raiz(outro) != _raiz(rede):
                grupo[_raiz(rede)] = _raiz(outro)

    tipos_do_grupo: dict[str, list[str]] = {}
    for rede, pinos_r in N.NETS.items():
        g = _raiz(rede)
        tipos_do_grupo.setdefault(g, []).extend(
            P.PARTS[r].etype_de(
                next(q.number for q in P.PARTS[r].pins
                     if q.name == pi or q.number == pi)) for r, pi in pinos_r)

    feitos: set[str] = set()
    for rede, pinos_r in N.NETS.items():
        g = _raiz(rede)
        if g in feitos:
            continue
        tipos = tipos_do_grupo[g]
        if "power_out" in tipos or "output" in tipos:
            continue
        # Um trilho SEMPRE tem entrada de alimentacao, mesmo quando todos os
        # pinos de peca nele sao passivos: o proprio simbolo de alimentacao
        # que o carrega e um pino `power_in`. Era o caso do VBAT_CELULA, que
        # so toca o conector da bateria e um jumper, e do 3V0_BLOCO, entre o
        # jumper e o ferrite.
        if "power_in" not in tipos and rede not in S.TRILHOS:
            continue
        for folha_n, _a, _pg in S.FOLHAS:
            if any(S.sheet_of(r) == folha_n for r, _pi in pinos_r):
                FLAGS_AQUI.setdefault(folha_n, set()).add(rede)
                feitos.add(g)
                break
    if os.environ.get("SCH_DEBUG"):
        print("  [debug] PWR_FLAG por folha:",
              {f: sorted(v) for f, v in FLAGS_AQUI.items()})

    todas: list[tuple[str, Schematic]] = []
    falhas: list[str] = []
    for nome, arquivo, pagina in S.FOLHAS:
        sch, f, _n = montar_folha(nome, arquivo, pagina, raiz.uuid,
                                  por_nome[nome].uuid, tipo)
        todas.append((arquivo, sch))
        falhas += f

    # the root's own wiring: a line between the two blocks each signal joins
    r_router = Router([])
    r_router.build_obstacles()
    for b in blocos:
        for kx in range(r_router.key(b.x, 0)[0], r_router.key(b.x + b.w, 0)[0] + 1):
            for ky in range(r_router.key(0, b.y)[1], r_router.key(0, b.y + b.h)[1] + 1):
                r_router.blocked.add((kx, ky))
    # A sheet pin is a connection point like any other: a wire that merely
    # passes over one joins that signal. They have to be reachable and, to
    # every other net, closed.
    for b in blocos:
        for n, py, ang, _s in b.pins:
            k = r_router.key(*b.pin_pos(n))
            r_router.blocked.discard(k)
            r_router.pin_cells.add(k)
    # Fan-out. Every sheet pin gets a short straight stub before the router
    # takes over, and each stub is a different length, so the turns happen in
    # different columns. Without it the first net to turn takes the corner
    # cell next to the block and the pin behind it can no longer be reached.
    stubs: dict[tuple[str, str], tuple[float, float]] = {}
    for b in blocos:
        for i, (n, py, ang, _s) in enumerate(b.pins):
            px, _ = b.pin_pos(n)
            dx = -1 if ang == 180 else 1
            comp = 2 + (i % 10)
            fim = (px + dx * comp * GRID, py)
            raiz.wires.append(((px, py), fim))
            for k in range(comp + 1):
                cel = r_router.key(px + dx * k * GRID, py)
                r_router.used.setdefault(cel, set()).add(n)
                r_router.dirs.setdefault(cel, {}).setdefault(n, set()).add("H")
                r_router.blocked.discard(cel)
            stubs[(b.name, n)] = fim

    for rede in entre:
        pontos = [stubs[(por_nome[f].name, rede)]
                  for f in sorted({S.sheet_of(r) for r, _p in N.NETS[rede]})]
        feito = {r_router.key(*pontos[0])}
        r_router.used.setdefault(r_router.key(*pontos[0]), set()).add(rede)
        for pt in pontos[1:]:
            caminho = None
            for folga in (120, 400, 1200):
                caminho = r_router.route(rede, pt, feito, folga)
                if caminho is not None:
                    break
            if caminho is None:
                falhas.append(f"raiz: {rede}")
                continue
            r_router.add_path(rede, caminho)
            feito |= set(caminho)
    _fechar(raiz, r_router)
    raiz.text(25.0, 22.0,
              "Trilhos de alimentacao e terra viajam por simbolo de "
              "alimentacao, nao por linha. NADA FOI MONTADO NEM MEDIDO.", 2.2)

    (HERE / "pmeter.kicad_sch").write_text(raiz.render(), encoding="utf-8", newline="\n")
    for arquivo, sch in todas:
        (HERE / arquivo).write_text(sch.render(), encoding="utf-8", newline="\n")

    print(f"raiz + {len(todas)} folhas")
    for (arquivo, sch), (nome, _f, _p) in zip(todas, S.FOLHAS):
        print(f"  {arquivo}: {sch.paper}, {len(sch.parts)} pecas, "
              f"{len(sch.powers)} simbolos de alimentacao, "
              f"{len(sch.labels)} rotulos, {len(sch.wires)} fios")
    por_rotulo = [f for f in falhas if "fechada por rotulo" in f]
    reais = [f for f in falhas if "fechada por rotulo" not in f]
    if por_rotulo:
        print(f"  fechadas por rotulo em vez de fio (o labirinto nao passou): "
              f"{len(por_rotulo)}")
        for f in por_rotulo[:10]:
            print(f"    {f}")
    if reais:
        print(f"  NAO ROTEADOS: {len(reais)}")
        for f in reais[:10]:
            print(f"    {f}")
    return 1 if reais else 0


if __name__ == "__main__":
    sys.exit(main())
