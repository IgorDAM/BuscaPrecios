"""
Precio por unidad de los productos que se cuentan por unidades ("6uds").
Nombres REALES de Más y Más y Alimerka leídos el 2026-11-03. Se ejecutan con:

    python -m unittest discover -s tests -t . -v
"""

import unittest

from src.supermarkets.medidas import precio_por_medida


class PrecioPorUnidades(unittest.TestCase):
    def test_huevos_por_unidades(self):
        self.assertEqual(precio_por_medida(1.80, "Huevos 'L' GRANJA RUALMAR 6uds"), (0.3, "ud"))
        self.assertEqual(precio_por_medida(1.85, "Huevo codorniz PITAS PITAS 18uds"), (0.1, "ud"))
        self.assertEqual(precio_por_medida(1.79, "HUEVOS CAMPEROS M/L 6 UDS."), (0.3, "ud"))
        self.assertEqual(precio_por_medida(1.99, "Huevo CAMPERO granel 6 unds"), (0.33, "ud"))
        self.assertEqual(precio_por_medida(2.85, "HUEVOS  A-M LA DOCENA"), (2.85, "docena"))

    def test_el_peso_o_volumen_tiene_prioridad(self):
        self.assertEqual(precio_por_medida(1.00, "Huevos de chocolate SAN ISIDRO 80g"), (12.5, "kg"))
        self.assertEqual(precio_por_medida(1.24, "Leche entera 1L"), (1.24, "L"))

    def test_unidades_de_regalo_no_se_adivinan(self):
        # "4 + 2uds" son 6 rollos, no 2: mejor no calcular nada.
        self.assertEqual(precio_por_medida(2.99, "Papel higienico seda 3 capas FOXY 4 + 2uds"), (None, ""))

    def test_sin_medida(self):
        self.assertEqual(precio_por_medida(5.99, "Antical Calgon"), (None, ""))


if __name__ == "__main__":
    unittest.main()
