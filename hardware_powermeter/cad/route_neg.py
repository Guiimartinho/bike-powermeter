#!/usr/bin/env python3
"""Negotiated congestion routing: the stage that closes what order cannot.

route.py draws one net at a time, and a net that finds its way takes the
channel the next one needed. Re-ordering only moves the failure: measured on
this board on 2026-09-27, every ordering and every rip-up variant landed
within two connections of the same number, and so did every board size from
55 to 78 mm of length and 16 to 18 of width. Twenty-four connections short
is not a shortage of copper, it is the method.

What fixes it is the method every real router uses (McMurchie and Ebeling,
1995, "PathFinder"): let every net take the path it wants, even where
another net already is, and then charge for the crowding and do it again.
A cell that two nets want gets more expensive each round, so one of them
gives way - and which one gives way is decided by how much the detour costs
that net, not by who was drawn first.

The loop:

  1. rip everything up;
  2. route every connection, allowed to share cells, paying
     `base * (1 + historico) * (1 + presente)`;
  3. find the cells more than one net is using;
  4. if there are none the board is routed - otherwise raise the history of
     those cells and go back to 1.

`presente` makes a net avoid a cell someone is using right now; `historico`
remembers that the cell has been fought over, which is what stops the two
nets from swapping places for ever.

This module only routes. route.py keeps the pads, the grid, the widths, the
ground stubs and the stitching, and calls this when its own passes leave
something open.
"""

from __future__ import annotations

import heapq
import math

# How hard a cell that someone else is using costs right now, and how much
# a contested cell remembers. The two numbers are the classic ones: a
# present cost big enough that a net prefers a detour of a few cells, and a
# history that grows slowly so the search does not thrash.
# The pressure GROWS from round to round, which is the part that makes the
# loop end. With a fixed pressure two nets that want the same cell keep
# swapping places: measured on 2026-09-27, forty rounds all closed 108 of
# the 110 connections and never got the contested cells below thirty. A
# pressure that rises makes sharing steadily less affordable than the
# detour, so the board settles.
PRESENTE_0 = 0.5
PRESENTE_FATOR = 1.6
HISTORICO = 1.0
MAX_RODADAS = 60


def _custo_passo(v, atual, ant, CUSTO_VIA, CUSTO_CURVA, CUSTO_CURVA_45):
    """The same geometry cost route.a_estrela uses: via, diagonal, corner."""
    c, ix, iy = atual
    if v[0] != c:
        return CUSTO_VIA
    passo = 2.2 if (v[1] != ix and v[2] != iy) else 1.0
    if ant is not None and v[0] == c and ant[0] == c:
        d1 = (ix - ant[1], iy - ant[2])
        d2 = (v[1] - ix, v[2] - iy)
        if d1 != d2:
            reto = (d1[0] == 0) != (d2[0] == 0) or (d1[1] == 0) != (d2[1] == 0)
            passo += (CUSTO_CURVA if (d1[0] and d1[1]) == (d2[0] and d2[1])
                      and reto else CUSTO_CURVA_45)
    return passo


def rotear(R, g, rede, inicio, alvos, uso, hist, campos_cel, larg_estreita,
           so_camada=None, perto_de=None, orcamento=400000,
           pressao=PRESENTE_0, duro=False, off_uso=((0, 0),),
           off_via_olha=((0, 0),), vias_postas=None):
    """A* that may cross another net, for a price.

    The price is what makes the whole thing work, so it is worth being
    exact about what is and is not allowed: a PAD of another net is solid
    and is never crossed - copper that is already there cannot move. What
    may be shared is the space another net's TRACK is using, because that
    track can be drawn somewhere else in the next round.
    """
    if inicio in alvos:
        return [inicio]
    off = R._disco_off(R.extra_de(rede))
    off_estreito = ((0, 0),)

    def _off(ix, iy):
        if campos_cel:
            for x0, y0, x1, y1 in campos_cel:
                if x0 <= ix <= x1 and y0 <= iy <= y1:
                    return off_estreito
        return off

    def ocupada(k, _o):
        """Is another net's copper-plus-clearance where this one wants to be?

        Asked with THIS net's half width: the other net already marked its
        own clearance, so the two together are exactly the distance the
        DRC requires.
        """
        c, ix, iy = k
        for dx, dy in off_uso:
            outros = uso.get((c, ix + dx, iy + dy))
            if outros and (outros - {rede}):
                return True
        return False

    def solido(k, o):
        """A pad of another net, or a keep-out: never passable.

        The grid this runs on is built by route.base() alone - pads, holes
        and keep-outs - and no track is ever marked on it, so everything
        in it is copper that cannot move. What CAN move is in `uso`, and
        that is charged for instead of forbidden.
        """
        c, ix, iy = k
        for dx, dy in o:
            d = g.t.get((c, ix + dx, iy + dy))
            if d is not None and d != rede:
                return True
        return duro and ocupada(k, o)

    def preco(k, _o):
        """What sharing this cell costs: who is there now, and its history."""
        c, ix, iy = k
        n = 0
        for dx, dy in off_uso:
            cel = (c, ix + dx, iy + dy)
            outros = uso.get(cel)
            if outros:
                n += len(outros - {rede})
        h = hist.get(k, 0.0)
        return (1.0 + h) * (1.0 + pressao * n) if (n or h) else 1.0

    tx = sum(t[1] for t in alvos) / len(alvos)
    ty = sum(t[2] for t in alvos) / len(alvos)
    fila = [(abs(inicio[1] - tx) + abs(inicio[2] - ty), 0.0, inicio, None)]
    veio = {}
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
        vizinhos = [(c, ix + 1, iy), (c, ix - 1, iy), (c, ix, iy + 1),
                    (c, ix, iy - 1)]
        for dx, dy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            a, b = (c, ix + dx, iy), (c, ix, iy + dy)
            if not solido(a, _off(a[1], a[2])) and not solido(b, _off(b[1], b[2])):
                vizinhos.append((c, ix + dx, iy + dy))
        if so_camada is None:
            vizinhos += [(k, ix, iy) for k in range(R.NC) if k != c]
        for v in vizinhos:
            if v in veio or not g.dentro(v[1], v[2]):
                continue
            o = _off(v[1], v[2])
            if solido(v, o):
                continue
            if v[0] != c:
                if not g.cabe_via(v[1], v[2], rede):
                    continue
                # two vias may not share a hole, not even on the same net
                if vias_postas is not None:
                    n_v = int(math.ceil((R.VIA_D + R.FOLGA) / R.PASSO))
                    perto_via = False
                    for dx2 in range(-n_v, n_v + 1):
                        for dy2 in range(-n_v, n_v + 1):
                            if math.hypot(dx2, dy2) * R.PASSO > R.VIA_D + R.FOLGA:
                                continue
                            if (v[1] + dx2, v[2] + dy2) in vias_postas:
                                perto_via = True
                                break
                        if perto_via:
                            break
                    if perto_via:
                        continue
                # and nobody else's copper may be within the via's own
                # radius, on any layer
                ocupado_via = False
                for cam in range(R.NC):
                    for dx, dy in off_via_olha:
                        quem = uso.get((cam, v[1] + dx, v[2] + dy))
                        if quem and (quem - {rede}):
                            ocupado_via = True
                            break
                    if ocupado_via:
                        break
                if ocupado_via and duro:
                    continue
            passo = _custo_passo(v, atual, ant, R.CUSTO_VIA, R.CUSTO_CURVA,
                                 R.CUSTO_CURVA_45)
            passo *= preco(v, o)
            if perto_de is not None and (v[1], v[2]) in perto_de:
                passo *= 0.35
            novo = custo + passo
            if novo < melhor.get(v, float("inf")):
                melhor[v] = novo
                h = abs(v[1] - tx) + abs(v[2] - ty)
                heapq.heappush(fila, (novo + h, novo, v, atual))
    return None


def _disco(R, raio):
    """The cell offsets inside a radius, in grid steps."""
    n = int(math.ceil(raio / R.PASSO))
    return tuple((dx, dy) for dx in range(-n, n + 1) for dy in range(-n, n + 1)
                 if math.hypot(dx, dy) * R.PASSO <= raio + 1e-9)


def _marcar(uso, celulas, off, rede, R=None, off_via=None):
    ant = None
    for c, ix, iy in celulas:
        for dx, dy in off:
            uso.setdefault((c, ix + dx, iy + dy), set()).add(rede)
        # a change of layer is a via: 0,45 mm of copper through the board,
        # so it takes its own disc on every layer, not the track's halo
        if off_via is not None and ant is not None and ant[0] != c:
            for cam in range(R.NC):
                for dx, dy in off_via:
                    uso.setdefault((cam, ix + dx, iy + dy), set()).add(rede)
        ant = (c, ix, iy)


def rodar(R, arv, numeros, todos, por_rede, caixa_fp, ordem_redes):
    """The whole loop. Returns (segmentos, vias, falhas, n_ok, rodadas)."""
    g = R.base(arv, todos)
    hist: dict = {}
    melhor_saida = None
    pressao = PRESENTE_0
    for rodada in range(MAX_RODADAS):
        # the last quarter negotiates no more: sharing is simply forbidden
        duro = rodada >= MAX_RODADAS - max(3, MAX_RODADAS // 4)
        uso: dict = {}
        vias_postas: set = set()
        caminhos_por_rede: dict = {}
        falhas: list[str] = []
        sufocados: list = []
        n_ok = 0
        for rede in ordem_redes:
            pads = por_rede.get(rede, [])
            if len(pads) < 2:
                continue
            estreitos = [min(2 * q[4], 2 * q[5]) for q in pads]
            if rede in R.PAR:
                estreitos = [min(e, R.LARGURA) for e in estreitos]
            celulas = []
            for _n, idx, x, y, _hw, _hh in pads:
                c0, c1 = g.cel(x - R.MP.ORIGEM[0], y - R.MP.ORIGEM[1])
                celulas.append({(c, c0, c1)
                                for c in (range(R.NC) if idx < 0 else (idx,))})
            campos_cel = []
            for q in pads:
                b = caixa_fp.get((round(q[2], 4), round(q[3], 4)))
                if not b:
                    b = (q[2] - q[4], q[3] - q[5], q[2] + q[4], q[3] + q[5])
                a0 = g.cel(b[0] - R.MP.ORIGEM[0] - R.EXTRA_CAMPO,
                           b[1] - R.MP.ORIGEM[1] - R.EXTRA_CAMPO)
                a1 = g.cel(b[2] - R.MP.ORIGEM[0] + R.EXTRA_CAMPO,
                           b[3] - R.MP.ORIGEM[1] + R.EXTRA_CAMPO)
                campos_cel.append((a0[0], a0[1], a1[0], a1[1]))
            larg_rede = R.largura(rede)
            # what this net's copper and its clearance occupy, and what it
            # has to ask with when it looks at someone else's
            # half a grid step of margin on every disc: the cells are a
            # discrete set and the nearest one can be that much further
            # out than the true nearest point of the copper. Without it
            # the DRC found six clearance errors, all just under the
            # limit, on a board the model called clean (2026-09-27).
            # The margin goes on what a net MARKS, and it is a third of a
            # grid step: the cells are a discrete set, so the nearest one
            # can be that much further out than the copper really is.
            # Half a step on BOTH the mark and the look was tried and cost
            # eighteen connections (2026-09-27).
            m = R.PASSO / 2.0
            off_marca = _disco(R, larg_rede / 2.0 + R.folga_de(rede) + m)
            off_olha = _disco(R, larg_rede / 2.0)
            off_via_marca = _disco(R, R.VIA_D / 2.0 + R.folga_de(rede) + m)
            off_via_olha = _disco(R, R.VIA_D / 2.0)
            feito = set(celulas[0])
            caminhos_por_rede.setdefault(rede, [])
            restantes = list(range(1, len(celulas)))

            def _perto(k):
                cl = next(iter(celulas[k]))
                return min((abs(cl[1] - c[1]) + abs(cl[2] - c[2]) for c in feito),
                           default=0)

            while restantes:
                restantes.sort(key=_perto)
                k = restantes.pop(0)
                alvo = celulas[k]
                if alvo & feito:
                    continue
                larg = R.largura(rede)
                larg_pad = max(R.LARGURA, min(larg, estreitos[k] - R.PASSO))
                so_camada = 0 if rede in R.SO_FRENTE else None
                p = rotear(R, g, rede, next(iter(alvo)), feito, uso, hist,
                           campos_cel, larg_pad, so_camada=so_camada,
                           pressao=pressao, duro=duro, off_uso=off_olha,
                           off_via_olha=off_via_olha, vias_postas=vias_postas)
                if p is None:
                    c0 = next(iter(alvo))
                    falhas.append(
                        f"{rede}: sem caminho ate ({c0[1] * R.PASSO:.1f}; "
                        f"{c0[2] * R.PASSO:.1f}) na camada {c0[0]}")
                    # push: the way out of this pad is worth more to
                    # everybody than whatever is parked around it
                    sufocados.append(c0)
                    for c2 in feito:
                        sufocados.append(c2)
                        break
                    continue
                caminhos_por_rede[rede].append((p, larg, larg_pad, campos_cel))
                _marcar(uso, p, off_marca, rede, R=R, off_via=off_via_marca)
                ant_v = None
                for cel_v in p:
                    if ant_v is not None and ant_v[0] != cel_v[0]:
                        vias_postas.add((cel_v[1], cel_v[2]))
                    ant_v = cel_v
                feito |= set(p)
                n_ok += 1

        # The real question is the DRC's: does any net's centre line fall
        # inside another net's copper-plus-clearance? Asked after every
        # net is down, because a net drawn early never saw the late ones.
        disputadas = []
        for rede_c, caminhos_c in caminhos_por_rede.items():
            larg_c = R.largura(rede_c)
            olha_c = _disco(R, larg_c / 2.0)
            via_c = _disco(R, R.VIA_D / 2.0)
            for caminho_c, _l, _lp, _cc in caminhos_c:
                ant_c = None
                for c, ix, iy in caminho_c:
                    bateu = False
                    for dx, dy in olha_c:
                        quem = uso.get((c, ix + dx, iy + dy))
                        if quem and (quem - {rede_c}):
                            disputadas.append((c, ix, iy))
                            bateu = True
                            break
                    if not bateu and ant_c is not None and ant_c[0] != c:
                        for cam in range(R.NC):
                            for dx, dy in via_c:
                                quem = uso.get((cam, ix + dx, iy + dy))
                                if quem and (quem - {rede_c}):
                                    disputadas.append((c, ix, iy))
                                    bateu = True
                                    break
                            if bateu:
                                break
                    ant_c = (c, ix, iy)
        if melhor_saida is None or (len(disputadas), len(falhas)) < melhor_saida[0]:
            melhor_saida = ((len(disputadas), len(falhas)), caminhos_por_rede,
                            list(falhas), n_ok, rodada + 1)
        print(f"    rodada {rodada + 1}{' (sem partilha)' if duro else ''}: "
              f"{n_ok} ligacoes, {len(falhas)} sem caminho, "
              f"{len(disputadas)} celulas disputadas", flush=True)
        if rodada + 1 == MAX_RODADAS or (not disputadas and not falhas):
            for f in falhas[:8]:
                print("      " + f, flush=True)
            for c in disputadas[:8]:
                quem = ", ".join(sorted(uso[c]))
                print(f"      disputada: camada {c[0]} em "
                      f"({c[1] * R.PASSO:.1f}; {c[2] * R.PASSO:.1f}) "
                      f"entre {quem}", flush=True)
        if not disputadas and not falhas:
            break
        for c in disputadas:
            hist[c] = hist.get(c, 0.0) + HISTORICO * 2.0
        # and the neighbourhood of every connection that found no way
        raio_sufoco = _disco(R, 1.2)
        for c, ix, iy in sufocados:
            for dx, dy in raio_sufoco:
                k = (c, ix + dx, iy + dy)
                hist[k] = hist.get(k, 0.0) + HISTORICO
        pressao *= PRESENTE_FATOR
    return melhor_saida
