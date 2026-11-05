"""
Backend local del comparador de supermercados.

Es un servidor Flask sencillo pensado para ejecutarse en tu ordenador
(con tu conexión a internet real). Sirve la interfaz web (PWA) y expone
un endpoint que ejecuta la comparación de precios de verdad.

Uso:
    pip install -r ../requirements.txt
    pip install flask
    python app.py
    -> abre http://localhost:5000 en el navegador

Este mismo código es la base para migrarlo más adelante a una Azure
Function (la lógica de negocio ya está separada en src/, aquí solo hay
"pegamento" HTTP).
"""

import hmac
import os
import sys
import threading
import time
from collections import deque
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # para importar cache.py

from src.supermarkets import Mercadona, Hipercor, Alimerka, Alcampo, MasYMas
from src.supermarkets.base import Producto, filtrar_relevantes

import cache

app = Flask(__name__, static_folder="static", static_url_path="")

# --- Protecciones del modo LAN ------------------------------------------
# El servidor escucha en 0.0.0.0, así que cualquier dispositivo de la red
# puede llamarlo. Cada búsqueda con Hipercor/Mercadona/Alcampo abre un
# navegador real, y Akamai/AWS WAF bloquean cuando ven demasiadas visitas:
# conviene que no se pueda disparar eso sin límite.
MAX_PRODUCTOS = 60            # líneas de la lista por petición
MAX_LARGO_NOMBRE = 100        # caracteres por producto
LIMITE_PETICIONES = 40        # /api/buscar por IP y ventana
VENTANA_SEGUNDOS = 60         # (el frontend hace 1 por súper: ~5 por búsqueda)

# Un solo scraping a la vez por supermercado. Si dos dispositivos buscan a la
# vez, el segundo ESPERA y luego encuentra los precios ya en caché, en vez de
# abrir dos navegadores contra la misma web.
_CERROJOS_SUPER = {
    nombre: threading.Lock()
    for nombre in ("Hipercor", "Alimerka", "Mercadona", "Alcampo", "Más y Más")
}

_visitas: dict = {}
_visitas_guardia = threading.Lock()


def _supera_limite(ip: str) -> bool:
    """Ventana deslizante en memoria por IP (suficiente para uso doméstico)."""
    ahora = time.monotonic()
    with _visitas_guardia:
        cola = _visitas.setdefault(ip, deque())
        while cola and ahora - cola[0] > VENTANA_SEGUNDOS:
            cola.popleft()
        if len(cola) >= LIMITE_PETICIONES:
            return True
        cola.append(ahora)
        return False


def _es_local() -> bool:
    return request.remote_addr in ("127.0.0.1", "::1")


def _token_valido() -> bool:
    """Si BUSCAPRECIOS_TOKEN está definido, se acepta con cabecera X-Token."""
    esperado = os.environ.get("BUSCAPRECIOS_TOKEN", "")
    enviado = request.headers.get("X-Token", "")
    return bool(esperado) and hmac.compare_digest(esperado, enviado)


def _limpiar_productos(crudo) -> list:
    """Lista de nombres sin vacíos ni duplicados, o lanza ValueError."""
    if not isinstance(crudo, list):
        raise ValueError("'productos' debe ser una lista")
    vistos, limpios = set(), []
    for p in crudo:
        if not isinstance(p, str):
            raise ValueError("Cada producto debe ser un texto")
        p = p.strip()
        if not p or p in vistos:
            continue
        if len(p) > MAX_LARGO_NOMBRE:
            raise ValueError(f"Nombre de producto demasiado largo (máx. {MAX_LARGO_NOMBRE})")
        vistos.add(p)
        limpios.append(p)
    if len(limpios) > MAX_PRODUCTOS:
        raise ValueError(f"Demasiados productos (máx. {MAX_PRODUCTOS})")
    return limpios


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


def _producto_a_dict(supermercado: str, p: Producto) -> dict:
    return {
        "supermercado": supermercado,
        "nombre_real": p.nombre_real,
        "marca": p.marca,
        "precio": p.precio,
        "unidad": p.unidad,
        "precio_unidad": p.precio_unidad,
        "url": p.url,
    }


@app.route("/api/buscar", methods=["POST"])
def api_buscar():
    """
    Para cada producto de la lista, devuelve TODAS las opciones
    encontradas en cada supermercado (no solo la más barata), ordenadas
    de más barata a más cara. Así la interfaz puede enseñarte el abanico
    completo (todas las leches, todas las marcas, etc.) y avisarte si lo
    que eliges existe más barato en otro sitio.
    """
    if _supera_limite(request.remote_addr or "?"):
        return jsonify({"error": "Demasiadas búsquedas seguidas; espera un minuto"}), 429

    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Cuerpo de la petición no válido"}), 400
    cp = str(body.get("cp", "")).strip()
    try:
        productos = _limpiar_productos(body.get("productos", []))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    incluir_hipercor = bool(body.get("incluir_hipercor", True))
    incluir_alimerka = bool(body.get("incluir_alimerka", True))
    incluir_mercadona = bool(body.get("incluir_mercadona", True))
    # Los nuevos van por defecto a False: un app.js viejo en caché (que no
    # los envía) no debe lanzar de pronto búsquedas en ellos.
    incluir_alcampo = bool(body.get("incluir_alcampo", False))
    incluir_masymas = bool(body.get("incluir_masymas", False))

    if not cp:
        return jsonify({"error": "Falta el código postal"}), 400
    if not productos:
        return jsonify({"error": "La lista de la compra está vacía"}), 400
    if not (incluir_hipercor or incluir_alimerka or incluir_mercadona
            or incluir_alcampo or incluir_masymas):
        return jsonify({"error": "Elige al menos un supermercado"}), 400

    opciones_por_producto = {p: [] for p in productos}
    # Un fallo en un supermercado no debe tumbar la búsqueda entera, pero
    # tampoco puede desaparecer en silencio: si no se avisa, no hay forma
    # de distinguir "ese súper no vende esto" de "ese súper está caído o
    # bloqueado". Se recogen aquí y se devuelven junto a los resultados.
    avisos = []
    hubo_cache = False
    forzar = bool(body.get("forzar", False))

    def _pendientes(supermercado: str) -> list:
        """
        Productos que hay que buscar de verdad: los que no estén ya en la
        caché se piden a la web; el resto se sirven de lo guardado.
        """
        nonlocal hubo_cache
        if forzar:
            return list(productos)
        pendientes = []
        for nombre in productos:
            guardado = cache.leer(supermercado, cp, nombre)
            if guardado is None:
                pendientes.append(nombre)
            else:
                opciones_por_producto[nombre].extend(guardado)
                hubo_cache = True
        return pendientes

    def _registrar(supermercado: str, nombre: str, productos_encontrados) -> None:
        opciones = [
            _producto_a_dict(supermercado, opt)
            for opt in filtrar_relevantes(nombre, productos_encontrados)
        ]
        opciones_por_producto[nombre].extend(opciones)
        cache.guardar(supermercado, cp, nombre, opciones)

    # Alimerka es rápido (requests normal): una búsqueda por producto.
    # Hipercor y Mercadona necesitan navegador real (ver navegador.py), así
    # que reutilizan un solo navegador para toda la lista.
    if incluir_hipercor:
        with _CERROJOS_SUPER["Hipercor"]:
            pendientes = _pendientes("Hipercor")
            if pendientes:
                try:
                    resultado = Hipercor(cp).buscar_productos_multiples(pendientes)
                    for nombre, opts in resultado.items():
                        _registrar("Hipercor", nombre, opts)
                except Exception as e:
                    avisos.append({"supermercado": "Hipercor", "motivo": str(e) or type(e).__name__})

    if incluir_alimerka:
        with _CERROJOS_SUPER["Alimerka"]:
            pendientes = _pendientes("Alimerka")
            if pendientes:
                alimerka = Alimerka(cp)
                fallos = []
                for nombre in pendientes:
                    try:
                        _registrar("Alimerka", nombre, alimerka.buscar_productos(nombre))
                    except Exception as e:
                        fallos.append(f"{nombre}: {e or type(e).__name__}")
                if fallos:
                    avisos.append({"supermercado": "Alimerka", "motivo": "; ".join(fallos)})

    if incluir_mercadona:
        with _CERROJOS_SUPER["Mercadona"]:
            pendientes = _pendientes("Mercadona")
            if pendientes:
                try:
                    resultado = Mercadona(cp).buscar_productos_multiples(pendientes)
                    for nombre, opts in resultado.items():
                        _registrar("Mercadona", nombre, opts)
                except Exception as e:
                    avisos.append({"supermercado": "Mercadona", "motivo": str(e) or type(e).__name__})

    if incluir_alcampo:
        with _CERROJOS_SUPER["Alcampo"]:
            # Navegador real (AWS WAF) y zona de Gijón fijada por el propio
            # conector: no usa el CP de la petición.
            pendientes = _pendientes("Alcampo")
            if pendientes:
                try:
                    resultado = Alcampo().buscar_productos_multiples(pendientes)
                    for nombre, opts in resultado.items():
                        _registrar("Alcampo", nombre, opts)
                except Exception as e:
                    avisos.append({"supermercado": "Alcampo", "motivo": str(e) or type(e).__name__})

    if incluir_masymas:
        with _CERROJOS_SUPER["Más y Más"]:
            # Tienda online de Asturias (requests normal, como Alimerka).
            pendientes = _pendientes("Más y Más")
            if pendientes:
                masymas = MasYMas()
                fallos = []
                for nombre in pendientes:
                    try:
                        _registrar("Más y Más", nombre, masymas.buscar_productos(nombre))
                    except Exception as e:
                        fallos.append(f"{nombre}: {e or type(e).__name__}")
                if fallos:
                    avisos.append({"supermercado": "Más y Más", "motivo": "; ".join(fallos)})

    resultados = []
    for nombre in productos:
        opciones = sorted(opciones_por_producto[nombre], key=lambda o: o["precio"])
        resultados.append({"producto": nombre, "opciones": opciones})

    # Un supermercado que no dio error pero tampoco devolvió NADA en toda
    # la lista es sospechoso (bloqueo silencioso, cambio de la web...).
    pedidos = {
        "Hipercor": incluir_hipercor,
        "Alimerka": incluir_alimerka,
        "Mercadona": incluir_mercadona,
        "Alcampo": incluir_alcampo,
        "Más y Más": incluir_masymas,
    }
    ya_avisados = {a["supermercado"] for a in avisos}
    for nombre_super, pedido in pedidos.items():
        if not pedido or nombre_super in ya_avisados:
            continue
        total = sum(
            1
            for opciones in opciones_por_producto.values()
            for o in opciones
            if o["supermercado"] == nombre_super
        )
        if total == 0:
            avisos.append({
                "supermercado": nombre_super,
                "motivo": "No devolvió ningún resultado para toda la lista.",
            })

    return jsonify({"resultados": resultados, "avisos": avisos, "desde_cache": hubo_cache})


@app.route("/api/cache", methods=["DELETE"])
def api_limpiar_cache():
    """
    Tirar los precios guardados para volver a mirarlos todos en vivo.

    Solo desde este mismo ordenador, o desde la red con la cabecera X-Token
    si se definió BUSCAPRECIOS_TOKEN: vaciar la caché obliga a repetir todos
    los scrapings, así que no debe poder hacerlo cualquier dispositivo.
    """
    if not (_es_local() or _token_valido()):
        return jsonify({"error": "No autorizado"}), 403
    cache.limpiar()
    return jsonify({"ok": True})


@app.route("/api/health")
def api_health():
    """Para que el frontend sepa si hay backend (modo LAN) o es un sitio estático."""
    return jsonify({"ok": True})


@app.route("/manifest.json")
def manifest():
    return send_from_directory(app.static_folder, "manifest.json")


@app.route("/sw.js")
def service_worker():
    return send_from_directory(app.static_folder, "sw.js")


if __name__ == "__main__":
    import socket

    # Modo LAN: escucha en todas las interfaces para que otros dispositivos
    # de la misma red (móvil, portátil de casa) puedan entrar por IP.
    # Se puede sobreescribir con variables de entorno si hace falta.
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("DEBUG", "0") == "1"
    # El depurador de Werkzeug permite ejecutar código Python desde el
    # navegador. Con host 0.0.0.0 lo tendría cualquiera de la red: nunca.
    if debug and host not in ("127.0.0.1", "localhost", "::1"):
        print("AVISO: DEBUG ignorado porque el servidor escucha fuera de localhost.")
        debug = False

    ip_lan = "IP-de-este-ordenador"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip_lan = s.getsockname()[0]
    except OSError:
        pass

    print(f"* Accesible en este PC:        http://localhost:{port}")
    print(f"* Accesible desde otros PCs/móviles de casa: http://{ip_lan}:{port}")
    print("  (si no carga desde otro dispositivo, revisa el Firewall de Windows:")
    print("   puede pedir permiso la primera vez que arranque el servidor)")

    app.run(host=host, port=port, debug=debug)
