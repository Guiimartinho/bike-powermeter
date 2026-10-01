# Visão geral

O Bike Power Meter é um medidor de potência para bicicleta de código aberto, par do [GNSS Bike Computer](https://github.com/Guiimartinho/gnss-bike-computer): mesma base de firmware (Zephyr, nRF Connect SDK v3.3.0, BLE e ANT+; o ciclocomputador no nRF54LM20A, o medidor no nRF54L15), mesma cadeia de CAD gerada por script e conferida por dry run, e o ciclocomputador como banco de teste e como configurador.

**Nesta página:** [O que mede](#o-que-mede) · [Decisão](#decisão) · [Fases](#fases) · [A classe de produto](#a-classe-de-produto) · [Estado](#estado)

## O que mede

Potência é torque vezes velocidade angular. O torque vem de uma ponte de extensômetros colada na peça que transmite a força; a velocidade angular vem de um acelerômetro, pelo giro do vetor gravidade. O módulo amostra a ponte dezenas de vezes por volta, faz a média da volta e envia a potência por BLE (Cycling Power Service) e ANT+ (Bicycle Power).

| Grandeza | Como |
|---|---|
| Torque | Ponte completa de extensômetros de 5 kΩ, excitação chaveada de 3,0 V, conversor ADS1220 com ganho 128 e referência ratiométrica |
| Cadência e ângulo | BMA400 |
| Temperatura da ponte | TMP117, curva de compensação levantada uma vez |
| Potência | Média do torque na volta × velocidade angular; um lado × 2 na fase 1 |
| Calibração | Zero sem carga (auto-zero) e inclinação por massa pendurada com o braço na horizontal |

## Decisão

Fase 1 é um **módulo no braço esquerdo do pedivela que já existe**, o formato mais comum entre os produtos comerciais dessa classe: sem usinagem, aproveitando tudo do ciclocomputador. O pedal (eixo usinado com a eletrônica dentro) é a fase 2, com a mesma placa encolhida e o mesmo firmware.

```mermaid
flowchart LR
    F1["Fase 1<br/>módulo no braço esquerdo<br/>placa + pod + firmware"] --> V["Validação<br/>bancada com massas<br/>rua contra referência"]
    V --> F2["Fase 2<br/>eixo de pedal usinado<br/>mesma placa encolhida"]
    F1 -.-> CC["Ciclocomputador<br/>pareia, configura, calibra"]
```

A lista fechada de componentes, com o datasheet de cada peça, está em [`../hardware_powermeter/01-lista-de-componentes.md`](../hardware_powermeter/01-lista-de-componentes.md).

## Fases

1. Braço usado, extensômetros, ADS1220 em placa de avaliação e o nRF54LM20 DK: bancada com massas de 5 a 20 kg, linearidade, histerese e deriva.
2. Firmware em Zephyr com a estrutura do ciclocomputador: serviços de amostragem, cadência, cálculo, rádio, energia e porta serial; servidor BLE Cycling Power escrito no projeto; ANT+ pelo perfil `ant_bpwr` do add-on, fora do repositório.
3. Prova no rolo e na rua contra um medidor de referência, por semanas, até ±2 %.
4. Placa própria, pod impresso e envasado, conector magnético de carga, porta serial e SWD.
5. Fase 2: eixo de pedal.

## A classe de produto

O piso deste projeto é o que um módulo de braço comercial da mesma classe publica na própria página de produto. Conferido em 2026-09-27, na página do produto, na do irmão de eixo de pedal e nas duas lojas do fabricante:

| O que a classe publica | Requisito deste projeto |
|---|---|
| 20 g com bateria | ≤ 20 g; o pod desenhado está em 17,0 g estimados |
| máximo de 52 h de uso contínuo por carga | ≥ 50 h; com a ponte de 5 kΩ **e o conversor em duty-cycle** são 0,68 mA, e a célula de 81 mAh que cabe no pod dá **119 h** ([02](02-hardware.md#orçamento-de-consumo)) |
| ±2,5 % de precisão | ±2 % na fase 1, ±1,5 % como meta da fase 2 |
| 0 a 2000 W, 10 a 200 rpm | os mesmos |
| −5 a +50 °C | −10 a +50 °C |
| IPX7 | o mesmo |
| ANT+ e BLE | os mesmos |
| bateria LiPo recarregável, carga por USB magnético | os mesmos |

**As dimensões não são publicadas em lugar nenhum**, e isso foi verificado, não suposto: a página do produto, a do outro modelo, a loja e a lista de produtos montados não trazem nenhum número em milímetro. A única medida física publicada é a massa.

### O envelope da classe, medido por fotogrametria

Sem número publicado, as dimensões foram **medidas na foto de imprensa do fabricante** em 2026-09-27, com régua conhecida na própria imagem: o módulo aparece colado num braço Shimano FC-M8100 marcado **170**, e a distância entre o centro do furo do eixo e o do furo do pedal é exatamente 170 mm. Isso dá 0,1319 mm por pixel ao longo do braço. A escala foi conferida por um segundo caminho independente: os dois contatos de carga do módulo medem 19,8 px entre centros, ou seja **2,6 mm**, o passo padrão de 2,5 mm de pino pogo, e a cabeça de cada contato dá 1,3 a 1,6 mm, também padrão.

| Medida | Estimativa | Confiança |
|---|---|---|
| Comprimento ao longo do braço | **37 a 39 mm** | boa: referência de 170 mm na mesma direção, com duas pontas ampliadas e conferidas |
| Largura atravessada | **18 a 22 mm** | média: depende da inclinação do plano, estimada pela elipse do furo do pedal |
| Altura | **9 a 13 mm** | fraca: nenhuma foto tem vista de perfil; o intervalo sai do volume que a massa de 20 g exige |

**O que isso muda:** o alvo de 60 mm de comprimento que este projeto vinha perseguindo já era generoso. A classe faz o mesmo aparelho em **cerca de 38 mm**, quase a metade. Largura e altura do nosso desenho estão na mesma faixa; o comprimento não está. O alvo de [`02-hardware.md`](02-hardware.md#requisitos) passa a ser esse, com a ressalva de que é medida de foto e não de paquímetro: uma unidade medida à mão continua sendo o que fecharia o assunto.

## Estado

2026-09-27: componentes fechados por datasheet; firmware inteiro escrito, compilando nos três alvos com zero avisos e com o modelo testado no PC (134 casos, 99,9 % das linhas), **nunca executado em placa nem no DK**; esquemático, placa e pod gerados por script, **nada fabricado, impresso nem montado**. A matriz item a item está em [`07-status.md`](07-status.md). Licença CC BY-NC 4.0, a mesma do ciclocomputador, embora este projeto não derive de nada: é escolha do dono pela mesma restrição de uso não comercial.
