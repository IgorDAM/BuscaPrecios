"""
Rastreo del catálogo completo de Alimerka (alimerkaonline.es).

Verificado en vivo el 2026-10-16 (CP 33012, entrando como invitado):

  - El HTML de cada categoría viene renderizado en el servidor: basta
    `requests`, sin navegador.
  - El menú de la portada enlaza todas las categorías con un código
    jerárquico en la URL (`/101` -> `/10117` -> `/1011720` -> `/101172010`):
    694 códigos, ~576 de ellos "hojas" (sin subcategorías).
  - Cada categoría se pagina con
        Search-UpdateGrid?cgid={codigo}&start={n}&sz={m}
    (probado con sz=96; la página 2 no repite productos de la 1).
  - Una categoría padre lista TODOS los productos de sus hojas: comparado
    en "Lo Tienes Hecho", la unión de sus 8 hojas son exactamente los mismos
    32 productos que el listado del padre, sin faltar ni sobrar ninguno. Por
    eso se rastrean solo las hojas: cada producto sale con su categoría más
    fina y no hay que descargar los padres (que repetirían todo).

Un rastreo completo son ~600 peticiones. Se hace UNA vez por semana (o dos),
con pausa entre peticiones: es uso personal, no una descarga masiva.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..supermarkets.alimerka import BASE_URL, Alimerka, tarjeta_a_producto

RUTA_GRID = "/on/demandware.store/Sites-Alimerka-Site/default/Search-UpdateGrid"
_CODIGO_CATEGORIA_RE = re.compile(r"^/(\d{3,9})$")

# Si el menú trae menos categorías que esto, la página no es la esperada
# (bloqueo, cambio de diseño...): mejor abortar que publicar medio catálogo.
MIN_CATEGORIAS = 20


@dataclass
class Rastreo:
    productos: List[Dict] = field(default_factory=list)
    fallos: List[str] = field(default_factory=list)
    n_hojas: int = 0


def extraer_categorias(html: str) -> Dict[str, str]:
    """{código: nombre} a partir de los enlaces `/<código>` del menú."""
    soup = BeautifulSoup(html, "html.parser")
    categorias: Dict[str, str] = {}
    for a in soup.select("a[href]"):
        m = _CODIGO_CATEGORIA_RE.match(urlparse(a["href"]).path)
        if not m:
            continue
        nombre = " ".join(a.get_text().split())
        if nombre and m.group(1) not in categorias:
            categorias[m.group(1)] = nombre
    return categorias


def hojas_con_ruta(categorias: Dict[str, str]) -> List[Tuple[str, str]]:
    """[(código de la hoja, "Padre > Hijo > Hoja")] de las categorías sin hijas."""
    codigos = sorted(categorias)
    resultado = []
    for c in codigos:
        if any(o != c and o.startswith(c) for o in codigos):
            continue
        ruta = " > ".join(categorias[c[:n]] for n in range(3, len(c) + 1) if c[:n] in categorias)
        resultado.append((c, ruta))
    return resultado


def _pedir(sesion, params: Dict, reintentos: int, dormir: Callable[[float], None]):
    """GET a Search-UpdateGrid con reintentos y espera creciente."""
    ultimo: Optional[Exception] = None
    for intento in range(1, reintentos + 1):
        try:
            r = sesion.get(f"{BASE_URL}{RUTA_GRID}", params=params, timeout=30)
            r.raise_for_status()
            return r
        except Exception as e:  # red, 5xx...
            ultimo = e
            if intento < reintentos:
                dormir(3 * intento)
    raise RuntimeError(f"{ultimo or 'error desconocido'} (tras {reintentos} intentos)")


def _tarjetas_de(html: str) -> List[Tuple[str, object]]:
    """[(pid, Producto)] de las tarjetas reales de la página."""
    soup = BeautifulSoup(html, "html.parser")
    salida, vistos = [], set()
    for tile in soup.select("[data-pid]"):
        producto = tarjeta_a_producto(tile)
        pid = tile.get("data-pid")
        if producto is None or not pid or pid in vistos:
            continue
        vistos.add(pid)
        salida.append((pid, producto))
    return salida


def rastrear(
    alimerka: Alimerka,
    pausa_s: float = 1.0,
    tam_pagina: int = 96,
    max_hojas: Optional[int] = None,
    reintentos: int = 3,
    log: Callable[[str], None] = print,
    dormir: Callable[[float], None] = time.sleep,
    max_paginas_por_hoja: int = 200,
) -> Rastreo:
    """Recorre todas las categorías hoja y devuelve los productos únicos."""
    alimerka._preparar_sesion()
    sesion = alimerka._session

    portada = sesion.get(f"{BASE_URL}/", timeout=30)
    portada.raise_for_status()
    categorias = extraer_categorias(portada.text)
    if len(categorias) < MIN_CATEGORIAS:
        raise RuntimeError(
            f"La portada solo trae {len(categorias)} categorías (se esperan >= "
            f"{MIN_CATEGORIAS}): probable bloqueo o cambio de diseño."
        )
    hojas = hojas_con_ruta(categorias)
    if max_hojas:
        hojas = hojas[:max_hojas]
    log(f"Alimerka: {len(categorias)} categorías, {len(hojas)} hojas a rastrear")

    resultado = Rastreo(n_hojas=len(hojas))
    unicos: Dict[str, Dict] = {}
    for i, (cgid, ruta) in enumerate(hojas, 1):
        try:
            start = 0
            for _ in range(max_paginas_por_hoja):
                r = _pedir(sesion, {"cgid": cgid, "start": start, "sz": tam_pagina}, reintentos, dormir)
                tarjetas = _tarjetas_de(r.text)
                for pid, p in tarjetas:
                    if pid not in unicos:  # el primero que aparece se queda con su categoría
                        unicos[pid] = {
                            "pid": pid,
                            "nombre": p.nombre_real,
                            "marca": p.marca,
                            "categoria": ruta,
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
            resultado.fallos.append(f"{cgid} ({ruta}): {e}")
        if i % 50 == 0 or i == len(hojas):
            log(f"  {i}/{len(hojas)} hojas, {len(unicos)} productos, {len(resultado.fallos)} fallos")

    resultado.productos = list(unicos.values())
    return resultado
