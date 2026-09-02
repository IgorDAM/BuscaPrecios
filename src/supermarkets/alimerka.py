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
    primer <a class="link">, el nombre en el segundo, y el precio en un
    elemento con clase que contiene "price".

No he detectado protecciones anti-bot agresivas (tipo Akamai) en esta
tienda, pero aun así: uso personal, sin automatizar peticiones masivas.
"""

from __future__ import annotations

import re
from typing import List

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
        tiles = soup.select("[data-pid]")

        resultado = []
        for tile in tiles:
            enlaces = [a for a in tile.select("a.link") if a.get_text(strip=True)]
            if len(enlaces) < 2:
                continue
            marca = enlaces[0].get_text(strip=True)
            nombre_real = enlaces[1].get_text(strip=True)
            precio_el = tile.select_one("[class*=price]")
            if not precio_el:
                continue
            m = _PRECIO_RE.search(precio_el.get_text(" ", strip=True))
            if not m:
                continue
            precio = float(m.group(1).replace(",", "."))
            pid = tile.get("data-pid")
            # Alimerka no publica el formato en ningún campo: el peso o el
            # volumen va dentro del nombre ("JAMÓN SERRANO RESERVA 120 G.").
            precio_unidad, unidad = precio_por_medida(precio, nombre_real)
            resultado.append(
                Producto(
                    nombre_buscado=nombre_producto,
                    nombre_real=nombre_real,
                    precio=precio,
                    marca=marca,
                    unidad=unidad,
                    precio_unidad=precio_unidad,
                    url=f"{BASE_URL}/{pid}.html" if pid else "",
                )
            )
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
