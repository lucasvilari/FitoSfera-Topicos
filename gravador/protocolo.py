"""Contrato BLE do FitoSfera (versão 2), do lado de quem recebe.

Espelha firmware/src/main.cpp e a seção "Contrato BLE" do README. É usado
pelo gravador (que decodifica o pacote para gravar o CSV) e pelo
qualidade.py (que relê o CSV).
"""

import struct

NOME_BLE = "FitoSfera"
UUID_SERVICO = "f1705f3a-0001-4c7e-9a5b-3d0a6e2b9c10"
UUID_LEITURA = "f1705f3a-0002-4c7e-9a5b-3d0a6e2b9c10"
UUID_COMANDO = "f1705f3a-0003-4c7e-9a5b-3d0a6e2b9c10"

CMD_MEDIR_AGORA = 0x01
CMD_CONFIRMAR = 0x02

TAMANHO_PACOTE = 19
# Período do ciclo de medição do firmware (INTERVALO_MS)
PERIODO_S = 300

TEMP_AUSENTE = -32768
UMID_AUSENTE = 0xFFFF
LUX_AUSENTE = 0xFFFFFFFF

# uint8 seq, uint16 id do reinício, uint32 lux x min acumulados,
# uint32 segundos sem confirmação, int16 temp, uint16 umid, uint32 lux
_FORMATO = struct.Struct("<BHIIhHI")


def decodificar(dados):
    """Devolve um dicionário com os campos do pacote, ou None se o tamanho
    não for o do contrato. Campos sem leitura vêm como None."""
    if len(dados) != TAMANHO_PACOTE:
        return None
    seq, boot, acum, sem_sucesso, temp, umid, lux = _FORMATO.unpack(bytes(dados))
    return {
        "seq": seq,
        "id_reinicio": boot,
        "lux_min_acum": acum,
        "seg_sem_sucesso": sem_sucesso,
        "temp_c": None if temp == TEMP_AUSENTE else temp / 100,
        "umid_pct": None if umid == UMID_AUSENTE else umid / 100,
        "lux": None if lux == LUX_AUSENTE else lux,
    }


# Colunas dos arquivos do gravador. O carimbo de tempo é do computador que
# recebeu: o nó não tem relógio.
COLUNAS_MENSAGENS = [
    "ts_recebido", "hora_utc", "endereco", "tamanho", "bytes_hex",
    "seq", "id_reinicio", "lux_min_acum", "seg_sem_sucesso",
    "temp_c", "umid_pct", "lux",
]
COLUNAS_EVENTOS = ["ts", "hora_utc", "evento", "detalhe"]


def comando_confirmar(seq):
    return bytes([CMD_CONFIRMAR, seq & 0xFF])
