"""
Conector para Alimerka (alimerkaonline.es).

Verificado en vivo el 2026-08-09:

  - Es una tienda Salesforce Commerce Cloud ("demandware"). Se puede
    entrar como invitado (sin DNI ni cuenta) indicando un código
    postal.
  - Flujo de dos peticiones, ambas GET normales (sin JS):
      1. GET /on/demandware.store/Sites-Alimerka-Site/default/
             Stores-FindByZipcode?consent=true&zipCode={cp}
         -> fija la tienda/zona de entrega en la sesión (cookies).
      2. GET /on/demandware.store/Sites-Alimerka-Site/default/
             Search-Show?q={texto}
         -> HTML con los productos ya renderizados (data-pid, nombre,
            precio), sin necesidad de ejecutar JavaScript.
  - Cada resultado es un <div data-pid="...">, con la marca en el
    primer <a class="link">, el nombre en el segundo. El precio vigente está
    en `.sales .value`; si hay rebaja, el precio anterior va aparte en
    `.strike-through .value` (leer "el primer elemento price" cogía el
    precio tachado). El precio por kg/l/docena viene en
    `.unit-price-per-unit` ("(10,68 €/kg)").

No he detectado protecciones anti-bot agresivas (tipo Akamai) en esta
tienda, pero aun así: uso personal, sin automatizar peticiones masivas.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from .base import Producto, Supermercado
from .medidas import precio_por_medida

BASE_URL = "https://www.alimerkaonline.es"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}

_PRECIO_RE = re.compile(r"(\d+,\d+)\s*€")

# Número con coma decimal y, a veces, punto de millares: "2,99", "1.234,50".
_NUMERO = r"\d{1,3}(?:\.\d{3})*,\d+|\d+,\d+"
_NUMERO_RE = re.compile(_NUMERO)
# Precio por unidad que Alimerka calcula en la tarjeta: "(10,68 €/kg)",
# "(3,54 €/Docena)", "(2,10 €/l)".
_PRECIO_UNIDAD_RE = re.compile(rf"({_NUMERO})\s*€\s*/\s*([A-Za-zñÑ.]+)")
_UNIDADES_TARJETA = {"kg": "kg", "kilo": "kg", "l": "L", "litro": "L", "docena": "docena"}


def _a_float(texto: str) -> Optional[float]:
    """Primer número con coma decimal del texto ("1.234,50 €" -> 1234.5)."""
    m = _NUMERO_RE.search(texto or "")
    if not m:
        return None
    return float(m.group(0).replace(".", "").replace(",", "."))


def precio_vigente(tile) -> Optional[float]:
    """
    El precio que se paga HOY por el producto.

    Verificado en vivo (2026-10-16): en un producto rebajado la tarjeta trae
    DOS elementos `.value`: el precio antiguo, dentro de `.strike-through`
    (con el texto accesible "Price reduced from 0,83 € to"), y el vigente,
    dentro de `.sales`. Leer "el primer número del bloque de precio", como
    se hacía antes, daba el precio ANTIGUO (más alto) en todos los
    productos con oferta: la leche Cremosita entera salía a 0,96 € cuando
    costaba 0,89 €.
    """
    el = tile.select_one(".sales .value")
    if el is not None:
        return _a_float(el.get_text(" ", strip=True))
    # Plantilla distinta a la esperada: se coge el ÚLTIMO número del bloque
    # de precio (el vigente suele ir después del antiguo).
    bloque = tile.select_one("[class*=price]")
    if bloque is None:
        return None
    numeros = _NUMERO_RE.findall(bloque.get_text(" ", strip=True))
    if not numeros:
        return None
    return float(numeros[-1].replace(".", "").replace(",", "."))


def precio_por_unidad(tile) -> Tuple[Optional[float], str]:
    """(precio por kg/L/docena, unidad) si la tarjeta lo trae calculado."""
    el = tile.select_one(".unit-price-per-unit")
    if el is None:
        return None, ""
    m = _PRECIO_UNIDAD_RE.search(el.get_text(" ", strip=True))
    if not m:
        return None, ""
    valor = float(m.group(1).replace(".", "").replace(",", "."))
    etiqueta = m.group(2).lower().rstrip(".")
    return valor, _UNIDADES_TARJETA.get(etiqueta, etiqueta)


def tarjeta_a_producto(tile, nombre_buscado: str = "") -> Optional[Producto]:
    """Convierte una tarjeta `[data-pid]` en un Producto (None si no es una
    tarjeta de producto: los avisos emergentes también llevan data-pid)."""
    enlaces = [a for a in tile.select("a.link") if a.get_text(strip=True)]
    if len(enlaces) < 2:
        return None
    marca = enlaces[0].get_text(strip=True)
    nombre_real = enlaces[1].get_text(strip=True)
    precio = precio_vigente(tile)
    if precio is None:
        return None
    # La tarjeta trae el precio por kg/L/docena ya calculado cuando el
    # producto no se vende ya "por kilo"; si no, se intenta con el formato
    # que va dentro del nombre ("JAMÓN SERRANO RESERVA 120 G.").
    precio_unidad, unidad = precio_por_unidad(tile)
    if precio_unidad is None:
        precio_unidad, unidad = precio_por_medida(precio, nombre_real)
    pid = tile.get("data-pid")
    return Producto(
        nombre_buscado=nombre_buscado,
        nombre_real=nombre_real,
        precio=precio,
        marca=marca,
        unidad=unidad,
        precio_unidad=precio_unidad,
        url=f"{BASE_URL}/{pid}.html" if pid else "",
    )


class Alimerka(Supermercado):
    nombre = "Alimerka"

    def __init__(self, codigo_postal: str):
        self.codigo_postal = codigo_postal
        self._session = requests.Session()
        self._session.headers.update(HEADERS)
        self._preparada = False

    def _preparar_sesion(self):
        if self._preparada:
            return
        # Cargar la home primero para obtener cookies de sesión base.
        self._session.get(BASE_URL, timeout=20)
        # Fijar la tienda/zona de entrega según el código postal.
        r = self._session.get(
            f"{BASE_URL}/on/demandware.store/Sites-Alimerka-Site/default/Stores-FindByZipcode",
            params={"consent": "true", "zipCode": self.codigo_postal},
            timeout=20,
        )
        r.raise_for_status()
        self._preparada = True

    def buscar_productos(self, nombre_producto: str) -> List[Producto]:
        self._preparar_sesion()
        r = self._session.get(
            f"{BASE_URL}/on/demandware.store/Sites-Alimerka-Site/default/Search-Show",
            params={"q": nombre_producto, "search-button": "", "lang": "default"},
            timeout=20,
        )
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        resultado = []
        for tile in soup.select("[data-pid]"):
            producto = tarjeta_a_producto(tile, nombre_producto)
            if producto is not None:
                resultado.append(producto)
        return resultado


def test_conexion(codigo_postal: str = "33012", termino: str = "leche entera") -> None:
    a = Alimerka(codigo_postal)
    print(f"Buscando '{termino}' en Alimerka (CP {codigo_postal})...")
    opciones = a.buscar_productos(termino)
    print(f"{len(opciones)} opciones encontradas:")
    for o in opciones[:10]:
        print(" ", o)


if __name__ == "__main__":
    test_conexion()
