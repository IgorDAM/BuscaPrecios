"""
POST /api/buscar en Azure Static Web Apps (función gestionada, plan gratuito).

Solo atiende ALIMERKA en directo: es la única web que se puede consultar
con `requests` normal, sin navegador (Hipercor y Mercadona necesitan
Playwright y Akamai los bloquea desde IPs de nube). Para ellos responde
501 y el frontend cae solo a precios_generados.json (el del cron).

Mismo contrato que webapp/app.py: recibe {cp, productos, incluir_*} y
devuelve {resultados, avisos}. Los conectores NO viven aquí: el workflow
copia src/supermarkets/{base,medidas,alimerka}.py a api/_lib/supermarkets/
antes de desplegar (así no hay dos copias que se desincronicen).
"""
import json
import os
import sys

import azure.functions as func

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "_lib"))

from supermarkets.alimerka import Alimerka  # noqa: E402
from supermarkets.base import filtrar_relevantes  # noqa: E402

MAX_PRODUCTOS = 40  # límite razonable por petición (timeout de la función)


def _json(cuerpo: dict, estado: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(cuerpo, ensure_ascii=False),
        status_code=estado,
        mimetype="application/json",
    )


def _a_dict(p) -> dict:
    return {
        "supermercado": "Alimerka",
        "nombre_real": p.nombre_real,
        "marca": p.marca,
        "precio": p.precio,
        "unidad": p.unidad,
        "precio_unidad": p.precio_unidad,
        "url": p.url,
    }


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return _json({"error": "JSON no válido"}, 400)

    cp = str(body.get("cp", "")).strip()
    productos = body.get("productos", [])
    if not cp:
        return _json({"error": "Falta el código postal"}, 400)
    if not productos:
        return _json({"error": "La lista de la compra está vacía"}, 400)

    # Solo Alimerka en directo. Si piden Hipercor/Mercadona, 501 -> el
    # frontend usa los precios publicados por el cron.
    if body.get("incluir_hipercor") or body.get("incluir_mercadona") or not body.get("incluir_alimerka", True):
        return _json({"error": "Solo Alimerka se consulta en directo en la nube"}, 501)

    productos = productos[:MAX_PRODUCTOS]
    alimerka = Alimerka(cp)
    opciones_por_producto = {}
    fallos = []
    for nombre in productos:
        try:
            encontrados = alimerka.buscar_productos(nombre)
            opciones_por_producto[nombre] = [_a_dict(o) for o in filtrar_relevantes(nombre, encontrados)]
        except Exception as e:  # un producto que falla no tumba el resto
            opciones_por_producto[nombre] = []
            fallos.append(f"{nombre}: {e or type(e).__name__}")

    avisos = []
    if fallos:
        avisos.append({"supermercado": "Alimerka", "motivo": "; ".join(fallos)})
    elif not any(opciones_por_producto.values()):
        avisos.append({"supermercado": "Alimerka", "motivo": "No devolvió ningún resultado para toda la lista."})

    resultados = [
        {"producto": n, "opciones": sorted(opciones_por_producto[n], key=lambda o: o["precio"])}
        for n in productos
    ]
    return _json({"resultados": resultados, "avisos": avisos, "desde_cache": False, "origen": "nube"})
