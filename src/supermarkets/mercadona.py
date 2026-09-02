from __future__ import annotations

from typing import Any

from .base import ProductoEncontrado, Supermercado


class Mercadona(Supermercado):
    _catalogo_simulado: dict[str, list[tuple[str, float, float, str]]] = {
        "leche": [
            ("Leche entera Hacendado 1L", 0.98, 1.0, "l"),
            ("Leche sin lactosa Hacendado 1L", 1.18, 1.0, "l"),
        ],
        "arroz": [
            ("Arroz redondo Hacendado 1kg", 1.52, 1.0, "kg"),
            ("Arroz basmati Hacendado 1kg", 1.95, 1.0, "kg"),
        ],
        "pan": [("Pan de molde blanco Hacendado 820g", 1.58, 0.82, "kg")],
    }

    @property
    def nombre(self) -> str:
        return "mercadona"

    def buscar_productos(self, nombre_producto: str) -> list[dict[str, Any]]:
        # Nota: en scraping real con Playwright, mantener headless=False.
        # Hipercor y Mercadona bloquean o no renderizan correctamente en headless.
        clave = nombre_producto.strip().lower()
        resultados: list[dict[str, Any]] = []
        for termino, opciones in self._catalogo_simulado.items():
            if termino in clave or clave in termino:
                for nombre, precio, cantidad, unidad in opciones:
                    resultados.append(
                        ProductoEncontrado(nombre, precio, self.nombre, cantidad, unidad).como_diccionario()
                    )
        return resultados
