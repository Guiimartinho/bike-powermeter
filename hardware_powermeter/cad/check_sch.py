#!/usr/bin/env python3
"""Check the hierarchical schematic: KiCad reads it, and it says what we meant.

The checks, in order of how much they prove:

  1. every one of the five files is a balanced s-expression, and KiCad's own
     netlist exporter walks the hierarchy and accepts it;
  2. the netlist KiCad extracts is the netlist nets.py declares, pin by pin.
     Two names in nets.py can be one electrical node - a signal that reaches a
     connector and carries on to the part behind it - so nets that share a pin
     are merged before the comparison;
  3. no wire runs across a component body, on any sheet;
  4. every hierarchical label has the sheet pin on the root that answers it,
     and every sheet pin has its label;
  5. no two parts overlap, and no power symbol sits on top of a part.

It regenerates the schematic first, so what it checks is always what the
generator currently produces.

Run: python hardware_powermeter/cad/check_sch.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import make_sch as MK  # noqa: E402
import nets as N  # noqa: E402
import parts as P  # noqa: E402
import sheets as S  # noqa: E402

KICAD = pathlib.Path(r"D:\KiCAD\bin\kicad-cli.exe")
RAIZ = HERE / "pmeter.kicad_sch"
NET = HERE / "pmeter.net"
fails: list[str] = []
# pins found in two nets outside the declared pass-through connectors
CURTOS: list[str] = []


def check(ok: bool, what: str, *detalhes: str) -> None:
    print(("  ok    " if ok else "  FALHA ") + what)
    if not ok:
        for d in detalhes:
            print("      " + d)
        fails.append(what)


def tokens(text: str):
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "()":
            yield c
            i += 1
        elif c == '"':
            j, buf = i + 1, []
            while j < n:
                if text[j] == "\\":
                    buf.append(text[j + 1])
                    j += 2
                    continue
                if text[j] == '"':
                    break
                buf.append(text[j])
                j += 1
            yield ("str", "".join(buf))
            i = j + 1
        elif c.isspace():
            i += 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in '()"':
                j += 1
            yield ("sym", text[i:j])
            i = j


def parse(text: str) -> list:
    stack: list[list] = [[]]
    for t in tokens(text):
        if t == "(":
            stack.append([])
        elif t == ")":
            # in two steps: stack[-1] is evaluated before the pop, so the one
            # liner appends the list to itself and loses the whole tree
            pronto = stack.pop()
            stack[-1].append(pronto)
        else:
            stack[-1].append(t[1])
    if len(stack) != 1:
        raise ValueError(f"parenteses abertos a mais: {len(stack) - 1}")
    return stack[0][0]


def kids(node, name):
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


def kid(node, name):
    got = kids(node, name)
    return got[0] if got else None


def esperado_unificado() -> dict[str, frozenset]:
    bruto: dict[str, set] = {}
    for name, pins in N.NETS.items():
        membros = set()
        for ref, pin_name in pins:
            part = P.PARTS[ref]
            numero = next(q.number for q in part.pins
                          if q.name == pin_name or q.number == pin_name)
            membros.add((ref, numero))
        bruto[name] = membros
    pai = {n: n for n in bruto}

    def raiz(n):
        while pai[n] != n:
            pai[n] = pai[pai[n]]
            n = pai[n]
        return n

    de_pino: dict[tuple, str] = {}
    for name, membros in bruto.items():
        for m in membros:
            if m in de_pino:
                if m[0] not in N.PASSA_DIRETO:
                    CURTOS.append(f"{m[0]}.{m[1]} esta em {de_pino[m]} e em {name}")
                a, b = raiz(de_pino[m]), raiz(name)
                if a != b:
                    pai[b] = a
            else:
                de_pino[m] = name
    juntos: dict[str, set] = {}
    for name, membros in bruto.items():
        juntos.setdefault(raiz(name), set()).update(membros)
    return {k: frozenset(v) for k, v in juntos.items() if len(v) >= 2}


# As unicas violacoes de ERC que este projeto aceita, uma a uma e com o
# motivo. Qualquer outra faz a verificacao falhar.
#
# As quatro sao a mesma coisa: duas SAIDAS de alimentacao ligadas entre si. O
# KiCad chama de erro por padrao porque, em circuito de sinal, duas saidas no
# mesmo no e curto. Num caminho de energia nao e - e o desenho.
# ERC errors accepted one by one, with the reason. None on this board yet:
# an error the ERC finds has to be fixed or written here with its cause.
ERC_ACEITO: set[tuple] = set()


def _erc() -> None:
    """O ERC do KiCad, que este projeto nunca tinha rodado.

    Sao 52 erros que ninguem viu, entre eles um capacitor com os DOIS
    terminais no ar. A verificacao propria daqui compara a nossa lista de
    nos com a que o KiCad extrai - e boa nisso e cega para tudo o mais: pino
    aberto, trilho sem fonte, duas saidas ligadas entre si.
    """
    import json
    import subprocess
    import tempfile

    saida = pathlib.Path(tempfile.gettempdir()) / "pmeter_erc.json"
    r = subprocess.run(
        [str(KICAD), "sch", "erc", "--severity-error", "--format", "json",
         "-o", str(saida), str(RAIZ)],
        capture_output=True, text=True)
    if r.returncode not in (0, 5) or not saida.exists():
        check(False, "o KiCad roda o ERC", r.stderr.strip()[:200])
        return
    check(True, "o KiCad roda o ERC")
    d = json.loads(saida.read_text(encoding="utf-8"))
    sobrou = []
    for folha in d.get("sheets", []):
        for v in folha.get("violations", []):
            if v.get("severity") != "error":
                continue
            chave = tuple([v["type"]] + sorted(
                "%s:%s" % (i.get("description", "").split()[1],
                           i.get("description", "").split("Pino ")[1].split(" ")[0])
                for i in v.get("items", [])
                if i.get("description", "").startswith("Symbol ")
                and "Pino " in i.get("description", "")))
            if chave in ERC_ACEITO:
                continue
            sobrou.append("%s: %s" % (v["type"], "; ".join(
                i.get("description", "")[:60] for i in v.get("items", [])[:2])))
    check(not sobrou, f"o ERC do KiCad nao acusa erro novo ({len(ERC_ACEITO)} "
          "aceitos, um a um, com o motivo)", *sobrou[:8])


def main() -> int:
    print("gerando...")
    MK.main()
    print()

    _erc()

    arquivos = [RAIZ] + [HERE / a for _n, a, _p in S.FOLHAS]
    arvores = {}
    for f in arquivos:
        try:
            arvores[f.name] = parse(f.read_text(encoding="utf-8"))
        except ValueError as exc:
            check(False, f"{f.name}: {exc}")
            return 1
    check(all(t[0] == "kicad_sch" for t in arvores.values()),
          f"os {len(arquivos)} arquivos abrem como s-expression equilibrada")

    r = subprocess.run([str(KICAD), "sch", "export", "netlist",
                        "--output", str(NET), str(RAIZ)], capture_output=True, text=True)
    check(r.returncode == 0,
          "o KiCad percorre a hierarquia e exporta o netlist"
          + ("" if r.returncode == 0 else f": {r.stdout.strip()} {r.stderr.strip()}"))
    if r.returncode != 0:
        return 1

    nl = parse(NET.read_text(encoding="utf-8"))
    achado: dict[frozenset, str] = {}
    soltos: list[str] = []
    for nd in kids(kid(nl, "nets"), "net"):
        nome = kid(nd, "name")[1]
        membros = frozenset((kid(x, "ref")[1], kid(x, "pin")[1]) for x in kids(nd, "node"))
        if nome.startswith("unconnected-"):
            soltos.append(sorted(membros)[0][0] + "." + sorted(membros)[0][1])
        else:
            achado[membros] = nome

    esperado = esperado_unificado()
    check(not CURTOS,
          f"nenhum pino em dois nos fora dos conectores que atravessam sinal "
          f"({len(CURTOS)})")
    for c in CURTOS[:8]:
        print(f"      {c}")
    faltando = {k: v for k, v in esperado.items() if v not in achado}
    sobrando = [v for k, v in achado.items() if k not in esperado.values()]
    check(not faltando,
          f"os {len(esperado)} nos de dois pinos ou mais saem iguais do KiCad"
          + ("" if not faltando else f"; {len(faltando)} diferentes"))
    for nome, quer in list(faltando.items())[:8]:
        parciais = [(nm, k) for k, nm in achado.items() if k & quer]
        if parciais:
            nm, got = parciais[0]
            print(f"      {nome}: faltou {sorted(quer - got)}, sobrou {sorted(got - quer)}")
        else:
            print(f"      {nome}: nenhum no do KiCad toca estes pinos")
    check(not sobrando, f"nenhum no a mais no KiCad (achou {len(sobrando)})")

    esperados_soltos = sum(1 for ref, part in P.PARTS.items() for q in part.pins
                           if not any((ref, q.number) in v for v in esperado.values()))
    check(len(soltos) == esperados_soltos,
          f"{len(soltos)} pinos sem no, e nets.py deixa {esperados_soltos} de proposito")

    # ---- legibility, measured on the exported PDF ----
    # The ERC and every geometric check above pass on a sheet whose text is
    # a smudge. This exports the PDF and measures the words the plotter
    # actually drew (sch_legivel.py explains why the PDF and not the
    # s-expression).
    try:
        import sch_legivel as LEG
        pdf = HERE / "_legivel.pdf"
        LEG.exportar(RAIZ, pdf)
        refs_t = set(P.PARTS)
        vals_t = {w for q in P.PARTS.values() for w in str(q.value).split()}
        leg = LEG.medir(pdf, refs_t, vals_t)
        check(not leg["sobrepostos"],
              f"TX1: nenhum texto por cima de outro no PDF "
              f"({leg['palavras']} palavras em {leg['paginas']} paginas)")
        for pg, a, b, ar in leg["sobrepostos"][:6]:
            print(f"      p{pg}: {a!r} sobre {b!r} ({ar} mm2)")
        check(not leg["no_corpo"],
              f"TX2: nenhuma referencia nem valor dentro do corpo de um simbolo")
        for pg, a in leg["no_corpo"][:6]:
            print(f"      p{pg}: {a!r}")
    except ImportError:
        check(False, "TX1 e TX2: sch_legivel.py nao pode ser importado")

    # ---- per sheet: wires off the parts, and no part on top of another ----
    total_fios = 0
    for nome, arquivo, _p in S.FOLHAS:
        arv = arvores[arquivo]
        segs = []
        for w in kids(arv, "wire"):
            xy = kids(kid(w, "pts"), "xy")
            segs.append(((float(xy[0][1]), float(xy[0][2])),
                         (float(xy[1][1]), float(xy[1][2]))))
        total_fios += len(segs)
        refs = S.por_folha()[nome]
        encostam = []
        for ref in refs:
            x0, y0, x1, y1 = P.PARTS[ref].box()
            for a, b in segs:
                if max(a[0], b[0]) <= x0 or min(a[0], b[0]) >= x1 or \
                        max(a[1], b[1]) <= y0 or min(a[1], b[1]) >= y1:
                    continue
                encostam.append((ref, a, b))
        check(not encostam, f"{nome}: nenhum fio por cima de componente "
                            f"({len(segs)} fios, {len(refs)} pecas)")
        for ref, a, b in encostam[:3]:
            print(f"      {ref}: {a} a {b}")

        # nothing may hang off the page: a part outside the frame is invisible
        # on paper and in the PDF
        # the sheet the generator would choose for these parts. It takes the
        # refs, not a count: the size comes from laying them out, not from a
        # budget per part.
        # the sheet's OWN paper, read from the file: the energy sheet is
        # generated on a forced A2 (make_sch.main), and recomputing the size
        # here chose A3 and reported three labels "outside" that were inside
        papel = kid(arv, "paper")
        w_pag, h_pag = MK.PAPEIS[papel[1]] if papel and papel[1] in MK.PAPEIS             else MK.PAPEIS[MK.escolher_papel(refs, len(kids(arv, "hierarchical_label")))]
        fora = []
        for ref in refs:
            x0, y0, x1, y1 = P.PARTS[ref].box()
            if x0 < 0 or y0 < 0 or x1 > w_pag or y1 > h_pag:
                fora.append(ref)
        for lb in kids(arv, "hierarchical_label"):
            at = kid(lb, "at")
            if not (0 < float(at[1]) < w_pag and 0 < float(at[2]) < h_pag):
                fora.append(lb[1])
        if fora:
            print("      fora da folha: " + ", ".join(
                f"{r} {tuple(round(v, 1) for v in P.PARTS[r].box())}"
                if r in P.PARTS else str(r) for r in fora[:6]))
        check(not fora, f"{nome}: nada fora da folha {papel[1] if papel else '?'} "
                        f"({len(fora)})")

        sobrepostas = []
        for i, ra in enumerate(refs):
            ax0, ay0, ax1, ay1 = P.PARTS[ra].box()
            for rb in refs[i + 1:]:
                bx0, by0, bx1, by1 = P.PARTS[rb].box()
                if ax1 > bx0 and bx1 > ax0 and ay1 > by0 and by1 > ay0:
                    sobrepostas.append((ra, rb))
        check(not sobrespostas_vazias(sobrepostas), f"{nome}: nenhuma peca sobre outra")

    # ---- labels and sheet pins agree ----
    raiz = arvores[RAIZ.name]
    pinos_raiz: dict[str, set[str]] = {}
    for sh in kids(raiz, "sheet"):
        nome_folha = next(p[2] for p in kids(sh, "property") if p[1] == "Sheetname")
        for pn in kids(sh, "pin"):
            pinos_raiz.setdefault(nome_folha, set()).add(pn[1])
    for nome, arquivo, _p in S.FOLHAS:
        rotulos = {lb[1] for lb in kids(arvores[arquivo], "hierarchical_label")}
        check(rotulos == pinos_raiz.get(nome, set()),
              f"{nome}: os {len(rotulos)} rotulos hierarquicos batem com os pinos da folha")
        if rotulos != pinos_raiz.get(nome, set()):
            print(f"      so no rotulo: {sorted(rotulos - pinos_raiz.get(nome, set()))}")
            print(f"      so no pino:   {sorted(pinos_raiz.get(nome, set()) - rotulos)}")

    print()
    print(f"  {len(P.PARTS)} posicoes, {len(N.NETS)} nos, {len(esperado)} nos eletricos, "
          f"{total_fios} fios em {len(S.FOLHAS)} folhas")
    print(f"  pinagem NAO confirmada na ficha em {len(P.UNCONFIRMED)} pecas")
    if fails:
        print(f"\n{len(fails)} verificacoes falharam")
        return 1
    print("\no esquematico confere com a lista de nos")
    return 0


def sobrespostas_vazias(lst):
    if lst:
        for a, b in lst[:3]:
            print(f"      {a} sobre {b}")
    return bool(lst)


if __name__ == "__main__":
    sys.exit(main())
