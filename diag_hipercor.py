"""
Diagnóstico puntual: qué devuelve realmente Hipercor/Akamai cuando se
busca desde un runner de GitHub Actions, en vez de tragar la excepción
del timeout como hace el conector real. No se queda en el repo a largo
plazo, es solo para decidir si merece la pena perseguir un arreglo.
"""
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
    resp = page.goto(url, timeout=30000)
    print("STATUS HTTP:", resp.status if resp else "(sin respuesta)")
    print("TITLE:", page.title())
    page.wait_for_timeout(3000)
    body_text = (page.evaluate("document.body.innerText") or "").strip()
    print(f"--- BODY visible (primeros 1500 chars, de {len(body_text)} totales) ---")
    print(body_text[:1500] if body_text else "(vacío)")
    print("--- HTML crudo (primeros 800 chars) ---")
    print(page.content()[:800])
    browser.close()
