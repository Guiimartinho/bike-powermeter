#!/usr/bin/env python3
"""Desenha o desenho de MONTAGEM: cada peca com o seu designador, sem duvida.

Neither of KiCad's layers gives a readable assembly drawing of this board.

  F.SilkS is real silkscreen, so it obeys manufacturing: 0,6 mm of text, and
  127 designators on a 34 x 90 mm board at 48% occupancy simply do not fit
  around the parts without landing on one another or drifting so far from
  the part that they name nothing.

  F.Fab carries whatever each library footprint happens to put there, at
  whatever size that footprint's author chose, plus the value - so it prints
  "TP110" at 1,0 mm next to "100 nF" at 0,5 and both over the outline.

An assembly drawing is not a copper layer. It is a drawing, and it is
allowed to do the one thing a silkscreen cannot: put the label where it is
readable and draw a LINE from the label to the part. That line is what makes
a displaced designator unambiguous, and it is why this file exists.

    python hardware_powermeter/cad/montagem.py

Sai `pmeter-montagem.pdf`, duas paginas: frente e verso.
"""
from __future__ import annotations

import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import make_dxf as M  # noqa: E402
import make_pcb as MP  # noqa: E402

MM = 72.0 / 25.4              # pontos por milimetro
MARGEM = 46.0                 # pontos
FONTE = "helv"
ALT_MIN = 4.2                 # pontos: abaixo disso nao se le impresso
ALT_MAX = 9.0
FOLGA = 1.2                   # pontos entre dois rotulos


def _cruza(a, b) -> bool:
    return a[2] > b[0] and b[2] > a[0] and a[3] > b[1] and b[3] > a[1]


def _larg(texto: str, alt: float) -> float:
    import fitz
    return fitz.get_text_length(texto, fontname=FONTE, fontsize=alt)


def desenha(pag, lugar, atras: bool, esc: float, ox: float, oy: float) -> int:
    """One face: the outline, each courtyard, and each reference with a leader."""
    import fitz

    def P(x, y):
        return fitz.Point(ox + x * esc, oy + y * esc)

    # o contorno
    r = M.RADIUS_DRAWING
    pag.draw_rect(fitz.Rect(P(0, 0), P(M.W, M.H)), color=(0, 0, 0), width=1.1,
                  radius=min(0.49, r / min(M.W, M.H)))

    pecas = [(ref, v) for ref, v in sorted(lugar.items()) if v[3] == atras]
    caixas = {}
    for ref, (x, y, ang, _a) in pecas:
        bx = MP.caixa(ref, ang)
        caixas[ref] = (x + bx[0], y + bx[1], x + bx[2], y + bx[3])
        pag.draw_rect(fitz.Rect(P(caixas[ref][0], caixas[ref][1]),
                                P(caixas[ref][2], caixas[ref][3])),
                      color=(0.45, 0.45, 0.45), width=0.5)

    # os maiores primeiro: eles tem espaco dentro e liberam o anel dos outros
    ordem = sorted(pecas, key=lambda kv: -((caixas[kv[0]][2] - caixas[kv[0]][0])
                                           * (caixas[kv[0]][3] - caixas[kv[0]][1])))
    postos: list[tuple] = []
    n_chamada = 0
    for ref, _v in ordem:
        cx0, cy0, cx1, cy1 = caixas[ref]
        w_pt = (cx1 - cx0) * esc
        h_pt = (cy1 - cy0) * esc
        meio = ((cx0 + cx1) / 2, (cy0 + cy1) / 2)

        # cabe DENTRO da peca? entao e ali, sem duvida nenhuma
        alt = min(ALT_MAX, h_pt * 0.62)
        if alt >= ALT_MIN and _larg(ref, alt) <= w_pt * 0.88:
            p = P(*meio)
            cx = (p.x - _larg(ref, alt) / 2, p.y - alt * 0.36,
                  p.x + _larg(ref, alt) / 2, p.y + alt * 0.36)
            if not any(_cruza(cx, q) for q in postos):
                pag.insert_text(fitz.Point(cx[0], p.y + alt * 0.34), ref,
                                fontsize=alt, fontname=FONTE, color=(0, 0, 0))
                postos.append(cx)
                continue

        # nao cabe: vai para fora, no ponto livre mais perto, COM linha de
        # chamada. A linha e o que torna um rotulo deslocado nao ambiguo.
        alt = ALT_MIN + 0.6
        lw = _larg(ref, alt)
        achou = None
        for raio in (1.0, 1.8, 2.8, 4.0, 5.6, 7.5, 10.0, 13.0):
            for k in range(16):
                a = 2 * math.pi * k / 16
                mx = meio[0] + raio * math.cos(a)
                my = meio[1] + raio * math.sin(a)
                if not (0.5 < mx < M.W - 0.5 and 0.5 < my < M.H - 0.5):
                    continue
                p = P(mx, my)
                cx = (p.x - lw / 2 - FOLGA, p.y - alt * 0.36 - FOLGA,
                      p.x + lw / 2 + FOLGA, p.y + alt * 0.36 + FOLGA)
                if any(_cruza(cx, q) for q in postos):
                    continue
                achou = (mx, my, p, cx)
                break
            if achou:
                break
        if achou is None:
            continue
        mx, my, p, cx = achou
        # a linha vai da borda do rotulo ate a borda da peca
        a0 = P(*meio)
        pag.draw_line(fitz.Point(p.x, p.y), a0, color=(0.30, 0.30, 0.30),
                      width=0.35)
        pag.draw_circle(a0, 0.9, color=(0.30, 0.30, 0.30),
                        fill=(0.30, 0.30, 0.30))
        # o rotulo por cima da linha, em caixa branca para nao se misturar
        pag.draw_rect(fitz.Rect(cx[0], cx[1], cx[2], cx[3]),
                      color=None, fill=(1, 1, 1))
        pag.insert_text(fitz.Point(p.x - lw / 2, p.y + alt * 0.34), ref,
                        fontsize=alt, fontname=FONTE, color=(0, 0, 0))
        postos.append(cx)
        n_chamada += 1
    return n_chamada


def main() -> int:
    try:
        import fitz
    except ImportError:
        print("PyMuPDF nao esta instalado", file=sys.stderr)
        return 2

    lugar, falhas = MP.colocar()
    if falhas:
        print("colocacao com falhas: " + "; ".join(falhas[:3]), file=sys.stderr)

    doc = fitz.open()
    total = 0
    for atras, titulo in ((False, "Montagem - frente"), (True, "Montagem - verso")):
        pag = doc.new_page(width=595, height=842)
        esc = min((595 - 2 * MARGEM) / (M.W * MM),
                  (842 - 2 * MARGEM - 30) / (M.H * MM)) * MM
        ox = (595 - M.W * esc) / 2
        oy = MARGEM + 22
        pag.insert_text(fitz.Point(MARGEM, MARGEM), titulo,
                        fontsize=13, fontname="hebo")
        pag.insert_text(
            fitz.Point(MARGEM, MARGEM + 13),
            f"Bike Power Meter - placa {M.W:g} x {M.H:g} mm - "
            "NADA FABRICADO NEM MEDIDO", fontsize=8, fontname=FONTE)
        total += desenha(pag, lugar, atras, esc, ox, oy)
    saida = HERE.parent / "placa" / "pmeter-montagem.pdf"
    saida.parent.mkdir(parents=True, exist_ok=True)
    doc.save(saida, garbage=3, deflate=True)
    doc.close()
    print(f"{saida.name}: 2 paginas, {len(lugar)} pecas, "
          f"{total} com linha de chamada")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
