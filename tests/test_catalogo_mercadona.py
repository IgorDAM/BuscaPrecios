"""Pruebas del rastreo de Mercadona con datos con la forma real de su API
(campos tomados de respuestas reales verificadas el 2026-10-16)."""

import unittest

from src.catalogo.mercadona import producto_desde_api, rastrear


def api_producto(id_, nombre, unit_price, ref_price, ref_fmt, **extra):
    pi = {"unit_price": unit_price, "reference_price": ref_price, "reference_format": ref_fmt,
          "previous_unit_price": None, "price_decreased": False}
    pi.update(extra)
    return {"id": id_, "display_name": nombre, "share_url": f"https://tienda.mercadona.es/product/{id_}/x",
            "price_instructions": pi}


ACEITE = api_producto("4241", "Aceite de oliva 0,4º Hacendado", "17.25", "3.450", "L")


class ProductoDesdeApi(unittest.TestCase):
    def test_aceite_litro(self):
        p = producto_desde_api(ACEITE, "Aceite > Aceite de oliva")
        self.assertEqual(p["pid"], "4241")
        self.assertEqual(p["precio"], 17.25)
        self.assertEqual(p["precio_unidad"], 3.45)
        self.assertEqual(p["unidad"], "L")
        self.assertEqual(p["categoria"], "Aceite > Aceite de oliva")

    def test_cien_gramos_pasa_a_kilo(self):
        p = producto_desde_api(api_producto("1", "Jamón", "1.50", "1.250", "100 g"))
        self.assertEqual((p["unidad"], p["precio_unidad"]), ("kg", 12.5))

    def test_cien_ml_pasa_a_litro(self):
        p = producto_desde_api(api_producto("1", "Gel", "2.00", "0.400", "100 ml"))
        self.assertEqual((p["unidad"], p["precio_unidad"]), ("L", 4.0))

    def test_docena_y_unidad(self):
        self.assertEqual(producto_desde_api(api_producto("1", "Huevos", "2.5", "2.5", "dz"))["unidad"], "docena")
        self.assertEqual(producto_desde_api(api_producto("1", "Pila", "2.5", "0.5", "ud"))["unidad"], "ud")

    def test_formato_raro_sin_precio_unidad(self):
        p = producto_desde_api(api_producto("1", "Cable", "2.5", "1.0", "m"))
        self.assertIsNone(p["precio_unidad"])
        self.assertEqual(p["unidad"], "")

    def test_rebajado_usa_precio_actual(self):
        p = producto_desde_api(api_producto("1", "Leche", "0.89", "0.89", "L",
                                            previous_unit_price="0.96", price_decreased=True))
        self.assertEqual(p["precio"], 0.89)

    def test_sin_precio_se_descarta(self):
        self.assertIsNone(producto_desde_api(api_producto("1", "X", None, None, "kg")))


def fake_api(n_sub=12, fallo_en=None):
    subs = [{"id": 100 + i, "name": f"Sub{i}"} for i in range(n_sub)]
    raiz = {"count": 1, "results": [{"id": 1, "name": "Nivel1", "categories": subs}]}
    respuestas = {"/api/categories/?lang=es": raiz}
    for i, s in enumerate(subs):
        prods = [api_producto(f"{i}-{k}", f"Prod {i}-{k}", "1.00", "2.000", "kg") for k in range(3)]
        prods.append(ACEITE)  # el mismo producto aparece en varias categorías
        respuestas[f"/api/categories/{s['id']}/?lang=es"] = {"categories": [{"name": "Hijo", "products": prods}]}

    def pedir(ruta):
        if fallo_en is not None and ruta == f"/api/categories/{fallo_en}/?lang=es":
            raise RuntimeError("HTTP 500")
        return respuestas[ruta]
    return pedir


class Rastreo(unittest.TestCase):
    def test_recorre_y_deduplica(self):
        r = rastrear(fake_api(), pausa_s=0, dormir=lambda s: None, log=lambda m: None)
        self.assertEqual(len(r.productos), 12 * 3 + 1)  # 36 propios + el aceite una sola vez
        self.assertEqual(r.fallos, [])
        self.assertEqual(r.n_hojas, 12)
        aceite = next(p for p in r.productos if p["pid"] == "4241")
        self.assertEqual(aceite["categoria"], "Nivel1 > Sub0 > Hijo")  # la primera que lo trae

    def test_subcategoria_fallida_se_registra(self):
        esperas = []
        r = rastrear(fake_api(fallo_en=103), pausa_s=0, dormir=esperas.append, log=lambda m: None)
        self.assertEqual(len(r.fallos), 1)
        self.assertIn("Sub3", r.fallos[0])
        self.assertEqual(len(r.productos), 11 * 3 + 1)
        self.assertIn(3, esperas)  # reintentos con espera creciente

    def test_portada_sospechosa_aborta(self):
        with self.assertRaises(RuntimeError):
            rastrear(fake_api(n_sub=3), dormir=lambda s: None, log=lambda m: None)

    def test_max_hojas(self):
        r = rastrear(fake_api(), max_hojas=2, pausa_s=0, dormir=lambda s: None, log=lambda m: None)
        self.assertEqual(r.n_hojas, 2)
        self.assertEqual(len(r.productos), 2 * 3 + 1)


if __name__ == "__main__":
    unittest.main()
