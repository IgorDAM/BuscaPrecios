"""
Interfaz común para todos los "conectores" de supermercado.

Cada supermercado (Mercadona, Hipercor, Alimerka...) implementa una
subclase de Supermercado con dos métodos:

  - buscar_productos(nombre): devuelve TODOS los productos que el
    buscador del supermercado encuentra para ese texto (el abanico
    completo, sin elegir "el mejor"). Cuanto más concreta sea la
    búsqueda ("leche" vs "leche entera" vs "leche central lechera
    asturiana"), más se filtra el resultado - eso ya lo hace el propio
    buscador de cada supermercado.
  - buscar_producto(nombre): atajo que devuelve solo el más barato de
    buscar_productos(). Lo sigue usando el CLI (src/main.py) para una
    comparación rápida de un único precio por producto.

Esto permite que compare.py y la interfaz web traten a todos los
supermercados igual, sin importar cómo consigue cada uno los precios
por dentro (HTML renderizado, navegador headless, etc).
"""

import unicodedata
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Producto:
    nombre_buscado: str      # lo que escribiste en la lista de la compra
    nombre_real: str         # el nombre exacto del producto encontrado
    precio: float            # precio en euros
    marca: str = ""          # marca del producto, si el supermercado la separa del nombre
    unidad: str = ""         # p.ej. "ud", "kg", "L" (si se conoce)
    precio_unidad: Optional[float] = None  # precio por Kg/L si se conoce
    url: str = ""            # enlace al producto, si existe


def _normalizar(texto: str) -> str:
    """Minúsculas y sin acentos, para poder comparar textos."""
    sin_acentos = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in sin_acentos if unicodedata.category(c) != "Mn")


def _raiz(palabra: str) -> str:
    """Raíz muy simple: quita el plural para que 'huevos' case con 'huevo'."""
    if len(palabra) > 3 and palabra.endswith("es"):
        return palabra[:-2]
    if len(palabra) > 3 and palabra.endswith("s"):
        return palabra[:-1]
    return palabra


def filtrar_relevantes(termino: str, productos: List["Producto"]) -> List["Producto"]:
    """
    Se queda solo con los productos que de verdad tienen que ver con lo
    que se buscó.

    Hace falta porque el buscador de algunos supermercados devuelve, tras
    los resultados buenos, secciones enteras de "relacionados": buscando
    "huevos" Mercadona devuelve 91 resultados que incluyen mantequillas,
    natas y batidos (verificado el 2026-08-10). Como la app ordena todas
    las opciones por precio y preselecciona la más barata, sin filtrar
    acabaría eligiendo una bebida de avena como "los huevos más baratos".

    Criterio (comparando sin acentos ni plurales):

      1. El nombre debe contener todas las palabras significativas de la
         búsqueda.
      2. Además, la primera palabra buscada debe aparecer al principio del
         nombre. Sin esto, buscando "huevos" se colaban "pasta fresca al
         huevo" o "huevo sorpresa de chocolate", que además son más
         baratos que los huevos de verdad y se llevaban la preselección
         de "lo más barato".

      0. Si algún producto contiene la frase buscada tal cual, se usan
         solo esos (ver comentario dentro de la función).
      3. Las palabras se buscan primero en el nombre del producto y solo
         si así no queda nada se admite que las aporte la marca. Buscando
         "jamón serrano" salía elegido un "jamón cocido en dados" de la
         marca Serrano: la marca cumplía la palabra "serrano" aunque el
         producto fuese jamón cocido. Admitir la marca sigue siendo útil
         para buscar por marca a propósito ("leche cremosita").

    Cada criterio es más estricto que el siguiente; si uno deja la lista
    vacía se prueba el siguiente, y si ninguno da resultados se devuelve
    la lista original: es preferible enseñar de más que nada.
    """
    palabras = [_raiz(p) for p in _normalizar(termino).split() if len(p) > 2]
    if not palabras:
        return productos

    def empieza_por_lo_buscado(p: "Producto") -> bool:
        # Los tres supermercados nombran los productos empezando por lo que
        # son ("Huevos grandes L", "leche entera brik 1 l - Asturiana"), así
        # que se exige que la primera palabra buscada sea la primera del
        # nombre. Con solo pedir que aparezca "cerca del principio" seguían
        # colándose "Nidos al huevo" o "Tortellini al huevo".
        primera = (_normalizar(p.nombre_real).split() or [""])[0]
        return palabras[0] in primera

    # Lo más fiable: que aparezca la frase buscada tal cual. Distingue
    # "jamón serrano" de un "jamón cocido ... - Serrano" (Hipercor pega la
    # marca al final del nombre, así que buscar las palabras sueltas no
    # bastaba: "jamon" y "serrano" estaban ambas, pero era jamón cocido).
    frase = " ".join(palabras)
    exactos = [p for p in productos if frase in _normalizar(p.nombre_real)]

    por_nombre = [
        p for p in productos if all(w in _normalizar(p.nombre_real) for w in palabras)
    ]
    con_marca = [
        p
        for p in productos
        if all(w in _normalizar(f"{p.marca} {p.nombre_real}") for w in palabras)
    ]

    # De más estricto a menos: dentro de cada grupo se prefiere lo que
    # además empiece por lo buscado (así "Nidos al huevo" no compite con
    # "Huevos grandes L").
    for candidatos in (exactos, por_nombre, con_marca):
        estrictos = [p for p in candidatos if empieza_por_lo_buscado(p)]
        if estrictos:
            return estrictos

    return exactos or por_nombre or con_marca or productos


class Supermercado:
    """Clase base. Cada supermercado debe heredar de esta clase."""

    nombre = "Supermercado"

    def buscar_productos(self, nombre_producto: str) -> List[Producto]:
        """
        Busca un texto y devuelve TODOS los productos que encuentra el
        buscador del supermercado (lista vacía si no hay resultados).
        """
        raise NotImplementedError

    def buscar_producto(self, nombre_producto: str) -> Optional[Producto]:
        """Atajo: el más barato de buscar_productos(), o None."""
        opciones = filtrar_relevantes(nombre_producto, self.buscar_productos(nombre_producto))
        if not opciones:
            return None
        return min(opciones, key=lambda p: p.precio)
