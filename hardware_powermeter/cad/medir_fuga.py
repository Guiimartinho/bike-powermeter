#!/usr/bin/env python3
"""Ha lugar para uma VIA DE FUGA ao lado de cada pad das redes em aberto?

Por que isto existe. Em 2026-10-01 e 02 a placa passou a rotear com 0 erros de
DRC e duas a tres redes SEMPRE em aberto, e o `fechar_ultimas.py` falhava nas
tres com a mesma frase: "nao cabe via". Tres colocacoes diferentes e trinta
passadas de roteador - com esforco 100 e com 500 - deram o mesmo resultado, o
que diz que o problema nao e busca.

A hipotese que isto mede: uma rede so muda de camada por uma VIA, e uma via so
cabe onde ha espaco. Se o pad de uma ponta nao tem onde pôr via, aquela ponta
fica presa na camada em que esta, e nenhum esforco de roteador resolve - foi
exatamente o gargalo da rodada anterior do projeto (fuga de pad na `F.Cu`, e
nao area de placa).

Para cada pad das redes pedidas, varre um anel em volta dele, de 0,5 a 3,0 mm,
e pergunta ao `route.via_cabe_aqui` - o mesmo juiz que o `fechar_ultimas` usa -
se uma via daquela rede cabe ali. O cobre vem do arquivo, como ele esta.

    python hardware_powermeter/cad/medir_fuga.py [REDE ...]
"""
from __future__ import annotations

import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import dry_run_pcb as DR      # noqa: E402
import fp_load                # noqa: E402
import reparar as RP          # noqa: E402
import route as R             # noqa: E402

PLACA = HERE / "pmeter.kicad_pcb"
RAIO_MAX = 3.0
PASSO = 0.1


def main() -> int:
    alvo = set(sys.argv[1:]) or {"CHG_N", "VBAT", "GAUGE_ALRT"}
    pecas, _pads, _seg, _vias, _c = DR.ler(PLACA)
    texto = PLACA.read_text(encoding="utf-8")
    arv = fp_load.parse(texto)
    todos, _por_rede, _caixa = R.pads_da_placa(arv)
    segmentos, vias = RP.cobre_da_placa(texto)
    print(f"placa com {len(segmentos)} trilhas e {len(vias)} vias; "
          f"redes olhadas: {', '.join(sorted(alvo))}\n")

    sem_fuga = 0
    for ref, p in sorted(pecas.items()):
        for q in p["pads"]:
            if q.get("rede") not in alvo:
                continue
            cx, cy = q["x"], q["y"]
            achou = None
            raio = 0.5
            while raio <= RAIO_MAX + 1e-9 and achou is None:
                n = max(12, int(2 * math.pi * raio / 0.12))
                for i in range(n):
                    a = 2 * math.pi * i / n
                    vx, vy = cx + raio * math.cos(a), cy + raio * math.sin(a)
                    if R.via_cabe_aqui(vx, vy, q["rede"], segmentos, vias, todos):
                        achou = (raio, vx, vy)
                        break
                raio += PASSO
            if achou:
                onde = (f"via cabe a {achou[0]:.2f} mm, "
                        f"em ({achou[1]:.2f}; {achou[2]:.2f})")
            else:
                onde = f"SEM LUGAR DE VIA ate {RAIO_MAX:.1f} mm"
                sem_fuga += 1
            print(f"  {ref:7s} {q['rede']:11s} ({cx:6.2f}; {cy:6.2f}) "
                  f"{q['camada']:6s}  {onde}")
    print(f"\n{sem_fuga} pad(s) sem lugar de via. Um pad assim nao muda de "
          "camada, e a rede dele nao fecha por geometria, nao por busca.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
