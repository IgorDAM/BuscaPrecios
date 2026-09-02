from __future__ import annotations

import json
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template, request

RAIZ_REPOSITORIO = Path(__file__).resolve().parents[1]
if str(RAIZ_REPOSITORIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_REPOSITORIO))

from src.compare import comparar_resultados
from src.supermarkets import crear_supermercados

app = Flask(__name__)


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/buscar")
def api_buscar():
    datos = request.get_json(silent=True) or {}
    codigo_postal = str(datos.get("codigo_postal", "")).strip()
    productos = [str(p).strip() for p in datos.get("productos", []) if str(p).strip()]
    supermercados = [str(s).strip().lower() for s in datos.get("supermercados", []) if str(s).strip()]

    if not codigo_postal:
        return jsonify({"error": "El código postal es obligatorio."}), 400
    if not productos:
        return jsonify({"error": "Debes indicar al menos un producto."}), 400
    if not supermercados:
        supermercados = ["mercadona", "hipercor", "alimerka"]

    conectores = crear_supermercados(codigo_postal, supermercados)
    resultados: dict[str, dict[str, list[dict]]] = {}
    for conector in conectores:
        resultados[conector.nombre] = {}
        for producto in productos:
            resultados[conector.nombre][producto] = conector.buscar_productos(producto)

    comparacion = comparar_resultados(productos, resultados)
    return jsonify({"resultados": resultados, "comparacion": comparacion})


if __name__ == "__main__":
    app.run()
