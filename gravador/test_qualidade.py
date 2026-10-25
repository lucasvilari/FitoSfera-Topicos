"""Confere o qualidade.py contra um arquivo sintético com perdas, duplicata,
reinício, leitura extra e linha fora do contrato conhecidas de antemão.

O arquivo é gerado aqui, no teste; não é dado de campanha.

    python -m unittest discover gravador
"""

import csv
import io
import os
import struct
import tempfile
import unittest

import protocolo
import qualidade

T0 = 1792800000.0  # um instante qualquer
P = protocolo.PERIODO_S


def pacote(seq, boot, acum, sem_sucesso, temp=30.0, umid=50.0, lux=1000):
    return struct.pack("<BHIIhHI", seq % 256, boot, acum, sem_sucesso,
                       round(temp * 100), round(umid * 100), lux)


def linha(ts, dados):
    p = protocolo.decodificar(dados) or {}
    base = {"ts_recebido": f"{ts:.3f}", "hora_utc": "", "endereco": "AA:BB",
            "tamanho": len(dados), "bytes_hex": dados.hex()}
    base.update({k: ("" if v is None else v) for k, v in p.items()})
    return base


def montar():
    linhas = []
    # Boot 0x1111: seq 1..10 a cada período
    for i in range(10):
        linhas.append(linha(T0 + i * P, pacote(i + 1, 0x1111, i * 5000, P)))
    linhas.append(dict(linhas[-1]))  # duplicata da seq 10
    # Desconexão: o nó mede as seq 11, 12 e 13 sem ninguém ouvindo; o gravador volta,
    # assina e o nó manda a seq 14 na hora (extra, 30 s depois da medição da seq 13)
    t13 = T0 + 12 * P
    linhas.append(linha(t13 + 30, pacote(14, 0x1111, 70000, 4 * P)))
    # O ciclo recomeça na assinatura: seq 15 e 16
    linhas.append(linha(t13 + 30 + P, pacote(15, 0x1111, 75000, P)))
    linhas.append(linha(t13 + 30 + 2 * P, pacote(16, 0x1111, 80000, P)))
    # Comando 0x01 (medir agora) 40 s depois: seq 17, extra
    linhas.append(linha(t13 + 70 + 2 * P, pacote(17, 0x1111, 80500, 40)))
    # Linha fora do contrato
    linhas.append(linha(t13 + 75 + 2 * P, b"\x01\x02\x03"))
    # Queda de energia: 30 min sem nada, depois um boot novo que começa em seq 1
    t_boot = t13 + 30 + 2 * P + 1800
    for i in range(3):
        linhas.append(linha(t_boot + i * P, pacote(i + 1, 0x2222, i * 100, P, temp=31.0)))
    return linhas


class TesteQualidade(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.csv = os.path.join(self.pasta.name, "mensagens.csv")
        with open(self.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=protocolo.COLUNAS_MENSAGENS)
            w.writeheader()
            w.writerows(montar())

    def tearDown(self):
        self.pasta.cleanup()

    def test_contagens(self):
        validas, fora = qualidade.ler_mensagens(self.csv)
        self.assertEqual(len(fora), 1)
        unicas, duplicatas = qualidade.analisar(validas, P)
        self.assertEqual(duplicatas, 1)
        self.assertEqual(len(unicas), 17)
        self.assertEqual(sum(r["extra"] for r in unicas), 1)  # só a do comando 0x01
        self.assertEqual(sum(r["perdidas_antes"] for r in unicas), 3)  # seq 11, 12 e 13
        self.assertEqual(sum(r["reinicio"] for r in unicas), 1)

    def test_lacunas(self):
        validas, _ = qualidade.ler_mensagens(self.csv)
        unicas, _ = qualidade.analisar(validas, P)
        achadas = qualidade.lacunas(unicas, [], P)
        self.assertEqual(len(achadas), 2)
        self.assertIn("sem entregar", achadas[0]["causa"])
        self.assertIn("reiniciou", achadas[1]["causa"])

    def test_volta_da_sequencia(self):
        # 300 leituras perdidas: a sequência anda 301, o que mod 256 dá 45
        dados = [linha(T0, pacote(10, 1, 0, P)), linha(T0 + 301 * P, pacote(10 + 301, 1, 0, P))]
        with open(self.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=protocolo.COLUNAS_MENSAGENS)
            w.writeheader()
            w.writerows(dados)
        validas, _ = qualidade.ler_mensagens(self.csv)
        unicas, _ = qualidade.analisar(validas, P)
        self.assertEqual(unicas[1]["perdidas_antes"], 300)

    def test_tempos_de_conexao(self):
        eventos = [
            {"ts": T0 - 3.0, "evento": "encontrado", "detalhe": "AA:BB rssi=-71 dBm"},
            {"ts": T0 - 1.5, "evento": "conectado", "detalhe": "AA:BB"},
            {"ts": T0 + 9 * P + 10, "evento": "desconectado", "detalhe": "AA:BB"},
            {"ts": T0 + 12 * P + 25, "evento": "encontrado", "detalhe": "AA:BB rssi=-80 dBm"},
            {"ts": T0 + 12 * P + 28, "evento": "conectado", "detalhe": "AA:BB"},
        ]
        validas, _ = qualidade.ler_mensagens(self.csv)
        unicas, _ = qualidade.analisar(validas, P)
        t = qualidade.tempos_de_conexao(eventos, unicas)
        self.assertEqual(t["rssi"], [-71, -80])
        self.assertAlmostEqual(t["conectar"][0], 1.5)
        self.assertAlmostEqual(t["primeiro"][0], 1.5)   # seq 1 chega em T0
        self.assertAlmostEqual(t["primeiro"][1], 2.0)   # seq 14 chega 30 s depois da medição 13
        self.assertAlmostEqual(t["reconectar"][0], 3 * P + 18)

    def test_relatorio_roda(self):
        saida = io.StringIO()
        qualidade.relatorio(self.csv, None, P, saida=saida)
        texto = saida.getvalue()
        self.assertIn("reinicios do no             1", texto)
        self.assertIn("faltam (a sequencia pulou)  3", texto)


if __name__ == "__main__":
    unittest.main()
