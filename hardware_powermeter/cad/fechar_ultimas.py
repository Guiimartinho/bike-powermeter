#!/usr/bin/env python3
"""Fecha, uma a uma, as ligacoes que o DRC ainda chama de abertas.

    "D:/KiCAD/bin/kicad-cli.exe" pcb drc --severity-all --format json \
        -o _drc_all.json pmeter.kicad_pcb
    python hardware_powermeter/cad/fechar_ultimas.py

A ultima milha. Depois do `autoroute.py` e das passadas de limpeza sobram
poucas ligacoes, e elas nao sao todas do mesmo tipo: medido em 2026-10-01,
das seis que restaram QUATRO eram um pedaco de cobre em cima e outro embaixo
da mesma rede, sem via entre os dois. Isso nao e roteamento - e uma via.

Entao aqui cada ligacao e tratada sozinha, pelo que ela e:

  pontas em CAMADAS DIFERENTES -> uma via onde as duas alcancam, mais o
                                  toco de cada lado ate ela;
  pontas na MESMA camada       -> um toco reto de uma a outra.

Tudo medido contra o cobre que esta na placa antes de ser desenhado, com as
mesmas funcoes que o resto do projeto usa (`route.via_cabe_aqui` e
`route.toco_limpo`, esta ultima no modo estrito, que tambem olha borda, area
de regra, furo e mascara). O que nao couber fica aberto e o programa diz
qual, com a distancia: uma ligacao que falta e visivel, um curto nao.

Rode o `fill_zones.py` e o DRC depois: eles continuam sendo os juizes.
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fp_load                                             # noqa: E402
import reparar as RP                                       # noqa: E402
import route as R                                          # noqa: E402

PLACA = HERE / "pmeter.kicad_pcb"
RELATORIO = HERE / "_drc_all.json"

# Ate onde procurar lugar para a via, em mm, a partir do ponto medio entre as
# duas pontas. Passou disto, o que falta nao e uma via: e um caminho, e quem
# desenha caminho e o roteador.
# 5,0 e nao 2,0: duas das quatro ligacoes que sobraram tinham as pontas a
# 0,1 mm uma da outra e mesmo assim nao achavam via, porque a vizinhanca
# delas esta cheia - e a via, achada longe, ainda precisa dos dois tocos
# ate as pontas, que sao medidos como todo o resto.
RAIO = 5.0
PASSO_BUSCA = 0.09


def _camada(descricao: str) -> int | None:
    for nome, idx in RP.CAMADA_POR_NOME.items():
        if nome in descricao:
            return idx
    return None


def main() -> int:
    if not RELATORIO.is_file():
        raise SystemExit(f"nao achei {RELATORIO.name}: rode o DRC antes")
    dados = json.loads(RELATORIO.read_text(encoding="utf-8"))
    abertas = dados.get("unconnected_items", [])
    if not abertas:
        print("nada em aberto", flush=True)
        return 0

    texto = PLACA.read_text(encoding="utf-8")
    arv = fp_load.parse(texto)
    numeros = fp_load.redes_da_placa(arv)
    todos, _por_rede, _caixa = R.pads_da_placa(arv)
    segmentos, vias = RP.cobre_da_placa(texto)
    R.AREAS_DO_ARQUIVO = _areas(texto)
    orx, ory = R.MP.ORIGEM
    n_seg0, n_via0 = len(segmentos), len(vias)

    print(f"placa com {n_seg0} trilhas e {n_via0} vias; "
          f"{len(abertas)} ligacao(oes) em aberto", flush=True)

    fechadas, falhou = 0, []
    for v in abertas:
        its = v.get("items", [])
        if len(its) != 2:
            continue
        pontas = []
        for i in its:
            p = i.get("pos", {})
            pontas.append((float(p.get("x", 0.0)) - orx,
                           float(p.get("y", 0.0)) - ory,
                           _camada(i.get("description", ""))))
        (ax, ay, ca), (bx, by, cb) = pontas
        rede = _rede(its[0].get("description", ""))
        if rede is None or ca is None or cb is None:
            falhou.append("ponta sem rede ou sem camada")
            continue
        larg = max(R.LARGURA, R.largura(rede))
        d = math.hypot(bx - ax, by - ay)

        # Uma ponta que e a REGIAO (o despejo) nao e um ponto: o DRC da um
        # ponto qualquer dentro dela, que pode estar a dezenas de milimetros.
        # O que esse caso pede e uma VIA ao lado do pino - ela alcanca o
        # plano interno, e o plano e a regiao. Medido em 2026-10-01 com a
        # ilha 36 do modulo: o toco reto ate o ponto da regiao dava 46 mm.
        regiao = [n for n, i in enumerate(its)
                  if i.get("description", "").startswith(("Regi", "Zona"))]
        if regiao:
            k = 1 - regiao[0]
            px, py, pc = pontas[k]
            posto = _via_perto(px, py, pc, rede, segmentos, vias, todos, larg)
            if posto is None:
                falhou.append(f"{rede}: nao cabe via ao lado de "
                              f"({px:.1f}; {py:.1f}) para alcancar o plano")
                continue
            vias.append((posto[0], posto[1], rede))
            p0 = _borda_do_pad(px, py, posto[0], posto[1], todos)
            if math.hypot(posto[0] - p0[0], posto[1] - p0[1]) > 1e-9:
                segmentos.append((p0, posto, pc, rede, larg))
            fechadas += 1
            print(f"  {rede}: via ao lado de ({px:.1f}; {py:.1f}) ate o plano",
                  flush=True)
            continue

        if ca == cb:
            if R.toco_limpo((ax, ay), (bx, by), ca, rede, larg, segmentos,
                            todos, vias, estrito=True):
                falhou.append(f"{rede}: o toco de {d:.2f} mm na mesma camada "
                              "encostaria em alguem")
                continue
            segmentos.append(((ax, ay), (bx, by), ca, rede, larg))
            fechadas += 1
            print(f"  {rede}: toco de {d:.2f} mm na camada {ca}", flush=True)
            continue

        # camadas diferentes: uma via que as duas pontas alcancem
        posto = None
        raio = 0.0
        while raio <= RAIO and posto is None:
            n_p = 1 if raio < 1e-9 else max(8, int(2 * math.pi * raio / PASSO_BUSCA))
            for k in range(n_p):
                ang = 2.0 * math.pi * k / n_p
                vx = (ax + bx) / 2.0 + raio * math.cos(ang)
                vy = (ay + by) / 2.0 + raio * math.sin(ang)
                if not R.via_cabe_aqui(vx, vy, rede, segmentos, vias, todos):
                    continue
                if R.toco_limpo((ax, ay), (vx, vy), ca, rede, larg, segmentos,
                                todos, vias, estrito=True):
                    continue
                if R.toco_limpo((vx, vy), (bx, by), cb, rede, larg, segmentos,
                                todos, vias, estrito=True):
                    continue
                posto = (vx, vy)
                break
            raio += PASSO_BUSCA
        if posto is None:
            falhou.append(f"{rede}: nao cabe via entre ({ax:.1f}; {ay:.1f}) "
                          f"na camada {ca} e ({bx:.1f}; {by:.1f}) na {cb}")
            continue
        vias.append((posto[0], posto[1], rede))
        segmentos.append(((ax, ay), posto, ca, rede, larg))
        segmentos.append((posto, (bx, by), cb, rede, larg))
        fechadas += 1
        print(f"  {rede}: via em ({posto[0]:.1f}; {posto[1]:.1f}) entre as "
              f"camadas {ca} e {cb}", flush=True)

    print(f"{fechadas} de {len(abertas)} fechadas", flush=True)
    for f in falhou:
        print("  NAO FECHOU  " + f, flush=True)

    if fechadas:
        R.escrever(PLACA, texto, numeros, segmentos, vias)
        print(f"{PLACA.name}: {len(segmentos)} trilhas e {len(vias)} vias "
              f"(+{len(segmentos) - n_seg0} e +{len(vias) - n_via0})",
              flush=True)
        print("  rode fill_zones.py e o DRC: eles continuam sendo os juizes",
              flush=True)
    return 0


def _via_perto(px, py, pc, rede, segmentos, vias, todos, larg):
    """Lugar para uma via junto do pino, medido contra o cobre que ha.

    O toco comeca na BORDA do pad, nao no centro dele. Parece detalhe e nao
    e: as duas ilhas de terra do modulo de radio ficam em x = 45,95 e a
    faixa de proibicao da antena comeca em 45,70, entao o CENTRO delas esta
    dentro da faixa e a metade esquerda esta fora. Partindo do centro, todo
    toco nascia proibido e a ilha 36 ficava aberta; partindo da borda, ele
    nasce fora e a ligacao fecha - que e exatamente como a ilha 23, vizinha
    dela, ja estava ligada (medido em 2026-10-01).
    """
    raio = 0.0
    while raio <= 2.0:
        n_p = 1 if raio < 1e-9 else max(8, int(2 * math.pi * raio / PASSO_BUSCA))
        for k in range(n_p):
            ang = 2.0 * math.pi * k / n_p
            vx, vy = px + raio * math.cos(ang), py + raio * math.sin(ang)
            if not R.via_cabe_aqui(vx, vy, rede, segmentos, vias, todos):
                continue
            p0 = _borda_do_pad(px, py, vx, vy, todos)
            if raio > 1e-9 and R.toco_limpo(p0, (vx, vy), pc, rede,
                                            larg, segmentos, todos, vias,
                                            estrito=True):
                continue
            return (vx, vy)
        raio += PASSO_BUSCA
    return None


def _borda_do_pad(px, py, vx, vy, todos):
    """O ponto do pad em (px, py) mais proximo de (vx, vy)."""
    orx, ory = R.MP.ORIGEM
    for nome, idx, qx, qy, hw, hh in todos:
        if abs(qx - orx - px) < 0.01 and abs(qy - ory - py) < 0.01:
            return (min(max(vx, px - hw), px + hw),
                    min(max(vy, py - hh), py + hh))
    return (px, py)


def _rede(descricao: str) -> str | None:
    import re
    m = re.search(r"\[([^\]]+)\]", descricao)
    return m.group(1) if m else None


def _areas(texto: str) -> list:
    import re
    orx, ory = R.MP.ORIGEM
    saida = []
    for bloco in texto.split("\n\t(zone")[1:]:
        if "(keepout" not in bloco:
            continue
        pts = [(float(a), float(b)) for a, b in
               re.findall(r"\(xy ([-\d.]+) ([-\d.]+)\)", bloco)]
        if pts:
            saida.append((min(q[0] - orx for q in pts),
                          min(q[1] - ory for q in pts),
                          max(q[0] - orx for q in pts),
                          max(q[1] - ory for q in pts)))
    return saida


if __name__ == "__main__":
    sys.exit(main())
