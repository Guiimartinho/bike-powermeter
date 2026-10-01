#!/usr/bin/env python3
"""Medir o SOLIDO que o `make_pod.py` desenhou, nao as constantes dele.

Por que este arquivo existe. Em 2026-10-01 dez revisores mediram o pod e
acharam sete interferencias que o impediam de fechar - o ressalto de um
parafuso passando por um furo menor que ele, a aba da tampa dentro da bolsa
de litio, os fios da celula sem saida, o colar sobre dois resistores, a junta
da janela 0,30 enterrada no solido - e o `dry_run_pod.py` dizia, no mesmo
commit, que 18 das 20 regras estavam cumpridas. A causa era uma so: o
desenho e uma sopa de triangulos, a `Malha` nao sabe subtrair e nao da para
perguntar a ela "este ponto esta dentro?", entao sete regras liam a CONSTANTE
que deveria ter gerado a geometria em vez de medir a geometria. Uma regra
assim passa com a peca desenhada ou sem ela.

Como ele resolve. A `Malha` passou a registrar cada primitiva que desenha
(`Malha.solidos`), na mesma chamada que emite os triangulos - entao o
registro nao pode divergir da malha. Aqui essas primitivas sao rasterizadas
numa grade de voxels e tudo passa a ser medida: interferencia entre corpos,
caminho continuo para um fio, altura da face de baixo ponto a ponto, qual
plano existe dentro da pegada de uma junta.

Resolucao. `PASSO = 0,1 mm`, com amostragem no CENTRO do voxel. Um volume
sai com erro de meio voxel em cada face, o que para uma interferencia fina
(a aba contra as nervuras mede 0,05 mm) significa que o volume relatado vale
como ordem de grandeza e o que decide e ele ser maior que zero. Toda regra
que usa isto diz a resolucao na mensagem.
"""
from __future__ import annotations

import math
import pathlib
import struct

import numpy as np


PASSO = 0.1          # o voxel, em mm
MIN_VOL = 0.002      # mm3: dois voxels; abaixo disto e ruido de amostragem


class Grade:
    """Uma grade de voxels sobre um envelope, com os centros das celulas."""

    def __init__(self, x0, y0, z0, x1, y1, z1, passo: float = PASSO):
        self.passo = float(passo)
        self.o = (float(x0), float(y0), float(z0))
        self.n = tuple(max(1, int(math.ceil((b - a) / self.passo)))
                       for a, b in ((x0, x1), (y0, y1), (z0, z1)))
        self.xs = x0 + (np.arange(self.n[0]) + 0.5) * self.passo
        self.ys = y0 + (np.arange(self.n[1]) + 0.5) * self.passo
        self.zs = z0 + (np.arange(self.n[2]) + 0.5) * self.passo
        self.XX, self.YY = np.meshgrid(self.xs, self.ys, indexing="ij")

    # ------------------------------------------------------------ medidas
    @property
    def vox(self) -> float:
        return self.passo ** 3

    @property
    def area(self) -> float:
        return self.passo ** 2

    def volume(self, v: np.ndarray) -> float:
        return float(v.sum()) * self.vox

    # ------------------------------------------------------------ plantas
    def vazio(self) -> np.ndarray:
        return np.zeros(self.n, dtype=bool)

    def planta_rect(self, x0, y0, x1, y1) -> np.ndarray:
        return ((self.XX >= x0) & (self.XX < x1)
                & (self.YY >= y0) & (self.YY < y1))

    def planta_poli(self, pts) -> np.ndarray:
        """Par ou impar de cruzamentos, vetorizado: funciona para qualquer
        poligono simples, que e o que `extrusao` e `anel` recebem."""
        dentro = np.zeros(self.XX.shape, dtype=bool)
        n = len(pts)
        for k in range(n):
            ax, ay = pts[k][0], pts[k][1]
            bx, by = pts[(k + 1) % n][0], pts[(k + 1) % n][1]
            if ay == by:
                continue
            baixo, alto = min(ay, by), max(ay, by)
            faixa = (self.YY >= baixo) & (self.YY < alto)
            if not faixa.any():
                continue
            t = (self.YY - ay) / (by - ay)
            dentro ^= faixa & (self.XX < ax + t * (bx - ax))
        return dentro

    def faixa_k(self, z0, z1) -> tuple[int, int]:
        """Os indices k cujo CENTRO cai em [z0, z1)."""
        a = (z0 - self.o[2]) / self.passo - 0.5
        b = (z1 - self.o[2]) / self.passo - 0.5
        k0 = max(0, int(math.ceil(a - 1e-9)))
        k1 = min(self.n[2], int(math.ceil(b - 1e-9)))
        return k0, k1

    # ------------------------------------------------------------ solidos
    def solido(self, malha) -> np.ndarray:
        """Os voxels que as primitivas da malha ocupam.

        Le `Malha.solidos`, nao os triangulos: um triangulo nao diz de que
        lado e o cheio. Uma malha sem registro nenhum devolve vazio, e quem
        chama tem de tratar isso como falha - e o caso de uma malha montada
        por `tri()` solto.
        """
        v = self.vazio()
        for tipo, p in getattr(malha, "solidos", []):
            if tipo == "caixa":
                x0, y0, z0, x1, y1, z1 = p
                m2 = self.planta_rect(x0, y0, x1, y1)
            elif tipo == "prisma":
                pts, z0, z1 = p
                m2 = self.planta_poli(pts)
            elif tipo == "anel":
                fora, dentro, z0, z1 = p
                m2 = self.planta_poli(fora) & ~self.planta_poli(dentro)
            else:
                raise ValueError(f"primitiva desconhecida: {tipo}")
            k0, k1 = self.faixa_k(z0, z1)
            if k1 <= k0 or not m2.any():
                continue
            v[:, :, k0:k1] |= m2[:, :, None]
        return v

    # ------------------------------------------------------- superficies
    def topo(self, v: np.ndarray) -> np.ndarray:
        """A altura da face de CIMA do solido em cada coluna, NaN onde nao
        ha solido nenhum."""
        tem = v.any(axis=2)
        k = self.n[2] - 1 - np.argmax(v[:, :, ::-1], axis=2)
        z = np.where(tem, self.zs[np.clip(k, 0, self.n[2] - 1)] + self.passo / 2.0,
                     np.nan)
        return z

    def fundo(self, v: np.ndarray) -> np.ndarray:
        """A altura da face de BAIXO do solido em cada coluna, NaN onde nao
        ha solido nenhum."""
        tem = v.any(axis=2)
        k = np.argmax(v, axis=2)
        return np.where(tem, self.zs[k] - self.passo / 2.0, np.nan)


def grade_do_pod(C, folga: float = 0.4, passo: float = PASSO) -> Grade:
    """A grade que cobre o pod inteiro, com folga para o labio e a junta."""
    return Grade(-folga, -folga, -folga,
                 C.W_P + folga, C.H_P + folga, C.T_P + 0.4 + folga, passo)


def corpo_da_placa(C, pecas, MD) -> "C.Malha":
    """A placa e os corpos das pecas, como corpo rigido.

    Vem das caixas e das alturas que o leitor do KiCad devolve - os
    courtyards e as alturas reais -, nao de um envelope escrito aqui.

    Os furos dos parafusos sao VAZADOS: o pescoco do parafuso passa por eles
    de proposito, e sem o furo a medida de interferencia acusa 1,33 mm3 de
    pescoco dentro da placa (medido 2026-10-01, no primeiro uso). O furo e
    quadrado, do diametro do furo redondo, entao os cantos vazam 0,36 mm a
    mais no raio: quem mede o pescoco contra o furo com precisao e a `PD14`,
    por raio, nao esta regra.
    """
    m = C.Malha()
    furos = [(C.PLACA_X0 + fx - C.PARAF_FURO_PLACA / 2.0,
              C.PLACA_Y0 + fy - C.PARAF_FURO_PLACA / 2.0,
              C.PLACA_X0 + fx + C.PARAF_FURO_PLACA / 2.0,
              C.PLACA_Y0 + fy + C.PARAF_FURO_PLACA / 2.0)
             for fx, fy in MD.FUROS_DOC]
    m.placa_com_furos(C.PLACA_X0, C.PLACA_Y0,
                      C.PLACA_X0 + C.PLACA_W, C.PLACA_Y0 + C.PLACA_H,
                      C.PLACA_Z0, C.PLACA_Z1, furos, (0.1, 0.4, 0.2))
    for ref, p in pecas.items():
        x0, y0, x1, y1 = C.no_pod(p["caixa"])
        alt = p["altura"]
        if alt <= 0.0 or x1 - x0 <= 0.0 or y1 - y0 <= 0.0:
            continue
        if p["atras"]:
            m.caixa(x0, y0, C.PLACA_Z0 - alt, x1, y1, C.PLACA_Z0, (0.3, 0.3, 0.3))
        elif ref == "J101":
            # O conector magnetico tem DOIS degraus, e a vedacao da porta
            # depende do de baixo: o barrilete atravessa a tampa e o OMBRO
            # plano em volta dele e a face que a junta aperta. Modelado como
            # uma caixa unica, o ressalto da tampa media 13,97 mm3 dentro
            # dele e a junta 9,98 - interferencia da modelagem, nao do pod.
            # As duas cotas do ombro sao requisito de compra (`PD24`).
            m.caixa(x0, y0, C.PLACA_Z1, x1, y1,
                    C.PLACA_Z1 + C.CONECTOR_OMBRO_Z, (0.3, 0.3, 0.3))
            b = (x0 + C.CONECTOR_OMBRO_L, y0 + C.CONECTOR_OMBRO_L,
                 x1 - C.CONECTOR_OMBRO_L, y1 - C.CONECTOR_OMBRO_L)
            if b[2] > b[0] and b[3] > b[1]:
                m.caixa(b[0], b[1], C.PLACA_Z1 + C.CONECTOR_OMBRO_Z, b[2], b[3],
                        C.PLACA_Z1 + alt, (0.3, 0.3, 0.3))
        else:
            m.caixa(x0, y0, C.PLACA_Z1, x1, y1, C.PLACA_Z1 + alt, (0.3, 0.3, 0.3))
    return m


# ------------------------------------------------------------------- STL
def arestas_do_stl(caminho: pathlib.Path) -> dict:
    """Quantas faces cada aresta do STL tem.

    Um solido fechado tem toda aresta com exatamente duas. Aresta com uma
    (ou zero) e buraco; com quatro ou mais e superposicao - duas faces no
    mesmo lugar -, que o fatiador resolve como quiser e e justamente o que
    nao se quer num plano de vedacao.
    """
    dados = caminho.read_bytes()
    n = struct.unpack("<I", dados[80:84])[0]
    passo = 50
    conta: dict = {}
    for i in range(n):
        base = 84 + i * passo
        vs = struct.unpack("<9f", dados[base + 12:base + 48])
        p = [tuple(round(c, 4) for c in vs[k * 3:k * 3 + 3]) for k in range(3)]
        for k in range(3):
            a, b = p[k], p[(k + 1) % 3]
            chave = (a, b) if a <= b else (b, a)
            conta[chave] = conta.get(chave, 0) + 1
    por_contagem: dict = {}
    for v in conta.values():
        por_contagem[v] = por_contagem.get(v, 0) + 1
    return {"triangulos": n, "arestas": len(conta), "por_contagem": por_contagem,
            "borda": sum(c for v, c in por_contagem.items() if v < 2),
            "demais": sum(c for v, c in por_contagem.items() if v > 2)}
