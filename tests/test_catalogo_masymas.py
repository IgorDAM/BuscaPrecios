"""
Pruebas del rastreo del catálogo de Más y Más con una sesión simulada (sin
red). Las páginas reproducen la estructura verificada en vivo el 2026-11-03:
menú con rutas `/seccion/` y `/seccion/hoja/` (la sección aparece en
mayúsculas en el menú superior y normal en otro enlace), apartados que no son
catálogo (`/ofertas/...`, `/navidad/`) y, en las páginas de categoría, un
carrusel de recomendaciones con tarjetas idénticas a las de los resultados.
"""

import unittest

from src.catalogo import masymas as rastreador

BASE = "https://www.supermasymasonline.com"

PORTADA = """
<html><body><nav>
  <a href="/alimentacion/">ALIMENTACIÓN</a>
  <a href="/alimentacion/">Alimentación</a>
  <a href="/alimentacion/leches-y-bebidas-vegetales/">Leches y bebidas vegetales</a>
  <a href="/alimentacion/arroz--legumbres-y-pasta/">Arroz, legumbres y pasta</a>
  <a href="/frescos/">Frescos</a>
  <a href="/frescos/charcuteria-y-quesos/">Charcutería y quesos</a>
  <a href="/ofertas/frescos/">Frescos</a>
  <a href="/navidad/">Navidad</a>
  <a href="/leche-entera-alteza-1-5l/0028498.html">Un producto, no una categoría</a>
</nav></body></html>
"""


def tarjeta(pid, marca, nombre, precio, kg=None):
    granel = f'<span class="unit-price-per-unit-details red">{kg} €/kg</span>' if kg else ""
    return (f'<div class="product" data-pid="{pid}" data-brand="{marca}" data-price="{precio}" '
            f'data-original-price=""><a class="link" href="/{pid}.html">{nombre}</a>{granel}</div>')


def pagina(tarjetas, carrusel=()):
    return f"""<html><body>
      <div class="carousel-container"><div class="carousel-wrapper product-grid mx-0">
        {''.join(carrusel)}
      </div></div>
      <div class="container search-results"><div class="row product-grid">{''.join(tarjetas)}</div></div>
    </body></html>"""


RECOMENDADA = tarjeta("0028369", "ASTURIANA", "Leche semidesnatada Central Lechera ASTURIANA 1L", "1.09")


class Resp:
    def __init__(self, texto, estado=200):
        self.text, self.estado = texto, estado

    def raise_for_status(self):
        if self.estado >= 400:
            raise RuntimeError(f"HTTP {self.estado}")


class Sesion:
    """Sirve la portada y, por hoja, la página que toque según `start`."""

    def __init__(self, paginas, fallan=()):
        self.paginas, self.fallan, self.pedidas = paginas, set(fallan), []

    def get(self, url, params=None, timeout=None):
        params = params or {}
        self.pedidas.append((url, params.get("start")))
        if url == f"{BASE}/":
            return Resp(PORTADA)
        ruta = url[len(BASE):]
        if ruta in self.fallan:
            return Resp("", 500)
        lista = self.paginas.get(ruta, [])
        i = params.get("start", 0) // params.get("sz", 96)
        return Resp(pagina(lista[i] if i < len(lista) else [], carrusel=[RECOMENDADA]))


class Falso:
    def __init__(self, sesion):
        self._session = sesion


def rastrear(sesion, **kw):
    kw.setdefault("log", lambda m: None)
    kw.setdefault("dormir", lambda s: None)
    return rastreador.rastrear(Falso(sesion), **kw)


class Hojas(unittest.TestCase):
    def test_solo_subcategorias_del_catalogo_y_nombre_normal_de_la_seccion(self):
        hojas = rastreador.extraer_hojas(PORTADA)
        self.assertEqual(hojas, [
            ("/alimentacion/arroz--legumbres-y-pasta/", "Alimentación > Arroz, legumbres y pasta"),
            ("/alimentacion/leches-y-bebidas-vegetales/", "Alimentación > Leches y bebidas vegetales"),
            ("/frescos/charcuteria-y-quesos/", "Frescos > Charcutería y quesos"),
        ])


class Rastreo(unittest.TestCase):
    def setUp(self):
        self.antes = rastreador.MIN_HOJAS
        rastreador.MIN_HOJAS = 2  # la portada de prueba solo tiene 3 hojas

    def tearDown(self):
        rastreador.MIN_HOJAS = self.antes

    def test_pagina_hasta_acabar_y_descarta_el_carrusel(self):
        paginas = {"/alimentacion/leches-y-bebidas-vegetales/": [
            [tarjeta(f"1{i:03d}", "X", f"Leche {i} 1L", "1.0") for i in range(2)],
            [tarjeta("1999", "X", "Leche final 1L", "1.0")],
        ]}
        r = rastrear(Sesion(paginas), tam_pagina=2)
        pids = sorted(p["pid"] for p in r.productos)
        self.assertEqual(pids, ["1000", "1001", "1999"])  # sin la del carrusel
        self.assertEqual(r.n_hojas, 3)

    def test_granel_guarda_el_precio_del_kilo(self):
        paginas = {"/frescos/charcuteria-y-quesos/": [[
            tarjeta("0036002", "CAMPOFRÍO", "Jamon cocido Extra CAMPOFRÍO", "0.55", kg="10,95"),
        ]]}
        p = rastrear(Sesion(paginas)).productos[0]
        self.assertEqual((p["precio"], p["precio_unidad"], p["unidad"]), (10.95, 10.95, "kg"))
        self.assertEqual(p["categoria"], "Frescos > Charcutería y quesos")

    def test_un_producto_en_dos_hojas_se_guarda_una_vez(self):
        t = tarjeta("0028498", "ALTEZA", "Leche entera ALTEZA 1,5L", "1.56")
        paginas = {"/alimentacion/arroz--legumbres-y-pasta/": [[t]],
                   "/alimentacion/leches-y-bebidas-vegetales/": [[t]]}
        self.assertEqual(len(rastrear(Sesion(paginas)).productos), 1)

    def test_una_hoja_que_falla_no_tumba_el_resto(self):
        paginas = {"/frescos/charcuteria-y-quesos/": [[tarjeta("1", "X", "Queso 250g", "3.0")]]}
        r = rastrear(Sesion(paginas, fallan={"/alimentacion/arroz--legumbres-y-pasta/"}))
        self.assertEqual(len(r.productos), 1)
        self.assertEqual(len(r.fallos), 1)

    def test_portada_sin_categorias_aborta(self):
        rastreador.MIN_HOJAS = 20
        with self.assertRaises(RuntimeError):
            rastrear(Sesion({}))


if __name__ == "__main__":
    unittest.main()
