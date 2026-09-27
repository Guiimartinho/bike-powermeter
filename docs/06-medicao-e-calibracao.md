# Medição e calibração

Como o módulo transforma a deformação do braço do pedivela em watts, e como cada constante do caminho é obtida e mantida. Todas as fórmulas daqui são as que o firmware implementa em `zephyr_app/src/model/`, com testes de host.

**Nesta página:** [Da ponte ao torque](#da-ponte-ao-torque) · [Amostragem](#amostragem) · [Ângulo e cadência](#ângulo-e-cadência) · [Potência por volta](#potência-por-volta) · [Calibração](#calibração) · [Temperatura](#temperatura) · [Orçamento de erro](#orçamento-de-erro) · [Saúde do sensor](#saúde-do-sensor) · [Referências](#referências)

## Da ponte ao torque

A ponte completa de quatro grades, duas esticando e duas comprimindo, entrega uma tensão diferencial proporcional à deformação, com a temperatura e as forças fora do eixo canceladas [1, 2.1.4]. Medida de forma ratiométrica, com a excitação da ponte na referência do conversor, o código de saída é proporcional a ΔR/R e independe da tensão de excitação [1, 3.1]:

```mermaid
flowchart LR
    F["Força no pedal F"] --> E["Deformação ε = k1 · F"]
    E --> V["Vout = Vexc · GF · ε"]
    V --> C["Código = 2^23 · ganho · Vout / Vref"]
    C --> T["τ = s · (código − zero)"]
```

Com `Vref = Vexc`, o código não depende de `Vexc`, e o firmware trabalha com uma única constante de inclinação `s` (N·m por contagem) e um zero, ambos calibrados:

`τ = s(T) · (c − c0(T))`

onde `c` é o código do ADS1220 (24 bits, complemento de dois, PGA 128), `c0` o zero e `s` a inclinação, os dois corrigidos pela temperatura `T` da ponte ([Temperatura](#temperatura)).

**Escala.** A 200 W e 90 rpm o torque médio é 21 N·m; o pico numa pedalada forte passa de 100 N·m. Com extensômetros de fator 2 num braço de alumínio, a deformação de trabalho fica na casa de algumas centenas de µε, ou seja, 1 a 3 mV de saída da ponte a 3,0 V. Com ganho 128 o fundo de escala do conversor é ±23 mV, então sobra margem para o pico e para o zero deslocado pela colagem. A resolução sem ruído do sistema se calcula como em [1, 5.2.2]: com 2 mV de faixa útil e 1,6 µV pico a pico de ruído a 175 SPS (SBAS501D), são 2 mV / 1,6 µV ≈ 1250 contagens sem ruído por amostra, 0,08 % do fundo de escala, antes da média da volta, que divide isso por mais de dez.

## Amostragem

| Parâmetro | Valor | Motivo |
|---|---|---|
| Taxa da ponte | 175 amostras/s, modo normal do ADS1220 | a 120 rpm são 2 voltas/s, 87 amostras por volta; a pedalada tem conteúdo até cerca de 10 vezes a cadência (20 Hz), longe dos 87 Hz de Nyquist |
| Filtro | o sinc do próprio conversor; mediana de 3 contra pulsos; **nenhum passa-baixas** além disso | um passa-baixas achata o pico de torque e muda a média da volta por pouco, mas muda a efetividade e a suavidade por muito |
| Excitação | ligada 1,5 ms antes de cada conversão, desligada no DRDY | o TPS22916 liga em microssegundos; o filtro RC de entrada (datasheet do ADS1220, 9.1.2) assenta em menos de 1 ms |
| Acelerômetro | 100 Hz, ±4 g, modo normal, OSR 0 | o vetor gravidade gira a 2 Hz no máximo; 100 Hz dão 50 pontos por volta para o ângulo; ±4 g cobre a aceleração centrípeta (ω²r com r de 50 mm a 200 rpm é 22 m/s², 2,2 g) |
| Temperatura | 1 Hz | a ponte muda de temperatura em minutos, não em segundos |
| Relógio | uptime do kernel, 1 ms; eventos de volta com resolução de 1/1024 s como o BLE pede | |

Os dois fluxos (ponte e acelerômetro) são carimbados com o mesmo relógio e casados pelo carimbo, não pela ordem de chegada.

## Ângulo e cadência

O acelerômetro está fixo ao braço, no plano de rotação. Os dois eixos no plano leem a gravidade girando mais os termos do movimento:

```latex
a_t = g\,\sin\theta + \alpha r, \qquad a_r = g\,\cos\theta + \omega^{2} r
```

com `θ` o ângulo do braço a partir da vertical, `r` a distância do sensor ao eixo, `ω` a velocidade angular e `α` a aceleração angular. O firmware (`crank_angle`) tira cada grandeza do eixo que é limpo para ela. A velocidade angular vem dos **cruzamentos de zero de `a_t`**, que acontecem no alto e no baixo da pedalada seja qual for o termo centrípeto: meia volta entre dois cruzamentos, com o instante de cada cruzamento interpolado entre as duas amostras em volta dele (a 100 Hz, sem interpolação, a quantização sozinha dava ±3 % a 90 rpm). O ângulo vem de `atan2(−a_t, a_r − ω²r)` com esse `ω`; quando `ω` muda num cruzamento, o ângulo da amostra anterior é recalculado com o `ω` novo, para que o `Δθ` que a potência integra não pule. Um cruzamento distingue alto de baixo pelo sinal do eixo radial corrigido e o sentido pelo lado por que `a_t` cruzou; a volta é o baixo passado para a frente; pedalar para trás dá `ω` negativo e nenhuma volta. Histerese de 0,5 m/s² arma um cruzamento; dois cruzamentos mais próximos que o pedivela mais rápido permite (`π/ω_max`) são ruído; 2 s sem cruzamento é `ω = 0`. A cadência é `60·ω/2π`; o tempo do evento vai em 1/1024 s ao rádio. Antes desse estimador, o `ω` era a derivada de `θ`: a derivada do `atan2` carregava o erro do termo centrípeto para dentro de `ω`, e a 100 Hz o teste sintético a 90 rpm devolvia 4 voltas em 10 s.

Regras de validade: uma amostra que implicaria `|Δθ/Δt| > 25 rad/s` (240 rpm) é descartada inteira e o ângulo anterior fica; parado quando o módulo da aceleração fica dentro de ±10 % de `g` por 2 s e `ω` abaixo de 0,3 rad/s; enquanto parado, nenhuma volta é publicada e o zero pode ser revisto ([Calibração](#calibração)). A posição do sensor `r` entra na configuração e é medida na placa, não estimada.

## Potência por volta

A potência é a média, na volta, do produto torque × velocidade angular:

```latex
P = \frac{1}{T}\int_{0}^{T}\tau(t)\,\omega(t)\,dt \approx \frac{1}{T}\sum_{i}\tau_i\,\Delta\theta_i
```

Somar `τ_i Δθ_i` (o trabalho por amostra) e dividir pelo período é o que faz a estimativa não depender de a cadência variar dentro da volta, que ela varia: o torque cai perto dos pontos mortos e a velocidade angular junto [3]. Numa volta com 87 amostras a soma é a integral por retângulos, com erro de segunda ordem.

| Grandeza | Como sai da volta | Unidade que o rádio usa |
|---|---|---|
| Potência instantânea | `P` acima; com um lado só, `2·P` | W |
| Torque acumulado | soma de `τ_médio · 1` por volta | 1/32 N·m |
| Energia acumulada | soma de `P · T` | kJ |
| Voltas e tempo do último evento | contador e carimbo | 1/1024 s |
| Balanço esquerda/direita | 50 % declarado, "referência desconhecida", com um lado só | % |
| Efetividade do torque | `(W⁺ + W⁻) / W⁺ · 100`, com `W⁺` o trabalho dos trechos de torque positivo e `W⁻` o dos negativos (negativo) | % |
| Suavidade da pedalada | `P_média / P_pico · 100` na volta | % |

As duas últimas são as definições que os dois protocolos usam; a literatura chama a primeira de índice de efetividade da força e mede o mesmo trabalho útil sobre o total [4, 5]. Com um lado só, dobrar a potência assume simetria; a assimetria entre as pernas medida em ciclistas fica em geral abaixo de 5 % e cresce com a intensidade [6], o que entra no orçamento de erro.

## Calibração

Três constantes, três procedimentos, todos disparados pelo BLE ([05](05-protocolos.md)) e conduzidos pela tela do ciclocomputador ou por um app:

1. **Zero** (`c0`). Braço na vertical, sem carga, módulo parado. O firmware exige estabilidade: 64 amostras com desvio padrão abaixo de 4 contagens e média fora de ±20 % do fundo de escala (senão a ponte está aberta, em curto ou saturada). O zero também é revisto sozinho a cada parada de mais de 5 s, com a mesma regra, e só substitui o anterior se mudou menos que um limite configurado (auto-zero conservador): uma parada com o pé no pedal não pode virar zero.
2. **Inclinação** (`s`). Braço na horizontal, massa conhecida `m` pendurada no eixo do pedal, a `L` do centro do eixo: `τ = m · g · L · cos φ`, com `φ` o desvio da horizontal medido pelo próprio acelerômetro. Três a cinco massas (5 a 20 kg) e um ajuste por mínimos quadrados de `τ` contra `c − c0`; o firmware devolve a inclinação, o resíduo máximo e a histerese (subida contra descida). Resíduo acima de 0,5 % ou histerese acima de 0,3 % reprovam a colagem, não o firmware. É o método estático de calibração de células de carga [7, 8], aplicado com o braço como célula.
3. **Temperatura**. Zero e inclinação repetidos em três ou mais temperaturas entre −10 e 50 °C (câmara, congelador, sol), lidas pelo TMP117 junto da ponte; o ajuste dá `c0(T)` de segunda ordem e `s(T)` de primeira ([Temperatura](#temperatura)).

A verificação é a prova de estrada: rolo e rua contra um medidor de referência, por semanas, comparando potência média por intervalo e a distribuição da diferença; o critério da fase 1 é ±2 % na média de 1 minuto.

## Temperatura

A ponte completa cancela a dilatação comum das quatro grades, mas sobram o coeficiente do adesivo, a diferença entre a dilatação do alumínio e a compensação do extensômetro, a deriva do próprio conversor e a mudança do módulo de elasticidade do braço com a temperatura [1, 4.7; 2]. O modelo do firmware:

```latex
c_0(T) = c_0 + k_1\,(T - T_0) + k_2\,(T - T_0)^2, \qquad s(T) = s\,[1 + k_3\,(T - T_0)]
```

com `T0` a temperatura da calibração de inclinação. Os coeficientes vêm do procedimento 3; sem eles o firmware usa `k = 0` e declara na característica de recursos que a compensação não está calibrada. O sensor de temperatura interno do ADS1220 (0,5 °C) serve de reserva se o TMP117 faltar.

## Orçamento de erro

Contribuições na potência, a 200 W, estimadas como incertezas-padrão e somadas em quadratura, no espírito do guia GUM [9]:

| Fonte | Contribuição | Como se reduz |
|---|---|---|
| Massa de calibração | 0,1 % (massa aferida) | balança de referência |
| Comprimento do braço `L` | 0,3 % (0,5 mm em 172,5) | medir com paquímetro; gravar na configuração |
| Ângulo na calibração | 0,1 % (cos φ com φ < 2,5°) | o acelerômetro mede φ |
| Resíduo da temperatura | 0,5 % (residual depois da curva) | mais pontos de temperatura |
| Ruído do conversor | < 0,05 % na média da volta | nenhum |
| Tempo da volta | 0,1 % (1/1024 s em 0,67 s) | nenhum |
| Fluência da colagem | 0,3 % | AE-10, cura completa, verificação periódica do zero |
| Assimetria das pernas (um lado só) | 2 a 5 %, sistemático por ciclista | dois módulos (fase 1b) |
| **Total sem assimetria** | **≈ 0,7 %** | |

O que decide os ±2 % da fase 1 é, portanto, a assimetria, que o produto de um lado só não corrige; a medição em si tem margem.

## Saúde do sensor

Verificações contínuas, publicadas nas características de estado e no log:

As regras são as do módulo `health`, cada uma com o seu flag; as quatro primeiras e a última **param a medição** (nenhuma potência é publicada), as outras são avisos:

| Flag | Regra | Para? |
|---|---|---|
| `BRIDGE_OPEN` | código em ±80 % do fundo de escala ou além, com a excitação ligada (entrada no trilho: ponte aberta ou saturada) | sim |
| `BRIDGE_STUCK` | o mesmo código por 2 s com a excitação ligada (ponte em curto ou entrada presa) | sim |
| `EXCITATION` | a referência lida pelo monitor interno do ADS1220 fora de 3,0 V ± 10 % | sim |
| `IMU_STALE` | acelerômetro sem amostra por 500 ms | sim |
| `NOT_CALIBRATED` | inclinação desconhecida | sim |
| `IMU_RANGE` | módulo da aceleração fora de 0,5 a 6 g por mais de 1 s | não |
| `TEMP_RANGE` | temperatura da ponte fora de −20 a 70 °C | não |
| `ZERO_DRIFT` | zero em uso mais longe do zero da calibração que o passo do auto-zero: aviso de recalibrar | não |

Com a excitação desligada nada da ponte é julgado (o código de uma ponte sem excitação é zero, sã ou não): o que se lê nesse estado é o ruído do conversor, e é o monitor da referência que diz se a excitação existe.

## Referências

1. TEXAS INSTRUMENTS. *A Basic Guide to Bridge Measurements*, nota de aplicação SBAA532A. Seções 2.1.4 (ponte com quatro elementos ativos), 3.1 (medição ratiométrica), 4.7 (deriva), 5.2.2 (contagens sem ruído), 5.5 (calibração de offset e ganho). [ti.com/lit/an/sbaa532a/sbaa532a.pdf](https://www.ti.com/lit/an/sbaa532a/sbaa532a.pdf)
2. MICRO-MEASUREMENTS. *Stress Analysis Gage Reference Guide*: seleção de série, autocompensação térmica, resistência de 1 kΩ, adesivos M-Bond 200 e AE-10, proteções. [docs.micro-measurements.com/?id=18236](https://docs.micro-measurements.com/?id=18236)
3. *Interpretation of crank torque during an all-out cycling exercise at high pedal rate*. Sports Engineering, 2010. [doi:10.1007/s12283-010-0051-2](https://doi.org/10.1007/s12283-010-0051-2)
4. *Effect of Gear Ratio and Cadence on Gross Efficiency and Pedal Force Effectiveness during Multistage Graded Cycling Test Using a Road Racing Bicycle*. Sports, 2022. [doi:10.3390/sports11010005](https://doi.org/10.3390/sports11010005)
5. *Within- and between-session reliability of a pedal force system for power output and pedal force effectiveness measurements*. Human Movement, 2020. [doi:10.5114/hm.2020.94197](https://doi.org/10.5114/hm.2020.94197)
6. *Effects of Exercise Intensity on Pedal Force Asymmetry during Cycling*. Symmetry, 2021. [doi:10.3390/sym13081449](https://doi.org/10.3390/sym13081449)
7. NIST. *Automation of strain-gauge load-cell force calibration*, NISTIR 4823, 1992. [doi:10.6028/nist.ir.4823](https://doi.org/10.6028/nist.ir.4823)
8. BSI. *Force measurement. Strain gauge load cell systems. Calibration method*. [doi:10.3403/02919794](https://doi.org/10.3403/02919794)
9. JCGM 100:2008. *Evaluation of measurement data. Guide to the expression of uncertainty in measurement (GUM)*. [bipm.org](https://www.bipm.org/en/committees/jc/jcgm/publications)
10. *Determining the Stress Distribution in a Bicycle Crank Under In-Service Loads*. Experimental Techniques, 2015. [doi:10.1111/ext.12141](https://doi.org/10.1111/ext.12141): onde o braço deforma sob carga de pedalada, o que orienta a posição dos extensômetros.
11. TEXAS INSTRUMENTS. *ADS1220 datasheet*, SBAS501D. Bluetooth SIG, *Cycling Power Service 1.1*. Bosch, *BMA400 datasheet* BST-BMA400-DS000-14.

Os artigos 3 a 6 e 10 foram localizados pelo Crossref em 2026-09-27 (título, revista, ano e DOI conferidos); o texto completo não foi lido nesta sessão, e as definições usadas acima são as dos protocolos e das notas de aplicação.
