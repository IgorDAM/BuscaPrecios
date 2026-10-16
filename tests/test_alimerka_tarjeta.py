"""
Pruebas del análisis de tarjetas de producto de Alimerka.

Los datos de cada caso son tarjetas REALES leídas en vivo el 2026-10-16
(CP 33012, categoría 101); el HTML se reconstruye con la misma estructura
verificada en la web (.price > .strike-through + .sales > .value, y
.unit-price-per-unit aparte). Se ejecutan con:

    python -m unittest discover -s tests -t . -v
"""

import unittest

from bs4 import BeautifulSoup

from src.supermarkets.alimerka import precio_por_unidad, tarjeta_a_producto


def tarjeta(pid, marca, nombre, valores, unidad="", promo=""):
    """Tarjeta con la misma estructura que Alimerka. `valores` son los
    textos de los elementos `.value`: [precio] o [antiguo, vigente]."""
    if len(valores) == 2:
        antiguo = f'<span class="strike-through list"><span class="value">{valores[0]}</span></span>'
        vigente = valores[1]
    else:
        antiguo = '<span class="strike-through list"><br></span>'
        vigente = valores[0]
    return BeautifulSoup(
        f"""
        <div class="product" data-pid="{pid}">
          {f'<p class="tile-promo-callout">{promo}</p>' if promo else ''}
          <a class="link" href="/{pid}.html">{marca}</a>
          <a class="link" href="/{pid}.html">{nombre}</a>
          <div class="price"><span class="d-flex flex-column">{antiguo}
            <span class="sales"><span class="value"> {vigente} </span></span>
          </span></div>
          {f'<span class="unit-price-per-unit">{unidad}</span>' if unidad else ''}
          <button class="tile-add-to-cart">Añadir</button>
          <div class="newmodal" data-pid="{pid}"><h2 class="newmodal__title">{nombre}</h2></div>
        </div>
        """,
        "html.parser",
    ).select_one(".product")


ANTIGUO_RAW = "Price reduced from 0,83 € to"


class TarjetaAlimerka(unittest.TestCase):
    def test_precio_normal_con_precio_por_kilo(self):
        p = tarjeta_a_producto(tarjeta("710079", "RISI", "RISKETOS 120 G.", ["1,40 €"], "(11,67 €/kg)"))
        self.assertEqual((p.marca, p.nombre_real, p.precio), ("RISI", "RISKETOS 120 G.", 1.40))
        self.assertEqual((p.precio_unidad, p.unidad), (11.67, "kg"))
        self.assertTrue(p.url.endswith("/710079.html"))

    def test_producto_rebajado_usa_el_precio_vigente_no_el_antiguo(self):
        # Bug real: salía 0,83 (antiguo) en vez de 0,82 (el que se paga).
        p = tarjeta_a_producto(
            tarjeta("22029", "CREMOSITA", "LECHE SEMIDESNATADA 1 LITRO", [ANTIGUO_RAW, "0,82 €"])
        )
        self.assertEqual(p.precio, 0.82)
        # Sin €/l en la tarjeta: se calcula con el formato del nombre.
        self.assertEqual((p.precio_unidad, p.unidad), (0.82, "L"))

    def test_rebajado_por_kilo(self):
        p = tarjeta_a_producto(
            tarjeta("1", "QUESO TRES OSCOS", "QUESO EN BARRA LIGHT EL KILO",
                    ["Price reduced from 13,45 €/kg to", "10,95 €/kg"])
        )
        self.assertEqual(p.precio, 10.95)
        self.assertEqual((p.precio_unidad, p.unidad), (10.95, "kg"))

    def test_precio_por_docena(self):
        p = tarjeta_a_producto(
            tarjeta("10027275", "CAMAR", "HUEVOS CAMPEROS CALIBRES MEZCLADOS 10 UDS.",
                    ["2,95 €"], "(3,54 €/Docena)")
        )
        self.assertEqual((p.precio, p.precio_unidad, p.unidad), (2.95, 3.54, "docena"))

    def test_sin_precio_por_unidad_ni_formato_en_el_nombre(self):
        p = tarjeta_a_producto(tarjeta("8000198", "ALIMERKA", "HUEVOS  A-L LA DOCENA", ["3,05 €"]))
        self.assertEqual(p.precio, 3.05)
        self.assertIsNone(p.precio_unidad)

    def test_promocion_2x1_no_cambia_el_precio_de_etiqueta(self):
        p = tarjeta_a_producto(
            tarjeta("10022896", "DANONE", "YOGUR GRIEGO NATURAL 110 G. PACK 4",
                    ["1,49 €"], "(3,39 €/kg)", promo="2X1")
        )
        self.assertEqual((p.precio, p.precio_unidad), (1.49, 3.39))

    def test_precio_con_separador_de_millares(self):
        p = tarjeta_a_producto(tarjeta("2", "X", "JAMÓN IBÉRICO PIEZA", ["1.234,50 €"], "(150,00 €/kg)"))
        self.assertEqual(p.precio, 1234.50)

    def test_el_aviso_emergente_con_data_pid_no_es_un_producto(self):
        # La ventana emergente también lleva data-pid pero no tiene enlaces.
        modal = BeautifulSoup('<div data-pid="1"><h2>Aviso</h2></div>', "html.parser").div
        self.assertIsNone(tarjeta_a_producto(modal))

    def test_precio_por_unidad_sin_elemento(self):
        sopa = BeautifulSoup('<div class="product"></div>', "html.parser").div
        self.assertEqual(precio_por_unidad(sopa), (None, ""))


if __name__ == "__main__":
    unittest.main()
