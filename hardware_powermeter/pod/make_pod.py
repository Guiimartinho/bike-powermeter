#!/usr/bin/env python3
"""The crank pod, drawn around today's board: 2D (a PDF), 3D (PNG views)
and STL.

The pod is drawn AROUND the board and the cell, never the other way round
(the same rule as the bike computer's case, hardware_gnssbike/caixa): it
reads cad/pmeter.kicad_pcb with every footprint's courtyard, height and
face, plus the GLB the 3D renderer uses, and dry_run_pod.py measures this
file against the board.

What is decided HERE, and is a proposal until the owner says otherwise
(page 3 of the PDF repeats it):
  - a shallow box glued to the inner face of the left crank arm: walls of
    1,2, floor and lid of 1,0, corner radius 3; outside it is the board
    plus 0,5 of play on three sides and a 2,5 mm channel at the left end
    where the cell's leads rise from under the board to the JST on top;
  - the stack, from the arm up: glue 0,5 (not part of the pod), floor 1,0,
    cell 4,0, air 0,5, board 0,8, the module 2,4 plus 0,3 of air under the
    lid, lid 1,0: the height printed by main() and measured by the dry
    run against the 8,5 of docs/02, which this stack does NOT meet (docs/02
    says so too: 8,5 needs the cell beside the board, and 60 x 20 has no
    room for that beside a board this long);
  - the cell LYING UNDER THE BOARD, on the floor between the two ledges
    that carry the board's long edges, held by a rib at its right end and
    by the potting; the envelope reserved for it is 25 x 15 x 4 mm (the
    100 to 150 mAh class; the exact cell is not chosen, and the envelope
    is what the chosen one has to fit);
  - the board on the ledges and on two posts at its left end (the cell
    starts 2,5 mm further right, so the posts stand beside its end);
  - the magnetic connector through a window in the lid, its face in a
    0,7 mm well where the cable's magnetic head lands, with a flat gasket
    ring round the well; a 2,5 mm light hole over the LED, to be filled
    with clear resin; the bridge's wires up from the arm through a slot in
    the floor straight under the board's five plated holes;
  - the cavity potted to the lid's underside, the lid glued on its lip.

Run:  python hardware_powermeter/pod/make_pod.py (after the board's chain:
      it reads cad/pmeter.kicad_pcb and the GLB that dry_run_pcb.py exports)
Out:  here, pmeter-pod.pdf (3 pages) and the STL files pod-concha.stl and
      pod-tampa.stl (triangle soups of overlapping boxes, for a slicer, not
      a CAD solid); in docs/img/hardware/, pod-3d-aberta.png,
      pod-3d-fechada.png, pod-3d-explodida.png, pod-3d-tampa-por-dentro.png
      (the lid from below, where the seal, the clamping fingers and the
      window's rim are) and pod-3d-celula-no-berco.png.
"""

from __future__ import annotations

import math
import pathlib
import struct
import sys

import fitz
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent          # hardware_powermeter/pod
CAD = HERE.parent / "cad"                                # the board's sources
IMG = HERE.parents[1] / "docs" / "img" / "hardware"      # the rendered views
sys.path.insert(0, str(CAD))

import dry_run_pcb as DR      # noqa: E402
import footprints as FPS      # noqa: E402
import make_3d as M3          # noqa: E402
import make_dxf as MD         # noqa: E402
import make_pcb as MP         # noqa: E402

# ----------------------------------------------------------------- the pod
# The wall is 2,0 and not 1,2 since 2026-09-28, and the reason is the
# O-ring: the seal is a groove of 1,05 mm cut in the top face of the wall
# (JUNTA_SULCO_L below), and 1,2 mm of wall cannot hold it. It is 2,0
# EVERYWHERE and not only at the rim: a stepped wall would give back
# 1,6 mm at the bottom, and the bottom is exactly where the pod is BONDED
# to the crank arm, so the step would cost bonding area and stiffness to
# buy a millimetre where it does not show.
PAREDE, FUNDO, TAMPA = 2.0, 1.2, 1.0
# O `FUNDO` subiu de 1,0 para 1,2 em 2026-10-01 porque o RELEVO passou a ser
# CAVADO e nao acrescentado (ver `RELEVO`): fora da base de colagem a face de
# baixo esta em z = RELEVO, logo a espessura do piso ali e FUNDO - RELEVO. Com
# FUNDO = 1,0 e RELEVO = 0,5 o piso daria 0,5 mm; com 1,2 da 0,7 fora da base
# e 1,2 sobre ela.
R_P = 3.0
FOLGA_PLACA = 0.5             # board to wall, right end and both long sides
CANAL_FIO = 2.5               # left end: the cell's leads rise here to the JST
# A largura minima de assento da placa em cada borda. `RESSALTO - FOLGA_PLACA`
# dava 0,100 mm, e a folga radial do pino do parafuso e 0,100 tambem: a
# translacao que o pino permite consumia o assento inteiro de um lado
# (revisao de 2026-10-01).
ASSENTO_MIN = 0.5
# O ressalto e a FOLGA da placa mais o assento minimo: ate 2026-10-01 ele era
# 0,6 contra uma folga de 0,5 e sobravam 0,100 mm de apoio por borda, a mesma
# medida da folga radial do pino do parafuso - a translacao que o pino permite
# consumia o assento inteiro de um lado (`PD30`).
RESSALTO = FOLGA_PLACA + ASSENTO_MIN
# Quanto da BEIRADA de um ressalto pode ficar em balanco sobre o rasgo. O
# ressalto nasce no piso e e colado na parede; um balanco pequeno da borda
# interna dele sobre o rasgo nao cai, e exigir zero virou falsa falha quando
# o ressalto cresceu para dar assento a placa (`PD7`, 2026-10-01).
RESSALTO_BALANCO = 0.4
PLACA_W, PLACA_H, PLACA_ESP = MD.W, MD.H, MD.THICKNESS
# the envelope reserved for the cell. It shrank on 2026-09-27 with the
# owner's 5 kOhm decision: the meter draws 1,5 mA pedalling instead of 3,9,
# so 50 hours ask for about 75 mAh and a 100 mAh cell is enough. A 100 mAh
# pouch is 2,5 mm thick where a 150 mAh one is 4,0, and those 1,5 mm are
# what takes the pod's height from 10,0 to 8,5, the target of docs/02. The
# chosen cell has to fit this envelope, not the other way round.
# The cell is 13 mm wide, not 15, and it is NOT centred: it is pushed to
# the wall away from the bridge's wire slot. Measured on 2026-09-28 -
# when the board went from 60 to 48 mm the slot came with J301 and
# landed under the cell, undoing what 2026-09-27 had already settled
# ("a celula tem de acabar antes do rasgo", which is why it went from
# 25 to 23 mm then). In x there is no way out: between the cell's end
# at 25,5 and the module at 31 there are 5,5 mm and the connector needs
# 5,9 even in two rows. So the cell gives 2 mm of WIDTH - 13 % of its
# volume, 862 to 748 mm3 - and the slot passes beside it. The owner
# chose this over moving J301 away from the converter, which is what
# keeps the 2 mV analogue path short.
# 11,0 of width and not 13,0 since the board went to 14 mm with the
# smaller radio module (2026-09-28). PD15 is what caught it: between
# the ledges there are 14 + 1,0 - 2 x 0,6 = 13,8 mm, and a cradle rib
# of 0,8 with 0,25 of play on the side away from the wall needs 1,05 of
# them, so a 13 mm cell left 0,75 and the rib had nowhere to stand. The
# cell gives the width and keeps its length: 23 x 11 x 2,5 is 633 mm3,
# against 748 on the 16 mm board and 862 before the wire slot moved.
# 4,0 mm of thickness and not 2,5, decided by the owner on 2026-09-28 after
# the capacity was recomputed and the old premise turned out to be wrong.
# docs/02 carried "a 100 mAh cell is 2,5 mm thick", and no cell of 23 x 11 mm
# is 100 mAh at any thickness: calibrating the volumetric capacity of small
# LiPo pouches on four standard sizes (401230, 301020, 501225, 401020) gives
# 0,077 mAh/mm3, so this footprint holds
#
#     2,5 mm -> 632 mm3 -> ~49 mAh -> 32 h at 1,5 mA   (pod 8,5)
#     4,0 mm -> 1012 mm3 -> ~78 mAh -> 52 h            (pod 10,0)
#
# and the requirement is 50 h. The 8,5 mm pod only ever closed because the
# capacity was wrong. The class reference runs to 13 mm of height, so 10,0 is
# still inside it.
# 23 x 11 x 4,0, and each of the three is a measured limit rather than a
# choice:
#
#   4,0 of thickness   is what the 50 h need. docs/02 carried "a 100 mAh cell
#                      is 2,5 mm thick", and no cell of this footprint is
#                      100 mAh at any thickness: calibrating small LiPo
#                      pouches on four standard sizes (401230, 301020,
#                      501225, 401020) gives 0,077 mAh/mm3, so 2,5 mm held
#                      ~49 mAh and 32 h. The owner chose 4,0 and a 10,0 mm
#                      pod over a thinner pod that misses the requirement.
#   11 of width        is the board: 14 mm, less the ledges, less the room a
#                      cradle rib needs on the side away from the wall.
#   23 of LENGTH       is the back FACE, not the slot. At 24 and 25 mm the
#                      cell's shadow reaches past x 28 and the ferrite and
#                      the rail-side reservoir lose their place on the back -
#                      measured on 2026-09-28, one length after another.
#
# 1012 mm3 -> ~78 mAh -> 52 h at 1,5 mA, which TIES the class reference and
# does not beat it. Beating it means the 10 kOhm bridge (the bridge is 40 %
# of the current), and the owner chose to keep the 5 kOhm part.
# A CELULA AO LADO DA PLACA, decidida pelo dono em 2026-09-30 para o
# aparelho ficar mais baixo. Ela deixa de custar ALTURA e passa a custar
# COMPRIMENTO, e por isso muda de forma: antes era comprida e estreita
# porque tinha de caber sob a placa entre os ressaltos; agora e' o contrario
# - quanto mais larga e mais grossa, menos comprimento ela toma.
#
#   largura 15,0   e o que sobra entre as paredes (21,0 de pod menos 2 x 2,0
#                  de parede da' 17,0 uteis) com 1,0 de folga para o berco.
#   espessura 5,0  nao custa nada: a pilha da placa manda 5,0 no mesmo
#                  espaco (1,5 sob a placa + 0,8 dela + 2,7 de teto), entao
#                  ate 5,0 a celula e' de graca em altura.
#   comprimento 14,0  e o que sobra: 15 x 14 x 5,0 = 1050 mm3, que a 0,077
#                  mAh/mm3 da' ~81 mAh e ~54 h a 1,5 mA. O envelope de antes
#                  (23 x 11 x 4,0 = 1012 mm3) dava 78 mAh e 52 h, entao a
#                  troca nao perde carga - ganha um pouco - e custa 14 mm de
#                  pod em vez de 4 mm de altura.
#
# O `CELULA_VAO` deixa de existir como folga entre a celula e a placa: elas
# nao se sobrepoem mais. Ele vira a folga entre a celula e a PONTA da placa.
# 15 de comprimento e 14 de largura, e nao o contrario: entre as paredes
# sobram 17,0 mm, e uma celula de 15 deixava 1,0 mm para os dois lados -
# sem espaco para a nervura que a segura, que foi o que a `PD15` acusou na
# primeira execucao. Com 14 sobram 1,5 de cada lado, que e nervura de 0,8
# mais 0,7 de folga. O volume nao muda: 15 x 14 x 5,0 = 1050 mm3.
CELULA_W, CELULA_H, CELULA_ESP, CELULA_VAO = 15.0, 14.0, 5.0, 0.5
# A RESERVA DE INCHACO, em z. Uma bolsa de litio engorda com ciclo e com
# temperatura, e 8 a 10 % da espessura e a folga mecanica que os fabricantes
# pedem. Ate 2026-10-01 o teto da cavidade era `max(PLACA_Z1 + TETO,
# CELULA_Z1)`: a celula empatava com o teto em 0,000 mm de ar, com igualdade
# exata, enquanto a `PD2` cobrava 0,30 de folga de TODA peca rigida da placa.
# A unica peca do pod que cresce era justamente a que nao tinha reserva. O
# `CELULA_VAO` nao servia: ele e a folga LATERAL, em x, contra o canal.
CELULA_INCHACO = 0.10 * CELULA_ESP
# The cell's own leads: a pouch of this size ships with a two-wire tail, and
# it is what rises through the channel at the left end into J102. Drawn
# because a battery without its wires is not the part anyone buys.
CELULA_FIO_D = 0.9            # the lead, insulation included
CELULA_FIO_PASSO = 2.5        # between the two leads, as J102's holes are
# The clear width two leads side by side need: centres CELULA_FIO_PASSO apart
# plus half a diameter outside each. Until 2026-10-01 neither of the two
# constants above was used by any geometry and the cradle's ribs ran from the
# floor to the ceiling across the bay's only exit: the leads had 0,000 mm to
# come out of (flood fill, revision of 2026-10-01). This is the width of the
# notch cut through the ribs.
CELULA_FIO_VAO = CELULA_FIO_PASSO + CELULA_FIO_D
# From the board's left end, and the number is set by the SLOT: the
# bridge's five holes are at the middle of the board and the floor is cut
# under them (pod x 30,45 to 40,95, measured on 2026-09-27), so the cell
# has to end before that cut with room for the rib that holds it. Left of
# the slot there are 28,65 mm between the ledges; the two posts take the
# first 6,2, which leaves 23 for the cell and 0,6 for the rib. That is why
# the envelope is 23 mm long and not the 25 this started with, and it is
# also why the cell cannot simply be made longer to hold more charge.
TETO = MD.TETO_TAMPA          # the ceiling over the front parts (2,7)
JANELA_FOLGA = 0.15           # the lid's window round the connector's barrel

# ------------------------------------------- a vedacao da janela, refeita
# `docs/02-hardware.md` pede, literalmente, "IPX7: pod envasado, JUNTA NA FACE
# DO CONECTOR". Ate 2026-10-01 o desenho fazia outra coisa: uma junta plana de
# 1,5 mm de largura num anel em volta da janela, desenhada em z 6,70 a 7,20
# sobre uma chapa macica de 6,00 a 7,00 - o rebaixo de 0,30 que a regra
# anunciava nao existia no solido (o STL da tampa nao tem plano nenhum em
# 6,70), o labio ficava 0,40 ACIMA do topo dela e, em planta, a borda interna
# da junta era a propria janela, 0,55 mm por FORA do corpo do conector nos
# quatro lados: ela nunca tocava a peca. Sobrava um anel aberto de 16,61 mm2
# da face do conector ate a cavidade, fechado so pelo menisco do envase. E o
# "dreno" ficava 0,50 mm ACIMA do fundo do poco, com queda zero em 2,65 mm:
# a agua do poco so tinha para onde ir para DENTRO.
#
# O que ficou. A janela passa a ser o BARRILETE do conector mais folga, e a
# junta e um anel plano apoiado no OMBRO da peca, comprimido por um ressalto
# na face de baixo da tampa. O labio e o dreno sairam: um labio fechado em
# volta de uma face de contato que fica 0,7 mm abaixo do topo e' uma represa,
# e um canal de dreno na tampa de 1,0 mm teria de passar abaixo da face de
# baixo dela, ou seja, virar um furo para dentro da cavidade.
#
# As duas medidas do OMBRO sao REQUISITO DE COMPRA, como a altura do modulo
# de radio: nenhum conector esta escolhido ("o conector magnetico e generico"
# em todo o repositorio), e a `PD24` cobra as duas da peca que chegar.
CONECTOR_OMBRO_Z = 2.0        # altura do ombro plano acima da placa
CONECTOR_OMBRO_L = 0.8        # largura desse ombro em volta do barrilete
JUNTA_ESP = 0.70              # espessura da junta plana, livre
JUNTA_APERTO = 0.20           # quanto o ressalto da tampa a comprime: 28,6 %
# Quanto a face do conector pode ficar abaixo do topo da tampa. E o curso que
# o pino do cabo magnetico tem de vencer; 0,8 e' o curso tipico de um pino
# pogo, A CONFERIR no cabo comprado - se o cabo tiver menos, ou a tampa afina
# sobre a porta ou o conector tem de ser mais alto.
POCO_MAX = 0.80

# ---------------------------------------------------------- as vedacoes
# O aparelho fica na face interna do braco, a centimetros do chao: leva
# chuva, spray de estrada e mangueira. Toda abertura do pod e um caminho de
# agua ate a placa, e cada uma tem de ter a sua vedacao. A `PD19` enumera as
# aberturas e cobra estas constantes uma a uma.
#
# O furo de luz do LED: cheio de resina TRANSPARENTE ate a face de fora.
# Ele e' um furo passante de 2,5 mm na tampa, sobre o LED, e sem enchimento
# e' o maior buraco do pod.
LED_RESINA = True
# A vedacao do furo de cada parafuso. Ate 2026-10-01 era um tampao de resina
# de 0,8 mm sobre uma cabeca escareada, e a conta nunca tinha sido feita: uma
# cabeca escareada M1,6 tem 0,96 de altura, 0,96 + 0,80 = 1,76 contra os 1,00
# de tampa - e o escareado de 3,20 nao entra num furo de 1,90. Engrossar a
# tampa ate caber a pilha custaria altura em todo o pod por causa de dois
# pontos, e um ressalto na face de baixo bateria no colar do pescoco.
#
# O que fecha e uma ANILHA VEDANTE sob uma cabeca cilindrica: peca de
# prateleira, veda por compressao do elastomero contra a face da tampa, e a
# cabeca fica SALIENTE em vez de escareada. Custa altura nos dois pontos, e a
# `PD10` mede a caixa delimitadora incluindo-a.
PARAF_CABECA_K = 1.10         # altura da cabeca cilindrica M1,6 (DIN 7985)
PARAF_ANILHA_D = 4.00         # diametro externo da anilha vedante
PARAF_ANILHA_ESP = 0.50       # espessura dela, livre
PARAF_ANILHA_APERTO = 0.15    # quanto a cabeca a comprime: 30 %
# O colar em volta do rasgo dos fios da ponte, no FUNDO. O rasgo e' por onde
# os fios do extensometro sobem do braco, e e' a unica abertura do lado de
# baixo. O colar sobe 1,5 mm dentro da cavidade: ele segura o envase (que
# senao escorreria por ali antes de curar) e alonga o caminho da agua. Por
# fora, o proprio adesivo que cola o pod ao braco fecha o resto.
# ---------------------------------------- o extensometro e os fios dele
# O S5229 fica colado no braco DEBAIXO do pod, e os cinco fios dele correm na
# face do braco ate o rasgo. Na linha de cola de `COLA` (0,5 mm) nao cabe nem o
# fio (0,32 desenhado, cerca de 0,5 com isolacao) nem a matriz (0,10): ate
# 2026-10-01 o maior percurso media 44,83 mm SOB FUNDO COLADO, 64 % da linha de
# cola tomada por cinco cordas, e o rasgo - a unica abertura inferior - ficava
# inteiro dentro da area colada. Agora o pod abre um bolso sobre a matriz e uma
# canaleta sobre o feixe, as duas com `RELEVO` de profundidade (a face de baixo
# ali fica no mesmo nivel de fora da base de colagem), e a area colada e o que
# sobra. As cotas da matriz sao do databook 2622-EN rev. 12-Aug-2019, p. 58.
GAUGE_X = 14.0                # LUGAR RESERVADO: a medir no pedivela do dono
GAUGE_DESLOC_Y = 4.5          # fora da linha neutra da face (docs/06)
GAUGE_W, GAUGE_H = 4.0, 3.7   # a matriz, o que e colado
GAUGE_ALT = 0.10              # folha mais carrier
GAUGE_FOLGA = 0.4             # margem do bolso em volta da matriz
FIO_PONTE_D = 0.5             # 30 AWG COM isolacao (o condutor nu e 0,255)
FIO_PONTE_N = 5
FIO_PONTE_PASSO = FIO_PONTE_D + 0.2
CANALETA_L = FIO_PONTE_N * FIO_PONTE_PASSO
RASGO_COLAR_L = 0.8
RASGO_COLAR_ALT = 1.5
# O ar entre o topo de cada barra do colar e o que passa sobre ela (o verso da
# placa, o corpo de uma peca do verso, uma ilha). Sem ele o colar virava apoio
# da placa, e apoio em cima de dois 0402 (revisao de 2026-10-01).
COLAR_FOLGA = 0.1
# A espessura minima de cola que tem de sobrar sob o pod depois de passar o
# que passa por ali (o fio do extensometro, a matriz): sem ela o pod se apoia
# em cinco cordas em vez de na pelicula.
COLA_MIN = 0.15
# Material minimo entre duas aberturas da tampa impressa.
TAMPA_MIN_PAREDE = 0.6
# Largura minima de ombro que a junta da porta precisa para vedar.
JUNTA_MIN_L = 0.5
LED_FURO = 2.5
# O furo quadrado que a chapa recebe e um pouco MAIOR que o circulo, e o anel
# entre os dois devolve o redondo. Se o quadrado tivesse o lado igual ao
# diametro, o circulo inscrito encostaria nele nos quatro meios de lado e o
# anel teria largura zero ali: quatro quads degenerados, e a `PD26` pegou isso
# na primeira execucao (1 de 85 primitivas da tampa nao fechava).
LED_FURO_FOLGA = 0.1
# The floor slot round the bridge's holes. 0,4 and not 0,5: at 0,5 the cut
# ran 0,05 mm under the bottom ledge, which is what the board rests on
# (PD7, measured 2026-09-27). 0,4 still leaves 0,35 mm of clearance round a
# 0,9 mm hole.
RASGO_FOLGA = 0.4
PILAR_D = 2.0
PILAR_FOLGA = 0.15          # a post must not touch a pad: the solder sits proud
NERVURA = 0.6
COLA = 0.5                    # glue between the arm and the floor (not drawn)
# A margem de colagem por lado: a base nao pode terminar exatamente onde a
# face plana termina. Ate 2026-10-01 a `PD17` comparava `BASE_COLA <= util`
# com `BASE_COLA = BRACO_LARG - 2 * RAIO_CONC = util`: uma tautologia que nao
# podia reprovar.
COLA_MARGEM = 0.5

# ------------------------------------------------- the crank arm (2026-09-28)
# Nobody has measured the owner's crank, and waiting for that measurement was
# holding the whole design, so these are the numbers of the CLASS - Shimano
# 105 FC-R7000 and Ultegra FC-R8000, hollow-forged aluminium road cranks -
# and they are treated as a REQUIREMENT the pod has to satisfy, not as a
# measurement of his part. The rule that uses them (PD17) fails if the pod
# does not fit, which is the point: a reserved number that nothing checks is
# just a comment.
#
# What each one is, and how conservative it is:
#
#   BRACO_LARG   the inner face of the arm, across, at the middle where the
#                pod is bonded. A 105/Ultegra arm tapers from the spindle
#                boss to the pedal boss; the narrow END of that taper is
#                what matters and it is about 20 mm. Taking 20,0 is the
#                worst case, not the average.
#   BRACO_ESP    the arm's own thickness there, about 13 mm.
#   QUADRO       how much room there is between the arm's inner face and the
#                chainstay on a road frame. 10 mm is the tight end of what
#                road bikes give; some give 14 or more.
#   RAIO_CONC    the fillet where the inner face meets the sides, about 2,5:
#                the pod's floor cannot use the last RAIO_CONC of the face.
BRACO_LARG = 20.0
# And what follows from it: the pod is 19,0 wide and only BRACO_LARG minus
# two fillets - 15,0 - of the arm's face is FLAT. A pod bonded across its
# whole underside would sit on the fillet radius on both sides, which is the
# worst thing you can do to a bond line: the adhesive is thick at the edges,
# thin in the middle, and the joint peels from the outside in. PD17 caught
# it on 2026-09-28.
#
# So the underside is not flat either. It carries a BONDING LAND as wide as
# the flat part of the face, and outside that land the floor is relieved by
# RELEVO so it clears the fillet with air. The pod stays 19,0 mm wide - the
# board needs that - and the glue only ever touches flat metal.
# A base de colagem e a face PLANA do braco menos uma margem por lado: ate
# 2026-10-01 ela era a face plana inteira, e a `PD17` comparava
# `BASE_COLA <= util` com os dois iguais - tautologia que nao reprova.
BASE_COLA = BRACO_LARG - 2.0 * 2.5 - 2.0 * COLA_MARGEM   # RAIO_CONC = 2,5
# Quanto a face de baixo SOBE fora da base de colagem. Ate 2026-10-01 isto
# eram duas caixas ACRESCENTADAS de z 0 a 1,0 nas duas tiras externas - e a
# parede e o piso ja ocupavam z 0 a 1,0 ali, entao as caixas nao levantavam
# nada: medido no STL, 100 % de cada tira (222,60 mm2) era face macica em
# z = 0,000, e suprimir as duas caixas mudava a area em z = 0 de 445,20 para
# 433,55 mm2. O pod colava pelos 21,0 mm sobre uma face plana de 15,0,
# apoiando 3,0 mm por lado na concordancia - exatamente a falha que o
# comentario acima diz que o relevo evita. A `Malha` nao subtrai; hoje a
# concha nasce em z = RELEVO e a base de colagem e um ressalto desenhado
# dentro dela (`menos_retangulos` tira o rasgo).
RELEVO = 0.5
QUADRO = 10.0
# A espessura do corpo do braco. Fica AQUI e nao no `make_conjunto` porque e
# uma medida do pedivela de que o pod depende - a `PD6` mede a antena contra
# esta chapa de aluminio -, e porque ate 2026-10-01 havia duas: um
# `BRACO_ESP = 14,0` usado pelo desenho do conjunto e um `BRACO_ESP_CLASSE =
# 13,0` que nao era usado por nada. LUGAR RESERVADO, a medir no pedivela.
BRACO_ESP = 14.0
RAIO_CONC = 2.5

# And the module's height, which the advert does not give either. The same
# treatment: 2,40 mm is the ME54BS13's, and it is written here as the
# MAXIMUM this design accepts, because the lid's ceiling is built on it
# (make_dxf.TETO_TAMPA = 2,40 + 0,3 of air). A module with a metal can over
# a 0,8 mm PCB is 1,8 to 2,2 mm in this class, so 2,40 has margin - but the
# part that gets bought has to be measured against it, and PD2 is what
# measures it (09-modulo-de-radio.md).
MODULO_ALT_MAX = 2.40
# 10,0 of height and not 8,5. The 8,5 came from a capacity that was wrong
# (see CELULA_ESP): no cell of 23 x 11 mm holds 100 mAh at 2,5 mm thick,
# and the one that does fit 2,5 gives 32 h against a requirement of 50.
# The owner chose the runtime on 2026-09-28. The class reference runs to
# 13 mm of height, so 10,0 is still inside it.
# `docs/02-hardware.md`, Requisitos: "38 x 20 x 10 mm, nas tres medidas, com
# prioridade para o comprimento", com a medida por fotogrametria da classe
# (37 a 39 mm) como fonte, e a propria linha dizendo "nao nos 60 que este
# projeto perseguia". Ate 2026-10-01 esta constante era 60,0 e citava docs/02
# como fonte: a `PD10` media contra um alvo que o documento ja tinha trocado,
# e imprimia "74,2 contra 60" onde o excesso real e 36,5 mm, 96 % do alvo.
ALVO = (38.0, 20.0, 10.0)
MASSA_ALVO = 20.0             # docs/02: module with cell, in grams
# densities, g/cm3, for the mass ESTIMATE (page 3 says they are estimates):
# printed resin or nylon, silicone potting, FR-4, a LiPo pouch (3,5 g for a
# 401530), and the parts as a solid at the density of a small IC package
DENS_POD, DENS_ENVASE, DENS_FR4, DENS_CELULA, DENS_PECAS = 1.15, 1.0, 1.85, 2.0, 2.5

# ------------------------------------------------------- sealing (2026-09-28)
# Until now the pod was "sealed" by the potting alone, and the only gasket in
# the drawing was the flat ring round the connector's window. That is not
# IPX7 on a part that lives in the rain, gets washed with a hose and has to
# be opened for service: potting seals what it touches and says nothing about
# the lid's joint.
#
# The seal is AXIAL, in a groove cut in the top face of the wall, and NOT
# radial in the lid's lip. Measured trade on 2026-09-28: a radial groove
# needs a lip about 1,6 mm thick where today's is 0,4, and the lip drops into
# the 0,5 mm the board leaves to the wall - so the cavity, and the whole pod,
# would grow 2,4 mm in width. The axial groove grows only the WALL, and only
# at the rim, which is the end away from the crank arm: 1,6 mm of width
# against 2,4, and it lands where there is clearance to the frame instead of
# against the arm.
#
# The cord is 0,80 mm. The groove is 1,05 wide and 0,58 deep, which squeezes
# it to 0,58 of its 0,80 - 27,5 % of compression, inside the 20 to 30 % a
# static face seal asks for. The wall at the rim is 2,0 mm: 1,05 of groove
# plus 0,45 of material outside and 0,50 inside.
JUNTA_CORDAO = 0.80           # the O-ring's cord diameter
JUNTA_SULCO_L = 1.05          # groove width
JUNTA_SULCO_P = 0.58          # groove depth: 27,5 % of compression
PAREDE_VEDA = 2.00            # the wall the groove needs (see PAREDE)
if PAREDE < PAREDE_VEDA:
    raise SystemExit(f"a parede e {PAREDE} e o sulco do anel O pede "
                     f"{PAREDE_VEDA}: sem isso nao ha vedacao por anel O")

# --------------------------------------------- closing screws (2026-09-28)
# The lid is bonded and the pod is potted, and a bonded lid still has to be
# CLAMPED while the adhesive cures and while the O-ring is compressed, or the
# joint opens in the middle. Two M1,6 self-tapping screws, one at each end,
# into bosses that rise from the floor.
#
# What they cost is length, and it is the honest number: a boss is 3,4 mm
# across and the board takes the middle, so each one needs its own room
# outside the board. The left end already has the cell's 2,5 mm wire channel;
# the right end has 0,5 mm of play and grows.
PARAF_D = 1.60                # M1,6 self-tapping
PARAF_BOSS_D = 3.40           # boss outside diameter
PARAF_FURO_D = 1.35           # the pilot hole a self-tapping M1,6 wants
PARAF_CABECA_D = 3.20         # diametro da cabeca cilindrica

# ------------------------------------------------- retention (2026-09-28)
# The cell used to be held by "the potting", which is not a design. Four ribs
# make a cradle round its envelope so it cannot walk under vibration before
# the potting cures, and the board is CLAMPED: the lid's lip comes down on
# its top face through a compressible pad instead of stopping in the air. A
# measurement chain that starts at a strain gauge cannot have its board
# moving relative to the arm.
BERCO_LARG = 0.8              # the cradle's ribs round the cell
BERCO_FOLGA = 0.25            # play round the cell so it drops in
APERTO_PAD = 0.30             # the pad between the lip and the board

# ---------------------------------------- the connector's well (2026-09-28)
# The window is the only hole in the pod, so it is where the water goes. A
# lip round it on the OUTSIDE keeps a standing puddle off the contacts, and a
# channel takes what gets past it out to the edge instead of leaving it in
# the well. Neither exists in a potted pod by accident.

# ------------------------------------------------ where everything sits
# The wall is PAREDE_VEDA everywhere, not only at the sealing rim. A stepped
# wall would give back 1,6 mm at the bottom, and the bottom is exactly where
# the pod is BONDED to the crank arm: a wider base is more bonding area and a
# stiffer box, so the step would cost strength to buy a millimetre where it
# does not show. The thin PAREDE stays as the number the old drawings used.
PAREDE_EFET = PAREDE   # kept as a name; the wall IS the sealing wall

# What the closing screws cost, and how most of it was given back.
#
# The first arrangement put a boss outside the board at EACH end, which cost
# 5,4 mm of pod length - and the owner was right that the pod had not got
# smaller. The right-hand screw now goes THROUGH the board: a boss of
# PARAF_BOSS_D rises from the floor to the underside, a narrower neck of
# PARAF_PESCOCO_D passes through a hole in the board, and the screw comes
# down from the lid into it. That costs nothing in length.
#
# It can only be done on ONE side. A post that pierces the board needs floor
# under it with no cell, and the cell runs from the board's x 2,5 to 25,5;
# past it there are 8,5 mm before the module starts. The left end has no
# such window - the cell is there - so that screw keeps its boss, in the
# cell's own wire channel, and only the difference is paid.
PARAF_VAO = 0.4
PARAF_PESCOCO_D = 2.00        # the neck that passes through the board
PARAF_FURO_PLACA = 2.20       # the hole the board has to carry for it
_boss = PARAF_BOSS_D + 2.0 * PARAF_VAO
PARAF_EXTRA_ESQ = max(0.0, _boss - CANAL_FIO)
PARAF_EXTRA_DIR = 0.0

# O `BERCO_FOLGA` entra aqui porque a celula larga da parede: ate 2026-10-01
# `CELULA_X0` era a propria face interna da parede e a bolsa encostava nela com
# 0,000 mm, com a folga aplicada so nos outros tres lados (a nervura daquele
# lado caia por isso, e a `PD15` chamava a parede de retencao).
W_P = (PAREDE_EFET + BERCO_FOLGA + CELULA_W + CELULA_VAO + CANAL_FIO
       + PARAF_EXTRA_ESQ
       + PLACA_W + FOLGA_PLACA + PARAF_EXTRA_DIR + PAREDE_EFET)
H_P = PLACA_H + 2.0 * (FOLGA_PLACA + PAREDE_EFET)
PLACA_X0 = (PAREDE_EFET + BERCO_FOLGA + CELULA_W + CELULA_VAO + CANAL_FIO
           + PARAF_EXTRA_ESQ)
PLACA_Y0 = PAREDE_EFET + FOLGA_PLACA
CELULA_X0 = PAREDE_EFET + BERCO_FOLGA
CELULA_Y0 = (H_P - CELULA_H) / 2.0     # centrada entre as paredes

# The two screws, on the centre line. The left one sits in the wire
# channel; the right one is THROUGH the board, in the window between the
# cell's end and the module - and its x is derived from the cell, not
# written down, so it follows if either of them moves.
# Entre a CELULA e a placa, e nao na ponta esquerda: desde 2026-09-30 a
# ponta esquerda e a celula, e o ressalto do parafuso invadia a bolsa
# (PD14 pegou isso na primeira execucao). O vao entre as duas e' onde os
# fios da celula sobem para o J102, e o parafuso divide esse vao com eles.
PARAF_X_ESQ = (CELULA_X0 + CELULA_W + CELULA_VAO
               + (CANAL_FIO + PARAF_EXTRA_ESQ) / 2.0)
# taken from the BOARD's hole and not computed again here: the two have to
# be the same point, and deriving it twice is how they drift apart
PARAF_X_DIR = PLACA_X0 + MD.FUROS_DOC[0][0]
PARAF_XY = ((PARAF_X_ESQ, H_P / 2.0), (PARAF_X_DIR, PLACA_Y0 + MD.FUROS_DOC[0][1]))
# which of them pierces the board
PARAF_NA_PLACA = (False, True)
# A BAIA e CAVADA no piso: o piso dela tem a mesma espessura que o piso fora
# da base de colagem (FUNDO - RELEVO), e nao a espessura cheia. Sem isso a
# reserva de inchaco da celula levantava o TETO DA CAVIDADE inteiro meio
# milimetro - e o teto e o que fixa a altura do pod e a profundidade do poco do
# conector, que tem o curso do pino do cabo como limite. Cavando a baia, a
# celula com reserva (5,0 + 0,5) empata com a pilha da placa (0,8 + 2,7) e o
# pod nao cresce. Sob a baia a face de baixo esta em z = 0: ela cai dentro da
# base de colagem.
BAIA_PISO = FUNDO - RELEVO
CELULA_Z0 = BAIA_PISO
CELULA_Z1 = CELULA_Z0 + CELULA_ESP
# A placa nao sobe mais sobre a celula: ela desce ate o ar que as pecas do
# VERSO pedem, que e o teto do verso do `make_dxf` (1,5 mm desde que os 43
# passivos foram para la). Era esta soma que fazia o pod ter 10 mm.
SOB_A_PLACA = MD.TETO_VERSO
PLACA_Z0 = FUNDO + SOB_A_PLACA
PLACA_Z1 = PLACA_Z0 + PLACA_ESP
# O teto da cavidade e o mais alto dos dois: a pilha da placa ou a celula.
TAMPA_Z0 = max(PLACA_Z1 + TETO, CELULA_Z1 + CELULA_INCHACO)
T_P = TAMPA_Z0 + TAMPA
# O NIVEL DO ENVASE. Ate 2026-10-01 nao havia numero nenhum: a resina enchia
# "ate a face de baixo da tampa" em todo texto, o que punha o menisco dela
# rasante a boca dos dois furos cegos dos parafusos - e um M1,6
# autoatarraxante nao atarraxa em resina curada - e fazia dela a unica coisa
# que fechava o anel em volta do conector. Agora o envase para abaixo do teto,
# e a `PD28` cobra a margem da boca de todo furo cego contra este nivel.
ENVASE_FOLGA = 0.4
ENVASE_NIVEL = TAMPA_Z0 - ENVASE_FOLGA
# A celula ocupa a ponta ESQUERDA do pod, antes da placa. A esquerda e nao a
# direita porque a antena ceramica do modulo esta na ponta direita da placa
# e uma bolsa de LiPo e uma folha de metal: `PD6` mede essa distancia.
# The lid's lip, inside the walls. 0,4 wide and 0,1 of play, not 0,8 and
# 0,15: the lip drops into the same 0,5 mm the board leaves to the wall,
# and at 0,95 it came down on the module's 2,4 mm body (PD12).
ABA_ALT, ABA_LARG, ABA_FOLGA = 1.0, 0.4, 0.1

COR_POD = (0.22, 0.23, 0.26)
COR_TAMPA = (0.27, 0.28, 0.31)
COR_CELULA = (0.30, 0.31, 0.34)
COR_JUNTA = (0.55, 0.30, 0.28)
COR_LED = (0.80, 0.80, 0.55)


# ------------------------------------------------------------ geometry
def contorno_arredondado(x0, y0, x1, y1, r, n=6):
    """A rounded rectangle as a closed polyline (y down), n points per corner."""
    pts = []
    cantos = ((x1 - r, y0 + r, -90.0), (x1 - r, y1 - r, 0.0),
              (x0 + r, y1 - r, 90.0), (x0 + r, y0 + r, 180.0))
    for cx, cy, a0 in cantos:
        for k in range(n + 1):
            a = math.radians(a0 + 90.0 * k / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def menos_retangulos(r, buracos, minimo: float = 0.3) -> list:
    """The rectangle R cut into the pieces that no hole covers.

    `Malha` has no boolean subtraction - it is a triangle soup - and the pod
    paid for that twice: the relief ADDED two boxes where it meant to carve
    away, and the lid's lip was drawn as a closed ring straight through the
    cell and three ribs. Everything the pod carves in plan is rectangular, so
    one honest rectangle subtraction covers all of it.

    Cuts in BOTH axes, keeps only pieces wider and taller than `minimo` (a
    sliver below the process resolution is not a feature), and is exact: the
    union of the pieces is R minus the holes, with no overlap.
    """
    pedacos = [tuple(r)]
    for h in buracos:
        if h is None:
            continue
        saida = []
        for a, b, c, d in pedacos:
            if c <= h[0] or h[2] <= a or d <= h[1] or h[3] <= b:
                saida.append((a, b, c, d))
                continue
            if a < h[0]:
                saida.append((a, b, min(c, h[0]), d))
            if h[2] < c:
                saida.append((max(a, h[2]), b, c, d))
            mx0, mx1 = max(a, h[0]), min(c, h[2])
            if mx1 > mx0:
                if b < h[1]:
                    saida.append((mx0, b, mx1, min(d, h[1])))
                if h[3] < d:
                    saida.append((mx0, max(b, h[3]), mx1, d))
        pedacos = saida
    return [p for p in pedacos
            if p[2] - p[0] > minimo and p[3] - p[1] > minimo]


def poligono_regular(cx, cy, r, n=12):
    return [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n))
            for k in range(n)]


def quadrado_amostrado(cx, cy, lado, n=16):
    """Um quadrado amostrado nos MESMOS angulos do `poligono_regular`.

    Serve para fazer um anel entre um quadrado e um circulo e assim CAVAR um
    furo redondo numa chapa que `placa_com_furos` so sabe furar em retangulo.
    Com n = 16 os quatro cantos caem exatos (45 graus e multiplo de 22,5).
    """
    pts = []
    h = lado / 2.0
    for k in range(n):
        a = 2 * math.pi * k / n
        c, s = math.cos(a), math.sin(a)
        m = max(abs(c), abs(s))
        pts.append((cx + h * c / m, cy + h * s / m))
    return pts


def triangular(pts):
    """Ear clipping of a simple polygon (any winding), as index triples."""
    n = len(pts)
    if n < 3:
        return []
    area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
               for i in range(n))
    idx = list(range(n)) if area > 0 else list(range(n))[::-1]

    def convexo(a, b, c):
        return ((pts[b][0] - pts[a][0]) * (pts[c][1] - pts[a][1])
                - (pts[b][1] - pts[a][1]) * (pts[c][0] - pts[a][0])) > 1e-12

    def dentro(p, a, b, c):
        def s(u, v, w):
            return (v[0] - u[0]) * (w[1] - u[1]) - (v[1] - u[1]) * (w[0] - u[0])
        d1, d2, d3 = s(pts[a], pts[b], p), s(pts[b], pts[c], p), s(pts[c], pts[a], p)
        return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))

    out = []
    guarda = 0
    while len(idx) > 3 and guarda < 10 * n:
        guarda += 1
        for k in range(len(idx)):
            a, b, c = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            if not convexo(a, b, c):
                continue
            if any(dentro(pts[j], a, b, c) for j in idx if j not in (a, b, c)):
                continue
            out.append((a, b, c))
            del idx[k]
            break
    if len(idx) == 3:
        out.append(tuple(idx))
    return out


class Malha:
    """A pile of triangles with a colour each, in mm, y down, z up."""

    def __init__(self):
        self.tris: list = []
        self.cols: list = []
        # Every primitive, as it is drawn. The triangle soup cannot be asked
        # "is this point inside?", so until 2026-10-01 the dry run had no way
        # of measuring the drawn solid and every rule read a constant instead
        # - which is how a pod with 7 interferences reported 18 rules met.
        # These records are appended by the SAME calls that emit triangles,
        # so they cannot drift from the mesh, and `dry_run_pod.voxels()`
        # rasterises them.
        self.solidos: list = []
        # o intervalo de triangulos de cada primitiva, para `PD26` conferir que
        # CADA UMA e um solido fechado. O STL do pod nao e uma malha manifold
        # unica - e a uniao de solidos fechados, e e assim que o fatiador o le
        # -, entao a pergunta certa nao e "a malha toda e manifold?" (366
        # arestas com mais de duas faces, todas superposicao de faces vizinhas)
        # e sim "alguma primitiva tem aresta de borda?".
        self.faixas: list = []

    def tri(self, a, b, c, cor):
        self.tris.append(np.array([a, b, c], dtype=np.float64))
        self.cols.append(np.array(cor))

    def quad(self, a, b, c, d, cor):
        self.tri(a, b, c, cor)
        self.tri(a, c, d, cor)

    def caixa(self, x0, y0, z0, x1, y1, z1, cor):
        # A box with a side of zero or less is a bug, never a no-op: the
        # cell's wire tail was drawn as x0 = 2,30, x1 = 2,00 and came out of
        # `quad` as a pair of inverted triangles that the viewer showed and
        # nobody could see was wrong (found 2026-10-01).
        if x1 <= x0 or y1 <= y0 or z1 <= z0:
            raise ValueError(f"caixa de lado nao positivo: ({x0:.3f}; {y0:.3f}; "
                             f"{z0:.3f}) a ({x1:.3f}; {y1:.3f}; {z1:.3f})")
        self.solidos.append(("caixa", (x0, y0, z0, x1, y1, z1)))
        self.faixas.append((len(self.tris), 12))
        b = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)]
        t = [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        self.quad(b[0], b[3], b[2], b[1], cor)
        self.quad(t[0], t[1], t[2], t[3], cor)
        for k in range(4):
            a, c = k, (k + 1) % 4
            self.quad(b[a], b[c], t[c], t[a], cor)

    def extrusao(self, pts, z0, z1, cor):
        """Any simple polygon (plan, y down) extruded between two heights."""
        self.solidos.append(("prisma", (tuple(map(tuple, pts)), z0, z1)))
        self.faixas.append((len(self.tris), 2 * (len(pts) - 2) + 2 * len(pts)))
        for a, b, c in triangular(pts):
            self.tri((*pts[a], z0), (*pts[c], z0), (*pts[b], z0), cor)
            self.tri((*pts[a], z1), (*pts[b], z1), (*pts[c], z1), cor)
        n = len(pts)
        for k in range(n):
            a, b = pts[k], pts[(k + 1) % n]
            self.quad((a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1), cor)

    def anel(self, fora, dentro, z0, z1, cor):
        """The wall between two closed polylines of equal length."""
        self.solidos.append(("anel", (tuple(map(tuple, fora)),
                                      tuple(map(tuple, dentro)), z0, z1)))
        self.faixas.append((len(self.tris), 8 * len(fora)))
        n = len(fora)
        for k in range(n):
            a, b = fora[k], fora[(k + 1) % n]
            c, d = dentro[k], dentro[(k + 1) % n]
            self.quad((a[0], a[1], z0), (b[0], b[1], z0), (d[0], d[1], z0), (c[0], c[1], z0), cor)
            self.quad((a[0], a[1], z1), (c[0], c[1], z1), (d[0], d[1], z1), (b[0], b[1], z1), cor)
            self.quad((a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1), cor)
            self.quad((c[0], c[1], z0), (c[0], c[1], z1), (d[0], d[1], z1), (d[0], d[1], z0), cor)

    def placa_com_furos(self, x0, y0, x1, y1, z0, z1, furos, cor):
        """A plate minus rectangular holes: the grid of cells between the
        holes' edges, every cell wholly inside a hole left out."""
        xs = sorted({x0, x1} | {f[0] for f in furos if x0 < f[0] < x1} | {f[2] for f in furos if x0 < f[2] < x1})
        ys = sorted({y0, y1} | {f[1] for f in furos if y0 < f[1] < y1} | {f[3] for f in furos if y0 < f[3] < y1})
        for i in range(len(xs) - 1):
            for j in range(len(ys) - 1):
                cx, cy = (xs[i] + xs[i + 1]) / 2.0, (ys[j] + ys[j + 1]) / 2.0
                if any(f[0] <= cx <= f[2] and f[1] <= cy <= f[3] for f in furos):
                    continue
                self.caixa(xs[i], ys[j], z0, xs[i + 1], ys[j + 1], z1, cor)

    def cilindro(self, cx, cy, r, z0, z1, cor, n=12):
        self.extrusao(poligono_regular(cx, cy, r, n), z0, z1, cor)

    def arrays(self):
        if not self.tris:
            return np.zeros((0, 3, 3)), np.zeros((0, 3))
        return np.array(self.tris), np.array(self.cols)

    def stl(self, caminho: pathlib.Path) -> int:
        """Binary STL, in mm, as the slicer wants it."""
        with open(caminho, "wb") as f:
            f.write(b"pmeter pod, generated by make_pod.py".ljust(80, b"\0"))
            f.write(struct.pack("<I", len(self.tris)))
            for t in self.tris:
                n = np.cross(t[1] - t[0], t[2] - t[0])
                ln = np.linalg.norm(n)
                n = n / ln if ln > 0 else n
                f.write(struct.pack("<3f", *n))
                for v in t:
                    f.write(struct.pack("<3f", *v))
                f.write(struct.pack("<H", 0))
        return len(self.tris)


# ------------------------------------------------------------ the board
def ler_placa():
    pecas, _pads, _seg, _vias, _cortes = DR.ler(CAD / "pmeter.kicad_pcb")
    for ref, p in pecas.items():
        nome_fp = FPS.FP.get(ref, ("", 0, 0))[0]
        alt = DR.altura_do_footprint(nome_fp) if nome_fp else None
        p["altura"] = alt[0] if alt else 1.0
    return pecas


def no_pod(caixa):
    """A box in board coordinates to pod coordinates."""
    x0, y0, x1, y1 = caixa
    return (PLACA_X0 + x0, PLACA_Y0 + y0, PLACA_X0 + x1, PLACA_Y0 + y1)


class Pod:
    """Everything the pod has, derived from the placed board."""

    def __init__(self, pecas):
        self.pecas = pecas
        if "J101" not in pecas:
            raise SystemExit("J101 (o conector magnetico) nao esta na placa")
        j = pecas["J101"]
        x0, y0, x1, y1 = no_pod(j["caixa"])
        # A JANELA passa o BARRILETE com folga. O courtyard e o corpo todo; o
        # barrilete e ele menos o ombro de cada lado, e a janela e o barrilete
        # mais `JANELA_FOLGA`. Ate 2026-10-01 a janela era o courtyard MAIS
        # 0,30: 0,55 mm maior que o corpo por lado, um anel aberto da face do
        # conector ate a cavidade.
        f = CONECTOR_OMBRO_L - JANELA_FOLGA
        self.janela = (x0 + f, y0 + f, x1 - f, y1 - f)
        # O que sobra de ombro para a junta apertar, por lado. E a largura
        # efetiva da vedacao da porta, e a `PD24` cobra o minimo.
        self.junta_larg = f
        self.conector_alt = j["altura"]
        # the well: from the lid's top down to the connector's face
        self.poco = T_P - (PLACA_Z1 + self.conector_alt)
        # A junta plana: o anel entre a janela e a borda do corpo, apoiado no
        # OMBRO do conector. Nao e mais um anel sobre o nada em volta da peca.
        self.junta = (x0, y0, x1, y1)
        self.ombro_z = PLACA_Z1 + CONECTOR_OMBRO_Z
        # a face de baixo do ressalto que comprime a junta
        self.junta_aperta_em = self.ombro_z + JUNTA_ESP - JUNTA_APERTO
        d = pecas.get("D201")
        self.led = None
        if d:
            bx0, by0, bx1, by1 = no_pod(d["caixa"])
            self.led = ((bx0 + bx1) / 2.0, (by0 + by1) / 2.0)
        # the slot in the floor under the bridge's holes
        self.rasgo = None
        j3 = pecas.get("J301")
        if j3 and j3["pads"]:
            xs = [q["x"] for q in j3["pads"]]
            ys = [q["y"] for q in j3["pads"]]
            r = max(q["hw"] for q in j3["pads"])
            # (o colar vem logo abaixo, derivado deste retangulo)
            self.rasgo = (PLACA_X0 + min(xs) - r - RASGO_FOLGA, PLACA_Y0 + min(ys) - r - RASGO_FOLGA,
                          PLACA_X0 + max(xs) + r + RASGO_FOLGA, PLACA_Y0 + max(ys) + r + RASGO_FOLGA)
        # The two posts that hold the board's left end. They are NOT fixed
        # points: a post touches the back of the board, so it must not land
        # on a pad. Measured on 2026-09-28: the nominal post at 1,5 mm from
        # the edge was sitting on a through pad of J102 (the cell connector
        # has mounting tabs, which pierce the board), so each post now slides
        # along y from its nominal place until its whole head is clear of
        # every back pad, and stays between the ledges.
        pads_tras = [(PLACA_X0 + q["x"] - q["hw"] - PILAR_FOLGA,
                      PLACA_Y0 + q["y"] - q["hh"] - PILAR_FOLGA,
                      PLACA_X0 + q["x"] + q["hw"] + PILAR_FOLGA,
                      PLACA_Y0 + q["y"] + q["hh"] + PILAR_FOLGA)
                     for pe in pecas.values() for q in pe["pads"]
                     if q["camada"].startswith("B.") or not q["smd"]]
        ylim = (PAREDE + RESSALTO + PILAR_D / 2.0, H_P - PAREDE - RESSALTO - PILAR_D / 2.0)

        def livre(cx: float, cy: float) -> bool:
            a = (cx - PILAR_D / 2, cy - PILAR_D / 2, cx + PILAR_D / 2, cy + PILAR_D / 2)
            return not any(not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])
                           for b in pads_tras)

        # O COLAR em volta do rasgo, por dentro. O rasgo e a unica abertura
        # do lado de baixo do pod: e por ele que os fios do extensometro
        # sobem do braco. Sem colar, o envase escorreria por ali antes de
        # curar e a agua teria um caminho reto ate a placa; com ele, o
        # envase fica represado e o caminho da agua passa a ter a altura do
        # colar mais a espessura do fundo. Por fora, quem fecha o resto e o
        # proprio adesivo que cola o pod ao braco.
        # Recortado na CAVIDADE: um colar por dentro da parede ou do ressalto
        # e material dentro de material. Media 0,15 dentro da parede e 0,75
        # dentro do ressalto (revisao de 2026-10-01).
        self.colar = None
        if self.rasgo:
            a, b, c, d = self.rasgo
            self.colar = (max(a - RASGO_COLAR_L, PAREDE),
                          max(b - RASGO_COLAR_L, PAREDE),
                          min(c + RASGO_COLAR_L, W_P - PAREDE),
                          min(d + RASGO_COLAR_L, H_P - PAREDE))

        self.pilares = []
        for cy0 in (PLACA_Y0 + 1.5, PLACA_Y0 + PLACA_H - 1.5):
            cx = PLACA_X0 + 1.2
            escolha = (cx, cy0)
            for passo in [0.0] + [s * 0.25 * k for k in range(1, 61) for s in (1, -1)]:
                cy = cy0 + passo
                if ylim[0] - 1e-9 <= cy <= ylim[1] + 1e-9 and livre(cx, cy):
                    escolha = (cx, cy)
                    break
            self.pilares.append(escolha)
        # The rib at the cell's right end, short of the slot. And when the
        # slot IS there - measured on 2026-09-28: the bridge connector sits
        # 0,2 mm past the cell, so the rib was being clipped to 0,0 mm and
        # the board had nothing holding it off the cell's edge - the rib
        # goes just PAST the slot instead, which supports the same span.
        nx0 = CELULA_X0 + CELULA_W + 0.2
        nx1 = nx0 + NERVURA
        if self.rasgo:
            nx1 = min(nx1, self.rasgo[0] - 0.2)
            if nx1 - nx0 < NERVURA / 2.0:
                # past the slot AND past the cell: the slot of this board
                # ends at 28,85 and the cell at 29,2, so taking only the
                # slot into account would put the rib on top of the cell
                nx0 = max(self.rasgo[2] + 0.2, CELULA_X0 + CELULA_W + 0.2)
                nx1 = min(nx0 + NERVURA, W_P - PAREDE - RESSALTO - 0.2)
        self.nervura = (nx0, nx1)
        # A PASSAGEM dos fios da celula: da face direita da celula ate a borda
        # da placa, na altura dos pinos do J102. Tudo o que sobe na cavidade
        # dentro deste retangulo e cortado (berco, nervura, aba da tampa),
        # porque este e o unico caminho que os dois fios tem - e ate
        # 2026-10-01 ele nao existia: as tres nervuras iam do fundo ao teto e
        # o flood fill parava em x = 17,25, com o J102 em x = 24,45.
        j2 = pecas.get("J102")
        meia = CELULA_FIO_VAO / 2.0
        if j2 and j2["pads"]:
            fy = PLACA_Y0 + sum(q["y"] for q in j2["pads"]) / len(j2["pads"])
        else:
            fy = CELULA_Y0 + CELULA_H / 2.0
        # dentro da face da celula: e dela que os fios saem
        self.fio_y = min(max(fy, CELULA_Y0 + meia), CELULA_Y0 + CELULA_H - meia)
        self.passagem = (CELULA_X0 + CELULA_W, self.fio_y - meia,
                         PLACA_X0, self.fio_y + meia)
        # the module's antenna band, in pod coordinates (the same 4,46 mm
        # the board's dry run measures)
        self.antena = None
        if DR.MODULO in pecas:
            mx0, my0, mx1, my1 = no_pod(pecas[DR.MODULO]["caixa"])
            self.antena = (mx1 - DR.ANT_MOD, my0, mx1, my1)

    # ------------------------------------------------------------- solids
    def contornos(self, folga=0.0):
        fora = contorno_arredondado(0.0, 0.0, W_P, H_P, R_P)
        dentro = contorno_arredondado(PAREDE + folga, PAREDE + folga, W_P - PAREDE - folga,
                                      H_P - PAREDE - folga, max(0.3, R_P - PAREDE - folga))
        return fora, dentro

    def sulco(self):
        """The O-ring groove in the wall's top face, as two contours.

        Centred in the wall: 0,475 mm of land outside and 0,475 inside, which
        is what is left of 2,00 mm of wall after a groove of 1,05.
        """
        g0 = (PAREDE - JUNTA_SULCO_L) / 2.0
        g1 = g0 + JUNTA_SULCO_L
        return (contorno_arredondado(g0, g0, W_P - g0, H_P - g0, max(0.3, R_P - g0)),
                contorno_arredondado(g1, g1, W_P - g1, H_P - g1, max(0.3, R_P - g1)))

    def berco(self) -> list:
        """The ribs that box the cell in, clear of it by BERCO_FOLGA.

        A rib only exists where there is ROOM for it: where the cell already
        lies against a ledge - and it does, on the wall side - the ledge is
        the retention and a rib there would only push the cell out of its
        envelope. A rib that runs across the bridge's wire slot is CUT round
        it, not dropped: the long side of the cradle is what stops the cell
        sliding, and dropping it because 3 mm of it fall over the slot would
        leave the cell held on one side (measured 2026-09-28: dropping gave
        one rib out of four).
        """
        # O limite da baia e a PAREDE, nao parede mais ressalto. O ressalto
        # e a borda em que a PLACA se apoia, e desde 2026-09-30 a placa nao
        # chega a esta ponta do pod: a celula ficou sozinha aqui. Medindo
        # contra parede+ressalto, as duas nervuras dos lados longos caiam
        # por 0,15 mm e a `PD15` dizia, com razao, que a celula anda.
        ent = (PAREDE, PAREDE, W_P - PAREDE, H_P - PAREDE)
        x0 = CELULA_X0 - BERCO_FOLGA - BERCO_LARG
        y0 = CELULA_Y0 - BERCO_FOLGA - BERCO_LARG
        x1 = CELULA_X0 + CELULA_W + BERCO_FOLGA + BERCO_LARG
        y1 = CELULA_Y0 + CELULA_H + BERCO_FOLGA + BERCO_LARG
        # each rib is dropped only when ITS OWN side has no room; the other
        # two sides are simply clamped to the usable area, which is what was
        # wrong on the first try (the corner overhang dropped three of four)
        brutas = [((x0, y0, x0 + BERCO_LARG, y1), x0 >= ent[0]),
                  ((x1 - BERCO_LARG, y0, x1, y1), x1 <= ent[2]),
                  ((x0, y0, x1, y0 + BERCO_LARG), y0 >= ent[1]),
                  ((x0, y1 - BERCO_LARG, x1, y1), y1 <= ent[3])]
        ribs = []
        for (a, b, c, d), cabe in brutas:
            if not cabe:
                continue              # that side is a ledge already: no room
            a, b = max(a, ent[0]), max(b, ent[1])
            c, d = min(c, ent[2]), min(d, ent[3])
            for pedaco in self._sem_rasgo(a, b, c, d):
                if pedaco[2] - pedaco[0] > 0.3 and pedaco[3] - pedaco[1] > 0.3:
                    ribs.append(pedaco)
        return ribs

    def _sem_rasgo(self, a, b, c, d) -> list:
        """A rectangle cut clear of the slot AND of the leads' passage.

        In BOTH axes. Cutting only in x dropped the cradle's right rib whole,
        because it crosses the slot's x range while overlapping only 0,6 mm
        of its y range (measured 2026-09-28). The passage joined the list on
        2026-10-01: a rib across it walls the cell's leads in.
        """
        return menos_retangulos((a, b, c, d), [self.rasgo, self.passagem])

    @property
    def baia(self) -> tuple:
        """A baia da celula em planta: a celula mais a folga do berco.

        E o retangulo que as nervuras cercam e o que e cavado no piso,
        recortado na cavidade: do lado da parede a folga e a que a parede da.
        """
        return (max(CELULA_X0 - BERCO_FOLGA, PAREDE),
                max(CELULA_Y0 - BERCO_FOLGA, PAREDE),
                min(CELULA_X0 + CELULA_W + BERCO_FOLGA, W_P - PAREDE),
                min(CELULA_Y0 + CELULA_H + BERCO_FOLGA, H_P - PAREDE))

    @property
    def gauge_xy(self) -> tuple:
        """O centro da matriz do extensometro, em coordenadas do pod."""
        return (GAUGE_X, H_P / 2.0 - GAUGE_DESLOC_Y)

    def bolso_gauge(self) -> tuple:
        """O bolso na face de baixo sobre a matriz do extensometro."""
        cx, cy = self.gauge_xy
        f = GAUGE_FOLGA
        return (cx - GAUGE_W / 2 - f, cy - GAUGE_H / 2 - f,
                cx + GAUGE_W / 2 + f, cy + GAUGE_H / 2 + f)

    def canaleta_fios(self) -> list:
        """A canaleta do feixe dos cinco fios, do bolso ate o rasgo, em L.

        Os fios saem das ilhas da matriz como FEIXE, correm em x ate o eixo do
        rasgo e sobem em y ate ele; dentro do rasgo eles se abrem para os cinco
        furos. Desenhada em dois trechos de `CANALETA_L` de largura, e e por
        ela que `make_conjunto.fios()` passa - os dois leem as mesmas cotas.
        """
        if not self.rasgo:
            return []
        bx0, by0, bx1, by1 = self.bolso_gauge()
        cy = (by0 + by1) / 2.0
        xf = (self.rasgo[0] + self.rasgo[2]) / 2.0
        L = CANALETA_L / 2.0
        return [(bx1, cy - L, xf + L, cy + L),
                (xf - L, cy - L, xf + L, self.rasgo[1])]

    def base_cola(self) -> tuple:
        """A faixa da face de baixo que encosta no braco, em planta.

        `BASE_COLA` e a largura PLANA da face do braco (BRACO_LARG menos as
        duas concordancias), centrada na largura do pod. Fora dela nao ha face
        plana: ha a curva da concordancia, e o pod tem de livra-la com ar.
        """
        by0 = (H_P - BASE_COLA) / 2.0
        return (0.0, by0, W_P, H_P - by0)

    def sob_a_placa(self) -> list:
        """O que desce do verso da placa, e ate onde: (retangulo, z de baixo).

        Inclui a propria placa (em `PLACA_Z0`), o corpo de cada peca do verso
        e cada ilha do verso - uma ilha nao desce da placa, mas nada do pod
        pode encostar nela. E a lista contra a qual tudo o que sobe do fundo
        tem de ser medido.
        """
        itens = []
        for ref, p in self.pecas.items():
            x0, y0, x1, y1 = no_pod(p["caixa"])
            if p["atras"] and p["altura"] > 0.0:
                itens.append(((x0, y0, x1, y1), PLACA_Z0 - p["altura"], ref))
            for q in p["pads"]:
                if not (q["camada"].startswith("B.") or not q["smd"]):
                    continue
                itens.append(((PLACA_X0 + q["x"] - q["hw"], PLACA_Y0 + q["y"] - q["hh"],
                               PLACA_X0 + q["x"] + q["hw"], PLACA_Y0 + q["y"] + q["hh"]),
                              PLACA_Z0, f"ilha de {ref}"))
        return itens

    def colar_barras(self) -> list:
        """As quatro barras do colar, cada uma com a altura que CABE nela.

        O colar represa o envase em volta do rasgo, que e a unica abertura do
        lado de baixo. Ate 2026-10-01 ele subia `RASGO_COLAR_ALT` inteiro,
        chegando a `FUNDO + 1,50 = PLACA_Z0`, e a barra y+ passava por baixo
        do R302 e do C304, que descem 0,55 abaixo da placa: a placa ia parar
        0,55 mm alta apoiada em dois 0402, ou os dois eram esmagados, e nos
        dois casos o colar deixava de represar nada.

        Agora cada barra para `COLAR_FOLGA` abaixo do mais baixo que passa
        sobre ela. Uma barra mais baixa deixa o envase passar por cima dela
        ANTES de curar, o que e menos do que se queria - mas o envase enche a
        cavidade inteira de todo jeito, e represar durante o derrame e o que o
        colar faz; prensar um resistor nao e opcao.
        """
        if not self.colar:
            return []
        a, b, c, d = self.colar
        e, f, g, h = self.rasgo
        barras = [r for r in [(a, b, e, d), (g, b, c, d), (e, b, g, f), (e, h, g, d)]
                  if r[2] - r[0] > 0.05 and r[3] - r[1] > 0.05]
        acima = self.sob_a_placa()
        saida = []
        for r in barras:
            teto = PLACA_Z0
            for (bx0, by0, bx1, by1), z, _ref in acima:
                if r[2] <= bx0 or bx1 <= r[0] or r[3] <= by0 or by1 <= r[1]:
                    continue
                teto = min(teto, z)
            z1 = teto - COLAR_FOLGA if teto < PLACA_Z0 else PLACA_Z0 - COLAR_FOLGA
            z1 = min(z1, FUNDO + RASGO_COLAR_ALT)
            if z1 > FUNDO + 0.05:
                saida.append((r, z1))
        return saida

    def concha(self) -> Malha:
        m = Malha()
        fora, dentro = self.contornos()
        # the wall up to the groove's floor, then the two lands that frame it
        z_sulco = TAMPA_Z0 - JUNTA_SULCO_P
        m.anel(fora, dentro, RELEVO, z_sulco, COR_POD)
        s_fora, s_dentro = self.sulco()
        m.anel(fora, s_fora, z_sulco, TAMPA_Z0, COR_POD)
        m.anel(s_dentro, dentro, z_sulco, TAMPA_Z0, COR_POD)
        # Os ressaltos dos parafusos. O que ATRAVESSA a placa estreita no
        # pescoco, e isso nao e enfeite: o ressalto tem 3,40 de diametro e o
        # furo da placa tem 2,20, entao desenhado em diametro cheio ele
        # interfere 0,600 mm no raio, em todo angulo, e a placa simplesmente
        # nao assenta. Sem a placa em z 2,50 a tampa nao desce aos 6,00, as
        # duas terras nao encostam e o O-ring nunca comprime: as seis
        # vedacoes do pod dependiam disto (revisao de 2026-10-01). O
        # `PARAF_PESCOCO_D` estava declarado desde sempre e nunca tinha sido
        # desenhado.
        #
        # E acima da placa nao ha ressalto nenhum: o parafuso vem de cima,
        # pela tampa, atravessa o furo e rosqueia no ressalto de BAIXO. Um
        # ressalto de 3,40 acima da placa passaria dos 2,80 que a reserva do
        # furo (`make_dxf.FURO_RESERVA_R`) guarda, e bateria nas pecas.
        for (cx, cy), na_placa in zip(PARAF_XY, PARAF_NA_PLACA):
            furo = poligono_regular(cx, cy, PARAF_FURO_D / 2.0, 16)
            if not na_placa:
                m.anel(poligono_regular(cx, cy, PARAF_BOSS_D / 2.0, 16),
                       furo, FUNDO, TAMPA_Z0, COR_POD)
                continue
            m.anel(poligono_regular(cx, cy, PARAF_BOSS_D / 2.0, 16),
                   furo, FUNDO, PLACA_Z0, COR_POD)
            # O pescoco segue ACIMA da placa ate passar o nivel do envase: o
            # furo do parafuso e cego e a resina enche a cavidade inteira. Sem
            # este colar o M1,6 autoatarraxante ia atarraxar em resina curada
            # (`PD28`). O diametro e o mesmo pescoco de 2,0, que cabe nos 2,80
            # que a placa reserva em volta do furo (`make_dxf.FURO_RESERVA_R`):
            # nao bate em peca nenhuma.
            m.anel(poligono_regular(cx, cy, PARAF_PESCOCO_D / 2.0, 16),
                   furo, PLACA_Z0,
                   max(PLACA_Z1, ENVASE_NIVEL + ENVASE_FOLGA / 2.0), COR_POD)
        # the cell's cradle
        for r in self.berco():
            m.caixa(r[0], r[1], BAIA_PISO, r[2], r[3], CELULA_Z1, COR_POD)
        furos = [self.rasgo] if self.rasgo else []
        # A baia E a passagem dos fios sao cavadas no piso, no mesmo nivel: o
        # fio sai da celula rente ao piso da baia e segue pelo canal sem ter de
        # subir o degrau de meio milimetro que o piso cheio faria.
        cavado = [self.baia, self.passagem]
        m.placa_com_furos(PAREDE, PAREDE, W_P - PAREDE, H_P - PAREDE, RELEVO, FUNDO,
                          furos + cavado, COR_POD)
        for r in cavado:
            for a, b, c, d in menos_retangulos(r, furos, minimo=0.0):
                m.caixa(a, b, RELEVO, c, d, BAIA_PISO, COR_POD)
        # o colar do rasgo, subindo do fundo para dentro da cavidade
        for (a, b, c, d), z1 in self.colar_barras():
            m.caixa(a, b, FUNDO, c, d, z1, COR_POD)
        # A BASE DE COLAGEM: a unica parte da face de baixo que toca o braco.
        # Ela DESCE de RELEVO a zero, dentro da tira central; fora dela a
        # concha nasce em z = RELEVO e livra a concordancia da face do braco
        # com ar. O rasgo sai da base: ele e a unica abertura do lado de baixo
        # e tem de ficar vazado de z 0 ate o piso (a caixa antiga tapava 15 %
        # dele com espessura inteira).
        vazios = [self.rasgo, self.bolso_gauge()] + self.canaleta_fios()
        for a, b, c, d in menos_retangulos(self.base_cola(), vazios, minimo=0.0):
            m.caixa(a, b, 0.0, c, d, RELEVO, COR_POD)
        # the ledges under the board's long edges and its right end
        m.caixa(PAREDE, PAREDE, FUNDO, W_P - PAREDE, PAREDE + RESSALTO, PLACA_Z0, COR_POD)
        m.caixa(PAREDE, H_P - PAREDE - RESSALTO, FUNDO, W_P - PAREDE, H_P - PAREDE, PLACA_Z0, COR_POD)
        m.caixa(W_P - PAREDE - RESSALTO, PAREDE, FUNDO, W_P - PAREDE, H_P - PAREDE, PLACA_Z0, COR_POD)
        for cx, cy in self.pilares:
            m.cilindro(cx, cy, PILAR_D / 2.0, FUNDO, PLACA_Z0, COR_POD)
        nx0, nx1 = self.nervura
        if nx1 > nx0:
            # cortada na passagem dos fios, como o berco: ela cruza o unico
            # caminho que os dois fios da celula tem
            for a, b, c, d in menos_retangulos(
                    (nx0, PAREDE + RESSALTO, nx1, H_P - PAREDE - RESSALTO),
                    [self.passagem]):
                m.caixa(a, b, FUNDO, c, d, CELULA_Z1 - 0.5, COR_POD)
        return m

    def tampa(self, dz: float = 0.0) -> Malha:
        m = Malha()
        fora, dentro = self.contornos()
        z0, z1 = TAMPA_Z0 + dz, T_P + dz
        m.anel(fora, dentro, z0, z1, COR_TAMPA)
        furos = [self.janela]
        if self.led:
            lx, ly = self.led
            q = (LED_FURO + LED_FURO_FOLGA) / 2.0
            furos.append((lx - q, ly - q, lx + q, ly + q))
            # o furo e REDONDO: a chapa sai com um furo quadrado e os quatro
            # cantos voltam como um anel entre o quadrado e o circulo. Ate
            # 2026-10-01 o furo era quadrado de 2,5 x 2,5 = 6,25 mm2 onde o
            # projeto anuncia e desenha um circulo de 2,5 = 4,91: 27 % a mais
            # de area para a resina transparente encher, e o PDF mostrando
            # uma coisa e o STL sendo outra
        # the two screw holes, clear for the screw's shank
        for cx, cy in PARAF_XY:
            r = PARAF_D / 2.0 + 0.15
            furos.append((cx - r, cy - r, cx + r, cy + r))
        m.placa_com_furos(PAREDE, PAREDE, W_P - PAREDE, H_P - PAREDE, z0, z1, furos, COR_TAMPA)
        if self.led:
            lx, ly = self.led
            m.anel(quadrado_amostrado(lx, ly, LED_FURO + LED_FURO_FOLGA, 16),
                   poligono_regular(lx, ly, LED_FURO / 2.0, 16), z0, z1, COR_TAMPA)
        # O RESSALTO QUE COMPRIME A JUNTA, na face de baixo, em volta da
        # janela: ele desce do teto da cavidade ate `junta_aperta_em` e e o
        # que faz a vedacao da porta existir. Sem ele a junta era um anel
        # desenhado no ar.
        jx0, jy0, jx1, jy1 = self.junta
        wx0, wy0, wx1, wy1 = self.janela
        zr = self.junta_aperta_em + dz
        if zr < z0 - 1e-9:
            for a, b, c, d in menos_retangulos((jx0, jy0, jx1, jy1),
                                               [(wx0, wy0, wx1, wy1)], minimo=0.0):
                m.caixa(a, b, zr, c, d, z0, COR_TAMPA)
        # the fingers that CLAMP the board. They come down over the two
        # posts, so the board is held between a post below and a finger
        # above instead of merely resting on the ledges: a chain that starts
        # at a strain gauge cannot have its board moving against the arm.
        # They stop APERTO_PAD short, and that gap is a compressible pad.
        for cx, cy in self.pilares:
            m.cilindro(cx, cy, PILAR_D / 2.0, PLACA_Z1 + APERTO_PAD + dz, z0, COR_TAMPA)
        # the lip that drops inside the walls, in the pieces that have room
        for a, b, c, d in self.aba():
            m.caixa(a, b, z0 - ABA_ALT, c, d, z0, COR_TAMPA)
        return m

    def sobe_na_cavidade(self) -> list:
        """O que sobe dentro da cavidade, e ate onde: (retangulo, z de cima).

        Tudo: as nervuras do berco, o colar, os ressaltos dos parafusos, a
        nervura solta, os pilares, os apoios da placa, a celula e o corpo de
        cada peca da FRENTE. E a lista contra a qual a aba e os dedos da tampa
        tem de ser medidos - a `PD12` varria so as pecas da placa, e foi por
        isso que a aba atravessou a celula e tres nervuras sem ninguem ver.
        """
        itens = []
        for r in self.berco():
            itens.append((r, CELULA_Z1, "nervura do berco"))
        for r, z1 in self.colar_barras():
            itens.append((r, z1, "colar do rasgo"))
        for (cx, cy), na_placa in zip(PARAF_XY, PARAF_NA_PLACA):
            raio = PARAF_PESCOCO_D / 2.0 if na_placa else PARAF_BOSS_D / 2.0
            alto = PLACA_Z1 if na_placa else TAMPA_Z0
            itens.append(((cx - raio, cy - raio, cx + raio, cy + raio), alto,
                          f"ressalto do parafuso em ({cx:.1f}; {cy:.1f})"))
        nx0, nx1 = self.nervura
        if nx1 > nx0:
            itens.append(((nx0, PAREDE + RESSALTO, nx1, H_P - PAREDE - RESSALTO),
                          CELULA_Z1 - 0.5, "nervura da placa"))
        itens.append(((CELULA_X0, CELULA_Y0, CELULA_X0 + CELULA_W,
                       CELULA_Y0 + CELULA_H), CELULA_Z1, "celula"))
        for ref, p in self.pecas.items():
            if p["atras"] or p["altura"] <= 0.0:
                continue
            itens.append((no_pod(p["caixa"]), PLACA_Z1 + p["altura"], ref))
        return itens

    def aba(self) -> list:
        """A aba de centragem da tampa, nos pedacos que CABEM.

        Ate 2026-10-01 a aba era um anel FECHADO de 0,4 de largura descendo
        1,0 mm dentro das paredes, desenhado sem olhar o que havia ali: ela
        entrava 5,565 mm3 dentro da bolsa de litio e 2,315 mm3 dentro de tres
        nervuras do berco. A tampa parava 1,00 mm alta mesmo sem a celula no
        lugar, o vao do O-ring virava 1,58 contra um cordao de 0,80 -
        compressao zero - e os dois parafusos passavam a prensar a bolsa.
        Nenhuma das seis vedacoes do pod fechava, e a `PD12` varria so as
        pecas da placa.

        Agora ela e quatro barras retas cortadas em tudo o que sobe at a faixa
        dela, com `ABA_FOLGA` de ar. Barra que sobra menor que 2 mm sai: um
        toco de aba nao centra nada.
        """
        fo = PAREDE + ABA_FOLGA
        rc = max(0.0, R_P - PAREDE - ABA_FOLGA)   # fora do canto arredondado
        x0, y0, x1, y1 = fo, fo, W_P - fo, H_P - fo
        barras = [(x0, y0 + rc, x0 + ABA_LARG, y1 - rc),
                  (x1 - ABA_LARG, y0 + rc, x1, y1 - rc),
                  (x0 + rc, y0, x1 - rc, y0 + ABA_LARG),
                  (x0 + rc, y1 - ABA_LARG, x1 - rc, y1)]
        zb0 = TAMPA_Z0 - ABA_ALT
        buracos = [(r[0] - ABA_FOLGA, r[1] - ABA_FOLGA, r[2] + ABA_FOLGA, r[3] + ABA_FOLGA)
                   for r, z1, _n in self.sobe_na_cavidade() if z1 > zb0 + 1e-9]
        saida = []
        for b in barras:
            saida += menos_retangulos(b, buracos, minimo=0.0)
        return [p for p in saida
                if max(p[2] - p[0], p[3] - p[1]) >= 2.0
                and min(p[2] - p[0], p[3] - p[1]) > 0.05]

    def anel_oring(self, dz: float = 0.0) -> Malha:
        """The O-ring sitting in its groove, drawn for the views."""
        m = Malha()
        s_fora, s_dentro = self.sulco()
        z0 = TAMPA_Z0 - JUNTA_SULCO_P + dz
        m.anel(s_fora, s_dentro, z0, z0 + JUNTA_CORDAO, COR_JUNTA)
        return m

    def junta_3d(self, dz: float = 0.0) -> Malha:
        """A junta plana, apoiada no ombro do conector, ja comprimida.

        Desenhada na espessura COMPRIMIDA (`JUNTA_ESP - JUNTA_APERTO`): e
        assim que ela fica no pod fechado, e e nessa posicao que a medida de
        interferencia faz sentido. A espessura livre e `JUNTA_ESP`.
        """
        m = Malha()
        jx0, jy0, jx1, jy1 = self.junta
        wx0, wy0, wx1, wy1 = self.janela
        z0 = self.ombro_z + dz
        z1 = z0 + JUNTA_ESP - JUNTA_APERTO
        m.placa_com_furos(jx0, jy0, jx1, jy1, z0, z1, [(wx0, wy0, wx1, wy1)], COR_JUNTA)
        return m

    def anilhas_3d(self, dz: float = 0.0) -> Malha:
        """As anilhas vedantes sob as cabecas dos parafusos, ja comprimidas.

        Desenhadas na espessura COMPRIMIDA, que e como ficam no pod fechado,
        apoiadas na face de FORA da tampa. Sao o que veda os dois furos que
        atravessam a tampa por dentro do anel O - um furo ali e caminho direto
        para a cavidade.
        """
        m = Malha()
        z0 = T_P + dz
        for cx, cy in PARAF_XY:
            m.anel(poligono_regular(cx, cy, PARAF_ANILHA_D / 2.0, 16),
                   poligono_regular(cx, cy, PARAF_D / 2.0 + 0.15, 16),
                   z0, z0 + PARAF_ANILHA_ESP - PARAF_ANILHA_APERTO, COR_JUNTA)
        return m

    def celula_3d(self, dz: float = 0.0) -> Malha:
        m = Malha()
        m.caixa(CELULA_X0, CELULA_Y0, CELULA_Z0 + dz, CELULA_X0 + CELULA_W, CELULA_Y0 + CELULA_H,
                CELULA_Z1 + dz, COR_CELULA)
        # The leads, out of the bay on the side that FACES the connector and
        # along the passage drawn for them. Until 2026-10-01 this box was
        # x0 = 2,30 to x1 = 2,00 - negative width, on the wall side, the
        # opposite end from the J102, and wholly inside the cell's own body.
        # `Malha.caixa` now refuses a box like that.
        fy = self.fio_y
        m.caixa(CELULA_X0 + CELULA_W, fy - CELULA_FIO_VAO / 2.0, CELULA_Z0 + dz,
                PLACA_X0, fy + CELULA_FIO_VAO / 2.0,
                CELULA_Z0 + CELULA_FIO_D + dz, COR_CELULA)
        return m

    # -------------------------------------------------------------- mass
    def volumes(self) -> dict:
        """Volumes in mm3, analytic, of what the pod holds and is made of."""
        a_fora = W_P * H_P - (4.0 - math.pi) * R_P ** 2
        ri = R_P - PAREDE
        a_dentro = (W_P - 2 * PAREDE) * (H_P - 2 * PAREDE) - (4.0 - math.pi) * ri ** 2
        v_paredes = (a_fora - a_dentro) * (TAMPA_Z0 - FUNDO)
        v_fundo = a_fora * FUNDO
        if self.rasgo:
            v_fundo -= (self.rasgo[2] - self.rasgo[0]) * (self.rasgo[3] - self.rasgo[1]) * FUNDO
        v_ressaltos = (2 * (W_P - 2 * PAREDE) + (H_P - 2 * PAREDE)) * RESSALTO * (PLACA_Z0 - FUNDO)
        v_pilares = len(self.pilares) * math.pi * (PILAR_D / 2) ** 2 * (PLACA_Z0 - FUNDO)
        nx0, nx1 = self.nervura
        v_nervura = max(0.0, nx1 - nx0) * (H_P - 2 * PAREDE - 2 * RESSALTO) * (CELULA_Z1 - 0.5 - FUNDO)
        v_concha = v_fundo + v_paredes + v_ressaltos + v_pilares + v_nervura
        jx0, jy0, jx1, jy1 = self.janela
        v_tampa = a_fora * TAMPA - (jx1 - jx0) * (jy1 - jy0) * TAMPA
        if self.led:
            v_tampa -= math.pi * (LED_FURO / 2.0) ** 2 * TAMPA
        ra = R_P - PAREDE - ABA_FOLGA
        a_aba_fora = (W_P - 2 * (PAREDE + ABA_FOLGA)) * (H_P - 2 * (PAREDE + ABA_FOLGA)) - (4 - math.pi) * ra ** 2
        rb = max(0.3, ra - ABA_LARG)
        a_aba_dentro = (W_P - 2 * (PAREDE + ABA_FOLGA + ABA_LARG)) * (H_P - 2 * (PAREDE + ABA_FOLGA + ABA_LARG)) - (4 - math.pi) * rb ** 2
        v_tampa += (a_aba_fora - a_aba_dentro) * ABA_ALT
        v_placa = PLACA_W * PLACA_H * PLACA_ESP
        v_celula = CELULA_W * CELULA_H * CELULA_ESP
        # the parts as solids at 70 % of their courtyard box: a courtyard
        # is the body plus 0,25 a side, and most bodies are not full boxes
        v_pecas = 0.0
        for ref, p in self.pecas.items():
            if p["atras"]:
                continue
            x0, y0, x1, y1 = p["caixa"]
            v_pecas += 0.7 * (x1 - x0) * (y1 - y0) * p["altura"]
        v_cavidade = a_dentro * (TAMPA_Z0 - FUNDO) - v_ressaltos - v_pilares - v_nervura
        v_envase = v_cavidade - v_placa - v_celula - v_pecas - (a_aba_fora - a_aba_dentro) * ABA_ALT
        return {"concha": v_concha, "tampa": v_tampa, "placa": v_placa, "celula": v_celula,
                "pecas": v_pecas, "envase": max(0.0, v_envase), "cavidade": v_cavidade}

    def massa(self) -> dict:
        v = self.volumes()
        g = {"concha": v["concha"] / 1000 * DENS_POD, "tampa": v["tampa"] / 1000 * DENS_POD,
             "placa": v["placa"] / 1000 * DENS_FR4, "celula": v["celula"] / 1000 * DENS_CELULA,
             "pecas": v["pecas"] / 1000 * DENS_PECAS, "envase": v["envase"] / 1000 * DENS_ENVASE}
        g["total"] = sum(g.values())
        return g


def placa_3d() -> tuple[np.ndarray, np.ndarray]:
    """The board, from the sources make_3d.py draws it from, moved to where
    the pod holds it (the GLB and the bodies are in the sheet's frame, the
    board's top-left at make_pcb.ORIGEM)."""
    glb = M3._glb_atual()
    if glb is None:
        raise SystemExit("sem GLB da placa: rode dry_run_pcb.py ou make_3d.py")
    j, bina = M3.ler_glb(glb)
    pt, pc = M3.triangulos(j, bina)
    pt = np.stack([pt[..., 0] * 1000.0, -pt[..., 1] * 1000.0, pt[..., 2] * 1000.0], axis=-1)
    extra_t, extra_c = M3.caixas_das_pecas()
    silk_t, silk_c = M3.serigrafia()
    partes_t = [pt] + ([extra_t] if len(extra_t) else []) + ([silk_t] if len(silk_t) else [])
    partes_c = [pc] + ([extra_c] if len(extra_c) else []) + ([silk_c] if len(silk_c) else [])
    t = np.concatenate(partes_t) + np.array([PLACA_X0 - MP.ORIGEM[0], PLACA_Y0 - MP.ORIGEM[1], PLACA_Z0])
    return t, np.concatenate(partes_c)


def juntar(*malhas) -> tuple[np.ndarray, np.ndarray]:
    ts, cs = [], []
    for m in malhas:
        if isinstance(m, tuple):
            t, c = m
        else:
            t, c = m.arrays()
        if len(t):
            ts.append(t)
            cs.append(c)
    return np.concatenate(ts), np.concatenate(cs)


def deslocar(tc, dz: float):
    t, c = tc
    return t + np.array([0.0, 0.0, dz]), c


def renderizar(t, c, nome, w, h, az, el):
    t = np.stack([t[..., 0], -t[..., 1], t[..., 2]], axis=-1) / 1000.0
    img = M3.render(t, c, w, h, az, el)
    IMG.mkdir(parents=True, exist_ok=True)
    img.save(IMG / nome)
    print(f"  {IMG.relative_to(HERE.parents[1]) / nome}: {len(t)} triangulos")


# ------------------------------------------------------------------ 2D
S = 7.0


class Vista:
    def __init__(self, page, x0, y0, s=S):
        self.page, self.x0, self.y0, self.s = page, x0, y0, s

    def P(self, x, y):
        return fitz.Point(self.x0 + x * self.s, self.y0 + y * self.s)

    def rect(self, x0, y0, x1, y1, cor=(0, 0, 0), fill=None, largura=0.5, tracejado=None):
        sh = self.page.new_shape()
        sh.draw_rect(fitz.Rect(self.P(x0, y0), self.P(x1, y1)))
        sh.finish(color=cor, fill=fill, width=largura, dashes=tracejado)
        sh.commit()

    def poli(self, pts, cor=(0, 0, 0), fill=None, largura=0.8, tracejado=None):
        sh = self.page.new_shape()
        sh.draw_polyline([self.P(x, y) for x, y in pts] + [self.P(*pts[0])])
        sh.finish(color=cor, fill=fill, width=largura, dashes=tracejado, closePath=True)
        sh.commit()

    def linha(self, x1, y1, x2, y2, cor=(0.3, 0.3, 0.3), largura=0.5, tracejado=None):
        sh = self.page.new_shape()
        sh.draw_line(self.P(x1, y1), self.P(x2, y2))
        sh.finish(color=cor, width=largura, dashes=tracejado)
        sh.commit()

    def circulo(self, x, y, r, cor=(0, 0, 0), fill=None, largura=0.5):
        sh = self.page.new_shape()
        sh.draw_circle(self.P(x, y), r * self.s)
        sh.finish(color=cor, fill=fill, width=largura)
        sh.commit()

    def texto(self, x, y, s, tam=6.0, cor=(0.1, 0.1, 0.1), rot=0):
        self.page.insert_text(self.P(x, y), s, fontsize=tam, fontname="helv", color=cor, rotate=rot)

    def cota_h(self, y, x1, x2, s, acima=True):
        self.linha(x1, y, x2, y, (0.4, 0.4, 0.4), 0.4)
        for x in (x1, x2):
            self.linha(x, y - 0.6, x, y + 0.6, (0.4, 0.4, 0.4), 0.4)
        self.texto((x1 + x2) / 2 - len(s) * 0.4, y - 0.6 if acima else y + 1.6, s, 5.5, (0.35, 0.35, 0.35))

    def cota_v(self, x, y1, y2, s):
        self.linha(x, y1, x, y2, (0.4, 0.4, 0.4), 0.4)
        for y in (y1, y2):
            self.linha(x - 0.6, y, x + 0.6, y, (0.4, 0.4, 0.4), 0.4)
        self.texto(x + 0.8, (y1 + y2) / 2 + 0.6, s, 5.5, (0.35, 0.35, 0.35))


def _t(page, x, y, s, tam=10.0, negrito=True):
    page.insert_text(fitz.Point(x, y), s, fontsize=tam, fontname="hebo" if negrito else "helv",
                     color=(0.1, 0.1, 0.12))


def _paragrafo(page, x, y, s, tam, largura=780.0):
    linha = ""
    for w in s.split():
        prova = (linha + " " + w).strip()
        if fitz.get_text_length(prova, fontname="helv", fontsize=tam) > largura:
            page.insert_text(fitz.Point(x, y), linha, fontsize=tam, fontname="helv", color=(0.12, 0.12, 0.12))
            y += tam + 3
            linha = w
        else:
            linha = prova
    if linha:
        page.insert_text(fitz.Point(x, y), linha, fontsize=tam, fontname="helv", color=(0.12, 0.12, 0.12))
        y += tam + 3
    return y


def f2(v):
    return f"{v:.1f}".replace(".", ",")


def pagina_1(doc, pod: Pod):
    """Plan view: the pod from above with the lid off, and the lid."""
    page = doc.new_page(width=842, height=595)
    _t(page, 30, 30, f"Pod do medidor de potencia - planta, {f2(W_P)} x {f2(H_P)} x {f2(T_P)} mm por fora. "
                     "PROPOSTA: NADA IMPRESSO NEM MEDIDO.", 11)
    _t(page, 30, 46, "Sem a tampa, vista de cima (o braco fica embaixo da folha). Cinza: a concha; azul: as pecas "
                     "da frente da placa; tracejado: a celula sob a placa; vermelho: a janela do conector e o rasgo dos fios.",
       8, False)
    v = Vista(page, 60, 90)
    fora, dentro = pod.contornos()
    v.poli(fora, (0.2, 0.2, 0.2), (0.86, 0.86, 0.88), 0.8)
    v.poli(dentro, (0.3, 0.3, 0.3), (0.97, 0.97, 0.97), 0.5)
    # ledges, posts, rib
    v.rect(PAREDE, PAREDE, W_P - PAREDE, PAREDE + RESSALTO, (0.5, 0.5, 0.5), (0.8, 0.8, 0.82), 0.3)
    v.rect(PAREDE, H_P - PAREDE - RESSALTO, W_P - PAREDE, H_P - PAREDE, (0.5, 0.5, 0.5), (0.8, 0.8, 0.82), 0.3)
    v.rect(W_P - PAREDE - RESSALTO, PAREDE, W_P - PAREDE, H_P - PAREDE, (0.5, 0.5, 0.5), (0.8, 0.8, 0.82), 0.3)
    for cx, cy in pod.pilares:
        v.circulo(cx, cy, PILAR_D / 2, (0.4, 0.4, 0.4), (0.8, 0.8, 0.82), 0.3)
    nx0, nx1 = pod.nervura
    if nx1 > nx0:
        v.rect(nx0, PAREDE + RESSALTO, nx1, H_P - PAREDE - RESSALTO, (0.4, 0.4, 0.4), (0.8, 0.8, 0.82), 0.3)
    # the cell (under the board) and its leads
    v.rect(CELULA_X0, CELULA_Y0, CELULA_X0 + CELULA_W, CELULA_Y0 + CELULA_H, (0.2, 0.2, 0.5), None, 0.6, [2, 2])
    v.texto(CELULA_X0 + 1.0, CELULA_Y0 + CELULA_H - 1.0, f"celula {f2(CELULA_W)} x {f2(CELULA_H)} x {f2(CELULA_ESP)} (envelope)", 5.0, (0.2, 0.2, 0.5))
    # the board and its front parts
    v.rect(PLACA_X0, PLACA_Y0, PLACA_X0 + PLACA_W, PLACA_Y0 + PLACA_H, (0.1, 0.35, 0.1), None, 0.8)
    for ref, p in sorted(pod.pecas.items()):
        x0, y0, x1, y1 = no_pod(p["caixa"])
        if p["atras"]:
            v.rect(x0, y0, x1, y1, (0.6, 0.4, 0.2), None, 0.3, [1, 1])
        else:
            v.rect(x0, y0, x1, y1, (0.2, 0.3, 0.6), (0.85, 0.88, 0.95), 0.3)
        if (x1 - x0) * (y1 - y0) > 12.0:
            v.texto(x0 + 0.3, y0 + 1.4, ref, 4.0, (0.2, 0.3, 0.6))
    if pod.antena:
        ax0, ay0, ax1, ay1 = pod.antena
        v.rect(ax0, ay0, ax1, ay1, (0.7, 0.2, 0.2), None, 0.4, [1, 1])
        v.texto(ax0 - 6.0, ay0 - 0.6, "antena", 4.0, (0.7, 0.2, 0.2))
    # the window and the slot
    v.rect(*pod.janela, (0.8, 0.1, 0.1), None, 0.7)
    v.rect(*pod.junta, (0.8, 0.1, 0.1), None, 0.4, [1, 1])
    if pod.rasgo:
        v.rect(*pod.rasgo, (0.8, 0.1, 0.1), (1.0, 0.9, 0.9), 0.6)
        v.texto(pod.rasgo[0] - 2.0, pod.rasgo[3] + 2.4, "rasgo dos fios da ponte, no fundo", 4.5, (0.8, 0.1, 0.1))
    if pod.led:
        v.circulo(pod.led[0], pod.led[1], LED_FURO / 2, (0.8, 0.1, 0.1), None, 0.5)
    # the channel for the cell's leads
    v.rect(PAREDE, PAREDE + RESSALTO, PLACA_X0, H_P - PAREDE - RESSALTO, (0.5, 0.5, 0.5), None, 0.3, [1, 1])
    v.texto(PAREDE + 0.2, PAREDE + 4.0, "canal", 3.6, (0.4, 0.4, 0.4), 90)
    # dimensions
    v.cota_h(-3.0, 0.0, W_P, f"{f2(W_P)} (alvo {ALVO[0]:g})")
    v.cota_v(W_P + 3.0, 0.0, H_P, f"{f2(H_P)} (alvo {ALVO[1]:g})")
    v.cota_h(H_P + 3.5, PLACA_X0, PLACA_X0 + PLACA_W, f"placa {f2(PLACA_W)}", False)
    v.cota_h(H_P + 7.0, PAREDE, PLACA_X0, f"canal {f2(CANAL_FIO)}", False)
    v.cota_h(H_P + 7.0, PLACA_X0 + PLACA_W, W_P - PAREDE, f"{f2(FOLGA_PLACA)}", False)
    v.cota_v(-3.0, PLACA_Y0, PLACA_Y0 + PLACA_H, f"placa {f2(PLACA_H)}")
    jx0, jy0, jx1, jy1 = pod.janela
    v.cota_h(-6.5, jx0, jx1, f"janela {f2(jx1 - jx0)} x {f2(jy1 - jy0)}, poco de {f2(pod.poco)}")
    # the lid, drawn below
    y_t = H_P + 16.0
    v.texto(0.0, y_t - 1.0, "A tampa, vista de cima: janela do conector com a junta em volta, furo do LED, aba por dentro das paredes.", 6.0)
    fora_t = [(x, y + y_t) for x, y in fora]
    v.poli(fora_t, (0.2, 0.2, 0.2), (0.90, 0.90, 0.92), 0.8)
    aba = contorno_arredondado(PAREDE + ABA_FOLGA, PAREDE + ABA_FOLGA + y_t, W_P - PAREDE - ABA_FOLGA,
                               H_P - PAREDE - ABA_FOLGA + y_t, max(0.3, R_P - PAREDE - ABA_FOLGA))
    v.poli(aba, (0.4, 0.4, 0.4), None, 0.3, [1, 1])
    v.rect(jx0, jy0 + y_t, jx1, jy1 + y_t, (0.8, 0.1, 0.1), (1.0, 1.0, 1.0), 0.7)
    v.rect(pod.junta[0], pod.junta[1] + y_t, pod.junta[2], pod.junta[3] + y_t, (0.8, 0.3, 0.3), None, 0.5, [1, 1])
    if pod.led:
        v.circulo(pod.led[0], pod.led[1] + y_t, LED_FURO / 2, (0.8, 0.1, 0.1), (1.0, 1.0, 1.0), 0.5)
        v.texto(pod.led[0] + 2.0, pod.led[1] + y_t + 1.0, "LED", 4.0, (0.8, 0.1, 0.1))
    # legend
    y = 90 + (2 * H_P + 30.0) * S + 20
    y = _paragrafo(page, 60, y, "Cores: cinza claro, a concha vista de cima com os ressaltos das bordas, os dois pilares "
                                "da ponta esquerda e a nervura que segura a celula; verde, o contorno da placa; azul, o contorno "
                                "de ocupacao de cada peca da frente (os pontos de teste ficam atras, em laranja tracejado); "
                                "vermelho, a janela do conector na tampa, a junta em volta dela, o furo de luz do LED e o rasgo "
                                "no fundo por onde os cinco fios da ponte sobem do braco ate os furos metalizados da placa.", 8)
    _t(page, 30, 575, "hardware_powermeter/pod/make_pod.py - pagina 1 de 3 - medidas em mm", 7, False)


def pagina_2(doc, pod: Pod):
    """The two sections: across the pod through the cell, and along it."""
    page = doc.new_page(width=842, height=595)
    _t(page, 30, 30, "Cortes: a pilha de alturas. A esquerda o corte transversal pelo meio da celula, "
                     "a direita o longitudinal pelo eixo da placa. PROPOSTA.", 11)
    s = 9.0
    # ---- across (y, z), at x = middle of the cell
    v = Vista(page, 60, 320, s)

    def yz(y0, z0, y1, z1, cor, fill, largura=0.5, tracejado=None):
        v.rect(y0, -z1, y1, -z0, cor, fill, largura, tracejado)

    yz(0.0, 0.0, H_P, FUNDO, (0.2, 0.2, 0.2), (0.86, 0.86, 0.88))
    yz(0.0, 0.0, PAREDE, TAMPA_Z0, (0.2, 0.2, 0.2), (0.86, 0.86, 0.88))
    yz(H_P - PAREDE, 0.0, H_P, TAMPA_Z0, (0.2, 0.2, 0.2), (0.86, 0.86, 0.88))
    yz(PAREDE, FUNDO, PAREDE + RESSALTO, PLACA_Z0, (0.2, 0.2, 0.2), (0.8, 0.8, 0.82))
    yz(H_P - PAREDE - RESSALTO, FUNDO, H_P - PAREDE, PLACA_Z0, (0.2, 0.2, 0.2), (0.8, 0.8, 0.82))
    yz(0.0, TAMPA_Z0, H_P, T_P, (0.2, 0.2, 0.2), (0.90, 0.90, 0.92))
    yz(PAREDE + ABA_FOLGA, TAMPA_Z0 - ABA_ALT, PAREDE + ABA_FOLGA + ABA_LARG, TAMPA_Z0, (0.2, 0.2, 0.2), (0.90, 0.90, 0.92))
    yz(H_P - PAREDE - ABA_FOLGA - ABA_LARG, TAMPA_Z0 - ABA_ALT, H_P - PAREDE - ABA_FOLGA, TAMPA_Z0, (0.2, 0.2, 0.2), (0.90, 0.90, 0.92))
    yz(CELULA_Y0, CELULA_Z0, CELULA_Y0 + CELULA_H, CELULA_Z1, (0.2, 0.2, 0.5), (0.85, 0.85, 0.92))
    yz(PLACA_Y0, PLACA_Z0, PLACA_Y0 + PLACA_H, PLACA_Z1, (0.1, 0.35, 0.1), (0.75, 0.88, 0.75))
    # the tallest front part in this section's neighbourhood: the module
    if DR.MODULO in pod.pecas:
        m = pod.pecas[DR.MODULO]
        mx0, my0, mx1, my1 = no_pod(m["caixa"])
        yz(my0, PLACA_Z1, my1, PLACA_Z1 + m["altura"], (0.2, 0.3, 0.6), (0.85, 0.88, 0.95))
        v.texto(my0 + 0.5, -(PLACA_Z1 + m["altura"]) - 0.4, f"modulo {f2(m['altura'])}", 4.5, (0.2, 0.3, 0.6))
    yz(0.0, -COLA, H_P, 0.0, (0.5, 0.4, 0.2), (0.95, 0.9, 0.8), 0.3, [1, 1])
    v.texto(H_P / 2 - 6.0, COLA + 2.2, f"cola ao braco {f2(COLA)} (fora do pod)", 4.5, (0.5, 0.4, 0.2))
    v.cota_v(H_P + 2.0, -T_P, 0.0, f"{f2(T_P)} (alvo {ALVO[2]:g})")
    v.cota_v(H_P + 6.5, -CELULA_Z1, -CELULA_Z0, f"celula {f2(CELULA_ESP)}")
    v.cota_v(H_P + 6.5, -PLACA_Z1, -PLACA_Z0, f"placa {f2(PLACA_ESP)}")
    v.cota_v(H_P + 6.5, -TAMPA_Z0, -PLACA_Z1, f"teto {f2(TETO)}")
    v.cota_v(H_P + 6.5, -T_P, -TAMPA_Z0, f"tampa {f2(TAMPA)}")
    v.cota_v(H_P + 6.5, -FUNDO, 0.0, f"fundo {f2(FUNDO)}")
    v.cota_h(2.5, 0.0, H_P, f"{f2(H_P)}", False)
    v.texto(0.0, -T_P - 2.0, "corte transversal (y, z), pelo meio da celula", 6.0)
    # ---- along (x, z), at y = middle of the board
    v2 = Vista(page, 60, 520, 8.0)

    def xz(x0, z0, x1, z1, cor, fill, largura=0.5, tracejado=None):
        v2.rect(x0, -z1, x1, -z0, cor, fill, largura, tracejado)

    xz(0.0, 0.0, W_P, FUNDO, (0.2, 0.2, 0.2), (0.86, 0.86, 0.88))
    if pod.rasgo:
        xz(pod.rasgo[0], 0.0, pod.rasgo[2], FUNDO, (0.8, 0.1, 0.1), (1.0, 1.0, 1.0), 0.5)
        v2.texto(pod.rasgo[0], FUNDO + 2.4, "rasgo", 4.5, (0.8, 0.1, 0.1))
    xz(0.0, 0.0, PAREDE, TAMPA_Z0, (0.2, 0.2, 0.2), (0.86, 0.86, 0.88))
    xz(W_P - PAREDE, 0.0, W_P, TAMPA_Z0, (0.2, 0.2, 0.2), (0.86, 0.86, 0.88))
    xz(W_P - PAREDE - RESSALTO, FUNDO, W_P - PAREDE, PLACA_Z0, (0.2, 0.2, 0.2), (0.8, 0.8, 0.82))
    for cx, _cy in pod.pilares[:1]:
        xz(cx - PILAR_D / 2, FUNDO, cx + PILAR_D / 2, PLACA_Z0, (0.2, 0.2, 0.2), (0.8, 0.8, 0.82))
    nx0, nx1 = pod.nervura
    if nx1 > nx0:
        xz(nx0, FUNDO, nx1, CELULA_Z1 - 0.5, (0.2, 0.2, 0.2), (0.8, 0.8, 0.82))
    xz(0.0, TAMPA_Z0, W_P, T_P, (0.2, 0.2, 0.2), (0.90, 0.90, 0.92))
    jx0, _jy0, jx1, _jy1 = pod.janela
    xz(jx0, TAMPA_Z0, jx1, T_P, (0.8, 0.1, 0.1), (1.0, 1.0, 1.0), 0.5)
    xz(CELULA_X0, CELULA_Z0, CELULA_X0 + CELULA_W, CELULA_Z1, (0.2, 0.2, 0.5), (0.85, 0.85, 0.92))
    xz(PLACA_X0, PLACA_Z0, PLACA_X0 + PLACA_W, PLACA_Z1, (0.1, 0.35, 0.1), (0.75, 0.88, 0.75))
    for ref in ("J101", DR.MODULO, "U101", "J102", "U301", "J201"):
        p = pod.pecas.get(ref)
        if not p or p["atras"]:
            continue
        x0, _y0, x1, _y1 = no_pod(p["caixa"])
        xz(x0, PLACA_Z1, x1, PLACA_Z1 + p["altura"], (0.2, 0.3, 0.6), (0.85, 0.88, 0.95), 0.3)
        v2.texto(x0 + 0.2, -(PLACA_Z1 + p["altura"]) - 0.4, ref, 4.0, (0.2, 0.3, 0.6))
    v2.cota_h(-T_P - 3.0, 0.0, W_P, f"{f2(W_P)}")
    v2.cota_h(2.5, PAREDE, PLACA_X0, f"canal {f2(CANAL_FIO)}", False)
    v2.cota_h(2.5, CELULA_X0, CELULA_X0 + CELULA_W, f"celula {f2(CELULA_W)}", False)
    v2.cota_v(W_P + 2.0, -(PLACA_Z1 + pod.conector_alt), -T_P, f"poco {f2(pod.poco)}")
    v2.texto(0.0, -T_P - 5.0, "corte longitudinal (x, z), pelo eixo da placa; as pecas mais altas de cada bloco", 6.0)
    _t(page, 30, 575, "hardware_powermeter/pod/make_pod.py - pagina 2 de 3 - medidas em mm", 7, False)


def conflitos(pod: Pod) -> list[str]:
    """What this drawing knows is unresolved."""
    out = []
    if T_P > ALVO[2]:
        out.append(f"altura de {f2(T_P)} mm contra o alvo de {ALVO[2]:g}: a pilha celula sob a placa nao "
                   "chega a 8,5 (docs/02 ja diz que 8,5 pede a celula ao lado)")
    if W_P > ALVO[0]:
        out.append(f"comprimento de {f2(W_P)} mm contra o alvo de {ALVO[0]:g}: a placa de {f2(PLACA_W)} "
                   f"mais o canal dos fios da celula ({f2(CANAL_FIO)}) e as paredes")
    if H_P > ALVO[1]:
        out.append(f"largura de {f2(H_P)} mm contra o alvo de {ALVO[1]:g}")
    out.append("o conector magnetico e generico: a janela e o poco seguem o contorno de ocupacao de 18 x 5 x 3 "
               "e mudam com a peca escolhida")
    out.append("as medidas do braco (largura da face interna, folga ao quadro, raio da concordancia) sao "
               "LUGARES RESERVADOS ate serem medidas no pedivela do dono")
    return out


def pagina_3(doc, pod: Pod):
    page = doc.new_page(width=842, height=595)
    _t(page, 30, 30, "O que esta decidido aqui, o que e estimativa e o que falta medir", 11)
    y = 52
    g = pod.massa()
    y = _paragrafo(page, 30, y, f"Envelope: {f2(W_P)} x {f2(H_P)} x {f2(T_P)} mm por fora (alvo de docs/02: "
                                f"{ALVO[0]:g} x {ALVO[1]:g} x {ALVO[2]:g}), mais {f2(COLA)} de cola ao braco. Paredes {f2(PAREDE)}, "
                                f"fundo {f2(FUNDO)}, tampa {f2(TAMPA)}, raio dos cantos {f2(R_P)}. A pilha, do braco para cima: "
                                f"fundo {f2(FUNDO)}, celula {f2(CELULA_ESP)}, inchaco {f2(CELULA_INCHACO)}, placa {f2(PLACA_ESP)}, "
                                f"teto {f2(TETO)} (modulo de 2,4 mais 0,3), tampa {f2(TAMPA)}.", 9)
    y += 6
    y = _paragrafo(page, 30, y, "Massa ESTIMADA por volume e densidade, nao pesada (densidades: pod impresso 1,15; "
                                "envase de silicone 1,0; FR-4 1,85; celula 2,0; pecas 2,5 g/cm3 sobre 70 % do contorno de "
                                "ocupacao vezes a altura):", 9)
    for k, rot in (("concha", "concha"), ("tampa", "tampa"), ("placa", "placa nua"), ("pecas", "pecas da placa"),
                   ("celula", "celula (envelope cheio)"), ("envase", "envase ate a tampa")):
        _t(page, 50, y, f"{rot:<28} {g[k]:5.1f} g".replace(".", ","), 9, False)
        y += 13
    _t(page, 50, y, f"{'total':<28} {g['total']:5.1f} g  (alvo {MASSA_ALVO:g} g)".replace(".", ","), 9, True)
    y += 20
    y = _paragrafo(page, 30, y, "Decidido aqui (proposta): a celula na baia AO LADO da placa, presa por nervuras com "
                                f"{f2(BERCO_FOLGA)} mm de folga nos quatro lados e {f2(CELULA_INCHACO)} mm de reserva de inchaco "
                                f"sob o teto, com uma passagem de {f2(CELULA_FIO_VAO)} mm cortada nas nervuras por onde os dois "
                                "fios saem para o JST SH na frente da placa; a placa apoiada nos ressaltos das bordas e em dois "
                                "pilares, presa por dedos da tampa; o barrilete do conector magnetico atravessa a tampa e a face "
                                f"dele fica {f2(pod.poco)} mm abaixo do topo (limite {f2(POCO_MAX)}, o curso do pino do cabo), "
                                f"com uma junta plana de {f2(CONECTOR_OMBRO_L)} mm apoiada no ombro da peca e comprimida "
                                f"{f2(JUNTA_APERTO)} mm por um ressalto da tampa; um furo de {f2(LED_FURO)} mm sobre o LED, a "
                                "encher com resina transparente; os fios da ponte sobem do braco por um rasgo no fundo, direto "
                                "sob os cinco furos metalizados da placa, com um colar que represa o envase; a face de baixo "
                                f"toca o braco so na base de colagem de {f2(BASE_COLA)} mm, com {f2(RELEVO)} mm de relevo fora "
                                "dela; a cavidade envasada ate a face de baixo da tampa e a tampa colada pela aba.", 9)
    y += 6
    y = _paragrafo(page, 30, y, "LUGARES RESERVADOS, a medir no pedivela do dono antes de imprimir: largura da face interna "
                                "do braco esquerdo (____ mm; o pod tem " + f2(H_P) + "); folga entre a face interna do braco e o "
                                "quadro na pedalada (____ mm; o pod tem " + f2(T_P + COLA) + " com a cola); raio da concordancia "
                                "entre a face e o corpo do braco (____ mm; o fundo do pod e plano); posicao da ponte no braco "
                                "(distancia do eixo do pedivela ao centro do pod, ____ mm).", 9)
    y += 6
    for s in conflitos(pod):
        y = _paragrafo(page, 30, y, "- " + s, 9)
    y += 6
    y = _paragrafo(page, 30, y, "O que o dry run do pod mede (pod/dry_run_pod.py): a placa na cavidade com folga; toda peca "
                                "da frente sob o teto, menos o conector, que atravessa a tampa e cuja face tem de ficar dentro "
                                "do poco; a face de tras plana; a celula entre os ressaltos, sob a placa com o vao, longe do "
                                "rasgo, dos pilares e da area da antena; a janela sobre o conector e o furo sobre o LED; o "
                                "rasgo sob os furos da ponte; o envelope e a massa contra o alvo.", 9)
    _t(page, 30, 575, "hardware_powermeter/pod/make_pod.py - pagina 3 de 3", 7, False)


def main() -> int:
    pecas = ler_placa()
    pod = Pod(pecas)
    g = pod.massa()
    print(f"pod {W_P:.1f} x {H_P:.1f} x {T_P:.1f} (alvo {ALVO[0]:g} x {ALVO[1]:g} x {ALVO[2]:g}); "
          f"placa em x {PLACA_X0:.1f}-{PLACA_X0 + PLACA_W:.1f}, y {PLACA_Y0:.1f}-{PLACA_Y0 + PLACA_H:.1f}; "
          f"z: celula {CELULA_Z0:.1f}-{CELULA_Z1:.1f}, placa {PLACA_Z0:.1f}-{PLACA_Z1:.1f}, "
          f"tampa {TAMPA_Z0:.1f}-{T_P:.1f}; poco do conector {pod.poco:.1f}; "
          f"massa estimada {g['total']:.1f} g (alvo {MASSA_ALVO:g})")
    doc = fitz.open()
    pagina_1(doc, pod)
    pagina_2(doc, pod)
    pagina_3(doc, pod)
    doc.save(HERE / "pmeter-pod.pdf", garbage=3, deflate=True)
    print("  pmeter-pod.pdf: 3 paginas")
    for s in conflitos(pod):
        print("  - " + s)

    concha = pod.concha()
    tampa = pod.tampa()
    for nome, malha in (("pod-concha.stl", concha), ("pod-tampa.stl", tampa)):
        n = malha.stl(HERE / nome)
        print(f"  {nome}: {n} triangulos")

    placa = placa_3d()
    celula = pod.celula_3d()
    t, c = juntar(concha, celula, placa)
    renderizar(t, c, "pod-3d-aberta.png", 1800, 900, 200.0, 40.0)
    t, c = juntar(concha, celula, placa, tampa, pod.junta_3d())
    renderizar(t, c, "pod-3d-fechada.png", 1800, 900, 200.0, 62.0)
    dz_t, dz_p, dz_c = 22.0, 11.0, 0.0
    t, c = juntar(concha, pod.celula_3d(dz_c), deslocar(placa, dz_p), pod.tampa(dz_t),
                  pod.junta_3d(dz_t), pod.anel_oring(dz_t - 6.0))
    renderizar(t, c, "pod-3d-explodida.png", 1800, 1100, 200.0, 30.0)

    # The lid seen from BELOW, which is the face nobody ever draws and the
    # one that carries the work: the seat that squeezes the O-ring, the two
    # fingers that clamp the board down on its posts, the lip that drops
    # inside the walls and the window's rim. Rendered from under the part,
    # so the elevation is negative.
    t, c = juntar(pod.tampa())
    renderizar(t, c, "pod-3d-tampa-por-dentro.png", 1600, 1000, 200.0, -35.0)

    # The shell with the cell in its cradle, no board on top: what the
    # assembly looks like at the step where the cell goes in.
    t, c = juntar(concha, celula)
    renderizar(t, c, "pod-3d-celula-no-berco.png", 1800, 900, 200.0, 45.0)

    # The shell seen from BELOW: the face that is glued to the crank arm,
    # and the one the assembly manual talks about without ever showing. It
    # carries the 15 mm bonding land, the relief that keeps the glue off
    # the arm's fillet radius and the slot the bridge wires come up
    # through. Negative elevation, same trick as the lid from inside.
    t, c = juntar(pod.concha())
    renderizar(t, c, "pod-3d-por-baixo.png", 1800, 1000, 200.0, -40.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
