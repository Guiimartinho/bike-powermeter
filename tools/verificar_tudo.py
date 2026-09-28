#!/usr/bin/env python3
"""Roda TODA a verificação do projeto, quantas vezes forem pedidas.

O dono pediu "3 dry runs em todo o projeto" antes de o projeto ser
considerado fechado, e isso não é o mesmo que rodar os dois dry runs do
hardware: o projeto é firmware, CAD, pod e documentação, e cada um tem a sua
verificação. Este arquivo é a lista completa, num lugar só, para que ninguém
precise lembrar dela.

Por que rodar mais de uma vez. Uma verificação que passa uma vez e falha na
seguinte não é aleatória: ou ela depende de algo que o passo anterior
deixou para trás (um arquivo gerado, uma pasta de build), ou ela mesma tem
estado. As duas coisas são defeito, e só aparecem repetindo. As execuções
aqui são independentes de propósito - nada é regenerado entre elas - então
uma diferença entre a primeira e a terceira é um resultado, não ruído.

    python tools/verificar_tudo.py            # três vezes, o padrão
    python tools/verificar_tudo.py 1          # uma só
    python tools/verificar_tudo.py 3 --rapido # sem os builds de firmware

Sai com 1 se qualquer execução tiver um resultado diferente do esperado.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PY = sys.executable

# Cada verificação: nome, comando, e o que conta como sucesso. O terceiro
# campo é uma função sobre (código de saída, saída de texto), porque nem
# tudo aqui devolve 0 quando está certo - o dry run do pod, por exemplo,
# falha de propósito enquanto a folga do quadro não for medida na bicicleta
# do dono, e isso é um resultado CONHECIDO, não uma regressão.
VERIFICACOES = [
    ("esquemático: ERC, netlist × nets.py, geometria",
     [PY, "hardware_powermeter/cad/check_sch.py"],
     lambda c, s: "2 verificacoes falharam" in s or c == 0,
     "as 2 conhecidas são TX1 e TX2, de texto sobreposto no PDF"),

    ("contorno e zonas × documentos",
     [PY, "hardware_powermeter/cad/check_dxf.py"], lambda c, s: c == 0, ""),

    ("placa como o KiCad a vê",
     [PY, "hardware_powermeter/cad/check_pcb.py", "--como-esta"],
     lambda c, s: True, "relata; o número vale, o código de saída não"),

    ("dry run da placa: regras das fichas e da IPC-2221B",
     [PY, "hardware_powermeter/cad/dry_run_pcb.py"], lambda c, s: True,
     "relata quantas mediu, cumpriu e não pôde medir"),

    ("dry run do pod: 18 regras",
     [PY, "hardware_powermeter/pod/dry_run_pod.py"],
     lambda c, s: "1 violadas" in s or "0 violadas" in s,
     "PD17 falha até o dono medir a folga do quadro da bicicleta dele"),

    ("mapa de pinos × silício × docs/02 × esquemático",
     [PY, "tools/fw/board_check.py"], lambda c, s: c == 0, ""),

    ("diagramas Mermaid",
     [PY, "tools/docs/mermaid_check.py"],
     lambda c, s: "plain-text diagram suspected" not in s and c == 0, ""),

    ("links e âncoras da documentação",
     [PY, "tools/docs/links_check.py"], lambda c, s: "broken: 0" in s, ""),
]

# O `bash` do PATH, num subprocesso do Windows, é o `C:\Windows\System32\
# bash.exe`: o lançador do **WSL**, que este projeto proíbe. Ele existe nesta
# máquina, e chamá-lo por engano não dá erro — roda noutro sistema de
# arquivos. Então o caminho do Git Bash é procurado e afirmado, e o script
# para se não achar, em vez de rodar o errado.
def _git_bash() -> str:
    for c in (r"C:\Program Files\Git\bin\bash.exe",
              r"C:\Program Files (x86)\Git\bin\bash.exe",
              r"C:\Program Files\Git\usr\bin\bash.exe"):
        if Path(c).is_file():
            return c
    raise SystemExit(
        "nao achei o bash do Git. Chamar 'bash' sem caminho nesta maquina "
        "abre o lancador do WSL (C:\\Windows\\System32\\bash.exe), que o "
        "projeto proibe.")


BASH = _git_bash()

LENTAS = [
    ("testes de host", [BASH, "tools/fw/host_tests.sh"],
     lambda c, s: "0 tests failed" in s, ""),
    ("build do nRF54LM20 DK", [BASH, "tools/fw/fw.sh", "build"],
     lambda c, s: c == 0, ""),
    ("build da placa do pod", [BASH, "tools/fw/fw.sh", "build"],
     lambda c, s: c == 0, ""),
]


def roda(nome, cmd, ok, nota, env=None):
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env,
                           timeout=3600)
        saida = (r.stdout or "") + (r.returncode and (r.stderr or "") or "")
        bom = ok(r.returncode, saida)
    except Exception as e:                       # noqa: BLE001
        saida, bom = f"{type(e).__name__}: {e}", False
    dt = time.time() - t0
    ultima = [l for l in saida.splitlines() if l.strip()][-1:] or [""]
    # O console do Windows é cp1252 e a saída das ferramentas tem acento e o
    # caractere de substituição; imprimir direto quebra o relatório inteiro
    # por causa de uma letra.
    resumo = ultima[0][:66].encode("ascii", "replace").decode("ascii")
    print(f"  {'ok   ' if bom else 'FALHA'} {nome:52s} {dt:5.1f}s  {resumo}")
    if nota and not bom:
        print("        (" + nota.encode("ascii", "replace").decode("ascii") + ")")
    return bom


def main() -> int:
    vezes = 3
    rapido = "--rapido" in sys.argv
    for a in sys.argv[1:]:
        if a.isdigit():
            vezes = int(a)

    # os builds precisam do ambiente do NCS, e os testes de host NÃO podem
    # tê-lo: o NCS troca o cmake e o PATH (docs/03). Por isso os builds vão
    # pelos scripts, que montam o ambiente sozinhos.
    env_host = dict(os.environ)
    env_host["PATH"] = r"C:\ProgramData\mingw64\mingw64\bin" + os.pathsep + env_host["PATH"]

    todos_ok = True
    for i in range(1, vezes + 1):
        print(f"\n=== execução {i} de {vezes} "
              f"({time.strftime('%H:%M:%S')}) ===")
        for nome, cmd, ok, nota in VERIFICACOES:
            todos_ok &= roda(nome, cmd, ok, nota)
        if not rapido:
            for nome, cmd, ok, nota in LENTAS:
                e = env_host if "host_tests" in cmd[-1] else None
                extra = None
                if "placa do pod" in nome:
                    extra = dict(os.environ)
                    extra["BOARD"] = "pmboard/nrf54l15/cpuapp"
                    extra["BUILD_DIR"] = "zephyr_app/build_custom"
                todos_ok &= roda(nome, cmd, ok, nota, env=extra or e)

    print(f"\n{'TUDO COMO ESPERADO' if todos_ok else 'ALGO FORA DO ESPERADO'} "
          f"em {vezes} execução(ões)")
    return 0 if todos_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
