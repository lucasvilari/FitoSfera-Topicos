# Ensaios da AP2 feitos no notebook (24/10/2026)

Firmware `firmware/src/main.cpp` (contrato v2, 19 bytes, 300 s), placa do Lucas,
endereço `8C:94:DF:8F:FA:16`, id de reinício `ebea`. Central: notebook Acer Aspire A515-57,
BlueZ, `bleak`. Nó **a 50 cm do chão, perto de uma janela aberta, com sol direto**.
Horas em Teresina (UTC−3).

## Teste de fumaça (14:04)
`ensaios/fumaca.csv`, `ensaios/fumaca-eventos.csv`. Encontrado → conectado em 1,2 s, primeiro
pacote 0,5 s após o `conectado`, RSSI −61 dBm, 19 bytes, 0 fora do contrato.
T = 35,2 °C, UR = 45 %, lux = 71 803.

## CT-14, CT-13, CT-02 (14:05–14:06) — `gravador/ensaio.py`, `ensaios/ct13-14-02.csv`

| CT | Resultado | Veredito |
|---|---|---|
| CT-14 | sem confirmar, o contador cresceu 114 → 117 → 121 s; `02` com seq errada: 124 s (não zerou); `02` com a seq do pacote em espera: 3 s no pacote seguinte | atende |
| CT-13 | assinatura → pacote em 0,472 s; 10 de 10 `01` responderam com pacote novo; latência mediana 0,166 s, máx. 0,215 s; seq 7 → 17 sem salto | atende |
| CT-02 | sol direto, 14:06: 70 619, 70 682 e 70 530 lux (válidos, acima de 54 612 e abaixo de 121 557) | atende |
| CT-12 | todos os pacotes com 19 bytes (fumaça, ensaio, campanha) ; 10 de 10 testes automáticos | atende (com o firmware novo) |
| CT-23 | 19 bytes por notificação, sem negociar MTU (bleak/BlueZ) | atende |

Observação: com o nó ao sol a temperatura do DHT11 subiu de 35,2 para 43,0 °C em 2 min
(aquecimento do sensor/caixa pelo sol direto, não do ar). Vale citar no Cap. 8.

## Campanha (início 24/10 14:07:41) — `ensaios/campanha.sh`
Gravador desacoplado da sessão, com `systemd-inhibit` bloqueando suspensão e tampa.
Ações automáticas registradas em `ensaios/diario-automatico.txt`:

- 14:17:41 CT-15 `bluetoothctl power off`; 14:19:41 `power on`
- 14:34:41 CT-16 Ctrl+C no gravador; 15:09:41 gravador de volta (35 min parado → serve também de CT-20)

Pendentes (precisam de mão no nó, depois das 15:10): CT-17 (EN), CT-18 (USB ×3, com
`date +%T.%N`), CT-19 (sai do CT-18) e CT-05 (nó na USB do notebook, serial, no fim da campanha).

## CT-15 (14:17:41–14:19:41) — `dados/eventos.csv`, `ensaios/diario-automatico.txt`
- `desconectado` às 14:17:44,8 (3 s depois do `power off`); 5 tentativas com
  `BleakBluetoothNotAvailableError` enquanto o adaptador estava desligado.
- `power on` 14:19:41 → `encontrado` 14:19:47,9 → `conectado` 14:19:48,9 → pacote extra 14:19:49,1:
  **reconectou em 7,2 s** depois do `power on` (limite: 90 s), sem mexer no gravador.
- **1 leitura perdida** (seq 23): o `power off` caiu 297 s depois da última leitura (seq 22, 14:12:44),
  e o ciclo seguinte (≈14:17:44) aconteceu com o rádio desligado. O pacote da volta (seq 24) veio com
  `seg_sem_sucesso` = 424 s, coerente com a última confirmação às 14:12:44. Bate com o esperado
  ("nenhuma perda se a queda for menor que 300 s desde a última leitura"; aqui não foi).
- Veredito proposto: **atende** (reconexão automática dentro do limite; a perda é explicada pela sequência).

## CT-16, primeira tentativa (14:34): falhou
O `kill -INT` do `campanha.sh` foi ignorado (processo em segundo plano de script bash nasce com
SIGINT ignorado) e o gravador seguiu gravando, sem lacuna. Correção em `gravador/gravador.py`:
SIGINT e SIGTERM encerram como o Ctrl+C. Na troca do processo (15:11, com TERM), o BlueZ manteve a
conexão do processo morto e o nó parou de anunciar; resolvido com `bluetoothctl disconnect`
(reconectou às 15:12:44, seq 34 → 35, sem perda). Refeito às 15:31 (abaixo).

## CT-18 (15:18–15:22) — `ensaios/ct18-hora.txt`, `dados/eventos.csv`
| vez | USB arrancado (Enter) | `desconectado` | tempo |
|---|---|---|---|
| 1 | 15:18:41,229 | 15:18:34,697 | inválido (Enter ~6,5 s atrasado) |
| 2 | 15:20:22,662 | 15:20:28,516 | 5,9 s |
| 3 | 15:22:16,480 | 15:22:20,118 | 3,6 s |
| 4 | 16:11:31,699 | 16:11:31,818 | 0,1 s (duvidoso: bem abaixo das outras; o Enter provavelmente saiu atrasado) |
Reconexão sozinha nas 3 (conectado 28 s, 16 s e 18 s depois do `desconectado`, com o USB religado
~10 s depois). 4ª vez: reconectou 22 s depois, id novo 44785, primeira seq 2.
Veredito proposto: atende (3 de 4 abaixo de 10 s; 2 confiáveis, 3,6 e 5,9 s; nenhuma acima de 10 s).

## CT-17 (15:25:36,871) — `ensaios/ct17-hora.txt`
EN → `desconectado` em 1,9 s → `conectado` em 5,6 s; id novo 6d2e (27950); primeira seq recebida 2,
acumulado 31 lux·min (a seq 1, medida 2 s após ligar, saiu antes da reconexão). `qualidade.py`:
4 reinícios (3 do CT-18 + CT-17), 0 repetidas; mas 3 dos 4 reinícios deixam 1 "falta" (a seq 1).

## CT-19 (dos reinícios do CT-18/CT-17)
Todas as linhas sem hora do nó (20 de 20); as primeiras de cada reinício chegam 0,1–0,5 s depois do
`conectado`, com `ts_recebido` do gravador. Veredito proposto: atende.

## Achado para o relatório
O nó mede 2 s depois de ligar, mas o gravador leva ~5–28 s para reconectar: a seq 1 de cada reinício
se perde (o nó não guarda pacote). O CT-17 esperava "nenhuma perda atribuída ao reinício":
veredito proposto **atende em parte**. Possível melhoria (AP3): guardar o último pacote não
confirmado e reenviá-lo na assinatura.

## CT-16 refeito (15:31:15–16:06:18) e CT-20 com o firmware novo
- `kill -INT` às 15:31:15,7 → `fim_gravador` às 15:31:18 (8 pacotes na execução); BlueZ liberou a
  conexão sozinho (`Connected: no`).
- Volta às 16:06:18,7 → `encontrado` 16:06:19,5 → `conectado` 16:06:21,0 → pacote 16:06:21,6.
- `qualidade.py`: 1 lacuna de **35 min 39 s** (15:30:42 → 16:06:21), "o nó mediu 7 vezes sem
  entregar; gravador parado" (seq 4 a 10 faltando, seq 3 → 11). Primeiro pacote da volta com
  `seg_sem_sucesso` = 2138 s (= 35 min 38 s desde a última confirmação).
- **CT-20:** o acumulado foi de 2828 para 19 068 lux·min: 16 240 lux·min em 35,6 min, média de
  456 lux, coerente com 569 lux antes e 419 lux depois (fim de tarde, luz caindo). A luz do
  período sem central chegou inteira no primeiro pacote.
- Vereditos propostos: CT-16 **atende em parte** (como previsto na DP-8: buraco no CSV, mas a
  sequência mede a perda e a luz não se perde); CT-20 **atende**.

## Fim da campanha (25/10 14:12:37)
Gravador encerrado com `kill -INT` depois da leitura das 14:12:32 (24 h 05 min desde a primeira, 14:07:44).
`dados/qualidade.txt` com `--inicio '2026-10-24 14:07' --fim '2026-10-25 14:13'`: 24,10 h, 288 leituras
únicas de 290 esperadas, completude 97,6 % das janelas, 0 fora do contrato, 0 repetidas, 0 campos
ausentes, 12 faltando (todas de ensaios provocados), 1 lacuna (CT-16). `mensagens_limpo.csv`: 288 linhas.

## CT-05 (25/10 14:20) — `gravador/ct05.py`, `ensaios/ct05.log`
Nó na USB do notebook (CP2102, `/dev/ttyUSB0`). O script abre a serial com DTR/RTS soltos (ativos, eles
seguram o ESP32 em reset), dá um pulso em EN e pede 10 leituras pelo BLE com `01`.
Cabeçalho do `setup()` presente; **11 de 11 linhas de dados com 7 campos**; nenhuma linha `#` depois do
cabeçalho. Antes do cabeçalho só há a saída da ROM no boot. Veredito: atende.
