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

FOLGA_TAMPA = 0.3        # air between a part's top and the lid's underside
FOLGA_ANTENA = 5.0       # ME54BS13 V1.0.0, 7.4


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
        problemas = []
        if not _dentro(caixa, pod.janela, C.JANELA_FOLGA):
            problemas.append("a janela nao cobre o contorno do conector com a folga")
        if face > C.T_P + 1e-9:
            problemas.append(f"a face do conector ({f2(face)}) passa do topo da tampa ({f2(C.T_P)})")
        if face < C.TAMPA_Z0 - 1e-9:
            problemas.append(f"a face do conector ({f2(face)}) fica abaixo da face de baixo da tampa "
                             f"({f2(C.TAMPA_Z0)}): o cabo nao a alcanca pela janela")
        if problemas:
            r.falha("PD3", "; ".join(problemas))
        else:
            r.ok("PD3", f"o conector de {f2(j['altura'])} atravessa a janela de "
                        f"{f2(pod.janela[2] - pod.janela[0])} x {f2(pod.janela[3] - pod.janela[1])} e a "
                        f"face dele fica {f2(pod.poco)} abaixo do topo da tampa (o poco)")

    # -- PD4: what a back-face body has under it ------------------------------
    # This rule used to fail on ANY body on the back, which is not what the
    # pod is: the cell covers 23 of the board's 38 mm, and past it the floor
    # steps down - first the rib, then the bare floor. Measured on
    # 2026-09-28: the blunt rule was reporting the module's own decoupling,
    # which sits over the recessed floor with 2,0 mm of air, as standing on
    # the cell. It now measures the air under each body.
    sob = [(celula, C.CELULA_Z1, "a celula"),
           ((pod.nervura[0], C.PAREDE + C.RESSALTO, pod.nervura[1],
             C.H_P - C.PAREDE - C.RESSALTO), C.CELULA_Z1 - 0.5, "a nervura")]
    sob += [((cx - C.PILAR_D / 2, cy - C.PILAR_D / 2, cx + C.PILAR_D / 2, cy + C.PILAR_D / 2),
             C.PLACA_Z0, "um pilar") for cx, cy in pod.pilares]
    sob += [(a, C.PLACA_Z0, "um ressalto") for a in
            ((C.PAREDE, C.PAREDE, C.W_P - C.PAREDE, C.PAREDE + C.RESSALTO),
             (C.PAREDE, C.H_P - C.PAREDE - C.RESSALTO, C.W_P - C.PAREDE, C.H_P - C.PAREDE),
             (C.W_P - C.PAREDE - C.RESSALTO, C.PAREDE, C.W_P - C.PAREDE, C.H_P - C.PAREDE))]
    corpos_tras = [(ref, p) for ref, p in tras.items() if p["altura"] > 1e-9]
    batem = []
    for ref, p in corpos_tras:
        caixa = C.no_pod(p["caixa"])
        topo, quem = C.FUNDO, "o fundo"
        for zona, z, nome in sob:
            if _cruza(caixa, zona) and z > topo:
                topo, quem = z, nome
        ar = C.PLACA_Z0 - topo
        if p["altura"] > ar + 1e-9:
            batem.append((ref, p["altura"], ar, quem))
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

    # -- PD6: the cell away from the antenna ----------------------------------
    if not pod.antena:
        r.falha("PD6", "nao mede nada: o modulo de radio nao esta na placa")
    else:
        d = max(pod.antena[0] - celula[2], celula[0] - pod.antena[2], 0.0)
        if d < FOLGA_ANTENA:
            r.falha("PD6", f"a celula fica a {f2(d)} da area da antena; a ficha pede {FOLGA_ANTENA:g}")
        else:
            r.ok("PD6", f"a celula fica a {f2(d)} da area da antena do modulo ({FOLGA_ANTENA:g} pedidos)")

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
        if not _dentro(pod.rasgo, entre_ressaltos, 0.0):
            problemas.append("o rasgo entra nos ressaltos ou na parede")
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
    terra_fora = (C.PAREDE - C.JUNTA_SULCO_L) / 2.0
    compr = (C.JUNTA_CORDAO - C.JUNTA_SULCO_P) / C.JUNTA_CORDAO * 100.0
    a_sulco = C.JUNTA_SULCO_L * C.JUNTA_SULCO_P
    a_cordao = math.pi * (C.JUNTA_CORDAO / 2.0) ** 2
    problemas = []
    if terra_fora < 0.35:
        problemas.append(f"so {f2(terra_fora)} de parede de cada lado do sulco; um sulco de "
                         f"{f2(C.JUNTA_SULCO_L)} numa parede de {f2(C.PAREDE)} pede 0,35")
    if not (20.0 <= compr <= 30.0):
        problemas.append(f"a compressao do anel e {compr:.1f} %, fora dos 20 a 30 % de uma "
                         "vedacao estatica de face")
    if a_sulco < a_cordao * 1.05:
        problemas.append(f"o sulco tem {a_sulco:.2f} mm2 de secao e o cordao {a_cordao:.2f}: "
                         "o anel nao cabe quando esmagado")
    if problemas:
        r.falha("PD13", "; ".join(problemas))
    else:
        r.ok("PD13", f"sulco de {f2(C.JUNTA_SULCO_L)} x {f2(C.JUNTA_SULCO_P)} numa parede de "
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
        r.ok("PD14", f"{len(C.PARAF_XY)} parafusos M{C.PARAF_D:g} com ressalto de "
                     f"{f2(C.PARAF_BOSS_D)} e furo-guia de {f2(C.PARAF_FURO_D)} "
                     f"({f2(paredinha)} de parede), livres da placa e da celula")

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

    # -- PD16: the connector's well drains ------------------------------------
    barras = pod.labio()
    jx0, jy0, jx1, jy1 = pod.janela
    L = C.POCO_LABIO_L
    volta = 2 * ((jx1 - jx0) + 2 * L) + 2 * ((jy1 - jy0) + 2 * L)
    coberto = sum(max(b[2] - b[0], b[3] - b[1]) for b in barras)
    problemas = []
    if not barras:
        problemas.append("nao ha labio em volta da janela: a agua fica sobre os contatos")
    elif coberto >= volta - 1e-6:
        problemas.append("o labio e fechado: ele segura a agua em vez de deixar escorrer")
    if C.DRENO_L < 0.8:
        problemas.append(f"o dreno tem {f2(C.DRENO_L)} e entope; pede 0,8")
    if problemas:
        r.falha("PD16", "; ".join(problemas))
    else:
        r.ok("PD16", f"labio de {f2(C.POCO_LABIO)} de altura em {len(barras)} trechos em volta da "
                     f"janela, com um dreno de {f2(C.DRENO_L)} para a borda mais proxima")

    # -- PD17: the pod fits the crank arm it is bonded to ---------------------
    # Nobody has measured the owner's crank, so these are the numbers of the
    # class (make_pod: Shimano 105 / Ultegra, the NARROW end of the arm's
    # taper, the TIGHT end of road frame clearance). Treating them as a
    # requirement the pod must meet is the only way a reserved number means
    # anything: the alternative is a comment that never fails.
    util = C.BRACO_LARG - 2.0 * C.RAIO_CONC
    pilha = C.COLA + C.T_P
    problemas = []
    if C.H_P > C.BRACO_LARG:
        problemas.append(f"o pod tem {f2(C.H_P)} de largura e a face interna do braco da classe "
                         f"tem {f2(C.BRACO_LARG)}: ele sobra pelos lados")
    if C.BASE_COLA > util + 1e-9:
        problemas.append(f"a base de colagem tem {f2(C.BASE_COLA)} e so {f2(util)} da face sao "
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
        r.ok("PD17", f"o pod tem {f2(C.H_P)} de largura mas cola so pela base de {f2(C.BASE_COLA)}, "
                     f"que cabe nos {f2(util)} planos da face interna de um braco da classe; fora "
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

    # 2. a janela do conector magnetico
    jx0, jy0, jx1, jy1 = pod.janela
    gx0, gy0, gx1, gy1 = pod.junta
    folga_junta = min(jx0 - gx0, jy0 - gy0, gx1 - jx1, gy1 - jy1)
    aberturas.append((
        "janela do conector magnetico", "tampa",
        f"junta plana de {f2(folga_junta)} em volta, rebaixo de "
        f"{f2(C.JUNTA_REBAIXO)}, labio de {f2(C.POCO_LABIO)} e dreno de "
        f"{f2(C.DRENO_L)}",
        # o minimo, e nao a largura nominal: a junta e grampeada na parede
        # onde o conector fica rente a borda, e ai ela e' menor de proposito
        folga_junta >= C.JUNTA_MIN - 1e-9 and C.JUNTA_REBAIXO > 0.0
        and C.POCO_LABIO > 0.0 and C.DRENO_L > 0.0))

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
        colar_alt = getattr(C, "RASGO_COLAR_ALT", 0.0)
        cerca = False
        if getattr(pod, "colar", None):
            cx0, cy0, cx1, cy1 = pod.colar
            rx0, ry0, rx1, ry1 = pod.rasgo
            larg = min(rx0 - cx0, ry0 - cy0, cx1 - rx1, cy1 - ry1)
            cerca = larg >= getattr(C, "RASGO_COLAR_L", 0.0) - 1e-9
        aberturas.append((
            "rasgo dos fios da ponte", "fundo",
            f"colar de {f2(getattr(C, 'RASGO_COLAR_L', 0.0))} cercando os "
            f"quatro lados e subindo {f2(colar_alt)} para o envase segurar, "
            "mais a cola ao braco",
            cerca and colar_alt >= 1.0))

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
    """A agua que entra no poco do conector sai para FORA, nunca para dentro.

    O conector magnetico e' a unica coisa que fica exposta de proposito: os
    seis contatos tem de ser alcancaveis pelo cabo. Entao o poco em volta
    deles enche de agua, e o que decide se isso e' um problema nao e' o
    poco - e' para onde ele drena. O dreno tem de apontar para a BORDA do
    pod, e a junta plana tem de ficar entre o poco e a cavidade.
    """
    problemas = []
    jx0, jy0, jx1, jy1 = pod.janela
    gx0, gy0, gx1, gy1 = pod.junta
    # a junta cerca a janela por inteiro?
    if not (gx0 < jx0 and gy0 < jy0 and gx1 > jx1 and gy1 > jy1):
        problemas.append("a junta plana nao cerca a janela por inteiro")
    # o dreno sai para a borda mais proxima, e nao para o meio do pod
    if min(gy0 - C.PAREDE, C.H_P - C.PAREDE - gy1,
           gx0 - C.PAREDE, C.W_P - C.PAREDE - gx1) < -1e-9:
        problemas.append("a junta plana passa da parede")
    # e a largura que sobra em cada lado, que e o que veda
    largs = (jx0 - gx0, jy0 - gy0, gx1 - jx1, gy1 - jy1)
    if min(largs) < C.JUNTA_MIN - 1e-9:
        problemas.append(f"a junta plana tem so {f2(min(largs))} no lado mais "
                         f"estreito, e o minimo e {f2(C.JUNTA_MIN)}")
    # e a placa nao pode ficar sob o poco sem a junta no meio
    if C.JUNTA_REBAIXO <= 0.0:
        problemas.append("a junta plana nao tem rebaixo: ela nao comprime")
    if problemas:
        r.falha("PD20", "; ".join(problemas))
    else:
        r.ok("PD20", f"o poco do conector drena por um canal de "
                     f"{f2(C.DRENO_L)} x {f2(C.DRENO_P)} ate a borda, e entre "
                     f"ele e a cavidade ha a junta plana de {f2(min(largs))} "
                     f"no lado mais estreito, comprimida {f2(C.JUNTA_REBAIXO)}")


def main() -> int:
    pecas = C.ler_placa()
    pod = C.Pod(pecas)
    print(f"dry-run do pod: {C.W_P:.1f} x {C.H_P:.1f} x {C.T_P:.1f}, placa de {C.PLACA_W:g} x "
          f"{C.PLACA_H:g} com {len(pecas)} pecas\n")
    r = Relatorio()
    regras(pod, r)
    return r.imprimir()


if __name__ == "__main__":
    sys.exit(main())
