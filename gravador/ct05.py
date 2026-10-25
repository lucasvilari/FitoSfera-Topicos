"""CT-05: registra a serial do nó e confere se as linhas de dados são CSV com 7 campos.

Enquanto lê a serial, pede leituras pelo BLE com o comando 01, para não esperar
dez ciclos de 300 s. Rodar com o gravador da campanha parado.

    python gravador/ct05.py --porta /dev/ttyUSB0 --saida ensaios/ct05.log
"""

import argparse
import asyncio
import csv
import io
import time

import serial
from bleak import BleakClient, BleakScanner

import protocolo


async def pedir_leituras(n, pausa):
    dispositivo = await BleakScanner.find_device_by_filter(
        lambda d, a: a.local_name == protocolo.NOME_BLE or protocolo.UUID_SERVICO in a.service_uuids,
        timeout=30)
    if not dispositivo:
        raise SystemExit("nó não encontrado pelo BLE")
    async with BleakClient(dispositivo, timeout=20) as cliente:
        await cliente.start_notify(protocolo.UUID_LEITURA, lambda _c, _d: None)  # a assinatura já mede uma vez
        for _ in range(n - 1):
            await asyncio.sleep(pausa)
            await cliente.write_gatt_char(protocolo.UUID_COMANDO, bytes([protocolo.CMD_MEDIR_AGORA]), response=True)
        await asyncio.sleep(pausa)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--porta", default="/dev/ttyUSB0")
    parser.add_argument("--saida", default="ensaios/ct05.log")
    parser.add_argument("--leituras", type=int, default=10)
    parser.add_argument("--pausa", type=float, default=3)
    args = parser.parse_args()

    # Com DTR/RTS ativos, o circuito de gravação da DevKit segura o ESP32 em reset.
    # Abre com as duas linhas soltas e dá um pulso em RTS (EN) para ver o boot desde o início.
    porta = serial.Serial()
    porta.port, porta.baudrate, porta.timeout = args.porta, 115200, 0.2
    porta.dtr = porta.rts = False
    porta.open()
    porta.rts = True
    time.sleep(0.1)
    porta.rts = False
    linhas = []
    tarefa = None
    with open(args.saida, "w", encoding="utf-8") as log:
        loop = asyncio.new_event_loop()
        tarefa = loop.create_task(pedir_leituras(args.leituras, args.pausa))
        while not tarefa.done():
            loop.run_until_complete(asyncio.sleep(0.05))
            for bruta in porta.readlines():
                linha = bruta.decode("utf-8", "replace").rstrip("\r\n")
                log.write(f"{time.strftime('%H:%M:%S')} {linha}\n")
                print(linha, flush=True)
                linhas.append(linha)
        tarefa.result()
        time.sleep(1)
        for bruta in porta.readlines():
            linha = bruta.decode("utf-8", "replace").rstrip("\r\n")
            log.write(f"{time.strftime('%H:%M:%S')} {linha}\n")
            linhas.append(linha)

    cabecalho = "tempo_s, temp_c, umidade_pct, lux, lux_min_acum, seg_sem_sucesso, enviado"
    # Só conta o que vem depois do cabeçalho: antes dele está a saída da ROM no boot
    depois = linhas[linhas.index(cabecalho) + 1:] if cabecalho in linhas else []
    dados = [l for l in depois if l and not l.startswith("#")]
    leitor = csv.reader(io.StringIO("\n".join(dados)), skipinitialspace=True)
    campos = [len(c) for c in leitor]
    ok = sum(n == 7 for n in campos)
    print(f"\nCT-05: cabeçalho {'presente' if cabecalho in linhas else 'AUSENTE'}; "
          f"{ok} de {len(campos)} linhas de dados com 7 campos")


if __name__ == "__main__":
    main()
