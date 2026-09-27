#!/usr/bin/env python3
"""Which way each footprint faces, measured from the footprint itself.

A connector that comes out of the case has a mating face, and putting it on
the board turned the wrong way is not something a DRC catches: the board
passes every rule and the cable does not fit. This measures, for every
footprint, where its pads sit, where its body sits and which sides the
silkscreen leaves open, and prints it so the rotation of each part can be
argued from a number instead of from memory.

Read it as: FRENTE is the side of the footprint, in its own coordinates, that
has to end up facing out of the board.

Run: python hardware_powermeter/cad/orientacao.py
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import footprints as FPS  # noqa: E402
import fp_load  # noqa: E402
import make_pcb as MP  # noqa: E402

# Which way each edge-facing part has to look, in BOARD coordinates, and why.
# +Y is down the board, toward the bottom edge; +X is right.
PARA_ONDE: dict[str, tuple[str, str]] = {
    "U201": ("+X", "a antena do modulo tem de olhar para fora da borda direita "
                   "(ficha ME54BS13 V1.0.0, 7.2)"),
    "J102": ("-X", "a boca do conector da celula olha para a ponta esquerda da "
                   "placa: a celula fica sob a placa com as abas nessa ponta, e "
                   "o fio dobra em volta da ponta para entrar (docs/02, Pod)"),
}

DIR = {"+X": (1, 0), "-X": (-1, 0), "+Y": (0, 1), "-Y": (0, -1)}


def medir(nome: str) -> dict:
    """Pad box, body box and which sides the silkscreen leaves open."""
    texto = fp_load.carregar(nome)[0]
    arv = fp_load.parse(texto)
    px = []
    py = []
    for p in fp_load.kids(arv, "pad"):
        at = fp_load.kid(p, "at")
        s = fp_load.kid(p, "size")
        x, y = float(at[1]), float(at[2])
        px += [x - float(s[1]) / 2, x + float(s[1]) / 2]
        py += [y - float(s[2]) / 2, y + float(s[2]) / 2]
    fx = []
    fy = []
    sx = []
    sy = []
    for chave in ("fp_line", "fp_rect", "fp_poly", "fp_circle", "fp_arc"):
        for g in fp_load.kids(arv, chave):
            lay = fp_load.kid(g, "layer")
            if not lay:
                continue
            alvo = None
            if lay[1] in ("F.Fab", "B.Fab"):
                alvo = (fx, fy)
            elif lay[1] in ("F.SilkS", "B.SilkS"):
                alvo = (sx, sy)
            if alvo is None:
                continue
            for tag in ("start", "end", "center", "mid"):
                q = fp_load.kid(g, tag)
                if q:
                    alvo[0].append(float(q[1]))
                    alvo[1].append(float(q[2]))
    def caixa(a, b):
        return (min(a), min(b), max(a), max(b)) if a else None
    return {"pads": caixa(px, py), "corpo": caixa(fx, fy), "silk": caixa(sx, sy)}


def frente_do_footprint(nome: str, m: dict) -> tuple[str, str]:
    """Guess the mating face, and say what the guess is based on.

    For a connector the contacts leave at the BACK, so the side of the body
    farthest from the pads is the front. It is a rule of thumb and it is
    printed as such: every one of these was then checked against the part's
    own drawing.
    """
    corpo, pads = m["corpo"], m["pads"]
    if not corpo or not pads:
        return ("?", "sem contorno mecanico no footprint")
    cx = (corpo[0] + corpo[2]) / 2
    cy = (corpo[1] + corpo[3]) / 2
    ax = (pads[0] + pads[2]) / 2
    ay = (pads[1] + pads[3]) / 2
    dx, dy = cx - ax, cy - ay
    if abs(dx) >= abs(dy):
        return ("+X" if dx > 0 else "-X",
                f"o corpo esta {abs(dx):.2f} mm a {'direita' if dx > 0 else 'esquerda'} "
                f"do centro dos pads")
    return ("+Y" if dy > 0 else "-Y",
            f"o corpo esta {abs(dy):.2f} mm {'abaixo' if dy > 0 else 'acima'} "
            f"do centro dos pads")


def girar(d: str, ang: int, atras: bool = False) -> str:
    """Where a footprint direction points once the board places the part.

    Two transforms, in this order: a part on the back face is mirrored in x,
    and then the whole thing turns by the stored angle. Doing it with the
    vector instead of with a list of names is what keeps the mirror honest -
    a mirrored part turns the other way round.
    """
    import math as _m
    dx, dy = DIR[d]
    if atras:
        dx = -dx
    r = _m.radians(ang)
    nx = dx * _m.cos(r) + dy * _m.sin(r)
    ny = -dx * _m.sin(r) + dy * _m.cos(r)
    for nome, (vx, vy) in DIR.items():
        if abs(nx - vx) < 1e-6 and abs(ny - vy) < 1e-6:
            return nome
    return "?"


def main() -> int:
    print(f"{'ref':6} {'rot':>4}  {'frente do fp':12} {'vira para':10} "
          f"{'pedido':8}  situacao")
    ruim = 0
    for ref, (quer, porque) in PARA_ONDE.items():
        nome = FPS.FP[ref][0]
        m = medir(nome)
        f, base = frente_do_footprint(nome, m)
        ang = MP.BORDA_FIXA.get(ref, (0, 0, 0))[2]
        atras = ref in MP.ATRAS
        vira = girar(f, ang, atras) if f != "?" else "?"
        ok = vira == quer
        ruim += 0 if ok else 1
        print(f"{ref:6} {ang:>4}{'T' if atras else ' '} {f:12} {vira:10} {quer:8}  "
              f"{'ok' if ok else 'ERRADO'}")
        print(f"         {base}")
        print(f"         {porque}")
        if not ok and f != "?":
            certo = next((a for a in (0, 90, 180, 270)
                          if girar(f, a, atras) == quer), None)
            print(f"         a rotacao que resolve e {certo}")
    print()
    print(f"{ruim} de {len(PARA_ONDE)} pecas viradas para o lado errado")
    return 1 if ruim else 0


if __name__ == "__main__":
    sys.exit(main())
