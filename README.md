# Monitor Ambiental com ESP32

Protótipo de nó sensor IoT para monitoramento de condições ambientais de cultivo, desenvolvido para a disciplina de Tópicos em Sistemas Computacionais — UFPI.

---

## Objetivo

Construir um dispositivo capaz de medir temperatura, umidade relativa do ar e luminosidade de um ambiente, e transmiti-las por Bluetooth Low Energy (BLE) a um aplicativo no celular.

> **Estado atual:** o aplicativo FitoSfera ainda está em desenvolvimento e não consome este dispositivo. O circuito e o firmware foram testados com um **celular Android usando o app nRF Connect**, que lê as características BLE e escreve os comandos à mão. Veja "Estado da validação" abaixo.

---

## Hardware

### Microcontrolador

**ESP32 DevKit V1 (módulo ESP32-WROOM-32)**

### Sensores

**DHT11 — temperatura e umidade relativa** (GPIO18)

**BH1750 (módulo GY-302) — luminosidade em lux**, via I2C (endereço 0x23). Mede de 1 a 65.535 lux no modo padrão; o firmware reduz a sensibilidade (MTreg = 31) para alcançar cerca de 120 mil lux, cobrindo sol pleno. A incerteza declarada pelo fabricante é de ±20 %.

---

## Dimensionamento elétrico

### Orçamento de corrente

O dispositivo fica sempre ligado, com a CPU a 80 MHz e o BLE anunciando ou conectado o tempo todo. Os valores abaixo são estimativas, ainda não medidas no circuito.

| Componente | Corrente |
|---|---|
| ESP32 (CPU a 80 MHz, BLE ativo) | ~35 a 45 mA |
| DHT11 | ~1,5 mA |
| BH1750 | ~0,2 mA |
| **Total estimado** | **~40 a 50 mA** |

Os picos de transmissão BLE ficam em torno de 130 mA, cerca de 26 % da capacidade de 500 mA de uma porta USB 2.0.

**Alimentação.** Nesse regime, uma bateria de 2000 mAh dura menos de 2 dias, então o protótipo deve ser alimentado por um carregador USB (5 V, 1 A ou mais). Em power banks, atenção: muitos desligam sozinhos com cargas abaixo de ~50 a 100 mA. A placa DevKit consome ainda ~3 a 10 mA só com o regulador, o chip USB-serial e o LED de energia, o que limita o ganho de qualquer modo de economia na placa como está.

---

## Firmware

Desenvolvido em C++ sobre o framework Arduino, com PlatformIO no VSCode como ambiente de build.

### Estrutura

```
FitoSfera-Topicos/
├── README.md
├── firmware/               (abrir esta pasta no PlatformIO)
│   ├── platformio.ini
│   ├── intrucoes_montagem.md   (ligação dos fios na protoboard)
│   └── src/main.cpp
├── gravador/               (central BLE que grava a campanha; ver gravador/README.md)
│   ├── gravador.py
│   ├── protocolo.py
│   ├── qualidade.py
│   ├── ensaio.py           (CT-02, CT-13, CT-14 cronometrados)
│   └── ct05.py             (CT-05: serial + BLE)
├── dados/                  (CSV da campanha, limpar.py e grafico.py)
├── ensaios/                (evidências dos ensaios da AP2; RESULTADOS.md resume)
└── docs/                   (fontes LaTeX do relatório)
```

O firmware não tem credenciais: o BLE não usa senha de rede nem *broker*, então não há
`secrets.h` nem `secrets.example.h`.

### Configuração

A velocidade de gravação foi reduzida para 115200, porque 460800 falhou com o cabo e a porta usados.

```ini
[env:esp32dev]
platform = espressif32
board = esp32dev
framework = arduino
monitor_speed = 115200
upload_speed = 115200
lib_deps =
    adafruit/DHT sensor library@^1.4.6
    adafruit/Adafruit Unified Sensor@^1.1.14
    claws/BH1750@^1.3.0
    h2zero/NimBLE-Arduino@^1.4.3
```

### Contrato BLE (versão 2)

O ESP32 anuncia com o nome `FitoSfera` e expõe um serviço com uma característica de leitura (leitura e notificação) e uma de comando (escrita). Aceita **um celular por vez**, fica sempre ligado e volta a anunciar quando a conexão cai.

| Item | UUID |
|---|---|
| Serviço | `f1705f3a-0001-4c7e-9a5b-3d0a6e2b9c10` |
| Característica de leitura (READ, NOTIFY) | `f1705f3a-0002-4c7e-9a5b-3d0a6e2b9c10` |
| Característica de comando (WRITE, WRITE sem resposta) | `f1705f3a-0003-4c7e-9a5b-3d0a6e2b9c10` |

#### Quando o ESP32 envia

- **A cada 5 minutos**, o ESP32 liga os sensores, mede e notifica o celular conectado. Os sensores só são lidos nesse ciclo ou a pedido do app.
- **Assim que o celular assina a notificação** da característica de leitura (por exemplo, ao reconectar), o ESP32 mede e envia na hora, entregando o que se acumulou enquanto o celular estava fora.
- **Quando o app pede**, escrevendo `0x01` na característica de comando. O relógio dos 5 minutos recomeça dali.
- Sem celular conectado ou inscrito, o ciclo de 5 minutos mede e acumula a luz, mas não envia nada.
- Se algum sensor falhar, o firmware tenta de novo em 5 s, até 3 vezes; na última tentativa, envia o que tiver, com os campos que faltarem marcados como ausentes. Então a resposta a um pedido do app pode levar até ~25 s.

#### Pacote de leitura (19 bytes, little-endian)

| Bytes | Campo | Tipo | Observação |
|---|---|---|---|
| 0 | sequência | `uint8` | aumenta a cada pacote e volta a 0 depois de 255 |
| 1–2 | id do reinício | `uint16` | muda a cada vez que o ESP32 liga |
| 3–6 | luz acumulada | `uint32` | lux × minutos desde que ligou; volta a 0 ao estourar (~30 dias de sol forte) |
| 7–10 | segundos desde o último sucesso | `uint32` | zera quando o app confirma um pacote |
| 11–12 | temperatura | `int16` | centésimos de °C; `0x8000` = sem leitura |
| 13–14 | umidade | `uint16` | centésimos de %; `0xFFFF` = sem leitura |
| 15–18 | luz agora | `uint32` | lux; `0xFFFFFFFF` = sem leitura |

Antes do primeiro envio, a característica de leitura fica vazia (0 bytes), e o app deve ler isso como "ainda não há leitura".

#### Confirmação do app (o que define "sucesso")

Depois de processar um pacote, o app escreve na característica de comando **`[0x02, sequência]`**, com a sequência do pacote recebido. Só então o ESP32 considera a entrega bem-sucedida e zera o contador de segundos. Uma notificação enviada, sem essa confirmação, **não** zera o contador: o "enviado" da pilha BLE não prova que o app recebeu. Se a confirmação não chega, o contador continua crescendo e vai no próximo pacote.

#### O que o aplicativo deve fazer

1. Ao conectar, **assinar a notificação** da característica de leitura (isso dispara um envio imediato). Para pedir uma atualização, escrever `[0x01]` no comando e esperar a notificação (tempo limite sugerido: ~30 s).
2. **Decodificar** o pacote (exemplo abaixo). Se vier vazio ou com tamanho diferente de 19 bytes, ignorar.
3. **Somar luz ao total do dia** pela *diferença* do acumulado, e não pelo valor da luz de agora:
   - O app guarda, por dispositivo, o último `idReinicio` e o último acumulado que somou.
   - Se o `idReinicio` for o mesmo: `luz_nova = (acumulado − ultimoAcumulado) mod 2³²` (lux × min). Some isso ao total do dia.
   - Se o `idReinicio` mudou (o ESP32 reiniciou): o acumulado recomeçou do zero, e o app deve somar o acumulado inteiro como luz nova, sem diferença.
   - Guarde o novo acumulado e o novo `idReinicio`.
   - Como é diferença, um pacote repetido ou perdido não faz o app contar luz em dobro nem a menos, e a confirmação nem precisa ser perfeita para o total ficar certo.
4. **Confirmar** com `[0x02, sequência]` depois de salvar.
5. **Hora das medições:** o dispositivo não tem relógio, então o app carimba a hora ao receber. O campo "segundos desde o último sucesso" diz quanto tempo faltou comunicação: a luz entregue cobre esse intervalo, que pode cruzar a meia-noite. O app decide como repartir (sugestão: atribuir ao dia em que o pacote chegou, ou dividir pelo tempo).
6. **Converter para DLI:** lux × minutos → µmol/m²: `luz_nova_lux_min × 60 × fator` (fator ≈ 0,0185 µmol/m²/s por lux para luz solar), dividido por 1.000.000 para mol/m².

#### Exemplos e decodificador de referência

| Caso | Bytes (hex) | Base64 |
|---|---|---|
| Normal: seq 7, reinício `0xA1B2`, acumulado 150.000 lux·min, 1830 s sem sucesso, 25,14 °C, 58 %, 20.000 lux | `07 B2 A1 F0 49 02 00 26 07 00 00 D2 09 A8 16 20 4E 00 00` | `B7Kh8EkCACYHAADSCagWIE4AAA==` |
| DHT11 e BH1750 sem leitura | `08 B2 A1 F0 49 02 00 52 08 00 00 00 80 FF FF FF FF FF FF` | `CLKh8EkCAFIIAAAAgP///////w==` |
| Noite, −3,50 °C, 80 %, 0 lux, acumulado perto de estourar | `09 01 00 FA FF FF FF 3C 00 00 00 A2 FE 40 1F 00 00 00 00` | `CQEA+v///zwAAACi/kAfAAAAAA==` |

Comandos: medir agora = `01` (`AQ==`); confirmar o pacote 7 = `02 07` (`Agc=`).

```ts
const TEMP_AUSENTE = -32768;
const UMID_AUSENTE = 0xffff;
const LUX_AUSENTE = 0xffffffff;

interface PacoteDoSensor {
  sequencia: number;
  idReinicio: number;
  luxMinutosAcumulados: number; // uint32; volta a 0 ao estourar
  segundosDesdeUltimoSucesso: number;
  temperaturaCelsius: number | null;
  umidadePercentual: number | null;
  luminosidadeLux: number | null;
}

function decodificarPacote(bytes: Uint8Array): PacoteDoSensor | null {
  if (bytes.length !== 19) return null;
  const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const temp = v.getInt16(11, true);
  const umid = v.getUint16(13, true);
  const lux = v.getUint32(15, true);
  return {
    sequencia: v.getUint8(0),
    idReinicio: v.getUint16(1, true),
    luxMinutosAcumulados: v.getUint32(3, true),
    segundosDesdeUltimoSucesso: v.getUint32(7, true),
    temperaturaCelsius: temp === TEMP_AUSENTE ? null : temp / 100,
    umidadePercentual: umid === UMID_AUSENTE ? null : umid / 100,
    luminosidadeLux: lux === LUX_AUSENTE ? null : lux,
  };
}

// Diferença do acumulado, com a volta de 32 bits: (novo - antigo) >>> 0
```

O decodificador foi conferido contra os três pacotes da tabela (Node). O contrato foi exercitado no hardware com o nRF Connect em um celular Android, e não ainda com o aplicativo FitoSfera (ver "Estado da validação").

### Decisões de implementação

**Temporização não bloqueante.** O controle de intervalo entre leituras usa comparação sobre `millis()` em vez de `delay()`. A chamada bloqueante congela o processador por completo, impedindo qualquer outra tarefa. Como a evolução prevista inclui gerenciamento de conexão BLE e tratamento de eventos, a abordagem não bloqueante evita a reescrita do laço principal.

**Tratamento de falha de leitura.** O DHT11 retorna `NaN` em caso de falha de comunicação, ocorrência esperada em uma fração das leituras. A verificação por `isnan()` impede a propagação de valores inválidos. Cada campo do pacote BLE tem um valor reservado para "sem leitura", de modo que a falha de um sensor não impede o envio dos demais nem do acumulado de luz.

**Nova tentativa rápida.** Se o DHT11 ou o BH1750 falharem, o firmware tenta de novo em 5 s, até 3 vezes, antes de enviar o que tiver e voltar ao intervalo de 5 minutos. Vale também para leituras pedidas pelo app.

**Luz acumulada no próprio ESP32.** A cada medição, o firmware soma a área sob a curva da luz (trapézio entre duas leituras seguidas) e envia o total acumulado. O app calcula a luz de um período pela diferença entre dois acumulados, o que dispensa guardar leituras no ESP32 e torna a soma imune a pacotes perdidos ou repetidos. Intervalos de mais de 15 minutos sem leitura de luz (sensor com defeito) não entram na soma. A medição é uma amostra a cada 5 minutos, então a estimativa de luz é grosseira em dias de nuvens passando.

**BH1750 em modo de uma medida.** O chip dorme entre as leituras (a cada medição, a sensibilidade é reenviada e o firmware espera ~100 ms pela conversão). Essa sequência foi escrita pela documentação da biblioteca e funcionou no circuito: os pacotes recebidos no nRF Connect trouxeram leituras de lux válidas.

**CPU a 80 MHz.** O firmware reduz a frequência da CPU de 240 para 80 MHz (o mínimo com BLE) logo no início do `setup()`. A carga é leve (dois sensores a cada 5 minutos), e a redução diminui o consumo ativo. O ganho ainda não foi medido no circuito; os valores do orçamento de corrente acima correspondem a 240 MHz e devem ser reavaliados com um medidor.

**Periférico opcional.** Na inicialização, o firmware lista no monitor serial os endereços I2C encontrados. Se o BH1750 não responder, o firmware avisa e continua, em vez de travar.

---

## Metodologia de construção

A montagem seguiu validação incremental, com cada camada testada isoladamente antes da integração:

1. Verificação da cadeia de compilação e gravação (blink no LED interno)
2. Validação da comunicação serial
3. Leitura do DHT11 isolada
4. Varredura I2C e leitura do BH1750
5. Anúncio BLE, leitura e escrita das características com o nRF Connect em um celular Android
6. Integração com o aplicativo FitoSfera (pendente: o aplicativo ainda está em desenvolvimento)

### Estado da validação

Todos os testes de BLE foram feitos com o **nRF Connect em um celular Android**, lendo os pacotes em hexadecimal e escrevendo os comandos manualmente. O aplicativo FitoSfera ainda não tem o adaptador BLE, então nada aqui foi testado com ele.

**Verificado no hardware (nRF Connect, Android)**
- Anúncio como `FitoSfera`, conexão e assinatura da notificação de leitura, que dispara o envio imediato de um pacote.
- Comando `01` (medir agora): chega um pacote novo com a sequência seguinte.
- Comando `02 NN` (confirmar): o contador de segundos sem sucesso zera no pacote seguinte; sem confirmação, ele continua crescendo.
- Luz acumulada: a diferença entre acumulados bate com a luz e o tempo entre os pacotes. Após uma desconexão de cerca de 55 minutos, o pacote seguinte trouxe a luz do período inteiro de uma vez.
- Reinício do ESP32: o id do reinício muda, a sequência volta a 1 e o acumulado recomeça de 0.
- Nova tentativa em 5 s quando um sensor falha, e leituras do BH1750 no modo de uma medida.
- Funcionamento ligado em um carregador USB comum de 5 V (um carregador rápido que religava a saída com a carga baixa foi descartado).

**Verificado com o gravador no notebook (AP2, 24 e 25/10/2026)**

Resumo em `ensaios/RESULTADOS.md`; números no Capítulo 7 e no Apêndice C do relatório.
- Campanha de 24,1 h num quarto: 288 leituras, completude de 97,6 % das janelas de 5 min, 0 fora do contrato, 0 repetidas, 0 campos ausentes, 1 lacuna (a provocada no CT-16).
- `01` respondido em 0,17 s (mediana de 10); `02` só zera o contador com a sequência do pacote em espera (CT-13, CT-14).
- Sol direto: 70 a 72 mil lux sem saturar (CT-02); série CSV da serial com 7 campos (CT-05).
- Queda do Bluetooth do PC: reconexão sozinha 7,2 s depois (CT-15). Gravador parado 35 min: lacuna no CSV, perda contada pela sequência e luz do intervalo inteira no pacote seguinte (CT-16, CT-20).
- Nó sem energia: `desconectado` em 3,6 e 5,9 s (CT-18). Reinício: id novo, sem repetidas nem perdas falsas (CT-17), mas a seq 1, medida 2 s depois de ligar, se perde quando o gravador demora a reconectar.

---

## Limitações reconhecidas

**Precisão do DHT11.** A resolução de 1 °C e 1 %, com incerteza de ±2 °C, é adequada para detecção de tendências mas insuficiente para caracterização fina de microclima. O DHT22 ou o BME280 são substitutos pino-compatíveis quando maior precisão for necessária.

**Ausência de referência temporal.** O dispositivo não tem relógio, e a serial mostra só o tempo desde a inicialização. A hora da medição é carimbada pelo aplicativo ao receber o pacote, o que atribui uma defasagem de até 5 minutos a uma leitura lida direto (READ).

**Sem pareamento nem segurança.** O firmware não faz *bonding*: qualquer celular ao alcance pode conectar e ler os dados, e o dispositivo aceita um celular por vez. O primeiro uso (escolher o dispositivo certo entre os que estiverem por perto) e a restrição ao celular do dono ainda não foram implementados.

**Autonomia.** Sempre ligado, o consumo estimado inviabiliza bateria (menos de 2 dias com 2000 mAh). 

**Incerteza do BH1750.** O fabricante declara variação de ±20 % na medição de lux. É adequado para comparar o ambiente com as faixas de luminosidade das espécies, mas não substitui um luxímetro calibrado. Com a sensibilidade reduzida (MTreg = 31) para alcançar sol pleno, a resolução em luz fraca é um pouco menor.

