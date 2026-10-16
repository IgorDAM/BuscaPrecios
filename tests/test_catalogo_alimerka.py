"""
Pruebas del rastreo del catálogo de Alimerka y del formato común, con una
sesión simulada (sin red). Las páginas reproducen la estructura verificada en
vivo el 2026-10-16: menú con enlaces `/<código>` y tarjetas `[data-pid]`.
"""

import json
import unittest
from datetime import datetime, timezone
from unittest import mock

from src.catalogo import alimerka as rastreador
from src.catalogo.formato import CAMPOS, catalogo_degradado, construir_catalogo, serializar
from src.supermarkets.alimerka import Alimerka
from tests.test_alimerka_tarjeta import ANTIGUO_RAW, tarjeta

BASE = "https://www.alimerkaonline.es"

PORTADA = f"""
<html><body><nav>
  <a href="/101">Alimentación</a>
  <a href="{BASE}/10117">Lo Tienes Hecho</a>
  <a href="/1011720">Arroces y Pastas</a>
  <a href="/101172010">Arroces</a>
  <a href="/101172020">Pastas</a>
  <a href="/102">  Bebidas  </a>
  <a href="/103"></a>
  <a href="/103">Carnicería</a>
  <a href="/10032039.html">Un producto, no una categoría</a>
  <a href="/on/demandware.store/Sites-Alimerka-Site/default/Cart-Show">Carrito</a>
  <a href="/12">Demasiado corto</a>
</nav></body></html>
"""


def pagina(pids):
    """HTML de Search-UpdateGrid con una tarjeta por pid."""
    return "<div>" + "".join(
        str(tarjeta(pid, "MARCA", f"PRODUCTO {pid} 1 KG", [f"{1 + int(pid) % 7},50 €"], "(2,00 €/kg)"))
        for pid in pids
    ) + "</div>"


class Respuesta:
    def __init__(self, texto="", error=None):
        self.text, self._error = texto, error

    def raise_for_status(self):
        if self._error:
            raise self._error


class SesionFalsa:
    """Imita requests.Session: portada y Search-UpdateGrid paginado."""

    def __init__(self, portada, catalogo, rotas=()):
        self.portada, self.catalogo, self.rotas = portada, catalogo, set(rotas)
        self.peticiones = []

    def get(self, url, params=None, timeout=None):
        if url.endswith("/") and params is None:
            return Respuesta(self.portada)
        cgid, start, sz = params["cgid"], params["start"], params["sz"]
        self.peticiones.append((cgid, start, sz))
        if cgid in self.rotas:
            return Respuesta(error=RuntimeError("503"))
        return Respuesta(pagina(self.catalogo.get(cgid, [])[start:start + sz]))


def alimerka_con(sesion):
    a = Alimerka("33012")
    a._session, a._preparada = sesion, True
    return a


def ejecutar(sesion, **kw):
    kw.setdefault("log", lambda m: None)
    kw.setdefault("dormir", lambda s: None)
    with mock.patch.object(rastreador, "MIN_CATEGORIAS", 3):
        return rastreador.rastrear(alimerka_con(sesion), **kw)


class Categorias(unittest.TestCase):
    def test_extrae_codigos_con_nombre_y_descarta_lo_que_no_es_categoria(self):
        cats = rastreador.extraer_categorias(PORTADA)
        self.assertEqual(cats["101"], "Alimentación")
        self.assertEqual(cats["10117"], "Lo Tienes Hecho")  # href absoluto
        self.assertEqual(cats["102"], "Bebidas")  # espacios normalizados
        self.assertEqual(cats["103"], "Carnicería")  # ignora el enlace sin texto
        self.assertNotIn("10032039", cats)  # /10032039.html es un producto
        self.assertNotIn("12", cats)  # demasiado corto
        self.assertEqual(len(cats), 7)

    def test_hojas_y_ruta_completa(self):
        hojas = dict(rastreador.hojas_con_ruta(rastreador.extraer_categorias(PORTADA)))
        self.assertEqual(
            hojas["101172010"], "Alimentación > Lo Tienes Hecho > Arroces y Pastas > Arroces"
        )
        self.assertEqual(hojas["102"], "Bebidas")  # una categoría sin hijas es su propia hoja
        self.assertNotIn("101", hojas)  # los padres no se rastrean
        self.assertEqual(sorted(hojas), ["101172010", "101172020", "102", "103"])


class Rastreo(unittest.TestCase):
    def test_pagina_hasta_acabar_y_une_las_hojas(self):
        sesion = SesionFalsa(PORTADA, {
            "101172010": [str(1000 + i) for i in range(5)],  # 5 productos, páginas de 2
            "101172020": ["2000", "2001"],
            "102": [],
            "103": ["3000"],
        })
        r = ejecutar(sesion, tam_pagina=2)
        self.assertEqual(len(r.productos), 8)
        self.assertEqual(r.fallos, [])
        # Arroces: 5 productos = páginas de 2+2+1 (la última, corta, corta el bucle).
        self.assertEqual([p for p in sesion.peticiones if p[0] == "101172010"],
                         [("101172010", 0, 2), ("101172010", 2, 2), ("101172010", 4, 2)])
        # Pastas: página llena (2 de 2) -> pide una más, que viene vacía.
        self.assertEqual(len([p for p in sesion.peticiones if p[0] == "101172020"]), 2)
        arroz = next(p for p in r.productos if p["pid"] == "1000")
        self.assertEqual(arroz["categoria"],
                         "Alimentación > Lo Tienes Hecho > Arroces y Pastas > Arroces")
        self.assertEqual((arroz["precio_unidad"], arroz["unidad"]), (2.0, "kg"))

    def test_un_producto_en_dos_hojas_se_guarda_una_vez(self):
        sesion = SesionFalsa(PORTADA, {"101172010": ["1", "2"], "101172020": ["2", "3"]})
        r = ejecutar(sesion, tam_pagina=96)
        self.assertEqual(sorted(p["pid"] for p in r.productos), ["1", "2", "3"])
        self.assertEqual(next(p for p in r.productos if p["pid"] == "2")["categoria"].split(" > ")[-1],
                         "Arroces")  # se queda con la primera categoría en que aparece

    def test_una_hoja_que_falla_no_tumba_el_resto_y_queda_anotada(self):
        sesion = SesionFalsa(PORTADA, {"101172010": ["1"], "103": ["9"]}, rotas=["101172020"])
        r = ejecutar(sesion, tam_pagina=96, reintentos=2)
        self.assertEqual(sorted(p["pid"] for p in r.productos), ["1", "9"])
        self.assertEqual(len(r.fallos), 1)
        self.assertIn("101172020", r.fallos[0])
        self.assertIn("tras 2 intentos", r.fallos[0])

    def test_reintenta_con_espera_creciente(self):
        esperas = []
        sesion = SesionFalsa(PORTADA, {}, rotas=["102"])
        ejecutar(sesion, tam_pagina=96, reintentos=3, dormir=esperas.append, pausa_s=0)
        self.assertEqual([e for e in esperas if e >= 3], [3, 6])  # 3 s, luego 6 s

    def test_portada_sin_categorias_aborta_en_vez_de_publicar_medio_catalogo(self):
        sesion = SesionFalsa("<html>Access Denied</html>", {})
        with self.assertRaises(RuntimeError) as cm:
            rastreador.rastrear(alimerka_con(sesion), log=lambda m: None, dormir=lambda s: None)
        self.assertIn("categorías", str(cm.exception))

    def test_max_hojas_limita_el_rastreo_para_pruebas(self):
        sesion = SesionFalsa(PORTADA, {c: ["1"] for c in ("101172010", "101172020", "102", "103")})
        r = ejecutar(sesion, tam_pagina=96, max_hojas=2)
        self.assertEqual(r.n_hojas, 2)

    def test_producto_rebajado_guarda_el_precio_vigente(self):
        class SesionRebaja(SesionFalsa):
            def get(self, url, params=None, timeout=None):
                if params and params["cgid"] == "102":
                    return Respuesta("<div>" + str(tarjeta("22029", "CREMOSITA",
                        "LECHE SEMIDESNATADA 1 LITRO", [ANTIGUO_RAW, "0,82 €"])) + "</div>")
                return super().get(url, params, timeout)
        r = ejecutar(SesionRebaja(PORTADA, {}), tam_pagina=96)
        self.assertEqual(next(p for p in r.productos if p["pid"] == "22029")["precio"], 0.82)


class Formato(unittest.TestCase):
    PRODUCTOS = [
        {"pid": "20", "nombre": "B", "marca": "M", "categoria": "Bebidas", "precio": 1.0,
         "precio_unidad": 1.0, "unidad": "L", "url": "https://x/20"},
        {"pid": "10", "nombre": "A", "marca": "", "categoria": "Lácteos", "precio": 2.5,
         "precio_unidad": None, "unidad": "", "url": "https://x/10"},
        {"pid": "30", "nombre": "C", "marca": "M", "categoria": "Bebidas", "precio": 3.0,
         "precio_unidad": 6.0, "unidad": "kg", "url": "https://x/30"},
    ]

    def test_categorias_en_tabla_aparte_y_filas_ordenadas_por_pid(self):
        c = construir_catalogo("Alimerka", "33012", self.PRODUCTOS,
                               ahora=datetime(2026, 10, 16, 16, 0, tzinfo=timezone.utc))
        self.assertEqual(c["categorias"], ["Lácteos", "Bebidas"])
        self.assertEqual([f[0] for f in c["productos"]], ["10", "20", "30"])
        self.assertEqual(c["productos"][1], ["20", "B", "M", 1, 1.0, 1.0, "L", "https://x/20"])
        self.assertEqual(c["campos"], CAMPOS)
        self.assertEqual(c["generado_en"], "2026-10-16T16:00:00+00:00")
        self.assertEqual(len(c["campos"]), len(c["productos"][0]))

    def test_serializacion_compacta_y_con_tildes(self):
        s = serializar(construir_catalogo("Alimerka", "33012", self.PRODUCTOS))
        self.assertIn("Lácteos", s)
        self.assertNotIn(": ", s)
        self.assertEqual(json.loads(s)["supermercado"], "Alimerka")

    def test_un_rastreo_muy_recortado_se_considera_degradado(self):
        previo = {"productos": [[i] for i in range(100)]}
        self.assertTrue(catalogo_degradado(previo, {"productos": [[i] for i in range(49)]}))
        self.assertFalse(catalogo_degradado(previo, {"productos": [[i] for i in range(50)]}))
        self.assertFalse(catalogo_degradado(None, {"productos": []}))
        self.assertFalse(catalogo_degradado({"productos": []}, {"productos": []}))


if __name__ == "__main__":
    unittest.main()
