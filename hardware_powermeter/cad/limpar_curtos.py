#!/usr/bin/env python3
"""Tira da placa a trilha que o DRC do KiCad chama de curto.

    "D:/KiCAD/bin/kicad-cli.exe" pcb drc --severity-all --format json \
        -o _drc_all.json pmeter.kicad_pcb
    python hardware_powermeter/cad/limpar_curtos.py

Para que serve. O Freerouting roda uma segunda vez sobre a placa ja roteada e
fecha ligacoes que a primeira passada nao fechou - medido em 2026-10-01, de
15 em aberto para 6 -, mas ele nao respeita direito o cobre que ja estava la
e deixa alguns curtos pelo caminho. Um curto so aparece depois de fabricado;
uma ligacao faltando o `RT1` conta. Entao a trilha culpada sai.

Quem julga e o DRC do KiCad, nao uma medida nossa: este arquivo le o
`_drc_all.json`, pega os itens que ele chama de `shorting_items` ou
`solder_mask_bridge`, e apaga as TRILHAS que aparecem neles. Ilha e via nao
saem - a ilha e a peca e a via pode ser a unica ligacao entre faces -, e cada
trilha e identificada pelo UUID que o proprio relatorio da, nao por posicao.

Depois disto, encha as zonas e rode o DRC de novo: o que sobrar nao era
trilha.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
PLACA = HERE / "pmeter.kicad_pcb"
RELATORIO = HERE / "_drc_all.json"

# Os tipos de violacao que uma trilha a mais causa, e que apagar a trilha
# resolve. `clearance` fica de fora de proposito: ela e quase sempre dois
# vizinhos legitimos perto demais, e apagar um dos dois e exagero.
TIPOS = ("shorting_items", "tracks_crossing", "solder_mask_bridge")


def main() -> int:
    if not RELATORIO.is_file():
        raise SystemExit(f"nao achei {RELATORIO.name}: rode o DRC antes")
    dados = json.loads(RELATORIO.read_text(encoding="utf-8"))
    culpadas: dict[str, str] = {}
    for v in dados.get("violations", []):
        if v.get("severity") != "error" or v.get("type") not in TIPOS:
            continue
        for it in v.get("items", []):
            d = it.get("description", "")
            if not d.startswith("Trilha"):
                continue                 # ilha e via ficam
            u = it.get("uuid")
            if u:
                culpadas[u] = d
    if not culpadas:
        print("nenhuma trilha culpada de curto", flush=True)
        return 0

    texto = PLACA.read_text(encoding="utf-8")
    saiu = 0
    for u, d in culpadas.items():
        # o bloco `(segment ... (uuid "U"))`, inteiro
        padrao = re.compile(r"\n\t\(segment\n(?:\t\t[^\n]*\n)*?\t\t\(uuid \""
                            + re.escape(u) + r"\"\)\n\t\)")
        texto, n = padrao.subn("", texto)
        if n:
            saiu += n
            print(f"  fora: {d[:58]}", flush=True)
    if saiu:
        PLACA.write_text(texto, encoding="utf-8", newline="\n")
    print(f"{saiu} de {len(culpadas)} trilha(s) culpadas retiradas; "
          "encha as zonas e rode o DRC de novo", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
