"""
Configuración común del navegador para los conectores que lo necesitan
(Mercadona e Hipercor).

Por qué NO usamos modo headless (verificado en vivo el 2026-08-10):

  - Hipercor devuelve 403 "Access Denied" (Akamai) a TODA petición hecha
    en headless, incluida la portada sin cookies. Con navegador visible,
    la misma URL devuelve 200 y los productos.
  - Mercadona carga la página en headless, pero su buscador nunca llega a
    pedir los resultados (la SPA falla por dentro y solo se ve "Se ha
    vaciado el carro"). Con navegador visible devuelve los productos.

Probé también las contramedidas habituales en headless (User-Agent real,
--disable-blink-features=AutomationControlled, ocultar navigator.webdriver)
y NO bastan: ambos siguen bloqueando. Por eso se abre un navegador de
verdad, pero colocado fuera de la pantalla (--window-position) para que no
moleste mientras se hace la búsqueda.
"""

from __future__ import annotations

# User-Agent de un Chrome real: el de Playwright delata que es automático.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# La ventana existe (si no, nos bloquean) pero se abre fuera de la pantalla.
ARGS_NAVEGADOR = [
    "--window-position=-2400,-2400",
    "--disable-blink-features=AutomationControlled",
]


def importar_playwright():
    """Importa Playwright con un mensaje claro si no está instalado."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Falta playwright. Instala con: pip install playwright "
            "&& playwright install chromium"
        ) from e
    return sync_playwright


def nuevo_contexto(playwright, headless: bool = False):
    """Abre un navegador y un contexto ya configurados. Devuelve (browser, context)."""
    browser = playwright.chromium.launch(headless=headless, args=ARGS_NAVEGADOR)
    context = browser.new_context(
        locale="es-ES",
        user_agent=USER_AGENT,
        viewport={"width": 1366, "height": 900},
    )
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    return browser, context


# Cuántas búsquedas seguidas pueden irse en blanco antes de dar por
# perdido el supermercado entero. Si está bloqueado, cada búsqueda agota
# su espera completa (25 s), así que una lista de 10 productos serían más
# de 4 minutos tirados para acabar sin nada.
FALLOS_SEGUIDOS_PARA_RENDIRSE = 2


class SupermercadoCaido(RuntimeError):
    """El supermercado no responde: no tiene sentido seguir intentándolo."""


def aceptar_cookies(page) -> None:
    """Cierra el aviso de cookies si aparece (si no aparece, no pasa nada)."""
    try:
        page.click("text=Aceptar", timeout=5000)
    except Exception:
        pass
