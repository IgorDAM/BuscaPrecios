"""Rastreo del catálogo de Alcampo con datos con la forma de la API real
(`unitPrice`, `categoryPath`, `metadata.nextPageToken` vistos el 2026-11-04)."""

import unittest

from src.catalogo.alcampo import (
    BloqueoWAF, PAUSA_MINIMA_S, producto_desde_api, rastrear, _ruta,
)


def api_prod(rid, nombre, precio, unit_label=None, unit_precio=None, **extra):
    p = {
        "productId": f"uuid-{rid}", "retailerProductId": rid, "name": nombre,
        "brand": "AUCHAN", "available": True, "packSizeDescription": "1l",
        "price": {"amount": str(precio), "currency": "EUR"},
        "categoryPath": ["Frescos", "Charcutería", "Jamón"],
    }
    if unit_label:
        p["unitPrice"] = {"price": {"amount": str(unit_precio), "currency": "EUR"},
                          "unit": unit_label, "unitName": "PER_1KG"}
    p.update(extra)
    return p


class ProductoDesdeApi(unittest.TestCase):
    def test_jamon_por_kilo(self):
        p = producto_desde_api(api_prod("111", "EL POZO Jamón cocido 150 g.", "1.89", "fop.price.per.kg", "12.60"))
        self.assertEqual((p["pid"], p["precio"], p["precio_unidad"], p["unidad"]), ("111", 1.89, 12.6, "kg"))
        self.assertEqual(p["categoria"], "Frescos > Charcutería > Jamón")
        self.assertEqual(p["marca"], "AUCHAN")
        self.assertTrue(p["url"].endswith("/products/111"))

    def test_precio_anidado_en_current(self):
        p = producto_desde_api(api_prod("1", "Leche 1 l", 0.96, price={"current": {"amount": "0.96"}}))
        self.assertEqual(p["precio"], 0.96)

    def test_cien_gramos_a_kilo(self):
        p = producto_desde_api(api_prod("1", "Jamón", "1.50", "fop.price.per.100gram", "1.25"))
        self.assertEqual((p["unidad"], p["precio_unidad"]), ("kg", 12.5))

    def test_sin_etiqueta_usa_el_formato_del_nombre(self):
        p = producto_desde_api(api_prod("1", "AUCHAN Leche entera 6 x 1 l", "5.76"))
        self.assertEqual((p["unidad"], p["precio_unidad"]), ("L", 0.96))

    def test_no_disponible_se_descarta(self):
        self.assertIsNone(producto_desde_api(api_prod("1", "X", "1", available=False)))

    def test_sin_precio_o_nombre_se_descarta(self):
        self.assertIsNone(producto_desde_api(api_prod("1", "X", "1", price={})))
        self.assertIsNone(producto_desde_api(api_prod("1", "", "1")))


class Rastrear(unittest.TestCase):
    def setUp(self):
        self.dormidas = []
        self.raices = [(f"r{i}", f"Raíz {i}") for i in range(6)]

    def _rastrear(self, pedir, **kw):
        return rastrear(pedir, self.raices, log=lambda _: None, dormir=self.dormidas.append, **kw)

    def test_pagina_con_pageToken_y_deduplica(self):
        paginas = {
            _ruta("r0", None): {"productGroups": [{"decoratedProducts": [api_prod("1", "A 1 l", 1), api_prod("2", "B 1 l", 2)]}],
                                "metadata": {"nextPageToken": "T1"}},
            _ruta("r0", "T1"): {"productGroups": [{"decoratedProducts": [api_prod("2", "B 1 l", 2), api_prod("3", "C 1 l", 3)]}],
                                "metadata": {}},
        }
        vacia = {"productGroups": [], "metadata": {}}
        r = self._rastrear(lambda ruta: paginas.get(ruta, vacia))
        self.assertEqual(sorted(p["pid"] for p in r.productos), ["1", "2", "3"])
        self.assertEqual(r.fallos, [])

    def test_va_despacio(self):
        r = self._rastrear(lambda ruta: {"productGroups": [], "metadata": {}}, pausa_s=0.1)
        self.assertTrue(self.dormidas and all(d >= PAUSA_MINIMA_S for d in self.dormidas))

    def test_captcha_detiene_todo_sin_reintentar(self):
        llamadas = []

        def pedir(ruta):
            llamadas.append(ruta)
            if "categoryId=r1" in ruta:
                raise BloqueoWAF("verificación humana pedida (HTTP 405 captcha)")
            return {"productGroups": [{"decoratedProducts": [api_prod("1", "A 1 l", 1)]}], "metadata": {}}

        r = self._rastrear(pedir)
        self.assertEqual(sum("categoryId=r1" in x for x in llamadas), 1)   # sin reintentos
        self.assertFalse(any("categoryId=r2" in x for x in llamadas))      # no sigue con otras raíces
        self.assertEqual(len(r.fallos), 5)                                  # r1..r5
        self.assertEqual(len(r.productos), 1)

    def test_error_normal_no_para_las_demas_raices(self):
        def pedir(ruta):
            if "categoryId=r0" in ruta:
                raise RuntimeError("HTTP 500")
            return {"productGroups": [{"decoratedProducts": [api_prod(ruta[-3:], "A 1 l", 1)]}], "metadata": {}}
        r = self._rastrear(pedir)
        self.assertEqual(len(r.fallos), 1)
        self.assertTrue(r.productos)

    def test_pocas_raices_aborta(self):
        with self.assertRaises(RuntimeError):
            rastrear(lambda r: {}, [("a", "A")], log=lambda _: None, dormir=lambda _: None)


if __name__ == "__main__":
    unittest.main()
