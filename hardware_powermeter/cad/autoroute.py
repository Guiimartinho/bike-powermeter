#!/usr/bin/env python3
"""Rotear a placa com o Freerouting, pelo caminho nativo do KiCad.

    "D:/KiCAD/bin/python.exe" hardware_powermeter/cad/autoroute.py

Roda com o Python DO KICAD, nao com o do sistema: quem exporta o DSN e
importa o SES e o proprio `pcbnew`, e ele so existe la (o mesmo motivo do
`fill_zones.py`).

Por que ele existe. Ate 2026-09-30 esta cadeia roteava com um labirinto
escrito aqui dentro (`route.py` e `route_neg.py`), para o arquivo sair
pronto sem ninguem abrir o KiCad. Para todo o resto - esquematico, contorno,
colocacao, 3D, PDF, dry runs - gerar por script foi a decisao certa; para o
roteamento, nao. Um roteador e decadas de pesquisa, e o nosso, depois de
quatro dias de conserto, deixava 21 ligacoes sem cobre numa placa de 43
redes e 108 ligacoes. O Freerouting fecha esse tamanho de placa em minutos.

O que NAO muda: a colocacao, as zonas, as regras do `pmeter.kicad_pro`, o
DRC do KiCad, o `check_pcb.py` e os dois dry runs continuam sendo os juizes.
Troca-se apenas quem desenha a trilha.

Cuidado registrado pelo proprio Freerouting (notas da v2.4.1): o DSN que o
KiCad exporta NAO leva a folga cobre-borda, e o roteamento sobre plano de
cobre pode gerar violacao de isolamento. Por isso a placa passa pelo nosso
DRC e pelos dry runs depois - nunca se publica o resultado sem eles.

Freerouting v2.4.1, GPL-3.0, rodado como FERRAMENTA EXTERNA sobre os nossos
arquivos: nada dele entra no projeto, e a licenca CC BY-NC nao muda.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PLACA = HERE / "pmeter.kicad_pcb"

# O jar e o Java ficam FORA do repositorio: sao binarios de terceiros, e
# distribuir um jar GPL-3 dentro de um projeto CC BY-NC nao e da conta deste
# repositorio. Os dois caminhos sao sobrescreviveis por variavel de ambiente.
FERRAMENTAS = pathlib.Path(
    os.environ.get("PMETER_FERRAMENTAS",
                   r"C:\Users\AORUS-Desktop\tools\freerouting"))
JAR = pathlib.Path(os.environ.get("FREEROUTING_JAR",
                                  FERRAMENTAS / "freerouting-2.4.1.jar"))
# O jar da v2.4.1 e compilado para Java 25 (class file 69): o Java 17 que ja
# estava na maquina recusa com UnsupportedClassVersionError, entao vai o
# runtime proprio, descompactado ao lado dele.
JAVA = pathlib.Path(os.environ.get(
    "FREEROUTING_JAVA",
    FERRAMENTAS / "jdk-25.0.4.1+1-jre" / "bin" / "java.exe"))

DSN = HERE / "_pmeter.dsn"
SES = HERE / "_pmeter.ses"

# Quantas passagens de roteamento automatico. Nao e tempo de espera: o
# Freerouting para sozinho quando nao acha mais o que melhorar.
PASSAGENS = int(os.environ.get("FREEROUTING_PASSAGENS", "100"))


# As camadas que sao PLANO e nao devem receber trilha, pelo nome que elas tem
# no DSN (o KiCad exporta o nome de usuario da camada, nao "In1.Cu").
PLANOS = ("gnd",)


def marcar_plano(dsn: pathlib.Path) -> int:
    """Troca `(type signal)` por `(type power)` nas camadas de plano.

    O KiCad exporta TODAS as camadas de cobre como `signal`, e o Freerouting
    acredita: na primeira placa que ele roteou, em 2026-09-30, saiu trilha de
    sinal dentro da In1.Cu, que e o plano de terra macico deste projeto - e o
    `stitch_gnd.py` recusou a placa dizendo "ha trilha numa camada que o
    roteador nao usa (In1.Cu)", que foi como o defeito apareceu. Em Specctra,
    uma camada `power` nao recebe roteamento, que e exatamente o que se quer:
    o plano fica inteiro e as vias o atravessam.
    """
    texto = dsn.read_text(encoding="utf-8")
    n = 0
    for nome in PLANOS:
        alvo = f"(layer {nome}\n      (type signal)"
        if alvo in texto:
            texto = texto.replace(alvo, f"(layer {nome}\n      (type power)", 1)
            n += 1
    texto, n_folga = folga_que_cobre_o_furo(texto)
    if n or n_folga:
        dsn.write_text(texto, encoding="utf-8", newline="\n")
    if n_folga:
        print(f"  folga do DSN subida para {FOLGA_DSN_UM} um em {n_folga} "
              "regra(s), por causa do furo", flush=True)
    return n


# A folga que o DSN pede ao Freerouting, em micrometros. NAO e a folga de
# cobre do projeto (88,9): e ela mais o que falta para o FURO da via caber.
#
# O Freerouting nao modela folga de furo - ele so guarda cobre contra cobre.
# Com a via de 0,40 e furo de 0,20, o anel tem 0,10: uma trilha parada a
# 0,0889 do cobre da via fica a 0,1889 do furo, e o `min_hole_clearance` do
# projeto pede 0,20. Foram 79 erros de uma vez em 2026-09-30, todos entre
# vias e trilhas do PROPRIO Freerouting, todos por um centesimo. Pedindo
# 0,115 de cobre, o furo fica a 0,215 e sobra margem.
FOLGA_DSN_UM = 115.0


def folga_que_cobre_o_furo(texto: str) -> tuple[str, int]:
    """Sobe a folga do DSN o bastante para o furo da via tambem caber.

    A folga entre duas ilhas SMD (`smd_smd`) fica como esta: ela e a do
    proprio encapsulamento, nao tem furo no meio, e subi-la fecharia a porta
    de pinos que ja sao apertados.
    """
    import re
    n = 0

    def troca(m):
        nonlocal n
        if float(m.group(1)) >= FOLGA_DSN_UM:
            return m.group(0)
        n += 1
        return f"(clearance {FOLGA_DSN_UM:g}{m.group(2)})"

    novo = re.sub(r"\(clearance ([\d.]+)((?: \(type (?!smd_smd)[a-z_]+\))?)\)",
                  troca, texto)
    return novo, n


# A largura minima de trilha do projeto, em mm, e a que o `pmeter.kicad_pro`
# cobra. O Freerouting estreita uma trilha abaixo disso quando precisa passar
# num vao apertado: em 2026-09-30 foram dez trilhas de 0,0674 mm em AIN_N e
# ICHG, dez erros de `track_width` no DRC.
LARGURA_MINIMA = 0.09


def alargar_finas(placa: pathlib.Path) -> int:
    """Devolve a largura minima a toda trilha que saiu abaixo dela.

    Alargar cobre ja desenhado pode encostar em vizinho, entao quem julga e
    o DRC logo depois - e foi assim que se mediu: as dez trilhas finas viraram
    dez erros a menos e um so' de isolamento, que e uma troca boa.
    """
    import re
    texto = placa.read_text(encoding="utf-8")
    n = 0

    def troca(m):
        nonlocal n
        if float(m.group(1)) >= LARGURA_MINIMA - 1e-9:
            return m.group(0)
        n += 1
        return f"(width {LARGURA_MINIMA})"

    novo = re.sub(r"\(width ([\d.]+)\)(?=\s*\(layer \"[FB]\.Cu\"|\s*\(layer \"In[12]\.Cu\")",
                  troca, texto)
    if n:
        placa.write_text(novo, encoding="utf-8", newline="\n")
    return n


def _exige(caminho: pathlib.Path, o_que: str) -> None:
    if not caminho.exists():
        raise SystemExit(
            f"nao achei {o_que}: {caminho}\n"
            "  o jar vem de https://github.com/freerouting/freerouting/"
            "releases e o runtime de https://api.adoptium.net/v3/binary/"
            "latest/25/ga/windows/x64/jre/hotspot/normal/eclipse")


def main() -> int:
    import pcbnew                                          # noqa: E402

    _exige(PLACA, "a placa")
    _exige(JAR, "o jar do Freerouting")
    _exige(JAVA, "o Java 25")

    placa = pcbnew.LoadBoard(str(PLACA))
    antes_t = len(placa.GetTracks())
    print(f"placa carregada: {len(placa.GetFootprints())} pecas, "
          f"{placa.GetNetCount() - 1} redes, {antes_t} itens de cobre",
          flush=True)

    # 1. DSN. O Freerouting le a placa, as regras e a lista de ligacoes
    #    daqui; e o formato que o proprio KiCad usa para falar com roteador
    #    externo desde sempre.
    if not pcbnew.ExportSpecctraDSN(placa, str(DSN)):
        raise SystemExit("o KiCad recusou exportar o DSN")
    n_plano = marcar_plano(DSN)
    print(f"{DSN.name}: {DSN.stat().st_size} B, {n_plano} camada(s) de plano",
          flush=True)

    # 2. o roteamento
    #
    # `-Djava.awt.headless=true` NAO e cosmetico, e o que faz isto funcionar.
    # Sem ele o Freerouting abre a janela e ESTOURA ao desenhar o nosso
    # despejo de cobre (NullPointerException em
    # BoardRenderer.renderConductionArea, por ConductionArea sem cache de
    # preenchimento); a caixa de erro modal trava o processo e o .ses sai com
    # ZERO BYTE, depois de a linha "Saving '...ses'" ja ter sido impressa.
    # Tres execucoes inteiras foram perdidas nisso em 2026-09-30, e o
    # processo ainda sai com codigo 0. Sem interface nao ha o que desenhar.
    #
    # `-mt 1`: o proprio Freerouting avisa, em toda execucao, que a
    # otimizacao multi-thread esta quebrada e gera violacao de isolamento.
    # Uma thread demora mais e entrega placa limpa, que e o que interessa.
    cmd = [str(JAVA), "-Djava.awt.headless=true", "-jar", str(JAR),
           "-de", str(DSN), "-do", str(SES),
           "-mp", str(PASSAGENS), "-mt", "1"]
    print("rodando: " + " ".join(cmd[2:]), flush=True)
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    for linha in (r.stdout or "").splitlines():
        if any(p in linha for p in ("INFO", "WARN", "ERROR", "pass",
                                    "Board", "rout")):
            print("  " + linha, flush=True)
    if r.returncode != 0:
        print((r.stderr or "")[:2000], file=sys.stderr)
        raise SystemExit(f"o Freerouting saiu com {r.returncode}")
    if not SES.exists():
        raise SystemExit("o Freerouting nao gravou o .ses")
    print(f"{SES.name}: {SES.stat().st_size} B em {time.time() - t0:.0f} s",
          flush=True)

    # 3. de volta para a placa
    placa = pcbnew.LoadBoard(str(PLACA))
    if not pcbnew.ImportSpecctraSES(placa, str(SES)):
        raise SystemExit("o KiCad recusou importar o SES")
    if not pcbnew.SaveBoard(str(PLACA), placa):
        raise SystemExit("nao consegui gravar a placa")

    n_larg = alargar_finas(PLACA)
    if n_larg:
        print(f"{n_larg} trilha(s) alargadas ate a largura minima", flush=True)

    conferida = pcbnew.LoadBoard(str(PLACA))
    trilhas = [t for t in conferida.GetTracks()
               if t.Type() == pcbnew.PCB_TRACE_T]
    vias = [t for t in conferida.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    print(f"{PLACA.name}: {len(trilhas)} trilhas e {len(vias)} vias",
          flush=True)
    print("  rode fill_zones.py, o DRC, o check_pcb.py e os dois dry runs: "
          "eles continuam sendo os juizes", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
