---
name: docs-pm
description: Escrever, atualizar e validar a documentação do Bike Power Meter no padrão do projeto - português do Brasil, diagramas Mermaid (nunca diagramas em texto puro), README de padrão industrial com badges do shields.io, CHANGELOG no formato Keep a Changelog e rastreabilidade legacy x port. Use ao criar ou mudar qualquer arquivo .md do repositório, inclusive CLAUDE.md, AGENTS.md, CHANGELOG.md e skills.
---

# Documentação do Bike Power Meter

## Padrão

| Regra | Detalhe |
|---|---|
| Idioma | português do Brasil, frases diretas, voz ativa; termos técnicos consagrados em inglês (thread, buffer, devicetree, sysbuild) |
| Identificadores | comandos, arquivos, funções, constantes e símbolos Kconfig em crases, exatamente como no código |
| Nomes em francês do legacy | mantidos como no código (`Boucle`, `Parcours`, `ListePoints`, `Vecteur`, `Vue`); o glossário está em `docs/04-arquitetura-legacy.md` |
| Diagramas | sempre Mermaid; **nunca** ASCII, caracteres de caixa, árvores indentadas ou setas desenhadas em bloco de texto |
| Tabelas | para dados estruturados: pinos, constantes, status do port, comandos |
| Verdade | todo fato conferido no código, no build ou na placa; o que não foi testado é dito como pendente ("não testado na placa") |
| Legacy × port | ao citar um algoritmo, diga de onde vem (`legacy/...:linha`) e onde está no port (`zephyr_app/...`), com as diferenças |
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
10. Créditos e licenças (o legacy é CC BY-NC 4.0; ver `legacy/README.md`).

Badges estáticos do shields.io: `https://img.shields.io/badge/<rótulo>-<mensagem>-<cor>?logo=<slug>&logoColor=white`. Codifique espaço como `%20`, `-` como `--`, `+` como `%2B`, `:` como `%3A` e acentos em UTF-8 (`ç` = `%C3%A7`, `ã` = `%C3%A3`, `é` = `%C3%A9`). Não use badges de workflow: o CI está desligado (só roda à mão).

## Mermaid

| Para | Tipo |
|---|---|
| blocos, camadas, topologia, estrutura de pastas | `flowchart` com `subgraph` |
| processos e decisões | `flowchart TD` |
| troca de mensagens, protocolos BLE/ANT+, boot entre componentes | `sequenceDiagram` |
| máquinas de estado (GPS, segmento, modos) | `stateDiagram-v2` |
| estruturas de dados | `classDiagram` |
| roteiros com datas | `gantt` ou `timeline` |
| proporções e números simples | `pie`, `xychart-beta` |

- Evite `block-beta`, `packet-beta`, `architecture-beta`, `sankey` e C4: o GitHub pode não renderizar.
- Rótulos com parênteses, barras, dois-pontos, colchetes ou acentos vão entre aspas: `A["Texto (x/y)"]`.
- Quebra de linha com `<br/>`; em `stateDiagram-v2`, use `note` em vez de `<br/>` nas transições.
- IDs de nó em ASCII sem espaços; nunca `end` como ID.
- Um diagrama por ideia, até cerca de 40 nós.
- Cores só com significado: `classDef done fill:#2e7d32,color:#ffffff`, `classDef partial fill:#f9a825,color:#000000`, `classDef pending fill:#ef6c00,color:#ffffff`, `classDef missing fill:#c62828,color:#ffffff`.
- Layout de tela do LCD não é diagrama: descreva em tabela (linha, coluna, campo, unidade) ou use a imagem em `docs/img/`.

## Validar antes de entregar ou commitar

Roda no Windows, sem servidor: o `mermaid_check.py` usa o mermaid-cli que já está no cache do npx (`%LOCALAPPDATA%\npm-cache\_npx\...\@mermaid-js\mermaid-cli`) e o Chrome headless do puppeteer. Não instala nada.

```sh
python tools/docs/mermaid_check.py      # extrai, procura diagramas em texto puro e renderiza cada bloco
python tools/docs/links_check.py        # links relativos e âncoras
```

- Espere `rendered N of N` e nenhuma linha `plain-text diagram suspected`; `broken: 0` nos links.
- Os `.mmd` e `.svg` ficam em `build/docs/mermaid/` (ignorado pelo git). Para olhar um diagrama, abra o `.svg` gerado.
- Se o mermaid-cli sumir do cache, `npx -y @mermaid-js/mermaid-cli -V` baixa de novo (pergunte ao dono antes: é um download).
- Os scripts ignoram `legacy/`, `libraries/`, `tools/`, `hardware/` e `docs/historico/` (material de terceiros ou arquivado).

## Onde cada assunto mora

| Assunto | Arquivo |
|---|---|
| visão geral do projeto | `README.md` |
| contexto para IA | `CLAUDE.md`, `AGENTS.md`, `.claude/skills/` |
| histórico de mudanças | `CHANGELOG.md` |
| índice da documentação | `docs/README.md` |
| produto e modos | `docs/01-visao-geral.md` |
| placa, pinagem, alimentação | `docs/02-hardware.md` |
| ambiente, build, gravação | `docs/03-ambiente-build.md` |
| firmware original (stravaV10) | `docs/04-arquitetura-legacy.md` |
| port Zephyr | `docs/05-arquitetura-zephyr.md` |
| algoritmos e constantes | `docs/06-algoritmos.md` |
| rádio (ANT+, BLE, stravaAP, Komoot) | `docs/07-radio-ant-ble.md` |
| interface (telas, menus, botões) | `docs/08-interface.md` |
| arquivos no SD, USB | `docs/09-armazenamento-usb.md` |
| status do port e roteiro | `docs/10-status-do-port.md` |
| qualidade, MISRA, análise estática | `docs/11-qualidade-misra.md` |
| ferramentas e testes | `docs/12-ferramentas-testes.md` |
| proposta da placa nova | `docs/13-placa-nova.md` |
| especificação de hardware da placa nova | `docs/14-hardware-placa-nova.md` |
| avaliação dos componentes da placa nova | `docs/15-avaliacao-componentes.md` |
| arquitetura do firmware e máquinas de estado da placa nova | `docs/16-arquitetura-firmware.md` |
| catálogo de dispositivos BLE e ANT+ | `docs/17-dispositivos-ble-ant.md` |
| interface e telas da placa nova (imagens por `tools/ui/render_screens.py`) | `docs/18-interface-telas.md` |
| os 44 quadros da interface, um a um, com o que cada um mostra | `docs/telas/README.md` (as imagens são geradas; o texto, não) |
| lista de compras da placa nova, validada em duas passagens | `docs/19-lista-de-compras.md` |
| código herdado | `legacy/README.md` |

Quando o comportamento muda, o documento muda **junto** com o código, e o `CHANGELOG.md` ganha uma linha em `[Não lançado]`. Quando um item do port muda de estado, atualize a matriz de `docs/10-status-do-port.md` e a seção "Estado" do `CLAUDE.md`.
