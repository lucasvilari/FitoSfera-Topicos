#include <Arduino.h>
#include <DHT.h>

#define PINO_DHT      18
#define TIPO_DHT      DHT11
#define PINO_LUZ      19

#define LED_VERMELHO  21
#define LED_AMARELO   22
#define LED_VERDE     23

const float TEMP_ALTA  = 25.0;   // °C
const float UMID_BAIXA = 50.0;   // %

// LOW deve ser ao detectar luz. Caso o contrário, só inverter.
const int NIVEL_CLARO = LOW;

const unsigned long INTERVALO_MS = 2000;
unsigned long ultimaLeitura = 0;

DHT dht(PINO_DHT, TIPO_DHT);

void setup() {
  Serial.begin(115200);

  pinMode(PINO_LUZ, INPUT);
  pinMode(LED_VERMELHO, OUTPUT);
  pinMode(LED_AMARELO, OUTPUT);
  pinMode(LED_VERDE, OUTPUT);

  dht.begin();
  delay(2000);

  Serial.println();
  Serial.println("tempo_s, temp_c, umidade_pct, escuro");
}

void loop() {
  if (millis() - ultimaLeitura < INTERVALO_MS) return;
  ultimaLeitura = millis();

  float temp = dht.readTemperature();
  float umid = dht.readHumidity();
  int   luz  = digitalRead(PINO_LUZ);

  if (isnan(temp) || isnan(umid)) {
    Serial.println("# leitura invalida do DHT11");
    return;
  }

  bool frio = temp < TEMP_ALTA;
  bool seco = umid < UMID_BAIXA;
  bool escuro = (luz != NIVEL_CLARO);

  digitalWrite(LED_VERMELHO, frio);
  digitalWrite(LED_AMARELO, seco);
  digitalWrite(LED_VERDE, escuro);

  Serial.printf("%lu, %.1f, %.1f, %d\n",
                millis() / 1000, temp, umid, escuro ? 1 : 0);
}