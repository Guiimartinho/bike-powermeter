#!/usr/bin/env python3
"""As regras do pod que MEDEM O SOLIDO DESENHADO.

Tudo aqui rasteriza as primitivas que a `Malha` registrou ao desenhar
(`medir.py`). E a resposta a causa unica dos sete bloqueantes que a revisao de
2026-10-01 achou: sete das vinte regras do `dry_run_pod.py` liam a CONSTANTE
que deveria ter gerado a geometria em vez de medir a geometria, e uma regra
assim passa com a peca desenhada ou sem ela. Foi assim que um pod com o
ressalto de um parafuso de 3,40 passando por um furo de 2,20, a aba da tampa
5,565 mm3 dentro da bolsa de litio, os fios da celula sem saida nenhuma, o
colar sobre dois resistores e a junta da porta 0,30 enterrada no solido
relatou 18 das 20 regras cumpridas.

A resolucao e `medir.PASSO` (0,1 mm), com amostragem no centro do voxel, e
cada mensagem diz isso. Um encosto fino (a aba contra as nervuras media 0,05
mm) sai com volume de ordem de grandeza, nao exato: o que decide e ele ser
maior que zero.

Chamado por `dry_run_pod.main()`. As regras de PD1 a PD20 ficam lá.
"""
from __future__ import annotations

import math
import pathlib
import re

import numpy as np
from scipy import ndimage

import make_pod as C
import make_dxf as MD
import medir as ME

HERE = pathlib.Path(__file__).resolve().parent

# O unico par de corpos que PODE se interpenetrar e a vedacao que comprime de
# proposito: o O-ring no sulco e a junta plana sob o ressalto da tampa.
PARES_QUE_COMPRIMEM = ({"oring", "tampa"}, {"junta", "tampa"})


def f2(v) -> str:
    return f"{v:.2f}".replace(".", ",")


def corpos_do_pod(pod, g):
    """Cada corpo do conjunto, rasterizado, mais a malha de onde veio."""
    malhas = {
        "concha": pod.concha(),
        "tampa": pod.tampa(),
        "celula": pod.celula_3d(),
        "placa": ME.corpo_da_placa(C, pod.pecas, MD),
        "junta": pod.junta_3d(),
        "oring": pod.anel_oring(),
        "anilhas": pod.anilhas_3d(),
    }
    return malhas, {k: g.solido(m) for k, m in malhas.items()}


def _caixa_da_regiao(g, v) -> str:
    idx = np.argwhere(v)
    lo, hi = idx.min(axis=0), idx.max(axis=0)
    meio = g.passo / 2.0
    return (f"x {g.xs[lo[0]] - meio:.2f}..{g.xs[hi[0]] + meio:.2f}, "
            f"y {g.ys[lo[1]] - meio:.2f}..{g.ys[hi[1]] + meio:.2f}, "
            f"z {g.zs[lo[2]] - meio:.2f}..{g.zs[hi[2]] + meio:.2f}")


def pd21_interferencia(pod, r, g, corpos) -> None:
    """Nenhum par de corpos ocupa o mesmo espaco.

    Esta e a regra que faltava. Dos sete bloqueantes de 2026-10-01, quatro
    eram interferencia solida - o ressalto do parafuso no furo da placa, a aba
    da tampa dentro da bolsa de litio e dentro de tres nervuras do berco, o
    colar do rasgo sobre o R302 e o C304 - e nenhuma das vinte regras media
    volume de material dentro de material: a `PD12` varria so as pecas da
    placa, a `PD4` calculava o ar por constante e a `PD14` desligava o teste
    de interferencia justamente quando o parafuso atravessava a placa.
    """
    pares = []
    nomes = list(corpos)
    for i in range(len(nomes)):
        for j in range(i + 1, len(nomes)):
            a, b = nomes[i], nomes[j]
            if {a, b} in PARES_QUE_COMPRIMEM:
                continue
            inter = corpos[a] & corpos[b]
            v = g.volume(inter)
            if v > ME.MIN_VOL:
                pares.append(f"{a} x {b}: {v:.3f} mm3 em {_caixa_da_regiao(g, inter)}")
    if pares:
        r.falha("PD21", f"{len(pares)} par(es) de corpos ocupam o mesmo espaco: "
                        + "; ".join(pares))
    else:
        r.ok("PD21", f"nenhum dos {len(nomes)} corpos do conjunto invade outro "
                     f"(voxel de {ME.PASSO:g} mm); so o O-ring e a junta plana "
                     "comprimem, e por projeto")


def pd22_caminho_do_fio(pod, r, g, corpos) -> None:
    """Os dois fios da celula tem por onde ir da baia ate o J102.

    Medido por conectividade no solido, com o vao erodido pelo RAIO do fio:
    nao basta haver uma fresta, tem de passar um fio de `CELULA_FIO_D`. Ate
    2026-10-01 as tres nervuras do berco iam do piso ao teto, a saida real era
    0,000 mm - o flood fill parava em x = 17,25 com o J102 em x = 24,45 - e
    nem `CELULA_FIO_D` nem `CELULA_FIO_PASSO` eram lidos por regra nenhuma.
    """
    j2 = pod.pecas.get("J102")
    if not j2 or not j2["pads"]:
        r.falha("PD22", "nao mede nada: o J102 (conector da celula) nao esta na placa")
        return
    livre = ~(corpos["concha"] | corpos["celula"] | corpos["placa"])
    # so dentro da cavidade: fora dela "livre" e o mundo
    dentro = g.planta_rect(C.PAREDE, C.PAREDE, C.W_P - C.PAREDE, C.H_P - C.PAREDE)
    k0, k1 = g.faixa_k(C.BAIA_PISO, C.TAMPA_Z0)
    caixa = np.zeros(g.n, dtype=bool)
    caixa[:, :, k0:k1] = dentro[:, :, None]
    livre &= caixa
    raio = max(1, int(round((C.CELULA_FIO_D / 2.0) / g.passo)))
    ii, jj, kk = np.ogrid[-raio:raio + 1, -raio:raio + 1, -raio:raio + 1]
    bola = (ii * ii + jj * jj + kk * kk) <= raio * raio
    passa = ndimage.binary_erosion(livre, structure=bola)
    rot, _n = ndimage.label(passa)

    def rotulos(x0, y0, z0, x1, y1, z1) -> set:
        a0, a1 = g.faixa_k(z0, z1)
        if a1 <= a0:
            return set()
        m = g.planta_rect(x0, y0, x1, y1)
        bloco = rot[:, :, a0:a1]
        return set(int(v) for v in np.unique(bloco[m]) if v)

    # A semente do lado da celula e a BOCA DA PASSAGEM, rente a face de onde os
    # fios saem - nao o interior da baia. Dentro da baia o espaco livre e a
    # folga de 0,25 em volta da bolsa, por onde fio nenhum passa, e o terminal
    # da celula fica na face dela: medir dentro da baia reprovava um caminho que
    # existe (visto na primeira execucao desta regra, 2026-10-01).
    na_baia = rotulos(pod.passagem[0], pod.fio_y - 1.0, C.BAIA_PISO,
                      pod.passagem[0] + 1.5, pod.fio_y + 1.0, C.CELULA_Z1)
    xs = [C.PLACA_X0 + q["x"] for q in j2["pads"]]
    ys = [C.PLACA_Y0 + q["y"] for q in j2["pads"]]
    no_j102 = rotulos(min(xs) - 0.6, min(ys) - 0.6, C.PLACA_Z1,
                      max(xs) + 0.6, max(ys) + 0.6, C.TAMPA_Z0)
    if not na_baia:
        r.falha("PD22", f"nao passa fio de {f2(C.CELULA_FIO_D)} nem dentro da "
                        "baia da celula")
    elif not no_j102:
        r.falha("PD22", f"nao passa fio de {f2(C.CELULA_FIO_D)} sobre os pinos do J102")
    elif not (na_baia & no_j102):
        r.falha("PD22", f"os dois fios da celula nao tem caminho continuo da baia "
                        f"ate o J102: um fio de {f2(C.CELULA_FIO_D)} nao passa (a "
                        f"passagem desenhada tem {f2(C.CELULA_FIO_VAO)} de largura "
                        f"em x {f2(pod.passagem[0])}..{f2(pod.passagem[2])})")
    else:
        r.ok("PD22", f"um fio de {f2(C.CELULA_FIO_D)} passa da baia ate o J102 pela "
                     f"passagem de {f2(C.CELULA_FIO_VAO)} cortada nas nervuras "
                     f"(conectividade no solido erodido pelo raio do fio; "
                     f"{g.volume(passa):.0f} mm3 de vao passavel)")


def pd23_face_de_baixo(pod, r, g, corpos) -> None:
    """A face de baixo toca o braco SO na base de colagem, e o relevo existe.

    Medido ponto a ponto no solido. Ate 2026-10-01 o relevo eram duas caixas
    ACRESCENTADAS onde queriam cavar: 100 % de cada tira externa (222,60 mm2)
    era face macica em z = 0,000, o pod colava pelos 21,0 mm sobre uma face
    plana de 15,0 apoiando 3,0 mm por lado na concordancia, e uma das caixas
    tapava 15 % do rasgo com espessura inteira. A `PD17` lia `if RELEVO < 0.5`
    e imprimia "fora dela o fundo sobe e livra a concordancia".
    """
    f = g.fundo(corpos["concha"])
    tem = ~np.isnan(f)
    base = g.planta_rect(*pod.base_cola())
    toca = (f < g.passo) & tem
    a_fora = float((toca & ~base).sum()) * g.area
    a_dentro = float((toca & base).sum()) * g.area
    problemas = []
    if a_fora > 1.0:
        problemas.append(f"{a_fora:.1f} mm2 de face em z = 0 FORA da base de "
                         "colagem: o pod apoia na concordancia do braco")
    if a_dentro < 100.0:
        problemas.append(f"so {a_dentro:.1f} mm2 de area colada")
    menor = float(np.nanmin(np.where(tem & ~base, f, np.nan)))
    if menor < C.RELEVO - g.passo:
        problemas.append(f"fora da base a face de baixo chega a z = {menor:.2f} e "
                         f"o relevo e {f2(C.RELEVO)}")
    vazios = [("rasgo", pod.rasgo), ("bolso do extensometro", pod.bolso_gauge())]
    vazios += [(f"canaleta {i + 1}", q) for i, q in enumerate(pod.canaleta_fios())]
    k0, k1 = g.faixa_k(0.0, C.RELEVO)
    for nome, rect in vazios:
        if rect is None:
            continue
        m = g.planta_rect(*rect)
        v = float((corpos["concha"][:, :, k0:k1] & m[:, :, None]).sum()) * g.vox
        if v > ME.MIN_VOL:
            problemas.append(f"{v:.2f} mm3 de material dentro do {nome} abaixo de "
                             f"z = {f2(C.RELEVO)}")
    if problemas:
        r.falha("PD23", "; ".join(problemas))
    else:
        r.ok("PD23", f"a face de baixo toca o braco em {a_dentro:.0f} mm2, toda "
                     f"dentro da base de colagem de {f2(C.BASE_COLA)}; fora dela a "
                     f"face esta em z >= {menor:.2f} ({f2(C.RELEVO)} de relevo) e o "
                     f"rasgo, o bolso do extensometro e as {len(vazios) - 2} "
                     f"canaletas ficam vazados (voxel de {ME.PASSO:g} mm)")


def pd24_vedacao_da_janela(pod, r, g, corpos) -> None:
    """A junta da porta aperta a face do conector, medida no solido.

    `docs/02-hardware.md:21` pede, literalmente, "IPX7: pod envasado, junta na
    face do conector". Ate 2026-10-01 a junta era desenhada em z 6,70 a 7,20
    sobre uma chapa macica de 6,00 a 7,00 - o rebaixo de 0,30 nao existia na
    peca, o `pod-tampa.stl` nao tinha plano nenhum em 6,70 - e, em planta, a
    borda interna dela era a propria janela, 0,55 mm por FORA do corpo do
    conector nos quatro lados: ela nunca tocava a peca. A `PD19` e a `PD20`
    aprovavam lendo `JUNTA_REBAIXO > 0` e imprimiam "comprimida 0,3".
    """
    j = pod.pecas.get("J101")
    if not j:
        r.falha("PD24", "nao mede nada: o conector magnetico nao esta na placa")
        return
    problemas = []
    jx0, jy0, jx1, jy1 = pod.junta
    wx0, wy0, wx1, wy1 = pod.janela
    cx0, cy0, cx1, cy1 = C.no_pod(j["caixa"])
    if not (jx0 >= cx0 - 1e-9 and jy0 >= cy0 - 1e-9
            and jx1 <= cx1 + 1e-9 and jy1 <= cy1 + 1e-9):
        problemas.append("a pegada da junta sai do corpo do conector: ela nao tem "
                         "no que apoiar")
    if pod.junta_larg < C.JUNTA_MIN_L - 1e-9:
        problemas.append(f"o ombro que sobra para a junta tem {f2(pod.junta_larg)} "
                         f"e o minimo e {f2(C.JUNTA_MIN_L)}")
    # o ressalto da tampa EXISTE, medido na face de baixo dela
    anel = (g.planta_rect(jx0, jy0, jx1, jy1)
            & ~g.planta_rect(wx0, wy0, wx1, wy1))
    fundo = g.fundo(corpos["tampa"])
    sob = np.where(anel & ~np.isnan(fundo), fundo, np.nan)
    medido = float("nan")
    aperto = pc = float("nan")
    if not np.isfinite(sob).any():
        problemas.append("nao ha tampa nenhuma sobre a pegada da junta")
    else:
        medido = float(np.nanmax(sob))
        if medido > C.TAMPA_Z0 - g.passo:
            problemas.append(f"a tampa nao tem ressalto sobre a junta: a face de "
                             f"baixo dela esta em {medido:.2f}, no proprio teto da "
                             f"cavidade ({f2(C.TAMPA_Z0)})")
        aperto = (pod.ombro_z + C.JUNTA_ESP) - medido
        pc = 100.0 * aperto / C.JUNTA_ESP
        if not (20.0 - 1e-9 <= pc <= 35.0 + 1e-9):
            problemas.append(f"a junta e comprimida {pc:.1f} % ({aperto:.2f} de "
                             f"{f2(C.JUNTA_ESP)}), fora da faixa de 20 a 35 %")
    if pod.poco > C.POCO_MAX + 1e-9:
        problemas.append(f"a face do conector fica {f2(pod.poco)} abaixo do topo da "
                         f"tampa e o limite e {f2(C.POCO_MAX)}: o pino do cabo nao "
                         "alcanca")
    if problemas:
        r.falha("PD24", "; ".join(problemas))
    else:
        r.ok("PD24", f"a junta plana de {f2(pod.junta_larg)} de largura apoia no "
                     f"ombro do conector em z = {f2(pod.ombro_z)}, o ressalto "
                     f"medido na face de baixo da tampa ({medido:.2f}) a comprime "
                     f"{aperto:.2f} = {pc:.1f} %, e a face do conector fica "
                     f"{f2(pod.poco)} abaixo do topo (limite {f2(C.POCO_MAX)}, o "
                     "curso do pino do cabo)")


def pd25_fio_da_ponte(pod, r, g, corpos) -> None:
    """Nem o fio do extensometro nem a matriz correm dentro da linha de cola.

    Ate 2026-10-01 os cinco fios corriam de 40,7 a 45,98 mm pela face do braco,
    dos quais 44,83 mm sob fundo COLADO, desenhados com 0,32 de altura numa
    linha de cola de 0,50 - 64 % dela -, o rasgo ficava inteiro dentro da area
    colada e o dry run nunca importava o `make_conjunto`. Aqui ele importa: a
    altura livre sob o pod e medida no solido, coluna por coluna, sobre os fios
    que o conjunto desenha.
    """
    import make_conjunto as MC
    base = C.Malha()
    centros = MC.extensometros(base)
    ilhas = MC.ilhas_da_ponte(pod.pecas)
    mf = C.Malha()
    MC.fios(mf, pod, centros, ilhas, C.PLACA_Z0)
    fundo = g.fundo(corpos["concha"])
    tem = ~np.isnan(fundo)
    # uma regra que nao acha o que medir tem de falhar dizendo isso
    if not mf.solidos or not base.solidos or not pod.canaleta_fios():
        r.falha("PD25", f"nao mede nada: {len(mf.solidos)} trecho(s) de fio, "
                        f"{len(base.solidos)} corpo(s) de extensometro e "
                        f"{len(pod.canaleta_fios())} canaleta(s) desenhados")
        return
    faltas = []
    for nome, malha, alto in (("os cinco fios da ponte", mf, C.FIO_PONTE_D),
                              ("a matriz do extensometro", base, C.GAUGE_ALT)):
        topo = MC.FACE_Z + alto
        area = 0.0
        for tipo, par in malha.solidos:
            if tipo == "caixa":
                x0, y0, _z0, x1, y1, z1 = par
                if z1 > 1e-9:          # o que sobe pelo rasgo nao e problema
                    continue
                m = g.planta_rect(x0, y0, x1, y1)
            elif tipo == "prisma":
                pts, _z0, z1 = par
                if z1 > 1e-9:
                    continue
                m = g.planta_poli(pts)
            else:
                continue
            area += float((m & tem & (fundo < topo + C.COLA_MIN - 1e-9)).sum()) * g.area
        if area > 0.5:
            faltas.append(f"{nome}: {area:.1f} mm2 com menos de {f2(C.COLA_MIN)} "
                          "de cola livre por cima")
    if faltas:
        r.falha("PD25", "; ".join(faltas))
    else:
        r.ok("PD25", f"os {C.FIO_PONTE_N} fios de {f2(C.FIO_PONTE_D)} e a matriz de "
                     f"{f2(C.GAUGE_ALT)} correm sob o bolso e as canaletas, com ao "
                     f"menos {f2(C.COLA_MIN)} de cola livre acima (medido no "
                     f"solido, voxel de {ME.PASSO:g} mm)")


def pd26_malha_fechada(pod, r) -> None:
    """Cada primitiva do STL e um solido FECHADO, sem aresta de borda.

    A revisao de 2026-10-01 contou 366 arestas com mais de duas faces nos dois
    STL e 0 de borda: nao ha buraco, ha superposicao de faces vizinhas, e 56
    das 94 da concha ficam no fundo do sulco do O-ring. O STL do pod e a UNIAO
    de solidos fechados, que e o que o fatiador resolve por regra de
    preenchimento; o que nao pode e uma primitiva ABERTA, e nenhuma regra
    conferia isso - o dry run nunca abria arquivo STL nenhum.
    """
    problemas = []
    totais = []
    for nome, malha, arq in (("concha", pod.concha(), "pod-concha.stl"),
                             ("tampa", pod.tampa(), "pod-tampa.stl")):
        abertas = 0
        for i0, n in malha.faixas:
            conta: dict = {}
            for tri in malha.tris[i0:i0 + n]:
                for k in range(3):
                    a = tuple(np.round(tri[k], 4))
                    b = tuple(np.round(tri[(k + 1) % 3], 4))
                    chave = (a, b) if a <= b else (b, a)
                    conta[chave] = conta.get(chave, 0) + 1
            if any(v != 2 for v in conta.values()):
                abertas += 1
        caminho = HERE / arq
        if not caminho.is_file():
            problemas.append(f"nao achei {arq}: rode make_pod.py")
            continue
        m = ME.arestas_do_stl(caminho)
        if m["borda"]:
            problemas.append(f"{nome}: {m['borda']} arestas de BORDA no {arq} "
                             "(buraco na malha)")
        if abertas:
            problemas.append(f"{nome}: {abertas} de {len(malha.faixas)} primitivas "
                             "nao fecham")
        totais.append(f"{nome} {m['triangulos']} triangulos em "
                      f"{len(malha.faixas)} solidos fechados, {m['demais']} arestas "
                      "compartilhadas entre solidos vizinhos")
    if problemas:
        r.falha("PD26", "; ".join(problemas))
    else:
        r.ok("PD26", "sem aresta de borda nos dois STL e toda primitiva fecha: "
                     + "; ".join(totais))


def pd27_constantes_mortas(pod, r) -> None:
    """Nenhuma constante declarada como geometria fica sem uso.

    Meta-regra. A revisao de 2026-10-01 achou oito constantes mortas, e cada
    uma era uma mentira publicada: `DRENO_P` aparecia na mensagem de sucesso da
    `PD20` sem existir no desenho, `PARAF_CABECA_D` so na propria definicao,
    `PARAF_PESCOCO_D` e `PARAF_FURO_PLACA` justificavam a reserva do furo da
    placa sem nunca serem desenhados, `CELULA_FIO_D` e `CELULA_FIO_PASSO` davam
    nome a um canal que nao existia, `JUNTA_REBAIXO` nunca foi cortado.
    """
    fontes = {}
    for nome in ("make_pod.py", "make_conjunto.py", "dry_run_pod.py",
                 "regras_medidas.py", "medir.py"):
        q = HERE / nome
        if q.is_file():
            fontes[nome] = q.read_text(encoding="utf-8")
    nomes = []
    for linha in fontes.get("make_pod.py", "").splitlines():
        mm = re.match(r"^([A-Z][A-Z0-9_]*(?:\s*,\s*[A-Z][A-Z0-9_]*)*)\s*=\s*[^=]",
                      linha)
        if not mm:
            continue
        for n in [q.strip() for q in mm.group(1).split(",")]:
            if n.startswith("COR_"):
                continue
            v = getattr(C, n, None)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                nomes.append(n)
    # Conta TOKENS de codigo, nao ocorrencias no texto: o `PARAF_CABECA_D`
    # passou esta regra na primeira execucao porque o nome dele aparece no
    # comentario logo acima, citado como exemplo de constante morta. Uma
    # meta-regra que a propria documentacao engana nao mede nada.
    import io
    import tokenize
    usos: dict = {}
    for fonte in fontes.values():
        try:
            for tok in tokenize.generate_tokens(io.StringIO(fonte).readline):
                if tok.type == tokenize.NAME:
                    usos[tok.string] = usos.get(tok.string, 0) + 1
        except tokenize.TokenError:
            pass
    mortas = []
    for n in sorted(set(nomes)):
        if usos.get(n, 0) <= 1:
            mortas.append(f"{n} = {getattr(C, n)}")
    if mortas:
        r.falha("PD27", f"{len(mortas)} constante(s) de geometria sem uso nenhum: "
                        + ", ".join(mortas))
    else:
        r.ok("PD27", f"as {len(set(nomes))} constantes numericas do make_pod sao "
                     "todas usadas por geometria, por regra ou pelo desenho")


def pd28_furo_cego(pod, r, g, corpos) -> None:
    """Todo furo cego da concha tem boca acima do envase e proporcao viavel.

    Cada ressalto de parafuso e um tubo cego. Ate 2026-10-01 o envase nao tinha
    NIVEL nenhum no repositorio ("ate a face de baixo da tampa", em todo
    texto), o que punha o menisco rasante a boca dos dois furos: o M1,6
    autoatarraxante ia atarraxar em resina curada, e o furo era o unico ponto
    do pod onde a agua fica parada sem evaporar.
    """
    problemas = []
    medidas = []
    # A boca de cada furo vem MEDIDA do solido: a altura maxima da concha nas
    # colunas em volta do parafuso. Ler `PLACA_Z1`/`TAMPA_Z0` daria o mesmo
    # numero com o colar do pescoco desenhado ou sem ele - o vicio que esta
    # revisao condenou.
    topo_concha = g.topo(corpos["concha"])
    for i, ((cx, cy), na_placa) in enumerate(zip(C.PARAF_XY, C.PARAF_NA_PLACA)):
        volta = (g.planta_rect(cx - C.PARAF_BOSS_D, cy - C.PARAF_BOSS_D,
                               cx + C.PARAF_BOSS_D, cy + C.PARAF_BOSS_D)
                 & ~np.isnan(topo_concha))
        if not volta.any():
            problemas.append(f"nao ha concha nenhuma em volta do parafuso {i + 1}")
            continue
        topo = float(np.nanmax(np.where(volta, topo_concha, np.nan)))
        prof = topo - C.FUNDO
        razao = prof / C.PARAF_FURO_D
        if topo < C.ENVASE_NIVEL - 1e-9:
            problemas.append(f"a boca do furo {i + 1} esta em {f2(topo)}, abaixo do "
                             f"nivel do envase ({f2(C.ENVASE_NIVEL)}): a rosca fica "
                             "em resina")
        if razao > 5.0:
            problemas.append(f"o furo {i + 1} tem {f2(prof)} de fundo para "
                             f"{f2(C.PARAF_FURO_D)} de diametro ({razao:.1f}:1)")
        medidas.append(f"{f2(C.PARAF_FURO_D)} x {f2(prof)} ({razao:.1f}:1), boca em "
                       f"{f2(topo)}")
    if problemas:
        r.falha("PD28", "; ".join(problemas))
    else:
        r.ok("PD28", f"os {len(C.PARAF_XY)} furos cegos: " + "; ".join(medidas)
                     + f"; o envase para em {f2(C.ENVASE_NIVEL)}, "
                     f"{f2(C.ENVASE_FOLGA)} abaixo do teto")


def pd29_aberturas_da_tampa(pod, r) -> None:
    """As aberturas da tampa nao se comem entre si nem comem a junta.

    A revisao de 2026-10-01: o furo do parafuso direito deixava 0,500 mm de
    junta contra um minimo de 1,0 e invadia duas barras do labio em 0,30 x
    1,80 e 0,30 x 0,80, e as barras eram acrescentadas DEPOIS do
    `placa_com_furos`, sem subtrair furo nenhum: o solido tapava 0,30 mm da
    boca por onde o parafuso desce.
    """
    furos = [(f"parafuso {i + 1}", cx, cy, C.PARAF_D / 2.0 + 0.15)
             for i, (cx, cy) in enumerate(C.PARAF_XY)]
    if pod.led:
        furos.append(("luz do LED", pod.led[0], pod.led[1], C.LED_FURO / 2.0))
    problemas = []
    medidas = []
    jx0, jy0, jx1, jy1 = pod.junta
    for nome, cx, cy, raio in furos:
        d = max(jx0 - (cx + raio), (cx - raio) - jx1,
                jy0 - (cy + raio), (cy - raio) - jy1)
        medidas.append(f"{nome} a {f2(d)} da junta da porta")
        if d < C.TAMPA_MIN_PAREDE - 1e-9:
            problemas.append(f"o furo do {nome} fica a {f2(d)} da pegada da junta "
                             f"da porta, e o minimo e {f2(C.TAMPA_MIN_PAREDE)}")
    for i in range(len(furos)):
        for j in range(i + 1, len(furos)):
            n1, x1, y1, r1 = furos[i]
            n2, x2, y2, r2 = furos[j]
            d = math.hypot(x1 - x2, y1 - y2) - r1 - r2
            if d < C.TAMPA_MIN_PAREDE - 1e-9:
                problemas.append(f"{n1} e {n2} ficam a {f2(d)} um do outro")
    if problemas:
        r.falha("PD29", "; ".join(problemas))
    else:
        r.ok("PD29", f"as {len(furos)} aberturas da tampa guardam "
                     f"{f2(C.TAMPA_MIN_PAREDE)} entre si e da junta da porta: "
                     + "; ".join(medidas))


def pd31_cabeca_do_parafuso(pod, r, g, corpos) -> None:
    """A cabeca do parafuso e a vedacao dela cabem onde estao.

    A revisao de 2026-10-01: `PARAF_CABECA_D = 3,20` tinha UMA unica ocorrencia
    em todo o repositorio, a propria definicao. Se a cabeca fosse desenhada
    onde estava declarada - escareada na tampa - ela entraria 0,15 x 1,65 na
    janela do conector, e a pilha escareado mais tampao daria 1,60 contra os
    1,00 de tampa. A cabeca passou a ser CILINDRICA e SALIENTE, sobre uma
    anilha vedante, e esta regra mede o que isso ocupa.
    """
    problemas = []
    # a anilha tem de ser maior que a cabeca, e as duas cabem na face da tampa
    if C.PARAF_ANILHA_D <= C.PARAF_CABECA_D:
        problemas.append(f"a anilha de {f2(C.PARAF_ANILHA_D)} nao e maior que a "
                         f"cabeca de {f2(C.PARAF_CABECA_D)}: ela nao veda")
    aperto = 100.0 * C.PARAF_ANILHA_APERTO / C.PARAF_ANILHA_ESP
    if not (20.0 - 1e-9 <= aperto <= 35.0 + 1e-9):
        problemas.append(f"a anilha e comprimida {aperto:.1f} %, fora da faixa de "
                         "20 a 35 %")
    # e nada da tampa fica sob a anilha alem da propria face
    topo = g.topo(corpos["tampa"])
    for i, (cx, cy) in enumerate(C.PARAF_XY):
        m = (g.planta_rect(cx - C.PARAF_ANILHA_D / 2, cy - C.PARAF_ANILHA_D / 2,
                           cx + C.PARAF_ANILHA_D / 2, cy + C.PARAF_ANILHA_D / 2)
             & ~np.isnan(topo))
        if not m.any():
            problemas.append(f"nao ha tampa sob a anilha do parafuso {i + 1}")
            continue
        alto = float(np.nanmax(np.where(m, topo, np.nan)))
        baixo = float(np.nanmin(np.where(m, topo, np.nan)))
        if alto - baixo > 2 * g.passo:
            problemas.append(f"a face da tampa sob a anilha do parafuso {i + 1} "
                             f"varia de {baixo:.2f} a {alto:.2f}: a anilha nao "
                             "assenta plana")
    # a saliencia entra na altura do pod
    alturas = C.T_P + C.PARAF_ANILHA_ESP - C.PARAF_ANILHA_APERTO + C.PARAF_CABECA_K
    if alturas > C.ALVO[2] + 1e-9:
        problemas.append(f"com a cabeca e a anilha o pod chega a {f2(alturas)} e o "
                         f"alvo de altura e {C.ALVO[2]:g}")
    if problemas:
        r.falha("PD31", "; ".join(problemas))
    else:
        r.ok("PD31", f"cabeca cilindrica de {f2(C.PARAF_CABECA_D)} x "
                     f"{f2(C.PARAF_CABECA_K)} sobre anilha vedante de "
                     f"{f2(C.PARAF_ANILHA_D)} comprimida {aperto:.1f} %, numa face "
                     f"plana medida no solido; o pod chega a {f2(alturas)} nos dois "
                     f"parafusos, contra o alvo de {C.ALVO[2]:g}")


def pd30_assento_da_placa(pod, r) -> None:
    """A placa assenta numa borda mais larga que a folga do pino.

    `RESSALTO - FOLGA_PLACA` dava 0,100 mm em cada borda, e a folga radial do
    pino do parafuso era 0,100 tambem: a translacao que o pino permite
    consumia o assento inteiro de um lado, e a rotacao livre em torno do pino
    unico (0,94 graus) levava o canto inferior esquerdo a andar 0,500 mm e sair
    do ressalto. A `PD8` reservava o ressalto inteiro como apoio, 6 vezes o que
    existia.
    """
    assento = C.RESSALTO - C.FOLGA_PLACA
    folga_pino = (C.PARAF_FURO_PLACA - C.PARAF_PESCOCO_D) / 2.0
    problemas = []
    if assento < C.ASSENTO_MIN - 1e-9:
        problemas.append(f"o assento tem {f2(assento)} por borda (RESSALTO "
                         f"{f2(C.RESSALTO)} menos FOLGA_PLACA {f2(C.FOLGA_PLACA)}) "
                         f"e o minimo e {f2(C.ASSENTO_MIN)}")
    if assento <= folga_pino + 1e-9:
        problemas.append(f"o assento ({f2(assento)}) nao e maior que a folga radial "
                         f"do pino ({f2(folga_pino)}): a placa sai do ressalto so "
                         "deslizando")
    if problemas:
        r.falha("PD30", "; ".join(problemas))
    else:
        r.ok("PD30", f"assento de {f2(assento)} por borda contra folga de pino de "
                     f"{f2(folga_pino)}, com {len(pod.pilares)} pilares e os dedos "
                     "da tampa prendendo a placa")


def todas(pod, r) -> None:
    """As dez regras de medida do solido, na ordem."""
    g = ME.grade_do_pod(C)
    _malhas, corpos = corpos_do_pod(pod, g)
    pd21_interferencia(pod, r, g, corpos)
    pd22_caminho_do_fio(pod, r, g, corpos)
    pd23_face_de_baixo(pod, r, g, corpos)
    pd24_vedacao_da_janela(pod, r, g, corpos)
    pd25_fio_da_ponte(pod, r, g, corpos)
    pd26_malha_fechada(pod, r)
    pd27_constantes_mortas(pod, r)
    pd28_furo_cego(pod, r, g, corpos)
    pd29_aberturas_da_tampa(pod, r)
    pd30_assento_da_placa(pod, r)
    pd31_cabeca_do_parafuso(pod, r, g, corpos)
