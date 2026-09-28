#!/usr/bin/env python3
"""Confere o mapa de pinos da placa do medidor contra o silício e contra docs/02.

Um arquivo de devicetree compila com um pino em dois lugares, com o SCL de
um TWIM num pino que não é de clock e com o pad do NFC ocupado. Nada disso
aparece no build: aparece na bancada, meses depois, com o osciloscópio na
mão. Este script lê a placa e diz antes. E como o esquemático
(hardware_powermeter/cad/nets.py) e o devicetree saem da mesma tabela de
docs/02-hardware.md, ele confere também que cada pino da tabela está no
devicetree, e que o devicetree não usa pino que a tabela não dá.

O que ele confere:

1. **Pino em dois lugares.** Um pino só pode ter uma função. Os estados
   ``_default`` e ``_sleep`` do mesmo periférico não contam.
2. **Pinos de clock.** O SCL de um TWIM e o SCK de um SPIM só funcionam em
   alguns pinos. A ficha do nRF54L15 não está aqui, então a lista é a dos
   pinos que a **própria Nordic** usa para isso nos arquivos de placa do
   NCS, cada um com o arquivo citado.
3. **Pads do NFC.** P1.01 e P1.02 saem do reset como antena NFC (e o
   módulo não os expõe).
4. **Cristal.** P1.20 e P1.21 levam o cristal de 32,768 kHz no nRF54LM20A;
   no nRF54L15 eles não existem, e o cristal é interno ao módulo.
5. **Limite da porta.** No nRF54L15, P0 tem 7 pinos, P1 tem 16 e P2 tem 11.
6. **Blocos seriais.** Cada bloco (00, 20 a 22, 30) tem **um** periférico.
7. **Apelidos.** Os serviços acham o hardware por apelido; um que falte
   deixa o serviço sem o dispositivo, em silêncio.
8. **A tabela de docs/02.** Todo pino ``Px.yy`` da coluna "Pino do SoC" da
   tabela "Pinos do módulo" tem de estar no devicetree, e vice-versa.
9. **O esquemático contra a mesma tabela.** Todo pino da tabela está numa
   rede do ``nets.py`` com o módulo, e vice-versa, e nenhum pino do módulo
   aparece em duas redes (isso é curto). É o que garante que a placa é
   fabricada com a pinagem que o firmware espera: sem esta conferência, o
   devicetree e o esquemático podem divergir e só a bancada conta.

Uso:

    python tools/fw/board_check.py                  # a placa do projeto
    python tools/fw/board_check.py <pasta-da-placa> # outra

Sai com 1 se achar problema.
"""

import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BOARD = ROOT / "zephyr_app" / "boards" / "pm" / "pmboard"
PIN_DOC = ROOT / "docs" / "02-hardware.md"
SCH_NETS = ROOT / "hardware_powermeter" / "cad" / "nets.py"
# A referência do módulo no esquemático (hardware_powermeter/03-netlist.md)
MODULE_REF = "U201"

# Os pinos de clock do nRF54L15, e a fonte deles NÃO é uma tabela de ficha:
# a ficha do nRF54L15 não está neste repositório, e a do nRF54LM20A (tabela
# 79) descreve outro chip - usá-la aqui foi o que fez este verificador
# reprovar o P1.11 em 2026-09-28, um pino que a própria Nordic usa como
# TWIM_SCL.
#
# A evidência é o NCS instalado: cada pino abaixo é usado pela Nordic como
# SCL de TWIM ou SCK de SPIM num arquivo de placa do nRF54L, e o arquivo
# está citado ao lado. Enquanto a ficha não estiver aqui, esta lista é o que
# há, e ela é conservadora: um pino que não está nela não é necessariamente
# ruim, só não tem evidência - por isso o problema diz exatamente isso.
CLOCK_PINS = {
    "P1.02",  # nrf54l15dk_nrf54l_05_10_15-pinctrl.dtsi e vários shields
    "P1.03",  # idem
    "P1.08",
    "P1.11",  # nrf/boards/shields/pca63565/.../nrf54l15dk_nrf54l15_cpuapp.overlay
    "P1.12",
    "P1.13",
    "P2.00",
    "P2.01",  # spi00 SCK do DK do L15
    "P2.03",
    "P0.03",  # nrf/boards/shields/nrf2240ek/.../nrf54l15dk_nrf54l15_cpuapp.overlay
}

NFC_PINS = {"P1.01", "P1.02"}
LFXO_PINS = {"P1.20", "P1.21"}

# ngpios de cada porta (zephyr/dts/vendor/nordic/nrf54lm20_a_b.dtsi)
# nRF54L15, do `ngpios` de nrf54l_05_10_15.dtsi no NCS instalado.
# Eram {0: 10, 1: 32, 2: 11, 3: 13} do nRF54LM20A, e a diferença não é
# cosmética: P1 acaba em P1.15 aqui, e o mapa antigo usava P1.29 e P1.31.
PORT_PINS = {0: 7, 1: 16, 2: 11}

# Apelidos que os serviços procuram (docs/02, Pinos do módulo)
REQUIRED_ALIASES = [
    "bridge-adc", "bridge-excitation", "imu0", "temp0", "fuel-gauge0",
    "charger-status", "charger-error", "ship-activate",
    "led-r", "led-g", "led-b", "watchdog0",
]


def pin_name(port, pin):
    return f"P{port}.{pin:02d}"


def read_all(board_dir):
    """Todo o texto da placa, .dts e .dtsi juntos."""
    text = ""
    for path in sorted(board_dir.glob("*.dts")) + sorted(board_dir.glob("*.dtsi")):
        text += path.read_text(encoding="utf-8") + "\n"
    return text


def collect_pins(text):
    """{pino: {dono}}, com os estados _sleep somados ao periférico."""
    used = defaultdict(set)

    for block in re.finditer(
        r"(\w+)_(default|sleep):\s*\w+\s*\{(.*?)\n\t\};", text, re.S
    ):
        owner, _state, body = block.group(1), block.group(2), block.group(3)
        for m in re.finditer(r"NRF_PSEL\((\w+),\s*(\d+),\s*(\d+)\)", body):
            fn, port, pin = m.group(1), int(m.group(2)), int(m.group(3))
            used[pin_name(port, pin)].add(f"{owner} {fn}")

    for m in re.finditer(r"([\w-]+)\s*=\s*<&gpio(\d)\s+(\d+)", text):
        prop, port, pin = m.group(1), int(m.group(2)), int(m.group(3))
        used[pin_name(port, pin)].add(prop)
    # cs-gpios lista mais de um: <&gpio2 5 ...>, <&gpio2 7 ...>
    for m in re.finditer(r"cs-gpios\s*=\s*([^;]+);", text):
        for g in re.finditer(r"<&gpio(\d)\s+(\d+)", m.group(1)):
            used[pin_name(int(g.group(1)), int(g.group(2)))].add("cs-gpios")

    return used


def collect_blocks(text):
    """{bloco: {periférico ligado}} dos nós com status okay."""
    blocks = defaultdict(set)
    for m in re.finditer(r"&(uart|i2c|spi)(\d\d)\s*\{([^}]*)", text):
        kind, num, body = m.group(1), m.group(2), m.group(3)
        if 'status = "okay"' in body:
            blocks[num].add(f"{kind}{num}")
    return blocks


def doc_pins():
    """Os pinos Px.yy da tabela "Pinos do módulo" de docs/02, com o sinal."""
    if not PIN_DOC.is_file():
        return {}
    text = PIN_DOC.read_text(encoding="utf-8")
    start = text.find("## Pinos do módulo")
    end = text.find("\n## ", start + 1)
    section = text[start:end if end > 0 else None]
    pins = {}
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        # uma linha pode trazer vários sinais e vários pinos, na mesma ordem
        # (`LED_R`, `LED_G`, `LED_B` | P1.06, P1.08, P1.09): cada pino leva o
        # seu, não a célula inteira.
        signals = [s.strip().strip("`") for s in cells[0].split(",")]
        found = re.findall(r"P(\d)\.(\d\d)", cells[1])
        for i, (port, num) in enumerate(found):
            signal = signals[i] if i < len(signals) else signals[0]
            pins[pin_name(int(port), int(num))] = signal
    return pins


def pinos_do_modulo():
    """Os GPIO que o módulo traz para fora, lidos da tabela do esquemático.

    O SoC tem 34 GPIO e o HOLYIOT-26001-A traz 30: `P0.05`, `P0.06`, `P1.00`
    e `P1.01` não têm pad no módulo, então não existem nesta placa. Listar um
    deles como "livre" convida a escolher um pino que não dá para usar, e foi
    o que este verificador fazia até 2026-09-28.

    A lista sai de `PADS_HOLYIOT` em `cad/parts.py`, que é o de-para para o
    pad do módulo, e não de uma cópia digitada aqui. Devolve `None` quando
    não consegue ler, para quem chama poder dizer isso em vez de mentir.
    """
    caminho = SCH_NETS.parent / "parts.py"
    if not caminho.is_file():
        return None
    texto = caminho.read_text(encoding="utf-8")
    m = re.search(r"PADS_HOLYIOT\s*[:=][^=]*=?\s*\{(.*?)\n\}", texto, re.S)
    if not m:
        return None
    nomes = set(re.findall(r'"(P\d\.\d\d)"', m.group(1)))
    return nomes or None


def sch_pins():
    """Os pinos do módulo no esquemático: {pino: [(rede, [outros membros])]}.

    Lê hardware_powermeter/cad/nets.py, que é a lista de nós do esquemático
    como dado. Uma lista por pino, e não um valor, porque pino em duas redes
    é curto e precisa ser visto, não sobrescrito.
    """
    if not SCH_NETS.is_file():
        return None
    text = SCH_NETS.read_text(encoding="utf-8")
    pins = defaultdict(list)
    for block in re.finditer(r'net\("([^"]+)"((?:[^)]*\([^)]*\))*[^)]*)\)', text):
        name, body = block.group(1), block.group(2)
        members = re.findall(r'\("([^"]+)",\s*"([^"]+)"\)', body)
        for ref, pin in members:
            if ref == MODULE_REF and re.fullmatch(r"P\d\.\d\d", pin):
                others = [f"{r}.{p}" for r, p in members if r != MODULE_REF]
                pins[pin].append((name, others))
    return pins


def main():
    board_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_BOARD
    if not board_dir.is_dir():
        print(f"board_check: {board_dir} não é uma pasta")
        return 1

    text = read_all(board_dir)
    if not text.strip():
        print(f"board_check: nenhum .dts em {board_dir}")
        return 1

    used = collect_pins(text)
    problems = []

    print(f"placa: {board_dir.relative_to(ROOT)}")
    print(f"{len(used)} pinos usados de {sum(PORT_PINS.values())}\n")

    for pin, owners in sorted(used.items()):
        if len(owners) > 1:
            problems.append(f"{pin} em dois lugares: {', '.join(sorted(owners))}")

    for pin, owners in sorted(used.items()):
        for owner in owners:
            if ("TWIM_SCL" in owner or "SPIM_SCK" in owner) and pin not in CLOCK_PINS:
                problems.append(f"{pin} leva {owner} e não há evidência de que seja pino "
                                "de clock: a Nordic não o usa assim em nenhum arquivo "
                                "de placa do nRF54L do NCS")

    for pin in sorted(NFC_PINS & used.keys()):
        problems.append(f"{pin} é pad do NFC e sai do reset sem GPIO: {used[pin]}")
    for pin in sorted(LFXO_PINS & used.keys()):
        problems.append(f"{pin} leva o cristal de 32,768 kHz: {used[pin]}")

    for pin in sorted(used):
        port, num = int(pin[1]), int(pin[3:])
        if num >= PORT_PINS[port]:
            problems.append(f"{pin} não existe: P{port} tem {PORT_PINS[port]} pinos")

    for block, periphs in sorted(collect_blocks(text).items()):
        if len(periphs) > 1:
            problems.append(
                f"bloco {block} com mais de um periférico: {', '.join(sorted(periphs))}"
            )

    alias_block = re.search(r"aliases\s*\{(.*?)\n\t\};", text, re.S)
    aliases = set()
    if alias_block:
        aliases = set(re.findall(r"([\w-]+)\s*=\s*&", alias_block.group(1)))
    for name in REQUIRED_ALIASES:
        if name not in aliases:
            problems.append(f"falta o apelido {name}, que um serviço procura")

    # 8. a tabela de docs/02 contra o devicetree, nos dois sentidos
    table = doc_pins()
    if not table:
        problems.append("docs/02-hardware.md sem a tabela 'Pinos do módulo': nada para conferir")
    for pin, signal in sorted(table.items()):
        if pin not in used:
            problems.append(f"{pin} ({signal}) está na tabela de docs/02 e não no devicetree")
    for pin in sorted(used):
        if table and pin not in table:
            problems.append(f"{pin} está no devicetree ({', '.join(sorted(used[pin]))}) e não na tabela de docs/02")

    # 9. o esquemático contra a mesma tabela, nos dois sentidos
    sch = sch_pins()
    if sch is None:
        problems.append(
            f"{SCH_NETS.relative_to(ROOT)} não existe: o esquemático não pôde ser conferido"
        )
    elif not sch:
        problems.append(
            f"{SCH_NETS.relative_to(ROOT)} não tem nenhum pino de {MODULE_REF}:"
            " o esquemático não pôde ser conferido"
        )
    else:
        for pin, nets in sorted(sch.items()):
            if len(nets) > 1:
                problems.append(
                    f"{pin} do {MODULE_REF} em {len(nets)} redes do esquemático"
                    f" ({', '.join(n for n, _ in nets)}): isso é curto"
                )
        for pin, signal in sorted(table.items()):
            if pin not in sch:
                problems.append(
                    f"{pin} ({signal}) está na tabela de docs/02 e não no esquemático"
                )
        for pin in sorted(sch):
            if table and pin not in table:
                problems.append(
                    f"{pin} está no esquemático ({sch[pin][0][0]}) e não na tabela de docs/02"
                )
        if not problems:
            print(f"esquemático: {len(sch)} pinos do {MODULE_REF}, os mesmos da tabela")
            for pin in sorted(sch, key=lambda s: (s[1], s[3:])):
                net, others = sch[pin][0]
                print(f"  {pin}  {table.get(pin, '?'):14s} {net:12s} -> {', '.join(others)}")
            print()

    free = []
    for port, count in sorted(PORT_PINS.items()):
        for num in range(count):
            name = pin_name(port, num)
            if name not in used and name not in NFC_PINS and name not in LFXO_PINS:
                free.append(name)
    # Free on the SoC is not the same as usable: the module brings out 30 of
    # the 34 GPIO, and a pin the module does not carry has no pad on the
    # board. One list called "livres" invited picking a pin that does not
    # exist here, so the two are separated, and the module's pads come from
    # the schematic's own table instead of being retyped.
    no_modulo = pinos_do_modulo()
    uteis = [p for p in free if not no_modulo or p in no_modulo]
    so_no_soc = [p for p in free if no_modulo and p not in no_modulo]
    print(f"livres E presentes no modulo ({len(uteis)}): {', '.join(uteis)}")
    if so_no_soc:
        print(f"livres no SoC mas NAO no modulo ({len(so_no_soc)}): "
              f"{', '.join(so_no_soc)}")
    if not no_modulo:
        print("  AVISO: nao foi possivel ler a lista de pads do modulo, "
              "entao a lista acima e a do SoC inteiro")
    # As mesmas exclusões da lista de livres: um pino que sai do reset como
    # antena NFC ou como cristal não está disponível só porque tem clock.
    # Sem isto a linha anunciava P1.02, que é pad de NFC.
    clock_livres = CLOCK_PINS - used.keys() - NFC_PINS - LFXO_PINS
    if no_modulo:
        clock_livres &= set(no_modulo)
    print(f"de clock ainda livres no modulo: "
          f"{', '.join(sorted(clock_livres))}\n")

    if problems:
        print(f"{len(problems)} problema(s):")
        for p in problems:
            print(f"  {p}")
        return 1

    print("mapa de pinos coerente com o silício e com docs/02")
    return 0


if __name__ == "__main__":
    sys.exit(main())
