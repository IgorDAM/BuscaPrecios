"""
Rastreo del catálogo completo de Más y Más Asturias (supermasymasonline.com).

Verificado en vivo el 2026-11-03 (sin cookies, como invitado):

  - Misma plataforma que Alimerka (Salesforce Commerce Cloud) y el HTML de
    cada categoría viene renderizado en el servidor: basta `requests`.
  - Las categorías tienen rutas legibles en dos niveles, enlazadas desde el
    menú de la portada: `/alimentacion/` -> `/alimentacion/leches-y-bebidas-vegetales/`.
    51 subcategorías ("hojas") en 8 secciones. `/ofertas/...` repite las
    mismas secciones y `/navidad/`, `/folletos/`... son apartados especiales:
    no se rastrean.
  - Cada hoja se pagina con `?start={n}&sz={m}` (probado: sz=48 dos páginas
    sin solapes; sz=200 devuelve los 126 de "Leches y bebidas vegetales").
  - La suma de las hojas cubre cada sección (Alimentación 2.323 productos,
    sus 9 hojas suman 2.340: algunos están en dos hojas, se deduplican por
    pid). Catálogo total ~7.200 productos, ~100 peticiones con sz=96.
  - Las tarjetas son las mismas que en la búsqueda: se reutiliza
    `tarjeta_a_producto()` del conector (incluida la trampa del granel).
"""

from __future__ import annotations

import re
import time
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..supermarkets.masymas import BASE_URL, MasYMas, tarjeta_a_producto, tarjetas_resultado
from .alimerka import Rastreo

_HOJA_RE = re.compile(r"^/([a-z0-9-]+)/([a-z0-9-]+)/$")
_SECCION_RE = re.compile(r"^/([a-z0-9-]+)/$")
# Rutas del menú que no son secciones del catálogo (o que lo repiten).
SECCIONES_EXCLUIDAS = {"ofertas", "navidad", "folletos", "app-masymas", "dashboard"}

# Si el menú trae menos hojas que esto, la página no es la esperada
# (bloqueo, cambio de diseño...): mejor abortar que publicar medio catálogo.
MIN_HOJAS = 20


def extraer_hojas(html: str) -> List[Tuple[str, str]]:
    """[(ruta de la hoja, "Sección > Hoja")] a partir de los enlaces del menú."""
    soup = BeautifulSoup(html, "html.parser")
    secciones: Dict[str, str] = {}
    hojas: Dict[str, str] = {}
    for a in soup.select("a[href]"):
        ruta = urlparse(a["href"]).path
        nombre = " ".join(a.get_text().split())
        if not nombre:
            continue
        m = _SECCION_RE.match(ruta)
        if m and m.group(1) not in SECCIONES_EXCLUIDAS:
            # El menú superior la escribe en mayúsculas ("ALIMENTACIÓN") y
            # otro enlace con su forma normal ("Alimentación"): se prefiere esa.
            previo = secciones.get(m.group(1))
            if previo is None or (previo.isupper() and not nombre.isupper()):
                secciones[m.group(1)] = nombre
            continue
        m = _HOJA_RE.match(ruta)
        if m and m.group(1) not in SECCIONES_EXCLUIDAS:
            hojas.setdefault(ruta, nombre)
    resultado = []
    for ruta, nombre in sorted(hojas.items()):
        seccion = _HOJA_RE.match(ruta).group(1)
        resultado.append((ruta, f"{secciones.get(seccion, seccion)} > {nombre}"))
    return resultado


def _pedir(sesion, url: str, params: Dict, reintentos: int, dormir: Callable[[float], None]):
    """GET con reintentos y espera creciente."""
    ultimo: Optional[Exception] = None
    for intento in range(1, reintentos + 1):
        try:
            r = sesion.get(url, params=params, timeout=30)
            r.raise_for_status()
            return r
        except Exception as e:  # red, 5xx...
            ultimo = e
            if intento < reintentos:
                dormir(3 * intento)
    raise RuntimeError(f"{ultimo or 'error desconocido'} (tras {reintentos} intentos)")


def tarjetas_de(html: str) -> List[Tuple[str, object]]:
    """[(pid, Producto)] de las tarjetas de producto de la página."""
    soup = BeautifulSoup(html, "html.parser")
    salida, vistos = [], set()
    for tile in tarjetas_resultado(soup):
        pid = tile.get("data-pid")
        if not pid or pid in vistos:
            continue
        producto = tarjeta_a_producto(tile)
        if producto is None:
            continue
        vistos.add(pid)
        salida.append((pid, producto))
    return salida


def rastrear(
    masymas: MasYMas,
    pausa_s: float = 1.0,
    tam_pagina: int = 96,
    max_hojas: Optional[int] = None,
    reintentos: int = 3,
    log: Callable[[str], None] = print,
    dormir: Callable[[float], None] = time.sleep,
    max_paginas_por_hoja: int = 100,
) -> Rastreo:
    """Recorre todas las hojas y devuelve los productos únicos."""
    sesion = masymas._session
    portada = _pedir(sesion, f"{BASE_URL}/", {}, reintentos, dormir)
    hojas = extraer_hojas(portada.text)
    if len(hojas) < MIN_HOJAS:
        raise RuntimeError(
            f"La portada solo enlaza {len(hojas)} subcategorías (se esperan >= "
            f"{MIN_HOJAS}): probable bloqueo o cambio de diseño."
        )
    if max_hojas:
        hojas = hojas[:max_hojas]
    log(f"Más y Más: {len(hojas)} subcategorías a rastrear")

    resultado = Rastreo(n_hojas=len(hojas))
    unicos: Dict[str, Dict] = {}
    for i, (ruta, categoria) in enumerate(hojas, 1):
        try:
            start = 0
            for _ in range(max_paginas_por_hoja):
                r = _pedir(sesion, f"{BASE_URL}{ruta}", {"start": start, "sz": tam_pagina}, reintentos, dormir)
                tarjetas = tarjetas_de(r.text)
                for pid, p in tarjetas:
                    if pid not in unicos:  # el primero que aparece se queda con su categoría
                        unicos[pid] = {
                            "pid": pid,
                            "nombre": p.nombre_real,
                            "marca": p.marca,
                            "categoria": categoria,
                            "precio": p.precio,
                            "precio_unidad": p.precio_unidad,
                            "unidad": p.unidad,
                            "url": p.url,
                        }
                dormir(pausa_s)
                if len(tarjetas) < tam_pagina:
                    break
                start += tam_pagina
        except Exception as e:
            resultado.fallos.append(f"{ruta} ({categoria}): {e}")
        if i % 10 == 0 or i == len(hojas):
            log(f"  {i}/{len(hojas)} subcategorías, {len(unicos)} productos, {len(resultado.fallos)} fallos")

    resultado.productos = list(unicos.values())
    return resultado
