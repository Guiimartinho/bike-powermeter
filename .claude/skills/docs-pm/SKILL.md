---
name: docs-pm
description: Escrever, atualizar e validar a documentação do Bike Power Meter no padrão do projeto - português do Brasil, diagramas Mermaid (nunca diagramas em texto puro), README de padrão industrial com badges do shields.io, CHANGELOG no formato Keep a Changelog e rastreabilidade entre documentação, fichas técnicas e código. Use ao criar ou mudar qualquer arquivo .md do repositório, inclusive CLAUDE.md, AGENTS.md, CHANGELOG.md e skills.
---

# Documentação do Bike Power Meter

## Padrão

| Regra | Detalhe |
|---|---|
| Idioma | português do Brasil, frases diretas, voz ativa; termos técnicos consagrados em inglês (thread, buffer, devicetree, sysbuild) |
| Identificadores | comandos, arquivos, funções, constantes e símbolos Kconfig em crases, exatamente como no código |
| Nomes | módulos, canais e comandos como no código (`pm_fsm`, `chan_torque`, `$ZERO`); grandezas com o símbolo usual (ω, θ, TE, PS), explicado na primeira vez em cada documento |
| Fabricantes | os componentes eletrônicos têm nome e código; **nenhum fabricante de medidor de potência** é citado em lugar nenhum do repositório (regra do dono) |
| Diagramas | sempre Mermaid; **nunca** ASCII, caracteres de caixa, árvores indentadas ou setas desenhadas em bloco de texto |
| Tabelas | para dados estruturados: pinos, constantes, status do firmware, comandos, orçamento de consumo |
| Verdade | todo fato conferido no código, no build ou na placa; o que não foi testado é dito como pendente ("não testado na placa"); nada rodou em hardware até agora |
| Origem | ao citar uma fórmula, uma constante ou um registrador, diga de onde vem (`docs/06`, seção; a ficha com a página, como SBAS501D 8.3.6; a especificação CPS 1.1) e onde está no código (`zephyr_app/...`) |
| Links | relativos entre documentos; âncoras em minúsculas com acentos preservados |

## Estrutura de um documento

1. `# Título` e um parágrafo que diz o que o documento cobre.
2. Em documento longo, uma linha **Nesta página:** com links para as seções.
3. Seções com diagrama onde ele explica melhor que o texto.
4. Verificação ou referências no fim, quando fizer sentido.

## Estrutura de um README (padrão industrial)

1. Bloco centralizado (`<div align="center">`) com título, subtítulo em negrito e badges.
2. Parágrafo de apresentação e alerta do GitHub (`> [!WARNING]`, `> [!IMPORTANT]`) quando houver risco ou estado importante.
3. Índice.
4. Visão geral com diagrama.
5. Funcionalidades em tabela, com o estado de cada uma no port.
6. Início rápido com pré-requisitos e comandos.
7. Estrutura em diagrama.
8. Documentação em tabela.
9. Estado e próximos passos.
10. Créditos e licença (a do projeto ainda está em aberto com o dono, e o README diz isso; a de cada terceiro fica registrada onde ele entra, e o material do ANT+ nunca entra).

Badges estáticos do shields.io: `https://img.shields.io/badge/<rótulo>-<mensagem>-<cor>?logo=<slug>&logoColor=white`. Codifique espaço como `%20`, `-` como `--`, `+` como `%2B`, `:` como `%3A` e acentos em UTF-8 (`ç` = `%C3%A7`, `ã` = `%C3%A3`, `é` = `%C3%A9`). Não use badges de workflow: o CI está desligado (só roda à mão).

## Mermaid

| Para | Tipo |
|---|---|
| blocos, camadas, topologia, estrutura de pastas | `flowchart` com `subgraph` |
| processos e decisões | `flowchart TD` |
| troca de mensagens, protocolos BLE/ANT+, boot entre componentes | `sequenceDiagram` |
| máquinas de estado (sistema, carga, calibração) | `stateDiagram-v2` |
| estruturas de dados | `classDiagram` |
| roteiros com datas | `gantt` ou `timeline` |
| proporções e números simples | `pie`, `xychart-beta` |

- Evite `block-beta`, `packet-beta`, `architecture-beta`, `sankey` e C4: o GitHub pode não renderizar.
- Rótulos com parênteses, barras, dois-pontos, colchetes ou acentos vão entre aspas: `A["Texto (x/y)"]`.
- Quebra de linha com `<br/>`; em `stateDiagram-v2`, use `note` em vez de `<br/>` nas transições.
- IDs de nó em ASCII sem espaços; nunca `end` como ID.
- Um diagrama por ideia, até cerca de 40 nós.
- Cores só com significado: `classDef done fill:#2e7d32,color:#ffffff`, `classDef partial fill:#f9a825,color:#000000`, `classDef pending fill:#ef6c00,color:#ffffff`, `classDef missing fill:#c62828,color:#ffffff`.
- A placa e o pod não são diagramas: use os PDF, as vistas e os STL que os geradores de `hardware_powermeter/` produzem, e as imagens em `docs/img/`.

## Validar antes de entregar ou commitar

Roda no Windows, sem servidor: o `mermaid_check.py` usa o mermaid-cli que já está no cache do npx (`%LOCALAPPDATA%\npm-cache\_npx\...\@mermaid-js\mermaid-cli`) e o Chrome headless do puppeteer. Não instala nada.

```sh
python tools/docs/mermaid_check.py      # extrai, procura diagramas em texto puro e renderiza cada bloco
python tools/docs/links_check.py        # links relativos e âncoras
```

- Espere `rendered N of N` e nenhuma linha `plain-text diagram suspected`; `broken: 0` nos links.
- Os `.mmd` e `.svg` ficam em `build/docs/mermaid/` (ignorado pelo git). Para olhar um diagrama, abra o `.svg` gerado.
- Se o mermaid-cli sumir do cache, `npx -y @mermaid-js/mermaid-cli -V` baixa de novo (pergunte ao dono antes: é um download).
- Os scripts ignoram `tools/`, as pastas `build*/`, `docs/historico/` e `hardware_powermeter/datasheets/` (as fichas não entram no repositório); as skills em `.claude/skills/` entram na conferência.

## Onde cada assunto mora

| Assunto | Arquivo |
|---|---|
| visão geral do projeto | `README.md` |
| contexto para IA | `CLAUDE.md`, `AGENTS.md`, `.claude/skills/` |
| histórico de mudanças | `CHANGELOG.md` |
| índice da documentação | `docs/README.md` |
| o que é o medidor, a decisão de arquitetura, as fases | `docs/01-visao-geral.md` |
| blocos da placa, mapa de pinos (a fonte única do devicetree e do esquemático), consumo, pod | `docs/02-hardware.md` |
| ambiente, build, gravação, números de referência | `docs/03-ambiente-build.md` |
| serviços, canais, máquinas de estado, drivers, atualização, pilhas, testes | `docs/04-arquitetura-firmware.md` |
| BLE Cycling Power, ANT+ Bicycle Power, serviço de configuração, comandos `$...` | `docs/05-protocolos.md` |
| ponte, amostragem, cadência, zero, inclinação, temperatura, saúde | `docs/06-medicao-e-calibracao.md` |
| o que existe, o que falta, o que não foi testado | `docs/07-status.md` |
| lista fechada de componentes | `hardware_powermeter/01-lista-de-componentes.md` |
| esquemático, placa, pod, geradores e dry runs | `hardware_powermeter/README.md` e os documentos numerados ao lado |
| os conjuntos de testes de host | `zephyr_app/tests/host/README.md` |

Quando o comportamento muda, o documento muda **junto** com o código, e o `CHANGELOG.md` ganha uma linha em `[Não lançado]`. Quando um item do firmware ou do hardware muda de estado, atualize a matriz de `docs/07-status.md` e a seção "Estado" do `CLAUDE.md`.
