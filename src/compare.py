from __future__ import annotations

from math import inf
from typing import Any


def calcular_coste_real(opcion: dict[str, Any]) -> float:
    precio = float(opcion.get("precio", inf))
    cantidad = float(opcion.get("cantidad", 1) or 1)
    if cantidad <= 0:
        return precio
    return precio / cantidad


def _mejor_opcion(opciones: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not opciones:
        return None
    return min(opciones, key=calcular_coste_real)


def comparar_resultados(
    lista_compra: list[str],
    resultados_por_supermercado: dict[str, dict[str, list[dict[str, Any]]]],
) -> dict[str, Any]:
    detalle_mixto: dict[str, dict[str, Any]] = {}
    total_mixto = 0.0

    for producto in lista_compra:
        candidatas: list[dict[str, Any]] = []
        for supermercado, productos in resultados_por_supermercado.items():
            opcion = _mejor_opcion(productos.get(producto, []))
            if opcion is not None:
                candidatas.append(opcion | {"supermercado": supermercado})

        if candidatas:
            mejor = min(candidatas, key=calcular_coste_real)
            coste = calcular_coste_real(mejor)
            total_mixto += coste
            detalle_mixto[producto] = {
                "supermercado": mejor["supermercado"],
                "opcion": mejor,
                "coste_real": round(coste, 4),
            }
        else:
            detalle_mixto[producto] = {
                "supermercado": None,
                "opcion": None,
                "coste_real": None,
            }

    mejor_supermercado_unico = None
    mejor_total_unico = inf

    for supermercado, productos in resultados_por_supermercado.items():
        total_actual = 0.0
        productos_encontrados = 0
        for producto in lista_compra:
            opcion = _mejor_opcion(productos.get(producto, []))
            if opcion is None:
                continue
            total_actual += calcular_coste_real(opcion)
            productos_encontrados += 1

        if productos_encontrados == len(lista_compra) and total_actual < mejor_total_unico:
            mejor_total_unico = total_actual
            mejor_supermercado_unico = supermercado

    ahorro = 0.0 if mejor_total_unico == inf else max(0.0, mejor_total_unico - total_mixto)

    return {
        "mixto": {
            "total": round(total_mixto, 4),
            "detalle": detalle_mixto,
        },
        "supermercado_unico": {
            "nombre": mejor_supermercado_unico,
            "total": None if mejor_total_unico == inf else round(mejor_total_unico, 4),
        },
        "ahorro": round(ahorro, 4),
    }
