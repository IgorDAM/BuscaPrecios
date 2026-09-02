from __future__ import annotations

from typing import Any

from .base import ProductoEncontrado, Supermercado


class Hipercor(Supermercado):
    _catalogo_simulado: dict[str, list[tuple[str, float, float, str]]] = {
        "leche": [
            ("Leche entera El Corte Inglés 1L", 1.12, 1.0, "l"),
            ("Leche semidesnatada El Corte Inglés 1L", 1.09, 1.0, "l"),
        ],
        "arroz": [("Arroz redondo Hipercor 1kg", 1.59, 1.0, "kg")],
        "pan": [("Pan de molde Hipercor 820g", 1.67, 0.82, "kg")],
    }

    @property
    def nombre(self) -> str:
        return "hipercor"

    def buscar_productos(self, nombre_producto: str) -> list[dict[str, Any]]:
        # Nota: en scraping real con Playwright, mantener headless=False.
        clave = nombre_producto.strip().lower()
        resultados: list[dict[str, Any]] = []
        for termino, opciones in self._catalogo_simulado.items():
            if termino in clave or clave in termino:
                for nombre, precio, cantidad, unidad in opciones:
                    resultados.append(
                        ProductoEncontrado(nombre, precio, self.nombre, cantidad, unidad).como_diccionario()
                    )
        return resultados
