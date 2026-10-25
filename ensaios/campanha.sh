#!/usr/bin/env bash
# Roda a campanha e, no começo dela, os ensaios provocados que não precisam de mão:
#   CT-15: bluetoothctl power off por 2 min
#   CT-16 (e CT-20): gravador parado por 35 min
# Cada ação fica com hora em ensaios/diario-automatico.txt.
#
# Guardado como evidência: o CT-16 daqui falhou. Um processo de fundo de script sem controle
# de tarefas nasce com o SIGINT ignorado, e o kill -INT não parou o gravador. O gravador.py
# passou a tratar SIGINT e SIGTERM, e o CT-16 foi refeito à mão (ver RESULTADOS.md).
cd "$(dirname "$0")/.."
DIARIO=ensaios/diario-automatico.txt
anota() { echo "$(date '+%F %T.%N %Z') $*" | tee -a "$DIARIO"; }

gravar() {
  .venv/bin/python -u gravador/gravador.py --saida dados/mensagens.csv --eventos dados/eventos.csv \
    >> ensaios/gravador.log 2>&1 &
  GRAVADOR=$!
  anota "gravador iniciado (pid $GRAVADOR)"
}

anota "inicio da campanha; no a 50 cm do chao, perto de janela aberta, com sol"
gravar

sleep 600
anota "CT-15 bluetoothctl power off"
bluetoothctl power off >> "$DIARIO" 2>&1
sleep 120
anota "CT-15 bluetoothctl power on"
bluetoothctl power on >> "$DIARIO" 2>&1

sleep 900
anota "CT-16 Ctrl+C no gravador"
kill -INT "$GRAVADOR"; wait "$GRAVADOR"
sleep 2100
anota "CT-16 gravador de volta (35 min parado)"
gravar
wait "$GRAVADOR"
