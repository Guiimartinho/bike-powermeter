# AGENTS.md

Instruções para agentes de IA neste repositório (Claude Code, Codex, Cursor, Gemini e outros).

A fonte única do contexto é o [`CLAUDE.md`](CLAUDE.md) na raiz. Procedimentos passo a passo ficam em [`.claude/skills/`](.claude/skills/), um `SKILL.md` por tarefa, e a documentação técnica em [`docs/`](docs/README.md).

Regras mínimas, caso só este arquivo seja lido:

- Responda em português do Brasil; código, comentários de código e commits em inglês.
- **Este firmware é obra original, não um port**: não existe `legacy/` aqui. O aparelho é o **medidor de potência**, par do [GNSS Bike Computer](https://github.com/Guiimartinho/gnss-bike-computer), e o firmware ativo é o `zephyr_app/` (Zephyr, nRF Connect SDK v3.3.0, **nRF54L15** no módulo HOLYIOT-26001-A).
- Nada pesado em ISR, sem alocação dinâmica depois do boot, pilhas medidas com `CONFIG_STACK_USAGE` e pelo menos 1 KB de folga.
- Verifique antes de afirmar: `bash tools/fw/fw.sh build`, `bash tools/fw/host_tests.sh`, `python tools/verificar_tudo.py`, e diga o que **não** foi testado na placa — hoje isso é tudo: o firmware nunca rodou e nada foi fabricado.
- Commits em Conventional Commits, nunca atribuídos a IA, na branch `develop`; a `main` só recebe merge da `develop` quando o dono pedir.
- Push só com pedido do dono, para o `origin` no GitHub (**`Guiimartinho/bike-powermeter`**, público). O do ciclocomputador é outro repositório: não confunda.
- Documentação em português com diagramas Mermaid, nunca diagramas em texto puro.
- **Nunca use WSL**, e num subprocesso do Windows `bash` sem caminho **é** o lançador do WSL: chame o do Git pelo caminho completo. As ferramentas do projeto ficam em `tools/fw/`, `tools/docs/` e `tools/verificar_tudo.py`.
- A cadeia de CAD tem ordem e intérprete certos: o `fill_zones.py` **só** roda com o Python do KiCad (`D:/KiCAD/bin/python.exe`), e o `check_pcb.py` regera a placa — depois do roteamento, só `--como-esta`. Está em [`hardware_powermeter/cad/README.md`](hardware_powermeter/cad/README.md#a-cadeia).
- **Uma regra de dry run que não acha o que medir tem de falhar dizendo isso**, e uma que mede uma peça que saiu do projeto é pior que nenhuma: ela falha apontando para o lugar errado.
- O CI (`.github/workflows/ci.yml`) está desligado, só roda à mão: não ligue gatilhos sem o dono pedir.
