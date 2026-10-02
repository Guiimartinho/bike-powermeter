# Conectores e pontos de teste

Todo conector e todo ponto de teste da placa, **contato a contato**. As
[folhas do esquemático](02-esquematico.md) dizem quais sinais existem e a
[lista de nós](03-netlist.md) diz de onde cada um sai e aonde chega;
nenhuma das duas diz **em que contato** de cada conector o sinal entra. É
essa lacuna que este documento fecha, porque ela é a forma clássica de
inverter a polaridade da célula na primeira montagem.

**Nesta página:** [Como ler](#como-ler) · [De onde vem cada pinagem](#de-onde-vem-cada-pinagem) · [J101 · Conector magnético](#j101--conector-magnético) · [J102 · Célula](#j102--célula) · [J201 · Tag-Connect](#j201--tag-connect) · [J301 · Furos da ponte](#j301--furos-da-ponte) · [Pontos de teste](#pontos-de-teste) · [O que falta conferir](#o-que-falta-conferir)

> [!WARNING]
> **Nada disto foi montado, medido ou fabricado.** Cada pinagem abaixo
> vem de uma ficha de fabricante ou de uma escolha feita aqui, e está
> marcada como tal. O conector magnético **não tem fornecedor escolhido**:
> a sua numeração é deste projeto e muda com a peça.

## Como ler

- **Contato**: o número como o desenho do fabricante o numera; onde não há
  fabricante (o magnético), o número é o do footprint deste projeto.
- **Direção**: do ponto de vista **da placa**. `entrada` é o que chega,
  `saída` é o que a placa aciona, `bidir` é linha compartilhada, `alim` é
  alimentação ou retorno.
- **Origem da pinagem**: cada seção diz se a ordem dos contatos veio da
  **ficha do fabricante** ou é **escolha deste projeto**.
- Os designadores seguem o esquema por folha de [05](05-materiais.md#como-ler).

```mermaid
flowchart LR
    subgraph EXT["Fora do pod"]
        CABO["cabo magnético<br/>USB-A + SWD de 10 vias"]
        TC["cabo Tag-Connect<br/>TC2030 → J-Link"]
        PACK["célula com JST SH"]
        ARM["braço: ponte de extensômetros"]
    end
    subgraph PCB["Placa"]
        J101["J101 magnético<br/>6 contatos + 2 ímãs"]
        J102["J102 JST SH 2 vias"]
        J201["J201 Tag-Connect<br/>6 pads, 3 furos"]
        J301["J301<br/>5 furos"]
        TP["TP101 a TP104, TP201, TP202, TP301<br/>face de trás"]
    end
    CABO -.->|"pela janela da tampa"| J101
    TC -.->|"só com a placa nua"| J201
    PACK -->|"canal na ponta esquerda"| J102
    ARM -->|"rasgo no fundo do pod"| J301
```

## De onde vem cada pinagem

| Conector | Origem | Confiança |
|---|---|---|
| J101 magnético | **escolha deste projeto** sobre um footprint genérico | baixa: muda com a peça |
| J102 JST SH | ficha JST (mecânica); a polaridade é **escolha deste projeto** | média: a mandar ao fabricante do pack |
| J201 Tag-Connect | ficha do TC2030 (o padrão ARM de 6 vias) | alta |
| J301 furos | escolha deste projeto (ordem dos fios) | alta: são fios soldados, sem cabo padrão |

## J101 · Conector magnético

Seis contatos em **duas fileiras de três** a 2,5 mm, dois ímãs com
polaridade nos extremos, na face de cima da placa, atravessando a janela da
tampa do pod ([07](07-pod.md)). O cabo termina em USB-A (5 V, GND, D+, D−) e
numa saída SWD de 10 vias para o J-Link
([`docs/02`](../docs/02-hardware.md#conector-magnético)).

> [!IMPORTANT]
> **Nenhuma peça foi escolhida.** Todas as páginas de fornecedor tentadas em
> 2026-09-27 e 2026-09-28 estavam fora de alcance desta máquina. O footprint
> `pmeter:Pogo_Magnetico_6P_2x3_P2.5mm` e o corpo 3D são **deste projeto**,
> desenhados a partir do que o circuito e o pod exigem, e cada número abaixo
> é um **requisito de compra**, não uma medida. Quando a peça for escolhida,
> o footprint, a altura e a janela da tampa mudam com ela, e o dry run do pod
> mede os três.

### A peça que este projeto desenhou

| Medida | Valor | De onde vem |
|---|---|---|
| Contatos | 6, em 2 fileiras de 3, passo 2,5 mm | seis em fila custariam 12,5 mm só de contatos; em 2 × 3 ocupam 5,0 × 2,5 |
| Pad de cada contato | Ø 1,5 mm | escolha deste projeto |
| Abas dos ímãs | 0,8 × 4,4 mm em `x = ±3,9` | a 3,5 o cobre encostava no contato de 1,5 e o DRC acusava curto |
| Corpo | 8,6 × 4,6, dentro do courtyard de 9,0 × 5,0 | escolha deste projeto |
| Altura | **3,20 mm, no mínimo** | requisito do pod: a tampa fica a essa altura sobre a placa e a face do conector tem de alcançá-la |
| Chanfro do topo | 0,35 mm | para a cabeça do cabo se centrar sozinha em vez de parar numa quina viva |

**Os contatos chatos ficam no aparelho e as molas no cabo.** Um conector
magnético pode ser feito dos dois jeitos, e este é o que o pod exige: pôr as
molas na placa seria pôr seis peças móveis, seis barris e seis frestas numa
peça que tem de aguentar IPX7, poeira de estrada e jato de lavagem, e cada
barril é caminho de água para dentro de um corpo que é envasado e não abre
mais. Alvos chatos de ouro não têm o que emperrar nem por onde vazar; o
desgaste e o mecanismo vão para o cabo, que é barato de trocar e vive dentro
de casa. É o que faz qualquer aparelho vedado: num carregador de relógio as
molas estão no berço, não no relógio.

O corpo 3D em `cad/3d/Pogo_Magnetico_6P_2x3_P2.5mm.wrl` desenha exatamente
isso — caixa preta de LCP com chanfro, seis alvos de ouro de 1,3 mm 0,05 mm
salientes sobre os pads, dois ímãs niquelados de 1,1 × 4,2 × 2,6 expostos no
topo sobre as abas, e do lado da solda os seis pads estanhados e as duas
abas — e é o que aparece nas vistas 3D da placa.

| Contato | Sinal | Direção | Por quê nesta posição |
|---|---|---|---|
| 1 | `GND` | alim | na ponta, ao lado do 5 V |
| 2 | `VBUS` | entrada | ao lado do terra: um cabo forçado ao contrário põe 5 V no terra e terra no 5 V, um curto que a fonte do cabo aguenta, e não 5 V num sinal |
| 3 | `USB_DM` | bidir | par USB no meio, lado a lado |
| 4 | `USB_DP` | bidir | |
| 5 | `SWDIO_J` | bidir | par SWD na outra ponta, pelo TVS e por 100 Ω |
| 6 | `SWCLK_J` | entrada | |
| MP1, MP2 | `GND` | mecânico | as abas do quadro dos ímãs, soldadas ao terra |

Os quatro sinais passam pelo `D101` (TPD4E05U06, 12 kV de contato) antes
de chegar ao módulo; o `VBUS` entra no nPM1100, que é entrada, e nada sai
do pod pelos contatos sem cabo.

## J102 · Célula

**JST SM02B-SRSS-TB** na placa (série SH, passo 1,0 mm, 2 vias, **entrada
lateral**, 2,90 mm de altura, 1 A por contato) e **SHR-02V-S** no cabo do
pack. Fica em (3,5; 3,0) a **270°**, com a boca virada para a ponta
**esquerda** da placa: a baía da célula fica ao lado dela, naquela ponta, e o
plugue entra na horizontal pelo canal do pod ([07](07-pod.md)). O
`orientacao.py` mede a boca do footprint e confere o giro — foi ele que disse
que 270° é o ângulo.

> [!IMPORTANT]
> **A série importa, e é requisito de compra.** O SH tem 2,90 mm e é o que
> fixa o teto da tampa do pod em 3,20. Uma célula que chegue com **JST PH de
> 2,0 mm** — o conector comum nas células de hobby — tem receptáculo de 6 mm:
> **o pod não fecha com ele.** Ou a célula vem com SH, ou o plugue dela é
> trocado.

**Ele saiu e voltou.** Em 2026-09-26 o conector virou **dois furos
metalizados** para fio soldado, e o argumento era bom: tirava a peça mais alta
da placa — 2,90 mm, que fixava o teto sozinho — e, num pod envasado, fio
soldado segura melhor que trava. O que esse argumento não via é que a célula
que se **compra** já vem com dois fios e um plugue: com furos, montar o
aparelho significa cortar o plugue, soldar fio nu de 30 AWG dentro de uma
caixa de 20 mm e perder a possibilidade de trocar a célula. **Decisão do dono
em 2026-10-01:** o conector volta, e o pod paga os 0,5 mm de altura.

> [!IMPORTANT]
> **A polaridade é escolha deste projeto** e vai ao fabricante do pack
> antes da montagem: não existe padrão para conector de célula.

| Contato | Sinal | Direção | Observação |
|---|---|---|---|
| 1 | `VBAT+` | alim | o fio vermelho, na convenção usual |
| 2 | `GND` | alim | |

A célula é de **≥ 81 mAh com proteção própria** (a placa não tem proteção de
sobredescarga além do que o nPM1100 faz); o envelope reservado no pod é
**15 × 14 × 5,0 mm** — códigos `501415` ou `501414`
([12](12-comparacao-com-a-classe.md#a-célula-o-levantamento-nas-lojas-e-o-que-comprar)).

## J201 · Tag-Connect

**TC2030-IDC-NL**: seis pads de 0,7 × 0,6 mm a 1,27 mm de passo e três
furos de alinhamento, sem peça na placa. É a gravação de fábrica e a
bancada com a placa nua; dentro do pod fechado a depuração é pelo
conector magnético. Pinagem da ficha do Tag-Connect (o padrão ARM de 6
vias), em pé, com o `VTref` no `3V0`:

| Contato | Sinal | Direção |
|---|---|---|
| 1 | `VTref` (`3V0`) | alim |
| 2 | `SWDIO` | bidir |
| 3 | `nRESET` | entrada |
| 4 | `SWDCLK` | entrada |
| 5 | `GND` | alim |
| 6 | `SWO` | — (não ligado) |

## J301 · Furos da ponte

Cinco furos metalizados de 0,9 mm em ilhas de 1,5 mm, a 2,0 mm de passo,
na borda de baixo da placa, sob o conversor. Os fios sobem do braço pelo
rasgo no fundo do pod e entram nos furos por baixo; a solda no furo é o
alívio de tração ([07](07-pod.md#os-fios-da-ponte)).

| Furo | Sinal | Vai para |
|---|---|---|
| 1 | `E+` | `3V0_EXC`: a excitação, também `REFP0` do ADS1220 |
| 2 | `S+` | `R301` 1 kΩ → `AIN0` |
| 3 | `S−` | `R302` 1 kΩ → `AIN1` |
| 4 | `E−` | `GND` (o retorno da ponte e `REFN0`) |
| 5 | `SH` | `GND`: a blindagem do cabo, se houver |

A ordem `E+ S+ S− E−` é a ordem das cores usuais dos cabos de célula de
carga (vermelho, verde, branco, preto), para que quem for soldar não
precise de tabela.

Com a ponte escolhida, o **S5229**, que é ponte completa numa peça só
([01](01-lista-de-componentes.md#a-peça-achada-no-databook-do-fabricante-2026-09-28)),
**quatro** destes cinco furos são terminais do extensômetro: as duas
pontas da excitação e as duas do sinal. O quinto é a blindagem do cabo,
que não é terminal de grade nenhuma; fica onde está porque é por ali que
o cabo entra. Os cinco furos permanecem: a blindagem vale o furo, e o
padrão de 2,0 mm em cinco ilhas ocupa 10 mm de borda que a placa já tem.

## Pontos de teste

Pads de 1,0 mm **na face de trás**, para a bancada com a placa nua: no
pod a célula encosta nessa face e nada é alcançável além do conector
magnético. Cada um fica junto do que mede, pela tabela `JUNTO` de
[`cad/make_pcb.py`](cad/make_pcb.py).

| Ponto | Sinal | Junto de | Para quê |
|---|---|---|---|
| TP101 | `VBUS` | J101 | o 5 V do cabo chega? |
| TP102 | `VBAT` | J102 | a tensão da célula |
| TP103 | `3V0` | U101 | o buck |
| TP104 | `GND` | U101 | a referência da ponta de prova, com via própria ao plano |
| TP201 | `UART_TX` | U201 | o console do firmware |
| TP202 | `UART_RX` | U201 | |
| TP301 | `3V0_EXC` | U302 | a excitação da ponte chaveando |

## O que falta conferir

- **o conector magnético inteiro**: fornecedor, passo, corrente, altura,
  footprint, e se a peça escolhida aceita a numeração acima;
- a polaridade do `J102` com o fabricante do pack;
- a tabela `PADS_HOLYIOT` num módulo real, que decide se os pads 4
  (`SWDIO`), 5 (`SWDCLK`) e 1 (`NRESET`) do módulo são os que o `J201`
  alcança. Ela saiu do desenho mecânico do anúncio, não de uma ficha.
