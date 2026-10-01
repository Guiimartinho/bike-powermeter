#!/usr/bin/env python3
"""Close the connections the DRC still calls open, on the finished board.

Why a separate pass. route.py has two routing stages and both keep their own
books: the sequential one counts connections it found, the negotiated one
counts connections whose path it planned. Neither of those numbers is what
the fabricator cares about, and on 2026-09-28 they disagreed with reality -
the negotiated stage reported 96 connections and 0 contested cells while
eleven pads had no copper at all, among them every terminal of USB_DM. A
stage cannot be the judge of its own output.

So the judge here is KiCad. This reads `_drc_all.json`, takes the pairs it
calls unconnected, rebuilds the grid from the copper that is actually on the
board, and routes each of those pairs with the same A* route.py uses - which
means the same clearances, the same widths and the same pad necks. What it
cannot close it says so, by net and by pad, and leaves alone: copper drawn
blind across a finished board is worse than a missing connection, because
the missing one is visible.

    "D:/KiCAD/bin/kicad-cli.exe" pcb drc --severity-all --format json \
        -o _drc_all.json pmeter.kicad_pcb
    python hardware_powermeter/cad/reparar.py

Run it after fill_zones.py, and fill the zones again afterwards: this adds
copper, and a pour is only valid for the copper it was poured around.
"""
from __future__ import annotations

import json
import math
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import route as R                                        # noqa: E402
import fp_load                                           # noqa: E402

PLACA = HERE / "pmeter.kicad_pcb"
RELATORIO = HERE / "_drc_all.json"

# The user layer names make_pcb.py writes, and the index route.py uses.
# The router has THREE layers, not four: In1.Cu is the ground plane and
# nothing is routed on it (route.CAMADAS). Measured on 2026-09-28 - mapping
# B.Cu to 3 made every search on the back layer fail silently, which is why
# the first run of this file could not close a gap of 1,7 mm.
CAMADA_POR_NOME = {"top_cu": 0, "F.Cu": 0,
                   "pwr": 1, "In2.Cu": 1,
                   "bottom_cu": 2, "B.Cu": 2}

PAT_SEG = re.compile(
    r'\(segment\s+\(start ([-\d.]+) ([-\d.]+)\)\s+\(end ([-\d.]+) ([-\d.]+)\)\s+'
    r'\(width ([-\d.]+)\)\s+\(layer "([^"]+)"\)(?:\s+\(locked [a-z]+\))?\s+\(net (\d+)\)')
PAT_VIA = re.compile(
    r'\(via\s+\(at ([-\d.]+) ([-\d.]+)\)\s+\(size ([-\d.]+)\)\s+\(drill ([-\d.]+)\)\s+'
    r'\(layers "([^"]+)" "([^"]+)"\)(?:[^()]|\([^()]*\))*?\(net (\d+)\)')
PAT_NET = re.compile(r'\(net (\d+) "([^"]*)"\)')

IDX_POR_CAMADA = {"F.Cu": 0, "In2.Cu": 1, "B.Cu": 2}


def cobre_da_placa(texto: str):
    """The tracks and vias already on the board, in route.py's own format."""
    nomes = {int(m.group(1)): m.group(2) for m in PAT_NET.finditer(texto)}
    orx, ory = R.MP.ORIGEM
    segmentos = []
    fora = set()
    for m in PAT_SEG.finditer(texto):
        rede = nomes.get(int(m.group(7)), "")
        if m.group(6) not in IDX_POR_CAMADA:
            fora.add(m.group(6))
            continue
        segmentos.append(((float(m.group(1)) - orx, float(m.group(2)) - ory),
                          (float(m.group(3)) - orx, float(m.group(4)) - ory),
                          IDX_POR_CAMADA[m.group(6)], rede, float(m.group(5))))
    if fora:
        raise SystemExit("ha trilha numa camada que o roteador nao usa "
                         f"({', '.join(sorted(fora))}): este passe reescreve "
                         "todas as trilhas e as perderia")
    vias = []
    for m in PAT_VIA.finditer(texto):
        rede = nomes.get(int(m.group(7)), "")
        vias.append((float(m.group(1)) - orx, float(m.group(2)) - ory, rede))
    return segmentos, vias


def pares_abertos(relatorio: pathlib.Path):
    """The DRC's unconnected items, as (net, (x, y, layer), (x, y, layer))."""
    if not relatorio.is_file():
        raise SystemExit(f"nao achei {relatorio.name}: rode o DRC antes "
                         "(a instrucao esta no topo deste arquivo)")
    dados = json.loads(relatorio.read_text(encoding="utf-8"))
    abertos = dados.get("unconnected_items", [])
    pares = []
    for v in abertos:
        pontas = []
        for it in v.get("items", []):
            d = it.get("description", "")
            p = it.get("pos", {})
            m = re.search(r"\[([^\]]+)\]", d)
            if not m or "x" not in p:
                continue
            cam = None
            for nome, idx in CAMADA_POR_NOME.items():
                if re.search(r"\b" + re.escape(nome) + r"\b", d):
                    cam = idx
                    break
            pontas.append((m.group(1), float(p["x"]), float(p["y"]), cam))
        if len(pontas) == 2 and pontas[0][0] == pontas[1][0]:
            pares.append((pontas[0][0], pontas[0][1:], pontas[1][1:]))
        elif len(pontas) == 2:
            # the two ends carry different net names, which happens when one
            # of them is a pad of a net that only touches this one through a
            # component: nothing to route, and saying so beats guessing
            print(f"  ignorado: {pontas[0][0]} e {pontas[1][0]} "
                  "sao redes diferentes", flush=True)
    return pares


def celulas_da_ponta(g, todos, rede, ponta):
    """Every cell that counts as this end of the connection.

    A pad is the whole pad, not its centre cell: the A* has to be allowed to
    arrive anywhere inside it, and on a 0,5 mm pitch the centre cell is often
    the only one that is NOT reachable.
    """
    x, y, cam = ponta
    orx, ory = R.MP.ORIGEM
    bx, by = x - orx, y - ory
    # is there a pad of this net whose rectangle holds the point?
    for nome, idx, px, py, hw, hh in todos:
        if nome != rede:
            continue
        qx, qy = px - orx, py - ory
        if abs(qx - bx) <= hw + 1e-6 and abs(qy - by) <= hh + 1e-6:
            camadas = range(R.NC) if idx < 0 else (idx,)
            saida = set()
            a0 = g.cel(qx - hw, qy - hh)
            a1 = g.cel(qx + hw, qy + hh)
            for c in camadas:
                for ix in range(a0[0], a1[0] + 1):
                    for iy in range(a0[1], a1[1] + 1):
                        saida.add((c, ix, iy))
            return saida, (qx, qy), True
    c0, c1 = g.cel(bx, by)
    camadas = (cam,) if cam is not None else range(R.NC)
    return {(c, c0, c1) for c in camadas}, (bx, by), False


def celulas_do_cobre(g, segmentos, vias):
    """Every cell each net's copper already covers, by net.

    The DRC names two ends, but a connection does not have to be made
    between exactly those two: a pad only has to reach its net, wherever the
    net is nearest. Aiming at the whole net instead of at the named end is
    what closes a connection whose named end sits in a corner with no room
    for a via.
    """
    por_rede: dict = {}
    for p0, p1, cam, rede, w in segmentos:
        a0 = g.cel(min(p0[0], p1[0]), min(p0[1], p1[1]))
        a1 = g.cel(max(p0[0], p1[0]), max(p0[1], p1[1]))
        alvo = por_rede.setdefault(rede, set())
        for ix in range(a0[0], a1[0] + 1):
            for iy in range(a0[1], a1[1] + 1):
                # Only a cell whose CENTRE is inside the run's copper, and
                # by half the narrowest track: a path that ends on a cell
                # merely NEAR the run does not touch it, and KiCad still
                # counts the connection open. Measured on 2026-09-28 with
                # `w / 2 + PASSO` here: six connections the pass reported
                # closed were all still open in the DRC.
                x, y = g.pos(ix, iy)
                if _dist_ponto_seg(x, y, p0, p1) <= max(0.0, w / 2 - R.LARGURA / 2):
                    alvo.add((cam, ix, iy))
    for vx, vy, rede in vias:
        ix, iy = g.cel(vx, vy)
        alvo = por_rede.setdefault(rede, set())
        for c in range(R.NC):
            alvo.add((c, ix, iy))
    return por_rede


def _dist_ponto_seg(x, y, p0, p1):
    ax, ay = p0
    bx, by = p1
    dx, dy = bx - ax, by - ay
    n = dx * dx + dy * dy
    k = 0.0 if n <= 1e-12 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / n))
    return math.hypot(x - (ax + k * dx), y - (ay + k * dy))


def campos_da_rede(g, por_rede, caixa_fp, rede):
    campos = []
    for q in por_rede.get(rede, ()):
        b = caixa_fp.get((round(q[2], 4), round(q[3], 4)))
        if not b:
            b = (q[2] - q[4], q[3] - q[5], q[2] + q[4], q[3] + q[5])
        a0 = g.cel(b[0] - R.MP.ORIGEM[0] - R.EXTRA_CAMPO,
                   b[1] - R.MP.ORIGEM[1] - R.EXTRA_CAMPO)
        a1 = g.cel(b[2] - R.MP.ORIGEM[0] + R.EXTRA_CAMPO,
                   b[3] - R.MP.ORIGEM[1] + R.EXTRA_CAMPO)
        campos.append((a0[0], a0[1], a1[0], a1[1]))
    return campos


def emitir(g, caminho, rede, larg, larg_pad, campos):
    """The path as segments and vias, with the same neck rule as route.py."""
    segmentos, vias = [], []

    def no_campo(k: int) -> bool:
        _c, ix, iy = caminho[k]
        return any(x0 <= ix <= x1 and y0 <= iy <= y1 for x0, y0, x1, y1 in campos)

    i = 0
    while i < len(caminho) - 1:
        a = caminho[i]
        j = i + 1
        if caminho[j][0] != a[0]:
            x, y = g.pos(a[1], a[2])
            vias.append((x, y, rede))
            g.via(x, y, rede, R.folga_de(rede))
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
            g.trilha(a[0], p0, p1, w, rede, R.folga_de(rede))
            k0 = k1
        i = j
    return segmentos, vias


def main() -> int:
    texto = PLACA.read_text(encoding="utf-8")
    arv = fp_load.parse(texto)
    numeros = fp_load.redes_da_placa(arv)
    todos, por_rede, caixa_fp = R.pads_da_placa(arv)
    segmentos, vias = cobre_da_placa(texto)
    print(f"placa com {len(segmentos)} segmentos e {len(vias)} vias", flush=True)

    pares = pares_abertos(RELATORIO)
    print(f"{len(pares)} ligacoes abertas no relatorio do DRC", flush=True)
    if not pares:
        return 0

    # the grid with everything that is already there
    g = R.base(arv, todos)
    for p0, p1, cam, rede, w in segmentos:
        g.trilha(cam, p0, p1, w, rede, R.folga_de(rede))
    for vx, vy, rede in vias:
        g.via(vx, vy, rede, R.folga_de(rede))

    cobre_cel = celulas_do_cobre(g, segmentos, vias)

    # quantos pares a placa JA tem pela nossa medida, antes de qualquer
    # conserto: e a linha de base contra a qual cada conserto e julgado
    antes_ruins = len(R.conferir(segmentos, vias, todos))
    if antes_ruins:
        print(f"a placa ja tem {antes_ruins} par(es) que a nossa medida acusa "
              "e o DRC do KiCad aceita; o conserto e julgado contra isso",
              flush=True)
    fechadas, falhas = 0, []
    for rede, a, b in pares:
        if rede == "GND":
            # the ground net is not routed here and never was: it lives on
            # the pours of F.Cu, In1.Cu and B.Cu, which this grid does not
            # model. An open GND pad is a missing stitching via, and that is
            # route.py's ground pass, not this one.
            falhas.append(f"{rede}: e do plano, nao deste passe "
                          f"(falta via de costura perto de ({a[0]:.1f}; {a[1]:.1f}))")
            continue
        campos = campos_da_rede(g, por_rede, caixa_fp, rede)
        cel_a, pos_a, pad_a = celulas_da_ponta(g, todos, rede, a)
        cel_b, pos_b, pad_b = celulas_da_ponta(g, todos, rede, b)
        if cel_a & cel_b:
            print(f"  {rede}: as duas pontas caem na mesma celula, nada a fazer",
                  flush=True)
            continue
        # The search always STARTS at a pad. Measured on 2026-09-28: starting
        # at the track end instead, with the whole net as the target, finds a
        # target one cell away - on that very track - and emits a stub that
        # joins the track to itself. Five connections were "closed" that way
        # and the DRC still counted all eleven. A pad that the DRC calls
        # unconnected touches no copper of its net by definition, so anything
        # it reaches is a real new connection.
        if not pad_a and not pad_b:
            falhas.append(f"{rede}: nenhuma das duas pontas e um pad "
                          f"(({pos_a[0]:.1f}; {pos_a[1]:.1f}) e "
                          f"({pos_b[0]:.1f}; {pos_b[1]:.1f}))")
            continue
        if not pad_a:
            cel_a, pos_a, cel_b, pos_b = cel_b, pos_b, cel_a, pos_a
        larg = R.largura(rede)
        estreito = min((min(2 * q[4], 2 * q[5]) for q in por_rede.get(rede, ())),
                       default=larg)
        larg_pad = max(R.LARGURA, min(larg, estreito - R.PASSO))
        so_camada = 0 if rede in R.SO_FRENTE else None
        # aim at the whole net, not only at the end the DRC named
        vizinhos = {(c, ix + dx, iy + dy) for c, ix, iy in cel_a
                    for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
        alvo_set = (cel_b | cobre_cel.get(rede, set())) - vizinhos
        achou = None
        if alvo_set:
            for inicio in sorted(cel_a):
                p = R.a_estrela(g, rede, inicio, alvo_set, campos=campos,
                                so_camada=so_camada, larg_estreita=larg_pad)
                if p and len(p) > 1:
                    achou = p
                    break
        if not achou:
            d = math.hypot(pos_a[0] - pos_b[0], pos_a[1] - pos_b[1])
            falhas.append(f"{rede}: sem caminho de ({pos_a[0]:.1f}; {pos_a[1]:.1f}) "
                          f"a ({pos_b[0]:.1f}; {pos_b[1]:.1f}), {d:.1f} mm")
            continue
        s, v = emitir(g, achou, rede, larg, larg_pad, campos)
        if not s and not v:
            falhas.append(f"{rede}: o caminho saiu sem cobre nenhum")
            continue
        # MEASURE what was just drawn, against everything already there,
        # before keeping it. Measured on 2026-09-28: this pass closed four
        # connections and gave the board four SHORTS (UART_RX to GND,
        # SPI_MOSI to 3V0), three crossing tracks and two holes drilled in
        # the same place - from 4 real DRC violations to 13. A pass that
        # repairs by breaking is worse than one that leaves the gap, because
        # the gap is visible and the short is not.
        # O que importa e o que o conserto ACRESCENTA, nao o que a placa ja
        # tinha. Comparando o total, este passe recusava um caminho perfeito
        # porque a placa ja carregava 62 pares que a nossa medida (mais
        # estrita que o DRC) acusa e o KiCad aceita - medido em 2026-10-01,
        # com a ultima ligacao da placa, o `CHG_N`.
        depois = R.conferir(segmentos + s, vias + v, todos)
        if len(depois) > antes_ruins:
            novos = len(depois) - antes_ruins
            falhas.append(f"{rede}: o conserto criaria {novos} problema(s) de "
                          f"geometria a mais ({depois[-1][:70]}); nao foi "
                          "desenhado")
            continue
        segmentos += s
        vias += v
        cobre_cel[rede] = cobre_cel.get(rede, set()) | set(achou)
        fechadas += 1
        print(f"  {rede}: fechada com {len(s)} trilhas e {len(v)} vias, "
              f"de ({pos_a[0]:.1f}; {pos_a[1]:.1f})", flush=True)

    print(f"{fechadas} de {len(pares)} ligacoes fechadas", flush=True)
    for f in falhas:
        print("  NAO FECHOU  " + f, flush=True)

    if fechadas:
        R.escrever(PLACA, texto, numeros, segmentos, vias)
        print(f"placa gravada com {len(segmentos)} segmentos e {len(vias)} vias",
              flush=True)
        print("  rode fill_zones.py e o DRC de novo", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
