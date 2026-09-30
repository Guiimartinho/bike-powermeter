#!/usr/bin/env python3
"""As classes de rede do KiCad, geradas da tabela de correntes.

    python hardware_powermeter/cad/make_netclasses.py

Roda antes do `autoroute.py`: e por estas classes que o Freerouting fica
sabendo a largura de cada trilha, porque o DSN que o KiCad exporta leva uma
`class` Specctra por classe do projeto, com a largura e a folga dela.

Ate 2026-09-30 havia tres classes escritas a mao - Default, Alimentacao e
USB - e elas mentiam nos dois sentidos. Medido:

    rede        IPC pede   o DSN mandava
    3V0            0,090       0,40
    3V0_EXC        0,090       0,40
    3V0_MOD        0,090       0,40
    VBAT           0,105       0,40
    VSYS           0,105       0,40
    VBUS           0,320       0,32   (essa estava certa)
    BUCK_SW        0,204       0,09   (essa ia ESTREITA demais)

Quatro vezes mais largo do que a norma pede gasta canal que faz falta - o
`3V0` foi uma das redes que o Freerouting nao conseguiu fechar -, e o
`BUCK_SW`, que leva os 350 mA do indutor, ia com largura de sinal.

Agora cada rede cai numa classe pela largura que a `route.largura()` calcula
(IPC-2221, 10 C de subida, cobre de 35 um), arredondada para cima num degrau
de 0,01 mm. A folga e uma so', a minima do fabricante, e a via tambem: o que
muda de classe para classe e a largura, que e o que a corrente decide.

A classe USB sai: o nRF54L15 nao tem USB, os dois contatos que levavam D+ e
D- agora levam UART, e nao ha par diferencial nenhum nesta placa - deixar
uma classe de par diferencial sem par foi o que fez o Freerouting desenhar
dez trilhas de 0,0674 mm.
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import nets as N                                           # noqa: E402
import route as R                                          # noqa: E402

PROJETO = HERE / "pmeter.kicad_pro"

# A folga que todas as classes pedem, em mm: o minimo do fabricante para
# quatro camadas. Quem precisa de mais que isto e o FURO da via, e esse
# acrescimo e feito no DSN pelo `autoroute.folga_que_cobre_o_furo()`, porque
# e um problema do roteador e nao do projeto.
FOLGA = 0.0889
VIA_D, VIA_FURO = 0.4, 0.2
# O degrau em que a largura e arredondada para cima. Sem ele sairia uma
# classe por rede, e a lista fica ilegivel sem ganhar nada.
DEGRAU = 0.01


def classes_por_largura() -> tuple[list, list]:
    """(classes, padroes) do `pmeter.kicad_pro`, uma classe por largura."""
    por_larg: dict[float, list[str]] = {}
    for rede in sorted(N.NETS):
        w = math.ceil(R.largura(rede) / DEGRAU) * DEGRAU
        w = max(w, R.LARGURA)
        por_larg.setdefault(round(w, 3), []).append(rede)

    classes, padroes = [], []
    for w in sorted(por_larg):
        nome = "Default" if abs(w - R.LARGURA) < 1e-9 else f"W{w * 1000:.0f}um"
        classes.append({
            "name": nome,
            "clearance": FOLGA,
            "track_width": w,
            "via_diameter": VIA_D,
            "via_drill": VIA_FURO,
            "microvia_diameter": 0.2,
            "microvia_drill": 0.1,
            # Nao ha par diferencial nesta placa. Os numeros ficam iguais aos
            # da trilha para que, se algum dia houver um, ele nao herde uma
            # largura inventada - e para o Freerouting nao ter uma largura
            # menor a que recorrer quando o vao aperta.
            "diff_pair_width": w,
            "diff_pair_gap": round(FOLGA, 4),
            "diff_pair_via_gap": round(FOLGA, 4),
            "wire_width": 6,
            "bus_width": 12,
            "line_style": 0,
            "pcb_color": "rgba(0, 0, 0, 0.000)",
            "schematic_color": "rgba(0, 0, 0, 0.000)",
        })
        if nome == "Default":
            continue                    # o resto cai nela sozinho
        for rede in por_larg[w]:
            padroes.append({"netclass": nome, "pattern": rede})
    return classes, padroes


def main() -> int:
    d = json.loads(PROJETO.read_text(encoding="utf-8"))
    classes, padroes = classes_por_largura()
    d["net_settings"]["classes"] = classes
    d["net_settings"]["netclass_patterns"] = padroes
    PROJETO.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8", newline="\n")
    print(f"{len(classes)} classes de rede, {len(padroes)} redes nomeadas:",
          flush=True)
    for c in classes:
        quantas = sum(1 for p in padroes if p["netclass"] == c["name"])
        quem = "as demais" if c["name"] == "Default" else f"{quantas} rede(s)"
        print(f"  {c['name']:10s} trilha {c['track_width']:.3f} mm   {quem}",
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
