# Changelog

Formato do [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/); versões pelo [SemVer](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Adicionado

- Modelo de protocolo e de sistema em C puro (`cps_encode`, `pm_settings`, `pm_cmd`, `health`, `pm_fsm`, `pm_wire`) com 67 casos de teste de host, 100 % das linhas e cinco mutações mortas; o bloco de configuração passa a ser binário versionado com CRC-16 em vez de CBOR, e a máquina do sistema mora no modelo em vez do SMF; `docs/07-status.md` vira a matriz de estado do projeto (2026-09-27).
- Modelo de medição em C puro (`bridge_calc`, `crank_angle`, `rev_power`, `calib`) com 66 casos de teste de host, cobertura por linha medida pelo gcov (`tools/fw/coverage.py`, 100 % nos quatro) e sete mutações mortas (2026-09-27).
- Estrutura do repositório, espelhando o ciclocomputador, e a lista fechada de componentes com o número do datasheet de cada peça (2026-09-27).
