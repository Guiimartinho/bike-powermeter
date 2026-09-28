#!/usr/bin/env python3
"""Measure the board against the rules the datasheets and the standards give.

check_pcb.py answers "does KiCad accept this board": outline, footprints,
nets, DRC. It says nothing about whether the board WORKS, because no DRC
knows that a chip antenna 6 mm from a switching inductor will not radiate,
nor that a 24-bit converter beside a buck will not resolve a microvolt.
Those rules live in the manufacturers' integration notes and in IPC-2221,
and this file writes each one down with where it comes from and then
measures the board against it. It is the bike computer's dry run
(hardware_gnssbike/cad/dry_run_pcb.py) with that board's rules taken out
(GNSS receiver, display, light sensor) and this board's put in (the
analog corner of the ADS1220, the flat back under the cell).

Everything printed here is measured from pmeter.kicad_pcb, not asserted.
A rule this cannot measure is listed at the end as pending, so that the
difference between "checked and passed" and "nobody looked" stays visible.

Run: python hardware_powermeter/cad/dry_run_pcb.py
"""

from __future__ import annotations

import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import footprints as FPS  # noqa: E402
import fp_load  # noqa: E402
import make_dxf as M  # noqa: E402
import make_pcb as MP  # noqa: E402
import nets as N  # noqa: E402
import parts as P  # noqa: E402

_PLACA_PATH = pathlib.Path(__file__).resolve().parent / "pmeter.kicad_pcb"


def redes_do_arquivo() -> dict[str, int]:
    """Net name -> number, from the board file itself (fp_load explains why)."""
    return fp_load.redes_da_placa(
        fp_load.parse(_PLACA_PATH.read_text(encoding="utf-8")))

PCB = HERE / "pmeter.kicad_pcb"

# --- the rules, with their source -------------------------------------------
# Each entry: id, what it demands, where it is written.
# Every line below was read in the manufacturer's own PDF, not in a summary
# of it, and not in an earlier version of this comment either.
#
# What this file said on 2026-09-24, and got wrong: that "20 mm between the
# antenna and a switching converter" was a rule nobody could find in the
# datasheet, and that 7.3 only carried a qualitative "do not place modules
# adjacent to strong interference sources". The 20 mm is REAL. It is in 7.2,
# under "Interference Isolation Rule", in a table of four rows - the section
# number was wrong, not the rule - and deleting it took a measured constraint
# off the placer. It is back, as ISOLACAO below, with all four rows and with
# the row nobody had ever carried: 25 mm from a display or an FPC cable.
#
# What that older comment did get right, and stays corrected: the module's
# decoupling distance is 0.5 mm (7.2, "Power Supply Design"), not the 2 mm
# this once used.
#
# The PDFs live in ../datasheets/, which the .gitignore keeps out of this
# public repository.
REGRAS = [
    ("RF1", "sem cobre, sem componente e sem caixa metalica fechada sobre a "
            "area da antena do modulo",
     "MinewSemi ME54BS13 V1.0.0, 7.3"),
    ("RF2", "o lado de RF do modulo virado para a borda, nunca para dentro "
            "da placa",
     "MinewSemi ME54BS13 V1.0.0, 7.3"),
    ("RF3", "5 mm em volta da area da antena sem trilha de sinal, sem metal e "
            "sem fonte de interferencia; modulo na borda ou no canto",
     "MinewSemi ME54BS13 V1.0.0, 7.4"),
    ("RF4", "a antena do modulo passando para FORA do plano de terra da "
            "placa, que e o que uma antena ceramica pede",
     "HOLYIOT-26001-A, guia de montagem do anuncio: a antena para fora da "
     "borda e a melhor posicao, o canto e boa, o meio da placa e a pior"),
    ("RF9", "a distancia de isolacao que a ficha do modulo pede de cada tipo "
            "de fonte de interferencia: 20 mm de fonte chaveada, indutor de "
            "potencia ou transformador",
     "MinewSemi ME54BS13 V1.0.0, 7.2, Interference Isolation Rule"),
    ("US1", "o par USB_DP/USB_DM roteado, com a largura e o afastamento que "
            "dao 90 ohm diferenciais nesta pilha",
     "USB 2.0, 7.1.6: 90 ohm +-15%; a geometria sai do empilhamento, "
     "calculada em route.py"),
    ("AL1", "desacoplamento do modulo de radio a 0,5 mm do pino de "
            "alimentacao; dos demais CIs, 2 mm para o de alta frequencia e "
            "5 mm para o de reserva",
     "MinewSemi ME54BS13 V1.0.0, 7.2; fichas do nPM1100, ADS1220, BMA400, "
     "TMP117, MAX17048"),
    ("AL5", "footprint de filtro pi reservado junto ao pino de alimentacao "
            "do modulo de radio, por ele vir de fonte chaveada",
     "MinewSemi ME54BS13 V1.0.0, 7.2"),
    ("AL2", "largura de trilha suficiente para a corrente, 10 C de subida",
     "IPC-2221B, 6.2, curva de condutor externo"),
    ("AL3", "laco de chaveamento curto: SW ao indutor e ao capacitor de saida",
     "nPM1100 PS v1.5, 8.3 (layout recomendado)"),
    ("AN1", "o conversor da ponte e o seu filtro longe do buck e do modulo: "
            "4 mm do indutor e do nPM1100, 5 mm do corpo do modulo",
     "TI ADS1220 SBAS501D, 9.4.1 (separar o analogico do chaveado; a ficha "
     "nao da numero, e 4 e 5 mm sao deste projeto, 04-placa.md)"),
    ("AN2", "o filtro RC das entradas e da referencia junto dos pinos do "
            "conversor, e a referencia REFP0 tirada do mesmo no que excita "
            "a ponte (medicao ratiometrica)",
     "TI ADS1220 SBAS501D, 9.1.2 e figura 9-11; TI SBAA532A, 3.1"),
    ("GN1", "uma via de terra junto de cada pad de terra do modulo de radio, "
            "e todo pad de terra de superficie ligado ao terra",
     "MinewSemi ME54BS13 V1.0.0, 7.2"),
    ("GN2", "costura de vias de terra na borda a cada 5 mm no maximo",
     "lambda/10 a 2,44 GHz em FR-4 e 6,1 mm"),
    ("AL6", "nenhuma via sob o pad termico: ela suga a solda da junta no "
            "forno",
     "TI ADS1220 SBAS501D, 11.1 (pad termico ao AVSS por vias so fora da "
     "ilha); Nordic nPM1100 PS v1.5, 8.3"),
    ("ME6", "o corpo 3D de cada peca tem o eixo do footprint (comprimento "
            "onde o F.Fab tem comprimento) e, onde as fileiras de pinos sao "
            "desiguais, as pernas saem pelos mesmos lados que as ilhas",
     "o dono, no 3D do ciclocomputador, em 2026-09-26; o F.Fab e as ilhas "
     "do footprint"),
    ("ME5", "os rabichos de solda do modelo 3D de cada conector ficam sobre "
            "as ilhas de sinal do footprint, e nao do lado oposto",
     "o dono, no 3D do ciclocomputador, em 2026-09-26; as ilhas do "
     "footprint do KiCad"),
    ("ME3", "o corpo que a ficha de cada peca cota cabe no footprint que "
            "foi desenhado para ela, e bate com o contorno dele",
     "desenho mecanico de cada ficha, em footprints.PACOTE"),
    ("ME1", "a placa cabe no envelope alvo do pod com folga",
     "docs/02-hardware.md, Requisitos e Pod: 60 x 20 por fora, paredes de "
     "1,2 mm"),
    ("ME2", "altura dos componentes da frente dentro do teto da tampa do "
            "pod, e a face de tras plana: so pads, porque a celula encosta "
            "nela",
     "docs/02-hardware.md, Pod (a pilha de alturas) e make_dxf.TETO_TAMPA"),
    ("RT1", "toda ligacao da lista de nos existe em cobre: zero itens "
            "desconectados no DRC completo do KiCad",
     "kicad-cli pcb drc --severity-all. E a unica contagem que vale: o "
     "roteador daqui relata o que tentou, e um DRC so de erros esconde os "
     "desconectados, que sao aviso"),
    ("IM1", "os eixos do acelerometro na placa sao os que o firmware supoe: "
            "o canto do pino 1 do footprint, a rotacao e a face do U401 "
            "decidem qual eixo do BMA400 fica radial e qual fica tangencial",
     "Bosch BST-BMA400-DS000-14, 8.2 (Sensing axis orientation, pagina 112) "
     "e a tabela de orientacao da mesma pagina; docs/02-hardware.md, "
     "Orientacao do acelerometro"),
    ("ME7", "o land pattern do modulo de radio bate, pad a pad, com um "
            "desenho independente do mesmo modulo: nome, posicao relativa "
            "ao centro da caixa de pads e tamanho",
     "footprints.me54bs13() e o desenho da ficha ME54BS13 V1.0.0 nao sao "
     "o land pattern oficial (a Minew fornece o dela sob pedido), entao a "
     "unica conferencia possivel e contra um terceiro: "
     "datasheets/ME54BS13_3rdparty_girishji.kicad_mod"),
    ("ME4", "as ilhas de solda de uma peca ficam sob o corpo do modelo 3D "
            "do fabricante",
     "um rabicho de solda fica em cima da sua ilha: se o corpo nao as cobre, "
     "o modelo esta fora de posicao ou fora de orientacao"),
]

# As pecas cujo corpo vem de um modelo do fabricante: sao as unicas em que
# o modelo pode estar girado em relacao ao footprint, porque as outras tem o
# corpo desenhado aqui a partir da cota da ficha.
# Nenhuma nesta placa ainda: todo corpo e desenhado aqui a partir da cota
# da ficha (footprints.DESENHADOS e PACOTE), e o conector magnetico e
# generico. Quando o STEP de um fabricante entrar em cad/3d/real/, a peca
# entra aqui e a ME4 passa a medi-la.
CORPOS_CONFERIDOS: tuple[str, ...] = ()

# What each rail carries, and where the number comes from. Without this a
# trace width is a guess.
CORRENTE = {
    "VBUS": (0.5, "porta USB: ate 500 mA em DCP ou CDP (nPM1100 PS v1.5, "
                  "tabela 10, ISET no AVSS)"),
    "VBAT": (0.2, "carga de 75 mA (ICHG 6,8 k, PS v1.5 6.2.4) e a descarga de "
                  "pico do sistema, bem abaixo de 200 mA"),
    "VSYS": (0.2, "o buck de 150 mA e o LED RGB pelo VSYS (PS v1.5, 6.3)"),
    "3V0": (0.15, "o buck do nPM1100 da 150 mA no maximo (PS v1.5, 6.3)"),
    "3V0_MOD": (0.1, "o modulo de radio: dezenas de mA transmitindo"),
    "3V0_EXC": (0.05, "a ponte de 1 kOhm a 3,0 V puxa 3 mA; 50 mA e o "
                      "minimo da curva IPC"),
    "BUCK_SW": (0.35, "no de chaveamento: a corrente de saturacao que a ficha "
                      "pede ao indutor, 350 mA (PS v1.5, tabela 20)"),
}

# The height of the packages that come out of KiCad's library, which the
# board file does not carry. These are the usual maximum for the case size,
# not a reading of the part's own drawing, and they say so: a number from a
# drawing lives in footprints.PACOTE and wins over anything here.
ALTURA_PADRAO = (
    ("_0402_", 0.55), ("_0603_", 0.95), ("_0805_", 1.00), ("_1008_", 1.20),
    ("_1206_", 0.75), ("SOIC-8", 2.00), ("LGA-14", 0.80),
    ("B3S-1000", 3.40), ("USB_C_Receptacle", 3.26), ("JST_GH", 4.25),
    ("FH12-10S", 0.90), ("1734839", 1.20), ("Buzzer", 1.70),
    ("TestPoint", 0.00), ("MountingHole", 0.00), ("Tag-Connect", 0.00),
    ("ContatoMola", 0.00),
)


def altura_do_footprint(nome: str):
    """(height, where the number comes from) or None when nobody knows."""
    import footprints as _F

    m = _F.altura_de(nome)
    if m:
        return m
    if nome in _F.CORPO:
        return (_F.CORPO[nome][2], "medida do encapsulamento em footprints.CORPO")
    for chave, h in ALTURA_PADRAO:
        if chave in nome:
            return (h, f"altura corrente de um {chave.strip('_')}, NAO lida da "
                       "ficha da peca")
    return None


CHAVEADOS = ["L101", "U101"]

# ME54BS13 V1.0.0, 7.2, "Interference Isolation Rule": the table of minimum
# recommended isolation from the module, by type of source. The datasheet
# names its own way out in the same paragraph - "Isolation using different
# PCB layers and shielding covers is recommended" - so a row this board
# cannot meet is reported with what it measures, not hidden.
#
# Rows with nothing on this board to match are left out of the table on
# purpose rather than carried empty: there is no USB 3.0, HDMI, DDR or
# high-speed SDIO here (the USB is 2.0 full speed), and the only
# high-frequency MCU clock is inside the module itself.
# There is no display, no camera and no FPC cable on this board, and the
# only high-frequency clock is inside the module: the one row that applies
# is the switching supply.
ISOLACAO = (
    ("fonte chaveada, indutor de potencia ou transformador", 20.0, CHAVEADOS),
)
MODULO = "U201"          # the radio module
# The analog corner: the converter, its input and reference filters and the
# load switch of the excitation. SBAS501D 9.4.1 asks to keep it away from
# the switching supply and does not give a number; 4 mm from the inductor
# and the charger and 5 mm from the module's body are this project's, in
# 04-placa.md, and the placer's zones are drawn to give them.
ANALOGICO = ["U301", "R301", "R302", "C301", "C302", "C303", "C304", "C305",
             "C306", "U302"]
FOLGA_ANALOGICO_BUCK = 4.0
FOLGA_ANALOGICO_MODULO = 5.0
# The antenna band of the ME54BS13, from its mechanical drawing: 4.46 mm of
# the module's 16.5 mm length, across the whole 12 mm width. It is NOT the
# keep-out rectangle, which is drawn larger and reaches the board edge.
# 3,80 mm e nao 4,46: a faixa da antena e do HOLYIOT-26001-A, e sao os
# 3,80 mm que o desenho mecanico dele mantem livres de pads entre a borda
# de cima e a primeira fileira (09-modulo-de-radio.md). Os 4,46 eram do
# ME54BS13, e deixados aqui faziam a faixa comecar 0,41 mm antes da zona
# sem cobre - a RF4 reprovava a placa por uma cota de uma peca que saiu.
ANT_MOD = 3.80
FOLGA_ANTENA = 5.0       # 7.4: "3-5 mm around the antenna area"
LIMITE_MODULO = 0.5      # 7.2: "trace length ... should be <= 0.5 mm"

# How far a decoupling capacitor may sit from the pin it serves. One number
# for both kinds is wrong in both directions: twelve 10 uF bulk capacitors
# cannot all fit inside 2 mm of a 4 x 4 mm QFN, and a 100 nF at 4 mm is no
# longer decoupling anything above a few tens of megahertz - the loop
# inductance of the track swamps it. So the limit follows the value.
LIMITE_HF, LIMITE_RESERVA = 2.0, 5.0
CORTE_HF = 1.1e-6            # at or below this the capacitor is the fast one


def farads(valor: str) -> float:
    """The value on the bill of materials, as a number."""
    v = valor.lower().replace(",", ".").strip()
    for letra, m in (("p", 1e-12), ("n", 1e-9), ("u", 1e-6),
                     ("µ", 1e-6), ("m", 1e-3)):
        if letra + "f" in v:
            try:
                return float(v.split()[0]) * m
            except (ValueError, IndexError):
                return 1.0
    return 1.0


def limite(ref: str) -> float:
    if ref not in P.PARTS:
        return LIMITE_HF
    return LIMITE_HF if farads(P.PARTS[ref].value) <= CORTE_HF \
        else LIMITE_RESERVA


def ler(caminho: pathlib.Path):
    arv = fp_load.parse(caminho.read_text(encoding="utf-8"))
    pecas = {}
    pads = []
    for f in fp_load.kids(arv, "footprint"):
        at = fp_load.kid(f, "at")
        fx, fy = float(at[1]) - MP.ORIGEM[0], float(at[2]) - MP.ORIGEM[1]
        ang = float(at[3]) if len(at) > 3 else 0.0
        ref = ""
        for pr in fp_load.kids(f, "property"):
            if pr[1] == "Reference":
                ref = pr[2]
        atras = (fp_load.kid(f, "layer") or ["", "F.Cu"])[1].startswith("B.")
        # two outlines, both in the footprint's own frame: the courtyard
        # (what the placer keeps clear) and the fabrication body (where the
        # part itself is; the ME5 rule measures the model's solder tails
        # against it, because a tail is what sticks OUT of the body)
        xs, ys = [], []
        xs_f, ys_f = [], []
        for chave in ("fp_line", "fp_rect", "fp_poly", "fp_circle"):
            for g in fp_load.kids(f, chave):
                lay = fp_load.kid(g, "layer")
                if not lay:
                    continue
                if "CrtYd" in lay[1]:
                    lx, ly = xs, ys
                elif "Fab" in lay[1]:
                    lx, ly = xs_f, ys_f
                else:
                    continue
                for tag in ("start", "end", "center"):
                    q = fp_load.kid(g, tag)
                    if q:
                        lx.append(float(q[1]))
                        ly.append(float(q[2]))
                pts = fp_load.kid(g, "pts")
                if pts:
                    for q in fp_load.kids(pts, "xy"):
                        lx.append(float(q[1]))
                        ly.append(float(q[2]))
        meus = []
        for p in fp_load.kids(f, "pad"):
            a = fp_load.kid(p, "at")
            px, py = float(a[1]), float(a[2])
            r = math.radians(ang)
            gx = fx + px * math.cos(r) + py * math.sin(r)
            gy = fy - px * math.sin(r) + py * math.cos(r)
            rede = fp_load.kid(p, "net")
            camadas = list(fp_load.kid(p, "layers")[1:])
            sz = fp_load.kid(p, "size")
            item = {"ref": ref, "pad": p[1], "x": gx, "y": gy,
                    "rede": rede[2] if rede else "",
                    "hw": float(sz[1]) / 2 if sz else 0.0,
                    "hh": float(sz[2]) / 2 if sz else 0.0,
                    "smd": p[2] == "smd",
                    "camada": "B.Cu" if any("B.Cu" in c for c in camadas)
                              else "F.Cu"}
            pads.append(item)
            meus.append(item)
        def _caixa(lx, ly):
            if not lx:
                return (fx, fy, fx, fy)
            r = math.radians(ang)
            cx = [x * math.cos(r) + y * math.sin(r) for x, y in zip(lx, ly)]
            cy = [-x * math.sin(r) + y * math.cos(r) for x, y in zip(lx, ly)]
            return (fx + min(cx), fy + min(cy), fx + max(cx), fy + max(cy))

        caixa = _caixa(xs, ys)
        pecas[ref] = {"x": fx, "y": fy, "ang": ang, "atras": atras,
                      "caixa": caixa, "fab": _caixa(xs_f, ys_f) if xs_f else None,
                      "pads": meus}
    seg = []
    for s in fp_load.kids(arv, "segment"):
        a, b = fp_load.kid(s, "start"), fp_load.kid(s, "end")
        seg.append({"a": (float(a[1]) - MP.ORIGEM[0], float(a[2]) - MP.ORIGEM[1]),
                    "b": (float(b[1]) - MP.ORIGEM[0], float(b[2]) - MP.ORIGEM[1]),
                    "w": float(fp_load.kid(s, "width")[1]),
                    "n": int(fp_load.kid(s, "net")[1]),
                    "c": fp_load.kid(s, "layer")[1]})
    # the cut-outs of the board outline, as boxes. A notch for the antenna
    # is what 7.4 asks for, and it lives on Edge.Cuts like the outline.
    ex, ey = [], []
    seg_edge = []
    for chave in ("gr_line", "gr_arc", "gr_rect"):
        for g in fp_load.kids(arv, chave):
            lay = fp_load.kid(g, "layer")
            if not lay or lay[1] != "Edge.Cuts":
                continue
            pts = []
            for tag in ("start", "end", "mid", "center"):
                q = fp_load.kid(g, tag)
                if q:
                    pts.append((float(q[1]) - MP.ORIGEM[0],
                                float(q[2]) - MP.ORIGEM[1]))
            if pts:
                seg_edge.append(pts)
                ex += [q[0] for q in pts]
                ey += [q[1] for q in pts]
    # A notch is a corner of Edge.Cuts that sits INSIDE the board instead of
    # on its rectangle. Collecting those points is enough to say where the
    # board has a bite taken out of it, and it works whether the cut was
    # drawn as lines or as a rectangle.
    cortes = []
    borda = 0.6
    dentro = [(x, y) for x, y in zip(ex, ey)
              if borda < x < M.W - borda and borda < y < M.H - borda]
    if dentro:
        cortes.append((min(q[0] for q in dentro), min(q[1] for q in dentro),
                       max(q[0] for q in dentro), max(q[1] for q in dentro)))
    del seg_edge

    vias = []
    for v in fp_load.kids(arv, "via"):
        a = fp_load.kid(v, "at")
        vias.append({"x": float(a[1]) - MP.ORIGEM[0],
                     "y": float(a[2]) - MP.ORIGEM[1],
                     "n": int(fp_load.kid(v, "net")[1])})
    return pecas, pads, seg, vias, cortes


def dist_caixas(a, b) -> float:
    """Gap between two boxes; negative when they overlap."""
    dx = max(a[0] - b[2], b[0] - a[2])
    dy = max(a[1] - b[3], b[1] - a[3])
    if dx < 0 and dy < 0:
        return max(dx, dy)
    return math.hypot(max(dx, 0), max(dy, 0))


def zona(nome: str):
    for n, r, _c, _s in M.ZONES:
        if n == nome:
            return r
    raise KeyError(nome)


# --- IPC-2221 ---------------------------------------------------------------
def largura_ipc(corrente: float, subida: float = 10.0,
                espessura_um: float = 35.0, interna: bool = False) -> float:
    """IPC-2221B, 6.2: the width a current needs for a given temperature rise.

    I = k * dT^0.44 * A^0.725, with A in square mils. k is 0.048 for an
    OUTER conductor and 0.024 for an INNER one: an inner track has no air to
    give its heat to, and the standard asks it to be about 2.6 times wider
    for the same rise. Until 2026-09-26 this applied the outer curve to every
    segment, and VBUS runs 37 mm on In2.Cu.
    """
    k = 0.024 if interna else 0.048
    area_mil2 = (corrente / (k * subida ** 0.44)) ** (1 / 0.725)
    esp_mil = espessura_um / 25.4
    return area_mil2 / esp_mil * 0.0254


def _ilhas_sob_o_corpo(ref: str, pecas: dict):
    """As ilhas de solda desta peca ficam sob o corpo do modelo 3D?

    Devolve `(n_fora, total, caixa_do_corpo)`, ou None se nao houver corpo.

    Esta pergunta e feita porque a outra - "de que lado fica a boca?" - nao
    tem resposta confiavel por geometria: tentei responde-la com um raio
    pela cavidade e o raio mentiu, porque a traseira de um receptaculo USB-C
    tambem e oca. Esta aqui nao depende de palpite nenhum. Um rabicho de
    solda fica em cima da sua ilha; se o corpo do modelo nao cobre as ilhas
    da peca, o modelo esta fora de posicao ou fora de orientacao, e ponto.

    Foi exatamente a assinatura do defeito do J101: com o STEP da LCSC como
    ele vem, as 16 ilhas de contato caiam 1,45 mm ALEM do corpo, do lado
    oposto, e a boca do conector apontava para o miolo da placa.
    """
    import numpy as np

    sys.path.insert(0, str(HERE))
    import make_3d as M3

    if ref not in pecas:
        return None
    pe = pecas[ref]
    ilhas = [(q["pad"], q["x"], q["y"]) for q in pe.get("pads", []) if q["smd"]]
    glb = M3._glb_atual()
    if glb is None:
        return None
    j, bina = M3.ler_glb(glb)
    tris, _cor = M3.triangulos(j, bina)
    X = tris[..., 0] * 1000.0 - MP.ORIGEM[0]
    Y = -tris[..., 1] * 1000.0 - MP.ORIGEM[1]
    H = tris[..., 2] * 1000.0
    x0, y0, x1, y1 = pe["caixa"]
    # so o que esta INTEIRO dentro da envoltoria da peca mais 1 mm: assim a
    # caixa medida e a do corpo dela, e nao a do vizinho - e na FACE dela:
    # ate 2026-09-26 a regra so olhava z > 0,95, e para o J103, que foi para
    # o verso nesse dia, mediu o sensor de luz e o diodo da frente por cima
    # dele e acusou uma ilha fora de um corpo que nao era o seu
    if pe.get("atras", False):
        na_face = H.max(axis=1) < -0.05
    else:
        na_face = H.min(axis=1) > 0.95
    c = ((X.min(axis=1) > x0 - 1.0) & (X.max(axis=1) < x1 + 1.0)
         & (Y.min(axis=1) > y0 - 1.0) & (Y.max(axis=1) < y1 + 1.0)
         & na_face)
    if not c.any():
        return None
    caixa = (float(X[c].min()), float(Y[c].min()),
             float(X[c].max()), float(Y[c].max()))
    fora = [nome for nome, px, py in ilhas
            if not (caixa[0] - 0.05 <= px <= caixa[2] + 0.05
                    and caixa[1] - 0.05 <= py <= caixa[3] + 0.05)]
    return (fora, len(ilhas), caixa)


# Os conectores cujos rabichos de solda a ME5 confere: os que tem modelo do
# fabricante ou da biblioteca do KiCad no GLB e ilhas de sinal numa fileira.
# None yet: no connector on this board has a manufacturer's model
# (CORPOS_CONFERIDOS says why).
RABICHOS_CONFERIDOS: tuple[str, ...] = ()

# Models whose solder contacts have a colour of their own in the maker's
# STEP, so that the contacts can be told from the nails' plate. Measured in
# the exported GLB on 2026-09-26: the HCTL FPC's five contacts are pure
# yellow (1, 1, 0), the housing white, the lid black, the nail plate grey.
# The general method of ME5 and ME6 - material touching the board outside
# the F.Fab, weighed by area - took the nail plate, which lay on the pads'
# side in the WRONG orientation, for the tails, and it outweighs five 0,3 mm
# contacts: both rules passed the model turned 180 degrees, and the owner
# saw it in the 3D. With the colour the question is direct: the coloured
# faces that touch the board have to lie on the pads' side of the body.
CONTATOS_POR_COR: dict[str, tuple[float, float, float]] = {}


def _modelo_base(ref: str):
    """The base name of the maker's model this part carries, or None."""
    nome_fp = FPS.FP[ref][0] if ref in FPS.FP else None
    if not nome_fp or ":" not in nome_fp:
        return None
    real = FPS.modelo_de_verdade(nome_fp.split(":", 1)[1])
    if not real:
        return None
    return real.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def _contatos_por_cor(ref: str, pe: dict, corpos, ux: float, uy: float, fc):
    """The signed position, along the pad axis from the F.Fab centre, of the
    faces with the contacts' colour that touch the board (positive is the
    pads' side), with their count; None when the model is not in
    CONTATOS_POR_COR or has no such face near the board."""
    import numpy as np
    base = _modelo_base(ref)
    if base not in CONTATOS_POR_COR:
        return None
    alvo = CONTATOS_POR_COR[base]
    x0, y0, x1, y1 = pe["caixa"]
    atras = pe.get("atras", False)
    soma = peso = 0.0
    n = 0
    for tris, cor in corpos:
        c = tuple(round(float(v), 2) for v in np.array(cor).reshape(-1)[:3])
        if c != alvo:
            continue
        X = tris[..., 0] * 1000.0 - MP.ORIGEM[0]
        Y = -tris[..., 1] * 1000.0 - MP.ORIGEM[1]
        H = tris[..., 2] * 1000.0
        if X.max() < x0 or X.min() > x1 or Y.max() < y0 or Y.min() > y1:
            continue
        cx = X.mean(axis=1)
        cy = Y.mean(axis=1)
        dentro = (cx > x0) & (cx < x1) & (cy > y0) & (cy < y1)
        if atras:
            toca = (H.min(axis=1) < -0.08) & (H.max(axis=1) < 0.001) & (H.max(axis=1) > -1.2)
        else:
            toca = (H.max(axis=1) > 0.9) & (H.min(axis=1) > 0.80) & (H.min(axis=1) < 2.0)
        sel = dentro & toca
        if not sel.any():
            continue
        a = tris[sel]
        area = 0.5 * np.linalg.norm(np.cross(a[:, 1] - a[:, 0], a[:, 2] - a[:, 0]), axis=1)
        proj = (cx[sel] - fc[0]) * ux + (cy[sel] - fc[1]) * uy
        soma += float((proj * area).sum())
        peso += float(area.sum())
        n += int(sel.sum())
    if peso <= 0.0:
        return None
    return (soma / peso, n)
_GLB_CACHE: dict = {}


def _glb_lido():
    """The GLB parsed once per run: five connectors, one file."""
    sys.path.insert(0, str(HERE))
    import make_3d as M3
    glb = M3._glb_atual()
    if glb is None:
        return None
    if _GLB_CACHE.get("caminho") != glb:
        j, bina = M3.ler_glb(glb)
        _GLB_CACHE.update(caminho=glb, corpos=M3.corpos(j, bina))
    return _GLB_CACHE["corpos"]


def _rabichos_sobre_as_ilhas(ref: str, pecas: dict):
    """Os rabichos de solda do modelo 3D ficam sobre as ilhas de sinal?

    A ME4 pergunta se as ilhas ficam sob o corpo. Um corpo simetrico cobre
    as ilhas nos dois sentidos, e foi assim que o JST ZH do J103 passou na
    ME4 girado 180 graus: o dono viu no 3D as pernas apontando para a borda
    enquanto as ilhas ficavam do lado de dentro. Um rabicho de solda e um
    corpo pequeno e fino que encosta na placa, e o centro dos rabichos tem
    de cair sobre o centro das ilhas de sinal - nao do lado oposto.

    Devolve (distancia, n_rabichos, centro_rabichos, centro_ilhas), ou
    None quando nao ha corpo ou rabicho para medir.
    """
    if ref not in pecas:
        return None
    pe = pecas[ref]

    def mecanica(nome: str) -> bool:
        # "MP1"/"MP2" (the HCTL FPC's nails) were counted as signal pads
        # until 2026-09-26, and pulled the pads' centre towards the nails
        return nome in ("", "MP") or nome.startswith("S") or nome.startswith("MP")

    ilhas = [(q["x"], q["y"]) for q in pe.get("pads", [])
             if q["smd"] and not mecanica(q["pad"])]
    fixacao = [(q["x"], q["y"]) for q in pe.get("pads", []) if mecanica(q["pad"])]
    if not ilhas:
        return None
    corpos = _glb_lido()
    if corpos is None:
        return None
    x0, y0, x1, y1 = pe["caixa"]
    fab = pe.get("fab")
    if fab is None:
        return None
    atras = pe.get("atras", False)
    # The GLB that KiCad exports is one primitive per FACE, not per solid,
    # so "a small thin body" is not something it can tell apart: a housing
    # is thousands of small faces too. What a tail IS, geometrically, is
    # material that touches the board OUTSIDE the fabrication outline of
    # the footprint - the outline is where the housing stands, and the
    # tails stick out of it over the pads. So: every face near the board
    # whose centre is outside the F.Fab box and inside the courtyard,
    # weighted by its area.
    import numpy as np
    ci = (sum(p[0] for p in ilhas) / len(ilhas), sum(p[1] for p in ilhas) / len(ilhas))
    # The axis that matters: from the centre of the body to the centre of
    # the signal pads. The tails stick out of the body ALONG it, on the pad
    # side; a housing whose ends poke 0,2 mm past the F.Fab box pokes out
    # ACROSS it, and must not count - it did, and pulled the centre of the
    # "tails" into the middle of the body.
    fc = ((fab[0] + fab[2]) / 2.0, (fab[1] + fab[3]) / 2.0)
    ux, uy = ci[0] - fc[0], ci[1] - fc[1]
    norma = math.hypot(ux, uy)
    if norma < 0.3:
        return None
    ux, uy = ux / norma, uy / norma
    meio = abs(ux) * (fab[2] - fab[0]) / 2.0 + abs(uy) * (fab[3] - fab[1]) / 2.0
    # a model whose contacts have their own colour is measured by them,
    # not by whatever metal touches the board (CONTATOS_POR_COR says why)
    por_cor = _contatos_por_cor(ref, pe, corpos, ux, uy, fc)
    if por_cor is not None:
        return (por_cor[0], por_cor[1], ci, meio)
    soma = 0.0
    peso = 0.0
    n_faces = 0
    for tris, _cor in corpos:
        X = tris[..., 0] * 1000.0 - MP.ORIGEM[0]
        Y = -tris[..., 1] * 1000.0 - MP.ORIGEM[1]
        H = tris[..., 2] * 1000.0
        # a quick reject on the primitive, then face by face: inside the
        # COURTYARD (no margin - the neighbours' courtyards do not overlap
        # ours, so their faces stay out), near the board, and past the body
        # along the pad axis
        if X.max() < x0 or X.min() > x1 or Y.max() < y0 or Y.min() > y1:
            continue
        cx = X.mean(axis=1)
        cy = Y.mean(axis=1)
        dentro = (cx > x0) & (cx < x1) & (cy > y0) & (cy < y1)
        # ON the board, but NOT the board: the GLB carries the substrate
        # (z 0 to 0,82) and the copper (0,82 to 0,85 on top, -0,04 to 0
        # underneath), and a pad is a flat gold face lying exactly where a
        # tail lies. Measured in the file on 2026-09-26: the tails of the
        # JST ZH start at z 0,91, the copper ends at 0,85. So a tail is a
        # face that starts above the top copper and within a millimetre of
        # it; on the back face, one that ends below the bottom copper.
        if atras:
            toca = (H.min(axis=1) < -0.08) & (H.max(axis=1) < 0.001) & (H.max(axis=1) > -1.2)
        else:
            toca = (H.max(axis=1) > 0.9) & (H.min(axis=1) > 0.80) & (H.min(axis=1) < 2.0)
        proj = (cx - fc[0]) * ux + (cy - fc[1]) * uy
        fora = np.abs(proj) > meio + 0.15
        sel = dentro & toca & fora
        if fixacao:
            perto = np.zeros(len(cx), dtype=bool)
            for fx_, fy_ in fixacao:
                perto |= np.hypot(cx - fx_, cy - fy_) < 1.2
            sel &= ~perto
        if not sel.any():
            continue
        a = tris[sel]
        area = 0.5 * np.linalg.norm(np.cross(a[:, 1] - a[:, 0], a[:, 2] - a[:, 0]), axis=1)
        soma += float((proj[sel] * area).sum())
        peso += float(area.sum())
        n_faces += int(sel.sum())
    if peso <= 0.0:
        return None
    # the signed position of the tails along the pad axis, from the body
    # centre: positive is the pad side, negative the opposite one
    media = soma / peso
    return (media, n_faces, ci, meio)


def _corpos_mm():
    """Every body on the board, in board millimetres: (triangles, source).

    Two sources. The GLB that kicad-cli exports carries the STEP models -
    the library's and the three from the LCSC - together with the board's
    own copper. The parts drawn from a .wrl (the ones footprints.py made
    from the datasheet cotes, and the library packages that have no STEP,
    like the SOT-523) are not in it: they are placed by make_3d.py the
    same way it draws them, so a rule sees exactly what the picture shows.
    """
    import numpy as np
    if "mm" in _GLB_CACHE:
        return _GLB_CACHE["mm"]
    saida = []
    corpos = _glb_lido()
    if corpos:
        for tris, _cor in corpos:
            T = np.stack([tris[..., 0] * 1000.0 - MP.ORIGEM[0],
                          -tris[..., 1] * 1000.0 - MP.ORIGEM[1],
                          tris[..., 2] * 1000.0], axis=-1)
            saida.append((T, "glb"))
    sys.path.insert(0, str(HERE))
    import make_3d as M3
    t, _c = M3.caixas_das_pecas()
    if len(t):
        T = np.stack([t[..., 0] - MP.ORIGEM[0], t[..., 1] - MP.ORIGEM[1],
                      t[..., 2]], axis=-1)
        saida.append((T, "wrl"))
    _GLB_CACHE["mm"] = saida
    return saida


def _faces_da_peca(pe: dict, corpos=None):
    """The model faces of one part: inside its courtyard and off the copper.

    Returns (cx, cy, area, hmin, hmax) as arrays, or None. Same frame as
    the rest of this file: board millimetres, y downward, z up with the
    top copper ending at 0,855 and the bottom copper starting at -0,035.
    """
    import numpy as np
    x0, y0, x1, y1 = pe["caixa"]
    atras = pe.get("atras", False)
    cxs, cys, ars, h0s, h1s = [], [], [], [], []
    for T, fonte in _corpos_mm():
        X, Y, H = T[..., 0], T[..., 1], T[..., 2]
        if X.max() < x0 or X.min() > x1 or Y.max() < y0 or Y.min() > y1:
            continue
        cx = X.mean(axis=1)
        cy = Y.mean(axis=1)
        dentro = (cx > x0) & (cx < x1) & (cy > y0) & (cy < y1)
        # the GLB carries the copper: a face lying flat on it (0,82 to
        # 0,855 on top, -0,035 to 0 underneath) is the board, not the part.
        # A leg standing on the copper starts AT 0,855 and rises above 0,9.
        if fonte == "glb":
            if atras:
                fora_do_cobre = (H.min(axis=1) < -0.08) & (H.max(axis=1) < 0.001)
            else:
                fora_do_cobre = (H.max(axis=1) > 0.9) & (H.min(axis=1) > 0.80)
        else:
            # the bodies make_3d draws from a .wrl stand on FRENTE_Z (0,855)
            # or hang from VERSO_Z (-0,035). A back part under a front one
            # shares its courtyard in plan - the buzzer under the SWD header
            # - and until 2026-09-26 its faces were counted as the front
            # part's: ME6 called J202 "girado 90" with the buzzer's box.
            if atras:
                fora_do_cobre = H.max(axis=1) < 0.001
            else:
                fora_do_cobre = H.min(axis=1) > 0.80
        sel = dentro & fora_do_cobre
        if not sel.any():
            continue
        a = T[sel]
        area = 0.5 * np.linalg.norm(np.cross(a[:, 1] - a[:, 0], a[:, 2] - a[:, 0]), axis=1)
        cxs.append(cx[sel]); cys.append(cy[sel]); ars.append(area)
        h0s.append(H.min(axis=1)[sel]); h1s.append(H.max(axis=1)[sel])
    if not cxs:
        return None
    return (np.concatenate(cxs), np.concatenate(cys), np.concatenate(ars),
            np.concatenate(h0s), np.concatenate(h1s))


def _corpo_bate_com_o_footprint(ref: str, pecas: dict):
    """Does the 3D body have the footprint's shape and orientation?

    Two measurements, for every part that has a fabrication outline and a
    model in the GLB:

      1. the body's box against the F.Fab box. A part turned 90 degrees
         has its length where the footprint has its width, and a 0402 is
         twice as long as it is wide: the swap is unmistakable. This is
         the owner's question about the resistors, answered by measure.
      2. for a part whose pads sit in two facing rows of DIFFERENT counts
         (a SOT-23 has two on one side and one on the other), the legs of
         the model must stick out of the body on the same sides, in the
         same proportion. A part turned 180 degrees fails this and passes
         the first.

    Returns a dict with the verdicts and the numbers, or None.
    """
    import numpy as np
    if ref not in pecas:
        return None
    pe = pecas[ref]
    fab = pe.get("fab")
    if fab is None:
        return None
    corpos = _glb_lido()
    if corpos is None:
        return None
    faces = _faces_da_peca(pe, corpos)
    if faces is None:
        return None
    cx, cy, area, h0, h1 = faces
    # 1. the box of the body: the faces of the model, area-weighted 2nd and
    #    98th percentiles so that a stray sliver does not stretch it
    def _faixa(v):
        ordem = np.argsort(v)
        acum = np.cumsum(area[ordem]) / area.sum()
        return (float(v[ordem][np.searchsorted(acum, 0.02)]),
                float(v[ordem][min(np.searchsorted(acum, 0.98), len(v) - 1)]))
    bx0, bx1 = _faixa(cx)
    by0, by1 = _faixa(cy)
    w_m, h_m = bx1 - bx0, by1 - by0
    w_f, h_f = fab[2] - fab[0], fab[3] - fab[1]
    out = {"modelo": (w_m, h_m), "fab": (w_f, h_f), "eixo": "ok"}
    if abs(w_f - h_f) > 0.4 and abs(w_m - h_m) > 0.4:
        if (w_m > h_m) != (w_f > h_f):
            out["eixo"] = "girado 90"
    # 2. legs per side, only where the pad rows are asymmetric
    ilhas = [(q["x"], q["y"]) for q in pe.get("pads", []) if q["smd"]]
    out["lados"] = "sem medida"
    # a model with coloured contacts: the contacts decide the side (the
    # area count below took the HCTL FPC's nail plate for its tails)
    sinal = [(q["x"], q["y"]) for q in pe.get("pads", [])
             if q["smd"] and not (q["pad"] in ("", "MP") or q["pad"].startswith(("S", "MP")))]
    if sinal and _modelo_base(ref) in CONTATOS_POR_COR:
        fc = ((fab[0] + fab[2]) / 2.0, (fab[1] + fab[3]) / 2.0)
        ci = (sum(p[0] for p in sinal) / len(sinal), sum(p[1] for p in sinal) / len(sinal))
        ux, uy = ci[0] - fc[0], ci[1] - fc[1]
        norma = math.hypot(ux, uy)
        if norma >= 0.3:
            por_cor = _contatos_por_cor(ref, pe, corpos, ux / norma, uy / norma, fc)
            if por_cor is not None:
                out["lados"] = "ok" if por_cor[0] > 0.0 else "girado 180"
                out["lados_n"] = ("contatos pela cor", round(por_cor[0], 3), por_cor[1])
                return out
    if len(ilhas) >= 3:
        xs = sorted(set(round(p[0], 2) for p in ilhas))
        ys = sorted(set(round(p[1], 2) for p in ilhas))
        for eixo, vals, coord in (("x", xs, 0), ("y", ys, 1)):
            if len(vals) != 2:
                continue
            lo, hi = vals
            n_lo = sum(1 for p in ilhas if round(p[coord], 2) == lo)
            n_hi = sum(1 for p in ilhas if round(p[coord], 2) == hi)
            if n_lo == n_hi:
                out["lados"] = "simetrico"
                continue
            c = cx if coord == 0 else cy
            f0, f1 = (fab[0], fab[2]) if coord == 0 else (fab[1], fab[3])
            a_lo = float(area[c < f0 - 0.05].sum())
            a_hi = float(area[c > f1 + 0.05].sum())
            if a_lo + a_hi < 1e-6:
                out["lados"] = "sem perna fora do corpo"
                continue
            out["lados"] = ("ok" if (a_lo > a_hi) == (n_lo > n_hi)
                            else "girado 180")
            out["lados_n"] = (n_lo, n_hi, round(a_lo, 3), round(a_hi, 3), eixo)
    return out


def main() -> int:
    if not PCB.exists():
        print("pmeter.kicad_pcb nao existe: rode make_pcb.py")
        return 1
    pecas, pads, seg, vias, cortes = ler(PCB)
    achados: list[tuple[str, str]] = []
    ok: list[str] = []

    def falhou(rid: str, msg: str) -> None:
        achados.append((rid, msg))

    print(f"dry-run de {PCB.name}: {len(pecas)} pecas, {len(seg)} segmentos, "
          f"{len(vias)} vias\n")

    # -- a area real da antena do modulo, do desenho mecanico ----------------
    def rect_antena():
        """The 4.46 x 12 mm band at the RF end of U201, in board coordinates.

        The keep-out rectangle of make_dxf is a planning shape drawn out to
        the board edge; the datasheet's rules talk about the ANTENNA AREA,
        which is 4.46 mm of the module's 16.5 mm length. Measuring the rules
        against the planning rectangle answers a different question.
        """
        if MODULO not in pecas:
            return None
        m = pecas[MODULO]
        x0, y0, x1, y1 = m["caixa"]
        a = int(round(m["ang"])) % 360
        if a == 0:      # antenna at -Y in the footprint
            return (x0, y0, x1, y0 + ANT_MOD)
        if a == 180:
            return (x0, y1 - ANT_MOD, x1, y1)
        if a == 270:    # rotated so the antenna points +X
            return (x1 - ANT_MOD, y0, x1, y1)
        return (x0, y0, x0 + ANT_MOD, y1)

    ant = rect_antena()

    # -- RF1: nada sobre a area da antena ------------------------------------
    if ant:
        invadem = [(r, dist_caixas(p["caixa"], ant)) for r, p in pecas.items()
                   if r != MODULO and dist_caixas(p["caixa"], ant) < 0]
        if invadem:
            falhou("RF1", f"{len(invadem)} pecas sobre a area da antena: " +
                   ", ".join(f"{r}" for r, _d in sorted(invadem)[:6]))
        else:
            ok.append(f"RF1: a area da antena ({ant[2]-ant[0]:.2f} x "
                      f"{ant[3]-ant[1]:.2f} mm) esta livre de componente")

    # -- RF3: 5 mm em volta da area da antena --------------------------------
    if ant:
        # The module's own decoupling is not a foreign interference source,
        # and it CANNOT obey both rules of this datasheet at once: 7.2 wants
        # it 0.5 mm from the power pin and that pin is 2.1 mm from the
        # antenna band. The exemption is named, printed and limited to those
        # two capacitors.
        perto = sorted((dist_caixas(p["caixa"], ant), r)
                       for r, p in pecas.items()
                       if r != MODULO and r not in MP.DO_MODULO)
        dentro = [(d, r) for d, r in perto if d < FOLGA_ANTENA]
        proprias = sorted((dist_caixas(pecas[r]["caixa"], ant), r)
                          for r in MP.DO_MODULO if r in pecas)
        if dentro:
            falhou("RF3", f"{len(dentro)} pecas alheias a menos de "
                   f"{FOLGA_ANTENA:.0f} mm da area da antena: " +
                   ", ".join(f"{r} {d:.1f}" for d, r in dentro[:8]))
        else:
            ok.append(f"RF3: a peca alheia mais proxima da area da antena e "
                      f"{perto[0][1]} a {perto[0][0]:.1f} mm; o desacoplamento "
                      "do proprio modulo fica mais perto de proposito (" +
                      ", ".join(f"{r} {d:.1f}" for d, r in proprias) + ")")

    # -- RF4: a antena fora do plano de terra --------------------------------
    #
    # Esta regra mudou de pergunta em 2026-09-28 junto com o modulo, e a
    # diferenca importa: o ME54BS13 tinha antena de TRACO e a ficha dele
    # mandava vazar a placa embaixo, deixando a regiao suspensa. O
    # HOLYIOT-26001-A tem antena CERAMICA e o guia de montagem do fabricante
    # pede outra coisa - a antena para fora do plano de terra da placa
    # hospedeira, com "best" na borda, "good" no canto e "bad" no meio.
    # Continuar cobrando o vazado seria cobrar a ficha de uma peca que nao
    # esta mais na placa.
    if ant:
        # quanto da faixa da antena tem plano de terra por baixo
        planos = [z for z in getattr(M, "ZONES", ())
                  if z[0].startswith("KEEPOUT_ANTENA")]
        livre = any(z[1][0] <= ant[0] + 0.01 and z[1][2] >= ant[2] - 0.01 and
                    z[1][1] <= ant[1] + 0.01 and z[1][3] >= ant[3] - 0.01
                    for z in planos)
        na_borda = ant[2] >= M.W - 0.05 or ant[0] <= 0.05 or             ant[3] >= M.H - 0.05 or ant[1] <= 0.05
        if not planos:
            falhou("RF4", "nao mede nada: nao ha zona de exclusao declarada "
                   "para a antena em make_dxf.ZONES")
        elif not livre:
            falhou("RF4", "a faixa da antena nao esta inteira dentro da zona "
                   "sem cobre: parte dela ficaria sobre o plano de terra")
        elif not na_borda:
            falhou("RF4", "a antena nao encosta em borda nenhuma da placa; o "
                   "fabricante chama o meio da placa de a pior posicao")
        else:
            ok.append("RF4: a faixa da antena esta inteira dentro da zona sem "
                      "cobre e encosta na borda da placa")

    # -- RF9: a tabela de isolacao da 7.2 ------------------------------------
    if MODULO in pecas:
        cm = pecas[MODULO]["caixa"]
        perto_demais, medidos = [], []
        for tipo, limite_mm, refs in ISOLACAO:
            pior = None
            for r in refs:
                if r not in pecas:
                    continue
                d = dist_caixas(cm, pecas[r]["caixa"])
                if pior is None or d < pior[0]:
                    pior = (d, r)
            if pior is None:
                continue
            medidos.append((tipo, limite_mm, pior))
            if pior[0] < limite_mm:
                perto_demais.append((tipo, limite_mm, pior))
        if perto_demais:
            falhou("RF9", "; ".join(
                f"{t}: {p[1]} a {p[0]:.1f} mm, a ficha pede {lim:.0f}"
                for t, lim, p in perto_demais))
        elif medidos:
            ok.append("RF9: " + "; ".join(
                f"{t}: {p[1]} a {p[0]:.1f} de {lim:.0f} mm"
                for t, lim, p in medidos))

    # -- US1: o par diferencial do USB ---------------------------------------
    # Not "is it routed" but "is it the pair the spec asks for". The width
    # that gives 90 ohm differential on this stack-up is computed in route.py
    # and printed here beside what is actually drawn, because a pair routed
    # at the wrong width is not a pair - it is two tracks - and nothing else
    # in the chain would ever say so.
    import route as _R
    # from the board's own net table, never from nets.py at run time
    _numeros = redes_do_arquivo()
    _por_num = {n: r for r, n in _numeros.items()}
    par = {}
    for r in ("USB_DP", "USB_DM"):
        sg = [q for q in seg if _por_num.get(q["n"], "") == r]
        comp = sum(math.hypot(q["b"][0] - q["a"][0], q["b"][1] - q["a"][1])
                   for q in sg)
        larg = sorted({round(q["w"], 3) for q in sg})
        par[r] = (len(sg), comp, larg)
    alvo = _R.LARGURA_USB_CALC
    faltando = [r for r, v in par.items() if v[0] == 0]
    if faltando:
        falhou("US1", "o par nao esta roteado: " + ", ".join(faltando))
    else:
        larguras = sorted({w for v in par.values() for w in v[2]})
        maior = max(larguras)
        if maior < alvo - 1e-6:
            falhou("US1", "o par esta roteado a " +
                   ", ".join(f"{w:.3f}" for w in larguras) +
                   f" mm, e 90 ohm diferenciais nesta pilha pedem "
                   f"{alvo:.3f} mm com {_R.PASSO_PAR:.1f} de afastamento. "
                   f"Comprimentos: " +
                   ", ".join(f"{r} {v[1]:.1f} mm" for r, v in par.items()) +
                   ". Tem de ser terminado a mao")
        else:
            ok.append("US1: o par esta roteado a " +
                      ", ".join(f"{w:.3f}" for w in larguras) +
                      f" mm, contra os {alvo:.3f} que dao 90 ohm")

    # -- AL5: o filtro pi no pino de alimentacao do modulo -------------------
    # 7.2, Power Supply Design: "For switching power supply applications, a
    # pi-type filter circuit footprint must be reserved near the module power
    # input pins." The module here is fed from the buck of the nPM1100, which is
    # switching, so the rule applies. What is measured is the SHAPE of a pi:
    # a series element between the rail and the pin, with a capacitor to
    # ground on each side of it. Whether the series part is a 0 ohm jumper or
    # a ferrite is a stuffing decision - the footprint is what the datasheet
    # asks to be reserved - but a rail with no series element at all has no
    # pi footprint to stuff. Here the module is fed from the nPM1100's buck
    # through FB201, with C203 upstream and C201 and C202 at the pin.
    alim_mod = [q["rede"] for q in pecas.get(MODULO, {}).get("pads", [])
                if q.get("pad") == "VDD" or q["rede"] in ("3V0_MOD",)]
    rede_mod = alim_mod[0] if alim_mod else None
    if rede_mod and rede_mod in N.NETS:
        # the series element: a two terminal part on this net whose other end
        # is on a different net
        serie = []
        for ref, _p in N.NETS[rede_mod]:
            if ref == MODULO or ref not in P.PARTS:
                continue
            if len(P.PARTS[ref].pins) != 2:
                continue
            outras = {n for n, v in N.NETS.items()
                      if n != rede_mod and any(t[0] == ref for t in v)}
            if outras - {"GND"}:
                serie.append((ref, sorted(outras - {"GND"})[0]))
        caps_mod = [r for r, _p in N.NETS[rede_mod]
                    if r.startswith("C") and r in P.PARTS]
        montante = serie[0][1] if serie else None
        caps_up = [r for r, _p in N.NETS.get(montante, [])
                   if r.startswith("C") and r in P.PARTS] if montante else []
        if not serie:
            falhou("AL5", f"o trilho {rede_mod} chega ao pino do modulo sem "
                   "elemento em serie: nao ha footprint de pi para povoar")
        elif not caps_mod or not caps_up:
            falhou("AL5", f"{serie[0][0]} esta em serie entre {montante} e "
                   f"{rede_mod}, mas faltam capacitores de um dos lados "
                   f"(montante {len(caps_up)}, lado do modulo {len(caps_mod)})")
        else:
            pino = [q for q in pecas[MODULO]["pads"] if q["rede"] == rede_mod]
            d = "?"
            if pino and serie[0][0] in pecas:
                p0 = (pino[0]["x"], pino[0]["y"])
                d = "%.1f" % min(math.hypot(a["x"] - p0[0], a["y"] - p0[1])
                                 for a in pecas[serie[0][0]]["pads"])
            ok.append(f"AL5: filtro pi do modulo montado como "
                      f"{'+'.join(caps_up)} | {serie[0][0]} | "
                      f"{'+'.join(caps_mod)}, com o elemento em serie a "
                      f"{d} mm do pino de alimentacao")

    # -- AL1: desacoplamento --------------------------------------------------
    piores = []
    for cap, chip in MP.DECOPLA.items():
        # MP.DECOPLA also carries pull-ups and series resistors, which go
        # beside their chip for a different reason and are not held to the
        # decoupling distance: a pull-up 5 mm from the master is fine, a
        # decoupling capacitor 5 mm from the pin is not.
        if not cap.startswith("C"):
            continue
        if cap not in pecas or chip not in pecas:
            continue
        # and only a capacitor that decouples a SUPPLY PIN. C601 to C603 sit
        # across a key for debounce: they are in the table so the placer knows
        # where to put them, and holding them to a supply pin's distance is
        # measuring the wrong thing.
        if chip not in P.PARTS or len(P.PARTS[chip].pins) < 4:
            continue
        # and only a capacitor that decouples an IC. The rule reads "do
        # modulo de radio a 0,5 mm do pino; dos DEMAIS CIs, 2 mm" - a
        # connector is not an IC, and the capacitor that sits on the rail
        # leaving through one is bulk for the cable, not decoupling for a
        # supply pin. C404 on J401, the display's flat cable, was being held
        # to a chip's 2 mm at 3,1.
        if chip.startswith("J"):
            continue
        redes = {q["rede"] for q in pecas[cap]["pads"]} - {"GND", ""}
        alvo = [q for q in pecas[chip]["pads"] if q["rede"] in redes]
        if not alvo:
            continue
        d = min(min(math.hypot(a["x"] - b["x"], a["y"] - b["y"])
                    for b in alvo) for a in pecas[cap]["pads"])
        piores.append((d, cap, chip))
    piores.sort(reverse=True)
    acima = [t for t in piores if t[0] > limite(t[1])]
    media = sum(t[0] for t in piores) / len(piores) if piores else 0.0
    hf = [t for t in piores if limite(t[1]) == 2.0]
    if acima:
        falhou("AL1", f"{len(acima)} de {len(piores)} capacitores alem do limite "
               f"(media geral {media:.2f} mm): " +
               ", ".join(f"{c}->{u} {d:.1f} de {limite(c):.0f}"
                         for d, c, u in acima[:6]))
    else:
        ok.append(f"AL1: {len(piores)} capacitores dentro do limite; o pior de "
                  f"alta frequencia esta a {max(t[0] for t in hf):.2f} mm e o "
                  f"pior de reserva a {piores[0][0]:.2f} mm")

    # -- AL2: largura por IPC-2221 -------------------------------------------
    numeros = redes_do_arquivo()
    por_num = {n: r for r, n in numeros.items()}
    estreitas = []
    necks = 0
    for s in seg:
        rede = por_num.get(s["n"], "")
        if rede not in CORRENTE:
            continue
        i, _fonte = CORRENTE[rede]
        pedida = largura_ipc(i, interna=s["c"] in ("In1.Cu", "In2.Cu"))
        if s["w"] >= pedida - 1e-6:
            continue
        # A short stretch next to a pad is a neck-down, not an undersized
        # conductor: the copper on either side carries the heat away, and
        # IPC-2221's curve is for a conductor long enough to reach a steady
        # temperature. The rail that feeds the TPS7A02 has to neck to 0.2 mm
        # because the part's pad is 0.2 mm wide, and no width of track fixes
        # a pad.
        # A neck-down is not an undersized conductor: it is the track
        # matching a pad that is narrower than the rule wants, and no width
        # of copper fixes a pad. Recognised by what it actually is - one end
        # sitting on a pad of this net whose narrow side is no wider than the
        # track - instead of by a length that someone picked.
        colado = any(
            q["rede"] == rede and
            math.hypot(q["x"] - e[0], q["y"] - e[1]) < 0.6
            for e in (s["a"], s["b"]) for q in pads)
        comp = math.hypot(s["b"][0] - s["a"][0], s["b"][1] - s["a"][1])
        if colado or comp < 2.0:
            necks += 1
            continue
        estreitas.append((rede, s["w"], pedida))
    if estreitas:
        piores_l = {}
        for rede, w, pedida in estreitas:
            piores_l[rede] = (w, pedida)
        falhou("AL2", f"{len(estreitas)} segmentos abaixo da largura IPC-2221: " +
               ", ".join(f"{r} {w:.2f} < {p:.2f} mm"
                         for r, (w, p) in sorted(piores_l.items())[:6]))
    elif seg:
        ok.append("AL2: nenhum trecho de alimentacao abaixo da largura IPC-2221 "
                  f"(10 C de subida, cobre de 35 um); {necks} estreitamentos "
                  "curtos junto a pad, que a norma nao cobra")
    else:
        falhou("AL2", "sem trilhas: nada a medir")

    # -- GN1: pad de terra com via -------------------------------------------
    gnd_num = numeros.get("GND")
    gnd_smd = [q for q in pads if q["rede"] == "GND" and q["smd"]]
    vias_gnd = [v for v in vias if v["n"] == gnd_num]
    sem = 0
    for q in gnd_smd:
        if not any(math.hypot(v["x"] - q["x"], v["y"] - q["y"]) < 2.0
                   for v in vias_gnd):
            sem += 1
    # F.Cu and B.Cu both carry a ground pour, so a pad without a via of its
    # own is still connected - KiCad ties it to the pour when it fills. What
    # the via buys is the short path down to In1.Cu, and that is what gets
    # counted: a pad without one has a longer return, not an open circuit.
    com = len(gnd_smd) - sem
    frac = com / len(gnd_smd) if gnd_smd else 0.0
    # The bar is "connected", not a fraction someone made up. Every outer
    # layer carries a ground pour, so a pad without a via of its own is still
    # tied to ground when KiCad fills. The via buys the SHORT path down to
    # the inner plane, and how many have one is a quality number worth
    # printing, not a rule to pass or fail: inventing a threshold and then
    # tuning it until the board clears it measures nothing.
    faces = {"F.Cu", "B.Cu"}      # the two that get a pour, from make_pcb.py
    soltos = [q for q in gnd_smd if q["camada"] not in faces
              and not any(math.hypot(v["x"] - q["x"], v["y"] - q["y"]) < 2.0
                          for v in vias_gnd)]
    if soltos:
        falhou("GN1", f"{len(soltos)} pads de terra sem plano na propria face "
               "e sem via: ficam soltos")
    else:
        ok.append(f"GN1: os {len(gnd_smd)} pads de terra de superficie estao "
                  f"ligados; {com} deles ({frac:.0%}) por via propria ao plano "
                  f"interno, os outros {sem} pelo plano da propria face")

    # -- GN2: costura na borda ------------------------------------------------
    if vias_gnd:
        borda = [v for v in vias_gnd
                 if min(v["x"], v["y"], M.W - v["x"], M.H - v["y"]) < 3.0]
        if len(borda) < 2:
            falhou("GN2", f"so {len(borda)} vias de terra a menos de 3 mm da "
                   "borda: nao ha costura")
        else:
            maior = 0.0
            for v in borda:
                d = min(math.hypot(v["x"] - w["x"], v["y"] - w["y"])
                        for w in borda if w is not v)
                maior = max(maior, d)
            if maior > 5.0:
                falhou("GN2", f"a maior falha na costura da borda e {maior:.1f} mm "
                       "(o limite e 5)")
            else:
                ok.append(f"GN2: {len(borda)} vias na borda, maior vao {maior:.1f} mm")
    else:
        falhou("GN2", "sem vias de terra: nao ha costura")

    # -- ME1: a placa no envelope do pod --------------------------------------
    # docs/02-hardware.md: o pod tem 60 x 20 mm POR FORA como alvo, com
    # paredes de 1,2 mm, o que deixa 57,6 x 17,6 por dentro. O pod real e o
    # de pod/make_pod.py, e o dry run dele mede a placa contra a cavidade
    # que ele desenha; aqui a pergunta e se a placa ainda cabe no ALVO.
    POD_FORA, PAREDE = (60.0, 20.0), 1.2
    folga = ((POD_FORA[0] - 2 * PAREDE) - M.W) / 2, ((POD_FORA[1] - 2 * PAREDE) - M.H) / 2
    if min(folga) < 0.5:
        falhou("ME1", f"folga de {folga[0]:.1f} x {folga[1]:.1f} mm no envelope "
                      f"alvo do pod ({POD_FORA[0]:g} x {POD_FORA[1]:g} por fora)")
    else:
        ok.append(f"ME1: a placa de {M.W:g} x {M.H:g} deixa {folga[0]:.1f} mm em "
                  f"cada ponta e {folga[1]:.1f} mm de cada lado no envelope alvo "
                  f"do pod ({POD_FORA[0]:g} x {POD_FORA[1]:g} por fora)")

    # -- AN1: o canto analogico longe do buck e do modulo ---------------------
    if "U301" in pecas:
        perto_buck, perto_mod = [], []
        for r in ANALOGICO:
            if r not in pecas:
                continue
            for ch in CHAVEADOS:
                if ch in pecas:
                    d = dist_caixas(pecas[r]["caixa"], pecas[ch]["caixa"])
                    if d < FOLGA_ANALOGICO_BUCK:
                        perto_buck.append((d, r, ch))
            if MODULO in pecas:
                d = dist_caixas(pecas[r]["caixa"], pecas[MODULO]["caixa"])
                if d < FOLGA_ANALOGICO_MODULO:
                    perto_mod.append((d, r, MODULO))
        d_buck = min((dist_caixas(pecas[r]["caixa"], pecas[ch]["caixa"])
                      for r in ANALOGICO if r in pecas for ch in CHAVEADOS
                      if ch in pecas), default=None)
        d_mod = min((dist_caixas(pecas[r]["caixa"], pecas[MODULO]["caixa"])
                     for r in ANALOGICO if r in pecas), default=None)
        if d_buck is None or d_mod is None:
            falhou("AN1", "nao mede nada: falta o conversor, o buck ou o modulo "
                          "na placa")
        elif perto_buck or perto_mod:
            falhou("AN1", "; ".join(
                f"{r} a {d:.1f} mm de {ch}" for d, r, ch in
                sorted(perto_buck + perto_mod)[:6]) +
                f" (o projeto pede {FOLGA_ANALOGICO_BUCK:.0f} do buck e "
                f"{FOLGA_ANALOGICO_MODULO:.0f} do modulo)")
        else:
            ok.append(f"AN1: o canto analogico ({len([r for r in ANALOGICO if r in pecas])} "
                      f"pecas) fica a {d_buck:.1f} mm do buck e a {d_mod:.1f} mm "
                      f"do modulo")

    # -- AN2: o filtro da ponte junto do conversor, e a referencia da excitacao
    if "U301" in pecas:
        pinos = {q["pad"]: q for q in pecas["U301"]["pads"]}
        # each filter part against the converter pin it serves: the input
        # capacitors and resistors to AIN0/AIN1, the reference capacitor to
        # REFP0. 5 mm is the same reach as a bulk capacitor's (LIMITE_RESERVA)
        FILTRO = {"R301": "9", "R302": "8", "C301": "9", "C302": "9",
                  "C303": "8", "C304": "7"}
        longe = []
        medidos = []
        for r, pino in FILTRO.items():
            if r not in pecas or pino not in pinos:
                continue
            p0 = pinos[pino]
            d = min(math.hypot(a["x"] - p0["x"], a["y"] - p0["y"])
                    for a in pecas[r]["pads"])
            medidos.append((d, r))
            if d > LIMITE_RESERVA:
                longe.append((d, r))
        # and the ratiometric tie: REFP0 on the same net as the bridge's E+
        refp = pinos.get("7", {}).get("rede", "")
        eplus = next((q["rede"] for q in pecas.get("J301", {}).get("pads", [])
                      if q["pad"] == "1"), "")
        if not medidos:
            falhou("AN2", "nao mede nada: o filtro da ponte nao esta na placa")
        elif longe or refp != eplus or not refp:
            falhou("AN2", (", ".join(f"{r} a {d:.1f} mm do pino" for d, r in longe)
                           + "; " if longe else "") +
                   (f"REFP0 esta em {refp or '?'} e a excitacao da ponte em "
                    f"{eplus or '?'}: a medicao nao e ratiometrica"
                    if refp != eplus or not refp else ""))
        else:
            pior = max(medidos)
            ok.append(f"AN2: {len(medidos)} pecas do filtro a no maximo "
                      f"{pior[0]:.1f} mm do seu pino ({pior[1]}); REFP0 e o E+ da "
                      f"ponte estao no mesmo no ({refp})")

    # -- AL6: via sob pad termico ---------------------------------------
    # Which pad of which part is a thermal pad. It is the one the datasheet
    # numbers last and connects to ground, and the two that matter here say
    # so by name.
    TERMICOS = {("U301", "17"), ("U101", "25"), ("U402", "7"), ("U102", "9")}
    sobre_termico = []
    for q in pads:
        if (q["ref"], q["pad"]) not in TERMICOS:
            continue
        for v in vias:
            # "sob o pad" e o pad mais 0,5 mm de margem, nao 1,2 mm fixos:
            # com 1,2 a regra acusou uma via de terra a 1,3 mm do centro de
            # um pad de 0,58, que esta a 1 mm do cobre dele. A ponte de
            # mascara entre via e pad e assunto do DRC, que a mede
            if (abs(v["x"] - q["x"]) < q["hw"] + 0.5
                    and abs(v["y"] - q["y"]) < q["hh"] + 0.5):
                sobre_termico.append((q["ref"], q["pad"],
                                      round(math.hypot(v["x"] - q["x"],
                                                       v["y"] - q["y"]), 2)))
                break
    if sobre_termico:
        falhou("AL6", f"{len(sobre_termico)} vias sobre um pad termico: " +
               ", ".join(f"{r}.{p} a {d} mm" for r, p, d in sobre_termico[:6]))
    else:
        ok.append(f"AL6: nenhuma via sobre os {len(TERMICOS)} pads termicos")

    # -- ME3: o 2D e o 3D contam a mesma historia ------------------------
    import footprints as _FP
    for _n in _FP.PACOTE:
        try:
            fp_load.carregar(_n)
        except FileNotFoundError:
            pass
    div = _FP.conferir_2d_3d()
    if div:
        falhou("ME3", f"{len(div)} encapsulamentos em que a ficha e o "
               "footprint discordam: " + "; ".join(div[:3]))
    else:
        ok.append(f"ME3: os {len(_FP.PACOTE)} encapsulamentos com cota de "
                  "ficha cabem no footprint desenhado para eles e batem com "
                  "o contorno")

    # -- ME2: cabe sob a tampa, e a face de tras e plana? ------------------
    # docs/02 (Pod) gives the stack: the cell under the board, the parts of
    # the front under the lid. So the front has one ceiling, make_dxf's
    # TETO_TAMPA, and the back has NONE: a part with a body on the back
    # would stand on the cell. A part taller than the shadow it stands in
    # does not fit, and no DRC will ever say so - which is the whole reason
    # the heights had to come from the datasheets.
    TETOS = ((M.SOMBRA_TAMPA, M.TETO_TAMPA, False),)
    altos = []
    sem_altura = []
    sem_zona: set = set()
    for ref, pe in sorted(pecas.items()):
        nome_fp = FPS.FP[ref][0] if ref in FPS.FP else None
        if nome_fp is None:
            continue
        medida = altura_do_footprint(nome_fp)
        if medida is None:
            sem_altura.append(ref)
            continue
        h, _fonte = medida
        if ref in M.ATRAVESSA_TAMPA:
            # the connector goes through the lid's window: the pod's dry
            # run measures its face against the lid, not this ceiling
            continue
        for znome, teto, atras in TETOS:
            try:
                z = zona(znome)
            except KeyError:
                # A zona nao existe: ate 2026-09-26 isto era um `continue`
                # mudo e a regra saia "ok" sem medir peca nenhuma - as
                # sombras foram tiradas do make_dxf de proposito, porque a
                # caixa nao esta definida, e a regra continuou passando.
                sem_zona.add(znome)
                continue
            if pe["atras"] != atras:
                continue
            if dist_caixas(pe["caixa"], z) >= 0:
                continue                      # not under this shadow
            if h > teto + 1e-9:
                altos.append((ref, h, teto, znome))
        if pe["atras"] and h > 1e-9:
            altos.append((ref, h, 0.0, "a face de tras (plana, sob a celula)"))
    if sem_zona:
        falhou("ME2", "nao mede nada: as zonas " + ", ".join(sorted(sem_zona))
                      + " nao existem no make_dxf - o teto da tampa sobre a "
                      "placa nao esta definido em arquivo nenhum")
    elif altos:
        falhou("ME2", f"{len(altos)} pecas mais altas que o teto da sombra em "
               "que estao: " +
               ", ".join(f"{r} {h:.2f} contra {t:.1f} mm"
                         for r, h, t, _z in altos[:6]))
    else:
        n_tras = sum(1 for pe in pecas.values() if pe["atras"])
        ok.append(f"ME2: nenhuma peca da frente passa do teto da tampa "
                  f"({TETOS[0][1]:.1f} mm) e as {n_tras} da face de tras sao pads "
                  f"sem corpo; {len(sem_altura)} pecas sem altura conhecida")

    # -- IM1: os eixos do acelerometro --------------------------------------
    # Trocar radial por tangencial mete o termo centripeto dentro da
    # cadencia e a potencia sai errada SEM NENHUM SINAL DE ERRO. O fato
    # fisico que decide isso e o canto do pino 1 do footprint contra a
    # convencao da ficha, e ate 2026-09-27 nenhum documento o carregava.
    #
    # Lido na ficha BST-BMA400-DS000-14, 8.2, pagina 112, na tabela de
    # orientacao (quatro vistas de cima com o ponto do pino 1 e o vetor da
    # gravidade para baixo): com o PONTO NO CANTO SUPERIOR ESQUERDO da
    # vista de cima, +X aponta para CIMA da pagina e +Y para a ESQUERDA,
    # com +Z saindo da face que leva o ponto.
    FICHA_IMU = HERE.parent / "datasheets" / "bst-bma400-ds000-14.pdf"
    IMU = "U401"
    if not FICHA_IMU.exists():
        falhou("IM1", f"nao mede nada: {FICHA_IMU.name} nao esta em "
                      "datasheets/, entao a convencao de eixos do "
                      "acelerometro nao tem fonte para conferir")
    elif IMU not in pecas:
        falhou("IM1", f"nao mede nada: {IMU} nao esta na placa")
    else:
        texto_fp = fp_load.carregar(FPS.FP[IMU][0])[0]
        arv_fp = fp_load.parse(texto_fp)
        p1 = None
        for q in fp_load.kids(arv_fp, "pad"):
            if str(q[1]) == "1":
                a = fp_load.kid(q, "at")
                p1 = (float(a[1]), float(a[2]))
        pe = pecas[IMU]
        ang = int(round(pe["ang"])) % 360
        atras = pe["atras"]
        if p1 is None:
            falhou("IM1", f"o footprint de {IMU} nao tem pad 1 para medir")
        else:
            # The pin-1 corner in FOOTPRINT coordinates (KiCad: +x right,
            # +y down). Then the sheet's top view: screen-up is -y of the
            # board, screen-right is +x.
            quadrante = ("-x" if p1[0] < 0 else "+x", "-y" if p1[1] < 0 else "+y")
            # With pin 1 at (-x, -y) - the top left of the top view - the
            # datasheet puts +X up the page and +Y to the left, which in
            # board terms is -y and -x. A rotation of the part turns both.
            base = {"X": (0.0, -1.0), "Y": (-1.0, 0.0)}   # (dx, dy) no board
            if quadrante != ("-x", "-y"):
                base = None
            if base is None:
                falhou("IM1", f"o pino 1 do footprint de {IMU} esta em "
                              f"{quadrante[0]}{quadrante[1]}, e a leitura da "
                              "ficha so cobre o canto superior esquerdo da "
                              "vista de cima: refazer a medida")
            elif atras:
                falhou("IM1", f"{IMU} esta na face de tras, e a face inverte "
                              "um eixo: a leitura da ficha foi feita para a "
                              "face da frente")
            else:
                import math as _m
                r = _m.radians(ang)
                eixos = {}
                for nome_eixo, (dx, dy) in base.items():
                    nx = dx * _m.cos(r) + dy * _m.sin(r)
                    ny = -dx * _m.sin(r) + dy * _m.cos(r)
                    eixos[nome_eixo] = (round(nx, 6), round(ny, 6))
                # the board's long axis is x, and it is the one that runs
                # along the crank arm (04-placa.md): an axis along x is
                # RADIAL, one along y is TANGENTIAL
                def _papel(v):
                    if abs(v[0]) > abs(v[1]):
                        return "radial", ("+x" if v[0] > 0 else "-x")
                    return "tangencial", ("+y" if v[1] > 0 else "-y")
                px, sx = _papel(eixos["X"])
                py, sy = _papel(eixos["Y"])
                # THE OTHER SIDE. Until 2026-09-27 this rule carried the
                # firmware's answer as a constant, so it went on failing
                # after the firmware was changed to agree with the board -
                # a rule that promises to compare two sides has to read
                # both. These are the Kconfig defaults, read from the file.
                KCONFIG = HERE.parents[1] / "zephyr_app" / "Kconfig"
                EIXO = {0: "X", 1: "Y", 2: "Z"}
                fw = {}
                if KCONFIG.exists():
                    import re as _re
                    texto_k = KCONFIG.read_text(encoding="utf-8")
                    for simbolo in ("PM_IMU_AXIS_RADIAL", "PM_IMU_AXIS_TANGENTIAL",
                                    "PM_IMU_RADIAL_SIGN"):
                        alvo = texto_k + chr(10) + "config "
                        m = _re.search(r"^config " + simbolo + r"\b(.*?)^config ",
                                       alvo, _re.S | _re.M)
                        if not m:
                            continue
                        d = _re.search(r"^\s*default\s+(-?\d+)\s*$", m.group(1),
                                       _re.M)
                        if d:
                            fw[simbolo] = int(d.group(1))
                faltam = [s for s in ("PM_IMU_AXIS_RADIAL", "PM_IMU_AXIS_TANGENTIAL",
                                      "PM_IMU_RADIAL_SIGN") if s not in fw]
                if faltam:
                    falhou("IM1", "nao mede nada: " +
                           (f"{KCONFIG} nao existe" if not KCONFIG.exists()
                            else "sem default para " + ", ".join(faltam)) +
                           ", entao o lado do firmware nao pode ser lido")
                else:
                    # what the board says, as the firmware spells it
                    papel_do_eixo = {"X": (px, sx), "Y": (py, sy)}
                    rad_fw = EIXO.get(fw["PM_IMU_AXIS_RADIAL"], "?")
                    tan_fw = EIXO.get(fw["PM_IMU_AXIS_TANGENTIAL"], "?")
                    sinal_fw = fw["PM_IMU_RADIAL_SIGN"]
                    # the radial is positive OUTWARDS, away from the crank's
                    # centre; the board's outward end is +x (04-placa.md), so
                    # an axis pointing to -x needs a sign of -1
                    erros = []
                    if papel_do_eixo.get(rad_fw, ("?", "?"))[0] != "radial":
                        erros.append(f"o firmware chama {rad_fw} de radial e na "
                                     f"placa {rad_fw} e "
                                     f"{papel_do_eixo.get(rad_fw, ('?',))[0]}")
                    if papel_do_eixo.get(tan_fw, ("?", "?"))[0] != "tangencial":
                        erros.append(f"o firmware chama {tan_fw} de tangencial e "
                                     f"na placa {tan_fw} e "
                                     f"{papel_do_eixo.get(tan_fw, ('?',))[0]}")
                    sentido = papel_do_eixo.get(rad_fw, ("", "+x"))[1]
                    sinal_placa = 1 if sentido == "+x" else -1
                    if sinal_fw != sinal_placa:
                        erros.append(f"o radial da placa aponta para {sentido}, "
                                     f"que pede PM_IMU_RADIAL_SIGN {sinal_placa}, "
                                     f"e o firmware tem {sinal_fw}")
                    if erros:
                        falhou("IM1", f"{IMU} a {ang} graus na frente: " +
                               "; ".join(erros) + ". Ou o U401 gira, ou os "
                               "simbolos do Kconfig mudam (04-placa.md)")
                    else:
                        ok.append(f"IM1: {IMU} a {ang} graus na frente, pino 1 em "
                                  f"{quadrante[0]}{quadrante[1]}: X do sensor {px} "
                                  f"para {sx}, Y {py} para {sy}, Z saindo da face "
                                  f"da frente (ficha 8.2); o firmware diz radial "
                                  f"{rad_fw}, tangencial {tan_fw}, sinal "
                                  f"{sinal_fw} - os dois lados concordam")

    # -- ME7: o land pattern do modulo contra um desenho independente ------
    # O footprint do modulo e desenhado aqui a partir da ficha, e a ficha
    # NAO traz land pattern oficial. Um desenho de terceiros do mesmo
    # modulo e a unica conferencia independente que existe, e em
    # 2026-09-27 ninguem dos dois projetos o tinha comparado. A regra nao
    # passa calada quando o arquivo nao esta: diz que nao pode medir.
    REF_MODULO = HERE.parent / "datasheets" / "ME54BS13_3rdparty_girishji.kicad_mod"
    TOL_ME7 = 0.05        # mm, por eixo e por lado do pad
    if not REF_MODULO.exists():
        falhou("ME7", f"nao mede nada: {REF_MODULO.name} nao esta em "
                      "datasheets/ (pasta fora do git), entao o land pattern "
                      "do modulo nao tem conferencia independente")
    else:
        def _pads_do_texto(texto: str):
            arv = fp_load.parse(texto)
            saida = {}
            for q in fp_load.kids(arv, "pad"):
                a = fp_load.kid(q, "at")
                s = fp_load.kid(q, "size")
                if not a or not s:
                    continue
                w, h = float(s[1]), float(s[2])
                # a pad carries its OWN angle, and a 0,7 x 1,5 pad turned
                # 90 degrees is the same copper as a 1,5 x 0,7 pad at 0.
                # Comparing the numbers without it made the twenty
                # castellated pads of the reference look 0,8 mm wrong when
                # they are the same pad (2026-09-27).
                ang = int(round(float(a[3]))) % 180 if len(a) > 3 else 0
                if ang == 90:
                    w, h = h, w
                saida[str(q[1])] = (float(a[1]), float(a[2]), w, h)
            return saida

        nosso = _pads_do_texto(fp_load.carregar(FPS.FP[MODULO][0])[0])
        deles = _pads_do_texto(REF_MODULO.read_text(encoding="utf-8"))

        def _centro(d):
            xs = [v[0] for v in d.values()]
            ys = [v[1] for v in d.values()]
            return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)

        if not nosso or not deles:
            falhou("ME7", "um dos dois desenhos nao tem pad nenhum para medir")
        else:
            cn, cd = _centro(nosso), _centro(deles)
            faltam = sorted(set(deles) - set(nosso))
            sobram = sorted(set(nosso) - set(deles))
            piores = []
            for nome_pad in sorted(set(nosso) & set(deles)):
                ax, ay, aw, ah = nosso[nome_pad]
                bx, by, bw, bh = deles[nome_pad]
                dx = abs((ax - cn[0]) - (bx - cd[0]))
                dy = abs((ay - cn[1]) - (by - cd[1]))
                dw = abs(aw - bw)
                dh = abs(ah - bh)
                piores.append((max(dx, dy, dw, dh), nome_pad, dx, dy, dw, dh))
            piores.sort(reverse=True)
            fora = [q for q in piores if q[0] > TOL_ME7]
            if faltam or sobram or fora:
                falhou("ME7", (f"{len(faltam)} pads faltando, {len(sobram)} a "
                               f"mais, {len(fora)} fora de {TOL_ME7:g} mm" +
                               ("; pior " + ", ".join(
                                   f"{n} dx {a:.3f} dy {b:.3f} dw {c:.3f} dh {e:.3f}"
                                   for _m, n, a, b, c, e in fora[:4]) if fora else "")))
            else:
                ok.append(f"ME7: os {len(nosso)} pads do modulo batem com o "
                          f"desenho independente ({REF_MODULO.name}): desvio "
                          f"maximo {piores[0][0]:.3f} mm, tolerancia "
                          f"{TOL_ME7:g}")

    # -- ME4: a boca do conector de borda aponta para fora? ------------------
    # O 2D nao responde isto e o DRC muito menos: as ilhas de um receptaculo
    # USB-C sao quase simetricas em y, entao a peca "cabe" nos dois sentidos,
    # e a diferenca esta so no corpo. Em 2026-09-25 o J101 passou o dia a 180
    # graus, com a boca 10 mm para dentro da placa, e quem viu foi o dono - no
    # desenho 3D, duas vezes, porque da primeira eu "corrigi" para o lado
    # errado. Aqui a pergunta e feita ao STEP do fabricante e nao a um numero
    # decorado: um raio atravessa o corpo ao longo do eixo do conector, na
    # meia altura da cavidade. Do lado da boca ele entra na parede externa e
    # so reencontra material milimetros adiante, que e o vao onde o plugue
    # entra; do lado de tras bate em material logo na entrada. O lado com o
    # vao tem de ser o que olha para a borda.
    for ref in sorted(CORPOS_CONFERIDOS):
        achado = _ilhas_sob_o_corpo(ref, pecas)
        if achado is None:
            falhou("ME4", f"{ref}: nao achei o corpo 3D para conferir")
            continue
        fora, total, caixa = achado
        if fora:
            falhou("ME4", f"{ref}: {len(fora)} das {total} ilhas de solda "
                          f"ficam FORA do corpo do modelo 3D "
                          f"({' '.join(sorted(set(fora))[:6])}); o modelo esta "
                          f"deslocado ou girado em relacao ao footprint")
        else:
            ok.append(f"ME4: as {total} ilhas de {ref} ficam sob o corpo do "
                      f"modelo do fabricante")

    # -- ME5: os rabichos do modelo ficam sobre as ilhas de sinal? ----------
    # A pergunta que a ME4 nao responde: de que lado esta a peca. Medido nos
    # corpos pequenos e finos do GLB que encostam na placa, contra o centro
    # das ilhas de sinal do footprint.
    for ref in sorted(RABICHOS_CONFERIDOS):
        achado = _rabichos_sobre_as_ilhas(ref, pecas)
        if achado is None:
            falhou("ME5", f"{ref}: nao achei rabichos de solda no modelo 3D "
                          "para conferir")
            continue
        media, n_rab, ci, meio = achado
        if media < 0.0:
            falhou("ME5", f"{ref}: o que sai do corpo do modelo junto da placa "
                          f"(os rabichos, {n_rab} faces) esta a {-media:.1f} mm "
                          "do centro do corpo pelo lado OPOSTO ao das ilhas de "
                          f"sinal (({ci[0]:.1f}; {ci[1]:.1f})): o modelo esta "
                          "girado 180 graus em relacao ao footprint")
        else:
            ok.append(f"ME5: os rabichos de {ref} saem do corpo pelo lado das "
                      f"ilhas de sinal ({media:.1f} mm do centro, corpo de "
                      f"{meio:.1f} de meia largura; {n_rab} faces)")

    # -- ME6: cada corpo 3D com o eixo e os lados do seu footprint ----------
    # Toda peca que tem modelo, do 0402 ao modulo: a caixa do corpo contra
    # o F.Fab, e as pernas contra as fileiras de ilhas. E a pergunta do dono
    # sobre os passivos e os CIs "girados", respondida peca a peca.
    girados = []
    n_medidos = 0
    sem_corpo = []
    for ref in sorted(pecas):
        if ref.startswith(("TP", "REF", "JP")):
            continue
        achado = _corpo_bate_com_o_footprint(ref, pecas)
        if achado is None:
            sem_corpo.append(ref)
            continue
        n_medidos += 1
        if achado["eixo"] != "ok" or achado["lados"] == "girado 180":
            girados.append((ref, achado))
    if n_medidos == 0:
        falhou("ME6", "nao mediu corpo nenhum: o GLB nao existe ou nao tem "
                      "corpo sobre a placa (rode make_3d.py)")
    elif girados:
        falhou("ME6", f"{len(girados)} de {n_medidos} corpos fora do eixo ou "
                      "do lado das ilhas: " +
                      "; ".join(f"{r} {a['eixo'] if a['eixo'] != 'ok' else a['lados']} "
                                f"(corpo {a['modelo'][0]:.2f} x {a['modelo'][1]:.2f}, "
                                f"F.Fab {a['fab'][0]:.2f} x {a['fab'][1]:.2f})"
                                for r, a in girados[:6]))
    else:
        ok.append(f"ME6: os {n_medidos} corpos 3D medidos tem o eixo do F.Fab "
                  f"e as pernas do lado das ilhas; {len(sem_corpo)} pecas sem "
                  "corpo ou sem F.Fab para medir")

    # -- RT1: a placa esta inteira? ------------------------------------------
    # O DRC do KiCad com TODAS as severidades. Ate 2026-09-25 as rodadas a
    # mao usavam --severity-error, e "0 itens desconectados" saiu impresso
    # em documento e em pull request enquanto havia 55: item desconectado e
    # aviso, e o filtro de erros o esconde.
    import subprocess
    sys.path.insert(0, str(HERE))
    import make_3d as _M3
    rel = HERE / "_drc.json"
    r = subprocess.run([str(_M3.KICAD_CLI), "pcb", "drc", "--severity-all",
                        "--format", "json", "--output", str(rel), str(PCB)],
                       capture_output=True, text=True)
    if not rel.exists():
        falhou("RT1", "o kicad-cli nao rodou o DRC: " + r.stderr.strip()[:120])
    else:
        import json as _json
        d = _json.loads(rel.read_text(encoding="utf-8"))
        soltos = d.get("unconnected_items", [])
        por_rede: dict[str, int] = {}
        for u in soltos:
            for it in u.get("items", []):
                s = it.get("description", "")
                if "[" in s and "]" in s:
                    n = s[s.index("[") + 1:s.index("]")]
                    por_rede[n] = por_rede.get(n, 0) + 1
        viol = d.get("violations", [])
        tipos: dict[str, int] = {}
        for v in viol:
            tipos[v.get("type", "?")] = tipos.get(v.get("type", "?"), 0) + 1
        if soltos:
            piores = ", ".join(f"{k} {v}" for k, v in
                               sorted(por_rede.items(), key=lambda kv: -kv[1])[:8])
            falhou("RT1", f"{len(soltos)} itens desconectados em "
                          f"{len(por_rede)} redes ({piores}); e o DRC completo "
                          f"tem {len(viol)} violacoes: "
                          + ", ".join(f"{k} {v}" for k, v in sorted(tipos.items())))
        else:
            ok.append(f"RT1: 0 itens desconectados no DRC completo; "
                      f"{len(viol)} violacoes de qualquer severidade"
                      + (" (" + ", ".join(f"{k} {v}" for k, v in sorted(tipos.items())) + ")"
                         if viol else ""))

    # -- resultado -------------------------------------------------------------
    for linha in ok:
        print(f"  ok      {linha}")
    print()
    for rid, msg in achados:
        fonte = next((f for i, _d, f in REGRAS if i == rid), "")
        print(f"  FALHA   {rid}: {msg}")
        print(f"          fonte: {fonte}")
    print()
    medidas = {r for r, _ in achados} | {linha.split(":")[0] for linha in ok}
    naomedidas = [(i, d, f) for i, d, f in REGRAS if i not in medidas]
    if naomedidas:
        print("  nao medido aqui (precisa de bancada, do empilhamento do "
              "fabricante ou de modelo 3D):")
        for i, d, _f in naomedidas:
            print(f"    {i}: {d}")
    print()
    print(f"{len(ok)} regras medidas e cumpridas, {len(achados)} violadas, "
          f"{len(naomedidas)} nao medidas")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main())
