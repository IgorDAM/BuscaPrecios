"""
Rastreo del catálogo de Hipercor (Supermercado El Corte Inglés).

Verificado en vivo el 2026-10-16 (CP 33012, cookies ff_postal_code /
ff_food_center ya fijadas) en un Chrome real:

  - Cada categoría de primer nivel se pagina en `/supermercado/<cat>/<n>/`
    (n desde 1, 24 productos por página). La página trae el estado en
    `window.__MOONSHINE_STATE__.viewData.plp`:
        products    24 de tipo "item" + algunos "placement_product_list"
                    (publicidad, se ignoran) + uno "next"
        pagination  {count, page, size, totalPages}
  - Totales por categoría (productos / páginas): alimentacion 3940/165,
    desayunos-dulces-y-pan 2909/122, lacteos 855/36, congelados 591/25,
    bebidas 2910/122, frescos 2454/103, bebes 425/18, cuidado-personal-y-belleza
    3233/135, drogueria-y-limpieza 1597/67, mascotas 559/24 (+ parafarmacia
    y nutricion-y-bienestar, que no se rastrean: no son compra de súper).
    Unas ~800 páginas de ~2 MB: es el rastreo más pesado, de ahí que sea
    semanal y con pausa.
  - Producto: `id`, `description`, `brand.name`, `url`, `priceSpecification`
    ({price, salePrice, measurementUnitPrice, pum_description}), `categories`
    (cadena con `parent_category` anidado).
  - Akamai exige navegador visible (ver navegador.py): en Actions, con xvfb.
"""

from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional, Tuple

from .alimerka import Rastreo
from ..supermarkets.medidas import normalizar_unidad
from ..supermarkets.navegador import (
    SupermercadoCaido,
    importar_playwright,
    nuevo_contexto,
)

BASE_URL = "https://www.hipercor.es"

CENTROS = {"33012": "0703-DELIVERY"}

CATEGORIAS = [
    "alimentacion",
    "desayunos-dulces-y-pan",
    "lacteos",
    "congelados",
    "bebidas",
    "frescos",
    "bebes",
    "cuidado-personal-y-belleza",
    "drogueria-y-limpieza",
    "mascotas",
]

# Páginas seguidas que pueden fallar antes de dar el supermercado por bloqueado.
FALLOS_SEGUIDOS_MAX = 5


def _numero(texto) -> Optional[float]:
    if texto is None:
        return None
    try:
        return float(str(texto).replace(".", "").replace(",", "."))
    except ValueError:
        return None


def ruta_categoria(categorias: List[dict]) -> str:
    """
    "Lácteos > Leche y bebidas vegetales > Leche semidesnatada" a partir de la
    cadena anidada `parent_category`. Se ignoran la raíz "Hipercor" y los
    nombres repetidos seguidos ("Lácteos > Lácteos").
    """
    for c in categorias or []:
        if not c.get("name"):
            continue
        nombres = []
        actual = c
        while actual:
            nombres.append(actual.get("name", ""))
            actual = actual.get("parent_category")
        nombres = [n for n in reversed(nombres) if n and n != "Hipercor"]
        limpios = [n for i, n in enumerate(nombres) if i == 0 or n != nombres[i - 1]]
        return " > ".join(limpios)
    return ""


def producto_desde_estado(p: dict) -> Optional[dict]:
    """Producto del estado de Hipercor -> dict común del catálogo (o None)."""
    ps = p.get("priceSpecification") or {}
    precio = _numero(ps.get("salePrice") or ps.get("price"))
    nombre = (p.get("description") or "").strip()
    if precio is None or not nombre or not p.get("id"):
        return None
    marca = p.get("brand") or ""
    if isinstance(marca, dict):
        marca = marca.get("name", "") or ""
    precio_unidad = _numero(ps.get("measurementUnitPrice"))
    unidad = normalizar_unidad(ps.get("pum_description", "")) if precio_unidad is not None else ""
    url = p.get("url") or ""
    return {
        "pid": str(p["id"]),
        "nombre": nombre,
        "marca": marca,
        "categoria": ruta_categoria(p.get("categories")),
        "precio": round(precio, 2),
        "precio_unidad": precio_unidad,
        "unidad": unidad,
        "url": f"{BASE_URL}{url}" if url.startswith("/") else url,
    }


def rastrear(
    leer_pagina: Callable[[str, int], Optional[Tuple[List[dict], int]]],
    categorias: List[str] = CATEGORIAS,
    pausa_s: float = 1.0,
    max_hojas: Optional[int] = None,
    reintentos: int = 3,
    log: Callable[[str], None] = print,
    dormir: Callable[[float], None] = time.sleep,
) -> Rastreo:
    """
    `leer_pagina(categoria, n)` devuelve ([items], total_paginas) o None si la
    página no cargó. `max_hojas` limita el nº total de páginas (pruebas).
    """
    resultado = Rastreo()
    unicos: Dict[str, dict] = {}
    paginas = 0
    seguidos = 0

    def leer(cat, n):
        for intento in range(1, reintentos + 1):
            leida = leer_pagina(cat, n)
            if leida is not None:
                return leida
            if intento < reintentos:
                dormir(3 * intento)
        return None

    for cat in categorias:
        n, total = 1, 1
        while n <= total:
            if max_hojas and paginas >= max_hojas:
                break
            paginas += 1
            leida = leer(cat, n)
            if leida is None:
                resultado.fallos.append(f"{cat} página {n}")
                seguidos += 1
                if seguidos >= FALLOS_SEGUIDOS_MAX:
                    resultado.n_hojas = paginas
                    raise SupermercadoCaido(
                        f"{seguidos} páginas seguidas sin cargar (último: {cat} {n}): "
                        "probable bloqueo de Akamai."
                    )
            else:
                seguidos = 0
                items, total = leida
                for it in items:
                    prod = producto_desde_estado(it)
                    if prod and prod["pid"] not in unicos:
                        unicos[prod["pid"]] = prod
            if n == 1 and leida is not None:
                log(f"  {cat}: {total} páginas")
            elif paginas % 50 == 0:
                log(f"  {paginas} páginas leídas, {len(unicos)} productos")
            n += 1
            dormir(pausa_s)

    resultado.n_hojas = paginas
    resultado.productos = list(unicos.values())
    return resultado


def rastrear_con_navegador(cp, pausa_s, max_hojas, log):
    """Abre Chrome visible con la zona del CP en cookies y rastrea."""
    centro = CENTROS.get(cp)
    if not centro:
        raise RuntimeError(f"No conozco el centro de entrega de Hipercor para el CP {cp}.")
    sync_playwright = importar_playwright()
    with sync_playwright() as p:
        browser, context = nuevo_contexto(p, headless=False)
        try:
            context.add_cookies([
                {"name": "ff_postal_code", "value": cp, "domain": "www.hipercor.es", "path": "/"},
                {"name": "ff_food_center", "value": centro, "domain": "www.hipercor.es", "path": "/"},
            ])
            page = context.new_page()

            def leer_pagina(cat, n):
                try:
                    page.goto(f"{BASE_URL}/supermercado/{cat}/{n}/", timeout=45000)
                    page.wait_for_function(
                        "window.__MOONSHINE_STATE__ && window.__MOONSHINE_STATE__.viewData"
                        " && window.__MOONSHINE_STATE__.viewData.plp",
                        timeout=25000,
                    )
                    return page.evaluate(
                        """() => {
                            const plp = window.__MOONSHINE_STATE__.viewData.plp;
                            const items = (plp.products || []).filter((p) => p.type === 'item');
                            const total = (plp.pagination && plp.pagination.totalPages) || 1;
                            return [items, total];
                        }"""
                    )
                except Exception:
                    return None

            return rastrear(leer_pagina, pausa_s=pausa_s, max_hojas=max_hojas, log=log)
        finally:
            browser.close()
