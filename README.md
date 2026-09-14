# Monitor Ambiental com ESP32

Protótipo de nó sensor IoT para monitoramento de condições ambientais de cultivo, desenvolvido para a disciplina de Tópicos em Sistemas Computacionais — UFPI.

---

## Objetivo

Construir um dispositivo capaz de medir temperatura, umidade relativa do ar e luminosidade de um ambiente, sinalizar localmente condições fora da faixa desejada por meio de LEDs indicadores, e expor os dados em formato estruturado para consumo posterior.

---

## Hardware

### Microcontrolador

**ESP32 DevKit V1 (módulo ESP32-WROOM-32)**

### Sensores

**DHT11 — temperatura e umidade relativa**

**LDR (fotoresistor) — luminosidade**

### Atuadores

Três LEDs indicadores sinalizam o estado ambiental sem depender de conexão de rede: um para temperatura fora da faixa, um para umidade abaixo do mínimo, e um para baixa luminosidade.

---

## Dimensionamento elétrico

### Limitação de corrente nos LEDs

Cada LED é acionado através de um resistor em série, dimensionado pela lei de Ohm a partir da tensão direta do diodo:

```
R = (V_fonte − V_f) / I_desejada
R = (3,3 − 2,0) / 0,006 ≈ 216 Ω  →  valor comercial: 220 Ω
```

A corrente resultante de aproximadamente 5,9 mA fica bem abaixo dos 12 mA recomendados por GPIO no ESP32, e muito distante do limite absoluto de 40 mA especificado no datasheet.

### Orçamento de corrente

| Componente | Corrente |
|---|---|
| ESP32 (CPU ativa, rádio desligado) | ~45 mA |
| DHT11 | ~1,5 mA |
| Divisor do LDR | ~0,3 mA |
| 3 LEDs simultâneos | ~16 mA |
| **Total (pior caso)** | **~63 mA** |

O consumo representa cerca de 13 % da capacidade de 500 mA de uma porta USB 2.0. Com o rádio Wi-Fi ativo, os picos de transmissão elevam o consumo para aproximadamente 310 mA, ainda dentro da margem disponível.

Para operação autônoma por bateria, o modo *deep sleep* do ESP32 (consumo da ordem de 10 µA) reduz o consumo médio em várias ordens de grandeza, viabilizando meses de autonomia com duas transmissões diárias.

---

## Firmware

Desenvolvido em C++ sobre o framework Arduino, com PlatformIO no VSCode como ambiente de build.

### Estrutura

```
FitoSfera/
├── platformio.ini
└── src/
    └── main.cpp
```

### Configuração

```ini
[env:esp32doit-devkit-v1]
platform = espressif32
board = esp32doit-devkit-v1
framework = arduino
monitor_speed = 115200
lib_deps =
    adafruit/DHT sensor library@^1.4.6
    adafruit/Adafruit Unified Sensor@^1.1.14
```

### Decisões de implementação

**Temporização não bloqueante.** O controle de intervalo entre leituras usa comparação sobre `millis()` em vez de `delay()`. A chamada bloqueante congela o processador por completo, impedindo qualquer outra tarefa. Como a evolução prevista inclui gerenciamento de conexão Wi-Fi e tratamento de eventos, a abordagem não bloqueante evita a reescrita do laço principal.

**Tratamento de falha de leitura.** O DHT11 retorna `NaN` em caso de falha de comunicação, ocorrência esperada em uma fração das leituras. A verificação por `isnan()` impede a propagação de valores inválidos, e a falha de um sensor não interrompe o reporte dos demais.

---

## Metodologia de construção

A montagem seguiu validação incremental, com cada camada testada isoladamente antes da integração:

1. Verificação da cadeia de compilação e gravação (blink no LED interno)
2. Validação da comunicação serial
3. LED externo individual, com verificação do dimensionamento do resistor
4. Leitura analógica do divisor do LDR
5. Leitura do DHT11 isolada
6. Integração completa com lógica de limiares

---

## Limitações reconhecidas

**Precisão do DHT11.** A resolução de 1 °C e 1 %, com incerteza de ±2 °C, é adequada para detecção de tendências mas insuficiente para caracterização fina de microclima. O DHT22 ou o BME280 são substitutos pino-compatíveis quando maior precisão for necessária.

**Ausência de referência temporal absoluta.** O dispositivo registra tempo relativo desde a inicialização. A correlação com horário real depende de sincronização NTP, prevista para a etapa de conectividade.

**Sensor de luminosidade será substituído.** Atualmente, o projeto responde apenas uma booleana: está escuro ou não? Mas ao longo do projeto, é interessante adicionar a detecção contínua de medidas de luminosidade para determinar intervalos de claridade.

**Não linearidade do ADC.** O conversor do ESP32 apresenta desvio significativo nas extremidades da faixa. O uso de `analogReadMilliVolts()`, que aplica a curva de calibração gravada de fábrica, mitiga parcialmente o problema, mas leituras próximas dos extremos permanecem menos confiáveis.

---

## Próximas etapas

Transmissão periódica via Wi-Fi com o dispositivo em *deep sleep* entre as medições; persistência do histórico em backend; e desenvolvimento da camada de recomendação por espécie vegetal no aplicativo móvel.
