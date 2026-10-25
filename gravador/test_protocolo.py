"""Confere o decodificador contra os três pacotes de exemplo do README.

    python -m unittest discover gravador
"""

import unittest

from protocolo import comando_confirmar, decodificar


class TestePacotesDoReadme(unittest.TestCase):
    def test_normal(self):
        p = decodificar(bytes.fromhex("07 B2 A1 F0 49 02 00 26 07 00 00 D2 09 A8 16 20 4E 00 00"))
        self.assertEqual(p["seq"], 7)
        self.assertEqual(p["id_reinicio"], 0xA1B2)
        self.assertEqual(p["lux_min_acum"], 150000)
        self.assertEqual(p["seg_sem_sucesso"], 1830)
        self.assertAlmostEqual(p["temp_c"], 25.14)
        self.assertAlmostEqual(p["umid_pct"], 58.0)
        self.assertEqual(p["lux"], 20000)

    def test_sensores_ausentes(self):
        p = decodificar(bytes.fromhex("08 B2 A1 F0 49 02 00 52 08 00 00 00 80 FF FF FF FF FF FF"))
        self.assertEqual(p["seq"], 8)
        self.assertIsNone(p["temp_c"])
        self.assertIsNone(p["umid_pct"])
        self.assertIsNone(p["lux"])

    def test_noite_negativa(self):
        p = decodificar(bytes.fromhex("09 01 00 FA FF FF FF 3C 00 00 00 A2 FE 40 1F 00 00 00 00"))
        self.assertEqual(p["id_reinicio"], 1)
        self.assertEqual(p["lux_min_acum"], 0xFFFFFFFA)
        self.assertAlmostEqual(p["temp_c"], -3.5)
        self.assertAlmostEqual(p["umid_pct"], 80.0)
        self.assertEqual(p["lux"], 0)

    def test_tamanho_errado(self):
        self.assertIsNone(decodificar(b""))
        self.assertIsNone(decodificar(bytes(18)))

    def test_confirmacao(self):
        self.assertEqual(comando_confirmar(7), b"\x02\x07")


if __name__ == "__main__":
    unittest.main()
