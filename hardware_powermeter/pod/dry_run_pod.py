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

    # -- PD4: the back is flat ------------------------------------------------
    corpos_tras = [(ref, p["altura"]) for ref, p in tras.items() if p["altura"] > 1e-9]
    if corpos_tras:
        r.falha("PD4", f"{len(corpos_tras)} pecas com corpo na face de tras, que encosta na celula: " +
                ", ".join(f"{ref} {f2(h)}" for ref, h in corpos_tras[:6]))
    else:
        r.ok("PD4", f"a face de tras e plana: {len(tras)} pecas, todas pads sem corpo")

    # -- PD5: the cell between the ledges, under the board ---------------------
    entre_ressaltos = (C.PAREDE + C.RESSALTO, C.PAREDE + C.RESSALTO,
                       C.W_P - C.PAREDE - C.RESSALTO, C.H_P - C.PAREDE - C.RESSALTO)
    problemas = []
    if not _dentro(celula, entre_ressaltos, 0.0):
        problemas.append("a celula bate nos ressaltos ou na parede")
    if not _dentro(celula, placa, 0.0):
        problemas.append("a celula sai de baixo da placa")
    if C.PLACA_Z0 - C.CELULA_Z1 < C.CELULA_VAO - 1e-9:
        problemas.append(f"so {f2(C.PLACA_Z0 - C.CELULA_Z1)} de ar entre a celula e a placa")
    nx0, nx1 = pod.nervura
    if nx1 <= nx0 + 0.3:
        problemas.append(f"a nervura ficou com {f2(max(0.0, nx1 - nx0))} mm: o rasgo esta em cima da "
                         "ponta da celula")
    elif nx0 < celula[2]:
        problemas.append("a nervura invade a celula")
    for cx, cy in pod.pilares:
        pil = (cx - C.PILAR_D / 2, cy - C.PILAR_D / 2, cx + C.PILAR_D / 2, cy + C.PILAR_D / 2)
        if _cruza(pil, celula):
            problemas.append(f"o pilar em ({f2(cx)}; {f2(cy)}) esta sobre a celula")
    if pod.rasgo and _cruza(pod.rasgo, celula):
        problemas.append("o rasgo dos fios da ponte fica sob a celula")
    if problemas:
        r.falha("PD5", "; ".join(problemas))
    else:
        r.ok("PD5", f"celula de {f2(C.CELULA_W)} x {f2(C.CELULA_H)} x {f2(C.CELULA_ESP)} entre os "
                    f"ressaltos ({f2(entre_ressaltos[3] - entre_ressaltos[1])} de vao), "
                    f"{f2(C.PLACA_Z0 - C.CELULA_Z1)} sob a placa, {f2(nx0 - celula[2])} da nervura e "
                    f"{f2(pod.rasgo[0] - celula[2]) if pod.rasgo else '?'} do rasgo")

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
    if fora:
        r.falha("PD10", "fora do envelope alvo de docs/02: " + "; ".join(fora) +
                f" (pilha: fundo {f2(C.FUNDO)} + celula {f2(C.CELULA_ESP)} + ar {f2(C.CELULA_VAO)} + placa "
                f"{f2(C.PLACA_ESP)} + teto {f2(C.TETO)} + tampa {f2(C.TAMPA)})")
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
