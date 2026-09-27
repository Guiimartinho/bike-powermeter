# Protocolos

- BLE Cycling Power Service 1.1 (servidor escrito no projeto; o Zephyr traz só os UUIDs): Measurement, Feature, Sensor Location, Control Point, Vector.
- ANT+ Bicycle Power (transmissor): o add-on `sdk-ant` traz o perfil `ant_bpwr` com as páginas 1, 16, 17, 18, 80 e 81 e o exemplo `bpwr_tx`; o material ANT+ fica fora do repositório.
- Serviço de configuração do projeto (GATT próprio): inclinação, curva de temperatura, lado, modelo do pedivela, taxa de amostragem.
