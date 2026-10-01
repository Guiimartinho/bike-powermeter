#!/usr/bin/env python3
"""Measure the pod against the board it is drawn around.

make_pod.py draws the pod from numbers; this file asks whether those numbers
work with the board that actually came out of the CAD chain - the real
courtyards, the real heights, the real face of every part - and with the
cell's envelope. Nothing here is asserted: every rule reads make_pod's
constants and the placed board, and a rule with nothing to measure FAILS
saying so (the bike computer's dry runs passed for days on empty boards).

The rules, with their source:
  PD1  the board fits the cavity with its play (make_pod.FOLGA_PLACA and
       CANAL_FIO)
  PD2  every part of the front face stays under the lid's underside with
       air (make_dxf.TETO_TAMPA; heights from the datasheets)
  PD3  the connector goes through the lid's window: the window covers its
       courtyard with play, and its face sits in the well, below the lid's
       top and above the lid's underside
  PD4  the back face is flat: a part with a body on the back would stand on
       the cell (docs/02, Pod: the cell under the board)
  PD5  the cell fits between the ledges and under the board with the air of
       CELULA_VAO, short of the rib, the posts and the slot
  PD6  the cell (a metal pouch) stays 5 mm from the module's antenna area
       (ME54BS13 V1.0.0, 7.4: no metal 3 to 5 mm round the antenna)
  PD7  the slot in the floor lies straight under the bridge's holes, inside
       the floor and clear of the ledges and the cell
  PD8  the posts and the ledges touch the board only where its back has no
       pad (the test points are on the back)
  PD9  the LED's light hole sits over the LED's body
  PD10 the outside stays within the envelope target of docs/02 (60 x 20 x
       8,5) - the height is measured and reported against it
  PD11 the estimated mass stays under 20 g (docs/02, Requisitos)
  PD12 the lid's lip clears every part near the board's edge

Run: python hardware_powermeter/pod/dry_run_pod.py (after make_pcb.py: it
reads cad/pmeter.kicad_pcb through make_pod.ler_placa)
"""

from __future__ import annotations

import math

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "cad"))

import make_pod as C          # noqa: E402
import make_dxf as MD         # noqa: E402
import medir as ME            # noqa: E402
import regras_medidas as RM   # noqa: E402

FOLGA_TAMPA = 0.3        # air between a part's top and the lid's underside
FOLGA_ANTENA = 5.0       # ME54BS13 V1.0.0, 7.4


def raio_do_solido(malha, cx: float, cy: float, z0: float, z1: float,
                   limite: float = 3.0) -> float:
    """O maior raio que a MALHA ocupa em volta de (cx, cy), entre z0 e z1.

    Mede o triangulo desenhado, nao a constante que o gerou. Uma regra que
    le `PARAF_PESCOCO_D` passa com o pescoco desenhado ou sem ele, e foi
    exatamente o que aconteceu ate 2026-10-01: a constante existia desde
    sempre, o ressalto saia em diametro cheio pela placa toda, e as vinte
    regras do dry run disseram que estava certo.

    Tres cuidados, todos medidos em 2026-10-01:

    - `limite` e a janela em volta do ponto. Sem ela a medida pega a parede
      do pod e devolve 105,8 mm para um pescoco de 2,0: o maior raio da
      concha e o canto oposto. 3,0 mm cobre qualquer ressalto deste pod
      (o maior tem 3,4 de diametro) e nao alcanca parede nenhuma. Se um dia
      uma nervura entrar nessa janela, a regra passa a reprovar - que e o
      lado certo para errar.
    - a banda z e ESTRITA, com 0,05 de margem: a tampa do ressalto de baixo
      fica exatamente em `PLACA_Z0`, e um triangulo plano nessa altura
      entrava na conta e media 3,4 mesmo com o pescoco desenhado.
    - devolve 0,0 quando nao achou nada, e quem chama tem de tratar isso
      como falha: um parafuso que atravessa a placa sem solido nenhum na
      altura dela nao esta desenhado.
    """
    import numpy as _np
    margem = 0.05
    maior = 0.0
    for tri in malha.tris:
        zs = tri[:, 2]
        if zs.max() <= z0 + margem or zs.min() >= z1 - margem:
            continue
        d = _np.hypot(tri[:, 0] - cx, tri[:, 1] - cy)
        if d.max() > limite:
            continue
        maior = max(maior, float(d.max()))
    return maior


def _cruza(a, b, folga=0.0) -> bool:
    return (a[0] < b[2] + folga and b[0] < a[2] + folga
            and a[1] < b[3] + folga and b[1] < a[3] + folga)


def _dentro(a, b, margem=0.0) -> bool:
    """a inside b, by at least margem."""
    return (a[0] >= b[0] + margem - 1e-9 and a[1] >= b[1] + margem - 1e-9
            and a[2] <= b[2] - margem + 1e-9 and a[3] <= b[3] - margem + 1e-9)


def f2(v):
    return f"{v:.1f}".replace(".", ",")


class Relatorio:
    def __init__(self):
        self.linhas: list[tuple[str, str, str]] = []

    def ok(self, regra, texto):
        self.linhas.append(("ok", regra, texto))

    def falha(self, regra, texto):
        self.linhas.append(("FALHA", regra, texto))

    def nao_medido(self, regra, texto):
        self.linhas.append(("nao medido", regra, texto))

    def imprimir(self) -> int:
        for estado, regra, texto in self.linhas:
            print(f"  {estado:<10} {regra}: {texto}")
        n_ok = sum(1 for e, _r, _t in self.linhas if e == "ok")
        n_f = sum(1 for e, _r, _t in self.linhas if e == "FALHA")
        n_n = sum(1 for e, _r, _t in self.linhas if e == "nao medido")
        print(f"\n{n_ok} regras medidas e cumpridas, {n_f} violadas, {n_n} nao medidas")
        return 1 if n_f else 0


def regras(pod: C.Pod, r: Relatorio) -> None:
    pecas = pod.pecas
    frente = {k: v for k, v in pecas.items() if not v["atras"]}
    tras = {k: v for k, v in pecas.items() if v["atras"]}
    placa = (C.PLACA_X0, C.PLACA_Y0, C.PLACA_X0 + C.PLACA_W, C.PLACA_Y0 + C.PLACA_H)
    cavidade = (C.PAREDE, C.PAREDE, C.W_P - C.PAREDE, C.H_P - C.PAREDE)
    celula = (C.CELULA_X0, C.CELULA_Y0, C.CELULA_X0 + C.CELULA_W, C.CELULA_Y0 + C.CELULA_H)

    # -- PD1: the board in the cavity --------------------------------------
    folgas = (placa[0] - cavidade[0], placa[1] - cavidade[1],
              cavidade[2] - placa[2], cavidade[3] - placa[3])
    if min(folgas) < C.FOLGA_PLACA - 1e-9:
        r.falha("PD1", f"a placa de {f2(C.PLACA_W)} x {f2(C.PLACA_H)} nao deixa {f2(C.FOLGA_PLACA)} "
                       f"para a parede: folgas {', '.join(f2(v) for v in folgas)}")
    elif folgas[0] < C.CANAL_FIO - 1e-9:
        r.falha("PD1", f"o canal dos fios da celula tem {f2(folgas[0])} e pede {f2(C.CANAL_FIO)}")
    else:
        r.ok("PD1", f"placa de {f2(C.PLACA_W)} x {f2(C.PLACA_H)} na cavidade de "
                    f"{f2(cavidade[2] - cavidade[0])} x {f2(cavidade[3] - cavidade[1])}: canal de "
                    f"{f2(folgas[0])} a esquerda, {f2(folgas[2])} a direita, {f2(folgas[1])} e "
                    f"{f2(folgas[3])} nos lados")

    # -- PD2: the front under the lid ----------------------------------------
    sob_tampa = {ref: p for ref, p in frente.items() if ref not in MD.ATRAVESSA_TAMPA}
    if not sob_tampa:
        r.falha("PD2", "nao mede nada: a placa nao tem peca na frente")
    else:
        altos = []
        for ref, p in sob_tampa.items():
            topo = C.PLACA_Z1 + p["altura"]
            if topo > C.TAMPA_Z0 - FOLGA_TAMPA + 1e-9:
                altos.append((ref, p["altura"], C.TAMPA_Z0 - C.PLACA_Z1 - FOLGA_TAMPA))
        mais_alta = max((p["altura"], ref) for ref, p in sob_tampa.items())
        if altos:
            r.falha("PD2", f"{len(altos)} pecas nao deixam {f2(FOLGA_TAMPA)} de ar ate a tampa: " +
                    ", ".join(f"{ref} {f2(h)} contra {f2(lim)}" for ref, h, lim in altos[:6]))
        else:
            r.ok("PD2", f"a peca mais alta sob a tampa e {mais_alta[1]} com {f2(mais_alta[0])}; o teto "
                        f"esta a {f2(C.TAMPA_Z0 - C.PLACA_Z1)} da placa, "
                        f"{f2(C.TAMPA_Z0 - C.PLACA_Z1 - mais_alta[0])} de ar")

    # -- PD3: the connector through the window --------------------------------
    j = pecas.get("J101")
    if not j:
        r.falha("PD3", "nao mede nada: o conector magnetico nao esta na placa")
    else:
        caixa = C.no_pod(j["caixa"])
        face = C.PLACA_Z1 + j["altura"]
        # O BARRILETE, nao o corpo: desde 2026-10-01 a vedacao da porta e uma
        # junta plana apoiada no OMBRO do conector, entao a janela passa o
        # barrilete com folga e a tampa cobre o ombro de proposito. Ate aqui
        # esta regra cobrava `janela >= corpo + folga`, o que e exatamente o que
        # deixava um anel aberto de 16,61 mm2 em volta da peca.
        barrilete = (caixa[0] + C.CONECTOR_OMBRO_L, caixa[1] + C.CONECTOR_OMBRO_L,
                     caixa[2] - C.CONECTOR_OMBRO_L, caixa[3] - C.CONECTOR_OMBRO_L)
        problemas = []
        if barrilete[2] <= barrilete[0] or barrilete[3] <= barrilete[1]:
            problemas.append(f"o corpo de {f2(caixa[2] - caixa[0])} x "
                             f"{f2(caixa[3] - caixa[1])} nao sobra barrilete nenhum "
                             f"depois dos {f2(C.CONECTOR_OMBRO_L)} de ombro")
        elif not _dentro(barrilete, pod.janela, C.JANELA_FOLGA):
            problemas.append("a janela nao passa o barrilete do conector com a folga")
        if face > C.T_P + 1e-9:
            problemas.append(f"a face do conector ({f2(face)}) passa do topo da tampa ({f2(C.T_P)})")
        if face < C.TAMPA_Z0 - 1e-9:
            problemas.append(f"a face do conector ({f2(face)}) fica abaixo da face de baixo da tampa "
                             f"({f2(C.TAMPA_Z0)}): o cabo nao a alcanca pela janela")
        if problemas:
            r.falha("PD3", "; ".join(problemas))
        else:
            r.ok("PD3", f"o barrilete de {f2(barrilete[2] - barrilete[0])} x "
                        f"{f2(barrilete[3] - barrilete[1])} do conector de "
                        f"{f2(j['altura'])} atravessa a janela de "
                        f"{f2(pod.janela[2] - pod.janela[0])} x {f2(pod.janela[3] - pod.janela[1])} "
                        f"com {f2(C.JANELA_FOLGA)} de folga, e a face dele fica "
                        f"{f2(pod.poco)} abaixo do topo da tampa")

    # -- PD4: what a back-face body has under it ------------------------------
    # This rule used to fail on ANY body on the back, which is not what the
    # pod is: the cell covers 23 of the board's 38 mm, and past it the floor
    # steps down - first the rib, then the bare floor. Measured on
    # 2026-09-28: the blunt rule was reporting the module's own decoupling,
    # which sits over the recessed floor with 2,0 mm of air, as standing on
    # the cell. It now measures the air under each body.
    # O ar vem MEDIDO do solido desenhado - a altura da face de cima da concha
    # e da celula em cada coluna sob a peca -, e nao de uma lista de zonas
    # escrita aqui. A lista escrita a mao nao tinha o COLAR do rasgo, e foi por
    # isso que esta regra imprimiu "as 36 pecas cabem no ar que tem sob elas"
    # com o colar atravessando o R302 e o C304 (revisao de 2026-10-01).
    import numpy as _np
    g4 = ME.grade_do_pod(C)
    sob_solido = g4.topo(g4.solido(pod.concha()) | g4.solido(pod.celula_3d()))
    corpos_tras = [(ref, p) for ref, p in tras.items() if p["altura"] > 1e-9]
    batem = []
    for ref, p in corpos_tras:
        caixa = C.no_pod(p["caixa"])
        m = g4.planta_rect(*caixa) & ~_np.isnan(sob_solido)
        topo = float(_np.nanmax(_np.where(m, sob_solido, _np.nan))) if m.any() else C.FUNDO
        ar = C.PLACA_Z0 - topo
        if p["altura"] > ar + 1e-9:
            batem.append((ref, p["altura"], ar, f"o solido em z = {f2(topo)}"))
    if not tras:
        r.falha("PD4", "nao mede nada: a placa nao tem peca na face de tras")
    elif batem:
        r.falha("PD4", f"{len(batem)} pecas da face de tras batem no que esta sob elas: " +
                ", ".join(f"{ref} tem {f2(h)} e so cabe {f2(ar)} sobre {quem}"
                          for ref, h, ar, quem in batem[:4]))
    else:
        r.ok("PD4", f"as {len(corpos_tras)} pecas com corpo da face de tras cabem no ar que tem "
                    f"sob elas (as outras {len(tras) - len(corpos_tras)} sao pads sem corpo)")

    # -- PD5: the cell between the ledges, under the board ---------------------
    entre_ressaltos = (C.PAREDE + C.RESSALTO, C.PAREDE + C.RESSALTO,
                       C.W_P - C.PAREDE - C.RESSALTO, C.H_P - C.PAREDE - C.RESSALTO)
    problemas = []
    # A celula fica AO LADO da placa desde 2026-09-30, nao sob ela: o que se
    # mede mudou de "cabe no vao debaixo" para "tem baia propria e nao
    # encosta na placa". A regra antiga cobrava as duas coisas que agora
    # estao erradas de proposito - ficar sob a placa e ter ar entre as duas.
    dentro_das_paredes = (C.PAREDE, C.PAREDE,
                          C.W_P - C.PAREDE, C.H_P - C.PAREDE)
    if not _dentro(celula, dentro_das_paredes, 0.0):
        problemas.append("a celula bate na parede")
    if _cruza(celula, placa):
        problemas.append("a celula esta sob a placa: a baia dela e ao lado")
    vao_x = placa[0] - celula[2]
    if vao_x < C.CELULA_VAO - 1e-9:
        problemas.append(f"so {f2(vao_x)} entre a celula e a ponta da placa, "
                         f"pede {f2(C.CELULA_VAO)}")
    if C.CELULA_Z1 > C.TAMPA_Z0 + 1e-9:
        problemas.append(f"a celula de {f2(C.CELULA_ESP)} passa do teto da "
                         f"cavidade ({f2(C.TAMPA_Z0)})")
    for cx, cy in pod.pilares:
        pil = (cx - C.PILAR_D / 2, cy - C.PILAR_D / 2, cx + C.PILAR_D / 2, cy + C.PILAR_D / 2)
        if _cruza(pil, celula):
            problemas.append(f"o pilar em ({f2(cx)}; {f2(cy)}) esta sobre a celula")
    if pod.rasgo and _cruza(pod.rasgo, celula):
        problemas.append("o rasgo dos fios da ponte fica sob a celula")
    if problemas:
        r.falha("PD5", "; ".join(problemas))
    else:
        r.ok("PD5", f"celula de {f2(C.CELULA_W)} x {f2(C.CELULA_H)} x "
                    f"{f2(C.CELULA_ESP)} na baia ao lado da placa, "
                    f"{f2(vao_x)} da ponta dela, {f2(C.TAMPA_Z0 - C.CELULA_Z1)} "
                    f"sob o teto da cavidade e "
                    f"{f2(C.H_P - C.PAREDE - celula[3])} da parede de cima")

    # -- PD6: a antena longe de TODO metal, nos tres eixos --------------------
    # Ate 2026-10-01 esta regra media uma distancia em X e contra UM objeto, a
    # celula, e imprimia 50,9 - enquanto o braco de aluminio, que e a maior
    # chapa de metal do conjunto, fica 4,0 mm abaixo da antena em Z e a faixa
    # inteira da antena cai sobre a base de colagem. `make_dxf` proibe cobre,
    # componente ou metal sobre a area da antena; o aluminio do pedivela nao
    # era medido por regra nenhuma.
    if not pod.antena:
        r.falha("PD6", "nao mede nada: o modulo de radio nao esta na placa")
    else:
        ax0, ay0, ax1, ay1 = pod.antena
        az0 = C.PLACA_Z1          # a antena esta na face de cima da placa
        metais = [("a celula (bolsa de litio)", celula[0], celula[1], C.CELULA_Z0,
                   celula[2], celula[3], C.CELULA_Z1),
                  # o braco: a face interna fica COLA abaixo do pod e ocupa
                  # toda a planta dele
                  ("o braco de aluminio", 0.0, 0.0, -C.COLA - C.BRACO_ESP,
                   C.W_P, C.H_P, -C.COLA)]
        for i, (px, py) in enumerate(C.PARAF_XY):
            rr = C.PARAF_BOSS_D / 2.0
            metais.append((f"o parafuso {i + 1} (aco)", px - rr, py - rr, C.FUNDO,
                           px + rr, py + rr, C.T_P))
        medidas = []
        for nome, mx0, my0, mz0, mx1, my1, mz1 in metais:
            dx = max(mx0 - ax1, ax0 - mx1, 0.0)
            dy = max(my0 - ay1, ay0 - my1, 0.0)
            dz = max(mz0 - C.T_P, az0 - mz1, 0.0)
            medidas.append((math.sqrt(dx * dx + dy * dy + dz * dz), nome,
                            f"x {f2(dx)}, y {f2(dy)}, z {f2(dz)}"))
        medidas.sort()
        perto = [(d, n, c) for d, n, c in medidas if d < FOLGA_ANTENA - 1e-9]
        if perto:
            r.falha("PD6", f"{len(perto)} metal(is) a menos de {FOLGA_ANTENA:g} mm da "
                           "area da antena: " + "; ".join(
                               f"{n} a {f2(d)} ({c})" for d, n, c in perto)
                    + ". A ficha do ME54BS13 (V1.0.0, 7.4) pede 3 a 5 mm; o que "
                      "estiver entre 3 e 5 e risco a medir na bancada, abaixo de "
                      "3 e defeito")
        else:
            r.ok("PD6", f"os {len(metais)} metais do conjunto ficam a "
                        f"{f2(medidas[0][0])} ou mais da area da antena "
                        f"({FOLGA_ANTENA:g} pedidos); o mais perto e "
                        f"{medidas[0][1]} ({medidas[0][2]})")

    # -- PD7: the slot under the bridge's holes -------------------------------
    j3 = pecas.get("J301")
    if not j3 or not j3["pads"] or not pod.rasgo:
        r.falha("PD7", "nao mede nada: os furos da ponte nao estao na placa")
    else:
        furos = [(C.PLACA_X0 + q["x"] - q["hw"], C.PLACA_Y0 + q["y"] - q["hh"],
                  C.PLACA_X0 + q["x"] + q["hw"], C.PLACA_Y0 + q["y"] + q["hh"]) for q in j3["pads"]]
        fora = [f for f in furos if not _dentro(f, pod.rasgo, 0.0)]
        problemas = []
        if fora:
            problemas.append(f"{len(fora)} dos {len(furos)} furos nao ficam sobre o rasgo")
        # O rasgo tem de ficar dentro do PISO - entre as paredes - e pode no
        # maximo passar por baixo da BEIRADA de um ressalto: o ressalto nasce
        # no piso e e colado na parede, entao um balanco pequeno dele sobre o
        # rasgo nao cai. Ate 2026-10-01 a regra exigia o rasgo inteiramente
        # fora dos ressaltos, e isso virou falsa falha quando o `RESSALTO`
        # cresceu de 0,6 para 1,0 para dar assento a placa (`PD30`): sobrava
        # 0,35 mm de beirada sobre o rasgo, que nao e problema nenhum.
        if not _dentro(pod.rasgo, cavidade, 0.0):
            problemas.append("o rasgo passa da parede")
        balanco = max(entre_ressaltos[0] - pod.rasgo[0], entre_ressaltos[1] - pod.rasgo[1],
                      pod.rasgo[2] - entre_ressaltos[2], pod.rasgo[3] - entre_ressaltos[3], 0.0)
        if balanco > C.RESSALTO_BALANCO + 1e-9:
            problemas.append(f"o rasgo entra {f2(balanco)} no ressalto, e a beirada "
                             f"em balanco nao pode passar de {f2(C.RESSALTO_BALANCO)}")
        if any(not q["smd"] for q in j3["pads"]) is False:
            problemas.append("os pads da ponte nao sao furos: o fio nao tem por onde subir")
        if problemas:
            r.falha("PD7", "; ".join(problemas))
        else:
            r.ok("PD7", f"os {len(furos)} furos da ponte ficam sobre o rasgo de "
                        f"{f2(pod.rasgo[2] - pod.rasgo[0])} x {f2(pod.rasgo[3] - pod.rasgo[1])} no fundo")

    # -- PD8: posts and ledges against a clean back ---------------------------
    apoios = [(cx - C.PILAR_D / 2, cy - C.PILAR_D / 2, cx + C.PILAR_D / 2, cy + C.PILAR_D / 2)
              for cx, cy in pod.pilares]
    apoios += [(C.PAREDE, C.PAREDE, C.W_P - C.PAREDE, C.PAREDE + C.RESSALTO),
               (C.PAREDE, C.H_P - C.PAREDE - C.RESSALTO, C.W_P - C.PAREDE, C.H_P - C.PAREDE),
               (C.W_P - C.PAREDE - C.RESSALTO, C.PAREDE, C.W_P - C.PAREDE, C.H_P - C.PAREDE)]
    pads_tras = []
    for ref, p in pecas.items():
        for q in p["pads"]:
            if q["camada"].startswith("B.") or not q["smd"]:
                pads_tras.append((ref, (C.PLACA_X0 + q["x"] - q["hw"], C.PLACA_Y0 + q["y"] - q["hh"],
                                        C.PLACA_X0 + q["x"] + q["hw"], C.PLACA_Y0 + q["y"] + q["hh"])))
    tocados = [(ref, b) for ref, b in pads_tras if any(_cruza(b, a) for a in apoios)]
    if not pads_tras:
        r.falha("PD8", "nao mede nada: a face de tras nao tem pad nenhum (os pontos de teste deviam "
                       "estar la)")
    elif tocados:
        r.falha("PD8", f"{len(tocados)} pads da face de tras ficam sob um pilar ou um ressalto: " +
                ", ".join(sorted({ref for ref, _b in tocados})))
    else:
        r.ok("PD8", f"nenhum dos {len(pads_tras)} pads da face de tras fica sob os {len(pod.pilares)} "
                    "pilares nem sob os ressaltos")

    # -- PD9: the light hole over the LED --------------------------------------
    d = pecas.get("D201")
    if not d or not pod.led:
        r.falha("PD9", "nao mede nada: o LED nao esta na placa")
    else:
        bx = C.no_pod(d["caixa"])
        lx, ly = pod.led
        furo = (lx - C.LED_FURO / 2, ly - C.LED_FURO / 2, lx + C.LED_FURO / 2, ly + C.LED_FURO / 2)
        if not _dentro(furo, bx, 0.0):
            r.falha("PD9", "o furo de luz sai do contorno do LED")
        else:
            r.ok("PD9", f"furo de luz de {f2(C.LED_FURO)} sobre o LED, dentro do contorno de "
                        f"{f2(bx[2] - bx[0])} x {f2(bx[3] - bx[1])}")

    # -- PD10: the envelope ------------------------------------------------------
    fora = []
    for nome, valor, alvo in (("comprimento", C.W_P, C.ALVO[0]), ("largura", C.H_P, C.ALVO[1]),
                              ("altura", C.T_P, C.ALVO[2])):
        if valor > alvo + 1e-9:
            fora.append(f"{nome} {f2(valor)} contra {alvo:g}")
    # A pilha impressa e a de AGORA. Ate 2026-09-30 esta linha somava a
    # celula, porque a celula ficava sob a placa; com ela ao lado quem manda
    # na altura e o ar sob o verso mais a placa mais o teto, e a celula so
    # entra se for mais alta que isso. Numero com nome errado engana mais
    # que numero nenhum.
    dentro = [f"{nome} {f2(valor)} de {alvo:g}"
              for nome, valor, alvo in (("comprimento", C.W_P, C.ALVO[0]),
                                        ("largura", C.H_P, C.ALVO[1]),
                                        ("altura", C.T_P, C.ALVO[2]))
              if valor <= alvo + 1e-9]
    pilha = (f"pilha: fundo {f2(C.FUNDO)} + ar do verso {f2(C.SOB_A_PLACA)} + "
             f"placa {f2(C.PLACA_ESP)} + teto {f2(C.TETO)} + tampa "
             f"{f2(C.TAMPA)} = {f2(C.T_P)}; a celula de {f2(C.CELULA_ESP)} "
             f"cabe nesse mesmo espaco, ao lado")
    if fora:
        r.falha("PD10", "fora do envelope alvo de docs/02: " + "; ".join(fora)
                + (" (cumpre " + ", ".join(dentro) + ")" if dentro else "")
                + f" ({pilha})")
    else:
        r.ok("PD10", f"{f2(C.W_P)} x {f2(C.H_P)} x {f2(C.T_P)} dentro do alvo de "
                     f"{C.ALVO[0]:g} x {C.ALVO[1]:g} x {C.ALVO[2]:g}")

    # -- PD11: the mass ------------------------------------------------------------
    g = pod.massa()
    if g["total"] > C.MASSA_ALVO:
        r.falha("PD11", f"massa estimada de {f2(g['total'])} g contra {C.MASSA_ALVO:g}")
    else:
        r.ok("PD11", f"massa estimada de {f2(g['total'])} g (concha {f2(g['concha'])}, tampa "
                     f"{f2(g['tampa'])}, placa {f2(g['placa'])}, pecas {f2(g['pecas'])}, celula "
                     f"{f2(g['celula'])}, envase {f2(g['envase'])}) contra {C.MASSA_ALVO:g}; "
                     "estimativa por volume e densidade, nada pesado")

    # -- PD12: the lid's lip against the parts near the edge ------------------------
    aba = C.PAREDE + C.ABA_FOLGA + C.ABA_LARG
    faixa = (aba, aba, C.W_P - aba, C.H_P - aba)
    z_aba = C.TAMPA_Z0 - C.ABA_ALT
    batem = []
    for ref, p in frente.items():
        cx = C.no_pod(p["caixa"])
        if _dentro(cx, faixa, 0.0):
            continue
        if C.PLACA_Z1 + p["altura"] > z_aba + 1e-9:
            batem.append((ref, p["altura"]))
    if batem:
        r.falha("PD12", f"{len(batem)} pecas junto da borda batem na aba da tampa (que desce ate "
                        f"{f2(z_aba)}): " + ", ".join(f"{ref} {f2(h)}" for ref, h in batem[:6]))
    else:
        r.ok("PD12", f"a aba da tampa ({f2(C.ABA_LARG)} larga, desce {f2(C.ABA_ALT)}) nao bate em "
                     "peca nenhuma da borda")

    # -- PD13: the O-ring groove ----------------------------------------------
    # A PROFUNDIDADE do sulco vem medida no solido: a altura da face de cima da
    # concha dentro da pegada do sulco, contra o teto. Ate 2026-10-01 esta regra
    # lia `JUNTA_SULCO_P` e passaria igual com o sulco nao desenhado - e e por
    # isso que a aba atravessando tres nervuras nao aparecia aqui, embora o vao
    # real do O-ring virasse 1,58 contra um cordao de 0,80.
    import numpy as _np13
    g13 = ME.grade_do_pod(C)
    v13 = g13.solido(pod.concha())
    s_fora, s_dentro = pod.sulco()
    pegada = (g13.planta_poli(s_fora) & ~g13.planta_poli(s_dentro)
              & ~_np13.isnan(g13.topo(v13)))
    piso_sulco = (float(_np13.nanmin(_np13.where(pegada, g13.topo(v13), _np13.nan)))
                  if pegada.any() else C.TAMPA_Z0)
    prof_medida = C.TAMPA_Z0 - piso_sulco
    terra_fora = (C.PAREDE - C.JUNTA_SULCO_L) / 2.0
    compr = (C.JUNTA_CORDAO - prof_medida) / C.JUNTA_CORDAO * 100.0
    a_sulco = C.JUNTA_SULCO_L * C.JUNTA_SULCO_P
    a_cordao = math.pi * (C.JUNTA_CORDAO / 2.0) ** 2
    problemas = []
    if terra_fora < 0.35:
        problemas.append(f"so {f2(terra_fora)} de parede de cada lado do sulco; um sulco de "
                         f"{f2(C.JUNTA_SULCO_L)} numa parede de {f2(C.PAREDE)} pede 0,35")
    if not (20.0 <= compr <= 30.0):
        problemas.append(f"a compressao do anel e {compr:.1f} %, fora dos 20 a 30 % de uma "
                         "vedacao estatica de face")
    if not pegada.any():
        problemas.append("nao ha sulco desenhado: a pegada dele nao tem solido nenhum")
    elif abs(prof_medida - C.JUNTA_SULCO_P) > 2 * ME.PASSO:
        problemas.append(f"o sulco desenhado tem {f2(prof_medida)} de fundo e "
                         f"`JUNTA_SULCO_P` diz {f2(C.JUNTA_SULCO_P)}")
    if a_sulco < a_cordao * 1.05:
        problemas.append(f"o sulco tem {a_sulco:.2f} mm2 de secao e o cordao {a_cordao:.2f}: "
                         "o anel nao cabe quando esmagado")
    if problemas:
        r.falha("PD13", "; ".join(problemas))
    else:
        r.ok("PD13", f"sulco de {f2(C.JUNTA_SULCO_L)} x {f2(prof_medida)} MEDIDO no solido numa parede de "
                     f"{f2(C.PAREDE)}, cordao de {f2(C.JUNTA_CORDAO)}: {compr:.1f} % de compressao, "
                     f"{f2(terra_fora)} de parede de cada lado, secao {a_sulco:.2f} contra "
                     f"{a_cordao:.2f} mm2")

    # -- PD14: the closing screws ---------------------------------------------
    problemas = []
    if not C.PARAF_XY:
        problemas.append("nao ha parafuso nenhum: a tampa depende so da cola")
    cavidade = (C.PAREDE, C.PAREDE, C.W_P - C.PAREDE, C.H_P - C.PAREDE)
    for i, (cx, cy) in enumerate(C.PARAF_XY):
        b = (cx - C.PARAF_BOSS_D / 2, cy - C.PARAF_BOSS_D / 2,
             cx + C.PARAF_BOSS_D / 2, cy + C.PARAF_BOSS_D / 2)
        atravessa = C.PARAF_NA_PLACA[i]
        if _cruza(b, placa) and not atravessa:
            problemas.append(f"o ressalto em ({f2(cx)}; {f2(cy)}) invade a placa")
        if atravessa:
            # ATRAVESSAR NAO E PASSE LIVRE: o que atravessa tem de CABER no
            # furo. Ate 2026-10-01 esta regra desligava o teste de
            # interferencia quando `atravessa` era verdade e imprimia
            # "livres da placa", enquanto o ressalto de 3,40 passava por um
            # furo de 2,20 - 0,600 mm de interferencia no raio, em todo
            # angulo, que impedia a placa de assentar e, por tabela, o
            # O-ring de comprimir. Dez revisores acharam isso; a regra que
            # devia te-lo achado olhava para o outro lado.
            #
            # E o numero vem MEDIDO do solido, nao da constante: o maior
            # raio que a concha ocupa em volta do parafuso dentro da faixa
            # z da placa, vezes dois. Ler `PARAF_PESCOCO_D` daria o mesmo
            # numero com o pescoco desenhado ou sem ele.
            d_na_placa = 2.0 * raio_do_solido(pod.concha(), cx, cy,
                                              C.PLACA_Z0, C.PLACA_Z1)
            folga_furo = (C.PARAF_FURO_PLACA - d_na_placa) / 2.0
            if d_na_placa <= 1e-9:
                problemas.append(
                    f"o parafuso em ({f2(cx)}; {f2(cy)}) atravessa a placa e "
                    "nao ha solido nenhum desenhado na altura dela: nao ha "
                    "pescoco, so a constante")
            elif d_na_placa > C.PARAF_FURO_PLACA - 1e-9:
                problemas.append(
                    f"o que atravessa a placa em ({f2(cx)}; {f2(cy)}) tem "
                    f"{f2(d_na_placa)} de diametro e o furo dela tem "
                    f"{f2(C.PARAF_FURO_PLACA)}")
            elif folga_furo < 0.05:
                problemas.append(
                    f"so {f2(folga_furo)} de folga no raio entre o pescoco de "
                    f"{f2(d_na_placa)} e o furo de {f2(C.PARAF_FURO_PLACA)}")
            # e o que passa pelo furo nao pode passar da reserva do furo na
            # placa, que e o que garante que nao ha peca em volta dele
            reserva = 2.0 * C.MD.FURO_RESERVA_R
            if d_na_placa > reserva + 1e-9:
                problemas.append(
                    f"o pescoco de {f2(d_na_placa)} passa da reserva de "
                    f"{f2(reserva)} que a placa guarda em volta do furo")
            # it pierces the board on purpose, and then the BOARD has to
            # carry the hole for it - if it does not, the post has nowhere
            # to pass and nothing else would say so
            furos = [(C.PLACA_X0 + fx, C.PLACA_Y0 + fy) for fx, fy in C.MD.FUROS_DOC]
            if not any(abs(fx - cx) < 0.05 and abs(fy - cy) < 0.05 for fx, fy in furos):
                problemas.append(f"o parafuso em ({f2(cx)}; {f2(cy)}) atravessa a placa "
                                 "e a placa nao tem furo nesse ponto")
        if _cruza(b, celula):
            problemas.append(f"o ressalto em ({f2(cx)}; {f2(cy)}) invade a celula")
        if not _dentro(b, cavidade, 0.0):
            problemas.append(f"o ressalto em ({f2(cx)}; {f2(cy)}) sai da cavidade")
    paredinha = (C.PARAF_BOSS_D - C.PARAF_FURO_D) / 2.0
    if paredinha < 0.8:
        problemas.append(f"so {f2(paredinha)} de parede no ressalto; um M1,6 autoatarraxante "
                         "pede 0,8")
    if problemas:
        r.falha("PD14", "; ".join(problemas))
    else:
        medidos = ", ".join(
            f"{f2(2.0 * raio_do_solido(pod.concha(), cx, cy, C.PLACA_Z0, C.PLACA_Z1))}"
            for (cx, cy), na in zip(C.PARAF_XY, C.PARAF_NA_PLACA) if na)
        r.ok("PD14", f"{len(C.PARAF_XY)} parafusos M{C.PARAF_D:g} com ressalto de "
                     f"{f2(C.PARAF_BOSS_D)} e furo-guia de {f2(C.PARAF_FURO_D)} "
                     f"({f2(paredinha)} de parede); o que atravessa a placa mede "
                     f"{medidos} de diametro no solido, contra o furo de "
                     f"{f2(C.PARAF_FURO_PLACA)}")

    # -- PD15: the cell and the board are HELD --------------------------------
    ribs = pod.berco()
    ressalto = (C.PAREDE + C.RESSALTO, C.PAREDE + C.RESSALTO,
                C.W_P - C.PAREDE - C.RESSALTO, C.H_P - C.PAREDE - C.RESSALTO)
    lados = {"esquerda": False, "direita": False, "cima": False, "baixo": False}
    for a, b, c, d in ribs:
        if c <= celula[0] + 1e-6:
            lados["esquerda"] = True
        if a >= celula[2] - 1e-6:
            lados["direita"] = True
        if b >= celula[3] - 1e-6:
            lados["cima"] = True
        if d <= celula[1] + 1e-6:
            lados["baixo"] = True
    encosta = {"esquerda": celula[0] <= ressalto[0] + 1e-6,
               "direita": celula[2] >= ressalto[2] - 1e-6,
               "cima": celula[3] >= ressalto[3] - 1e-6,
               "baixo": celula[1] <= ressalto[1] + 1e-6}
    problemas = []
    for lado, tem in lados.items():
        if not tem and not encosta[lado]:
            problemas.append(f"a celula nao tem nervura nem ressalto do lado {lado}: ela anda")
    if not pod.pilares:
        problemas.append("a placa nao tem pilar: nao ha o que prender contra a tampa")
    if C.APERTO_PAD <= 0.0:
        problemas.append("o dedo da tampa encosta na placa sem pastilha: prende no rigido")
    if problemas:
        r.falha("PD15", "; ".join(problemas))
    else:
        presos = ", ".join(k for k, v in lados.items() if v)
        r.ok("PD15", f"a celula fica presa por {len(ribs)} nervuras ({presos}) e pelos ressaltos "
                     f"que ela encosta, e a placa entre {len(pod.pilares)} pilares e os dedos da "
                     f"tampa, com {f2(C.APERTO_PAD)} de pastilha")

    # -- PD16: nada represa agua em volta da porta ----------------------------
    # Ate 2026-10-01 esta regra media um labio em volta da janela e um dreno
    # para a borda. As duas coisas sairam do projeto, e por medida: o labio
    # ficava 0,40 ACIMA do topo da junta e 0,55 por fora do corpo do conector,
    # e o "dreno" tinha a soleira 0,50 mm ACIMA do fundo do poco, com queda
    # zero em 2,65 mm - a agua do poco so tinha para onde ir para DENTRO. Um
    # canal de dreno numa tampa de 1,0 mm teria de passar abaixo da face de
    # baixo dela, virando um furo para a cavidade. O que veda a porta e a junta
    # plana no ombro do conector (`PD24`); o que esta regra cobra e que nada
    # fique em pe na face de fora da tampa para represar agua ali.
    alto = max((C.PLACA_Z1 + p["altura"] for ref, p in pecas.items()
                if not p["atras"] and ref != "J101"), default=0.0)
    problemas = []
    if C.T_P <= C.TAMPA_Z0:
        problemas.append("a tampa nao tem espessura")
    for nome, valor in (("POCO_LABIO", None), ("DRENO_L", None)):
        if hasattr(C, nome):
            problemas.append(f"{nome} voltou a existir: o labio represa agua "
                             "sobre os contatos")
    if problemas:
        r.falha("PD16", "; ".join(problemas))
    else:
        r.ok("PD16", f"a face de fora da tampa e plana em z = {f2(C.T_P)}: nao ha "
                     f"labio nem canal que represe agua em volta da porta, e o "
                     f"barrilete do conector sai dela ({f2(pod.poco)} de poco). A "
                     f"vedacao da porta e a junta no ombro, medida na PD24")

    # -- PD17: the pod fits the crank arm it is bonded to ---------------------
    # Nobody has measured the owner's crank, so these are the numbers of the
    # class (make_pod: Shimano 105 / Ultegra, the NARROW end of the arm's
    # taper, the TIGHT end of road frame clearance). Treating them as a
    # requirement the pod must meet is the only way a reserved number means
    # anything: the alternative is a comment that never fails.
    # A face do braco MEDIDA ao longo da faixa x do pod, e nao um escalar: o
    # cone do pedivela vai de 27,29 mm em x = 0 a 22,93 em x = 74,2, e o
    # `BRACO_LARG = 20,0` que esta regra cobrava so ocorre no eixo do pedal,
    # quase 40 mm depois do fim do pod. Os dois numeros valem: o 20,0 e o pior
    # caso da classe tomado como requisito, e a largura sob o pod e o que o
    # modelo do braco realmente da. A regra diz os dois.
    import make_conjunto as _MC
    larguras = [2.0 * _MC.meia_largura(C.W_P * k / 40.0) for k in range(41)]
    sob_o_pod = min(larguras)
    util = C.BRACO_LARG - 2.0 * C.RAIO_CONC
    pilha = C.COLA + C.T_P
    problemas = []
    if C.H_P > C.BRACO_LARG:
        problemas.append(f"o pod tem {f2(C.H_P)} de largura e a face interna do braco da classe "
                         f"tem {f2(C.BRACO_LARG)}: ele sobra pelos lados (no modelo do braco a "
                         f"face sob o pod mede de {f2(sob_o_pod)} a {f2(max(larguras))}, mas o "
                         f"{f2(C.BRACO_LARG)} e o pior caso da classe, e e ele que vale ate o "
                         "pedivela do dono ser medido)")
    if C.BASE_COLA + 2.0 * C.COLA_MARGEM > util + 1e-9:
        problemas.append(f"a base de colagem tem {f2(C.BASE_COLA)} mais "
                         f"{f2(C.COLA_MARGEM)} de margem por lado e so {f2(util)} da face sao "
                         f"planos (a concordancia come {f2(C.RAIO_CONC)} de cada lado): a cola "
                         "apoiaria no raio")
    if C.RELEVO < 0.5:
        problemas.append(f"o relevo fora da base tem {f2(C.RELEVO)} e nao livra a concordancia")
    if pilha > C.QUADRO:
        problemas.append(f"a pilha cola + pod e {f2(pilha)} e a folga de quadro reservada e "
                         f"{f2(C.QUADRO)}. Isto e um REQUISITO SOBRE A BICICLETA, nao um defeito "
                         "do pod: o quadro tem de dar pelo menos "
                         f"{f2(pilha)} mm entre a face interna do braco e o que estiver mais "
                         "perto. Meca com um paquimetro antes de colar")
    if problemas:
        r.falha("PD17", "; ".join(problemas))
    else:
        r.ok("PD17", f"o pod tem {f2(C.H_P)} de largura mas cola so pela base de {f2(C.BASE_COLA)} "
                     f"mais {f2(C.COLA_MARGEM)} de margem por lado, "
                     f"que cabe nos {f2(util)} planos da face interna de um braco da classe "
                     f"(o modelo do braco da de {f2(sob_o_pod)} a {f2(max(larguras))} sob o pod); fora "
                     f"dela o fundo sobe {f2(C.RELEVO)} e livra a concordancia de {f2(C.RAIO_CONC)}. "
                     f"A pilha cola + pod de {f2(pilha)} cabe nos {f2(C.QUADRO)} do quadro. "
                     "NUMEROS DA CLASSE, nao do braco do dono")

    # -- PD18: the module is no taller than the lid was built for -------------
    mod = pecas.get("U201")
    if not mod:
        r.falha("PD18", "nao mede nada: nao ha U201 na placa")
    elif mod["altura"] > C.MODULO_ALT_MAX + 1e-9:
        r.falha("PD18", f"o modulo tem {f2(mod['altura'])} e o teto da tampa foi construido sobre "
                        f"{f2(C.MODULO_ALT_MAX)}: a tampa nao fecha")
    else:
        r.ok("PD18", f"o modulo mede {f2(mod['altura'])} contra os {f2(C.MODULO_ALT_MAX)} que o teto "
                     "da tampa reserva. O anuncio NAO da a altura: 2,40 e requisito de compra, e a "
                     "peca que chegar tem de ser medida contra ele")

    pd19_aberturas(pod, r)
    pd20_caminho_da_agua(pod, r)


def pd19_aberturas(pod, r) -> None:
    """Toda abertura do pod tem vedacao, e a vedacao e medida.

    O aparelho fica na face interna do braco, a centimetros do chao, e leva
    chuva, spray de estrada e mangueira de lavagem. Cada furo do pod e um
    caminho de agua ate a placa, e ate 2026-09-30 nao havia regra nenhuma
    cobrando isso: o O-ring tinha a `PD13`, a janela do conector tinha a
    `PD3` e a `PD16`, e o resto - o furo de luz, os dois parafusos e o rasgo
    dos fios da ponte - nao tinha dono.

    Aqui as aberturas sao ENUMERADAS a partir da geometria, uma a uma, e
    cada uma tem de apontar para a vedacao que a fecha, com a medida dessa
    vedacao. Uma abertura sem vedacao reprova pelo nome.
    """
    aberturas = []

    # 1. a junta entre a concha e a tampa, em todo o contorno
    aberturas.append((
        "junta concha-tampa", "tampa",
        f"O-ring de {f2(C.JUNTA_CORDAO)} num sulco de {f2(C.JUNTA_SULCO_L)} x "
        f"{f2(C.JUNTA_SULCO_P)}",
        C.JUNTA_SULCO_P > 0.0 and C.JUNTA_CORDAO > C.JUNTA_SULCO_P))

    # 2. a janela do conector magnetico. Quem MEDE a vedacao dela no solido e
    #    a `PD24`; aqui ela so entra na lista de aberturas, apontando para a
    #    junta que a fecha, e o criterio e o mesmo numero que a PD24 mede.
    aberturas.append((
        "janela do conector magnetico", "tampa",
        f"junta plana de {f2(pod.junta_larg)} apoiada no ombro do conector em "
        f"z = {f2(pod.ombro_z)}, comprimida {f2(C.JUNTA_APERTO)} de "
        f"{f2(C.JUNTA_ESP)} por um ressalto da tampa",
        pod.junta_larg >= C.JUNTA_MIN_L - 1e-9
        and C.JUNTA_APERTO > 0.0
        and pod.junta_aperta_em < C.TAMPA_Z0 - 1e-9))

    # 3. o furo de luz do LED
    if pod.led:
        aberturas.append((
            "furo de luz do LED", "tampa",
            f"resina transparente enchendo os {f2(C.TAMPA)} de tampa "
            f"(coluna de {f2(C.LED_FURO)} de diametro)",
            getattr(C, "LED_RESINA", False)))

    # 4. os furos dos parafusos
    for i, (px, py) in enumerate(C.PARAF_XY):
        aberturas.append((
            f"furo do parafuso {i + 1} em ({f2(px)}; {f2(py)})", "tampa",
            f"tampao de resina de {f2(getattr(C, 'PARAF_TAMPAO_P', 0.0))} "
            "sobre a cabeca",
            getattr(C, "PARAF_TAMPAO_P", 0.0) >= 0.5))

    # 5. o rasgo dos fios da ponte, no fundo
    if pod.rasgo:
        # medido no DESENHO: o colar tem de cercar o rasgo pelos quatro
        # lados e subir. Uma regra que le so a constante passa mesmo quando
        # a peca nao foi desenhada.
        # As quatro barras COMO FORAM DESENHADAS, cada uma com a altura que
        # cabe nela: desde 2026-10-01 a barra que passa sob uma peca do verso
        # para `COLAR_FOLGA` abaixo dela em vez de prensa-la (a barra y+ subia
        # 1,5 e esmagava o R302 e o C304, dois 0402 de 0,55). Entao o criterio
        # nao e mais uma altura unica: e haver as quatro barras, cada uma com
        # altura util, e o colar nao passar da cavidade.
        barras = pod.colar_barras()
        alturas = [z1 - C.FUNDO for _r, z1 in barras]
        cerca = len(barras) >= 4 and min(alturas, default=0.0) >= 0.5
        aberturas.append((
            "rasgo dos fios da ponte", "fundo",
            f"colar de {f2(getattr(C, 'RASGO_COLAR_L', 0.0))} em {len(barras)} "
            f"barras de {f2(min(alturas, default=0.0))} a "
            f"{f2(max(alturas, default=0.0))} de altura, represando o envase, "
            "mais a cola ao braco",
            cerca))

    sem = [f"{nome} ({onde}): {como}" for nome, onde, como, ok in aberturas
           if not ok]
    if sem:
        r.falha("PD19", f"{len(sem)} de {len(aberturas)} aberturas sem "
                        "vedacao que feche: " + "; ".join(sem))
    else:
        r.ok("PD19", f"as {len(aberturas)} aberturas do pod tem vedacao: " +
                     "; ".join(f"{nome} por {como}"
                               for nome, _o, como, _k in aberturas))


def pd20_caminho_da_agua(pod, r) -> None:
    """Entre a agua de fora e a cavidade ha sempre DUAS barreiras em serie.

    O conector magnetico e' a unica coisa exposta de proposito: os contatos
    tem de ser alcancaveis pelo cabo, molhados ou nao. O que decide se isso e
    um problema nao e o poco - e o que existe entre ele e a placa. Esta regra
    conta as barreiras de cada caminho de agua, uma por uma, e cobra duas.

    Ate 2026-10-01 ela calculava a largura da junta pelos quatro lados
    nominais, lia `JUNTA_REBAIXO > 0` e imprimia "comprimida 0,3" - sem uma
    unica conta em z, num desenho em que a junta estava 0,30 enterrada no
    solido e 0,55 por fora do corpo do conector.
    """
    caminhos = []

    # 1. pela porta: a agua chega a face do conector por projeto
    caminhos.append(("pela porta do conector", [
        ("a junta plana no ombro, comprimida",
         pod.junta_aperta_em < C.TAMPA_Z0 - 1e-9
         and C.JUNTA_APERTO > 0.0
         and pod.junta_larg >= C.JUNTA_MIN_L - 1e-9),
        ("o envase da cavidade, que para abaixo do teto",
         C.ENVASE_NIVEL < C.TAMPA_Z0 - 1e-9),
    ]))

    # 2. pela costura concha-tampa
    caminhos.append(("pela costura concha-tampa", [
        ("o O-ring no sulco, comprimido",
         C.JUNTA_CORDAO > C.JUNTA_SULCO_P and C.JUNTA_SULCO_P > 0.0),
        ("a aba da tampa colada dentro da parede",
         bool(pod.aba()) and C.ABA_ALT > 0.0),
    ]))

    # 3. pelo rasgo do fundo, a unica abertura inferior
    if pod.rasgo:
        caminhos.append(("pelo rasgo dos fios da ponte", [
            ("a cola ao braco em volta do rasgo",
             pod.rasgo[1] >= pod.base_cola()[1] - 1e-9
             or pod.rasgo[3] <= pod.base_cola()[3] + 1e-9),
            ("o colar que represa o envase, em quatro barras",
             len(pod.colar_barras()) >= 4),
        ]))

    # 4. pelo furo de luz do LED
    if pod.led:
        caminhos.append(("pelo furo de luz do LED", [
            ("a resina transparente enchendo a espessura da tampa",
             getattr(C, "LED_RESINA", False)),
            ("o envase sob o furo", C.ENVASE_NIVEL > 0.0),
        ]))

    # 5. pelos furos dos parafusos
    for i, (px, py) in enumerate(C.PARAF_XY):
        caminhos.append((f"pelo furo do parafuso {i + 1}", [
            ("o tampao de resina sobre a cabeca",
             getattr(C, "PARAF_TAMPAO_P", 0.0) >= 0.5),
            ("a rosca no ressalto, acima do envase",
             C.TAMPA_Z0 >= C.ENVASE_NIVEL - 1e-9),
        ]))

    fracos = [f"{nome}: so {sum(1 for _d, ok in bs if ok)} barreira(s) "
              f"({', '.join(d for d, ok in bs if not ok)} nao fecha)"
              for nome, bs in caminhos if sum(1 for _d, ok in bs if ok) < 2]
    if fracos:
        r.falha("PD20", f"{len(fracos)} de {len(caminhos)} caminhos de agua com "
                        "menos de duas barreiras: " + "; ".join(fracos))
    else:
        r.ok("PD20", f"os {len(caminhos)} caminhos de agua tem duas barreiras em "
                     "serie cada: " + "; ".join(
                         f"{nome} ({' + '.join(d for d, _ok in bs)})"
                         for nome, bs in caminhos))


def main() -> int:
    pecas = C.ler_placa()
    pod = C.Pod(pecas)
    print(f"dry-run do pod: {C.W_P:.1f} x {C.H_P:.1f} x {C.T_P:.1f}, placa de {C.PLACA_W:g} x "
          f"{C.PLACA_H:g} com {len(pecas)} pecas\n")
    r = Relatorio()
    regras(pod, r)
    RM.todas(pod, r)
    return r.imprimir()


if __name__ == "__main__":
    sys.exit(main())
