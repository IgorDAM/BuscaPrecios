"""
Pruebas del análisis de tarjetas de Más y Más Asturias.

Atributos, nombres y precios son REALES (supermasymasonline.com leído en
vivo el 2026-11-03); el HTML se reconstruye con la estructura verificada:
div.product[data-pid, data-brand, data-price, data-original-price] con un
a.link y, solo a granel, span.unit-price-per-unit-details (con una segunda
copia "strike-through" si hay oferta). Se ejecutan con:

    python -m unittest discover -s tests -t . -v
"""

import unittest

from bs4 import BeautifulSoup

from src.supermarkets.masymas import precio_granel, tarjeta_a_producto


def tarjeta(pid, marca, nombre, price, original="", kg=None, kg_antiguo=None):
    granel = ""
    if kg:
        if kg_antiguo:
            granel += (f'<span class="unit-price-per-unit-details strike-through">'
                       f'{kg_antiguo} €/kg</span>')
        granel += f'<span class="unit-price-per-unit-details red">{kg} €/kg</span><span class="unit">kg</span>'
    href = f"/{nombre.lower().replace(' ', '-')}/{pid}.html"
    return BeautifulSoup(
        f"""
        <div class="product" data-pid="{pid}" data-brand="{marca}"
             data-price="{price}" data-original-price="{original}">
          <a class="link" href="{href}">{nombre}</a>
          <div class="price">{granel}</div>
        </div>
        """,
        "html.parser",
    ).select_one(".product")


class TarjetaMasYMas(unittest.TestCase):
    def test_envasado_usa_data_price_y_calcula_el_precio_por_litro(self):
        t = tarjeta("0028498", "ALTEZA", "Leche entera ALTEZA 1,5L", "1.56")
        p = tarjeta_a_producto(t, "leche entera")
        self.assertEqual((p.marca, p.nombre_real, p.precio), ("ALTEZA", "Leche entera ALTEZA 1,5L", 1.56))
        self.assertEqual((p.precio_unidad, p.unidad), (1.04, "L"))
        self.assertTrue(p.url.endswith("/0028498.html"))

    def test_envasado_en_oferta_usa_el_precio_vigente(self):
        # Central Lechera 1 L: 1,24 vigente, 1,29 antes.
        t = tarjeta("0028368", "ASTURIANA", "Leche entera Central Lechera ASTURIANA 1L", "1.24", "1.29")
        self.assertEqual(tarjeta_a_producto(t).precio, 1.24)

    def test_granel_con_oferta_usa_el_kilo_vigente_no_el_tachado_ni_data_price(self):
        # Bug a evitar: data-price=0.55 es el precio de 50 g, no el del kilo.
        t = tarjeta("0036002", "CAMPOFRÍO", "Jamon cocido Extra CAMPOFRÍO", "0.55", "0.7",
                    kg="10,95", kg_antiguo="13,95")
        self.assertEqual(precio_granel(t), (10.95, "kg"))
        p = tarjeta_a_producto(t)
        self.assertEqual((p.precio, p.precio_unidad, p.unidad), (10.95, 10.95, "kg"))

    def test_granel_sin_oferta(self):
        t = tarjeta("0036003", "ALTEZA", "Jamon cocido Extra ALTEZA kg", "1.0", kg="9,95")
        self.assertEqual(precio_granel(t), (9.95, "kg"))

    def test_envasado_no_es_granel(self):
        t = tarjeta("0028388", "", "Leche entera fresca 1L", "1.15")
        self.assertEqual(precio_granel(t), (None, ""))

    def test_sin_formato_en_el_nombre_no_hay_precio_por_unidad(self):
        t = tarjeta("0073027", "FOXY", "Papel higienico seda 3 capas FOXY 4 + 2uds", "2.99", "3.89")
        p = tarjeta_a_producto(t)
        self.assertEqual((p.precio, p.precio_unidad), (2.99, None))


if __name__ == "__main__":
    unittest.main()
