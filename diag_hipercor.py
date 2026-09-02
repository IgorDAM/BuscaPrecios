"""
Diagnóstico puntual (v2): la página de Hipercor SÍ carga bien (200, con
resultados reales) en GitHub Actions, así que el problema no es Akamai
sino la espera de window.__MOONSHINE_STATE__ en hipercor.py. Este script
comprueba cada segundo si esa variable aparece, y si aparece, inspecciona
su forma real para ver si la ruta viewData.plp.products sigue existiendo.
No se queda en el repo a largo plazo, es solo para decidir el arreglo.
"""
import time
from urllib.parse import urlencode

from src.supermarkets.navegador import importar_playwright, nuevo_contexto
from src.supermarkets.hipercor import BASE_URL, SEARCH_PATH, CENTROS_CONOCIDOS

sync_playwright = importar_playwright()
cp = "33012"
food_center = CENTROS_CONOCIDOS[cp]

with sync_playwright() as p:
    browser, context = nuevo_contexto(p, headless=False)
    context.add_cookies([
        {"name": "ff_postal_code", "value": cp, "domain": "www.hipercor.es", "path": "/"},
        {"name": "ff_food_center", "value": food_center, "domain": "www.hipercor.es", "path": "/"},
    ])
    page = context.new_page()
    query = urlencode({"question": "leche entera", "catalog": "supermercado", "stype": "text_box"})
    url = f"{BASE_URL}{SEARCH_PATH}?{query}"
    print(f"Navegando a {url}")
    t0 = time.time()
    resp = page.goto(url, timeout=30000)
    print(f"STATUS HTTP: {resp.status if resp else None}  (a los {time.time()-t0:.1f}s)")

    existe = False
    for i in range(15):
        existe = page.evaluate("window.__MOONSHINE_STATE__ !== undefined")
        print(f"t={time.time()-t0:.1f}s  MOONSHINE_STATE existe: {existe}")
        if existe:
            break
        page.wait_for_timeout(1000)

    if existe:
        keys = page.evaluate("Object.keys(window.__MOONSHINE_STATE__)")
        print("Claves nivel superior de __MOONSHINE_STATE__:", keys)
        vd = page.evaluate(
            "window.__MOONSHINE_STATE__.viewData ? "
            "Object.keys(window.__MOONSHINE_STATE__.viewData) : 'NO hay viewData'"
        )
        print("Claves de viewData:", vd)
        plp = page.evaluate(
            "(window.__MOONSHINE_STATE__.viewData||{}).plp ? "
            "Object.keys(window.__MOONSHINE_STATE__.viewData.plp) : 'NO hay plp'"
        )
        print("Claves de viewData.plp:", plp)
        n = page.evaluate(
            """() => {
                const s = window.__MOONSHINE_STATE__;
                const ps = (s && s.viewData && s.viewData.plp && s.viewData.plp.products) || [];
                return ps.length;
            }"""
        )
        print("Nº de productos en viewData.plp.products:", n)
    else:
        print("MOONSHINE_STATE nunca apareció en 15s. Buscando pistas alternativas...")
        script_ids = page.evaluate(
            "Array.from(document.scripts).map(s => s.id).filter(Boolean).slice(0, 30)"
        )
        print("IDs de <script> en la página:", script_ids)
        window_keys_moonshine = page.evaluate(
            "Object.keys(window).filter(k => /moon|state|plp|catalog/i.test(k))"
        )
        print("Claves de window que parecen relacionadas:", window_keys_moonshine)

    browser.close()
