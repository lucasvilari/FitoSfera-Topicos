#include <Arduino.h>
#include <Wire.h>
#include <DHT.h>
#include <BH1750.h>
#include <NimBLEDevice.h>

#define PINO_DHT      18
#define TIPO_DHT      DHT11

// Barramento I2C do BH1750
#define PINO_SDA      21
#define PINO_SCL      22
#define ENDERECO_LUX  0x23   // BH1750 com o pino ADDR solto

// Reduz a sensibilidade do BH1750 para medir acima de 65535 lux (sol pleno)
// 69 é o padrão do chip (teto ~54 mil lux); 31 leva o teto a ~120 mil lux
#define MTREG_LUX     31

// Valores enviados no pacote quando o sensor correspondente não respondeu
#define TEMP_AUSENTE  ((int16_t)0x8000)
#define UMID_AUSENTE  ((uint16_t)0xFFFF)
#define LUX_AUSENTE   0xFFFFFFFFu

const char* NOME_BLE     = "FitoSfera";
#define UUID_SERVICO  "f1705f3a-0001-4c7e-9a5b-3d0a6e2b9c10"
#define UUID_LEITURA  "f1705f3a-0002-4c7e-9a5b-3d0a6e2b9c10"
#define UUID_COMANDO  "f1705f3a-0003-4c7e-9a5b-3d0a6e2b9c10"

// Comandos escritos pelo app na característica de comando
//   [0x01]       mede e envia agora
//   [0x02, seq]  confirma que o app recebeu e processou o pacote de número seq
#define CMD_MEDIR_AGORA 0x01
#define CMD_CONFIRMAR   0x02

// Os sensores só são lidos a cada ciclo de envio (ou a pedido do app)
const unsigned long INTERVALO_MS = 5UL * 60UL * 1000UL;
// Se algum sensor falhar, tenta de novo logo, até MAX_TENTATIVAS vezes; na última, envia o que houver
const unsigned long REPETICAO_MS = 5000;
const int MAX_TENTATIVAS = 3;
int tentativas = 0;
// A primeira leitura sai 2 s após ligar, tempo de estabilizar o DHT11
unsigned long proximaLeitura = 2000;
// Ligado pelo app (comando ou assinatura da notificação); o loop mede e envia na hora
volatile bool pedidoDoApp = false;

// Intervalos maiores que isso sem leitura de luz não entram na soma: o dado fica de fora, em vez de inventado
const unsigned long LACUNA_MAX_MS = 15UL * 60UL * 1000UL;

DHT dht(PINO_DHT, TIPO_DHT);
BH1750 sensorLuz(ENDERECO_LUX);

bool luzOk = false;
NimBLEServer* servidorBle = nullptr;
NimBLECharacteristic* caracteristicaLeitura = nullptr;

// Muda a cada inicialização, para o app saber que o acumulado recomeçou do zero
uint16_t idReinicio = 0;
// Integral da luz desde que ligou, em lux x segundos
double luxSegundos = 0;
float luxAnterior = NAN;
unsigned long luxAnteriorMs = 0;

uint8_t seqPacote = 0;
// Instante da última confirmação do app; os segundos desde ele vão em todo pacote
unsigned long ultimoSucessoMs = 0;
volatile bool confirmacaoRecebida = false;
volatile uint8_t confirmacaoSeq = 0;
uint8_t seqAguardando = 0;
bool aguardandoConfirmacao = false;

class CallbacksDoServidor : public NimBLEServerCallbacks {
  // Um só celular por vez: o NimBLE para de anunciar ao conectar e volta ao desconectar
  void onDisconnect(NimBLEServer*) override { NimBLEDevice::startAdvertising(); }
};

// Assinar a notificação dispara um envio imediato, entregando o que se acumulou enquanto o celular estava fora
class CallbacksDaLeitura : public NimBLECharacteristicCallbacks {
  void onSubscribe(NimBLECharacteristic*, ble_gap_conn_desc*, uint16_t subValue) override {
    if (subValue & 1) pedidoDoApp = true;
  }
};

class CallbacksDoComando : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* caracteristica) override {
    NimBLEAttValue valor = caracteristica->getValue();
    const uint8_t* dados = valor.data();
    size_t n = valor.length();
    if (n >= 1 && dados[0] == CMD_MEDIR_AGORA) {
      pedidoDoApp = true;
    } else if (n >= 2 && dados[0] == CMD_CONFIRMAR) {
      confirmacaoSeq = dados[1];
      confirmacaoRecebida = true;
    }
  }
};

bool existeNoBarramento(uint8_t endereco) {
  Wire.beginTransmission(endereco);
  return Wire.endTransmission() == 0;
}

void listarDispositivosI2C() {
  Serial.print("# I2C:");
  int achados = 0;
  for (uint8_t endereco = 1; endereco < 127; endereco++) {
    if (existeNoBarramento(endereco)) {
      Serial.printf(" 0x%02X", endereco);
      achados++;
    }
  }
  Serial.println(achados ? "" : " nenhum dispositivo");
}

void iniciarBle() {
  NimBLEDevice::init(NOME_BLE);
  servidorBle = NimBLEDevice::createServer();
  servidorBle->setCallbacks(new CallbacksDoServidor());

  NimBLEService* servico = servidorBle->createService(UUID_SERVICO);
  caracteristicaLeitura = servico->createCharacteristic(
      UUID_LEITURA, NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);
  caracteristicaLeitura->setCallbacks(new CallbacksDaLeitura());

  NimBLECharacteristic* comando = servico->createCharacteristic(
      UUID_COMANDO, NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_NR);
  comando->setCallbacks(new CallbacksDoComando());

  servico->start();

  NimBLEAdvertising* anuncio = NimBLEDevice::getAdvertising();
  anuncio->addServiceUUID(UUID_SERVICO);
  anuncio->setScanResponse(true);
  anuncio->start();
}

void escrever16(uint8_t* destino, uint16_t v) {
  destino[0] = v & 0xFF;
  destino[1] = (v >> 8) & 0xFF;
}

void escrever32(uint8_t* destino, uint32_t v) {
  destino[0] = v & 0xFF;
  destino[1] = (v >> 8) & 0xFF;
  destino[2] = (v >> 16) & 0xFF;
  destino[3] = (v >> 24) & 0xFF;
}

// Pacote de 19 bytes:
//   [0]     número de sequência, uint8 (volta a 0 depois de 255)
//   [1..2]  id do reinício, uint16
//   [3..6]  luz acumulada desde que ligou, uint32, lux x minutos (volta a 0 ao estourar)
//   [7..10] segundos desde a última confirmação do app, uint32
//   [11..12] temperatura, int16, centésimos de °C (TEMP_AUSENTE = sem leitura)
//   [13..14] umidade, uint16, centésimos de % (UMID_AUSENTE = sem leitura)
//   [15..18] luz agora, uint32, lux (LUX_AUSENTE = sem leitura)
// Devolve true se havia um celular inscrito para receber a notificação
bool enviarPacote(float temp, float umid, float lux) {
  uint32_t acumulado = (uint32_t)(uint64_t)(luxSegundos / 60.0);
  uint32_t segundosSemSucesso = (millis() - ultimoSucessoMs) / 1000;

  uint8_t pacote[19];
  pacote[0] = ++seqPacote;
  escrever16(pacote + 1, idReinicio);
  escrever32(pacote + 3, acumulado);
  escrever32(pacote + 7, segundosSemSucesso);
  escrever16(pacote + 11, isnan(temp) ? (uint16_t)TEMP_AUSENTE : (uint16_t)(int16_t)lroundf(temp * 100.0f));
  escrever16(pacote + 13, isnan(umid) ? UMID_AUSENTE : (uint16_t)lroundf(umid * 100.0f));
  escrever32(pacote + 15, isnan(lux) ? LUX_AUSENTE : (uint32_t)lroundf(lux));

  caracteristicaLeitura->setValue(pacote, sizeof(pacote));

  bool haInscrito = caracteristicaLeitura->getSubscribedCount() > 0;
  if (haInscrito) {
    caracteristicaLeitura->notify();
    seqAguardando = pacote[0];
    aguardandoConfirmacao = true;
  }
  return haInscrito;
}

// O app confirmou o pacote: a comunicação foi um sucesso e o contador de segundos zera
void tratarConfirmacao() {
  if (!confirmacaoRecebida) return;
  confirmacaoRecebida = false;
  if (aguardandoConfirmacao && confirmacaoSeq == seqAguardando) {
    aguardandoConfirmacao = false;
    ultimoSucessoMs = millis();
    Serial.printf("# confirmado seq %u; contador zerado\n", confirmacaoSeq);
  }
}

bool iniciarLuz() {
  return existeNoBarramento(ENDERECO_LUX) &&
         sensorLuz.begin(BH1750::ONE_TIME_HIGH_RES_MODE, ENDERECO_LUX, &Wire) &&
         sensorLuz.setMTreg(MTREG_LUX);
}

// Modo de uma medida: o chip dorme entre as leituras. O setMTreg reenvia a sensibilidade e o modo,
// o que dispara uma medição; depois espera a conversão (até ~80 ms com MTreg 31)
float medirLuz() {
  if (!luzOk) return NAN;
  if (!sensorLuz.setMTreg(MTREG_LUX)) return NAN;
  delay(100);
  float medida = sensorLuz.readLightLevel();
  return medida >= 0 ? medida : NAN;
}

// Soma a área sob a curva da luz (trapézio entre duas leituras seguidas)
void integrarLuz(float lux) {
  if (isnan(lux)) return;
  unsigned long agora = millis();
  if (!isnan(luxAnterior) && agora - luxAnteriorMs <= LACUNA_MAX_MS) {
    luxSegundos += (luxAnterior + lux) / 2.0 * ((agora - luxAnteriorMs) / 1000.0);
  }
  luxAnterior = lux;
  luxAnteriorMs = agora;
}

void imprimirCampo(float valor, int casas) {
  if (isnan(valor)) Serial.print("-");
  else              Serial.print(valor, casas);
}

void setup() {
  // 80 MHz é o mínimo com BLE
  setCpuFrequencyMhz(80);
  Serial.begin(115200);
  Wire.begin(PINO_SDA, PINO_SCL);

  idReinicio = (uint16_t)(esp_random() & 0xFFFF);

  Serial.println();
  listarDispositivosI2C();

  dht.begin();

  luzOk = iniciarLuz();
  if (!luzOk) Serial.println("# BH1750 nao encontrado; seguindo sem luz");

  iniciarBle();

  Serial.println("tempo_s, temp_c, umidade_pct, lux, lux_min_acum, seg_sem_sucesso, enviado");
}

void loop() {
  tratarConfirmacao();

  bool pedido = pedidoDoApp;
  if (!pedido && (long)(millis() - proximaLeitura) < 0) return;
  pedidoDoApp = false;

  float temp = dht.readTemperature();
  float umid = dht.readHumidity();
  // Tenta de novo a cada ciclo, para o sensor voltar sem precisar de reset
  if (!luzOk && (luzOk = iniciarLuz())) Serial.println("# BH1750 encontrado");
  float lux = medirLuz();
  integrarLuz(lux);

  if (isnan(temp) || isnan(umid)) Serial.println("# leitura invalida do DHT11");
  if (luzOk && isnan(lux))        Serial.println("# leitura invalida do BH1750");

  bool completo = !isnan(temp) && !isnan(umid) && !isnan(lux);

  if (!completo && tentativas < MAX_TENTATIVAS) {
    tentativas++;
    proximaLeitura = millis() + REPETICAO_MS;
    Serial.printf("# nova tentativa em %lu s (%d/%d)\n", REPETICAO_MS / 1000, tentativas, MAX_TENTATIVAS);
    return;
  }

  tentativas = 0;
  proximaLeitura = millis() + INTERVALO_MS;

  bool enviado = enviarPacote(temp, umid, lux);

  Serial.printf("%lu, ", millis() / 1000);
  imprimirCampo(temp, 1); Serial.print(", ");
  imprimirCampo(umid, 1); Serial.print(", ");
  imprimirCampo(lux, 0);  Serial.print(", ");
  Serial.printf("%lu, %lu, %s\n",
                (unsigned long)(luxSegundos / 60.0),
                (millis() - ultimoSucessoMs) / 1000,
                enviado ? "sim" : "sem celular");
}
