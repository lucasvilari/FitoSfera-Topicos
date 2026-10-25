# Gravador da campanha

O FitoSfera fala BLE, e não MQTT, então não há *broker* entre o nó e o arquivo. Quem
guarda é quem recebe: o `gravador.py` é um central BLE que roda num computador
perto do nó e faz o que o aplicativo vai fazer no futuro.

1. Procura o nó pelo nome `FitoSfera` (ou pelo `--endereco`).
2. Conecta e assina a notificação da característica de leitura. A assinatura faz o nó
   medir e enviar na hora.
3. A cada pacote, **primeiro grava** a linha em `dados/mensagens.csv` (com `fsync`) e
   **só depois confirma** com `[0x02, seq]`. Um pacote confirmado está sempre no disco.
4. Se a conexão cai, anota em `dados/eventos.csv` e volta a procurar, com espera de
   2 s dobrando até 60 s. Se o enlace fica de pé mas nada chega por 630 s (dois
   períodos + 30 s), derruba a conexão e recomeça.

O gravador foi escrito pela equipe na AP2: a disciplina não tinha gravador BLE.

## Instalar e rodar

Requer Python 3.10+ e um adaptador Bluetooth 4.0+ (no Linux, BlueZ).

```bash
python3 -m venv .venv
.venv/bin/pip install -r gravador/requirements.txt
.venv/bin/python gravador/gravador.py --saida dados/mensagens.csv --eventos dados/eventos.csv
```

Feche o nRF Connect no celular antes: o nó aceita **um central por vez**.
Para parar, Ctrl+C; rodando em segundo plano, `kill -INT` ou `kill -TERM` fazem o mesmo e anotam
`fim_gravador`. Não use `kill -9`: o BlueZ pode manter a conexão aberta, e o nó, ainda conectado,
para de anunciar (resolve com `bluetoothctl disconnect <endereço>`).
Se o gravador for interrompido e voltar a rodar, ele acrescenta ao mesmo arquivo.

## Durante a campanha

```bash
.venv/bin/python gravador/qualidade.py dados/mensagens.csv --eventos dados/eventos.csv
```

No fim, gere o arquivo limpo e a figura do relatório:

```bash
.venv/bin/python dados/limpar.py dados/mensagens.csv dados/mensagens_limpo.csv
.venv/bin/python dados/grafico.py dados/mensagens_limpo.csv docs/figuras/serie-campanha.pdf
```

## Arquivos

| Arquivo | O que é |
|---|---|
| `protocolo.py` | UUIDs, tamanho e decodificação do pacote de 19 bytes (espelha `firmware/src/main.cpp`) |
| `gravador.py` | o central BLE que grava o CSV |
| `qualidade.py` | completude, perdas, duplicatas, reinícios, lacunas e luz por dia |
| `ensaio.py` | CT-14, CT-13 e CT-02 cronometrados (comandos `01` e `02`); grava em `ensaios/` |
| `ct05.py` | CT-05: lê a serial (DTR/RTS soltos) enquanto pede leituras pelo BLE |
| `test_*.py` | `python3 -m unittest discover gravador` |

## Colunas de `mensagens.csv` (bruto)

| Coluna | O que é |
|---|---|
| `ts_recebido` | época Unix (s, 3 casas) **do computador** na chegada; o nó não tem relógio |
| `hora_utc` | a mesma hora em ISO 8601 |
| `endereco` | endereço BLE do nó |
| `tamanho`, `bytes_hex` | o pacote como chegou; fora do contrato se `tamanho` ≠ 19 |
| `seq` | sequência do pacote, 0–255, volta a 0 |
| `id_reinicio` | muda a cada vez que o nó liga |
| `lux_min_acum` | luz acumulada desde que ligou (lux × min) |
| `seg_sem_sucesso` | segundos desde a última confirmação que o nó recebeu |
| `temp_c`, `umid_pct`, `lux` | vazios quando o sensor não respondeu |

## Colunas de `eventos.csv`

`ts`, `hora_utc`, `evento`, `detalhe`. Eventos: `inicio_gravador`, `encontrado` (com RSSI),
`nao_encontrado`, `conectado`, `inscrito`, `desconectado`, `silencio`, `confirmacao_falhou`,
`fora_do_contrato`, `erro`, `fim_gravador`.
