"""
Conector para Alcampo (compraonline.alcampo.es), zona de Gijón (Porceyo).

Verificado en vivo el 2026-11-03 (navegador del escritorio, como invitado):

  - Es una tienda tipo Ocado (SPA con renderizado en servidor) protegida con
    AWS WAF (cookie `aws-waf-token`). Por eso se usa un navegador real
    visible, igual que Hipercor y Mercadona (ver navegador.py), en vez de
    `requests`: reproducir a mano la secuencia de API que fija la zona
    (addresses/areas -> by-coordinates -> temporary-delivery-destinations)
    no está verificado y el WAF puede bloquearla.
  - La ZONA IMPORTA: por defecto un invitado cae en "Entrega: 28029"
    (Madrid) y al cambiar a Gijón cambia el `regionId` y algunos precios
    (yogur natural AUCHAN 8x125 g: 1,40 € en Madrid, 1,39 € en Gijón; la web
    avisa de que "los precios y la disponibilidad pueden cambiar").
    Sin cookie de zona visible: se fija con el formulario de la propia web:
      1. botón "Cambia tu método de entrega" -> "Cambiar el método de entrega"
      2. campo "Busca tu dirección": "Porceyo Gijón" -> sugerencia
         "Porceyo, 33392 Gijón, Asturias, España"
      3. "Confirmar ubicación" -> diálogo "Elegir método de entrega": radio
         "Entrega" -> "Confirmar"
      4. la cabecera pasa a "Entrega: 33392"
    Si la zona no queda fijada se lanza SupermercadoCaido: mejor fallar que
    enseñar precios de Madrid como si fueran de Gijón.
  - Búsqueda: /search?q={texto}. El HTML trae `window.__INITIAL_STATE__` con
    `data.products.productEntities`: los 50 primeros resultados ya con
    marca, nombre, `price.current.amount` y `price.unit` (precio por kg,
    litro, 100 g, docena o unidad, según `price.unit.label`). Los resultados
    de más allá del 50 no vienen decorados; no se han necesitado.
  - No hay EAN; sí `available` (false = no se puede comprar ahora).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

from .base import Producto, Supermercado
from .medidas import precio_por_medida
from .navegador import (
    FALLOS_SEGUIDOS_PARA_RENDIRSE,
    SupermercadoCaido,
    importar_playwright,
    nuevo_contexto,
)

BASE_URL = "https://www.compraonline.alcampo.es"

DIAGNOSTICO = Path(__file__).resolve().parent.parent.parent / "diag"

# Pausa entre búsquedas seguidas. Alcampo (AWS WAF) muestra un CAPTCHA
# ("Human Verification") si se le pide deprisa: verificado el 2026-11-04 con
# ~25 peticiones en 10 s. Con navegador real y estas pausas se evita.
PAUSA_ENTRE_BUSQUEDAS_MS = 4000


class BloqueoWAF(SupermercadoCaido):
    """El WAF de Alcampo ha pedido verificación humana (CAPTCHA). No se
    reintenta, ni se intenta resolver ni esquivar: hay que esperar un rato."""

_JS_HAY_CAPTCHA = """() => {
  const t = (document.title + ' ' + (document.body ? document.body.innerText : '')).toLowerCase();
  return t.includes('human verification') || t.includes('verificación humana')
    || !!document.querySelector('#captcha-container, [id*=captcha]');
}"""

# Clics que se hacen con JavaScript porque en la web real (verificado a mano
# el 2026-11-03) funcionan donde un locator de Playwright puede toparse con
# nodos ocultos (la sugerencia aparece duplicada para lectores de pantalla)
# o con radios estilizados no visibles.
_JS_ELEGIR_SUGERENCIA = """(texto) => {
  const hojas = [...document.querySelectorAll('[role=dialog] *')]
    .filter(e => e.children.length === 0 && e.textContent.trim().startsWith(texto));
  if (!hojas.length) return false;
  (hojas[0].closest('li,[role=option],button,div') || hojas[0]).click();
  return true;
}"""
# Tras elegir la sugerencia, el mapa tarda ~1 s en moverse: hasta entonces
# "Entregar en:" sigue mostrando el punto por defecto (Puerta del Sol, 28013
# Madrid) y confirmar en ese momento fija MADRID. Verificado en vivo el
# 2026-11-03: fue la causa real del primer fallo en el PC de Igor.
_JS_DIRECCION_ELEGIDA = """(cp) => {
  const d = [...document.querySelectorAll('[role=dialog]')]
    .find(x => /Comprobación de si podemos hacerte entregas/.test(x.innerText));
  if (!d) return false;
  const t = d.innerText;
  const i = t.indexOf('Entregar en');
  return i >= 0 && t.slice(i, i + 200).includes(cp);
}"""
_JS_ELEGIR_ENTREGA = """() => {
  const d = [...document.querySelectorAll('[role=dialog]')]
    .find(x => /Elegir método de entrega/.test(x.innerText));
  if (!d) return false;
  const radios = [...d.querySelectorAll('input[type=radio]')];
  const entrega = radios.find(r => r.labels && r.labels[0] && /^Entrega/.test(r.labels[0].innerText.trim()))
    || radios[0];
  if (!entrega) return false;
  entrega.click();
  return true;
}"""

# etiqueta de price.unit.label -> (unidad, multiplicador para pasarlo a kg/L)
_UNIDADES = {
    "fop.price.per.kg": ("kg", 1.0),
    "fop.price.per.litre": ("L", 1.0),
    "fop.price.per.100gram": ("kg", 10.0),  # 2,00 €/100 g = 20,00 €/kg
    "fop.price.per.dozen": ("docena", 1.0),
}


def entidad_a_producto(ent: dict, nombre_buscado: str = "") -> Optional[Producto]:
    """Convierte un elemento de `productEntities` en un Producto. None si el
    producto no se puede comprar ahora (`available` falso) o no trae precio."""
    if not ent.get("available", True):
        return None
    precio_info = ent.get("price") or {}
    try:
        precio = float(precio_info["current"]["amount"])
    except (KeyError, TypeError, ValueError):
        return None

    nombre_real = (ent.get("name") or "").strip()
    unidad_info = precio_info.get("unit") or {}
    unidad, factor = _UNIDADES.get(unidad_info.get("label", ""), ("", 0.0))
    precio_unidad: Optional[float] = None
    if unidad:
        try:
            precio_unidad = round(float(unidad_info["current"]["amount"]) * factor, 2)
        except (KeyError, TypeError, ValueError):
            precio_unidad, unidad = None, ""
    if precio_unidad is None:
        # "fop.price.per.each" (precio por unidad) u otra etiqueta: se intenta
        # con el formato que va dentro del nombre ("... 6 x 1 l").
        precio_unidad, unidad = precio_por_medida(precio, nombre_real)

    pid = ent.get("retailerProductId")
    return Producto(
        nombre_buscado=nombre_buscado,
        nombre_real=nombre_real,
        precio=precio,
        marca=(ent.get("brand") or "").strip(),
        unidad=unidad,
        precio_unidad=precio_unidad,
        url=f"{BASE_URL}/products/{pid}" if pid else "",  # redirige a la ficha
    )


class Alcampo(Supermercado):
    nombre = "Alcampo"

    def __init__(
        self,
        buscar_direccion: str = "Porceyo Gijón",
        sugerencia: str = "Porceyo, 33392",
        cp_esperado: str = "33392",
        headless: bool = False,
    ):
        # Como CENTROS_CONOCIDOS en Hipercor: si cambias de tienda/zona,
        # cambia estos tres valores (lo que se teclea, la sugerencia que
        # aparece y el CP que la cabecera debe mostrar después).
        self.buscar_direccion = buscar_direccion
        self.sugerencia = sugerencia
        self.cp_esperado = cp_esperado
        self.headless = headless
        self.diagnostico = ""  # en qué paso falló la última vez que no se pudo fijar la zona
        self.metodo_sugerencia = ""  # qué forma de elegir la sugerencia funcionó

    def buscar_productos(self, nombre_producto: str) -> List[Producto]:
        return self.buscar_productos_multiples([nombre_producto]).get(nombre_producto, [])

    def buscar_productos_multiples(self, terminos: List[str]) -> Dict[str, List[Producto]]:
        """Busca varios términos con UN solo navegador (arrancarlo tarda)."""
        sync_playwright = importar_playwright()
        resultado: Dict[str, List[Producto]] = {}
        with sync_playwright() as p:
            browser, context = nuevo_contexto(p, headless=self.headless)
            # El mapa del selector pide la ubicación al abrirse (sin permiso
            # sale el aviso "se deben activar los permisos de ubicación"). Se
            # le da la de la propia tienda de Porceyo, no la del usuario.
            try:
                context.grant_permissions(["geolocation"], origin=BASE_URL)
                context.set_geolocation({"latitude": 43.5098, "longitude": -5.7253})
            except Exception:
                pass
            page = context.new_page()
            try:
                if not self._fijar_zona(page):
                    raise SupermercadoCaido(
                        f"No se pudo fijar la zona de entrega ({self.cp_esperado}): "
                        f"{self.diagnostico or 'causa desconocida'}. "
                        "Sin ella saldrían precios de Madrid."
                    )
                fallos_seguidos = 0
                for n, termino in enumerate(terminos):
                    if n:
                        page.wait_for_timeout(PAUSA_ENTRE_BUSQUEDAS_MS)
                    opciones = self._buscar_uno(page, termino)
                    if opciones is None:
                        fallos_seguidos += 1
                        resultado[termino] = []
                        if fallos_seguidos >= FALLOS_SEGUIDOS_PARA_RENDIRSE:
                            raise SupermercadoCaido(
                                "No responde (varias búsquedas seguidas sin cargar)."
                            )
                    else:
                        fallos_seguidos = 0
                        resultado[termino] = opciones
            finally:
                browser.close()
        return resultado

    def _fijar_zona(self, page) -> bool:
        """Elige la zona con el formulario de la propia web. True si la
        cabecera acaba mostrando 'Entrega: <cp>'. Si falla, deja en
        self.diagnostico el paso exacto y guarda una captura en diag/."""
        paso = "abrir la portada"
        try:
            page.goto(f"{BASE_URL}/")
            page.wait_for_timeout(3000)
            paso = "rechazar cookies"
            try:  # lo más privado: rechazar las cookies no esenciales
                page.get_by_role("button", name="Rechazar cookies").first.click(timeout=5000)
            except Exception:
                pass  # puede no aparecer
            paso = "abrir 'Cambia tu método de entrega'"
            page.get_by_role("button", name=re.compile("Cambia tu método de entrega")).first.click(timeout=10000)
            paso = "abrir 'Cambiar el método de entrega'"
            page.get_by_role("button", name="Cambiar el método de entrega").click(timeout=10000)
            paso = "escribir la dirección en 'Busca tu dirección'"
            # Todo acotado al diálogo: la página tiene DOS input#search (el
            # buscador general y el de dirección) - verificado el 2026-11-03.
            dialogo = page.get_by_role("dialog").filter(has_text="Comprobación de si podemos hacerte entregas")
            buscador = dialogo.get_by_placeholder("Busca tu dirección")
            opcion = dialogo.locator("[role=listbox] [role=option]").filter(has_text=self.sugerencia).first

            def escribir() -> None:
                # Tecla a tecla (eventos de teclado reales), no pegado de golpe.
                buscador.click(timeout=10000)
                buscador.fill("")
                buscador.press_sequentially(self.buscar_direccion, delay=60)
                opcion.wait_for(state="visible", timeout=15000)

            escribir()
            paso = f"elegir la sugerencia '{self.sugerencia}' y que el mapa se mueva a {self.cp_esperado}"
            # Verificado en vivo (2026-11-03): un clic sintético por JavaScript
            # cerraba la lista pero NO seleccionaba (el mapa seguía en Madrid).
            # Se prueban métodos de más a menos "humanos" hasta que el diálogo
            # muestre "Entregar en: ... <cp>"; el que funcione queda anotado.
            metodos = [
                ("clic real en la opción", lambda: opcion.click(timeout=5000)),
                ("teclado (flecha abajo + Enter)", lambda: (buscador.press("ArrowDown"), buscador.press("Enter"))),
                ("clic por JavaScript", lambda: page.evaluate(_JS_ELEGIR_SUGERENCIA, self.sugerencia)),
            ]
            fallidos = []
            for nombre_metodo, accion in metodos:
                try:
                    accion()
                    page.wait_for_function(_JS_DIRECCION_ELEGIDA, arg=self.cp_esperado, timeout=6000)
                    self.metodo_sugerencia = nombre_metodo
                    break
                except Exception as e:
                    fallidos.append(f"{nombre_metodo}: {type(e).__name__}")
                    try:
                        escribir()  # la lista suele cerrarse tras un intento fallido
                    except Exception:
                        pass
            else:
                raise RuntimeError("ningún método movió el mapa (" + "; ".join(fallidos) + ")")
            paso = "pulsar 'Confirmar ubicación'"
            page.get_by_role("button", name="Confirmar ubicación").click(timeout=15000)
            paso = "elegir 'Entrega' en el diálogo de método de entrega"
            for _ in range(30):
                if page.evaluate(_JS_ELEGIR_ENTREGA):
                    break
                page.wait_for_timeout(500)
            else:
                raise RuntimeError("no apareció el diálogo 'Elegir método de entrega'")
            paso = "pulsar 'Confirmar' del método de entrega"
            page.get_by_role("button", name="Confirmar", exact=True).click(timeout=15000)
            paso = f"comprobar que la cabecera muestra 'Entrega: {self.cp_esperado}'"
            page.wait_for_function(
                # Tras confirmar, la web recarga y durante un instante no hay
                # <body>: sin esta guarda el TypeError abortaba la espera
                # (fallo real del 2026-11-04) en vez de reintentar.
                "(cp) => !!document.body && document.body.innerText.includes('Entrega: ' + cp)",
                arg=self.cp_esperado,
                timeout=20000,
            )
            return True
        except Exception as e:
            primera_linea = (str(e).strip().splitlines() or [""])[0][:200]
            self.diagnostico = f"falló al {paso} ({type(e).__name__}: {primera_linea})"
            self._guardar_diagnostico(page)
            return False

    @staticmethod
    def _guardar_diagnostico(page) -> None:
        """Captura y texto de la página en diag/ para ver qué pasó."""
        try:
            DIAGNOSTICO.mkdir(exist_ok=True)
            page.screenshot(path=str(DIAGNOSTICO / "alcampo_fallo.png"))
            (DIAGNOSTICO / "alcampo_fallo.txt").write_text(
                f"{page.url}\n\n{page.inner_text('body')[:4000]}", encoding="utf-8"
            )
        except Exception:
            pass

    @staticmethod
    def _buscar_uno(page, termino: str) -> Optional[List[Producto]]:
        """Opciones encontradas, [] si no vende eso, o None si no cargó."""
        page.goto("about:blank")  # como en Mercadona: evita leer la búsqueda anterior
        page.goto(f"{BASE_URL}/search?q={quote(termino)}")
        try:
            page.wait_for_function(
                "() => window.__INITIAL_STATE__ && window.__INITIAL_STATE__.data"
                " && window.__INITIAL_STATE__.data.products",
                timeout=25000,
            )
        except Exception:
            # Sin estado: ¿CAPTCHA del WAF o simple caída? Se distingue para no
            # seguir pidiendo (empeora el bloqueo) y para dar el motivo real.
            try:
                captcha = page.evaluate(_JS_HAY_CAPTCHA)
            except Exception:
                captcha = False
            Alcampo._guardar_diagnostico(page)
            if captcha:
                raise BloqueoWAF(
                    "Alcampo pide verificación humana (CAPTCHA) por exceso de peticiones. "
                    "Espera al menos 1 hora sin usarlo y vuelve a probar."
                )
            return None  # bloqueo o caída, no "no lo venden"
        entidades = page.evaluate(
            "() => Object.values(window.__INITIAL_STATE__.data.products.productEntities || {})"
        )
        opciones = []
        for ent in entidades:
            producto = entidad_a_producto(ent, termino)
            if producto is not None:
                opciones.append(producto)
        return opciones


def test_conexion(termino: str = "leche entera") -> None:
    a = Alcampo()
    print(f"Buscando '{termino}' en Alcampo (Gijón, Porceyo)...")
    opciones = a.buscar_productos(termino)
    print(f"Zona fijada eligiendo la sugerencia por: {a.metodo_sugerencia or '?'}")
    print(f"{len(opciones)} opciones encontradas:")
    for o in opciones[:10]:
        print(" ", o)


if __name__ == "__main__":
    test_conexion()
