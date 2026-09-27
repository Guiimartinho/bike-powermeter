# AGENTS.md

Instruções para agentes de IA neste repositório (Claude Code, Codex, Cursor, Gemini e outros).

A fonte única do contexto é o [`CLAUDE.md`](CLAUDE.md) na raiz. Procedimentos passo a passo ficam em [`.claude/skills/`](.claude/skills/), um `SKILL.md` por tarefa, e a documentação técnica em [`docs/`](docs/README.md).

Regras mínimas, caso só este arquivo seja lido:

- Responda em português do Brasil; código, comentários de código e commits em inglês.
- `legacy/` (stravaV10 original) é a especificação de comportamento e **não é alterado**; o firmware ativo é o `zephyr_app/` (Zephyr, nRF Connect SDK v3.3.0).
- Nada pesado em ISR, sem alocação dinâmica depois do boot, pilhas medidas.
- Verifique antes de afirmar: `bash tools/fw/fw.sh build`, `bash tools/fw/host_tests.sh`, e diga o que não foi testado na placa.
- Commits em Conventional Commits, nunca atribuídos a IA, na branch `develop`; a `main` só recebe merge da `develop` quando o dono pedir.
- Push só com pedido do dono, para o `origin` no GitHub (`Guiimartinho/gnss-bike-computer`, público).
- Documentação em português com diagramas Mermaid, nunca diagramas em texto puro.
- Nunca use WSL; ferramentas do projeto ficam em `tools/fw/`, `tools/docs/` e `tools/ui/`.
- O CI (`.github/workflows/ci.yml`) está desligado, só roda à mão: não ligue gatilhos sem o dono pedir.
