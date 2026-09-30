#!/usr/bin/env python3
"""A via de fuga de cada pino dos CIs apertados, na placa ainda vazia.

    python hardware_powermeter/cad/fanout.py

Roda ENTRE o `make_pcb.py` e o `autoroute.py`.

Por que existe. Tres estrategias de busca diferentes do Freerouting - a
padrao, a global e a aleatoria - deixaram exatamente as MESMAS nove ligacoes
sem rotear, e quase todas tocam o `U101`, o nPM1100. Numero igual com busca
diferente nao e problema de busca: e geometria. Um QFN24 de 4 x 4 mm tem
vinte e quatro pinos no perimetro, todos tem de sair radialmente, e quando o
roteador chega ali a vizinhanca ja esta tomada pelo que ele desenhou antes.

Com a placa vazia todas as vias cabem. Depois delas, o pino deixa de ser um
ponto de 0,25 mm entre dois vizinhos e passa a ser uma via que alcanca as
tres camadas - que e como se rotea um encapsulamento de passo fino desde
sempre, e nao e invencao deste projeto.

Isto so' foi possivel depois de descobrir que o DSN PODE levar cobre. Duas
tentativas anteriores de por cobre antes falharam com um `.ses` de zero byte,
e a conclusao na epoca foi "o DSN nao pode ter cobre" - estava errada. O que
quebrava era a interface grafica do Freerouting estourando ao desenhar o
despejo; sem interface e sem despejo, ele le a placa com cobre e grava a
sessao normalmente (medido em 2026-09-30, 112 KB de sessao numa segunda
passada sobre a placa ja roteada).
"""
from __future__ import annotations

import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fp_load                                             # noqa: E402
import route as R                                          # noqa: E402

PLACA = HERE / "pmeter.kicad_pcb"

# De quem se faz o fanout. Nao e "todo CI de passo fino": e quem o roteador
# nao consegue atender, medido, e ate agora e um so'. Por em volta de todos
# gasta espaco onde ninguem estava reclamando.
APERTADOS = {"U101"}
# Ate onde a via pode ficar do pino, em mm. Passou disto, nao e mais fuga -
# e trilha, e quem desenha trilha e o Freerouting.
#
# 3,0 e nao 1,4: a via nao precisa sair do PINO, precisa sair do COURTYARD.
# O do nPM1100 tem 4,5 mm de lado com o centro em (8,3), entao um pino da
# coluna esquerda, em x = 7,0, so tem cobre livre a partir de x = 6,05 - quase
# um milimetro. Com 1,4 o laco descartava todas as direcoes antes de tentar, e
# saiu "0 de 22 pinos" numa placa vazia (2026-09-30).
LONGE = 3.0


def main() -> int:
    orx0, ory0 = R.MP.ORIGEM
    texto = PLACA.read_text(encoding="utf-8")
    arv = fp_load.parse(texto)
    numeros = fp_load.redes_da_placa(arv)
    todos, por_rede, _caixa = R.pads_da_placa(arv)

    if "(segment" in texto or "\n\t(via" in texto:
        print("a placa ja tem cobre: rode o make_pcb.py antes", flush=True)
        return 1

    # os pads dos apertados, com a rede de cada um. Quem sabe de que PECA e
    # cada pad e o leitor do dry run, que ja le a placa peca por peca; o
    # `pads_da_placa` do roteador devolve so' a geometria e a rede.
    import dry_run_pcb as D
    import pathlib as _pl
    _pecas, _pads, _s, _v, _c = D.ler(_pl.Path(PLACA))
    camadas = {"F.Cu": 0, "In2.Cu": 1, "B.Cu": R.I_BCU}
    alvo = []
    for q in _pads:
        if q["ref"] not in APERTADOS or not q["rede"]:
            continue
        if q["rede"] in R.NAO_ROTEAR:
            continue
        idx = camadas.get(q["camada"])
        if idx is None:
            continue
        alvo.append((q["rede"], idx,
                     q["x"] + orx0, q["y"] + ory0, q["hw"], q["hh"]))
    if not alvo:
        print(f"nenhum pad de {sorted(APERTADOS)} encontrado", flush=True)
        return 1

    g = R.base(arv, todos)
    segmentos: list = []
    vias: list = []
    postas, sem = 0, []
    orx, ory = R.MP.ORIGEM
    dirs = ((0, 1), (0, -1), (1, 0), (-1, 0),
            (0.7071, 0.7071), (0.7071, -0.7071),
            (-0.7071, 0.7071), (-0.7071, -0.7071))
    # ESCALONADO em duas fileiras, e nao um anel so'. Uma via de 0,40 com
    # folga de 0,10 quer 0,50 mm entre centros, e o passo do QFN e' 0,50
    # exatos: um anel unico cabe sem margem nenhuma, e o passe guloso enchia
    # a fileira de dentro e travava o resto (4 de 22 pinos, medido). Pinos
    # alternados comecam a procurar mais longe, que e como se faz fanout de
    # passo fino desde sempre.
    for k, (rede, idx, x, y, hw, hh) in enumerate(alvo):
        bx, by = x - orx, y - ory
        larg = max(R.LARGURA, min(R.largura(rede), 2 * hw, 2 * hh))
        posto = None
        degraus = (0.0, 0.1, 0.2, 0.35, 0.5, 0.7, 0.9, 1.2, 1.6, 2.0)
        if k % 2:
            degraus = degraus[3:] + degraus[:3]
        for extra in degraus:
            for dx, dy in dirs:
                meia = math.hypot(hw * dx, hh * dy)
                d = meia + R.VIA_D / 2 + R.FOLGA + extra
                if d > LONGE:
                    continue
                vx, vy = bx + dx * d, by + dy * d
                c0, c1 = g.cel(vx, vy)
                if not g.dentro(c0, c1) or not g.cabe_via(c0, c1, rede):
                    continue
                vx, vy = g.pos(c0, c1)
                if not g.corredor_livre(idx, (bx, by), (vx, vy), rede):
                    continue
                if R.toco_limpo((bx, by), (vx, vy), idx, rede, larg,
                                segmentos, todos, vias, estrito=True):
                    continue
                if not R.via_cabe_aqui(vx, vy, rede, segmentos, vias, todos):
                    continue
                posto = (vx, vy)
                break
            if posto:
                break
        if posto is None:
            sem.append(f"{rede} em ({bx:.1f}; {by:.1f})")
            continue
        vias.append((posto[0], posto[1], rede))
        segmentos.append(((bx, by), posto, idx, rede, larg))
        g.trilha(idx, (bx, by), posto, larg, rede)
        g.via(posto[0], posto[1], rede)
        postas += 1

    print(f"{postas} de {len(alvo)} pinos de {sorted(APERTADOS)} com via de "
          f"fuga propria", flush=True)
    for s in sem[:6]:
        print("  sem lugar: " + s, flush=True)
    if postas:
        R.escrever(PLACA, texto, numeros, segmentos, vias)
        print(f"{PLACA.name}: {len(segmentos)} trilhas e {len(vias)} vias",
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
