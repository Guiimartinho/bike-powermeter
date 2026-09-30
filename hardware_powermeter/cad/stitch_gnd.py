#!/usr/bin/env python3
"""So a costura do plano de terra, sobre a placa que o roteador ja desenhou.

    python hardware_powermeter/cad/stitch_gnd.py

Roda DEPOIS do `autoroute.py`, e a ordem foi medida, nao escolhida.

O Freerouting roteia redes; um PLANO nao e rede dele, entao ele nao poe via
de costura nenhuma. Na primeira placa que ele roteou, em 2026-09-30, das 28
ligacoes que o DRC deu como abertas 18 eram pads de GND sem via ate o plano
interno - as outras 10 eram as que ele mesmo declarou nao ter roteado.

A tentativa obvia era costurar ANTES, com a placa vazia, onde a via sempre
cabe. Nao da: com cobre ja no arquivo, o Freerouting roda, anuncia "Saving
'...ses'" e grava um arquivo de ZERO BYTE - duas execucoes inteiras foram
perdidas ate isso ficar claro. Entao a costura vem depois, e para caber ela
precisa enxergar o que ele desenhou: as trilhas e vias que ja estao na placa
sao marcadas na grade antes de qualquer via nova ser procurada.

O trabalho e o do `route.terra()`, `route.costurar()` e
`route.costurar_area()`, que continuam sendo os donos das regras (folga do
furo, corredor livre ate o pad, vao maximo da costura).
"""
from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fp_load                                             # noqa: E402
import reparar as RP                                       # noqa: E402
import route as R                                          # noqa: E402

PLACA = HERE / "pmeter.kicad_pcb"


def em_45_graus(segmentos: list) -> list:
    """Reescreve cada toco como um trecho de 45 graus mais um reto.

    `route.terra()` liga o pad a via em linha reta, e a via foi encaixada na
    grade: o angulo que sobra e qualquer um. O KiCad aceita, mas o
    Freerouting recusa a placa inteira - ele avisa "Invalid traces after
    autoroute: N traces not 45 degree". Aqui isso nao chega a importar,
    porque a costura vem depois dele; fica pelo desenho, que e como se
    desenha placa, e para o dia em que a ordem mudar.
    """
    saida = []
    for p0, p1, cam, rede, w in segmentos:
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        m = min(abs(dx), abs(dy))
        if m < 1e-9 or abs(abs(dx) - abs(dy)) < 1e-9:
            saida.append((p0, p1, cam, rede, w))   # ja e reto ou ja e 45
            continue
        sx = 1.0 if dx > 0 else -1.0
        sy = 1.0 if dy > 0 else -1.0
        canto = (p0[0] + sx * m, p0[1] + sy * m)
        saida.append((p0, canto, cam, rede, w))
        saida.append((canto, p1, cam, rede, w))
    return saida


def areas_de_regra(texto: str) -> list:
    """As areas `keepout` da placa, como retangulos em coordenada local.

    A do no de chaveamento nasce na hora de escrever a placa, a partir da
    colocacao, e por isso nao esta no `make_dxf` - so' esta no arquivo.
    """
    import re
    orx, ory = R.MP.ORIGEM
    saida = []
    # `(zone` e quebra de linha, SEM espaco: um bloco de zona do KiCad abre
    # assim, e procurar "(zone " com espaco nao achava nenhuma (2026-09-30).
    for bloco in texto.split("\n\t(zone")[1:]:
        if "(keepout" not in bloco:
            continue
        pts = [(float(a), float(b)) for a, b in
               re.findall(r"\(xy ([-\d.]+) ([-\d.]+)\)", bloco)]
        if not pts:
            continue
        xs = [q[0] - orx for q in pts]
        ys = [q[1] - ory for q in pts]
        saida.append((min(xs), min(ys), max(xs), max(ys)))
    return saida


def main() -> int:
    texto = PLACA.read_text(encoding="utf-8")
    arv = fp_load.parse(texto)
    numeros = fp_load.redes_da_placa(arv)
    todos, por_rede, _caixa = R.pads_da_placa(arv)

    # o que ja esta na placa, e que a grade tem de conhecer
    seg_ja, via_ja = RP.cobre_da_placa(texto)
    print(f"placa com {len(seg_ja)} trilhas e {len(via_ja)} vias do roteador",
          flush=True)

    # O cobre que ja esta la e marcado com a folga de FURO, nao com a de
    # cobre. Uma via de 0,40 com furo de 0,20 tem a borda do furo a 0,10 do
    # centro; se ela parar a folga de cobre (0,10) de uma trilha de 0,09, o
    # furo fica a 0,19 dela e o `min_hole_clearance` do projeto pede 0,20.
    # Foram 78 erros de uma vez em 2026-09-30, todos por essa casa decimal.
    R.AREAS_DO_ARQUIVO = areas_de_regra(texto)
    print(f"{len(R.AREAS_DO_ARQUIVO)} area(s) de regra lidas da placa",
          flush=True)
    folga_furo = max(R.FOLGA_FURO, R.FOLGA)
    g = R.base(arv, todos)
    for p0, p1, cam, rede, w in seg_ja:
        g.trilha(cam, p0, p1, w, rede, folga_furo)
    for vx, vy, rede in via_ja:
        g.via(vx, vy, rede, folga_furo)

    segmentos = list(seg_ja)
    vias = list(via_ja)
    falhas: list = []
    n_gnd = R.terra(g, por_rede, segmentos, vias, falhas, todos)
    n_borda = R.costurar(g, vias)
    n_malha = R.costurar_area(g, vias)
    print(f"{n_gnd} pads de terra com via propria ao plano, "
          f"{n_borda} vias de costura na borda, {n_malha} na malha da area",
          flush=True)
    for f in falhas[:4]:
        print("  " + f, flush=True)
    if len(falhas) > 4:
        print(f"  ... e mais {len(falhas) - 4}", flush=True)

    # E MEDIR o que foi acrescentado, contra tudo o que ja estava la. A
    # `terra()` decide pela grade, e a grade e uma aproximacao: quem julga
    # geometria e a `conferir`, que mede cobre contra cobre.
    ruins = R.conferir(segmentos, vias, todos)
    if ruins:
        print(f"  {len(ruins)} par(es) perto demais depois da costura:",
              flush=True)
        for r in ruins[:4]:
            print("    " + r, flush=True)

    segmentos = em_45_graus(segmentos)
    R.escrever(PLACA, texto, numeros, segmentos, vias)
    print(f"{PLACA.name}: {len(segmentos)} trilhas e {len(vias)} vias",
          flush=True)
    print("  rode fill_zones.py e o DRC: eles continuam sendo os juizes",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
