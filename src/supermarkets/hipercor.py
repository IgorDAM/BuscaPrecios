"""
Conector para Hipercor (Supermercado El Corte Inglés).

Verificado en vivo (navegando hipercor.es con un CP real) el 2026-08-09:

  - La página de búsqueda es SSR (Vue "Moonshine" framework): el HTML ya
    contiene todos los productos con su precio, embebidos en un <script>
    como:

        window.__MOONSHINE_STATE__ = { ... }

  - La zona de entrega (y por tanto el catálogo/precios) se controla
    con dos cookies: `ff_postal_code` y `ff_food_center`. Al elegir
    "envío" + tu código postal en la web, quedan fijadas. He verificado
    que para el CP 33012 (Oviedo) el centro asignado es "0703-DELIVERY".
    Para otros CPs habría que descubrir el centro correspondiente.

CORRECCIÓN (2026-08-10): la primera versión de este conector usaba
`requests` normal (sin navegador), porque el día que se verificó no hacía
falta ejecutar JavaScript. Al retomarlo, Akamai Bot Manager empezó a
devolver 403 "Access Denied" a todo, incluida la portada sin cookies.
Comprobado que NO es un bloqueo por IP ni por exceso de peticiones: es
detección del cliente. Con un navegador visible (ver navegador.py) la
misma URL responde 200 con todos los productos; con `requests` o con
Playwright en modo headless, 403.

El estado del catálogo se sigue leyendo de `window.__MOONSHINE_STATE__`,
pero ahora preguntándoselo directamente a la página (page.evaluate) en vez
de buscarlo con una expresión regular dentro del HTML: es más fiable, ya
que el HTML serializado no siempre conserva el bloque tal cual.
"""

from __future__ import annotations

from typing import Dict, List, Optional
from urllib.parse import urlencode

from .base import Producto, Supermercado
from .medidas import normalizar_unidad, precio_por_medida
from .navegador import (
    FALLOS_SEGUIDOS_PARA_RENDIRSE,
    SupermercadoCaido,
    importar_playwright,
    nuevo_contexto,
)

BASE_URL = "https://www.hipercor.es"
SEARCH_PATH = "/supermercado/buscar/"

# Mapa conocido de código postal -> centro de entrega ("food_center").
# Solo tengo verificado el de Oviedo (33012). Si usas otro CP, añade
# aquí el que te asigne la web (Cambiar entrega -> tu CP -> mira la
# cookie ff_food_center en el navegador).
CENTROS_CONOCIDOS = {
    "33012": "0703-DELIVERY",
}


class Hipercor(Supermercado):
    nombre = "Hipercor"

    def __init__(self, codigo_postal: str, headless: bool = False):
        self.codigo_postal = codigo_postal
        self.headless = headless

    def _food_center(self) -> str:
        food_center = CENTROS_CONOCIDOS.get(self.codigo_postal)
        if not food_center:
            raise RuntimeError(
                f"No tengo el centro de entrega ('food_center') para el CP "
                f"{self.codigo_postal}. Añádelo a CENTROS_CONOCIDOS en "
                f"hipercor.py (mira la cookie ff_food_center en tu navegador "
                f"tras elegir ese CP en la web)."
            )
        return food_center

    def buscar_productos(self, nombre_producto: str) -> List[Producto]:
        """Búsqueda suelta: abre un navegador, busca un término, lo cierra."""
        resultado = self.buscar_productos_multiples([nombre_producto])
        return resultado.get(nombre_producto, [])

    def buscar_productos_multiples(
        self, terminos: List[str]
    ) -> Dict[str, List[Producto]]:
        """
        Busca varios términos abriendo el navegador UNA sola vez (igual que
        Mercadona: mucho más rápido que un navegador por producto).
        """
        sync_playwright = importar_playwright()
        food_center = self._food_center()
        resultado: Dict[str, List[Producto]] = {}

        with sync_playwright() as p:
            browser, context = nuevo_contexto(p, headless=self.headless)
            context.add_cookies([
                {
                    "name": "ff_postal_code",
                    "value": self.codigo_postal,
                    "domain": "www.hipercor.es",
                    "path": "/",
                },
                {
                    "name": "ff_food_center",
                    "value": food_center,
                    "domain": "www.hipercor.es",
                    "path": "/",
                },
            ])
            page = context.new_page()

            fallos_seguidos = 0
            for termino in terminos:
                opciones = self._buscar_uno(page, termino)
                if opciones is None:
                    # None = la página no cargó (el 403 de Akamai entra aquí);
                    # [] sería "cargó pero no tiene ese producto".
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

    @staticmethod
    def _buscar_uno(page, termino: str) -> Optional[List[Producto]]:
        """Opciones encontradas, [] si no lo vende, o None si no cargó."""
        query = urlencode({"question": termino, "catalog": "supermercado", "stype": "text_box"})
        page.goto(f"{BASE_URL}{SEARCH_PATH}?{query}")
        try:
            page.wait_for_function(
                "window.__MOONSHINE_STATE__ !== undefined", timeout=25000
            )
        except Exception:
            return None

        productos = Hipercor._extraer_productos(page)

        resultado = []
        for p in productos:
            producto = Hipercor._a_producto(termino, p)
            if producto is not None:
                resultado.append(producto)
        return resultado

    @staticmethod
    def _extraer_productos(page) -> list[dict]:
        """Lee el catálogo del estado que la propia página deja en window."""
        try:
            return page.evaluate(
                """() => {
                    const s = window.__MOONSHINE_STATE__;
                    const ps = (s && s.viewData && s.viewData.plp && s.viewData.plp.products) || [];
                    return ps.filter((p) => p.type === 'item');
                }"""
            )
        except Exception:
            return []

    @staticmethod
    def _a_producto(nombre_producto: str, p: dict) -> Optional[Producto]:
        precios = p.get("priceSpecification", {})
        precio_texto = precios.get("salePrice") or precios.get("price")
        if not precio_texto:
            return None
        try:
            precio = float(precio_texto.replace(".", "").replace(",", "."))
        except ValueError:
            return None

        precio_unidad = None
        pu_texto = precios.get("measurementUnitPrice")
        if pu_texto:
            try:
                precio_unidad = float(pu_texto.replace(".", "").replace(",", "."))
            except ValueError:
                pass

        marca = p.get("brand", "")
        if isinstance(marca, dict):
            marca = marca.get("name", "") or ""

        # Hipercor ya da el precio por unidad de medida, solo hay que pasar
        # su etiqueta ("Kilo", "Litro") al mismo formato que los demás.
        unidad = normalizar_unidad(precios.get("pum_description", ""))
        if precio_unidad is None:
            precio_unidad, unidad = precio_por_medida(precio, p.get("description", ""))

        return Producto(
            nombre_buscado=nombre_producto,
            nombre_real=p.get("description", "?"),
            precio=precio,
            marca=marca,
            unidad=unidad,
            precio_unidad=precio_unidad,
            url=f"{BASE_URL}{p.get('url', '')}",
        )


def test_conexion(codigo_postal: str = "33012", termino: str = "leche entera") -> None:
    h = Hipercor(codigo_postal)
    print(f"Buscando '{termino}' en Hipercor (CP {codigo_postal})...")
    opciones = h.buscar_productos(termino)
    print(f"{len(opciones)} opciones encontradas:")
    for o in opciones[:10]:
        print(" ", o)


if __name__ == "__main__":
    test_conexion()
