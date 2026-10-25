"""Gravador da campanha do FitoSfera: central BLE que guarda cada pacote do nó.

Faz o papel que o aplicativo vai fazer no futuro: procura o nó pelo nome,
conecta, assina a notificação da característica de leitura e, a cada pacote,
primeiro grava a linha no CSV (com fsync) e só depois confirma com
[0x02, seq]. Assim, um pacote confirmado está sempre no disco.

Quando a conexão cai, anota o evento e volta a procurar o nó, sem parar.
Se o enlace continua de pé mas nenhum pacote chega por mais de dois períodos,
derruba a conexão e começa de novo (o nó pode ter travado com o rádio vivo).

    python gravador/gravador.py --saida dados/mensagens.csv --eventos dados/eventos.csv

Ctrl+C encerra e anota o fim no arquivo de eventos.
"""

import argparse
import asyncio
import csv
import os
import signal
import time
from datetime import datetime, timezone

from bleak import BleakClient, BleakScanner

import protocolo

TEMPO_BUSCA_S = 20
ESPERA_MIN_S = 2
ESPERA_MAX_S = 60
SILENCIO_MAX_S = 2 * protocolo.PERIODO_S + 30


def agora():
    t = time.time()
    return t, datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="milliseconds")


class ArquivoCsv:
    """CSV só de acréscimo: cada linha vai para o disco antes de a função voltar."""

    def __init__(self, caminho, colunas):
        pasta = os.path.dirname(caminho)
        if pasta:
            os.makedirs(pasta, exist_ok=True)
        novo = not os.path.exists(caminho) or os.path.getsize(caminho) == 0
        self._arquivo = open(caminho, "a", newline="", encoding="utf-8")
        self._escritor = csv.DictWriter(self._arquivo, fieldnames=colunas)
        if novo:
            self._escritor.writeheader()
            self._gravar_no_disco()

    def escrever(self, linha):
        self._escritor.writerow(linha)
        self._gravar_no_disco()

    def _gravar_no_disco(self):
        self._arquivo.flush()
        os.fsync(self._arquivo.fileno())

    def fechar(self):
        self._arquivo.close()


class Gravador:
    def __init__(self, mensagens, eventos, nome, endereco):
        self.mensagens = mensagens
        self.eventos = eventos
        self.nome = nome
        self.endereco = endereco
        self.recebidos = 0

    def evento(self, evento, detalhe=""):
        ts, hora = agora()
        self.eventos.escrever({"ts": f"{ts:.3f}", "hora_utc": hora, "evento": evento, "detalhe": detalhe})
        print(f"{hora} # {evento} {detalhe}".rstrip(), flush=True)

    def guardar(self, endereco, dados):
        """Grava o pacote e devolve a sequência a confirmar (None se fora do contrato)."""
        ts, hora = agora()
        pacote = protocolo.decodificar(dados)
        linha = {"ts_recebido": f"{ts:.3f}", "hora_utc": hora, "endereco": endereco,
                 "tamanho": len(dados), "bytes_hex": bytes(dados).hex()}
        if pacote:
            linha.update({k: ("" if v is None else v) for k, v in pacote.items()})
        self.mensagens.escrever(linha)
        self.recebidos += 1
        if not pacote:
            self.evento("fora_do_contrato", f"{len(dados)} bytes")
            return None
        print(f"{hora} seq={pacote['seq']} boot={pacote['id_reinicio']:04x} "
              f"T={pacote['temp_c']} UR={pacote['umid_pct']} lux={pacote['lux']} "
              f"acum={pacote['lux_min_acum']} sem_sucesso={pacote['seg_sem_sucesso']}s", flush=True)
        return pacote["seq"]

    async def procurar(self):
        def eh_o_no(dispositivo, anuncio):
            if self.endereco:
                return dispositivo.address.upper() == self.endereco.upper()
            return (anuncio.local_name == self.nome or dispositivo.name == self.nome
                    or protocolo.UUID_SERVICO in anuncio.service_uuids)

        achados = {}

        def anotar(dispositivo, anuncio):
            if eh_o_no(dispositivo, anuncio):
                achados[dispositivo.address] = anuncio.rssi

        async with BleakScanner(detection_callback=anotar):
            fim = time.monotonic() + TEMPO_BUSCA_S
            while not achados and time.monotonic() < fim:
                await asyncio.sleep(0.5)
        if not achados:
            return None, None
        endereco = next(iter(achados))
        return endereco, achados[endereco]

    async def sessao(self, endereco):
        """Uma conexão, do início até cair. Devolve quando ela cai."""
        caiu = asyncio.Event()
        confirmar = asyncio.Queue()
        ultimo_pacote = time.monotonic()

        def ao_desconectar(_cliente):
            caiu.set()

        def ao_notificar(_caracteristica, dados):
            nonlocal ultimo_pacote
            ultimo_pacote = time.monotonic()
            seq = self.guardar(endereco, dados)
            if seq is not None:
                confirmar.put_nowait(seq)

        async with BleakClient(endereco, disconnected_callback=ao_desconectar, timeout=20) as cliente:
            self.evento("conectado", endereco)
            await cliente.start_notify(protocolo.UUID_LEITURA, ao_notificar)
            self.evento("inscrito", "a assinatura faz o nó medir e enviar na hora")

            while not caiu.is_set():
                try:
                    seq = await asyncio.wait_for(confirmar.get(), timeout=5)
                except asyncio.TimeoutError:
                    if time.monotonic() - ultimo_pacote > SILENCIO_MAX_S:
                        self.evento("silencio", f"nenhum pacote em {SILENCIO_MAX_S} s; reconectando")
                        break
                    continue
                try:
                    await cliente.write_gatt_char(protocolo.UUID_COMANDO,
                                                  protocolo.comando_confirmar(seq), response=True)
                except Exception as erro:  # a conexão pode cair entre gravar e confirmar
                    self.evento("confirmacao_falhou", f"seq {seq}: {erro}")
        self.evento("desconectado", endereco)

    async def rodar(self):
        self.evento("inicio_gravador", f"procurando '{self.endereco or self.nome}'")
        espera = ESPERA_MIN_S
        while True:
            try:
                endereco, rssi = await self.procurar()
                if not endereco:
                    self.evento("nao_encontrado", f"nada em {TEMPO_BUSCA_S} s; nova busca em {espera} s")
                else:
                    self.evento("encontrado", f"{endereco} rssi={rssi} dBm")
                    antes = self.recebidos
                    await self.sessao(endereco)
                    if self.recebidos > antes:
                        espera = ESPERA_MIN_S
            except Exception as erro:
                self.evento("erro", f"{type(erro).__name__}: {erro}")
            await asyncio.sleep(espera)
            espera = min(espera * 2, ESPERA_MAX_S)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--saida", default="dados/mensagens.csv", help="CSV das leituras (acrescenta se já existir)")
    parser.add_argument("--eventos", default="dados/eventos.csv", help="CSV de conexões, quedas e erros")
    parser.add_argument("--nome", default=protocolo.NOME_BLE, help="nome anunciado pelo nó")
    parser.add_argument("--endereco", help="endereço BLE do nó, para não conectar em outro FitoSfera por perto")
    args = parser.parse_args()

    mensagens = ArquivoCsv(args.saida, protocolo.COLUNAS_MENSAGENS)
    eventos = ArquivoCsv(args.eventos, protocolo.COLUNAS_EVENTOS)
    gravador = Gravador(mensagens, eventos, args.nome, args.endereco)
    # Rodando em segundo plano por um script, o SIGINT chega ignorado; kill -INT e kill -TERM
    # encerram como o Ctrl+C, anotando o fim no arquivo de eventos
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    try:
        asyncio.run(gravador.rodar())
    except KeyboardInterrupt:
        pass
    finally:
        gravador.evento("fim_gravador", f"{gravador.recebidos} pacotes nesta execução")
        mensagens.fechar()
        eventos.fechar()


if __name__ == "__main__":
    main()
