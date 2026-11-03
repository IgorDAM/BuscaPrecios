"""
Pruebas del análisis de productos de Alcampo.

Cada caso es un elemento REAL de `productEntities` (compraonline.alcampo.es,
sesión de invitado con entrega en 33392 Gijón, leído el 2026-11-03),
recortado a los campos que usa el conector. Se ejecutan con:

    python -m unittest discover -s tests -t . -v
"""

import unittest

from src.supermarkets.alcampo import entidad_a_producto


def ent(pid, marca, nombre, actual, unidad, etiqueta, disponible=True):
    return {
        "retailerProductId": pid,
        "brand": marca,
        "available": disponible,
        "name": nombre,
        "price": {
            "current": {"amount": actual, "currency": "EUR"},
            "unit": {"label": etiqueta, "current": {"amount": unidad, "currency": "EUR"}},
        },
    }


LECHE_PACK = ent("54178", "PRODUCTO ALCAMPO", "AUCHAN Leche entera de vaca 6 x 1 l Producto Alcampo.",
                 "5.76", "0.96", "fop.price.per.litre")
LECHE_POLVO = ent("548508", "ASTURIANA", "ASTURIANA Leche en polvo entera 1 kg.",
                  "9.89", "9.89", "fop.price.per.kg")
JAMON_100G = ent("88201", "NAVIDUL", "NAVIDUL Jamón curado bodega, elaborado sin gluten ni lactosa y cortado en lonchas 45 g.",
                 "0.90", "2.00", "fop.price.per.100gram")
HUEVOS = ent("904493", "PRODUCTO ALCAMPO", "AUCHAN Huevos de gallinas sueltas en el gallinero clase M y cat. A 30 uds. Producto Alcampo",
             "6.55", "2.62", "fop.price.per.dozen")
HUEVOS_COCIDOS = ent("502361", "LA HUERTA DE GALLOCANTA", "LA HUERTA DE GALLOCANTA Huevo cocidos medianos 6 unidades",
                     "2.33", "0.39", "fop.price.per.each", disponible=False)


class EntidadAlcampo(unittest.TestCase):
    def test_precio_por_litro(self):
        p = entidad_a_producto(LECHE_PACK, "leche entera")
        self.assertEqual((p.precio, p.precio_unidad, p.unidad), (5.76, 0.96, "L"))
        self.assertEqual(p.marca, "PRODUCTO ALCAMPO")
        self.assertTrue(p.url.endswith("/products/54178"))

    def test_precio_por_kilo(self):
        p = entidad_a_producto(LECHE_POLVO)
        self.assertEqual((p.precio, p.precio_unidad, p.unidad), (9.89, 9.89, "kg"))

    def test_precio_por_100_gramos_se_pasa_a_kilo(self):
        # 0,90 € por 45 g = 20 €/kg, no 2 €/kg.
        p = entidad_a_producto(JAMON_100G)
        self.assertEqual((p.precio, p.precio_unidad, p.unidad), (0.90, 20.0, "kg"))

    def test_precio_por_docena(self):
        p = entidad_a_producto(HUEVOS)
        self.assertEqual((p.precio_unidad, p.unidad), (2.62, "docena"))

    def test_producto_no_disponible_se_descarta(self):
        self.assertIsNone(entidad_a_producto(HUEVOS_COCIDOS))

    def test_sin_precio_se_descarta(self):
        self.assertIsNone(entidad_a_producto({"name": "X", "available": True, "price": {}}))


if __name__ == "__main__":
    unittest.main()
