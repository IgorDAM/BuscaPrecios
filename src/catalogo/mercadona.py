"""
Rastreo del catálogo completo de Mercadona (tienda.mercadona.es).

Verificado en vivo el 2026-10-16 (CP 33012) en un Chrome real:

  - CORRIGE lo que decían README/CLAUDE.md: `/api/categories/` SÍ responde
    (200 JSON) cuando se pide DESDE LA PROPIA PÁGINA (mismo origen, con las
    cookies de Akamai ya puestas). Desde `requests` no, por eso se hace con
    un navegador visible (Playwright) y `fetch` dentro de la página.
  - `/api/categories/?lang=es` -> 26 categorías de nivel 1, cada una con sus
    subcategorías (152 en total).
  - `/api/categories/{id}/?lang=es` (id de una SUBcategoría) -> sus
    categorías hijas, cada una con la lista COMPLETA de sus productos
    (sin paginar). Recorrer las 152 subcategorías: 0 fallos, 4.326
    productos únicos, ~150 peticiones.
  - Cada producto trae `display_name`, `share_url` y `price_instructions`:
        unit_price     precio del envase que se paga ("3.45")
        reference_price precio por unidad de referencia ("3.450")
        reference_format "kg", "L", "100 g", "100 ml", "ud", "dz", "dc"...
        previous_unit_price / price_decreased  (rebaja)
    No trae marca como campo (va en el nombre: "... Hacendado").
  - La zona de entrega la fija el CP escrito en el formulario de la web (ya
    estaba en 33012 en el navegador de prueba).
"""

from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional

from .alimerka import Rastreo
from ..supermarkets.navegador import (
    SupermercadoCaido,
    aceptar_cookies,
    importar_playwright,
    nuevo_contexto,
)

BASE_URL = "https://tienda.mercadona.es"
MIN_SUBCATEGORIAS = 10

# reference_format -> (unidad que se publica, factor para llevar el precio de
# referencia a esa unidad). "100 g" y "100 ml" se pasan a kilo y litro.
_REFERENCIAS = {
    "kg": ("kg", 1),
    "l": ("L", 1),
    "100 g": ("kg", 10),
    "100 ml": ("L", 10),
    "ud": ("ud", 1),
    "dz": ("docena", 1),
    "dc": ("docena", 1),
}


def _a_float(valor) -> Optional[float]:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def producto_desde_api(p: dict, ruta: str = "") -> Optional[dict]:
    """Producto de la API de Mercadona -> dict común del catálogo (o None)."""
    pi = p.get("price_instructions") or {}
    precio = _a_float(pi.get("unit_price"))
    nombre = (p.get("display_name") or "").strip()
    if precio is None or not nombre or p.get("id") is None:
        return None

    precio_unidad, unidad = None, ""
    ref = _REFERENCIAS.get((pi.get("reference_format") or "").strip().lower())
    referencia = _a_float(pi.get("reference_price"))
    if ref and referencia is not None:
        unidad = ref[0]
        precio_unidad = round(referencia * ref[1], 4)

    return {
        "pid": str(p["id"]),
        "nombre": nombre,
        "marca": "",
        "categoria": ruta,
        "precio": round(precio, 2),
        "precio_unidad": precio_unidad,
        "unidad": unidad,
        "url": p.get("share_url") or "",
    }


def _con_reintentos(pedir, ruta, reintentos, dormir):
    ultimo: Optional[Exception] = None
    for intento in range(1, reintentos + 1):
        try:
            return pedir(ruta)
        except Exception as e:
            ultimo = e
            if intento < reintentos:
                dormir(3 * intento)
    raise RuntimeError(f"{ultimo or 'error desconocido'} (tras {reintentos} intentos)")


def rastrear(
    pedir: Callable[[str], dict],
    pausa_s: float = 0.3,
    max_hojas: Optional[int] = None,
    reintentos: int = 3,
    log: Callable[[str], None] = print,
    dormir: Callable[[float], None] = time.sleep,
) -> Rastreo:
    """
    `pedir(ruta)` devuelve el JSON de una ruta de la API (en producción es un
    `fetch` dentro del navegador; en los tests, un diccionario).
    """
    raiz = _con_reintentos(pedir, "/api/categories/?lang=es", reintentos, dormir)
    subcategorias = []  # [(id, "Nivel 1 > Subcategoría")]
    for n1 in raiz.get("results", []):
        for sub in n1.get("categories", []):
            subcategorias.append((sub["id"], f"{n1['name']} > {sub['name']}"))
    if len(subcategorias) < MIN_SUBCATEGORIAS:
        raise RuntimeError(
            f"La API solo devuelve {len(subcategorias)} subcategorías (se esperan >= "
            f"{MIN_SUBCATEGORIAS}): probable bloqueo o cambio de la web."
        )
    if max_hojas:
        subcategorias = subcategorias[:max_hojas]
    log(f"Mercadona: {len(subcategorias)} subcategorías a rastrear")

    resultado = Rastreo(n_hojas=len(subcategorias))
    unicos: Dict[str, dict] = {}
    for i, (sid, ruta_sub) in enumerate(subcategorias, 1):
        try:
            d = _con_reintentos(pedir, f"/api/categories/{sid}/?lang=es", reintentos, dormir)
            for cat in d.get("categories", []):
                ruta = f"{ruta_sub} > {cat['name']}"
                for p in cat.get("products", []):
                    prod = producto_desde_api(p, ruta)
                    if prod and prod["pid"] not in unicos:
                        unicos[prod["pid"]] = prod
        except Exception as e:
            resultado.fallos.append(f"{ruta_sub}: {e}")
        if i % 25 == 0:
            log(f"  {i}/{len(subcategorias)} subcategorías, {len(unicos)} productos")
        dormir(pausa_s)

    resultado.productos = list(unicos.values())
    return resultado


def rastrear_con_navegador(cp, pausa_s, max_hojas, log):
    """Abre Chrome visible, fija el CP en la web y rastrea con fetch interno."""
    sync_playwright = importar_playwright()
    with sync_playwright() as p:
        browser, context = nuevo_contexto(p, headless=False)
        try:
            page = context.new_page()
            page.goto(f"{BASE_URL}/")
            page.wait_for_timeout(3000)
            aceptar_cookies(page)
            page.wait_for_timeout(1500)
            try:
                page.fill('[data-testid="postal-code-checker-input"]', cp, timeout=8000)
                page.click('[data-testid="postal-code-checker-button"]')
                page.wait_for_timeout(3000)
            except Exception:
                pass  # la zona ya podía estar fijada

            def pedir(ruta):
                r = page.evaluate(
                    """async (ruta) => {
                        const r = await fetch(ruta);
                        if (!r.ok) return {__error: r.status};
                        return await r.json();
                    }""",
                    ruta,
                )
                if isinstance(r, dict) and "__error" in r:
                    raise RuntimeError(f"HTTP {r['__error']} en {ruta}")
                return r

            return rastrear(pedir, pausa_s=pausa_s, max_hojas=max_hojas, log=log)
        finally:
            browser.close()
