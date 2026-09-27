#!/usr/bin/env python3
"""Render the board's 3D model to PNG, without a 3D program.

kicad-cli exports the board as GLB, geometry and all, but KiCad 8 has no
command that turns it into a picture. So this reads the GLB - the JSON chunk
describes the nodes and the meshes, the binary chunk holds the vertices - and
rasterises the triangles with a z-buffer, in numpy.

Two pictures come out: the board seen from above, which is the placement, and
an angled view, which is what the thing looks like.

Run: python hardware_powermeter/cad/make_3d.py
"""

from __future__ import annotations

import json
import math
import pathlib
import re
import struct
import sys

import numpy as np
from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
# the rendered views live with the documentation's images, not with the
# CAD sources (the repository's reorganisation of 2026-09-26)
IMG = HERE.parents[1] / "docs" / "img" / "hardware"

TIPOS = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2),
         5125: ("I", 4), 5126: ("f", 4)}
N_COMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def ler_glb(caminho: pathlib.Path) -> tuple[dict, bytes]:
    b = caminho.read_bytes()
    magic, _ver, total = struct.unpack("<III", b[:12])
    if magic != 0x46546C67:
        raise ValueError("nao e um GLB")
    off, js, bina = 12, None, b""
    while off < total:
        tam, tipo = struct.unpack("<II", b[off:off + 8])
        dados = b[off + 8:off + 8 + tam]
        if tipo == 0x4E4F534A:
            js = json.loads(dados)
        elif tipo == 0x004E4942:
            bina = dados
        off += 8 + tam
    return js, bina


def acessor(j: dict, bina: bytes, i: int) -> np.ndarray:
    a = j["accessors"][i]
    n = a["count"]
    nc = N_COMP[a["type"]]
    fmt, tam = TIPOS[a["componentType"]]
    bv = j["bufferViews"][a["bufferView"]]
    inicio = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    passo = bv.get("byteStride") or nc * tam
    if passo == nc * tam:
        bruto = np.frombuffer(bina, dtype=np.dtype(fmt), count=n * nc, offset=inicio)
        return bruto.reshape(n, nc).astype(np.float64 if fmt == "f" else np.int64)
    out = np.empty((n, nc), dtype=np.float64 if fmt == "f" else np.int64)
    for k in range(n):
        out[k] = np.frombuffer(bina, dtype=np.dtype(fmt), count=nc,
                               offset=inicio + k * passo)
    return out


def matriz(no: dict) -> np.ndarray:
    if "matrix" in no:
        return np.array(no["matrix"], dtype=np.float64).reshape(4, 4).T
    m = np.eye(4)
    if "scale" in no:
        m = np.diag(list(no["scale"]) + [1.0]) @ m
    if "rotation" in no:
        x, y, z, w = no["rotation"]
        r = np.array([
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0],
            [0, 0, 0, 1]], dtype=np.float64)
        m = r @ m
    if "translation" in no:
        t = np.eye(4)
        t[:3, 3] = no["translation"]
        m = t @ m
    return m


def triangulos(j: dict, bina: bytes) -> tuple[np.ndarray, np.ndarray]:
    """Every triangle in world space, and the colour of each."""
    cores = []
    for mat in j.get("materials", []):
        pbr = mat.get("pbrMetallicRoughness", {})
        cores.append(np.array(pbr.get("baseColorFactor", [0.7, 0.7, 0.7, 1.0])[:3]))
    if not cores:
        cores = [np.array([0.7, 0.7, 0.7])]

    verts: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    cena = j.get("scenes", [{}])[j.get("scene", 0)]

    def andar(i_no: int, pai: np.ndarray) -> None:
        no = j["nodes"][i_no]
        m = pai @ matriz(no)
        if "mesh" in no:
            for prim in j["meshes"][no["mesh"]].get("primitives", []):
                if prim.get("mode", 4) != 4 or "POSITION" not in prim.get("attributes", {}):
                    continue
                pos = acessor(j, bina, prim["attributes"]["POSITION"])
                if "indices" in prim:
                    idx = acessor(j, bina, prim["indices"]).reshape(-1)
                else:
                    idx = np.arange(len(pos))
                n_tri = len(idx) // 3
                if n_tri == 0:
                    continue
                p = np.concatenate([pos, np.ones((len(pos), 1))], axis=1)
                p = (m @ p.T).T[:, :3]
                verts.append(p[idx[:n_tri * 3]].reshape(n_tri, 3, 3))
                c = cores[prim.get("material", 0)] if prim.get("material") is not None \
                    else cores[0]
                cols.append(np.tile(c, (n_tri, 1)))
        for f in no.get("children", []):
            andar(f, m)

    for i_no in cena.get("nodes", []):
        andar(i_no, np.eye(4))
    if not verts:
        raise ValueError("nenhum triangulo")
    t = np.concatenate(verts)
    # glTF is Y up and this renderer is Z up: (x, y, z) -> (x, -z, y).
    t = np.stack([t[..., 0], -t[..., 2], t[..., 1]], axis=-1)
    return t, np.concatenate(cols)


def render(tris: np.ndarray, cols: np.ndarray, largura: int, altura: int,
           azimute: float, elevacao: float, fundo=(250, 250, 252)) -> Image.Image:
    """Orthographic z-buffer, flat shading, one directional light."""
    az, el = math.radians(azimute), math.radians(elevacao)
    olho = np.array([math.cos(el) * math.sin(az), math.cos(el) * math.cos(az),
                     math.sin(el)])
    # straight down the up axis the cross product vanishes, so use another
    cima = np.array([0.0, 0.0, 1.0])
    if abs(abs(elevacao) - 90.0) < 1e-6:
        cima = np.array([0.0, 1.0, 0.0])
    direita = np.cross(cima, olho)
    n = np.linalg.norm(direita)
    if n < 1e-9:
        direita = np.array([1.0, 0.0, 0.0])
        n = 1.0
    direita /= n
    verdadeiro_cima = np.cross(olho, direita)
    R = np.stack([direita, verdadeiro_cima, olho])

    v = tris.reshape(-1, 3) @ R.T
    v = v.reshape(-1, 3, 3)
    mn, mx = v.reshape(-1, 3).min(axis=0), v.reshape(-1, 3).max(axis=0)
    esc = 0.92 * min(largura / (mx[0] - mn[0]), altura / (mx[1] - mn[1]))
    cx, cy = (mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2
    sx = (v[:, :, 0] - cx) * esc + largura / 2
    sy = altura / 2 - (v[:, :, 1] - cy) * esc
    sz = v[:, :, 2]

    normais = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    ln = np.linalg.norm(normais, axis=1)
    ln[ln == 0] = 1.0
    normais /= ln[:, None]
    luz = np.array([0.35, -0.45, 0.82])
    luz /= np.linalg.norm(luz)
    brilho = 0.35 + 0.65 * np.clip(np.abs(normais @ luz), 0, 1)
    rgb = np.clip(cols * brilho[:, None], 0, 1) * 255

    img = np.zeros((altura, largura, 3), dtype=np.float32)
    img[:, :] = fundo
    zbuf = np.full((altura, largura), -1e30, dtype=np.float64)

    ordem = np.argsort(-sz.mean(axis=1))
    for t in ordem:
        x0, x1 = sx[t].min(), sx[t].max()
        y0, y1 = sy[t].min(), sy[t].max()
        if x1 < 0 or y1 < 0 or x0 > largura or y0 > altura:
            continue
        i0, i1 = max(int(math.floor(y0)), 0), min(int(math.ceil(y1)) + 1, altura)
        j0, j1 = max(int(math.floor(x0)), 0), min(int(math.ceil(x1)) + 1, largura)
        if i1 <= i0 or j1 <= j0:
            continue
        ys, xs = np.mgrid[i0:i1, j0:j1]
        px, py = xs + 0.5, ys + 0.5
        ax, ay = sx[t, 0], sy[t, 0]
        bx, by = sx[t, 1], sy[t, 1]
        ccx, ccy = sx[t, 2], sy[t, 2]
        den = (by - ccy) * (ax - ccx) + (ccx - bx) * (ay - ccy)
        if abs(den) < 1e-12:
            continue
        w0 = ((by - ccy) * (px - ccx) + (ccx - bx) * (py - ccy)) / den
        w1 = ((ccy - ay) * (px - ccx) + (ax - ccx) * (py - ccy)) / den
        w2 = 1.0 - w0 - w1
        dentro = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
        if not dentro.any():
            continue
        z = w0 * sz[t, 0] + w1 * sz[t, 1] + w2 * sz[t, 2]
        sub = zbuf[i0:i1, j0:j1]
        melhor = dentro & (z > sub)
        if not melhor.any():
            continue
        sub[melhor] = z[melhor]
        img[i0:i1, j0:j1][melhor] = rgb[t]
    return Image.fromarray(img.astype(np.uint8))


# Where the board's two faces actually are in the GLB, measured and not
# assumed: kicad-cli puts the substrate from z 0 to 0.820 and the 35 um of
# copper on top of it, so the front surface a part stands on is 0.855 and the
# back one is -0.035. Everything here used 0 and -0.8, which sank every front
# part 0.855 mm INTO the board and put the silkscreen inside it, where the
# copper pour hid it: in the 3D view not one reference designator was visible
# anywhere the pour reached, which is almost everywhere.
FRENTE_Z = 0.855
VERSO_Z = -0.035

KICAD_CLI = pathlib.Path(r"D:\KiCAD\bin\kicad-cli.exe")
SILK_TRACO = 0.15          # a largura do traco da serigrafia, em mm
SILK_COR = (0.92, 0.92, 0.89)


def serigrafia() -> tuple[np.ndarray, np.ndarray]:
    """The silkscreen of both faces, as flat geometry on the board.

    kicad-cli's GLB export has no silkscreen option, so a 3D view of this
    board showed a bare green rectangle with parts on it and not one
    reference designator - which is the one thing silkscreen exists for.

    The SVG export does carry it, and carries it as the simplest possible
    thing: 6.484 `<path d="M x y L x y"/>`, one per stroke, glyphs included.
    No font is needed and nothing is approximated. Exported over the FULL
    page, the SVG's millimetres are the board file's own coordinates, so the
    segments drop straight into the same frame the part bodies use.
    """
    import re
    import subprocess
    import tempfile

    if not KICAD_CLI.exists():
        return np.zeros((0, 3, 3)), np.zeros((0, 3))
    tris: list[list] = []
    with tempfile.TemporaryDirectory() as tmp:
        for camada, z in (("F.SilkS", FRENTE_Z + 0.005),
                          ("B.SilkS", VERSO_Z - 0.005)):
            fora = pathlib.Path(tmp) / (camada.replace(".", "_") + ".svg")
            r = subprocess.run(
                [str(KICAD_CLI), "pcb", "export", "svg", "--output", str(fora),
                 "--layers", camada, "--exclude-drawing-sheet",
                 str(HERE / "pmeter.kicad_pcb")],
                capture_output=True, text=True)
            if r.returncode != 0 or not fora.exists():
                continue
            texto = fora.read_text(encoding="utf-8")
            h = SILK_TRACO / 2.0
            for m in re.finditer(r'<path d="M([-\d.]+) ([-\d.]+)\s*'
                                 r'L([-\d.]+) ([-\d.]+)', texto):
                x0, y0, x1, y1 = (float(m.group(i)) for i in (1, 2, 3, 4))
                dx, dy = x1 - x0, y1 - y0
                comp = math.hypot(dx, dy)
                if comp < 1e-9:
                    dx, dy, comp = 1.0, 0.0, 1.0
                # a quad of SILK_TRACO wide along the segment
                nx, ny = -dy / comp * h, dx / comp * h
                a = (x0 + nx, y0 + ny, z)
                b = (x1 + nx, y1 + ny, z)
                c = (x1 - nx, y1 - ny, z)
                d = (x0 - nx, y0 - ny, z)
                tris.append([a, b, c])
                tris.append([a, c, d])
            for m in re.finditer(r'<circle cx="([-\d.]+)" cy="([-\d.]+)" '
                                 r'r="([-\d.]+)"', texto):
                cx, cy, rr = (float(m.group(i)) for i in (1, 2, 3))
                n = 10
                for i in range(n):
                    a1 = 2 * math.pi * i / n
                    a2 = 2 * math.pi * (i + 1) / n
                    tris.append([(cx, cy, z),
                                 (cx + rr * math.cos(a1), cy + rr * math.sin(a1), z),
                                 (cx + rr * math.cos(a2), cy + rr * math.sin(a2), z)])
    if not tris:
        return np.zeros((0, 3, 3)), np.zeros((0, 3))
    t = np.array(tris, dtype=np.float64)
    return t, np.array([SILK_COR] * len(t))


def ler_wrl(caminho: pathlib.Path) -> list[tuple[np.ndarray, tuple]]:
    """The shapes of a VRML body, in millimetres.

    Reads two dialects, and reading the SECOND one is what put the passives
    back on the board:

      - the one footprints.py writes, with each face on its own line as
        `0 1 2 -1` and the faces separated by commas;
      - the one KiCad's own library uses, written by kicad StepUp, with a
        comma between EVERY index: `0,1,2,-1,2,1,3,-1`.

    Splitting on the comma and reading each piece as a face works for the
    first and silently yields nothing for the second - every piece is a
    single index, no triangle comes out, and the part simply does not
    appear. That is why 105 resistors, capacitors and inductors were
    invisible in the 3D while their pads were there: the drawing showed
    bare copper where a component should be, which is exactly what the
    owner saw. The list of indices is now read as one flat sequence and cut
    at each -1, which is what VRML actually specifies.

    Colour: the library files declare materials once with `DEF` and reuse
    them with `USE`, so most Shape blocks carry no diffuseColor of their
    own. The map is built on the way through.

    VRML here is in tenths of an inch, the unit KiCad uses for .wrl, so
    everything is multiplied by 2.54 on the way out.
    """
    texto = caminho.read_text(encoding="utf-8")
    saida: list[tuple[np.ndarray, tuple]] = []
    i = 0
    while True:
        i = texto.find("Shape {", i)
        if i < 0:
            break
        j = texto.find("Shape {", i + 7)
        bloco = texto[i:j if j > 0 else len(texto)]
        i = i + 7

        k = bloco.find("diffuseColor")
        cor = (0.13, 0.13, 0.14)
        if k >= 0:
            partes = bloco[k + 12:k + 60].split()
            try:
                cor = (float(partes[0]), float(partes[1]), float(partes[2]))
            except (IndexError, ValueError):
                pass

        k = bloco.find("point [")
        if k < 0:
            continue
        corpo = bloco[k + 7:bloco.index("]", k)]
        pts = []
        for linha in corpo.split(","):
            n = linha.split()
            if len(n) == 3:
                pts.append([float(n[0]) * 2.54, float(n[1]) * 2.54,
                            float(n[2]) * 2.54])
        k = bloco.find("coordIndex [")
        if k < 0 or not pts:
            continue
        idx = bloco[k + 12:bloco.index("]", k)]
        # uma sequencia unica de indices, cortada a cada -1. Nao se separa
        # por virgula: a biblioteca do KiCad poe virgula entre TODOS os
        # indices, e nao so entre as faces.
        seq = [int(q) for q in re.findall(r"-?\d+", idx)]
        tris = []
        face: list[int] = []
        for q in seq + [-1]:
            if q < 0:
                # um leque: toda face que estes dois escritores emitem e convexa
                for m in range(1, len(face) - 1):
                    if max(face[0], face[m], face[m + 1]) < len(pts):
                        tris.append([pts[face[0]], pts[face[m]],
                                     pts[face[m + 1]]])
                face = []
            else:
                face.append(q)
        if tris:
            saida.append((np.array(tris, dtype=np.float64), cor))
    return saida


# The three things that are NOT on the board and decide its shape anyway.
# Every rectangle and every ceiling here is a line of 04-pcb-e-caixa.md, and
# the column that says which one is part of the table on purpose: a number
# with no line behind it does not belong in a drawing that is supposed to be
# checkable.
#
# The thickness of the display and of the cell are the ones the document
# gives for the part; the GAP under each of them is the shadow ceiling, which
# is the clearance the board has to respect, not the part's own thickness.
MONTAGEM = (
    # nome, x0, y0, x1, y1, vao ate a placa, espessura, atras, cor, fonte
    #
    # The cell under the board, centred on it: a 30 x 20 x 4 LiPo of the
    # 100 to 150 mAh class (docs/02, Pod), wider than the 16 mm board by
    # 2 mm a side. The pod (pod/make_pod.py) is what really places it;
    # this is the stack the exploded view of the board shows.
    ("celula LiPo 30 x 20 x 4", 24.0 - 15.0, 8.0 - 10.0, 24.0 + 15.0, 8.0 + 10.0,
     0.5, 4.00, True, (0.30, 0.31, 0.34),
     "docs/02, Pod: celula sob a placa; pod/make_pod.py e quem a posiciona"),
)


def pecas_da_caixa(afastar: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """The display and the cell, in the board's own coordinates.

    With `afastar` at zero they sit where the case really holds them, which
    is what shows whether a part fouls them. Pulled apart, it is the exploded
    view: the same three things in the same order, far enough apart to see
    the board between them.
    """
    tris: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    for _nome, x0, y0, x1, y1, vao, esp, atras, cor, _fonte in MONTAGEM:
        if atras:
            z1 = VERSO_Z - vao - afastar
            z0 = z1 - esp
        else:
            z0 = FRENTE_Z + vao + afastar
            z1 = z0 + esp
        cantos = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        base = [(px, py, z0) for px, py in cantos]
        topo = [(px, py, z1) for px, py in cantos]
        faces = [(base[0], base[3], base[2]), (base[0], base[2], base[1]),
                 (topo[0], topo[1], topo[2]), (topo[0], topo[2], topo[3])]
        for k in range(4):
            a, b = k, (k + 1) % 4
            faces.append((base[a], base[b], topo[b]))
            faces.append((base[a], topo[b], topo[a]))
        for t in faces:
            tris.append(np.array(t, dtype=np.float64))
            cols.append(np.array(cor))
    if not tris:
        return np.zeros((0, 3, 3)), np.zeros((0, 3))
    return np.array(tris), np.array(cols)


def caixas_das_pecas() -> tuple[np.ndarray, np.ndarray]:
    """Bodies for the parts whose footprint was generated here.

    KiCad's GLB carries only the STEP models of the library footprints, so the
    parts drawn in footprints.py - the radio module, the GNSS receiver, the
    level translator, the sensors, the key, the buzzer, the receptacle -
    would appear as bare pads.

    Each of them already has a body in cad/3d/*.wrl, with the package's real
    shape and the real colour of its material, and until now this function
    ignored both: it drew a plain cuboid of the courtyard size in one hard
    coded near-black for all of them. That is exactly what the board looked
    like - twenty-two identical black bricks - and it is not what any of
    those parts is. The .wrl is read instead, and only a part with no body
    file at all falls back to the box.
    """
    sys.path.insert(0, str(HERE))
    import footprints as FPS
    import fp_load
    import make_pcb as MP

    arv = fp_load.parse((HERE / "pmeter.kicad_pcb").read_text(encoding="utf-8"))
    # CORPO_TODOS is filled while the footprints are read, and this runs in a
    # process of its own: without touching them first it would know only the
    # ten generated footprints and miss the eight library ones that got a box.
    for _ref, (nome_fp, _o, _n) in FPS.FP.items():
        try:
            fp_load.corpo(nome_fp)
        except FileNotFoundError:
            pass
    pasta3d = HERE / "3d"
    tris: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    for f in fp_load.kids(arv, "footprint"):
        nome = f[1]
        # O corpo sai de tres lugares, nesta ordem: o .wrl que este projeto
        # desenhou, o .wrl da biblioteca do KiCad que o proprio footprint
        # aponta, e - so se nao houver nenhum - a caixa do contorno.
        #
        # Ate 2026-09-25 a funcao pulava tudo o que nao fosse desenhado aqui,
        # confiando no GLB para o resto. Mas o `--subst-models` do kicad-cli
        # nao substitui o .wrl pelo .step no GLB, entao os 105 resistores,
        # capacitores e indutores da biblioteca NAO APARECIAM: o desenho
        # mostrava cobre nu onde havia peca, e foi isso que o dono viu.
        caminho_kicad = ""
        desloca_modelo = (0.0, 0.0, 0.0)
        for mm in f:
            if isinstance(mm, list) and mm and mm[0] == "model":
                caminho_kicad = mm[1]
                sub = fp_load.kid(mm, "offset")
                if sub:
                    v = fp_load.kid(sub, "xyz")
                    if v:
                        desloca_modelo = tuple(float(q) for q in v[1:4])
                break
        if nome not in FPS.CORPO_TODOS and not caminho_kicad:
            continue
        # Uma peca com STEP de verdade ja vem desenhada pelo GLB, que o
        # kicad-cli exporta do proprio `.kicad_pcb`. Desenhar por cima dela o
        # `.wrl` que este projeto tinha escrito antes de conseguir o STEP poe
        # DOIS corpos no mesmo lugar - e os dois discordam: o `.wrl` do J101 e
        # um paralelepipedo centrado nas ilhas, enquanto o receptaculo de
        # verdade tem a boca numa ponta so, e o do J103 tinha 4,50 mm de
        # altura, o numero velho, contra os 3,75 mm do JST ZH. O resultado e
        # uma peca que parece deslocada, torta ou alta demais. Quem tem STEP
        # e desenhado uma vez so, pelo KiCad.
        #
        # Isto vale tambem para o STEP que vem girado de fabrica: o
        # `(rotate ...)` do footprint e aplicado pelo `kicad-cli` na
        # exportacao, entao o corpo ja sai do GLB no lugar certo.
        if caminho_kicad.lower().endswith((".step", ".stp")):
            continue
        w, h, alt = FPS.CORPO_TODOS.get(nome, (0.0, 0.0, 0.0))
        at = fp_load.kid(f, "at")
        x, y = float(at[1]), float(at[2])
        ang = math.radians(float(at[3])) if len(at) > 3 else 0.0
        atras = fp_load.kid(f, "layer")[1] == "B.Cu"
        ca, sa = math.cos(ang), math.sin(ang)

        ox, oy, oz = desloca_modelo

        def por_no_lugar(v: np.ndarray) -> np.ndarray:
            """The body's own coordinates, put where the board has the part.

            The footprint's `(model ... (offset ...))` comes first, in
            millimetres and in the model's own frame: the U.FL of J302 carries
            0.475 mm in X, and without it the connector sat half a millimetre
            off its pads in the drawing while the board itself was right.
            """
            vx = v[..., 0] + ox
            vx = -vx if atras else vx
            vy, vz = v[..., 1] + oy, v[..., 2] + oz
            return np.stack([x + vx * ca + vy * sa,
                             y - vx * sa + vy * ca,
                             (VERSO_Z - vz) if atras else (FRENTE_Z + vz)],
                            axis=-1)

        arq = pasta3d / (nome.split(":", 1)[1] + ".wrl")
        if not arq.exists() and caminho_kicad:
            # o caminho que o footprint aponta, com a variavel do KiCad
            # resolvida para a biblioteca instalada
            alvo = caminho_kicad.replace("${KICAD8_3DMODEL_DIR}",
                                         str(FPS.LIB3D)).replace("${KIPRJMOD}",
                                                             str(HERE))
            arq = pathlib.Path(alvo.replace("\\", "/"))
            # kicad-cli's --subst-models swaps a library .wrl for the .step
            # that sits beside it, so that part is ALREADY in the GLB: drawing
            # the .wrl too puts two bodies in the same place. Only a library
            # model with no .step - the SOT-523 has none installed here - is
            # drawn from here.
            if arq.with_suffix(".step").exists() or arq.with_suffix(".STEP").exists():
                continue
        formas = ler_wrl(arq) if (arq.exists() and arq.suffix.lower() == ".wrl") \
            else []
        if formas:
            for malha, cor in formas:
                tris.extend(por_no_lugar(malha))
                cols.extend([np.array(cor)] * len(malha))
            continue

        # no body file: the courtyard box, which is all anybody knows
        cantos = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
        caixa = np.array([[list(c) + [z] for c in cantos] for z in (0.0, alt)])
        base = [por_no_lugar(np.array(p)) for p in caixa[0]]
        topo = [por_no_lugar(np.array(p)) for p in caixa[1]]
        faces = [(base[0], base[3], base[2]), (base[0], base[2], base[1]),
                 (topo[0], topo[1], topo[2]), (topo[0], topo[2], topo[3])]
        for k in range(4):
            a, b = k, (k + 1) % 4
            faces.append((base[a], base[b], topo[b]))
            faces.append((base[a], topo[b], topo[a]))
        for t in faces:
            tris.append(np.array(t, dtype=np.float64))
            cols.append(np.array([0.13, 0.13, 0.14]))
    if not tris:
        return np.zeros((0, 3, 3)), np.zeros((0, 3))
    return np.array(tris), np.array(cols)


def corpos(j: dict, bina: bytes) -> list[tuple[np.ndarray, np.ndarray]]:
    """Every primitive on its own: (triangles in world space, colour).

    triangulos() flattens the scene, which is what a renderer wants. A rule
    that asks "where are the solder tails of this connector" needs the
    bodies one by one: a tail is a small thin body that touches the board,
    the housing is a big one, and only the first says which way the part is
    turned. Same coordinates as triangulos(): metres, Z up.
    """
    cores = []
    for mat in j.get("materials", []):
        pbr = mat.get("pbrMetallicRoughness", {})
        cores.append(np.array(pbr.get("baseColorFactor", [0.7, 0.7, 0.7, 1.0])[:3]))
    if not cores:
        cores = [np.array([0.7, 0.7, 0.7])]
    saida: list[tuple[np.ndarray, np.ndarray]] = []
    cena = j.get("scenes", [{}])[j.get("scene", 0)]

    def andar(i_no: int, pai: np.ndarray) -> None:
        no = j["nodes"][i_no]
        m = pai @ matriz(no)
        if "mesh" in no:
            for prim in j["meshes"][no["mesh"]].get("primitives", []):
                if prim.get("mode", 4) != 4 or "POSITION" not in prim.get("attributes", {}):
                    continue
                pos = acessor(j, bina, prim["attributes"]["POSITION"])
                if "indices" in prim:
                    idx = acessor(j, bina, prim["indices"]).reshape(-1)
                else:
                    idx = np.arange(len(pos))
                n_tri = len(idx) // 3
                if n_tri == 0:
                    continue
                p = np.concatenate([pos, np.ones((len(pos), 1))], axis=1)
                p = (m @ p.T).T[:, :3]
                t = p[idx[:n_tri * 3]].reshape(n_tri, 3, 3)
                t = np.stack([t[..., 0], -t[..., 2], t[..., 1]], axis=-1)
                c = cores[prim.get("material", 0)] if prim.get("material") is not None \
                    else cores[0]
                saida.append((t, c))
        for f in no.get("children", []):
            andar(f, m)

    for i_no in cena.get("nodes", []):
        andar(i_no, np.eye(4))
    return saida


def _glb_atual() -> pathlib.Path | None:
    """O GLB da placa, exportado do KiCad, e sempre o da placa de AGORA.

    Este desenho e feito de duas metades: a placa e os modelos do KiCad vem
    do GLB, e os corpos que este projeto desenha sao acrescentados por cima,
    lidos do `.kicad_pcb`. Se o GLB for de uma versao anterior da placa, as
    duas metades ficam de versoes diferentes - a placa de antes com os corpos
    de agora -, e o resultado parece uma peca torta, com o pad fora da ilha.
    Foi exatamente o que aconteceu: um GLB de sete horas antes, com todas as
    pecas que se moveram no intervalo, e ninguem avisou.

    Entao aqui nao se confia: se o GLB nao existe ou e mais velho que a
    placa, ele e refeito. Nunca se desenha a partir de entrada velha.
    """
    import subprocess

    glb = HERE / "pmeter.glb"
    pcb = HERE / "pmeter.kicad_pcb"
    if not pcb.exists():
        print("pmeter.kicad_pcb nao existe: rode o make_pcb.py antes")
        return None
    if glb.exists() and glb.stat().st_mtime >= pcb.stat().st_mtime:
        return glb
    print("exportando o GLB da placa (o que havia era mais velho que ela)...")
    r = subprocess.run(
        [str(KICAD_CLI), "pcb", "export", "glb", "--subst-models",
         "--include-tracks", "--include-zones", "-o", str(glb), str(pcb)],
        capture_output=True, text=True)
    if r.returncode != 0 or not glb.exists():
        print("o kicad-cli nao exportou o GLB:", r.stderr.strip()[:200])
        return None
    return glb


def main() -> int:
    glb = _glb_atual()
    if glb is None:
        return 1
    j, bina = ler_glb(glb)
    tris, cols = triangulos(j, bina)
    extra_t, extra_c = caixas_das_pecas()
    n_corpos = len(extra_t)
    silk_t, silk_c = serigrafia()
    if len(silk_t):
        extra_t = np.concatenate([extra_t, silk_t])
        extra_c = np.concatenate([extra_c, silk_c])
    if len(extra_t):
        # the boxes are in millimetres with y growing downward, as the board
        # file has them; the GLB is in metres with y already up
        extra_t = np.stack([extra_t[..., 0], -extra_t[..., 1], extra_t[..., 2]],
                           axis=-1) / 1000.0
        tris = np.concatenate([tris, extra_t])
        cols = np.concatenate([cols, extra_c])
    print(f"{len(tris)} triangulos, {len(j.get('meshes', []))} malhas, "
          f"{n_corpos} corpos e {len(silk_t)} tracos de serigrafia "
          "desenhados aqui")

    for nome, az, el, w, h in (("placa-3d-frente.png", 0.0, 90.0, 1800, 900),
                               ("placa-3d-angulo.png", 28.0, 38.0, 1600, 1100),
                               ("placa-3d-tras.png", 180.0, -90.0, 1800, 900)):
        img = render(tris, cols, w, h, az, el)
        IMG.mkdir(parents=True, exist_ok=True)
        img.save(IMG / nome)
        print(f"  {IMG.relative_to(HERE.parents[1]) / nome}: {w} x {h}")

    # and the stack: board over cell, pulled apart so both are visible at
    # once; the pod around them is pod/make_pod.py's view.
    caixa_t, caixa_c = pecas_da_caixa(afastar=16.0)
    caixa_t = np.stack([caixa_t[..., 0], -caixa_t[..., 1], caixa_t[..., 2]],
                       axis=-1) / 1000.0
    montagem_t = np.concatenate([tris, caixa_t])
    montagem_c = np.concatenate([cols, caixa_c])
    img = render(montagem_t, montagem_c, 1600, 1100, 24.0, 26.0)
    img.save(IMG / "placa-3d-montagem.png")
    print(f"  placa-3d-montagem.png: 1500 x 1500 "
          f"({len(MONTAGEM)} peca sob a placa)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
