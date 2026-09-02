"""
Conector para Mercadona.

CORRECCIÓN IMPORTANTE (2026-08-09): la primera versión de este archivo
asumía que Mercadona tenía una API JSON pública simple en
tienda.mercadona.es/api/... Al verificarlo en un navegador real, eso
resultó ser incorrecto/desactualizado: esa ruta da 404.

Lo que sí he comprobado en vivo:

  - tienda.mercadona.es es una SPA (no hay contenido en el HTML inicial,
    solo 2 KB de "cascarón"). Los productos se cargan por JavaScript.
  - El sitio usa Akamai Bot Manager (cookies `_abck`, `bm_sz`, y rutas
    de API ofuscadas y rotativas tipo `/HAESKI.../...`). No hay una URL
    de API estable y pública como en Alimerka.
  - Los productos están en elementos con `data-testid="product-cell"`, y
    dentro de cada uno `data-testid="product-cell-name"` (nombre) y
    `data-testid="product-price"` (precio).

SEGUNDA CORRECCIÓN (2026-08-10): dos cosas que fallaban en silencio.

  1. La zona de entrega se fijaba escribiendo a mano la cookie `__mo_da`
     con un almacén hardcodeado por código postal. Dejó de funcionar: la
     web descarta esa cookie inyectada, se queda sin zona y la búsqueda
     sale vacía ("Se ha vaciado el carro"). Ahora se introduce el código
     postal en el formulario de la propia web, que es quien resuelve el
     almacén correspondiente; así ya no hay ningún almacén hardcodeado.
  2. En modo headless la SPA nunca llega a pedir los resultados de
     búsqueda (la detectan y la bloquean por dentro). Ver navegador.py:
     por eso se usa un navegador visible colocado fuera de la pantalla.

Requiere: `pip install playwright` y luego `playwright install chromium`
(una sola vez).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .base import Producto, Supermercado
from .medidas import precio_por_medida
from .navegador import (
    FALLOS_SEGUIDOS_PARA_RENDIRSE,
    SupermercadoCaido,
    aceptar_cookies,
    importar_playwright,
    nuevo_contexto,
)

BASE_URL = "https://tienda.mercadona.es"


class Mercadona(Supermercado):
    nombre = "Mercadona"

    def __init__(self, codigo_postal: str, headless: bool = False):
        self.codigo_postal = codigo_postal
        self.headless = headless

    def buscar_productos(self, nombre_producto: str) -> List[Producto]:
        """Búsqueda suelta: abre un navegador, busca un término, lo cierra."""
        resultado = self.buscar_productos_multiples([nombre_producto])
        return resultado.get(nombre_producto, [])

    def buscar_productos_multiples(
        self, terminos: List[str]
    ) -> Dict[str, List[Producto]]:
        """
        Busca varios términos abriendo el navegador UNA sola vez (mucho
        más rápido que llamar a buscar_productos() por cada producto de
        la lista, porque Playwright tarda un buen rato en arrancar).
        """
        sync_playwright = importar_playwright()
        resultado: Dict[str, List[Producto]] = {}

        with sync_playwright() as p:
            browser, context = nuevo_contexto(p, headless=self.headless)
            page = context.new_page()

            self._fijar_zona_entrega(page)

            fallos_seguidos = 0
            for termino in terminos:
                opciones = self._buscar_uno(page, termino)
                if opciones is None:
                    # None = la página no cargó (bloqueo o caída); [] sería
                    # "cargó pero no vende eso", que no es un fallo.
                    fallos_seguidos += 1
                    resultado[termino] = []
                    if fallos_seguidos >= FALLOS_SEGUIDOS_PARA_RENDIRSE:
                        browser.close()
                        raise SupermercadoCaido(
                            "No responde (varias búsquedas seguidas sin cargar). "
                            "Suele ser un bloqueo temporal; inténtalo más tarde."
                        )
                else:
                    fallos_seguidos = 0
                    resultado[termino] = opciones

            browser.close()

        return resultado

    def _fijar_zona_entrega(self, page) -> None:
        """
        Abre la portada e introduce el código postal en el formulario de la
        web. Es la web quien decide el almacén que sirve ese CP, así que no
        hace falta mantener un mapa de códigos postales a mano.
        """
        page.goto(f"{BASE_URL}/")
        page.wait_for_timeout(3000)
        aceptar_cookies(page)
        page.wait_for_timeout(1500)
        try:
            page.fill('[data-testid="postal-code-checker-input"]', self.codigo_postal, timeout=8000)
            page.click('[data-testid="postal-code-checker-button"]')
            page.wait_for_timeout(3000)
        except Exception:
            # Si el formulario no aparece, puede ser que la zona ya estuviera
            # fijada en esta sesión; seguimos e intentamos buscar igualmente.
            pass

    @staticmethod
    def _buscar_uno(page, termino: str) -> Optional[List[Producto]]:
        """Opciones encontradas, [] si no vende eso, o None si no cargó."""
        # Pasar por una página en blanco antes de cada búsqueda. Sin esto,
        # al encadenar búsquedas la SPA conserva en pantalla los resultados
        # de la anterior mientras carga los nuevos, y se leían productos
        # equivocados (buscando "huevos" salían las leches de la búsqueda
        # previa).
        page.goto("about:blank")
        page.goto(f"{BASE_URL}/search-results?query={termino}")
        try:
            page.wait_for_selector('[data-testid="product-cell"]', timeout=25000)
        except Exception:
            # Sin productos puede significar dos cosas muy distintas: que la
            # página no cargó (bloqueo) o que cargó pero no venden eso. Si
            # el contenedor de resultados está ahí, la página funcionó; hay
            # que distinguirlo o dos búsquedas raras seguidas harían pensar
            # que el supermercado entero está caído.
            if page.query_selector('[data-testid="search-results"]'):
                return []
            return None

        celdas = page.query_selector_all('[data-testid="product-cell"]')
        opciones = []
        for celda in celdas:
            nombre_el = celda.query_selector('[data-testid="product-cell-name"]')
            precio_el = celda.query_selector('[data-testid="product-price"]')
            if not nombre_el or not precio_el:
                continue
            nombre_real = nombre_el.inner_text().strip()
            precio_texto = precio_el.inner_text().strip()
            # El formato ("Paquete 120 Gramos", "6 briks x 1 Litro") no tiene
            # campo propio: viene en el texto de la tarjeta, junto al nombre.
            formato = celda.inner_text()
            producto = Mercadona._a_producto(termino, nombre_real, precio_texto, formato)
            if producto is not None:
                opciones.append(producto)
        return opciones

    @staticmethod
    def _a_producto(nombre_producto: str, nombre_real: str, precio_texto: str, formato: str = ""):
        precio_limpio = precio_texto.replace("€", "").strip().replace(",", ".")
        try:
            precio = float(precio_limpio.split("/")[0].strip())
        except ValueError:
            return None

        precio_unidad, unidad = precio_por_medida(precio, formato)

        return Producto(
            nombre_buscado=nombre_producto,
            nombre_real=nombre_real,
            precio=precio,
            unidad=unidad,
            precio_unidad=precio_unidad,
        )


def test_conexion(codigo_postal: str = "33012", termino: str = "manzanas") -> None:
    m = Mercadona(codigo_postal)
    print(f"Buscando '{termino}' en Mercadona (CP {codigo_postal})...")
    opciones = m.buscar_productos(termino)
    print(f"{len(opciones)} opciones encontradas:")
    for o in opciones[:10]:
        print(" ", o)


if __name__ == "__main__":
    test_conexion()
