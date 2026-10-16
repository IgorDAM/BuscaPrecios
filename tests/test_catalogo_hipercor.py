"""Pruebas del rastreo de Hipercor con la forma real del estado de la página
(producto de leche verificado en vivo el 2026-10-16)."""

import unittest

from src.catalogo.hipercor import ruta_categoria, producto_desde_estado, rastrear
from src.supermarkets.navegador import SupermercadoCaido

LECHE = {
    "id": "B001020616600035",
    "description": "leche semidesnatada brik 1 l - Asturiana",
    "categories": [
        {"identifier": "6807.1083618121"},
        {"name": "Leche semidesnatada", "identifier": "6807.349119",
         "parent_category": {"name": "Leche y bebidas vegetales", "identifier": "6807.346119",
                             "parent_category": {"name": "Lácteos", "identifier": "6807.345119",
                                                 "parent_category": {"name": "Lácteos", "identifier": "6807.1083618121",
                                                                     "parent_category": {"name": "Hipercor", "identifier": "x"}}}}},
    ],
    "brand": {"name": "asturiana", "url": "/supermercado/marcas/asturiana/"},
    "url": "/supermercado/B001020616600035-asturiana-leche-semidesnatada-brik-1-l/",
    "priceSpecification": {"price": "1,09", "salePrice": "1,09", "measurementUnitPrice": "1,09", "pum_description": "Litro"},
    "type": "item",
}


class Producto(unittest.TestCase):
    def test_leche(self):
        p = producto_desde_estado(LECHE)
        self.assertEqual(p["pid"], "B001020616600035")
        self.assertEqual(p["marca"], "asturiana")
        self.assertEqual(p["precio"], 1.09)
        self.assertEqual((p["precio_unidad"], p["unidad"]), (1.09, "L"))
        self.assertEqual(p["categoria"], "Lácteos > Leche y bebidas vegetales > Leche semidesnatada")
        self.assertTrue(p["url"].startswith("https://www.hipercor.es/supermercado/B001"))

    def test_oferta_usa_precio_de_venta(self):
        d = {**LECHE, "priceSpecification": {"price": "2,00", "salePrice": "1,50"}}
        p = producto_desde_estado(d)
        self.assertEqual(p["precio"], 1.5)
        self.assertIsNone(p["precio_unidad"])
        self.assertEqual(p["unidad"], "")

    def test_miles_con_punto(self):
        d = {**LECHE, "priceSpecification": {"price": "1.234,50", "salePrice": "1.234,50"}}
        self.assertEqual(producto_desde_estado(d)["precio"], 1234.5)

    def test_sin_precio_o_sin_id(self):
        self.assertIsNone(producto_desde_estado({**LECHE, "priceSpecification": {}}))
        self.assertIsNone(producto_desde_estado({**LECHE, "id": ""}))

    def test_ruta_sin_categorias(self):
        self.assertEqual(ruta_categoria([{"identifier": "x"}]), "")
        self.assertEqual(ruta_categoria(None), "")


def item(i):
    return {**LECHE, "id": f"B{i}", "description": f"producto {i}"}


def fake_paginas(paginas_por_cat, malas=()):
    """leer_pagina falso: 2 productos por página; `malas` = {(cat, n)} que no cargan."""
    llamadas = []

    def leer(cat, n):
        llamadas.append((cat, n))
        if (cat, n) in malas:
            return None
        return [item(f"{cat}-{n}-{k}") for k in range(2)], paginas_por_cat[cat]
    return leer, llamadas


class Rastreo(unittest.TestCase):
    def run_rastreo(self, leer, cats, **kw):
        return rastrear(leer, categorias=cats, pausa_s=0, dormir=lambda s: None, log=lambda m: None, **kw)

    def test_recorre_todas_las_paginas(self):
        leer, llamadas = fake_paginas({"a": 3, "b": 2})
        r = self.run_rastreo(leer, ["a", "b"])
        self.assertEqual(len(llamadas), 5)
        self.assertEqual(len(r.productos), 10)
        self.assertEqual(r.n_hojas, 5)
        self.assertEqual(r.fallos, [])

    def test_deduplica_entre_paginas(self):
        def leer(cat, n):
            return [item("igual")], 3
        r = self.run_rastreo(leer, ["a"])
        self.assertEqual(len(r.productos), 1)

    def test_pagina_mala_se_reintenta_y_se_registra(self):
        leer, llamadas = fake_paginas({"a": 3}, malas={("a", 2)})
        r = self.run_rastreo(leer, ["a"])
        self.assertEqual(r.fallos, ["a página 2"])
        self.assertEqual(len(r.productos), 4)  # páginas 1 y 3
        self.assertEqual(llamadas.count(("a", 2)), 3)  # 3 intentos

    def test_bloqueo_seguido_aborta(self):
        malas = {("a", n) for n in range(2, 20)}
        leer, _ = fake_paginas({"a": 19}, malas=malas)
        with self.assertRaises(SupermercadoCaido):
            self.run_rastreo(leer, ["a"])

    def test_max_hojas_limita_paginas(self):
        leer, llamadas = fake_paginas({"a": 50, "b": 50})
        r = self.run_rastreo(leer, ["a", "b"], max_hojas=4)
        self.assertEqual(len(llamadas), 4)
        self.assertEqual(r.n_hojas, 4)

    def test_primera_pagina_mala_no_se_cuelga(self):
        leer, _ = fake_paginas({"a": 3, "b": 1}, malas={("a", 1)})
        r = self.run_rastreo(leer, ["a", "b"])
        self.assertEqual(r.fallos, ["a página 1"])  # total desconocido: se pasa a la siguiente categoría
        self.assertEqual(len(r.productos), 2)


if __name__ == "__main__":
    unittest.main()
