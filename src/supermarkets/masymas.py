"""
Conector para Más y Más Asturias (supermasymasonline.com).

OJO: NO es tienda.masymas.com, que es la tienda de la Comunidad Valenciana
y Murcia (otra plataforma y otra zona; descartada).

Verificado en vivo el 2026-11-03 (navegador, sin iniciar sesión ni cookies):

  - Es una tienda Salesforce Commerce Cloud ("demandware"), igual que
    Alimerka. Los precios se ven como invitado.
  - Búsqueda: GET /search?q={texto} -> HTML con los productos ya
    renderizados (no hace falta JavaScript). Cada resultado es un
    <div class="product" data-pid="0028388" data-brand="ALTEZA"
         data-price="1.56" data-original-price="">
    y dentro un <a class="link" href="/leche-entera-alteza-1-5l/0028388.html">
    con el nombre ("Leche entera ALTEZA 1,5L"). El formato va en el nombre.
  - data-price es el precio VIGENTE (con oferta ya aplicada: la leche Central
    Lechera 1 L sale a 1,24 con data-original-price 1,29).
  - TRAMPA (la misma familia que el bug "EL KILO" de Alimerka): en los
    productos a granel (jamón, queso, cachopo...) data-price NO es el precio
    del kilo sino el de la cantidad mínima de compra (0,55 € por 50 g de
    jamón cocido Campofrío, que es a 10,95 €/kg). El precio real va en
    <span class="unit-price-per-unit-details">10,95 €/kg</span>; si hay
    oferta, el precio antiguo va aparte en el mismo tipo de span con la
    clase extra "strike-through" (13,95 €/kg), así que hay que leer el que
    NO es strike-through.
  - Los resultados de la primera página (16-21 productos) son todos los de
    búsquedas concretas; no se ha verificado la paginación de búsquedas
    amplias ("+ Ver más").
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from .base import Producto, Supermercado
from .medidas import precio_por_medida

BASE_URL = "https://www.supermasymasonline.com"

TAM_PAGINA_BUSQUEDA = 96
MAX_PAGINAS_BUSQUEDA = 3  # hasta ~288 resultados: de sobra para una búsqueda

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "es-ES,es;q=0.9",
}


# Precio por kilo/litro de un producto a granel: "10,95 €/kg", "1.234,50 €/l".
_PRECIO_GRANEL_RE = re.compile(
    r"(\d{1,3}(?:\.\d{3})*,\d+|\d+,\d+)\s*€\s*/\s*(kg|l)\b", re.IGNORECASE
)
_UNIDAD_GRANEL = {"kg": "kg", "l": "L"}


def precio_granel(tile) -> Tuple[Optional[float], str]:
    """
    (precio por kilo, "kg") si el producto se vende a granel; (None, "") si
    no (producto envasado normal).

    Una tarjeta a granel contiene <span class="unit-price-per-unit-details">
    con el texto "10,95 €/kg". Si el producto está en oferta hay DOS spans
    de ese tipo: el vigente ("10,95 €/kg") y el antiguo, que lleva además la
    clase "strike-through" ("13,95 €/kg") y NO debe devolverse.

    Casos reales verificados el 2026-11-03:
      - Jamón cocido Campofrío: 10,95 €/kg vigente y 13,95 €/kg tachado -> 10.95
      - Jamón cocido Alteza kg: un solo span, 9,95 €/kg                 -> 9.95
      - Leche entera 1 L (envasada): no hay ese span                    -> (None, "")
    (Implementada por Claude el 2026-11-03 mientras Igor no estaba; la
    selección CSS `:not(.strike-through)` descarta el precio antiguo.)
    """
    el = tile.select_one(".unit-price-per-unit-details:not(.strike-through)")
    if el is None:
        return (None, "")
    m = _PRECIO_GRANEL_RE.search(el.get_text(" ", strip=True))
    if not m:
        return (None, "")
    valor = float(m.group(1).replace(".", "").replace(",", "."))
    return (valor, _UNIDAD_GRANEL[m.group(2).lower()])


def tarjeta_a_producto(tile, nombre_buscado: str = "") -> Optional[Producto]:
    """Convierte un `div.product[data-pid]` en un Producto (None si la
    tarjeta no tiene nombre o precio utilizable)."""
    enlace = tile.select_one("a.link")
    nombre_real = enlace.get_text(strip=True) if enlace else ""
    if not nombre_real:
        return None

    precio_unidad, unidad = precio_granel(tile)
    if precio_unidad is not None:
        # A granel el "precio" que se enseña es el del kilo entero: igual que
        # en Alimerka, precio == precio_unidad es lo que la web interpreta
        # como "se paga exactamente lo pedido" (esAlPeso en app.js).
        precio = precio_unidad
    else:
        try:
            precio = float(tile.get("data-price", ""))
        except ValueError:
            return None
        precio_unidad, unidad = precio_por_medida(precio, nombre_real)

    href = enlace.get("href", "") if enlace else ""
    return Producto(
        nombre_buscado=nombre_buscado,
        nombre_real=nombre_real,
        precio=precio,
        marca=(tile.get("data-brand") or "").strip(),
        unidad=unidad,
        precio_unidad=precio_unidad,
        url=f"{BASE_URL}{href}" if href.startswith("/") else href,
    )


def tarjetas_resultado(soup) -> list:
    """Tarjetas de producto de los RESULTADOS de la página. Las páginas de
    categoría traen además un carrusel de recomendaciones con tarjetas
    idénticas (`.carousel-wrapper`, que también lleva la clase product-grid):
    verificado el 2026-11-03, 8 productos de otras secciones se colaban en
    "Leches y bebidas vegetales". Se descartan."""
    return [
        t for t in soup.select("div.product[data-pid]")
        if not t.find_parent(class_="carousel-wrapper")
    ]


class MasYMas(Supermercado):
    nombre = "Más y Más"

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update(HEADERS)

    def buscar_productos(self, nombre_producto: str) -> List[Producto]:
        """
        Todos los resultados de la búsqueda, no solo la primera página (una
        búsqueda amplia como "leche" trae más de 16-21 productos). Se pide con
        `start`/`sz` (verificado en las categorías; en la búsqueda se protege):
        si una página no aporta ningún producto nuevo (la web ignoró `start`)
        se para, así que en el peor caso se queda como antes, con la primera.
        """
        resultado: List[Producto] = []
        vistos = set()
        start = 0
        for _ in range(MAX_PAGINAS_BUSQUEDA):
            r = self._session.get(
                f"{BASE_URL}/search",
                params={"q": nombre_producto, "start": start, "sz": TAM_PAGINA_BUSQUEDA},
                timeout=20,
            )
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            tarjetas = tarjetas_resultado(soup)
            nuevos = 0
            for tile in tarjetas:
                pid = tile.get("data-pid")
                if pid in vistos:
                    continue
                producto = tarjeta_a_producto(tile, nombre_producto)
                if producto is None:
                    continue
                vistos.add(pid)
                resultado.append(producto)
                nuevos += 1
            if nuevos == 0 or len(tarjetas) < TAM_PAGINA_BUSQUEDA:
                break
            start += TAM_PAGINA_BUSQUEDA
        return resultado


def test_conexion(termino: str = "leche entera") -> None:
    m = MasYMas()
    print(f"Buscando '{termino}' en Más y Más (Asturias)...")
    opciones = m.buscar_productos(termino)
    print(f"{len(opciones)} opciones encontradas:")
    for o in opciones[:10]:
        print(" ", o)


if __name__ == "__main__":
    test_conexion()
