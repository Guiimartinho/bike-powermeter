#!/usr/bin/env python3
"""Qual peca deste projeto usa qual simbolo da biblioteca do KiCad.

A mesma regra do ciclocomputador (hardware_gnssbike/cad/simbolos.py): so
entra aqui o simbolo em que **o numero de cada pino bate** com a nossa
pinagem, e `ksym.checar()` roda em `check_sch.py` e falha se sobrar ou
faltar um pino. Um simbolo bonito com o fio no pino errado e pior que um
retangulo certo.

Nesta placa so o conector da celula toma simbolo da biblioteca: os CIs
(nPM1100, MAX17048, ADS1220, TPS22916, BMA400, TMP117) e o modulo nao tem
simbolo revisado na biblioteca do KiCad 8 com a pinagem lida nas fichas, e
saem como retangulos com os pinos nomeados, que e o certo para um CI; o
conector magnetico e generico e nao tem peca.
"""
from __future__ import annotations

# peca -> "Biblioteca:Simbolo" da biblioteca oficial do KiCad
KICAD: dict[str, str] = {}

# Pinos em que o nome do nosso e o do KiCad diferem DE PROPOSITO, aceitos um
# a um.
ALIAS: dict[str, set[str]] = {}


def _p(refs, simbolo: str) -> None:
    for r in ([refs] if isinstance(refs, str) else refs):
        KICAD[r] = simbolo


# ------------------------------------------------------------ conectores
# O conector da celula: duas vias, e o corpo com os quadradinhos de contato
# diz isso melhor que um retangulo vazio.
# Nenhum: a celula entra por dois furos de solda, que sao cobre e nao
# peca, e um retangulo com os dois pinos nomeados diz isso melhor que
# um simbolo de conector que nao existe na placa.
