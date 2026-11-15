"""Contrato do comando de velocidade, sem hardware."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from motor import protocolo as P


class TestVelocidade(unittest.TestCase):
    def test_pacote_assinado(self):
        self.assertEqual(P.comando_velocidade(-40, 60),
                         P.montar_comando(ord("R"), -40, 60))

    def test_rejeita_fora_da_faixa_e_fracao(self):
        for valor in (-121, 121, 1.5, True):
            with self.assertRaises(ValueError):
                P.comando_velocidade(valor, 0)


if __name__ == "__main__":
    unittest.main()
