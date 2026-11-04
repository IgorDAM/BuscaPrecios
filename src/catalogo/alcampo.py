"""
Rastreo del catálogo completo de Alcampo (compraonline.alcampo.es).

Verificado en vivo el 2026-11-04 (navegador, invitado):

  - Es una tienda tipo Ocado. La propia web pide los productos a
        GET /api/webproductpagews/v6/product-pages
            ?categoryId={id}&maxPageSize=300&maxProductsToDecorate=300&tag=web
    y devuelve hasta 300 productos YA DECORADOS (nombre, marca, precio,
    precio por unidad, categoryPath, available) en `productGroups[].
    decoratedProducts`. La respuesta trae `metadata.nextPageToken`; se pide la
    página siguiente repitiendo la URL con `&pageToken={token}` (con
    `nextPageToken` como nombre del parámetro NO pagina). La sección
    "Leche, Huevos, Lácteos..." entera (1.328 productos) salió en 5 páginas, y
    "Frescos" (3.115) en 11. Pedir una categoría de nivel 1 incluye todas sus
    subcategorías, así que basta con las ~13 raíces de alimentación y hogar.
  - Las categorías raíz salen de `window.__INITIAL_STATE__.data.categories`
    (`root` = ids; `categories[id].name`).
  - El precio por kilo/litro va en `unitPrice` con `unit` "fop.price.per.kg",
    etc. (las mismas etiquetas que `price.unit.label` en la búsqueda).

LÍMITE QUE HAY QUE RESPETAR (verificado): pidiendo ~25 páginas en 10 s el WAF
de AWS contestó HTTP 405 con `x-amzn-waf-action: captcha` ("Human
Verification"). Por eso aquí se va DESPACIO (pausa de varios segundos) y, si
aparece ese 405/CAPTCHA, se DETIENE el rastreo: no se reintenta ni se intenta
resolver ni esquivar. Lo que se había leído se descarta (los protectores de
scripts/rastrear_catalogo.py no publican un rastreo con fallos).

El WAF también bloquea a los runners de GitHub Actions, así que este rastreo
se ejecuta desde el PC de casa (scripts/actualizar_alcampo.bat) y el JSON se
sube con el resto.
"""

from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional, Tuple

from .alimerka import Rastreo
from ..supermarkets.alcampo import _UNIDADES, BASE_URL, Alcampo
from ..supermarkets.medidas import precio_por_medida
from ..supermarkets.navegador import (
    SupermercadoCaido,
    importar_playwright,
    nuevo_contexto,
)

RUTA_PRODUCTOS = "/api/webproductpagews/v6/product-pages"
TAM_PAGINA = 300
MAX_PAGINAS_POR_RAIZ = 60
MIN_RAICES = 5
# Pausa mínima entre peticiones: más rápido hizo saltar el CAPTCHA.
PAUSA_MINIMA_S = 3.0

# Categorías raíz que se rastrean (por el principio del nombre). Se dejan
# fuera "Folletos y Promociones" y "Campañas" (repiten productos de las
# demás) y electrónica, juguetes, bricolaje... (no son compra de súper).
RAICES_INCLUIDAS = (
    "Frescos", "Leche, Huevos", "Alimentación", "Desayuno y Merienda",
    "Congelados", "Comida Preparada", "Supermercado Ecológico", "Bebidas",
    "Sin Gluten", "Veganos", "Droguería", "Perfumeria", "Bebé",
)


class BloqueoWAF(SupermercadoCaido):
    """El WAF de Alcampo ha pedido verificación humana (CAPTCHA): se para."""


def _a_float(valor) -> Optional[float]:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _importe(nodo) -> Optional[float]:
    """Importe de un nodo de precio. Se aceptan las dos formas vistas en la
    web: {"amount": "5.76"} y {"current": {"amount": "5.76"}}."""
    if not isinstance(nodo, dict):
        return None
    if "amount" in nodo:
        return _a_float(nodo["amount"])
    return _importe(nodo.get("current"))


def producto_desde_api(p: dict) -> Optional[dict]:
    """Producto decorado de la API -> dict común del catálogo. None si no se
    puede comprar ahora (`available` falso) o no trae nombre/precio/id."""
    if not p.get("available", True):
        return None
    nombre = (p.get("name") or "").strip()
    precio = _importe(p.get("price"))
    pid = p.get("retailerProductId") or p.get("productId")
    if not nombre or precio is None or not pid:
        return None

    unidad, precio_unidad = "", None
    up = p.get("unitPrice") or {}
    etiqueta = up.get("unit") or ""
    if etiqueta in _UNIDADES:
        unidad, factor = _UNIDADES[etiqueta]
        base = _importe(up.get("price"))
        if base is not None:
            precio_unidad = round(base * factor, 2)
        else:
            unidad = ""
    if precio_unidad is None:
        # "por unidad" u otra etiqueta: se intenta con el formato del nombre.
        precio_unidad, unidad = precio_por_medida(precio, nombre)

    ruta = " > ".join(str(c) for c in (p.get("categoryPath") or []))
    return {
        "pid": str(pid),
        "nombre": nombre,
        "marca": (p.get("brand") or "").strip(),
        "categoria": ruta,
        "precio": round(precio, 2),
        "precio_unidad": precio_unidad,
        "unidad": unidad,
        "url": f"{BASE_URL}/products/{pid}",
    }


def _ruta(categoria_id: str, token: Optional[str]) -> str:
    r = (f"{RUTA_PRODUCTOS}?categoryId={categoria_id}&maxPageSize={TAM_PAGINA}"
         f"&maxProductsToDecorate={TAM_PAGINA}&tag=web")
    return r + (f"&pageToken={token}" if token else "")


def rastrear(
    pedir: Callable[[str], dict],
    raices: List[Tuple[str, str]],
    pausa_s: float = PAUSA_MINIMA_S,
    max_hojas: Optional[int] = None,
    log: Callable[[str], None] = print,
    dormir: Callable[[float], None] = time.sleep,
) -> Rastreo:
    """
    `pedir(ruta)` devuelve el JSON de una ruta (en producción, un `fetch`
    dentro del navegador; en los tests, un diccionario). Lanza BloqueoWAF si
    la web pide verificación humana. `raices`: [(id, nombre)].
    """
    if len(raices) < MIN_RAICES and not max_hojas:
        raise RuntimeError(
            f"Solo {len(raices)} categorías raíz (se esperan >= {MIN_RAICES}): "
            "probable bloqueo o cambio de la web."
        )
    if max_hojas:
        raices = raices[:max_hojas]
    pausa_s = max(pausa_s, PAUSA_MINIMA_S)
    log(f"Alcampo: {len(raices)} categorías raíz a rastrear (pausa {pausa_s:.0f} s)")

    resultado = Rastreo(n_hojas=len(raices))
    unicos: Dict[str, dict] = {}
    for i, (rid, nombre) in enumerate(raices):
        token = None
        try:
            for _ in range(MAX_PAGINAS_POR_RAIZ):
                datos = pedir(_ruta(rid, token))
                nuevos = 0
                for grupo in datos.get("productGroups") or []:
                    for p in grupo.get("decoratedProducts") or []:
                        prod = producto_desde_api(p)
                        if prod and prod["pid"] not in unicos:
                            unicos[prod["pid"]] = prod
                            nuevos += 1
                token = (datos.get("metadata") or {}).get("nextPageToken")
                dormir(pausa_s)
                if not token or nuevos == 0:
                    break
        except BloqueoWAF as e:
            # CAPTCHA: se para TODO. No se reintenta ni se sigue con otras raíces.
            resultado.fallos.append(f"{nombre}: {e}")
            resultado.fallos.extend(f"{n}: no rastreada (bloqueo del WAF)" for _, n in raices[i + 1:])
            log(f"  El WAF de Alcampo ha pedido verificación humana en '{nombre}': se detiene el rastreo.")
            break
        except Exception as e:
            resultado.fallos.append(f"{nombre}: {e}")
        log(f"  {i + 1}/{len(raices)} {nombre}: {len(unicos)} productos en total")

    resultado.productos = list(unicos.values())
    return resultado


def rastrear_con_navegador(cp, pausa_s, max_hojas, log):
    """Abre Chrome visible, fija Gijón con el formulario de la web (igual que
    el conector de búsqueda) y rastrea con `fetch` dentro de la página."""
    sync_playwright = importar_playwright()
    alcampo = Alcampo()
    with sync_playwright() as p:
        browser, context = nuevo_contexto(p, headless=False)
        try:
            try:
                context.grant_permissions(["geolocation"], origin=BASE_URL)
                context.set_geolocation({"latitude": 43.5098, "longitude": -5.7253})
            except Exception:
                pass
            page = context.new_page()
            if not alcampo._fijar_zona(page):
                raise SupermercadoCaido(
                    f"No se pudo fijar la zona de entrega ({alcampo.cp_esperado}): "
                    f"{alcampo.diagnostico or 'causa desconocida'}. Sin ella saldrían precios de Madrid."
                )
            todas = page.evaluate(
                """() => {
                    const s = window.__INITIAL_STATE__.data.categories;
                    return s.root.map(id => ({id, name: s.categories[id].name}));
                }"""
            )
            raices = [(c["id"], c["name"]) for c in todas
                      if c["name"].startswith(RAICES_INCLUIDAS)]

            def pedir(ruta):
                r = page.evaluate(
                    """async (ruta) => {
                        const r = await fetch(ruta, {headers: {Accept: 'application/json'}});
                        const waf = r.headers.get('x-amzn-waf-action') || '';
                        if (r.status === 405 || waf) return {__waf: r.status + ' ' + waf};
                        if (!r.ok) return {__error: r.status};
                        return await r.json();
                    }""",
                    ruta,
                )
                if isinstance(r, dict) and "__waf" in r:
                    raise BloqueoWAF(f"verificación humana pedida (HTTP {r['__waf'].strip()})")
                if isinstance(r, dict) and "__error" in r:
                    raise RuntimeError(f"HTTP {r['__error']}")
                return r

            return rastrear(pedir, raices, pausa_s=pausa_s, max_hojas=max_hojas, log=log)
        finally:
            browser.close()
