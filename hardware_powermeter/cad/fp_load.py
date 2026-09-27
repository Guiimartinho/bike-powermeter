#!/usr/bin/env python3
"""Read a footprint, from the KiCad library or from the ones generated here.

Gives back the text ready to be embedded in a board, the courtyard size that
placement needs, and the pad names, which have to match the symbol's pin
numbers or the board will be wired wrong.
"""

from __future__ import annotations

import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import footprints as FPS  # noqa: E402

LIB = pathlib.Path(r"D:\KiCAD\share\kicad\footprints")


def _tokens(text: str):
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "()":
            yield c
            i += 1
        elif c == '"':
            j, buf = i + 1, []
            while j < n:
                if text[j] == "\\":
                    buf.append(text[j + 1])
                    j += 2
                    continue
                if text[j] == '"':
                    break
                buf.append(text[j])
                j += 1
            yield ("str", "".join(buf))
            i = j + 1
        elif c.isspace():
            i += 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in '()"':
                j += 1
            yield ("sym", text[i:j])
            i = j


def parse(text: str) -> list:
    stack: list[list] = [[]]
    for t in _tokens(text):
        if t == "(":
            stack.append([])
        elif t == ")":
            pronto = stack.pop()
            stack[-1].append(pronto)
        else:
            stack[-1].append(t[1])
    return stack[0][0]


def kids(node, name):
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


def kid(node, name):
    got = kids(node, name)
    return got[0] if got else None


_cache: dict[str, tuple[str, tuple[float, float], list[str]]] = {}
# the real courtyard, not the symmetric one: x0, y0, x1, y1 around the
# footprint origin. It is what decides whether a capacitor can sit 0.5 mm
# from the pin it decouples, which is what the datasheets ask for.
CAIXA: dict[str, tuple[float, float, float, float]] = {}


def carregar(nome: str) -> tuple[str, tuple[float, float], list[str]]:
    """footprint text, its courtyard size, and the pad names."""
    if nome in _cache:
        return _cache[nome]
    if nome in FPS.GERADOS:
        texto = FPS.GERADOS[nome]
    else:
        lib, base = nome.split(":", 1)
        caminho = LIB / f"{lib}.pretty" / f"{base}.kicad_mod"
        if not caminho.exists():
            raise FileNotFoundError(caminho)
        texto = caminho.read_text(encoding="utf-8")

    arv = parse(texto)
    xs: list[float] = []
    ys: list[float] = []
    for chave in ("fp_line", "fp_rect", "fp_poly", "fp_circle", "fp_arc"):
        for g in kids(arv, chave):
            camada = kid(g, "layer")
            if not camada or "CrtYd" not in camada[1]:
                continue
            if chave == "fp_circle":
                # A circle is a centre and a point ON it, not two corners.
                # Read as two points it gives half the box: the D1.0mm test
                # point has a courtyard of radius 1.0 and was read as 0.5,
                # which let TP201 and TP203 sit exactly 2.0 mm apart with
                # their courtyards touching - the one DRC error the board had.
                c, e = kid(g, "center"), kid(g, "end")
                if c and e:
                    cx_, cy_ = float(c[1]), float(c[2])
                    r_ = math.hypot(float(e[1]) - cx_, float(e[2]) - cy_)
                    xs += [cx_ - r_, cx_ + r_]
                    ys += [cy_ - r_, cy_ + r_]
                    continue
            for tag in ("start", "end", "center", "mid"):
                p = kid(g, tag)
                if p:
                    xs.append(float(p[1]))
                    ys.append(float(p[2]))
            pts = kid(g, "pts")
            if pts:
                for p in kids(pts, "xy"):
                    xs.append(float(p[1]))
                    ys.append(float(p[2]))
    pads = []
    for p in kids(arv, "pad"):
        pads.append(p[1])
        at = kid(p, "at")
        size = kid(p, "size")
        if at and size:
            px, py = float(at[1]), float(at[2])
            sw, sh = float(size[1]), float(size[2])
            xs += [px - sw / 2, px + sw / 2]
            ys += [py - sh / 2, py + sh / 2]
    if not xs:
        xs, ys = [-1.0, 1.0], [-1.0, 1.0]
    # A courtyard is not centred on the footprint origin, and a part can be
    # rotated on the board, so the size that placement may use is the
    # symmetric box around the origin: twice the furthest edge.
    tam = (2 * max(abs(min(xs)), abs(max(xs))),
           2 * max(abs(min(ys)), abs(max(ys))))
    CAIXA[nome] = (min(xs), min(ys), max(xs), max(ys))
    _cache[nome] = (texto, tam, pads)
    return _cache[nome]


def _tira_propriedade(texto: str, nome_prop: str) -> str:
    """Remove a whole (property "X" ...) block, matching its parentheses.

    The board writes its own Reference and Value for each part. If the
    library's are left in the body, they come after and win, and every part on
    the board ends up called REF**.
    """
    alvo = f'(property "{nome_prop}"'
    while True:
        i = texto.find(alvo)
        if i < 0:
            return texto
        d, j = 0, i
        while j < len(texto):
            if texto[j] == '"':
                j += 1
                while j < len(texto) and texto[j] != '"':
                    j += 2 if texto[j] == "\\" else 1
            elif texto[j] == "(":
                d += 1
            elif texto[j] == ")":
                d -= 1
                if d == 0:
                    break
            j += 1
        inicio = texto.rfind("\n", 0, i) + 1
        texto = texto[:inicio] + texto[j + 1:].lstrip("\n")


def corpo(nome: str) -> str:
    """The footprint's body, without the leading (footprint "name" and the )."""
    texto = carregar(nome)[0]
    i = texto.index("\n")
    corpo = texto[i:].rstrip()
    assert corpo.endswith(")")
    corpo = corpo[:-1].rstrip()
    for prop in ("Reference", "Value", "Footprint", "Datasheet", "Description"):
        corpo = _tira_propriedade(corpo, prop)
    return FPS.trocar_modelo(nome, corpo)


if __name__ == "__main__":
    import parts as P
    falhas = []
    for ref, (nome, origem, _n) in sorted(FPS.FP.items()):
        try:
            _t, tam, pads = carregar(nome)
        except FileNotFoundError as exc:
            falhas.append(f"{ref}: {exc}")
            continue
        pinos = {q.number for q in P.PARTS[ref].pins}
        pads_s = set(pads)
        if not pinos <= pads_s:
            falhas.append(f"{ref} ({nome}): pinos sem pad {sorted(pinos - pads_s)}")
    print(f"{len(FPS.FP)} footprints lidos, {len(falhas)} problemas")
    for f in falhas:
        print("  " + f)


def redes_da_placa(arv) -> dict[str, int]:
    """Net name -> number, read from the board's OWN net table.

    route.py and dry_run_pcb.py used to take the numbers from nets.py at
    run time. That is the same table only while nets.py does not change
    between the board being generated and the script running - and on
    2026-09-26 it did change, mid-chain: one net added ahead of GND moved
    every number after it by one, the router wrote its ground vias with the
    new number into a file that used the old one, and the checker counted
    7 ground vias where there were 316. The file is the truth about itself.
    """
    out: dict[str, int] = {}
    for n in kids(arv, "net"):
        if len(n) >= 3 and n[2] != "":
            out[n[2]] = int(n[1])
    return out
