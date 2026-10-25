"""Ensaios provocados pelo central: CT-14 (confirmação), CT-13 (medir agora) e CT-02 (luz sob sol).

Faz com o nó o que o nRF Connect faria à mão, mas cronometrando: anota o instante
de cada comando e o do pacote que ele provoca. Rodar com o gravador da campanha
parado (o nó aceita um central por vez).

    python gravador/ensaio.py --saida ensaios/ct13-14-02.csv
"""

import argparse
import asyncio
import csv
import os
import statistics
import time
from datetime import datetime, timezone

from bleak import BleakClient, BleakScanner

import protocolo

ESPERA_PACOTE_S = 10


def hora(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="milliseconds")


class Ensaio:
    def __init__(self, cliente, escritor):
        self.cliente = cliente
        self.escritor = escritor
        self.fila = asyncio.Queue()

    def ao_notificar(self, _caracteristica, dados):
        self.fila.put_nowait((time.time(), bytes(dados)))

    async def proximo(self, ct, acao, t_acao):
        """Espera o pacote provocado pela ação e grava a linha do ensaio."""
        t, dados = await asyncio.wait_for(self.fila.get(), ESPERA_PACOTE_S)
        pacote = protocolo.decodificar(dados) or {}
        linha = {"ct": ct, "acao": acao, "ts_acao": f"{t_acao:.3f}", "ts_recebido": f"{t:.3f}",
                 "hora_utc": hora(t), "latencia_s": f"{t - t_acao:.3f}", "tamanho": len(dados),
                 "bytes_hex": dados.hex(), **{k: ("" if v is None else v) for k, v in pacote.items()}}
        self.escritor.writerow(linha)
        print(f"{ct:6} {acao:22} {t - t_acao:6.3f} s  tam={len(dados)} seq={pacote.get('seq')} "
              f"sem_sucesso={pacote.get('seg_sem_sucesso')}s lux={pacote.get('lux')} "
              f"T={pacote.get('temp_c')} UR={pacote.get('umid_pct')}", flush=True)
        return pacote, t - t_acao

    async def comando(self, dados):
        t = time.time()
        await self.cliente.write_gatt_char(protocolo.UUID_COMANDO, dados, response=True)
        return t

    async def medir(self, ct, acao="01"):
        return await self.proximo(ct, acao, await self.comando(bytes([protocolo.CMD_MEDIR_AGORA])))

    async def confirmar(self, seq):
        await self.comando(protocolo.comando_confirmar(seq))


async def rodar(args, escritor):
    print("procurando o nó...", flush=True)
    dispositivo = await BleakScanner.find_device_by_filter(
        lambda d, a: (d.address.upper() == args.endereco.upper()) if args.endereco
        else (a.local_name == protocolo.NOME_BLE or protocolo.UUID_SERVICO in a.service_uuids),
        timeout=20)
    if not dispositivo:
        raise SystemExit("nó não encontrado")
    async with BleakClient(dispositivo, timeout=20) as cliente:
        e = Ensaio(cliente, escritor)
        t = time.time()
        await cliente.start_notify(protocolo.UUID_LEITURA, e.ao_notificar)
        primeiro, _ = await e.proximo("CT-13", "assinatura", t)

        # CT-14: sem confirmar, o contador cresce; confirmando o pacote em espera, zera
        await asyncio.sleep(args.pausa)
        sem1, _ = await e.medir("CT-14", "01 sem confirmar")
        await asyncio.sleep(args.pausa)
        sem2, _ = await e.medir("CT-14", "01 sem confirmar")
        await e.confirmar((sem2["seq"] + 1) & 0xFF)  # sequência errada: não deve zerar
        await asyncio.sleep(args.pausa)
        errado, _ = await e.medir("CT-14", "01 apos 02 seq errada")
        await e.confirmar(errado["seq"])
        await asyncio.sleep(args.pausa)
        certo, _ = await e.medir("CT-14", "01 apos 02 seq certa")
        await e.confirmar(certo["seq"])

        # CT-13: 10 pedidos de medida, confirmando cada um
        latencias, seqs = [], [certo["seq"]]
        for i in range(10):
            await asyncio.sleep(args.pausa)
            p, lat = await e.medir("CT-13", f"01 ({i + 1}/10)")
            await e.confirmar(p["seq"])
            latencias.append(lat)
            seqs.append(p["seq"])

        # CT-02: 3 leituras de luz
        luzes = []
        for i in range(3):
            await asyncio.sleep(args.pausa)
            p, _ = await e.medir("CT-02", f"01 ({i + 1}/3)")
            await e.confirmar(p["seq"])
            luzes.append(p["lux"])

    seguidas = all((b - a) & 0xFF == 1 for a, b in zip(seqs, seqs[1:]))
    print("\n## Resumo")
    print(f"CT-14 contador sem confirmar: {primeiro['seg_sem_sucesso']} -> {sem1['seg_sem_sucesso']} -> "
          f"{sem2['seg_sem_sucesso']} s; após 02 com seq errada: {errado['seg_sem_sucesso']} s; "
          f"após 02 com seq certa: {certo['seg_sem_sucesso']} s")
    print(f"CT-13 latência do 01: mediana {statistics.median(latencias):.3f} s, "
          f"máx {max(latencias):.3f} s; {sum(l <= 2 for l in latencias)} de 10 em até 2 s; "
          f"sequências {seqs} {'seguidas' if seguidas else 'COM SALTO'}")
    print(f"CT-02 lux: {luzes}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--saida", default="ensaios/ct13-14-02.csv")
    parser.add_argument("--endereco")
    parser.add_argument("--pausa", type=float, default=3, help="segundos entre os comandos")
    args = parser.parse_args()
    os.makedirs(os.path.dirname(args.saida) or ".", exist_ok=True)
    colunas = ["ct", "acao", "ts_acao", "ts_recebido", "hora_utc", "latencia_s", "tamanho", "bytes_hex",
               "seq", "id_reinicio", "lux_min_acum", "seg_sem_sucesso", "temp_c", "umid_pct", "lux"]
    with open(args.saida, "w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=colunas)
        escritor.writeheader()
        asyncio.run(rodar(args, escritor))


if __name__ == "__main__":
    main()
