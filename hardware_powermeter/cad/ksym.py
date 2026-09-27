#!/usr/bin/env python3
"""Le um simbolo da biblioteca oficial do KiCad e o entrega pronto para uso.

Por que isto existe
-------------------

Ate 2026-09-25 este projeto desenhava TODO simbolo por conta propria. Os de
dois terminais ficaram bons - resistor em ziguezague, capacitor, diodo, LED -
mas os circuitos integrados, os conectores e o display viravam retangulos com
pinos em volta, e um retangulo nao diz nada. Quem le um esquematico reconhece
um receptaculo USB-C pelo desenho dele, nao por um bloco escrito "J101".

A biblioteca do KiCad tem 21.110 simbolos, revisados contra a KLC (a norma de
qualidade da propria biblioteca), e entre eles estao alguns EXATAMENTE das
pecas deste projeto: `Battery_Management:ADP5091` e `RF_GPS:MAX-M10S` sao os
nossos, pino por pino, e `Connector:USB_C_Receptacle_USB2.0_16P` e o
receptaculo de 16 contatos com a lingueta desenhada.

Desenhar de novo o que ja existe revisado e trabalho perdido e risco de erro.

Como funciona
-------------

Um `.kicad_sym` e uma lista de `(symbol "Nome" ...)`, e cada um traz dentro
as suas unidades, `Nome_0_1` para o desenho comum e `Nome_1_1` para a
primeira unidade. Este modulo recorta esse bloco, troca o nome pelo que este
projeto usa, e devolve junto:

  - a posicao de cada pino, ja no sistema do simbolo. No formato do KiCad o
    `(at x y ang)` de um pino e a ponta ELETRICA dele, e o `ang` aponta do
    fio para o corpo - a mesma convencao que `sch_lib.pin_local()` usa, entao
    nao ha conversao nenhuma;
  - a caixa do desenho, medida nos retangulos, polilinhas, circulos e arcos.

O que este modulo NAO faz: nao inventa simbolo, nao adapta pinagem. Se a
peca do KiCad tiver pino que a nossa nao tem, ou vice-versa, quem chama tem
de resolver - e `checar()` existe para isso falhar cedo, no lugar de sair um
esquematico com fio ligado no pino errado.
"""
from __future__ import annotations

import pathlib
import re

BIBLIOTECA = pathlib.Path(r"D:\KiCAD\share\kicad\symbols")

_cache: dict[str, str] = {}


def _arquivo(lib: str) -> str:
    if lib not in _cache:
        p = BIBLIOTECA / f"{lib}.kicad_sym"
        if not p.exists():
            raise FileNotFoundError(f"biblioteca {lib} nao existe em {BIBLIOTECA}")
        _cache[lib] = p.read_text(encoding="utf-8")
    return _cache[lib]


def _recorta(texto: str, i: int) -> str:
    """Do '(' em i ate o ')' que o fecha."""
    d = 0
    for j in range(i, len(texto)):
        if texto[j] == "(":
            d += 1
        elif texto[j] == ")":
            d -= 1
            if d == 0:
                return texto[i:j + 1]
    raise ValueError("s-expression sem fechamento")


def bloco(ref: str) -> str:
    """`ref` e "Biblioteca:Nome". Devolve o `(symbol ...)` inteiro."""
    lib, nome = ref.split(":", 1)
    t = _arquivo(lib)
    alvo = f'\n\t(symbol "{nome}"\n'
    i = t.find(alvo)
    if i < 0:
        raise KeyError(f"simbolo {ref} nao esta na biblioteca")
    return _recorta(t, i + 1)


_PINO = re.compile(
    r'\(pin\s+(\w+)\s+(\w+)\s*\n\s*\(at\s+([-\d.]+)\s+([-\d.]+)\s+(\d+)\)'
    r'\s*\n\s*\(length\s+([\d.]+)\)')


def pinos(blk: str) -> dict[str, tuple[float, float, int]]:
    """Numero do pino -> (x, y, angulo) da ponta eletrica, no simbolo."""
    out: dict[str, tuple[float, float, int]] = {}
    for m in re.finditer(r'\(pin\s', blk):
        p = _recorta(blk, m.start())
        a = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)\s+(\d+)\)', p)
        n = re.search(r'\(number\s+"([^"]+)"', p)
        if not a or not n:
            continue
        out[n.group(1)] = (float(a.group(1)), float(a.group(2)), int(a.group(3)))
    return out


def caixa(blk: str) -> tuple[float, float, float, float]:
    """x0, y0, x1, y1 do desenho - so das formas, sem os pinos."""
    xs: list[float] = []
    ys: list[float] = []
    for m in re.finditer(r'\((rectangle|polyline|circle|arc)\s', blk):
        f = _recorta(blk, m.start())
        # polilinha e arco usam `(xy x y)`; retangulo usa `(start ...)` e
        # `(end ...)`, e arco usa tambem `(start)`, `(mid)` e `(end)`
        for a, b in re.findall(
                r'\((?:xy|start|mid|end)\s+([-\d.]+)\s+([-\d.]+)\)', f):
            xs.append(float(a))
            ys.append(float(b))
        r = re.search(r'\(radius\s+([\d.]+)\)', f)
        c = re.search(r'\(center\s+([-\d.]+)\s+([-\d.]+)\)', f)
        if r and c:
            cx, cy, rr = float(c.group(1)), float(c.group(2)), float(r.group(1))
            xs += [cx - rr, cx + rr]
            ys += [cy - rr, cy + rr]
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


def renomear(blk: str, de: str, para: str) -> str:
    """Troca o nome do simbolo e o das unidades dele.

    As unidades se chamam `Nome_0_1`, `Nome_1_1` e assim por diante, e o
    KiCad casa a unidade com o pai pelo prefixo do nome - trocar so o pai
    deixa as unidades orfas e o simbolo sai vazio na folha.
    """
    blk = blk.replace(f'(symbol "{de}"', f'(symbol "{para}"', 1)
    return re.sub(r'\(symbol "' + re.escape(de) + r'_(\d+_\d+)"',
                  lambda m: f'(symbol "{para}_{m.group(1)}"', blk)


def sem_propriedades(blk: str) -> str:
    """Tira as propriedades do simbolo da biblioteca.

    Referencia, valor, footprint e ficha sao deste projeto, e quem as escreve
    e o `sch_lib`. Deixar as da biblioteca faz o KiCad mostrar duas de cada,
    uma por cima da outra.
    """
    fora = []
    for m in re.finditer(r'\t\t\(property "', blk):
        i = blk.rindex("(", 0, m.end())
        fora.append((i, i + len(_recorta(blk, i))))
    for i, j in reversed(fora):
        k = j
        while k < len(blk) and blk[k] in "\n\t":
            k += 1
        blk = blk[:i] + blk[k:]
    return blk


def tipos(blk: str) -> dict[str, str]:
    """Numero do pino -> tipo eletrico, como o simbolo o declara."""
    out: dict[str, str] = {}
    for m in re.finditer(r'\(pin\s+(\w+)\s', blk):
        p = _recorta(blk, m.start())
        n = re.search(r'\(number\s+"([^"]+)"', p)
        if n:
            out[n.group(1)] = m.group(1)
    return out


def nomes(blk: str) -> dict[str, str]:
    """Numero do pino -> nome do pino."""
    out: dict[str, str] = {}
    for m in re.finditer(r'\(pin\s', blk):
        p = _recorta(blk, m.start())
        n = re.search(r'\(number\s+"([^"]+)"', p)
        nm = re.search(r'\(name\s+"([^"]+)"', p)
        if n and nm:
            out[n.group(1)] = nm.group(1)
    return out


_PLACEHOLDER = re.compile(r'^(pin_?\d+|in|out|ext|~|\d+|[abk]|nc|k?a)$', re.I)


def _generico(nome: str) -> bool:
    """O nome do pino e enfeite de simbolo de classe, nao funcao de peca.

    `Conn_01x06_Socket` chama os pinos de `Pin_1` a `Pin_6` e `Conn_Coaxial`
    de `In` e `Ext`: sao simbolos de CLASSE, e neles o que liga o desenho a
    peca e o numero. Ja num simbolo de PECA - o ADP5091, o MAX-M10S - o nome
    e a funcao, e uma diferenca ali significa que uma das duas fontes esta
    errada sobre o que o pino faz.
    """
    return bool(_PLACEHOLDER.match(nome.strip()))


def _normal(s: str) -> str:
    """O nome de um pino sem as diferencas que sao so de escrita.

    A barra do KiCad e o sufixo `_N` deste projeto dizem a mesma coisa, e um
    nome com barra - `LSIN1/VINLDO1` - traz duas funcoes do mesmo pino.
    """
    s = s.strip().upper()
    s = s.replace("~{", "").replace("}", "")
    s = s.split("/")[0]
    for suf in ("_N", "_L", "#"):
        if s.endswith(suf):
            s = s[:-len(suf)]
    return s.replace("_", "").replace("-", "")


def checar(ref: str, peca) -> tuple[set[str], set[str], list[tuple[str, str, str]]]:
    """(so no KiCad, so no nosso, [(pino, nosso nome, nome do KiCad)]).

    Conferir so os NUMEROS nao basta, e isso custou caro: o simbolo
    `Battery_Management:ADP5091` tem os mesmos 25 numeros que a nossa peca e
    **seis deles com outro sinal** - duas permutacoes de tres, MPPT/VIN/AGND
    e SETHYST/SETSD/TERM. A conferencia por numero passava, e o esquematico
    sairia com o fio do MPPT no pino do terra.

    Um numero igual com nome diferente e um erro de projeto ou um erro da
    biblioteca, e nos dois casos quem decide e a ficha - nunca este arquivo.
    """
    b = bloco(ref)
    k = set(pinos(b))
    kn = nomes(b)
    nossos = {q.number: q.name for q in peca.pins}
    n = set(nossos)
    dif = []
    for num in sorted(k & n):
        deles = kn.get(num, "")
        if _generico(deles):
            # o simbolo e de classe, nao de peca: o nome do pino e enfeite e
            # o que liga o desenho a peca e o NUMERO
            continue
        a, b2 = _normal(nossos[num]), _normal(deles)
        if a == b2 or a.startswith(b2) or b2.startswith(a):
            continue
        dif.append((num, nossos[num], deles))
    return (k - n, n - k, dif)


def main() -> int:
    """Confere os simbolos que este projeto usa contra as pecas dele."""
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import parts as P  # noqa: E402
    import simbolos as S  # noqa: E402

    ruim = 0
    for our, ksimbolo in sorted(S.KICAD.items()):
        if our not in P.PARTS:
            print(f"  ! {our} nao e peca deste projeto")
            ruim += 1
            continue
        so_k, so_n, dif = checar(ksimbolo, P.PARTS[our])
        aceitos = S.ALIAS.get(our, set())
        dif = [d for d in dif if d[0] not in aceitos]
        if so_k or so_n or dif:
            print(f"  FALHA {our} ({ksimbolo})")
            if so_k:
                print(f"      so no KiCad: {sorted(so_k)}")
            if so_n:
                print(f"      so no nosso: {sorted(so_n)}")
            for num, a, b2 in dif:
                print(f"      pino {num}: nosso diz {a}, o KiCad diz {b2}")
            ruim += 1
        else:
            b = bloco(ksimbolo)
            x0, y0, x1, y1 = caixa(b)
            print(f"  ok    {our:<6} {ksimbolo:<46} "
                  f"{len(pinos(b)):2d} pinos, {x1 - x0:5.2f} x {y1 - y0:5.2f} mm")
    print(f"\n{len(S.KICAD)} simbolos do KiCad, {ruim} com problema")
    return 1 if ruim else 0


if __name__ == "__main__":
    raise SystemExit(main())
