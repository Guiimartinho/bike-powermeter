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

import math
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

    # Pad de terra que NAO conseguiu via: liga por um toco ao cobre de terra
    # mais perto, na propria camada.
    #
    # A `terra()` so sabe por via, e via precisa de lugar. Quando nao ha, o
    # pad fica aberto - e sete das dezesseis ligacoes em aberto da placa de
    # 2026-10-01 eram isso, inclusive DOIS PINOS DE TERRA VIZINHOS do mesmo
    # `U101` que nao se tocavam. Dois pinos a 0,5 mm um do outro nao precisam
    # de via nenhuma: precisam de meio milimetro de cobre. E se um deles
    # alcanca o plano, o outro alcanca junto.
    n_toco = 0
    orx, ory = R.MP.ORIGEM
    gnd = [q for q in todos if q[0] == "GND" and q[1] >= 0]
    por_camada: dict = {}
    for s in segmentos:
        por_camada.setdefault(s[2], []).append(s)

    def ligado(x, y, hw, hh, idx) -> bool:
        for vx, vy, rede in vias:
            if rede == "GND" and abs(vx - x) <= hw + R.VIA_D / 2 and                     abs(vy - y) <= hh + R.VIA_D / 2:
                return True
        for s in por_camada.get(idx, ()):
            if s[3] != "GND":
                continue
            for q in (s[0], s[1]):
                if abs(q[0] - x) <= hw + s[4] / 2 + 0.02 and                         abs(q[1] - y) <= hh + s[4] / 2 + 0.02:
                    return True
        return False

    for nome, idx, px, py, hw, hh in gnd:
        x, y = px - orx, py - ory
        if ligado(x, y, hw, hh, idx):
            continue
        # o cobre de terra mais perto na MESMA camada: outro pad ou uma ponta
        alvos = []
        for n2, i2, qx, qy, h2, k2 in gnd:
            if (n2, i2, qx, qy) == (nome, idx, px, py) or i2 != idx:
                continue
            if ligado(qx - orx, qy - ory, h2, k2, i2):
                alvos.append((math.hypot(qx - orx - x, qy - ory - y),
                              (qx - orx, qy - ory)))
        for s in por_camada.get(idx, ()):
            if s[3] != "GND":
                continue
            for q in (s[0], s[1]):
                alvos.append((math.hypot(q[0] - x, q[1] - y), q))
        alvos = [a for a in alvos if a[0] <= 2.5]
        alvos.sort()
        larg = max(R.LARGURA, min(R.LARGURA_ALIM, 2 * hw, 2 * hh))
        for _d, q in alvos[:12]:
            if R.toco_limpo((x, y), q, idx, "GND", larg, segmentos, todos,
                            vias):
                continue
            segmentos.append(((x, y), q, idx, "GND", larg))
            por_camada.setdefault(idx, []).append(segmentos[-1])
            n_toco += 1
            break
    if n_toco:
        print(f"{n_toco} pad(s) de terra ligados por toco ao cobre vizinho",
              flush=True)

    # E MEDIR o que foi acrescentado, contra tudo o que ja estava la. A
    # `terra()` decide pela grade, e a grade e uma aproximacao: quem julga
    # geometria e a `conferir`, que mede cobre contra cobre.
    # E RETIRAR o que saiu sujo. Ate 2026-10-01 esta parte media, imprimia
    # "89 pares perto demais" e gravava a placa assim mesmo: o Freerouting
    # entregava ZERO erro de DRC e este arquivo devolvia 123, sendo 59
    # curtos. Deteccao sem consequencia nao e verificacao.
    #
    # Sai sempre o que ESTE arquivo desenhou, nunca o que veio do roteador:
    # a costura e' dispensavel item a item (o pad alcanca o plano pelo
    # despejo da propria face), e um curto na placa fabricada nao e.
    n_fora = 0
    for _volta in range(400):
        ruins = R.conferir(segmentos, vias, todos)
        if not ruins:
            break
        import re as _re
        culpado = None
        for texto_r in ruins:
            mp = _re.search(r"\(em ([-\d.]+); ([-\d.]+)\)", texto_r)
            if not mp:
                mp = _re.search(r" em \(([-\d.]+); ([-\d.]+)\)", texto_r)
            if not mp:
                continue
            px, py = float(mp.group(1)), float(mp.group(2))
            # a via de costura mais perto do ponto, entre as que nos pusemos
            melhor, dmin = None, 1e9
            for k in range(len(via_ja), len(vias)):
                d = math.hypot(vias[k][0] - px, vias[k][1] - py)
                if d < dmin:
                    melhor, dmin = ("v", k), d
            for k in range(len(seg_ja), len(segmentos)):
                s = segmentos[k]
                d = min(math.hypot(s[0][0] - px, s[0][1] - py),
                        math.hypot(s[1][0] - px, s[1][1] - py))
                if d < dmin:
                    melhor, dmin = ("s", k), d
            if melhor is not None:
                culpado = melhor
                break
        if culpado is None:
            break
        if culpado[0] == "v":
            vias.pop(culpado[1])
        else:
            segmentos.pop(culpado[1])
        n_fora += 1
    if n_fora:
        print(f"  {n_fora} item(ns) da costura RETIRADO(s) por ficarem perto "
              "demais do cobre do roteador", flush=True)
    ruins = R.conferir(segmentos, vias, todos)
    if ruins:
        print(f"  ainda {len(ruins)} par(es) perto demais, e nenhum deles e "
              "da costura:", flush=True)
        for r in ruins[:4]:
            print("    " + r, flush=True)

    # O `em_45_graus` vale SO' para o que este arquivo desenhou, nunca para
    # o que o roteador desenhou. Passado em tudo, ele reescrevia as trilhas
    # do Freerouting - que produz trechos fora de 45 graus, como ele mesmo
    # avisa ("Invalid traces after autoroute: N traces not 45 degree") - e
    # cada uma virava um "L" que ia parar noutro lugar. Medido em 2026-10-01:
    # a placa saia do Freerouting com ZERO erro e deste arquivo com 123,
    # sendo 59 curtos e 59 pontes de mascara, quase todos de trilhas de 3V0
    # no verso cruzando pad alheio.
    novos = segmentos[len(seg_ja):]
    segmentos = seg_ja + em_45_graus(novos)
    R.escrever(PLACA, texto, numeros, segmentos, vias)
    print(f"{PLACA.name}: {len(segmentos)} trilhas e {len(vias)} vias",
          flush=True)
    print("  rode fill_zones.py e o DRC: eles continuam sendo os juizes",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
