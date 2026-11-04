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


class RastrearReanudable(unittest.TestCase):
    """Alcampo muestra un CAPTCHA tras ~25-28 peticiones: el rastreo se reparte
    en varias ejecuciones con un tope de peticiones y progreso guardado."""

    def setUp(self):
        self.raices = [(f"r{i}", f"Raíz {i}") for i in range(6)]
        self.guardados = []

    def _servidor(self, paginas_por_raiz=3, caducan_tokens=False):
        """Cada raíz tiene `paginas_por_raiz` páginas con productos propios."""
        llamadas = []

        def pedir(ruta):
            llamadas.append(ruta)
            rid = ruta.split("categoryId=")[1].split("&")[0]
            tok = ruta.split("pageToken=")[1] if "pageToken=" in ruta else None
            if tok and caducan_tokens:
                raise RuntimeError("HTTP 400 token caducado")
            n = int(tok.split("-")[1]) if tok else 0
            prods = [api_prod(f"{rid}-{n}-{k}", f"P {rid} {n} {k} 1 l", 1) for k in range(2)]
            sig = f"{rid}-{n + 1}" if n + 1 < paginas_por_raiz else None
            return {"productGroups": [{"decoratedProducts": prods}],
                    "metadata": {"nextPageToken": sig} if sig else {}}
        return pedir, llamadas

    def _ejecutar(self, pedir, estado, maxp):
        return rastrear(pedir, self.raices, log=lambda _: None, dormir=lambda _: None,
                        estado=estado, guardar=lambda e: self.guardados.append(1), max_peticiones=maxp)

    def test_respeta_el_tope_y_marca_pendiente(self):
        pedir, llamadas = self._servidor()
        r = self._ejecutar(pedir, {}, 7)
        self.assertEqual(len(llamadas), 7)
        self.assertTrue(r.fallos and all("pendiente" in f for f in r.fallos))

    def test_varias_ejecuciones_completan_sin_perder_ni_duplicar(self):
        pedir, llamadas = self._servidor()
        estado = {}
        for _ in range(10):
            r = self._ejecutar(pedir, estado, 7)
            if not r.fallos:
                break
        self.assertEqual(r.fallos, [])
        self.assertEqual(len(r.productos), 6 * 3 * 2)           # todas las raíces, sin duplicados
        self.assertEqual(len(llamadas), 6 * 3)                  # ni una petición repetida

    def test_token_caducado_reinicia_la_raiz_en_curso(self):
        pedir, _ = self._servidor(caducan_tokens=False)
        estado = {"hechas": {}, "en_curso": {"id": "r0", "token": "r0-1", "productos": []}}
        pedir_caducado, _ = self._servidor(paginas_por_raiz=1, caducan_tokens=True)
        r = self._ejecutar(pedir_caducado, estado, 50)
        self.assertEqual(r.fallos, [])
        self.assertEqual(len(r.productos), 6 * 1 * 2)

    def test_captcha_conserva_lo_ya_descargado(self):
        pedir, _ = self._servidor(paginas_por_raiz=1)
        estado = {}

        def con_captcha(ruta):
            if "categoryId=r3" in ruta:
                raise BloqueoWAF("verificación humana pedida (HTTP 405 captcha)")
            return pedir(ruta)

        r = self._ejecutar(con_captcha, estado, 50)
        self.assertEqual(sorted(estado["hechas"]), ["r0", "r1", "r2"])   # guardado
        self.assertTrue(r.fallos)
        # siguiente ejecución, sin captcha: solo pide lo que falta
        pedir2, llamadas2 = self._servidor(paginas_por_raiz=1)
        r2 = self._ejecutar(pedir2, estado, 50)
        self.assertEqual(r2.fallos, [])
        self.assertEqual(len(llamadas2), 3)                              # r3, r4, r5
        self.assertEqual(len(r2.productos), 6 * 2)


class Progreso(unittest.TestCase):
    def test_guardar_y_cargar_y_caducidad(self):
        import tempfile
        from datetime import datetime, timedelta, timezone
        from pathlib import Path
        from src.catalogo.alcampo import cargar_progreso, guardar_progreso
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "p.json"
            self.assertEqual(cargar_progreso(ruta), {})
            guardar_progreso({"hechas": {"r0": []}}, ruta)
            self.assertEqual(list(cargar_progreso(ruta)["hechas"]), ["r0"])
            futuro = datetime.now(timezone.utc) + timedelta(hours=25)
            self.assertEqual(cargar_progreso(ruta, ahora=futuro), {})


if __name__ == "__main__":
    unittest.main()
