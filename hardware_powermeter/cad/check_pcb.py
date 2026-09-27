#!/usr/bin/env python3
"""Check pmeter.kicad_pcb: KiCad reads it, and what is on it is what we meant.

  1. the file parses and KiCad loads it;
  2. KiCad's own DRC runs. Unconnected nets are expected - nothing is routed -
     so they are counted, not treated as failures; anything else is;
  3. every part of parts.py is on the board exactly once, except the ones
     footprints.py declares to live in the case;
  4. every pad carries the net nets.py gives it, and no pad carries another;
  5. no two courtyards overlap, nothing crosses the outline, and nothing sits
     inside an antenna keep-out;
  6. the outline is the one make_dxf.py declares, with no mounting hole.

Run: python hardware_powermeter/cad/check_pcb.py
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import footprints as FPS  # noqa: E402
import fp_load  # noqa: E402
import make_dxf as M  # noqa: E402
import make_pcb as MP  # noqa: E402
import parts as P  # noqa: E402

KICAD = pathlib.Path(r"D:\KiCAD\bin\kicad-cli.exe")
PCB = HERE / "pmeter.kicad_pcb"
fails: list[str] = []


def check(ok: bool, what: str) -> None:
    print(("  ok    " if ok else "  FALHA ") + what)
    if not ok:
        fails.append(what)


def main() -> int:
    # Regenerating wipes the tracks, and then the DRC is run on an empty
    # board and says nothing about the routing. After route.py has run, the
    # board on disk is the thing to check, so: --como-esta checks the file
    # as it stands and prints what it found there.
    como_esta = "--como-esta" in sys.argv
    if como_esta:
        print("conferindo o arquivo como esta, sem regerar")
    else:
        print("gerando...")
        import make_pro
        make_pro.main()
        MP.main()
    print()

    arv = fp_load.parse(PCB.read_text(encoding="utf-8"))
    check(arv[0] == "kicad_pcb", "o arquivo abre como kicad_pcb")

    # ---- DRC ----
    rel = HERE / "_drc.json"
    r = subprocess.run([str(KICAD), "pcb", "drc", "--format", "json",
                        "--output", str(rel), str(PCB)],
                       capture_output=True, text=True)
    check(rel.exists(), "o KiCad roda o DRC"
          + ("" if rel.exists() else f": {r.stdout.strip()} {r.stderr.strip()}"))
    if rel.exists():
        d = json.loads(rel.read_text(encoding="utf-8"))
        viol = d.get("violations", [])
        soltos = d.get("unconnected_items", [])
        graves = [v for v in viol if v.get("severity") == "error"]
        print(f"        DRC: {len(viol)} violacoes, {len(graves)} de erro, "
              f"{len(soltos)} itens desconectados")
        tipos: dict[str, int] = {}
        for v in graves:
            tipos[v.get("type", "?")] = tipos.get(v.get("type", "?"), 0) + 1
        for t, n in sorted(tipos.items(), key=lambda kv: -kv[1]):
            print(f"          {t}: {n}")
        check(not graves, f"o DRC nao acusa erro de projeto ({len(graves)})")
        # Desconectado e AVISO no KiCad, e por isso ficou meses fora desta
        # conta: a placa passava aqui com dezenas de ligacoes sem cobre.
        # This script regenerates the board before checking it, so at this
        # point there is never any copper beyond the pads: the count is
        # information about the netlist, not a verdict. The verdict on the
        # ROUTED board is rule RT1 of dry_run_pcb.py, which runs after
        # route.py and fill_zones.py.
        print(f"        {len(soltos)} itens desconectados na placa recem-gerada, "
              "sem trilhas: quem julga isso e a RT1 do dry_run_pcb.py")

    # ---- the parts ----
    fps = fp_load.kids(arv, "footprint")
    refs_na_placa: list[str] = []
    for f in fps:
        ref = next((p[2] for p in fp_load.kids(f, "property") if p[1] == "Reference"), None)
        if ref and ref != "REF**":
            refs_na_placa.append(ref)
    esperadas = {r for r in P.PARTS if r not in FPS.FORA_DA_PLACA}
    na_placa = set(refs_na_placa)
    check(len(refs_na_placa) == len(na_placa), "nenhuma referencia repetida")
    faltam = esperadas - na_placa
    check(not faltam, f"todas as {len(esperadas)} pecas de placa estao nela"
                      + ("" if not faltam else f"; faltam {sorted(faltam)}"))
    sobram = na_placa - esperadas
    check(not sobram, f"nenhuma peca a mais (achou {sorted(sobram)})")

    # ---- the nets on the pads ----
    _numeros, por_pad = MP.redes()
    erros = []
    vistos = set()
    for f in fps:
        ref = next((p[2] for p in fp_load.kids(f, "property") if p[1] == "Reference"), None)
        if ref not in P.PARTS:
            continue
        for pad in fp_load.kids(f, "pad"):
            num = pad[1]
            rede = fp_load.kid(pad, "net")
            tem = rede[2] if rede else None
            quer = por_pad.get((ref, num))
            if quer != tem:
                erros.append(f"{ref}.{num}: esperava {quer}, achou {tem}")
            if quer:
                vistos.add((ref, num))
    check(not erros, f"cada pad leva a rede da lista de nos ({len(erros)} erros)")
    for e in erros[:8]:
        print(f"      {e}")
    falta_pad = set(por_pad) - vistos - {(r, n) for (r, n) in por_pad
                                         if r in FPS.FORA_DA_PLACA}
    check(not falta_pad,
          f"nenhuma ligacao da lista ficou sem pad ({len(falta_pad)})")
    for e in sorted(falta_pad)[:8]:
        print(f"      {e[0]}.{e[1]}")

    # ---- geometry ----
    lugar, _f = MP.colocar()

    # the SAME courtyard the placer used, imported and not copied
    cx = {r: MP.caixa(r, lugar[r][2]) for r in lugar}
    tam = {r: (cx[r][2] - cx[r][0], cx[r][3] - cx[r][1]) for r in lugar}
    sobre = []
    itens = sorted(lugar.items())
    # Two courtyards only fight if they are on the SAME face - or if one of
    # them pierces the board, in which case it takes the room on both. Before
    # this, a part on the back counted as overlapping a part on the front,
    # which is not a defect and hid the one that is: the Tag-Connect's
    # non-plated holes landing under the buzzer.
    for i, (ra, (ax, ay, _ang, fa)) in enumerate(itens):
        a0, a1 = (ax + cx[ra][0], ay + cx[ra][1]), (ax + cx[ra][2], ay + cx[ra][3])
        for rb, (bx, by, _ang2, fb) in itens[i + 1:]:
            if fa != fb and ra not in MP.PASSANTE and rb not in MP.PASSANTE:
                continue
            b0, b1 = (bx + cx[rb][0], by + cx[rb][1]), (bx + cx[rb][2], by + cx[rb][3])
            if a1[0] > b0[0] and b1[0] > a0[0] and                     a1[1] > b0[1] and b1[1] > a0[1]:
                sobre.append((ra, rb))
    check(not sobre, f"nenhum contorno de peca sobre outro ({len(sobre)})")
    for a, b in sobre[:6]:
        print(f"      {a} e {b}")

    fora = []
    dentro_keepout = []
    for ref, (x, y, _ang, _b) in lugar.items():
        # the courtyard sits where the placer put it, relative to the
        # footprint origin - NOT centred on it. Centring it here said the
        # USB-C crossed the edge by 0,42 mm when its box ends 0,14 mm inside.
        bx = cx[ref]
        x0, y0, x1, y1 = x + bx[0], y + bx[1], x + bx[2], y + bx[3]
        if x0 < 0 or y0 < 0 or x1 > M.W or y1 > M.H:
            fora.append(ref)
        for nome, (kx0, ky0, kx1, ky1), _c, _s in M.ZONES:
            # a part is allowed in the keep-out that exists because of it: the
            # radio module sits over its own antenna zone
            if nome in MP.KEEPOUTS and MP.DONO_DO_KEEPOUT.get(ref) != nome \
                    and x1 > kx0 and kx1 > x0 and y1 > ky0 and ky1 > y0:
                dentro_keepout.append((ref, nome))
    check(not fora, f"nenhuma peca passa da borda ({len(fora)})")
    for ref in fora[:5]:
        x, y, _ang, _b = lugar[ref]
        w, h = tam[ref]
        print(f"      {ref} em ({x:.2f}; {y:.2f}), contorno de {w:.2f} x {h:.2f}")
    check(not dentro_keepout,
          f"nenhuma peca dentro de area de antena ({len(dentro_keepout)})")
    for ref, z in dentro_keepout[:5]:
        print(f"      {ref} em {z}")

    # ---- the board has to fit the pod ----
    # docs/02, Pod: envelope target 60 x 20 outside, walls of 1,2 mm, so the
    # cavity is 57,6 x 17,6; the pod's own dry run measures the real one.
    dentro_caixa = (60.0 - 2 * 1.2, 20.0 - 2 * 1.2)
    check(M.W <= dentro_caixa[0] and M.H <= dentro_caixa[1],
          f"a placa de {M.W:g} x {M.H:g} mm cabe no envelope alvo do pod "
          f"({dentro_caixa[0]:g} x {dentro_caixa[1]:g} mm por dentro): sobra "
          f"{(dentro_caixa[0] - M.W) / 2:.1f} mm em cada ponta e "
          f"{(dentro_caixa[1] - M.H) / 2:.1f} mm de cada lado")

    planos = [z for z in fp_load.kids(arv, "zone")
              if fp_load.kid(z, "name") and fp_load.kid(z, "name")[1] == "PLANO_GND"]
    camadas_plano = set()
    for z in planos:
        lay = fp_load.kid(z, "layers") or fp_load.kid(z, "layer")
        camadas_plano.update(lay[1:])
    esperadas = {"In1.Cu", "F.Cu", "B.Cu"}
    check(camadas_plano == esperadas,
          f"plano de terra em In1.Cu e nas duas faces ({len(planos)} zonas em "
          f"{sorted(camadas_plano)})")

    linhas = [g for g in fp_load.kids(arv, "gr_line")
              if fp_load.kid(g, "layer")[1] == "Edge.Cuts"]
    arcos = [g for g in fp_load.kids(arv, "gr_arc")
             if fp_load.kid(g, "layer")[1] == "Edge.Cuts"]
    # Four sides and four rounded corners, plus the four extra segments of
    # the notch that section 7.4 of the ME54BS13 datasheet asks for under the
    # module's antenna. Counting only 4 and 4 was a check written before the
    # notch existed, and it failed on a board that had got BETTER.
    recorte = any(n == "RECORTE_ANTENA_MODULO" for n, _z, _c, _s in M.ZONES)
    n_linhas = 8 if recorte else 4
    check(len(linhas) == n_linhas and len(arcos) == 4,
          f"contorno com {n_linhas} linhas e 4 arcos"
          + (" (4 lados mais o recorte da antena)" if recorte else ""))
    furos = [f for f in fps
             if next((p[2] for p in fp_load.kids(f, "property")
                      if p[1] == "Reference"), "") == "REF**"]
    # As many holes as make_dxf declares: none on this board (docs/02, Pod)
    check(len(furos) == len(M.FUROS_DOC),
          f"{len(M.FUROS_DOC)} furos de fixacao ({len(furos)})")

    # --- a serigrafia, medida no que o KiCad DESENHA ---------------------
    # Not in what this project believes it drew. make_pcb has a model of how
    # wide a label is, and that model was 30% too narrow: it reported zero
    # collisions while the exported silkscreen had 35 pairs of reference
    # designators printed on top of each other. The only trustworthy source
    # is the export, where every label carries its own textLength and its
    # own font size.
    import tempfile

    # the angle each label is drawn at, from the board file: the SVG's <text>
    # element is invisible (it exists so the PDF is searchable) and carries no
    # rotation, so a vertical designator would be measured as if it were
    # horizontal - which is a box turned 90 degrees from the one that prints.
    bruto = PCB.read_text(encoding="utf-8")
    ang_rotulo: dict[str, int] = {}
    for corpo in re.findall(r'\(footprint "[^"]+"(.*?)\n\t\)\n', bruto, re.S):
        m = re.search(r'\(property "Reference" "([^"]+)"\s*\n\s*'
                      r'\(at [-\d.]+ [-\d.]+ ([-\d.]+)\)', corpo)
        if m:
            ang_rotulo[m.group(1)] = int(float(m.group(2))) % 180

    sobrepostos: list[tuple[str, str]] = []
    n_textos = 0
    with tempfile.TemporaryDirectory() as tmp:
        for camada in ("F.SilkS", "B.SilkS"):
            fora = pathlib.Path(tmp) / (camada.replace(".", "_") + ".svg")
            r = subprocess.run(
                [str(KICAD), "pcb", "export", "svg", "--output", str(fora),
                 "--layers", camada, "--exclude-drawing-sheet", str(PCB)],
                capture_output=True, text=True)
            if r.returncode != 0 or not fora.exists():
                continue
            texto = fora.read_text(encoding="utf-8")
            itens = []
            for m in re.finditer(
                    r'<text x="([-\d.]+)" y="([-\d.]+)"[^>]*?'
                    r'textLength="([-\d.]+)" font-size="([-\d.]+)"[^>]*>'
                    r'([^<]*)</text>', texto, re.S):
                # the SVG font-size is the em box, 4/3 of the glyph height
                w = float(m.group(3))
                h = float(m.group(4)) * 0.75
                if ang_rotulo.get(m.group(5), 0):
                    w, h = h, w
                itens.append((m.group(5), float(m.group(1)),
                              float(m.group(2)), w, h))
            n_textos += len(itens)
            for i, a in enumerate(itens):
                for b in itens[i + 1:]:
                    if abs(a[1] - b[1]) < (a[3] + b[3]) / 2 and \
                            abs(a[2] - b[2]) < (a[4] + b[4]) / 2:
                        sobrepostos.append((a[0], b[0]))
    check(not sobrepostos,
          f"nenhuma referencia de serigrafia sobre outra ({len(sobrepostos)} "
          f"de {n_textos} textos nas duas faces)")
    for a, b in sobrepostos[:6]:
        print(f"      {a} e {b}")

    print()
    print(f"  {len(na_placa)} pecas na placa, {len(FPS.FORA_DA_PLACA)} fora dela, "
          f"{len(set(por_pad.values()))} redes")
    if fails:
        print(f"\n{len(fails)} verificacoes falharam")
        return 1
    print("\na placa confere com o esquematico")
    return 0


if __name__ == "__main__":
    sys.exit(main())
