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

import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # para importar cache.py

from src.supermarkets import Mercadona, Hipercor, Alimerka
from src.supermarkets.base import Producto, filtrar_relevantes

import cache

app = Flask(__name__, static_folder="static", static_url_path="")


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
    body = request.get_json(force=True) or {}
    cp = str(body.get("cp", "")).strip()
    productos = body.get("productos", [])
    incluir_hipercor = bool(body.get("incluir_hipercor", True))
    incluir_alimerka = bool(body.get("incluir_alimerka", True))
    incluir_mercadona = bool(body.get("incluir_mercadona", True))

    if not cp:
        return jsonify({"error": "Falta el código postal"}), 400
    if not productos:
        return jsonify({"error": "La lista de la compra está vacía"}), 400
    if not (incluir_hipercor or incluir_alimerka or incluir_mercadona):
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
        pendientes = _pendientes("Hipercor")
        if pendientes:
            try:
                resultado = Hipercor(cp).buscar_productos_multiples(pendientes)
                for nombre, opts in resultado.items():
                    _registrar("Hipercor", nombre, opts)
            except Exception as e:
                avisos.append({"supermercado": "Hipercor", "motivo": str(e) or type(e).__name__})

    if incluir_alimerka:
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
        pendientes = _pendientes("Mercadona")
        if pendientes:
            try:
                resultado = Mercadona(cp).buscar_productos_multiples(pendientes)
                for nombre, opts in resultado.items():
                    _registrar("Mercadona", nombre, opts)
            except Exception as e:
                avisos.append({"supermercado": "Mercadona", "motivo": str(e) or type(e).__name__})

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
    """Tirar los precios guardados para volver a mirarlos todos en vivo."""
    cache.limpiar()
    return jsonify({"ok": True})


@app.route("/manifest.json")
def manifest():
    return send_from_directory(app.static_folder, "manifest.json")


@app.route("/sw.js")
def service_worker():
    return send_from_directory(app.static_folder, "sw.js")


if __name__ == "__main__":
    import os
    import socket

    # Modo LAN: escucha en todas las interfaces para que otros dispositivos
    # de la misma red (móvil, portátil de casa) puedan entrar por IP.
    # Se puede sobreescribir con variables de entorno si hace falta.
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("DEBUG", "0") == "1"

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
